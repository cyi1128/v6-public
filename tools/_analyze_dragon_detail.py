# -*- coding: utf-8 -*-
"""精钻选入：把「绝对封单额」和「封单强度(封单/流通市值)」两种口径排一遍，
看名次差多少；同时看炸板次数换掉「涨幅兜底」后有没有变化。"""
import sqlite3
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

DB = r'D:\QuantMonitorV6\data\limit_up_reason.db'
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
recs = [dict(r) for r in con.execute(
    "SELECT code,name,time,lbc,fund,amount,hs,zbc,ltsz,industry,reason "
    "FROM limit_up_reasons WHERE date='20261009' AND fund>0")]
con.close()
print('2026-10-09 有封单额的涨停股：%d 只' % len(recs))

pct = {r['code']: 10.0 for r in recs}


def k_now(r):
    """现行 _dragon_key"""
    t = r.get('time') or ''
    return (0 if t else 1, -(r.get('lbc') or 0), t or '99:99',
            -(r.get('fund') or 0.0))


def k_new(r):
    """建议口径：连板 → 首封 → 炸板少优先 → 封单强度(封单/流通市值)"""
    t = r.get('time') or ''
    q = (r.get('fund') or 0.0) / (r.get('ltsz') or 1.0)
    return (0 if t else 1, -(r.get('lbc') or 0), t or '99:99',
            r.get('zbc') or 0, -q)


print()
print('=' * 100)
print('一、封单额绝对值 vs 封单强度（封单/流通市值）')
print('=' * 100)
print('%-9s %-4s %-8s %8s %9s %8s   %8s' %
      ('名称', '连板', '首封', '封单(亿)', '流通市值(亿)', '封单强度', '换手%'))
print('-' * 100)
for r in sorted(recs, key=lambda r: -(r['fund'] or 0))[:12]:
    q = (r['fund'] or 0) / (r['ltsz'] or 1)
    print('%-9s %-4s %-8s %8.3f %9.1f %7.2f%%   %6.2f' %
          (r['name'], r['lbc'], r['time'], r['fund'] / 1e8,
           (r['ltsz'] or 0) / 1e8, q * 100, r['hs'] or 0))

print()
print('  ↑ 按【绝对封单额】排，前 12 名')
print()
print('%-9s %-4s %-8s %8s %9s %8s   %8s' %
      ('名称', '连板', '首封', '封单(亿)', '流通市值(亿)', '封单强度', '换手%'))
print('-' * 100)
for r in sorted(recs, key=lambda r: -((r['fund'] or 0) / (r['ltsz'] or 1)))[:12]:
    q = (r['fund'] or 0) / (r['ltsz'] or 1)
    print('%-9s %-4s %-8s %8.3f %9.1f %7.2f%%   %6.2f' %
          (r['name'], r['lbc'], r['time'], r['fund'] / 1e8,
           (r['ltsz'] or 0) / 1e8, q * 100, r['hs'] or 0))
print('  ↑ 按【封单强度】排，前 12 名 —— 两张表重合的没几个')

print()
print('=' * 100)
print('二、现行排序 vs 建议排序，前 12 名有没有变')
print('=' * 100)
a = [r['code'] for r in sorted(recs, key=lambda r: k_now(r))[:12]]
b = [r['code'] for r in sorted(recs, key=lambda r: k_new(r))[:12]]
an = {r['code']: r['name'] for r in recs}
print('  现行：' + ' '.join(an[c] for c in a))
print('  建议：' + ' '.join(an[c] for c in b))
print('  前 12 名重合 %d 个' % len(set(a) & set(b)))

print()
print('=' * 100)
print('三、炸板次数：现在算了但不参与排序')
print('=' * 100)
zb = [r for r in recs if (r['zbc'] or 0) > 0]
print('  今天 69 只里有 %d 只炸过板：' % len(zb))
for r in sorted(zb, key=lambda r: -(r['zbc'] or 0))[:8]:
    print('    %-9s %2d板 炸板%2d次 首封%-8s 封单%.3f亿 换手%.2f%%'
          % (r['name'], r['lbc'], r['zbc'], r['time'],
             r['fund'] / 1e8, r['hs'] or 0))

print()
print('=' * 100)
print('四、板块内「谁先动」和「谁板多」打架的案例')
print('=' * 100)
grp = defaultdict(list)
for r in recs:
    grp[r['industry'] or '未知'].append(r)
for ind, mem in sorted(grp.items(), key=lambda kv: -len(kv[1])):
    if len(mem) < 3:
        continue
    by_lbc = max(mem, key=lambda r: (r['lbc'], ))
    by_time = min(mem, key=lambda r: r['time'] or '99:99')
    if by_lbc['code'] != by_time['code']:
        print('  【%s】' % ind)
        print('    板最高：%s %d板 首封%s' % (by_lbc['name'], by_lbc['lbc'],
                                            by_lbc['time']))
        print('    先发动：%s %d板 首封%s  ← 板少但先封' % (
            by_time['name'], by_time['lbc'], by_time['time']))

print()
print('=' * 100)
print('五、连板高度分布（高位板 = 接力风险，不该无条件排最前）')
print('=' * 100)
d = defaultdict(int)
for r in recs:
    d[r['lbc'] or 0] += 1
for k in sorted(d, reverse=True):
    print('  %2d板：%2d 只' % (k, d[k]))
