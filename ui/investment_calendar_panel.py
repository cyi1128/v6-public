# -*- coding: utf-8 -*-
"""
股票投资日历面板
显示新股申购/上市、分红除权、财报披露、限售解禁、宏观数据等
"""
from datetime import datetime, timedelta
from typing import List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTextEdit, QSplitter, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    ACCENT_GOLD, ACCENT_PURPLE, STATUS_SUCCESS, STATUS_INFO,
)
from data.investment_calendar import (
    CALENDAR_DATA, get_calendar_by_date, get_week_calendar,
    get_event_type_info, get_all_event_types, get_upcoming_events
)


class InvestmentCalendarPanel(QWidget):
    """股票投资日历面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
            QGroupBox {{
                color: {ACCENT_BLUE};
                font-weight: 700;
                border: 1px solid {BORDER};
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
            }}
            QComboBox, QTextEdit, QTableWidget {{
                background: {BG_INTERACTIVE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SOFT};
                border-radius: 6px;
            }}
            QPushButton {{
                background: {BG_INTERACTIVE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background: {BG_CARD};
                border-color: {BORDER_STRONG};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ===== 顶部标题栏 =====
        title_layout = QHBoxLayout()
        title_label = QLabel('📅 股票投资日历')
        title_label.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};')
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 日期导航
        self.prev_btn = QPushButton('◀ 前一天')
        self.prev_btn.clicked.connect(self._prev_day)
        title_layout.addWidget(self.prev_btn)

        self.date_label = QLabel()
        self.date_label.setStyleSheet(f'font-size: 14px; color: {ACCENT_BLUE}; padding: 0 10px;')
        self.date_label.setMinimumWidth(160)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(self.date_label)

        self.next_btn = QPushButton('后一天 ▶')
        self.next_btn.clicked.connect(self._next_day)
        title_layout.addWidget(self.next_btn)

        self.today_btn = QPushButton('今天')
        self.today_btn.clicked.connect(self._go_today)
        title_layout.addWidget(self.today_btn)

        self.week_btn = QPushButton('本周')
        self.week_btn.clicked.connect(self._show_week)
        title_layout.addWidget(self.week_btn)

        self.month_btn = QPushButton('未来30天')
        self.month_btn.clicked.connect(self._show_month)
        title_layout.addWidget(self.month_btn)

        layout.addLayout(title_layout)

        # ===== 主体：左侧事件列表 + 右侧详情 =====
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：事件列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 事件类型筛选
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel('筛选:'))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem('全部事件')
        for etype, info in get_all_event_types().items():
            self.filter_combo.addItem(f"{info['icon']} {info['name']}", etype)
        self.filter_combo.currentIndexChanged.connect(self._filter_events)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()
        left_layout.addLayout(filter_layout)

        # 事件表格
        self.event_table = QTableWidget(0, 5)
        self.event_table.setHorizontalHeaderLabels(['类型', '事件', '代码', '重要性', '详情'])
        self.event_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.event_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.event_table.setAlternatingRowColors(True)
        self.event_table.setStyleSheet(f'''
            QTableWidget {{ background: {BG_CONTAINER}; color: {TEXT_PRIMARY}; gridline-color: {BORDER}; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); }}
            QHeaderView::section {{ background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY}; padding: 4px; border: 1px solid {BORDER}; }}
        ''')
        self.event_table.verticalHeader().setVisible(False)
        left_layout.addWidget(self.event_table)

        splitter.addWidget(left_widget)

        # 右侧：详情 + 本周概览
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 当日详情
        detail_group = QGroupBox('📋 当日事件详情')
        detail_layout = QVBoxLayout(detail_group)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setStyleSheet(f'''
            QTextEdit {{ background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; padding: 8px; }}
        ''')
        detail_layout.addWidget(self.detail_text)
        right_layout.addWidget(detail_group, stretch=2)

        # 未来重要事件
        upcoming_group = QGroupBox('🔔 未来30天重要事件')
        upcoming_layout = QVBoxLayout(upcoming_group)
        self.upcoming_text = QTextEdit()
        self.upcoming_text.setReadOnly(True)
        self.upcoming_text.setStyleSheet(f'''
            QTextEdit {{ background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; padding: 8px; }}
        ''')
        upcoming_layout.addWidget(self.upcoming_text)
        right_layout.addWidget(upcoming_group, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setSizes([650, 400])

        layout.addWidget(splitter)

        # ===== 底部统计 =====
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        layout.addWidget(self.stats_label)

    def _load_data(self):
        """加载数据"""
        day_data = get_calendar_by_date(self.current_date)
        self._update_date_label()
        self._update_event_table(day_data.get('events', []))
        self._update_detail(day_data)
        self._update_upcoming()
        self._update_stats(day_data)

    def _update_date_label(self):
        """更新日期标签"""
        dt = datetime.strptime(self.current_date, '%Y-%m-%d')
        weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        weekday = weekday_names[dt.weekday()]
        self.date_label.setText(f'{self.current_date} {weekday}')

    def _update_event_table(self, events: List[Dict]):
        """更新事件表格"""
        # 筛选
        filter_type = self.filter_combo.currentData()
        if filter_type:
            events = [e for e in events if e.get('type') == filter_type]

        self.event_table.setRowCount(0)
        for row, event in enumerate(events):
            self.event_table.insertRow(row)

            # 类型
            type_info = get_event_type_info(event.get('type', 'other'))
            type_item = QTableWidgetItem(f"{type_info['icon']} {type_info['name']}")
            type_item.setForeground(QColor(type_info['color']))
            self.event_table.setItem(row, 0, type_item)

            # 事件标题
            title_item = QTableWidgetItem(event.get('title', ''))
            self.event_table.setItem(row, 1, title_item)

            # 代码
            code_item = QTableWidgetItem(event.get('code', '-'))
            self.event_table.setItem(row, 2, code_item)

            # 重要性
            importance = event.get('importance', 'medium')
            imp_map = {'high': '🔴 高', 'medium': '🟡 中', 'low': '🟢 低'}
            imp_item = QTableWidgetItem(imp_map.get(importance, '中'))
            self.event_table.setItem(row, 3, imp_item)

            # 详情
            detail_item = QTableWidgetItem(event.get('detail', ''))
            self.event_table.setItem(row, 4, detail_item)

    def _update_detail(self, day_data: Dict):
        """更新详情面板"""
        events = day_data.get('events', [])
        if not events:
            self.detail_text.setPlainText('当日无重要事件')
            return

        lines = []
        lines.append(f"📅 {day_data['date']} {day_data.get('weekday', '')}")
        lines.append('=' * 50)
        lines.append('')

        # 按类型分组
        by_type = {}
        for event in events:
            etype = event.get('type', 'other')
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(event)

        for etype, type_events in by_type.items():
            type_info = get_event_type_info(etype)
            lines.append(f"{type_info['icon']} 【{type_info['name']}】({len(type_events)}项)")
            lines.append('-' * 40)
            for event in type_events:
                code = event.get('code', '')
                code_str = f" ({code})" if code else ''
                lines.append(f"  • {event.get('title', '')}{code_str}")
                detail = event.get('detail', '')
                if detail:
                    lines.append(f"    {detail}")
            lines.append('')

        self.detail_text.setPlainText('\n'.join(lines))

    def _update_upcoming(self):
        """更新未来重要事件"""
        events = get_upcoming_events(days=30)
        if not events:
            self.upcoming_text.setPlainText('暂无未来重要事件')
            return

        lines = []
        current_date = ''
        for event in events:
            if event['date'] != current_date:
                current_date = event['date']
                lines.append(f"\n📆 {current_date} {event.get('weekday', '')}")
                lines.append('-' * 30)

            type_info = get_event_type_info(event.get('type', 'other'))
            importance = event.get('importance', 'medium')
            imp_icon = '🔴' if importance == 'high' else '🟡'
            lines.append(f"  {imp_icon} {type_info['icon']} {event.get('title', '')}")

        self.upcoming_text.setPlainText('\n'.join(lines))

    def _update_stats(self, day_data: Dict):
        """更新统计信息"""
        events = day_data.get('events', [])
        by_type = {}
        for event in events:
            etype = event.get('type', 'other')
            type_info = get_event_type_info(etype)
            name = type_info['name']
            by_type[name] = by_type.get(name, 0) + 1

        stats_str = f"当日共 {len(events)} 项事件 | "
        stats_str += ' | '.join([f"{k}:{v}" for k, v in by_type.items()])
        self.stats_label.setText(stats_str)

    def _filter_events(self):
        """筛选事件"""
        day_data = get_calendar_by_date(self.current_date)
        self._update_event_table(day_data.get('events', []))

    def _prev_day(self):
        """前一天"""
        dt = datetime.strptime(self.current_date, '%Y-%m-%d')
        dt -= timedelta(days=1)
        self.current_date = dt.strftime('%Y-%m-%d')
        self._load_data()

    def _next_day(self):
        """后一天"""
        dt = datetime.strptime(self.current_date, '%Y-%m-%d')
        dt += timedelta(days=1)
        self.current_date = dt.strftime('%Y-%m-%d')
        self._load_data()

    def _go_today(self):
        """回到今天"""
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        self._load_data()

    def _show_week(self):
        """显示本周"""
        week_data = get_week_calendar()
        if not week_data:
            return

        # 合并本周所有事件
        all_events = []
        for day in week_data:
            for event in day.get('events', []):
                event_copy = dict(event)
                event_copy['title'] = f"[{day['date'][5:]}] {event.get('title', '')}"
                all_events.append(event_copy)

        self._update_event_table(all_events)
        self.date_label.setText(f"本周 ({week_data[0]['date'][5:]} ~ {week_data[-1]['date'][5:]})")

    def _show_month(self):
        """显示未来30天"""
        from datetime import datetime, timedelta
        today = datetime.now()
        end_date = today + timedelta(days=30)
        month_data = get_calendar_range(
            today.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        if not month_data:
            return

        # 合并未来30天所有事件
        all_events = []
        for day in month_data:
            for event in day.get('events', []):
                event_copy = dict(event)
                event_copy['title'] = f"[{day['date'][5:]}] {event.get('title', '')}"
                all_events.append(event_copy)

        self._update_event_table(all_events)
        self.date_label.setText(f"未来30天 ({month_data[0]['date'][5:]} ~ {month_data[-1]['date'][5:]})")

        # 详情显示未来30天汇总
        lines = ['📅 未来30天投资日历汇总', '=' * 50, '']
        for day in month_data:
            events = day.get('events', [])
            if events:
                lines.append(f"\n📆 {day['date']} {day.get('weekday', '')} ({len(events)}项)")
                for event in events:
                    type_info = get_event_type_info(event.get('type', 'other'))
                    imp = event.get('importance', 'medium')
                    imp_icon = '🔴' if imp == 'high' else '🟡' if imp == 'medium' else '⚪'
                    lines.append(f"  {imp_icon} {type_info['icon']} {event.get('title', '')}")
                    if event.get('detail'):
                        lines.append(f"     {event['detail'][:80]}")
        self.detail_text.setPlainText('\n'.join(lines))
        self._update_upcoming()

        # 详情显示本周汇总
        lines = ['📅 本周投资日历汇总', '=' * 50, '']
        for day in week_data:
            events = day.get('events', [])
            if events:
                lines.append(f"\n📆 {day['date']} {day.get('weekday', '')} ({len(events)}项)")
                for event in events:
                    type_info = get_event_type_info(event.get('type', 'other'))
                    lines.append(f"  {type_info['icon']} {event.get('title', '')}")
        self.detail_text.setPlainText('\n'.join(lines))

        # 统计
        total = sum(len(d.get('events', [])) for d in week_data)
        self.stats_label.setText(f"本周共 {total} 项事件")
