import time
from typing import Dict, Any, List
from .core_types import TaskStatus
import logging

logger = logging.getLogger(__name__)

class ImageGenerationTask:
    """图片生成任务"""
    def __init__(self, task_id: str, prompt: str, model: str, ratio: str, metadata: Dict[str, Any] | None = None):
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
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.time()
        self.result = result
    
    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.completed_at = time.time()
        self.error = error
    
    def get_duration(self) -> float:
        if self.completed_at:
            return self.completed_at - self.created_at
        return time.time() - self.created_at

class BatchProcessor:
    """批处理器 - 顺序处理（因为接口不支持并发调用）"""
    def __init__(self, request_delay: float = 1.0):
        self.request_delay = request_delay
        self.tasks: List[ImageGenerationTask] = []
    
    def add_task(self, task: ImageGenerationTask) -> None:
        self.tasks.append(task)
    
    async def process_batch(self, generator_func, *args, **kwargs) -> List[ImageGenerationTask]:
        if not self.tasks:
            return []
        logger.info(f"[BatchProcessor] 开始顺序处理 {len(self.tasks)} 个任务")
        completed_tasks = []
        for i, task in enumerate(self.tasks):
            try:
                logger.info(f"[BatchProcessor] 处理任务 {i+1}/{len(self.tasks)}: {task.task_id}")
                result = await generator_func(task, *args, **kwargs)
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
            if i < len(self.tasks) - 1:
                logger.debug(f"[BatchProcessor] 等待 {self.request_delay} 秒...")
                time.sleep(self.request_delay)
        self.tasks.clear()
        return completed_tasks
    
    def close(self) -> None:
        self.tasks.clear()
        logger.debug("[BatchProcessor] 资源已清理") 