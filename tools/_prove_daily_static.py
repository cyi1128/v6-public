# -*- coding: utf-8 -*-
"""实证：日K建仓表里的「现价/涨跌幅」是盘后扫描快照，还是实时价"""
import sys, os, datetime
sys.path.insert(0, r'D:\QuantMonitorV6')

print('当前时间:', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print()

from services.band_pattern_engine import query_signals
sigs = query_signals() or []
print('query_signals() 返回:', len(sigs), '条')

# 只看会进表格的（建仓触发 / 等待确认）
show = [s for s in sigs if s.get('signal_level') in ('建仓触发', '等待确认')]
print('其中会进表格(建仓触发/等待确认):', len(show), '条')
print()

codes = [s['code'] for s in show[:8]]
from utils.http_market_data import get_realtime_quotes_http
q = get_realtime_quotes_http(codes) or {}

print('%-8s %-8s | %-22s | %-22s | %s' % ('代码', '名称', 'DB里的push_price/pct', '接口实时price/pct', '是否一致'))
print('-' * 100)
for s in show[:8]:
    c = s['code']
    v = q.get(c) or {}
    db_p = s.get('push_price') or 0
    db_pct = s.get('push_pct') or 0
    rt_p = v.get('price') or 0
    rt_pct = v.get('pct_chg') or 0
    same = (abs(db_p - rt_p) < 0.005) if rt_p else None
    print('%-8s %-8s | %8.2f / %+7.2f%%     | %8.2f / %+7.2f%%     | %s'
          % (c, (s.get('name') or '')[:6], db_p, db_pct, rt_p, rt_pct,
             '一致' if same else ('不一致' if same is False else '无实时价')))

print()
print('=== DB 里 pattern_record 的写入时间/字段 ===')
import duckdb
p = r'D:\QuantMonitorV6\data\cache\band_pattern.db'
con = duckdb.connect(p, read_only=True)
print('表:', [r[0] for r in con.execute('show tables').fetchall()])
cols = [c[0] for c in con.execute('describe pattern_record').fetchall()]
print('列:', cols)
n = con.execute('select count(*) from pattern_record').fetchone()[0]
print('总记录:', n)
for r in con.execute('select * from pattern_record limit 3').fetchall():
    print('  样例:', dict(zip(cols, r)))
if 'scan_time' in cols:
    print('  scan_time 分布:', con.execute('select scan_time, count(*) from pattern_record group by scan_time').fetchall())
if 'valid_until' in cols:
    print('  valid_until 分布:', con.execute('select valid_until, count(*) from pattern_record group by valid_until').fetchall())
print('  signal_level 分布:', con.execute('select signal_level, count(*) from pattern_record group by signal_level').fetchall())
con.close()
