# -*- coding: utf-8 -*-
"""控盘度/洗盘 审计 · 第2步：反推拆解（真实全市场数据）

做法要点
--------
1. 直接 import 引擎与 base 的【真函数】，不重写：
      services.band_pattern_engine._bars_to_df / _ctrl_note / 四个阈值
      strategy.base.TechnicalIndicators.estimate_control_score / judge_wash_or_distribute
2. 分量分解（换手/量价/振幅/位置加权）在脚本里复刻，并与真函数输出
   逐位对拍（|diff| < 1e-6 才采信归因）。
3. 事后验证用【滚动历史截面】：在历史某根 K（T）上只用 T 之前的数据算分，
   再看 T 之后 3/5/10/20 日的真实收益、最大回撤、未来波动、未来量比。
   —— 现在库截止 2026-10-09，最新一根没有未来数据，所以必须做滚动，
      否则「事后验证」这件事根本不可能成立。

跑法： & $py -X utf8 "tools/_audit_ctrl_reverse.py"
"""
import io, os, sys, time, math, json
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import duckdb

from services.band_pattern_engine import (_bars_to_df, _ctrl_note,
                                          _CTRL_HIGH, _CTRL_CAND,
                                          _CTRL_DIST, _CTRL_POS_LOW,
                                          _CTRL_DIST_POS, _CTRL_CAND_POS)
from strategy.base import TechnicalIndicators as TI

OUT = os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.txt')
CSV = os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.csv')
KL = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
BARS = 200
ANCHORS = (20, 40, 60, 80)     # 从最后一根往前数第 k 根作为 T（保证有 k>=20 的未来数据）

_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')

P('=' * 100)
P('控盘度 / 洗盘出货判断 · 反推拆解（真实全市场数据）')
P('=' * 100)
P('阈值实测: _CTRL_HIGH=%s _CTRL_CAND=%s(已停用C3) _CTRL_CAND_POS=%s '
  '_CTRL_DIST=%s(已停用C1) _CTRL_DIST_POS=%s _CTRL_POS_LOW=%s(已停用C3)'
  % (_CTRL_HIGH, _CTRL_CAND, _CTRL_CAND_POS, _CTRL_DIST, _CTRL_DIST_POS, _CTRL_POS_LOW))

# ============================================================
# 0. 读 K 线
# ============================================================
t0 = time.time()
con = duckdb.connect(KL, read_only=True)
df_all = con.execute("""
    SELECT code, date, open, high, low, close, volume
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn
          FROM kline_cache)
    WHERE rn <= %d ORDER BY code, date
""" % BARS).df()
con.close()
P('\n[kline] 载入 %d 行 / %d 只 / 用时 %.1fs' % (len(df_all), df_all['code'].nunique(), time.time() - t0))
P('       日期范围 %s ~ %s' % (df_all['date'].min(), df_all['date'].max()))

# 顺便查 amount 是否全 0（数据质量旁证）
con = duckdb.connect(KL, read_only=True)
amt = con.execute("SELECT COUNT(*) , SUM(CASE WHEN amount>0 THEN 1 ELSE 0 END) FROM kline_cache").fetchone()
P('       [旁证] kline_cache.amount: 共 %d 行, 其中 >0 的 %d 行  -> amount 基本没填' % amt)
con.close()

groups = {c: g.reset_index(drop=True) for c, g in df_all.groupby('code', sort=False)}
P('       分组完成 %d 只 / 用时 %.1fs' % (len(groups), time.time() - t0))

# ============================================================
# 1. 复刻分量（用于归因）+ 与真函数逐位对拍
# ============================================================
def components(df, window=20):
    """复刻 estimate_control_score 的四段分量。返回 dict 或 None。"""
    if df is None or len(df) < 60:
        return None
    recent = df.tail(window)
    # 1 换手分量
    if 'turnover' in df.columns:
        avg_turnover = float(recent['turnover'].mean())
        ts = max(0.0, min(100.0, 100.0 - avg_turnover * 8.0)); branch = 'turnover'
        p = float('nan')
    else:
        vm20 = float(df['volume'].tail(window).mean())
        vm60 = float(df['volume'].tail(60).mean())
        if not vm60:
            return None
        p = vm20 / (vm60 + 1e-8)
        ts = max(0.0, min(100.0, (1.2 - p) / 0.5 * 100.0)); branch = 'volratio'
    # 2 量价配合
    seg = df.tail(window + 1)
    up = seg[seg['close'] > seg['close'].shift(1)]
    dn = seg[seg['close'] < seg['close'].shift(1)]
    vm = float(seg['volume'].mean()) + 1e-8
    upr = float(up['volume'].mean()) / vm if len(up) > 0 else 1.0
    dnr = float(dn['volume'].mean()) / vm if len(dn) > 0 else 1.0
    vs = 50.0
    if upr < 0.85: vs += 25.0
    if dnr > 1.15: vs -= 15.0
    # 2026-10-10 C2：真函数已删除「upr>1.3 且 dnr<0.8 -> +10」这一档，
    # 复刻必须同步删掉，否则对拍会出现 4.2 分偏差（0.35 x 1.2 x 10）而误判成分量错误。
    vs = max(0.0, min(100.0, vs))
    # 3 振幅
    amp = float(((recent['high'] - recent['low']) / (recent['close'] + 1e-8)).mean())
    # 2026-10-10 C5：真函数已把振幅分量从「越低越高」改为「峰值 4.0% 帐篷」，
    # 复刻必须同步，否则对拍会出现几十点偏差、分量归因全失真。
    if amp <= 0.040:
        ams = 100.0 - (0.040 - amp) * 2300.0
    else:
        ams = 100.0 - (amp - 0.040) * 1200.0
    ams = max(0.0, min(100.0, ams))
    # 4 位置
    t120 = df['close'].tail(120)
    lo, hi = float(t120.min()), float(t120.max())
    pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
    pw = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)
    raw = (ts * 0.40 + vs * 0.35 + ams * 0.25) * pw
    return dict(turnover_score=ts, vol_score=vs, amp_score=ams, pos_weight=pw,
                pos120=pos, p_ratio=p, up_ratio=upr, down_ratio=dnr,
                amp=amp, raw=raw, clamp=max(0.0, min(100.0, raw)), branch=branch)


def bars_of(g, T=None):
    """按引擎口径切 bars（list[dict]）"""
    rows = g if T is None else g.iloc[:T + 1]
    rows = rows.iloc[max(0, len(rows) - 120):]
    return rows.to_dict('records')


# ---- 对拍 ----
P('\n[对拍] 复刻分量 vs 真函数（随机 400 只，最新 K）')
codes = list(groups.keys())
rng = np.random.RandomState(20261010)
check = [codes[i] for i in rng.choice(len(codes), min(400, len(codes)), replace=False)]
maxdiff = 0.0
nbranch = {'turnover': 0, 'volratio': 0}
for c in check:
    g = groups[c]
    bs = bars_of(g)
    d = _bars_to_df(bs)
    if d is None:
        continue
    real = float(TI().estimate_control_score(d))
    comp = components(d)
    if comp is None:
        continue
    nbranch[comp['branch']] += 1
    maxdiff = max(maxdiff, abs(real - comp['clamp']))
P('   对拍样本 %d 只 | 最大偏差 = %.3e  | 分支命中: %s' % (sum(nbranch.values()), maxdiff, nbranch))
P('   -> 偏差 ~0 说明分量分解可采信；turnover 分支命中 0 次',
  )
PACK = maxdiff < 1e-6
P('   分解结论可采信: %s' % PACK)

# ============================================================
# 2. 全市场最新截面：分数分布 + 分量均值 + 阶段分布
# ============================================================
P('\n' + '=' * 100)
P('[A] 全市场最新截面（用最新一根 K 算分，即程序盘中看到的口径）')
P('=' * 100)
rows = []
for c, g in groups.items():
    bs = bars_of(g)
    d = _bars_to_df(bs)
    if d is None:
        continue
    comp = components(d)
    if comp is None:
        continue
    sc = float(TI().estimate_control_score(d))
    st = TI().judge_wash_or_distribute(d)
    rows.append(dict(code=c, score=sc, stage=st, **{k: v for k, v in comp.items()
                                                    if k not in ('raw',)}))
A = pd.DataFrame(rows)
P('\n有效样本 %d 只（_bars_to_df 要求 >=60 根，不足则整股跳过）' % len(A))
P('\n分数分布:')
q = A['score'].describe(percentiles=[.1, .25, .5, .75, .9, .95, .99])
for k in ['min', '10%', '25%', '50%', '75%', '90%', '95%', '99%', 'max']:
    P('   %-5s = %6.2f' % (k, q[k]))
P('   mean  = %6.2f  std = %.2f' % (A['score'].mean(), A['score'].std()))
P('\n阈值命中率（分母 = 全市场 %d 只）:' % len(A))
for th in (_CTRL_HIGH, _CTRL_CAND, 60, 70, 80, 95):
    c = int((A['score'] >= th).sum())
    P('   >=%-5.0f : %4d 只 (%.1f%%)' % (th, c, 100.0 * c / len(A)))

P('\n各分量均值（看分数被什么托起来）:')
for col, nm in [('turnover_score', '换手分量(实为近20/近60量比代理)'),
                ('vol_score', '量价配合'), ('amp_score', '振幅收敛'),
                ('pos_weight', '位置加权'), ('p_ratio', '近20日/近60日均量比'),
                ('amp', '20日平均振幅'), ('pos120', '近120日位置'),
                ('up_ratio', '上涨日均量/均量'), ('down_ratio', '下跌日均量/均量')]:
    P('   %-34s mean=%7.3f  p25=%7.3f  p75=%7.3f' %
      (nm, A[col].mean(), A[col].quantile(.25), A[col].quantile(.75)))

P('\n分量与总分相关性（谁在决定分数）:')
for col in ('turnover_score', 'vol_score', 'amp_score', 'pos_weight'):
    P('   corr(%-16s, score) = %+.3f' % (col, A[col].corr(A['score'])))

P('\n阶段分布（全市场）:')
vc = A['stage'].value_counts()
for k, v in vc.items():
    P('   %-12s %4d 只 (%.1f%%)' % (k, v, 100.0 * v / len(A)))

P('\n高分段 vs 低分段的特征对比（检验「分高=控盘」是否成立）:')
hi = A[A['score'] >= _CTRL_HIGH]
lo = A[A['score'] < 60]
for nm, sub in (('>=85 高分组', hi), ('<60 低分组', lo)):
    P('   %-12s n=%4d | 近20/60量比 %5.3f | 均振幅 %5.3f | 位置 %5.3f | 上涨均量比 %5.3f | 下跌均量比 %5.3f'
      % (nm, len(sub), sub['p_ratio'].mean(), sub['amp'].mean(),
         sub['pos120'].mean(), sub['up_ratio'].mean(), sub['down_ratio'].mean()))

P('\n全市场前 20 名（分数最高）:')
top = A.sort_values('score', ascending=False).head(20)
for _, r in top.iterrows():
    P('   %s 分=%5.1f %-11s 近20/60量比=%5.2f 振幅=%5.3f 位置=%5.2f 上涨量比=%5.2f 下跌量比=%5.2f'
      % (r['code'], r['score'], r['stage'], r['p_ratio'], r['amp'], r['pos120'],
         r['up_ratio'], r['down_ratio']))
P('\n全市场后 10 名（分数最低）:')
for _, r in A.sort_values('score').head(10).iterrows():
    P('   %s 分=%5.1f %-11s 近20/60量比=%5.2f 振幅=%5.3f 位置=%5.2f 上涨量比=%5.2f 下跌量比=%5.2f'
      % (r['code'], r['score'], r['stage'], r['p_ratio'], r['amp'], r['pos120'],
         r['up_ratio'], r['down_ratio']))

# ============================================================
# 3. 滚动历史截面 + 事后验证
# ============================================================
P('\n' + '=' * 100)
P('[B] 滚动历史截面事后验证（T 上只用 T 之前数据算分，看 T 之后真实走势）')
P('=' * 100)
P('锚点: 从最后一根往前 20/40/60/80 根；未来窗口最多 20 日')
t0 = time.time()
obs = []
for ci, (c, g) in enumerate(groups.items()):
    n = len(g)
    for k in ANCHORS:
        T = n - 1 - k
        if T < 60 or T + 20 >= n:
            continue
        d = _bars_to_df(bars_of(g, T))
        if d is None:
            continue
        comp = components(d)
        if comp is None:
            continue
        sc = float(TI().estimate_control_score(d))
        st = TI().judge_wash_or_distribute(d)
        cl = g['close'].values
        lo_ = g['low'].values
        vl = g['volume'].values
        base = float(cl[T])
        if base <= 0:
            continue
        def ret(kk):
            return (float(cl[T + kk]) / base - 1.0) * 100.0
        fwd = np.array([cl[T + j] / base - 1.0 for j in range(1, 21)])
        mdd = (float(lo_[T + 1:T + 21].min()) / base - 1.0) * 100.0
        vola = float(np.std(np.diff(cl[T:T + 21]) / cl[T:T + 20])) * 100.0
        v_now = float(vl[T - 59:T + 1].mean())
        v_next = float(vl[T + 1:T + 21].mean())
        obs.append(dict(code=c, T_date=g['date'].iloc[T], k=k, score=sc, stage=st,
                        pos120=comp['pos120'], p_ratio=comp['p_ratio'],
                        amp=comp['amp'], up_ratio=comp['up_ratio'], down_ratio=comp['down_ratio'],
                        r3=ret(3), r5=ret(5), r10=ret(10), r20=ret(20),
                        mdd20=mdd, vola20=vola, vratio_fwd=(v_next / v_now if v_now else 0.0)))
O = pd.DataFrame(obs)
P('\n观测样本 %d 条 / %d 只 / 用时 %.1fs' % (len(O), O['code'].nunique(), time.time() - t0))

def bucket(s):
    if s < 60: return '1 <60'
    if s < 70: return '2 60-70'
    if s < 80: return '3 70-80'
    if s < 85: return '4 80-85'
    if s < 90: return '5 85-90'
    return '6 >=90'
O['bucket'] = O['score'].apply(bucket)

P('\n[B1] 按控盘分档：未来收益 / 最大回撤 / 未来波动 / 未来量比')
P('   %-10s %6s %8s %8s %8s %8s %8s | %8s | %7s | %8s' %
  ('分数档', 'n', 'r3%', 'r5%', 'r10%', 'r20%', '胜率20', 'mdd20%', 'vola20', '未来量比'))
for b, sub in O.groupby('bucket'):
    P('   %-10s %6d %8.2f %8.2f %8.2f %8.2f %7.1f%% | %8.2f | %7.2f | %8.3f' %
      (b, len(sub), sub['r3'].mean(), sub['r5'].mean(), sub['r10'].mean(), sub['r20'].mean(),
       100.0 * (sub['r20'] > 0).mean(), sub['mdd20'].mean(), sub['vola20'].mean(),
       sub['vratio_fwd'].mean()))

P('\n[B2] 按 stage：事后是否验证了「洗盘 / 出货」的判断')
P('   %-12s %6s %8s %8s %8s %8s %8s | %8s | %7s | %8s' %
  ('stage', 'n', 'r3%', 'r5%', 'r10%', 'r20%', '胜率20', 'mdd20%', 'vola20', '未来量比'))
for b, sub in O.groupby('stage'):
    P('   %-12s %6d %8.2f %8.2f %8.2f %8.2f %7.1f%% | %8.2f | %7.2f | %8.3f' %
      (b, len(sub), sub['r3'].mean(), sub['r5'].mean(), sub['r10'].mean(), sub['r20'].mean(),
       100.0 * (sub['r20'] > 0).mean(), sub['mdd20'].mean(), sub['vola20'].mean(),
       sub['vratio_fwd'].mean()))

P('\n[B3] 直接检验三条提示规则（与 _ctrl_note 完全一致）')
r1 = O[(O['score'] >= _CTRL_HIGH) & (O['stage'] == 'wash')]
# 2026-10-10 C1：出货警示已由「score>=_CTRL_DIST」改为「pos120>=_CTRL_DIST_POS」
r2 = O[(O['stage'] == 'distribute') & (O['pos120'] >= _CTRL_DIST_POS)]
r2_ref = O[(O['stage'] == 'distribute') & (O['score'] >= _CTRL_DIST)]
# 2026-10-10 C3：规则③ 已由「分数主导(score>=_CTRL_CAND & pos<_CTRL_POS_LOW)」改为
# 「位置主导(pos<_CTRL_CAND_POS & score>=_CTRL_HIGH)」
r3 = O[(O['pos120'] < _CTRL_CAND_POS) & (O['score'] >= _CTRL_HIGH)]
r3_ref = O[(O['score'] >= _CTRL_CAND) & (O['pos120'] < _CTRL_POS_LOW)]
for nm, sub in (('①高度控盘+疑似洗盘', r1),
                ('②出货风险警示(新:位置)', r2),
                ('②出货风险警示(旧:分数)', r2_ref),
                ('③高度控盘候选(新:位置)', r3),
                ('③高度控盘候选(旧:分数)', r3_ref)):
    if len(sub) == 0:
        P('   %-18s n=0   （该规则在 %d 条样本里一次都没触发）' % (nm, len(O)))
        continue
    P('   %-18s n=%5d | r5=%7.2f%% r20=%7.2f%% 胜率20=%5.1f%% | mdd20=%7.2f%% | 未来量比=%5.3f'
      % (nm, len(sub), sub['r5'].mean(), sub['r20'].mean(),
         100.0 * (sub['r20'] > 0).mean(), sub['mdd20'].mean(), sub['vratio_fwd'].mean()))
P('   %-18s n=%5d | r5=%7.2f%% r20=%7.2f%% 胜率20=%5.1f%% | mdd20=%7.2f%% | 未来量比=%5.3f'
  % ('（对照）全样本', len(O), O['r5'].mean(), O['r20'].mean(),
     100.0 * (O['r20'] > 0).mean(), O['mdd20'].mean(), O['vratio_fwd'].mean()))

P('\n[B4] 「高控盘分 = 真的更控盘吗」：未来波动 / 回撤 / 量比（控盘应当表现为波动更小、缩量）')
for lo_, hi_ in ((0, 60), (60, 80), (80, 85), (85, 90), (90, 101)):
    sub = O[(O['score'] >= lo_) & (O['score'] < hi_)]
    if len(sub) == 0:
        continue
    P('   分数 [%3d,%3d) n=%5d | vola20=%6.2f | mdd20=%7.2f%% | 未来量比=%5.3f | 上涨日均量比=%5.3f 下跌日均量比=%5.3f'
      % (lo_, hi_, len(sub), sub['vola20'].mean(), sub['mdd20'].mean(),
         sub['vratio_fwd'].mean(), sub['up_ratio'].mean(), sub['down_ratio'].mean()))

P('\n[B5] wash / distribute 的「位置」是否与庄家手法阶段对应')
for st in ('wash', 'distribute', 'unknown'):
    sub = O[O['stage'] == st]
    if len(sub) == 0:
        continue
    P('   %-12s n=%5d | 位置120 mean=%5.3f  p25=%5.3f p75=%5.3f | 均振幅=%5.3f'
      % (st, len(sub), sub['pos120'].mean(), sub['pos120'].quantile(.25),
         sub['pos120'].quantile(.75), sub['amp'].mean()))

P('\n[B6] 出货警示按控盘分再切一刀（现有规则 = distribute 且 score>=%.0f）' % _CTRL_DIST)
d = O[O['stage'] == 'distribute']
for lo_, hi_ in ((0, 60), (60, 70), (70, 80), (80, 101)):
    sub = d[(d['score'] >= lo_) & (d['score'] < hi_)]
    if len(sub) == 0:
        P('   distribute 且 score[%3d,%3d)  n=0' % (lo_, hi_)); continue
    P('   distribute 且 score[%3d,%3d)  n=%5d | r5=%7.2f%% r20=%7.2f%% 胜率20=%5.1f%% | mdd20=%7.2f%%'
      % (lo_, hi_, len(sub), sub['r5'].mean(), sub['r20'].mean(),
         100.0 * (sub['r20'] > 0).mean(), sub['mdd20'].mean()))
P('   （对照）非 distribute：n=%5d | r5=%7.2f%% r20=%7.2f%% 胜率20=%5.1f%% | mdd20=%7.2f%%'
  % (len(O) - len(d), O[O['stage'] != 'distribute']['r5'].mean(),
     O[O['stage'] != 'distribute']['r20'].mean(),
     100.0 * (O[O['stage'] != 'distribute']['r20'] > 0).mean(),
     O[O['stage'] != 'distribute']['mdd20'].mean()))

P('\n[B7] 控盘分阈值敏感性（已与规则③解耦，只看「分数本身」的区分度）')
for th in (80, 82, 85, 90):
    sub = O[O['score'] >= th]
    P('   score>=%2d  n=%5d (占 %4.1f%%) | r5=%6.2f%% r20=%6.2f%% 胜率20=%5.1f%% | mdd20=%6.2f%% | 未来量比=%5.3f'
      % (th, len(sub), 100.0 * len(sub) / len(O), sub['r5'].mean(), sub['r20'].mean(),
         100.0 * (sub['r20'] > 0).mean(), sub['mdd20'].mean(), sub['vratio_fwd'].mean()))

P('\n[B8] 「高位 + 高控盘分」是否是陷阱（位置加权在压 0.8 倍，但仍是高分的那些）')
for lo_, hi_ in ((0.0, 0.4), (0.4, 0.7), (0.7, 1.01)):
    for s0 in (0, 85):
        sub = O[(O['pos120'] >= lo_) & (O['pos120'] < hi_) & (O['score'] >= s0)]
        if len(sub) < 20:
            continue
        P('   位置[%.1f,%.1f) 且 score>=%2d : n=%5d | r20=%6.2f%% 胜率20=%5.1f%% | mdd20=%6.2f%%'
          % (lo_, hi_, s0, len(sub), sub['r20'].mean(),
             100.0 * (sub['r20'] > 0).mean(), sub['mdd20'].mean()))

P('\n[B9] 振幅分量（C5 目标）分档：未来20日表现 + 新旧 amp_score 对照')
for _lo, _hi in ((0, 0.02), (0.02, 0.025), (0.025, 0.03), (0.03, 0.0375),
                 (0.0375, 0.045), (0.045, 0.055), (0.055, 0.07), (0.07, 9)):
    sub = O[(O['amp'] >= _lo) & (O['amp'] < _hi)]
    if len(sub) < 20:
        continue
    mid = (_lo + min(_hi, 0.12)) / 2.0
    old_ = max(0.0, min(100.0, 100.0 - mid * 300.0))
    new_ = (100.0 - (0.040 - mid) * 2300.0) if mid <= 0.040 else (100.0 - (mid - 0.040) * 1200.0)
    P('   amp[%.3f,%.3f) n=%5d | r20=%6.2f%% 胜率20=%5.1f%% mdd20=%6.2f%% | amp_score 旧%5.1f -> 新%5.1f'
      % (_lo, _hi, len(sub), sub['r20'].mean(), 100.0 * (sub['r20'] > 0).mean(),
         sub['mdd20'].mean(), old_, max(0.0, min(100.0, new_))))

# 落 CSV
O.to_csv(CSV, index=False, encoding='utf-8-sig')
A.to_csv(CSV.replace('.csv', '_cross.csv'), index=False, encoding='utf-8-sig')
P('\nCSV 已写: %s  (%d 行)' % (CSV, len(O)))
P('CSV 已写: %s  (%d 行)' % (CSV.replace('.csv', '_cross.csv'), len(A)))
P('\n' + '=' * 100)
P('第2步完成')
_fh.close()
