# -*- coding: utf-8 -*-
"""策略选股扫描服务 —— 「策略看板」页（对标 TickFlow Stock Panel 的选股/扫描部分）。

在本地 kline_cache.duckdb 上跑经典技术指标策略：
  MA金叉5/20 / 均线多头排列 / MACD金叉 / RSI超卖 / KDJ金叉 / 放量突破新高 / 缩量回踩MA20。
只吃日K，不做网络兜底；与「控盘选股」共用 load_all_bars() / code_name_map() / is_st_name()。
信号一律判在**最新一根**上（盘中=未收盘 bar，与控盘选股同一口径）。
"""
import json
import os
import time

from services.control_screen_service import (
    load_all_bars, code_name_map, is_st_name,
)

SNAPSHOT_PATH = os.path.join('data', 'cache', 'strategy_panel.json')

# key -> (显示名, 一句话说明)
STRATEGIES = [
    ('ma_gold',       'MA金叉5/20',   'MA5上穿MA20'),
    ('ma_long',       '均线多头排列',  'MA5 > MA20 > MA60'),
    ('macd_gold',     'MACD金叉',     'DIF 上穿 DEA'),
    ('rsi_oversold',  'RSI超卖',      'RSI14 ≤ 25'),
    ('kdj_gold',      'KDJ金叉',      'K 上穿 D'),
    ('brk_vol',       '放量突破新高',  '收盘创20日新高 且 量比 ≥ 1.5'),
    ('pull_ma20',     '缩量回踩MA20',  '触及MA20附近、缩量企稳'),
]
KEY2NAME = {k: n for k, n, _ in STRATEGIES}
KEYS_ALL = [k for k, _, _ in STRATEGIES]


# ============================================================
# 指标（纯 Python，不引 pandas/numpy，4400 只 ×120 根实测够用）
# ============================================================
def _ma_series(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _ema_series(vals, n):
    k = 2.0 / (n + 1)
    out = []
    e = None
    for v in vals:
        e = v if e is None else e + k * (v - e)
        out.append(e)
    return out


def _kdj_series(highs, lows, closes, n=9):
    ks, ds = [], []
    k = d = 50.0
    for i in range(len(closes)):
        if i < n - 1:
            ks.append(k); ds.append(d)
            continue
        lo = min(lows[i - n + 1:i + 1])
        hi = max(highs[i - n + 1:i + 1])
        rsv = (closes[i] - lo) / (hi - lo) * 100.0 if hi > lo else 50.0
        k = 2.0 / 3.0 * k + 1.0 / 3.0 * rsv
        d = 2.0 / 3.0 * d + 1.0 / 3.0 * k
        ks.append(k); ds.append(d)
    return ks, ds


# ============================================================
# 单只判定
# ============================================================
def signal_series(bars):
    """{key: [bool,...]} 与 bars 等长：T 日收盘出信号（按 T+1 约定，次日开盘才能买）。
    与 compute_signals 共用同一套中间量，保证「扫描」与「回测」信号定义永不分叉。"""
    closes = [b['close'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    vols = [b['volume'] for b in bars]
    n = len(closes)
    out = {k: [False] * n for k in KEYS_ALL}
    if n < 61:
        return out
    ma5 = _ma_series(closes, 5)
    ma20 = _ma_series(closes, 20)
    ma60 = _ma_series(closes, 60)
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    ks, ds = _kdj_series(highs, lows, closes)
    dif = [ema12[i] - ema26[i] for i in range(n)]
    dea = _ema_series(dif, 9)
    for i in range(60, n):
        # 1) MA5 上穿 MA20
        if None not in (ma5[i - 1], ma20[i - 1], ma5[i], ma20[i]) and \
           ma5[i - 1] < ma20[i - 1] and ma5[i] >= ma20[i]:
            out['ma_gold'][i] = True
        # 2) 均线多头排列
        if ma5[i] and ma20[i] and ma60[i] and ma5[i] > ma20[i] > ma60[i]:
            out['ma_long'][i] = True
        # 3) MACD 金叉
        if dif[i - 1] < dea[i - 1] and dif[i] >= dea[i]:
            out['macd_gold'][i] = True
        # 4) RSI14 ≤ 25（滚动 14 日简单 Wilder 近似）
        g = l = 0.0
        for j in range(i - 13, i + 1):
            d = closes[j] - closes[j - 1]
            if d > 0:
                g += d
            else:
                l -= d
        if l > 0:
            rsi = 100.0 - 100.0 / (1.0 + (g / 14.0) / (l / 14.0))
        elif g > 0:
            rsi = 100.0
        else:
            rsi = 50.0
        if rsi <= 25.0:
            out['rsi_oversold'][i] = True
        # 5) KDJ 金叉
        if ks[i - 1] < ds[i - 1] and ks[i] >= ds[i]:
            out['kdj_gold'][i] = True
        # 6) 放量突破：收盘创过去20日新高（不含当天）且 量比 ≥ 1.5
        prev_h = max(highs[i - 20:i])
        avg5 = sum(vols[i - 5:i]) / 5.0 if i >= 5 else 0.0
        if closes[i] > prev_h and avg5 > 0 and vols[i] >= avg5 * 1.5:
            out['brk_vol'][i] = True
        # 7) 缩量回踩 MA20：近2日最低价触及 MA20 ±2%、收盘站上 MA20、缩量
        if ma20[i] and avg5 > 0:
            touch = (min(lows[i - 1:i + 1]) <= ma20[i] * 1.02 and
                     min(lows[i - 1:i + 1]) >= ma20[i] * 0.97)
            if touch and closes[i] > ma20[i] and vols[i] < avg5 * 0.9:
                out['pull_ma20'][i] = True
    return out


def compute_signals(bars):
    """bars: 按日期升序的 [{date,open,high,low,close,volume}, ...]。
    返回 (hits: set(key), info: dict)。bars 不足 60 根时 hits 为空。"""
    closes = [b['close'] for b in bars]
    vols = [b['volume'] for b in bars]
    n = len(closes)
    if n < 60:
        return set(), {}

    series = signal_series(bars)
    hits = {k for k, v in series.items() if v[-1]}

    # 近120日位置（与控盘选股同口径）
    win = closes[-120:]
    lo = min(win)
    hi = max(win)
    pos = (closes[-1] - lo) / (hi - lo) if hi > lo else 0.5

    info = {
        'price': closes[-1],
        'pct': (closes[-1] / closes[-2] - 1.0) * 100.0 if closes[-2] > 0 else 0.0,
        'pos': round(pos, 3),
        'date': str(bars[-1].get('date', '')),
    }
    return hits, info


def scan_market(keys=None, progress_cb=None, cancel_cb=None):
    """全市场扫描。keys=None 或为空 → 用全部策略。
    返回 {'rows': [...], 'data_date': ..., 'stats': {...}}。"""
    keys = keys or KEYS_ALL
    t0 = time.time()
    bars_map = load_all_bars()
    names = code_name_map()
    total = len(bars_map)
    rows = []
    per_strategy = {k: 0 for k in keys}
    data_date = ''
    for i, (code, bars) in enumerate(sorted(bars_map.items())):
        if cancel_cb is not None and cancel_cb():
            break
        if i % 300 == 0 and progress_cb is not None:
            progress_cb(i, total, '策略扫描中 %d/%d' % (i, total))
        name = names.get(code, '')
        if is_st_name(name):
            continue
        try:
            hits, info = compute_signals(bars)
        except Exception:
            continue
        hits = hits & set(keys)
        if not hits:
            continue
        rows.append({
            'code': code, 'name': name,
            'price': round(info['price'], 2), 'pct': round(info['pct'], 2),
            'pos': info['pos'], 'date': info['date'],
            'hits': sorted(hits, key=KEYS_ALL.index),
        })
        for k in hits:
            per_strategy[k] += 1
        data_date = data_date or info['date']

    rows.sort(key=lambda r: (-len(r['hits']), -abs(r['pct'])))
    out = {
        'rows': rows,
        'data_date': data_date,
        'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'keys': list(keys),
        'stats': {
            'total': total, 'hits': len(rows),
            'per_strategy': per_strategy,
            'elapsed': round(time.time() - t0, 1),
        },
    }
    if progress_cb is not None:
        progress_cb(total, total, '扫描完成：%d 只命中 / %d 只' % (len(rows), total))
    return out


def save_snapshot(payload, path=None):
    path = path or SNAPSHOT_PATH
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except Exception as e:
        print('[策略看板] 写快照失败: %s' % e, flush=True)
        return False


def load_snapshot(path=None):
    path = path or SNAPSHOT_PATH
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
