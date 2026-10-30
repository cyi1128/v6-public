"""
7×24快讯UI组件
类似同花顺快讯界面，实时滚动显示财经新闻
股票代码/名称自动高亮
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QDesktopServices
from PyQt6.QtCore import QUrl
import re
import threading

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    ACCENT_GOLD,
)


# 全市场股票名称字典（运行时从通达信加载，缓存到本地）
_all_stock_names = None
_stock_names_loading = False


def _load_stock_names_async():
    """异步加载全市场股票名称"""
    global _all_stock_names, _stock_names_loading
    if _stock_names_loading:
        return
    _stock_names_loading = True

    def _load():
        global _all_stock_names
        try:
            from utils.stock_name_manager import get_stock_names_with_fallback
            _all_stock_names = get_stock_names_with_fallback()
        except Exception:
            _all_stock_names = {}

    thread = threading.Thread(target=_load, daemon=True)
    thread.start()


def get_stock_names():
    """获取股票名称字典（优先全市场，兜底内置）"""
    global _all_stock_names
    if _all_stock_names is not None:
        return _all_stock_names

    # 尝试从缓存加载（快速，不阻塞）
    try:
        from utils.stock_name_manager import load_cached_stock_names, BUILTIN_STOCKS
        cached = load_cached_stock_names()
        if cached:
            _all_stock_names = cached
            return cached
        # 没有缓存，先返回内置的，同时异步加载全市场
        _all_stock_names = BUILTIN_STOCKS
        _load_stock_names_async()
        return BUILTIN_STOCKS
    except Exception:
        return {}


def highlight_stocks(text):
    """高亮文本中的股票代码和股票名称（红色标记）"""
    if not text:
        return text

    result = text

    # 1. 高亮6位数字股票代码（中文环境下不用\b，用前后非数字判断）
    def replace_code(match):
        code = match.group(1)
        if code.startswith(('000', '001', '002', '003', '300', '301', '600', '601', '603', '605', '688')):
            return f'\x00{code}\x01'
        return code

    result = re.sub(r'(?<!\d)(\d{6})(?!\d)', replace_code, result)

    # 2. 高亮股票名称（按名称长度降序，避免短名称先匹配）
    stock_names = get_stock_names()
    if stock_names:
        sorted_names = sorted(stock_names.keys(), key=len, reverse=True)
        for name in sorted_names:
            if name and len(name) >= 2 and name in result:
                # 用正则替换，确保不匹配已被临时标记包围的内容
                # (?<!\x00) 确保前面不是开始标记，(?!\x01) 确保后面不是结束标记
                pattern = re.escape(name)
                result = re.sub(
                    rf'(?<!\x00){pattern}(?!\x01)',
                    lambda m: f'\x00{m.group(0)}\x01',
                    result
                )

    # 3. 把临时标记替换成真正的span标签
    result = result.replace('\x00', '<span style="color: #ff1744; font-weight: bold;">')
    result = result.replace('\x01', '</span>')

    return result


class NewsItemWidget(QFrame):
    """单条新闻条目"""

    def __init__(self, news_data: dict, parent=None):
        super().__init__(parent)
        self.news_data = news_data
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border: none;
                border-bottom: 1px solid {BORDER};
            }}
            QFrame:hover {{
                background-color: {BG_CARD};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # 顶部：时间 + 来源 + 重要性标记
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # 时间
        time_label = QLabel(self.news_data.get('time', ''))
        time_label.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold;")
        time_label.setFixedWidth(60)
        top_layout.addWidget(time_label)

        # 重要性标记
        importance = self.news_data.get('importance', 0)
        if importance >= 2:
            imp_label = QLabel("🔴 重大")
            imp_label.setStyleSheet(f"color: {ACCENT_RED}; font-size: 10px; font-weight: bold;")
            top_layout.addWidget(imp_label)
        elif importance >= 1:
            imp_label = QLabel("🟠 重要")
            imp_label.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 10px; font-weight: bold;")
            top_layout.addWidget(imp_label)

        # 来源
        source = self.news_data.get('source', '')
        if source:
            source_label = QLabel(source)
            source_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
            top_layout.addWidget(source_label)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # 标题
        title = self.news_data.get('title', '')
        if title:
            title_label = QLabel()
            title_label.setTextFormat(Qt.TextFormat.RichText)
            title_label.setText(highlight_stocks(title))
            title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
            title_label.setWordWrap(True)
            layout.addWidget(title_label)

        # 内容
        content = self.news_data.get('content', '')
        if content:
            content_label = QLabel()
            content_label.setTextFormat(Qt.TextFormat.RichText)
            content_label.setText(highlight_stocks(content))
            content_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            content_label.setWordWrap(True)
            layout.addWidget(content_label)

        # 标签
        tags = self.news_data.get('tags', [])
        if tags:
            tag_layout = QHBoxLayout()
            tag_layout.setSpacing(4)
            for tag in tags[:3]:
                if tag:
                    tag_label = QLabel(f"#{tag}")
                    tag_label.setStyleSheet(f"""
                        color: {ACCENT_BLUE};
                        font-size: 10px;
                        background-color: rgba(90,169,255,0.15);
                        padding: 2px 6px;
                        border-radius: 3px;
                    """)
                    tag_layout.addWidget(tag_label)
            tag_layout.addStretch()
            layout.addLayout(tag_layout)

    def mousePressEvent(self, event):
        """点击打开新闻链接"""
        url = self.news_data.get('url', '')
        if url:
            QDesktopServices.openUrl(QUrl(url))


class NewsTickerWidget(QWidget):
    """
    7×24快讯滚动组件
    类似同花顺顶部滚动条
    """
    news_clicked = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.news_list = []
        self.current_index = 0
        self._init_ui()

        # 自动滚动定时器
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._scroll_next)
        self._scroll_timer.start(8000)  # 8秒切换一条

    def _init_ui(self):
        self.setFixedHeight(32)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        # 标题
        title_label = QLabel("📰 7×24快讯")
        title_label.setStyleSheet(f"color: {ACCENT_RED}; font-size: 12px; font-weight: bold;")
        title_label.setFixedWidth(80)
        layout.addWidget(title_label)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color: {BORDER};")
        line.setFixedWidth(1)
        layout.addWidget(line)

        # 新闻内容
        self.content_label = QLabel("暂无快讯，正在加载...")
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        self.content_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.content_label, 1)

        # 时间
        self.time_label = QLabel("")
        self.time_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.time_label.setFixedWidth(60)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.time_label)

    def update_news(self, news_list: list):
        """更新新闻列表"""
        self.news_list = news_list
        self.current_index = 0
        self._display_current()

    def _scroll_next(self):
        """滚动到下一条"""
        if not self.news_list:
            return
        self.current_index = (self.current_index + 1) % len(self.news_list)
        self._display_current()

    def _display_current(self):
        """显示当前新闻"""
        if not self.news_list:
            self.content_label.setText("暂无快讯")
            self.time_label.setText("")
            return

        news = self.news_list[self.current_index]
        title = news.get('title', '') or news.get('content', '')[:50]
        time_str = news.get('time', '')

        # 截断过长的标题
        if len(title) > 80:
            title = title[:77] + "..."

        self.content_label.setText(highlight_stocks(title))
        self.time_label.setText(time_str)

    def mousePressEvent(self, event):
        """点击打开完整快讯"""
        if self.news_list:
            self.news_clicked.emit(self.news_list[self.current_index])


class NewsPanelWidget(QWidget):
    """
    7×24快讯面板（完整列表）
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.news_list = []
        self._init_ui()
        # 异步加载全市场股票名称（用于新闻高亮）
        _load_stock_names_async()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题栏
        header = QFrame()
        header.setFixedHeight(40)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border-bottom: 1px solid {BORDER};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("📰 7×24小时财经快讯")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title)

        # V1.3.17：新闻总数标签
        self.count_label = QLabel("今日共 0 条快讯")
        self.count_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; margin-left: 8px;")
        header_layout.addWidget(self.count_label)

        header_layout.addStretch()

        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setFixedSize(60, 26)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_INTERACTIVE};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
            }}
        """)
        header_layout.addWidget(self.refresh_btn)

        layout.addWidget(header)

        # 新闻列表滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG_WINDOW};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {BG_WINDOW};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {BORDER};
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {BORDER_STRONG};
            }}
        """)

        self.news_container = QWidget()
        self.news_layout = QVBoxLayout(self.news_container)
        self.news_layout.setContentsMargins(0, 0, 0, 0)
        self.news_layout.setSpacing(0)
        self.news_layout.addStretch()

        scroll.setWidget(self.news_container)
        layout.addWidget(scroll, 1)

    def update_news(self, news_list: list):
        """更新新闻列表"""
        try:
            self.news_list = news_list
            print(f"新闻面板收到 {len(news_list)} 条新闻")

            # V1.3.17：更新新闻总数标签
            if hasattr(self, 'count_label'):
                self.count_label.setText(f"今日共 {len(news_list)} 条快讯")

            # 清空旧新闻
            while self.news_layout.count() > 1:
                item = self.news_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            if not news_list:
                empty_label = QLabel("暂无新闻")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; padding: 40px;")
                self.news_layout.insertWidget(0, empty_label)
                return

            # 添加新新闻
            for news in news_list:
                item_widget = NewsItemWidget(news)
                self.news_layout.insertWidget(self.news_layout.count() - 1, item_widget)
        except Exception as e:
            print(f"更新新闻列表失败: {e}")
            import traceback
            traceback.print_exc()

    def set_refresh_callback(self, callback):
        """设置刷新回调"""
        self.refresh_btn.clicked.connect(callback)
