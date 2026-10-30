# -*- coding: utf-8 -*-
"""
自选股面板 - 上下布局
上方：自选股列表
下方左侧：K线图 + 成交量
下方右侧：持仓管理 + 信号标签提醒
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QLineEdit, QFrame, QSplitter, QScrollArea, QInputDialog,
    QListWidget, QListWidgetItem, QCompleter, QTabWidget, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl
from datetime import datetime
from utils.trading_time import is_trading_time, get_trading_status
from PyQt6.QtGui import QColor, QBrush, QDesktopServices, QPainter, QPen, QFont

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_CARD_HOVER,
    BG_INTERACTIVE, BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE,
    ACCENT_RED, ACCENT_GREEN, ACCENT_GOLD, UP, DOWN,
)
from core.watchlist import get_watchlist_manager
from core.scan_engine import get_scan_engine
from utils.tdx_stock_list import get_realtime_quotes_tdx, get_finance_info_batch
from utils.tdx_connector import get_tdx_api
from utils.kline_provider import get_daily_kline
from utils.indicators import calc_ma_series, calc_kdj_series, calc_macd_series

# 导入专业K线图组件
from ui.echarts_kline import EChartsKlineWidget
from ui.kline_container import KlineContainer


class KlineChartWidget(QWidget):
    """K线图组件 - K线 + 均线 + 成交量"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kline_data = None
        self.code = ''          # [CYB-GATE] 按板性判涨停色用
        self.ma5 = None
        self.ma10 = None
        self.ma20 = None
        self.setMinimumHeight(300)
        self.setStyleSheet(f'background: #FFFFFF; border-radius: 12px; border: 1px solid rgba(0,0,0,0.06);')

    def set_kline_data(self, kline_data, code=''):
        """设置K线数据（code 用于按板性判涨停配色）"""
        self.code = str(code or '')

        print(f"[K线组件] set_kline_data被调用，数据: {kline_data is not None}")
        self.kline_data = kline_data

        if kline_data and len(kline_data.get('close', [])) >= 5:
            import pandas as pd
            closes = pd.Series(kline_data['close'])
            self.ma5 = closes.rolling(5).mean().values
            self.ma10 = closes.rolling(10).mean().values
            self.ma20 = closes.rolling(20).mean().values
            print(f"[K线组件] 均线计算完成，MA5: {self.ma5 is not None}, MA10: {self.ma10 is not None}, MA20: {self.ma20 is not None}")
        else:
            self.ma5 = None
            self.ma10 = None
            self.ma20 = None

        print(f"[K线组件] 调用update()")
        self.update()
        print(f"[K线组件] update()完成")

    def paintEvent(self, event):
        """绘制K线图"""
        import pandas as pd
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor('#FFFFFF'))

        if not self.kline_data or len(self.kline_data.get('close', [])) < 5:
            painter.setPen(QColor('#86868B'))
            painter.setFont(QFont('Arial', 12))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, '请选择股票查看K线图')
            return

        try:
            closes = self.kline_data['close']
            opens = self.kline_data['open']
            highs = self.kline_data['high']
            lows = self.kline_data['low']
            volumes = self.kline_data['volume']

            count = min(40, len(closes))
            start_idx = len(closes) - count

            # 区域划分
            chart_top = 25
            chart_bottom = int(h * 0.7)
            chart_h = chart_bottom - chart_top

            vol_top = chart_bottom + 10
            vol_bottom = h - 20
            vol_h = vol_bottom - vol_top

            # K线宽度
            left_margin = 50
            right_margin = 10
            chart_w = w - left_margin - right_margin
            kline_w = chart_w / count
            candle_w = max(kline_w * 0.6, 2)

            # 计算价格范围
            price_high = max(highs[start_idx:])
            price_low = min(lows[start_idx:])

            # 加入均线
            def add_ma_range(ma_data):
                nonlocal price_high, price_low
                if ma_data is not None:
                    ma_slice = ma_data[start_idx:]
                    valid = ma_slice[~pd.isna(ma_slice)]
                    if len(valid) > 0:
                        price_high = max(price_high, max(valid))
                        price_low = min(price_low, min(valid))

            add_ma_range(self.ma5)
            add_ma_range(self.ma10)
            add_ma_range(self.ma20)

            price_range = price_high - price_low
            if price_range == 0:
                price_range = 1

            # 网格
            painter.setPen(QColor('#F0F0F0'))
            for i in range(5):
                y = chart_top + chart_h * i / 4
                painter.drawLine(left_margin, int(y), w - right_margin, int(y))

            # 价格标签
            painter.setPen(QColor('#000000'))
            painter.setFont(QFont('Arial', 9))
            for i in range(5):
                price = price_high - price_range * i / 4
                y = chart_top + chart_h * i / 4
                painter.drawText(2, int(y) + 4, f'{price:.2f}')

            # 绘制均线
            def draw_ma(ma_data, color):
                if ma_data is None:
                    return
                painter.setPen(QPen(QColor(color), 1))
                points = []
                for i in range(count):
                    idx = start_idx + i
                    if idx < len(ma_data) and not pd.isna(ma_data[idx]):
                        x = left_margin + i * kline_w + kline_w / 2
                        y = chart_top + chart_h * (1 - (ma_data[idx] - price_low) / price_range)
                        points.append((x, y))
                if len(points) >= 2:
                    for i in range(len(points) - 1):
                        painter.drawLine(
                            int(points[i][0]), int(points[i][1]),
                            int(points[i+1][0]), int(points[i+1][1])
                        )

            draw_ma(self.ma5, '#000000')   # MA5 黑色
            draw_ma(self.ma10, '#FFC107')  # MA10 黄色
            draw_ma(self.ma20, '#FF3B30')  # MA20 红色

            # 绘制K线
            # [CYB-GATE] 涨停阈值按板性：创业板/科创板 20cm -> 19.8
            _lu_pct = 19.8 if self.code.startswith(('300', '301', '688', '689')) else 9.8
            for i in range(count):
                idx = start_idx + i
                x = left_margin + i * kline_w + kline_w * 0.2

                open_p = opens[idx]
                close_p = closes[idx]
                high_p = highs[idx]
                low_p = lows[idx]

                y_high = chart_top + chart_h * (1 - (high_p - price_low) / price_range)
                y_low = chart_top + chart_h * (1 - (low_p - price_low) / price_range)
                y_open = chart_top + chart_h * (1 - (open_p - price_low) / price_range)
                y_close = chart_top + chart_h * (1 - (close_p - price_low) / price_range)

                # 计算涨跌幅
                pct = (close_p - open_p) / open_p * 100 if open_p > 0 else 0

                # 颜色判断（涨停紫色实心，跌停黑色实心，上涨红实心，下跌绿空心）
                is_limit_up = (close_p == high_p) and (pct >= _lu_pct)
                is_limit_down = (close_p == low_p) and (pct <= -_lu_pct)
                if is_limit_up:
                    color = QColor('#AF52DE')
                    is_hollow = False
                elif is_limit_down:
                    color = QColor('#000000')
                    is_hollow = False
                elif close_p >= open_p:
                    color = QColor('#FF3B30')
                    is_hollow = False
                else:
                    color = QColor('#34C759')
                    is_hollow = True

                painter.setPen(color)
                if is_hollow:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    painter.setBrush(color)

                # 影线
                painter.drawLine(int(x + candle_w / 2), int(y_high), int(x + candle_w / 2), int(y_low))

                # 实体
                body_top = min(y_open, y_close)
                body_bottom = max(y_open, y_close)
                body_h = max(body_bottom - body_top, 1)
                painter.drawRect(int(x), int(body_top), int(candle_w), int(body_h))

            # 均线图例
            legend_y = 8
            painter.setFont(QFont('Arial', 9))

            # MA5
            painter.setPen(QColor('#000000'))
            ma5_val = self.ma5[-1] if self.ma5 is not None and len(self.ma5) > 0 and not pd.isna(self.ma5[-1]) else 0
            ma5_text = f'MA5: {ma5_val:.2f}' if ma5_val > 0 else 'MA5'
            painter.drawText(55, legend_y + 8, ma5_text)

            # MA10
            painter.setPen(QColor('#FFC107'))
            ma10_val = self.ma10[-1] if self.ma10 is not None and len(self.ma10) > 0 and not pd.isna(self.ma10[-1]) else 0
            ma10_text = f'MA10: {ma10_val:.2f}' if ma10_val > 0 else 'MA10'
            painter.drawText(130, legend_y + 8, ma10_text)

            # MA20
            painter.setPen(QColor('#FF3B30'))
            ma20_val = self.ma20[-1] if self.ma20 is not None and len(self.ma20) > 0 and not pd.isna(self.ma20[-1]) else 0
            ma20_text = f'MA20: {ma20_val:.2f}' if ma20_val > 0 else 'MA20'
            painter.drawText(215, legend_y + 8, ma20_text)

            # 成交量
            max_vol = max(volumes[start_idx:])
            if max_vol == 0:
                max_vol = 1

            painter.setPen(QColor('#000000'))
            painter.drawText(2, vol_top + 12, '成交量')

            for i in range(count):
                idx = start_idx + i
                x = left_margin + i * kline_w + kline_w * 0.2
                vol = volumes[idx]
                bar_h = (vol / max_vol) * vol_h

                open_p = opens[idx]
                close_p = closes[idx]
                pct = (close_p - open_p) / open_p * 100 if open_p > 0 else 0

                # 成交量颜色：上涨红实心，下跌蓝实心
                if close_p >= open_p:
                    color = QColor('#FF3B30')
                    is_hollow = False
                else:
                    color = QColor('#2563EB')
                    is_hollow = False

                painter.setPen(color)
                if is_hollow:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    painter.setBrush(color)

                painter.drawRect(int(x), int(vol_bottom - bar_h), int(candle_w), int(bar_h))

                # 倍量标记
                if idx > 0 and volumes[idx-1] > 0:
                    vol_ratio = volumes[idx] / volumes[idx-1]
                    if vol_ratio >= 5:
                        label_text = '5倍量'
                        label_color = QColor('#FF9500')
                    elif vol_ratio >= 3:
                        label_text = '3倍量'
                        label_color = QColor('#FF9500')
                    elif vol_ratio >= 2:
                        label_text = '2倍量'
                        label_color = QColor('#FF3B30')
                    else:
                        label_text = None
                        label_color = None

                    if label_text:
                        painter.setPen(label_color)
                        painter.setFont(QFont('Arial', 8))
                        text_x = int(x + candle_w / 2 - 20)
                        text_y = int(vol_bottom - bar_h - 5)
                        painter.drawText(text_x, text_y, label_text)
                        painter.setFont(QFont('Arial', 9))

        except Exception as e:
            print(f"K线绘制错误: {e}")
            import traceback
            traceback.print_exc()
            painter.setPen(QColor('#FF3B30'))
            painter.setFont(QFont('Arial', 10))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, f'绘制错误: {str(e)[:30]}')



class WatchlistWidget(QWidget):
    """自选股面板 - 上下布局"""

    stock_clicked = pyqtSignal(str, str)  # code, name
    data_ready = pyqtSignal(list)  # 数据加载完成信号
    theme_ready = pyqtSignal()  # 题材计算完成信号
    kline_data_ready = pyqtSignal(object, str, str)  # K线数据就绪信号 (kline_data, code, name)
    time_share_ready = pyqtSignal(object, str, str)  # 分时数据就绪信号 (time_share_data, code, name)
    quote_detail_ready = pyqtSignal(float, float, str, float, float, float)  # 详细数据就绪 (amount, turnover, industry, market_cap, float_cap, volume_ratio)
    quote_detail_error = pyqtSignal(str)  # 详细数据获取失败
    news_ready = pyqtSignal(list)  # 资讯数据就绪信号
    announce_ready = pyqtSignal(list)  # 公告数据就绪信号
    fund_flow_ready = pyqtSignal(dict)  # 资金流向数据就绪信号
    forecast_ready = pyqtSignal(list)  # 业绩预告数据就绪信号
    biz_data_ready = pyqtSignal(str, list)  # 主营构成数据就绪 (code6, items)
    profit_breakdown_ready = pyqtSignal(str, str)  # 营利拆解纯文本就绪 (code6, text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.watchlist_manager = get_watchlist_manager()
        self.scan_engine = get_scan_engine()
        self.stocks = []
        self.selected_stock = None
        self.position_stocks = []  # 持仓股票列表
        self.theme_cache = {}  # 题材分析缓存 {code: theme_result}
        self._init_signals()
        self._init_ui()
        # 注册自选股变化回调
        self.watchlist_manager.add_change_callback(self._on_watchlist_changed)
        # 自动刷新定时器（每30秒刷新一次，避免频繁刷新导致卡顿）
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(lambda: self._refresh_data(auto=True))
        self._refresh_timer.start(30000)
        self._refresh_data()

        # 大盘指数功能已删除
        # self._market_timer = QTimer(self)
        # self._market_timer.timeout.connect(self._refresh_market_index)
        # self._market_timer.start(30000)
        # self._refresh_market_index()

    def _on_watchlist_changed(self):
        """自选股变化时触发（通过QTimer确保在UI线程执行）"""
        print("[WatchlistPanel] 收到变化通知，准备刷新")
        QTimer.singleShot(0, self._refresh_data)

    def _refresh_market_index(self):
        """刷新大盘指数数据（新浪财经主接口 + 东方财富备用）"""
        import threading
        def _do():
            try:
                print(f"[大盘指数] 开始获取真实数据")
                import requests

                # ========== 上证指数（新浪财经主接口） ==========
                sh_price = 0
                sh_pct = 0
                sh_success = False
                try:
                    url = 'https://hq.sinajs.cn/list=sh000001'
                    headers = {
                        'Referer': 'https://finance.sina.com.cn',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    r = requests.get(url, headers=headers, timeout=8)
                    if r.status_code == 200 and '="' in r.text:
                        parts = r.text.split('"')[1].split(',')
                        if len(parts) >= 4:
                            sh_price = float(parts[3])
                            sh_last = float(parts[2])
                            sh_pct = (sh_price - sh_last) / sh_last * 100 if sh_last > 0 else 0
                            sh_success = True
                            print(f"[大盘指数] 新浪上证指数: {sh_price:.2f}, {sh_pct:+.2f}%")
                except Exception as e:
                    print(f"[大盘指数] 新浪上证接口失败: {e}")

                # 备用：东方财富
                if not sh_success:
                    try:
                        url = 'http://push2delay.eastmoney.com/api/qt/stock/get'
                        params = {'secid': '1.000001', 'fields': 'f43,f60,f170'}
                        r = requests.get(url, params=params, timeout=8)
                        if r.status_code == 200:
                            data = r.json()
                            if data.get('data'):
                                d = data['data']
                                sh_price = d.get('f43', 0) / 100
                                sh_last = d.get('f60', 0) / 100
                                sh_pct = d.get('f170', 0) / 100
                                sh_success = True
                                print(f"[大盘指数] 东方财富上证指数: {sh_price:.2f}, {sh_pct:+.2f}%")
                    except Exception as e:
                        print(f"[大盘指数] 东方财富上证接口失败: {e}")

                # ========== 深证成指（新浪财经主接口） ==========
                sz_price = 0
                sz_pct = 0
                sz_success = False
                try:
                    url = 'https://hq.sinajs.cn/list=sz399001'
                    headers = {
                        'Referer': 'https://finance.sina.com.cn',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    r = requests.get(url, headers=headers, timeout=8)
                    if r.status_code == 200 and '="' in r.text:
                        parts = r.text.split('"')[1].split(',')
                        if len(parts) >= 4:
                            sz_price = float(parts[3])
                            sz_last = float(parts[2])
                            sz_pct = (sz_price - sz_last) / sz_last * 100 if sz_last > 0 else 0
                            sz_success = True
                            print(f"[大盘指数] 新浪深证成指: {sz_price:.2f}, {sz_pct:+.2f}%")
                except Exception as e:
                    print(f"[大盘指数] 新浪深证接口失败: {e}")

                # 备用：东方财富
                if not sz_success:
                    try:
                        url = 'http://push2delay.eastmoney.com/api/qt/stock/get'
                        params = {'secid': '0.399001', 'fields': 'f43,f60,f170'}
                        r = requests.get(url, params=params, timeout=8)
                        if r.status_code == 200:
                            data = r.json()
                            if data.get('data'):
                                d = data['data']
                                sz_price = d.get('f43', 0) / 100
                                sz_last = d.get('f60', 0) / 100
                                sz_pct = d.get('f170', 0) / 100
                                sz_success = True
                                print(f"[大盘指数] 东方财富深证成指: {sz_price:.2f}, {sz_pct:+.2f}%")
                    except Exception as e:
                        print(f"[大盘指数] 东方财富深证接口失败: {e}")

                # ========== 涨跌家数（估算） ==========
                sh_up = 0
                sh_flat = 0
                sh_down = 0
                sz_up = 0
                sz_flat = 0
                sz_down = 0

                try:
                    sh_total = 2200  # 沪市约2200只
                    sz_total = 2800  # 深市约2800只

                    # 根据指数涨跌幅估算涨跌家数比例
                    if sh_total > 0:
                        ratio = 0.5 + (sh_pct / 5) * 0.3
                        ratio = max(0.1, min(0.9, ratio))
                        sh_up = int(sh_total * ratio)
                        sh_down = sh_total - sh_up
                        sh_flat = int(sh_total * 0.05)

                    if sz_total > 0:
                        ratio = 0.5 + (sz_pct / 5) * 0.3
                        ratio = max(0.1, min(0.9, ratio))
                        sz_up = int(sz_total * ratio)
                        sz_down = sz_total - sz_up
                        sz_flat = int(sz_total * 0.05)
                except Exception as e:
                    print(f"[大盘指数] 涨跌家数估算失败: {e}")

                # ========== 更新UI ==========
                def update_ui():
                    # 上证指数
                    if sh_success:
                        sh_color = '#f85149' if sh_pct >= 0 else '#3fb950'
                        self.sh_price_label.setText(f'{sh_price:.2f}')
                        self.sh_price_label.setStyleSheet(f'font-size: 12px; font-weight: bold; color: {sh_color};')
                        self.sh_pct_label.setText(f'{sh_pct:+.2f}%')
                        self.sh_pct_label.setStyleSheet(f'font-size: 11px; color: {sh_color};')
                        self.sh_count_label.setText(f'上涨 {sh_up}家  平盘 {sh_flat}家  下跌 {sh_down}家')
                    else:
                        self.sh_price_label.setText('获取失败')
                        self.sh_pct_label.setText('--')
                        self.sh_count_label.setText('行情接口异常')

                    # 深证成指
                    if sz_success:
                        sz_color = '#f85149' if sz_pct >= 0 else '#3fb950'
                        self.sz_price_label.setText(f'{sz_price:.2f}')
                        self.sz_price_label.setStyleSheet(f'font-size: 12px; font-weight: bold; color: {sz_color};')
                        self.sz_pct_label.setText(f'{sz_pct:+.2f}%')
                        self.sz_pct_label.setStyleSheet(f'font-size: 11px; color: {sz_color};')
                        self.sz_count_label.setText(f'上涨 {sz_up}家  平盘 {sz_flat}家  下跌 {sz_down}家')
                    else:
                        self.sz_price_label.setText('获取失败')
                        self.sz_pct_label.setText('--')
                        self.sz_count_label.setText('行情接口异常')

                QTimer.singleShot(0, update_ui)
                print(f"[大盘指数] 更新完成, 上证成功:{sh_success}, 深证成功:{sz_success}")

            except Exception as e:
                print(f"[大盘指数] 整体失败: {e}")
                import traceback
                traceback.print_exc()

        threading.Thread(target=_do, daemon=True).start()

    def _init_signals(self):
        """初始化信号槽连接"""
        self.data_ready.connect(self._update_table)
        self.theme_ready.connect(self._update_table)  # 题材计算完成后更新表格
        self.kline_data_ready.connect(self._on_kline_data_ready)
        self.time_share_ready.connect(self._set_time_share_data)
        self.quote_detail_ready.connect(self._on_quote_detail_ready)
        self.quote_detail_error.connect(self._on_quote_detail_error)
        self.news_ready.connect(self._update_news_list)
        self.announce_ready.connect(self._update_announce_list)
        self.fund_flow_ready.connect(self._update_fund_flow)
        self.forecast_ready.connect(self._update_forecast_list)
        self.biz_data_ready.connect(self._fill_biz_table)
        self.profit_breakdown_ready.connect(self._fill_business_breakdown)

    def _init_ui(self):
        self.setStyleSheet(f"""
            WatchlistWidget {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel('⭐ 我的自选')
        title.setStyleSheet(f'font-size: 15px; font-weight: 700; color: {TEXT_PRIMARY}; letter-spacing: 0.2px;')
        header.addWidget(title)
        header.addStretch()
        
        # 股票搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索股票代码/名称...')
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; padding: 4px 8px; color: {TEXT_PRIMARY};
                font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_BLUE}; }}
        """)
        header.addWidget(self.search_input)
        
        # 搜索自动补全
        self.search_completer = QCompleter([])
        self.search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_completer.setMaxVisibleItems(20)
        self.search_completer.popup().setStyleSheet(f"""
            QListView {{
                background: {BG_PANEL_ALT}; border: 1px solid {BORDER};
                border-radius: 4px; color: {TEXT_PRIMARY}; font-size: 12px;
                outline: none;
            }}
            QListView::item {{ padding: 6px 12px; }}
            QListView::item:hover {{ background: {BG_CARD_HOVER}; }}
            QListView::item:selected {{ background: {ACCENT_BLUE}; }}
        """)
        self.search_input.setCompleter(self.search_completer)
        self.search_completer.activated.connect(self._on_search_completed)
        # 回车也触发添加
        self.search_input.returnPressed.connect(self._on_search_return_pressed)

        # 搜索数据延迟加载（第一次输入时加载）
        self._search_data_loaded = False
        self.search_input.textChanged.connect(self._on_search_text_changed)
        
        # 刷新按钮
        self.refresh_btn = QPushButton('🔄 刷新行情')
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; padding: 4px 12px; color: {TEXT_PRIMARY};
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
        """)
        self.refresh_btn.clicked.connect(self._refresh_data)
        header.addWidget(self.refresh_btn)
        
        layout.addLayout(header)

        # ========== V2.8 模块7：组合分析面板（用户要求删除） ==========
        self.portfolio_panel = None
        # ========== 模块7 END ==========

        # 分割器（上下两栏）
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {BORDER};
            }}
            QSplitter::handle:vertical {{
                height: 4px;
            }}
        """)

        # 上半部分：自选股列表
        self.top_widget = self._create_stock_list_panel()
        splitter.addWidget(self.top_widget)

        # 下半部分：左右两栏（K线图 + 持仓/信号）
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {BORDER};
            }}
            QSplitter::handle:horizontal {{
                width: 4px;
            }}
        """)

        # 下方左侧：K线图 + 成交量
        self.kline_widget = self._create_kline_panel()
        bottom_splitter.addWidget(self.kline_widget)

        # 下方右侧：持仓管理 + 信号提醒
        self.right_panel = self._create_position_panel()
        bottom_splitter.addWidget(self.right_panel)

        # 设置下方左右比例
        bottom_splitter.setStretchFactor(0, 65)
        bottom_splitter.setStretchFactor(1, 35)

        splitter.addWidget(bottom_splitter)

        # 设置上下比例
        splitter.setStretchFactor(0, 40)
        splitter.setStretchFactor(1, 60)

        layout.addWidget(splitter, 1)

    def _create_stock_list_panel(self):
        """创建自选股列表面板（上方）"""
        frame = QFrame()
        frame.setStyleSheet(f'background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px;')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 数据状态栏
        status_bar = QHBoxLayout()
        status_bar.setSpacing(15)

        # 行情接口状态
        self.quote_status_label = QLabel('行情接口: 🟢 正常')
        self.quote_status_label.setStyleSheet(f'font-size: 11px; color: {ACCENT_GREEN};')
        status_bar.addWidget(self.quote_status_label)

        # 股票资料状态
        self.info_status_label = QLabel('股票资料: 🟢 正常')
        self.info_status_label.setStyleSheet(f'font-size: 11px; color: {ACCENT_GREEN};')
        status_bar.addWidget(self.info_status_label)

        status_bar.addStretch()

        # 最后更新时间
        self.update_time_label = QLabel('更新时间: --')
        self.update_time_label.setStyleSheet(f'font-size: 11px; color: {TEXT_SECONDARY};')
        status_bar.addWidget(self.update_time_label)

        layout.addLayout(status_bar)

        # 股票表格
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            '代码', '名称', '现价', '涨跌幅', '涨停异动题材', '趋势', '涨停次数', '关键价格', 'AI操作建议', '控盘'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  # 列宽可手动调节
        self.table.horizontalHeader().setSectionsMovable(True)  # 列可左右拖动
        self.table.horizontalHeader().setSortIndicatorShown(True)  # 显示排序箭头
        # 设置各列默认宽度
        self.table.setColumnWidth(0, 70)   # 代码
        self.table.setColumnWidth(1, 90)   # 名称
        self.table.setColumnWidth(2, 60)   # 现价
        self.table.setColumnWidth(3, 70)   # 涨跌幅
        self.table.setColumnWidth(4, 220)  # 涨停异动题材
        self.table.setColumnWidth(5, 60)   # 趋势
        self.table.setColumnWidth(6, 70)   # 涨停次数
        self.table.setColumnWidth(7, 140)  # 关键价格
        self.table.setColumnWidth(8, 120)  # AI操作建议
        self.table.setColumnWidth(9, 78)    # 控盘
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(45)  # 默认行高（支持多行核心题材）
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_stock_selected)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG_CONTAINER}; gridline-color: {BORDER};
                color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; font-size: 12px;
                alternate-background-color: {BG_PANEL_ALT};
                selection-background-color: rgba(90,169,255,0.22);
                selection-color: {TEXT_PRIMARY};
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER};
                padding: 6px; font-weight: 700; font-size: 12px;
            }}
            QTableWidget::item {{ border-bottom: 1px solid {BORDER}; padding: 5px 4px; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); }}
        """)
        layout.addWidget(self.table)

        return frame

    def _create_kline_panel(self):
        """创建专业K线图面板（自绘）"""
        frame = QFrame()
        frame.setStyleSheet(f'background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 10px;')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 标题
        title_layout = QHBoxLayout()
        self.kline_title = QLabel('📈 专业K线图（日K）')
        self.kline_title.setStyleSheet(f'font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};')
        title_layout.addWidget(self.kline_title)
        title_layout.addStretch()

        self.kline_stock_label = QLabel('点击股票查看K线')
        self.kline_stock_label.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 12px;')
        title_layout.addWidget(self.kline_stock_label)
        layout.addLayout(title_layout)

        # 盘口实时信息条
        self.order_book_bar = QLabel('盘口: 请点击股票查看实时盘口')
        self.order_book_bar.setStyleSheet(f'background: {BG_PANEL_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 6px; padding: 6px 10px; font-size: 12px; color: {TEXT_PRIMARY};')
        layout.addWidget(self.order_book_bar)

        # 周期切换按钮栏
        period_bar = QWidget()
        period_bar.setStyleSheet(f'background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 6px;')
        period_layout = QHBoxLayout(period_bar)
        period_layout.setContentsMargins(10, 5, 10, 5)
        period_layout.setSpacing(5)
        
        self.kline_period = 'day'
        self.period_buttons = {}
        periods = [
            ('15min', '15分'),
            ('30min', '30分'),
            ('60min', '60分'),
            ('day', '日K'),
            ('week', '周K'),
            ('month', '月K'),
        ]
        
        for period, name in periods:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SECONDARY};
                    border: none;
                    padding: 2px 8px;
                    font-size: 12px;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: {BG_CARD_HOVER};
                    color: {TEXT_PRIMARY};
                }}
                QPushButton:checked {{
                    background: {BG_INTERACTIVE};
                    color: {ACCENT_BLUE};
                    font-weight: 700;
                }}
            """)
            btn.clicked.connect(lambda checked, p=period: self._on_kline_period_changed(p))
            period_layout.addWidget(btn)
            self.period_buttons[period] = btn
        
        self.period_buttons['day'].setChecked(True)
        period_layout.addStretch()
        layout.addWidget(period_bar)

        # 专业K线图（ECharts，支持缩放拖动、十字光标、一年数据）
        self.kline_chart = KlineContainer()  # K线容器，ECharts优先，QPainter备用
        layout.addWidget(self.kline_chart, 1)

        return frame

    def _create_position_panel(self):
        """创建盘口实时信息 + 大盘指数 + 公司资料 + 板块概念面板"""
        frame = QFrame()
        frame.setStyleSheet(f'background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 10px;')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ========== 盘口实时信息 ==========
        quote_title = QLabel('📊 盘口实时信息')
        quote_title.setStyleSheet(f'font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY};')
        layout.addWidget(quote_title)

        # 价格信息区域
        price_widget = QWidget()
        price_layout = QHBoxLayout(price_widget)
        price_layout.setContentsMargins(0, 0, 0, 0)
        price_layout.setSpacing(10)

        self.quote_price_label = QLabel('--')
        self.quote_price_label.setStyleSheet(f'font-size: 28px; font-weight: 700; color: {ACCENT_RED};')
        price_layout.addWidget(self.quote_price_label)

        pct_widget = QWidget()
        pct_layout = QVBoxLayout(pct_widget)
        pct_layout.setContentsMargins(0, 0, 0, 0)
        pct_layout.setSpacing(2)

        self.quote_pct_label = QLabel('--')
        self.quote_pct_label.setStyleSheet(f'font-size: 13px; color: {ACCENT_RED};')
        pct_layout.addWidget(self.quote_pct_label)

        self.quote_change_label = QLabel('--')
        self.quote_change_label.setStyleSheet(f'font-size: 11px; color: {ACCENT_RED};')
        pct_layout.addWidget(self.quote_change_label)

        price_layout.addWidget(pct_widget)
        price_layout.addStretch()

        layout.addWidget(price_widget)

        # 盘口数据表格
        self.quote_table = QTableWidget()
        self.quote_table.setColumnCount(4)
        self.quote_table.horizontalHeader().setVisible(False)
        self.quote_table.verticalHeader().setVisible(False)
        self.quote_table.setRowCount(6)
        self.quote_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.quote_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.quote_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.quote_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.quote_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.quote_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.quote_table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG_CONTAINER}; gridline-color: {BORDER};
                color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; font-size: 11px;
                border-radius: 8px;
            }}
            QTableWidget::item {{ padding: 2px 4px; }}
        """)

        # 初始化盘口数据（两列布局）
        quote_items = [
            ('今开', '--', '最高', '--'),
            ('最低', '--', '昨收', '--'),
            ('涨停', '--', '跌停', '--'),
            ('成交量', '--', '成交额', '--'),
            ('换手率', '--', '量比', '--'),
            ('总市值', '--', '流通市值', '--'),
        ]
        for row, (label1, value1, label2, value2) in enumerate(quote_items):
            label_item1 = QTableWidgetItem(label1)
            label_item1.setForeground(QBrush(QColor('#64748B')))
            self.quote_table.setItem(row, 0, label_item1)
            value_item1 = QTableWidgetItem(value1)
            value_item1.setForeground(QBrush(QColor('#1E293B')))
            self.quote_table.setItem(row, 1, value_item1)
            label_item2 = QTableWidgetItem(label2)
            label_item2.setForeground(QBrush(QColor('#64748B')))
            self.quote_table.setItem(row, 2, label_item2)
            value_item2 = QTableWidgetItem(value2)
            value_item2.setForeground(QBrush(QColor('#1E293B')))
            self.quote_table.setItem(row, 3, value_item2)

        layout.addWidget(self.quote_table)

        self.info_tab = QTabWidget()
        self.info_tab.setTabBarAutoHide(False)
        self.info_tab.setVisible(False)  # V2.8：隐藏公告/资讯/资金/业绩标签页
        # 标签可拖动排序
        self.info_tab.tabBar().setMovable(True)
        # 标签样式
        self.info_tab.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {BORDER};
                border-radius: 6px;
                background: {BG_CONTAINER};
            }}
            QTabBar::tab {{
                background: {BG_PANEL};
                color: {TEXT_SECONDARY};
                padding: 6px 12px;
                border: 1px solid {BORDER};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {BG_CONTAINER};
                color: {ACCENT_BLUE};
                border-bottom: 2px solid {ACCENT_BLUE};
            }}
            QTabBar::tab:hover {{
                background: {BG_CARD_HOVER};
                color: {TEXT_PRIMARY};
            }}
            QScrollBar:vertical {{
                background: {BG_PANEL};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_STRONG};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {BORDER_SOFT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        self.info_tab.setStyleSheet(f"""
            QTabWidget {{
                background: {BG_CONTAINER};
                border: none;
            }}
            QTabBar::tab {{
                background: {BG_PANEL};
                color: {TEXT_SECONDARY};
                padding: 6px 12px;
                border: none;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {BG_INTERACTIVE};
                color: {ACCENT_BLUE};
                border-bottom: 2px solid {ACCENT_BLUE};
            }}
            QTabWidget::pane {{
                border: 1px solid {BORDER};
                border-radius: 4px;
                background: {BG_CONTAINER};
            }}
            QListWidget QScrollBar:vertical {{
                width: 0px;
            }}
            QListWidget QScrollBar::handle:vertical {{
                width: 0px;
            }}
        """)

        # 标签1：公司公告
        self.announce_list = QListWidget()
        self.announce_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_CONTAINER};
                border: none;
                color: {TEXT_SECONDARY};
                font-size: 11px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 4px;
                border-bottom: 1px solid {BORDER};
            }}
            QListWidget::item:hover {{
                background: {BG_CARD_HOVER};
                color: {ACCENT_BLUE};
            }}
            QListWidget::item:selected {{
                background: {ACCENT_BLUE};
                color: {TEXT_PRIMARY};
            }}
        """)
        self.announce_list.addItem('点击股票加载公告...')
        self.announce_list.itemClicked.connect(self._on_announce_clicked)
        self.info_tab.addTab(self.announce_list, '📢 公告')

        # 标签2：个股资讯
        self.news_list = QListWidget()
        self.news_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_CONTAINER};
                border: none;
                color: {TEXT_SECONDARY};
                font-size: 11px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 4px;
                border-bottom: 1px solid {BORDER};
            }}
            QListWidget::item:hover {{
                background: {BG_CARD_HOVER};
                color: {ACCENT_BLUE};
            }}
            QListWidget::item:selected {{
                background: {ACCENT_BLUE};
                color: {TEXT_PRIMARY};
            }}
        """)
        self.news_list.addItem('点击股票加载资讯...')
        self.news_list.itemClicked.connect(self._on_news_clicked)
        self.info_tab.addTab(self.news_list, '📰 资讯')

        # 标签3：资金流向
        self.fund_flow_list = QListWidget()
        self.fund_flow_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_CONTAINER};
                border: none;
                color: {TEXT_SECONDARY};
                font-size: 11px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 4px;
                border-bottom: 1px solid {BORDER};
            }}
        """)
        self.fund_flow_list.addItem('点击股票加载资金流向...')
        self.info_tab.addTab(self.fund_flow_list, '💰 资金')

        # 标签4：业绩预告
        self.forecast_list = QListWidget()
        self.forecast_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_CONTAINER};
                border: none;
                color: {TEXT_SECONDARY};
                font-size: 11px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 4px;
                border-bottom: 1px solid {BORDER};
            }}
            QListWidget::item:hover {{
                background: {BG_CARD_HOVER};
                color: {ACCENT_BLUE};
            }}
            QListWidget::item:selected {{
                background: {ACCENT_BLUE};
                color: {TEXT_PRIMARY};
            }}
        """)
        self.forecast_list.addItem('点击股票加载业绩预告...')
        self.forecast_list.itemClicked.connect(self._on_forecast_clicked)
        self.info_tab.addTab(self.forecast_list, '📊 业绩')

        # 可拖动调整高度
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(4)
        splitter.addWidget(self.info_tab)

        # ========== AI操作建议 + 关键价格区域 ==========
        ai_frame = QFrame()
        ai_frame.setStyleSheet(f'background: {BG_CONTAINER}; border: 1px solid {BORDER}; border-radius: 8px;')
        ai_layout = QVBoxLayout(ai_frame)
        ai_layout.setContentsMargins(8, 8, 8, 8)
        ai_layout.setSpacing(6)

        # AI操作建议标题
        ai_title = QLabel('🤖 AI操作建议')
        ai_title.setStyleSheet(f'font-size: 13px; font-weight: 700; color: {TEXT_PRIMARY};')
        ai_title.setVisible(False)  # V2.8：隐藏AI操作建议标题
        ai_layout.addWidget(ai_title)

        # AI建议内容
        self.ai_advice_label = QLabel('请选择股票查看AI分析')
        self.ai_advice_label.setStyleSheet(f'font-size: 14px; font-weight: 700; color: {ACCENT_BLUE}; padding: 4px;')
        self.ai_advice_label.setWordWrap(True)
        self.ai_advice_label.setVisible(False)  # V2.8：隐藏AI操作建议内容
        ai_layout.addWidget(self.ai_advice_label)

        # 关键价格标题
        kp_title = QLabel('💰 关键价格')
        kp_title.setStyleSheet(f'font-size: 13px; font-weight: 700; color: {TEXT_PRIMARY}; margin-top: 6px;')
        ai_layout.addWidget(kp_title)

        # 关键价格表格
        self.ai_key_price_table = QTableWidget()
        self.ai_key_price_table.setColumnCount(2)
        self.ai_key_price_table.horizontalHeader().setVisible(False)
        self.ai_key_price_table.verticalHeader().setVisible(False)
        self.ai_key_price_table.setRowCount(5)
        self.ai_key_price_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.ai_key_price_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ai_key_price_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ai_key_price_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.ai_key_price_table.setMaximumHeight(140)
        self.ai_key_price_table.setStyleSheet(f"""
            QTableWidget {{ background: {BG_CONTAINER}; gridline-color: {BORDER}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; font-size: 11px; }}
        """)

        kp_items = [
            ('买入区域', '--'),
            ('止损位', '--'),
            ('压力位', '--'),
            ('第一目标', '--'),
            ('第二目标', '--'),
        ]
        for row, (label, value) in enumerate(kp_items):
            label_item = QTableWidgetItem(label)
            label_item.setForeground(QBrush(QColor('#64748B')))  # V2.8：调亮标签颜色
            self.ai_key_price_table.setItem(row, 0, label_item)
            value_item = QTableWidgetItem(value)
            value_item.setForeground(QBrush(QColor('#1E293B')))  # V2.8：改成深色，确保可见
            self.ai_key_price_table.setItem(row, 1, value_item)

        ai_layout.addWidget(self.ai_key_price_table)
        ai_layout.addStretch()

        # splitter.addWidget(ai_frame)  # 用户要求删除关键价格面板
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([300, 200])  # 初始高度

        layout.addWidget(splitter, 1)  # 占拉伸空间

        return frame

    def _refresh_data(self, auto=False):
        """刷新自选股数据
        Args:
            auto: 是否自动刷新（True=自动刷新，非交易时间跳过；False=手动刷新，始终执行）
        """
        # 防止并发刷新
        if getattr(self, '_is_refreshing', False):
            print("[自选股刷新] 上一次刷新未完成，跳过")
            return
        self._is_refreshing = True

        # 自动刷新时，非交易时间跳过（只在状态变化时打印一次，避免刷屏）
        if auto and not is_trading_time():
            status = get_trading_status()
            last_status = getattr(self, '_last_trading_status', None)
            if last_status != status:
                print(f"[自选股刷新] 当前为{status}时段，暂停自动刷新（进入交易时间后自动恢复）")
                self._last_trading_status = status
            self._is_refreshing = False
            return
        # 进入交易时间时打印恢复提示
        if auto and is_trading_time():
            last_status = getattr(self, '_last_trading_status', None)
            if last_status and last_status != 'trading':
                print(f"[自选股刷新] 进入交易时段，恢复实时行情刷新")
            self._last_trading_status = 'trading'

        print("[刷新日志 1/10] 开始刷新数据")
        import threading
        def _do():
            try:
                watchlist = self.watchlist_manager.get_all()
                print(f"[刷新日志 2/10] 从管理器获取到 {len(watchlist)} 只自选股")
                if not watchlist:
                    self.data_ready.emit([])
                    return

                codes = [s['code'] for s in watchlist]
                names = {s['code']: s['name'] for s in watchlist}

                # 先构建基础数据
                stocks = []
                for code in codes:
                    stocks.append({
                        'code': code,
                        'name': names.get(code, ''),
                        'price': 0,
                        'pct_chg': 0,
                        'volume': 0,
                        'signals': [],
                        'trend': '--',
                        'limit_up_count': 0,
                        'limit_up_reason': '--',
                        'sector': '--',
                        'concept': '--',
                    })

                print(f"[刷新日志 3/10] 基础数据构建完成，共 {len(stocks)} 只股票")

                # 获取实时行情
                print(f"[刷新日志 4/10] 开始获取实时行情...")

                # 尝试获取实时行情（通达信）
                try:
                    print(f"[WatchlistPanel] 获取 {len(codes)} 只股票的实时行情...")
                    quotes = get_realtime_quotes_tdx(codes)
                    print(f"[WatchlistPanel] 获取到 {len(quotes)} 条行情数据")

                    for stock in stocks:
                        code = stock['code']
                        quote = quotes.get(code, {})
                        stock['price'] = quote.get('price', 0)
                        stock['pct_chg'] = quote.get('pct_chg', 0)
                        stock['volume'] = quote.get('volume', 0)
                        stock['amount'] = quote.get('amount', 0)
                        stock['open'] = quote.get('open', 0)
                        stock['high'] = quote.get('high', 0)
                        stock['low'] = quote.get('low', 0)
                        stock['last_close'] = quote.get('last_close', 0)
                except Exception as e:
                    print(f"[WatchlistPanel] 获取行情失败: {e}")

                # 腾讯行情接口（补齐换手率、市值等字段）
                try:
                    print(f"[WatchlistPanel] ========== 腾讯行情数据获取开始 ==========")
                    import requests

                    # 构造腾讯行情URL
                    q_codes = []
                    for code in codes:
                        if code.startswith('6'):
                            q_codes.append(f'sh{code}')
                        else:
                            q_codes.append(f'sz{code}')

                    print(f"[WatchlistPanel] 请求股票: {q_codes}")

                    url = f'https://qt.gtimg.cn/q={",".join(q_codes)}'
                    r = requests.get(url, timeout=10)
                    print(f"[WatchlistPanel] 腾讯接口状态码: {r.status_code}")

                    if r.status_code == 200:
                        lines = r.text.strip().split(';')
                        tencent_quotes = {}
                        for line in lines:
                            if '="' in line:
                                parts = line.split('"')[1].split('~')
                                if len(parts) > 45:
                                    code = parts[2]
                                    tencent_quotes[code] = {
                                        'name': parts[1],
                                        'price': float(parts[3]) if parts[3] else 0,
                                        'amount': float(parts[37]) * 10000 if parts[37] else 0,  # 万元转元
                                        'turnover': float(parts[38]) if parts[38] else 0,  # 换手率%
                                        'market_cap': float(parts[45]) if parts[45] else 0,  # 总市值亿
                                        'float_cap': float(parts[44]) if parts[44] else 0,  # 流通市值亿
                                    }
                                    print(f"[WatchlistPanel]   {code}: 成交额={parts[37]}万, 换手率={parts[38]}%, 总市值={parts[45]}亿, 流通市值={parts[44]}亿")

                        print(f"[WatchlistPanel] 获取到 {len(tencent_quotes)} 条腾讯行情数据")

                        # 补齐字段
                        for stock in stocks:
                            code = stock['code']
                            if code in tencent_quotes:
                                q = tencent_quotes[code]
                                stock['turnover'] = q['turnover']
                                stock['market_cap'] = q['market_cap']
                                stock['float_cap'] = q['float_cap']
                                stock['amount'] = q['amount']
                                if not stock['name']:
                                    stock['name'] = q['name']
                                print(f"[WatchlistPanel]   赋值 {code}: turnover={stock['turnover']}, market_cap={stock['market_cap']}, float_cap={stock['float_cap']}, amount={stock['amount']}")
                            else:
                                print(f"[WatchlistPanel]   {code}: 未在腾讯数据中找到")

                        # 验证赋值结果
                        if len(stocks) > 0:
                            first = stocks[0]
                            print(f"[WatchlistPanel] 验证第一只股票 {first['code']}:")
                            print(f"[WatchlistPanel]   amount: {first.get('amount', '不存在')}")
                            print(f"[WatchlistPanel]   turnover: {first.get('turnover', '不存在')}")
                            print(f"[WatchlistPanel]   market_cap: {first.get('market_cap', '不存在')}")
                            print(f"[WatchlistPanel]   float_cap: {first.get('float_cap', '不存在')}")
                            print(f"[WatchlistPanel]   所有字段: {list(first.keys())}")
                    else:
                        print(f"[WatchlistPanel] 腾讯接口返回非200状态码")
                except Exception as e:
                    print(f"[WatchlistPanel] 腾讯行情获取失败: {e}")
                    import traceback
                    traceback.print_exc()

                print(f"[WatchlistPanel] ========== 腾讯行情数据获取结束 ==========")

                # 批量获取K线数据，用于信号扫描和涨停统计
                try:
                    print(f"[WatchlistPanel] 批量获取K线数据...")
                    from utils.kline_provider import get_daily_kline_batch
                    kline_map = get_daily_kline_batch(codes, count=150, max_workers=3)
                    print(f"[WatchlistPanel] 获取到 {len(kline_map)} 只股票的K线数据")

                    # 导入扫描器
                    from strategy.kline_scanner import get_scanner
                    from strategy.indicator_scanner import get_indicator_scanner
                    from strategy.main_trend_scanner import get_main_trend_scanner

                    kline_scanner = get_scanner()
                    indicator_scanner = get_indicator_scanner()
                    main_trend_scanner = get_main_trend_scanner()

                    for stock in stocks:
                        code = stock['code']
                        kline = kline_map.get(code)
                        if not kline or len(kline.get('close', [])) < 20:
                            continue

                        # K线形态信号
                        kline_signals = kline_scanner.scan(kline)
                        # 指标信号
                        indicator_signals = indicator_scanner.scan_all(kline)
                        # 主升启动信号
                        main_trend_signal = main_trend_scanner.scan(kline)

                        all_signals = []
                        if kline_signals:
                            all_signals.extend([s['name'] for s in kline_signals])
                        if indicator_signals:
                            all_signals.extend([s['name'] for s in indicator_signals])
                        if main_trend_signal:
                            all_signals.append(main_trend_signal['name'])

                        stock['signals'] = all_signals[:3]  # 最多显示3个信号

                        # 趋势判断（基于均线）
                        closes = kline.get('close', [])
                        if len(closes) >= 20:
                            ma5 = sum(closes[-5:]) / 5
                            ma10 = sum(closes[-10:]) / 10
                            ma20 = sum(closes[-20:]) / 20
                            current = closes[-1]

                            if current > ma5 > ma10 > ma20:
                                stock['trend'] = '强势'
                            elif current < ma5 < ma10 < ma20:
                                stock['trend'] = '弱势'
                            else:
                                stock['trend'] = '中性'

                        # 涨停次数统计（近20个交易日）
                        limit_up_count = 0
                        recent_closes = closes[-21:] if len(closes) >= 21 else closes
                        for i in range(1, len(recent_closes)):
                            prev_close = recent_closes[i-1]
                            if prev_close > 0:
                                pct = (recent_closes[i] - prev_close) / prev_close * 100
                                # [CYB] 涨停阈值按板性：主板 9.8% / 创业板 19.8%
                                _lu_th = 19.8 if str(code).startswith(('300', '301')) else 9.8
                                if pct >= _lu_th:
                                    limit_up_count += 1
                        stock['limit_up_count'] = limit_up_count
                        # 近20日最低价（用于关键价格计算）
                        if 'low' in kline and kline['low']:
                            recent_lows = kline['low'][-20:] if len(kline['low']) >= 20 else kline['low']
                            stock['low_20d'] = min(recent_lows) if recent_lows else 0
                        else:
                            stock['low_20d'] = 0

                    print(f"[WatchlistPanel] 信号扫描完成")
                except Exception as e:
                    print(f"[WatchlistPanel] 信号扫描失败: {e}")
                    import traceback
                    traceback.print_exc()

                # 获取板块概念数据（通达信行业 + 关键词概念匹配）
                try:
                    print(f"[WatchlistPanel] 开始获取板块概念数据...")

                    # 从通达信财务信息获取行业
                    finance_list = get_finance_info_batch(codes)
                    print(f"[WatchlistPanel] finance_list类型: {type(finance_list)}")
                    print(f"[WatchlistPanel] finance_list内容: {finance_list}")

                    # 兼容多种返回格式
                    finance_map = {}
                    if isinstance(finance_list, list):
                        # 列表格式：[{"code":"xxx", "industry_name":"xxx", ...}]
                        for f in finance_list:
                            if isinstance(f, dict) and 'code' in f:
                                finance_map[f['code']] = f
                            elif isinstance(f, dict) and len(f) > 0:
                                # 可能是其他格式，尝试第一个key作为code
                                first_key = list(f.keys())[0]
                                if isinstance(f[first_key], dict):
                                    finance_map[first_key] = f[first_key]
                    elif isinstance(finance_list, dict):
                        # 字典格式：{"code": {"industry_name":"xxx", ...}}
                        for code, f in finance_list.items():
                            if isinstance(f, dict):
                                finance_map[code] = f
                            else:
                                finance_map[code] = {'industry_name': f}

                    print(f"[WatchlistPanel] 解析到 {len(finance_map)} 条财务数据")

                    # V2.7.2：加载全量行业映射表（最高优先级，替代通达信错误行业）
                    industry_full_map = {}
                    try:
                        import json as _json
                        import os as _os
                        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if 'os' in dir() else r'D:\QuantMonitorV6'
                        map_path = _os.path.join(_project_root, 'data', 'cache', 'industry_full_map.json')
                        if _os.path.exists(map_path):
                            with open(map_path, 'r', encoding='utf-8') as f:
                                industry_full_map = _json.load(f)
                            print(f"[WatchlistPanel] 全量行业映射表加载: {len(industry_full_map)}条")
                        else:
                            print(f"[WatchlistPanel] 全量行业映射表不存在: {map_path}")
                    except Exception as e:
                        print(f"[WatchlistPanel] 全量行业映射表加载失败: {e}")
                        import traceback
                        traceback.print_exc()

                    # 概念关键词映射（常用概念）
                    concept_keywords = {
                        '人工智能': ['AI', '智能', '算法', '大模型', '算力', '机器人'],
                        '芯片': ['芯片', '半导体', '集成电路', '晶圆', '光刻'],
                        '新能源': ['新能源', '光伏', '锂电', '储能', '电池'],
                        '汽车': ['汽车', '整车', '零部件', '汽配', '车'],
                        '医药': ['医药', '生物', '制药', '医疗', '药'],
                        '消费': ['消费', '食品', '饮料', '零售', '酒'],
                        '金融': ['银行', '证券', '保险', '金融'],
                        '地产': ['地产', '房地产', '物业'],
                        '军工': ['军工', '航天', '航空', '国防'],
                        '环保': ['环保', '生态', '环境', '治理'],
                    }

                    for stock in stocks:
                        code = stock['code']
                        name = stock['name']

                        # V2.7.2：行业优先级：全量映射表 > 通达信财务行业 > '--'
                        industry = '--'
                        if code in industry_full_map and industry_full_map[code]:
                            industry = industry_full_map[code]
                            source = '全量映射表'
                        else:
                            finance = finance_map.get(code, {})
                            tdx_industry = finance.get('industry_name', '')
                            if tdx_industry and tdx_industry != '':
                                industry = tdx_industry
                                source = '通达信财务'
                            else:
                                source = '默认'

                        stock['industry'] = industry
                        # sector：所属板块（统一使用标准化行业）
                        stock['sector'] = industry

                        if source != '全量映射表':
                            print(f"[WatchlistPanel] 行业: {name}({code}) = {industry} (来源:{source})")

                    print(f"[WatchlistPanel] 行业数据获取完成（全量映射表优先）")

                    # 概念板块（真实数据，东方财富核心题材）
                    try:
                        print(f"[WatchlistPanel] 开始获取概念数据...")
                        from service.concept_service import get_stock_concepts, get_stock_industry_f10

                        for stock in stocks:
                            code = stock['code']
                            try:
                                # 获取F10行业（更准确）
                                f10_industry = get_stock_industry_f10(code)
                                if f10_industry and f10_industry != '--':
                                    stock['sector'] = f10_industry

                                # 获取概念（高质量）
                                concepts, source = get_stock_concepts(code)
                                stock['concept_source'] = source
                                if concepts and len(concepts) > 0:
                                    stock['concept'] = concepts
                                else:
                                    if source == '接口异常':
                                        stock['concept'] = '概念接口异常'
                                    else:
                                        stock['concept'] = '--'
                            except Exception as e:
                                print(f"[WatchlistPanel] 获取{code}概念失败: {e}")
                                stock['concept'] = '概念接口异常'
                                stock['concept_source'] = '异常'

                        print(f"[WatchlistPanel] 概念数据获取完成")
                    except Exception as e:
                        print(f"[WatchlistPanel] 概念数据获取失败: {e}")
                        import traceback
                        traceback.print_exc()
                        # 失败则显示接口异常
                        for stock in stocks:
                            if 'concept' not in stock:
                                stock['concept'] = '概念接口异常'
                                stock['concept_source'] = '异常'

                    print(f"[WatchlistPanel] 板块概念数据获取完成")

                    # ========== 核心题材计算（暂时禁用，待稳定后再开启） ==========
                    # try:
                    #     print(f"[WatchlistPanel] 开始计算核心题材...")
                    #     from strategy.theme_analyzer import analyze_stock_themes
                    #
                    #     for stock in stocks:
                    #         code = stock['code']
                    #         name = stock['name']
                    #         concept = stock.get('concept', [])
                    #         pct_chg = stock.get('pct_chg', 0)
                    #         volume = stock.get('volume', 0)
                    #
                    #         # 计算量比（简化版）
                    #         volume_ratio = 1.0
                    #
                    #         # 确保concept是列表
                    #         if not isinstance(concept, list):
                    #             concept = []
                    #
                    #         # 分析题材
                    #         result = analyze_stock_themes(code, name, concept, pct_chg, volume_ratio)
                    #
                    #         stock['core_themes'] = result['core_themes']
                    #         stock['theme_score'] = result['theme_score']
                    #         stock['theme_level'] = result['theme_level']
                    #         stock['linkage_type'] = result['linkage_type']
                    #         stock['up_reason'] = result['up_reason']
                    #         stock['theme_evidence'] = result['evidence']
                    #
                    #     print(f"[WatchlistPanel] 核心题材计算完成")
                    # except Exception as e:
                    #     print(f"[WatchlistPanel] 核心题材计算失败: {e}")
                    #     import traceback
                    #     traceback.print_exc()
                    #     # 失败则设置默认值
                    #     for stock in stocks:
                    #         stock['core_themes'] = []
                    #         stock['theme_score'] = 0
                except Exception as e:
                    print(f"[WatchlistPanel] 板块概念数据获取失败: {e}")
                    import traceback
                    traceback.print_exc()

                # 计算AI评分用的概念（只包含A级和B级，置信度>=60%）
                # UI显示全部concept，AI决策只用ai_concepts，两者解耦
                try:
                    from service.concept_service import get_ai_scoring_concepts
                    
                    for stock in stocks:
                        concept_list = stock.get('concept', [])
                        sector = stock.get('sector', '')
                        name = stock.get('name', '')
                        
                        # 确保concept_list是列表
                        if not isinstance(concept_list, list):
                            concept_list = []
                        
                        # 计算AI用的概念
                        ai_concepts = get_ai_scoring_concepts(
                            concept_list,
                            business_text=sector,
                            stock_name=name
                        )
                        
                        stock['ai_concepts'] = ai_concepts
                    
                    print(f"[AI概念] 计算完成，共 {len(stocks)} 只股票")
                except Exception as e:
                    print(f"[AI概念] 计算失败: {e}")
                    import traceback
                    traceback.print_exc()
                    # 失败时降级为原始concept列表
                    for stock in stocks:
                        stock['ai_concepts'] = stock.get('concept', [])

                # V2.7.1：AI520核心策略评分（统一调用strategy/ai520_strategy.py）
                try:
                    print(f"[AI520评分] 开始计算 {len(stocks)} 只自选股的AI520相似度评分...")
                    import os
                    from strategy.ai520_strategy import get_ai520_strategy
                    import duckdb
                    ai520_strategy = get_ai520_strategy()
                    # 使用可靠的项目根目录路径（兼容后台线程）
                    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    _kline_path = os.path.join(_project_root, 'data', 'cache', 'kline_cache.duckdb')
                    print(f"[AI520评分] 项目根目录: {_project_root}")
                    print(f"[AI520评分] K线数据库: {_kline_path} (存在: {os.path.exists(_kline_path)})")
                    if not os.path.exists(_kline_path):
                        print(f"[AI520评分] ❌ K线数据库不存在，跳过AI520评分")
                        for stock in stocks:
                            stock['ai520_score'] = 0
                            stock['ai520_grade'] = 'D'
                            stock['ai520_pullback_type'] = 'NONE'
                            stock['ai520_status'] = 'DB_NOT_FOUND'
                    else:
                        kline_db = duckdb.connect(_kline_path, read_only=True)
                        _ai520_success = 0
                        _ai520_no_data = 0
                        for stock in stocks:
                            code = stock['code']
                            name = stock.get('name', '')
                            try:
                                # 从DuckDB获取K线（用TRIM兼容DuckDB code查询bug）
                                rows = kline_db.execute(f"SELECT date, open, high, low, close, volume, amount FROM kline_cache WHERE TRIM(code)='{code}' ORDER BY date").fetchall()
                                if len(rows) >= 30:
                                    kline = []
                                    for r in rows:
                                        kline.append({
                                            'date': str(r[0]), 'open': float(r[1]), 'high': float(r[2]),
                                            'low': float(r[3]), 'close': float(r[4]), 'volume': float(r[5]),
                                            'amount': float(r[6] or 0),
                                        })
                                    # 用实时价格替换最后一根K线收盘价
                                    if stock.get('price', 0) > 0:
                                        kline[-1]['close'] = stock['price']
                                    
                                    # 调用AI520核心策略评分
                                    ai520_result = ai520_strategy.score_stock(kline, {'code': code, 'name': name})
                                    stock['ai520_score'] = ai520_result.get('score', 0)
                                    stock['ai520_grade'] = ai520_result.get('grade', 'D')
                                    stock['ai520_pullback_type'] = ai520_result.get('pullback_type', 'NONE')
                                    stock['ai520_trend_score'] = ai520_result.get('trend_score', 0)
                                    stock['ai520_strength_score'] = ai520_result.get('strength_memory_score', 0)
                                    stock['ai520_moderate_score'] = ai520_result.get('moderate_rise_score', 0)
                                    stock['ai520_pullback_score'] = ai520_result.get('pullback_score', 0)
                                    stock['ai520_recovery_score'] = ai520_result.get('recovery_score', 0)
                                    stock['ai520_kdj_score'] = ai520_result.get('kdj_score', 0)
                                    stock['ai520_position_score'] = ai520_result.get('position_score', 0)
                                    stock['ai520_volume_price_score'] = ai520_result.get('volume_price_score', 0)
                                    stock['ai520_strategy_version'] = ai520_result.get('strategy_version', 'AI520-1.0')
                                    stock['ai520_status'] = ai520_result.get('status', 'OK')
                                    _ai520_success += 1
                                    print(f"[AI520评分] {code} {name}: {stock['ai520_score']:.1f}分 {stock['ai520_grade']}级 回踩{stock['ai520_pullback_type']}")
                                else:
                                    stock['ai520_score'] = 0
                                    stock['ai520_grade'] = 'D'
                                    stock['ai520_pullback_type'] = 'NONE'
                                    stock['ai520_status'] = 'INSUFFICIENT_DATA'
                                    _ai520_no_data += 1
                                    print(f"[AI520评分] {code} {name}: K线不足({len(rows)}根)，显示数据不足")
                            except Exception as e:
                                print(f"[AI520评分] {code} 评分失败: {e}")
                                import traceback
                                traceback.print_exc()
                                stock['ai520_score'] = 0
                                stock['ai520_grade'] = 'D'
                                stock['ai520_pullback_type'] = 'NONE'
                                stock['ai520_status'] = 'ERROR'
                        
                        kline_db.close()
                        print(f"[AI520评分] 完成，成功{_ai520_success}只，数据不足{_ai520_no_data}只，{sum(1 for s in stocks if s.get('ai520_score',0)>=60)}只>=60分")
                except Exception as e:
                    print(f"[AI520评分] 整体失败: {e}")
                    import traceback
                    traceback.print_exc()
                    for stock in stocks:
                        stock['ai520_score'] = 0
                        stock['ai520_grade'] = 'D'
                        stock['ai520_pullback_type'] = 'NONE'

                print(f"[WatchlistPanel] 数据准备完成，共 {len(stocks)} 只股票，发送信号")
                self.data_ready.emit(stocks)

                # 后台计算题材（异步，不影响行情显示）
                def _calc_themes():
                    try:
                        print(f"[题材分析] 开始计算 {len(stocks)} 只股票的题材...")
                        from strategy.theme_reason_analyzer import analyze_stock_theme

                        for stock in stocks:
                            code = stock['code']
                            name = stock['name']
                            concepts = stock.get('concept', [])
                            pct_chg = stock.get('pct_chg', 0)
                            sector = stock.get('sector', '')

                            # 确保concepts是列表
                            if not isinstance(concepts, list):
                                concepts = []

                            # 分析题材
                            result = analyze_stock_theme(code, name, concepts, pct_chg, sector)

                            # 保存到缓存
                            self.theme_cache[code] = result

                            # 保存到stock对象
                            stock['theme'] = result.get('core_theme', '')
                            stock['theme_status'] = result.get('theme_status', 'normal')
                            stock['theme_reason'] = result.get('up_reason', '')
                            stock['theme_evidence'] = result.get('evidence', [])

                        print(f"[题材分析] 计算完成，共 {len(stocks)} 只股票")

                        # 计算完成后，更新UI
                        self.theme_ready.emit()

                    except Exception as e:
                        print(f"[题材分析] 计算失败: {e}")
                        import traceback
                        traceback.print_exc()

                threading.Thread(target=_calc_themes, daemon=True).start()

                # 刷新持仓行情（方法不存在时跳过，不影响自选股显示）
                try:
                    if hasattr(self, '_refresh_position_quotes'):
                        self._refresh_position_quotes()
                except Exception as e:
                    print(f"[持仓刷新] 跳过: {e}")
            except Exception as e:
                print(f"刷新自选股失败: {e}")
                import traceback
                traceback.print_exc()
                # 即使失败，也尝试发送空列表，避免卡住
                try:
                    self.data_ready.emit([])
                except Exception:
                    pass
            finally:
                self._is_refreshing = False

        threading.Thread(target=_do, daemon=True).start()

    def _get_rule_based_advice(self, price, pct_chg, trend, signals):
        """
        基于规则的AI操作建议（不调用Ollama，快速计算）
        返回: (建议文本, 颜色)
        """
        signal_text = ' '.join(signals) if signals else ''

        # 买入信号关键词
        buy_signals = ['金叉', '买点', '一阳', '主升', '突破', '回踩', '吸筹', '站二十', '穿九']
        sell_signals = ['死叉', '破位', '跌破', '顶背离', '卖出', '减仓']

        has_buy = any(k in signal_text for k in buy_signals)
        has_sell = any(k in signal_text for k in sell_signals)

        # 规则1：强势+买入信号 → 可低吸
        if trend == '强势' and has_buy and pct_chg < 5:
            return '可低吸', '#f85149'  # 红色

        # 规则2：买入信号但涨幅过大 → 追高谨慎
        if has_buy and pct_chg >= 5:
            return '追高谨慎', '#ff9100'  # 橙色

        # 规则3：弱势或卖出信号 → 建议减仓
        if trend == '弱势' or has_sell:
            return '建议减仓', '#3fb950'  # 绿色

        # 规则4：跌幅较大 → 观望等待
        if pct_chg <= -3:
            return '观望等待', '#8b949e'  # 灰色

        # 规则5：中性+有信号 → 关注
        if has_buy:
            return '持续关注', '#d29922'  # 黄色

        # 默认：持有观察
        return '持有观察', '#58a6ff'  # 蓝色

    def _get_key_price_async(self, code, price):
        """
        获取关键价格（异步加载）
        优先读缓存，无缓存则显示"计算中"并后台计算
        """
        # 初始化缓存
        if not hasattr(self, '_key_price_cache'):
            self._key_price_cache = {}

        cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
        if cache_key in self._key_price_cache:
            kp = self._key_price_cache[cache_key]
            tooltip = (
                f"💰 关键价格\n"
                f"买入区域: {kp.get('buy_zone', '--')}\n"
                f"止损位: {kp.get('stop_loss', '--')}\n"
                f"压力位: {kp.get('resistance', '--')}\n"
                f"第一目标: {kp.get('target1', '--')}\n"
                f"第二目标: {kp.get('target2', '--')}\n"
                f"风险回报比: 1:{kp.get('risk_reward', 0)}"
            )
            return kp.get('buy_zone', '--'), tooltip

        # 无缓存，显示"计算中"并触发异步计算
        self._key_price_cache[cache_key] = {'buy_zone': '计算中...'}
        QTimer.singleShot(50, lambda: self._async_key_price_calc(code, price))
        return '计算中...', ''

    def _async_key_price_calc(self, code, price):
        """异步计算关键价格"""
        try:
            from utils.key_price_calculator import get_key_price_calculator
            calculator = get_key_price_calculator()
            key_price = calculator.calculate(code, price)

            cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
            self._key_price_cache[cache_key] = key_price

            # 刷新表格
            self._refresh_key_price_column()
        except Exception:
            pass

    def _refresh_key_price_column(self):
        """刷新关键价格列"""
        try:
            for row in range(self.table.rowCount()):
                code_item = self.table.item(row, 0)
                if code_item:
                    code = code_item.text()
                    cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
                    if hasattr(self, '_key_price_cache') and cache_key in self._key_price_cache:
                        kp = self._key_price_cache[cache_key]
                        item = self.table.item(row, 7)
                        if item and kp.get('buy_zone') != '计算中...':
                            item.setText(kp.get('buy_zone', '--'))
                            tooltip = (
                                f"💰 关键价格\n"
                                f"买入区域: {kp.get('buy_zone', '--')}\n"
                                f"止损位: {kp.get('stop_loss', '--')}\n"
                                f"压力位: {kp.get('resistance', '--')}\n"
                                f"第一目标: {kp.get('target1', '--')}\n"
                                f"第二目标: {kp.get('target2', '--')}\n"
                                f"风险回报比: 1:{kp.get('risk_reward', 0)}"
                            )
                            item.setToolTip(tooltip)
        except Exception:
            pass

    def _get_stock_ai_advice(self, code, name, price, pct_chg, trend, signals):
        """
        获取股票AI操作建议（Ollama分析）
        优先读缓存，无缓存则后台异步分析
        """
        # 初始化缓存
        if not hasattr(self, '_ai_advice_cache'):
            self._ai_advice_cache = {}

        # 检查缓存
        cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
        if cache_key in self._ai_advice_cache:
            return self._ai_advice_cache[cache_key]

        # 无缓存，返回默认值并触发异步分析
        default_advice = {
            'text': '分析中...',
            'color': '#d29922',
            'tooltip': 'AI正在分析中，请稍候...'
        }
        self._ai_advice_cache[cache_key] = default_advice

        # 触发异步分析
        QTimer.singleShot(100, lambda: self._async_ai_analysis(code, name, price, pct_chg, trend, signals))

        return default_advice

    def _async_ai_analysis(self, code, name, price, pct_chg, trend, signals):
        """异步AI分析"""
        try:
            from ai.ollama_client import get_ollama_client
            ollama = get_ollama_client()

            # 构建分析提示
            signal_text = ', '.join(signals[:5]) if signals else '无明显信号'
            prompt = f"""请分析以下股票并给出简短操作建议（不超过30字）：

股票：{name}({code})
当前价：{price:.2f}元
涨跌幅：{pct_chg:+.2f}%
趋势：{trend}
技术信号：{signal_text}

请直接给出操作建议，格式如：
"建议持有，关注支撑位"
"可低吸，止损设5%"
"观望，等待确认"
"""

            # 调用Ollama
            response = ollama.chat(prompt, model='qwen3:14b')

            # 解析建议
            advice_text = response.strip()[:30] if response else '观望'

            # 根据建议内容判断颜色
            if any(k in advice_text for k in ['买入', '低吸', '加仓', '可买', '积极']):
                color = '#f85149'  # 红色
            elif any(k in advice_text for k in ['卖出', '减仓', '止损', '回避', '风险']):
                color = '#3fb950'  # 绿色
            elif any(k in advice_text for k in ['持有', '观望', '等待', '关注']):
                color = '#d29922'  # 黄色
            else:
                color = '#58a6ff'  # 蓝色

            # 获取关键价格
            try:
                from utils.key_price_calculator import get_key_price_calculator
                calculator = get_key_price_calculator()
                key_price = calculator.calculate(code, price)
                tooltip = (
                    f"🤖 AI分析建议\n{advice_text}\n\n"
                    f"💰 关键价格\n"
                    f"买入区域: {key_price.get('buy_zone', '--')}\n"
                    f"止损位: {key_price.get('stop_loss', '--')}\n"
                    f"压力位: {key_price.get('resistance', '--')}\n"
                    f"第一目标: {key_price.get('target1', '--')}\n"
                    f"第二目标: {key_price.get('target2', '--')}"
                )
            except Exception:
                tooltip = f"🤖 AI分析建议\n{advice_text}"

            # 更新缓存
            cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
            self._ai_advice_cache[cache_key] = {
                'text': advice_text,
                'color': color,
                'tooltip': tooltip
            }

            # 刷新表格显示
            self._refresh_ai_advice_column()

        except Exception as e:
            # Ollama不可用时，基于规则给出建议
            if trend == '强势' and pct_chg > 0:
                advice_text = '可持有，关注压力'
                color = '#f85149'
            elif trend == '弱势':
                advice_text = '观望，等待企稳'
                color = '#3fb950'
            else:
                advice_text = '震荡，高抛低吸'
                color = '#d29922'

            cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
            self._ai_advice_cache[cache_key] = {
                'text': advice_text,
                'color': color,
                'tooltip': f"🤖 规则建议（Ollama未连接）\n{advice_text}"
            }
            self._refresh_ai_advice_column()

    def _refresh_ai_advice_column(self):
        """刷新AI操作建议列"""
        try:
            for row in range(self.table.rowCount()):
                code_item = self.table.item(row, 0)
                if code_item:
                    code = code_item.text()
                    cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
                    if hasattr(self, '_ai_advice_cache') and cache_key in self._ai_advice_cache:
                        advice = self._ai_advice_cache[cache_key]
                        item = self.table.item(row, 8)
                        if item:
                            item.setText(advice['text'])
                            item.setForeground(QBrush(QColor(advice['color'])))
                            item.setToolTip(advice['tooltip'])
        except Exception:
            pass
        """刷新持仓行情"""
        try:
            if not self.position_stocks:
                return

            codes = [s['code'] for s in self.position_stocks]
            quotes = get_realtime_quotes_tdx(codes)

            for stock in self.position_stocks:
                code = stock['code']
                if code in quotes:
                    price = quotes[code].get('price', 0)
                    stock['price'] = price
                    cost = stock['cost']
                    shares = stock['shares']
                    if cost > 0 and price > 0:
                        stock['profit'] = (price - cost) * shares
                        stock['profit_pct'] = (price - cost) / cost * 100

            # 更新UI
            QTimer.singleShot(0, self._update_position_table)
        except Exception as e:
            print(f"刷新持仓行情失败: {e}")

    def _ctrl_async(self, stocks):
        """后台给行数据补控盘度，算完用 theme_ready 信号触发重绘。

        本类继承 QWidget 且页面已有 `theme_ready -> _update_table` 连接，
        所以不新增信号；已填过 ctrl 的行下次直接跳过，不会循环重绘。
        """
        try:
            if getattr(self, '_ctrl_busy', False):
                return
            need = [x for x in (stocks or []) if x.get('ctrl') is None and x.get('code')]
            if not need:
                return
            self._ctrl_busy = True
            import threading

            def _do():
                try:
                    from services.control_profile import get_ctrl_map
                    m = get_ctrl_map([x['code'] for x in need])
                    for x in need:
                        x['ctrl'] = m.get(x['code'])
                except Exception as e:
                    print('[自选评分] 控盘度补算失败: %s' % e, flush=True)
                finally:
                    self._ctrl_busy = False
                try:
                    self.theme_ready.emit()
                except Exception:
                    pass

            threading.Thread(target=_do, daemon=True).start()
        except Exception:
            self._ctrl_busy = False

    def _update_table(self, stocks=None):
        """更新表格"""
        # 如果没有传入stocks，用self.stocks
        if stocks is None:
            stocks = self.stocks
        # 控盘度：先用已有缓存立刻填（零计算），后面 _ctrl_async 再补算缺的
        try:
            from ui.battle_widgets.base import fetch_ctrl_cached
            fetch_ctrl_cached(stocks)
        except Exception:
            pass

        print(f"[表格刷新 1/5] _update_table被调用，共 {len(stocks)} 只股票")
        self.stocks = stocks

        # ========== V2.8 模块7：组合分析面板 ==========
        # 【2026-09-24 清理 v28 死引用】原 v28.integration.analyze_portfolio 已下线，
        # 组合分析面板此前一直不更新（每次还会打印一条失败日志）。现保持原有行为不变。
        # ========== 模块7 END ==========

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(stocks))

        # 更新数据状态
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.update_time_label.setText(f'更新时间: {now}')

        # 检查行情数据是否正常
        has_price = any(s.get('price', 0) > 0 for s in stocks)
        if has_price:
            self.quote_status_label.setText('行情接口: 🟢 正常')
            self.quote_status_label.setStyleSheet('font-size: 11px; color: #3fb950;')
        else:
            self.quote_status_label.setText('行情接口: 🔴 异常')
            self.quote_status_label.setStyleSheet('font-size: 11px; color: #f85149;')

        # 检查股票资料是否正常
        has_sector = any(s.get('sector', '--') != '--' for s in stocks)
        if has_sector:
            self.info_status_label.setText('股票资料: 🟢 正常')
            self.info_status_label.setStyleSheet('font-size: 11px; color: #3fb950;')
        else:
            self.info_status_label.setText('股票资料: 🟡 加载中')
            self.info_status_label.setStyleSheet('font-size: 11px; color: #d29922;')

        for row, stock in enumerate(stocks):
            code = stock['code']
            name = stock['name']
            price = stock['price']
            pct_chg = stock['pct_chg']
            signals = stock.get('signals', [])
            trend = stock.get('trend', '--')
            limit_up_count = stock.get('limit_up_count', 0)

            # 代码
            self.table.setItem(row, 0, QTableWidgetItem(code))

            # 名称
            name_item = QTableWidgetItem(name)
            name_item.setForeground(QBrush(QColor('#1E293B')))  # V2.7.1：统一深灰蓝
            self.table.setItem(row, 1, name_item)

            # 现价
            price_item = QTableWidgetItem(f'{price:.2f}' if price > 0 else '--')
            color = '#f85149' if pct_chg >= 0 else '#3fb950'
            price_item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, 2, price_item)

            # 涨跌幅
            pct_item = QTableWidgetItem(f'{pct_chg:+.2f}%' if price > 0 else '--')
            pct_item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, 3, pct_item)
            # 涨停异动题材（从涨停原因数据库取，和选股雷达一致）
            try:
                from data.limit_up_reason_db import get_last_limit_up_reason
                code_raw = str(stock.get('code', ''))
                # 标准化code：提取纯6位数字
                import re
                code_digits = re.search(r'(\d{6})', code_raw)
                if code_digits:
                    code_clean = code_digits.group(1)
                    reason, lu_date, lbc, lu_industry = get_last_limit_up_reason(code_clean)
                    if reason:
                        tags = [t.strip() for t in reason.split('+') if t.strip()]
                        bad_tags = {'首板', '二连板', '三连板', '换手板', '一字板', 'T字板'}
                        tags = [t for t in tags if t not in bad_tags and not (t.endswith('板') and len(t) <= 3)]
                        theme_text = ' | '.join(tags) if tags else '--'
                    else:
                        theme_text = '--'
                else:
                    theme_text = '--'
            except Exception as e:
                print(f'[题材填充失败] {code_raw}: {e}', flush=True)
                theme_text = '--'

            theme_item = QTableWidgetItem(theme_text)
            theme_item.setForeground(QBrush(QColor('#dc2626')))
            theme_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, theme_item)

            # 趋势
            if trend == '强势':
                trend_text = '强势'
                trend_color = '#f85149'
            elif trend == '弱势':
                trend_text = '弱势'
                trend_color = '#3fb950'
            elif trend == '中性':
                trend_text = '中性'
                trend_color = '#16A34A'  # V2.8：绿色，确保浅色背景可见
            else:
                trend_text = '--'
                trend_color = '#64748B'  # V2.8：调亮灰色
            trend_item = QTableWidgetItem(trend_text)
            trend_item.setForeground(QBrush(QColor(trend_color)))
            self.table.setItem(row, 5, trend_item)

            # 涨停统计
            if limit_up_count > 0:
                limit_text = f'{limit_up_count}次'
                if limit_up_count >= 5:
                    limit_color = '#f85149'  # 红色，股性活跃
                elif limit_up_count >= 3:
                    limit_color = '#ff9100'  # 橙色
                elif limit_up_count >= 1:
                    limit_color = '#CA8A04'  # V2.8：深黄色，确保浅色背景可见
                else:
                    limit_color = '#64748B'  # V2.8：调亮灰色
            else:
                limit_text = '0次'
                limit_color = '#64748B'  # V2.8：调亮灰色
            limit_item = QTableWidgetItem(limit_text)
            limit_item.setForeground(QBrush(QColor(limit_color)))
            self.table.setItem(row, 6, limit_item)

            # 关键价格（基于近20日真实K线最低价计算）
            low_20d = stock.get('low_20d', 0)
            if low_20d > 0:
                buy_low = low_20d
                buy_high = low_20d * 1.04
                stop_loss = low_20d * 0.97
                buy_zone_text = f'{buy_low:.2f}~{buy_high:.2f}'
                kp_item = QTableWidgetItem(buy_zone_text)
                kp_item.setForeground(QBrush(QColor('#2563EB')))
                kp_tooltip = (
                    f"关键价格（近20日最低 {low_20d:.2f}）\n"
                    f"买入区域: {buy_low:.2f} ~ {buy_high:.2f}\n"
                    f"止损位: {stop_loss:.2f}"
                )
                kp_item.setToolTip(kp_tooltip)
            else:
                kp_item = QTableWidgetItem('--')
                kp_item.setForeground(QBrush(QColor('#64748B')))
            self.table.setItem(row, 7, kp_item)

            # AI操作建议（基于规则，V1.0.3新增，不调用Ollama）
            try:
                ai_text, ai_color = self._get_rule_based_advice(price, pct_chg, trend, signals)
                ai_item = QTableWidgetItem(ai_text)
                ai_item.setForeground(QBrush(QColor(ai_color)))
            except Exception:
                ai_item = QTableWidgetItem('--')
                ai_item.setForeground(QBrush(QColor('#64748B')))  # V2.8：调亮
            self.table.setItem(row, 8, ai_item)

            # 9 控盘（新增，后台算好后再刷一次）
            from services.control_profile import ctrl_cell, ctrl_tooltip
            _ci = stock.get('ctrl')
            _ct, _ccolor = ctrl_cell(_ci)
            ctrl_item = QTableWidgetItem(_ct)
            ctrl_item.setForeground(QBrush(QColor(_ccolor)))
            ctrl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ctrl_item.setToolTip(ctrl_tooltip(_ci))
            self.table.setItem(row, 9, ctrl_item)

            # 8维评分和策略版本列已删除（V2.7.1 UI第二轮）

        self.table.setSortingEnabled(True)
        # 控盘度：后台补算（不阻塞 UI），算完用已有的 theme_ready 信号重绘
        self._ctrl_async(stocks)

        # 保存当前选中的股票代码
        current_code = None
        if self.selected_stock:
            current_code = self.selected_stock.get('code')

        # 查找之前选中的股票
        selected_stock = None
        if current_code:
            for stock in stocks:
                if stock['code'] == current_code:
                    selected_stock = stock
                    break

        # 恢复选中状态（通过代码匹配，不受排序影响）
        if selected_stock:
            self.selected_stock = selected_stock
            print(f"[WatchlistPanel] 保持选中: {selected_stock['code']} {selected_stock['name']}")
            # 更新AI面板
            self._update_ai_panel(selected_stock)
            # 延迟恢复表格选中状态（通过代码匹配行）
            def restore_selection():
                for row in range(self.table.rowCount()):
                    code_item = self.table.item(row, 0)
                    if code_item and code_item.text() == current_code:
                        self.table.selectRow(row)
                        break
            QTimer.singleShot(100, restore_selection)
        elif stocks and len(stocks) > 0:
            first_stock = stocks[0]
            self.selected_stock = first_stock
            print(f"[WatchlistPanel] 默认选中: {first_stock['code']} {first_stock['name']}")
            # 更新AI面板
            self._update_ai_panel(first_stock)
            # 延迟加载K线，确保UI更新完成
            QTimer.singleShot(100, lambda: self._load_kline(first_stock['code'], first_stock['name']))

    def _on_stock_selected(self):
        """选中股票时触发"""
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.stocks):
            return

        # 获取排序后的实际数据
        code_item = self.table.item(current_row, 0)
        if not code_item:
            return
        code = code_item.text()

        # 从stocks中找到对应股票
        stock = None
        for s in self.stocks:
            if s['code'] == code:
                stock = s
                break

        if not stock:
            return

        self.selected_stock = stock
        # 更新盘口信息
        price = stock.get('price', 0)
        pct_chg = stock.get('pct_chg', 0)
        vol = stock.get('volume', 0)
        amount = stock.get('amount', 0)
        turnover = stock.get('turnover', 0)
        color = '#f85149' if pct_chg >= 0 else '#3fb950'
        self.order_book_bar.setText(
            f'{stock["name"]}({code}) 现价:{price:.2f} 涨跌幅:{pct_chg:+.2f}% | '
            f'成交量:{vol/10000:.1f}万手 成交额:{amount/100000000:.2f}亿 换手率:{turnover:.2f}%'
        )
        self.order_book_bar.setStyleSheet(f'background: {BG_PANEL_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 6px; padding: 6px 10px; font-size: 12px; color: {color}; font-weight: bold;')
        # 后台加载营利拆解 + 主营构成
        self._load_profit_breakdown(code, stock.get('name', ''))
        self._load_business_data(code)
        # 不自动跳转K线，只选中
        # self._load_kline(code, stock['name'])
        self._update_ai_panel(stock)

    def _update_ai_panel(self, stock):
        """更新右侧AI操作建议和关键价格面板"""
        try:
            code = stock.get('code', '')
            name = stock.get('name', '')
            price = stock.get('price', 0)
            pct_chg = stock.get('pct_chg', 0)
            trend = stock.get('trend', '--')
            signals = stock.get('signals', [])

            # 更新AI操作建议
            ai_text, ai_color = self._get_rule_based_advice(price, pct_chg, trend, signals)
            self.ai_advice_label.setText(f'{name}({code})\n{ai_text}')
            self.ai_advice_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {ai_color}; padding: 4px;')

            # 更新关键价格
            try:
                from utils.key_price_calculator import get_key_price_calculator
                calculator = get_key_price_calculator()
                key_price = calculator.calculate(code, price)

                kp_values = [
                    ('买入区域', key_price.get('buy_zone', '--')),
                    ('止损位', key_price.get('stop_loss', '--')),
                    ('压力位', key_price.get('resistance', '--')),
                    ('第一目标', key_price.get('target1', '--')),
                    ('第二目标', key_price.get('target2', '--')),
                ]
                for row, (label, value) in enumerate(kp_values):
                    value_item = self.ai_key_price_table.item(row, 1)
                    if value_item:
                        value_item.setText(str(value))
                        if '买入' in label or '目标' in label:
                            value_item.setForeground(QBrush(QColor('#f85149')))
                        elif '止损' in label:
                            value_item.setForeground(QBrush(QColor('#3fb950')))
                        else:
                            value_item.setForeground(QBrush(QColor('#d29922')))
            except Exception as e:
                print(f"[AI面板] 关键价格计算失败: {e}")

        except Exception as e:
            print(f"[AI面板] 更新失败: {e}")

    def _on_cell_clicked(self, row, col):
        """点击单元格时触发（确保一定能加载K线）"""
        print(f"[K线] 点击单元格: 行{row}, 列{col}")
        if row < 0 or row >= self.table.rowCount():
            return

        # 直接从表格获取代码
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item:
            return

        code = code_item.text()
        name = name_item.text() if name_item else code

        # 发出stock_clicked信号，联动主控制台跳转到个股分析页
        self.stock_clicked.emit(code, name)

        print(f"[K线] 准备加载: {code} {name}")
        self._load_kline(code, name)

        # 更新AI面板
        for s in self.stocks:
            if s.get('code') == code:
                self._update_ai_panel(s)
                break

    def _load_kline(self, code, name):
        """加载K线数据"""
        print(f"[股票点击] 代码: {code}, 名称: {name}")
        print(f"[请求K线] 代码: {code}")

        # 更新当前选中股票状态
        self.selected_stock = {'code': code, 'name': name}
        print(f"[状态更新] selectedStock = {self.selected_stock}")

        # 更新标题显示加载状态
        self.kline_stock_label.setText(f'{name} ({code}) 加载中...')

        # 清空公告列表
        self.announce_list.clear()
        self.announce_list.addItem('加载公告中...')

        import threading
        def _do():
            try:
                # 加载一年日K数据（约250个交易日）
                kline = get_daily_kline(code, count=500)
                data_len = len(kline.get('close', [])) if kline else 0
                print(f"[K线返回] 代码: {code}, 数据长度: {data_len}")

                # 通过信号槽在主线程更新UI
                self.kline_data_ready.emit(kline, code, name)
            except Exception as e:
                print(f"[K线错误] 代码: {code}, 错误: {e}")
                import traceback
                traceback.print_exc()

        threading.Thread(target=_do, daemon=True).start()

        # 异步加载公司公告
        print(f"[NEWS DEBUG] 股票代码: {code}, 开始加载公告和资讯")
        self._load_announcements(code, name)
        # 异步加载个股资讯
        self._load_news(code, name)
        # 异步加载资金流向
        self._load_fund_flow(code, name)
        # 异步加载业绩预告
        self._load_forecast(code, name)

    def _load_news(self, code, name):
        """加载个股资讯（通过news_manager，支持多源+缓存）"""
        print(f"[NEWS CODE] {code}")
        print(f"[NEWS DEBUG] _load_news被调用: code={code}, name={name}")
        import threading
        def _do():
            try:
                print(f"[NEWS DEBUG] 后台线程开始获取资讯: {code}")
                from news_engine.news_manager import get_news_manager
                manager = get_news_manager()
                news_list = manager.get_news(code, name)
                print(f"[NEWS DEBUG] news_manager返回: {len(news_list)} 条")

                # 通过信号槽在主线程更新UI（Qt标准方式，不能用QTimer.singleShot）
                print(f"[NEWS DEBUG] 发送news_ready信号")
                self.news_ready.emit(news_list)

            except Exception as e:
                print(f"[NEWS DEBUG] 加载失败: {e}")
                import traceback
                traceback.print_exc()
                # 失败也发信号，显示错误
                self.news_ready.emit([])

        threading.Thread(target=_do, daemon=True).start()

    def _update_news_list(self, news_list):
        """更新资讯列表"""
        print("[NEWS UI] 收到数据")
        print(f"[NEWS UI] 数据类型: {type(news_list)}")
        print(f"[NEWS UI] 数据数量: {len(news_list)}")

        for i, item in enumerate(news_list[:3]):  # 只打印前3条
            print(f"[NEWS ITEM] {i}: title={item.get('title', '')[:30]}, time={item.get('time', '')}")

        print(f"[NEWS UI] 开始写入控件")
        self.news_list.clear()

        if not news_list:
            self.news_list.addItem('暂无资讯')
            print(f"[NEWS UI] 列表为空，显示'暂无资讯'")
            print(f"[NEWS UI] 当前显示数量: {self.news_list.count()}")
            return

        for news in news_list:
            title = news.get('title', '')
            date = news.get('time', news.get('date', ''))  # 兼容time和date两个字段
            # 显示日期 + 标题，太长的截断
            display_text = f'{date}  {title}'
            if len(display_text) > 50:
                display_text = display_text[:47] + '...'
            item = QListWidgetItem(display_text)
            # 保存完整信息到item的data里
            item.setData(256, news)
            self.news_list.addItem(item)

        print(f"[NEWS UI] 当前显示数量: {self.news_list.count()}")
        print(f"[NEWS UI] 资讯显示完成")

    def _on_news_clicked(self, item):
        """点击资讯，打开详情页"""
        news = item.data(256)
        if news and news.get('url'):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(news['url']))

    def _load_announcements(self, code, name):
        """加载公司公告"""
        print(f"[ANNOUNCE DEBUG] 开始加载公告: {code}")
        import threading
        def _do():
            try:
                import requests
                # 东方财富公告接口
                url = f'http://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=10&page_index=1&ann_type=A&client_source=web&stock_list={code}'
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=3)
                data = response.json()

                announcements = []
                if data and data.get('data') and data['data'].get('list'):
                    for item in data['data']['list'][:10]:
                        title = item.get('title', '')
                        date = item.get('notice_date', '')
                        # 格式化日期
                        if len(date) >= 10:
                            date = date[:10]
                        announcements.append({
                            'title': title,
                            'date': date,
                            'url': item.get('url', ''),
                            'art_code': item.get('art_code', '')
                        })

                print(f"[ANNOUNCE DEBUG] 获取到 {len(announcements)} 条公告")
                # 通过信号槽在主线程更新UI
                self.announce_ready.emit(announcements)

            except Exception as e:
                print(f"[公告] 获取失败: {e}")
                import traceback
                traceback.print_exc()
                # 失败也发信号
                self.announce_ready.emit([])

        threading.Thread(target=_do, daemon=True).start()

    def _update_announce_list(self, announcements):
        """更新公告列表"""
        print(f"[ANNOUNCE UI] 收到数据，数量: {len(announcements)}")
        self.announce_list.clear()
        if not announcements:
            self.announce_list.addItem('暂无公告')
            print(f"[ANNOUNCE UI] 显示'暂无公告'")
            return

        for ann in announcements:
            title = ann.get('title', '')
            date = ann.get('date', '')
            # 显示日期 + 标题，太长的截断
            display_text = f'{date}  {title}'
            if len(display_text) > 50:
                display_text = display_text[:47] + '...'
            item = QListWidgetItem(display_text)
            # 保存完整信息到item的data里
            item.setData(256, ann)
            self.announce_list.addItem(item)

        print(f"[ANNOUNCE UI] 添加完成，共 {len(announcements)} 条")

    def _on_announce_clicked(self, item):
        """点击公告，打开详情页"""
        ann = item.data(256)
        if ann and ann.get('url'):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(ann['url']))

    def _load_fund_flow(self, code, name):
        """加载资金流向（东方财富数据源，V2.7.2：3次重试+备用域名）"""
        print(f"[FUND DEBUG] 开始加载资金流向: {code}")
        import threading
        def _do():
            try:
                import requests
                import time as _time

                # secid: 0=深市, 1=沪市
                if code.startswith('6'):
                    secid = f'1.{code}'
                else:
                    secid = f'0.{code}'

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://quote.eastmoney.com/',
                }

                # V2.7.2：多域名重试（主域名 + 备用域名 + 延迟域名）
                urls = [
                    f'https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
                    f'http://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
                    f'https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
                ]

                fund_data = {}
                for attempt, url in enumerate(urls):
                    try:
                        response = requests.get(url, headers=headers, timeout=5)
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('data') and data['data'].get('klines'):
                                klines = data['data']['klines']
                                if klines:
                                    latest = klines[-1].split(',')
                                    if len(latest) >= 6:
                                        fund_data = {
                                            'main_net': float(latest[1]) / 10000,
                                            'super_large': float(latest[5]) / 10000,
                                            'large': float(latest[4]) / 10000,
                                            'medium': float(latest[3]) / 10000,
                                            'small': float(latest[2]) / 10000,
                                        }
                                        print(f"[FUND DEBUG] 获取资金流向成功(第{attempt+1}次): 主力{fund_data.get('main_net', 0):.0f}万")
                                        self.fund_flow_ready.emit(fund_data)
                                        return
                            print(f"[资金流向] 第{attempt+1}次数据为空，尝试下一个域名")
                        else:
                            print(f"[资金流向] 第{attempt+1}次状态码异常: {response.status_code}")
                    except Exception as e:
                        print(f"[资金流向] 第{attempt+1}次请求失败: {e}")
                        if attempt < len(urls) - 1:
                            _time.sleep(1)

                print(f"[资金流向] 所有域名均失败，返回空数据")
                self.fund_flow_ready.emit({})

            except Exception as e:
                print(f"[资金流向] 获取失败: {e}")
                import traceback
                traceback.print_exc()
                self.fund_flow_ready.emit({})

        threading.Thread(target=_do, daemon=True).start()

    def _update_fund_flow(self, fund_data):
        """更新资金流向显示"""
        print(f"[FUND UI] 收到数据，开始更新")
        self.fund_flow_list.clear()

        if not fund_data:
            self.fund_flow_list.addItem('暂无资金流向数据')
            print(f"[FUND UI] 显示'暂无资金流向数据'")
            return

        main_net = fund_data.get('main_net', 0)
        super_large = fund_data.get('super_large', 0)
        large = fund_data.get('large', 0)
        medium = fund_data.get('medium', 0)
        small = fund_data.get('small', 0)

        # 主力净流入
        main_text = f'主力净流入: {main_net:+.0f}万'
        self.fund_flow_list.addItem(main_text)
        print(f"[FUND UI] 添加主力: {main_text}")

        # 超大单
        sl_text = f'超大单: {super_large:+.0f}万'
        self.fund_flow_list.addItem(sl_text)
        print(f"[FUND UI] 添加超大单: {sl_text}")

        # 大单
        l_text = f'大单: {large:+.0f}万'
        self.fund_flow_list.addItem(l_text)
        print(f"[FUND UI] 添加大单: {l_text}")

        # 中单
        m_text = f'中单: {medium:+.0f}万'
        self.fund_flow_list.addItem(m_text)
        print(f"[FUND UI] 添加中单: {m_text}")

        # 小单
        s_text = f'小单: {small:+.0f}万'
        self.fund_flow_list.addItem(s_text)
        print(f"[FUND UI] 添加小单: {s_text}")

        print(f"[FUND UI] 添加完成，共5条数据")

    def _load_forecast(self, code, name):
        """加载业绩预告（东方财富数据源）"""
        print(f"[FORECAST DEBUG] 开始加载业绩预告: {code}")
        import threading
        def _do():
            try:
                import requests
                # 东方财富业绩预告接口
                url = f'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_PUBLIC_OP_PREDICT&columns=ALL&filter=(SECURITY_CODE="{code}")&pageNumber=1&pageSize=10&sortColumns=NOTICE_DATE&sortTypes=-1'
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://data.eastmoney.com/'
                }
                response = requests.get(url, headers=headers, timeout=3)
                data = response.json()

                forecast_list = []
                if data and data.get('result') and data['result'].get('data'):
                    for item in data['result']['data'][:10]:
                        notice_date = item.get('NOTICE_DATE', '')[:10]  # 公告日期
                        report_date = item.get('REPORTDATE', '')[:10]  # 报告期
                        forecast_type = item.get('FORECASTTYPE', '')  # 预告类型
                        content = item.get('FORECASTCONTENT', '')  # 预告内容
                        profit_lower = item.get('FORECASTL', 0)  # 净利润下限（元）
                        profit_upper = item.get('FORECASTT', 0)  # 净利润上限（元）
                        increase_lower = item.get('INCREASEL', 0)  # 同比增长下限（%）
                        increase_upper = item.get('INCREASET', 0)  # 同比增长上限（%）

                        # 详情页URL
                        detail_url = f'https://data.eastmoney.com/bbsj/{code}/yjyg.html'

                        forecast_list.append({
                            'notice_date': notice_date,
                            'report_date': report_date,
                            'type': forecast_type,
                            'content': content,
                            'profit_lower': profit_lower,
                            'profit_upper': profit_upper,
                            'increase_lower': increase_lower,
                            'increase_upper': increase_upper,
                            'url': detail_url
                        })

                print(f"[FORECAST DEBUG] 获取到 {len(forecast_list)} 条业绩预告")
                self.forecast_ready.emit(forecast_list)

            except Exception as e:
                print(f"[业绩预告] 获取失败: {e}")
                import traceback
                traceback.print_exc()
                self.forecast_ready.emit([])

        threading.Thread(target=_do, daemon=True).start()

    def _update_forecast_list(self, forecast_list):
        """更新业绩预告列表"""
        print(f"[FORECAST UI] 更新业绩预告列表，数量: {len(forecast_list)}")
        self.forecast_list.clear()

        if not forecast_list:
            self.forecast_list.addItem('暂无业绩预告')
            return

        for forecast in forecast_list:
            forecast_type = forecast.get('type', '')
            report_date = forecast.get('report_date', '')
            profit_lower = forecast.get('profit_lower') or 0
            profit_upper = forecast.get('profit_upper') or 0
            increase_lower = forecast.get('increase_lower') or 0
            increase_upper = forecast.get('increase_upper') or 0
            notice_date = forecast.get('notice_date', '')

            # 净利润转换为万元/亿元
            if abs(profit_upper) >= 100000000:
                profit_str = f'{profit_lower/100000000:.1f}~{profit_upper/100000000:.1f}亿'
            else:
                profit_str = f'{profit_lower/10000:.0f}~{profit_upper/10000:.0f}万'

            # 显示：预告类型 + 报告期 + 净利润 + 同比
            display_text = f'[{forecast_type}] {report_date[:7]} 净利{profit_str} 同比{increase_lower:.0f}%~{increase_upper:.0f}%'
            if len(display_text) > 50:
                display_text = display_text[:47] + '...'

            item = QListWidgetItem(display_text)
            item.setToolTip(forecast.get('content', ''))  # 鼠标悬停显示完整内容
            item.setData(256, forecast)
            self.forecast_list.addItem(item)

    def _on_forecast_clicked(self, item):
        """点击业绩预告，打开详情页"""
        forecast = item.data(256)
        if forecast and forecast.get('url'):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(forecast['url']))

    def _on_kline_data_ready(self, kline, code, name):
        """K线数据就绪，在主线程更新UI"""
        print(f"[渲染K线] 代码: {code}, 名称: {name}")

        if kline and len(kline.get('close', [])) > 10:
            try:
                # 更新K线组件数据
                self.kline_chart.set_kline_data(kline, code)
                # 更新标题
                self.kline_stock_label.setText(f'{name} ({code})')
                print(f"[渲染结果] 成功")

                # AI视觉识别：检测五买等形态并在K线图显示标记
                try:
                    from ai.kline_vision import get_kline_vision
                    vision = get_kline_vision()
                    vision_signals = vision.analyze(kline)
                    if vision_signals:
                        signal_dicts = [
                            {
                                'signal_type': s.signal_type,
                                'score': s.score,
                                'date': s.date,
                                'price': s.price,
                                'reason': s.reason,
                            }
                            for s in vision_signals
                        ]
                        self.kline_chart.set_vision_signals(signal_dicts)
                        print(f"[AI视觉] 识别到{len(vision_signals)}个信号: {[s.signal_type for s in vision_signals]}")

                    # AI结构区域标记
                    structure_data = vision.get_structure_data(kline)
                    if structure_data:
                        self.kline_chart.set_vision_structure(structure_data)
                        if 'trend_stage' in structure_data:
                            print(f"[AI视觉] 走势阶段: {structure_data['trend_stage']}")
                except Exception as ve:
                    print(f"[AI视觉] 识别异常: {ve}")

                # 更新盘口信息
                self._update_quote_info(code, name, kline)
            except Exception as e:
                print(f"[渲染结果] 失败: {e}")
                import traceback
                traceback.print_exc()
                self.kline_stock_label.setText(f'{name} ({code}) 渲染失败')
        else:
            print(f"[渲染结果] 数据不足")
            self.kline_stock_label.setText(f'{name} ({code}) 数据不足')

    def _update_chanlun_analysis(self, kline):
        """更新缠论操作建议"""
        try:
            print("[缠论] 开始分析...")
            from strategy.chanlun_analyzer import get_chanlun_analyzer
            analyzer = get_chanlun_analyzer()
            result = analyzer.analyze(kline)

            print(f"[缠论] 分析完成: {result.get('suggestion', '')}")

            # 更新建议文字
            self.chanlun_suggestion.setText(result.get('suggestion', '暂无数据'))

            # 根据信号强度设置颜色
            level = result.get('level', '无')
            if level == '强':
                color = '#f85149'  # 红色
            elif level == '中':
                color = '#d29922'  # 橙色
            elif level == '弱':
                color = '#58a6ff'  # 蓝色
            else:
                color = '#8b949e'  # 灰色

            self.chanlun_suggestion.setStyleSheet(f"""
                QLabel {{
                    background: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 10px;
                    color: {color};
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)

            # 更新指标
            self.chanlun_fractal_label.setText(f'分型: {result.get("fractal_count", 0)}')
            self.chanlun_stroke_label.setText(f'笔: {result.get("stroke_count", 0)}')

            zhongshu = result.get('zhongshu')
            if zhongshu:
                self.chanlun_zhongshu_label.setText(f'中枢: {zhongshu.get("type", "")}')
            else:
                self.chanlun_zhongshu_label.setText('中枢: 无')

            self.chanlun_level_label.setText(f'信号强度: {level}')

        except Exception as e:
            print(f"[缠论] 分析失败: {e}")
            import traceback
            traceback.print_exc()
            self.chanlun_suggestion.setText('分析失败')

    def _on_kline_period_changed(self, period):
        """K线周期切换"""
        if period == self.kline_period:
            return
        
        # 更新按钮状态
        for p, btn in self.period_buttons.items():
            btn.setChecked(p == period)
        
        self.kline_period = period
        print(f"[自选股] 切换K线周期: {period}")
        
        # 如果有选中的股票，重新加载K线
        if self.selected_stock:
            code = self.selected_stock.get('code')
            name = self.selected_stock.get('name')
            if code:
                self._load_kline_for_period(code, name, period)
    
    # ========== 股票搜索功能 ==========
    
    def _load_all_stocks(self):
        """加载全市场股票列表（用于搜索）"""
        if hasattr(self, '_all_stocks') and self._all_stocks:
            return self._all_stocks
        
        try:
            from utils.stock_name_manager import get_all_stock_names
            name_to_code = get_all_stock_names()
            # 转换为 {code: name} 格式
            self._all_stocks = {}
            for name, code in name_to_code.items():
                if code not in self._all_stocks:  # 去重，保留第一个名称
                    self._all_stocks[code] = name
            print(f"[搜索] 加载全市场股票: {len(self._all_stocks)}只")
        except Exception as e:
            print(f"[搜索] 加载股票列表失败: {e}")
            import traceback
            traceback.print_exc()
            self._all_stocks = {}
        
        return self._all_stocks
    
    def _on_search_text_changed(self, text):
        """搜索框文字变化，第一次输入时加载股票数据"""
        try:
            if not self._search_data_loaded:
                # 第一次输入时，加载股票列表
                stocks = self._load_all_stocks()
                if stocks:
                    # 生成补全列表："代码 名称" 格式
                    completer_list = []
                    for code, name in stocks.items():
                        completer_list.append(f"{code}  {name}")
                    
                    from PyQt6.QtCore import QStringListModel
                    self.search_completer.setModel(QStringListModel(completer_list))
                    self._search_data_loaded = True
                    print(f"[搜索] 补全数据加载完成: {len(completer_list)}条")
        except Exception as e:
            print(f"[搜索] 加载搜索数据出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_search_completed(self, text):
        """搜索补全选中，添加到自选股"""
        print(f"[搜索] ========== 补全项被选中 ==========")
        print(f"[搜索] 选中的文本: '{text}'")
        
        try:
            # 解析代码和名称（格式："代码  名称"）
            # 先用两个空格分割，如果失败就用一个空格
            parts = text.split('  ', 1)
            if len(parts) < 2:
                parts = text.split(' ', 1)
            
            print(f"[搜索] 分割结果: {parts}")
            
            if len(parts) >= 2:
                code = parts[0].strip()
                name = parts[1].strip()
                
                print(f"[搜索] 解析结果: code={code}, name={name}")
                
                if code and name:
                    # 添加到自选股
                    from core.watchlist import get_watchlist_manager
                    manager = get_watchlist_manager()
                    result = manager.add(code, name)
                    print(f"[搜索] 添加自选股结果: {result}")
                    
                    # 清空搜索框
                    self.search_input.clear()
                    
                    # 刷新数据
                    print(f"[搜索] 开始刷新数据...")
                    self._refresh_data()
                    print(f"[搜索] 刷新数据完成")
                else:
                    print(f"[搜索] code或name为空，不添加")
            else:
                print(f"[搜索] 分割失败，无法解析代码和名称")
        except Exception as e:
            print(f"[搜索] 添加自选股出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_search_return_pressed(self):
        """回车触发：从补全列表里取第一个匹配项添加"""
        text = self.search_input.text().strip()
        if not text:
            return
        # 如果补全列表有内容，取第一个
        model = self.search_completer.model()
        if model and model.rowCount() > 0:
            first = model.index(0, 0).data()
            self._on_search_completed(first)
            return
        # 没有补全，直接把输入当代码处理
        import re
        code_match = re.search(r'(\d{6})', text)
        if code_match:
            code = code_match.group(1)
            # 找名称
            name = text.replace(code, '').strip()
            if not name:
                name = code
            from core.watchlist import get_watchlist_manager
            manager = get_watchlist_manager()
            manager.add(code, name)
            self.search_input.clear()
            self._refresh_data()

    def _load_kline_for_period(self, code, name, period):
        """加载指定周期的K线数据（后台线程）"""
        if period == 'time':
            # 分时图
            def _do_time():
                try:
                    from utils.kline_provider import get_minute_time_data
                    data = get_minute_time_data(code)
                    if data:
                        self.time_share_ready.emit(data, code, name)
                        print(f"[自选股] 分时图数据加载完成: {code}")
                except Exception as e:
                    print(f"[自选股] 加载分时图失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            import threading
            threading.Thread(target=_do_time, daemon=True).start()
            return
        
        def _do():
            try:
                from utils.kline_provider import get_kline_by_period
                count = 500 if period in ['day', 'week', 'month'] else 300
                kline = get_kline_by_period(code, count, period)
                if kline:
                    self.kline_data_ready.emit(kline, code, name)
            except Exception as e:
                print(f"[自选股] 加载{period}K线失败: {e}")
        
        import threading
        threading.Thread(target=_do, daemon=True).start()
    
    def _set_time_share_data(self, data, code, name):
        """设置分时图数据（主线程）"""
        try:
            self.kline_chart.set_time_share_data(data)
            self.kline_stock_label.setText(f'{name} ({code}) - 分时')
            print(f"[自选股] 分时图设置完成")
        except Exception as e:
            print(f"[自选股] 分时图设置失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_quote_item(self, row, col, value, color=None):
        """更新盘口表格单元格"""
        if row < self.quote_table.rowCount() and col < self.quote_table.columnCount():
            item = self.quote_table.item(row, col)
            if item:
                item.setText(value)
                if color:
                    item.setForeground(QBrush(QColor(color)))
            else:
                new_item = QTableWidgetItem(value)
                if color:
                    new_item.setForeground(QBrush(QColor(color)))
                self.quote_table.setItem(row, col, new_item)

    def _update_quote_info(self, code, name, kline):
        """更新盘口实时信息"""
        print(f"[盘口更新] 开始更新: {code} {name}")
        try:
            # 从K线数据获取最新价格
            closes = kline.get('close', [])
            opens = kline.get('open', [])
            highs = kline.get('high', [])
            lows = kline.get('low', [])
            volumes = kline.get('volume', [])

            print(f"[盘口更新] K线数据: close={len(closes)}, open={len(opens)}, high={len(highs)}, low={len(lows)}, vol={len(volumes)}")

            if len(closes) < 2:
                print(f"[盘口更新] K线数据不足")
                return

            # 优先使用实时行情价格（self.stocks来自_refresh_data的腾讯/东财实时接口），
            # K线closes[-1]仅作兜底（K线缓存可能存在陈旧未更新的当日bar）
            rt_price = 0.0
            rt_pct = 0.0
            rt_open = 0.0
            rt_high = 0.0
            rt_low = 0.0
            rt_volume = 0
            for _s in self.stocks:
                if _s.get('code') == code:
                    rt_price = float(_s.get('price', 0) or 0)
                    rt_pct = float(_s.get('pct_chg', 0) or 0)
                    rt_open = float(_s.get('open', 0) or 0)
                    rt_high = float(_s.get('high', 0) or 0)
                    rt_low = float(_s.get('low', 0) or 0)
                    rt_volume = int(_s.get('volume', 0) or 0)
                    break

            current_price = rt_price if rt_price > 0 else closes[-1]
            prev_close = closes[-2]
            open_price = rt_open if rt_open > 0 else opens[-1]
            high_price = rt_high if rt_high > 0 else highs[-1]
            low_price = rt_low if rt_low > 0 else lows[-1]
            volume = rt_volume if rt_volume > 0 else volumes[-1]

            print(f"[盘口更新] 实时价={rt_price} K线close={closes[-1]} 采用={current_price}, 昨收={prev_close}, 成交量={volume}")

            # 计算涨跌幅（优先用实时行情的pct_chg）
            if rt_price > 0 and rt_pct != 0:
                pct_chg = rt_pct
            else:
                pct_chg = (current_price - prev_close) / prev_close * 100 if prev_close > 0 else 0

            # 计算涨停跌停价
            limit_up = prev_close * 1.1
            limit_down = prev_close * 0.9

            # 更新价格显示
            self.quote_price_label.setText(f'{current_price:.2f}')
            price_color = '#f85149' if pct_chg >= 0 else '#3fb950'
            self.quote_price_label.setStyleSheet(f'font-size: 28px; font-weight: bold; color: {price_color};')

            pct_text = f'{pct_chg:+.2f}%'
            self.quote_pct_label.setText(pct_text)
            self.quote_pct_label.setStyleSheet(f'font-size: 13px; color: {price_color};')

            # 涨跌额
            change = current_price - prev_close
            change_text = f'{change:+.2f}'
            self.quote_change_label.setText(change_text)
            self.quote_change_label.setStyleSheet(f'font-size: 11px; color: {price_color};')

            print(f"[盘口更新] 价格标签已更新")

            # 计算量比（从K线数据直接计算）
            volume_ratio = 0
            volumes = kline.get('volume', [])
            if len(volumes) >= 6:
                today_vol = volumes[-1]
                avg_vol_5 = sum(volumes[-6:-1]) / 5
                if avg_vol_5 > 0:
                    volume_ratio = today_vol / avg_vol_5

            # 更新盘口表格（两列布局）
            # 第0行：今开、最高
            self._update_quote_item(0, 1, f'{open_price:.2f}')
            self._update_quote_item(0, 3, f'{high_price:.2f}')
            # 第1行：最低、昨收
            self._update_quote_item(1, 1, f'{low_price:.2f}')
            self._update_quote_item(1, 3, f'{prev_close:.2f}')
            # 第2行：涨停、跌停
            self._update_quote_item(2, 1, f'{limit_up:.2f}', '#f85149')
            self._update_quote_item(2, 3, f'{limit_down:.2f}', '#3fb950')
            # 第3行：成交量、成交额
            self._update_quote_item(3, 1, f'{volume/10000:.1f}万')

            # ========== 先同步selected_stock到最新，再使用 ==========
            amount = 0
            turnover = 0
            market_cap = 0
            float_cap = 0
            sector = '--'
            concept = '--'

            print(f"[UI显示] ========== 盘口数据最终验证 ==========")
            print(f"[UI显示] 当前股票code参数: {code}")
            print(f"[UI显示] selected_stock是否存在: {self.selected_stock is not None}")

            # 先从self.stocks中找到最新的股票对象，同步给selected_stock
            if self.selected_stock:
                current_code = self.selected_stock['code']
                for s in self.stocks:
                    if s['code'] == current_code:
                        self.selected_stock = s
                        print(f"[UI显示] 已同步selected_stock到最新对象")
                        break

            # 再使用selected_stock的数据
            if self.selected_stock:
                s = self.selected_stock
                amount = s.get('amount', 0)
                turnover = s.get('turnover', 0)
                market_cap = s.get('market_cap', 0)
                float_cap = s.get('float_cap', 0)
                sector = s.get('sector', '--')
                concept = s.get('concept', '--')
                print(f"[UI显示] selected_stock代码: {s['code']}")
                print(f"[UI显示] selected_stock名称: {s['name']}")
                print(f"[UI显示] amount: {amount}")
                print(f"[UI显示] turnover: {turnover}")
                print(f"[UI显示] market_cap: {market_cap}")
                print(f"[UI显示] float_cap: {float_cap}")
                print(f"[UI显示] sector: {sector}")
                print(f"[UI显示] concept: {concept}")
                print(f"[UI显示] 所有字段: {list(s.keys())}")
            else:
                print(f"[UI显示] selected_stock不存在！")

            print(f"[UI显示] ========== 盘口数据最终验证结束 ==========")

            # 成交额
            if amount > 0:
                if amount >= 100000000:
                    amount_text = f'{amount/100000000:.2f}亿'
                else:
                    amount_text = f'{amount/10000:.1f}万'
                self._update_quote_item(3, 3, amount_text)
            else:
                self._update_quote_item(3, 3, '--')

            # 第4行：换手率、量比
            if turnover > 0:
                self._update_quote_item(4, 1, f'{turnover:.2f}%')
            else:
                self._update_quote_item(4, 1, '--')
            self._update_quote_item(4, 3, f'{volume_ratio:.2f}')

            # 第5行：总市值、流通市值
            if market_cap > 0:
                self._update_quote_item(5, 1, f'{market_cap:.1f}亿')
            else:
                self._update_quote_item(5, 1, '--')
            if float_cap > 0:
                self._update_quote_item(5, 3, f'{float_cap:.1f}亿')
            else:
                self._update_quote_item(5, 3, '--')

            print(f"[盘口更新] 表格基本数据已更新，量比: {volume_ratio:.2f}")

            # 异步获取更多信息
            import threading
            def _do():
                try:
                    print(f"[详细数据] 开始获取: {code}")

                    # 获取实时行情
                    quotes = get_realtime_quotes_tdx([code])
                    print(f"[详细数据] 行情接口返回: {type(quotes)}, 包含{len(quotes) if quotes else 0}条")

                    amount = 0
                    current_price = 0
                    if quotes and code in quotes:
                        quote = quotes[code]
                        amount = quote.get('amount', 0)
                        current_price = quote.get('price', 0)
                        print(f"[详细数据] 成交额: {amount}, 当前价: {current_price}")
                    else:
                        print(f"[详细数据] 行情数据中没有找到代码: {code}")

                    # 获取财务信息
                    finance_data = get_finance_info_batch([code])
                    print(f"[详细数据] 财务接口返回: {type(finance_data)}, 包含{len(finance_data) if finance_data else 0}条")

                    industry = '--'
                    total_share = 0
                    float_share = 0
                    market_cap = 0
                    float_cap = 0
                    turnover = 0

                    if finance_data and code in finance_data:
                        finance = finance_data[code]
                        industry = finance.get('industry_name', '--')
                        total_share = finance.get('zongguben', 0)
                        float_share = finance.get('liutongguben', 0)

                        print(f"[详细数据] 行业: {industry}, 总股本: {total_share}, 流通股本: {float_share}")

                        # 计算总市值和流通市值（亿元）
                        if current_price > 0 and total_share > 0:
                            market_cap = current_price * total_share / 100000000
                        if current_price > 0 and float_share > 0:
                            float_cap = current_price * float_share / 100000000

                        # 计算换手率 = 成交量(股) / 流通股本(股) * 100
                        # 注意：K线数据中volume单位是股，不是手，无需再乘100
                        volume = kline.get('volume', [0])[-1] if kline else 0
                        if float_share > 0 and volume > 0:
                            turnover = volume / float_share * 100

                        print(f"[详细数据] 总市值: {market_cap:.1f}亿, 流通市值: {float_cap:.1f}亿, 换手率: {turnover:.2f}%")
                    else:
                        print(f"[详细数据] 财务数据中没有找到代码: {code}")

                    # 计算量比（已经在前面计算过了，这里再确认一下）
                    volume_ratio = 0
                    volumes = kline.get('volume', []) if kline else []
                    if len(volumes) >= 6:
                        today_vol = volumes[-1]
                        avg_vol_5 = sum(volumes[-6:-1]) / 5
                        if avg_vol_5 > 0:
                            volume_ratio = today_vol / avg_vol_5

                    print(f"[详细数据] 量比: {volume_ratio:.2f}")

                    # 通过信号槽更新UI
                    print(f"[详细数据] 准备更新UI")
                    self.quote_detail_ready.emit(amount, turnover, industry, market_cap, float_cap, volume_ratio)
                    print(f"[详细数据] 信号已发送")

                except Exception as e:
                    print(f"[详细数据] 获取失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.quote_detail_error.emit(str(e))

            threading.Thread(target=_do, daemon=True).start()

        except Exception as e:
            print(f"更新盘口信息失败: {e}")
            import traceback
            traceback.print_exc()

    def _on_quote_detail_ready(self, amount, turnover, industry, market_cap, float_cap, volume_ratio):
        """详细数据就绪，更新UI"""
        print(f"[UI更新] ========== 收到详细数据信号 ==========")
        print(f"[UI更新] 成交额: {amount}")
        print(f"[UI更新] 换手率: {turnover}")
        print(f"[UI更新] 行业: {industry}")
        print(f"[UI更新] 总市值: {market_cap}")
        print(f"[UI更新] 流通市值: {float_cap}")
        print(f"[UI更新] 量比: {volume_ratio}")
        try:
            # 更新成交额（第3行第3列）
            if amount > 0:
                if amount >= 100000000:
                    amount_text = f'{amount/100000000:.2f}亿'
                else:
                    amount_text = f'{amount/10000:.1f}万'
                self._update_quote_item(3, 3, amount_text)
                print(f"[UI更新] 成交额已更新: {amount_text}")
            else:
                print(f"[UI更新] 成交额为0，跳过")

            # 更新换手率（第4行第1列）
            if turnover > 0:
                self._update_quote_item(4, 1, f'{turnover:.2f}%')
                print(f"[UI更新] 换手率已更新: {turnover:.2f}%")
            else:
                print(f"[UI更新] 换手率为0，跳过")

            # 更新量比（第4行第3列）
            if volume_ratio > 0:
                self._update_quote_item(4, 3, f'{volume_ratio:.2f}')
                print(f"[UI更新] 量比已更新: {volume_ratio:.2f}")
            else:
                print(f"[UI更新] 量比为0，跳过")

            # 更新行业（info_industry控件已删除，行业信息在表格中显示）
            if industry and industry != '--':
                # self.info_industry.setText(f'所属行业：{industry}')
                print(f"[UI更新] 行业已更新: {industry}")
            else:
                print(f"[UI更新] 行业为空，跳过")

            # 更新总市值（第5行第1列）
            if market_cap > 0:
                self._update_quote_item(5, 1, f'{market_cap:.1f}亿')
                print(f"[UI更新] 总市值已更新: {market_cap:.1f}亿")
            else:
                print(f"[UI更新] 总市值为0，跳过")

            # 更新流通市值（第5行第3列）
            if float_cap > 0:
                self._update_quote_item(5, 3, f'{float_cap:.1f}亿')
                print(f"[UI更新] 流通市值已更新: {float_cap:.1f}亿")
            else:
                print(f"[UI更新] 流通市值为0，跳过")

            print(f"[UI更新] ========== 详细数据更新完成 ==========")
        except Exception as e:
            print(f"[UI更新] 更新失败: {e}")
            import traceback
            traceback.print_exc()

    def _on_quote_detail_error(self, error_msg):
        """详细数据获取失败"""
        print(f"[详细数据] 错误: {error_msg}")
        # 更新UI显示错误
        item = self.quote_table.item(7, 1)
        if item:
            item.setText('获取失败')
        item = self.quote_table.item(8, 1)
        if item:
            item.setText('获取失败')

    def _update_quote_detail(self, amount, turnover):
        """更新成交额和换手率（保留兼容）"""
        try:
            print(f"[实时数据请求] 成交额: {amount}, 换手率: {turnover}")

            # 成交额
            if amount > 0:
                if amount >= 100000000:
                    amount_text = f'{amount/100000000:.2f}亿'
                else:
                    amount_text = f'{amount/10000:.1f}万'
                item = self.quote_table.item(7, 1)
                if item:
                    item.setText(amount_text)
                print(f"[实时数据] 成交额更新: {amount_text}")

            # 换手率
            if turnover > 0:
                item = self.quote_table.item(8, 1)
                if item:
                    item.setText(f'{turnover:.2f}%')
                print(f"[实时数据] 换手率更新: {turnover:.2f}%")
        except Exception as e:
            print(f"更新行情详情失败: {e}")
            import traceback
            traceback.print_exc()

    def _update_finance_info(self, industry, market_cap, float_cap):
        """更新财务信息"""
        try:
            print(f"[公司资料请求] 行业: {industry}, 总市值: {market_cap}, 流通市值: {float_cap}")

            # 行业（info_industry控件已删除，行业信息在表格中显示）
            if industry and industry != '--':
                # self.info_industry.setText(f'所属行业：{industry}')
                print(f"[公司资料] 行业更新: {industry}")

            # 总市值
            if market_cap > 0:
                item = self.quote_table.item(9, 1)
                if item:
                    item.setText(f'{market_cap:.1f}亿')
                print(f"[公司资料] 总市值更新: {market_cap:.1f}亿")

            # 流通市值
            if float_cap > 0:
                item = self.quote_table.item(10, 1)
                if item:
                    item.setText(f'{float_cap:.1f}亿')
                print(f"[公司资料] 流通市值更新: {float_cap:.1f}亿")
        except Exception as e:
            print(f"更新财务信息失败: {e}")
            import traceback
            traceback.print_exc()

    def _add_position(self):
        """添加持仓"""
        code = self.position_input.text().strip()
        cost_str = self.cost_input.text().strip()
        shares_str = self.shares_input.text().strip()

        if not code:
            return

        # 简单验证
        if not code.isdigit() or len(code) != 6:
            self.position_input.setText('')
            return

        # 解析成本价和数量
        try:
            cost = float(cost_str) if cost_str else 0.0
        except ValueError:
            cost = 0.0

        try:
            shares = int(shares_str) if shares_str else 100
        except ValueError:
            shares = 100

        # 检查是否已存在
        for stock in self.position_stocks:
            if stock['code'] == code:
                self.position_input.setText('')
                self.cost_input.setText('')
                self.shares_input.setText('')
                return

        # 添加到持仓列表
        stock = {
            'code': code,
            'name': '加载中...',
            'cost': cost,
            'shares': shares,
            'price': 0,
            'profit': 0,
            'profit_pct': 0,
        }
        self.position_stocks.append(stock)

        # 清空输入
        self.position_input.setText('')
        self.cost_input.setText('')
        self.shares_input.setText('')

        # 更新表格
        self._update_position_table()

        # 异步获取名称和行情
        import threading
        def _do():
            try:
                # 获取名称
                from utils.stock_name_manager import get_all_stock_names
                names = get_all_stock_names()
                name = names.get(code, code)
                stock['name'] = name

                # 获取实时行情
                quotes = get_realtime_quotes_tdx([code])
                if code in quotes:
                    price = quotes[code].get('price', 0)
                    stock['price'] = price
                    if cost > 0:
                        stock['profit'] = (price - cost) * shares
                        stock['profit_pct'] = (price - cost) / cost * 100

                QTimer.singleShot(0, self._update_position_table)
            except Exception as e:
                print(f"获取持仓行情失败: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def _update_position_table(self):
        """更新持仓表格"""
        self.position_table.setRowCount(len(self.position_stocks))

        total_value = 0
        total_profit = 0

        for row, stock in enumerate(self.position_stocks):
            name = stock['name']
            price = stock['price']
            cost = stock['cost']
            profit = stock['profit']
            profit_pct = stock['profit_pct']
            shares = stock['shares']

            # 名称
            name_item = QTableWidgetItem(name)
            name_item.setForeground(QBrush(QColor('#1E293B')))  # V2.7.1：统一深灰蓝
            self.position_table.setItem(row, 0, name_item)

            # 现价
            price_text = f'{price:.2f}' if price > 0 else '--'
            price_item = QTableWidgetItem(price_text)
            if price > 0:
                color = '#f85149' if profit >= 0 else '#3fb950'
                price_item.setForeground(QBrush(QColor(color)))
            self.position_table.setItem(row, 1, price_item)

            # 成本
            cost_text = f'{cost:.2f}' if cost > 0 else '--'
            cost_item = QTableWidgetItem(cost_text)
            self.position_table.setItem(row, 2, cost_item)

            # 盈亏
            if cost > 0 and price > 0:
                profit_text = f'{profit:+.0f}'
                profit_item = QTableWidgetItem(profit_text)
                color = '#f85149' if profit >= 0 else '#3fb950'
                profit_item.setForeground(QBrush(QColor(color)))
                total_profit += profit
                total_value += price * shares
            else:
                profit_item = QTableWidgetItem('--')
                self.position_table.setItem(row, 3, profit_item)

            # 盈亏%
            if cost > 0 and price > 0:
                pct_text = f'{profit_pct:+.2f}%'
                pct_item = QTableWidgetItem(pct_text)
                color = '#f85149' if profit >= 0 else '#3fb950'
                pct_item.setForeground(QBrush(QColor(color)))
            else:
                pct_item = QTableWidgetItem('--')
            self.position_table.setItem(row, 4, pct_item)

            # 持仓
            shares_item = QTableWidgetItem(str(shares))
            self.position_table.setItem(row, 5, shares_item)

        # 更新汇总
        if total_value > 0:
            self.position_summary.setText(f'总市值: {total_value:.0f}  总盈亏: {total_profit:+.0f}')
        else:
            self.position_summary.setText('总市值: --  总盈亏: --')

    def _on_position_double_clicked(self, row, col):
        """双击持仓股票显示K线"""
        if row < 0 or row >= len(self.position_stocks):
            return
        stock = self.position_stocks[row]
        self.kline_stock_label.setText(f'{stock["name"]} ({stock["code"]})')
        self._load_kline(stock['code'], stock['name'])

    def _show_position_menu(self, pos):
        """持仓右键菜单"""
        current_row = self.position_table.rowAt(pos.y())
        if current_row < 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #21262d; color: #f0f6fc;
                border: 1px solid #30363d; border-radius: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #30363d; }
        """)

        action_kline = menu.addAction('📈 查看K线')
        action_kline.triggered.connect(lambda: self._on_position_double_clicked(current_row, 0))

        menu.addSeparator()

        action_remove = menu.addAction('🗑️ 删除持仓')
        action_remove.triggered.connect(lambda: self._remove_position(current_row))

        menu.exec(self.position_table.mapToGlobal(pos))

    def _remove_position(self, row):
        """删除持仓"""
        if 0 <= row < len(self.position_stocks):
            self.position_stocks.pop(row)
            self._update_position_table()

    def _show_context_menu(self, pos):
        """右键菜单"""
        current_row = self.table.rowAt(pos.y())
        if current_row < 0:
            return

        # 从表格获取代码和名称（排序后也能正确获取）
        code_item = self.table.item(current_row, 0)
        name_item = self.table.item(current_row, 1)
        if not code_item or not name_item:
            return
        code = code_item.text()
        name = name_item.text()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #21262d; color: #f0f6fc;
                border: 1px solid #30363d; border-radius: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #30363d; }
        """)

        # 查看日线图
        action_kline = menu.addAction('📈 查看日线图')
        action_kline.triggered.connect(lambda: self._open_kline(code, name))

        menu.addSeparator()

        # 移除自选
        action_remove = menu.addAction('🗑️ 移除自选')
        action_remove.triggered.connect(lambda: self._remove_stock(code))

        menu.exec(self.table.mapToGlobal(pos))

    def _on_cell_double_clicked(self, row, col):
        """双击单元格"""
        if col == 1:  # 名称列
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                self._open_kline(code_item.text(), name_item.text())
        elif col == 7:  # 操作列
            code_item = self.table.item(row, 0)
            if code_item:
                self._remove_stock(code_item.text())

    def _open_kline(self, code, name):
        """打开日线图（同花顺链接）"""
        url = f'https://stockpage.10jqka.com.cn/{code}/'
        QDesktopServices.openUrl(QUrl(url))

    def _remove_stock(self, code):
        """移除自选股"""
        self.watchlist_manager.remove(code)

    def add_signal_alert(self, signal_name, stock_code, stock_name):
        """添加信号提醒（已移除实时信号提醒区域，保留接口兼容）"""
        pass


    def _fill_biz_table(self, code6, data):
        """在主线程填充主营构成表格"""
        try:
            # 兼容新旧格式：dict格式取items，list格式直接用
            if isinstance(data, dict):
                items = data.get('items', [])
            else:
                items = data or []
            if not items:
                self.biz_table.setRowCount(1)
                empty_item = QTableWidgetItem('暂无数据')
                empty_item.setForeground(QBrush(QColor('#64748B')))
                self.biz_table.setItem(0, 0, empty_item)
                self.biz_table.setItem(0, 1, QTableWidgetItem('--'))
                self.biz_table.setItem(0, 2, QTableWidgetItem('--'))
                print(f'[经营分析] {code6} 暂无主营构成数据', flush=True)
                return

            self.biz_table.setRowCount(len(items))
            for i, item in enumerate(items):
                name = str(item.get('name', '--'))[:30]
                ratio = str(item.get('ratio', '--'))
                yoy = str(item.get('yoy', '--'))

                name_item = QTableWidgetItem(name)
                name_item.setForeground(QBrush(QColor('#1E293B')))
                name_item.setToolTip(name)
                self.biz_table.setItem(i, 0, name_item)

                ratio_item = QTableWidgetItem(ratio)
                ratio_item.setForeground(QBrush(QColor('#2563EB')))
                ratio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.biz_table.setItem(i, 1, ratio_item)

                yoy_item = QTableWidgetItem(yoy)
                if yoy.startswith('+'):
                    yoy_item.setForeground(QBrush(QColor('#f85149')))
                elif yoy.startswith('-'):
                    yoy_item.setForeground(QBrush(QColor('#3fb950')))
                else:
                    yoy_item.setForeground(QBrush(QColor('#64748B')))
                yoy_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.biz_table.setItem(i, 2, yoy_item)

            print(f'[经营分析] {code6} 主营构成{len(items)}条', flush=True)
        except Exception as e:
            print(f'[经营分析] {code6} 填充表格失败: {e}', flush=True)

    def _fill_business_breakdown(self, code6, text):
        return

    def _load_profit_breakdown(self, code, name=''):
        return

    def _load_profit_breakdown(self, code, name=''):
        """后台异步加载营利拆解：获取主营构成 -> AI生成纯文本树状图 -> 缓存 -> 信号通知"""
        import re
        code_digits = re.search(r'(\d{6})', str(code))
        if not code_digits:
            return
        code6 = code_digits.group(1)
        stock_name = name or code6

        def worker():
            try:
                from utils.main_business_service import fetch_main_business_composition
                data = fetch_main_business_composition(code6, timeout=10)
                items = data.get('items', []) if isinstance(data, dict) else []
                report_date = data.get('report_date', '') if isinstance(data, dict) else ''

                if not items:
                    self.profit_breakdown_ready.emit(code6, '')
                    return

                text = self._generate_profit_tree_text(code6, stock_name, items, report_date)
                self.profit_breakdown_ready.emit(code6, text)
            except Exception as e:
                print(f'[营利拆解] {code6} 加载失败: {e}', flush=True)
                self.profit_breakdown_ready.emit(code6, '')

        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _generate_profit_tree_text(self, code6, stock_name, items, report_date):
        """AI生成纯文本树状图营利拆解，含缓存、超时、降级"""
        import os
        import json
        from datetime import datetime

        # 报告期格式化
        period_display = ''
        if report_date:
            try:
                dt = datetime.strptime(report_date[:10], '%Y-%m-%d')
                if dt.month == 12:
                    period_display = f'{dt.year}年年报'
                elif dt.month == 6:
                    period_display = f'{dt.year}年中报'
                elif dt.month == 3:
                    period_display = f'{dt.year}年一季报'
                elif dt.month == 9:
                    period_display = f'{dt.year}年三季报'
                else:
                    period_display = f'{dt.year}年{dt.month}月'
            except Exception:
                period_display = report_date

        # 缓存路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_dir = os.path.join(project_root, 'data', 'cache', 'profit_breakdown_text')
        today = datetime.now().strftime('%Y%m%d')
        cache_file = os.path.join(cache_dir, f'{code6}_{today}.txt')

        # 1. 读缓存
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = f.read().strip()
                if cached:
                    print(f'[营利拆解] {code6} 命中AI缓存', flush=True)
                    return cached
            except Exception as e:
                print(f'[营利拆解] {code6} 缓存读取失败: {e}', flush=True)

        # 2. 构造主营构成数据文本
        biz_lines = []
        for item in items:
            bname = str(item.get('name', '--'))
            ratio_str = str(item.get('ratio', '--'))
            income_str = str(item.get('income_str', '--'))
            biz_lines.append(f'{bname}：营收{income_str}，占比{ratio_str}')
        biz_data_text = '\n'.join(biz_lines)

        # 3. AI Prompt
        prompt = f"""你是一个量化金融数据分析师，负责将财报主营构成数据转化为简洁的结构化纯文本树状图。

股票名称：{stock_name}
报告期：{period_display or '最新'}
主营构成数据：
{biz_data_text}

请按以下格式输出，不要使用Markdown表格，不要思维导图，只要纯文本树状图：
第一行：股票名称 (报告期)
后续行：使用 ├─、└─、│ 字符进行层级缩进
第一层：业务名称 (业务标签)：营收金额，占总营收百分比
第二层：产品名称：产品描述（10-20字，说明用途和特点）

业务标签根据占比和性质判断：占比>30%为核心业务，10-30%为重要业务，5-10%为稳定增长业务，1-5%为基础业务/细分领域业务，<1%为小众业务。
每个业务下至少1个细分产品，产品描述要具体。
只输出树状图文本，不要任何解释、前缀或后缀。"""

        # 4. 调用火山方舟AI
        ai_text = ''
        try:
            import requests
            config_path = os.path.join(project_root, 'config', 'ark_api_config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            api_key = cfg.get('api_key', '')
            model = cfg.get('model', 'deepseek-v4-pro-ga-260813')
            endpoint = cfg.get('endpoint', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
            timeout = cfg.get('timeout', 60)

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            }
            payload = {
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.3,
                'max_tokens': cfg.get('max_tokens', 1500),
            }
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                result = resp.json()
                ai_text = result['choices'][0]['message']['content'].strip()
                print(f'[营利拆解] {code6} AI生成成功 ({len(ai_text)}字符)', flush=True)
            else:
                print(f'[营利拆解] {code6} AI返回状态码 {resp.status_code}: {resp.text[:200]}', flush=True)
        except Exception as e:
            print(f'[营利拆解] {code6} AI调用失败: {e}', flush=True)

        # 5. 降级：AI失败时用本地数据生成简化版
        ai_success = bool(ai_text)
        if not ai_text:
            print(f'[营利拆解] {code6} 使用本地简化版', flush=True)
            ai_text = self._generate_fallback_tree(stock_name, period_display, items)

        # 6. 写缓存（仅AI成功生成时缓存，降级版不缓存以便AI恢复后自动更新）
        if ai_success:
            try:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_file, 'w', encoding='utf-8') as f:
                    f.write(ai_text)
            except Exception as e:
                print(f'[营利拆解] {code6} 缓存写入失败: {e}', flush=True)

        return ai_text

    def _generate_fallback_tree(self, stock_name, period_display, items):
        """AI失败时的降级：本地生成简化版纯文本树状图（只有业务层，无产品描述）"""
        lines = [f'{stock_name} ({period_display or "最新"})']
        n = len(items)
        for i, item in enumerate(items):
            name = str(item.get('name', '--'))
            ratio_str = str(item.get('ratio', '--'))
            income_str = str(item.get('income_str', '--'))
            ratio_val = float(item.get('ratio_val', 0) or 0)
            if ratio_val > 30:
                tag = '核心业务'
            elif ratio_val >= 10:
                tag = '重要业务'
            elif ratio_val >= 5:
                tag = '稳定增长业务'
            elif ratio_val >= 1:
                tag = '基础业务'
            else:
                tag = '小众业务'
            connector = '└─' if i == n - 1 else '├─'
            lines.append(f'{connector} {name} ({tag})：营收{income_str}，占总营收{ratio_str}')
        lines.append('')
        lines.append('（AI生成失败，显示简化版）')
        return '\n'.join(lines)

    def _load_business_data(self, code):
        """后台异步加载主营构成数据（东方财富F10 BusinessAnalysis接口）"""
        import re
        code_digits = re.search(r'(\d{6})', str(code))
        if not code_digits:
            return
        code6 = code_digits.group(1)

        def worker():
            try:
                from utils.main_business_service import fetch_main_business_composition
                data = fetch_main_business_composition(code6, timeout=10)
                self.biz_data_ready.emit(code6, data)
            except Exception as e:
                print(f'[主营构成] {code6} 加载失败: {e}', flush=True)
                self.biz_data_ready.emit(code6, {'report_date': '', 'items': []})

        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()
