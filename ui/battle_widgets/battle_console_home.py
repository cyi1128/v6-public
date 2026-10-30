# -*- coding: utf-8 -*-
"""
作战中控台主页面 V3.0（6模块 2x3 布局）
布局：
  顶部 8-10%：市场状态/更新时间/刷新按钮
  第一行 31%：我的自选 | 领涨题材TOP20
  第二行 31%：今日涨停 | 板块异动
  第三行 31%：机会发现 | 龙头梯队
"""
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
    QSizePolicy, QInputDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from .base import BC, L
from .watchlist_widget import WatchlistWidget
from .auction_filter_widget import AuctionFilterWidget
from .limit_up_widget import LimitUpWidget
from .atr_t_widget import AtrTWidget
from .market_rhythm_widget import MarketRhythmWidget
from .leader_ladder_widget import LeaderLadderWidget


class BattleConsoleHome(QWidget):
    """作战中控台主页面（6模块 2x3）"""

    # 聚合各子模块的"点击股票名称"信号，转发给主窗口跳转个股分析
    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 统一浅色金融主题页面背景
        self.setStyleSheet(f'QWidget{{background:{BC.BG};}}')
        self._build_ui()
        self._start_clock()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(10, 8, 10, 8)
        main.setSpacing(8)

        # ===== 顶部栏（8-10%）=====
        top_bar = QFrame()
        top_bar.setFixedHeight(30)
        top_bar.setStyleSheet(f"""
            QFrame{{background:{BC.BG_CARD};border:1px solid {BC.BORDER};border-radius:8px;}}
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(12)

        # 标题
        top_layout.addWidget(L('⚡ 清一盘', BC.TEXT_PRIMARY, 16, True))
        top_layout.addSpacing(16)

        # 市场状态指示
        self.market_status = L('● 行情正常', BC.GREEN, 11)
        top_layout.addWidget(self.market_status)
        top_layout.addSpacing(12)

        top_layout.addStretch()

        # 数据更新时间
        self.update_time_label = L('行情更新时间：--:--:--', BC.TEXT2, 11)
        top_layout.addWidget(self.update_time_label)
        top_layout.addSpacing(12)

        # 微信推送配置快捷入口（方便后期更换Webhook地址）
        self.wechat_cfg_btn = QPushButton('📡 微信配置')
        self.wechat_cfg_btn.setFixedHeight(30)
        self.wechat_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wechat_cfg_btn.setStyleSheet(f"""
            QPushButton{{background:{BC.BG_CARD};color:{BC.TEXT_PRIMARY};border:1px solid {BC.BLUE};border-radius:6px;
            padding:0 12px;font-size:12px;}}
            QPushButton:hover{{background:{BC.BLUE};color:white;}}
        """)
        self.wechat_cfg_btn.clicked.connect(self._open_wechat_config)
        top_layout.addWidget(self.wechat_cfg_btn)
        top_layout.addSpacing(8)

        # 刷新按钮
        self.refresh_btn = QPushButton('🔄 全部刷新')
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton{{background:{BC.BLUE};color:white;border:none;border-radius:6px;
            padding:0 16px;font-size:12px;font-weight:bold;}}
            QPushButton:hover{{background:#1a5ce6;}}
            QPushButton:pressed{{background:#1550c8;}}
        """)
        self.refresh_btn.clicked.connect(self._refresh_all)
        top_layout.addWidget(self.refresh_btn)

        main.addWidget(top_bar)

        # ===== 第一行（31%）：我的自选 | 集合竞价筛选 =====
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.watchlist = WatchlistWidget()
        self.auction_filter = AuctionFilterWidget()
        row1.addWidget(self._wrap_card(self.watchlist), 1)
        row1.addWidget(self._wrap_card(self.auction_filter), 1)
        main.addLayout(row1, 30)

        # ===== 第二行（31%）：今日涨停 | ATR做T助手 =====
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.limit_up = LimitUpWidget()
        self.atr_t = AtrTWidget()
        row2.addWidget(self._wrap_card(self.limit_up), 1)
        row2.addWidget(self._wrap_card(self.atr_t), 1)
        main.addLayout(row2, 30)

        # ===== 第三行（40%）：市场节奏（盘中机会 + 金铲子 + 板块异动 三合一，单列不分栏）=====
        row3 = QVBoxLayout()
        row3.setSpacing(0)
        self.market_rhythm = MarketRhythmWidget()
        row3.addWidget(self._wrap_card(self.market_rhythm), 1)
        main.addLayout(row3, 40)

        # 转发各子模块"点击股票名称"信号到本页 stock_clicked，供主窗口跳转个股分析
        # 我的自选 / 今日涨停 / 市场节奏 / 竞价模块 / 分时做T + 日K建仓
        for _w in (self.watchlist, self.limit_up, self.market_rhythm,
                   self.auction_filter, self.atr_t):
            try:
                _w.stock_clicked.connect(self.stock_clicked.emit)
            except Exception as _e:
                print(f'[作战中台] 连接{type(_w).__name__}跳转信号失败: {_e}', flush=True)

    @staticmethod
    def _wrap_card(widget):
        """将模块包裹为卡片（模块自身已有背景，这里只做间距容器）"""
        container = QFrame()
        container.setStyleSheet(f'QFrame{{background:transparent;border:none;}}')
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return container

    def _open_wechat_config(self):
        """企业微信Webhook快捷配置：读取/修改 data/wechat_config.json"""
        import os as _os, json as _json
        cfg_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))))), 'data', 'wechat_config.json')
        cur = ''
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cur = _json.load(f).get('webhook_url', '')
        except Exception:
            cur = ''
        url, ok = QInputDialog.getText(
            self, '企业微信推送配置',
            'Webhook 地址：\n（保存到 data/wechat_config.json，重启程序后生效）',
            text=cur)
        if not ok:
            return
        url = url.strip()
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                _json.dump({'webhook_url': url}, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, '已保存', f'企业微信Webhook已更新：\n{url}\n\n重启程序后生效。')
        except Exception as e:
            QMessageBox.warning(self, '保存失败', str(e))

    def _refresh_all(self):
        """手动刷新所有模块，后台线程执行不卡UI"""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText('刷新中...')
        # 用QTimer逐个触发，不阻塞主线程
        def do_refresh():
            try:
                self.watchlist.refresh()
            except Exception as e:
                print(f"[全部刷新] watchlist失败: {e}")
            try:
                self.auction_filter.refresh()
            except Exception as e:
                print(f"[全部刷新] auction_filter失败: {e}")
            try:
                self.limit_up.refresh()
            except Exception as e:
                print(f"[全部刷新] limit_up失败: {e}")
            try:
                self.atr_t.refresh()
            except Exception as e:
                print(f"[全部刷新] atr_t失败: {e}")
            try:
                self.market_rhythm.refresh(force=True)
            except Exception as e:
                print(f"[全部刷新] market_rhythm失败: {e}")
        # 放到后台线程跑，不卡UI
        import threading
        t = threading.Thread(target=do_refresh, daemon=True)
        t.start()
        QTimer.singleShot(1500, self._restore_refresh_btn)

    def _restore_refresh_btn(self):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText('🔄 全部刷新')

    def _start_clock(self):
        """启动时钟，更新顶部时间"""
        self._update_time()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_time)
        self._clock_timer.start(1000)

    def _update_time(self):
        now = datetime.now()
        self.update_time_label.setText(f'行情更新时间：{now.strftime("%H:%M:%S")}')
        # 简单判断交易时段
        h, m = now.hour, now.minute
        weekday = now.weekday()
        if weekday >= 5:
            self.market_status.setText('● 休市（周末）')
            self.market_status.setStyleSheet(f'color:{BC.TEXT3};font-size:11px;background:transparent;')
        elif (h == 9 and 30 <= m <= 59) or (h == 10) or (h == 11 and m <= 30) or \
             (h == 13) or (h == 14):
            self.market_status.setText('● 交易中')
            self.market_status.setStyleSheet(f'color:{BC.GREEN};font-size:11px;background:transparent;')
        else:
            self.market_status.setText('● 非交易时段')
            self.market_status.setStyleSheet(f'color:{BC.YELLOW};font-size:11px;background:transparent;')
