import os
import time
import requests
from PIL import Image
from io import BytesIO
import math
import logging
from retry import retry
from requests.exceptions import SSLError, ConnectionError, Timeout, RequestException

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        self.image_data = {}  # 初始化图片数据字典
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

    @retry(
        tries=5,
        delay=1,
        backoff=2,
        exceptions=(SSLError, ConnectionError, Timeout, RequestException),
        logger=logger
    )
    def _download_with_retry(self, url, timeout=30):
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response

    def get_file_path(self, filename: str) -> str:
        """获取文件路径"""
        return os.path.join(self.temp_dir, filename)

    def download_image(self, prefix, urls):
        for idx, url in enumerate(urls):
            try:
                response = self._download_with_retry(url)
                if response and response.status_code == 200:
                    img_data = BytesIO(response.content)
                    img = Image.open(img_data)
                    img.save(os.path.join(self.temp_dir, f"{prefix}_{idx}.jpeg"))
                else:
                    logger.error(f"[Jimeng] 下载图片失败: {url}")
            except Exception as e:
                logger.error(f"[Jimeng] 下载图片失败: {url}, 错误: {e}")
        return None  
    
        """将多张图片合并为一张图片并保存
        Args:
            images: 图片列表(每个元素可以是PIL.Image对象、文件路径或URL)
            output_path: 输出文件路径,如果为None则使用临时文件
        Returns:
            file: 保存的图片文件对象
        """
        try:
            # 如果没有指定输出路径，使用临时文件
            if not output_path:
                output_path = os.path.join(self.temp_dir, f"combined_{int(time.time())}.jpg")
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 获取所有图片
            pil_images = []
            for img in images:
                if isinstance(img, Image.Image):
                    pil_images.append(img)
                elif isinstance(img, str):
                    if img.startswith(('http://', 'https://')):
                        # 下载URL图片
                        try:
                            response = self._download_with_retry(img)
                            if response and response.status_code == 200:
                                img_data = BytesIO(response.content)
                                pil_images.append(Image.open(img_data))
                                logger.info(f"[Jimeng] 成功下载图片: {img}")
                            else:
                                logger.error(f"[Jimeng] 下载图片失败，状态码: {response.status_code if response else 'No response'}")
                                continue
                        except Exception as e:
                            logger.error(f"[Jimeng] 下载图片失败: {img}, 错误: {e}")
                            continue
                    else:
                        # 加载本地图片
                        pil_images.append(Image.open(img))
                elif isinstance(img, bytes):
                    # 从字节数据加载图片
                    img_data = BytesIO(img)
                    pil_images.append(Image.open(img_data))
                elif hasattr(img, 'read'):
                    # 从文件对象加载图片
                    pil_images.append(Image.open(img))
            
            if not pil_images:
                logger.error("[Jimeng] No valid images to combine")
                return None
            
            # 调整所有图片大小为相同尺寸
            target_size = (512, 512)  # 可以根据需要调整
            resized_images = [img.resize(target_size) for img in pil_images]
            
            # 计算合并图片的布局
            num_images = len(resized_images)
            if num_images == 1:
                cols, rows = 1, 1
            elif num_images == 2:
                cols, rows = 2, 1
            elif num_images <= 4:
                cols, rows = 2, 2
            else:
                cols = math.ceil(math.sqrt(num_images))
                rows = math.ceil(num_images / cols)
            
            # 创建空白画布
            canvas_width = cols * target_size[0]
            canvas_height = rows * target_size[1]
            canvas = Image.new('RGB', (canvas_width, canvas_height), 'white')
            
            # 粘贴图片到画布
            for idx, img in enumerate(resized_images):
                x = (idx % cols) * target_size[0]
                y = (idx // cols) * target_size[1]
                canvas.paste(img, (x, y))
            
            # 保存合并后的图片
            canvas.save(output_path, 'JPEG', quality=95)
            logger.info(f"[Jimeng] Successfully saved combined image to {output_path}")
            
            # 返回文件对象
            return open(output_path, 'rb')
            
        except Exception as e:
            logger.error(f"[Jimeng] Error combining images: {e}")
            return None
        finally:
            # 清理PIL图片对象
            for img in pil_images:
                try:
                    img.close()
                except:
                    pass 