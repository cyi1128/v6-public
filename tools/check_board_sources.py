# -*- coding: utf-8 -*-
"""核查两件事：
1) 金铲子(辅助) golden_shovel_scanner 依赖的东财主力净流入接口是否可用
2) 它写的 golden_spade.duckdb 现在是什么状态
3) 板块异动用的涨停库/腾讯源是否正常
"""
import os
import sys
import time

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")

print('=' * 70)
print('1) 东财主力净流入接口 (金铲子辅助的唯一数据源)')
print('=' * 70)
try:
    from utils.http_market_data import eastmoney_request
    params = {"pn": "1", "pz": "100", "po": "1", "np": "1", "fltt": "2",
              "invt": "2", "fid": "f62",
              "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
              "fields": "f12,f14,f2,f3,f6,f7,f10,f15,f16,f17,f62,f100"}
    ok = 0
    for i in range(3):
        try:
            d = eastmoney_request("/api/qt/clist/get", params, timeout=15)
            diff = (d or {}).get("data", {}).get("diff", []) if isinstance(d, dict) else []
            print('  第%d次: 返回 %d 条 %s' % (i + 1, len(diff),
                  ('样本 ' + str(diff[0].get('f14'))) if diff else ''))
            if diff:
                ok += 1
        except Exception as e:
            print('  第%d次: 失败 %s: %s' % (i + 1, type(e).__name__, str(e)[:90]))
        time.sleep(1)
    print('  >>> 3 次中成功 %d 次' % ok)
    print('  >>> 结论: %s' % ('接口可用' if ok else '接口不可用 —— 金铲子(辅助)每5分钟空跑一次'))
except Exception as e:
    print('  导入失败:', e)

print()
print('=' * 70)
print('2) golden_spade.duckdb 状态')
print('=' * 70)
p = r"D:\QuantMonitorV6\data\cache\golden_spade.duckdb"
if os.path.exists(p):
    print('  文件存在，大小 %.1f KB，修改时间 %s' % (
        os.path.getsize(p) / 1024.0,
        time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p)))))
    try:
        import duckdb
        c = duckdb.connect(p, read_only=True)
        n = c.execute('SELECT COUNT(*) FROM golden_spade').fetchone()[0]
        ft = c.execute('SELECT MAX(found_time) FROM golden_spade').fetchone()[0]
        print('  行数 %d，最新 found_time %s' % (n, ft))
        c.close()
    except Exception as e:
        print('  读取失败:', e)
else:
    print('  文件不存在 —— 从未成功写入过')

print()
print('=' * 70)
print('3) 板块异动数据源')
print('=' * 70)
try:
    from services.board_anomaly_engine import get_board_anomaly
    t0 = time.time()
    d = get_board_anomaly(force=True)
    print('  ok=%s  date=%s  ludate=%s  涨停 %s 只  题材 %d  行业 %d  耗时 %.2fs' % (
        d.get('ok'), d.get('date'), d.get('ludate'), d.get('lu_count'),
        len(d.get('themes') or []), len(d.get('industries') or []),
        time.time() - t0))
    print('  error=%s' % (d.get('error') or '无'))
    for r in (d.get('themes') or [])[:5]:
        print('   %-14s 家数%-3d 均涨%5.2f%% 龙头 %s' % (
            r['name'], r['count'], r['avg_pct'], r['lead_name']))
except Exception as e:
    import traceback
    traceback.print_exc()

print()
print('=' * 70)
print('4) 涨停原因库历史覆盖（板块异动做时间维度就靠它）')
print('=' * 70)
try:
    import sqlite3
    c = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
    r = c.execute('SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date) '
                  'FROM limit_up_reasons').fetchone()
    print('  总行 %d，交易日 %d 个，范围 %s ~ %s' % r)
    rows = c.execute('SELECT date, COUNT(*) FROM limit_up_reasons '
                     'GROUP BY date ORDER BY date DESC LIMIT 12').fetchall()
    print('  近 12 个交易日涨停家数:')
    print('   ', '  '.join('%s:%d' % (d[4:], n) for d, n in rows))
    c.close()
except Exception as e:
    print('  失败:', e)
