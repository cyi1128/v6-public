# -*- coding: utf-8 -*-
"""诊断：引擎 _load_bars 与 kline_cache 的末日/根数/成交量口径是否一致（一次性）。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
import duckdb  # noqa: E402
import services.band_pattern_engine as E  # noqa: E402

for cd in ('600519', '002409', '601~'[:6]):
    b = E._load_bars(cd)
    if not b:
        print(cd, '空')
        continue
    print('引擎 %s 共%d根 末日=%s 末3:' % (cd, len(b), str(b[-1].get('date'))[:10]),
          [(str(x.get('date'))[:10], x.get('close'), x.get('volume')) for x in b[-3:]])

con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
for cd in ('600519', '002409'):
    r = con.execute("SELECT date,close,volume FROM kline_cache WHERE code=? ORDER BY date DESC LIMIT 3",
                    [cd]).fetchall()
    n = con.execute("SELECT COUNT(*) FROM kline_cache WHERE code=?", [cd]).fetchone()[0]
    print('缓存 %s 共%d根 末3:' % (cd, n), r)
print('缓存全市场末日分布:',
      con.execute("SELECT date, COUNT(*) FROM kline_cache WHERE date >= '2026-09-30' GROUP BY date ORDER BY date").fetchall())
con.close()