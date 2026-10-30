# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.2 - 并行扫描器

使用 concurrent.futures.ThreadPoolExecutor 实现多线程并行扫描：
- workers=8（可配置）
- 线程安全的结果收集
- 轻量节流（请求间隔0.05秒）
- 支持三层扫描流程
"""
import time
import threading
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field


@dataclass
class ScanProgress:
    """扫描进度信息"""
    stage: str = ""              # 当前阶段：基础筛选/行为预筛/深度分析
    total: int = 0               # 总数
    processed: int = 0           # 已处理
    candidates: int = 0          # 候选数量
    elapsed: float = 0.0         # 耗时（秒）
    current_code: str = ""       # 当前处理的股票


class ParallelScanner:
    """并行扫描器 - V1.2"""

    def __init__(self, max_workers: int = 8, throttle: float = 0.02):
        """
        Args:
            max_workers: 最大线程数，默认8
            throttle: 每个请求的最小间隔（秒），默认0.02秒轻量节流
        """
        self.max_workers = max_workers
        self.throttle = throttle
        self._lock = threading.Lock()
        self._results = []
        self._progress = ScanProgress()
        self._stop_flag = False
        self._last_request_time = 0.0
        self._request_lock = threading.Lock()

    def _throttle_request(self):
        """轻量节流：确保请求间隔不小于throttle秒"""
        with self._request_lock:
            now = time.time()
            wait = self.throttle - (now - self._last_request_time)
            if wait > 0:
                time.sleep(wait)
            self._last_request_time = time.time()

    def scan_parallel(self, items: List, worker_func: Callable,
                       stage: str = "扫描",
                       progress_callback: Optional[Callable] = None,
                       batch_size: int = 100,
                       throttle: Optional[float] = None) -> List:
        """
        并行扫描

        Args:
            items: 待扫描项目列表
            worker_func: 工作函数，接收单个item，返回结果或None
            stage: 阶段名称
            progress_callback: 进度回调函数(progress: ScanProgress)
            batch_size: 批处理大小
            throttle: 节流时间（秒），None使用默认值，0表示不节流（内存计算场景）

        Returns:
            扫描结果列表（过滤None）
        """
        # V1.3.3：支持调用方覆盖节流设置（内存计算场景设为0）
        old_throttle = self.throttle
        if throttle is not None:
            self.throttle = throttle
        self._results = []
        self._progress = ScanProgress(stage=stage, total=len(items))
        self._stop_flag = False
        start_time = time.time()

        total = len(items)
        if total == 0:
            return []

        # 分批处理，避免一次性提交太多任务
        all_results = []
        for batch_start in range(0, total, batch_size):
            if self._stop_flag:
                break
            batch = items[batch_start:batch_start + batch_size]

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_item = {}
                for item in batch:
                    future = executor.submit(self._safe_worker, worker_func, item)
                    future_to_item[future] = item

                for future in as_completed(future_to_item):
                    if self._stop_flag:
                        break
                    try:
                        result = future.result()
                        if result is not None:
                            all_results.append(result)
                    except Exception:
                        pass

                    # 更新进度
                    with self._lock:
                        self._progress.processed += 1
                        self._progress.candidates = len(all_results)
                        self._progress.elapsed = time.time() - start_time
                        item = future_to_item.get(future)
                        if item and isinstance(item, dict):
                            self._progress.current_code = item.get('code', item.get('ts_code', ''))

                    if progress_callback and (self._progress.processed % 10 == 0 or
                                               self._progress.processed == total):
                        progress_callback(self._progress)

        self._progress.elapsed = time.time() - start_time
        if progress_callback:
            progress_callback(self._progress)

        # V1.3.3：恢复原节流设置
        self.throttle = old_throttle

        return all_results

    def _safe_worker(self, worker_func: Callable, item):
        """安全工作函数：捕获异常，节流请求，V1.2.1增加异常打印"""
        try:
            self._throttle_request()
            return worker_func(item)
        except Exception as e:
            # V1.2.1：不再静默吞掉异常，打印到控制台
            code = ''
            if isinstance(item, dict):
                code = item.get('code', item.get('ts_code', ''))
            print(f"[PARALLEL ERROR] 股票{code}处理异常: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return None

    def stop(self):
        """停止扫描"""
        self._stop_flag = True

    def get_progress(self) -> ScanProgress:
        """获取当前进度"""
        with self._lock:
            return self._progress

    def get_results(self) -> List:
        """获取结果"""
        with self._lock:
            return list(self._results)


# ============================================================
# 便捷函数
# ============================================================

def create_scanner(max_workers: int = 8, throttle: float = 0.02) -> ParallelScanner:
    """创建并行扫描器"""
    return ParallelScanner(max_workers=max_workers, throttle=throttle)
