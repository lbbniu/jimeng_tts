import sqlite3
import json
import time
import logging
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """数据库配置"""
    max_connections: int = 10
    timeout: float = 30.0
    check_same_thread: bool = False
    journal_mode: str = "WAL"  # Write-Ahead Logging
    synchronous: str = "NORMAL"
    cache_size: int = -64000  # 64MB cache
    temp_store: str = "MEMORY"

class ConnectionPool:
    """SQLite连接池"""
    
    def __init__(self, db_path: str, config: DatabaseConfig):
        self.db_path = db_path
        self.config = config
        self._pool = []
        self._used = set()
        self._lock = threading.Lock()
        self._created_connections = 0
        
        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[ImageStorage] 初始化连接池: {db_path}")
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.config.timeout,
                check_same_thread=self.config.check_same_thread
            )
            
            # 优化数据库配置
            conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")
            conn.execute(f"PRAGMA synchronous = {self.config.synchronous}")
            conn.execute(f"PRAGMA cache_size = {self.config.cache_size}")
            conn.execute(f"PRAGMA temp_store = {self.config.temp_store}")
            conn.execute("PRAGMA foreign_keys = ON")
            
            # 启用行工厂以获得字典形式的结果
            conn.row_factory = sqlite3.Row
            
            self._created_connections += 1
            logger.debug(f"[ImageStorage] 创建新连接 #{self._created_connections}")
            
            return conn
            
        except Exception as e:
            logger.error(f"[ImageStorage] 创建数据库连接失败: {e}")
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        with self._lock:
            if self._pool:
                conn = self._pool.pop()
                self._used.add(conn)
                logger.debug(f"[ImageStorage] 复用连接，池中剩余: {len(self._pool)}")
                return conn
            
            if self._created_connections < self.config.max_connections:
                conn = self._create_connection()
                self._used.add(conn)
                return conn
            
            # 如果达到最大连接数，创建临时连接
            logger.warning(f"[ImageStorage] 达到最大连接数 {self.config.max_connections}，创建临时连接")
            return self._create_connection()
    
    def return_connection(self, conn: sqlite3.Connection):
        """归还数据库连接"""
        with self._lock:
            if conn in self._used:
                self._used.remove(conn)
            
            if len(self._pool) < self.config.max_connections:
                self._pool.append(conn)
                logger.debug(f"[ImageStorage] 归还连接，池中数量: {len(self._pool)}")
            else:
                conn.close()
                logger.debug("[ImageStorage] 关闭多余连接")
    
    def close_all(self):
        """关闭所有连接"""
        with self._lock:
            # 关闭池中的连接
            for conn in self._pool:
                try:
                    conn.close()
                except:
                    pass
            self._pool.clear()
            
            # 关闭正在使用的连接
            for conn in self._used:
                try:
                    conn.close()
                except:
                    pass
            self._used.clear()
            
            logger.info(f"[ImageStorage] 已关闭所有数据库连接")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._lock:
            return {
                "pool_size": len(self._pool),
                "used_connections": len(self._used),
                "total_created": self._created_connections,
                "max_connections": self.config.max_connections
            }

class ImageStorage:
    """优化后的图片存储类"""
    
    def __init__(self, db_path: str, retention_days: int = 7, config: Optional[DatabaseConfig] = None):
        self.db_path = db_path
        self.retention_days = retention_days
        self.config = config or DatabaseConfig()
        
        # 性能统计 - 必须在初始化数据库之前设置
        self._stats = {
            "operations": 0,
            "errors": 0,
            "total_time": 0.0
        }
        
        # 初始化连接池
        self.pool = ConnectionPool(db_path, self.config)
        
        # 初始化数据库
        self._init_db()
        
        logger.info(f"[ImageStorage] 初始化完成: {db_path}, 保留天数: {retention_days}")
    
    @contextmanager
    def get_connection(self):
        """连接上下文管理器"""
        conn = None
        start_time = time.time()
        try:
            conn = self.pool.get_connection()
            yield conn
            self._stats["operations"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[ImageStorage] 数据库操作错误: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.return_connection(conn)
            self._stats["total_time"] += time.time() - start_time
    
    def _init_db(self):
        """初始化数据库和索引"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 创建图片信息表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS images (
                        id TEXT PRIMARY KEY,
                        urls TEXT,
                        metadata TEXT,
                        create_time INTEGER NOT NULL,
                        update_time INTEGER DEFAULT (strftime('%s', 'now')),
                        status INTEGER DEFAULT 0,  -- 0: pending, 1: completed, 2: failed
                        file_size INTEGER DEFAULT 0,
                        download_count INTEGER DEFAULT 0
                    )
                ''')
                
                # 创建索引以提高查询性能
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_create_time ON images(create_time)",
                    "CREATE INDEX IF NOT EXISTS idx_status ON images(status)",
                    "CREATE INDEX IF NOT EXISTS idx_update_time ON images(update_time)",
                    "CREATE INDEX IF NOT EXISTS idx_create_status ON images(create_time, status)"
                ]
                
                for index_sql in indexes:
                    cursor.execute(index_sql)
                
                # 创建统计表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS storage_stats (
                        id INTEGER PRIMARY KEY,
                        date TEXT UNIQUE,
                        total_images INTEGER DEFAULT 0,
                        total_size INTEGER DEFAULT 0,
                        operations INTEGER DEFAULT 0,
                        last_cleanup INTEGER DEFAULT 0
                    )
                ''')
                
                conn.commit()
                logger.info("[ImageStorage] 数据库初始化完成")
                
        except Exception as e:
            logger.error(f"[ImageStorage] 数据库初始化失败: {e}")
            raise
    
    def store_image(self, img_id: str, metadata: Optional[Dict[str, Any]] = None, status: int = 0) -> bool:
        """存储图片信息
        
        Args:
            img_id: 图片ID
            metadata: 元数据字典
            status: 状态 (0: pending, 1: completed, 2: failed)
            
        Returns:
            bool: 是否存储成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
                current_time = int(time.time())
                
                cursor.execute('''
                    INSERT OR REPLACE INTO images 
                    (id, metadata, create_time, update_time, status) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (img_id, metadata_json, current_time, current_time, status))
                
                conn.commit()
                logger.debug(f"[ImageStorage] 存储图片信息: {img_id}")
                return True
                
        except Exception as e:
            logger.error(f"[ImageStorage] 存储图片信息失败 {img_id}: {e}")
            return False
    
    def store_images_batch(self, images_data: List[Tuple[str, Optional[Dict[str, Any]], int]]) -> int:
        """批量存储图片信息
        
        Args:
            images_data: 图片数据列表 [(img_id, metadata, status), ...]
            
        Returns:
            int: 成功存储的数量
        """
        if not images_data:
            return 0
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                current_time = int(time.time())
                
                # 准备批量数据
                batch_data = []
                for img_id, metadata, status in images_data:
                    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
                    batch_data.append((img_id, metadata_json, current_time, current_time, status))
                
                cursor.executemany('''
                    INSERT OR REPLACE INTO images 
                    (id, metadata, create_time, update_time, status) 
                    VALUES (?, ?, ?, ?, ?)
                ''', batch_data)
                
                conn.commit()
                success_count = cursor.rowcount
                logger.info(f"[ImageStorage] 批量存储 {success_count}/{len(images_data)} 张图片")
                return success_count
                
        except Exception as e:
            logger.error(f"[ImageStorage] 批量存储失败: {e}")
            return 0
    
    def update_image(self, img_id: str, urls: Optional[List[str]] = None, 
                    status: Optional[int] = None, file_size: Optional[int] = None) -> bool:
        """更新图片信息
        
        Args:
            img_id: 图片ID
            urls: 图片URL列表
            status: 新状态
            file_size: 文件大小
            
        Returns:
            bool: 是否更新成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 构建动态更新SQL
                update_fields = []
                params = []
                
                if urls is not None:
                    update_fields.append("urls = ?")
                    params.append(json.dumps(urls, ensure_ascii=False))
                
                if status is not None:
                    update_fields.append("status = ?")
                    params.append(status)
                
                if file_size is not None:
                    update_fields.append("file_size = ?")
                    params.append(file_size)
                
                if not update_fields:
                    return True  # 没有要更新的字段
                
                update_fields.append("update_time = ?")
                params.append(int(time.time()))
                params.append(img_id)
                
                sql = f"UPDATE images SET {', '.join(update_fields)} WHERE id = ?"
                
                cursor.execute(sql, params)
                conn.commit()
                
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"[ImageStorage] 更新图片信息: {img_id}")
                else:
                    logger.warning(f"[ImageStorage] 图片不存在，无法更新: {img_id}")
                
                return success
                
        except Exception as e:
            logger.error(f"[ImageStorage] 更新图片信息失败 {img_id}: {e}")
            return False
    
    def get_image(self, img_id: str, check_expired: bool = True) -> Optional[Dict[str, Any]]:
        """获取图片信息
        
        Args:
            img_id: 图片ID
            check_expired: 是否检查过期
            
        Returns:
            Optional[Dict[str, Any]]: 图片信息字典
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, urls, metadata, create_time, update_time, status, file_size, download_count
                    FROM images WHERE id = ?
                ''', (img_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # 转换为字典
                image_data = dict(row)
                
                # 解析JSON字段
                if image_data['urls']:
                    image_data['urls'] = json.loads(image_data['urls'])
                
                if image_data['metadata']:
                    image_data['metadata'] = json.loads(image_data['metadata'])
                
                # 检查是否过期
                if check_expired and self._is_expired(image_data['create_time']):
                    self.delete_image(img_id)
                    return None
                
                # 增加下载计数
                cursor.execute(
                    'UPDATE images SET download_count = download_count + 1 WHERE id = ?',
                    (img_id,)
                )
                conn.commit()
                
                return image_data
                
        except Exception as e:
            logger.error(f"[ImageStorage] 获取图片信息失败 {img_id}: {e}")
            return None
    
    def get_images_by_status(self, status: int, limit: int = 100) -> List[Dict[str, Any]]:
        """根据状态获取图片列表
        
        Args:
            status: 图片状态
            limit: 返回数量限制
            
        Returns:
            List[Dict[str, Any]]: 图片信息列表
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, urls, metadata, create_time, update_time, status, file_size, download_count
                    FROM images 
                    WHERE status = ? 
                    ORDER BY create_time ASC 
                    LIMIT ?
                ''', (status, limit))
                
                rows = cursor.fetchall()
                images = []
                
                for row in rows:
                    image_data = dict(row)
                    
                    # 解析JSON字段
                    if image_data['urls']:
                        image_data['urls'] = json.loads(image_data['urls'])
                    
                    if image_data['metadata']:
                        image_data['metadata'] = json.loads(image_data['metadata'])
                    
                    images.append(image_data)
                
                return images
                
        except Exception as e:
            logger.error(f"[ImageStorage] 获取状态图片列表失败 {status}: {e}")
            return []
    
    def delete_image(self, img_id: str) -> bool:
        """删除图片信息
        
        Args:
            img_id: 图片ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM images WHERE id = ?', (img_id,))
                conn.commit()
                
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"[ImageStorage] 删除图片: {img_id}")
                
                return success
                
        except Exception as e:
            logger.error(f"[ImageStorage] 删除图片失败 {img_id}: {e}")
            return False
    
    def delete_images_batch(self, img_ids: List[str]) -> int:
        """批量删除图片
        
        Args:
            img_ids: 图片ID列表
            
        Returns:
            int: 成功删除的数量
        """
        if not img_ids:
            return 0
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 使用IN查询批量删除
                placeholders = ','.join('?' * len(img_ids))
                cursor.execute(f'DELETE FROM images WHERE id IN ({placeholders})', img_ids)
                conn.commit()
                
                deleted_count = cursor.rowcount
                logger.info(f"[ImageStorage] 批量删除 {deleted_count}/{len(img_ids)} 张图片")
                return deleted_count
                
        except Exception as e:
            logger.error(f"[ImageStorage] 批量删除失败: {e}")
            return 0
    
    def cleanup_expired(self) -> int:
        """清理过期的图片信息
        
        Returns:
            int: 清理的数量
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 计算过期时间
                expire_time = int(time.time()) - self.retention_days * 24 * 3600
                
                # 首先查询要删除的数量
                cursor.execute('SELECT COUNT(*) FROM images WHERE create_time < ?', (expire_time,))
                count_to_delete = cursor.fetchone()[0]
                
                if count_to_delete == 0:
                    logger.debug("[ImageStorage] 没有过期图片需要清理")
                    return 0
                
                # 删除过期数据
                cursor.execute('DELETE FROM images WHERE create_time < ?', (expire_time,))
                conn.commit()
                
                # 更新统计信息
                self._update_cleanup_stats(conn, count_to_delete)
                
                logger.info(f"[ImageStorage] 清理过期图片: {count_to_delete} 张")
                return count_to_delete
                
        except Exception as e:
            logger.error(f"[ImageStorage] 清理过期图片失败: {e}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 基本统计
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_images,
                        COUNT(CASE WHEN status = 0 THEN 1 END) as pending_images,
                        COUNT(CASE WHEN status = 1 THEN 1 END) as completed_images,
                        COUNT(CASE WHEN status = 2 THEN 1 END) as failed_images,
                        SUM(file_size) as total_size,
                        AVG(file_size) as avg_size,
                        MIN(create_time) as oldest_time,
                        MAX(create_time) as newest_time
                    FROM images
                ''')
                
                stats = dict(cursor.fetchone())
                
                # 连接池统计
                pool_stats = self.pool.get_stats()
                
                # 性能统计
                performance_stats = self._stats.copy()
                if performance_stats["operations"] > 0:
                    performance_stats["avg_operation_time"] = performance_stats["total_time"] / performance_stats["operations"]
                else:
                    performance_stats["avg_operation_time"] = 0.0
                
                # 合并所有统计信息
                return {
                    "database": stats,
                    "connection_pool": pool_stats,
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
    
    def _update_cleanup_stats(self, conn: sqlite3.Connection, cleaned_count: int):
        """更新清理统计"""
        try:
            cursor = conn.cursor()
            today = time.strftime('%Y-%m-%d')
            
            cursor.execute('''
                INSERT OR REPLACE INTO storage_stats 
                (date, last_cleanup) VALUES (?, ?)
            ''', (today, int(time.time())))
            
        except Exception as e:
            logger.warning(f"[ImageStorage] 更新清理统计失败: {e}")
    
    def optimize_database(self) -> bool:
        """优化数据库
        
        Returns:
            bool: 是否优化成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                logger.info("[ImageStorage] 开始优化数据库...")
                
                # 分析查询计划
                cursor.execute('ANALYZE')
                
                # 重建索引
                cursor.execute('REINDEX')
                
                # 压缩数据库
                cursor.execute('VACUUM')
                
                conn.commit()
                logger.info("[ImageStorage] 数据库优化完成")
                return True
                
        except Exception as e:
            logger.error(f"[ImageStorage] 数据库优化失败: {e}")
            return False
    
    def backup_database(self, backup_path: str) -> bool:
        """备份数据库
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            bool: 是否备份成功
        """
        try:
            with self.get_connection() as conn:
                # 确保备份目录存在
                Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
                
                backup_conn = sqlite3.connect(backup_path)
                conn.backup(backup_conn)
                backup_conn.close()
                
                logger.info(f"[ImageStorage] 数据库备份完成: {backup_path}")
                return True
                
        except Exception as e:
            logger.error(f"[ImageStorage] 数据库备份失败: {e}")
            return False
    
    def close(self):
        """关闭存储，清理资源"""
        try:
            self.pool.close_all()
            logger.info("[ImageStorage] 存储已关闭")
        except Exception as e:
            logger.error(f"[ImageStorage] 关闭存储失败: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close() 