# -*- coding: utf-8 -*-
"""用涨停库真实历史，演示「板块异动加时间维度」后能看到什么

现在板块异动只看 MAX(date) 一天 -> 只能看到「今天谁涨停多」
加上时间维度后 -> 能看到「这个题材是第几天、在升温还是退潮、资金从哪切到哪」

本脚本只读取，不写任何库。
"""
import os
import re
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")

KW_MIN, KW_MAX = 2, 12
SPLIT = re.compile(r'[+＋·、/]')


def split_reason(reason):
    out, seen = [], set()
    for p in SPLIT.split(reason or ''):
        p = p.strip().strip('* ')
        for ch in ('“', '”', '‘', '’', '「', '」'):
            p = p.replace(ch, '')
        p = p.strip()
        if KW_MIN <= len(p) <= KW_MAX and p not in seen:
            seen.add(p)
            out.append(p)
    return out


c = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")

# 近 10 个交易日
dates = [r[0] for r in c.execute(
    'SELECT DISTINCT date FROM limit_up_reasons ORDER BY date DESC LIMIT 10')]
dates = sorted(dates)
print('统计窗口: %s ~ %s（%d 个交易日）' % (dates[0], dates[-1], len(dates)))

# 题材 -> {date: (家数, 龙头)}
mat = defaultdict(dict)
for d in dates:
    rows = c.execute(
        'SELECT code,name,reason,time,lbc,fund,pct_chg FROM limit_up_reasons '
        'WHERE date=?', (d,)).fetchall()
    for kw in set(k for r in rows for k in split_reason(r[2])):
        mem = [r for r in rows if kw in split_reason(r[2])]
        if len(mem) < 2:
            continue
        def key(r):
            t = (r[3] or '').strip()
            return (0 if t else 1, -(r[4] or 0), t or '99:99', -(r[5] or 0))
        lead = sorted(mem, key=key)[0]
        mat[kw][d] = (len(mem), lead[1])
c.close()

# 只看窗口内至少出现过 3 次的题材（有持续性才值得看）
items = [(kw, v) for kw, v in mat.items() if len(v) >= 3]
items.sort(key=lambda x: (-len(x[1]), -sum(n for n, _ in x[1].values())))

print('\n出现 >=3 天的题材共 %d 个，列前 12 个：\n' % len(items))
hdr = '%-12s %s' % ('题材', ' '.join('%5s' % d[4:] for d in dates))
print(hdr)
print('-' * len(hdr))
for kw, v in items[:12]:
    line = '%-12s' % kw
    for d in dates:
        n = v.get(d, (0, ''))[0]
        line += ' %5s' % (n if n else '·')
    print(line)

print('\n\n【最近一天 vs 前一天：谁在进场、谁在退潮】')
today, prev = dates[-1], dates[-2]
t_cnt = {kw: v.get(today, (0,))[0] for kw, v in mat.items()}
p_cnt = {kw: v.get(prev, (0,))[0] for kw, v in mat.items()}
new_in = sorted([k for k in t_cnt if t_cnt[k] >= 2 and p_cnt.get(k, 0) == 0],
                key=lambda k: -t_cnt[k])
fade = sorted([k for k in p_cnt if p_cnt[k] >= 2 and t_cnt.get(k, 0) == 0],
              key=lambda k: -p_cnt[k])
print('  今日新进(前排昨日无): %s' %
      ('、'.join('%s%d家' % (k, t_cnt[k]) for k in new_in[:8]) or '无'))
print('  昨日退潮(今日无):     %s' %
      ('、'.join('%s%d家' % (k, p_cnt[k]) for k in fade[:8]) or '无'))

print('\n\n【题材生命周期：连续异动天数 + 趋势】')
print('%-14s %6s %6s %8s %s' % ('题材', '连续', '今日', '昨日', '趋势'))
print('-' * 62)
for kw, v in items[:14]:
    # 连续天数（从最新往回数）
    run, i = 0, len(dates) - 1
    while i >= 0 and v.get(dates[i], (0,))[0] >= 2:
        run += 1
        i -= 1
    t = v.get(today, (0,))[0]
    p = v.get(prev, (0,))[0]
    if t > p:
        trend = '升温 +%d' % (t - p)
    elif t < p:
        trend = '退潮 %d' % (t - p)
    else:
        trend = '走平'
    if run >= 3:
        stage = '持续(%d日)' % run
    elif run == 2:
        stage = '发酵中'
    elif run == 1:
        stage = '首日/一日游?'
    else:
        stage = '今日未上榜'
    print('%-14s %6d %6d %8d %s  %s' % (kw, run, t, p, trend, stage))

print('\n\n【首日启动 且 今日 3 家以上】—— 这是「新题材」信号')
fresh = [(kw, t_cnt[kw]) for kw in mat
         if t_cnt.get(kw, 0) >= 3
         and all(mat[kw].get(dates[i], (0,))[0] < 2
                 for i in range(max(0, len(dates) - 4), len(dates) - 1))]
for kw, n in sorted(fresh, key=lambda x: -x[1]):
    print('  %-14s 今日 %d 家（前 3 日都未成板块）  龙头 %s'
          % (kw, n, mat[kw][today][1]))
if not fresh:
    print('  无')

print('\n\n【龙头连续性：今日龙一前几天是否也在榜】')
for kw, v in items[:8]:
    if today not in v:
        continue
    lead = v[today][1]
    appeared = [d[4:] for d in dates if d in mat[kw]
                and any(True for _ in [0])]
    print('  %-14s 今日龙一 %-8s 该题材近%d日出榜日: %s'
          % (kw, lead, len(dates),
             '、'.join(d[4:] for d in dates if d in mat[kw])))
