import os
import json
import logging
from typing import Dict, Any
from .core_types import GenerationConfig, ApiConfig

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "../config.json")
        
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