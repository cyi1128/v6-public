# -*- coding: utf-8 -*-
"""
实时新闻中心 - 定时刷新引擎
核心功能：
  - 进入新闻页后自动定时拉取（默认3分钟，可配置）
  - 增量更新逻辑：仅拉取最新新闻，追加到列表顶部，不清空历史
  - 智能启停：切换到其他标签页降低频率至10分钟，切回立即触发增量刷新
  - 所有拉取/解析在独立后台线程执行，不阻塞UI主线程
  - 状态回调：刷新开始/完成/失败、最后更新时间、新增数量
"""

import sys
import os
import time
import traceback
from datetime import datetime
from typing import List, Dict, Callable, Optional
from threading import Thread, Lock, Event

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_center.news_config import REFRESH_CONFIG, PERFORMANCE_CONFIG
from news_center.news_sources import get_multi_source_manager
from news_center.news_dedup import get_deduplicator
from services.news_matcher import get_news_matcher


# ============================================================
# 刷新结果数据类
# ============================================================
class RefreshResult:
    """单次刷新结果"""
    def __init__(self):
        self.success = False
        self.new_count = 0           # 新增新闻条数
        self.total_count = 0         # 刷新后总条数
        self.elapsed_sec = 0.0       # 耗时
        self.error = ''              # 错误信息
        self.timestamp = ''          # 刷新完成时间
        self.source_status = {}      # 各数据源状态


# ============================================================
# 后台刷新Worker（独立线程）
# ============================================================
class RefreshWorker(Thread):
    """
    后台刷新Worker：在独立线程中执行多源拉取+去重
    通过回调函数将结果传回主线程
    """

    def __init__(self, limit: int = 80, existing_news: List[Dict] = None,
                 on_result: Callable = None, on_error: Callable = None):
        super().__init__(daemon=True)
        self.limit = limit
        self.existing_news = existing_news or []
        self.on_result = on_result
        self.on_error = on_error
        self._cancelled = Event()

    def cancel(self):
        self._cancelled.set()

    def run(self):
        result = RefreshResult()
        start_time = time.time()
        try:
            if self._cancelled.is_set():
                return

            # 1. 多源并行拉取
            manager = get_multi_source_manager()
            raw_news = manager.fetch_all(limit=self.limit)

            if self._cancelled.is_set():
                return

            # 2. 智能去重
            dedup = get_deduplicator()
            unique_news = dedup.deduplicate(raw_news, existing_news=self.existing_news)

            # 3. 标记新增
            for n in unique_news:
                n['is_new'] = True

            result.success = True
            result.new_count = len(unique_news)
            result.source_status = manager.get_source_status()

            # 4. 回调（在主线程中通过信号/队列处理）
            result.elapsed_sec = time.time() - start_time
            result.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            result.total_count = len(self.existing_news) + len(unique_news)

            if self.on_result and not self._cancelled.is_set():
                self.on_result(unique_news, result)

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.elapsed_sec = time.time() - start_time
            result.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[刷新引擎] 后台刷新异常: {e}", flush=True)
            traceback.print_exc()
            if self.on_error and not self._cancelled.is_set():
                self.on_error(str(e), result)


# ============================================================
# 定时刷新引擎
# ============================================================
class NewsRefreshEngine:
    """
    定时刷新引擎
    - 管理刷新间隔（激活态/后台态）
    - 管理后台Worker生命周期
    - 提供手动触发、暂停、恢复接口
    - 线程安全
    """

    def __init__(self):
        self._active_interval = REFRESH_CONFIG.get('active_interval', 180)
        self._background_interval = REFRESH_CONFIG.get('background_interval', 600)
        self._current_interval = self._active_interval
        self._is_active = True          # 是否在新闻页（激活态）
        self._is_running = False        # 引擎是否运行
        self._is_refreshing = False     # 是否正在刷新
        self._last_refresh_time = ''    # 最后更新时间
        self._worker: Optional[RefreshWorker] = None
        self._lock = Lock()
        self._timer_thread: Optional[Thread] = None
        self._stop_event = Event()

        # 回调（由UI层设置）
        self.on_refresh_start: Optional[Callable] = None       # 刷新开始
        self.on_refresh_success: Optional[Callable] = None     # 刷新成功 (new_news, result)
        self.on_refresh_error: Optional[Callable] = None       # 刷新失败 (error, result)
        self.on_status_change: Optional[Callable] = None       # 状态变化

        # 当前已有的新闻列表引用（由UI层更新）
        self._existing_news: List[Dict] = []

    def set_existing_news(self, news_list: List[Dict]):
        """更新当前已有新闻列表（用于去重比对）"""
        with self._lock:
            self._existing_news = list(news_list)

    def get_existing_news(self) -> List[Dict]:
        with self._lock:
            return list(self._existing_news)

    @property
    def last_refresh_time(self) -> str:
        return self._last_refresh_time

    @property
    def is_refreshing(self) -> bool:
        return self._is_refreshing

    @property
    def is_active(self) -> bool:
        return self._is_active

    def start(self):
        """启动刷新引擎（进入新闻页时调用）"""
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        self._is_active = True
        self._current_interval = self._active_interval
        print(f"[刷新引擎] 已禁用自动刷新（避免Python 3.14多线程崩溃）", flush=True)
        return

        # 启动定时线程（已禁用）
        self._timer_thread = Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

        # 延迟首次刷新（已禁用）
        initial_delay = REFRESH_CONFIG.get('initial_delay', 2)
        Thread(target=self._delayed_first_refresh, args=(initial_delay,), daemon=True).start()

    def stop(self):
        """停止刷新引擎（程序退出时调用）"""
        self._is_running = False
        self._stop_event.set()
        if self._worker:
            self._worker.cancel()
        print("[刷新引擎] 已停止", flush=True)

    def set_active(self, active: bool):
        """
        设置激活状态（Tab切换时调用）
        active=True: 新闻页可见，使用高频刷新
        active=False: 切换到其他标签页，降低刷新频率
        """
        was_active = self._is_active
        self._is_active = active
        if active:
            self._current_interval = self._active_interval
            print(f"[刷新引擎] 切回新闻页，立即触发增量刷新，间隔恢复{self._current_interval}秒", flush=True)
            # 切回时立即触发一次全量增量刷新
            self.trigger_refresh(immediate=True)
        else:
            self._current_interval = self._background_interval
            print(f"[刷新引擎] 切换到其他标签页，降低刷新频率至{self._current_interval}秒", flush=True)

        if self.on_status_change:
            self.on_status_change({'active': active, 'interval': self._current_interval})

    def trigger_refresh(self, immediate: bool = False, limit: int = None):
        """
        手动触发一次刷新
        immediate: 是否立即执行（跳过冷却判断）
        """
        if self._is_refreshing and not immediate:
            print("[刷新引擎] 正在刷新中，跳过本次触发", flush=True)
            return

        if not immediate and self._last_refresh_time:
            # 防止过于频繁的手动刷新（最小间隔10秒）
            try:
                last = datetime.strptime(self._last_refresh_time, '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - last).total_seconds() < 10:
                    return
            except Exception:
                pass

        self._do_refresh(limit=limit)

    def _do_refresh(self, limit: int = None):
        """执行一次刷新（创建后台Worker）"""
        if self._is_refreshing:
            return
        self._is_refreshing = True

        if self.on_refresh_start:
            try:
                self.on_refresh_start()
            except Exception:
                pass

        fetch_limit = limit or REFRESH_CONFIG.get('incremental_limit', 80)
        existing = self.get_existing_news()

        self._worker = RefreshWorker(
            limit=fetch_limit,
            existing_news=existing,
            on_result=self._handle_refresh_result,
            on_error=self._handle_refresh_error,
        )
        self._worker.start()

    def _handle_refresh_result(self, new_news: List[Dict], result: RefreshResult):
        """刷新成功回调（在Worker线程中调用，需线程安全）"""
        self._is_refreshing = False
        self._last_refresh_time = result.timestamp

        # 标记为已展示
        try:
            dedup = get_deduplicator()
            dedup.mark_as_displayed(new_news)
        except Exception as e:
            print(f"[刷新引擎] 标记已展示失败: {e}", flush=True)

        # V2.9 新增：新闻利好关键词匹配推送（纯本地文本匹配，性能开销小）
        if new_news:
            try:
                matcher = get_news_matcher()
                match_count = 0
                push_count = 0
                for news_item in new_news:
                    try:
                        matches = matcher.match_news(news_item)
                        if matches:
                            match_count += 1
                            push_count += sum(1 for m in matches if m.get('pushed'))
                    except Exception as _e:
                        print(f"[刷新引擎] 单条新闻匹配异常: {_e}", flush=True)
                if match_count > 0:
                    print(f"[刷新引擎] 新闻匹配完成: {len(new_news)}条新新闻, {match_count}条命中关键词, {push_count}条已推送", flush=True)
            except Exception as e:
                print(f"[刷新引擎] 新闻匹配推送异常(已忽略): {e}", flush=True)

        # V2.10 新增：利好股票新闻 → AI解读 → 企业微信推送（异步，每轮最多3条）
        if new_news:
            try:
                from services.news_ai_push import push_async
                for item in list(new_news)[:3]:
                    push_async(item)
            except Exception as _e:
                print(f"[刷新引擎] AI解读推送触发异常(已忽略): {_e}", flush=True)

        if self.on_refresh_success:
            try:
                self.on_refresh_success(new_news, result)
            except Exception as e:
                print(f"[刷新引擎] 成功回调异常: {e}", flush=True)

    def _handle_refresh_error(self, error: str, result: RefreshResult):
        """刷新失败回调"""
        self._is_refreshing = False
        self._last_refresh_time = result.timestamp
        if self.on_refresh_error:
            try:
                self.on_refresh_error(error, result)
            except Exception as e:
                print(f"[刷新引擎] 失败回调异常: {e}", flush=True)

    def _delayed_first_refresh(self, delay: float):
        """延迟首次刷新"""
        time.sleep(delay)
        if self._is_running and not self._stop_event.is_set():
            self._do_refresh(limit=REFRESH_CONFIG.get('full_load_limit', 200))

    def _timer_loop(self):
        """定时循环线程"""
        while self._is_running and not self._stop_event.is_set():
            # 使用可中断的等待
            interval = self._current_interval
            self._stop_event.wait(timeout=interval)
            if self._stop_event.is_set() or not self._is_running:
                break
            if not self._is_refreshing:
                self._do_refresh()

    def update_intervals(self, active_sec: int = None, background_sec: int = None):
        """运行时更新刷新间隔"""
        if active_sec:
            self._active_interval = active_sec
            if self._is_active:
                self._current_interval = active_sec
        if background_sec:
            self._background_interval = background_sec
            if not self._is_active:
                self._current_interval = background_sec


# ============================================================
# 单例
# ============================================================
_engine_instance = None

def get_refresh_engine() -> NewsRefreshEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = NewsRefreshEngine()
    return _engine_instance
