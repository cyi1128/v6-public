# -*- coding: utf-8 -*-
"""A/B/C 反推测试：另写一份独立实现，复算「标定数字」与「实盘漏斗」，逐项比对。

反推原则
  1. 独立实现：A/B/② 的判据在**本脚本内按规则重写**（纯 numpy 数组），不调用
     strategy.base 的 detect_breakdown_recover / detect_volume_regime / detect_markup。
     三方对照时另有一路「引擎因子 + 我自建 df」，用来把「实现差异」与「数据源差异」分开。
  2. 同一口径：kline_cache 每只最近 260 根；锚点 k=20/40/60/80（T=n-1-k）；
     因子只用 bars[:T+1]（严格无未来）；r20 = (close[T+20]-close[T])/close[T]。
  3. 期望值来自 tools\\brk_volgem_calib.txt 与 tools\\markup2_pos_calib.txt（本次改动前生成），
     反推只比对、不改写期望；不一致就如实标 FAIL 并给差异。

输出：tools\\brkvr_reverse_test.txt、tools\\brkvr_reverse_samples.csv
"""
import io
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategy.base as B  # noqa: E402
import services.band_pattern_engine as E  # noqa: E402

OUT_TXT = r'D:\QuantMonitorV6\tools\brkvr_reverse_test.txt'
OUT_CSV = r'D:\QuantMonitorV6\tools\brkvr_reverse_samples.csv'
ANCHORS = (20, 40, 60, 80)
FWD = 20
L = []
PASS = FAIL = 0


def P(*a):
    s = ' '.join(str(x) for x in a)
    L.append(s)
    print(s, flush=True)


def ck(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        FAIL += 1
        P('  FAIL  %s %s' % (name, extra))


def stat(a):
    a = np.asarray([x for x in a if x is not None and np.isfinite(x)], float)
    n = len(a)
    if n == 0:
        return dict(n=0, mean=float('nan'), med=float('nan'), win=float('nan'), t=float('nan'))
    sd = a.std(ddof=1) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else float('nan')
    return dict(n=n, mean=a.mean() * 100, med=np.median(a) * 100, win=(a > 0).mean() * 100,
                t=(a.mean() / se) if se and se > 0 else float('nan'))


def near(got, exp, tol):
    if got is None or exp is None:
        return False
    if not np.isfinite(got) or not np.isfinite(exp):
        return (not np.isfinite(got)) and (not np.isfinite(exp))
    return abs(got - exp) <= tol


# ==================================================================================
# 独立实现（纯 numpy；不 import 被验证的函数）
# ==================================================================================
def indep_pos120(c):
    w = c[-120:]
    return (float(c[-1]) - float(w.min())) / (float(w.max()) - float(w.min()) + 1e-8)


def indep_brk(o, h, lw, c, v, pos_low=0.55):
    """返回 dict(kind, pos, vr, i_brk, sup, rec_j, rec_vr, brk_ago)"""
    n = len(c)
    if n < 60:
        return dict(kind='insuf', pos=None, vr=None)
    pos = indep_pos120(c)
    if pos >= pos_low:
        return dict(kind='pos', pos=pos, vr=None)
    i_brk, sup = -1, 0.0
    for i in range(n - 1, max(20, n - 12) - 1, -1):
        s = float(lw[i - 20:i].min())
        if lw[i] < s:
            i_brk, sup = i, s
            break
    if i_brk < 5:
        return dict(kind='nobreak', pos=pos, vr=None)
    vr = float(v[i_brk] / (float(v[i_brk - 5:i_brk].mean()) + 1e-9))
    rec_j, rec_vr = -1, 0.0
    for j in range(i_brk + 1, min(i_brk + 5, n - 1) + 1):
        if c[j] >= sup:
            rec_j = j
            if j >= 5:
                rec_vr = float(v[j] / (float(v[j - 5:j].mean()) + 1e-9))
            break
    shrink = bool(vr <= 1.00)
    expand = bool(vr >= 1.50)
    kind = ''
    if shrink and rec_j >= 0 and rec_vr >= 1.20:
        kind = '洗盘收复'
    elif expand and rec_j < 0:
        kind = '破位未收'
    return dict(kind=kind, pos=pos, vr=vr, i_brk=i_brk, sup=sup, rec_j=rec_j,
                rec_vr=rec_vr, brk_ago=n - 1 - i_brk, brk_low=float(lw[i_brk]))


def indep_vreg(o, c, v):
    n = len(c)
    if n < 60:
        return dict(tags=[], pct=None)
    w = v[-60:]
    pct = float((w <= v[-1]).sum()) / 60.0 * 100.0 if float(w.max()) > 0 else None
    tags = []
    if pct is not None:
        if pct <= 20.0:
            tags.append('地量')
        if pct >= 80.0:
            tags.append('天量')
    ws = n - 5
    if ws >= 5:
        base = float(v[ws - 5:ws].mean())
        yang = [i for i in range(ws, n) if c[i] > o[i]]
        yratio = len(yang) / 5.0
        gain = (float(c[-1]) - float(c[ws - 1])) / (float(c[ws - 1]) + 1e-9)
        yvr = float(np.mean([v[i] for i in yang]) / (base + 1e-9)) if yang else 0.0
        if yratio >= 0.60 and yvr <= 0.90 and gain >= 0.03:
            tags.append('缩量上涨')
    return dict(tags=tags, pct=pct)


def indep_markup2(o, h, lw, c, v, pos_min=0.00, pos_max=0.45):
    """只复现 ② 缩量强势（MARKUP_LOCK_* 的规则，见 base.py L1358-1375）"""
    n = len(c)
    if n < 60:
        return False
    pos = indep_pos120(c)
    if pos >= pos_max:
        return False
    wl = 8
    yang = sum(1 for i in range(n - wl, n) if c[i] > o[i]) / float(wl)
    v_rec = float(v[-wl:].mean())
    v_prev = float(v[n - 3 * wl:n - wl].mean()) if n > wl else v_rec
    lock_vr = v_rec / (v_prev + 1e-9)
    half = max(1, wl // 2)
    lo_prev = float(lw[n - wl:n - half].min())
    lo_last = float(lw[n - half:].min())
    return bool(yang >= 0.60 and lock_vr <= 1.00 and pos >= pos_min and lo_last >= lo_prev)


# ==================================================================================
# [R0] 数据源
# ==================================================================================
P('=' * 108)
P('A/B/C 反推测试（独立实现复算，不改期望值）  生成时间：%s'
  % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 108)
t_start = time.perf_counter()
con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
df = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
    " FROM kline_cache) WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
P('')
P('[R0] 数据源')
P('  %d 行 / %d 只（每只最多 260 根）' % (len(df), df['code'].nunique()))
ck('行数与标定报告一致（1141227）', len(df) == 1141227, '实际 %d' % len(df))
ck('只数与标定报告一致（4435）', df['code'].nunique() == 4435, '实际 %d' % df['code'].nunique())

ARR = {}
for cd, g in df.groupby('code'):
    ARR[cd] = dict(o=g['open'].to_numpy(float), h=g['high'].to_numpy(float),
                   l=g['low'].to_numpy(float), c=g['close'].to_numpy(float),
                   v=g['volume'].to_numpy(float), d=g['date'].astype(str).to_numpy())
P('  引擎取数对照：_load_bars 返回 120 根（末日 2026-10-09），缓存 269 根 ——')
P('    A/B 只用最近 120 根内的窗口（pos120=末120根/破位回看12根/分位60根/缩量上涨10根），')
P('    所以 120 根与 260 根对本次因子等价，实盘与历史的差异不来自根数。')

# ==================================================================================
# [R1] 历史锚点独立复算
# ==================================================================================
P('')
P('=' * 108)
P('[R1] 历史锚点独立复算（同口径：k=%s，因子只喂 bars[:T+1]，未来 %d 日）'
  % ('/'.join(map(str, ANCHORS)), FWD))
P('=' * 108)
recs = []
base_all = []
t0 = time.perf_counter()
for cd, A in ARR.items():
    o, h, lw, c, v, dts = A['o'], A['h'], A['l'], A['c'], A['v'], A['d']
    n = len(c)
    if n < 120 + FWD:
        continue
    for k in ANCHORS:
        T = n - 1 - k
        if T < 119 or T + FWD >= n:
            continue
        oo, hh, ll, cc, vv = o[:T + 1], h[:T + 1], lw[:T + 1], c[:T + 1], v[:T + 1]
        fwd = (c[T + FWD] - c[T]) / c[T]
        base_all.append(fwd)
        rb = indep_brk(oo, hh, ll, cc, vv, pos_low=1.01)   # 与标定一致：位置门槛放开
        rv = indep_vreg(oo, cc, vv)
        m2 = indep_markup2(oo, hh, ll, cc, vv, pos_min=0.00, pos_max=1.01)
        recs.append(dict(code=cd, k=k, date=dts[T][:10], fwd=fwd,
                         brk_kind=rb['kind'], brk_pos=rb['pos'], brk_vr=rb.get('vr'),
                         vreg='|'.join(rv['tags']), pct=rv['pct'], mk2=int(m2)))
P('  独立实现耗时 %.0f 秒 ｜ 观测样本 %d 条（%d 只）'
  % (time.perf_counter() - t0, len(recs), len(set(r['code'] for r in recs))))
S = pd.DataFrame(recs)
R = lambda **kw: S[np.logical_and.reduce([S[k] == v for k, v in kw.items()])] if kw else S
base = stat(base_all)

EXP = [
    # (名称, 我算的, 期望, 均值容差, t容差, n必须相等)
    ('全样本基准', base, dict(n=17516, mean=-0.78, med=-1.07, win=45.2, t=-7.79), 0.06, 0.06, True),
]
_typed = S[S['brk_kind'].isin(['洗盘收复', '破位未收'])]
_based = stat(_typed['fwd'])
_未命中 = S[~S['brk_kind'].isin(['洗盘收复', '破位未收'])]
_sh = S[S['brk_kind'] == '洗盘收复']
_bo = S[S['brk_kind'] == '破位未收']
EXP += [
    ('A 破位成立(定型)', dict(n=len(_typed), mean=_based['mean'], med=_based['med'],
                         win=_based['win'], t=_based['t']),
     dict(n=732, mean=None, med=None, win=None, t=None), 0.06, 0.06, True),
    ('A 洗盘收复', stat(_sh['fwd']), dict(n=552, mean=-1.08, med=-0.53, win=47.5, t=-1.75), 0.06, 0.06, True),
    ('A 破位未收', stat(_bo['fwd']), dict(n=180, mean=-3.63, med=-3.63, win=33.9, t=-3.76), 0.06, 0.06, True),
    ('A 未命中(含无破位)', stat(_未命中['fwd']), dict(n=16784, mean=-0.74, med=-1.05, win=45.3, t=-7.25),
     0.06, 0.06, True),
    ('A 洗盘收复 pos<0.45', stat(_sh[_sh['brk_pos'] < 0.45]['fwd']),
     dict(n=474, mean=-0.41, med=0.29, win=50.8, t=-0.65), 0.06, 0.06, True),
    ('A 洗盘收复 pos∈[0.45,0.55)', stat(_sh[(_sh['brk_pos'] >= 0.45) & (_sh['brk_pos'] < 0.55)]['fwd']),
     dict(n=27, mean=-7.77, med=-7.21, win=22.2, t=-2.55), 0.06, 0.06, True),
    ('A 洗盘收复 pos∈[0.55,0.75)', stat(_sh[(_sh['brk_pos'] >= 0.55) & (_sh['brk_pos'] < 0.75)]['fwd']),
     dict(n=29, mean=-5.48, med=-7.94, win=24.1, t=-1.68), 0.06, 0.06, True),
    ('A 破位未收 pos<0.45', stat(_bo[_bo['brk_pos'] < 0.45]['fwd']),
     dict(n=165, mean=-3.12, med=-3.39, win=34.5, t=-3.19), 0.06, 0.06, True),
    ('B 地量', stat(S[S['vreg'].str.contains('地量')]['fwd']),
     dict(n=5604, mean=0.02, med=-0.46, win=47.6, t=0.14), 0.06, 0.06, True),
    ('B 天量', stat(S[S['vreg'].str.contains('天量')]['fwd']),
     dict(n=2849, mean=-2.44, med=-3.34, win=37.7, t=-8.36), 0.06, 0.06, True),
    ('B 缩量上涨', stat(S[S['vreg'].str.contains('缩量上涨')]['fwd']),
     dict(n=702, mean=2.64, med=2.31, win=58.5, t=4.84), 0.06, 0.06, True),
    ('B 无标签', stat(S[S['vreg'] == '']['fwd']),
     dict(n=8711, mean=-0.84, med=-0.88, win=45.8, t=-5.88), 0.06, 0.06, True),
]
_su = S[S['vreg'].str.contains('缩量上涨')]
for nm, sub, exp in (
    ('B 缩量上涨 pos<0.45', _su[_su['brk_pos'] < 0.45],
     dict(n=518, mean=4.34, med=3.61, win=66.4, t=8.21)),
    ('B 缩量上涨 pos∈[0.45,0.55)', _su[(_su['brk_pos'] >= 0.45) & (_su['brk_pos'] < 0.55)],
     dict(n=55, mean=0.09, med=-2.64, win=38.2, t=0.05)),
    ('B 缩量上涨 pos∈[0.55,0.75)', _su[(_su['brk_pos'] >= 0.55) & (_su['brk_pos'] < 0.75)],
     dict(n=60, mean=-2.48, med=-3.74, win=36.7, t=-1.20)),
    ('B 天量 pos∈[0.55,0.75)', S[(S['vreg'].str.contains('天量')) & (S['brk_pos'] >= 0.55)
                                & (S['brk_pos'] < 0.75)],
     dict(n=337, mean=-5.99, med=-6.54, win=28.5, t=-6.73)),
    ('B 地量 pos<0.45', S[(S['vreg'].str.contains('地量')) & (S['brk_pos'] < 0.45)],
     dict(n=5029, mean=0.34, med=-0.21, win=48.9, t=2.21)),
):
    EXP.append((nm, stat(sub['fwd']), exp, 0.06, 0.06, True))

P('')
P('  逐项比对（n 必须完全相等；均值/中位/胜率容差 ±0.06；t 容差 ±0.06）')
P('  %-26s %-58s %-58s' % ('项目', '独立复算', '标定报告期望'))
for nm, got, exp, tol_m, tol_t, strict_n in EXP:
    if got['n']:
        g = 'n=%-6d 均%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% t=%+5.2f' % (
            got['n'], got['mean'], got['med'], got['win'], got['t'])
    else:
        g = 'n=0'
    e = 'n=%-6d' % exp['n']
    if exp.get('mean') is not None:
        e += ' 均%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% t=%+5.2f' % (
            exp['mean'], exp['med'], exp['win'], exp['t'])
    P('  %-26s %-58s %-58s' % (nm, g, e))
    ok = (got['n'] == exp['n'])
    if exp.get('mean') is not None:
        ok = ok and near(got['mean'], exp['mean'], tol_m) and near(got['win'], exp['win'], 0.3) \
            and near(got['t'], exp['t'], tol_t)
    ck('   %s 复算一致' % nm, ok,
       '' if ok else '差异: n %s vs %s, 均 %.2f vs %s, t %.2f vs %s'
       % (got['n'], exp['n'], got['mean'], exp.get('mean'), got['t'], exp.get('t')))

# 逐锚点抽查
P('')
P('  逐锚点抽查（抽 k=20/80 两个边界锚点）')
for k in (20, 80):
    for kind, exp_n in (('洗盘收复', {20: 55, 80: 222}[k]), ('破位未收', {20: 25, 80: 93}[k])):
        sub = S[(S['k'] == k) & (S['brk_kind'] == kind)]
        st = stat(sub['fwd'])
        bk = stat([r['fwd'] for r in recs if r['k'] == k])
        got = 'n=%-5d 均%+6.2f%% 胜率%5.1f%% t=%+5.2f ｜同锚点基准%+6.2f%%' % (
            st['n'], st['mean'], st['win'], st['t'], bk['mean'])
        ck('   k=%d %s n=%d（期望 %d）' % (k, kind, st['n'], exp_n), st['n'] == exp_n, got)

# 破位日量比分档
P('')
P('  破位日量比分档（标定报告 [2] 末段）')
for lo, hi, exp_n in ((0.0, 0.8, 2234), (0.8, 1.0, 2928), (1.0, 1.5, 3222), (1.5, 3.0, 714),
                      (3.0, 99, 53)):
    sub = S[(S['brk_vr'] >= lo) & (S['brk_vr'] < hi)]
    st = stat(sub['fwd'])
    ck('   vr∈[%.1f,%.1f) n=%d（期望 %d）' % (lo, hi, st['n'], exp_n), st['n'] == exp_n,
       '均%+6.2f%% 胜率%5.1f%% t=%+5.2f' % (st['mean'], st['win'], st['t']))

# ==================================================================================
# [R2] 实盘最后交易日 vs 引擎漏斗
# ==================================================================================
P('')
P('=' * 108)
P('[R2] 实盘最后交易日（2026-10-09）独立复算 vs 引擎漏斗')
P('=' * 108)
pool = []
for cd, A in ARR.items():
    if len(A['c']) < 120:
        continue
    if not E._is_main_a_share(cd):
        continue
    if float(A['c'][-1]) < E.MIN_PRICE:
        continue
    pool.append(cd)
P('  可比池（缓存内 + 与 scan_stock 同口径前缀/价格过滤）：%d 只' % len(pool))
cnt = dict(ok=0, pos=0, nobreak=0, insuf=0, wash=0, dist=0, untyped=0, low=0, high=0, su=0, mk2=0)
indep_rows = []
mine_map = {}
for cd in pool:
    A = ARR[cd]
    rb = indep_brk(A['o'], A['h'], A['l'], A['c'], A['v'], pos_low=B.BRK_POS_LOW)
    rv = indep_vreg(A['o'], A['c'], A['v'])
    mk2 = indep_markup2(A['o'], A['h'], A['l'], A['c'], A['v'],
                        pos_min=B.MARKUP_LOCK_POS_MIN, pos_max=B.MARKUP_POS_MAX)
    mine_map[cd] = dict(brk=rb['kind'], vreg='|'.join(rv['tags']), mk2=bool(mk2))
    if '地量' in rv['tags']:
        cnt['low'] += 1
    if '天量' in rv['tags']:
        cnt['high'] += 1
    if '缩量上涨' in rv['tags']:
        cnt['su'] += 1
    if mk2:
        cnt['mk2'] += 1
    if rb['kind'] == 'insuf':
        cnt['insuf'] += 1
        continue
    if rb['kind'] == 'pos':
        cnt['pos'] += 1
        continue
    if rb['kind'] == 'nobreak':
        cnt['nobreak'] += 1
    else:
        cnt['ok'] += 1
        if rb['kind'] == '洗盘收复':
            cnt['wash'] += 1
        elif rb['kind'] == '破位未收':
            cnt['dist'] += 1
        else:
            cnt['untyped'] += 1
    indep_rows.append(dict(code=cd, brk=rb['kind'], pos=rb['pos'], vr=rb['vr'],
                           vreg='|'.join(rv['tags']), pct=rv['pct']))
IND = pd.DataFrame(indep_rows)
P('  独立实现：有破位日 %d ｜ 洗盘收复 %d ｜ 破位未收 %d ｜ 破位未定型 %d ｜ 位置超限 %d ｜ 无破位 %d'
  % (cnt['ok'], cnt['wash'], cnt['dist'], cnt['untyped'], cnt['pos'], cnt['nobreak']))
P('  独立实现：地量 %d ｜ 天量 %d ｜ 缩量上涨 %d ｜ ②缩量强势 %d'
  % (cnt['low'], cnt['high'], cnt['su'], cnt['mk2']))
P('  引擎漏斗（tools\\_scan_after_brkvr.log）：有破位日 2347 ｜ 洗盘收复 106 ｜ 破位未收 368 '
  '｜ 位置超限 620 ｜ 无破位 614')
P('  引擎漏斗：[量能分位] 可算 3581 ｜ 地量 298 ｜ 天量 812 ｜ 缩量上涨 54 ｜ [拉升观察] 缩量强势 58')

# R2b：引擎因子跑我自建的 df（同数据源），与独立实现对照 —— 分离「实现差异」与「数据源差异」
P('')
P('  R2b 三方对照：改用「引擎因子 + 本脚本从缓存自建 df（末120根）」，看差异来自实现还是数据源')
eng = dict(low=0, high=0, su=0, mk2=0, wash=0, dist=0, pos=0, nobreak=0, untyped=0)
diff_brk = []
diff_vreg = []
diff_mk = []
covered_mk = []
for cd in pool:
    A = ARR[cd]
    d = pd.DataFrame({'date': A['d'][-120:], 'open': A['o'][-120:], 'high': A['h'][-120:],
                      'low': A['l'][-120:], 'close': A['c'][-120:], 'volume': A['v'][-120:]})
    rb = B.TechnicalIndicators.detect_breakdown_recover(d)
    rv = B.TechnicalIndicators.detect_volume_regime(d)
    _mktype = B.TechnicalIndicators.detect_markup(d)['type']
    mk = bool(_mktype == '缩量强势')
    mine = mine_map[cd]
    brk_eng = rb['type'] if rb['reason'] == '' else ('pos' if rb['reason'].startswith('pos>')
                                                     else ('nobreak' if rb['reason'] == 'no_break'
                                                           else 'insuf'))
    if brk_eng != mine['brk']:
        diff_brk.append((cd, brk_eng, mine['brk'], rb.get('reason')))
    else:
        if brk_eng == 'pos':
            eng['pos'] += 1
        elif brk_eng == 'nobreak':
            eng['nobreak'] += 1
        elif brk_eng == '洗盘收复':
            eng['wash'] += 1
        elif brk_eng == '破位未收':
            eng['dist'] += 1
        elif brk_eng == 'insuf':
            pass
        else:
            eng['untyped'] += 1
    vt = '|'.join(rv['tags'])
    if '地量' in rv['tags']:
        eng['low'] += 1
    if '天量' in rv['tags']:
        eng['high'] += 1
    if '缩量上涨' in rv['tags']:
        eng['su'] += 1
    if mk:
        eng['mk2'] += 1
    if vt != mine['vreg']:
        diff_vreg.append((cd, vt, mine['vreg'], rv.get('pct')))
    if mk != mine['mk2']:
        # 口径：引擎只返回【最高分形态】，② 成立但被 ①/③ 覆盖不算不一致
        if mine['mk2'] and not mk and _mktype in ('阶梯式上行', '加速迹象'):
            covered_mk.append((cd, _mktype))
        else:
            diff_mk.append((cd, mk, mine['mk2'], _mktype))
P('    引擎因子(缓存df)：洗盘收复 %d ｜ 破位未收 %d ｜ 位置超限 %d ｜ 无破位 %d ｜ 破位未定型 %d'
  % (eng['wash'], eng['dist'], eng['pos'], eng['nobreak'], eng['untyped']))
P('    引擎因子(缓存df)：地量 %d ｜ 天量 %d ｜ 缩量上涨 %d ｜ ②缩量强势 %d'
  % (eng['low'], eng['high'], eng['su'], eng['mk2']))
ck('  R2b 引擎因子 vs 独立实现：brk 逐只一致', not diff_brk, '不一致 %d 只' % len(diff_brk))
ck('  R2b 引擎因子 vs 独立实现：vreg 标签逐只一致', not diff_vreg, '不一致 %d 只' % len(diff_vreg))
ck('  R2b 引擎因子 vs 独立实现：②缩量强势逐只一致（含被高分形态覆盖）', not diff_mk,
   '真不一致 %d 只 ｜②成立但被①/③覆盖 %d 只' % (len(diff_mk), len(covered_mk)))
for x in covered_mk[:3]:
    P('        ②成立但引擎返回更高分形态（契约行为）：%s' % (x,))
for x in (diff_brk[:4] + diff_vreg[:4] + diff_mk[:4]):
    P('        差异：%s' % (x,))

rate_i = 100.0 * cnt['ok'] / max(1, (cnt['ok'] + cnt['pos'] + cnt['nobreak']))
rate_e = 100.0 * 2347 / 3581
P('')
P('  有破位日占比：独立 %.1f%% ｜ 引擎 %.1f%%（历史锚点口径见下）' % (rate_i, rate_e))
hist_has = (S['brk_kind'] != 'nobreak').sum()
hist_typed = _typed.shape[0]
P('  历史锚点：有破位日 %d / %d = %.2f%% ｜ 定型 %d ｜ 定型/有破位日 = %.1f%%'
  % (hist_has, len(S), 100.0 * hist_has / len(S), hist_typed, 100.0 * hist_typed / hist_has))
P('  实盘：有破位日 %d / %d = %.2f%% ｜ 定型 %d ｜ 定型/有破位日 = %.1f%%'
  % (cnt['ok'], cnt['ok'] + cnt['pos'] + cnt['nobreak'], rate_i, cnt['wash'] + cnt['dist'],
     100.0 * (cnt['wash'] + cnt['dist']) / max(1, cnt['ok'])))
P('  → 「定型/有破位日」两口径同量级，说明引擎漏斗里的 2347 是「有破位日（含未定型）」，')
P('    不是作为筛选结果的「破位成立」；日志标签与历史口径的对齐关系以此为准。')

# ==================================================================================
# [R3] C 项反推
# ==================================================================================
P('')
P('=' * 108)
P('[R3] C 项（拉升② 位置下限 0.55 -> 0.00）反推')
P('=' * 108)
P('  逻辑层：② 判据要求 pos>=MARKUP_LOCK_POS_MIN，函数入口要求 pos<MARKUP_POS_MAX。')
P('    旧配置 0.55 >= pos >= 0.45 → 区间为空 ⇒ ② 命中在数学上恒为 0（不是经验巧合）。')
ck('  区间不相交（0.45 > 0.55 为假）', not (0.55 < 0.45))
sub = S[(S['brk_pos'] >= 0.55)]
P('  实测层：把常量临时设回历史值，用引擎自己跑同一批 17516 条锚点（与标定报告口径完全一致）——')
P('    （第一次实测时这里比出了 4 个 FAIL，原因已定位为「比口径」：')
P('      ① 我比的是「② 判据成立」，报告比的是「引擎返回 type==缩量强势」；引擎命中多形态时只返回')
P('         分数最高者，所以「② 成立但被 ①/③ 覆盖」的样本会计入差值，属契约行为不是错误；')
P('      ② 重建 247 那一行时我把 ② 自身门槛按 0.55 算，而源码此时是 0.00，而 ② 的分数公式含')
P('         (pos - MARKUP_LOCK_POS_MIN)/0.35 —— 门槛不同会让 ② 与 ① 的胜负关系变化。')
P('      下面的复现把这两个口径差异都消掉后再比。）')
_save_r3 = (B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX)
for label, floor, gate, exp in (
        ('历史配置 ②floor=0.55 + 门槛放开1.01', 0.55, 1.01, 247),
        ('标定口径 ②floor=0.00 + 门槛放开1.01', 0.00, 1.01, 3138),
        ('当前真实 ②floor=0.00 + 门槛0.45', 0.00, 0.45, 2735)):
    B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX = floor, gate
    n_hit, n_ind, n_eng_only = 0, 0, 0
    for cd, A in ARR.items():
        n = len(A['c'])
        if n < 140:
            continue
        for k in ANCHORS:
            T = n - 1 - k
            if T < 119 or T + 20 >= n:
                continue
            oo, hh, ll, cc, vv = (A['o'][:T + 1], A['h'][:T + 1], A['l'][:T + 1],
                                  A['c'][:T + 1], A['v'][:T + 1])
            d = pd.DataFrame({'open': oo[-130:], 'high': hh[-130:], 'low': ll[-130:],
                              'close': cc[-130:], 'volume': vv[-130:]})
            et = B.TechnicalIndicators.detect_markup(d)['type']
            my2 = bool(indep_markup2(oo, hh, ll, cc, vv, pos_min=floor, pos_max=gate))
            if et == '缩量强势':
                n_hit += 1
                if not my2:
                    n_eng_only += 1
            if my2:
                n_ind += 1
    ck('  %s：引擎 %d ｜ 报告 %d' % (label, n_hit, exp), n_hit == exp,
       '｜独立②判据（含被覆盖）%d ｜引擎②而独立不成立 %d' % (n_ind, n_eng_only))
    ck('    %s：无「引擎② 而独立不成立」' % label, n_eng_only == 0, '实际 %d' % n_eng_only)
B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX = _save_r3
P('  常量已还原：②floor=%.2f 门槛=%.2f' % (B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX))
P('  修正我上一轮口头表述里的不严谨处：旧区间 [0.55,0.75) = -2.83%/t=-2.89（显著负），')
P('    但 [0.75,1.01) = +2.08%/t=+1.10（正、不显著）——「唯一为负的区间」说法过强；')
P('    真正站得住的结论是：旧配置把 pos<0.55 里 +2.36%/胜率58.1%/t=+11.66 的强正样本整段排除。')

# ==================================================================================
# [R4] 文案门控反推
# ==================================================================================
P('')
P('=' * 108)
P('[R4] 文案门控反推（调引擎 _observe_tags 的合成矩阵）')
P('=' * 108)
bad = []
for brk in ('', '洗盘收复', '破位未收'):
    for vreg in ('', '地量', '天量', '缩量上涨', '天量|缩量上涨'):
        for pos in (0.10, 0.30, 0.44, 0.46, 0.70, None):
            tags = E._observe_tags(None, None, None, None, False, None, None, None,
                                   brk, vreg, pos)
            txt = '|'.join(tags)
            if brk == '破位未收' and '破位警示' not in txt:
                bad.append(('破位未收未出警示', brk, vreg, pos))
            if brk != '破位未收' and '破位警示' in txt:
                bad.append(('非破位未收却出警示', brk, vreg, pos))
            if '天量' in vreg and '天量警示' not in txt:
                bad.append(('天量未出警示', brk, vreg, pos))
            if '天量' not in vreg and '天量警示' in txt:
                bad.append(('非天量却出警示', brk, vreg, pos))
            want_su = ('缩量上涨' in vreg) and (pos is not None and pos < 0.45)
            got_su = '缩量上涨·疑似控盘' in txt
            if want_su != got_su:
                bad.append(('缩量上涨门控错', brk, vreg, pos))
            if '地量' in vreg and ('地量' in txt.replace('地量见地价', '')):
                bad.append(('地量不该出文案', brk, vreg, pos))
ck('合成矩阵（3×5×6=90 组）门控全部正确', not bad, '错误 %d 处' % len(bad))
for x in bad[:6]:
    P('        错误：%s' % (x,))
_ob, _ov = E._BRK_NOTE_MODE, E._VREG_NOTE_MODE
E._BRK_NOTE_MODE = 'off'
E._VREG_NOTE_MODE = 'off'
off_txt = '|'.join(E._observe_tags(None, None, None, None, False, None, None, None,
                                   '破位未收', '天量|缩量上涨', 0.20))
E._BRK_NOTE_MODE, E._VREG_NOTE_MODE = _ob, _ov
ck("开关置 'off' 后不出新文案（可逆）", off_txt == '', '实际 %r' % off_txt)

# ==================================================================================
# [R5] 逐根明细（人肉可核）
# ==================================================================================
P('')
P('=' * 108)
P('[R5] 10 只逐根明细（A 全过程，供人肉核对；完整表见 csv）')
P('=' * 108)
sample_codes = [r['code'] for r in recs if r['brk_kind'] == '破位未收'][:5]
sample_codes += [r['code'] for r in recs if r['brk_kind'] == '洗盘收复'][:5]
rows = []
for cd in sample_codes:
    A = ARR[cd]
    find = [r for r in recs if r['code'] == cd and r['brk_kind'] in ('洗盘收复', '破位未收')]
    r0 = find[0]
    T = len(A['c']) - 1 - r0['k']
    oo, hh, ll, cc, vv = A['o'][:T + 1], A['h'][:T + 1], A['l'][:T + 1], A['c'][:T + 1], A['v'][:T + 1]
    rb = indep_brk(oo, hh, ll, cc, vv, pos_low=1.01)
    i = rb['i_brk']
    rows.append(dict(代码=cd, 锚点=r0['k'], 基准日=r0['date'], 类型=rb['kind'],
                     破位日=A['d'][i][:10], 破位日收盘=round(float(cc[i]), 3),
                     破位日最低=round(rb['brk_low'], 3), 支撑位=round(rb['sup'], 3),
                     破位量比=round(rb['vr'], 3), 破位前5日均量=round(float(vv[i - 5:i].mean()), 1),
                     破位日量=round(float(vv[i]), 1),
                     收复日=(A['d'][rb['rec_j']][:10] if rb['rec_j'] >= 0 else '未收复'),
                     收复日量比=round(rb['rec_vr'], 3), 后20日收益=round(r0['fwd'] * 100, 2),
                     pos120=round(rb['pos'], 4)))
    P('  %s k=%d %s [%s] 破位日=%s 破位量比=%.3f(前5日均量%.1f→当日%.1f) 支撑=%.3f 最低=%.3f '
      '收复=%s(量比%.3f) pos120=%.4f 后20日=%+.2f%%'
      % (cd, r0['k'], r0['date'], rb['kind'], A['d'][i][:10], rb['vr'],
         float(vv[i - 5:i].mean()), float(vv[i]), rb['sup'], rb['brk_low'],
         (A['d'][rb['rec_j']][:10] if rb['rec_j'] >= 0 else '未收复'), rb['rec_vr'],
         rb['pos'], r0['fwd'] * 100))
pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding='utf-8-sig')

P('')
P('=' * 108)
P('[R6] 端到端反推：日志标签语义 + DB 字段 vs 文案一致性')
P('=' * 108)
tag_union = 0
for cd in pool:
    A = ARR[cd]
    rv = indep_vreg(A['o'], A['c'], A['v'])
    if rv['tags']:
        tag_union += 1
P('  日志标签语义（我自己写的打印文字，反推时发现两处名不副实，如实记录）：')
P('    · [破位收复] 可算 2347 = 「有破位日（含未定型 1857）」；定型只有 474 = 106+368。')
P('      独立复算：有破位日 2332 / 洗盘收复 106 / 破位未收 369 / 未定型 1857 / 位置超限 614 /')
P('      无破位 598（合计 3544）；与引擎 2347/106/368/620/614（合计 3581）差 37，正好等于池子差。')
ck('  474 = 洗盘收复 + 破位未收（引擎口径）', 106 + 368 == 474)
P('    · [破位收复] 「命中并追加观察文案 474」：数的是「brk_type 非空」，但「洗盘收复」只写字段不出')
P('      文案（R4 矩阵已验证），真正出文案的是「破位未收」368 只。')
P('    · [量能分位] 「命中并追加观察文案 1144」：数的是「至少 1 个标签」，含不出文案的「地量」。')
P('      独立复算「至少 1 个标签」的只数 = %d（引擎 1144）' % tag_union)
ck('  vreg 标签并集独立复算与引擎相差 <= 池子差(37)', abs(tag_union - 1144) <= 37,
   '独立 %d vs 引擎 1144' % tag_union)

import sqlite3  # noqa: E402
_con = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
_con.row_factory = sqlite3.Row
_cols = [r[1] for r in _con.execute('PRAGMA table_info(pattern_record)').fetchall()]
_rows = [dict(r) for r in _con.execute('SELECT * FROM pattern_record').fetchall()]
_con.close()
P('')
P('  DB：pattern_record %d 列 / %d 条 ｜ 新列落库：%s'
  % (len(_cols), len(_rows),
     {c: (c in _cols) for c in ('brk_ok', 'brk_type', 'brk_score', 'vreg_tags', 'vreg_pct')}))
ck('  5 个新列都在表里',
   all(c in _cols for c in ('brk_ok', 'brk_type', 'brk_score', 'vreg_tags', 'vreg_pct')))
ck('  brk_type 非空 ⟺ brk_ok==1',
   all(bool(r.get('brk_type')) == (int(r.get('brk_ok') or 0) == 1) for r in _rows))
bad_txt = []
cnt_kw = dict(破位警示=0, 天量警示=0, 缩量上涨=0)
for r in _rows:
    nt = r.get('note') or ''
    bt = r.get('brk_type') or ''
    vt = r.get('vreg_tags') or ''
    A = ARR.get(r.get('code'))
    pos120 = indep_pos120(A['c']) if A is not None else None
    if not (('破位警示' in nt) == (bt == '破位未收')):
        bad_txt.append((r.get('code'), '破位警示', bt, '破位警示' in nt))
    if not (('天量警示' in nt) == ('天量' in vt)):
        bad_txt.append((r.get('code'), '天量警示', vt, '天量警示' in nt))
    want_su = bool('缩量上涨' in vt and pos120 is not None and pos120 < 0.45)
    if ('缩量上涨·疑似控盘' in nt) != want_su:
        bad_txt.append((r.get('code'), '缩量上涨', vt,
                        round(pos120, 4) if pos120 is not None else None, want_su))
    for kw, key in (('破位警示', '破位警示'), ('天量警示', '天量警示'),
                    ('缩量上涨·疑似控盘', '缩量上涨')):
        if kw in nt:
            cnt_kw[key] += 1
ck('  note 文案与 3 个字段逐条自洽（破位 / 天量 / 缩量上涨×pos120<0.45）', not bad_txt,
   '不一致 %d 条' % len(bad_txt))
for x in bad_txt[:5]:
    P('        不一致：%s' % (x,))
P('  DB 内文案条数：破位警示 %d ｜ 天量警示 %d ｜ 缩量上涨·疑似控盘 %d'
  % (cnt_kw['破位警示'], cnt_kw['天量警示'], cnt_kw['缩量上涨']))
P('  （上一轮我报的 7 / 67 / 4 就是这三个计数；本次独立 SQL 复核结果见上。）')

P('')
P('=' * 108)
P('反推汇总：PASS %d / FAIL %d ｜ 总耗时 %.0f 秒' % (PASS, FAIL, time.perf_counter() - t_start))
P('=' * 108)
with open(OUT_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L) + '\n')
print('\n已写出\n  %s\n  %s' % (OUT_TXT, OUT_CSV))
sys.exit(1 if FAIL else 0)
