# -*- coding: utf-8 -*-
"""
非GUI验证脚本：测试ReasonCardWidget能否正常实例化和数据渲染
使用 offscreen 平台，不显示窗口
"""
import sys
import os

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PyQt6.QtWidgets import QApplication
from ui.limit_up_reason_card import analyze_and_format
from ui.widgets.reason_card_widget import ReasonCardWidget


def test_card_widget():
    app = QApplication(sys.argv)

    test_cases = [
        ('000815', '美利云', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 3, 'trade_date': '20260804'}),
        ('600666', '奥瑞德', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 1, 'trade_date': '20260804'}),
        ('300615', '欣天科技', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 2, 'trade_date': '20260804'}),
    ]

    print('=' * 70)
    print('V1.3-A-4-DEV Step2：原因卡片组件非GUI验证')
    print('=' * 70)

    all_passed = True

    for code, name, limit_data in test_cases:
        print(f'\n[{name} ({code})]')
        try:
            # 1. 数据分析
            card_data = analyze_and_format(code, name, limit_data)
            card_data['code'] = code
            card_data['name'] = name

            confidence = card_data.get('confidence', {})
            level = confidence.get('level', '?')
            score = confidence.get('score', 0)
            print(f'  数据层: {level}级 {score}分 ✓')

            # 2. 组件实例化
            card = ReasonCardWidget(card_data)
            print(f'  组件实例化: ✓')

            # 3. 验证各区域标签
            assert card.stock_name_label.text() == name, f"名称不匹配: {card.stock_name_label.text()}"
            assert card.stock_code_label.text() == code, f"代码不匹配: {card.stock_code_label.text()}"
            print(f'  头部区域: ✓ (名称+代码)')

            # 4. 验证可信度标签
            conf_text = card.confidence_label.text()
            assert level in conf_text, f"可信度标签不包含级别: {conf_text}"
            print(f'  可信度标签: ✓ ({conf_text.replace(chr(10), " ")})')

            # 5. 验证涨停方向
            theme = card_data.get('core_theme', {}).get('theme', '--')
            assert theme in card.theme_label.text(), f"涨停方向不匹配: {card.theme_label.text()}"
            print(f'  涨停方向: ✓ ({theme})')

            # 6. 验证核心依据区域有内容
            evidence_count = card.evidence_layout.count()
            assert evidence_count > 0, "核心依据区域为空"
            print(f'  核心依据: ✓ ({evidence_count}条)')

            # 7. 验证评分拆解区域
            score_count = card.score_grid.count()
            assert score_count > 0, "评分拆解区域为空"
            print(f'  评分拆解: ✓ ({score_count}个组件)')

            # 8. 验证风险提示区域
            risk_count = card.risk_layout.count()
            assert risk_count > 0, "风险提示区域为空"
            print(f'  风险提示: ✓ ({risk_count}条)')

            # 9. 验证set_data方法可重复调用
            card.set_data(card_data)
            print(f'  set_data重复调用: ✓')

            print(f'  结果: ✅ 全部通过')

        except Exception as e:
            all_passed = False
            print(f'  结果: ❌ 失败 - {e}')
            import traceback
            traceback.print_exc()

    print('\n' + '=' * 70)
    if all_passed:
        print('验证结果: ✅ 全部通过')
    else:
        print('验证结果: ❌ 存在失败')
    print('=' * 70)

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(test_card_widget())
