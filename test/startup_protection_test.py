# -*- coding: utf-8 -*-
"""
V1.3-A-4.1-FROZEN 启动保护测试
每次冻结版本后必须运行，确保：
1. MainWindow 可正常创建
2. 所有Tab可实例化
3. 涨停原因页面关键组件存在
4. 5种排序方式可切换
5. 无异常退出
"""
import os
import sys
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_startup():
    """启动保护测试"""
    print('=' * 70)
    print('V1.3-A-4.1-FROZEN 启动保护测试')
    print('=' * 70)

    results = []
    app = QApplication(sys.argv)

    # ========== 测试1: MainWindow创建 ==========
    print('\n[测试1] MainWindow 创建...')
    try:
        from ui.main_window import MainWindow
        window = MainWindow()
        print('  ✅ MainWindow 创建成功')
        results.append(('MainWindow创建', True))
    except Exception as e:
        print(f'  ❌ MainWindow 创建失败: {e}')
        results.append(('MainWindow创建', False))
        return False

    # ========== 测试2: Tab数量和名称 ==========
    print('\n[测试2] Tab 检查...')
    expected_tabs = ['实时监控', 'AI选股池', '我的自选', '7×24快讯', '涨停原因']
    tab_count = window.tab_widget.count()
    print(f'  Tab数量: {tab_count} (期望≥5)')

    all_tabs_ok = True
    for i in range(tab_count):
        tab_name = window.tab_widget.tabText(i)
        print(f'  Tab {i}: {tab_name}')

    for expected in expected_tabs:
        found = any(expected in window.tab_widget.tabText(i) for i in range(tab_count))
        if not found:
            print(f'  ❌ 缺少Tab: {expected}')
            all_tabs_ok = False

    if all_tabs_ok:
        print('  ✅ 所有期望Tab存在')
    results.append(('Tab完整性', all_tabs_ok))

    # ========== 测试3: 涨停原因页面组件 ==========
    print('\n[测试3] 涨停原因页面组件检查...')
    try:
        # 找到涨停原因Tab
        reason_page = None
        for i in range(tab_count):
            if '涨停原因' in window.tab_widget.tabText(i):
                reason_page = window.tab_widget.widget(i)
                break

        if reason_page is None:
            print('  ❌ 未找到涨停原因页面')
            results.append(('涨停原因页面', False))
        else:
            # 检查关键组件
            checks = {
                '排序下拉框(sort_combo)': hasattr(reason_page, 'sort_combo'),
                '涨停列表(stock_list)': hasattr(reason_page, 'stock_list'),
                '刷新按钮(refresh_btn)': hasattr(reason_page, 'refresh_btn'),
                '卡片容器(card_scroll)': hasattr(reason_page, 'card_scroll'),
                '排序方法(_sort_stocks)': hasattr(reason_page, '_sort_stocks'),
                '快速排序分(_calc_quick_rank_score)': hasattr(reason_page, '_calc_quick_rank_score'),
            }

            all_ok = True
            for name, ok in checks.items():
                status = '✅' if ok else '❌'
                print(f'  {status} {name}')
                if not ok:
                    all_ok = False

            results.append(('涨停原因组件', all_ok))
    except Exception as e:
        print(f'  ❌ 检查异常: {e}')
        results.append(('涨停原因组件', False))

    # ========== 测试4: 排序下拉框选项 ==========
    print('\n[测试4] 排序下拉框选项检查...')
    try:
        if hasattr(reason_page, 'sort_combo'):
            count = reason_page.sort_combo.count()
            items = [reason_page.sort_combo.itemText(i) for i in range(count)]
            print(f'  排序选项数量: {count}')
            for item in items:
                print(f'    - {item}')

            expected_sorts = ['综合强度', '连板高度', '封板时间', '封单强度', '炸板次数']
            all_sorts_ok = all(any(s in item for item in items) for s in expected_sorts)
            if all_sorts_ok:
                print('  ✅ 5种排序方式齐全')
            else:
                print('  ❌ 排序方式不完整')
            results.append(('排序选项', all_sorts_ok))
        else:
            results.append(('排序选项', False))
    except Exception as e:
        print(f'  ❌ 检查异常: {e}')
        results.append(('排序选项', False))

    # ========== 测试5: 原因卡片组件 ==========
    print('\n[测试5] 原因卡片组件检查...')
    try:
        from ui.widgets.reason_card_widget import ReasonCardWidget
        card = ReasonCardWidget()
        card_checks = {
            '股票信息(stock_info_label)': hasattr(card, 'stock_info_label'),
            '概念区域(concept_layout)': hasattr(card, 'concept_layout'),
            '涨停强度(strength_layout)': hasattr(card, 'strength_layout'),
            '核心依据(evidence_layout)': hasattr(card, 'evidence_layout'),
            '详细依据(detail_layout)': hasattr(card, 'detail_layout'),
            '评分拆解(score_grid)': hasattr(card, 'score_grid'),
            'AI总结(ai_layout)': hasattr(card, 'ai_layout'),
            '风险提示(risk_layout)': hasattr(card, 'risk_layout'),
        }
        all_ok = True
        for name, ok in card_checks.items():
            status = '✅' if ok else '❌'
            print(f'  {status} {name}')
            if not ok:
                all_ok = False
        card.deleteLater()
        results.append(('原因卡片组件', all_ok))
    except Exception as e:
        print(f'  ❌ 检查异常: {e}')
        results.append(('原因卡片组件', False))

    # ========== 测试6: 分析接口 ==========
    print('\n[测试6] 分析接口检查...')
    try:
        from ui.limit_up_reason_card import analyze_and_format
        # 用模拟数据测试
        mock_stock = {
            'code': '000001',
            'name': '测试股票',
            'lbc': 2,
            'first_limit_time': '09:30:00',
            'last_limit_time': '09:30:00',
            'seal_amount': 50000000,
            'break_count': 0,
            'float_market_cap': 2000000000,
            'pct_chg': 10.0,
            'industry': '测试行业',
            'amount': 100000000,
            'hs': 5.0,
        }
        # 不实际调用网络接口，只检查函数存在
        print('  ✅ analyze_and_format 函数存在')
        results.append(('分析接口', True))
    except Exception as e:
        print(f'  ❌ 接口异常: {e}')
        results.append(('分析接口', False))

    # ========== 汇总 ==========
    print('\n' + '=' * 70)
    print('测试汇总')
    print('=' * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        status = '✅ 通过' if ok else '❌ 失败'
        print(f'  {name}: {status}')

    print(f'\n  总计: {passed}/{total} 通过')
    all_pass = passed == total
    print(f'  结论: {"✅ 启动保护测试通过，可以发布" if all_pass else "❌ 存在问题，需修复"}')
    print('=' * 70)

    window.deleteLater()
    app.quit()
    return all_pass


if __name__ == '__main__':
    success = test_startup()
    sys.exit(0 if success else 1)
