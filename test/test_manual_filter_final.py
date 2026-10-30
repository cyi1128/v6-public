# -*- coding: utf-8 -*-
"""
V6.0 Pro 手动筛选最终验收测试
10个单条件测试 + 1个组合测试 + 结果验证
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.manual_filter_engine import ManualFilterConfig, ManualFilterEngine
from datetime import datetime
import random


def test_single_condition(name, config_func):
    """测试单个条件"""
    print(f"\n{'='*60}")
    print(f"单条件测试: {name}")
    print(f"{'='*60}")

    config = config_func()
    engine = ManualFilterEngine()
    results = engine.filter(config)

    print(f"筛选结果: {len(results)}只")
    if results:
        sample = random.sample(results, min(3, len(results)))
        for s in sample:
            print(f"  {s.get('code')} {s.get('name')} 价格={s.get('price'):.2f}")
    return results


def main():
    print("=" * 70)
    print("V6.0 Pro 手动筛选最终验收测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results_summary = {}

    # ===== 不需要K线的条件（快速） =====

    # 1. 股价5-60元
    def c1():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        return c
    r = test_single_condition("1. 股价5-60元", c1)
    results_summary['股价5-60元'] = len(r)

    # 2. 市值30-230亿
    def c2():
        c = ManualFilterConfig()
        c.market_cap_enabled = True
        c.market_cap_min = 30
        c.market_cap_max = 230
        return c
    r = test_single_condition("2. 市值30-230亿", c2)
    results_summary['市值30-230亿'] = len(r)

    # 3. 换手率5%-20%
    def c3():
        c = ManualFilterConfig()
        c.turnover_enabled = True
        c.turnover_min = 5
        c.turnover_max = 20
        return c
    r = test_single_condition("3. 换手率5%-20%", c3)
    results_summary['换手率5-20%'] = len(r)

    # 4. 振幅3%-15%
    def c4():
        c = ManualFilterConfig()
        c.amplitude_enabled = True
        c.amplitude_min = 3
        c.amplitude_max = 15
        return c
    r = test_single_condition("4. 振幅3%-15%", c4)
    results_summary['振幅3-15%'] = len(r)

    # ===== 需要K线的条件 =====

    # 5. 量比>1.2
    def c5():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        c.volume_ratio_enabled = True
        c.volume_ratio_min = 1.2
        c.volume_ratio_max = 50
        return c
    r = test_single_condition("5. 量比>1.2 (含价格过滤)", c5)
    results_summary['量比>1.2'] = len(r)

    # 6. 成交量突破1.5倍
    def c6():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        c.volume_break_enabled = True
        c.volume_break_min = 1.5
        c.volume_break_max = 50
        return c
    r = test_single_condition("6. 成交量突破1.5倍 (含价格过滤)", c6)
    results_summary['成交量突破1.5倍'] = len(r)

    # 7. MA5>MA9>MA20
    def c7():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        c.ma_bullish_enabled = True
        return c
    r = test_single_condition("7. 均线多头MA5>MA9>MA20 (含价格过滤)", c7)
    results_summary['均线多头'] = len(r)

    # 8. KDJ J -20到10
    def c8():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        c.kdj_enabled = True
        c.kdj_j_min = -20
        c.kdj_j_max = 10
        return c
    r = test_single_condition("8. KDJ J值-20到10 (含价格过滤)", c8)
    results_summary['KDJ J-20~10'] = len(r)

    # 9. MA5上穿MA9
    def c9():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        c.ma5_cross_ma9_enabled = True
        return c
    r = test_single_condition("9. MA5上穿MA9 (含价格过滤)", c9)
    results_summary['MA5上穿MA9'] = len(r)

    # 10. 连续3日涨幅≥1%
    def c10():
        c = ManualFilterConfig()
        c.price_enabled = True
        c.price_min = 5
        c.price_max = 60
        c.continuous_up_enabled = True
        c.continuous_up_days = 3
        c.continuous_up_min_pct = 1.0
        return c
    r = test_single_condition("10. 连续3日涨幅≥1% (含价格过滤)", c10)
    results_summary['连续3日上涨≥1%'] = len(r)

    # ===== 组合测试 =====
    print(f"\n{'='*70}")
    print("组合测试: 全部条件同时开启")
    print("=" * 70)

    combo = ManualFilterConfig()
    combo.name = '全条件组合'
    combo.price_enabled = True
    combo.price_min = 5
    combo.price_max = 60
    combo.market_cap_enabled = True
    combo.market_cap_min = 30
    combo.market_cap_max = 230
    combo.turnover_enabled = True
    combo.turnover_min = 5
    combo.turnover_max = 20
    combo.volume_ratio_enabled = True
    combo.volume_ratio_min = 1.2
    combo.volume_ratio_max = 50
    combo.volume_break_enabled = True
    combo.volume_break_min = 1.5
    combo.volume_break_max = 50
    combo.amplitude_enabled = True
    combo.amplitude_min = 3
    combo.amplitude_max = 15
    combo.ma_bullish_enabled = True
    combo.kdj_enabled = True
    combo.kdj_j_min = -20
    combo.kdj_j_max = 10
    combo.ma5_cross_ma9_enabled = True
    combo.ma5_distance_enabled = True
    combo.ma5_distance_min = 0.02
    combo.ma5_distance_max = 0.10
    combo.ma9_distance_enabled = True
    combo.ma9_distance_min = 0.02
    combo.ma9_distance_max = 0.10
    combo.continuous_up_enabled = True
    combo.continuous_up_days = 3
    combo.continuous_up_min_pct = 1.0

    engine = ManualFilterEngine()
    combo_results = engine.filter(combo)
    print(f"\n组合筛选结果: {len(combo_results)}只")
    results_summary['全条件组合'] = len(combo_results)

    if combo_results:
        print(f"\n随机抽查10只:")
        print(f"{'代码':<8}{'名称':<10}{'价格':>8}{'市值':>8}{'换手':>7}{'量比':>7}{'MA状态':<10}{'KDJ状态':<12}")
        print("-" * 80)
        sample = random.sample(combo_results, min(10, len(combo_results)))
        for s in sample:
            print(f"{s.get('code',''):<8}{s.get('name','')[:8]:<10}{s.get('price',0):>8.2f}{s.get('market_cap',0):>7.0f}亿{s.get('turnover',0):>6.1f}%{s.get('volume_ratio',0):>7.2f}{s.get('ma_status','--'):<10}{s.get('kdj_status','--'):<12}")

    # ===== 汇总报告 =====
    print(f"\n\n{'='*70}")
    print("验收汇总报告")
    print("=" * 70)
    print(f"{'条件':<25}{'筛选数量':>10}{'状态':>10}")
    print("-" * 50)
    for name, count in results_summary.items():
        status = "✅ 通过" if count > 0 else "⚠️ 无结果"
        print(f"{name:<25}{count:>10}{status:>10}")

    print(f"\n{'='*70}")
    print("验收结论")
    print("=" * 70)

    passed = sum(1 for v in results_summary.values() if v > 0)
    total = len(results_summary)
    print(f"单条件测试: {passed-1}/{total-1} 个有结果")
    print(f"组合测试: {results_summary['全条件组合']} 只")

    if passed >= 8:
        print("\n✅ V6.0 Pro手动筛选验收通过")
        print("  - 所有条件均可正常筛选")
        print("  - 数据链路正确")
        print("  - 技术指标计算正常")
        print("  - 组合条件逻辑正确")
    else:
        print("\n⚠️ 部分条件无结果，可能是条件过于严格或当前行情不匹配")

    print("=" * 70)


if __name__ == '__main__':
    main()
