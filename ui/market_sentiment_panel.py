# -*- coding: utf-8 -*-
"""
市场情绪仪表盘 V1.0
只新增展示模块，不修改已有行情、选股、实时监控逻辑
"""
import os
import sys
import time
import threading
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QPushButton, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


# 板性前缀：主板 10cm；创业板 300/301 与科创板 688/689 是 20cm。
# 原先把涨停/跌停/炸板统一按 9.8% 判：前缀 '0' 会把创业板、'6' 会把
# 科创板一起吞进主板分支，20cm 那条 elif 永远执行不到 —— 家数全错。
PLUS_PREFIXES = ('300', '301', '688', '689')


def limit_pct(code):
    """按板性返回涨停幅度阈值（%）：主板 9.8，创业板/科创板 19.8。"""
    return 19.8 if str(code or '').startswith(PLUS_PREFIXES) else 9.8


def log_error(error):
    """记录错误日志"""
    try:
        log_file = os.path.join(LOG_DIR, 'market_sentiment_error.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {error}\n')
            f.write(traceback.format_exc() + '\n')
    except Exception:
        pass


DARK_COLORS = {
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
    'purple': '#d500f9',
    'yellow': '#ffea00',
}


class MarketSentimentPanel(QWidget):
    """市场情绪仪表盘页面"""

    # 数据就绪信号
    data_ready = pyqtSignal(dict)
    # 加载状态信号
    loading_changed = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._is_loading = False
        self._data = None
        self._update_time = None

        # 自动刷新定时器
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_interval = 60000  # 60秒

        self._init_ui()
        self._init_signals()

        print("[市场情绪] 仪表盘初始化完成")

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # ========== 顶部：市场温度 ==========
        self._create_temperature_section(main_layout)

        # ========== 中间：核心指标卡片 ==========
        self._create_metrics_section(main_layout)

        # ========== 底部：市场状态分析 ==========
        self._create_analysis_section(main_layout)

        # 底部留白
        main_layout.addStretch()

        # 初始状态
        self._show_loading('等待加载市场数据...')

    def _init_signals(self):
        """初始化信号槽"""
        self.data_ready.connect(self._on_data_ready)
        self.loading_changed.connect(self._on_loading_changed)

    # ============================================================
    # UI 创建
    # ============================================================
    def _create_temperature_section(self, parent_layout):
        """创建顶部市场温度区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)

        # 标题行
        title_layout = QHBoxLayout()
        title_label = QLabel('📊 今日市场温度')
        title_label.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 更新时间
        self.update_time_label = QLabel('--')
        self.update_time_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
        title_layout.addWidget(self.update_time_label)

        layout.addLayout(title_layout)

        # 温度大数字 + 状态
        temp_layout = QHBoxLayout()
        temp_layout.setSpacing(30)

        # 温度数字
        self.temp_label = QLabel('--')
        self.temp_label.setStyleSheet(f'font-size: 72px; font-weight: bold; color: {DARK_COLORS["accent"]};')
        self.temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        temp_layout.addWidget(self.temp_label, 1)

        # 状态描述
        status_layout = QVBoxLayout()
        status_layout.setSpacing(8)

        self.status_label = QLabel('加载中...')
        self.status_label.setStyleSheet(f'font-size: 24px; font-weight: bold; color: {DARK_COLORS["text_secondary"]};')
        status_layout.addWidget(self.status_label)

        self.status_desc_label = QLabel('正在获取市场数据')
        self.status_desc_label.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_secondary"]};')
        status_layout.addWidget(self.status_desc_label)

        # 温度条
        self.temp_bar = QFrame()
        self.temp_bar.setFixedHeight(10)
        self.temp_bar.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_tertiary']};
                border-radius: 5px;
            }}
        """)
        status_layout.addWidget(self.temp_bar)

        temp_layout.addLayout(status_layout, 2)

        layout.addLayout(temp_layout)

        parent_layout.addWidget(frame)

    def _create_metrics_section(self, parent_layout):
        """创建中间核心指标卡片区域"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)

        content = QWidget()
        layout = QGridLayout(content)
        layout.setSpacing(15)

        # 6个指标卡片
        self.metric_cards = {}

        # 第一行：上涨、下跌、平盘
        self._create_metric_card(layout, 'up', '📈 上涨家数', '--', DARK_COLORS['red'], 0, 0)
        self._create_metric_card(layout, 'down', '📉 下跌家数', '--', DARK_COLORS['green'], 0, 1)
        self._create_metric_card(layout, 'flat', '➖ 平盘家数', '--', DARK_COLORS['text_secondary'], 0, 2)

        # 第二行：涨停、跌停、炸板
        self._create_metric_card(layout, 'limit_up', '🔴 涨停数量', '--', DARK_COLORS['red'], 1, 0)
        self._create_metric_card(layout, 'limit_down', '🟢 跌停数量', '--', DARK_COLORS['green'], 1, 1)
        self._create_metric_card(layout, 'broken', '💥 炸板数量', '--', DARK_COLORS['orange'], 1, 2)

        # 第三行：最高连板、上涨比例、炸板率
        self._create_metric_card(layout, 'max_board', '🏆 最高连板', '--板', DARK_COLORS['purple'], 2, 0)
        self._create_metric_card(layout, 'up_ratio', '📊 上涨比例', '--%', DARK_COLORS['accent'], 2, 1)
        self._create_metric_card(layout, 'broken_ratio', '⚠️ 炸板率', '--%', DARK_COLORS['orange'], 2, 2)

        scroll.setWidget(content)
        parent_layout.addWidget(scroll, 1)

    def _create_metric_card(self, layout, key, title, value, color, row, col):
        """创建单个指标卡片"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(15, 12, 15, 12)
        card_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_secondary"]};')
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f'font-size: 28px; font-weight: bold; color: {color};')
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        card_layout.addWidget(value_label)

        layout.addWidget(frame, row, col)
        self.metric_cards[key] = value_label

    def _create_analysis_section(self, parent_layout):
        """创建底部市场状态分析区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        title_label = QLabel('📋 市场状态分析')
        title_label.setStyleSheet(f'font-size: 15px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        layout.addWidget(title_label)

        self.analysis_label = QLabel('暂无数据')
        self.analysis_label.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_secondary"]}; line-height: 1.6;')
        self.analysis_label.setWordWrap(True)
        layout.addWidget(self.analysis_label)

        # 刷新按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.refresh_btn = QPushButton('🔄 手动刷新')
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                color: {DARK_COLORS['text_primary']};
                padding: 8px 20px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {DARK_COLORS['border']};
            }}
        """)
        self.refresh_btn.clicked.connect(self.refresh_data)
        btn_layout.addWidget(self.refresh_btn)

        layout.addLayout(btn_layout)

        parent_layout.addWidget(frame)

    # ============================================================
    # 数据加载
    # ============================================================
    def refresh_data(self):
        """手动刷新数据"""
        if self._is_loading:
            return
        self._load_data()

    def _auto_refresh(self):
        """自动刷新（交易时间内）"""
        from utils.trading_time import is_trading_time
        if is_trading_time():
            self._load_data()

    def _load_data(self):
        """加载市场数据"""
        if self._is_loading:
            print("[市场情绪] 已在加载中，忽略重复请求")
            return

        print("[市场情绪] ========== 开始加载数据 ==========")
        self._is_loading = True
        self._show_loading('正在获取市场行情数据...')

        def _do():
            try:
                print("[市场情绪] 后台线程启动，开始获取全市场行情...")
                start_time = time.time()

                # 获取全市场股票列表
                from utils.tdx_stock_list import get_stock_list_tdx, get_realtime_quotes_tdx
                stock_list = get_stock_list_tdx()
                if not stock_list:
                    print("[市场情绪] 股票列表为空")
                    self.data_ready.emit({})
                    return

                print(f"[市场情绪] 股票列表获取完成，共 {len(stock_list)} 只")

                # 批量获取实时行情（全市场）
                codes = [s['code'] for s in stock_list]
                code_name_map = {s['code']: s['name'] for s in stock_list}
                quotes = get_realtime_quotes_tdx(codes)

                fetch_time = (time.time() - start_time) * 1000
                print(f"[市场情绪] 行情获取完成，耗时 {fetch_time:.0f}ms，共 {len(quotes) if quotes else 0} 只")

                if not quotes:
                    print("[市场情绪] 行情数据为空")
                    self.data_ready.emit({})
                    return

                # 转换为统一格式
                stocks = []
                for code, q in quotes.items():
                    stocks.append({
                        'code': code,
                        'name': code_name_map.get(code, ''),
                        'price': q.get('price', 0),
                        'pct_chg': q.get('pct_chg', 0),
                        'volume': q.get('volume', 0),
                        'amount': q.get('amount', 0),
                    })

                # 计算各项指标
                print("[市场情绪] 开始计算指标...")
                data = self._calculate_metrics(stocks)
                calc_time = (time.time() - start_time) * 1000 - fetch_time
                print(f"[市场情绪] 指标计算完成，耗时 {calc_time:.0f}ms")

                print(f"[市场情绪] 数据准备完成，温度: {data.get('temp_score', 0)}，共 {len(stocks)} 只股票")
                self.data_ready.emit(data)
                print("[市场情绪] 已发送 data_ready 信号")

            except Exception as e:
                log_error(str(e))
                print(f"[市场情绪] 数据加载失败: {e}")
                import traceback
                traceback.print_exc()
                self.data_ready.emit({})

        import threading
        thread = threading.Thread(target=_do, daemon=True)
        thread.start()
        print(f"[市场情绪] 后台线程已启动: {thread.name}")

    def _calculate_metrics(self, stocks):
        """计算市场情绪指标"""
        total = len(stocks)
        up_count = 0
        down_count = 0
        flat_count = 0
        limit_up_count = 0
        limit_down_count = 0
        broken_count = 0  # 炸板（涨停后打开）
        max_board = 0
        max_board_stock = ''

        # 连板股票（简化：用涨停次数近似）
        # 注意：这里只是简化计算，真实连板需要历史数据
        # 先用涨停数量和涨幅来估算

        for stock in stocks:
            try:
                code = stock.get('code', '')
                name = stock.get('name', '')
                price = stock.get('price', 0)
                last_close = stock.get('last_close', 0)
                pct_chg = stock.get('pct_chg', 0)
                volume = stock.get('volume', 0)

                # 涨跌统计
                if pct_chg > 0.1:  # 上涨
                    up_count += 1
                elif pct_chg < -0.1:  # 下跌
                    down_count += 1
                else:  # 平盘
                    flat_count += 1

                # 涨停判断（按板性：主板 9.8%，创业板/科创板 19.8%）
                _lp = limit_pct(code)
                is_limit_up = False
                if pct_chg >= _lp:
                    limit_up_count += 1
                    is_limit_up = True

                # 跌停判断（同样按板性）
                if pct_chg <= -_lp:
                    limit_down_count += 1

                # 炸板判断（简化：涨幅在涨停线的 70%~100% 之间且有量）
                # 主板 7%~9.8%，创业板/科创板 14%~19.8%
                _brk_lo = 14.0 if _lp > 10 else 7.0
                if _brk_lo <= pct_chg < _lp and volume > 0:
                    broken_count += 1

            except Exception:
                continue

        # 上涨比例
        up_ratio = (up_count / total * 100) if total > 0 else 0

        # 炸板率
        total_limit = limit_up_count + broken_count
        broken_ratio = (broken_count / total_limit * 100) if total_limit > 0 else 0

        # 市场温度评分（0-100）
        temp_score = self._calculate_temperature(up_ratio, limit_up_count, max_board, broken_ratio)

        # 市场状态
        status, status_desc = self._get_temperature_status(temp_score)

        return {
            'total': total,
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'limit_up': limit_up_count,
            'limit_down': limit_down_count,
            'broken': broken_count,
            'max_board': max_board,
            'max_board_stock': max_board_stock,
            'up_ratio': up_ratio,
            'broken_ratio': broken_ratio,
            'temp_score': temp_score,
            'status': status,
            'status_desc': status_desc,
        }

    def _calculate_temperature(self, up_ratio, limit_up_count, max_board, broken_ratio):
        """计算市场温度评分（0-100）"""
        score = 0

        # 1. 上涨比例（40分）
        # 0%上涨=0分，100%上涨=40分
        score += min(up_ratio / 100 * 40, 40)

        # 2. 涨停数量（30分）
        # 0个涨停=0分，100个涨停=30分
        score += min(limit_up_count / 100 * 30, 30)

        # 3. 连板高度（20分）
        # 0板=0分，10板=20分
        score += min(max_board / 10 * 20, 20)

        # 4. 炸板率（10分，反向）
        # 0%炸板=10分，50%炸板=0分
        score += max(10 - broken_ratio / 50 * 10, 0)

        return int(round(score))

    def _get_temperature_status(self, score):
        """获取温度状态"""
        if score < 20:
            return '冰点', '市场极度低迷，赚钱效应极差，建议观望'
        elif score < 40:
            return '弱势', '市场情绪较弱，赚钱效应一般，谨慎操作'
        elif score < 60:
            return '震荡', '市场震荡整理，结构性机会，轻仓参与'
        elif score < 80:
            return '活跃', '市场情绪活跃，赚钱效应较好，可适度参与'
        else:
            return '高潮', '市场情绪高涨，赚钱效应强，注意追高风险'

    # ============================================================
    # UI 更新
    # ============================================================
    def _on_data_ready(self, data):
        """数据就绪，更新UI"""
        print("[市场情绪] 收到 data_ready 信号，开始更新UI")
        self._is_loading = False
        self._data = data
        self._update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if not data:
            print("[市场情绪] 数据为空，显示错误")
            self._show_error('市场数据加载失败，请检查网络连接')
            return

        try:
            # 更新温度
            temp_score = data.get('temp_score', 0)
            self.temp_label.setText(str(temp_score))

            # 温度颜色
            status = data.get('status', '')
            if status == '冰点':
                color = DARK_COLORS['green']
            elif status == '弱势':
                color = '#58a6ff'
            elif status == '震荡':
                color = DARK_COLORS['orange']
            elif status == '活跃':
                color = '#ff9100'
            else:  # 高潮
                color = DARK_COLORS['red']

            self.temp_label.setStyleSheet(f'font-size: 72px; font-weight: bold; color: {color};')
            self.status_label.setText(status)
            self.status_label.setStyleSheet(f'font-size: 24px; font-weight: bold; color: {color};')
            self.status_desc_label.setText(data.get('status_desc', ''))

            # 更新时间
            self.update_time_label.setText(f'更新时间: {self._update_time}')

            # 更新指标卡片
            self._update_metric('up', str(data.get('up_count', 0)))
            self._update_metric('down', str(data.get('down_count', 0)))
            self._update_metric('flat', str(data.get('flat_count', 0)))
            self._update_metric('limit_up', str(data.get('limit_up', 0)))
            self._update_metric('limit_down', str(data.get('limit_down', 0)))
            self._update_metric('broken', str(data.get('broken', 0)))
            self._update_metric('max_board', f"{data.get('max_board', 0)}板")
            self._update_metric('up_ratio', f"{data.get('up_ratio', 0):.1f}%")
            self._update_metric('broken_ratio', f"{data.get('broken_ratio', 0):.1f}%")

            # 更新分析
            self._update_analysis(data)

            print(f"[市场情绪] UI更新完成，温度: {temp_score}分，状态: {status}")
            print("[市场情绪] ========== 加载完成 ==========")

        except Exception as e:
            log_error(str(e))
            print(f"[市场情绪] UI更新失败: {e}")
            import traceback
            traceback.print_exc()
            self._show_error('数据更新失败')

        finally:
            # 恢复刷新按钮状态
            self.refresh_btn.setEnabled(True)
            print("[市场情绪] 刷新按钮已恢复")

    def _update_metric(self, key, value):
        """更新单个指标"""
        if key in self.metric_cards:
            self.metric_cards[key].setText(value)

    def _update_analysis(self, data):
        """更新市场状态分析"""
        up_count = data.get('up_count', 0)
        down_count = data.get('down_count', 0)
        limit_up = data.get('limit_up', 0)
        limit_down = data.get('limit_down', 0)
        broken = data.get('broken', 0)
        up_ratio = data.get('up_ratio', 0)
        status = data.get('status', '')

        analysis = f"""
• 全市场共 {data.get('total', 0)} 只股票，上涨 {up_count} 只，下跌 {down_count} 只，上涨比例 {up_ratio:.1f}%
• 涨停 {limit_up} 家，跌停 {limit_down} 家，炸板 {broken} 家，炸板率 {data.get('broken_ratio', 0):.1f}%
• 市场情绪状态：【{status}】
• 操作建议：{data.get('status_desc', '')}
        """.strip()

        self.analysis_label.setText(analysis)

    def _show_loading(self, message):
        """显示加载状态"""
        self.status_label.setText('加载中...')
        self.status_desc_label.setText(message)
        self.refresh_btn.setEnabled(False)

    def _show_error(self, message):
        """显示错误状态"""
        self.temp_label.setText('--')
        self.status_label.setText('加载失败')
        self.status_desc_label.setText(message)
        self.analysis_label.setText(message)
        self.refresh_btn.setEnabled(True)

    def _on_loading_changed(self, is_loading, message):
        """加载状态变化"""
        if is_loading:
            self._show_loading(message)
        else:
            self.refresh_btn.setEnabled(True)

    # ============================================================
    # 自动刷新控制
    # ============================================================
    def start_auto_refresh(self):
        """启动自动刷新"""
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(self._refresh_interval)
            print(f"[市场情绪] 自动刷新已启动，间隔{self._refresh_interval//1000}秒")

    def stop_auto_refresh(self):
        """停止自动刷新"""
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
            print("[市场情绪] 自动刷新已停止")

    def showEvent(self, event):
        """页面显示时启动自动刷新"""
        super().showEvent(event)
        from utils.trading_time import is_trading_time

        # 首次显示时自动加载一次（不管是不是交易时间）
        if not self._data and not self._is_loading:
            self._load_data()

        # 交易时间内启动自动刷新
        if is_trading_time():
            self.start_auto_refresh()

    def hideEvent(self, event):
        """页面隐藏时停止自动刷新"""
        super().hideEvent(event)
        self.stop_auto_refresh()
