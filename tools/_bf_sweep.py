# -*- coding: utf-8 -*-
"""V20 建仓因子 · B 深挖分析（第二步/第三步）

只读 tools/buildfactor_wide.csv（秒级），不改引擎、不改规则。

判据说明（关键）：
  汇总均值很容易被「锚点构成」骗到（上一轮已经出现过：汇总 +2.23%、逐锚点 4/4 为负）。
  因此本脚本对每个候选子集都做 **逐锚点增量检验**：
      inc(k) = mean(r20 | 子集 ∩ 锚点k) - mean(r20 | 锚点k)
  只有 4 个锚点 **同号且全正** 才标 ★可信正向；4 个全负标 ▽确认负向。
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd

CSV = os.path.join(ROOT, 'tools', 'buildfactor_wide.csv')
OUT = os.path.join(ROOT, 'tools', 'buildfactor_deep.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
OK = [0]
BAD = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


O = pd.read_csv(CSV)
BASE = float(O.r20.mean())
BASE_W = 100 * float((O.r20 > 0).mean())
ANCH = sorted(O.k.unique())
AB = {k: float(O[O.k == k].r20.mean()) for k in ANCH}
P('=' * 132)
P('V20 建仓因子 · B 深挖（窗口敏感性 / 位置过滤 / 交叉 / 反向验证）')
P('=' * 132)
P('  观测 %d 条 / %d 只 / 锚点 %s' % (len(O), O.code.nunique(), ANCH))
P('  全样本基准 r20 = %+.2f%%  胜率 = %.1f%%  mdd20 = %+.2f%%' % (BASE, BASE_W, O.mdd20.mean()))
P('  各锚点基准: ' + ' ｜ '.join('k%d %+.2f%%' % (k, AB[k]) for k in ANCH))
P('  ★ = 4 锚点增量全为正（可信正向）   ▽ = 4 锚点增量全为负（确认负向）')


def anchor_inc(m):
    """逐锚点增量，返回 (list, 标记)"""
    incs = []
    for k in ANCH:
        sk = O[m & (O.k == k)]
        incs.append(float(sk.r20.mean()) - AB[k] if len(sk) >= 20 else None)
    if any(x is None for x in incs):
        return incs, '  '
    pos = all(x > 0 for x in incs)
    neg = all(x < 0 for x in incs)
    return incs, ('★' if pos else ('▽' if neg else '  '))


def show(nm, m, minn=40):
    s = O[m]
    if len(s) < minn:
        P('   %-40s n=%5d  (样本太少，跳过)' % (nm, len(s)))
        return
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    incs, flag = anchor_inc(m)
    ins = '  '.join('--' if x is None else '%+.2f' % x for x in incs)
    P('   %-40s n=%5d 只=%4d | r20=%+6.2f%% 胜率=%5.1f%% mdd=%+6.2f%% t=%+5.2f | 锚点增量 %s %s'
      % (nm, len(s), s.code.nunique(), s.r20.mean(), 100 * (s.r20 > 0).mean(),
         s.mdd20.mean(), t, ins, flag))


def rho(col, mask=None):
    a = O if mask is None else O[mask]
    if len(a) < 40:
        return float('nan')
    return float(pd.Series(a[col]).rank().corr(pd.Series(a.r20).rank()))


# ==================================================================
P('\n' + '=' * 132)
P('[1] 堆量窗口敏感性：15 组窗口 x 2 种口径（ratio>=1.15 / 组内 ratio TOP30%）')
P('=' * 132)
P('   口径A「堆量倍数 >= 1.15」= 生产函数当前语义')
P('   %-10s %6s %7s %7s %7s %7s %7s  %-18s %s' % ('窗口(近/基)', 'n', 'r20', '胜率', 'mdd', 't', 'rho', '锚点增量', ''))
P('   ' + '-' * 124)
rows_a = []
for w in (5, 8, 10, 12, 15):
    for b in (15, 20, 30):
        col = 's%02d_%02d_r' % (w, b)
        m = O[col] >= 1.15
        s = O[m]
        t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
        incs, flag = anchor_inc(m)
        r = rho(col)
        P('   %-10s %6d %+7.2f %6.1f%% %+7.2f %+7.2f %+7.4f  %-18s %s'
          % ('%d/%d' % (w, b), len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(),
             s.mdd20.mean(), t, r, '  '.join('%+.2f' % x for x in incs), flag))
        rows_a.append((w, b, s.r20.mean(), flag, r))
best_a = max(rows_a, key=lambda z: z[2])
P('   → 15 组里汇总均值最高：%d/%d  r20=%+.2f%%  标记=%s' % (best_a[0], best_a[1], best_a[2], best_a[3] or '无'))
P('   → 有 ★ 可信正向的窗口组合数：%d / 15' % sum(1 for z in rows_a if z[3] == '★'))

P('\n   口径B「组内 ratio TOP30%」（不看固定阈值，只看相对堆量）')
P('   %-10s %6s %7s %7s %7s %7s %7s  %-18s %s' % ('窗口(近/基)', 'n', 'r20', '胜率', 'mdd', 't', '阈值', '锚点增量', ''))
P('   ' + '-' * 124)
rows_b = []
for w in (5, 8, 10, 12, 15):
    for b in (15, 20, 30):
        col = 's%02d_%02d_r' % (w, b)
        thr = float(O[col].quantile(0.70))
        m = O[col] >= thr
        s = O[m]
        t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
        incs, flag = anchor_inc(m)
        P('   %-10s %6d %+7.2f %6.1f%% %+7.2f %+7.2f %7.2f  %-18s %s'
          % ('%d/%d' % (w, b), len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(),
             s.mdd20.mean(), t, thr, '  '.join('%+.2f' % x for x in incs), flag))
        rows_b.append((w, b, s.r20.mean(), flag, thr))
best_b = max(rows_b, key=lambda z: z[2])
P('   → TOP30%% 口径里汇总最高：%d/%d  r20=%+.2f%%（阈值 %.2f）标记=%s'
  % (best_b[0], best_b[1], best_b[2], best_b[4], best_b[3] or '无'))
P('   → 有 ★ 的组合数：%d / 15' % sum(1 for z in rows_b if z[3] == '★'))

# ==================================================================
P('\n' + '=' * 132)
P('[2] 红肥绿瘦窗口敏感性：4 组窗口（ratio>=1.30 / 组内 TOP30%）')
P('=' * 132)
P('   %-8s %6s %7s %7s %7s %7s %7s  %-18s %s' % ('窗口', 'n', 'r20', '胜率', 'mdd', 't', 'rho', '锚点增量', ''))
P('   ' + '-' * 124)
for w in (10, 15, 20, 30):
    col = 'f%02d_r' % w
    m = O[col] >= 1.30
    s = O[m]
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    incs, flag = anchor_inc(m)
    P('   %-8s %6d %+7.2f %6.1f%% %+7.2f %+7.2f %+7.4f  %-18s %s'
      % ('%d日' % w, len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(), s.mdd20.mean(), t,
         rho(col), '  '.join('%+.2f' % x for x in incs), flag))
P('   组内 TOP30%：')
P('   %-8s %6s %7s %7s %7s %7s %7s  %-18s %s' % ('窗口', 'n', 'r20', '胜率', 'mdd', 't', '阈值', '锚点增量', ''))
P('   ' + '-' * 124)
for w in (10, 15, 20, 30):
    col = 'f%02d_r' % w
    thr = float(O[col].quantile(0.70))
    m = O[col] >= thr
    s = O[m]
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    incs, flag = anchor_inc(m)
    P('   %-8s %6d %+7.2f %6.1f%% %+7.2f %+7.2f %7.2f  %-18s %s'
      % ('%d日' % w, len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(), s.mdd20.mean(), t,
         thr, '  '.join('%+.2f' % x for x in incs), flag))

# ==================================================================
P('\n' + '=' * 132)
P('[3] 位置过滤加强（pos120 用 close 口径，与上一轮报告一致）')
P('=' * 132)
for p in (0.15, 0.20, 0.25, 0.30, 0.45):
    show('pos120 < %.2f（纯位置，不加因子）' % p, O.pos120 < p)
P('')
P('   在低位区里再叠加堆量（默认窗口 10/20）：')
for p in (0.20, 0.25, 0.30):
    show('pos<%.2f 且 堆量ratio>=1.15' % p, (O.pos120 < p) & (O.s10_20_r >= 1.15))
    show('pos<%.2f 且 堆量ratio<0.80（明显缩量）' % p, (O.pos120 < p) & (O.s10_20_r < 0.80))
P('')
P('   在低位区里再叠加红肥绿瘦（默认窗口 20）：')
for p in (0.20, 0.25, 0.30):
    show('pos<%.2f 且 红肥ratio>=1.30' % p, (O.pos120 < p) & (O.f20_r >= 1.30))
    show('pos<%.2f 且 红瘦绿肥ratio<0.90' % p, (O.pos120 < p) & (O.f20_r < 0.90))
P('')
P('   位置 x 红肥比值 细分（窗口 20，看方向是否真的反向）')
P('   %-26s %6s %7s %7s %7s' % ('档位', 'n', 'r20', '胜率', 't'))
for p_lo, p_hi in ((0.0, 0.25), (0.25, 0.45), (0.45, 1.01)):
    for r_lo, r_hi in ((0.0, 0.9), (0.9, 1.3), (1.3, 2.0), (2.0, 9.0)):
        m = (O.pos120 >= p_lo) & (O.pos120 < p_hi) & (O.f20_r >= r_lo) & (O.f20_r < r_hi)
        s = O[m]
        if len(s) < 40:
            continue
        t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
        P('   %-26s %6d %+7.2f %6.1f%% %+7.2f'
          % ('pos[%.2f,%.2f) 红肥[%.1f,%.1f)' % (p_lo, p_hi, r_lo, r_hi),
             len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(), t))

# ==================================================================
P('\n' + '=' * 132)
P('[4] 与现有强因子交叉')
P('=' * 132)
g80 = O.score >= 80
g85 = O.score >= 85
amp_ok = (O.amp20 >= 0.025) & (O.amp20 <= 0.055)
volst = (O.up_r > 1.15) & (O.dn_r < 0.95)
show('基准: ctrl>=80', g80)
show('基准: ctrl>=85', g85)
show('基准: amp∈[2.5%,5.5%]', amp_ok)
show('基准: 量价结构 up_r>1.15 & dn_r<0.95', volst)
for nm, base_m in (('ctrl>=80', g80), ('ctrl>=85', g85)):
    P('   ---- 在 %s 之上叠加 ----' % nm)
    show('   %s + 堆量>=1.15' % nm, base_m & (O.s10_20_r >= 1.15))
    show('   %s + 红肥>=1.30' % nm, base_m & (O.f20_r >= 1.30))
    show('   %s + 两者都满足' % nm, base_m & (O.s10_20_r >= 1.15) & (O.f20_r >= 1.30))
    show('   %s + 两者都不满足' % nm, base_m & (O.s10_20_r < 1.15) & (O.f20_r < 1.30))
P('   ---- 低位 x 高控盘 x 振幅 x 量价 四重叠加 ----')
q = (O.pos120 < 0.25) & g85
show('pos<0.25 & ctrl>=85', q)
show('pos<0.25 & ctrl>=85 & amp∈[2.5%,5.5%]', q & amp_ok)
show('pos<0.25 & ctrl>=85 & amp∈[2.5%,5.5%] & 量价结构', q & amp_ok & volst)
show('  + 堆量>=1.15', q & amp_ok & volst & (O.s10_20_r >= 1.15))
show('  + 红肥>=1.30', q & amp_ok & volst & (O.f20_r >= 1.30))
show('  + 堆量>=1.15 & 红肥>=1.30', q & amp_ok & volst & (O.s10_20_r >= 1.15) & (O.f20_r >= 1.30))

# ==================================================================
P('\n' + '=' * 132)
P('[5] 反向验证（红瘦绿肥 / 明显缩量）')
P('=' * 132)
show('全样本 红瘦绿肥 ratio<0.90', O.f20_r < 0.90)
show('全样本 红瘦绿肥 ratio<0.80', O.f20_r < 0.80)
show('全样本 明显缩量 堆量<0.80', O.s10_20_r < 0.80)
show('全样本 明显缩量 堆量<0.60', O.s10_20_r < 0.60)
show('低位 红瘦绿肥<0.90', (O.pos120 < 0.45) & (O.f20_r < 0.90))
show('低位 红瘦绿肥<0.80', (O.pos120 < 0.45) & (O.f20_r < 0.80))
show('低位 明显缩量<0.80', (O.pos120 < 0.45) & (O.s10_20_r < 0.80))
show('低位 明显缩量<0.60', (O.pos120 < 0.45) & (O.s10_20_r < 0.60))
show('低位 + 红瘦绿肥<0.90 + 控盘>=85', (O.pos120 < 0.45) & (O.f20_r < 0.90) & g85)
show('低位 + 明显缩量<0.80 + 控盘>=85', (O.pos120 < 0.45) & (O.s10_20_r < 0.80) & g85)
show('低位 + 红瘦绿肥<0.90 + 量价结构', (O.pos120 < 0.45) & (O.f20_r < 0.90) & volst)

# ==================================================================
P('\n' + '=' * 132)
P('[6] 分档单调性复核（回答「是不是只是阈值选错，方向其实对」）')
P('=' * 132)
P('   6.1 堆量倍数 15 组窗口的「低→高」分档 r20（只列相关系数，全为负说明方向就是反的）')
for w in (5, 8, 12, 15):
    for b in (15, 20, 30):
        col = 's%02d_%02d_r' % (w, b)
        P('      窗口 %2d/%-2d  rho(r20) = %+.4f   五档 r20: %s'
          % (w, b, rho(col),
             ' | '.join('%+.2f' % float(O[(O[col] >= lo) & (O[col] < hi)].r20.mean())
                        for lo, hi in ((0, 0.8), (0.8, 1.0), (1.0, 1.15), (1.15, 1.6), (1.6, 99))
                        if len(O[(O[col] >= lo) & (O[col] < hi)]) > 20)))
P('   6.2 红肥绿瘦比值 4 组窗口的 rho')
for w in (10, 15, 20, 30):
    P('      窗口 %2d  rho(r20) = %+.4f' % (w, rho('f%02d_r' % w)))
P('   6.3 对照：本数据集里已知有效的因子（正相关应明显）')
for nm, col in (('pos120（越低越好 -> 应为负）', 'pos120'), ('ctrl 控盘分', 'score'),
                ('amp20 振幅', 'amp20'), ('up_r 上涨日量比', 'up_r'), ('dn_r 下跌日量比', 'dn_r')):
    P('      %-28s rho(r20) = %+.4f' % (nm, rho(col)))

P('\n' + '=' * 132)
P('  说明：本脚本只统计。引擎未做任何修改；_BUILD_NOTE_MODE 仍为 off。')
P('=' * 132)
_fh.close()
print('\n已写:', OUT)
