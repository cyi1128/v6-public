# -*- coding: utf-8 -*-
"""
预警中心 V1.0
只新增展示和管理层，不修改扫描逻辑、指标计算、评分算法
功能：实时信号列表、预警等级、弹窗提醒、历史记录
"""
import os
import sys
import json
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QPushButton, QTabWidget, QHeaderView, QMessageBox,
    QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    STATUS_ERROR, STATUS_WARNING, STATUS_INFO, UP, DOWN,
)

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# 历史记录文件
HISTORY_FILE = os.path.join(DATA_DIR, 'alarm_history.json')


def log_error(error):
    """记录错误日志"""
    try:
        log_file = os.path.join(LOG_DIR, 'alarm_center_error.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {error}\n')
            f.write(traceback.format_exc() + '\n')
    except Exception:
        pass


DARK_COLORS = {
    'bg_primary': BG_WINDOW,
    'bg_secondary': BG_CARD,
    'bg_tertiary': BG_INTERACTIVE,
    'border': BORDER,
    'text_primary': TEXT_PRIMARY,
    'text_secondary': TEXT_SECONDARY,
    'accent': ACCENT_BLUE,
    'red': ACCENT_RED,
    'green': ACCENT_GREEN,
    'orange': ACCENT_GOLD,
    'purple': '#9f7aea',
    'yellow': ACCENT_GOLD,
}

# 预警等级颜色
LEVEL_COLORS = {
    'S': STATUS_ERROR,
    'A': STATUS_WARNING,
    'B': STATUS_INFO,
}


class AlarmCenterPanel(QWidget):
    """预警中心页面"""

    # 新预警信号
    new_alarm = pyqtSignal(dict)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        super().__init__()
        self._current_alarms = []  # 当前预警列表
        self._history_alarms = []  # 历史预警列表
        self._popup_enabled = True  # 弹窗提醒开关
        self._stat_labels = {}  # 统计标签字典

        self._init_ui()
        self._load_history()

        print("[预警中心] 初始化完成")

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ========== 顶部：统计卡片 ==========
        self._create_stats_section(main_layout)

        # ========== 中间：Tab切换（实时预警/历史记录） ==========
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                background: {DARK_COLORS['bg_primary']};
            }}
            QTabBar::tab {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                padding: 8px 20px;
                border: 1px solid {DARK_COLORS['border']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background: {DARK_COLORS['bg_primary']};
                color: {DARK_COLORS['accent']};
                border-bottom: 2px solid {DARK_COLORS['accent']};
            }}
        """)

        # Tab1: 实时预警
        self._create_current_alarm_tab()
        # Tab2: 历史记录
        self._create_history_tab()
        # Tab3: V0.7 AI风险扫描（C5.2.3新增）
        self._create_ai_risk_tab()

        main_layout.addWidget(self.tab_widget, 1)

    # ============================================================
    # 顶部统计卡片
    # ============================================================
    def _create_stats_section(self, parent_layout):
        """创建统计卡片区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(30)

        # S级预警
        self._create_stat_item(layout, '🔥 S级预警', 's_count', '0', LEVEL_COLORS['S'])
        # A级预警
        self._create_stat_item(layout, '⭐ A级预警', 'a_count', '0', LEVEL_COLORS['A'])
        # B级预警
        self._create_stat_item(layout, '👀 B级预警', 'b_count', '0', LEVEL_COLORS['B'])
        # 今日总数
        self._create_stat_item(layout, '📊 今日总数', 'total_count', '0', DARK_COLORS['text_primary'])

        # 右侧：弹窗开关
        btn_layout = QVBoxLayout()
        btn_layout.addStretch()

        self.popup_btn = QPushButton('🔔 弹窗: 开')
        self.popup_btn.setCheckable(True)
        self.popup_btn.setChecked(True)
        self.popup_btn.clicked.connect(self._toggle_popup)
        self.popup_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                color: {DARK_COLORS['green']};
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:checked {{
                color: {DARK_COLORS['red']};
            }}
        """)
        btn_layout.addWidget(self.popup_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        parent_layout.addWidget(frame)

    def _create_stat_item(self, parent_layout, title, key, value, color):
        """创建单个统计项"""
        layout = QVBoxLayout()
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
        layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f'font-size: 28px; font-weight: bold; color: {color};')
        layout.addWidget(value_label)

        parent_layout.addLayout(layout)
        self._stat_labels[key] = value_label

    def _toggle_popup(self):
        """切换弹窗开关"""
        self._popup_enabled = self.popup_btn.isChecked()
        if self._popup_enabled:
            self.popup_btn.setText('🔔 弹窗: 开')
        else:
            self.popup_btn.setText('🔕 弹窗: 关')

    # ============================================================
    # Tab1: 实时预警
    # ============================================================
    def _create_current_alarm_tab(self):
        """创建实时预警Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 操作按钮行
        btn_layout = QHBoxLayout()

        clear_btn = QPushButton('🗑️ 清空当前')
        clear_btn.clicked.connect(self._clear_current)
        self._style_button(clear_btn)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # 预警表格
        self.current_table = QTableWidget()
        self.current_table.setColumnCount(8)
        self.current_table.setHorizontalHeaderLabels([
            '等级', '股票代码', '股票名称', '当前价', '涨跌幅',
            '信号', '评分', '时间'
        ])
        self.current_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.current_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.current_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.current_table.setStyleSheet(f"""
            QTableWidget {{
                background: {DARK_COLORS['bg_primary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                gridline-color: {DARK_COLORS['border']};
                color: {DARK_COLORS['text_primary']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                border: none;
                border-bottom: 1px solid {DARK_COLORS['border']};
                padding: 8px;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 6px;
                border: none;
            }}
        """)
        layout.addWidget(self.current_table, 1)

        self.tab_widget.addTab(widget, '🔔 实时预警')

    def _style_button(self, btn):
        """设置按钮样式"""
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                color: {DARK_COLORS['text_primary']};
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {DARK_COLORS['border']};
            }}
        """)

    # ============================================================
    # Tab2: 历史记录
    # ============================================================
    def _create_history_tab(self):
        """创建历史记录Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 操作按钮行
        btn_layout = QHBoxLayout()

        export_btn = QPushButton('📤 导出历史')
        export_btn.clicked.connect(self._export_history)
        self._style_button(export_btn)
        btn_layout.addWidget(export_btn)

        clear_history_btn = QPushButton('🗑️ 清空历史')
        clear_history_btn.clicked.connect(self._clear_history)
        self._style_button(clear_history_btn)
        btn_layout.addWidget(clear_history_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # 历史表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels([
            '等级', '股票代码', '股票名称', '价格', '涨跌幅',
            '信号', '评分', '时间'
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setStyleSheet(f"""
            QTableWidget {{
                background: {DARK_COLORS['bg_primary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                gridline-color: {DARK_COLORS['border']};
                color: {DARK_COLORS['text_primary']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                border: none;
                border-bottom: 1px solid {DARK_COLORS['border']};
                padding: 8px;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 6px;
                border: none;
            }}
        """)
        layout.addWidget(self.history_table, 1)

        self.tab_widget.addTab(widget, '📋 历史记录')

    # ============================================================
    # Tab3: V0.7 AI风险扫描（C5.2.3新增）
    # ============================================================
    def _create_ai_risk_tab(self):
        """创建AI风险扫描Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 操作按钮行
        btn_layout = QHBoxLayout()

        scan_btn = QPushButton('🔍 扫描风险股票')
        scan_btn.clicked.connect(self._scan_ai_risks)
        self._style_button(scan_btn)
        btn_layout.addWidget(scan_btn)

        # 风险阈值下拉
        self.ai_risk_threshold = QComboBox()
        self.ai_risk_threshold.addItems(['全部风险', '中风险以上', '高风险以上'])
        self.ai_risk_threshold.setStyleSheet(f"""
            QComboBox {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                color: {DARK_COLORS['text_primary']};
                padding: 6px 12px;
                font-size: 12px;
            }}
        """)
        btn_layout.addWidget(QLabel('阈值:'))
        btn_layout.addWidget(self.ai_risk_threshold)

        self.ai_risk_status = QLabel('点击扫描风险股票')
        self.ai_risk_status.setStyleSheet(f"color: {DARK_COLORS['text_secondary']}; font-size: 12px;")
        btn_layout.addWidget(self.ai_risk_status)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # AI风险表格
        self.ai_risk_table = QTableWidget()
        self.ai_risk_table.setColumnCount(7)
        self.ai_risk_table.setHorizontalHeaderLabels([
            '风险等级', '股票代码', '股票名称', 'SELL_SCORE',
            '触发信号', 'AI建议', '扫描时间'
        ])
        self.ai_risk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ai_risk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ai_risk_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.ai_risk_table.setStyleSheet(f"""
            QTableWidget {{
                background: {DARK_COLORS['bg_primary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                gridline-color: {DARK_COLORS['border']};
                color: {DARK_COLORS['text_primary']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                border: none;
                border-bottom: 1px solid {DARK_COLORS['border']};
                padding: 8px;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 6px;
                border: none;
            }}
        """)
        layout.addWidget(self.ai_risk_table, 1)

        self.tab_widget.addTab(widget, '🤖 AI风险扫描')

        # 初始化数据
        self._ai_risk_data = []

    def _scan_ai_risks(self):
        """扫描AI风险股票（V0.7 C5.2.3）"""
        from PyQt6.QtWidgets import QApplication
        self.ai_risk_status.setText('正在扫描风险股票...')
        QApplication.processEvents()

        try:
            # 确保项目根目录在 sys.path 中
            import sys as _sys
            import os as _os
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from dashboard.decision_adapter import get_decision_adapter
            adapter = get_decision_adapter()

            # 根据阈值过滤
            threshold_text = self.ai_risk_threshold.currentText()
            if '高风险' in threshold_text:
                min_score = 60
            elif '中风险' in threshold_text:
                min_score = 40
            else:
                min_score = 30

            risks = adapter.get_risk_warning_data(min_sell_score=min_score, n=50)

            self._ai_risk_data = risks
            self._refresh_ai_risk_table()

            high_count = sum(1 for r in risks if r.get('level') in ('高', '极高'))
            self.ai_risk_status.setText(
                f'扫描完成: 共{len(risks)}只风险股票 (高风险{high_count}只)'
            )

        except Exception as e:
            self.ai_risk_status.setText(f'扫描失败: {e}')
            import logging
            logging.getLogger(__name__).warning(f"AI风险扫描失败: {e}")

    def _refresh_ai_risk_table(self):
        """刷新AI风险表格"""
        risks = self._ai_risk_data
        self.ai_risk_table.setRowCount(len(risks))

        for row, risk in enumerate(risks):
            self._fill_ai_risk_row(row, risk)

    def _fill_ai_risk_row(self, row, risk):
        """填充AI风险单行数据"""
        from PyQt6.QtGui import QColor, QBrush

        # 风险等级
        level = risk.get('level', '低')
        level_item = QTableWidgetItem(level)
        if level in ('高', '极高'):
            level_item.setForeground(QBrush(QColor('#da3633')))
            level_item.setBackground(QBrush(QColor('#2d1212')))
        elif level == '中':
            level_item.setForeground(QBrush(QColor('#d29922')))
        else:
            level_item.setForeground(QBrush(QColor('#3fb950')))
        font = level_item.font()
        font.setBold(True)
        level_item.setFont(font)
        self.ai_risk_table.setItem(row, 0, level_item)

        # 股票代码
        self.ai_risk_table.setItem(row, 1, QTableWidgetItem(risk.get('code', '')))

        # 股票名称
        name_item = QTableWidgetItem(risk.get('name', ''))
        name_item.setForeground(QBrush(QColor('#58a6ff')))
        self.ai_risk_table.setItem(row, 2, name_item)

        # SELL_SCORE
        score = risk.get('sell_score', 0)
        score_item = QTableWidgetItem(f"{score:.0f}")
        if score >= 80:
            score_item.setForeground(QBrush(QColor('#da3633')))
        elif score >= 60:
            score_item.setForeground(QBrush(QColor('#f85149')))
        elif score >= 40:
            score_item.setForeground(QBrush(QColor('#d29922')))
        else:
            score_item.setForeground(QBrush(QColor('#8b949e')))
        font = score_item.font()
        font.setBold(True)
        score_item.setFont(font)
        self.ai_risk_table.setItem(row, 3, score_item)

        # 触发信号
        signals = risk.get('triggered_signals', [])
        if isinstance(signals, list):
            signal_text = '、'.join(signals[:4])
            if len(signals) > 4:
                signal_text += f'等{len(signals)}项'
        else:
            signal_text = str(signals)
        self.ai_risk_table.setItem(row, 4, QTableWidgetItem(signal_text))

        # AI建议
        suggestion = risk.get('suggestion', '')
        sug_item = QTableWidgetItem(suggestion)
        if suggestion in ('卖出', '减仓'):
            sug_item.setForeground(QBrush(QColor('#da3633')))
        elif suggestion == '持有':
            sug_item.setForeground(QBrush(QColor('#3fb950')))
        self.ai_risk_table.setItem(row, 5, sug_item)

        # 扫描时间
        from datetime import datetime
        self.ai_risk_table.setItem(row, 6, QTableWidgetItem(
            datetime.now().strftime('%H:%M:%S')
        ))

    # ============================================================
    # 外部接口：接收扫描结果
    # ============================================================
    def update_from_scan_result(self, results):
        """从扫描结果更新预警列表
        只读取已有数据，不重新计算
        """
        try:
            print(f"[ALARM DEBUG] 收到扫描结果: {len(results)}条")

            new_alarms = []

            for stock in results:
                try:
                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    price = stock.get('price', 0)
                    pct_chg = stock.get('pct_chg', 0)
                    signal_names = stock.get('signal_names', [])
                    score = stock.get('score', 0)

                    # 只有有信号的才加入预警
                    if not signal_names:
                        continue

                    # 判断预警等级
                    level = self._get_alarm_level(score)

                    alarm = {
                        'code': code,
                        'name': name,
                        'price': price,
                        'pct_chg': pct_chg,
                        'signals': signal_names,
                        'score': score,
                        'level': level,
                        'time': datetime.now().strftime('%H:%M:%S'),
                        'date': datetime.now().strftime('%Y-%m-%d')
                    }

                    new_alarms.append(alarm)

                    # 新预警弹窗提醒（S级和A级）
                    if self._popup_enabled and level in ['S', 'A']:
                        self._show_popup(alarm)

                except Exception:
                    continue

            # 统计各等级数量
            s_count = sum(1 for a in new_alarms if a['level'] == 'S')
            a_count = sum(1 for a in new_alarms if a['level'] == 'A')
            b_count = sum(1 for a in new_alarms if a['level'] == 'B')

            print(f"[ALARM DEBUG] 过滤后: {len(new_alarms)}条")
            print(f"[ALARM DEBUG] S级: {s_count}, A级: {a_count}, B级: {b_count}")

            # 更新当前预警列表
            self._current_alarms = sorted(new_alarms, key=lambda x: x['score'], reverse=True)

            # 添加到历史记录
            self._add_to_history(new_alarms)

            # 更新UI
            self._refresh_current_table()
            self._refresh_stats()

            print(f"[ALARM DEBUG] UI更新: 成功")
            print(f"[预警中心] 更新完成，共{len(self._current_alarms)}条预警")

        except Exception as e:
            log_error(str(e))
            print(f"[ALARM DEBUG] UI更新: 失败 - {e}")
            print(f"[预警中心] 更新失败: {e}")

    def _get_alarm_level(self, score):
        """根据评分判断预警等级"""
        if score >= 90:
            return 'S'
        elif score >= 80:
            return 'A'
        elif score >= 70:
            return 'B'
        else:
            return 'B'  # 70分以下也算B级观察

    def _show_popup(self, alarm):
        """显示弹窗提醒"""
        try:
            level = alarm['level']
            level_text = '🔥 S级 - 强烈关注' if level == 'S' else '⭐ A级 - 重点关注'
            color = LEVEL_COLORS.get(level, DARK_COLORS['accent'])

            signals_text = '、'.join(alarm['signals'][:3])
            if len(alarm['signals']) > 3:
                signals_text += f' 等{len(alarm["signals"])}个信号'

            msg = f"""
股票：{alarm['name']}({alarm['code']})
价格：{alarm['price']:.2f} 元
涨跌幅：{alarm['pct_chg']:+.2f}%
信号：{signals_text}
评分：{alarm['score']} 分
时间：{alarm['time']}
            """.strip()

            # 用QMessageBox提示（非阻塞）
            box = QMessageBox(self)
            box.setWindowTitle(f'【{level_text}】')
            box.setText(msg)
            box.setIcon(QMessageBox.Icon.Information)
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            # 3秒后自动关闭
            QTimer.singleShot(3000, box.close)
            box.show()

        except Exception as e:
            log_error(str(e))

    # ============================================================
    # UI 更新
    # ============================================================
    def _refresh_current_table(self):
        """刷新当前预警表格"""
        self.current_table.setRowCount(len(self._current_alarms))

        for row, alarm in enumerate(self._current_alarms):
            self._fill_alarm_row(self.current_table, row, alarm)

    def _refresh_history_table(self):
        """刷新历史记录表格"""
        self.history_table.setRowCount(len(self._history_alarms))

        for row, alarm in enumerate(self._history_alarms):
            self._fill_alarm_row(self.history_table, row, alarm)

    def _fill_alarm_row(self, table, row, alarm):
        """填充一行预警数据"""
        level = alarm.get('level', 'B')
        level_color = LEVEL_COLORS.get(level, DARK_COLORS['text_secondary'])

        # 等级
        level_item = QTableWidgetItem(level)
        level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        level_item.setForeground(QColor(level_color))
        level_item.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        table.setItem(row, 0, level_item)

        # 股票代码
        self._set_table_item(table, row, 1, alarm.get('code', ''))
        # 股票名称
        self._set_table_item(table, row, 2, alarm.get('name', ''))
        # 当前价
        self._set_table_item(table, row, 3, f"{alarm.get('price', 0):.2f}")

        # 涨跌幅
        pct = alarm.get('pct_chg', 0)
        pct_item = QTableWidgetItem(f'{pct:+.2f}%')
        pct_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if pct >= 0:
            pct_item.setForeground(QColor(DARK_COLORS['red']))
        else:
            pct_item.setForeground(QColor(DARK_COLORS['green']))
        table.setItem(row, 4, pct_item)

        # 信号
        signals = alarm.get('signals', [])
        signal_text = '、'.join(signals[:2])
        if len(signals) > 2:
            signal_text += f'...({len(signals)})'
        self._set_table_item(table, row, 5, signal_text)

        # 评分
        score = alarm.get('score', 0)
        score_item = QTableWidgetItem(str(score))
        score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if score >= 90:
            score_item.setForeground(QColor(LEVEL_COLORS['S']))
        elif score >= 80:
            score_item.setForeground(QColor(LEVEL_COLORS['A']))
        else:
            score_item.setForeground(QColor(LEVEL_COLORS['B']))
        table.setItem(row, 6, score_item)

        # 时间
        self._set_table_item(table, row, 7, alarm.get('time', ''))

    def _set_table_item(self, table, row, col, text):
        """设置表格项"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, col, item)

    def _refresh_stats(self):
        """刷新统计数据"""
        s_count = sum(1 for a in self._current_alarms if a['level'] == 'S')
        a_count = sum(1 for a in self._current_alarms if a['level'] == 'A')
        b_count = sum(1 for a in self._current_alarms if a['level'] == 'B')
        total = len(self._current_alarms)

        self._stat_labels['s_count'].setText(str(s_count))
        self._stat_labels['a_count'].setText(str(a_count))
        self._stat_labels['b_count'].setText(str(b_count))
        self._stat_labels['total_count'].setText(str(total))

    # ============================================================
    # 历史记录管理
    # ============================================================
    def _add_to_history(self, alarms):
        """添加到历史记录"""
        # 去重：同一天同一股票同一信号只保留一条
        today = datetime.now().strftime('%Y-%m-%d')

        for alarm in alarms:
            # 检查是否已存在
            exists = False
            for h in self._history_alarms:
                if (h.get('date') == today and
                    h.get('code') == alarm['code'] and
                    h.get('signals') == alarm['signals']):
                    exists = True
                    break

            if not exists:
                self._history_alarms.insert(0, alarm)

        # 最多保留500条
        if len(self._history_alarms) > 500:
            self._history_alarms = self._history_alarms[:500]

        self._save_history()
        self._refresh_history_table()

    def _load_history(self):
        """加载历史记录"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self._history_alarms = json.load(f)
                print(f"[预警中心] 加载历史记录，共{len(self._history_alarms)}条")
                self._refresh_history_table()
        except Exception as e:
            log_error(str(e))
            print(f"[预警中心] 加载历史记录失败: {e}")
            self._history_alarms = []

    def _save_history(self):
        """保存历史记录"""
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._history_alarms, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_error(str(e))
            print(f"[预警中心] 保存历史记录失败: {e}")

    def _clear_current(self):
        """清空当前预警"""
        reply = QMessageBox.question(
            self, '确认清空',
            '确定要清空当前预警列表吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._current_alarms = []
            self._refresh_current_table()
            self._refresh_stats()

    def _clear_history(self):
        """清空历史记录"""
        reply = QMessageBox.question(
            self, '确认清空',
            '确定要清空所有历史记录吗？此操作不可恢复！',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history_alarms = []
            self._save_history()
            self._refresh_history_table()

    def _export_history(self):
        """导出历史记录"""
        if not self._history_alarms:
            QMessageBox.information(self, '提示', '暂无历史记录')
            return

        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, '导出历史记录', 'alarm_history.csv', 'CSV文件 (*.csv)'
        )
        if not file_path:
            return

        try:
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['日期', '时间', '等级', '股票代码', '股票名称',
                                 '价格', '涨跌幅', '信号', '评分'])
                for alarm in self._history_alarms:
                    writer.writerow([
                        alarm.get('date', ''),
                        alarm.get('time', ''),
                        alarm.get('level', ''),
                        alarm.get('code', ''),
                        alarm.get('name', ''),
                        alarm.get('price', 0),
                        f"{alarm.get('pct_chg', 0):.2f}%",
                        '、'.join(alarm.get('signals', [])),
                        alarm.get('score', 0)
                    ])
            QMessageBox.information(self, '成功', f'历史记录已导出到：\n{file_path}')
        except Exception as e:
            log_error(str(e))
            QMessageBox.critical(self, '错误', f'导出失败：{e}')


# 全局单例
def get_alarm_center():
    """获取预警中心单例"""
    return AlarmCenterPanel()
