import random
import logging

logger = logging.getLogger(__name__)

class TokenManager:
    def __init__(self, config):
        self.config = config
        self.web_id = None
        self._extract_web_id_from_cookie()
        
        # 如果没有从cookie中提取到web_id，则生成一个新的
        if not self.web_id:
            self.web_id = self._generate_web_id()
        
    def _extract_web_id_from_cookie(self):
        """从cookie中提取web_id"""
        try:
            cookie = self.config.get("video_api", {}).get("cookie", "")
            if not cookie:
                return
                
            # 查找_tea_web_id或web_id
            for cookie_item in cookie.split(';'):
                cookie_item = cookie_item.strip()
                if cookie_item.startswith('_tea_web_id='):
                    self.web_id = cookie_item.split('=')[1]
                    break
                elif cookie_item.startswith('web_id='):
                    self.web_id = cookie_item.split('=')[1]
                    break
                elif cookie_item.startswith('_v2_spipe_web_id='):
                    self.web_id = cookie_item.split('=')[1]
                    break
        except Exception as e:
            logger.error(f"[Jimeng] Failed to extract web_id from cookie: {e}")
            
    def _generate_web_id(self):
        """生成新的web_id"""
        # 生成一个19位的随机数字字符串
        web_id = ''.join([str(random.randint(0, 9)) for _ in range(19)])
        return web_id
    
    def get_web_id(self):
        """获取web_id"""
        if not self.web_id:
            self.web_id = self._generate_web_id()
        return self.web_id
        
    def get_token(self):
        """获取token信息"""
        return {
            "msToken": self.config.get("video_api", {}).get("msToken", ""),
            "a_bogus": self.config.get("video_api", {}).get("a_bogus", "")
        } 