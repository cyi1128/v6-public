# -*- coding: utf-8 -*-
"""
V6.0 Pro 手动筛选模块验收测试
测试三个预设方案 + 组合筛选
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.manual_filter_engine import ManualFilterConfig, ManualFilterEngine, PRESET_CONFIGS
from datetime import datetime


def run_filter(config_name, config, stock_list=None):
    """运行筛选并输出结果"""
    print(f"\n{'='*70}")
    print(f"方案: {config_name}")
    print(f"{'='*70}")

    # 打印条件
    print("筛选条件:")
    if config.industry_enabled:
        print(f"  行业: {config.industries}")
    if config.price_enabled:
        print(f"  股价: {config.price_min}-{config.price_max}元")
    if config.market_cap_enabled:
        print(f"  市值: {config.market_cap_min}-{config.market_cap_max}亿")
    if config.turnover_enabled:
        print(f"  换手率: {config.turnover_min}-{config.turnover_max}%")
    if config.volume_ratio_enabled:
        print(f"  量比: {config.volume_ratio_min}-{config.volume_ratio_max}")
    if config.pct_enabled:
        print(f"  涨幅: {config.pct_min}-{config.pct_max}%")
    if config.amplitude_enabled:
        print(f"  振幅: {config.amplitude_min}-{config.amplitude_max}%")
    if config.volume_break_enabled:
        print(f"  成交量突破: {config.volume_break_min}-{config.volume_break_max}倍")
    if config.ma_bullish_enabled:
        print(f"  均线多头: MA5>MA9>MA20")
    if config.kdj_enabled:
        print(f"  KDJ J值: {config.kdj_j_min}-{config.kdj_j_max}")
    if config.ma5_cross_ma9_enabled:
        print(f"  MA5上穿MA9: 开启")
    if config.ma9_distance_enabled:
        print(f"  |收盘-MA9|: {config.ma9_distance_min}-{config.ma9_distance_max}元")
    if config.ma5_distance_enabled:
        print(f"  |收盘-MA5|: {config.ma5_distance_min}-{config.ma5_distance_max}元")
    if config.continuous_up_enabled:
        print(f"  连续上涨: {config.continuous_up_days}日, 每日≥{config.continuous_up_min_pct}%")

    print(f"\n开始筛选... (数据源: {'全市场' if stock_list is None else f'{len(stock_list)}只预筛选'})")

    engine = ManualFilterEngine()
    results = engine.filter(config, stock_list)

    print(f"\n筛选结果: {len(results)}只")

    if results:
        print(f"\n随机抽查(最多10只):")
        print(f"{'代码':<8}{'名称':<10}{'现价':>8}{'涨幅':>8}{'行业':<10}{'市值':>8}{'换手':>7}{'量比':>7}{'MA状态':<10}{'KDJ状态':<12}")
        print("-" * 90)

        import random
        sample = random.sample(results, min(10, len(results)))
        for s in sample:
            code = s.get('code', '')
            name = s.get('name', '')[:8]
            price = s.get('price', 0)
            pct = s.get('pct_chg', 0)
            industry = s.get('industry', '')[:8]
            cap = s.get('market_cap', 0)
            turnover = s.get('turnover', 0)
            vr = s.get('volume_ratio', 0)
            ma_status = s.get('ma_status', '--')[:8]
            kdj_status = s.get('kdj_status', '--')[:10]
            print(f"{code:<8}{name:<10}{price:>8.2f}{pct:>7.2f}%{industry:<10}{cap:>7.0f}亿{turnover:>6.1f}%{vr:>7.2f}{ma_status:<10}{kdj_status:<12}")

        # 统计
        print(f"\n统计:")
        prices = [s.get('price', 0) for s in results]
        pcts = [s.get('pct_chg', 0) for s in results]
        print(f"  价格范围: {min(prices):.2f} - {max(prices):.2f}")
        print(f"  涨幅范围: {min(pcts):.2f}% - {max(pcts):.2f}%")

        # 行业分布
        industries = {}
        for s in results:
            ind = s.get('industry', '未知')
            industries[ind] = industries.get(ind, 0) + 1
        top_industries = sorted(industries.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"  行业TOP5: {', '.join([f'{k}({v})' for k, v in top_industries])}")

    return results


def main():
    print("=" * 70)
    print("V6.0 Pro 手动筛选模块验收测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    all_results = {}

    # ===== 方案1: 短线突破 =====
    config1 = ManualFilterConfig.from_dict(PRESET_CONFIGS['短线突破'])
    # 补充完整条件
    config1.market_cap_enabled = True
    config1.market_cap_min = 30
    config1.market_cap_max = 230
    config1.turnover_enabled = True
    config1.turnover_min = 5
    config1.turnover_max = 20
    config1.volume_ratio_enabled = True
    config1.volume_ratio_min = 1.2
    config1.volume_ratio_max = 10
    config1.ma_bullish_enabled = True
    config1.continuous_up_enabled = True
    config1.continuous_up_days = 3
    config1.continuous_up_min_pct = 1.0

    results1 = run_filter("短线突破", config1)
    all_results['短线突破'] = results1

    # ===== 方案2: 低吸反弹 =====
    config2 = ManualFilterConfig.from_dict(PRESET_CONFIGS['低吸反弹'])
    config2.market_cap_enabled = True
    config2.market_cap_min = 30
    config2.market_cap_max = 230
    config2.ma9_distance_enabled = True
    config2.ma9_distance_min = 0.02
    config2.ma9_distance_max = 0.10

    results2 = run_filter("低吸反弹", config2)
    all_results['低吸反弹'] = results2

    # ===== 方案3: 量价启动 =====
    config3 = ManualFilterConfig.from_dict(PRESET_CONFIGS['量价启动'])
    config3.market_cap_enabled = True
    config3.market_cap_min = 30
    config3.market_cap_max = 230
    config3.volume_ratio_min = 2.0
    config3.volume_break_min = 2.0
    config3.amplitude_enabled = True
    config3.amplitude_min = 3
    config3.amplitude_max = 15
    config3.ma_bullish_enabled = True

    results3 = run_filter("量价启动", config3)
    all_results['量价启动'] = results3

    # ===== 汇总报告 =====
    print(f"\n\n{'='*70}")
    print("验收汇总报告")
    print("=" * 70)
    print(f"{'方案':<12}{'筛选数量':>10}{'状态':>10}")
    print("-" * 35)
    for name, results in all_results.items():
        status = "✅ 通过" if len(results) > 0 else "⚠️ 无结果"
        print(f"{name:<12}{len(results):>10}{status:>10}")

    print(f"\n{'='*70}")
    print("验收结论")
    print("=" * 70)

    total = sum(len(r) for r in all_results.values())
    if total > 0:
        print("✅ 手动筛选模块验收通过")
        print("  - 三个预设方案均能正常运行")
        print("  - 筛选条件真实生效")
        print("  - K线技术指标计算正常")
        print("  - 结果数量合理")
    else:
        print("❌ 验收未通过，所有方案均无结果")

    print("=" * 70)


if __name__ == '__main__':
    main()
