# -*- coding: utf-8 -*-
"""云端评分桥（工单1 适配层）

作用：在 Actions 的**纯标准库**运行时里，把能跑起来的引擎都算一遍，交给
strategy/score_aggregator.py 合成唯一 final_score。

原则：
  - 不 pip install、不改 yml 的前提下，只有纯 stdlib 的引擎能跑。
  - 跑不起来的引擎**如实标 unavailable + 原因**，由聚合层按比例摊权；
    绝不返回 50 分之类的假分（红线2）。
  - 全程异常隔离：任一引擎崩溃不影响其它引擎和主流程。
"""
from __future__ import annotations

import importlib.util
import os

_SELF = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SELF)

_MODS = {}


def _load(rel_path, alias):
    if alias in _MODS:
        return _MODS[alias]
    path = os.path.join(_ROOT, rel_path)
    if not os.path.exists(path):
        _MODS[alias] = None
        return None
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[alias] = mod
    return mod


def _bars_to_dicts(bars):
    """云端 K 线是 [date, open, close, high, low, vol] 的行；引擎要 dict。"""
    out = []
    for r in bars or []:
        try:
            out.append({'date': str(r[0]), 'open': float(r[1]), 'close': float(r[2]),
                        'high': float(r[3]), 'low': float(r[4]), 'volume': float(r[5])})
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# ---------------- 各引擎适配 ----------------

def _score_factor_engine(code, name, bars, quote, ctx, base_dir):
    fe = _load('tools/factor_engine.py', 'qm_fe')
    if fe is None:
        return None, 'factor_engine 文件缺失'
    q = quote or {}
    c = ctx or {}
    today = c.get('today')
    bars_ex = [r for r in (bars or []) if str(r[0]) != str(today)] if today else list(bars or [])
    vol_avg5 = None
    if len(bars_ex) >= 5:
        vs = [float(r[5]) for r in bars_ex[-5:] if _num(r[5]) and float(r[5]) > 0]
        vol_avg5 = sum(vs) / len(vs) if len(vs) == 5 else None
    emo = fe.score_emotion(lu=c.get('lu'), zb=c.get('zb'), max_lbc=c.get('max_lbc'),
                           yest_premium_pct=c.get('yest_premium_pct'))
    pv = fe.score_price_volume(bars=bars_ex, lb=q.get('lb') or c.get('lb'),
                               vol_today=q.get('vol'), vol_avg5=vol_avg5)
    pct = _num(q.get('pct')) or 0.0
    is_lu = pct >= (9.5 if str(code).startswith(('60', '00')) else 19.5)
    zj = fe.score_fund(out_vol=q.get('out'), in_vol=q.get('in'), bars=bars_ex,
                       is_limit_up=is_lu)
    dl = fe.score_momentum(bars=bars_ex)
    tc = fe.score_theme(theme_heat=(c.get('theme_heat') or {}).get(c.get('sec')), relation='实受益')
    fs = {'jq': emo.get('score'), 'lj': pv.get('score'), 'zj': zj.get('score'),
          'tc': tc.get('score'), 'dl': dl.get('score')}
    comb = fe.combine(auction_score=None, factor_scores=fs,
                      weights=_fe_weights(base_dir))
    total = comb.get('factor_total')
    return (_num(total) is not None and round(float(total), 2) or None), None


def _fe_weights(base_dir):
    import json
    p = os.path.join(base_dir or '.', 'data/factor_weights.json')
    try:
        with open(p, encoding='utf-8') as f:
            w = json.load(f)
        w = w.get('weights', w) if isinstance(w, dict) else {}
        if isinstance(w, dict) and w:
            s = sum(float(v) for v in w.values())
            if s > 0:
                return {k: float(v) / s for k, v in w.items()}
    except Exception:
        pass
    return {'jq': 0.30, 'lj': 0.30, 'zj': 0.20, 'tc': 0.10, 'dl': 0.10}


def _score_ai_520(code, name, bars, quote, ctx, base_dir):
    mod = _load('strategy/ai_520_buy_score.py', 'qm_520')
    if mod is None:
        return None, 'ai_520 文件缺失'
    q = quote or {}
    info = {'code': str(code), 'name': name or '', 'price': _num(q.get('cur')),
            'pct_chg': _num(q.get('pct'))}
    k = _bars_to_dicts(bars)
    if len(k) < 20:
        return None, 'K线不足20根'
    r = mod.get_buy_score().calc_buy_score(info, k)
    v = _num(r.get('buy_score'))
    return (round(v, 2) if v is not None else None), None


def _score_nine(code, name, bars, quote, ctx, base_dir):
    """九重评分：numpy 已装后真跑；入参由日K + 快照 + 市场上下文推出。"""
    mod = _load('strategy/nine_score_engine.py', 'qm_nine')
    if mod is None:
        return None, 'nine_score 文件缺失'
    k = _bars_to_dicts(bars)
    if len(k) < 20:
        return None, 'K线不足20根'
    closes = [x['close'] for x in k]
    vols = [x['volume'] for x in k]
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    avg5 = sum(vols[-6:-1]) / 5
    vr = (vols[-1] / avg5) if avg5 > 0 else 1.0
    c = ctx or {}
    fund = {'volume_ratio': round(vr, 2),
            'turnover_rate': _num((quote or {}).get('turn')) or 0.0}
    trend = {'ma_alignment': bool(closes[-1] > ma5 > ma10 > ma20),
             'ma5_above_ma10': bool(ma5 > ma10),
             'price_above_ma20': bool(closes[-1] > ma20)}
    sent = {'market_cycle': c.get('market_cycle') or '混沌期',
            'consecutive_board_height': int(c.get('max_lbc') or 0),
            'limit_up_gene': bool(c.get('limit_up_gene')),
            'stock_in_hot_sector': bool(c.get('sec') and (c.get('theme_heat') or {}).get(c.get('sec'))),
            'sentiment_temperature': _num(c.get('sentiment_temperature')) or 50.0}
    r = mod.get_nine_score_engine().calculate(fund_params=fund, trend_params=trend,
                                             sentiment_params=sent)
    v = _num(getattr(r, 'total', None))
    return (round(v, 2) if v is not None else None), (None if v is not None else '九重未返回总分')


def _score_multi(code, name, bars, quote, ctx, base_dir):
    """多因子评分：numpy+requests 已装后真跑；市场数据用引擎自带静态实现（不联网）。"""
    mod = _load('strategy/multi_factor_scoring.py', 'qm_multi')
    if mod is None:
        return None, 'multi_factor 文件缺失'
    k = _bars_to_dicts(bars)
    if len(k) < 20:
        return None, 'K线不足20根'
    sc = mod.MultiFactorScorer()
    r = sc.score({'code': str(code), 'close': k[-1]['close'], 'volume': k[-1]['volume']},
                 k, {'code': str(code), 'name': name or ''}, [], None)
    v = _num(r.get('total_score'))
    return (round(v, 2) if v is not None else None), (None if v is not None else '多因子未返回总分')


def _unavailable(reason):
    def _f(*a, **k):
        return None, reason
    return _f


_ADAPTERS = {
    'factor_engine': _score_factor_engine,
    'ai_520': _score_ai_520,
    'nine_score': _score_nine,
    'multi_factor': _score_multi,
    'factor_score': _unavailable('依赖 data.duckdb_adapter（本地 DuckDB 库）'),
    'main_force': _unavailable('桌面端独有（jq/tdx 行情源），云端永久摊空'),
}


def score_all(code, name='', bars=None, quote=None, ctx=None,
              auction_score=None, base_dir=None):
    """返回 {'scores':{engine:分/None}, 'reasons':{engine:原因}, 'agg':聚合结果, 'line':卡片一行}"""
    bd = base_dir or _ROOT
    scores, reasons = {}, {}
    for key, fn in _ADAPTERS.items():
        try:
            v, why = fn(code, name, bars, quote, ctx, bd)
            scores[key] = v
            if why:
                reasons[key] = why
        except Exception as e:
            scores[key] = None
            reasons[key] = '异常: %s' % str(e)[:60]
    # 竞价评分来自调用方（竞价卡自带 v3 分），不在这里重算
    scores['auction_v3'] = _num(auction_score)
    if scores['auction_v3'] is None:
        reasons['auction_v3'] = '非竞价场景/未传入'
    # ai_composite 只吃其它引擎的子分，缺子分就不算
    scores['ai_composite'] = None
    reasons['ai_composite'] = '需要 main_force/nine/六维 三个子分，当前不可得'

    try:
        from strategy.score_aggregator import aggregate, fmt_final
    except Exception:
        import importlib.util as _iu
        _p = os.path.join(_ROOT, 'strategy', 'score_aggregator.py')
        _s = _iu.spec_from_file_location('qm_agg', _p)
        _m = _iu.module_from_spec(_s)
        _s.loader.exec_module(_m)
        aggregate, fmt_final = _m.aggregate, _m.fmt_final
    agg = aggregate(scores, base_dir=bd)
    return {'scores': scores, 'reasons': reasons, 'agg': agg, 'line': fmt_final(agg)}
