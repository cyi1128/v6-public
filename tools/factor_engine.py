# -*- coding: utf-8 -*-
"""
factor_engine.py —— 云端因子引擎

阶段：第 1 步（只做 情绪分 jq + 量价分 lj）
后续：第 2 步硬闸否决生效、第 3 步补齐资金/题材/动量并两分合成

设计原则（写死，不许绕过）：
1. 纯函数，不自己做网络请求；K线/快照由调用方传入，避免重复拉数。
2. 每个子项返回 (得分, 明细)；数据缺失时该项按"满分 50%"中性计分，并在明细里标 '缺'。
   禁止用默认值冒充真实数据。
3. 任何异常都不许抛出到调用方，最差返回"全缺 + 中性分"。

K线行格式（与 tools/cloud_daily_review.py 的 get_klines 一致）：
    [日期, 开盘, 收盘, 最高, 最低, 成交量]
"""

from __future__ import annotations

# ============ 权重（短线口径；第3步补齐 资金/题材/动量 后整体归一）============
WEIGHTS_SHORT = {
    'jq': 0.30,   # 情绪
    'lj': 0.30,   # 量价
    'zj': 0.20,   # 资金
    'tc': 0.10,   # 题材
    'dl': 0.10,   # 动量
}
WEIGHTS_SWING = {
    'jm': 0.25,   # 基本面（波段）
    'lj': 0.25,
    'dl': 0.20,
    'tc': 0.15,
    'zj': 0.15,
}

# 中性兜底比例：数据缺失时按该项满分的 50% 计
NEUTRAL_RATIO = 0.5

# 硬闸阈值（第2步启用）
VETO_RULES = {
    'min_list_days': 60,        # 上市不足 60 天
    'max_lbc': 6,               # 连板 >= 6
    'min_float_cap_yi': 25,     # 流通市值 < 25 亿
    'max_float_cap_yi': 400,    # 流通市值 > 400 亿
    'max_turnover_pct': 45,     # 换手 > 45%
}


def _f(x, default=None):
    """安全转 float，失败返回 default。"""
    try:
        if x is None or x == '' or x == '-' or x == '--':
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _grade(value, tiers, default_neutral_max):
    """
    tiers: [(下界, 得分), ...] 按上界升序排列的阈值表，用 (阈值, 分) 表示
    这里改用显式区间判断，避免区间写错。
    """
    raise NotImplementedError  # 不使用，保留说明


NEUTRAL = '中性'


def _band_score(value, bands):
    """bands = [(lo, hi, score), ...]，hi 用 None 表示无穷。value 落在 [lo, hi) 内。"""
    if value is None:
        return None
    for lo, hi, sc in bands:
        if value >= lo and (hi is None or value < hi):
            return sc
    return bands[-1][2]


# ============ ① 情绪分 jq（0-100）============
def score_emotion(lu=None, zb=None, max_lbc=None, yest_premium_pct=None):
    """
    情绪分 = 涨停家数25 + 炸板率25 + 昨涨停溢价25 + 连板高度25
    任一子项数据缺失 → 该项按 12.5（=25*50%）计，并标 '缺'。
    返回 {'score': float, 'parts': {name: {'raw':…, 'score':…, 'state':'ok|缺'}}, 'missing': [...]}
    """
    parts = {}
    missing = []

    # 1) 涨停家数
    lu_i = None
    try:
        if lu is not None:
            lu_i = int(lu)
    except (TypeError, ValueError):
        lu_i = None
    if lu_i is None:
        parts['涨停家数'] = {'raw': None, 'score': 25 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('涨停家数')
    else:
        sc = _band_score(lu_i, [(80, None, 25), (60, 80, 20), (40, 60, 15), (20, 40, 10), (0, 20, 5)])
        parts['涨停家数'] = {'raw': lu_i, 'score': sc, 'state': 'ok'}

    # 2) 炸板率
    zbr = None
    lu_f, zb_f = _f(lu), _f(zb)
    if lu_f is not None and zb_f is not None and (lu_f + zb_f) > 0:
        zbr = zb_f / (lu_f + zb_f)
    if zbr is None:
        parts['炸板率'] = {'raw': None, 'score': 25 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('炸板率')
    else:
        sc = _band_score(zbr * 100, [
            (0, 20.0001, 25), (20.0001, 30.0001, 18), (30.0001, 40.0001, 12),
            (40.0001, 50.0001, 6), (50.0001, None, 0),
        ])
        parts['炸板率'] = {'raw': round(zbr * 100, 1), 'score': sc, 'state': 'ok'}

    # 3) 昨涨停溢价（昨日涨停股今日均涨幅，单位 %）
    yp = _f(yest_premium_pct)
    if yp is None:
        parts['昨涨停溢价'] = {'raw': None, 'score': 25 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('昨涨停溢价')
    else:
        sc = _band_score(yp, [(3.0, None, 25), (1.0, 3.0, 18), (0.0, 1.0, 10), (None, 0.0, 0)]) \
            if yp >= 0 else 0
        parts['昨涨停溢价'] = {'raw': round(yp, 2), 'score': sc, 'state': 'ok'}

    # 4) 连板高度
    lb = None
    try:
        if max_lbc is not None:
            lb = int(max_lbc)
    except (TypeError, ValueError):
        lb = None
    if lb is None:
        parts['连板高度'] = {'raw': None, 'score': 25 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('连板高度')
    else:
        sc = _band_score(lb, [(5, None, 25), (4, 5, 20), (3, 4, 15), (2, 3, 10), (0, 2, 5)])
        parts['连板高度'] = {'raw': lb, 'score': sc, 'state': 'ok'}

    total = sum(p['score'] for p in parts.values())
    return {'score': round(total, 1), 'parts': parts, 'missing': missing}


# ============ ② 量价分 lj（0-100）============
def _ma(closes, n):
    if closes is None or len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _corr(xs, ys):
    """皮尔逊相关系数；样本不足或方差为 0 返回 None。"""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return sxy / ((sxx ** 0.5) * (syy ** 0.5))


def score_price_volume(bars=None, lb=None, mom_window=20, vol_win=30,
                       vol_today=None, vol_avg5=None):
    """
    量价分 = 量比30 + MOM20 25 + 乖离结构25 + 量价配合20
    bars: [[date, open, close, high, low, volume], ...]，按日期升序（最后一根为最新）
    lb:   量比（腾讯 f43）。实测涨停封板时腾讯会返回 0.00，此时不可信。
    vol_today / vol_avg5: 当日实时成交量 与 前5日日均量；lb 不可信时用它们自算量比。
    """
    parts = {}
    missing = []

    # 清洗 bars
    cl = []
    vo = []
    if bars:
        for r in bars:
            if not r or len(r) < 6:
                continue
            c = _f(r[2])
            v = _f(r[5])
            if c is None or c <= 0:
                continue
            cl.append(c)
            vo.append(v if v is not None and v > 0 else None)

    # 1) 量比（腾讯 f43 优先；涨停封板时 f43 返回 0，改用 当日量/5日均量 自算）
    lb_f = _f(lb)
    src = 'qt_f43'
    if lb_f is None or lb_f <= 0:
        vt, va = _f(vol_today), _f(vol_avg5)
        if vt is not None and va is not None and va > 0 and vt > 0:
            lb_f, src = vt / va, '自算'
        else:
            lb_f, src = None, None
    if lb_f is None:
        parts['量比'] = {'raw': None, 'score': 30 * NEUTRAL_RATIO, 'state': '缺', 'src': None}
        missing.append('量比')
    else:
        sc = _band_score(lb_f, [(3, None, 30), (2, 3, 24), (1.5, 2, 18), (1, 1.5, 10), (0, 1, 4)])
        parts['量比'] = {'raw': round(lb_f, 2), 'score': sc, 'state': 'ok', 'src': src}

    # 2) 20日动量
    mom = None
    if len(cl) >= mom_window + 1:
        base = cl[-(mom_window + 1)]
        if base > 0:
            mom = (cl[-1] / base - 1) * 100
    if mom is None:
        parts['MOM20'] = {'raw': None, 'score': 25 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('MOM20')
    else:
        if mom > 30:
            sc = 15          # 涨过头，降档（规格原文）
        else:
            sc = _band_score(mom, [(15, None, 25), (8, 15, 20), (0, 8, 12), (None, 0, 0)]) \
                if mom >= 0 else 0
        parts['MOM20'] = {'raw': round(mom, 2), 'score': sc, 'state': 'ok'}

    # 3) 乖离结构
    ma5 = _ma(cl, 5)
    ma10 = _ma(cl, 10)
    if ma5 is None or ma10 is None:
        parts['乖离结构'] = {'raw': None, 'score': 25 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('乖离结构')
    else:
        cur = cl[-1]
        if cur >= ma5 and ma5 > ma10:
            sc, state = 25, 'ok'
        elif cur >= ma5:
            sc, state = 15, 'ok'
        else:
            sc, state = 5, 'ok'
        parts['乖离结构'] = {
            'raw': {'cur': round(cur, 2), 'ma5': round(ma5, 2), 'ma10': round(ma10, 2)},
            'score': sc, 'state': state,
        }

    # 4) 量价配合：日涨跌幅 与 成交量 的相关系数（涨放量+跌缩量 → 正相关）
    rets, vols = None, None
    if len(cl) >= 6:
        n = min(vol_win, len(cl) - 1)
        seg_c = cl[-(n + 1):]
        seg_v = vo[-(n + 1):]
        rets = [seg_c[i + 1] / seg_c[i] - 1 for i in range(n) if seg_c[i] > 0]
        vols = [seg_v[i + 1] if seg_v[i + 1] is not None else 0.0 for i in range(n)]
    corr = _corr(rets, vols) if rets and vols and len(rets) == len(vols) else None
    if corr is None:
        parts['量价配合'] = {'raw': None, 'score': 20 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('量价配合')
    else:
        sc = 20 if corr > 0.3 else 8
        parts['量价配合'] = {'raw': round(corr, 3), 'score': sc, 'state': 'ok'}

    total = sum(p['score'] for p in parts.values())
    return {'score': round(total, 1), 'parts': parts, 'missing': missing, 'bars_n': len(cl)}


# ============ ③ 资金分 zj（短线权重 20%）============
def score_fund(out_vol=None, in_vol=None, bars=None, is_limit_up=False, lhb_net_buy=None):
    """
    资金分 = 内外盘差35 + 3日上涨日量占比30 + 龙虎榜机构净买35

    【实测红线】涨停封板时腾讯快照 f[7]外盘会归零、f[8]内盘吞掉全部成交量。
    10 只样本实测：涨停票 (外-内)/总量 恒为 -0.33 ~ -1.00，非涨停正常票全在 ±0.15 内。
    若直接按 "差<-0.05→5分" 打分，所有涨停票会被系统性错杀 → 涨停时该项标「缺」按中性计。
    """
    parts, missing = {}, []

    # 1) 内外盘差 (外盘-内盘)/总量
    ov, iv = _f(out_vol), _f(in_vol)
    if is_limit_up:
        parts['内外盘差'] = {'raw': None, 'score': 35 * NEUTRAL_RATIO, 'state': '缺',
                            'note': '涨停封板外盘归零，失真不计'}
        missing.append('内外盘差(涨停失真)')
    elif ov is None or iv is None or (ov + iv) <= 0:
        parts['内外盘差'] = {'raw': None, 'score': 35 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('内外盘差')
    else:
        diff = (ov - iv) / (ov + iv)
        sc = _band_score(diff, [(0.15, None, 35), (0.05, 0.15, 25),
                                (-0.05, 0.05, 15), (-99, -0.05, 5)])
        parts['内外盘差'] = {'raw': round(diff, 3), 'score': sc, 'state': 'ok'}

    # 2) 最近3日上涨日成交量占比（主力净流入接口不稳时的替代）
    ratio, tot = None, 0.0
    try:
        if bars and len(bars) >= 4:
            seg = bars[-4:]
            ups = 0.0
            for i in range(len(seg) - 1):
                p0, p1 = float(seg[i][2]), float(seg[i + 1][2])
                v1 = float(seg[i + 1][5])
                tot += v1
                if p0 > 0 and p1 > p0:
                    ups += v1
            ratio = (ups / tot) if tot > 0 else None
    except (TypeError, ValueError, IndexError):
        ratio = None
    if ratio is None:
        parts['3日上涨日量占比'] = {'raw': None, 'score': 30 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('3日上涨日量占比')
    else:
        sc = 30 if ratio > 0.6 else (15 if ratio > 0.4 else 8)
        parts['3日上涨日量占比'] = {'raw': round(ratio, 3), 'score': sc, 'state': 'ok'}

    # 3) 龙虎榜机构净买（当日盘中拿不到，标缺不硬编）
    lb = _f(lhb_net_buy)
    if lb is None:
        parts['龙虎榜机构净买'] = {'raw': None, 'score': 35 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('龙虎榜机构净买')
    else:
        parts['龙虎榜机构净买'] = {'raw': lb, 'score': 35 if lb > 0 else 0, 'state': 'ok'}

    total = sum(p['score'] for p in parts.values())
    return {'score': round(total, 1), 'parts': parts, 'missing': missing}


# ============ ⑥ 动量分 dl ============
def score_momentum(bars=None):
    """动量分 = 5日动量30 + 20日动量30 + 创20日新高20 + 站稳MA20 20"""
    parts, missing = {}, []
    cl, hi = [], []
    try:
        for r in (bars or []):
            cl.append(float(r[2]))
            hi.append(float(r[3]))
    except (TypeError, ValueError, IndexError):
        cl, hi = [], []

    for label, win in (('5日动量', 5), ('20日动量', 20)):
        v = None
        if len(cl) >= win + 1 and cl[-win - 1] > 0:
            v = (cl[-1] / cl[-win - 1] - 1) * 100
        if v is None:
            parts[label] = {'raw': None, 'score': 30 * NEUTRAL_RATIO, 'state': '缺'}
            missing.append(label)
        else:
            sc = _band_score(v, [(15, None, 30), (8, 15, 24), (0, 8, 15), (-99, 0, 5)])
            parts[label] = {'raw': round(v, 2), 'score': sc, 'state': 'ok'}

    newhigh = None
    if len(cl) >= 21 and len(hi) >= 21:
        try:
            prev_hi = max(hi[-21:-1])
            newhigh = cl[-1] >= prev_hi if prev_hi > 0 else None
        except (TypeError, ValueError):
            newhigh = None
    if newhigh is None:
        parts['创20日新高'] = {'raw': None, 'score': 20 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('创20日新高')
    else:
        parts['创20日新高'] = {'raw': bool(newhigh), 'score': 20 if newhigh else 6, 'state': 'ok'}

    ma20 = _ma(cl, 20)
    above = None
    if ma20 is not None and ma20 > 0:
        above = cl[-1] > ma20
    if above is None:
        parts['站稳MA20'] = {'raw': None, 'score': 20 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('站稳MA20')
    else:
        parts['站稳MA20'] = {'raw': {'cur': round(cl[-1], 2), 'ma20': round(ma20, 2)},
                            'score': 20 if above else 5, 'state': 'ok'}

    total = sum(p['score'] for p in parts.values())
    return {'score': round(total, 1), 'parts': parts, 'missing': missing}


# ============ ⑤ 题材分 tc ============
_REL_K = {'实受益': 1.0, '沾边': 0.6, '纯蹭': 0.2}


def score_theme(theme_heat=None, relation='实受益'):
    """题材分：板块热度（_theme_heat 的 0-100）直接映射，再按个股与最强板块关系系数缩放。
    关系系数：实受益×1.0 / 沾边×0.6 / 纯蹭×0.2（用户锁定规格）。"""
    h = _f(theme_heat)
    k = _REL_K.get(relation, 0.6)
    if h is None:
        return {'score': 50.0,
                'parts': {'题材热度': {'raw': None, 'score': 50.0, 'state': '缺'}},
                'missing': ['题材热度']}
    sc = max(0.0, min(100.0, h * k))
    return {'score': round(sc, 1),
            'parts': {'题材热度': {'raw': {'heat': round(h, 1), 'rel': relation, 'k': k},
                                'score': round(sc, 1), 'state': 'ok'}},
            'missing': []}


# ============ ④ 基本面分 jm（波段权重 25%）============
def score_fundamental(pe_ttm=None, profit_yoy_pct=None, float_cap_yi=None, is_loss=False):
    """基本面分 = PE_TTM30 + 季报净利同比35 + 流通市值35（甜区 30-150 亿）"""
    parts, missing = {}, []

    pe = _f(pe_ttm)
    if is_loss:
        parts['PE_TTM'] = {'raw': '亏损', 'score': 5, 'state': 'ok'}
    elif pe is None or pe <= 0:
        parts['PE_TTM'] = {'raw': None, 'score': 30 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('PE_TTM')
    else:
        sc = _band_score(pe, [(30, 60, 20), (0, 30, 30), (60, None, 10)])
        parts['PE_TTM'] = {'raw': round(pe, 2), 'score': sc, 'state': 'ok'}

    yoy = _f(profit_yoy_pct)
    if yoy is None:
        parts['季报净利同比'] = {'raw': None, 'score': 35 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('季报净利同比')
    else:
        sc = _band_score(yoy, [(50, None, 35), (20, 50, 28), (0, 20, 18), (-99, 0, 5)])
        parts['季报净利同比'] = {'raw': round(yoy, 2), 'score': sc, 'state': 'ok'}

    cap = _f(float_cap_yi)
    if cap is None:
        parts['流通市值'] = {'raw': None, 'score': 35 * NEUTRAL_RATIO, 'state': '缺'}
        missing.append('流通市值')
    else:
        sc = _band_score(cap, [(30, 150, 35), (150, 300, 25), (0, 30, 15), (300, None, 20)])
        parts['流通市值'] = {'raw': round(cap, 2), 'score': sc, 'state': 'ok'}

    total = sum(p['score'] for p in parts.values())
    return {'score': round(total, 1), 'parts': parts, 'missing': missing}


# ============ ③ 硬闸（第2步启用，这里先给出判定函数）============
def veto_check(name=None, code=None, float_cap_yi=None, lbc=None,
               turnover_pct=None, list_days=None, bars=None, price=None):
    """
    返回 {'vetoed': bool, 'reasons': [str]}
    规则：ST/退市、上市<60天、连板>=6、放量破MA20、流通<25亿或>400亿、换手>45%
    数据缺失时该条不触发否决（不因缺数据误杀），并记录到 'unknown'。
    """
    reasons = []
    unknown = []

    nm = (name or '') + ''
    if nm and (('ST' in nm) or ('退' in nm)):
        reasons.append('ST/退市风险')

    if list_days is None and bars is not None and len(bars) >= 60:
        list_days = len(bars)   # 拉到 130 根仍剩 ≥60 根 → 上市已满 60 个交易日
    if list_days is None:
        unknown.append('上市天数')
    elif list_days < VETO_RULES['min_list_days']:
        reasons.append('上市不足%d天' % VETO_RULES['min_list_days'])

    if lbc is None:
        unknown.append('连板数')
    elif lbc >= VETO_RULES['max_lbc']:
        reasons.append('连板%d板(≥%d)' % (lbc, VETO_RULES['max_lbc']))

    cap = _f(float_cap_yi)
    if cap is None:
        unknown.append('流通市值')
    elif cap < VETO_RULES['min_float_cap_yi']:
        reasons.append('流通%.0f亿<25亿' % cap)
    elif cap > VETO_RULES['max_float_cap_yi']:
        reasons.append('流通%.0f亿>400亿' % cap)

    to = _f(turnover_pct)
    if to is None:
        unknown.append('换手率')
    elif to > VETO_RULES['max_turnover_pct']:
        reasons.append('换手%.1f%%>45%%' % to)

    # 放量破 MA20：收盘跌破 MA20 且成交量 > 5日均量
    blown = None
    cl, vo = [], []
    if bars:
        for r in bars:
            if r and len(r) >= 6:
                c = _f(r[2]); v = _f(r[5])
                if c and c > 0:
                    cl.append(c); vo.append(v if v else 0.0)
    cur = _f(price) or (cl[-1] if cl else None)
    ma20 = _ma(cl, 20)
    avg5 = (sum(vo[-5:]) / 5) if len(vo) >= 5 else None
    lastv = vo[-1] if vo else None
    if cur is not None and ma20 is not None and avg5 and lastv:
        blown = (cur < ma20) and (lastv > avg5)
    if blown is None:
        unknown.append('放量破MA20')
    elif blown:
        reasons.append('放量跌破MA20')

    return {'vetoed': bool(reasons), 'reasons': reasons, 'unknown': unknown}


# ============ ④ 合成（第3步补齐 zj/tc/dl 后启用）============
def combine(auction_score=None, factor_scores=None, weights=None):
    """
    auction_score: 竞价评分_v3 分数
    factor_scores: {'jq':…,'lj':…,'zj':…,'tc':…,'dl':…}
    weights:       默认 WEIGHTS_SHORT
    返回 {'factor_total':…, 'combined':…, 'used':[...], 'missing':[...]}
    只对已提供的因子归一权重（缺失项不参与分母），避免缺数据把总分拉低。
    """
    w = dict(weights or WEIGHTS_SHORT)
    fs = dict(factor_scores or {})
    used, miss = [], []
    num, den = 0.0, 0.0
    for k, weight in w.items():
        v = _f(fs.get(k))
        if v is None:
            miss.append(k)
            continue
        num += v * weight
        den += weight
        used.append(k)
    factor_total = (num / den) if den > 0 else None
    a = _f(auction_score)
    if factor_total is not None and a is not None:
        combined = a * 0.5 + factor_total * 0.5
    else:
        combined = None
    return {
        'factor_total': round(factor_total, 1) if factor_total is not None else None,
        'combined': round(combined, 1) if combined is not None else None,
        'used': used,
        'missing': miss,
    }


def fmt_short_line(jq=None, lj=None, zj=None, tc=None, total=None, veto=None):
    """推送卡用的因子摘要（规格：情绪85/量价68/资金55/题材80）。"""
    segs = []
    if jq is not None:
        segs.append('情绪%.0f' % jq)
    if lj is not None:
        segs.append('量价%.0f' % lj)
    if zj is not None:
        segs.append('资金%.0f' % zj)
    if tc is not None:
        segs.append('题材%.0f' % tc)
    tail = ''
    if total is not None:
        tail = '｜综合%.0f' % total
    if veto:
        tail += '｜⛔%s' % '、'.join(veto)
    return '/'.join(segs) + tail


def fmt_full_line(auction_score=None, jq=None, lj=None, zj=None, tc=None, dl=None,
                  factor_total=None, combined=None, veto=None,
                  final=None, final_subs=None):
    """用户锁定规格的完整卡格式：
        竞价分67 | 因子分72(情绪85/量价68/资金55/题材80) | 综合69
        veto 非空时追加：| ⛔已否决：原因
    缺项自动省略，不会出现空括号。

    工单1（2026-11-06）：卡顶部唯一最终分 final（评分仲裁层合成），
    此时不再输出旧的「综合XX」，避免多个总分各说各话。
    """
    inner = []
    for label, v in (('情绪', jq), ('量价', lj), ('资金', zj), ('题材', tc), ('动量', dl)):
        if v is not None:
            inner.append('%s%.0f' % (label, v))
    segs = []
    fn = _f(final)
    if fn is not None:
        segs.append('综合分%.1f%s' % (fn, ('（%s）' % final_subs) if final_subs else ''))
    a = _f(auction_score)
    if a is not None:
        segs.append('竞价分%.0f' % a)
    ft = _f(factor_total)
    if ft is not None:
        if inner:
            segs.append('因子分%.0f(%s)' % (ft, '/'.join(inner)))
        else:
            segs.append('因子分%.0f' % ft)
    cb = _f(combined)
    if cb is not None and fn is None:
        segs.append('综合%.0f' % cb)
    line = ' | '.join(segs)
    if veto:
        tail = ' | ⛔已否决：%s' % '、'.join(veto)
        line = (line + tail) if line else tail.lstrip(' | ')
    return line


# ============ 自检（不联网，纯函数）============
def _selftest():
    fails = []

    def ck(name, cond, got=''):
        if not cond:
            fails.append('%s  got=%s' % (name, got))

    # 情绪：全指标健康
    e = score_emotion(lu=85, zb=15, max_lbc=5, yest_premium_pct=3.5)
    ck('emotion_strong', abs(e['score'] - 100) < 1e-6, e['score'])
    ck('emotion_no_missing', e['missing'] == [], e['missing'])

    # 情绪：退潮
    e2 = score_emotion(lu=15, zb=60, max_lbc=1, yest_premium_pct=-2)
    ck('emotion_weak', abs(e2['score'] - 10) < 1e-6, e2['score'])

    # 情绪：全缺 → 50
    e3 = score_emotion()
    ck('emotion_all_missing_50', abs(e3['score'] - 50) < 1e-6, e3['score'])
    ck('emotion_missing_len4', len(e3['missing']) == 4, e3['missing'])

    # 量价：造 30 根稳步上涨 + 放量的 K 线
    bars_up = []
    p = 10.0
    for i in range(30):
        # 涨跌交替且整体上行；涨日放量、跌日缩量；最后 6 日连涨（保证站上 MA5/MA10）
        up = (i % 3 != 2) or (i >= 24)
        p *= (1.012 if up else 0.985)
        vol = (120000 + i * 3000) if up else (90000 + i * 500)
        bars_up.append(['2026-01-%02d' % (i + 1), p * 0.99, p, p * 1.01, p * 0.98, vol])
    pv = score_price_volume(bars_up, lb=3.2)
    ck('pv_lb30', pv['parts']['量比']['score'] == 30, pv['parts']['量比'])
    ck('pv_mom_positive', pv['parts']['MOM20']['score'] in (25, 20, 12, 15), pv['parts']['MOM20'])
    ck('pv_ma_strong', pv['parts']['乖离结构']['score'] == 25, pv['parts']['乖离结构'])
    ck('pv_no_missing', pv['missing'] == [], pv['missing'])
    ck('pv_total_high', pv['score'] >= 75, pv['score'])

    # 量价：全缺 → 47.5（30/25/25/20 各半）
    pv0 = score_price_volume(None, None)
    ck('pv_all_missing', abs(pv0['score'] - 50.0) < 1e-6, pv0['score'])
    ck('pv_all_missing_is_neutral', pv0['score'] == 50.0, pv0['score'])

    # 量价：涨过头 MOM>30 → 降为 15
    bars_hot = [['d', 1, 10.0 + i * 1.2, 1, 1, 1000] for i in range(25)]
    pv2 = score_price_volume(bars_hot, lb=1.2)
    ck('pv_mom_overheat', pv2['parts']['MOM20']['score'] == 15, pv2['parts']['MOM20'])

    # 量价：破 MA5
    bars_dn = [['d', 1, 20.0 - i * 0.5, 1, 1, 1000] for i in range(25)]
    pv3 = score_price_volume(bars_dn, lb=0.8)
    ck('pv_break_ma5', pv3['parts']['乖离结构']['score'] == 5, pv3['parts']['乖离结构'])
    ck('pv_lb_low', pv3['parts']['量比']['score'] == 4, pv3['parts']['量比'])

    # 硬闸
    v = veto_check(name='*ST某某', float_cap_yi=50, lbc=2, turnover_pct=10, list_days=300)
    ck('veto_st', v['vetoed'] and 'ST/退市风险' in v['reasons'], v)
    v2 = veto_check(name='正常', float_cap_yi=20, lbc=2, turnover_pct=10, list_days=300)
    ck('veto_cap_small', v2['vetoed'] and any('25亿' in r for r in v2['reasons']), v2)
    v3 = veto_check(name='正常', float_cap_yi=450, lbc=2, turnover_pct=10, list_days=300)
    ck('veto_cap_big', v3['vetoed'] and any('400亿' in r for r in v3['reasons']), v3)
    v4 = veto_check(name='正常', float_cap_yi=80, lbc=6, turnover_pct=10, list_days=300)
    ck('veto_lbc6', v4['vetoed'], v4)
    v5 = veto_check(name='正常', float_cap_yi=80, lbc=3, turnover_pct=50, list_days=300)
    ck('veto_turnover', v5['vetoed'] and any('换手' in r for r in v5['reasons']), v5)
    v6 = veto_check(name='正常')
    ck('veto_unknown_no_kill', (not v6['vetoed']) and len(v6['unknown']) >= 3, v6)

    # 合成：只用已提供的因子归一
    c = combine(auction_score=67, factor_scores={'jq': 85, 'lj': 68}, weights={'jq': 0.3, 'lj': 0.3, 'zj': 0.2, 'tc': 0.1, 'dl': 0.1})
    ck('combine_partial', abs(c['factor_total'] - 76.5) < 1e-6, c['factor_total'])
    ck('combine_score', abs(c['combined'] - 71.8) < 1e-6, c['combined'])

    # ============ 资金分 zj ============
    # 全缺 → 17.5 + 15 + 17.5 = 50.0
    f0 = score_fund()
    ck('fund_all_missing_50', abs(f0['score'] - 50.0) < 1e-6, f0['score'])

    # 涨停失真防线：外盘=0、内盘吞掉全部量，内外盘项必须标缺按中性，不许打成 5 分
    f_lu = score_fund(out_vol=0, in_vol=15644, is_limit_up=True)
    ck('fund_limitup_neutral', abs(f_lu['score'] - 50.0) < 1e-6, f_lu['score'])
    ck('fund_limitup_state_missing',
       f_lu['parts']['内外盘差']['state'] == '缺', f_lu['parts']['内外盘差'])
    # 同样的数据若误判为非涨停，就会掉到 5 分 —— 证明 is_limit_up 这道防线确实必要
    f_lu_bad = score_fund(out_vol=0, in_vol=15644, is_limit_up=False)
    ck('fund_limitup_without_guard_drops',
       f_lu_bad['parts']['内外盘差']['score'] == 5, f_lu_bad['parts']['内外盘差'])

    # 强资金：差 0.4→35 + 三日全是涨日→30 + 龙虎榜净买→35 = 100
    bars_f_up = [['d0', 1, 10, 10, 10, 100], ['d1', 1, 11, 11, 11, 3000],
                 ['d2', 1, 11.5, 11.5, 11.5, 100], ['d3', 1, 12, 12, 12, 3000]]
    f_strong = score_fund(out_vol=700, in_vol=300, bars=bars_f_up,
                          is_limit_up=False, lhb_net_buy=1.5)
    ck('fund_strong_100', abs(f_strong['score'] - 100) < 1e-6, f_strong['score'])

    # 弱资金：差 -0.8→5 + 三日无涨日→8 + 龙虎榜缺→17.5 = 30.5
    bars_f_dn = [['d0', 1, 12, 12, 12, 3000], ['d1', 1, 11, 11, 11, 100],
                 ['d2', 1, 10.5, 10.5, 10.5, 100], ['d3', 1, 10, 10, 10, 100]]
    f_weak = score_fund(out_vol=100, in_vol=900, bars=bars_f_dn)
    ck('fund_weak_30_5', abs(f_weak['score'] - 30.5) < 1e-6, f_weak['score'])

    # ============ 动量分 dl ============
    # 全缺 → 15 + 15 + 10 + 10 = 50.0
    m0 = score_momentum()
    ck('mom_all_missing_50', abs(m0['score'] - 50.0) < 1e-6, m0['score'])

    # 25 根每天 +2%：5日动量 10.4%→24、20日 48.6%→30、新高→20、站稳MA20→20 = 94
    bars_m = []
    mp = 10.0
    for i in range(25):
        if i > 0:
            mp *= 1.02
        bars_m.append(['d%d' % i, mp, mp, mp, mp, 1000])
    m_strong = score_momentum(bars_m)
    ck('mom_5d_24', m_strong['parts']['5日动量']['score'] == 24, m_strong['parts']['5日动量'])
    ck('mom_20d_30', m_strong['parts']['20日动量']['score'] == 30, m_strong['parts']['20日动量'])
    ck('mom_newhigh_20', m_strong['parts']['创20日新高']['score'] == 20, m_strong['parts']['创20日新高'])
    ck('mom_ma20_20', m_strong['parts']['站稳MA20']['score'] == 20, m_strong['parts']['站稳MA20'])
    ck('mom_strong_94', abs(m_strong['score'] - 94) < 1e-6, m_strong['score'])

    # 25 根每天 -2%：动量归零档、破 MA20
    bars_md = []
    mp2 = 10.0
    for i in range(25):
        if i > 0:
            mp2 *= 0.98
        bars_md.append(['d%d' % i, mp2, mp2, mp2, mp2, 1000])
    m_weak = score_momentum(bars_md)
    ck('mom_weak_5d_5', m_weak['parts']['5日动量']['score'] == 5, m_weak['parts']['5日动量'])
    ck('mom_weak_nohigh_6', m_weak['parts']['创20日新高']['score'] == 6, m_weak['parts']['创20日新高'])
    ck('mom_weak_below_ma20_5', m_weak['parts']['站稳MA20']['score'] == 5, m_weak['parts']['站稳MA20'])

    # ============ 题材分 tc ============
    t_full = score_theme(theme_heat=80, relation='实受益')
    ck('theme_full_80', abs(t_full['score'] - 80.0) < 1e-6, t_full['score'])
    t_near = score_theme(theme_heat=80, relation='沾边')
    ck('theme_near_48', abs(t_near['score'] - 48.0) < 1e-6, t_near['score'])
    t_fake = score_theme(theme_heat=80, relation='纯蹭')
    ck('theme_fake_16', abs(t_fake['score'] - 16.0) < 1e-6, t_fake['score'])
    t0 = score_theme()
    ck('theme_missing_50', abs(t0['score'] - 50.0) < 1e-6, t0['score'])

    # ============ 基本面分 jm ============
    # 全缺 → 15 + 17.5 + 17.5 = 50.0
    j0 = score_fundamental()
    ck('fund_jm_all_missing_50', abs(j0['score'] - 50.0) < 1e-6, j0['score'])
    # 优质：PE20→30 + 利润+60%→35 + 流通80亿→35 = 100
    j_best = score_fundamental(pe_ttm=20, profit_yoy_pct=60, float_cap_yi=80)
    ck('fund_jm_best_100', abs(j_best['score'] - 100) < 1e-6, j_best['score'])
    # 亏损：PE 5 + 利润+10%→18 + 流通500亿→20 = 43
    j_loss = score_fundamental(pe_ttm=None, profit_yoy_pct=10, float_cap_yi=500, is_loss=True)
    ck('fund_jm_loss_43', abs(j_loss['score'] - 43) < 1e-6, j_loss['score'])
    # 中性：PE45→20 + 利润+30%→28 + 流通200亿→25 = 73
    j_mid = score_fundamental(pe_ttm=45, profit_yoy_pct=30, float_cap_yi=200)
    ck('fund_jm_mid_73', abs(j_mid['score'] - 73) < 1e-6, j_mid['score'])

    # 完整卡格式（用户锁定规格原文）
    fl = fmt_full_line(auction_score=67, jq=85, lj=68, zj=55, tc=80,
                       factor_total=72, combined=69)
    ck('fmt_full_exact',
       fl == '竞价分67 | 因子分72(情绪85/量价68/资金55/题材80) | 综合69', fl)
    # 缺项不出现空括号
    fl2 = fmt_full_line(auction_score=67, jq=85, factor_total=85, combined=76)
    ck('fmt_full_partial', fl2 == '竞价分67 | 因子分85(情绪85) | 综合76', fl2)
    # 否决票必须带原因
    fl3 = fmt_full_line(auction_score=50, factor_total=40, combined=45,
                        veto=['流通市值 420.0亿超过 400亿上限'])
    ck('fmt_full_veto', fl3.endswith('⛔已否决：流通市值 420.0亿超过 400亿上限'), fl3)

    # 两分合成全量：竞价67 / 因子 85,68,55,80,60
    # 因子 = 25.5 + 20.4 + 11.0 + 8.0 + 6.0 = 70.9
    # 综合 = 67*0.5 + 70.9*0.5 = 68.95
    c_full = combine(auction_score=67,
                     factor_scores={'jq': 85, 'lj': 68, 'zj': 55, 'tc': 80, 'dl': 60},
                     weights=WEIGHTS_SHORT)
    ck('combine_full_factor_70_9', abs(c_full['factor_total'] - 70.9) < 1e-6, c_full['factor_total'])
    ck('combine_full_combined_68_95', abs(c_full['combined'] - 68.95) < 0.06, c_full['combined'])
    ck('combine_full_no_missing', c_full['missing'] == [], c_full['missing'])

    # 摘要行
    s = fmt_short_line(jq=85, lj=68, total=72)
    ck('fmt_line', s == '情绪85/量价68｜综合72', s)

    print('RESULT fail=%d' % len(fails))
    for f_ in fails:
        print('  FAIL %s' % f_)
    return len(fails)


if __name__ == '__main__':
    _selftest()
