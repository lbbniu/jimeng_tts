from dataclasses import dataclass
from enum import Enum

class TaskStatus(Enum):
    """任务状态枚举"""
    ALL = 0
    PENDING = 20
    COMPLETED = 50
    FAILED = 60

class ModelType(Enum):
    """模型类型枚举 - 基于config.json中的models配置"""
    V2_1 = "2.1"      # 图片 2.1 - 平面绘感强，可生成文字海报
    V2_0 = "2.0"      # 图片 2.0 - 文字遵循高，支持图片参考能力
    V2_0_PRO = "2.0p" # 图片 2.0 Pro - 极具想象力，擅长写真摄影
    V3_0 = "3.0"      # 图片 3.0 - 影视质感，文字更准，直出2k高清图
    V3_1 = "3.1"      # 图片 3.1 - 丰富的美学多样性，画面更鲜明生动

class RatioType(Enum):
    """比例类型枚举 - 基于config.json中的v2_ratios和v3_ratios配置"""
    SQUARE = "1:1"        # 正方形 1024x1024 (v2) / 1328x1328 (v3)
    PORTRAIT_9_16 = "9:16" # 竖屏 576x1024 (v2) / 936x1664 (v3)
    LANDSCAPE_16_9 = "16:9" # 横屏 1024x576 (v2) / 1664x936 (v3)
    WIDE_21_9 = "21:9"     # 超宽屏 1195x512 (v2) / 2016x864 (v3)
    PORTRAIT_3_4 = "3:4"   # 竖屏 768x1024 (v2) / 1104x1472 (v3)
    LANDSCAPE_4_3 = "4:3"  # 横屏 1024x768 (v2) / 1472x1104 (v3)
    PORTRAIT_2_3 = "2:3"   # 竖屏 682x1024 (v2) / 1056x1584 (v3)
    LANDSCAPE_3_2 = "3:2"  # 横屏 1024x682 (v2) / 1584x1056 (v3)

class VideoRatioType(Enum):
    """视频比例类型枚举 - 基于config.json中的video_ratios配置"""
    SQUARE = "1:1"        # 正方形 1024x1024
    PORTRAIT_9_16 = "9:16" # 竖屏 576x1024
    LANDSCAPE_16_9 = "16:9" # 横屏 1024x576
    WIDE_21_9 = "21:9"     # 超宽屏 1195x512
    PORTRAIT_3_4 = "3:4"   # 竖屏 768x1024
    LANDSCAPE_4_3 = "4:3"  # 横屏 1024x768

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