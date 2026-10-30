# -*- coding: utf-8 -*-
"""板块异动「可介入」标的跟踪服务

用途
----
板块异动表里的「可介入」列是当天筛出来的候选票。这些票到底准不准，
需要事后跟踪：入选后 5 个交易日、30 个交易日、以及到目前为止的累计盈亏。

数据流
------
  板块异动引擎当日 picks（未涨停 / 涨幅1~9% / 量比≥1.2 / 价≥6元 / 非ST / ≥MA20）
        ↓  幂等写入（同一 trade_date+code 只记一次，P0 锁定不覆盖）
  data/cache/picks_tracking.duckdb  表 picks_tracking
        ↓  只读 kline_cache.duckdb 取 T+N 收盘价
  5日盈亏% / 30日盈亏% / 累计盈亏% + 胜率统计

P0（入选价）口径
----------------
统一取「入选当日收盘价」。
  · 盘后记录：实时行情价已等于收盘价，直接使用
  · 回填历史：读 kline_cache 当日收盘价
这样第二天才动手也说得通，不会用盘中瞬时价虚增收益。

T+N 口径
--------
bars 按日期升序，idx = 入选日在 bars 中的下标。
  T+5  盈亏 = (bars[idx+5].close / P0 - 1) * 100
  T+30 盈亏 = (bars[idx+30].close / P0 - 1) * 100
不足 N 个交易日 -> None（界面显示「持有中」，不拿未到期数据充数）。

注意
----
本模块只读 kline_cache，不写它；所有写入只落在 picks_tracking.duckdb。
"""
import os
import re
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRACK_DB = os.path.join(PROJECT_ROOT, 'data', 'cache', 'picks_tracking.duckdb')
KLINE_DB = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
LU_DB = os.path.join(PROJECT_ROOT, 'data', 'limit_up_reason.db')

# 与 services.board_anomaly_engine 的候选口径保持一致
PICK_MIN_PCT = 1.0
PICK_MAX_PCT = 5.0
PICK_MIN_VR = 1.2
PICK_MIN_PRICE = 6.0
LIMIT_UP_PCT = 9.5          # 主板口径：涨幅 >= 9.5% 视为已涨停（创业板见 _lu_pct）
BACKFILL_DAYS = 70          # 回填最近多少个交易日
TRACK_KEEP_DAYS = 100       # 追踪表保留多少自然日（约 70 个交易日，
                            # 要留够 T+30 的样本，所以比回填窗口大）
BOARD_MIN_STOCK = 2         # 板块内至少 N 家涨停才算异动板块（回填用）
_PICK_TOP = 5               # 每个(日期,板块)最多记 N 只，与引擎 _PICK_TOP 对齐


# [CYB-GATE] 创业板 300/301 与科创板 688/689 是 20cm 板，主板 10cm。
# 原先把「已涨停 -> 不是介入标的」统一按 9.5% 判，会把创业板 +10%~19.4%
# 的非涨停股当成已涨停剔除掉，等于把正在走强的创业板票挡在候选之外。
def _lu_pct(code) -> float:
    """按板性返回「视为已涨停」的涨幅阈值（%）：主板 9.5，创业板/科创板 19.5。"""
    c = str(code or '')
    if c.startswith(('300', '301', '688', '689')):
        return 19.5
    return LIMIT_UP_PCT


def _load_name_map() -> Dict[str, str]:
    """一次读出 code -> name（回填时逐条查库太慢）"""
    out: Dict[str, str] = {}
    if not os.path.exists(LU_DB):
        return out
    try:
        c = sqlite3.connect(LU_DB)
        for code, name in c.execute(
                'SELECT DISTINCT code, name FROM limit_up_reasons '
                'WHERE name IS NOT NULL AND name != ""'):
            if code:
                out[str(code)] = str(name)
        c.close()
    except Exception as e:
        print(f'[可介入追踪] 读名称映射失败: {e}', flush=True)
    return out


# ======================================================================
# 建表
# ======================================================================
def ensure_schema(con) -> None:
    """幂等建表 + 老库列升级"""
    con.execute("""
        CREATE TABLE IF NOT EXISTS picks_tracking (
            trade_date   VARCHAR,
            code         VARCHAR,
            name         VARCHAR,
            board        VARCHAR,
            kind         VARCHAR,
            base_price   FLOAT,
            pct0         FLOAT,
            vol_ratio    FLOAT,
            base_source  VARCHAR,
            created_at   TIMESTAMP
        )
    """)
    for col, typ in (('board', 'VARCHAR'), ('kind', 'VARCHAR'),
                     ('pct0', 'FLOAT'), ('vol_ratio', 'FLOAT'),
                     ('base_source', 'VARCHAR')):
        try:
            con.execute(f'ALTER TABLE picks_tracking ADD COLUMN IF NOT EXISTS {col} {typ}')
        except Exception:
            pass
    # 同一 (交易日, 代码) 只保留一条
    try:
        con.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_picks '
                    'ON picks_tracking (trade_date, code)')
    except Exception:
        pass


# ======================================================================
# 写入：当天 picks
# ======================================================================
def persist_picks(rows: List[dict], trade_date: str, db_path: str = TRACK_DB) -> int:
    """把当天各板块的 picks 幂等写入追踪表。返回新写入条数。

    rows 里每个元素 = 板块行，含 'name'（板块名）、'kind'、'picks'（候选列表）。
    一只票可能同时属于多个板块，这里按 (trade_date, code) 去重，
    板块名取它首次出现时所属的板块。
    """
    try:
        from utils import trade_calendar as _tc
        if not _tc.is_trading_day(datetime.strptime(trade_date, '%Y-%m-%d')):
            print(f'[可介入追踪] 非交易日 {trade_date}：拒绝写入', flush=True)
            return 0
    except Exception as e:
        print(f'[可介入追踪] 交易日校验异常，拒绝写入: {e}', flush=True)
        return 0

    # 先把同一只票在多个板块里的重复合并
    merged: Dict[str, dict] = {}
    for r in rows or []:
        for p in (r.get('picks') or []):
            try:
                code = str(p[0] or '')
                if not code:
                    continue
                if code not in merged:
                    merged[code] = {
                        'code': code,
                        'name': p[1] or '',
                        'board': r.get('name') or '',
                        'kind': r.get('kind') or '',
                        'pct0': float(p[2] or 0),
                        'vol_ratio': float(p[3] or 0),
                        'price': float(p[4] or 0),
                    }
            except (TypeError, ValueError, IndexError):
                continue
    if not merged:
        return 0

    try:
        import duckdb
    except Exception as e:
        print(f'[可介入追踪] 无 duckdb: {e}', flush=True)
        return 0

    added = 0
    try:
        con = duckdb.connect(db_path)
        ensure_schema(con)
        for code, m in merged.items():
            px = m['price']
            if px <= 0:
                continue
            # P0 一旦写入就不再覆盖，保证收益基准稳定
            exists = con.execute(
                'SELECT base_price FROM picks_tracking WHERE trade_date=? AND code=?',
                [trade_date, code]).fetchone()
            if exists is not None:
                # 老记录缺价才补，其余不动
                if not exists[0] or float(exists[0]) <= 0:
                    con.execute(
                        'UPDATE picks_tracking SET base_price=?, base_source=? '
                        'WHERE trade_date=? AND code=?',
                        [px, 'REALTIME', trade_date, code])
                continue
            con.execute(
                'INSERT INTO picks_tracking '
                '(trade_date, code, name, board, kind, base_price, pct0, '
                ' vol_ratio, base_source, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?)',
                [trade_date, code, m['name'], m['board'], m['kind'],
                 px, m['pct0'], m['vol_ratio'], 'REALTIME', datetime.now()])
            added += 1
        # 清理超期记录
        try:
            con.execute(
                'DELETE FROM picks_tracking WHERE trade_date < '
                "CAST(CURRENT_DATE - INTERVAL %d DAY AS VARCHAR)" % TRACK_KEEP_DAYS)
        except Exception:
            pass
        con.close()
    except Exception as e:
        print(f'[可介入追踪] 写入失败: {e}', flush=True)
        return added
    if added:
        print(f'[可介入追踪] {trade_date} 写入 {added} 只可介入标的', flush=True)
    return added


# ======================================================================
# 读取 + 算盈亏
# ======================================================================
def _load_kline_map(codes: List[str]) -> Dict[str, List[tuple]]:
    """一次读全所有相关股票的日线（升序）：code -> [(date, close), ...]"""
    out: Dict[str, List[tuple]] = {}
    if not codes or not os.path.exists(KLINE_DB):
        return out
    try:
        import duckdb
        con = duckdb.connect(KLINE_DB, read_only=True)
        try:
            ph = ','.join(['?'] * len(codes))
            for code, date, close in con.execute(
                    f'SELECT code, date, close FROM kline_cache '
                    f'WHERE code IN ({ph}) ORDER BY code, date ASC',
                    codes).fetchall():
                c = float(close or 0)
                if c > 0:
                    out.setdefault(str(code), []).append((str(date)[:10], c))
        finally:
            con.close()
    except Exception as e:
        print(f'[可介入追踪] 读 kline_cache 失败: {e}', flush=True)
    return out


def fetch_tracking(today: Optional[str] = None,
                   today_quotes: Optional[Dict[str, dict]] = None) -> List[dict]:
    """读追踪表 + 算 T+5 / T+30 / 累计盈亏。供后台线程调用。

    today_quotes: 可选，{code: {'price':.., 'name':..}} 用于填「当前价」，
                  同时当 kline_cache 还没有当天K线时，用它拼一根补上，
                  否则入选当天找不到 idx，5日/30日盈亏会永远算不出来。
    """
    if not os.path.exists(TRACK_DB):
        return []
    try:
        import duckdb
    except Exception as e:
        print(f'[可介入追踪] 无 duckdb: {e}', flush=True)
        return []

    today = today or datetime.now().strftime('%Y-%m-%d')
    records = []
    try:
        con = duckdb.connect(TRACK_DB)
        try:
            con.execute(
                'DELETE FROM picks_tracking WHERE trade_date < '
                "CAST(CURRENT_DATE - INTERVAL %d DAY AS VARCHAR)" % TRACK_KEEP_DAYS)
        except Exception:
            pass
        try:
            records = con.execute(
                'SELECT trade_date, code, name, board, kind, base_price, '
                'pct0, vol_ratio FROM picks_tracking '
                'ORDER BY trade_date DESC, vol_ratio DESC').fetchall()
        finally:
            con.close()
    except Exception as e:
        print(f'[可介入追踪] 读追踪表失败: {e}', flush=True)
        return []
    if not records:
        return []

    codes = sorted({str(r[1]) for r in records if r[1]})
    kmap = _load_kline_map(codes)
    quotes = today_quotes or {}

    out = []
    for (td, code, name, board, kind, bp, pct0, vr) in records:
        td = str(td)[:10]
        code = str(code)
        bp = float(bp or 0)
        bars = kmap.get(code, [])

        # 当前价：优先实时，其次最近收盘
        cur = 0.0
        q = quotes.get(code)
        if q:
            try:
                cur = float(q.get('price') or 0)
            except (TypeError, ValueError):
                cur = 0.0
        if cur <= 0 and bars:
            cur = bars[-1][1]

        # 定位入选日
        idx = None
        for i, (d, _c) in enumerate(bars):
            if d == td:
                idx = i
                break
        # kline_cache 当天K线还没落盘（收盘后才更新）时，用实时行情拼一根，
        # 否则 idx 定位不到，T+5/T+30 永远是「持有中」。
        if idx is None and q and td == today and bars:
            cur_px = float(q.get('price') or 0)
            if cur_px > 0 and td > bars[-1][0]:
                bars = bars + [(td, cur_px)]
                idx = len(bars) - 1
        if idx is None and q and td == today and not bars:
            cur_px = float(q.get('price') or 0)
            if cur_px > 0:
                bars = [(td, cur_px)]
                idx = 0

        def _ret(n):
            if idx is None or bp <= 0:
                return None
            j = idx + n
            if j < len(bars) and bars[j][1] > 0:
                v = round((bars[j][1] - bp) / bp * 100.0, 2)
                return 0.0 if abs(v) < 0.005 else v
            return None

        # 累计盈亏：到最新价的收益。当天刚入选的不算（还没有持有期，
        # 收益必然为 0，计进去会被当成「没赢」压低胜率），显示为「持有中」。
        if td >= today or cur <= 0 or bp <= 0:
            cum = None
        else:
            cum = round((cur - bp) / bp * 100.0, 2)
            if abs(cum) < 0.005:
                cum = 0.0

        # 距 MA20：本地 K 线最近 20 个收盘均值（不足 20 根给 None，界面显示 --）
        ma20 = None
        _cl = [b[1] for b in bars[-20:] if b[1] and b[1] > 0]
        if len(_cl) >= 20:
            ma20 = sum(_cl) / 20.0

        out.append({
            'trade_date': td,
            'code': code,
            'name': str(name or ''),
            'board': str(board or '--'),
            'kind': str(kind or ''),
            'pct0': float(pct0 or 0),
            'vol_ratio': float(vr or 0),
            'base_price': bp,
            'cur_price': cur,
            'ma20': ma20,
            'r5': _ret(5),
            'r30': _ret(30),
            'cum': cum,
        })
    return out


def summarize(rows: List[dict]) -> dict:
    """统计胜率与均值。样本为 0 的项返回 None，界面上显示「--」而不是 0。"""
    def _stat(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return {'n': 0, 'win': None, 'avg': None, 'max': None, 'min': None}
        win = sum(1 for v in vals if v > 0)
        return {
            'n': len(vals),
            'win': round(win / len(vals) * 100.0, 1),
            'avg': round(sum(vals) / len(vals), 2),
            'max': round(max(vals), 2),
            'min': round(min(vals), 2),
        }

    return {'total': len(rows), 'r5': _stat('r5'),
            'r30': _stat('r30'), 'cum': _stat('cum')}


# ======================================================================
# 历史回填：从 kline_cache 反算过去 N 个交易日的可介入标的
# ======================================================================
def _load_theme_map() -> Dict[str, tuple]:
    """code -> (最近一次涨停的 industry, reason)，用于给回填记录标板块。"""
    out: Dict[str, tuple] = {}
    if not os.path.exists(LU_DB):
        return out
    try:
        c = sqlite3.connect(LU_DB)
        cur = c.cursor()
        for code, industry, reason in cur.execute(
                'SELECT code, industry, reason FROM limit_up_reasons ORDER BY date ASC'):
            out[str(code or '')] = ((industry or '').strip(), (reason or '').strip())
        c.close()
    except Exception as e:
        print(f'[可介入追踪] 读涨停库失败: {e}', flush=True)
    return out


def _norm_date(d) -> str:
    """统一日期成 YYYY-MM-DD。

    坑：涨停库 limit_up_reasons.date 是 '20260930'（8 位无横线），
    而 kline_cache.date 是 '2026-09-30'（带横线）。两边不规范化，
    按日期对齐板块时会永远匹配不上，候选会被全部过滤掉。
    """
    s = str(d or '').strip()
    if len(s) == 8 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:]}'
    return s[:10]


def _load_board_pools():
    """构建「板块活跃池」+「每天哪些板块异动」。

    关键区别（第一版在这里错了）：
      板块「是不是异动」用当天涨停家数判断；
      但板块「成分是谁」必须用**全历史活跃池**，和引擎一致。
      若拿当天涨停股当成分，候选又要求「当天没涨停」，两者互斥 -> 几乎筛不出票。

    返回 (ind_pool, th_pool, code_ind, code_th, active_by_date)
      ind_pool[行业] -> set(code)          全历史在该细分行业涨停过的股票
      th_pool[题材] -> set(code)           全历史带过该题材词的股票
      code_ind[code] -> set(行业)          反查表
      code_th[code]  -> set(题材)
      active_by_date[date] -> {'ind': set(), 'th': set()}   当天涨停≥2家的板块
    """
    from collections import defaultdict
    ind_pool, th_pool = defaultdict(set), defaultdict(set)
    code_ind, code_th = defaultdict(set), defaultdict(set)
    day_ind, day_th = defaultdict(lambda: defaultdict(set)), \
        defaultdict(lambda: defaultdict(set))

    if not os.path.exists(LU_DB):
        return {}, {}, {}, {}, {}
    try:
        c = sqlite3.connect(LU_DB)
        cur = c.cursor()
        for date, code, industry, reason in cur.execute(
                'SELECT date, code, industry, reason FROM limit_up_reasons'):
            code = str(code or '')
            if not code.startswith(('60', '00', '30')):
                continue
            d = _norm_date(date)
            industry = (industry or '').strip()
            if industry:
                ind_pool[industry].add(code)
                code_ind[code].add(industry)
                day_ind[d][industry].add(code)
            if reason:
                for t in re.split(r'[+＋·、/]', reason):
                    t = t.strip()
                    for ch in ('\u201c', '\u201d', '\u2018', '\u2019',
                               '\u300c', '\u300d'):
                        t = t.replace(ch, '')
                    t = t.strip()
                    if 2 <= len(t) <= 12:
                        th_pool[t].add(code)
                        code_th[code].add(t)
                        day_th[d][t].add(code)
        c.close()
    except Exception as e:
        print(f'[可介入追踪] 读涨停库(板块池)失败: {e}', flush=True)
        return {}, {}, {}, {}, {}

    # 当天涨停 >=2 家的板块才算「异动板块」
    active = {}
    for d in set(day_ind) | set(day_th):
        a_i = {k for k, v in day_ind[d].items() if len(v) >= BOARD_MIN_STOCK}
        a_t = {k for k, v in day_th[d].items() if len(v) >= BOARD_MIN_STOCK}
        if a_i or a_t:
            active[d] = {'ind': a_i, 'th': a_t}
    return (dict(ind_pool), dict(th_pool), dict(code_ind), dict(code_th), active)


def backfill_history(days: int = BACKFILL_DAYS, db_path: str = TRACK_DB) -> dict:
    """用 kline_cache 反算历史每个交易日的可介入标的并写入追踪表。

    为什么需要：功能刚上线时追踪表是空的，5日/30日盈亏全是「持有中」，
    完全看不出这个信号准不准。用本地日K把过去还原一遍，立刻就有样本。

    口径（与引擎当日筛选一致，唯一差别是不做 ST 名称过滤 —— kline_cache 无名称，
    这里用「该股在涨停库出现过」替代，天然排除了多数问题股）：
        非涨停(涨幅 主板<9.5% / 创业板·科创板<19.5%) + 涨幅 1~9% + 收盘≥6元 + 量比≥1.2 + 收盘≥MA20
        且所属板块当天涨停 ≥2 家
    """
    if not os.path.exists(KLINE_DB):
        return {'error': 'kline_cache.duckdb 不存在'}
    try:
        import duckdb
    except Exception as e:
        return {'error': f'无 duckdb: {e}'}

    th_map = None      # 已由 _load_board_pools 的 code_ind/code_th 覆盖，不再单独扫库

    # ---- 1) 一条 SQL 算全市场每天的 涨幅 / MA20 / 前5日均量 ----
    con = duckdb.connect(KLINE_DB, read_only=True)
    try:
        rows = con.execute("""
            WITH base AS (
                SELECT code, date, close, volume,
                       LAG(close) OVER (PARTITION BY code ORDER BY date) AS pc,
                       AVG(close)  OVER (PARTITION BY code ORDER BY date
                                         ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
                       AVG(volume) OVER (PARTITION BY code ORDER BY date
                                         ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS v5,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY date) AS rn
                FROM kline_cache
                WHERE code LIKE '60%' OR code LIKE '00%' OR code LIKE '30%'
            )
            SELECT code, date, close, pc, ma20, v5, rn,
                   (close / pc - 1.0) * 100.0 AS pct,
                   CASE WHEN v5 > 0 THEN volume / v5 ELSE 0 END AS vr
            FROM base
            WHERE pc IS NOT NULL AND pc > 0 AND rn > 20
        """).fetchall()
    finally:
        con.close()

    # ---- 2) 板块活跃池 + 每天哪些板块异动 ----
    ind_pool, th_pool, code_ind, code_th, active = _load_board_pools()
    if not active or not code_ind:
        return {'error': '涨停库为空或无法构建板块，检查 limit_up_reason.db'}

    # ---- 4) 过滤出候选 ----
    cutoff = None
    cand = []
    for (code, date, close, pc, ma20, v5, rn, pct, vr) in rows:
        d = str(date)[:10]
        if cutoff is None or d > cutoff:
            cutoff = d
        if pct is None or close is None:
            continue
        try:
            pct = float(pct)
            close = float(close)
            ma20 = float(ma20 or 0)
            vr = float(vr or 0)
        except (TypeError, ValueError):
            continue
        if pct >= _lu_pct(code):                       # 已涨停 -> 是龙头，不是介入标的
            continue
        if not (PICK_MIN_PCT <= pct < PICK_MAX_PCT):
            continue
        if close < PICK_MIN_PRICE:
            continue
        if vr < PICK_MIN_VR:
            continue
        if ma20 > 0 and close < ma20:
            continue
        if code not in code_ind and code not in code_th:
            continue                                  # 非板块活跃标的（涨停库无记录）
        a = active.get(d)
        if not a:                                     # 当天没有任何板块异动
            continue
        _ht = code_th.get(code, set()) & a['th']
        _hi = code_ind.get(code, set()) & a['ind']
        if _ht:                                       # 题材优先，与引擎展示顺序一致
            board, kind = sorted(_ht)[0], '题材'
        elif _hi:
            board, kind = sorted(_hi)[0], '行业'
        else:
            continue                                  # 所属板块当天没异动
        cand.append((d, code, board, kind, close, pct, vr))

    # ---- 5) 只保留最近 days 个交易日 ----
    all_dates = sorted({c[0] for c in cand})
    if days and len(all_dates) > days:
        keep = set(all_dates[-days:])
        cand = [c for c in cand if c[0] in keep]
        all_dates = all_dates[-days:]

    # ---- 6) 每个(日期,板块)按量比降序最多取 _PICK_TOP 只，对齐引擎 ----
    cand.sort(key=lambda x: (x[0], x[2], -x[6]))
    picked, cnt = [], {}
    for c in cand:
        k = (c[0], c[2])
        if cnt.get(k, 0) >= _PICK_TOP:
            continue
        cnt[k] = cnt.get(k, 0) + 1
        picked.append(c)
    cand = picked
    if not cand:
        return {'error': '没有回算出任何候选，检查 kline_cache 日期范围'}

    name_map = _load_name_map()

    # ---- 7) 写入（同一天同一只票只留一条）----
    con = duckdb.connect(db_path)
    added = 0
    try:
        ensure_schema(con)
        seen = set()
        for (d, code, board, kind, close, pct, vr) in cand:
            if (d, code) in seen:
                continue
            seen.add((d, code))
            exists = con.execute(
                'SELECT 1 FROM picks_tracking WHERE trade_date=? AND code=?',
                [d, code]).fetchone()
            if exists:
                continue
            con.execute(
                'INSERT INTO picks_tracking '
                '(trade_date, code, name, board, kind, base_price, pct0, '
                ' vol_ratio, base_source, created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?)',
                [d, code, name_map.get(code, ''), board, kind, close,
                 round(pct, 2), round(vr, 2), 'BACKFILL', datetime.now()])
            added += 1
        con.close()
    except Exception as e:
        print(f'[可介入追踪] 回填写入失败: {e}', flush=True)
        try:
            con.close()
        except Exception:
            pass
        return {'error': str(e)}

    res = {'added': added, 'scanned': len(cand), 'days': len(all_dates),
           'latest_kline': cutoff, 'first': all_dates[0] if all_dates else None}
    print(f'[可介入追踪] 回填完成：候选 {len(cand)} 条，新写入 {added} 条，'
          f'{len(all_dates)} 个交易日，kline 最新 {cutoff}', flush=True)
    return res


def has_data(db_path: str = TRACK_DB) -> bool:
    """追踪表是否已有数据（决定要不要触发首次回填）"""
    if not os.path.exists(db_path):
        return False
    try:
        import duckdb
        con = duckdb.connect(db_path, read_only=True)
        try:
            n = con.execute('SELECT COUNT(*) FROM picks_tracking').fetchone()[0]
        finally:
            con.close()
        return int(n or 0) > 0
    except Exception:
        return False


if __name__ == '__main__':
    import sys
    if '--backfill' in sys.argv:
        n = BACKFILL_DAYS
        for i, a in enumerate(sys.argv):
            if a == '--days' and i + 1 < len(sys.argv):
                n = int(sys.argv[i + 1])
        print(backfill_history(n))
    elif '--show' in sys.argv:
        rs = fetch_tracking()
        s = summarize(rs)
        print('样本 %d 只' % s['total'])
        for k, lbl in (('r5', '5日'), ('r30', '30日'), ('cum', '累计')):
            v = s[k]
            print('  %s: 样本 %d  胜率 %s%%  均值 %s%%  最好 %s%%  最差 %s%%'
                  % (lbl, v['n'], v['win'], v['avg'], v['max'], v['min']))
        for r in rs[:15]:
            print('   %s %s %s %s P0=%.2f 5日=%s 30日=%s 累计=%s'
                  % (r['trade_date'], r['code'], r['name'], r['board'],
                     r['base_price'], r['r5'], r['r30'], r['cum']))
