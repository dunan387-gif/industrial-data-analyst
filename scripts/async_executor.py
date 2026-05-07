#!/usr/bin/env python3
"""
异步任务执行模块
支持耗时分析任务的异步处理和进度反馈
"""

import os
import json
import uuid
import time
import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future


class AsyncAnalyzer:
    """异步分析任务执行器"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
    def submit_task(self, task_type: str, 
                    task_func: Callable,
                    task_params: Dict[str, Any],
                    callback: Optional[Callable] = None) -> str:
        """
        提交异步任务
        
        Args:
            task_type: 任务类型
            task_func: 任务函数
            task_params: 任务参数
            callback: 完成回调函数
            
        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())[:8]
        
        task_info = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None
        }
        
        with self._lock:
            self.tasks[task_id] = task_info
        
        def wrapped_task():
            with self._lock:
                self.tasks[task_id]["status"] = "running"
                self.tasks[task_id]["started_at"] = datetime.now().isoformat()
            
            try:
                result = task_func(**task_params)
                
                with self._lock:
                    self.tasks[task_id]["status"] = "completed"
                    self.tasks[task_id]["progress"] = 100
                    self.tasks[task_id]["completed_at"] = datetime.now().isoformat()
                    self.tasks[task_id]["result"] = result
                
                if callback:
                    callback(task_id, result)
                    
            except Exception as e:
                with self._lock:
                    self.tasks[task_id]["status"] = "failed"
                    self.tasks[task_id]["error"] = str(e)
                    self.tasks[task_id]["completed_at"] = datetime.now().isoformat()
        
        self.executor.submit(wrapped_task)
        print(f"任务已提交: {task_id} ({task_type})")
        return task_id
    
    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """更新任务进度"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id]["progress"] = min(progress, 100)
                if message:
                    self.tasks[task_id]["message"] = message
    
    def get_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        with self._lock:
            if task_id not in self.tasks:
                return {"error": f"任务 {task_id} 不存在"}
            
            task = self.tasks[task_id].copy()
            
            # 计算预计剩余时间
            if task["status"] == "running" and task["progress"] > 0:
                started = datetime.fromisoformat(task["started_at"])
                elapsed = (datetime.now() - started).total_seconds()
                eta = elapsed / task["progress"] * (100 - task["progress"])
                task["eta_seconds"] = round(eta, 1)
            
            return task
    
    def get_result(self, task_id: str, wait: bool = False, 
                   timeout: float = 300) -> Dict[str, Any]:
        """
        获取任务结果
        
        Args:
            task_id: 任务ID
            wait: 是否等待任务完成
            timeout: 等待超时时间（秒）
        """
        if wait:
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = self.get_status(task_id)
                if status.get("status") in ["completed", "failed"]:
                    return status
                time.sleep(0.5)
            return {"error": "等待超时"}
        
        return self.get_status(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务（仅对未开始的任务有效）"""
        with self._lock:
            if task_id in self.tasks and self.tasks[task_id]["status"] == "pending":
                self.tasks[task_id]["status"] = "cancelled"
                return True
        return False
    
    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有任务"""
        with self._lock:
            tasks = list(self.tasks.values())
            if status:
                tasks = [t for t in tasks if t["status"] == status]
            return tasks
    
    def cleanup_completed(self, max_age_hours: int = 24):
        """清理已完成的旧任务"""
        cutoff = datetime.now().timestamp() - max_age_hours * 3600
        
        with self._lock:
            to_remove = []
            for task_id, task in self.tasks.items():
                if task["status"] in ["completed", "failed", "cancelled"]:
                    completed_at = task.get("completed_at")
                    if completed_at:
                        task_time = datetime.fromisoformat(completed_at).timestamp()
                        if task_time < cutoff:
                            to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            return len(to_remove)
    
    def shutdown(self, wait: bool = True):
        """关闭执行器"""
        self.executor.shutdown(wait=wait)


# 全局实例
_global_analyzer = None

def get_analyzer() -> AsyncAnalyzer:
    """获取全局异步分析器实例"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = AsyncAnalyzer()
    return _global_analyzer


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="异步任务管理")
    parser.add_argument("--list", action="store_true", help="列出所有任务")
    parser.add_argument("--status", help="查询任务状态")
    parser.add_argument("--demo", action="store_true", help="运行演示任务")
    
    args = parser.parse_args()
    
    analyzer = get_analyzer()
    
    if args.demo:
        def demo_task(duration: int = 5):
            for i in range(duration):
                time.sleep(1)
            return {"message": "演示任务完成", "duration": duration}
        
        task_id = analyzer.submit_task(
            task_type="demo",
            task_func=demo_task,
            task_params={"duration": 3}
        )
        
        print(f"演示任务已提交: {task_id}")
        result = analyzer.get_result(task_id, wait=True, timeout=10)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif args.status:
        status = analyzer.get_status(args.status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
    
    elif args.list:
        tasks = analyzer.list_tasks()
        print(json.dumps(tasks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
