import json
import os
import time
import asyncio
import argparse
import sys
from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum
import logging
# 移除并发处理相关导入，因为接口不支持并发调用

from module import (
    TokenManager,
    ApiClient,
    ImageStorage,
    ImageProcessor,
    AudioProcessor,
    VideoGenerator,
    TaskStatus,
    ConfigManager,
    ImageGenerationTask,
    BatchProcessor
)
from dotenv import load_dotenv
load_dotenv()

# 确保日志目录存在，并使用模块目录的绝对路径
BASE_DIR = os.path.dirname(__file__)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

# 配置日志格式和处理器
logging.basicConfig(
    level=logging.INFO,
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE_DIR, 'logs', 'jimeng.log'), encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# 常量定义


class JimengPlugin:
    """即梦插件主类"""
    
    def __init__(self, config_path: str | None = None, feijing_path: str | None = None):
        # 初始化配置管理器
        self.config_manager = ConfigManager(config_path)
        
        # 设置飞镜配置文件路径
        self.feijing_path = feijing_path or os.path.join(os.path.dirname(__file__), "feijing.json")
        
        # 生成下载子目录名
        self.download_subdir = self._get_download_subdir()
        
        self.generation_config = self.config_manager.get_generation_config()
        self.api_config = self.config_manager.get_api_config()
        self.audio_processor = AudioProcessor()
        
        # 初始化目录
        self._init_directories()
        
        # 初始化组件
        self._init_components()
        
        # 初始化批处理器（顺序处理，添加请求间隔防止限流）
        request_delay = self.config_manager.get("api.request_delay", 1.0)
        self.batch_processor = BatchProcessor(request_delay=request_delay)
        
        logger.info(f"[JimengPlugin] 插件初始化完成，数据保留天数: {self.config_manager.get('storage.retention_days', 7)}")
        logger.info(f"[JimengPlugin] 飞镜配置文件: {self.feijing_path}")
        logger.info(f"[JimengPlugin] 下载子目录: {self.download_subdir}")
    
    def _get_download_subdir(self) -> str:
        """根据飞镜配置文件路径生成下载子目录名"""
        if not self.feijing_path:
            return "default"
        
        # 获取文件名（不含扩展名）
        filename = os.path.splitext(os.path.basename(self.feijing_path))[0]
        
        # 如果是默认的 feijing.json，使用 default
        if filename == "feijing":
            return "default"
        
        # 否则使用文件名作为子目录名
        return filename
    
    def _init_directories(self) -> None:
        """初始化目录结构"""
        base_dir = os.path.dirname(__file__)
        
        # 创建必要目录
        directories = [
            os.path.join(base_dir, "storage"),
            os.path.join(base_dir, "logs"),
            os.path.join(base_dir, "downloads", self.download_subdir)
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.debug(f"[JimengPlugin] 创建目录: {directory}")
    
    def _init_components(self) -> None:
        """初始化组件"""
        base_dir = os.path.dirname(__file__)
        
        # 获取保留天数
        retention_days = self.config_manager.get("storage.retention_days", 7)
        
        # 初始化存储组件
        self.image_storage = ImageStorage(
            os.path.join(base_dir, "storage", "images.db"),
            retention_days=retention_days
        )
        
        # 初始化图片处理器
        self.image_processor = ImageProcessor(
            os.path.join(base_dir, "downloads", self.download_subdir)
        )
        
        # 初始化Token管理器
        self.token_manager = TokenManager(self.config_manager.config)
        
        # 初始化API客户端
        self.api_client = ApiClient(self.token_manager, self.config_manager.config, self.image_storage)
        
        # 初始化视频生成器
        self.video_generator = VideoGenerator()
    
    async def generate_image(self, prompt: str, model: str | None = None, ratio: str | None = None) -> str | None:
        """生成单张图片
        
        Args:
            prompt: 图片提示词
            model: 模型版本，默认使用配置中的默认模型
            ratio: 图片比例，默认使用配置中的默认比例
            
        Returns:
            str | None: 成功时返回submit_id，失败时返回None
        """
        # 使用配置中的默认值
        model = model or self.generation_config.model
        ratio = ratio or self.generation_config.ratio
        
        # 验证参数
        if not prompt or not prompt.strip():
            logger.error("[JimengPlugin] 提示词不能为空")
            return None
        
        # 检查配置是否完整
        if not self._validate_api_config():
            return None
        
        # 重试机制
        for attempt in range(self.generation_config.max_retries):
            try:
                submit_id = await asyncio.to_thread(self.api_client.generate_image, prompt, model, ratio)
                if submit_id:
                    # 存储图片信息
                    await self.image_storage.store_image(
                        submit_id,
                        metadata={
                            "prompt": prompt,
                            "model": model,
                            "ratio": ratio,
                            "type": "generate",
                            "attempt": attempt + 1
                        }
                    )
                    logger.info(f"[JimengPlugin] 图片生成成功，submit_id: {submit_id}")
                    return submit_id
                else:
                    logger.warning(f"[JimengPlugin] 图片生成失败，第 {attempt + 1} 次尝试")
                    
            except Exception as e:
                logger.error(f"[JimengPlugin] 图片生成异常 (第 {attempt + 1} 次): {e}")
            
            # 等待重试（使用非阻塞睡眠）
            if attempt < self.generation_config.max_retries - 1:
                await asyncio.sleep(self.generation_config.retry_delay)
        
        logger.error(f"[JimengPlugin] 图片生成失败，已重试 {self.generation_config.max_retries} 次")
        return None
    
    async def generate_images_batch(self, prompts: List[str], model: str | None = None, ratio: str | None = None) -> List[ImageGenerationTask]:
        """批量生成图片
        
        Args:
            prompts: 提示词列表
            model: 模型版本
            ratio: 图片比例
            
        Returns:
            List[ImageGenerationTask]: 任务列表
        """
        if not prompts:
            logger.warning("[JimengPlugin] 没有提供提示词")
            return []
        
        # 使用配置中的默认值
        model = model or self.generation_config.model
        ratio = ratio or self.generation_config.ratio
        
        # 创建任务
        for i, prompt in enumerate(prompts):
            task_id = f"batch_{int(time.time())}_{i}"
            task = ImageGenerationTask(
                task_id=task_id,
                prompt=prompt,
                model=model,
                ratio=ratio,
                metadata={"batch_index": i}
            )
            self.batch_processor.add_task(task)
        
        # 批量处理
        completed_tasks = await self.batch_processor.process_batch(
            self._generate_single_task
        )
        
        return completed_tasks
    
    async def _generate_single_task(self, task: ImageGenerationTask) -> str | None:
        """处理单个生成任务"""
        try:
            submit_id = await self.generate_image(task.prompt, task.model, task.ratio)
            return submit_id
        except Exception as e:
            logger.error(f"[JimengPlugin] 任务 {task.task_id} 处理失败: {e}")
            return None
    
    def _validate_api_config(self) -> bool:
        """验证API配置"""
        cookie = self.config_manager.get("video_api.cookie")
        sign = self.config_manager.get("video_api.sign")
        
        if not cookie or not sign:
            logger.error("[JimengPlugin] 请先在config.json中配置video_api的cookie和sign")
            return False
        
        return True
    
    async def wait_for_completion(self, submit_ids: List[str], timeout: int = 3600) -> Dict[str, List[str]]:
        """等待图片生成完成
        
        Args:
            submit_ids: 任务ID列表
            timeout: 超时时间（秒）
            
        Returns:
            Dict[str, List[str]]: 完成的任务ID和对应的图片URLs
        """
        if not submit_ids:
            return {}
        
        start_time = time.time()
        results = {}
        remaining_ids = submit_ids.copy()
        
        logger.info(f"[JimengPlugin] 等待 {len(submit_ids)} 个任务完成...")
        
        while remaining_ids and (time.time() - start_time) < timeout:
            completed_ids = []
            
            for submit_id in remaining_ids:
                try:
                    image_urls = await asyncio.to_thread(self.api_client.get_generated_images, submit_id)
                    if image_urls is not None:
                        results[submit_id] = image_urls
                        completed_ids.append(submit_id)
                        
                        # 更新存储
                        await self.image_storage.update_image(submit_id, image_urls)
                        logger.info(f"[JimengPlugin] 任务 {submit_id} 完成，获得 {len(image_urls)} 张图片")
                        
                except Exception as e:
                    logger.error(f"[JimengPlugin] 检查任务 {submit_id} 状态失败: {e}")
            
            # 移除已完成的任务（避免 O(n^2) 删除）
            if completed_ids:
                completed_set = set(completed_ids)
                remaining_ids = [sid for sid in remaining_ids if sid not in completed_set]
            
            if remaining_ids:
                await asyncio.sleep(2)  # 等待2秒后再次检查
        
        # 记录未完成的任务
        if remaining_ids:
            logger.warning(f"[JimengPlugin] {len(remaining_ids)} 个任务未在超时时间内完成")
        
        return results
    
    def load_feijing_config(self) -> List[Dict[str, Any]] | None:
        """加载飞镜配置"""
        try:
            with open(self.feijing_path, "r", encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"[JimengPlugin] 飞镜配置加载成功，包含 {len(config)} 个项目")
            return config
        except Exception as e:
            logger.error(f"[JimengPlugin] 飞镜配置加载失败: {e}")
            return None
    
    async def download_images_from_db(self) -> None:
        """从数据库中下载飞镜图片"""
        images = await self.image_storage.get_images_by_status(TaskStatus.ALL.value)
        
        feijing_config = self.load_feijing_config()
        if not feijing_config:
            logger.error("[JimengPlugin] 无法加载飞镜配置")
            return
        feijing_dict = {}
        for item in feijing_config:
            feijing_dict[item.get('提示词', '')] = item
        
        for index, item in enumerate(images):
            submit_id = item.get('id', '').strip()
            metadata = item.get('metadata', {})
            if not metadata:
                continue
            prompt = metadata.get('prompt', '')
            if not prompt:
                continue
            if prompt not in feijing_dict:
                continue
            feijing_item = feijing_dict[prompt]
            filename = f"分镜{index+1}"
            filename = feijing_item.get('编号', filename)
            if submit_id:
                image_urls = await asyncio.to_thread(self.api_client.get_generated_images, submit_id)
                if image_urls is not None:
                    await asyncio.to_thread(self.image_processor.download_image, filename, image_urls)
                    logger.info(f"[JimengPlugin] {submit_id} 已下载图片: {filename}")
    
    def text_to_speech(self, filename: str, text: str, generate_srt: bool = True) -> bool:
        """文本转语音并生成字幕文件
        
        Args:
            filename: 输出文件名（不含扩展名）
            text: 要转换的文本
            generate_srt: 是否生成SRT字幕文件
            
        Returns:
            bool: 是否成功
        """
        # 构建完整的文件路径（包含子目录和扩展名）
        base_dir = os.path.dirname(__file__)
        full_filename = os.path.join(base_dir, "downloads", self.download_subdir, f"{filename}.mp3")
        
        success = self.audio_processor.text_to_speech(
            filename=full_filename,
            text=text,
            generate_srt=generate_srt,
            merge_words=10
        )
        
        if success:
            logger.info(f"[JimengPlugin] 音频和字幕生成成功: {full_filename}")
        else:
            logger.error(f"[JimengPlugin] 音频和字幕生成失败: {full_filename}")
        return success
    
     
    def process_to_tts(self, voice_name: str = 'zh-CN-YunzeNeural') -> None:
        """飞镜转TTS
        
        Args:
            voice_name: 语音名称，默认为中文云泽神经语音
        """
        feijing_config = self.load_feijing_config()
        if not feijing_config:
            logger.error("[JimengPlugin] 无法加载飞镜配置")
            return
        
        logger.info(f"[JimengPlugin] 开始飞镜转TTS，使用语音: {voice_name}")
        
        success_count = 0
        total_count = len(feijing_config)
        
        for i, item in enumerate(feijing_config):
            filename = item.get('编号', '')
            text = item.get('原文', '')
            if not filename or not text:
                logger.warning(f"[JimengPlugin] 跳过第 {i+1} 项：缺少编号或原文")
                continue
            
            logger.info(f"[JimengPlugin] 处理第 {i+1}/{total_count} 项: {filename}")
            
            # 检查文件是否已存在（使用子目录路径）
            base_dir = os.path.dirname(__file__)
            full_filename = os.path.join(base_dir, "downloads", self.download_subdir, f"{filename}.mp3")
            if os.path.exists(full_filename):
                success_count += 1
                continue
                
            try:
                success = self.text_to_speech(filename, text)
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"[JimengPlugin] {full_filename} TTS处理异常: {e}")
        
        logger.info(f"[JimengPlugin] 飞镜转TTS完成: {success_count}/{total_count} 成功")
    
    async def process_images_batch(self, model: str = "3.1", ratio: str = "9:16", timeout: int = 3600) -> bool:
        """批量处理飞镜配置
        
        Args:
            model: 图片生成模型，默认为3.1
            ratio: 图片比例，默认为9:16
            timeout: 超时时间（秒），默认为3600秒
            
        Returns:
            bool: 是否成功处理
        """
        feijing_config = self.load_feijing_config()
        if not feijing_config:
            logger.error("[JimengPlugin] 无法加载飞镜配置")
            return False
        
        # 准备提示词列表
        prompts = []
        item_mapping = {}
        
        for item in feijing_config:
            prompt = item.get('提示词', '').strip()
            number = item.get('编号', '').strip()
            first_image_file = f"{number}_0.jpeg"
            if os.path.exists(self.image_processor.get_file_path(first_image_file)):
                continue
            if prompt:
                prompts.append(prompt)
                item_mapping[len(prompts) - 1] = item
        
        if not prompts:
            logger.info("[JimengPlugin] 图片已经生成完成")
            return True
        
        logger.info(f"[JimengPlugin] 开始批量处理 {len(prompts)} 个提示词...")
        logger.info(f"[JimengPlugin] 使用模型: {model}, 比例: {ratio}, 超时: {timeout}秒")
        
        # 批量生成图片
        tasks = await self.generate_images_batch(prompts, model, ratio)
        
        # 收集成功的任务
        successful_tasks = [task for task in tasks if task.status == TaskStatus.COMPLETED]
        failed_tasks = [task for task in tasks if task.status == TaskStatus.FAILED]
        
        logger.info(f"[JimengPlugin] 生成完成: {len(successful_tasks)} 成功, {len(failed_tasks)} 失败")
        
        if not successful_tasks:
            logger.error("[JimengPlugin] 没有成功生成的任务")
            return False
        
        # 等待所有任务完成
        submit_ids = [task.result for task in successful_tasks if task.result]
        results = await self.wait_for_completion(submit_ids, timeout)
        
        # 下载图片
        download_count = 0
        for i, task in enumerate(successful_tasks):
            if task.result and task.result in results:
                try:
                    item = item_mapping.get(task.metadata.get('batch_index', i))
                    if item:
                        number = item.get('编号', f'img_{i}')
                        image_urls = results[task.result]
                        await asyncio.to_thread(self.image_processor.download_image, number, image_urls)
                        download_count += 1
                        logger.info(f"[JimengPlugin] 已下载图片: {number} 图片数量: {len(image_urls)}")
                except Exception as e:
                    logger.error(f"[JimengPlugin] 下载图片失败 (任务 {task.task_id}): {e}")
        
        logger.info(f"[JimengPlugin] 批量处理完成，共下载 {download_count} 组图片")
        return download_count > 0
    
    def generate_video_draft(self, 
                           output_name: str | None = None,
                           video_width: int = 1080,
                           video_height: int = 1920,
                           random_seed: int | None = None,
                           image_selection_strategy: str = "manual") -> str:
        """生成视频草稿
        
        Args:
            output_name: 输出文件名（默认使用飞镜配置文件名）
            video_width: 视频宽度
            video_height: 视频高度
            random_seed: 随机种子
            image_selection_strategy: 图片选择策略（random, manual）
            
        Returns:
            生成的草稿文件路径
        """
        try:
            # 获取素材目录
            base_dir = os.path.dirname(__file__)
            scene_dir = os.path.join(base_dir, "downloads", self.download_subdir)
            
            if not os.path.exists(scene_dir):
                logger.error(f"[JimengPlugin] 素材目录不存在: {scene_dir}")
                return ""
            
            # 使用分镜配置文件名作为默认输出名
            if output_name is None:
                output_name = self.download_subdir
            
            logger.info(f"[JimengPlugin] 开始生成视频草稿，素材目录: {scene_dir}")
            
            # 将字符串策略转换为枚举
            from module.video_generator import ImageSelectionStrategy
            strategy_map = {
                "random": ImageSelectionStrategy.RANDOM,
                "manual": ImageSelectionStrategy.MANUAL
            }
            strategy = strategy_map.get(image_selection_strategy, ImageSelectionStrategy.MANUAL)
            
            # 生成视频草稿
            draft_file = self.video_generator.create_video_draft_from_feijing(
                feijing_dir=scene_dir,
                output_name=output_name,
                video_width=video_width,
                video_height=video_height,
                random_seed=random_seed,
                image_selection_strategy=strategy
            )
            
            if draft_file:
                logger.info(f"[JimengPlugin] 视频草稿生成成功: {draft_file}")
            else:
                logger.error("[JimengPlugin] 视频草稿生成失败")
            
            return draft_file
            
        except Exception as e:
            logger.error(f"[JimengPlugin] 生成视频草稿异常: {e}")
            return ""
    
    async def cleanup(self) -> None:
        """清理资源"""
        try:
            if hasattr(self, 'batch_processor'):
                self.batch_processor.close()
            
            if hasattr(self, 'image_storage'):
                await self.image_storage.close()
            
            logger.info("[JimengPlugin] 资源清理完成")
        except Exception as e:
            logger.error(f"[JimengPlugin] 资源清理失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            stats = {
                "config": {
                    "model": self.generation_config.model,
                    "ratio": self.generation_config.ratio,
                    "max_retries": self.generation_config.max_retries,
                    "retention_days": self.config_manager.get("storage.retention_days", 7)
                },
                "storage": {
                    "db_path": self.image_storage.db_path,
                    "retention_days": self.image_storage.retention_days
                }
            }
            return stats
        except Exception as e:
            logger.error(f"[JimengPlugin] 获取统计信息失败: {e}")
            return {}

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="即梦插件 - AI图片生成和音频处理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python jimeng.py --tts                    # 只执行飞镜转TTS
  python jimeng.py --images                 # 只执行批量图片生成
  python jimeng.py --video                  # 只生成视频草稿
  python jimeng.py --tts --images           # 执行TTS和批量生成
  python jimeng.py --tts --images --video    # 执行TTS、批量生成和视频草稿
  python jimeng.py --download               # 从数据库下载飞镜图片
  python jimeng.py --stats                  # 只显示统计信息
  python jimeng.py --feijing custom.json    # 使用自定义飞镜配置文件
  python jimeng.py --config config.json --feijing feijing.json  # 同时指定配置文件和飞镜文件
  python jimeng.py --video --video-width 1920 --video-height 1080  # 生成横屏视频草稿
  python jimeng.py --video --image-strategy random  # 使用随机选择策略
  python jimeng.py --video --image-strategy manual  # 使用人工选择策略（GUI界面）
  python jimeng.py                          # 默认执行TTS和批量生成

图片选择策略说明:
  random: 随机选择图片
  manual: 人工选择（显示GUI界面，可选择每个分镜的图片）
        """
    )
    
    parser.add_argument(
        '--tts', 
        action='store_true',
        help='执行飞镜转TTS功能'
    )
    
    parser.add_argument(
        '--images', 
        action='store_true',
        help='执行批量图片生成功能'
    )
    
    parser.add_argument(
        '--download', 
        action='store_true',
        help='从数据库下载飞镜图片'
    )
    
    parser.add_argument(
        '--stats', 
        action='store_true',
        help='只显示统计信息'
    )
    
    parser.add_argument(
        '--config', 
        type=str,
        help='指定配置文件路径'
    )
    
    parser.add_argument(
        '--feijing', 
        type=str,
        help='指定飞镜配置文件路径 (默认: feijing.json)'
    )
    
    parser.add_argument(
        '--voice', 
        type=str,
        default='zh-CN-YunzeNeural',
        help='指定TTS语音名称 (默认: zh-CN-YunzeNeural)'
    )
    
    parser.add_argument(
        '--model', 
        type=str,
        default='3.1',
        help='指定图片生成模型 (默认: 3.1)'
    )
    
    parser.add_argument(
        '--ratio', 
        type=str,
        default='9:16',
        help='指定图片比例 (默认: 9:16)'
    )
    
    parser.add_argument(
        '--timeout', 
        type=int,
        default=3600,
        help='图片生成超时时间(秒) (默认: 3600)'
    )
    
    parser.add_argument(
        '--video', 
        action='store_true',
        help='生成视频草稿'
    )
    
    parser.add_argument(
        '--video-width', 
        type=int,
        default=1080,
        help='视频宽度 (默认: 1080)'
    )
    
    parser.add_argument(
        '--video-height', 
        type=int,
        default=1920,
        help='视频高度 (默认: 1920)'
    )
    
    parser.add_argument(
        '--video-seed', 
        type=int,
        help='视频生成随机种子'
    )
    
    parser.add_argument(
        '--image-strategy', 
        type=str,
        default='manual',
        choices=['random', 'manual'],
        help='图片选择策略 (默认: manual)'
    )
    
    return parser.parse_args()

async def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 创建插件实例
    jimeng = JimengPlugin(args.config, args.feijing)
    
    try:
        # results = await jimeng.wait_for_completion(["c424668f-7af5-4115-9736-86341497e471"], 3600)
        # print(results)
        # jimeng.image_processor.download_image("分镜1", results["c424668f-7af5-4115-9736-86341497e471"])
        # return
        # 显示统计信息
        stats = jimeng.get_stats()
        logger.info(f"[Main] 插件统计信息: {stats}")
        
        # 如果只显示统计信息，则退出
        if args.stats:
            logger.info("[Main] 统计信息显示完成")
            return
        
        # 从数据库下载飞镜图片
        if args.download:
            logger.info("[Main] 开始从数据库下载飞镜图片...")
            await jimeng.download_images_from_db()
            logger.info("[Main] 数据库下载完成")
            
        # 执行飞镜转TTS
        if args.tts:
            logger.info("[Main] 开始执行飞镜转TTS...")
            jimeng.process_to_tts(voice_name=args.voice)
            logger.info("[Main] 分镜转TTS完成")
        
        # 执行批量图片生成
        if args.images:
            logger.info("[Main] 开始执行批量图片生成...")
            success = await jimeng.process_images_batch(
                model=args.model,
                ratio=args.ratio,
                timeout=args.timeout
            )
            
            if success:
                logger.info("[Main] 批量图片生成成功完成")
            else:
                logger.error("[Main] 批量图片生成失败")
                sys.exit(1)
        
        # 生成视频草稿
        if args.video:
            logger.info("[Main] 开始生成视频草稿...")
            draft_file = jimeng.generate_video_draft(
                video_width=args.video_width,
                video_height=args.video_height,
                random_seed=args.video_seed,
                image_selection_strategy=args.image_strategy
            )
            
            if draft_file:
                logger.info(f"[Main] 视频草稿生成成功: {draft_file}")
            else:
                logger.error("[Main] 视频草稿生成失败")
                sys.exit(1)
        
        # 如果没有指定任何操作，默认执行TTS和批量生成
        if not any([args.stats, args.download, args.tts, args.images, args.video]):
            logger.info("[Main] 未指定操作，执行默认流程...")
            
            # 执行飞镜转TTS
            logger.info("[Main] 开始执行飞镜转TTS...")
            jimeng.process_to_tts(voice_name=args.voice)
            logger.info("[Main] 飞镜转TTS完成")
            
            # 执行批量图片生成
            logger.info("[Main] 开始执行批量图片生成...")
            success = await jimeng.process_images_batch(
                model=args.model,
                ratio=args.ratio,
                timeout=args.timeout
            )
            
            if success:
                logger.info("[Main] 批量图片生成成功完成")
            else:
                logger.error("[Main] 批量图片生成失败")
                sys.exit(1)

            logger.info("[Main] 开始生成视频草稿...")
            draft_file = jimeng.generate_video_draft(
                video_width=args.video_width,
                video_height=args.video_height,
                random_seed=args.video_seed,
                image_selection_strategy=args.image_strategy
            )
            if draft_file:
                logger.info(f"[Main] 视频草稿生成成功: {draft_file}")
            else:
                logger.error("[Main] 视频草稿生成失败")
                sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("[Main] 用户中断程序")
    except Exception as e:
        logger.error(f"[Main] 程序异常: {e}")
        sys.exit(1)
    finally:
        # 清理资源
        await jimeng.cleanup()
        logger.info("[Main] 程序结束")

def run_main():
    """运行主函数的包装器"""
    # Windows 下设置 Selector 策略以提高兼容性
    if sys.platform.startswith("win"):
        policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy_cls is not None:
            try:
                asyncio.set_event_loop_policy(policy_cls())
            except Exception:
                pass
    asyncio.run(main())

if __name__ == "__main__":
    run_main()