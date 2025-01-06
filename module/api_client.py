import json
import time
import uuid
import hashlib
import requests
import random
import os
from common.log import logger
from .image_processor import ImageProcessor
from .image_storage import ImageStorage

class ApiClient:
    def __init__(self, token_manager, config):
        self.token_manager = token_manager
        self.config = config
        self.temp_files = []
        self.base_url = "https://jimeng.jianying.com"
        self.aid = "513695"
        self.app_version = "5.8.0"
        
        # 初始化存储路径
        storage_dir = os.path.join(os.path.dirname(__file__), "../storage")
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir)
            
        temp_dir = os.path.join(os.path.dirname(__file__), "../temp")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # 初始化图片处理器和存储器
        self.image_processor = ImageProcessor(temp_dir)
        self.image_storage = ImageStorage(
            os.path.join(storage_dir, "images.db"),
            retention_days=config.get("storage", {}).get("retention_days", 7)
        )
        
        # 初始化通用请求头
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'app-sdk-version': '48.0.0',
            'appid': self.aid,
            'appvr': '5.8.0',
            'content-type': 'application/json',
            'cookie': self.config.get("video_api", {}).get("cookie", ""),
            'device-time': str(int(time.time())),
            'lan': 'zh-Hans',
            'loc': 'cn',
            'origin': 'https://jimeng.jianying.com',
            'pf': '7',
            'priority': 'u=1, i',
            'referer': 'https://jimeng.jianying.com/ai-tool/image/generate',
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

    def _send_request(self, method, url, **kwargs):
        """发送HTTP请求"""
        try:
            # 更新device-time
            current_time = str(int(time.time()))
            headers = self.headers.copy()
            headers.update({
                'device-time': current_time,
                'msToken': self.config.get("video_api", {}).get("msToken", ""),
                'a-bogus': self.config.get("video_api", {}).get("a_bogus", "")
            })
            
            # 如果kwargs中有headers，合并它们
            if 'headers' in kwargs:
                headers.update(kwargs.pop('headers'))
            
            kwargs['headers'] = headers
            
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            
            # 记录请求和响应信息
            logger.debug(f"[Jimeng] Request URL: {url}")
            logger.debug(f"[Jimeng] Request headers: {headers}")
            if 'params' in kwargs:
                logger.debug(f"[Jimeng] Request params: {kwargs['params']}")
            if 'json' in kwargs:
                logger.debug(f"[Jimeng] Request data: {kwargs['json']}")
            logger.debug(f"[Jimeng] Response: {response.text}")
            
            return response.json()
        except Exception as e:
            logger.error(f"[Jimeng] Request failed: {e}")
            return None

    def _get_generated_images(self, history_id):
        """获取生成的图片"""
        try:
            url = f"{self.base_url}/mweb/v1/get_history_by_ids"
            
            params = {
                "aid": self.aid,
                "device_platform": "web",
                "region": "CN",
                "web_id": self.token_manager.get_web_id()
            }
            
            data = {
                "history_ids": [history_id],
                "image_info": {
                    "width": 2048,
                    "height": 2048,
                    "format": "webp",
                    "image_scene_list": [
                        {"scene": "normal", "width": 2400, "height": 2400, "uniq_key": "2400", "format": "webp"},
                        {"scene": "normal", "width": 1080, "height": 1080, "uniq_key": "1080", "format": "webp"}
                    ]
                },
                "http_common_info": {"aid": self.aid}
            }
            
            # 更新device-time
            self.headers['device-time'] = str(int(time.time()))
            
            logger.debug(f"[Jimeng] Requesting generated images for history_id: {history_id}")
            response = requests.post(url, headers=self.headers, params=params, json=data)
            result = response.json()
            
            if result.get('ret') == '0':
                history_data = result.get('data', {}).get(history_id, {})
                if not history_data:
                    logger.error(f"[Jimeng] No history data found for ID: {history_id}")
                    return None
                    
                status = history_data.get('status')
                item_list = history_data.get('item_list', [])
                
                logger.debug(f"[Jimeng] Image generation status: {status}")
                
                if status == 50 and item_list:  # 50表示生成完成
                    image_urls = []
                    for item in item_list:
                        # 首先尝试获取large_images中的URL
                        image = item.get('image', {})
                        if image and image.get('large_images'):
                            image_url = image['large_images'][0].get('image_url')
                            if image_url:
                                image_urls.append(image_url)
                                continue
                                
                        # 如果large_images不可用，尝试从cover_url_map获取最高质量的图片
                        common_attr = item.get('common_attr', {})
                        cover_url_map = common_attr.get('cover_url_map', {})
                        if cover_url_map:
                            # 按优先级尝试不同尺寸
                            for size in ['2400', '1080', '900', '720']:
                                if size in cover_url_map:
                                    image_urls.append(cover_url_map[size])
                                    break
                            
                    if image_urls:
                        logger.debug(f"[Jimeng] Successfully retrieved {len(image_urls)} image URLs")
                        return image_urls
                    else:
                        logger.error("[Jimeng] No valid image URLs found in response")
                        return None
                        
                elif status == 20:  # 20表示正在生成
                    logger.debug("[Jimeng] Image is still generating")
                    return None
                else:
                    logger.error(f"[Jimeng] Unexpected status: {status}")
                    return None
            else:
                logger.error(f"[Jimeng] Failed to get generated images: {result}")
                return None
                
        except Exception as e:
            logger.error(f"[Jimeng] Error getting generated images: {e}")
            return None

    def get_original_image(self, img_id: str, index: int) -> tuple:
        """获取原始图片
        Args:
            img_id: 图片ID
            index: 图片序号（1-based）
        Returns:
            tuple: (image_content/url, error_message)
        """
        try:
            # 从存储中获取图片信息
            image_info = self.image_storage.get_image(img_id)
            if not image_info:
                return None, "图片不存在或已过期"
                
            urls = image_info.get("urls", [])
            if not urls or index < 1 or index > len(urls):
                return None, f"图片序号无效，有效范围: 1-{len(urls)}"
                
            # 获取指定序号的图片URL
            url = urls[index - 1]
            
            # 直接返回URL，让上层决定如何处理
            return url, None
            
        except Exception as e:
            logger.error(f"[Jimeng] Error getting original image: {e}")
            return None, f"获取图片失败: {str(e)}"

    def _parse_model_and_ratio(self, prompt: str) -> tuple:
        """解析提示词中的模型和比例参数
        Args:
            prompt: 完整的提示词
        Returns:
            tuple: (prompt, model_key, ratio)
        """
        # 获取配置
        models = self.config.get("params", {}).get("models", {})
        ratios = self.config.get("params", {}).get("ratios", {})
        default_model = self.config.get("params", {}).get("default_model", "2.1")
        default_ratio = self.config.get("params", {}).get("default_ratio", "1:1")
        
        # 初始化返回值
        model_key = default_model
        ratio = default_ratio
        
        # 分割提示词
        words = prompt.strip().split()
        if len(words) < 2:
            return prompt, model_key, ratio
            
        # 检查最后两个词是否包含模型或比例信息
        found_model = False
        found_ratio = False
        new_words = []
        
        for word in words:
            is_param = False
            # 检查是否是比例参数
            if ":" in word or "：" in word:
                clean_ratio = word.replace("：", ":")
                if clean_ratio in ratios:
                    ratio = clean_ratio
                    found_ratio = True
                    is_param = True
            
            # 检查是否是模型参数
            word_lower = word.lower()
            # 移除可能的分隔符
            for sep in ["-", ","]:
                if sep in word_lower:
                    word_lower = word_lower.split(sep)[0].strip()
            
            if word_lower in models:
                model_key = word_lower
                found_model = True
                is_param = True
            elif word_lower.replace(".", "") in models:
                model_key = word_lower.replace(".", "")
                found_model = True
                is_param = True
            elif word_lower in ["xl", "xlpro"]:
                model_key = "xl"
                found_model = True
                is_param = True
            
            if not is_param:
                new_words.append(word)
        
        # 如果找到了参数，使用过滤后的提示词
        if found_model or found_ratio:
            prompt = " ".join(new_words)
        
        # 记录解析结果
        logger.debug(f"[Jimeng] Parsed prompt: '{prompt}', model: {model_key}, ratio: {ratio}")
        
        return prompt.strip(), model_key, ratio

    def _get_ratio_value(self, ratio: str) -> int:
        """将比例字符串转换为数值
        Args:
            ratio: 比例字符串，如 "4:3"
        Returns:
            int: 比例对应的数值
        """
        ratio_map = {
            "4:3": 4,
            "3:4": 3,
            "1:1": 1,
            "16:9": 16,
            "9:16": 9
        }
        return ratio_map.get(ratio, 1)

    def _get_headers(self):
        """获取请求头"""
        current_time = int(time.time())
        # 生成sign
        sign_data = f"{current_time}一只猫"  # 使用当前时间和提示词生成sign
        sign = hashlib.md5(sign_data.encode()).hexdigest()
        
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'app-sdk-version': '48.0.0',
            'appid': self.aid,
            'appvr': self.app_version,
            'content-type': 'application/json',
            'cookie': self.config.get("video_api", {}).get("cookie", ""),
            'device-time': str(current_time),
            'lan': 'zh-Hans',
            'loc': 'cn',
            'origin': 'https://jimeng.jianying.com',
            'pf': '7',
            'priority': 'u=1, i',
            'referer': 'https://jimeng.jianying.com/ai-tool/image/generate',
            'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'sign': sign,
            'sign-ver': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }

    def _get_params(self, model_req_key):
        """获取URL参数"""
        babi_param = {
            "scenario": "image_video_generation",
            "feature_key": "aigc_to_image",
            "feature_entrance": "to_image",
            "feature_entrance_detail": f"to_image-{model_req_key}"
        }
        return {
            "babi_param": json.dumps(babi_param, ensure_ascii=False),
            "aid": self.aid,
            "device_platform": "web",
            "region": "CN",
            "web_id": self.token_manager.get_web_id(),
            "msToken": self.config.get("video_api", {}).get("msToken", ""),
            "a_bogus": self.config.get("video_api", {}).get("a_bogus", "")
        }

    def _get_ratio_dimensions(self, ratio):
        """获取指定比例的图片尺寸
        Args:
            ratio: 图片比例，如 "1:1", "16:9", "9:16" 等
        Returns:
            tuple: (width, height)
        """
        ratios = self.config.get("params", {}).get("ratios", {})
        ratio_config = ratios.get(ratio)
        
        if not ratio_config:
            # 默认使用 1:1
            return (1024, 1024)
            
        return (ratio_config.get("width", 1024), ratio_config.get("height", 1024))

    def _get_model_key(self, model):
        """获取模型的实际key
        Args:
            model: 模型名称或简写
        Returns:
            str: 模型的实际key
        """
        # 处理简写
        model_map = {
            "20": "2.0",
            "21": "2.1",
            "20p": "2.0p",
            "xlpro": "xl",
            "xl": "xl"
        }
        
        # 如果是简写，转换为完整名称
        if model.lower() in model_map:
            model = model_map[model.lower()]
            
        # 获取模型配置
        models = self.config.get("params", {}).get("models", {})
        if model not in models:
            # 如果模型不存在，使用默认模型
            return self.config.get("params", {}).get("default_model", "2.1")
            
        return model

    def generate_image(self, prompt, model="2.1", ratio="1:1"):
        """生成图片
        Args:
            prompt: 提示词
            model: 模型名称
            ratio: 图片比例
        Returns:
            dict: 包含生成的图片URL列表
        """
        try:
            # 获取实际的模型key
            model = self._get_model_key(model)
            
            # 获取图片尺寸
            width, height = self._get_ratio_dimensions(ratio)
            
            # 生成随机种子
            seed = random.randint(1, 999999999)
            
            # 准备请求数据
            url = f"{self.base_url}/mweb/v1/aigc_draft/generate"
            
            # 获取模型配置
            models = self.config.get("params", {}).get("models", {})
            model_info = models.get(model, {})
            model_req_key = model_info.get("model_req_key", f"high_aes_general_v20:general_{model}")
            
            # 准备babi_param
            babi_param = {
                "scenario": "image_video_generation",
                "feature_key": "aigc_to_image",
                "feature_entrance": "to_image",
                "feature_entrance_detail": f"to_image-{model_req_key}"
            }
            
            # 生成唯一的submit_id
            submit_id = str(uuid.uuid4())
            draft_id = str(uuid.uuid4())
            component_id = str(uuid.uuid4())
            
            # 准备metrics_extra
            metrics_extra = {
                "templateId": "",
                "generateCount": 1,
                "promptSource": "custom",
                "templateSource": "",
                "lastRequestId": "",
                "originRequestId": "",
                "originSubmitId": "",
                "isDefaultSeed": 1,
                "originTemplateId": "",
                "imageNameMapping": {},
                "isUseAiGenPrompt": False,
                "batchNumber": 1
            }
            
            data = {
                "extend": {
                    "root_model": model_req_key,
                    "template_id": ""
                },
                "submit_id": submit_id,
                "metrics_extra": json.dumps(metrics_extra),
                "draft_content": json.dumps({
                    "type": "draft",
                    "id": draft_id,
                    "min_version": "3.0.2",
                    "min_features": [],
                    "is_from_tsn": True,
                    "version": "3.0.9",
                    "main_component_id": component_id,
                    "component_list": [{
                        "type": "image_base_component",
                        "id": component_id,
                        "min_version": "3.0.2",
                        "generate_type": "generate",
                        "aigc_mode": "workbench",
                        "abilities": {
                            "type": "",
                            "id": str(uuid.uuid4()),
                            "generate": {
                                "type": "",
                                "id": str(uuid.uuid4()),
                                "core_param": {
                                    "type": "",
                                    "id": str(uuid.uuid4()),
                                    "model": model_req_key,
                                    "prompt": prompt,
                                    "negative_prompt": "",
                                    "seed": seed,
                                    "sample_strength": 0.5,
                                    "image_ratio": 3 if ratio == "9:16" else self._get_ratio_value(ratio),
                                    "large_image_info": {
                                        "type": "",
                                        "id": str(uuid.uuid4()),
                                        "height": height,
                                        "width": width
                                    }
                                },
                                "history_option": {
                                    "type": "",
                                    "id": str(uuid.uuid4())
                                }
                            }
                        }
                    }]
                }),
                "http_common_info": {"aid": self.aid}
            }
            
            params = {
                "babi_param": json.dumps(babi_param),
                "aid": self.aid,
                "device_platform": "web",
                "region": "CN",
                "web_id": self.token_manager.get_web_id()
            }
            
            # 发送请求
            logger.debug(f"[Jimeng] Generating image with prompt: {prompt}, model: {model}, ratio: {ratio}")
            response = self._send_request("POST", url, params=params, json=data)
            
            if not response or response.get('ret') != '0':
                logger.error(f"[Jimeng] Failed to generate image: {response}")
                return None
                
            # 获取history_id
            history_id = response.get('data', {}).get('aigc_data', {}).get('history_record_id')
            if not history_id:
                logger.error("[Jimeng] No history_id in response")
                return None
                
            # 等待图片生成完成
            for _ in range(30):  # 最多等待30次
                time.sleep(2)  # 每次等待2秒
                image_urls = self._get_generated_images(history_id)
                if image_urls:
                    return {"urls": image_urls}
                    
            logger.error("[Jimeng] Image generation timeout")
            return None
            
        except Exception as e:
            logger.error(f"[Jimeng] Error generating image: {e}")
            return None

    def cleanup_temp_files(self):
        """清理临时文件"""
        for file in self.temp_files:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except Exception as e:
                logger.warning(f"[Jimeng] Failed to remove temp file {file}: {e}")
        self.temp_files = [] 