# -*- coding: utf-8 -*-
"""一次性补丁：在 battle_console_v2.py 注册「策略看板」Tab（勿重跑）。"""
import io

P = r'D:\QuantMonitorV6\ui\battle_console_v2.py'

ANCHOR1 = """                                align=Qt.AlignmentFlag.AlignCenter))
            self.tabs.addTab(self.ctrl_screen_page, '🎛 控盘选股')
"""

INSERT1 = """
        # 【策略看板页】对标 TickFlow Stock Panel：经典技术指标策略全市场扫描（2026-10-17 新增）
        # v1：MA金叉/多头排列/MACD金叉/RSI超卖/KDJ金叉/放量突破/缩量回踩MA20，吃本地K线
        try:
            from ui.battle_widgets.strategy_panel_widget import StrategyPanelWidget
            self.strategy_panel_page = StrategyPanelWidget()
            self.tabs.addTab(self.strategy_panel_page, '📈 策略看板')
            print("[主窗口] 策略看板页已添加", flush=True)
        except Exception as _sp_err:
            print(f"[主窗口] 策略看板页加载失败: {_sp_err}", flush=True)
            import traceback; traceback.print_exc()
            self.strategy_panel_page = QWidget()
            _sp_lay = QVBoxLayout(self.strategy_panel_page)
            _sp_lay.addWidget(L(f'策略看板页加载失败: {_sp_err}', C.RED, 12,
                                align=Qt.AlignmentFlag.AlignCenter))
            self.tabs.addTab(self.strategy_panel_page, '📈 策略看板')
"""

ANCHOR2 = """            print(f'[信号连接] 控盘选股页 stock_clicked 连接失败: {_e}', flush=True)
"""

INSERT2 = """
        # 【策略看板页】双击股票跳转个股分析
        try:
            if getattr(self, 'strategy_panel_page', None) and hasattr(self.strategy_panel_page, 'stock_clicked'):
                self.strategy_panel_page.stock_clicked.connect(self._show_stock_detail)
                print('[信号连接] 策略看板页 stock_clicked 已连接个股分析', flush=True)
        except Exception as _e:
            print(f'[信号连接] 策略看板页 stock_clicked 连接失败: {_e}', flush=True)
"""

raw = io.open(P, encoding='utf-8', newline='').read()
norm = raw.replace('\r\n', '\n')
assert norm.count(ANCHOR1) == 1, '锚点1命中 %d 次' % norm.count(ANCHOR1)
assert norm.count(ANCHOR2) == 1, '锚点2命中 %d 次' % norm.count(ANCHOR2)

norm = norm.replace(ANCHOR1, ANCHOR1 + INSERT1, 1)
norm = norm.replace(ANCHOR2, ANCHOR2 + INSERT2, 1)

out = norm.replace('\n', '\r\n')
io.open(P, 'w', encoding='utf-8', newline='').write(out)
print('OK: battle_console_v2.py 已插入策略看板页（CRLF 保持）')
