# -*- coding: utf-8 -*-
"""查当前时间 + 关键数据新鲜度"""
import os
import sys
import time
import sqlite3
from datetime import datetime

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")

print('当前时间: %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S %A'))

try:
    from utils import trade_calendar as tc
    today = datetime.now().date()
    print('今天是否交易日: %s' % tc.is_trading_day(today))
    print('最近交易日: %s' % tc.get_latest_trading_date())
except Exception as e:
    print('交易日历失败:', e)

print()
print('kline_cache 最新:')
import duckdb
c = duckdb.connect(r"D:\QuantMonitorV6\data\cache\kline_cache.duckdb", read_only=True)
r = c.execute('SELECT MAX(date), COUNT(DISTINCT date) FROM kline_cache').fetchone()
print('  最新日期 %s，共 %d 个交易日' % r)
rows = c.execute('SELECT date, COUNT(*) FROM kline_cache GROUP BY date '
                 'ORDER BY date DESC LIMIT 6').fetchall()
for d, n in rows:
    print('   %s  %d 只' % (d, n))
c.close()

print()
print('limit_up_reasons 最新 6 个日期:')
c = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
for d, n in c.execute('SELECT date, COUNT(*) FROM limit_up_reasons '
                      'GROUP BY date ORDER BY date DESC LIMIT 6'):
    print('   %s  %d 只' % (d, n))
c.close()

print()
print('相关库文件修改时间:')
for p in ['data\\limit_up_reason.db', 'data\\cache\\kline_cache.duckdb',
          'data\\cache\\golden_spade.duckdb', 'data\\cache\\picks_tracking.duckdb']:
    fp = os.path.join(r"D:\QuantMonitorV6", p)
    if os.path.exists(fp):
        print('   %-42s %s  %.1f MB' % (
            p, time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(fp))),
            os.path.getsize(fp) / 1048576.0))
    else:
        print('   %-42s 不存在' % p)
