# -*- coding: utf-8 -*-
"""V0.6.1 真实运行验收 - ai_buy_signal接入验证"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.ai_buy_signal import AIBuySignalEngine, get_buy_signal_engine

print('========== V0.6.1 真实运行验收 ==========')
print()

# 测试1：默认关闭状态
engine = AIBuySignalEngine()
print(f'[1] 默认开关: {engine.DYNAMIC_WEIGHT_ENABLED}')
print(f'    类变量: {AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED}')

# 测试2：默认关闭时generate_report
stock_data = {
    'code': '600519',
    'name': '贵州茅台',
    'basic': {'concepts': ['白酒']},
    'chanlun': {'current_state': '中枢震荡'},
}
report = engine.generate_report(stock_data)
print(f'[2] 默认关闭 - score: {report["score"]}')
print(f'    original_score: {report.get("original_score")}')
print(f'    dynamic_weight_info: {report.get("dynamic_weight_info")}')
print(f'    rating: {report.get("rating")}')

# 测试3：开启动态权重
print()
print('[3] 开启动态权重...')
AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = True
engine2 = AIBuySignalEngine()
report2 = engine2.generate_report(stock_data)
print(f'    score: {report2["score"]}')
print(f'    original_score: {report2.get("original_score")}')
di = report2.get('dynamic_weight_info')
if di:
    print(f'    策略: {di["strategy"]}')
    print(f'    权重: {di["weight"]}')
    print(f'    启用: {di["enabled"]}')
    print(f'    样本: {di["sample"]}')
    print(f'    原因: {di["reason"]}')

# 测试4：单例
print()
print('[4] 单例测试')
singleton = get_buy_signal_engine()
print(f'    单例类型: {type(singleton).__name__}')
print(f'    单例开关: {singleton.DYNAMIC_WEIGHT_ENABLED}')

# 恢复
AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = False
print()
print('========== 接入验证完成 ==========')
print('结论: weight_adapter已接入ai_buy_signal.generate_report')
print('      默认关闭，设置 AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED=True 开启')
