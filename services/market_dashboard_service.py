# -*- coding: utf-8 -*-
"""市场看板仪表盘数据服务（对标 TickFlow Stock Panel 首页）。

所有块都吃本地已有数据，不新增外部依赖：
  - 全市场当日统计（涨跌家数/分布/MA站上率/新高新低/涨跌榜/成交额）
    ← control_screen_service.load_all_bars()（kline_cache）
  - 涨停/跌停/连板梯队/炸板/封板率
    ← data/limit_up_reason.db（THS 采集）
  - 概念/行业热度
    ← services/board_anomaly_engine（已聚合好，直接调）

周六休市时 = 最近一个交易日的收盘统计。
"""
import os
import sqlite3
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.control_screen_service import load_all_bars, code_name_map  # noqa: E402

_LU_DB = os.path.join(ROOT, 'data', 'limit_up_reason.db')


# ----------------------------------------------------------------------
# 通用小工具
# ----------------------------------------------------------------------
def _avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ----------------------------------------------------------------------
# 涨停数据库
# ----------------------------------------------------------------------
def _load_limit_up_today():
    """返回最新采集日的涨停股列表 + 统计。
    每只股票在 limit_up_reasons 里可能有多条（开板回封），按 code 去重取最后一条。"""
    if not os.path.exists(_LU_DB):
        return None, {}
    try:
        c = sqlite3.connect(_LU_DB)
        cur = c.cursor()
        d = cur.execute('SELECT MAX(date) FROM limit_up_reasons').fetchone()[0]
        rows = cur.execute(
            'SELECT code, name, pct_chg, lbc, reason, industry, zbc, amount '
            'FROM limit_up_reasons WHERE date=? ORDER BY id DESC', (d,)).fetchall()
        c.close()
    except Exception:
        return None, {}
    by_code = {}
    for code, name, pct, lbc, reason, industry, zbc, amount in rows:
        if code not in by_code:
            by_code[code] = {'code': code, 'name': name, 'pct': pct, 'lbc': lbc or 1,
                             'reason': reason or '', 'industry': industry or '',
                             'zbc': zbc or 0, 'amount': amount or 0.0}
    lst = list(by_code.values())
    ladder = defaultdict(int)
    for r in lst:
        ladder[max(1, r['lbc'])] += 1
    broken = sum(1 for r in lst if r['zbc'] > 0)
    stat = {
        'date': d,
        'lu_count': len(lst),
        'ladder': dict(sorted(ladder.items())),   # {连板数: 家数}
        'max_lbc': max(ladder) if ladder else 0,
        'broken': broken,                          # 当日炸板过的涨停股
        'fengban_rate': round(len(lst) / max(1, len(lst) + broken) * 100, 1),
    }
    return lst, stat


# ----------------------------------------------------------------------
# 全市场广度统计
# ----------------------------------------------------------------------
def compute_breadth(bars_map, names):
    pcts = []
    closes = []
    n_up = n_flat = n_dn = 0
    n_ma5 = n_ma20 = n_ma60 = 0
    n_new60h = n_new60l = 0
    total_amount = 0.0
    n_hi3 = n_lo3 = 0          # 涨超3% / 跌超3%
    turnoverish = []           # 用振幅近似活跃度
    for code, bars in bars_map.items():
        if len(bars) < 61:
            continue
        c = bars[-1]['close']
        prev = bars[-2]['close']
        if prev <= 0 or c <= 0:
            continue
        p = (c / prev - 1.0) * 100.0
        pcts.append(p)
        amt = bars[-1].get('amount', 0.0) or c * bars[-1].get('volume', 0)
        closes.append((code, names.get(code, ''), c, p, amt))
        if p > 0.05:
            n_up += 1
        elif p < -0.05:
            n_dn += 1
        else:
            n_flat += 1
        if p >= 3:
            n_hi3 += 1
        if p <= -3:
            n_lo3 += 1
        ma5 = sum(b['close'] for b in bars[-5:]) / 5.0
        ma20 = sum(b['close'] for b in bars[-20:]) / 20.0
        ma60 = sum(b['close'] for b in bars[-60:]) / 60.0
        if c > ma5:
            n_ma5 += 1
        if c > ma20:
            n_ma20 += 1
        if c > ma60:
            n_ma60 += 1
        win60 = bars[-60:]
        if c >= max(b['high'] for b in win60):
            n_new60h += 1
        if c <= min(b['low'] for b in win60):
            n_new60l += 1
        total_amount += bars[-1].get('amount', 0.0) or bars[-1].get('close', 0) * bars[-1].get('volume', 0)
        rng = (bars[-1]['high'] - bars[-1]['low']) / prev * 100.0 if prev else 0
        turnoverish.append((code, names.get(code, ''), c, p, bars[-1].get('amount', 0.0), rng))
    n = max(1, len(pcts))
    # 涨跌分布 8 桶
    buckets = [0] * 8   # <-5, -5~-3, -3~-1, -1~0, 0~1, 1~3, 3~5, >5
    for p in pcts:
        if p < -5:
            buckets[0] += 1
        elif p < -3:
            buckets[1] += 1
        elif p < -1:
            buckets[2] += 1
        elif p < 0:
            buckets[3] += 1
        elif p < 1:
            buckets[4] += 1
        elif p < 3:
            buckets[5] += 1
        elif p < 5:
            buckets[6] += 1
        else:
            buckets[7] += 1
    gainers = sorted(closes, key=lambda x: -x[3])[:8]
    losers = sorted(closes, key=lambda x: x[3])[:8]
    by_amt = sorted(closes, key=lambda x: -x[4])[:8]
    active = sorted(turnoverish, key=lambda x: -x[5])[:8]
    return {
        'n_total': n,
        'n_up': n_up, 'n_flat': n_flat, 'n_dn': n_dn,
        'avg_pct': round(_avg(pcts), 2),
        'median_pct': round(_median(pcts), 2),
        'buckets': buckets,
        'n_hi3': n_hi3, 'n_lo3': n_lo3,
        'ma5_pct': round(n_ma5 / n * 100, 1),
        'ma20_pct': round(n_ma20 / n * 100, 1),
        'ma60_pct': round(n_ma60 / n * 100, 1),
        'new_high': n_new60h, 'new_low': n_new60l,
        'hl_ratio': round(n_new60h / max(1, n_new60l), 1),
        'total_amount_yi': round(total_amount / 1e8, 0),
        'gainers': [(c, nm, p) for c, nm, _, p, _ in gainers],
        'losers': [(c, nm, p) for c, nm, _, p, _ in losers],
        'by_amt': [(c, nm, amt / 1e8) for c, nm, _, _, amt in by_amt],
        'active': [(c, nm, rng) for c, nm, _, _, _, rng in active],
    }


def _concept_industry():
    """概念/行业热度（复用现有引擎；失败返回空）。"""
    try:
        from services.board_anomaly_engine import get_board_anomaly
        res = get_board_anomaly()
        themes = res.get('themes') or []
        inds = res.get('industries') or []
        themes = sorted(themes, key=lambda t: -t.get('count', 0))[:5]
        inds = sorted(inds, key=lambda t: -t.get('count', 0))[:5]
        return themes, inds
    except Exception:
        return [], []


def compute_dashboard():
    bars_map = load_all_bars()
    names = code_name_map()
    breadth = compute_breadth(bars_map, names)
    lu_list, lu_stat = _load_limit_up_today()
    themes, inds = _concept_industry()
    # 情绪分（0~100）：45% 涨跌家数 + 30% MA20 站上率 + 25% 涨停跌停对比
    up_ratio = breadth['n_up'] / max(1, breadth['n_up'] + breadth['n_dn'])
    lu = lu_stat.get('lu_count', 0)
    score = round(45 * up_ratio + 30 * (breadth['ma20_pct'] / 100) +
                  25 * (lu / max(1, lu + breadth['n_lo3'])), 0)
    return {
        'breadth': breadth,
        'limit_up': lu_stat,
        'themes': themes,
        'industries': inds,
        'sentiment': int(score),
        'data_date': (bars_map.get(list(bars_map)[0])[-1]['date']
                      if bars_map else ''),
    }
