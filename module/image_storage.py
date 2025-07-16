import json
import time
import logging
from typing import Dict, List, Any, Tuple
from pathlib import Path
from tortoise import Tortoise, fields, models
from tortoise.contrib.pydantic import pydantic_model_creator

logger = logging.getLogger(__name__)

class ImageModel(models.Model):
    """图片数据模型"""
    
    id = fields.CharField(max_length=255, pk=True, description="图片ID")
    urls = fields.JSONField(null=True, description="图片URL列表")
    metadata = fields.JSONField(null=True, description="元数据")
    status = fields.IntField(default=0, description="状态: 0=pending, 1=completed, 2=failed")
    file_size = fields.BigIntField(default=0, description="文件大小")
    download_count = fields.IntField(default=0, description="下载次数")
    create_time = fields.BigIntField(description="创建时间戳")
    update_time = fields.BigIntField(default=int(time.time()), description="更新时间戳")
    
    class Meta:
        table = "images"
        table_description = "图片信息表"
    
    def __str__(self):
        return f"Image(id={self.id}, status={self.status})"

class StorageStatsModel(models.Model):
    """存储统计模型"""
    
    id = fields.IntField(pk=True, description="主键ID")
    date = fields.CharField(max_length=10, unique=True, description="日期")
    total_images = fields.IntField(default=0, description="总图片数")
    total_size = fields.BigIntField(default=0, description="总大小")
    operations = fields.IntField(default=0, description="操作次数")
    last_cleanup = fields.BigIntField(default=0, description="最后清理时间")
    
    class Meta:
        table = "storage_stats"
        table_description = "存储统计表"
    
    def __str__(self):
        return f"StorageStats(date={self.date})"

# 创建Pydantic模型用于序列化
ImagePydantic = pydantic_model_creator(ImageModel, name="Image")
StorageStatsPydantic = pydantic_model_creator(StorageStatsModel, name="StorageStats")

class ImageStorage:
    """使用Tortoise ORM的图片存储类"""
    
    def __init__(self, db_path: str, retention_days: int = 7):
        self.db_path = db_path
        self.retention_days = retention_days
        self._initialized = False
        
        # 性能统计
        self._stats = {
            "operations": 0,
            "errors": 0,
            "total_time": 0.0
        }
        
        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[ImageStorage] 初始化: {db_path}, 保留天数: {retention_days}")
    
    async def init_db(self):
        """初始化数据库"""
        if self._initialized:
            return
        
        try:
            # 配置数据库连接
            await Tortoise.init(
                db_url=f"sqlite://{self.db_path}",
                modules={"models": [__name__]}
            )
            
            # 生成数据库表
            await Tortoise.generate_schemas()
            
            self._initialized = True
            logger.info("[ImageStorage] 数据库初始化完成")
            
        except Exception as e:
            logger.error(f"[ImageStorage] 数据库初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭数据库连接"""
        if self._initialized:
            await Tortoise.close_connections()
            self._initialized = False
            logger.info("[ImageStorage] 数据库连接已关闭")
    
    async def store_image(self, img_id: str, metadata: Dict[str, Any] | None = None, status: int = 0) -> bool:
        """存储图片信息
        
        Args:
            img_id: 图片ID
            metadata: 元数据字典
            status: 状态 (0: pending, 1: completed, 2: failed)
            
        Returns:
            bool: 是否存储成功
        """
        start_time = time.time()
        try:
            await self.init_db()
            
            current_time = int(time.time())
            
            # 使用get_or_create避免重复插入
            image, created = await ImageModel.get_or_create(
                id=img_id,
                defaults={
                    "metadata": metadata,
                    "create_time": current_time,
                    "update_time": current_time,
                    "status": status
                }
            )
            
            if not created:
                # 更新现有记录
                image.metadata = metadata
                image.status = status
                image.update_time = current_time
                await image.save()
            
            self._stats["operations"] += 1
            logger.debug(f"[ImageStorage] 存储图片信息: {img_id}")
            return True
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 存储图片信息失败 {img_id}: {e}")
            return False
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def store_images_batch(self, images_data: List[Tuple[str, Dict[str, Any] | None, int]]) -> int:
        """批量存储图片信息
        
        Args:
            images_data: 图片数据列表 [(img_id, metadata, status), ...]
            
        Returns:
            int: 成功存储的数量
        """
        if not images_data:
            return 0
        
        start_time = time.time()
        try:
            await self.init_db()
            
            current_time = int(time.time())
            success_count = 0
            
            for img_id, metadata, status in images_data:
                try:
                    image, created = await ImageModel.get_or_create(
                        id=img_id,
                        defaults={
                            "metadata": metadata,
                            "create_time": current_time,
                            "update_time": current_time,
                            "status": status
                        }
                    )
                    
                    if not created:
                        image.metadata = metadata
                        image.status = status
                        image.update_time = current_time
                        await image.save()
                    
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"[ImageStorage] 批量存储失败 {img_id}: {e}")
            
            self._stats["operations"] += 1
            logger.info(f"[ImageStorage] 批量存储 {success_count}/{len(images_data)} 张图片")
            return success_count
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 批量存储失败: {e}")
            return 0
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def update_image(self, img_id: str, urls: List[str] | None = None, 
                          status: int | None = None, file_size: int | None = None) -> bool:
        """更新图片信息
        
        Args:
            img_id: 图片ID
            urls: 图片URL列表
            status: 新状态
            file_size: 文件大小
            
        Returns:
            bool: 是否更新成功
        """
        start_time = time.time()
        try:
            await self.init_db()
            
            image = await ImageModel.get_or_none(id=img_id)
            if not image:
                logger.warning(f"[ImageStorage] 图片不存在，无法更新: {img_id}")
                return False
            
            # 更新字段
            if urls is not None:
                image.urls = urls
            if status is not None:
                image.status = status
            if file_size is not None:
                image.file_size = file_size
            
            await image.save()
            
            self._stats["operations"] += 1
            logger.debug(f"[ImageStorage] 更新图片信息: {img_id}")
            return True
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 更新图片信息失败 {img_id}: {e}")
            return False
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def get_image(self, img_id: str, check_expired: bool = True) -> Dict[str, Any] | None:
        """获取图片信息
        
        Args:
            img_id: 图片ID
            check_expired: 是否检查过期
            
        Returns:
            Dict[str, Any] | None: 图片信息字典
        """
        start_time = time.time()
        try:
            await self.init_db()
            
            image = await ImageModel.get_or_none(id=img_id)
            if not image:
                return None
            
            # 检查是否过期
            if check_expired and self._is_expired(image.create_time):
                await self.delete_image(img_id)
                return None
            
            # 增加下载计数
            image.download_count += 1
            await image.save()
            
            # 转换为字典
            image_dict = await ImagePydantic.from_tortoise_orm(image)
            
            self._stats["operations"] += 1
            return image_dict.dict()
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 获取图片信息失败 {img_id}: {e}")
            return None
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def get_images_by_status(self, status: int, limit: int = 100) -> List[Dict[str, Any]]:
        """根据状态获取图片列表
        
        Args:
            status: 图片状态
            limit: 返回数量限制
            
        Returns:
            List[Dict[str, Any]]: 图片信息列表
        """
        start_time = time.time()
        try:
            await self.init_db()
            
            images = await ImageModel.filter(status=status).order_by('create_time').limit(limit)
            
            # 转换为字典列表
            result = []
            for image in images:
                image_dict = await ImagePydantic.from_tortoise_orm(image)
                result.append(image_dict.dict())
            
            self._stats["operations"] += 1
            return result
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 获取状态图片列表失败 {status}: {e}")
            return []
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def delete_image(self, img_id: str) -> bool:
        """删除图片信息
        
        Args:
            img_id: 图片ID
            
        Returns:
            bool: 是否删除成功
        """
        start_time = time.time()
        try:
            await self.init_db()
            
            deleted_count = await ImageModel.filter(id=img_id).delete()
            
            self._stats["operations"] += 1
            if deleted_count > 0:
                logger.debug(f"[ImageStorage] 删除图片: {img_id}")
            
            return deleted_count > 0
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 删除图片失败 {img_id}: {e}")
            return False
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def delete_images_batch(self, img_ids: List[str]) -> int:
        """批量删除图片
        
        Args:
            img_ids: 图片ID列表
            
        Returns:
            int: 成功删除的数量
        """
        if not img_ids:
            return 0
        
        start_time = time.time()
        try:
            await self.init_db()
            
            deleted_count = await ImageModel.filter(id__in=img_ids).delete()
            
            self._stats["operations"] += 1
            logger.info(f"[ImageStorage] 批量删除 {deleted_count}/{len(img_ids)} 张图片")
            return deleted_count
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 批量删除失败: {e}")
            return 0
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def cleanup_expired(self) -> int:
        """清理过期的图片信息
        
        Returns:
            int: 清理的数量
        """
        start_time = time.time()
        try:
            await self.init_db()
            
            # 计算过期时间
            expire_time = int(time.time()) - self.retention_days * 24 * 3600
            
            # 删除过期数据
            deleted_count = await ImageModel.filter(create_time__lt=expire_time).delete()
            
            if deleted_count > 0:
                # 更新统计信息
                await self._update_cleanup_stats(deleted_count)
                logger.info(f"[ImageStorage] 清理过期图片: {deleted_count} 张")
            else:
                logger.debug("[ImageStorage] 没有过期图片需要清理")
            
            self._stats["operations"] += 1
            return deleted_count
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 清理过期图片失败: {e}")
            return 0
        finally:
            self._stats["total_time"] += time.time() - start_time
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            await self.init_db()
            
            # 基本统计
            total_images = await ImageModel.all().count()
            pending_images = await ImageModel.filter(status=0).count()
            completed_images = await ImageModel.filter(status=1).count()
            failed_images = await ImageModel.filter(status=2).count()
            
            # 文件大小统计（简化版本）
            all_images = await ImageModel.all()
            total_size = sum(img.file_size for img in all_images)
            avg_size = total_size / len(all_images) if all_images else 0
            
            # 时间范围统计（简化版本）
            if all_images:
                oldest_time = min(img.create_time for img in all_images)
                newest_time = max(img.create_time for img in all_images)
            else:
                oldest_time = newest_time = 0
            
            # 性能统计
            performance_stats = self._stats.copy()
            if performance_stats["operations"] > 0:
                performance_stats["avg_operation_time"] = performance_stats["total_time"] / performance_stats["operations"]
            else:
                performance_stats["avg_operation_time"] = 0.0
            
            return {
                "database": {
                    "total_images": total_images,
                    "pending_images": pending_images,
                    "completed_images": completed_images,
                    "failed_images": failed_images,
                    "total_size": total_size,
                    "avg_size": avg_size,
                    "oldest_time": oldest_time,
                    "newest_time": newest_time
                },
                "performance": performance_stats,
                "config": {
                    "retention_days": self.retention_days,
                    "db_path": self.db_path
                }
            }
            
        except Exception as e:
            logger.error(f"[ImageStorage] 获取统计信息失败: {e}")
            return {}
    
    def _is_expired(self, create_time: int) -> bool:
        """检查是否过期"""
        return time.time() - create_time > self.retention_days * 24 * 3600
    
    async def _update_cleanup_stats(self, cleaned_count: int):
        """更新清理统计"""
        try:
            await self.init_db()
            
            today = time.strftime('%Y-%m-%d')
            stats, created = await StorageStatsModel.get_or_create(
                date=today,
                defaults={"last_cleanup": int(time.time())}
            )
            
            if not created:
                stats.last_cleanup = int(time.time())
                await stats.save()
            
        except Exception as e:
            logger.warning(f"[ImageStorage] 更新清理统计失败: {e}")
    
    async def optimize_database(self) -> bool:
        """优化数据库
        
        Returns:
            bool: 是否优化成功
        """
        try:
            await self.init_db()
            
            logger.info("[ImageStorage] 开始优化数据库...")
            
            # Tortoise ORM 会自动处理数据库优化
            # 这里可以添加自定义的优化逻辑
            
            logger.info("[ImageStorage] 数据库优化完成")
            return True
            
        except Exception as e:
            logger.error(f"[ImageStorage] 数据库优化失败: {e}")
            return False
    
    async def backup_database(self, backup_path: str) -> bool:
        """备份数据库
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            bool: 是否备份成功
        """
        try:
            # 确保备份目录存在
            Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 简单的文件复制备份
            import shutil
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"[ImageStorage] 数据库备份完成: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"[ImageStorage] 数据库备份失败: {e}")
            return False
    
    async def get_original_image(self, img_id: str, index: int) -> tuple:
        """获取原始图片
        Args:
            img_id: 图片ID
            index: 图片序号（1-based）
        Returns:
            tuple: (image_content/url, error_message)
        """
        try:
            # 从存储中获取图片信息
            image_info = await self.get_image(img_id)
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
            logger.error(f"[ImageStorage] Error getting original image: {e}")
            return None, f"获取图片失败: {str(e)}"
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.init_db()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
    
    def __enter__(self):
        """同步上下文管理器入口（兼容性）"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.init_db())
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """同步上下文管理器出口（兼容性）"""
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.close())
        loop.close() 