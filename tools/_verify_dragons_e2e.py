# -*- coding: utf-8 -*-
"""端到端验收：用真实引擎的 _dragon_key 给 2026-10-09 每个板块排龙一/龙二/龙三，
并标出封单额真正决定名次的组。"""
import sqlite3
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

from services.board_anomaly_engine import _dragon_key   # noqa: E402

DB = r'D:\QuantMonitorV6\data\limit_up_reason.db'
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
recs = [dict(r) for r in con.execute(
    "SELECT code,name,date,time,lbc,fund,zbc,pct_chg,industry FROM "
    "limit_up_reasons WHERE date='20261009'")]
con.close()
print('2026-10-09 涨停 %d 只' % len(recs))

pct = {r['code']: r['pct_chg'] or 0 for r in recs}
grp = defaultdict(list)
for r in recs:
    grp[(r['industry'] or '未知')].append(r)

imap = {}
for r in recs:
    imap.setdefault(r['industry'] or '未知', []).append(r)

print()
print('=' * 84)
print('按行业分组，龙一/龙二/龙三（真实 _dragon_key 排序）')
print('=' * 84)
decided_by_fund = []
for ind, mem in sorted(grp.items(), key=lambda kv: -len(kv[1])):
    if len(mem) < 3:
        continue
    ordered = sorted(mem, key=lambda r: _dragon_key(r, pct))
    top3 = ordered[:3]

    # 检查第 4 级（封单额）是否真的决定过名次：
    # 拿掉 fund 重排，看顺序有没有变
    def key_no_fund(r):
        t = r.get('time') or ''
        return (0 if t else 1, -(r.get('lbc') or 0), t or '99:99',
                -(pct.get(r['code'], -999)))
    alt = sorted(mem, key=key_no_fund)[:3]
    changed = [a['code'] for a, b in zip(top3, alt) if a['code'] != b['code']]
    if changed:
        decided_by_fund.append(ind)

    print()
    print('  【%s】%d 家' % (ind, len(mem)))
    for i, r in enumerate(top3):
        tag = ('🐉一', '🐉二', '🐉三')[i]
        print('    %s %-8s %s  %2d板  首封%-8s 封单%7.4f亿 炸板%d'
              % (tag, r['name'], r['code'], r['lbc'] or 0,
                 r['time'] or '--', (r['fund'] or 0) / 1e8, r['zbc'] or 0))

print()
print('=' * 84)
print('封单额真正改变过名次的板块：%s'
      % ('、'.join(decided_by_fund) if decided_by_fund
         else '今天没有（前 3 级已分出胜负）'))
print('=' * 84)
