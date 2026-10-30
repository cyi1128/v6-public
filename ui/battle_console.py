# -*- coding: utf-8 -*-
"""
量化交易作战中控台 - 主窗口
深色金融量化终端风格，参考专业交易作战台布局。
保留现有真实行情、策略、数据接口，不使用模拟数据。
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy, QApplication,
    QSplitter, QTabWidget, QStatusBar, QToolButton, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

# 统一数据适配层
from ui.battle_console_data import get_data_adapter


# ============================================================
# 颜色常量（深色金融风格）
# ============================================================
class BC:
    BG_MAIN = '#0a0e1a'        # 主背景深蓝黑
    BG_CARD = '#111827'        # 卡片背景
    BG_CARD_HOVER = '#1a2332'  # 卡片悬停
    BG_TAB = '#0f1623'         # Tab背景
    BG_TAB_ACTIVE = '#1e3a5f'  # Tab激活（蓝紫色）
    BORDER = '#1e293b'         # 边框
    BORDER_LIGHT = '#334155'   # 浅边框
    TEXT_PRIMARY = '#e2e8f0'   # 主文字
    TEXT_SECONDARY = '#94a3b8' # 次要文字
    TEXT_MUTED = '#64748b'     # 弱化文字
    ACCENT = '#3b82f6'         # 主强调蓝
    ACCENT_PURPLE = '#8b5cf6'  # 紫色强调
    RED = '#ef4444'             # 上涨/风险红
    GREEN = '#22c55e'           # 确认/盈利绿
    YELLOW = '#eab308'          # 观察/预警黄
    ORANGE = '#f97316'          # 橙
    CYAN = '#06b6d4'            # 青


# ============================================================
# 通用卡片组件
# ============================================================
class BCCard(QFrame):
    """作战中控台通用卡片"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            BCCard {{
                background: {BC.BG_CARD};
                border: 1px solid {BC.BORDER};
                border-radius: 8px;
            }}
            BCCard:hover {{
                border: 1px solid {BC.BORDER_LIGHT};
            }}
        """)
        self.setFrameShape(QFrame.Shape.StyledPanel)


class BCLabel(QLabel):
    """作战中控台标签"""
    def __init__(self, text='', color=BC.TEXT_PRIMARY, size=12, bold=False, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            color: {color};
            font-size: {size}px;
            font-weight: {'bold' if bold else 'normal'};
            background: transparent;
        """)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


# ============================================================
# 顶部状态栏
# ============================================================
class TopStatusBar(QFrame):
    """顶部状态栏"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"""
            TopStatusBar {{
                background: {BC.BG_CARD};
                border-bottom: 1px solid {BC.BORDER};
            }}
        """)
        self._build_ui()
        self._start_timer()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # 左侧：标题 + 服务状态
        left = QHBoxLayout()
        left.setSpacing(12)

        title = BCLabel('量化交易驾驶舱 V6.5', BC.TEXT_PRIMARY, 15, True)
        left.addWidget(title)

        # 分隔线
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f'background: {BC.BORDER};')
        left.addWidget(sep)

        # 行情服务
        self.quote_status = self._status_item('行情服务', '在线', BC.GREEN)
        left.addLayout(self.quote_status)

        # 交易进程
        self.trade_status = self._status_item('交易进程', '运行中', BC.GREEN)
        left.addLayout(self.trade_status)

        # 自动交易
        self.auto_trade = self._status_item('自动交易', '实盘已关', BC.YELLOW)
        left.addLayout(self.auto_trade)

        # 尾盘时间
        self.tail_time = BCLabel('尾盘 --:--:--', BC.CYAN, 12, True)
        left.addWidget(self.tail_time)

        layout.addLayout(left)
        layout.addStretch()

        # 右侧：统计数据
        right = QHBoxLayout()
        right.setSpacing(20)

        self.today_first_board = self._stat_item('今日首板', '0', BC.RED)
        right.addLayout(self.today_first_board)

        self.final_candidates = self._stat_item('最终候选', '0', BC.ACCENT_PURPLE)
        right.addLayout(self.final_candidates)

        self.holding_count = self._stat_item('持仓股票', '0', BC.GREEN)
        right.addLayout(self.holding_count)

        self.available_funds = self._stat_item('可用资金', '0万', BC.YELLOW)
        right.addLayout(self.available_funds)

        # 分隔线
        sep2 = QFrame()
        sep2.setFixedWidth(1)
        sep2.setStyleSheet(f'background: {BC.BORDER};')
        right.addWidget(sep2)

        # 按钮
        self.btn_settings = self._icon_button('⚙')
        self.btn_message = self._icon_button('🔔')
        self.btn_run_status = self._icon_button('▶ 运行状态')
        right.addWidget(self.btn_settings)
        right.addWidget(self.btn_message)
        right.addWidget(self.btn_run_status)

        layout.addLayout(right)

    def _status_item(self, label, value, color):
        layout = QHBoxLayout()
        layout.setSpacing(4)
        dot = BCLabel('●', color, 10)
        text = BCLabel(f'{label}:{value}', BC.TEXT_SECONDARY, 11)
        layout.addWidget(dot)
        layout.addWidget(text)
        return layout

    def _stat_item(self, label, value, color):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        l = BCLabel(label, BC.TEXT_MUTED, 10)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v = BCLabel(value, color, 14, True)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(l)
        layout.addWidget(v)
        return layout

    def _icon_button(self, text):
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {BC.BG_TAB};
                color: {BC.TEXT_SECONDARY};
                border: 1px solid {BC.BORDER};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {BC.BG_CARD_HOVER};
                color: {BC.TEXT_PRIMARY};
                border-color: {BC.BORDER_LIGHT};
            }}
        """)
        return btn

    def _start_timer(self):
        """启动定时器更新时间和数据"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(1000)
        self._update()

    def _update(self):
        """更新顶部状态栏数据"""
        now = datetime.now()
        self.tail_time.setText(f'尾盘 {now.strftime("%H:%M:%S")}')

        # 每30秒更新一次统计数据
        if now.second % 30 == 0:
            try:
                data = get_data_adapter().get_top_bar_data()
                self.today_first_board.itemAt(1).widget().setText(str(data.get('today_first_board', 0)))
                self.final_candidates.itemAt(1).widget().setText(str(data.get('final_candidates', 0)))
                self.holding_count.itemAt(1).widget().setText(str(data.get('holding_count', 0)))
                funds = data.get('available_funds', 0)
                self.available_funds.itemAt(1).widget().setText(f'{funds/10000:.1f}万' if funds > 10000 else f'{funds:.0f}')
            except Exception:
                pass


# ============================================================
# 横向Tab导航
# ============================================================
class TabNav(QFrame):
    """横向Tab导航"""
    tab_changed = pyqtSignal(int)

    TABS = [
        ('盘前新闻', False),
        ('盘前竞价', False),
        ('收盘首板', True),   # 默认选中
        ('自选评分', False),
        ('持仓监控', False),
        ('尾盘选股', True),   # NEW突出
        ('早盘竞价', False),
        ('个股分析', False),
        ('运行日志', False),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(f"""
            TabNav {{
                background: {BC.BG_TAB};
                border-bottom: 1px solid {BC.BORDER};
            }}
        """)
        self.buttons = []
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        for i, (name, highlight) in enumerate(self.TABS):
            btn = QPushButton()
            if highlight and name == '尾盘选股':
                btn.setText(f'  {name} NEW  ')
            else:
                btn.setText(f'  {name}  ')
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._on_tab_clicked(idx))

            if i == 2:  # 收盘首板默认选中
                btn.setStyleSheet(self._active_style(highlight))
            else:
                btn.setStyleSheet(self._normal_style(highlight))

            self.buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

    def _normal_style(self, highlight=False):
        color = BC.ACCENT_PURPLE if highlight else BC.TEXT_SECONDARY
        border = BC.ACCENT_PURPLE if highlight else BC.BORDER
        return f"""
            QPushButton {{
                background: transparent;
                color: {color};
                border: 1px solid {border};
                border-radius: 6px;
                font-size: 12px;
                font-weight: {'bold' if highlight else 'normal'};
            }}
            QPushButton:hover {{
                background: {BC.BG_CARD_HOVER};
                color: {BC.TEXT_PRIMARY};
            }}
        """

    def _active_style(self, highlight=False):
        return f"""
            QPushButton {{
                background: {BC.BG_TAB_ACTIVE};
                color: {BC.TEXT_PRIMARY};
                border: 1px solid {BC.ACCENT};
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #2a4a6f;
            }}
        """

    def _on_tab_clicked(self, idx):
        for i, btn in enumerate(self.buttons):
            _, highlight = self.TABS[i]
            if i == idx:
                btn.setStyleSheet(self._active_style(highlight))
            else:
                btn.setStyleSheet(self._normal_style(highlight))
        self.tab_changed.emit(idx)


# ============================================================
# 市场概况卡片（右侧）
# ============================================================
class MarketOverviewCard(BCCard):
    """市场概况卡片"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._start_timer()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 标题
        header = QHBoxLayout()
        title = BCLabel('市场概况', BC.TEXT_PRIMARY, 13, True)
        more = BCLabel('更多 >', BC.TEXT_MUTED, 11)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(more)
        layout.addLayout(header)

        # 指数行情（3列）
        index_layout = QGridLayout()
        index_layout.setSpacing(8)

        self.sh_label = BCLabel('上证指数', BC.TEXT_MUTED, 10)
        self.sh_value = BCLabel('--', BC.TEXT_PRIMARY, 14, True)
        self.sh_pct = BCLabel('--', BC.TEXT_MUTED, 11)

        self.sz_label = BCLabel('深证成指', BC.TEXT_MUTED, 10)
        self.sz_value = BCLabel('--', BC.TEXT_PRIMARY, 14, True)
        self.sz_pct = BCLabel('--', BC.TEXT_MUTED, 11)

        self.cyb_label = BCLabel('创业板指', BC.TEXT_MUTED, 10)
        self.cyb_value = BCLabel('--', BC.TEXT_PRIMARY, 14, True)
        self.cyb_pct = BCLabel('--', BC.TEXT_MUTED, 11)

        self.amount_label = BCLabel('沪深成交额', BC.TEXT_MUTED, 10)
        self.amount_value = BCLabel('--', BC.YELLOW, 14, True)

        for col, (label, value, pct) in enumerate([
            (self.sh_label, self.sh_value, self.sh_pct),
            (self.sz_label, self.sz_value, self.sz_pct),
            (self.cyb_label, self.cyb_value, self.cyb_pct),
        ]):
            index_layout.addWidget(label, 0, col)
            index_layout.addWidget(value, 1, col)
            index_layout.addWidget(pct, 2, col)

        index_layout.addWidget(self.amount_label, 0, 3)
        index_layout.addWidget(self.amount_value, 1, 3)

        layout.addLayout(index_layout)

        # 分隔线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f'background: {BC.BORDER};')
        layout.addWidget(sep)

        # 市场统计（4列）
        stats_layout = QGridLayout()
        stats_layout.setSpacing(8)

        self.lu_label = BCLabel('涨停家数', BC.TEXT_MUTED, 10)
        self.lu_value = BCLabel('--', BC.RED, 16, True)
        self.ld_label = BCLabel('跌停家数', BC.TEXT_MUTED, 10)
        self.ld_value = BCLabel('--', BC.GREEN, 16, True)
        self.mc_label = BCLabel('连板高度', BC.TEXT_MUTED, 10)
        self.mc_value = BCLabel('--', BC.ORANGE, 16, True)
        self.ms_label = BCLabel('市场情绪', BC.TEXT_MUTED, 10)
        self.ms_value = BCLabel('--', BC.CYAN, 16, True)

        for col, (label, value) in enumerate([
            (self.lu_label, self.lu_value),
            (self.ld_label, self.ld_value),
            (self.mc_label, self.mc_value),
            (self.ms_label, self.ms_value),
        ]):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stats_layout.addWidget(label, 0, col)
            stats_layout.addWidget(value, 1, col)

        layout.addLayout(stats_layout)

    def _start_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(30000)  # 30秒更新
        self._update()

    def _update(self):
        try:
            data = get_data_adapter().get_market_overview()

            self.sh_value.setText(f"{data['sh_index']:.2f}" if data['sh_index'] > 0 else '--')
            sh_pct = data['sh_pct']
            self.sh_pct.setText(f"{sh_pct:+.2f}%" if sh_pct != 0 else '--')
            self.sh_pct.setStyleSheet(f'color: {BC.RED if sh_pct >= 0 else BC.GREEN}; font-size: 11px;')

            self.sz_value.setText(f"{data['sz_index']:.2f}" if data['sz_index'] > 0 else '--')
            sz_pct = data['sz_pct']
            self.sz_pct.setText(f"{sz_pct:+.2f}%" if sz_pct != 0 else '--')
            self.sz_pct.setStyleSheet(f'color: {BC.RED if sz_pct >= 0 else BC.GREEN}; font-size: 11px;')

            self.cyb_value.setText(f"{data['cyb_index']:.2f}" if data['cyb_index'] > 0 else '--')
            cyb_pct = data['cyb_pct']
            self.cyb_pct.setText(f"{cyb_pct:+.2f}%" if cyb_pct != 0 else '--')
            self.cyb_pct.setStyleSheet(f'color: {BC.RED if cyb_pct >= 0 else BC.GREEN}; font-size: 11px;')

            self.amount_value.setText(f"{data['total_amount']:.1f}亿" if data['total_amount'] > 0 else '--')
            self.lu_value.setText(str(data['limit_up_count']))
            self.ld_value.setText(str(data['limit_down_count']))
            self.mc_value.setText(f"{data['max_consecutive']}板" if data['max_consecutive'] > 0 else '--')
            self.ms_value.setText(str(data['market_sentiment']))
        except Exception as e:
            print(f"[中控台] 市场概况更新失败: {e}", flush=True)


# ============================================================
# 首板候选大卡片
# ============================================================
class FirstBoardCard(BCCard):
    """首板候选大卡片"""
    def __init__(self, rank=1, data=None, parent=None):
        super().__init__(parent)
        self.rank = rank
        self.data = data or {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # 顶部：排名 + 代码名称 + 评分
        top = QHBoxLayout()

        rank_color = BC.RED if self.rank == 1 else BC.ACCENT_PURPLE
        rank_label = BCLabel(f'{self.rank}', rank_color, 20, True)
        top.addWidget(rank_label)

        code = self.data.get('code', '------')
        name = self.data.get('name', '加载中...')
        code_name = BCLabel(f'{code}  {name}', BC.TEXT_PRIMARY, 15, True)
        top.addWidget(code_name)
        top.addStretch()

        score = self.data.get('score', 0)
        score_label = BCLabel(f'评分 {score:.2f}' if score > 0 else '评分 --', BC.YELLOW, 14, True)
        top.addWidget(score_label)

        layout.addLayout(top)

        # 行业 + 涨跌幅
        info = QHBoxLayout()
        industry = self.data.get('industry', '--')
        pct = self.data.get('pct_chg', 0)
        pct_color = BC.RED if pct >= 0 else BC.GREEN
        industry_label = BCLabel(industry, BC.TEXT_SECONDARY, 12)
        pct_label = BCLabel(f'高开/涨幅 {pct:+.2f}%', pct_color, 12, True)
        info.addWidget(industry_label)
        info.addStretch()
        info.addWidget(pct_label)
        layout.addLayout(info)

        # 标签
        tags = QHBoxLayout()
        tags.setSpacing(6)
        tag_data = self.data.get('tags', [])
        if not tag_data:
            tag_data = ['首板', '未读取', '封单--', '炸板0次', '热度--', '逻辑--']
        for tag in tag_data[:6]:
            tag_label = BCLabel(tag, BC.TEXT_SECONDARY, 10)
            tag_label.setStyleSheet(f"""
                color: {BC.TEXT_SECONDARY};
                background: {BC.BG_TAB};
                border: 1px solid {BC.BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
            """)
            tags.addWidget(tag_label)
        tags.addStretch()
        layout.addLayout(tags)

        # 入选时间 + 最近5日
        bottom = QHBoxLayout()
        select_time = self.data.get('select_time', '--')
        time_label = BCLabel(f'入选时间：{select_time}', BC.TEXT_MUTED, 11)
        bottom.addWidget(time_label)
        bottom.addStretch()

        # 最近5日涨跌幅
        recent_5d = self.data.get('recent_5d', [])
        if recent_5d:
            for pct in recent_5d[:5]:
                color = BC.RED if pct >= 0 else BC.GREEN
                d = BCLabel(f'{pct:+.2f}%', color, 11)
                bottom.addWidget(d)
        else:
            for _ in range(5):
                d = BCLabel('--', BC.TEXT_MUTED, 11)
                bottom.addWidget(d)

        layout.addLayout(bottom)

        # 系统分析
        analysis = self.data.get('analysis', '数据加载中...')
        analysis_label = BCLabel(analysis, BC.TEXT_SECONDARY, 11)
        analysis_label.setWordWrap(True)
        layout.addWidget(analysis_label)


# ============================================================
# 热门板块卡片
# ============================================================
class HotSectorCard(BCCard):
    """热门板块卡片"""
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.data = data or {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # 标题
        header = QHBoxLayout()
        name = self.data.get('name', '板块加载中...')
        title = BCLabel(name, BC.TEXT_PRIMARY, 13, True)
        more = BCLabel('更多 >', BC.TEXT_MUTED, 11)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(more)
        layout.addLayout(header)

        # 板块指标
        stats = QHBoxLayout()
        pct = self.data.get('pct_chg', 0)
        pct_color = BC.RED if pct >= 0 else BC.GREEN
        fund = self.data.get('fund_flow', 0)
        fund_color = BC.RED if fund >= 0 else BC.GREEN
        lu_count = self.data.get('limit_up_count', 0)

        stats.addWidget(BCLabel(f'涨幅 {pct:+.2f}%', pct_color, 12, True))
        stats.addWidget(BCLabel(f'资金 {fund:+.1f}亿', fund_color, 12, True))
        stats.addWidget(BCLabel(f'涨停 {lu_count}只', BC.ORANGE, 12, True))
        stats.addStretch()
        layout.addLayout(stats)

        # 板块内股票
        stocks = self.data.get('stocks', [])
        for i, stock in enumerate(stocks[:3]):
            row = QHBoxLayout()
            rank = BCLabel(f'{i+1}.', BC.TEXT_MUTED, 11)
            code = stock.get('code', '')
            name = stock.get('name', '')
            price = stock.get('price', 0)
            s_label = BCLabel(f'{code}  {name}', BC.TEXT_SECONDARY, 11)
            p_label = BCLabel(f'{price:.2f}', BC.TEXT_PRIMARY, 11, True)
            status = BCLabel(stock.get('status', '未读取'), BC.TEXT_MUTED, 10)
            row.addWidget(rank)
            row.addWidget(s_label)
            row.addStretch()
            row.addWidget(p_label)
            row.addSpacing(8)
            row.addWidget(status)
            layout.addLayout(row)


# ============================================================
# 尾盘选股卡片
# ============================================================
class TailStockCard(BCCard):
    """尾盘选股候选卡片"""
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.data = data or {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # 顶部：定稿时间
        top = QHBoxLayout()
        time_label = BCLabel('14:52 定稿·2只最强', BC.YELLOW, 12, True)
        date_label = BCLabel(f'({datetime.now().strftime("%Y-%m-%d %H:%M")})', BC.TEXT_MUTED, 10)
        top.addWidget(time_label)
        top.addWidget(date_label)
        top.addStretch()
        layout.addLayout(top)

        # 股票信息
        info = QHBoxLayout()
        code = self.data.get('code', '------')
        name = self.data.get('name', '加载中...')
        score = self.data.get('score', 0)
        ai_level = self.data.get('ai_level', '数据不足')
        ai_color = {'可买': BC.GREEN, '观察': BC.YELLOW, '风险': BC.RED}.get(ai_level, BC.TEXT_MUTED)

        info.addWidget(BCLabel(f'{code}  {name}', BC.TEXT_PRIMARY, 14, True))
        info.addSpacing(12)
        info.addWidget(BCLabel(f'分 {score:.1f}', BC.ACCENT_PURPLE, 13, True))
        info.addSpacing(8)
        info.addWidget(BCLabel(f'AI:{ai_level}', ai_color, 12, True))
        info.addStretch()

        # 查看K线按钮
        btn_kline = QPushButton('📊 查看K线')
        btn_kline.setFixedHeight(28)
        btn_kline.setStyleSheet(f"""
            QPushButton {{
                background: {BC.BG_TAB_ACTIVE};
                color: {BC.TEXT_PRIMARY};
                border: 1px solid {BC.ACCENT};
                border-radius: 4px;
                font-size: 11px;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background: #2a4a6f; }}
        """)
        info.addWidget(btn_kline)
        layout.addLayout(info)

        # 价格和涨幅
        price_row = QHBoxLayout()
        price = self.data.get('price', 0)
        pct = self.data.get('pct_chg', 0)
        pct_color = BC.RED if pct >= 0 else BC.GREEN
        price_row.addWidget(BCLabel(f'现价 {price:.2f}', BC.TEXT_PRIMARY, 12, True))
        price_row.addSpacing(12)
        price_row.addWidget(BCLabel(f'今日 {pct:+.2f}%', pct_color, 12, True))
        price_row.addStretch()

        # 最近5日
        recent_5d = self.data.get('recent_5d', [])
        if recent_5d:
            price_row.addWidget(BCLabel('最近5日:', BC.TEXT_MUTED, 10))
            for p in recent_5d[:5]:
                c = BC.RED if p >= 0 else BC.GREEN
                price_row.addWidget(BCLabel(f'{p:+.2f}%', c, 10))
        layout.addLayout(price_row)

        # 次日预期
        expect_row = QHBoxLayout()
        high_win = self.data.get('next_high_win', 0)
        low_risk = self.data.get('next_low_risk', 0)
        expect_row.addWidget(BCLabel(f'次日高开胜率:{high_win}%', BC.GREEN, 11, True))
        expect_row.addSpacing(20)
        expect_row.addWidget(BCLabel(f'次日低开风险:{low_risk}%', BC.RED, 11, True))
        expect_row.addStretch()
        layout.addLayout(expect_row)

        # 标签
        tags = self.data.get('tags', [])
        if tags:
            tag_row = QHBoxLayout()
            tag_row.setSpacing(6)
            for tag in tags[:5]:
                t = BCLabel(tag, BC.CYAN, 10)
                t.setStyleSheet(f"""
                    color: {BC.CYAN};
                    background: rgba(6,182,212,0.1);
                    border: 1px solid {BC.CYAN};
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 10px;
                """)
                tag_row.addWidget(t)
            tag_row.addStretch()
            layout.addLayout(tag_row)

        # 板块和资金
        sector_row = QHBoxLayout()
        sector = self.data.get('sector', '--')
        fund = self.data.get('fund_flow', 0)
        linkage = self.data.get('linkage_count', 0)
        sector_row.addWidget(BCLabel(f'板块:{sector}', BC.TEXT_SECONDARY, 11))
        sector_row.addSpacing(16)
        fund_color = BC.RED if fund >= 0 else BC.GREEN
        sector_row.addWidget(BCLabel(f'资金:{fund:+.2f}亿', fund_color, 11))
        sector_row.addSpacing(16)
        sector_row.addWidget(BCLabel(f'同板块联动:{linkage}只', BC.ACCENT_PURPLE, 11))
        sector_row.addStretch()
        layout.addLayout(sector_row)

        # 分析原因
        reason = self.data.get('reason', '')
        if reason:
            reason_label = BCLabel(reason, BC.TEXT_SECONDARY, 11)
            reason_label.setWordWrap(True)
            layout.addWidget(reason_label)


# ============================================================
# 已卖出跟踪卡片（右侧）
# ============================================================
class SoldTrackingCard(BCCard):
    """已卖出跟踪卡片"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # 标题
        header = QHBoxLayout()
        title = BCLabel('已卖出跟踪（3天）', BC.TEXT_PRIMARY, 13, True)
        more = BCLabel('更多 >', BC.TEXT_MUTED, 11)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(more)
        layout.addLayout(header)

        # 表头
        table_header = QHBoxLayout()
        for text, w in [('股票', 80), ('卖出价', 50), ('现价', 50), ('涨跌幅', 50), ('卖出时间', 60)]:
            l = BCLabel(text, BC.TEXT_MUTED, 10)
            l.setFixedWidth(w)
            table_header.addWidget(l)
        table_header.addStretch()
        layout.addLayout(table_header)

        # 数据行容器
        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(4)
        layout.addLayout(self.rows_container)
        layout.addStretch()

    def _load_data(self):
        try:
            data = get_data_adapter().get_sold_tracking(days=3)
            for item in data[:6]:
                row = QHBoxLayout()
                name = item.get('name', '--')
                sell_price = item.get('sell_price', 0)
                cur_price = item.get('current_price', 0)
                pct = item.get('pct_chg', 0)
                sell_time = item.get('sell_time', '--')

                pct_color = BC.RED if pct >= 0 else BC.GREEN

                for text, w, color in [
                    (name, 80, BC.TEXT_PRIMARY),
                    (f'{sell_price:.2f}', 50, BC.TEXT_SECONDARY),
                    (f'{cur_price:.2f}', 50, BC.TEXT_PRIMARY),
                    (f'{pct:+.2f}%', 50, pct_color),
                    (sell_time, 60, BC.TEXT_MUTED),
                ]:
                    l = BCLabel(text, color, 10)
                    l.setFixedWidth(w)
                    row.addWidget(l)
                row.addStretch()
                self.rows_container.addLayout(row)
        except Exception as e:
            print(f"[中控台] 已卖出跟踪加载失败: {e}", flush=True)


# ============================================================
# 候选池卡片（右侧）
# ============================================================
class CandidatePoolCard(BCCard):
    """候选池（AI实时对比）卡片"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # 标题
        header = QHBoxLayout()
        title = BCLabel('候选池（AI实时对比）', BC.TEXT_PRIMARY, 13, True)
        more = BCLabel('更多 >', BC.TEXT_MUTED, 11)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(more)
        layout.addLayout(header)

        # 表头
        table_header = QHBoxLayout()
        for text, w in [('代码', 55), ('名称', 55), ('现价', 45), ('涨跌幅', 50), ('评分', 40), ('AI', 35), ('板块', 50), ('状态', 40)]:
            l = BCLabel(text, BC.TEXT_MUTED, 9)
            l.setFixedWidth(w)
            table_header.addWidget(l)
        table_header.addStretch()
        layout.addLayout(table_header)

        # 数据行容器
        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(4)
        layout.addLayout(self.rows_container)
        layout.addStretch()

    def _load_data(self):
        try:
            data = get_data_adapter().get_candidate_pool()
            for item in data[:8]:
                row = QHBoxLayout()
                code = item.get('code', '--')
                name = item.get('name', '--')
                price = item.get('price', 0)
                pct = item.get('pct_chg', 0)
                score = item.get('score', 0)
                ai = item.get('ai_level', '--')
                sector = item.get('sector', '--')
                status = item.get('status', '--')

                pct_color = BC.RED if pct >= 0 else BC.GREEN
                status_color = {'启动': BC.GREEN, '观察': BC.YELLOW, '预警': BC.ORANGE, '淘汰': BC.RED}.get(status, BC.TEXT_MUTED)
                ai_color = {'可买': BC.GREEN, '观察': BC.YELLOW, '风险': BC.RED}.get(ai, BC.TEXT_MUTED)

                for text, w, color in [
                    (code, 55, BC.TEXT_SECONDARY),
                    (name, 55, BC.TEXT_PRIMARY),
                    (f'{price:.2f}', 45, BC.TEXT_PRIMARY),
                    (f'{pct:+.2f}%', 50, pct_color),
                    (f'{score:.0f}', 40, BC.ACCENT_PURPLE),
                    (ai, 35, ai_color),
                    (sector, 50, BC.TEXT_SECONDARY),
                    (status, 40, status_color),
                ]:
                    l = BCLabel(text, color, 9)
                    l.setFixedWidth(w)
                    row.addWidget(l)
                row.addStretch()
                self.rows_container.addLayout(row)
        except Exception as e:
            print(f"[中控台] 候选池加载失败: {e}", flush=True)


# ============================================================
# 首页（收盘首板页面）
# ============================================================
class FirstBoardPage(QWidget):
    """收盘首板页面（首页）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 左侧75%
        left = QWidget()
        left.setMinimumWidth(800)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # 最终两只首板候选
        title1 = BCLabel('最终两只首板候选', BC.TEXT_PRIMARY, 14, True)
        left_layout.addWidget(title1)

        fb_layout = QHBoxLayout()
        fb_layout.setSpacing(12)
        self.fb_card1 = FirstBoardCard(rank=1)
        self.fb_card2 = FirstBoardCard(rank=2)
        fb_layout.addWidget(self.fb_card1, 1)
        fb_layout.addWidget(self.fb_card2, 1)
        left_layout.addLayout(fb_layout)

        # 热门板块前三强
        title2 = BCLabel('热门板块前三强', BC.TEXT_PRIMARY, 14, True)
        left_layout.addWidget(title2)

        sector_layout = QHBoxLayout()
        sector_layout.setSpacing(12)
        self.sector_card1 = HotSectorCard()
        self.sector_card2 = HotSectorCard()
        self.sector_card3 = HotSectorCard()
        sector_layout.addWidget(self.sector_card1, 1)
        sector_layout.addWidget(self.sector_card2, 1)
        sector_layout.addWidget(self.sector_card3, 1)
        left_layout.addLayout(sector_layout)

        # 尾盘选股
        title3 = BCLabel('尾盘选股（14:00起扫描·14:52定稿·14:53推送·尾盘买/明早预期卖）', BC.TEXT_PRIMARY, 14, True)
        left_layout.addWidget(title3)

        # 选股口径说明
        strategy_desc = BCLabel(
            '选股口径：20日内涨停记忆·回调后启动(站上5日线/创10日新高)·今日0.3-7%不追底·板块资金流入或新闻发酵·同板块联动·AI实时对比·排除一字板/ST/连板>2/5日>22%',
            BC.TEXT_MUTED, 10
        )
        strategy_desc.setWordWrap(True)
        left_layout.addWidget(strategy_desc)

        # 尾盘选股卡片
        self.tail_card1 = TailStockCard()
        self.tail_card2 = TailStockCard()
        left_layout.addWidget(self.tail_card1)
        left_layout.addWidget(self.tail_card2)

        left_layout.addStretch()

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {BC.BG_TAB}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {BC.BORDER_LIGHT}; border-radius: 4px; }}
        """)
        main_layout.addWidget(scroll, 3)

        # 右侧25%
        right = QWidget()
        right.setMinimumWidth(280)
        right.setMaximumWidth(380)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.market_card = MarketOverviewCard()
        self.sold_card = SoldTrackingCard()
        self.candidate_card = CandidatePoolCard()

        right_layout.addWidget(self.market_card)
        right_layout.addWidget(self.sold_card)
        right_layout.addWidget(self.candidate_card)
        right_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {BC.BG_TAB}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {BC.BORDER_LIGHT}; border-radius: 4px; }}
        """)
        main_layout.addWidget(right_scroll, 1)

    def _load_data(self):
        """加载真实数据"""
        try:
            # 首板候选
            candidates = get_data_adapter().get_first_board_candidates(limit=2)
            if candidates and len(candidates) >= 1:
                self.fb_card1.data = candidates[0]
                self.fb_card1._build_ui() if hasattr(self.fb_card1, '_build_ui') else None
            if candidates and len(candidates) >= 2:
                self.fb_card2.data = candidates[1]

            # 热门板块
            sectors = get_data_adapter().get_hot_sectors(limit=3)
            if sectors and len(sectors) >= 1:
                self.sector_card1.data = sectors[0]
            if sectors and len(sectors) >= 2:
                self.sector_card2.data = sectors[1]
            if sectors and len(sectors) >= 3:
                self.sector_card3.data = sectors[2]

            # 尾盘选股
            tail = get_data_adapter().get_tail_stock_picks()
            tail_candidates = tail.get('candidates', [])
            if tail_candidates and len(tail_candidates) >= 1:
                self.tail_card1.data = tail_candidates[0]
            if tail_candidates and len(tail_candidates) >= 2:
                self.tail_card2.data = tail_candidates[1]
        except Exception as e:
            print(f"[中控台] 首页数据加载失败: {e}", flush=True)


# ============================================================
# 主窗口
# ============================================================
class BattleConsoleWindow(QWidget):
    """量化交易作战中控台主窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('量化交易驾驶舱 V6.5 - 作战中控台')
        self.setMinimumSize(1280, 800)
        self.resize(1600, 900)
        self._build_ui()
        self._apply_dark_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部状态栏
        self.top_bar = TopStatusBar()
        layout.addWidget(self.top_bar)

        # 横向Tab导航
        self.tab_nav = TabNav()
        self.tab_nav.tab_changed.connect(self._on_tab_changed)
        layout.addWidget(self.tab_nav)

        # 内容区域（QStackedWidget）
        self.stacked = QTabWidget()
        self.stacked.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {BC.BG_MAIN}; }}
            QTabBar {{ display: none; }}
        """)

        # 页面0：盘前新闻（复用现有新闻组件）
        self.news_page = self._create_news_page()
        self.stacked.addTab(self.news_page, '盘前新闻')

        # 页面1：盘前竞价
        self.auction_page = QWidget()
        self.auction_page.setStyleSheet(f'background: {BC.BG_MAIN};')
        self._add_placeholder(self.auction_page, '盘前竞价', '9:15-9:25集合竞价数据')
        self.stacked.addTab(self.auction_page, '盘前竞价')

        # 页面2：收盘首板（首页，作战中控台）
        self.first_board_page = FirstBoardPage()
        self.stacked.addTab(self.first_board_page, '收盘首板')

        # 页面3：自选评分（复用现有自选组件）
        self.watchlist_page = self._create_watchlist_page()
        self.stacked.addTab(self.watchlist_page, '自选评分')

        # 页面4：持仓监控（复用现有持仓组件）
        self.portfolio_page = self._create_portfolio_page()
        self.stacked.addTab(self.portfolio_page, '持仓监控')

        # 页面5：尾盘选股
        self.tail_page = QWidget()
        self.tail_page.setStyleSheet(f'background: {BC.BG_MAIN};')
        self._add_placeholder(self.tail_page, '尾盘选股', '14:00扫描·14:52定稿·14:53推送')
        self.stacked.addTab(self.tail_page, '尾盘选股')

        # 页面6：早盘竞价
        self.early_auction_page = QWidget()
        self.early_auction_page.setStyleSheet(f'background: {BC.BG_MAIN};')
        self._add_placeholder(self.early_auction_page, '早盘竞价', '9:15-9:30早盘竞价分析')
        self.stacked.addTab(self.early_auction_page, '早盘竞价')

        # 页面7：个股分析（复用现有个股详情）
        self.stock_detail_page = QWidget()
        self.stock_detail_page.setStyleSheet(f'background: {BC.BG_MAIN};')
        self._add_placeholder(self.stock_detail_page, '个股分析', '点击股票查看详细分析')
        self.stacked.addTab(self.stock_detail_page, '个股分析')

        # 页面8：运行日志
        self.log_page = QWidget()
        self.log_page.setStyleSheet(f'background: {BC.BG_MAIN};')
        self._add_placeholder(self.log_page, '运行日志', '程序运行日志和策略执行记录')
        self.stacked.addTab(self.log_page, '运行日志')

        layout.addWidget(self.stacked, 1)

        # 底部状态栏
        self._build_bottom_bar(layout)

        # 默认显示收盘首板页面
        self.stacked.setCurrentIndex(2)

    def _create_news_page(self):
        """创建新闻页面（复用现有新闻组件）"""
        page = QWidget()
        page.setStyleSheet(f'background: {BC.BG_MAIN};')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        try:
            from ui.news_panel import NewsPanelWidget
            news_widget = NewsPanelWidget()
            layout.addWidget(news_widget)
        except Exception as e:
            self._add_placeholder(page, '盘前新闻', f'新闻组件加载失败: {e}')
        return page

    def _create_watchlist_page(self):
        """创建自选页面（复用现有自选组件）"""
        page = QWidget()
        page.setStyleSheet(f'background: {BC.BG_MAIN};')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        try:
            from ui.watchlist_panel import WatchlistWidget
            watchlist_widget = WatchlistWidget()
            layout.addWidget(watchlist_widget)
        except Exception as e:
            self._add_placeholder(page, '自选评分', f'自选组件加载失败: {e}')
        return page

    def _create_portfolio_page(self):
        """创建持仓页面（复用现有持仓组件）"""
        page = QWidget()
        page.setStyleSheet(f'background: {BC.BG_MAIN};')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        try:
            from ui.portfolio_widget import PortfolioWidget
            portfolio_widget = PortfolioWidget()
            layout.addWidget(portfolio_widget)
        except Exception as e:
            self._add_placeholder(page, '持仓监控', f'持仓组件加载失败: {e}')
        return page

    def _add_placeholder(self, widget, title, desc):
        """添加占位页面"""
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = BCLabel(title, BC.TEXT_PRIMARY, 24, True)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d = BCLabel(desc, BC.TEXT_MUTED, 14)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t)
        layout.addSpacing(12)
        layout.addWidget(d)

    def _build_bottom_bar(self, layout):
        """构建底部状态栏"""
        bottom = QFrame()
        bottom.setFixedHeight(32)
        bottom.setStyleSheet(f"""
            QFrame {{
                background: {BC.BG_CARD};
                border-top: 1px solid {BC.BORDER};
            }}
        """)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(16)

        bl.addWidget(BCLabel('数据源：通达信', BC.TEXT_MUTED, 11))
        self.bottom_time = BCLabel(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), BC.TEXT_SECONDARY, 11)
        bl.addWidget(self.bottom_time)
        bl.addWidget(BCLabel('所有数据仅供参考，不构成投资建议', BC.TEXT_MUTED, 10))
        bl.addStretch()

        # 指数行情
        self.bottom_sh = BCLabel('沪深 --', BC.TEXT_SECONDARY, 11)
        self.bottom_sz = BCLabel('深成 --', BC.TEXT_SECONDARY, 11)
        self.bottom_cyb = BCLabel('创业 --', BC.TEXT_SECONDARY, 11)
        bl.addWidget(self.bottom_sh)
        bl.addWidget(self.bottom_sz)
        bl.addWidget(self.bottom_cyb)

        bl.addSpacing(16)
        self.network_status = BCLabel('● 网络正常', BC.GREEN, 11)
        bl.addWidget(self.network_status)

        layout.addWidget(bottom)

        # 底部时间更新定时器
        self.bottom_timer = QTimer(self)
        self.bottom_timer.timeout.connect(self._update_bottom)
        self.bottom_timer.start(1000)

    def _update_bottom(self):
        self.bottom_time.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        try:
            data = get_data_adapter().get_market_overview()
            if data['sh_index'] > 0:
                sh_pct = data['sh_pct']
                sh_color = BC.RED if sh_pct >= 0 else BC.GREEN
                self.bottom_sh.setText(f'沪深 {data["sh_index"]:.2f} {sh_pct:+.2f}%')
                self.bottom_sh.setStyleSheet(f'color: {sh_color}; font-size: 11px;')
            if data['sz_index'] > 0:
                sz_pct = data['sz_pct']
                sz_color = BC.RED if sz_pct >= 0 else BC.GREEN
                self.bottom_sz.setText(f'深成 {data["sz_index"]:.2f} {sz_pct:+.2f}%')
                self.bottom_sz.setStyleSheet(f'color: {sz_color}; font-size: 11px;')
            if data['cyb_index'] > 0:
                cyb_pct = data['cyb_pct']
                cyb_color = BC.RED if cyb_pct >= 0 else BC.GREEN
                self.bottom_cyb.setText(f'创业 {data["cyb_index"]:.2f} {cyb_pct:+.2f}%')
                self.bottom_cyb.setStyleSheet(f'color: {cyb_color}; font-size: 11px;')
        except Exception:
            pass

    def _on_tab_changed(self, idx):
        """Tab切换"""
        self.stacked.setCurrentIndex(idx)

    def _apply_dark_theme(self):
        """应用深色主题"""
        self.setStyleSheet(f"""
            QWidget {{
                background: {BC.BG_MAIN};
                color: {BC.TEXT_PRIMARY};
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
            QScrollArea {{ border: none; }}
            QScrollBar:vertical {{
                background: {BC.BG_TAB};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {BC.BORDER_LIGHT};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {BC.ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: {BC.BG_TAB};
                height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: {BC.BORDER_LIGHT};
                border-radius: 4px;
            }}
        """)
