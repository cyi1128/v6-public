# -*- coding: utf-8 -*-
"""竞价快照历史 + 进程检查"""
import sys, os, json, datetime, subprocess
sys.path.insert(0, r'D:\QuantMonitorV6')

print('=== 当前时间 ===', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print()

print('=== 主程序进程 ===')
try:
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
                         capture_output=True, text=True, timeout=30).stdout
    for ln in out.strip().splitlines():
        if 'python' in ln.lower():
            print('  ', ln)
except Exception as e:
    print('  查询失败:', e)
print()

print('=== 竞价快照库：所有日期 ===')
p = r'D:\QuantMonitorV6\data\cache\auction_snapshot.duckdb'
print('  路径:', p, '大小:', os.path.getsize(p))
try:
    import duckdb
    con = duckdb.connect(p, read_only=True)
    tabs = con.execute("SHOW TABLES").fetchall()
    print('  表:', tabs)
    for t in tabs:
        tn = t[0]
        try:
            cols = [c[0] for c in con.execute(f'DESCRIBE {tn}').fetchall()]
            print(f'  -- {tn} 列: {cols}')
            rows = con.execute(f'SELECT * FROM {tn} ORDER BY 1 DESC LIMIT 30').fetchall()
            for r in rows:
                s = str(r)
                print('     ', s[:260])
        except Exception as e:
            print(f'  -- {tn} 读取失败: {e}')
    con.close()
except Exception as e:
    print('  duckdb 读取失败:', type(e).__name__, e)
