# -*- coding: utf-8 -*-
"""
交易日盘中快照持久化（intraday_snapshot.py）
================================================================
每个交易日保存一个完整快照：data/intraday_snapshots/{交易日}.json

用途（用户 V2.2 复盘需求）：
- 盘中每轮扫描完成后持续保存当天状态（引擎 + 竞价筛选结果）
- 程序关闭 / 电脑重启后，休市或下次启动时恢复最近交易日完整数据
- 休市复盘模式：四个模块（集合竞价 / 盘中机会 / 金铲子 / 题材联动）
  统一从同一个快照文件恢复，避免重新初始化为 0

快照 JSON 结构：
{
  "trading_date": "2026-09-18",
  "saved_at": "2026-09-18 14:59:10",
  "engine": {   # 盘中机会引擎状态（events/clusters/opportunities/stats/...）
    ...
  },
  "auction": {  # 集合竞价筛选结果（当日真实筛选表格数据）
    "rows": [ {code,name,price,score,...}, ... ],
    "saved_at": "..."
  }
}

写入方式：section 级读-改-写 + 进程内锁 + 临时文件原子替换，
避免引擎(每25s)与竞价(9:25-9:30)并发写互相覆盖。
"""
import json
import os
import threading
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(ROOT, 'data', 'intraday_snapshots')

_lock = threading.Lock()
_loaded_cache = {}  # {path: dict} 进程内读缓存（读多写少）


def ensure_dir():
    try:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    except Exception:
        pass


def snapshot_path(trading_date):
    """交易日 -> 快照文件绝对路径"""
    return os.path.join(SNAPSHOT_DIR, '%s.json' % trading_date)


def _read(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return None


def load_section(trading_date, section):
    """读取某交易日快照的某个 section（engine / auction）。无则 None。"""
    if not trading_date:
        return None
    path = snapshot_path(trading_date)
    doc = _read(path)
    if not isinstance(doc, dict):
        return None
    return doc.get(section)


def save_section(trading_date, section, data):
    """写入某交易日快照的某个 section（读-改-写 + 原子替换）。
    返回 True/False。数据必须 JSON 可序列化。"""
    if not trading_date:
        return False
    ensure_dir()
    path = snapshot_path(trading_date)
    with _lock:
        try:
            doc = _read(path) or {}
            if not isinstance(doc, dict):
                doc = {}
            doc[section] = data
            doc['trading_date'] = trading_date
            doc['saved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, default=str)
            os.replace(tmp, path)
            return True
        except Exception:
            try:
                if os.path.exists(path + '.tmp'):
                    os.remove(path + '.tmp')
            except Exception:
                pass
            return False


def list_snapshot_dates():
    """返回已有快照的交易日列表（升序）。"""
    ensure_dir()
    try:
        dates = []
        for fn in os.listdir(SNAPSHOT_DIR):
            if fn.endswith('.json'):
                dates.append(fn[:-5])
        return sorted(dates)
    except Exception:
        return []


def latest_snapshot_date(now=None):
    """最近一个"已存在"的交易日快照日期；无则 None。"""
    dates = list_snapshot_dates()
    if not dates:
        return None
    now = now or datetime.now()
    today = now.strftime('%Y-%m-%d')
    # 今天有快照优先（盘中/盘后当天）
    if today in dates:
        return today
    # 否则取早于今天的最近快照
    past = [d for d in dates if d < today]
    return past[-1] if past else dates[-1]
