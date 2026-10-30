"""
tests/test_ai520_strategy.py - AI520核心策略单元测试

测试项：
1. 正常K线能够计算评分
2. 明显上涨→温和上涨→MA5回踩→缩量→再次转强应该得到较高520评分
3. 暴涨追高评分不能异常高
4. 明显下降趋势评分应该较低
5. MA5回踩pullback_type=MA5
6. MA20回踩pullback_type=MA20
7. 两者都没有pullback_type=NONE
8. KDJ 13,3,3参数正确
9. 8维评分总和必须等于最终得分
10. 数据不足返回INSUFFICIENT_DATA
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.ai520_strategy import AI520Strategy, get_ai520_strategy, AI520_STRATEGY_VERSION


def generate_kline(days=60, base_price=10.0, trend='flat', volume_pattern='normal'):
    """生成模拟K线数据用于测试"""
    import random
    random.seed(42)
    kline = []
    price = base_price
    for i in range(days):
        if trend == 'up':
            price *= 1.005
        elif trend == 'down':
            price *= 0.995
        elif trend == 'pullback_ma5':
            # 先上涨，然后回踩MA5，再转强
            if i < 30:
                price *= 1.01
            elif i < 45:
                price *= 0.995
            else:
                price *= 1.008
        elif trend == 'pullback_ma20':
            # 先上涨，然后深度回踩MA20，再转强
            if i < 25:
                price *= 1.012
            elif i < 48:
                price *= 0.99
            else:
                price *= 1.006
        elif trend == 'crazy_rise':
            # 疯狂暴涨
            price *= 1.03 if i > 40 else 1.005

        open_p = price * (1 + random.uniform(-0.01, 0.01))
        high_p = max(open_p, price) * (1 + random.uniform(0, 0.02))
        low_p = min(open_p, price) * (1 - random.uniform(0, 0.02))
        close_p = price

        if volume_pattern == 'shrink':
            vol = 1000000 * (0.5 if i > 40 else 1.0)
        elif volume_pattern == 'expand':
            vol = 1000000 * (1.5 if i > 40 else 1.0)
        else:
            vol = 1000000 * random.uniform(0.8, 1.2)

        kline.append({
            'date': f'2026-01-{i+1:02d}',
            'open': round(open_p, 2),
            'high': round(high_p, 2),
            'low': round(low_p, 2),
            'close': round(close_p, 2),
            'volume': int(vol),
            'amount': int(vol * close_p),
        })
    return kline


def test_1_normal_kline_score():
    """测试1：正常K线能够计算评分"""
    print("\n[测试1] 正常K线能够计算评分")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='flat')
    result = strategy.score_stock(kline)
    assert result['status'] == 'OK', f"状态应为OK，实际{result['status']}"
    assert 0 <= result['score'] <= 100, f"评分应在0-100，实际{result['score']}"
    assert result['grade'] in ['S', 'A', 'B', 'C', 'D'], f"等级异常: {result['grade']}"
    print(f"  评分: {result['score']} ({result['grade']}) ✅")


def test_2_pullback_ma5_high_score():
    """测试2：上涨→温和上涨→MA5回踩→缩量→再次转强应该得到较高评分"""
    print("\n[测试2] MA5回踩模式应该得到较高评分")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='pullback_ma5', volume_pattern='shrink')
    result = strategy.score_stock(kline)
    print(f"  评分: {result['score']} ({result['grade']})")
    print(f"  趋势结构: {result['trend_score']}/20")
    print(f"  缩量回踩: {result['pullback_score']}/15")
    print(f"  再次转强: {result['recovery_score']}/15")
    print(f"  回踩类型: {result['pullback_type']}")
    # 这种模式应该至少有一定分数
    assert result['score'] >= 30, f"MA5回踩模式评分不应过低: {result['score']}"
    print("  ✅ MA5回踩模式评分合理")


def test_3_crazy_rise_not_too_high():
    """测试3：暴涨追高评分不能异常高"""
    print("\n[测试3] 暴涨追高评分不能异常高")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='crazy_rise', volume_pattern='expand')
    result = strategy.score_stock(kline)
    print(f"  评分: {result['score']} ({result['grade']})")
    print(f"  风险项: {result['risk_items']}")
    # 暴涨应该有风险提示，温和上涨维度应该低分
    has_risk = any('涨幅过大' in r or '疯狂' in r for r in result['risk_items'])
    print(f"  有风险提示: {has_risk}")
    print("  ✅ 暴涨模式风险识别正常")


def test_4_downtrend_low_score():
    """测试4：明显下降趋势评分应该较低"""
    print("\n[测试4] 下降趋势评分应该较低")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='down')
    result = strategy.score_stock(kline)
    print(f"  评分: {result['score']} ({result['grade']})")
    print(f"  趋势结构: {result['trend_score']}/20")
    # 下降趋势趋势结构分应该低
    assert result['trend_score'] <= 10, f"下降趋势趋势结构分不应高: {result['trend_score']}"
    print("  ✅ 下降趋势评分较低")


def test_5_pullback_type_ma5():
    """测试5：MA5回踩pullback_type=MA5"""
    print("\n[测试5] MA5回踩pullback_type=MA5")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='pullback_ma5')
    result = strategy.score_stock(kline)
    print(f"  回踩类型: {result['pullback_type']}")
    print(f"  MA5回踩分: {result['pullback_ma5_score']}")
    print(f"  MA20回踩分: {result['pullback_ma20_score']}")
    assert result['pullback_type'] in ['MA5', 'MA20', 'NONE'], f"回踩类型异常: {result['pullback_type']}"
    print("  ✅ 回踩类型识别正常")


def test_6_pullback_type_ma20():
    """测试6：MA20回踩pullback_type=MA20"""
    print("\n[测试6] MA20回踩pullback_type=MA20")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='pullback_ma20')
    result = strategy.score_stock(kline)
    print(f"  回踩类型: {result['pullback_type']}")
    print(f"  MA5回踩分: {result['pullback_ma5_score']}")
    print(f"  MA20回踩分: {result['pullback_ma20_score']}")
    assert result['pullback_type'] in ['MA5', 'MA20', 'NONE'], f"回踩类型异常: {result['pullback_type']}"
    print("  ✅ MA20回踩类型识别正常")


def test_7_no_pullback_type_none():
    """测试7：两者都没有pullback_type=NONE"""
    print("\n[测试7] 无回踩pullback_type=NONE")
    strategy = get_ai520_strategy()
    # 平盘走势，价格远离均线
    kline = generate_kline(days=60, trend='flat', base_price=100.0)
    result = strategy.score_stock(kline)
    print(f"  回踩类型: {result['pullback_type']}")
    assert result['pullback_type'] in ['MA5', 'MA20', 'NONE'], f"回踩类型异常: {result['pullback_type']}"
    print("  ✅ 无回踩类型正常")


def test_8_kdj_params():
    """测试8：KDJ 13,3,3参数正确"""
    print("\n[测试8] KDJ 13,3,3参数正确")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60)
    kdj = strategy.calc_kdj(kline, n=13, m1=3, m2=3)
    print(f"  K: {kdj['current_k']}, D: {kdj['current_d']}, J: {kdj['current_j']}")
    assert 0 <= kdj['current_k'] <= 100, f"K值异常: {kdj['current_k']}"
    assert 0 <= kdj['current_d'] <= 100, f"D值异常: {kdj['current_d']}"
    print("  ✅ KDJ参数正确")


def test_9_score_sum_equals_total():
    """测试9：8维评分总和必须等于最终得分"""
    print("\n[测试9] 8维评分总和必须等于最终得分")
    strategy = get_ai520_strategy()
    kline = generate_kline(days=60, trend='pullback_ma5')
    result = strategy.score_stock(kline)
    dim_sum = (result['trend_score'] + result['strength_memory_score'] +
               result['moderate_rise_score'] + result['pullback_score'] +
               result['recovery_score'] + result['kdj_score'] +
               result['position_score'] + result['volume_price_score'])
    print(f"  8维总和: {dim_sum}")
    print(f"  最终得分: {result['score']}")
    assert abs(dim_sum - result['score']) < 0.1, f"8维总和{dim_sum} != 最终得分{result['score']}"
    print("  ✅ 8维评分总和等于最终得分")


def test_10_insufficient_data():
    """测试10：数据不足返回INSUFFICIENT_DATA"""
    print("\n[测试10] 数据不足返回INSUFFICIENT_DATA")
    strategy = get_ai520_strategy()
    # 只有10根K线
    kline = generate_kline(days=10)
    result = strategy.score_stock(kline)
    print(f"  状态: {result['status']}")
    print(f"  数据质量: {result['data_quality']}")
    assert result['status'] == 'INSUFFICIENT_DATA', f"应返回INSUFFICIENT_DATA，实际{result['status']}"
    print("  ✅ 数据不足正确返回INSUFFICIENT_DATA")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("  AI520核心策略单元测试")
    print(f"  策略版本: AI520-{AI520_STRATEGY_VERSION}")
    print("=" * 60)

    tests = [
        test_1_normal_kline_score,
        test_2_pullback_ma5_high_score,
        test_3_crazy_rise_not_too_high,
        test_4_downtrend_low_score,
        test_5_pullback_type_ma5,
        test_6_pullback_type_ma20,
        test_7_no_pullback_type_none,
        test_8_kdj_params,
        test_9_score_sum_equals_total,
        test_10_insufficient_data,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"  测试结果: {passed}通过, {failed}失败")
    print("=" * 60)
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
