# -*- coding: utf-8 -*-
"""验证：封单额覆盖到哪些日期 + 龙一龙二龙三排序是否真的用上了封单额。"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

DB = r'D:\QuantMonitorV6\data\limit_up_reason.db'
con = sqlite3.connect(DB)

print('=' * 78)
print('一、封单额覆盖到哪些日期')
print('=' * 78)
rows = con.execute(
    "SELECT date, SUM(CASE WHEN fund IS NOT NULL AND fund!=0 THEN 1 ELSE 0 END),"
    " COUNT(*) FROM limit_up_reasons GROUP BY date "
    "ORDER BY date DESC LIMIT 22").fetchall()
for d, c, t in rows:
    print('  %s  封单额 %3d / %3d  %s' % (d, c, t, 'OK' if c else '—'))

print()
print('  有封单额的总行数 / 总行数：')
a, b = con.execute(
    "SELECT SUM(CASE WHEN fund IS NOT NULL AND fund!=0 THEN 1 ELSE 0 END),"
    " COUNT(*) FROM limit_up_reasons").fetchone()
print('    %d / %d' % (a, b))

print()
print('=' * 78)
print('二、龙一 / 龙二 / 龙三（用真实引擎函数，2026-10-09）')
print('=' * 78)
for code, name, lbc, tm, fund in con.execute(
        "SELECT code,name,lbc,time,fund FROM limit_up_reasons "
        "WHERE date='20261009' ORDER BY lbc DESC, fund DESC LIMIT 8"):
    print('  %s %-8s %2d板  首封%-8s 封单 %.4f亿'
          % (code, name, lbc or 0, tm or '--', (fund or 0) / 1e8))
con.close()

# 直接用引擎的排序键复算，确认封单额这一级真的参与
print()
print('=' * 78)
print('三、引擎排序键复算（模拟 _dragon_key，看第 4 级有没有生效）')
print('=' * 78)
try:
    from services.board_anomaly_engine import _dragon_key   # noqa: E402
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    recs = [dict(r) for r in con.execute(
        "SELECT code,name,lbc,time,fund,pct_chg FROM limit_up_reasons "
        "WHERE date='20261009'")]
    con.close()
    pct = {r['code']: r['pct_chg'] for r in recs}
    # 只取同身位、同首封的那一组来检验第 4 级
    from collections import defaultdict
    grp = defaultdict(list)
    for r in recs:
        grp[(r['lbc'], r['time'])].append(r)
    hit = [k for k, v in grp.items() if len(v) > 1]
    if hit:
        print('  同一（连板,首封时间）的组，看封单额是否分出先后：')
        for k in hit[:5]:
            v = sorted(grp[k], key=lambda r: _dragon_key(r, pct))
            print('    %s板 %s →' % (k[0], k[1]),
                  ' > '.join('%s(%.3f亿)' % (r['name'], (r['fund'] or 0) / 1e8)
                             for r in v))
    else:
        print('  今天没有（连板+首封时间）完全相同的股票，')
        print('  → 第 4 级封单额今天没被触发（说明前 3 级已分出胜负），这是正常的')
    print()
    print('  用引擎键排序的今日前 10（含封单额参与）：')
    for i, r in enumerate(sorted(recs, key=lambda r: _dragon_key(r, pct))[:10], 1):
        print('    %2d. %-8s %2d板 首封%-8s 封单 %.4f亿'
              % (i, r['name'], r['lbc'] or 0, r['time'] or '--',
                 (r['fund'] or 0) / 1e8))
except Exception as e:
    import traceback
    traceback.print_exc()
