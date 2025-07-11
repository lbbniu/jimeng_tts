import json
import os
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import azure.cognitiveservices.speech as speechsdk
# 移除并发处理相关导入，因为接口不支持并发调用

from module.token_manager import TokenManager
from module.api_client import ApiClient
from module.image_storage import ImageStorage
from module.image_processor import ImageProcessor
from dotenv import load_dotenv

load_dotenv()

# 配置日志格式和处理器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/jimeng.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# 常量定义
class TaskStatus(Enum):
    """任务状态枚举"""
    ALL = 0
    PENDING = 20
    COMPLETED = 50
    FAILED = 60

class ModelType(Enum):
    """模型类型枚举"""
    V2_1 = "2.1"
    V2_0 = "2.0"
    V2_0_PRO = "2.0p"
    V3_0 = "3.0"
    V3_1 = "3.1"

class RatioType(Enum):
    """比例类型枚举"""
    SQUARE = "1:1"
    PORTRAIT = "9:16"
    LANDSCAPE = "16:9"
    WIDE = "21:9"

# 配置数据类
@dataclass
class GenerationConfig:
    """生成配置"""
    model: str = "3.1"
    ratio: str = "9:16"
    max_retries: int = 3
    retry_delay: int = 2
    timeout: int = 30

@dataclass
class ApiConfig:
    """API配置"""
    base_url: str = "https://jimeng.jianying.com"
    aid: int = 513695
    app_version: str = "5.8.0"
    request_delay: float = 1.0  # 请求间隔（秒），防止API限流

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
        
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, "r", encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"[ConfigManager] 配置文件加载成功: {self.config_path}")
                return config
        except FileNotFoundError:
            logger.error(f"[ConfigManager] 配置文件不存在: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"[ConfigManager] 配置文件格式错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"[ConfigManager] 加载配置文件失败: {e}")
            return {}
    
    def _validate_config(self) -> None:
        """验证配置文件"""
        required_fields = ["video_api.cookie", "video_api.sign"]
        missing_fields = []
        
        for field in required_fields:
            keys = field.split(".")
            value = self.config
            try:
                for key in keys:
                    value = value[key]
                if not value:
                    missing_fields.append(field)
            except (KeyError, TypeError):
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"[ConfigManager] 缺少必要配置项: {missing_fields}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_generation_config(self) -> GenerationConfig:
        """获取生成配置"""
        return GenerationConfig(
            model=self.get("params.default_model", "3.1"),
            ratio=self.get("params.default_ratio", "9:16"),
            max_retries=self.get("generation.max_retries", 3),
            retry_delay=self.get("generation.retry_delay", 2),
            timeout=self.get("generation.timeout", 30),
        )
    
    def get_api_config(self) -> ApiConfig:
        """获取API配置"""
        return ApiConfig(
            base_url=self.get("api.base_url", "https://jimeng.jianying.com"),
            aid=self.get("api.aid", 513695),
            app_version=self.get("api.app_version", "5.8.0"),
            request_delay=self.get("api.request_delay", 1.0)
        )

class ImageGenerationTask:
    """图片生成任务"""
    
    def __init__(self, task_id: str, prompt: str, model: str, ratio: str, metadata: Optional[Dict[str, Any]] = None):
        self.task_id = task_id
        self.prompt = prompt
        self.model = model
        self.ratio = ratio
        self.metadata = metadata or {}
        self.status = TaskStatus.PENDING
        self.created_at = time.time()
        self.completed_at = None
        self.result = None
        self.error = None
    
    def mark_completed(self, result: Any) -> None:
        """标记任务完成"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.time()
        self.result = result
    
    def mark_failed(self, error: str) -> None:
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.completed_at = time.time()
        self.error = error
    
    def get_duration(self) -> float:
        """获取任务持续时间"""
        if self.completed_at:
            return self.completed_at - self.created_at
        return time.time() - self.created_at

class BatchProcessor:
    """批处理器 - 顺序处理（因为接口不支持并发调用）"""
    
    def __init__(self, request_delay: float = 1.0):
        """初始化批处理器
        
        Args:
            request_delay: 请求间隔时间（秒），防止API限流
        """
        self.request_delay = request_delay
        self.tasks: List[ImageGenerationTask] = []
    
    def add_task(self, task: ImageGenerationTask) -> None:
        """添加任务"""
        self.tasks.append(task)
    
    def process_batch(self, generator_func, *args, **kwargs) -> List[ImageGenerationTask]:
        """批量处理任务（顺序处理）"""
        if not self.tasks:
            return []
        
        logger.info(f"[BatchProcessor] 开始顺序处理 {len(self.tasks)} 个任务")
        
        completed_tasks = []
        for i, task in enumerate(self.tasks):
            try:
                logger.info(f"[BatchProcessor] 处理任务 {i+1}/{len(self.tasks)}: {task.task_id}")
                
                # 调用生成函数
                result = generator_func(task, *args, **kwargs)
                
                if result:
                    task.mark_completed(result)
                    logger.info(f"[BatchProcessor] 任务 {task.task_id} 完成，耗时 {task.get_duration():.2f}s")
                else:
                    task.mark_failed("生成失败")
                    logger.error(f"[BatchProcessor] 任务 {task.task_id} 失败")
                
            except Exception as e:
                task.mark_failed(str(e))
                logger.error(f"[BatchProcessor] 任务 {task.task_id} 异常: {e}")
            
            completed_tasks.append(task)
            
            # 添加请求间隔（除了最后一个任务）
            if i < len(self.tasks) - 1:
                logger.debug(f"[BatchProcessor] 等待 {self.request_delay} 秒...")
                time.sleep(self.request_delay)
        
        # 清空任务列表
        self.tasks.clear()
        return completed_tasks
    
    def close(self) -> None:
        """清理资源"""
        self.tasks.clear()
        logger.debug("[BatchProcessor] 资源已清理")

class JimengPlugin:
    """即梦插件主类"""
    
    def __init__(self, config_path: Optional[str] = None):
        # 初始化配置管理器
        self.config_manager = ConfigManager(config_path)
        self.generation_config = self.config_manager.get_generation_config()
        self.api_config = self.config_manager.get_api_config()
        
        # 初始化目录
        self._init_directories()
        
        # 初始化组件
        self._init_components()
        
        # 初始化批处理器（顺序处理，添加请求间隔防止限流）
        request_delay = self.config_manager.get("api.request_delay", 1.0)
        self.batch_processor = BatchProcessor(request_delay=request_delay)
        
        logger.info(f"[JimengPlugin] 插件初始化完成，数据保留天数: {self.config_manager.get('storage.retention_days', 7)}")
    
    def _init_directories(self) -> None:
        """初始化目录结构"""
        base_dir = os.path.dirname(__file__)
        
        # 创建必要目录
        directories = [
            os.path.join(base_dir, "storage"),
            os.path.join(base_dir, "temp"),
            os.path.join(base_dir, "logs")
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
            os.path.join(base_dir, "downloads")
        )
        
        # 初始化Token管理器
        self.token_manager = TokenManager(self.config_manager.config)
        
        # 初始化API客户端
        self.api_client = ApiClient(self.token_manager, self.config_manager.config)
    
    def generate_image(self, prompt: str, model: Optional[str] = None, ratio: Optional[str] = None) -> Optional[str]:
        """生成单张图片
        
        Args:
            prompt: 图片提示词
            model: 模型版本，默认使用配置中的默认模型
            ratio: 图片比例，默认使用配置中的默认比例
            
        Returns:
            Optional[str]: 成功时返回submit_id，失败时返回None
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
                submit_id = self.api_client.generate_image(prompt, model, ratio)
                if submit_id:
                    # 存储图片信息
                    self.image_storage.store_image(
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
            
            # 等待重试
            if attempt < self.generation_config.max_retries - 1:
                time.sleep(self.generation_config.retry_delay)
        
        logger.error(f"[JimengPlugin] 图片生成失败，已重试 {self.generation_config.max_retries} 次")
        return None
    
    def generate_images_batch(self, prompts: List[str], model: Optional[str] = None, ratio: Optional[str] = None) -> List[ImageGenerationTask]:
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
        completed_tasks = self.batch_processor.process_batch(
            self._generate_single_task
        )
        
        return completed_tasks
    
    def _generate_single_task(self, task: ImageGenerationTask) -> Optional[str]:
        """处理单个生成任务"""
        try:
            submit_id = self.generate_image(task.prompt, task.model, task.ratio)
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
    
    def wait_for_completion(self, submit_ids: List[str], timeout: int = 3600) -> Dict[str, List[str]]:
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
                    image_urls = self.api_client.get_generated_images(submit_id)
                    if image_urls is not None:
                        results[submit_id] = image_urls
                        completed_ids.append(submit_id)
                        
                        # 更新存储
                        self.image_storage.update_image(submit_id, image_urls)
                        logger.info(f"[JimengPlugin] 任务 {submit_id} 完成，获得 {len(image_urls)} 张图片")
                        
                except Exception as e:
                    logger.error(f"[JimengPlugin] 检查任务 {submit_id} 状态失败: {e}")
            
            # 移除已完成的任务
            for submit_id in completed_ids:
                remaining_ids.remove(submit_id)
            
            if remaining_ids:
                time.sleep(2)  # 等待2秒后再次检查
        
        # 记录未完成的任务
        if remaining_ids:
            logger.warning(f"[JimengPlugin] {len(remaining_ids)} 个任务未在超时时间内完成")
        
        return results
    
    def load_feijing_config(self) -> Optional[List[Dict[str, Any]]]:
        """加载飞镜配置"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), "feijing.json")
            with open(config_path, "r", encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"[JimengPlugin] 飞镜配置加载成功，包含 {len(config)} 个项目")
            return config
        except Exception as e:
            logger.error(f"[JimengPlugin] 飞镜配置加载失败: {e}")
            return None
    
    def download_feijing_from_db(self) -> None:
        """从数据库中下载飞镜图片"""
        images = self.image_storage.get_images_by_status(TaskStatus.ALL.value)
        
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
                image_urls = self.api_client.get_generated_images(submit_id)
                if image_urls is not None:
                    self.image_processor.download_image(filename, image_urls)
                    logger.info(f"[JimengPlugin] {submit_id} 已下载图片: {filename}")
    
    def azure_tts(self, filename: str, text: str, generate_srt: bool = True) -> None:
        """文本转语音并生成字幕文件
        
        Args:
            filename: 输出文件名（不含扩展名）
            text: 要转换的文本
            generate_srt: 是否生成SRT字幕文件
            
        """

        # This example requires environment variables named "SPEECH_KEY" and "ENDPOINT"
        # Replace with your own subscription key and endpoint, the endpoint is like : "https://japaneast.api.cognitive.microsoft.com"
        speech_config = speechsdk.SpeechConfig(subscription=os.environ.get('SPEECH_KEY'), endpoint=os.environ.get('ENDPOINT'))
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3)
        # audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        audio_filename = f"{filename}.mp3"
        audio_config = speechsdk.audio.AudioOutputConfig(filename=audio_filename)

        # The neural multilingual voice can speak different languages based on the input text.
        speech_config.speech_synthesis_voice_name='zh-CN-YunzeNeural'

        from module.submaker import SubMaker, TTSChunk
        submaker = SubMaker()
        def speech_synthesizer_word_boundary_cb(evt: speechsdk.SpeechSynthesisWordBoundaryEventArgs):
            # 将duration转换为100纳秒单位（与offset保持一致）
            duration_in_100ns = int(evt.duration.total_seconds() * 10000000)
            
            submaker.feed(TTSChunk(
                type="WordBoundary",
                offset=evt.audio_offset,
                duration=duration_in_100ns,
                text=evt.text
            ))
            # print('WordBoundary event:')
            # print('\tBoundaryType: {}'.format(evt.boundary_type))
            # print('\tAudioOffset: {}ms'.format(evt.audio_offset / 10000))
            # print('\tDuration: {}'.format(evt.duration))
            # print('\tText: {}'.format(evt.text))
            # print('\tTextOffset: {}'.format(evt.text_offset))
            # print('\tWordLength: {}'.format(evt.word_length))

        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        speech_synthesizer.synthesis_word_boundary.connect(speech_synthesizer_word_boundary_cb)

        speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()
        reason = speech_synthesis_result.reason # type: ignore

        if reason == speechsdk.ResultReason.SynthesizingAudioCompleted: # type: ignore
            logger.info("Speech synthesized for text [{}]".format(text))
            logger.info(f"[JimengPlugin] 音频文件已生成: {audio_filename}")
            if generate_srt:
                # 优化字幕：合并短字幕，避免剪映导入问题
                submaker.merge_cues(10)  # 合并为10个词一组
                srt_filename = f"{filename}.srt"
                with open(srt_filename, "w", encoding='utf-8') as f:
                    f.write(submaker.get_srt())
                logger.info(f"[JimengPlugin] 字幕文件已生成: {srt_filename}")
        elif reason == speechsdk.ResultReason.Canceled: # type: ignore
            cancellation_details = speech_synthesis_result.cancellation_details # type: ignore
            print("Speech synthesis canceled: {}".format(cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error: # type: ignore
                if cancellation_details.error_details:
                    print("Error details: {}".format(cancellation_details.error_details))
                    print("Did you set the speech resource key and endpoint values?")
    
     
    def fenjing_to_tts(self) -> None:
        """飞镜转TTS"""
        feijing_config = self.load_feijing_config()
        if not feijing_config:
            logger.error("[JimengPlugin] 无法加载飞镜配置")
            return
        for item in feijing_config:
            filename = item.get('编号', '')
            text = item.get('原文', '')
            if not filename or not text:
                continue
            filename = f"./downloads/{filename}"
            self.azure_tts(filename, text)
    
    def process_feijing_batch(self) -> bool:
        """批量处理飞镜配置"""
        feijing_config = self.load_feijing_config()
        if not feijing_config:
            logger.error("[JimengPlugin] 无法加载飞镜配置")
            return False
        
        # 准备提示词列表
        prompts = []
        item_mapping = {}
        
        for item in feijing_config:
            prompt = item.get('提示词', '').strip()
            if prompt:
                prompts.append(prompt)
                item_mapping[len(prompts) - 1] = item
        
        if not prompts:
            logger.warning("[JimengPlugin] 没有找到有效的提示词")
            return False
        
        logger.info(f"[JimengPlugin] 开始批量处理 {len(prompts)} 个提示词...")
        
        # 批量生成图片
        tasks = self.generate_images_batch(prompts, "3.1", "9:16")
        
        # 收集成功的任务
        successful_tasks = [task for task in tasks if task.status == TaskStatus.COMPLETED]
        failed_tasks = [task for task in tasks if task.status == TaskStatus.FAILED]
        
        logger.info(f"[JimengPlugin] 生成完成: {len(successful_tasks)} 成功, {len(failed_tasks)} 失败")
        
        if not successful_tasks:
            return False
        
        # 等待所有任务完成
        submit_ids = [task.result for task in successful_tasks if task.result]
        results = self.wait_for_completion(submit_ids)
        
        # 下载图片
        download_count = 0
        for i, task in enumerate(successful_tasks):
            if task.result and task.result in results:
                try:
                    item = item_mapping.get(task.metadata.get('batch_index', i))
                    if item:
                        number = item.get('编号', f'img_{i}')
                        image_urls = results[task.result]
                        self.image_processor.download_image(number, image_urls)
                        download_count += 1
                        logger.info(f"[JimengPlugin] 已下载图片: {number}")
                except Exception as e:
                    logger.error(f"[JimengPlugin] 下载图片失败 (任务 {task.task_id}): {e}")
        
        logger.info(f"[JimengPlugin] 批量处理完成，共下载 {download_count} 组图片")
        return download_count > 0
    
    def cleanup(self) -> None:
        """清理资源"""
        try:
            if hasattr(self, 'batch_processor'):
                self.batch_processor.close()
            
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

if __name__ == "__main__":
    # 创建插件实例
    jimeng = JimengPlugin()
    
    try:
        # 显示统计信息
        stats = jimeng.get_stats()
        logger.info(f"[Main] 插件统计信息: {stats}")
        
        # submit_id = "6dedc742-d8c2-45d4-9daf-7965916e89aa"
        # filename = "分镜1"
        # image_urls = jimeng.api_client.get_generated_images(submit_id)
        # if image_urls is not None:
        #     jimeng.image_processor.download_image(filename, image_urls)
        #     logger.info(f"[JimengPlugin] {submit_id} 已下载图片: {filename}")
        # exit(0)
        jimeng.fenjing_to_tts()
        # exit(0)
        # jimeng.download_feijing_from_db()
        # # 批量处理飞镜配置
        success = jimeng.process_feijing_batch()
        
        if success:
            logger.info("[Main] 批量处理成功完成")
        else:
            logger.error("[Main] 批量处理失败")
            exit(1)
            
    except KeyboardInterrupt:
        logger.info("[Main] 用户中断程序")
    except Exception as e:
        logger.error(f"[Main] 程序异常: {e}")
        exit(1)
    finally:
        # 清理资源
        jimeng.cleanup()
        logger.info("[Main] 程序结束")