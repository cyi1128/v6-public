# -*- coding: utf-8 -*-
"""验证 minute_kline.duckdb：表结构 + 当日VWAP手算核对"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
import duckdb
from services import minute_kline as mk

DB = mk.STORE_PATH
print("DB path:", DB)
con = duckdb.connect(DB, read_only=True)
print("TABLES:", [r[0] for r in con.execute("SHOW TABLES").fetchall()])
print("DESCRIBE:")
for r in con.execute("DESCRIBE minute_kline").fetchall():
    print("  ", r[0], r[1])
print("count:", con.execute("SELECT COUNT(*) FROM minute_kline").fetchone())
print("sample:")
print(con.execute("SELECT * FROM minute_kline WHERE code='000811' ORDER BY datetime LIMIT 2").fetchall())
con.close()

# 手算核对 000811 在 2026-09-15 的当日VWAP
con = duckdb.connect(DB, read_only=True)
df = con.execute("""
  SELECT high, low, close, volume FROM minute_kline
  WHERE code='000811' AND substr(datetime,1,10)='2026-09-15'
""").df()
con.close()
typ = (df['high']+df['low']+df['close'])/3.0
manual_vwap = (typ*df['volume']).sum()/df['volume'].sum()
print(f"\n000811 @2026-09-15  bar数={len(df)}  手算当日VWAP={manual_vwap:.4f}")

# load_day_vwap 接口
d = mk.load_day_vwap('000811', '2026-08-27', '2026-09-15')
print("load_day_vwap 天数:", len(d))
print("2026-09-15 接口值:", d.get('2026-09-15'), " 应≈", round(manual_vwap,4))
print("前3天:", list(d.items())[:3])
