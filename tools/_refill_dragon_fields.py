# -*- coding: utf-8 -*-
"""把 fund 为空的交易日重新采集一遍（INSERT OR REPLACE 会覆盖旧行）。"""
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

DB = r'D:\QuantMonitorV6\data\limit_up_reason.db'

con = sqlite3.connect(DB)
try:
    bad = [r[0] for r in con.execute(
        "SELECT date FROM limit_up_reasons WHERE source='ths' "
        "GROUP BY date HAVING SUM(CASE WHEN fund IS NOT NULL AND fund!=0 "
        "THEN 1 ELSE 0 END)=0 ORDER BY date DESC").fetchall()]
    tot = con.execute("SELECT COUNT(DISTINCT date) FROM limit_up_reasons "
                      "WHERE source='ths'").fetchone()[0]
finally:
    con.close()

print('source=ths 共 %d 个交易日，其中封单额为空的 %d 个：%s'
      % (tot, len(bad), ', '.join(bad) if bad else '无'))

if not bad:
    print('无需回填')
    sys.exit(0)

from services.limit_up_collector import collect      # noqa: E402

print()
print('开始逐日重采（每日 2 次请求，失败不影响后续）')
print('-' * 78)
ok = 0
for d in bad:
    try:
        n = collect(d)
        if n:
            ok += 1
        time.sleep(1.2)          # 温和限速
    except Exception as e:
        print('  %s 失败: %s' % (d, str(e)[:90]))

print('-' * 78)
print('回填完成：%d / %d 天' % (ok, len(bad)))

con = sqlite3.connect(DB)
try:
    print()
    print('=' * 78)
    print('回填后核对')
    print('=' * 78)
    for col in ('fund', 'amount', 'hs', 'zbc', 'ltsz'):
        nn = con.execute(
            "SELECT COUNT(*) FROM limit_up_reasons WHERE %s IS NOT NULL "
            "AND %s != 0" % (col, col)).fetchone()[0]
        allr = con.execute('SELECT COUNT(*) FROM limit_up_reasons').fetchone()[0]
        print('  %-8s 有值 %5d / %d' % (col, nn, allr))
    print()
    print('  最近 6 个交易日封单额覆盖：')
    for d, c, t in con.execute(
            "SELECT date, SUM(CASE WHEN fund IS NOT NULL AND fund!=0 THEN 1 "
            "ELSE 0 END), COUNT(*) FROM limit_up_reasons WHERE source='ths' "
            "GROUP BY date ORDER BY date DESC LIMIT 6").fetchall():
        print('    %s  %3d / %d  %s' % (d, c, t, 'OK' if c else '空'))
finally:
    con.close()
