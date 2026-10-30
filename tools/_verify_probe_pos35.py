# -*- coding: utf-8 -*-
"""验证「试盘位置门槛 0.75 -> 0.35」真正生效（只读，不改代码）

三件事：
  1. 造「同形态、只有 pos120 不同」的样本，自动搜出「刚好低于 / 刚好高于 0.35」两个临界样本，
     看门槛是否正好卡在 0.35；
  2. monkeypatch 常量回 0.75，确认这两个样本在旧门槛下都被放行 —— 差异确实来自本次改动；
  3. 逐项比对 base.py 与 .bak_before_probe_pos35：PROBE_* 只允许 PROBE_POS_MAX 一项不同，
     DIST_* 及其余 PROBE_* 必须逐字一致 —— 证明只改了这一处参数。
"""
import io
import sys

import pandas as pd

sys.path.insert(0, r'D:\QuantMonitorV6')
import strategy.base as B  # noqa: E402

BASE = r'D:\QuantMonitorV6\strategy\base.py'
BAK = BASE + '.bak_before_probe_pos35'
OUT = []
PASS = [0]
FAIL = [0]


def p(line=''):
    OUT.append(line)
    print(line, flush=True)


def ck(cond, msg, extra=''):
    if cond:
        PASS[0] += 1
        p('  PASS  %s %s' % (msg, extra))
    else:
        FAIL[0] += 1
        p('  FAIL  %s %s' % (msg, extra))


def hist(n, lo=8.0, hi=9.6, tail=6, volv=100.0):
    """前段从 hi 线性回落到 lo，最后 tail 根横盘在 lo（与单测同一套造数）。"""
    o, h, l, c, v = [], [], [], [], []
    for i in range(n):
        q = hi - (hi - lo) * i / (n - tail - 1) if i < n - tail else lo
        c.append(q)
        o.append(q * 0.998)
        h.append(q * 1.008)
        l.append(q * 0.992)
        v.append(volv)
    return o, h, l, c, v


def mk(level=None):
    """长上影试盘形态固定；level 决定现价在 120 日区间里的位置（None = 天然低位）。"""
    n = 90
    o, h, l, c, v = hist(n)
    if level is not None:
        for i in range(n - 12, n):
            c[i] = level
            o[i] = level * 0.998
            h[i] = level * 1.008
            l[i] = level * 0.992
            v[i] = 100.0
    i = n - 4
    pc = c[i - 1]
    o[i] = pc
    h[i] = pc * 1.075
    l[i] = pc * 0.995
    c[i] = pc * 1.02
    v[i] = 100.0 * 3.0
    for j in range(i + 1, n):
        o[j] = c[j] = c[i] * 0.998
        h[j] = c[i] * 1.005
        l[j] = c[i] * 0.99
        v[j] = 100.0 * 0.5
    return pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})


TI = B.TechnicalIndicators()

p('=' * 92)
p('试盘位置门槛验证（PROBE_POS_MAX 现值 = %s）' % B.PROBE_POS_MAX)
p('=' * 92)

ck(abs(float(B.PROBE_POS_MAX) - 0.35) < 1e-9,
   'base.py 里 PROBE_POS_MAX 已是 0.35', '实际=%s' % B.PROBE_POS_MAX)

# --- 自动搜临界样本 -------------------------------------------------------
lo_lv = hi_lv = None
lo_pos = hi_pos = None
lv = 8.00
while lv < 9.30:
    pos = TI.detect_probe(mk(round(lv, 3))).get('pos120')
    if pos is not None:
        if pos < 0.35 and (lo_pos is None or pos > lo_pos):
            lo_pos, lo_lv = pos, round(lv, 3)
        if pos > 0.35 and (hi_pos is None or pos < hi_pos):
            hi_pos, hi_lv = pos, round(lv, 3)
    lv += 0.01

p('')
p('[1] 自动搜出的两个临界样本（形态完全相同，只有现价位置不同）')
p('    刚低于门槛：level=%.3f  pos120=%.4f' % (lo_lv, lo_pos))
p('    刚高于门槛：level=%.3f  pos120=%.4f' % (hi_lv, hi_pos))

r_below = TI.detect_probe(mk(lo_lv))
r_above = TI.detect_probe(mk(hi_lv))
r_low = TI.detect_probe(mk(None))

p('')
p('[2] 新门槛 0.35 下的实际返回')
for tag, r in (('天然低位', r_low), ('刚低于线', r_below), ('刚高于线', r_above)):
    p('    %-8s pos120=%.4f  reason=%-10s ok=%-5s score=%.1f stage=%s'
      % (tag, r.get('pos120') or -1, r.get('reason') or '-', bool(r.get('ok')),
         float(r.get('score') or 0.0), r.get('stage') or '-'))

ck(abs(lo_pos - 0.35) <= 0.02 and abs(hi_pos - 0.35) <= 0.02,
   '两个临界样本正好夹住 0.35',
   '低=%.4f 高=%.4f' % (lo_pos, hi_pos))
ck(not str(r_below.get('reason') or '').startswith('pos>'),
   '刚好低于 0.35 的样本未被位置门槛拦掉（门槛没有收得过紧）',
   'reason=%s' % (r_below.get('reason') or '-'))
ck(str(r_above.get('reason') or '') == 'pos>0.35',
   '刚好高于 0.35 的样本被卡在 pos>0.35',
   'reason=%s' % (r_above.get('reason') or '-'))
ck(bool(r_low.get('ok')) and r_low.get('stage') == 'confirmed',
   '天然低位样本仍能正常判为 confirmed（功能没被改坏）',
   'score=%.1f' % float(r_low.get('score') or 0.0))

p('')
p('[3] 把常量临时改回 0.75：这两个样本在旧门槛下应当被放行')
_old = B.PROBE_POS_MAX
try:
    B.PROBE_POS_MAX = 0.75
    old_below = TI.detect_probe(mk(lo_lv))
    old_above = TI.detect_probe(mk(hi_lv))
finally:
    B.PROBE_POS_MAX = _old
for tag, r in (('刚低于线', old_below), ('刚高于线', old_above)):
    p('    旧门槛 0.75：%-8s reason=%-10s ok=%-5s score=%.1f'
      % (tag, r.get('reason') or '-', bool(r.get('ok')), float(r.get('score') or 0.0)))
ck(not str(old_above.get('reason') or '').startswith('pos>'),
   '旧门槛下「刚高于线」样本被放行 → 差异确实来自本次改动',
   'old reason=%s' % (old_above.get('reason') or '-'))

# --- 只改了这一处参数的回归证明 ------------------------------------------
p('')
p('[4] 与 .bak_before_probe_pos35 逐项比对（证明只动了 PROBE_POS_MAX 一处）')


def const_map(path):
    d = {}
    for line in io.open(path, 'r', encoding='utf-8'):
        line = line.strip()
        for pre in ('PROBE_', 'DIST_'):
            if line.startswith(pre) and '=' in line:
                name = line.split('=')[0].strip()
                val = line.split('=', 1)[1].split('#')[0].strip()
                d[name] = val
    return d


new_c = const_map(BASE)
old_c = const_map(BAK)
diff = sorted(k for k in set(new_c) | set(old_c) if new_c.get(k) != old_c.get(k))
p('    常量总数：新 %d / 旧 %d ｜ 有差异的：%s' % (len(new_c), len(old_c), diff or '无'))
ck(diff == ['PROBE_POS_MAX'], '差异只有 PROBE_POS_MAX 一项', 'diff=%s' % diff)
ck(old_c.get('PROBE_POS_MAX') == '0.75' and new_c.get('PROBE_POS_MAX') == '0.35',
   '新旧值分别为 0.75 / 0.35',
   '%s -> %s' % (old_c.get('PROBE_POS_MAX'), new_c.get('PROBE_POS_MAX')))
ck(all(new_c[k] == old_c[k] for k in new_c if k != 'PROBE_POS_MAX'),
   '其余 PROBE_* / DIST_* 常量逐字未变')

p('')
p('[5] 出货形态未受牵连')

d_mid = TI.detect_distribution_pattern(mk(8.80))
p('    detect_distribution_pattern(pos≈0.57 样本) reason=%s type=%s score=%.1f'
  % (d_mid.get('reason') or '-', d_mid.get('type') or '-', float(d_mid.get('score') or 0.0)))
ck(B.DIST_POS_HIGH == 0.65, 'DIST_POS_HIGH 仍是 0.65', '实际=%s' % B.DIST_POS_HIGH)

p('')
p('=' * 92)
p('总计：PASS %d ｜ FAIL %d' % (PASS[0], FAIL[0]))
p('=' * 92)

io.open(r'D:\QuantMonitorV6\tools\probe_pos35_verify.txt', 'w', encoding='utf-8').write('\n'.join(OUT))
sys.exit(1 if FAIL[0] else 0)
