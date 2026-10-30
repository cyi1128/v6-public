# -*- coding: utf-8 -*-
"""
K线缓存 DuckDB 全局读写锁
=============================
背景（崩溃根因）：
    Windows fatal exception: access violation (0xC0000005 / -1073741819)
    发生在 utils/kline_provider.py 第37行 duckdb.connect(..., read_only=True)。

    现象：主窗口创建后，后台 K线增量更新线程（写 kline_cache.duckdb）与
    WatchlistPanel / ATR做T / 竞价筛选 等多个后台 ThreadPool worker
    同时对同一个 kline_cache.duckdb 执行 duckdb.connect(read_only=True)。
    DuckDB 在 Windows 上当"写连接 + 多个 read_only 连接"并发打开同一文件时，
    C++ 层在 connect/execute/close 阶段会触发访问违例，Python try/except 无法捕获。

修复策略：
    1) 全进程所有对 data/cache/kline_cache.duckdb 的 connect/execute/close 必须
       在同一把 RLock 内串行化；读-读、读-写、写-写全部互斥。
    2) 每个线程仍使用"短连接"（connect→execute→close），但用锁把它们排开。
    3) 本模块只导出一把共享锁，所有读写方 import 后 with 使用。
"""
import threading

# 可重入锁：允许同一线程嵌套获取（例如写函数内部再调用读函数）
_kline_cache_lock = threading.RLock()


def get_kline_cache_lock():
    """返回保护 kline_cache.duckdb 的全局可重入锁。

    用法：
        from utils.kline_db_lock import get_kline_cache_lock
        with get_kline_cache_lock():
            con = duckdb.connect(db_path, read_only=True)
            ...
            con.close()
    """
    return _kline_cache_lock
