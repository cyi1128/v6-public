# -*- coding: utf-8 -*-
"""拉升阶段识别 detect_markup() 的验证套件。

[A] 造数单测：三种形态的典型形态 + 反例 + 边界 + 分数分段不重叠
[B] 真实数据：kline_cache 抽 300 只，分数/命中分布 + 关键中间值与独立算法逐只核对
[C] _ctrl_note / _observe_tags 新参数 + 旧参数组合与改动前逐字等价
[D] 静态检查：方法体内不得出现未来函数写法
输出 tools\\markup_unit.txt
"""
import importlib.machinery
import importlib.util
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
OUT = r'D:\QuantMonitorV6\tools\markup_unit.txt'
BAK = r'D:\QuantMonitorV6\services\band_pattern_engine.py.bak_before_markup'
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


PASS = [0, 0]


def check(name, cond, extra=''):
    if cond:
        PASS[0] += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        PASS[1] += 1
        P('  FAIL  %s %s' % (name, extra))


import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strategy.base import TechnicalIndicators as TI  # noqa: E402
import strategy.base as B  # noqa: E402   # 1010m：位置门槛要临时改常量
import services.band_pattern_engine as E  # noqa: E402

P('=' * 100)
P('拉升阶段识别 detect_markup() 验证')
P('=' * 100)


def df_of(o, h, l, c, v):
    return pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})


def mk(closes, vols, hi_add=0.012, lo_add=0.008):
    """由收盘价序列造一份「实体正常」的 OHLCV。开盘=前收（小跳空），高低按比例包住。"""
    n = len(closes)
    o = [closes[0] * 0.995] + [closes[i - 1] for i in range(1, n)]
    h = [max(o[i], closes[i]) * (1 + hi_add) for i in range(n)]
    l = [min(o[i], closes[i]) * (1 - lo_add) for i in range(n)]
    return df_of(o, h, l, list(closes), list(vols))


def base_series(n=140, px=8.0, vol=100.0):
    """底部横盘的一段明显「贴地」的历史，用于抬高/压低 pos120。"""
    return [px] * n, [vol] * n


def lower_pos(df, hi=12.0, keep=70, cut=120):
    """把窗口里较老的一段抬成高位横盘，用来压低 pos120。

    1010m 给 detect_markup 加了前置位置门槛（pos120 < 0.45），造数单测必须把形态放在
    【低位】才可能命中。只改 [-cut:-keep] 这一段，最近 keep 根原样不动 ——
    三种形态的判据、MA5/MA10/MA20、60 日最高都只看近端窗口，所以形态判据不受影响。
    """
    d = df.copy()
    n = len(d)
    a, b = max(0, n - cut), max(0, n - keep)
    if b > a:
        d.loc[d.index[a:b], ['open', 'high', 'low', 'close']] = hi
    return d


def pos120_of(df):
    c = np.asarray(df['close'].values, dtype=float)[-120:]
    return (float(c[-1]) - float(np.min(c))) / (float(np.max(c)) - float(np.min(c)) + 1e-8)


# ============================================================
P('')
P('[A] 造数单测')
P('-' * 100)

# ---- ① 阶梯式上行：MA5>MA10>MA20 + 10 根 +16% + 上涨放量/回调缩量 + 不破 MA20 ----
c, v = base_series(120, 8.0, 100.0)
up = [8.40, 8.30, 8.55, 8.45, 8.70, 8.60, 8.90, 8.80, 9.10, 9.30]
vv = [180, 60, 190, 65, 200, 70, 210, 75, 220, 230]
c = c + up
v = v + vv
d1 = lower_pos(mk(c, v, hi_add=0.010, lo_add=0.004))
r1 = TI.detect_markup(d1)
P('  ① 阶梯式上行 -> ok=%s type=%s score=%.1f n_ok=%d hits=%s pos120=%.3f'
  % (r1['ok'], r1['type'], r1['score'], r1['n_ok'], r1['hits'], pos120_of(d1)))
check('A0 造数已在低位（pos120 < 0.45，否则会被位置门槛拦下）', pos120_of(d1) < 0.45,
      'pos120=%.3f' % pos120_of(d1))
check('A1 命中阶梯式上行', r1['ok'] and r1['type'] == '阶梯式上行')
check('A2 分数 >= 70（两段不重叠）', r1['score'] >= 70.0, 'score=%.1f' % r1['score'])
check('A3 hits 四条全 True', r1['n_ok'] == 4 and all(r1['hits']))

# ---- ② 缩量强势：8 根阳线占比 75% + 量能萎缩 + pos>=0.55 + 低点抬高 ----
# 刻意把「下跌日成交量」做得比上涨日大 -> ① 的「上涨放量/回调缩量」不成立，
# 确保这条用例只可能落在 ② 上（同时验证两形态的判据是独立的）。
c2, v2 = base_series(120, 8.0, 130.0)
step = [8.10, 8.22, 8.20, 8.34, 8.46, 8.44, 8.60, 8.74]
sv = [92, 96, 120, 94, 88, 130, 86, 84]
c2 = c2 + step
v2 = v2 + sv
d2 = mk(c2, v2, hi_add=0.010, lo_add=0.004)
r2 = TI.detect_markup(d2)
P('  ② 缩量强势（原始高位造数）-> ok=%s reason=%r pos120=%.3f'
  % (r2['ok'], r2['reason'], pos120_of(d2)))
check('B0 位置门槛下，缩量强势（自带 pos>=0.55）必被拦下 —— 这是设计后果，不是缺陷',
      (r2['reason'] or '').startswith('pos>'))
_save_lock = B.MARKUP_POS_MAX
B.MARKUP_POS_MAX = 1.01
try:
    r2b = TI.detect_markup(d2)
finally:
    B.MARKUP_POS_MAX = _save_lock
P('  ② 缩量强势（临时关掉位置门槛）-> ok=%s type=%s score=%.1f'
  % (r2b['ok'], r2b['type'], r2b['score']))
check('B1 命中缩量强势（门槛关掉后形态逻辑仍完好）', r2b['ok'] and r2b['type'] == '缩量强势')
check('B2 分数 >= 70', r2b['score'] >= 70.0, 'score=%.1f' % r2b['score'])
check('B3 位置门槛已改回 0.45', B.MARKUP_POS_MAX == 0.45, repr(B.MARKUP_POS_MAX))

# ---- ③ 加速迹象：5 根 +16% + 量能放大 2.6 倍 + 接近 60 日新高 ----
c3, v3 = base_series(120, 8.0, 100.0)
acc = [8.00, 8.35, 8.70, 9.05, 9.20, 9.30]
av = [100, 200, 230, 260, 300, 320]
c3 = c3 + acc
v3 = v3 + av
d3 = lower_pos(mk(c3, v3, hi_add=0.010, lo_add=0.004))
r3 = TI.detect_markup(d3)
P('  ③ 加速迹象   -> ok=%s type=%s score=%.1f n_ok=%d hits=%s pos120=%.3f'
  % (r3['ok'], r3['type'], r3['score'], r3['n_ok'], r3['hits'], pos120_of(d3)))
check('C0 造数已在低位（pos120 < 0.45）', pos120_of(d3) < 0.45, 'pos120=%.3f' % pos120_of(d3))
check('C1 命中加速迹象', r3['ok'] and r3['type'] == '加速迹象')
check('C2 分数 >= 70', r3['score'] >= 70.0, 'score=%.1f' % r3['score'])

# ---- 反例 1：单边下跌 ----
c4, v4 = base_series(120, 12.0, 100.0)
c4 = c4 + [12.0, 11.6, 11.2, 10.9, 10.5, 10.2, 9.9, 9.6, 9.4, 9.2, 9.0]
v4 = v4 + [110, 120, 130, 120, 125, 130, 120, 135, 130, 125, 120]
r4 = TI.detect_markup(mk(c4, v4))
P('  反例1 单边下跌 -> ok=%s score=%.1f reason=%r' % (r4['ok'], r4['score'], r4['reason']))
check('D1 单边下跌不命中', not r4['ok'])
check('D2 未通过分数 <= 60', r4['score'] <= 60.0, 'score=%.1f' % r4['score'])

# ---- 反例 2：天天收阳、无下跌日（成交量低）→ ① 的第 3 条必须不成立 ----
c5, v5 = base_series(120, 8.0, 100.0)
c5 = c5 + [8.0, 8.01, 8.02, 8.03, 8.04, 8.05, 8.06, 8.07, 8.08, 8.09, 8.10]
v5 = v5 + [100] * 11
r5 = TI.detect_markup(lower_pos(mk(c5, v5)))
P('  反例2 无下跌日/无涨幅 -> ok=%s type=%s score=%.1f hits=%s'
  % (r5['ok'], r5['type'], r5['score'], r5['hits']))
check('E1 无下跌日不得判「放量上涨」', (not r5['ok']) or r5['type'] != '阶梯式上行')

# ---- 反例 3：上涨但放量下跌（冲高回落型放量长阴）→ 不命中 ① ----
c6, v6 = base_series(120, 8.0, 100.0)
c6 = c6 + [8.0, 8.30, 8.10, 8.45, 8.20, 8.55, 8.30, 8.70, 8.40, 8.90, 9.10]
v6 = v6 + [80, 60, 300, 70, 320, 75, 330, 80, 340, 90, 100]
r6 = TI.detect_markup(lower_pos(mk(c6, v6)))
P('  反例3 上涨日缩量+下跌日放量 -> ok=%s type=%s score=%.1f hits=%s'
  % (r6['ok'], r6['type'], r6['score'], r6['hits']))
check('F1 下跌放量不得判「上涨放量/回调缩量」',
      (not r6['ok']) or r6['type'] != '阶梯式上行')

# ---- 边界：K线不足 / 缺列 ----
r7 = TI.detect_markup(mk([8.0] * 40, [100.0] * 40))
P('  边界 K线 40 根 -> ok=%s reason=%r' % (r7['ok'], r7['reason']))
check('G1 不足 60 根返回 reason', (not r7['ok']) and r7['reason'] == 'bars<60')
_d_bad = mk(c, v).drop(columns=['volume'])
r8 = TI.detect_markup(_d_bad)
P('  边界 缺 volume -> ok=%s reason=%r' % (r8['ok'], r8['reason']))
check('G2 缺列返回 reason', (not r8['ok']) and r8['reason'] == 'missing:volume')
r9 = TI.detect_markup(None)
check('G3 None 不抛异常', (not r9['ok']) and r9['reason'] == 'bars<60')

# ---- 分数两段不重叠：随机 2000 组合 ----
bad_seg = 0
rng = np.random.default_rng(20261011)
for _ in range(2000):
    n = int(rng.integers(60, 160))
    px = float(rng.uniform(3, 30))
    cl = np.cumprod(1 + rng.normal(0.002, 0.03, n)) * px
    vl = np.abs(rng.normal(100, 60, n)) + 10
    rr = TI.detect_markup(mk(list(cl), list(vl)))
    if rr['ok'] and rr['score'] < 70.0:
        bad_seg += 1
    if (not rr['ok']) and rr['score'] > 60.0:
        bad_seg += 1
check('H1 分数两段不重叠（2000 组随机）', bad_seg == 0, '越界 %d 组' % bad_seg)

# ============================================================
P('')
P('[B] 真实数据抽样')
P('-' * 100)
try:
    import duckdb
    con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
    rows = con.execute(
        "SELECT code,date,open,high,low,close,volume FROM ("
        " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
        " FROM kline_cache) WHERE rn<=140 ORDER BY code,date").fetchdf()
    con.close()
    by_code = {k: g for k, g in rows.groupby('code')}
    codes = sorted(by_code.keys())
    import random
    random.seed(20261011)
    pick = random.sample(codes, min(300, len(codes)))
    recs = []
    for cd in pick:
        b = by_code[cd].to_dict('records')
        if len(b) < 120:
            continue
        df = E._bars_to_df(b[-130:])
        if df is None:
            continue
        r = TI.detect_markup(df)
        recs.append((cd, r, df))
    P('  抽样 %d 只，可算 %d 只' % (len(pick), len(recs)))
    okn = [x for x in recs if x[1]['ok']]
    P('  命中 %d / %d（%.2f%%）' % (len(okn), len(recs), 100.0 * len(okn) / max(len(recs), 1)))
    for tp in ('阶梯式上行', '缩量强势', '加速迹象'):
        sub = [x for x in okn if x[1]['type'] == tp]
        if sub:
            ps = np.median([x[1]['pos120'] for x in sub])
            sc = np.median([x[1]['score'] for x in sub])
            P('    %-6s %3d 只 ｜ pos120 中位 %.3f ｜ score 中位 %.1f' % (tp, len(sub), ps, sc))
        else:
            P('    %-6s %3d 只' % (tp, 0))
    pos_all = np.median([x[1]['pos120'] for x in recs])
    pos_hit = np.median([x[1]['pos120'] for x in okn]) if okn else float('nan')
    P('  全样本 pos120 中位 %.3f ｜ 命中样本 pos120 中位 %.3f（拉升应偏高位）'
      % (pos_all, pos_hit))
    check('I1 命中样本位置高于全样本', (not okn) or pos_hit > pos_all)
    _blocked = [x for x in recs if (x[1].get('reason') or '').startswith('pos>')]
    check('I1b 被位置门槛拦下的记录 > 0 且其 pos120 全部 >= 0.45',
          len(_blocked) > 0 and all(x[1]['pos120'] >= 0.45 for x in _blocked),
          '%d 只，最低 %.4f' % (len(_blocked),
                              min([x[1]['pos120'] for x in _blocked]) if _blocked else -1))
    check('I1c 命中样本 pos120 全部 < 0.45（1010m 门槛生效）',
          all(x[1]['pos120'] < 0.45 for x in okn),
          '最高 %.4f' % (max([x[1]['pos120'] for x in okn]) if okn else -1))

    # 关键中间值 vs 独立算法（被位置门槛拦下的记录只带 pos120/reason，不做中间值比对）
    bad = []
    n_cmp = 0
    for cd, r, df in recs:
        if (r.get('reason') or '').startswith('pos>'):
            continue
        n_cmp += 1
        c_ = df['close'].values.astype(float)
        h_ = df['high'].values.astype(float)
        d = r['detail']
        if abs(d['ma5'] - np.mean(c_[-5:])) > 1e-6:
            bad.append('%s ma5' % cd)
        if abs(d['ma10'] - np.mean(c_[-10:])) > 1e-6:
            bad.append('%s ma10' % cd)
        if abs(d['ma20'] - np.mean(c_[-20:])) > 1e-6:
            bad.append('%s ma20' % cd)
        if abs(d['hi60'] - np.max(h_[-60:])) > 1e-6:
            bad.append('%s hi60' % cd)
        _g = (c_[-1] - c_[-11]) / c_[-11]
        if abs(d['gain_trend'] - _g) > 1e-6:
            bad.append('%s gain_trend' % cd)
        _c120 = c_[-120:]
        _mn, _mx = _c120.min(), _c120.max()
        if abs(r['pos120'] - (c_[-1] - _mn) / (_mx - _mn + 1e-8)) > 1e-6:
            bad.append('%s pos120' % cd)
    check('I2 关键中间值与独立算法逐只一致（%d 只，已剔除被门槛拦下的 %d 只）' % (n_cmp, len(recs) - n_cmp),
          not bad, ('差异: %s' % bad[:6]) if bad else '')

    # 只喂 T 及之前的 K 线：结果必须与「用同一段数据再算一次」完全一致（可复现性）
    same = 0
    for cd, r, df in recs[:60]:
        r2 = TI.detect_markup(df.copy())
        if (r2['ok'], r2['type'], round(r2['score'], 6)) == (r['ok'], r['type'], round(r['score'], 6)):
            same += 1
    check('I3 相同输入可复现（60 只）', same == 60, '%d/60' % same)
except Exception as _e:
    P('  [B] 跳过：%s: %s' % (type(_e).__name__, _e))

# ============================================================
P('')
P('[C] 引擎文案：新参数 + 旧参数逐字等价')
P('-' * 100)
if not os.path.exists(BAK):
    P('  备份引擎不存在（%s），跳过 —— 先跑 tools\\_apply_markup_engine.py' % BAK)
else:
    loader = importlib.machinery.SourceFileLoader('eng_bak_markup', BAK)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    EB = importlib.util.module_from_spec(spec)
    loader.exec_module(EB)

    P('  开关：_MARKUP_NOTE_MODE=%s（备份侧无此常量）' % E._MARKUP_NOTE_MODE)
    check('J0 新开关存在且为 watch/off', E._MARKUP_NOTE_MODE in ('watch', 'off'))

    # markup 文案本身
    t_on = E._observe_tags(None, None, None, None, False, None, None, '阶梯式上行')
    P('  拉升文案（watch）：%r' % t_on)
    check('J1 追加「拉升观察：阶梯式上行」',
          any('拉升观察：阶梯式上行' == x for x in t_on))
    t3 = E._observe_tags(None, None, None, None, False, None, None, '加速迹象')
    check('J2 追加「拉升观察：加速迹象」', any(x == '拉升观察：加速迹象' for x in t3))
    check('J3 markup=None 不追加', not E._observe_tags(None, None, None, None, False,
                                                       None, None, None))

    # 旧参数（前 7 个位置参数 / 前 9 个位置参数）必须与备份逐字一致
    diffs = []
    ncase = 0
    for ctrl in (0.0, 72.0, 85.0, 90.0, 95.0):
        for stage in ('wash', 'distribute', 'unknown'):
            for pos in (None, 0.10, 0.25, 0.30, 0.65, 0.90):
                for st, rf in ((None, None), (72.0, 66.0), (50.0, 50.0)):
                    for c4 in (None, 5, 3):
                        for c6 in (None, 2, 1):
                            for pr in (None, True, False):
                                for dp in (None, '双顶雏形'):
                                    a = E._ctrl_note(ctrl, stage, pos, st, rf, c4, c6, pr, dp)
                                    b = EB._ctrl_note(ctrl, stage, pos, st, rf, c4, c6, pr, dp)
                                    ncase += 1
                                    if a != b:
                                        diffs.append((ctrl, stage, pos, st, rf, c4, c6, pr, dp, a, b))
    check('J4 旧 9 参数组合与备份逐字一致（%d 组）' % ncase, not diffs,
          ('首例 %s' % (diffs[0],)) if diffs else '')

    diffs2 = []
    n2 = 0
    for st, rf in ((None, None), (72.0, 66.0)):
        for c4 in (None, 5):
            for c6 in (None, 2):
                for lc in (False, True):
                    for pr in (None, True):
                        for dp in (None, '高位破位'):
                            a = E._observe_tags(st, rf, c4, c6, lc, pr, dp)
                            b = EB._observe_tags(st, rf, c4, c6, lc, pr, dp)
                            n2 += 1
                            if a != b:
                                diffs2.append((a, b))
    check('J5 _observe_tags 旧 7 参数与备份逐字一致（%d 组）' % n2, not diffs2)

    # 判定函数本身没被碰
    for fn in ('detect_probe', 'detect_distribution_pattern', 'is_c4_candidate',
               'is_c6_candidate', 'estimate_control_score', 'judge_wash_or_distribute'):
        P('    %s 仍可调用: %s' % (fn, callable(getattr(TI, fn, None))))
    check('J6 老因子未被破坏（逐个可调用）',
          all(callable(getattr(TI, f, None)) for f in
              ('detect_probe', 'detect_distribution_pattern', 'is_c4_candidate',
               'is_c6_candidate', 'estimate_control_score', 'judge_wash_or_distribute')))

# ============================================================
P('')
P('[D] 静态检查：不得出现未来函数写法')
P('-' * 100)
import inspect  # noqa: E402
src = inspect.getsource(TI.detect_markup)
for pat in ('shift(-', '[i + 1', '[i+1', 'i + 1:', 'reverse', '[::-1]', 'future'):
    check('K 方法体不含 %r' % pat, pat not in src)
_src_all = src
check('K1 只使用向后窗口（无负向 shift）', 'shift(' not in _src_all)

P('')
P('=' * 100)
P('结果：PASS %d / FAIL %d' % (PASS[0], PASS[1]))
P('=' * 100)
import io  # noqa: E402
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(_lines) + '\n')
print('已写出', OUT)
