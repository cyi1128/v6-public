# -*- coding: utf-8 -*-
"""
A股交易日历工具（真实日历优先 + 本地缓存兜底）
================================================================
所有盘中模块（盘中机会/题材联动/集合竞价/竞价追踪）统一通过本模块
判断交易日，禁止再直接用 datetime.now().date() 当作交易日。

数据源（按优先级）：
  1. 本地涨停原因库 data/limit_up_reason.db 的 date 字段
     —— 每一条都是真实发生过的A股交易日证据
  2. 缓存文件 data/trade_calendar_cache.json（refresh_from_market 写入）
  3. 可选扩展：东方财富上证指数日K（本项目已有 eastmoney_request 通道），
     懒加载刷新，网络失败静默保留本地数据

判断规则：
  - 日期在真实交易日集合内 → 交易日
  - 历史日期（早于集合最新日期）不在集合内 → 非交易日（节假日等）
  - 未来日期（晚于集合最新日期，尚未发生）→ 按工作日近似推断
    （节假日无法预知，属合理近似；日历刷新后自动纠正）
  - 完全无本地数据时兜底按周末判断（并提示）

测试模式：set_test_mode(True, datetime) 供单元测试使用。
"""
import os
import json
import sqlite3
import bisect
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_UP_DB = os.path.join(ROOT, 'data', 'limit_up_reason.db')
CACHE_FILE = os.path.join(ROOT, 'data', 'trade_calendar_cache.json')

# 测试模式
TEST_MODE = False
TEST_DATETIME = None

# 交易日集合缓存（'YYYY-MM-DD' 的 set）与升序列表
_trade_dates = None
_trade_dates_sorted = []
_loaded = False


def set_test_mode(enabled: bool, test_datetime: datetime = None):
    """设置测试模式（供单元测试注入固定时间）"""
    global TEST_MODE, TEST_DATETIME
    TEST_MODE = bool(enabled)
    TEST_DATETIME = test_datetime


def _now() -> datetime:
    if TEST_MODE and TEST_DATETIME:
        return TEST_DATETIME
    return datetime.now()


def _load_trade_dates(force: bool = False) -> set:
    """加载真实交易日集合。不联网。

    优先级：
      1) data/trade_calendar_cache.json（指数日K刷新过的真实交易日，主数据源）
      2) limit_up_reason.db 的 date 字段（涨停证据，仅辅助补充，不作为最新交易日来源）
    关键：cache 存在时即使 limit_up 停更，也不会回退到 limit_up 的旧日期。
    """
    global _trade_dates, _trade_dates_sorted, _loaded
    if _loaded and not force:
        return _trade_dates or set()
    dates = set()

    # 1) 缓存文件（主：指数日K刷新过的真实交易日历）
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if isinstance(cached, list):
                for d in cached:
                    if isinstance(d, str) and len(d) == 10:
                        dates.add(d)
    except Exception as e:
        logger.warning('交易日历缓存读取失败：%s', repr(e))

    # 2) 本地涨停原因库（辅助：补充历史涨停交易日证据）
    try:
        if os.path.exists(LIMIT_UP_DB):
            conn = sqlite3.connect(LIMIT_UP_DB)
            try:
                for (d,) in conn.execute(
                        "SELECT DISTINCT date FROM limit_up_reasons"):
                    d = str(d or '').strip()
                    if len(d) == 8 and d.isdigit():
                        dates.add(f"{d[:4]}-{d[4:6]}-{d[6:]}")
            finally:
                conn.close()
    except Exception:
        pass

    if dates:
        latest = sorted(dates)[-1]
        logger.info('交易日历加载：共 %d 个交易日，最新=%s（缓存主源 + 涨停库辅助）',
                    len(dates), latest)
    else:
        logger.warning('交易日历无任何本地数据，将按周末近似判断')

    _trade_dates = dates or None
    _trade_dates_sorted = sorted(dates) if dates else []
    _loaded = True
    return _trade_dates or set()


def _save_cache():
    """把当前交易日集合写入缓存文件"""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(_trade_dates or []), f, ensure_ascii=False)
    except Exception:
        pass


def _fetch_index_dates_tencent(count: int = 320) -> set:
    """用腾讯指数日K取交易日集合（实测含当天，比 get_kline_http 可靠）。

    背景：get_kline_http('sh000001') 走新浪源时会拿到「个股」数据
    （实测收盘价 11.6，而上证指数在 3900 点附近），且新浪源不含当天。
    腾讯 web.ifzq.gtimg.cn 的指数日K实测 321 根、最后一根就是当天。

    返回 {'YYYY-MM-DD', ...}；失败返回空集合（调用方保留本地缓存）。
    """
    import urllib.request
    out = set()
    for sym in ('sh000001', 'sz399001'):
        try:
            url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
                   '?param=%s,day,,,%d,qfq' % (sym, count))
            req = urllib.request.Request(
                url, headers={'User-Agent': 'Mozilla/5.0'})
            raw = urllib.request.urlopen(req, timeout=15).read().decode('utf-8')
            js = json.loads(raw)
            data = (js.get('data') or {}).get(sym) or {}
            bars = data.get('qfqday') or data.get('day') or []
            for b in bars:
                d = ''
                if isinstance(b, (list, tuple)) and b:
                    d = str(b[0]).strip()
                elif isinstance(b, dict):
                    d = str(b.get('date', '')).strip()
                if len(d) == 10:
                    out.add(d)
            if out:
                break
        except Exception as e:
            logger.warning('交易日历刷新：腾讯指数 %s 取数失败：%s', sym, repr(e))
    return out


def refresh_from_market() -> int:
    """刷新交易日集合（腾讯指数日K为主源，get_kline_http 为兜底）。

    - 主源：腾讯指数日K（含当天）。
    - 兜底：get_kline_http('sh000001')，但会做「像不像指数」的合理性校验，
      因为该函数走新浪源时实测返回的是个股数据（收盘 11.6），会污染日历。
    - 成功：合并新日期并 _save_cache()。
    - 失败/空数据：记录 warning 日志，保留本地已有缓存，绝不回退/清空。
    """
    global _trade_dates, _trade_dates_sorted
    dates = _load_trade_dates()

    new_dates = _fetch_index_dates_tencent(320)
    if new_dates:
        logger.info('交易日历刷新：腾讯指数源取到 %d 个交易日', len(new_dates))
    else:
        # 兜底：原 get_kline_http，带指数合理性校验
        try:
            from utils.http_market_data import get_kline_http
            bars = get_kline_http('sh000001', 320, 'day') or []
            closes = [b.get('close') for b in bars
                      if isinstance(b.get('close'), (int, float))]
            hi = max(closes) if closes else 0
            if bars and 300 <= hi <= 10000:
                for b in bars:
                    d = str(b.get('date', '')).strip()
                    if len(d) == 10:
                        new_dates.add(d)
                logger.info('交易日历刷新：兜底源 get_kline_http 取到 %d 个交易日',
                            len(new_dates))
            elif bars:
                logger.warning(
                    '交易日历刷新：兜底源返回疑似非指数数据（最高收盘 %.2f，'
                    '上证指数应在 300~10000 点），已丢弃', hi)
        except Exception as e:
            logger.warning('交易日历刷新：兜底源失败：%s', repr(e))

    if not new_dates:
        logger.warning(
            '交易日历刷新：全部源返回空，保留本地缓存（最新交易日=%s）',
            _trade_dates_sorted[-1] if _trade_dates_sorted else '未知')
        return 0

    before = len(dates)
    dates |= new_dates
    _trade_dates = dates
    _trade_dates_sorted = sorted(dates)
    _save_cache()
    added = len(dates) - before
    logger.info(
        '交易日历刷新成功：新增 %d 个交易日，最新交易日=%s',
        added, _trade_dates_sorted[-1] if _trade_dates_sorted else '未知')
    return added


# ============ 实时行情日期探测 ============
# 用途：日历缓存（腾讯指数日K）只到上一交易日时，用指数实时行情的时间戳
# 判断"今天到底开没开过盘"。
# 实测：休市日腾讯 qt.gtimg.cn 返回的仍是上一交易日的时间戳
# （如 2026-09-25 中秋当天返回 20260924161401）。
# 这条判断能识别出日历缓存天然覆盖不到的"今天的节假日"。
_live_date_cache = {'ts': 0.0, 'date': None, 'tried': False}
_LIVE_TTL = 300.0          # 秒：缓存有效期
_LIVE_TIMEOUT = 3          # 秒：单次联网超时（时长压短，避免拖住 UI 线程）
_prefetch_started = False


def _fetch_live_index_date(force: bool = False):
    """返回上证指数实时行情时间戳所属日期 'YYYY-MM-DD'；失败返回 None。"""
    import time as _time
    now = _time.time()
    if (not force) and _live_date_cache['tried'] and \
            (now - _live_date_cache['ts']) < _LIVE_TTL:
        return _live_date_cache['date']
    d = None
    try:
        import urllib.request
        req = urllib.request.Request(
            'https://qt.gtimg.cn/q=sh000001',
            headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=_LIVE_TIMEOUT).read()
        txt = raw.decode('gbk', 'ignore')
        f = txt.split('~')
        if len(f) > 30:
            ts = str(f[30]).strip()          # 形如 20260924161401
            if len(ts) >= 8 and ts[:8].isdigit():
                d = '%s-%s-%s' % (ts[:4], ts[4:6], ts[6:8])
    except Exception as e:
        logger.debug('实时行情日期探测失败：%s', repr(e))
    _live_date_cache['ts'] = now
    _live_date_cache['tried'] = True
    _live_date_cache['date'] = d
    return d


def _start_live_prefetch(interval: float = 240.0):
    """后台线程定期刷新实时行情日期，让 is_trading_day 平时零阻塞。"""
    global _prefetch_started
    if _prefetch_started:
        return
    _prefetch_started = True
    try:
        import threading
        import time as _time

        def _loop():
            while True:
                try:
                    _fetch_live_index_date(force=True)
                except Exception:
                    pass
                _time.sleep(interval)

        threading.Thread(target=_loop, daemon=True,
                         name='trade-cal-live-prefetch').start()
        logger.info('交易日历：实时行情日期预取线程已启动（每 %.0f 秒）', interval)
    except Exception as e:
        logger.debug('预取线程启动失败：%s', repr(e))


def get_live_market_date():
    """对外暴露：最近一次指数实时行情所属日期（可能为 None）"""
    return _fetch_live_index_date()


# ============ 节假日表（人工兜底）============
# 动态探测（实时行情时间戳）是主判断；断网时用本表兜底。
# 只登记有明确依据的日期，不预填未核实的内容。
HOLIDAY_FILE = os.path.join(ROOT, 'data', 'market_holidays.json')
_holidays = None


def _load_holidays() -> set:
    """读 data/market_holidays.json（{'holidays': ['YYYY-MM-DD', ...]}）"""
    global _holidays
    if _holidays is not None:
        return _holidays
    out = set()
    try:
        if os.path.exists(HOLIDAY_FILE):
            with open(HOLIDAY_FILE, 'r', encoding='utf-8') as f:
                js = json.load(f)
            arr = js.get('holidays') if isinstance(js, dict) else js
            for d in (arr or []):
                d = str(d).strip()
                if len(d) == 10:
                    out.add(d)
    except Exception as e:
        logger.warning('节假日表读取失败：%s', repr(e))
    _holidays = out
    if out:
        logger.info('节假日表加载：%d 条', len(out))
    return _holidays


def is_known_holiday(d) -> bool:
    """是否为已登记的休市日"""
    if isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return False
    return d.isoformat() in _load_holidays()


def is_trading_day(d=None) -> bool:
    """判断某天是否为A股交易日。
    d: date/datetime 或 'YYYY-MM-DD'；缺省用当前时间。"""
    if d is None:
        d = _now().date()
    elif isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return False
    ds = d.isoformat()
    dates = _load_trade_dates()
    if ds in dates:
        return True
    if not dates:
        # 完全无本地数据：兜底周末判断
        return d.weekday() < 5
    # 历史日期不在集合 → 非交易日；未来日期 → 按工作日近似
    if ds < _trade_dates_sorted[-1]:
        return False

    # [FIX 2026-09-25] 该日期晚于日历缓存最新日期。
    # 日历缓存来自指数日K，天然只到"已收盘的上一交易日"，
    # 所以"今天"必然会落到这里。不能简单按工作日判断 ——
    # 否则节假日（如 2026-09-25 中秋）会被误判为交易日，
    # 导致竞价模块在休市日继续拉数据。
    # 依次尝试：① 实时行情时间戳（最准）② 节假日表（断网兜底）③ 工作日近似
    # ① 节假日表最优先：任何时刻都准，包括开盘前（此时行情时间戳
    #    本来就还停在上一交易日，无法用行情判断今天是否休市）。
    if is_known_holiday(d):
        logger.info('交易日判断：%s 命中节假日表 → 判定休市', ds)
        return False

    # ② 实时行情时间戳：硬证据 —— 行情从未走到这一天，说明这天没开过盘。
    _start_live_prefetch()
    live = _fetch_live_index_date()
    if live:
        today_s = _now().date().isoformat()
        if ds == live:
            return True
        if ds < live:
            # 早于行情最新日期却不在日历集合里 → 视为交易日（日历尚未刷新）
            return True
        # ds > live：查询日期晚于行情最新日期
        if ds <= today_s:
            now = _now()
            hm = now.hour * 100 + now.minute
            if ds == today_s and hm < 930:
                # 今天还没到 9:30，行情自然还是上一交易日的 ——
                # 此时不能用行情判"今天休市"，只能按工作日近似。
                return d.weekday() < 5
            logger.info(
                '交易日判断：%s 晚于实时行情日期 %s 且行情未走到该日 → 判定休市',
                ds, live)
            return False

    # ③ 真未来日期 / 行情不可用：按工作日近似
    return d.weekday() < 5


def get_latest_trading_date(d=None) -> str:
    """返回 <= d 的最近一个真实交易日（'YYYY-MM-DD'）。
    无本地数据时兜底往回找最近工作日。"""
    if d is None:
        d = _now().date()
    elif isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            d = _now().date()
    ds = d.isoformat()
    dates = _load_trade_dates()
    if not dates:
        x = d
        for _ in range(14):
            if x.weekday() < 5:
                return x.isoformat()
            x -= timedelta(days=1)
        return d.isoformat()
    i = bisect.bisect_right(_trade_dates_sorted, ds)
    if i > 0:
        return _trade_dates_sorted[i - 1]
    return _trade_dates_sorted[0]


def is_market_open(now=None) -> bool:
    """当前是否处于市场开放时段（交易日 9:15~15:05，含集合竞价）。
    休市（午休 11:30~13:00 不算盘中机会扫描时段？）：
    盘中机会按 9:15~15:05 统一口径，午休也保留数据不失效。"""
    n = now or _now()
    if not is_trading_day(n.date()):
        return False
    hm = n.hour * 100 + n.minute
    return 915 <= hm <= 1505


def is_auction_period(now=None) -> bool:
    """当前是否处于集合竞价时段（交易日 9:15~9:30）。"""
    n = now or _now()
    if not is_trading_day(n.date()):
        return False
    hm = n.hour * 100 + n.minute
    return 915 <= hm < 930


def market_status_info(now=None) -> dict:
    """市场状态信息：{status, data_date, mode}
    status: 交易中/休市
    data_date: 数据所属交易日（休市时为最近交易日）
    mode: 实时/复盘"""
    n = now or _now()
    today = n.strftime('%Y-%m-%d')
    if is_market_open(n):
        return {'status': '交易中', 'data_date': today, 'mode': '实时'}
    draft = {
        'status': '休市',
        'data_date': get_latest_trading_date(n),
        'mode': '复盘',
    }
    # 诊断用：实时行情所属日期（None 表示探测失败）
    draft['live_market_date'] = _fetch_live_index_date()
    return draft


# ============ 模块导入即后台预热 ============
# _fetch_live_index_date 首次调用会同步联网（3 秒超时）。若第 0.15 秒就被
# 竞价模块的 QTimer 触发 refresh 调用 is_trading_day，会在 UI 线程上白等。
# 这里在导入时就启后台线程先取一次，主线程随后读到的多半已是缓存值。
try:
    _start_live_prefetch(interval=240.0)
except Exception:
    pass
