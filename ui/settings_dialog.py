"""
设置对话框
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QComboBox, QCheckBox, QGroupBox, QFormLayout, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from config.settings import MARKET_DATA, TDX_SERVERS, FILTER_CONFIG, SCORING_CONFIG, SIGNAL_CONFIG


class ConnectionTestThread(QThread):
    """连接测试线程"""
    finished = pyqtSignal(bool, str, float)

    def __init__(self, provider_name: str):
        super().__init__()
        self.provider_name = provider_name

    def run(self):
        try:
            from market import get_data_provider
            provider = get_data_provider(self.provider_name)
            result = provider.test_connection()
            self.finished.emit(
                result.get('success', False),
                result.get('message', ''),
                result.get('latency', 0)
            )
        except Exception as e:
            self.finished.emit(False, str(e), 0)


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("参数设置")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)
        self._init_ui()
        self._test_thread = None

    def _init_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # ========== 行情设置 ==========
        market_tab = QWidget()
        market_layout = QVBoxLayout(market_tab)

        # 基本设置
        basic_group = QGroupBox("基本设置")
        basic_form = QFormLayout(basic_group)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(['tdx', 'eastmoney', 'tencent', 'joinquant', 'ricequant'])
        self.provider_combo.setCurrentText(MARKET_DATA.get('provider', 'tdx'))
        basic_form.addRow("行情数据源:", self.provider_combo)

        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 60)
        self.refresh_spin.setValue(MARKET_DATA.get('refresh_interval', 3))
        basic_form.addRow("刷新间隔(秒):", self.refresh_spin)

        self.auto_reconnect_check = QCheckBox("自动重连")
        self.auto_reconnect_check.setChecked(MARKET_DATA.get('auto_reconnect', True))
        basic_form.addRow("", self.auto_reconnect_check)

        market_layout.addWidget(basic_group)

        # 通达信服务器设置
        tdx_group = QGroupBox("通达信行情服务器")
        tdx_layout = QVBoxLayout(tdx_group)

        self.server_list = QListWidget()
        for host, port in TDX_SERVERS:
            item = QListWidgetItem(f"{host}:{port}")
            self.server_list.addItem(item)
        tdx_layout.addWidget(self.server_list)

        # 服务器操作按钮
        server_btn_layout = QHBoxLayout()
        self.add_server_btn = QPushButton("添加")
        self.add_server_btn.clicked.connect(self._add_server)
        server_btn_layout.addWidget(self.add_server_btn)

        self.remove_server_btn = QPushButton("删除")
        self.remove_server_btn.clicked.connect(self._remove_server)
        server_btn_layout.addWidget(self.remove_server_btn)

        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        server_btn_layout.addWidget(self.test_btn)

        tdx_layout.addLayout(server_btn_layout)

        # 连接状态
        self.conn_status_label = QLabel("状态: 未测试")
        self.conn_status_label.setStyleSheet("color: gray;")
        tdx_layout.addWidget(self.conn_status_label)

        market_layout.addWidget(tdx_group)
        market_layout.addStretch()

        tabs.addTab(market_tab, "行情设置")

        # ========== 选股设置 ==========
        filter_tab = QWidget()
        filter_layout = QFormLayout(filter_tab)

        self.min_cap_spin = QDoubleSpinBox()
        self.min_cap_spin.setRange(1, 1000)
        self.min_cap_spin.setValue(FILTER_CONFIG.get('min_market_cap', 30))
        self.min_cap_spin.setSuffix(" 亿")
        filter_layout.addRow("最小市值:", self.min_cap_spin)

        self.max_cap_spin = QDoubleSpinBox()
        self.max_cap_spin.setRange(10, 10000)
        self.max_cap_spin.setValue(FILTER_CONFIG.get('max_market_cap', 230))
        self.max_cap_spin.setSuffix(" 亿")
        filter_layout.addRow("最大市值:", self.max_cap_spin)

        self.min_price_spin = QDoubleSpinBox()
        self.min_price_spin.setRange(1, 100)
        self.min_price_spin.setValue(FILTER_CONFIG.get('min_price', 5))
        self.min_price_spin.setSuffix(" 元")
        filter_layout.addRow("最低价格:", self.min_price_spin)

        self.max_price_spin = QDoubleSpinBox()
        self.max_price_spin.setRange(2, 1000)
        self.max_price_spin.setValue(FILTER_CONFIG.get('max_price', 60))
        self.max_price_spin.setSuffix(" 元")
        filter_layout.addRow("最高价格:", self.max_price_spin)

        self.high_ratio_spin = QDoubleSpinBox()
        self.high_ratio_spin.setRange(0.3, 1.0)
        self.high_ratio_spin.setSingleStep(0.05)
        self.high_ratio_spin.setValue(FILTER_CONFIG.get('high_price_ratio', 0.70))
        filter_layout.addRow("高点比例:", self.high_ratio_spin)

        self.min_limit_up_spin = QSpinBox()
        self.min_limit_up_spin.setRange(0, 50)
        self.min_limit_up_spin.setValue(FILTER_CONFIG.get('min_limit_up_count', 3))
        filter_layout.addRow("最少涨停次数:", self.min_limit_up_spin)

        self.exclude_st_check = QCheckBox("排除ST股票")
        self.exclude_st_check.setChecked(FILTER_CONFIG.get('exclude_st', True))
        filter_layout.addRow("", self.exclude_st_check)

        tabs.addTab(filter_tab, "选股设置")

        # ========== 信号设置 ==========
        signal_tab = QWidget()
        signal_layout = QFormLayout(signal_tab)

        self.buy_threshold_spin = QSpinBox()
        self.buy_threshold_spin.setRange(60, 100)
        self.buy_threshold_spin.setValue(SIGNAL_CONFIG.get('buy_score_threshold', 90))
        signal_layout.addRow("买入评分阈值:", self.buy_threshold_spin)

        self.sell_ma_check = QCheckBox("跌破MA5卖出")
        self.sell_ma_check.setChecked(SIGNAL_CONFIG.get('sell_ma_break', True))
        signal_layout.addRow("", self.sell_ma_check)

        self.sell_macd_check = QCheckBox("MACD转弱卖出")
        self.sell_macd_check.setChecked(SIGNAL_CONFIG.get('sell_macd_weak', True))
        signal_layout.addRow("", self.sell_macd_check)

        tabs.addTab(signal_tab, "信号设置")

        layout.addWidget(tabs)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _add_server(self):
        """添加服务器"""
        from PyQt6.QtWidgets import QInputDialog
        host, ok = QInputDialog.getText(self, "添加服务器", "服务器地址 (host:port):")
        if ok and host:
            if ':' in host:
                parts = host.split(':')
                try:
                    port = int(parts[1])
                    item = QListWidgetItem(f"{parts[0]}:{port}")
                    self.server_list.addItem(item)
                except ValueError:
                    QMessageBox.warning(self, "错误", "端口号必须是数字")
            else:
                item = QListWidgetItem(f"{host}:7709")
                self.server_list.addItem(item)

    def _remove_server(self):
        """删除服务器"""
        current_row = self.server_list.currentRow()
        if current_row >= 0:
            self.server_list.takeItem(current_row)

    def _test_connection(self):
        """测试连接"""
        provider = self.provider_combo.currentText()
        self.test_btn.setEnabled(False)
        self.conn_status_label.setText("状态: 正在测试...")
        self.conn_status_label.setStyleSheet("color: orange;")

        self._test_thread = ConnectionTestThread(provider)
        self._test_thread.finished.connect(self._on_test_finished)
        self._test_thread.start()

    def _on_test_finished(self, success: bool, message: str, latency: float):
        """测试完成回调"""
        self.test_btn.setEnabled(True)
        if success:
            self.conn_status_label.setText(f"状态: 连接正常 ({latency:.1f}ms)")
            self.conn_status_label.setStyleSheet("color: green;")
            QMessageBox.information(self, "连接成功", f"{message}\n延迟: {latency:.1f}ms")
        else:
            self.conn_status_label.setText(f"状态: 连接失败")
            self.conn_status_label.setStyleSheet("color: red;")
            QMessageBox.warning(self, "连接失败", message)

    def get_settings(self):
        """获取设置值"""
        # 获取服务器列表
        servers = []
        for i in range(self.server_list.count()):
            text = self.server_list.item(i).text()
            if ':' in text:
                parts = text.split(':')
                try:
                    servers.append((parts[0], int(parts[1])))
                except ValueError:
                    pass

        return {
            'market': {
                'provider': self.provider_combo.currentText(),
                'refresh_interval': self.refresh_spin.value(),
                'auto_reconnect': self.auto_reconnect_check.isChecked(),
                'tdx_servers': servers,
            },
            'filter': {
                'min_market_cap': self.min_cap_spin.value(),
                'max_market_cap': self.max_cap_spin.value(),
                'min_price': self.min_price_spin.value(),
                'max_price': self.max_price_spin.value(),
                'high_price_ratio': self.high_ratio_spin.value(),
                'min_limit_up_count': self.min_limit_up_spin.value(),
                'exclude_st': self.exclude_st_check.isChecked(),
            },
            'signal': {
                'buy_score_threshold': self.buy_threshold_spin.value(),
                'sell_ma_break': self.sell_ma_check.isChecked(),
                'sell_macd_weak': self.sell_macd_check.isChecked(),
            }
        }
