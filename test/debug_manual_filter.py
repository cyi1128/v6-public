# -*- coding: utf-8 -*-
"""手动筛选调试脚本 - 逐步排查"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.manual_filter_engine import ManualFilterConfig, ManualFilterEngine

print("=" * 60)
print("手动筛选调试 - 逐步排查")
print("=" * 60)

# 测试1: 只开启价格和市值
print("\n[测试1] 只开启价格5-60 + 市值30-230亿")
config = ManualFilterConfig()
config.price_enabled = True
config.price_min = 5
config.price_max = 60
config.market_cap_enabled = True
config.market_cap_min = 30
config.market_cap_max = 230

engine = ManualFilterEngine()
results = engine.filter(config)
print(f"结果: {len(results)}只")
if results:
    print(f"示例: {results[0].get('code')} {results[0].get('name')} 价格={results[0].get('price')} 市值={results[0].get('market_cap')}")

# 测试2: 价格+市值+换手率
print("\n[测试2] 价格5-60 + 市值30-230亿 + 换手率3-25%")
config2 = ManualFilterConfig()
config2.price_enabled = True
config2.price_min = 5
config2.price_max = 60
config2.market_cap_enabled = True
config2.market_cap_min = 30
config2.market_cap_max = 230
config2.turnover_enabled = True
config2.turnover_min = 3
config2.turnover_max = 25

results2 = engine.filter(config2)
print(f"结果: {len(results2)}只")

# 测试3: 只开启均线多头（需要K线）
print("\n[测试3] 价格5-60 + 市值30-230亿 + 均线多头MA5>MA9>MA20")
config3 = ManualFilterConfig()
config3.price_enabled = True
config3.price_min = 5
config3.price_max = 60
config3.market_cap_enabled = True
config3.market_cap_min = 30
config3.market_cap_max = 230
config3.ma_bullish_enabled = True

results3 = engine.filter(config3)
print(f"结果: {len(results3)}只")
if results3:
    for s in results3[:5]:
        print(f"  {s.get('code')} {s.get('name')} 价格={s.get('price')} MA状态={s.get('ma_status')}")

# 测试4: 只开启KDJ
print("\n[测试4] 价格5-60 + 市值30-230亿 + KDJ J值-50到150（宽松）")
config4 = ManualFilterConfig()
config4.price_enabled = True
config4.price_min = 5
config4.price_max = 60
config4.market_cap_enabled = True
config4.market_cap_min = 30
config4.market_cap_max = 230
config4.kdj_enabled = True
config4.kdj_j_min = -50
config4.kdj_j_max = 150

results4 = engine.filter(config4)
print(f"结果: {len(results4)}只")
if results4:
    for s in results4[:5]:
        print(f"  {s.get('code')} {s.get('name')} KDJ状态={s.get('kdj_status')}")

# 测试5: 单只股票K线验证
print("\n[测试5] 单只股票K线验证 600519")
from utils.kline_provider import get_daily_kline
from utils.indicators import calc_ma_series, calc_kdj_series
import pandas as pd

kline = get_daily_kline('600519')
if kline:
    closes = kline.get('close', [])
    print(f"K线数量: {len(closes)}")
    if len(closes) > 20:
        ma5 = calc_ma_series(closes, 5)
        ma9 = calc_ma_series(closes, 9)
        ma20 = calc_ma_series(closes, 20)
        kdj = calc_kdj_series(kline.get('high', []), kline.get('low', []), closes, n=13, m1=3, m2=3)

        def _last(series):
            if series is None or len(series) == 0:
                return None
            v = series.iloc[-1] if hasattr(series, 'iloc') else series[-1]
            return float(v) if not pd.isna(v) else None

        print(f"MA5={_last(ma5)}, MA9={_last(ma9)}, MA20={_last(ma20)}")
        print(f"KDJ K={_last(kdj[0])}, D={_last(kdj[1])}, J={_last(kdj[2])}")
        print(f"最新收盘={closes[-1]}")
else:
    print("K线获取失败")

print("\n" + "=" * 60)
print("调试完成")
