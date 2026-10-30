# -*- coding: utf-8 -*-
"""
大盘板块分析UI - 上下布局
上：大盘指数（上证+深证）
下：7×24财经新闻
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QMenu,
    QSplitter
)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QDesktopServices

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    ACCENT_GOLD, UP, DOWN, STATUS_INFO, STATUS_WARNING, STATUS_ERROR,
)
from core.watchlist import get_watchlist_manager
from utils.tdx_stock_list import get_stocks_with_quotes_tdx
from pytdx.hq import TdxHq_API
from market.news_center import NewsCenter
from ui.news_panel import NewsPanelWidget


class MarketDashboardWidget(QWidget):
    """大盘板块分析面板 - 上下布局"""

    # 信号（用于跨线程更新UI）
    index_data_ready = pyqtSignal(list)
    news_data_ready = pyqtSignal(list)
    market_stats_ready = pyqtSignal(int, int, int, int, int, int)  # sh_up, sh_flat, sh_down, sz_up, sz_flat, sz_down

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_signals()
        self._init_ui()
        self._setup_timer()
        self._news_center = None
        QTimer.singleShot(500, self._refresh_data)

    def _init_signals(self):
        """初始化信号槽连接"""
        self.index_data_ready.connect(self._update_index_ui)
        self.news_data_ready.connect(self._update_news_ui)
        self.market_stats_ready.connect(self._update_market_stats_ui)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel('📈 大盘 & 7×24快讯')
        title.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY};')
        header.addWidget(title)
        header.addStretch()

        self.refresh_btn = QPushButton('🔄 刷新')
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER};
                border-radius: 6px; padding: 4px 12px; color: {TEXT_PRIMARY};
            }}
            QPushButton:hover {{ background: {BG_CARD}; border-color: {ACCENT_BLUE}; }}
        """)
        self.refresh_btn.clicked.connect(self._refresh_data)
        header.addWidget(self.refresh_btn)

        main_layout.addLayout(header)

        # 上下分割布局
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {BORDER};
            }}
            QSplitter::handle:vertical {{
                height: 4px;
            }}
        """)

        # 上方：大盘指数
        self.index_frame = self._create_index_panel()
        splitter.addWidget(self.index_frame)

        # 下方：7×24财经新闻
        self.news_frame = self._create_news_panel()
        splitter.addWidget(self.news_frame)

        # 设置拉伸比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, 1)

    def _create_index_panel(self):
        """创建指数数据面板（左上）"""
        frame = QFrame()
        frame.setStyleSheet('background: #161b22; border-radius: 6px;')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel('📊 大盘指数')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc;')
        layout.addWidget(title)

        # 上证指数
        self.sh_index = self._create_index_card('上证指数')
        layout.addWidget(self.sh_index)

        # 深证成指
        self.sz_index = self._create_index_card('深证成指')
        layout.addWidget(self.sz_index)

        return frame

    def _create_index_card(self, name):
        """创建单个指数卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {BG_CONTAINER}; border-radius: 6px;
                border: 1px solid {BORDER_SOFT};
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 名称
        name_label = QLabel(name)
        name_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        layout.addWidget(name_label)

        # 价格和涨跌幅
        price_layout = QHBoxLayout()
        price_label = QLabel('--')
        price_label.setStyleSheet(f'font-size: 20px; font-weight: bold; color: {TEXT_PRIMARY};')
        price_layout.addWidget(price_label)
        price_layout.addStretch()
        pct_label = QLabel('--')
        pct_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY};')
        price_layout.addWidget(pct_label)
        layout.addLayout(price_layout)

        # 最高/最低/成交量/成交额
        detail_layout = QHBoxLayout()
        high_label = QLabel('最高: --')
        high_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        detail_layout.addWidget(high_label)
        detail_layout.addStretch()
        low_label = QLabel('最低: --')
        low_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        detail_layout.addWidget(low_label)
        detail_layout.addStretch()
        vol_label = QLabel('成交量: --')
        vol_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        detail_layout.addWidget(vol_label)
        detail_layout.addStretch()
        amount_label = QLabel('成交额: --')
        amount_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        detail_layout.addWidget(amount_label)
        layout.addLayout(detail_layout)

        # 涨跌家数
        stats_label = QLabel('上涨: -- | 平盘: -- | 下跌: --')
        stats_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px; padding-top: 4px;')
        layout.addWidget(stats_label)

        # 保存引用
        card.price_label = price_label
        card.pct_label = pct_label
        card.high_label = high_label
        card.low_label = low_label
        card.vol_label = vol_label
        card.amount_label = amount_label
        card.stats_label = stats_label

        return card

    def _create_interpretation_panel(self):
        """创建AI新闻解读仪表盘（右上）"""
        frame = QFrame()
        frame.setStyleSheet('background: #161b22; border-radius: 6px;')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel('🧠 AI新闻解读')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc;')
        layout.addWidget(title)

        # 整体情绪分数（大数字）
        score_layout = QHBoxLayout()
        self.overall_score_label = QLabel('0.00')
        self.overall_score_label.setStyleSheet('font-size: 32px; font-weight: bold; color: #ffea00;')
        score_layout.addWidget(self.overall_score_label)
        score_layout.addStretch()

        # 情绪标签
        self.overall_sentiment_label = QLabel('中性')
        self.overall_sentiment_label.setStyleSheet('''
            font-size: 14px; font-weight: bold;
            padding: 4px 12px; border-radius: 4px;
            background: #30363d; color: #f0f6fc;
        ''')
        score_layout.addWidget(self.overall_sentiment_label)
        layout.addLayout(score_layout)

        # 情绪进度条
        self.sentiment_bar = QProgressBar()
        self.sentiment_bar.setRange(-100, 100)
        self.sentiment_bar.setValue(0)
        self.sentiment_bar.setTextVisible(False)
        self.sentiment_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #30363d;
                border-radius: 4px;
                background: #0d1117;
                height: 6px;
            }
            QProgressBar::chunk {
                background: #ffea00;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.sentiment_bar)

        # 利好板块排行
        bullish_title = QLabel('🔥 利好板块 TOP5')
        bullish_title.setStyleSheet('color: #f85149; font-size: 12px; font-weight: bold; padding-top: 4px;')
        layout.addWidget(bullish_title)

        self.bullish_sectors_label = QLabel('暂无数据')
        self.bullish_sectors_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        self.bullish_sectors_label.setWordWrap(True)
        layout.addWidget(self.bullish_sectors_label)

        # 利空板块排行
        bearish_title = QLabel('❄️ 利空板块 TOP5')
        bearish_title.setStyleSheet('color: #3fb950; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(bearish_title)

        self.bearish_sectors_label = QLabel('暂无数据')
        self.bearish_sectors_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        self.bearish_sectors_label.setWordWrap(True)
        layout.addWidget(self.bearish_sectors_label)

        # 利好个股排行
        bullish_stock_title = QLabel('📈 利好个股 TOP5')
        bullish_stock_title.setStyleSheet('color: #f85149; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(bullish_stock_title)

        self.bullish_stocks_label = QLabel('暂无数据')
        self.bullish_stocks_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        self.bullish_stocks_label.setWordWrap(True)
        layout.addWidget(self.bullish_stocks_label)

        # 利空个股排行
        bearish_stock_title = QLabel('📉 利空个股 TOP5')
        bearish_stock_title.setStyleSheet('color: #3fb950; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(bearish_stock_title)

        self.bearish_stocks_label = QLabel('暂无数据')
        self.bearish_stocks_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        self.bearish_stocks_label.setWordWrap(True)
        layout.addWidget(self.bearish_stocks_label)

        layout.addStretch()

        return frame

    def _create_news_panel(self):
        """创建7×24快讯面板（复用NewsPanelWidget）"""
        self.news_panel = NewsPanelWidget()
        # 绑定刷新按钮
        self.news_panel.refresh_btn.clicked.connect(self._refresh_data)
        return self.news_panel

    def _create_detail_panel(self):
        """创建新闻解读详情面板（右下）"""
        frame = QFrame()
        frame.setStyleSheet('background: #161b22; border-radius: 6px;')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel('🔍 新闻解读详情')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc;')
        layout.addWidget(title)

        # 新闻标题
        self.detail_title_label = QLabel('请选择左侧新闻查看解读')
        self.detail_title_label.setStyleSheet('color: #58a6ff; font-size: 12px; font-weight: bold;')
        self.detail_title_label.setWordWrap(True)
        layout.addWidget(self.detail_title_label)

        # 情绪和分数
        sentiment_layout = QHBoxLayout()
        self.detail_sentiment_label = QLabel('情绪: --')
        self.detail_sentiment_label.setStyleSheet('font-size: 12px; font-weight: bold;')
        sentiment_layout.addWidget(self.detail_sentiment_label)
        sentiment_layout.addStretch()
        self.detail_score_label = QLabel('分数: --')
        self.detail_score_label.setStyleSheet('color: #8b949e; font-size: 12px;')
        sentiment_layout.addWidget(self.detail_score_label)
        layout.addLayout(sentiment_layout)

        # 利好板块
        bullish_sec_title = QLabel('✅ 利好板块')
        bullish_sec_title.setStyleSheet('color: #f85149; font-size: 12px; font-weight: bold; padding-top: 8px;')
        layout.addWidget(bullish_sec_title)
        self.bullish_sectors_detail = QLabel('--')
        self.bullish_sectors_detail.setStyleSheet('color: #f85149; font-size: 11px;')
        self.bullish_sectors_detail.setWordWrap(True)
        layout.addWidget(self.bullish_sectors_detail)

        # 利空板块
        bearish_sec_title = QLabel('❌ 利空板块')
        bearish_sec_title.setStyleSheet('color: #3fb950; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(bearish_sec_title)
        self.bearish_sectors_detail = QLabel('--')
        self.bearish_sectors_detail.setStyleSheet('color: #3fb950; font-size: 11px;')
        self.bearish_sectors_detail.setWordWrap(True)
        layout.addWidget(self.bearish_sectors_detail)

        # 利好个股
        bullish_stock_title = QLabel('📈 利好个股')
        bullish_stock_title.setStyleSheet('color: #f85149; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(bullish_stock_title)
        self.bullish_stocks_detail = QLabel('--')
        self.bullish_stocks_detail.setStyleSheet('color: #f85149; font-size: 11px;')
        self.bullish_stocks_detail.setWordWrap(True)
        layout.addWidget(self.bullish_stocks_detail)

        # 利空个股
        bearish_stock_title = QLabel('📉 利空个股')
        bearish_stock_title.setStyleSheet('color: #3fb950; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(bearish_stock_title)
        self.bearish_stocks_detail = QLabel('--')
        self.bearish_stocks_detail.setStyleSheet('color: #3fb950; font-size: 11px;')
        self.bearish_stocks_detail.setWordWrap(True)
        layout.addWidget(self.bearish_stocks_detail)

        # 分析原因
        reason_title = QLabel('💡 逻辑原因')
        reason_title.setStyleSheet('color: #ffea00; font-size: 12px; font-weight: bold; padding-top: 6px;')
        layout.addWidget(reason_title)
        self.reason_detail = QLabel('--')
        self.reason_detail.setStyleSheet('color: #c9d1d9; font-size: 11px;')
        self.reason_detail.setWordWrap(True)
        layout.addWidget(self.reason_detail)

        # 数据来源
        source_title = QLabel('📊 数据来源：同花顺问财AI + 7×24快讯')
        source_title.setStyleSheet('color: #6e7681; font-size: 10px; padding-top: 10px;')
        source_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(source_title)

        layout.addStretch()

        return frame

    def _setup_timer(self):
        """设置定时器"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_data)
        self.timer.start(300000)  # 5分钟刷新一次

    def _refresh_data(self):
        """刷新所有数据"""
        print("大盘板块开始刷新数据...")
        import threading
        def _do():
            try:
                print("后台线程开始执行...")
                # 1. 刷新指数数据
                self._refresh_index_data()
                print("指数数据刷新完成")
                # 2. 刷新新闻和解读
                self._refresh_news_and_interpretation()
                print("新闻和解读刷新完成")
                print("所有数据刷新完成!")
            except Exception as e:
                print(f"刷新大盘数据失败: {e}")
                import traceback
                traceback.print_exc()

        threading.Thread(target=_do, daemon=True).start()

    def _refresh_index_data(self):
        """刷新指数数据"""
        print("开始获取指数数据...")
        try:
            indices = None

            # 方法1：通达信
            try:
                api = TdxHq_API()
                if api.connect('180.153.18.170', 7709):
                    quotes = api.get_security_quotes([(1, '999999'), (0, '399001')])
                    api.disconnect()

                    if quotes and len(quotes) >= 2:
                        indices = []
                        for q in quotes:
                            code = q.get('code', '')
                            price = q.get('price', 0)
                            last_close = q.get('last_close', 0)
                            pct_chg = ((price - last_close) / last_close * 100) if last_close > 0 else 0
                            high = q.get('high', 0)
                            low = q.get('low', 0)
                            volume = q.get('vol', 0)
                            amount = q.get('amount', 0)

                            name = '上证指数' if code == '999999' else '深证成指'
                            indices.append({
                                'name': name,
                                'code': code,
                                'price': price,
                                'pct_chg': pct_chg,
                                'high': high,
                                'low': low,
                                'volume': volume,
                                'amount': amount,
                            })
                        print(f"通达信获取指数成功: {len(indices)} 条")
                else:
                    print("通达信连接失败")
            except Exception as e:
                print(f"通达信获取指数失败: {e}")

            # 方法2：新浪财经（备用）
            if not indices:
                print("尝试新浪财经备用接口...")
                indices = self._fetch_index_from_sina()

            if indices:
                # 发送信号更新UI
                self.index_data_ready.emit(indices)
                print("指数数据信号已发送")

                # 后台统计涨跌家数（比较慢，单独处理）
                self._calc_market_stats()
            else:
                print("所有指数数据源都失败了")
        except Exception as e:
            print(f"获取指数数据失败: {e}")
            import traceback
            traceback.print_exc()

    def _fetch_index_from_sina(self):
        """从新浪财经获取指数数据（备用）"""
        try:
            import requests
            url = "https://hq.sinajs.cn/list=sh000001,sz399001"
            headers = {
                'Referer': 'https://finance.sina.com.cn/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = 'gbk'
            text = resp.text

            indices = []
            lines = text.strip().split('\n')
            for line in lines:
                if '=' not in line:
                    continue
                parts = line.split('=')
                if len(parts) < 2:
                    continue
                code_str = parts[0].split('_')[-1]
                data = parts[1].strip().strip('"').split(',')

                if len(data) >= 5:
                    name = data[0]
                    price = float(data[3]) if data[3] else 0
                    last_close = float(data[2]) if data[2] else 0
                    high = float(data[4]) if data[4] else 0
                    low = float(data[5]) if data[5] else 0
                    volume = float(data[8]) if len(data) > 8 and data[8] else 0
                    amount = float(data[9]) if len(data) > 9 and data[9] else 0
                    pct_chg = ((price - last_close) / last_close * 100) if last_close > 0 else 0

                    indices.append({
                        'name': name,
                        'code': code_str,
                        'price': price,
                        'pct_chg': pct_chg,
                        'high': high,
                        'low': low,
                        'volume': volume,
                        'amount': amount,
                    })
            print(f"新浪财经获取指数成功: {len(indices)} 条")
            return indices
        except Exception as e:
            print(f"新浪财经获取指数失败: {e}")
            return []

    def _calc_market_stats(self):
        """统计分市场的涨跌家数"""
        try:
            print("开始统计涨跌家数...")
            stocks = get_stocks_with_quotes_tdx(max_stocks=5000)
            print(f"获取到 {len(stocks)} 只股票行情")

            # 沪市：60、68开头
            sh_stocks = [s for s in stocks if s.get('code', '').startswith(('60', '68'))]
            sh_up = len([s for s in sh_stocks if s.get('pct_chg', 0) > 0])
            sh_flat = len([s for s in sh_stocks if s.get('pct_chg', 0) == 0])
            sh_down = len([s for s in sh_stocks if s.get('pct_chg', 0) < 0])

            # 深市：00、30开头
            sz_stocks = [s for s in stocks if s.get('code', '').startswith(('00', '30'))]
            sz_up = len([s for s in sz_stocks if s.get('pct_chg', 0) > 0])
            sz_flat = len([s for s in sz_stocks if s.get('pct_chg', 0) == 0])
            sz_down = len([s for s in sz_stocks if s.get('pct_chg', 0) < 0])

            print(f"沪市: 涨{sh_up} 平{sh_flat} 跌{sh_down}, 深市: 涨{sz_up} 平{sz_flat} 跌{sz_down}")

            # 通过信号更新UI
            self.market_stats_ready.emit(sh_up, sh_flat, sh_down, sz_up, sz_flat, sz_down)
            print("涨跌家数信号已发送")
        except Exception as e:
            print(f"统计涨跌家数失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_market_stats_ui(self, sh_up, sh_flat, sh_down, sz_up, sz_flat, sz_down):
        """更新涨跌家数UI"""
        try:
            print("更新涨跌家数UI...")
            # 上证指数涨跌家数
            self.sh_index.stats_label.setText(
                f'上涨: <span style="color: #f85149;">{sh_up}</span> | '
                f'平盘: <span style="color: #8b949e;">{sh_flat}</span> | '
                f'下跌: <span style="color: #3fb950;">{sh_down}</span>'
            )
            self.sh_index.stats_label.setTextFormat(Qt.TextFormat.RichText)

            # 深证成指涨跌家数
            self.sz_index.stats_label.setText(
                f'上涨: <span style="color: #f85149;">{sz_up}</span> | '
                f'平盘: <span style="color: #8b949e;">{sz_flat}</span> | '
                f'下跌: <span style="color: #3fb950;">{sz_down}</span>'
            )
            self.sz_index.stats_label.setTextFormat(Qt.TextFormat.RichText)
            print("涨跌家数UI更新完成")
        except Exception as e:
            print(f"更新涨跌家数UI失败: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_news_and_interpretation(self):
        """刷新7×24快讯新闻"""
        try:
            print("开始获取新闻...")
            # 获取新闻
            if not self._news_center:
                self._news_center = NewsCenter(self)

            news_list = self._news_center.provider.get_all_news()
            print(f"获取到 {len(news_list)} 条新闻")

            if news_list:
                # 发送信号更新UI（V1.3.17：取前500条，覆盖全天新闻）
                self.news_data_ready.emit(news_list[:500])
                print("新闻信号已发送")
        except Exception as e:
            print(f"刷新新闻失败: {e}")
            import traceback
            traceback.print_exc()

    def _on_news_selected(self):
        """新闻选中时更新详情"""
        try:
            current_row = self.news_table.currentRow()
            if current_row < 0 or current_row >= len(self._interpreted_news):
                return

            news = self._interpreted_news[current_row]
            self._update_detail_ui(news)
        except Exception as e:
            print(f"更新新闻详情失败: {e}")

    def _update_index_ui(self, indices):
        """更新指数UI"""
        try:
            print(f"更新指数UI: {len(indices)} 条")
            for idx_data in indices:
                name = idx_data.get('name', '')
                price = idx_data.get('price', 0)
                pct = idx_data.get('pct_chg', 0)
                high = idx_data.get('high', 0)
                low = idx_data.get('low', 0)
                volume = idx_data.get('volume', 0)
                amount = idx_data.get('amount', 0)

                color = '#f85149' if pct >= 0 else '#3fb950'

                if '上证' in name:
                    card = self.sh_index
                elif '深证' in name:
                    card = self.sz_index
                else:
                    print(f"未知指数: {name}")
                    continue

                card.price_label.setText(f'{price:.2f}')
                card.price_label.setStyleSheet(f'font-size: 20px; font-weight: bold; color: {color};')
                card.pct_label.setText(f'{pct:+.2f}%')
                card.pct_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {color};')
                card.high_label.setText(f'最高: {high:.2f}')
                card.low_label.setText(f'最低: {low:.2f}')
                # 成交量（手转亿手）
                if volume > 0:
                    vol_yi = volume / 100000000  # 手转亿手
                    card.vol_label.setText(f'成交量: {vol_yi:.2f}亿手')
                else:
                    card.vol_label.setText('成交量: --')
                card.amount_label.setText(f'成交额: {amount/100000000:.1f}亿')
            print("指数UI更新完成")
        except Exception as e:
            print(f"更新指数UI失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_interpretation_ui(self, result):
        """更新解读仪表盘UI"""
        try:
            print(f"更新解读UI: 分数 {result['overall_score']}")
            score = result['overall_score']
            sentiment = result['overall_sentiment']

            # 更新分数
            self.overall_score_label.setText(f'{score:+.2f}')

            # 更新颜色
            if score > 0.2:
                color = '#f85149'  # 利好红色
            elif score < -0.2:
                color = '#3fb950'  # 利空绿色
            else:
                color = '#ffea00'  # 中性黄色

            self.overall_score_label.setStyleSheet(f'font-size: 32px; font-weight: bold; color: {color};')

            # 更新情绪标签
            self.overall_sentiment_label.setText(sentiment)
            self.overall_sentiment_label.setStyleSheet(f'''
                font-size: 14px; font-weight: bold;
                padding: 4px 12px; border-radius: 4px;
                background: {color}33; color: {color};
            ''')

            # 更新进度条
            self.sentiment_bar.setValue(int(score * 100))

            # 更新利好板块
            bullish_sectors = result.get('top_bullish_sectors', [])
            if bullish_sectors:
                text = ' | '.join([f"{name}({count}条)" for name, count in bullish_sectors[:5]])
                self.bullish_sectors_label.setText(text)
            else:
                self.bullish_sectors_label.setText('暂无明显利好板块')

            # 更新利空板块
            bearish_sectors = result.get('top_bearish_sectors', [])
            if bearish_sectors:
                text = ' | '.join([f"{name}({count}条)" for name, count in bearish_sectors[:5]])
                self.bearish_sectors_label.setText(text)
            else:
                self.bearish_sectors_label.setText('暂无明显利空板块')

            # 更新利好个股
            bullish_stocks = result.get('top_bullish_stocks', [])
            if bullish_stocks:
                text = ' | '.join([f"{name}({count}条)" for name, count in bullish_stocks[:5]])
                self.bullish_stocks_label.setText(text)
            else:
                self.bullish_stocks_label.setText('暂无明显利好个股')

            # 更新利空个股
            bearish_stocks = result.get('top_bearish_stocks', [])
            if bearish_stocks:
                text = ' | '.join([f"{name}({count}条)" for name, count in bearish_stocks[:5]])
                self.bearish_stocks_label.setText(text)
            else:
                self.bearish_stocks_label.setText('暂无明显利空个股')

            print("解读UI更新完成")
        except Exception as e:
            print(f"更新解读UI失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_news_ui(self, news_list):
        """更新新闻列表UI（复用NewsPanelWidget）"""
        try:
            print(f"更新新闻UI: {len(news_list)} 条")
            self.news_panel.update_news(news_list)
            print("新闻UI更新完成")
        except Exception as e:
            print(f"更新新闻UI失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_detail_ui(self, news):
        """更新详情面板UI"""
        try:
            title = news.get('title', '')
            sentiment = news.get('sentiment', '中性')
            score = news.get('sentiment_score', 0)
            bullish_sectors = news.get('bullish_sectors', [])
            bearish_sectors = news.get('bearish_sectors', [])
            bullish_stocks = news.get('bullish_stocks', [])
            bearish_stocks = news.get('bearish_stocks', [])
            reasons = news.get('reasons', [])

            # 标题
            self.detail_title_label.setText(title)

            # 情绪
            if sentiment == '利好':
                color = '#f85149'
            elif sentiment == '利空':
                color = '#3fb950'
            else:
                color = '#8b949e'

            self.detail_sentiment_label.setText(f'情绪: {sentiment}')
            self.detail_sentiment_label.setStyleSheet(f'font-size: 12px; font-weight: bold; color: {color};')
            self.detail_score_label.setText(f'分数: {score:+.3f}')

            # 利好板块
            if bullish_sectors:
                self.bullish_sectors_detail.setText('、'.join(bullish_sectors))
            else:
                self.bullish_sectors_detail.setText('无明显利好板块')

            # 利空板块
            if bearish_sectors:
                self.bearish_sectors_detail.setText('、'.join(bearish_sectors))
            else:
                self.bearish_sectors_detail.setText('无明显利空板块')

            # 利好个股
            if bullish_stocks:
                self.bullish_stocks_detail.setText('、'.join(bullish_stocks))
            else:
                self.bullish_stocks_detail.setText('无明显利好个股')

            # 利空个股
            if bearish_stocks:
                self.bearish_stocks_detail.setText('、'.join(bearish_stocks))
            else:
                self.bearish_stocks_detail.setText('无明显利空个股')

            # 分析原因
            if reasons:
                self.reason_detail.setText('\n'.join([f"• {r}" for r in reasons]))
            else:
                self.reason_detail.setText('暂无详细分析')

        except Exception as e:
            print(f"更新详情UI失败: {e}")
            import traceback
            traceback.print_exc()
