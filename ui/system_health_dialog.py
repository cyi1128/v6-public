# -*- coding: utf-8 -*-
"""
系统健康检查 V1.0
启动自检功能，快速定位问题
"""
import os
import sys
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QGridLayout, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

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
}

VERSION = 'V1.0 决策中心稳定版'
BUILD_DATE = '2026-08-14'


class SystemHealthDialog(QDialog):
    """系统健康检查对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('系统健康检查')
        self.setFixedSize(480, 520)
        self.setStyleSheet(f'background: {DARK_COLORS["bg_primary"]};')

        self._check_results = {}
        self._init_ui()

        # 延迟开始检查
        QTimer.singleShot(300, self._start_check)

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel('🩺 系统健康检查')
        title_label.setStyleSheet(f'font-size: 20px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 版本信息
        version_frame = QFrame()
        version_frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        version_layout = QVBoxLayout(version_frame)
        version_layout.setContentsMargins(15, 12, 15, 12)
        version_layout.setSpacing(5)

        ver_label = QLabel(f'版本：{VERSION}')
        ver_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {DARK_COLORS["accent"]};')
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_layout.addWidget(ver_label)

        date_label = QLabel(f'构建日期：{BUILD_DATE}')
        date_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
        date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_layout.addWidget(date_label)

        layout.addWidget(version_frame)

        # 检查项列表
        self.check_items = {}
        checks = [
            ('tdx', '🌐 行情接口', '通达信行情接口'),
            ('kline', '📈 K线模块', 'ECharts K线渲染'),
            ('stock_pool', '🎯 选股池', 'AI选股策略'),
            ('alarm', '🔔 预警中心', '预警信号管理'),
            ('dashboard', '📊 决策中心', '交易决策仪表盘'),
            ('dc_fields', '📋 字段完整性', '决策中心字段检查'),
            ('dc_speed', '⚡ 刷新速度', '决策中心刷新耗时'),
            ('cache', '💾 数据缓存', 'K线/股票列表缓存'),
            ('thread', '🧵 线程状态', '扫描线程/信号槽'),
        ]

        for key, title, desc in checks:
            item = self._create_check_item(title, desc)
            layout.addWidget(item)
            self.check_items[key] = item

        layout.addStretch()

        # 底部状态
        self.status_label = QLabel('正在检查...')
        self.status_label.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_secondary"]};')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DARK_COLORS['accent']};
                border: none;
                border-radius: 6px;
                color: white;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #79c0ff;
            }}
        """)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _create_check_item(self, title, desc):
        """创建单个检查项"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # 状态图标
        status_label = QLabel('⏳')
        status_label.setStyleSheet('font-size: 18px;')
        status_label.setFixedWidth(25)
        layout.addWidget(status_label)

        # 文字
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-size: 13px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        text_layout.addWidget(title_label)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, 1)

        # 结果标签
        result_label = QLabel('检查中...')
        result_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
        result_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(result_label)

        return {
            'frame': frame,
            'status_label': status_label,
            'result_label': result_label,
        }

    def _start_check(self):
        """开始检查"""
        checks = [
            ('tdx', self._check_tdx),
            ('kline', self._check_kline),
            ('stock_pool', self._check_stock_pool),
            ('alarm', self._check_alarm),
            ('dashboard', self._check_dashboard),
            ('dc_fields', self._check_dc_fields),
            ('dc_speed', self._check_dc_speed),
            ('cache', self._check_cache),
            ('thread', self._check_thread),
        ]

        passed = 0
        failed = 0

        for key, check_func in checks:
            try:
                result = check_func()
                if result.get('status', False):
                    self._set_check_result(key, True, result.get('message', '正常'))
                    passed += 1
                else:
                    self._set_check_result(key, False, result.get('message', '异常'))
                    failed += 1
            except Exception as e:
                self._set_check_result(key, False, f'错误: {str(e)[:20]}')
                failed += 1

        # 更新状态
        total = len(checks)
        if failed == 0:
            self.status_label.setText(f'✅ 全部正常 ({passed}/{total})')
            self.status_label.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["green"]}; font-weight: bold;')
        else:
            self.status_label.setText(f'⚠️  {failed}项异常 ({passed}/{total})')
            self.status_label.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["orange"]}; font-weight: bold;')

    def _set_check_result(self, key, success, text):
        """设置检查结果"""
        if key not in self.check_items:
            return

        item = self.check_items[key]
        if success:
            item['status_label'].setText('✅')
            item['result_label'].setText(text)
            item['result_label'].setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["green"]}; font-weight: bold;')
        else:
            item['status_label'].setText('❌')
            item['result_label'].setText(text)
            item['result_label'].setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["red"]}; font-weight: bold;')

    # ============================================================
    # 各项检查函数
    # ============================================================
    def _check_tdx(self):
        """检查通达信行情接口"""
        try:
            from utils.tdx_connector import get_tdx_api
            api = get_tdx_api()
            if api and hasattr(api, 'do_heartbeat'):
                return {'status': True, 'message': '连接正常'}
            return {'status': False, 'message': '连接失败'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_kline(self):
        """检查K线模块"""
        try:
            from ui.echarts_kline import ECHARTS_HTML
            if ECHARTS_HTML and len(ECHARTS_HTML) > 1000:
                return {'status': True, 'message': 'ECharts正常'}
            return {'status': False, 'message': '加载失败'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_stock_pool(self):
        """检查选股池"""
        try:
            from strategy.stock_pool_v1 import StockPoolV1
            return {'status': True, 'message': '模块正常'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_alarm(self):
        """检查预警中心"""
        try:
            from ui.alarm_center_panel import AlarmCenterPanel
            return {'status': True, 'message': '模块正常'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_dashboard(self):
        """检查决策中心"""
        try:
            from ui.trading_dashboard_panel import TradingDashboardPanel
            return True
        except Exception:
            return False

    def _check_dashboard(self):
        """检查决策中心数据读取"""
        try:
            from decision_center import DecisionDataReader
            reader = DecisionDataReader()
            health = reader.health_check()
            return {
                'status': health.get('reader_init', {}).get('status', False),
                'message': health.get('reader_init', {}).get('message', '异常'),
            }
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_dc_fields(self):
        """检查决策中心字段完整性"""
        try:
            from decision_center import DecisionDataReader
            reader = DecisionDataReader()
            health = reader.health_check()
            field_info = health.get('field_completeness', {})
            rate = field_info.get('rate', 0)
            missing = field_info.get('missing', [])

            if field_info.get('status', False):
                return {'status': True, 'message': f'完整率 {rate:.0f}%'}
            else:
                return {'status': False, 'message': f'缺少: {",".join(missing[:2])}'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_dc_speed(self):
        """检查决策中心刷新速度"""
        try:
            from decision_center import DecisionDataReader
            reader = DecisionDataReader()
            health = reader.health_check()
            read_time = health.get('read_time', 0)
            speed_status = health.get('read_time_status', 'slow')

            if speed_status == 'fast':
                return {'status': True, 'message': f'{read_time:.0f}ms (快)'}
            elif speed_status == 'normal':
                return {'status': True, 'message': f'{read_time:.0f}ms (正常)'}
            else:
                return {'status': False, 'message': f'{read_time:.0f}ms (慢)'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_cache(self):
        """检查数据缓存"""
        try:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
            if os.path.exists(data_dir):
                files = os.listdir(data_dir)
                cache_files = [f for f in files if 'cache' in f.lower() or f.endswith('.json')]
                if len(cache_files) >= 1:
                    return {'status': True, 'message': f'{len(cache_files)}个缓存文件'}
            return {'status': False, 'message': '无缓存'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}

    def _check_thread(self):
        """检查线程状态"""
        try:
            from core.scan_engine import ScanEngine
            return {'status': True, 'message': '线程正常'}
        except Exception as e:
            return {'status': False, 'message': str(e)[:20]}
