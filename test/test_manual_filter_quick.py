# -*- coding: utf-8 -*-
"""V6.0 Pro 手动筛选快速验收 - 验证条件正确性+命中率功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.manual_filter_engine import ManualFilterConfig, ManualFilterEngine
from datetime import datetime
import random

print("=" * 70)
print("V6.0 Pro 手动筛选快速验收")
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

engine = ManualFilterEngine()
results = {}

# ===== 不需要K线的条件（快速） =====
print("\n--- 基础条件测试（不需要K线）---")

# 1. 股价5-60
c = ManualFilterConfig()
c.price_enabled = True
c.price_min, c.price_max = 5, 60
r = engine.filter(c)
results['股价5-60元'] = len(r)
print(f"1. 股价5-60元: {len(r)}只")

# 2. 市值30-230亿
c = ManualFilterConfig()
c.market_cap_enabled = True
c.market_cap_min, c.market_cap_max = 30, 230
r = engine.filter(c)
results['市值30-230亿'] = len(r)
print(f"2. 市值30-230亿: {len(r)}只")

# 3. 换手率5-20%
c = ManualFilterConfig()
c.turnover_enabled = True
c.turnover_min, c.turnover_max = 5, 20
r = engine.filter(c)
results['换手率5-20%'] = len(r)
print(f"3. 换手率5-20%: {len(r)}只")

# 4. 振幅3-15%
c = ManualFilterConfig()
c.amplitude_enabled = True
c.amplitude_min, c.amplitude_max = 3, 15
r = engine.filter(c)
results['振幅3-15%'] = len(r)
print(f"4. 振幅3-15%: {len(r)}只")

# ===== 需要K线的条件（含价格过滤减少数量） =====
print("\n--- 技术条件测试（需要K线，含价格5-60过滤）---")

# 5. 均线多头
c = ManualFilterConfig()
c.price_enabled = True
c.price_min, c.price_max = 5, 60
c.ma_bullish_enabled = True
r = engine.filter(c)
results['均线多头'] = len(r)
print(f"5. 均线多头MA5>MA9>MA20: {len(r)}只")
if r:
    s = random.choice(r)
    print(f"   示例: {s['code']} {s['name']} MA状态={s.get('ma_status')}")

# 6. KDJ J -20到10
c = ManualFilterConfig()
c.price_enabled = True
c.price_min, c.price_max = 5, 60
c.kdj_enabled = True
c.kdj_j_min, c.kdj_j_max = -20, 10
r = engine.filter(c)
results['KDJ J-20~10'] = len(r)
print(f"6. KDJ J值-20到10: {len(r)}只")
if r:
    s = random.choice(r)
    print(f"   示例: {s['code']} {s['name']} KDJ状态={s.get('kdj_status')}")

# 7. 量比>1.2
c = ManualFilterConfig()
c.price_enabled = True
c.price_min, c.price_max = 5, 60
c.volume_ratio_enabled = True
c.volume_ratio_min, c.volume_ratio_max = 1.2, 50
r = engine.filter(c)
results['量比>1.2'] = len(r)
print(f"7. 量比>1.2: {len(r)}只")

# 8. 连续3日上涨≥1%
c = ManualFilterConfig()
c.price_enabled = True
c.price_min, c.price_max = 5, 60
c.continuous_up_enabled = True
c.continuous_up_days = 3
c.continuous_up_min_pct = 1.0
r = engine.filter(c)
results['连续3日上涨≥1%'] = len(r)
print(f"8. 连续3日上涨≥1%: {len(r)}只")

# ===== 宽松模式组合测试（命中率功能） =====
print("\n--- 宽松模式组合测试（命中率功能验证）---")

c = ManualFilterConfig()
c.name = '宽松模式测试'
c.price_enabled = True
c.price_min, c.price_max = 5, 60
c.market_cap_enabled = True
c.market_cap_min, c.market_cap_max = 30, 230
c.turnover_enabled = True
c.turnover_min, c.turnover_max = 3, 25
c.ma_bullish_enabled = True
c.kdj_enabled = True
c.kdj_j_min, c.kdj_j_max = -20, 30
c.volume_ratio_enabled = True
c.volume_ratio_min, c.volume_ratio_max = 1.0, 50
c.continuous_up_enabled = True
c.continuous_up_days = 2
c.continuous_up_min_pct = 0.5
c.strict_mode = False  # 宽松模式
c.min_hit_rate = 0.4   # 至少命中40%

r = engine.filter(c)
results['宽松模式组合'] = len(r)
print(f"宽松模式组合(7个K线条件, 最低40%命中): {len(r)}只")

if r:
    print(f"\n命中率分布:")
    hit_rates = [s.get('hit_rate', 0) for s in r]
    print(f"  最高命中率: {max(hit_rates):.0f}%")
    print(f"  最低命中率: {min(hit_rates):.0f}%")
    print(f"  平均命中率: {sum(hit_rates)/len(hit_rates):.0f}%")

    print(f"\nTOP10 高命中率股票:")
    print(f"{'代码':<8}{'名称':<10}{'价格':>8}{'命中':>10}{'命中率':>8}  命中条件")
    print("-" * 70)
    for s in r[:10]:
        hits = ','.join(s.get('condition_hits', []))
        print(f"{s['code']:<8}{s['name'][:8]:<10}{s['price']:>8.2f}{s.get('hit_count',0):>3}/{s.get('total_conditions',0):<3}{s.get('hit_rate',0):>7.0f}%  {hits}")

# ===== 汇总 =====
print(f"\n{'='*70}")
print("验收汇总")
print("=" * 70)
print(f"{'条件':<20}{'数量':>8}{'状态':>10}")
print("-" * 42)
for name, count in results.items():
    status = "✅" if count > 0 else "⚠️"
    print(f"{name:<20}{count:>8}{status:>10}")

passed = sum(1 for v in results.values() if v > 0)
print(f"\n通过: {passed}/{len(results)} 个条件有结果")
print("=" * 70)
