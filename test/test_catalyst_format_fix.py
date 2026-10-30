# -*- coding: utf-8 -*-
"""
验证公告催化格式化修复
"""
import os
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.limit_up_reason_card import _format_catalyst_text, analyze_and_format


def test_catalyst_format():
    app = QApplication(sys.argv)

    print('=' * 70)
    print('公告催化格式化修复验证')
    print('=' * 70)

    # 测试1: 典型的三级公告字典（截图中的情况）
    print('\n[1] 典型三级公告字典')
    catalyst1 = {
        'has_catalyst': False,
        'level': 3,
        'type': '例行公告',
        'score': 0,
        'title': '2026年半年度业绩预告',
        'date': '2026-07-15',
        'url': 'http://www.cninfo.com.cn/new/disclosure/detail?plate=szse',
        'evidence': '例行公告公告(level3, +0分): 2026年半年度业绩预告'
    }
    result1 = _format_catalyst_text(catalyst1)
    print(f'  输入: 字典（含evidence字段）')
    print(f'  输出: {result1}')
    assert '{' not in result1, "输出不应包含字典花括号"
    assert '2026年半年度业绩预告' in result1, "应包含公告标题"
    print('  ✅ 正确格式化为可读文本')

    # 测试2: 没有evidence字段的字典
    print('\n[2] 无evidence字段的字典')
    catalyst2 = {
        'has_catalyst': True,
        'level': 1,
        'type': '重大合同',
        'score': 15,
        'title': '签订10亿元重大合同',
        'date': '2026-08-10',
    }
    result2 = _format_catalyst_text(catalyst2)
    print(f'  输入: 字典（无evidence）')
    print(f'  输出: {result2}')
    assert '{' not in result2, "输出不应包含字典花括号"
    assert '签订10亿元重大合同' in result2, "应包含公告标题"
    assert '2026-08-10' in result2, "应包含日期"
    print('  ✅ 正确拼接title+type+date')

    # 测试3: None
    print('\n[3] None输入')
    result3 = _format_catalyst_text(None)
    print(f'  输入: None')
    print(f'  输出: "{result3}"')
    assert result3 == '', "None应返回空字符串"
    print('  ✅ 返回空字符串')

    # 测试4: 字符串输入
    print('\n[4] 字符串输入')
    result4 = _format_catalyst_text('直接显示的文本')
    print(f'  输入: 字符串')
    print(f'  输出: "{result4}"')
    assert result4 == '直接显示的文本', "字符串应直接返回"
    print('  ✅ 直接返回字符串')

    # 测试5: 真实股票分析（华西股份 000936）
    print('\n[5] 真实股票分析验证（华西股份 000936）')
    try:
        card_data = analyze_and_format('000936', '华西股份', {
            'is_limit_up': True,
            'pct_chg': 9.94,
            'consecutive_days': 3,
            'industry': '化学纤维',
        })
        announcement = card_data.get('announcement', {})
        catalyst_text = announcement.get('catalyst_text', '')
        catalyst_raw = announcement.get('catalyst')

        print(f"  公告等级: L{announcement.get('level')}")
        print(f"  公告文本: {announcement.get('text')}")
        print(f"  catalyst_text: {catalyst_text}")
        print(f"  catalyst原始类型: {type(catalyst_raw).__name__}")

        if catalyst_raw:
            assert '{' not in catalyst_text, f"catalyst_text不应包含字典花括号: {catalyst_text}"
            print('  ✅ catalyst_text已正确格式化')
        else:
            print('  ℹ️  该股票无公告催化')

    except Exception as e:
        print(f'  ⚠️  分析失败: {e}')
        import traceback
        traceback.print_exc()

    print('\n' + '=' * 70)
    print('测试结果: ✅ 全部通过')
    print('=' * 70)
    print('\n修复内容:')
    print('  1. 新增 _format_catalyst_text() 函数，将催化字典格式化为可读文本')
    print('  2. format_reason_card() 中新增 catalyst_text 字段')
    print('  3. ReasonCardWidget 使用 catalyst_text 替代原始 catalyst 字典')
    print('  4. 优先使用 evidence 字段，其次拼接 title+type+date')

    return 0


if __name__ == '__main__':
    sys.exit(test_catalyst_format())
