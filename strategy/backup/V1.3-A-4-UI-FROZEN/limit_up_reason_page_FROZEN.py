# -*- coding: utf-8 -*-
"""
V1.3-A-4-DEV Step5：涨停原因分析页面
独立UI页面，只负责展示，不修改FROZEN算法层。

数据来源：
- 涨停股票列表：market.limit_up_center.get_today_limit_up_stocks()
- 原因分析：ui.limit_up_reason_card.analyze_and_format()
- 卡片渲染：ui.widgets.reason_card_widget.ReasonCardWidget
"""
import os
import sys
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QSizePolicy, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ui.limit_up_reason_card import analyze_and_format
from ui.widgets.reason_card_widget import ReasonCardWidget
from data.cache.reason_card_cache import get_reason_card_cache


# ========== 颜色配置（与主窗口风格一致） ==========
COLORS = {
    'bg_primary': '#0d1117',
    'bg_secondary': '#161b22',
    'bg_tertiary': '#21262d',
    'border': '#30363d',
    'text_primary': '#f0f6fc',
    'text_secondary': '#8b949e',
    'accent': '#58a6ff',
    'red': '#f85149',
    'green': '#3fb950',
    'orange': '#d29922',
}


class LimitUpReasonPage(QWidget):
    """
    涨停原因分析页面

    布局：
    - 顶部：工具栏（刷新按钮 + 统计信息）
    - 左侧：涨停股票列表
    - 右侧：原因分析卡片（可滚动）
    """

    # 跨线程信号（替代QTimer.singleShot，更可靠）
    stocks_loaded_signal = pyqtSignal(list)
    stocks_load_error_signal = pyqtSignal(str)

    # 加载超时时间（秒）
    LOAD_TIMEOUT = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._limit_up_stocks = []  # 涨停股票列表缓存
        self._current_card = None   # 当前卡片组件
        self._is_loading = False
        self._load_timer = None     # 加载超时定时器

        self._init_ui()
        # 连接跨线程信号
        self.stocks_loaded_signal.connect(self._on_stocks_loaded)
        self.stocks_load_error_signal.connect(self._on_stocks_load_error)

        # 延迟加载涨停列表（避免阻塞UI初始化）
        QTimer.singleShot(300, self._load_limit_up_stocks)

    def _init_ui(self):
        """初始化UI"""
        self.setStyleSheet(f"""
            QWidget {{ background: {COLORS['bg_primary']}; color: {COLORS['text_primary']}; }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========== 顶部工具栏 ==========
        toolbar = QFrame()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 0, 16, 0)
        toolbar_layout.setSpacing(12)

        # 标题
        title = QLabel('🔥 涨停原因分析')
        title.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {COLORS["text_primary"]};')
        toolbar_layout.addWidget(title)

        toolbar_layout.addSpacing(20)

        # 统计信息
        self.stats_label = QLabel('加载中...')
        self.stats_label.setStyleSheet(f'color: {COLORS["text_secondary"]}; font-size: 13px;')
        toolbar_layout.addWidget(self.stats_label)

        toolbar_layout.addStretch()

        # 刷新按钮
        self.refresh_btn = QPushButton('🔄 刷新')
        self.refresh_btn.setFixedSize(80, 32)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                color: {COLORS['text_secondary']};
            }}
        """)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        toolbar_layout.addWidget(self.refresh_btn)

        # 清空缓存按钮
        self.clear_cache_btn = QPushButton('🗑 清缓存')
        self.clear_cache_btn.setFixedSize(80, 32)
        self.clear_cache_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {COLORS['red']};
                color: white;
                border-color: {COLORS['red']};
            }}
        """)
        self.clear_cache_btn.clicked.connect(self._on_clear_cache_clicked)
        toolbar_layout.addWidget(self.clear_cache_btn)

        main_layout.addWidget(toolbar)

        # ========== 主体区域（左右分栏） ==========
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {COLORS['border']};
                width: 1px;
            }}
        """)

        # --- 左侧：股票列表 ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 列表标题
        list_header = QLabel('  今日涨停')
        list_header.setFixedHeight(36)
        list_header.setStyleSheet(f"""
            background: {COLORS['bg_secondary']};
            color: {COLORS['text_secondary']};
            font-size: 12px;
            font-weight: bold;
            border-bottom: 1px solid {COLORS['border']};
            padding: 8px 12px;
        """)
        left_layout.addWidget(list_header)

        # 股票列表
        self.stock_list = QListWidget()
        self.stock_list.setStyleSheet(f"""
            QListWidget {{
                background: {COLORS['bg_primary']};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-bottom: 1px solid {COLORS['border']};
                color: {COLORS['text_primary']};
            }}
            QListWidget::item:hover {{
                background: {COLORS['bg_secondary']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['bg_tertiary']};
                border-left: 3px solid {COLORS['accent']};
            }}
        """)
        self.stock_list.itemClicked.connect(self._on_stock_clicked)
        left_layout.addWidget(self.stock_list)

        splitter.addWidget(left_panel)

        # --- 右侧：卡片区域 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 卡片标题
        card_header = QLabel('  原因分析')
        card_header.setFixedHeight(36)
        card_header.setStyleSheet(f"""
            background: {COLORS['bg_secondary']};
            color: {COLORS['text_secondary']};
            font-size: 12px;
            font-weight: bold;
            border-bottom: 1px solid {COLORS['border']};
            padding: 8px 12px;
        """)
        right_layout.addWidget(card_header)

        # 卡片滚动区域
        self.card_scroll = QScrollArea()
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {COLORS['bg_primary']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {COLORS['bg_secondary']};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border']};
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLORS['text_secondary']};
            }}
        """)

        # 占位提示
        self._placeholder = QLabel('👈 请从左侧选择一只涨停股票\n\n查看详细的涨停原因分析')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 15px;
            padding: 60px;
        """)
        self.card_scroll.setWidget(self._placeholder)

        right_layout.addWidget(self.card_scroll)

        splitter.addWidget(right_panel)

        # 设置分栏比例（左侧35%，右侧65%）
        splitter.setSizes([350, 650])

        main_layout.addWidget(splitter)

    # ========== 数据加载 ==========

    def _load_limit_up_stocks(self):
        """加载今日涨停股票列表（后台线程 + 信号机制 + 超时保护）"""
        if self._is_loading:
            print("[涨停原因页] 已有加载任务在进行，跳过")
            return
        self._is_loading = True
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText('加载中...')
        self.stats_label.setText('正在获取涨停数据...')

        # 启动超时保护定时器
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self._on_load_timeout)
        self._load_timer.start(self.LOAD_TIMEOUT * 1000)

        def _do():
            try:
                from market.limit_up_center import get_today_limit_up_stocks
                stocks = get_today_limit_up_stocks()
                # 使用信号切回主线程（比QTimer.singleShot更可靠）
                self.stocks_loaded_signal.emit(stocks)
            except Exception as e:
                print(f"[涨停原因页] 获取涨停列表失败: {e}")
                import traceback
                traceback.print_exc()
                self.stocks_load_error_signal.emit(str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _on_load_timeout(self):
        """加载超时处理"""
        print(f"[涨停原因页] 加载超时（{self.LOAD_TIMEOUT}秒），恢复按钮状态")
        self._is_loading = False
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText('🔄 刷新')
        self.stats_label.setText('加载超时，请点击刷新重试')
        if self._load_timer:
            self._load_timer.stop()
            self._load_timer = None

    def _on_stocks_loaded(self, stocks):
        """涨停列表加载完成"""
        # 停止超时定时器
        if self._load_timer:
            self._load_timer.stop()
            self._load_timer = None

        self._is_loading = False
        self._limit_up_stocks = stocks
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText('🔄 刷新')

        # 更新统计
        total = len(stocks)
        # 统计连板数
        multi_board = sum(1 for s in stocks if s.get('lbc', 0) > 1)
        # 缓存统计
        cache = get_reason_card_cache()
        cache_stats = cache.get_stats()
        cache_count = cache_stats.get('count', 0)

        if total == 0:
            self.stats_label.setText('今日暂无涨停数据（非交易日或休市）')
            # 显示空状态提示
            self.stock_list.clear()
            empty_item = QListWidgetItem('📭 今日暂无涨停股票')
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.stock_list.addItem(empty_item)
            return  # 空数据直接返回，不继续填充列表
        else:
            self.stats_label.setText(f'共 {total} 只涨停 | 连板 {multi_board} 只 | 已缓存 {cache_count} 只')

        # 填充列表
        self.stock_list.clear()
        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            lbc = stock.get('lbc', 0)
            pct = stock.get('pct_chg', 0)
            industry = stock.get('industry', '')

            # 连板标记
            board_tag = f' {lbc}连板' if lbc > 1 else ''
            # 显示文本
            display_text = f"{name} ({code}){board_tag}\n  {industry} | +{pct}%"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, stock)

            # 连板股用橙色标记
            if lbc > 1:
                item.setForeground(QColor(COLORS['orange']))

            self.stock_list.addItem(item)

        # 默认选中第一只
        if stocks:
            self.stock_list.setCurrentRow(0)
            self._on_stock_clicked(self.stock_list.currentItem())

    def _on_stocks_load_error(self, error_msg):
        """涨停列表加载失败"""
        # 停止超时定时器
        if self._load_timer:
            self._load_timer.stop()
            self._load_timer = None

        self._is_loading = False
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText('🔄 刷新')
        self.stats_label.setText(f'加载失败，请点击刷新重试')

        self.stock_list.clear()
        item = QListWidgetItem(f'获取涨停数据失败\n{error_msg}\n\n点击"刷新"重试')
        item.setForeground(QColor(COLORS['red']))
        self.stock_list.addItem(item)

    # ========== 交互事件 ==========

    def _on_refresh_clicked(self):
        """刷新按钮点击"""
        self._load_limit_up_stocks()

    def _on_clear_cache_clicked(self):
        """清空缓存按钮点击"""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, '确认清空',
            '确定要清空今日原因分析缓存吗？\n清空后点击股票将重新分析。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            cache = get_reason_card_cache()
            cache.clear()
            self._update_cache_stats()
            self.stats_label.setText('缓存已清空')

    def _update_cache_stats(self):
        """更新缓存统计显示"""
        cache = get_reason_card_cache()
        stats = cache.get_stats()
        return stats

    def _on_stock_clicked(self, item):
        """股票列表项点击（带缓存）"""
        if not item:
            return

        stock = item.data(Qt.ItemDataRole.UserRole)
        if not stock:
            return

        code = stock.get('code', '')
        name = stock.get('name', '')

        # 先查缓存（命中则秒开，不显示加载状态）
        cache = get_reason_card_cache()
        cached_data = cache.get(code)
        if cached_data:
            cached_data['code'] = code
            cached_data['name'] = name
            self._show_card(cached_data)
            self.statusBar().showMessage(f'{name} 缓存命中，秒开') if hasattr(self, 'statusBar') else None
            return

        # 未命中，显示加载状态
        self._show_loading(name)

        # 后台线程分析
        def _do():
            try:
                # 构造limit_up_data
                limit_up_data = {
                    'code': code,
                    'name': name,
                    'is_limit_up': True,
                    'pct_chg': stock.get('pct_chg', 10.0),
                    'consecutive_days': stock.get('lbc', 1),
                    'turnover_rate': stock.get('turnover', 0),
                    'industry': stock.get('industry', ''),
                }

                card_data = analyze_and_format(code, name, limit_up_data)
                card_data['code'] = code
                card_data['name'] = name

                # 保存到缓存
                cache.set(code, name, card_data)

                # UI操作必须在主线程
                QTimer.singleShot(0, lambda: self._show_card(card_data))
            except Exception as e:
                print(f"[涨停原因页] 分析 {name} 失败: {e}")
                import traceback
                traceback.print_exc()
                QTimer.singleShot(0, lambda: self._show_analysis_error(name, str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _show_loading(self, name):
        """显示加载中状态"""
        loading = QLabel(f'⏳ 正在分析 {name} 的涨停原因...\n\n请稍候')
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 15px;
            padding: 60px;
        """)
        self.card_scroll.setWidget(loading)

    def _show_card(self, card_data):
        """显示原因分析卡片"""
        self._current_card = ReasonCardWidget(card_data)
        self.card_scroll.setWidget(self._current_card)
        # 更新缓存统计
        cache = get_reason_card_cache()
        cache_stats = cache.get_stats()
        cache_count = cache_stats.get('count', 0)
        total = len(self._limit_up_stocks) if self._limit_up_stocks else 0
        multi_board = sum(1 for s in self._limit_up_stocks if s.get('lbc', 0) > 1) if self._limit_up_stocks else 0
        if total > 0:
            self.stats_label.setText(f'共 {total} 只涨停 | 连板 {multi_board} 只 | 已缓存 {cache_count} 只')

    def _show_analysis_error(self, name, error_msg):
        """显示分析失败"""
        error = QLabel(f'❌ {name} 分析失败\n\n{error_msg}\n\n请重试或选择其他股票')
        error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error.setStyleSheet(f"""
            color: {COLORS['red']};
            font-size: 14px;
            padding: 60px;
        """)
        self.card_scroll.setWidget(error)

    # ========== 外部接口 ==========

    def refresh_data(self):
        """外部调用：刷新数据"""
        self._load_limit_up_stocks()


# ========== 测试代码 ==========
if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    window = LimitUpReasonPage()
    window.setWindowTitle('涨停原因分析 - 测试')
    window.resize(1200, 800)
    window.show()

    print('=' * 60)
    print('涨停原因分析页面测试已启动')
    print('关闭窗口后退出')
    print('=' * 60)

    sys.exit(app.exec_())
