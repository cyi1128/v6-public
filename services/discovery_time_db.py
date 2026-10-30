# -*- coding: utf-8 -*-
"""
发现时间持久化服务（DuckDB）
============================
解决"程序重启后所有股票发现时间变成打开程序时间"的问题。

背景：
    ui/battle_widgets 各模块用内存字典 _found_time 记录某只股票/板块
    当天第一次被发现的时间。程序重启后内存清空，下一次扫描时所有
    已在池子里的股票都被当成"新发现"，用 datetime.now() 记录，
    导致时间错乱。

方案：
    把 (trade_date, module, code_or_name) -> found_time 持久化到
    data/cache/discovery_time.duckdb。程序启动时把今天的记录加载
    进内存，重启后即可还原真实发现时间；新发现的才写当前时间。

线程模型：
    DuckDB 连接不跨线程共享。这里每个函数调用都新建独立连接、用完
    关闭，可安全地在主线程 / worker 后台线程中调用。
    写操作使用 INSERT OR IGNORE（主键冲突不覆盖），保证老记录不被
    刷新时的当前时间覆盖。

表结构：
    discovery_records(
        trade_date   VARCHAR,   -- 'YYYY-MM-DD'
        module       VARCHAR,   -- auction/limit_up/opportunity/sector_spike/leader_ladder
        code_or_name VARCHAR,   -- 股票代码 或 板块名
        found_time   VARCHAR,   -- 'HH:MM'
        PRIMARY KEY (trade_date, module, code_or_name)
    )
"""
import os
from datetime import date

# 项目根目录（services/ 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'cache', 'discovery_time.duckdb')

# 模块名常量（与各 widget 中调用处保持一致）
MOD_AUCTION = 'auction'
MOD_LIMIT_UP = 'limit_up'
MOD_OPPORTUNITY = 'opportunity'
MOD_SECTOR_SPIKE = 'sector_spike'
MOD_LEADER_LADDER = 'leader_ladder'


def _trade_day():
    """发现时间归属交易日：今天是交易日→今天；休市/周末→最近交易日。
    休市期间模块显示的是最近交易日数据，发现时间必须归属该交易日，
    不能把自然日（周六/周日）当成交易日写入。"""
    try:
        from utils import trade_calendar as tc
        now = __import__('datetime').datetime.now()
        today = now.strftime('%Y-%m-%d')
        if tc.is_trading_day(today):
            return today
        return tc.get_latest_trading_date(now)
    except Exception:
        return _trade_day()


def _connect():
    """新建一个读写连接（需要写权限，不能 read_only=True）。"""
    import duckdb
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return duckdb.connect(DB_PATH, read_only=False)


def ensure_table():
    """建表（幂等）。启动时调用一次即可。"""
    con = _connect()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS discovery_records (
                trade_date   VARCHAR NOT NULL,
                module       VARCHAR NOT NULL,
                code_or_name VARCHAR NOT NULL,
                found_time   VARCHAR NOT NULL,
                PRIMARY KEY (trade_date, module, code_or_name)
            )
            """
        )
        con.commit()
    finally:
        con.close()


def load_today(module, today=None):
    """读取今天某模块的全部发现时间，返回 {code_or_name: 'HH:MM'}。

    跨天自动忽略历史记录：只取 trade_date == today 的行。
    """
    if today is None:
        today = _trade_day()
    out = {}
    try:
        con = _connect()
        try:
            rows = con.execute(
                "SELECT code_or_name, found_time FROM discovery_records "
                "WHERE trade_date = ? AND module = ?",
                [today, module],
            ).fetchall()
            for k, t in rows:
                out[str(k)] = str(t)
        finally:
            con.close()
    except Exception as e:
        print(f'[discovery_time] load_today({module}) 失败: {e}', flush=True)
    return out


def get_today(module, code_or_name, today=None):
    """查今天某模块某 key 是否已记录过发现时间。有则返回 'HH:MM'，否则 None。"""
    if today is None:
        today = _trade_day()
    try:
        con = _connect()
        try:
            row = con.execute(
                "SELECT found_time FROM discovery_records "
                "WHERE trade_date = ? AND module = ? AND code_or_name = ?",
                [today, module, str(code_or_name)],
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except Exception as e:
        print(f'[discovery_time] get_today({module},{code_or_name}) 失败: {e}', flush=True)
        return None


def save_today(module, code_or_name, found_time, today=None):
    """记录一条今天的发现时间。主键冲突时不覆盖老时间（INSERT OR IGNORE）。"""
    if today is None:
        today = _trade_day()
    if not code_or_name or not found_time:
        return
    try:
        con = _connect()
        try:
            con.execute(
                "INSERT OR IGNORE INTO discovery_records "
                "(trade_date, module, code_or_name, found_time) VALUES (?,?,?,?)",
                [today, module, str(code_or_name), str(found_time)],
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:
        print(f'[discovery_time] save_today({module},{code_or_name}) 失败: {e}', flush=True)


def save_many(module, mapping, today=None):
    """批量记录今天的发现时间。mapping: {code_or_name: 'HH:MM'}。同样 OR IGNORE。"""
    if today is None:
        today = _trade_day()
    if not mapping:
        return
    try:
        con = _connect()
        try:
            rows = [(today, module, str(k), str(v)) for k, v in mapping.items() if k and v]
            con.executemany(
                "INSERT OR IGNORE INTO discovery_records "
                "(trade_date, module, code_or_name, found_time) VALUES (?,?,?,?)",
                rows,
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:
        print(f'[discovery_time] save_many({module}) 失败: {e}', flush=True)


def cleanup_old(today=None, keep_days=3):
    """清理 N 天前的历史记录，避免表无限膨胀。今天/近 N 天保留。"""
    if today is None:
        today = date.today()
    else:
        from datetime import datetime as _dt
        today = _dt.strptime(today, '%Y-%m-%d').date()
    try:
        con = _connect()
        try:
            from datetime import timedelta
            cutoff = (today - timedelta(days=keep_days)).isoformat()
            con.execute("DELETE FROM discovery_records WHERE trade_date < ?", [cutoff])
            con.commit()
        finally:
            con.close()
    except Exception as e:
        print(f'[discovery_time] cleanup_old 失败: {e}', flush=True)


# 模块导入时即建表（幂等），确保后续读写可用
try:
    ensure_table()
    cleanup_old(keep_days=3)
except Exception as e:
    print(f'[discovery_time] 初始化失败: {e}', flush=True)
