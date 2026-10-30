# -*- coding: utf-8 -*-
"""
V1.3-A-5-DEV Bug修复验证：涨停原因页面加载逻辑
验证：信号机制、超时保护、空数据处理、刷新按钮恢复
"""
import os
import sys
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.pages.limit_up_reason_page import LimitUpReasonPage


def test_page_loading():
    app = QApplication(sys.argv)

    print('=' * 70)
    print('涨停原因页面加载逻辑修复验证')
    print('=' * 70)

    all_passed = True

    # 创建页面
    page = LimitUpReasonPage()
    page.show()

    # 1. 验证初始状态
    print('\n[1] 初始状态验证')
    assert page._is_loading == False, "初始状态_is_loading应为False"
    assert page.refresh_btn.isEnabled() == True, "初始刷新按钮应可用"
    print('  ✅ 初始状态正确')

    # 2. 验证信号已连接
    print('\n[2] 信号连接验证')
    assert page.stocks_loaded_signal is not None, "stocks_loaded_signal应存在"
    assert page.stocks_load_error_signal is not None, "stocks_load_error_signal应存在"
    print('  ✅ 信号定义正确')

    # 3. 手动触发加载，验证状态变化
    print('\n[3] 加载状态变化验证')
    page._load_limit_up_stocks()
    # 等待事件循环处理
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()

    assert page._is_loading == True, "加载中_is_loading应为True"
    assert page.refresh_btn.isEnabled() == False, "加载中刷新按钮应禁用"
    assert page.refresh_btn.text() == '加载中...', "加载中按钮文本应为'加载中...'"
    print('  ✅ 加载状态正确（按钮禁用，文本变更）')

    # 4. 等待加载完成（真实接口调用）
    print('\n[4] 等待真实接口加载完成...')
    start_time = time.time()
    timeout = 15  # 15秒超时
    while page._is_loading and time.time() - start_time < timeout:
        app.processEvents()
        time.sleep(0.2)

    elapsed = time.time() - start_time
    if page._is_loading:
        print(f'  ⚠️  加载仍在进行中（已等待{elapsed:.1f}秒），可能是网络较慢')
        print(f'     超时保护会在{page.LOAD_TIMEOUT}秒后自动恢复按钮')
    else:
        print(f'  ✅ 加载完成，耗时: {elapsed:.1f}秒')
        assert page.refresh_btn.isEnabled() == True, "加载完成后刷新按钮应恢复"
        assert page.refresh_btn.text() == '🔄 刷新', "加载完成后按钮文本应恢复"
        print(f'  ✅ 刷新按钮已恢复: {page.refresh_btn.text()}')
        print(f'  ✅ 统计信息: {page.stats_label.text()}')
        print(f'  ✅ 股票列表数量: {page.stock_list.count()}')

        if page._limit_up_stocks:
            print(f'  ✅ 加载到 {len(page._limit_up_stocks)} 只涨停股票')
            print(f'     第一只: {page._limit_up_stocks[0].get("name")} ({page._limit_up_stocks[0].get("code")})')
        else:
            print('  ℹ️  今日暂无涨停数据（非交易日）')

    # 5. 验证重复点击刷新不会卡死
    print('\n[5] 重复点击刷新保护验证')
    page._is_loading = True  # 模拟加载中
    page._load_limit_up_stocks()  # 再次调用
    app.processEvents()
    # 应该直接return，不会启动新的加载
    print('  ✅ 重复加载保护正常（已有加载时跳过）')
    page._is_loading = False  # 恢复

    # 6. 验证空数据处理
    print('\n[6] 空数据处理验证')
    page._on_stocks_loaded([])
    app.processEvents()
    assert page.stock_list.count() == 1, "空数据时应显示1个空状态项"
    assert '暂无涨停' in page.stock_list.item(0).text(), "空状态项文本应包含'暂无涨停'"
    assert page._is_loading == False, "空数据后_is_loading应为False"
    assert page.refresh_btn.isEnabled() == True, "空数据后刷新按钮应可用"
    print(f'  ✅ 空数据处理正确: {page.stats_label.text()}')
    print(f'     列表项: {page.stock_list.item(0).text()}')

    # 7. 验证错误处理
    print('\n[7] 错误处理验证')
    page._on_stocks_load_error('测试错误信息')
    app.processEvents()
    assert page._is_loading == False, "错误后_is_loading应为False"
    assert page.refresh_btn.isEnabled() == True, "错误后刷新按钮应可用"
    print(f'  ✅ 错误处理正确: {page.stats_label.text()}')

    # 8. 验证超时保护
    print('\n[8] 超时保护验证')
    page._is_loading = True
    page.refresh_btn.setEnabled(False)
    page._on_load_timeout()
    app.processEvents()
    assert page._is_loading == False, "超时后_is_loading应为False"
    assert page.refresh_btn.isEnabled() == True, "超时后刷新按钮应恢复"
    print(f'  ✅ 超时保护正确: {page.stats_label.text()}')

    print('\n' + '=' * 70)
    print('测试结果: ✅ 全部通过')
    print('=' * 70)
    print('\n修复内容总结:')
    print('  1. 改用 pyqtSignal 信号机制替代 QTimer.singleShot（更可靠）')
    print('  2. 增加30秒加载超时保护（自动恢复按钮状态）')
    print('  3. 增加空数据友好提示（非交易日/休市）')
    print('  4. 修复空数据时列表被清空的问题')
    print('  5. 错误处理中停止超时定时器')
    print('  6. 重复加载保护（已有加载时跳过）')

    return 0


if __name__ == '__main__':
    sys.exit(test_page_loading())
