import json
import os
import time
import uuid
import base64
import requests
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from plugins import Plugin, Event, EventAction, EventContext, register
from common.log import logger
from .module.token_manager import TokenManager
from .module.api_client import ApiClient
from .module.image_storage import ImageStorage

@register(
    name="Jimeng",
    desc="即梦AI绘画和视频生成插件",
    version="1.0",
    author="lanvent",
    desire_priority=0
)
class JimengPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        self.config = self._load_config()
        
        # 获取数据保留天数配置
        retention_days = self.config.get("storage", {}).get("retention_days", 7)
        
        # 初始化存储路径
        storage_dir = os.path.join(os.path.dirname(__file__), "storage")
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir)
            
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        # 初始化各个模块
        self.image_storage = ImageStorage(
            os.path.join(storage_dir, "images.db"),
            retention_days=retention_days
        )
        self.token_manager = TokenManager(self.config)
        self.api_client = ApiClient(self.token_manager, self.config)
        
        # 初始化图片处理器
        from .module.image_processor import ImageProcessor
        self.image_processor = ImageProcessor(temp_dir)
        
        # 初始化视频生成API相关配置
        self.video_api_headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'app-sdk-version': '48.0.0',
            'appid': '513695',
            'appvr': '5.8.0',
            'content-type': 'application/json',
            'cookie': self.config.get("video_api", {}).get("cookie", ""),
            'device-time': str(int(time.time())),
            'lan': 'zh-Hans',
            'loc': 'cn',
            'origin': 'https://jimeng.jianying.com',
            'pf': '7',
            'priority': 'u=1, i',
            'referer': 'https://jimeng.jianying.com/ai-tool/video/generate',
            'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'sign': self.config.get("video_api", {}).get("sign", ""),
            'sign-ver': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }
        self.video_api_base = "https://jimeng.jianying.com/mweb/v1"
        
        logger.info(f"[Jimeng] plugin initialized with {retention_days} days data retention")

    def _load_config(self):
        """加载配置文件"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            with open(config_path, "r", encoding='utf-8') as f:
                config = json.load(f)
                return config
        except Exception as e:
            logger.error(f"[Jimeng] Failed to load config: {e}")
            return {}

    def get_help_text(self, **kwargs):
        commands = self.config.get('commands', {})
        draw_command = commands.get('draw', '即梦') if isinstance(commands, dict) else '即梦'
        
        help_text = "即梦AI绘画和视频生成插件使用说明：\n\n"
        
        # 基本命令说明
        help_text += "基本命令：\n"
        help_text += f"1. 生成图片: '{draw_command} [描述] [模型] [比例]'\n"
        help_text += f"2. 生成视频: '{draw_command}v [描述] [比例]'\n\n"
        
        # 支持的模型
        help_text += "支持的模型: 2.0, 2.1, 2.0p, 3.0, xl\n\n"
        
        # 支持的比例
        help_text += "支持的比例: "
        ratios = list(self.config.get("params", {}).get("ratios", {}).keys())
        help_text += ", ".join(ratios)
        help_text += "\n\n"
        
        # 使用示例
        help_text += "示例：\n"
        help_text += f"1. {draw_command} 一只可爱的猫咪  # 使用默认模型(2.1)和比例(1:1)\n"
        help_text += f"2. {draw_command} 一只可爱的猫咪-3.0  # 使用图片3.0模型\n"
        help_text += f"3. {draw_command} 一只可爱的猫咪-2.0p-16:9  # 使用2.0 Pro模型和16:9比例\n"
        help_text += f"4. j放大 1704067890 2  # 查看ID为1704067890的第2张原图\n"
        help_text += f"5. {draw_command}v 现代美少女在海边  # 生成视频，使用默认比例\n"
        help_text += f"6. {draw_command}v 现代美少女在海边-16:9  # 生成视频，使用16:9比例\n"
        
        return help_text

    def send_reply(self, e_context: EventContext, reply: Reply):
        """发送回复"""
        e_context['reply'] = reply
        e_context.action = EventAction.BREAK_PASS

    def send_image_and_text(self, e_context: EventContext, image_content, text_content):
        """发送图片和文本消息"""
        # 先发送图片
        image_reply = Reply(ReplyType.IMAGE, image_content)
        self.send_reply(e_context, image_reply)
        
        # 再发送文本
        if text_content:
            text_reply = Reply(ReplyType.TEXT, text_content)
            self.send_reply(e_context, text_reply)

    def generate_video(self, prompt, ratio=None):
        """生成视频
        Args:
            prompt: 视频提示词
            ratio: 视频比例，如"16:9"，默认为配置中的默认比例
        Returns:
            tuple: (success, result)
        """
        try:
            # 检查配置是否完整
            if not self.config.get("video_api", {}).get("cookie") or not self.config.get("video_api", {}).get("sign"):
                return False, "请先在config.json中配置video_api的cookie和sign"

            # 获取视频比例配置
            if not ratio:
                ratio = self.config.get("default_video_ratio", "16:9")
                
            # 获取比例的宽高配置
            ratio_config = self.config.get("video_ratios", {}).get(ratio)
            if not ratio_config:
                # 如果未找到比例配置，使用默认16:9
                ratio = "16:9"
                ratio_config = {"width": 1024, "height": 576}
            
            # 生成唯一的submit_id
            submit_id = str(uuid.uuid4())
            
            # 准备请求数据
            generate_video_payload = {
                "submit_id": submit_id,
                "task_extra": "{\"promptSource\":\"custom\",\"originSubmitId\":\"0340110f-5a94-42a9-b737-f4518f90361f\",\"isDefaultSeed\":1,\"originTemplateId\":\"\",\"imageNameMapping\":{},\"isUseAiGenPrompt\":false,\"batchNumber\":1}",
                "http_common_info": {"aid": 513695},
                "input": {
                    "video_aspect_ratio": ratio,
                    "seed": 2934141961,
                    "video_gen_inputs": [
                        {
                            "prompt": prompt,
                            "fps": 24,
                            "duration_ms": 5000,
                            "video_mode": 2,
                            "template_id": ""
                        }
                    ],
                    "priority": 0,
                    "model_req_key": "dreamina_ic_generate_video_model_vgfm_lite"
                },
                "mode": "workbench",
                "history_option": {},
                "commerce_info": {
                    "resource_id": "generate_video",
                    "resource_id_type": "str",
                    "resource_sub_type": "aigc",
                    "benefit_type": "basic_video_operation_vgfm_lite"
                },
                "client_trace_data": {}
            }

            # 发送生成视频请求
            generate_video_url = f"{self.video_api_base}/generate_video?aid=513695"
            logger.debug(f"[Jimeng] Sending video generation request to {generate_video_url}")
            
            # 更新请求头的device-time
            self.video_api_headers['device-time'] = str(int(time.time()))
            response = requests.post(generate_video_url, headers=self.video_api_headers, json=generate_video_payload)
            
            if response.status_code != 200:
                logger.error(f"[Jimeng] Video generation request failed with status code {response.status_code}")
                return False, f"视频生成请求失败，状态码：{response.status_code}"

            response_data = response.json()
            logger.debug(f"[Jimeng] Video generation response: {response_data}")
            
            if not response_data or "data" not in response_data or "aigc_data" not in response_data["data"]:
                logger.error(f"[Jimeng] Invalid response format: {response_data}")
                return False, "视频生成接口返回格式错误"
                
            task_id = response_data["data"]["aigc_data"]["task"]["task_id"]
            logger.info(f"[Jimeng] Video generation task created with ID: {task_id}")
            
            # 轮询检查视频生成状态
            mget_generate_task_url = f"{self.video_api_base}/mget_generate_task?aid=513695"
            mget_generate_task_payload = {"task_id_list": [task_id]}
            
            # 最多尝试30次，每次间隔5秒
            for attempt in range(30):
                time.sleep(5)
                logger.debug(f"[Jimeng] Checking video status, attempt {attempt + 1}/30")
                
                # 更新请求头的device-time
                self.video_api_headers['device-time'] = str(int(time.time()))
                response = requests.post(mget_generate_task_url, headers=self.video_api_headers, json=mget_generate_task_payload)
                
                if response.status_code != 200:
                    logger.warning(f"[Jimeng] Status check failed with status code {response.status_code}")
                    continue
                
                response_data = response.json()
                if not response_data or "data" not in response_data or "task_map" not in response_data["data"]:
                    logger.warning(f"[Jimeng] Invalid status response format: {response_data}")
                    continue
                
                task_data = response_data["data"]["task_map"].get(task_id)
                if not task_data:
                    logger.warning(f"[Jimeng] Task {task_id} not found in response")
                    continue
                
                task_status = task_data.get("status")
                logger.debug(f"[Jimeng] Task {task_id} status: {task_status}")
                
                if task_status == 50:  # 视频生成完成
                    if "item_list" in task_data and task_data["item_list"] and "video" in task_data["item_list"][0]:
                        video_data = task_data["item_list"][0]["video"]
                        if "transcoded_video" in video_data and "origin" in video_data["transcoded_video"]:
                            video_url = video_data["transcoded_video"]["origin"]["video_url"]
                            logger.info(f"[Jimeng] Video generation completed, URL: {video_url}")
                            return True, video_url
                    
                    logger.error(f"[Jimeng] Video URL not found in completed task data: {task_data}")
                    return False, "视频生成完成但未找到下载地址"
                    
            logger.warning(f"[Jimeng] Video generation timed out for task {task_id}")
            return False, "视频生成超时，请稍后重试"
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[Jimeng] Network error during video generation: {str(e)}")
            return False, f"网络请求错误: {str(e)}"
        except json.JSONDecodeError as e:
            logger.error(f"[Jimeng] JSON decode error: {str(e)}")
            return False, "API响应格式错误"
        except Exception as e:
            logger.error(f"[Jimeng] Error generating video: {str(e)}")
            return False, f"视频生成失败: {str(e)}"

    def _parse_command(self, content):
        """解析命令参数
        Args:
            content: 命令内容，如 "一只猫 2.1 4:3" 或 "一只猫-2.1-4:3"
        Returns:
            tuple: (prompt, model, ratio)
        """
        # 设置默认值
        model = self.config.get("params", {}).get("default_model", "2.1")
        ratio = self.config.get("params", {}).get("default_ratio", "1:1")
        
        # 使用"-"分割提示词、模型和比例
        if "-" in content:
            parts = content.split("-")
            # 取除最后两个部分外的所有内容作为提示词
            if len(parts) >= 3:
                # 可能最后两个是模型和比例
                possible_model = parts[-2].strip().lower()
                possible_ratio = parts[-1].strip().lower()
                
                # 检查是否是有效的模型或比例
                valid_models = list(self.config.get("params", {}).get("models", {}).keys()) + ["20", "21", "20p", "30", "3.0", "xlpro"]
                valid_ratios = list(self.config.get("params", {}).get("ratios", {}).keys())
                
                is_model = False
                is_ratio = False
                
                # 检查possible_model是否为模型
                if possible_model in valid_models or possible_model.replace(".", "") in ["20", "21", "20p", "30", "xlpro"]:
                    is_model = True
                
                # 检查possible_ratio是否为比例
                if ":" in possible_ratio and possible_ratio in valid_ratios:
                    is_ratio = True
                
                if is_model and is_ratio:
                    # 如果最后两个部分是模型和比例，则取除这两个部分之外的所有内容作为提示词
                    prompt = "-".join(parts[:-2])
                    
                    # 处理模型简写
                    if possible_model == "20":
                        model = "2.0"
                    elif possible_model == "21":
                        model = "2.1"
                    elif possible_model == "20p":
                        model = "2.0p"
                    elif possible_model == "30":
                        model = "3.0"
                    elif possible_model == "xlpro":
                        model = "xl"
                    else:
                        model = possible_model
                    
                    ratio = possible_ratio
                else:
                    # 如果最后两个部分不全是模型和比例，则取所有内容作为提示词
                    prompt = content
            else:
                # 如果parts少于3个，则可能没有同时指定模型和比例，整个作为提示词
                prompt = content
        else:
            # 使用空格分割
            parts = content.split()
            prompt = parts[0] if parts else content
            
            # 解析剩余参数
            for part in parts[1:]:
                part = part.lower().replace("：", ":")  # 统一处理中英文冒号
                
                # 检查是否是模型参数
                models = self.config.get("params", {}).get("models", {})
                if part in models or part.replace(".", "") in ["20", "21", "20p", "30", "xlpro"]:
                    # 处理简写
                    if part == "20":
                        model = "2.0"
                    elif part == "21":
                        model = "2.1"
                    elif part == "20p":
                        model = "2.0p"
                    elif part == "30":
                        model = "3.0"
                    elif part == "xlpro":
                        model = "xl"
                    else:
                        model = part
                    continue
                    
                # 检查是否是比例参数
                ratios = self.config.get("params", {}).get("ratios", {})
                if part in ratios:
                    ratio = part
                    continue
        
        # 如果最终提示词为空，使用整个内容作为提示词
        if not prompt or prompt.strip() == "":
            prompt = content
                
        logger.debug(f"[Jimeng] Parsed command: prompt='{prompt}', model='{model}', ratio='{ratio}'")
        return prompt, model, ratio

    def on_handle_context(self, e_context: EventContext):
        """处理消息"""
        context = e_context['context']
        content = context.content
        logger.debug(f"[Jimeng] on_handle_context. content: {content}")
        
        if not content:
            return
            
        # 检查是否是即梦命令
        if not (content.startswith("即梦") or content.startswith("j放大")):
            return
            
        e_context.action = EventAction.BREAK_PASS
        
        # 处理放大图片命令
        if content.startswith("j放大"):
            try:
                _, img_id, index = content.split(" ")
                index = int(index)
                image_content, error = self.api_client.get_original_image(img_id, index)
                if error:
                    e_context['reply'] = Reply(ReplyType.TEXT, error)
                else:
                    # 如果返回的是URL，使用IMAGE_URL类型
                    if isinstance(image_content, str) and (image_content.startswith('http://') or image_content.startswith('https://')):
                        e_context['reply'] = Reply(ReplyType.IMAGE_URL, image_content)
                    else:
                        # 如果是二进制内容，使用IMAGE类型
                        e_context['reply'] = Reply(ReplyType.IMAGE, image_content)
            except Exception as e:
                logger.error(f"[Jimeng] Error getting original image: {str(e)}")
                e_context['reply'] = Reply(ReplyType.TEXT, f"获取原图失败: {str(e)}")
            return
            
        # 去除命令前缀
        content = content[2:].strip()
        
        # 处理视频生成命令
        if content.startswith('v') or content.startswith('V'):
            # 发送等待提示
            wait_reply = Reply(ReplyType.TEXT, "即梦正在生成视频中，请稍后......")
            e_context["channel"].send(wait_reply, e_context["context"])
            
            # 去除前缀v或V，获取提示词和可能的比例参数
            video_content = content[1:].strip()
            
            # 解析视频命令参数，支持比例参数
            prompt = video_content
            ratio = None
            
            # 检查是否包含比例参数（使用"-"分隔或空格分隔）
            if "-" in video_content:
                parts = video_content.split("-")
                if len(parts) >= 2:
                    last_part = parts[-1].strip()
                    valid_ratios = list(self.config.get("video_ratios", {}).keys())
                    
                    # 检查最后一部分是否是有效比例
                    if ":" in last_part and last_part in valid_ratios:
                        ratio = last_part
                        # 其余部分作为提示词
                        prompt = "-".join(parts[:-1])
            else:
                # 使用空格分割
                parts = video_content.split()
                if len(parts) >= 2:
                    last_part = parts[-1].strip()
                    valid_ratios = list(self.config.get("video_ratios", {}).keys())
                    
                    # 检查最后一部分是否是有效比例
                    if ":" in last_part and last_part in valid_ratios:
                        ratio = last_part
                        # 其余部分作为提示词
                        prompt = " ".join(parts[:-1])
            
            # 生成视频
            logger.debug(f"[Jimeng] Generating video with prompt: '{prompt}', ratio: {ratio}")
            success, result = self.generate_video(prompt, ratio)
            
            if success:
                e_context['reply'] = Reply(ReplyType.VIDEO_URL, result)
            else:
                e_context['reply'] = Reply(ReplyType.TEXT, result)
            return
        
        # 处理图片生成命令
        try:
            # 解析命令参数
            prompt, model, ratio = self._parse_command(content)
            
            # 发送等待提示
            wait_reply = Reply(ReplyType.TEXT, f"即梦正在使用 {model} 模型以 {ratio} 比例生成图片，请稍候......")
            e_context["channel"].send(wait_reply, e_context["context"])
            
            # 生成图片
            result = self.api_client.generate_image(prompt, model=model, ratio=ratio)
            if not result:
                e_context['reply'] = Reply(ReplyType.TEXT, "图片生成失败，请稍后重试")
                return
            
            # 存储图片信息
            img_id = str(int(time.time()))
            self.image_storage.store_image(
                img_id,
                result["urls"],
                metadata={
                    "prompt": content,
                    "type": "generate"
                }
            )
            
            # 发送图片
            if len(result["urls"]) >= 4:
                image_file = self.image_processor.combine_images(result["urls"][:4])
                if image_file:
                    image_reply = Reply(ReplyType.IMAGE, image_file)
                    e_context["channel"].send(image_reply, e_context["context"])
                    image_file.close()
                    
                    # 删除临时拼接图片
                    temp_dir = os.path.join(os.path.dirname(__file__), "temp")
                    for file in os.listdir(temp_dir):
                        if file.startswith("combined_"):
                            try:
                                os.remove(os.path.join(temp_dir, file))
                                logger.debug(f"[Jimeng] Removed temp file: {file}")
                            except Exception as e:
                                logger.warning(f"[Jimeng] Failed to remove temp file {file}: {e}")
                    
                    # 发送帮助文本
                    help_text = f"图片生成成功！\n图片ID: {img_id}\n使用'j放大 {img_id} 序号'可以查看原图"
                    e_context["channel"].send(Reply(ReplyType.TEXT, help_text), e_context["context"])
                    e_context['reply'] = None  # 已经发送过图片，不需要再设置reply
                else:
                    # 如果合并失败，发送单张图片
                    for url in result["urls"]:
                        image_reply = Reply(ReplyType.IMAGE_URL, url)
                        e_context["channel"].send(image_reply, e_context["context"])
                        
                    # 发送帮助文本
                    help_text = f"图片生成成功！\n图片ID: {img_id}\n使用'j放大 {img_id} 序号'可以查看原图"
                    text_reply = Reply(ReplyType.TEXT, help_text)
                    e_context["channel"].send(text_reply, e_context["context"])
                    e_context['reply'] = None  # 已经发送过图片，不需要再设置reply
            else:
                # 直接发送单张图片的URL
                for url in result["urls"]:
                    image_reply = Reply(ReplyType.IMAGE_URL, url)
                    e_context["channel"].send(image_reply, e_context["context"])
                    
                # 发送帮助文本
                help_text = f"图片生成成功！\n图片ID: {img_id}\n使用'j放大 {img_id} 序号'可以查看原图"
                text_reply = Reply(ReplyType.TEXT, help_text)
                e_context["channel"].send(text_reply, e_context["context"])
                e_context['reply'] = None  # 已经发送过图片，不需要再设置reply
            
        except Exception as e:
            logger.error(f"[Jimeng] Error generating image: {e}")
            e_context['reply'] = Reply(ReplyType.TEXT, f"图片生成失败: {str(e)}")

    def on_stop_plugin(self):
        """清理临时文件"""
        self.api_client.cleanup_temp_files()
