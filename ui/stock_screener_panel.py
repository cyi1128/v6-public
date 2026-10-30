# -*- coding: utf-8 -*-
"""
股票筛选面板
可视化筛选条件，快速筛选符合条件的股票
"""
import os
import json
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QScrollArea, QGroupBox,
    QFormLayout, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE, BG_CONTAINER,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    STATUS_SUCCESS, STATUS_INFO,
)


class StockScreenerPanel(QWidget):
    """股票筛选面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_stocks = []
        self.filtered_stocks = []
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        self.setStyleSheet(f"""
            StockScreenerPanel {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)
        
        # 顶部标题
        title = QLabel('🔍 股票筛选中心')
        title.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 15px; font-weight: 700; letter-spacing: 0.2px;')
        main_layout.addWidget(title)
        
        # 内容分割：左侧筛选条件 + 右侧结果
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧筛选条件
        left_panel = self._create_filter_panel()
        splitter.addWidget(left_panel)
        
        # 右侧结果表格
        right_panel = self._create_result_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(splitter, stretch=1)
    
    def _create_filter_panel(self) -> QWidget:
        """创建筛选条件面板"""
        panel = QFrame()
        panel.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 10px;")
        panel.setMaximumWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # 基础条件
        basic_group = QGroupBox('📊 基础条件')
        basic_group.setStyleSheet(f"QGroupBox {{ color: {ACCENT_BLUE}; font-weight: 700; border: 1px solid {BORDER}; border-radius: 8px; margin-top: 8px; background: {BG_CARD}; }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {TEXT_SECONDARY}; }}")
        basic_layout = QFormLayout()
        basic_layout.setSpacing(6)
        
        # 价格区间
        self.spin_price_min = QDoubleSpinBox()
        self.spin_price_min.setRange(0, 1000)
        self.spin_price_min.setValue(5)
        self.spin_price_min.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        self.spin_price_max = QDoubleSpinBox()
        self.spin_price_max.setRange(0, 1000)
        self.spin_price_max.setValue(60)
        self.spin_price_max.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        price_layout = QHBoxLayout()
        price_layout.addWidget(self.spin_price_min)
        price_layout.addWidget(QLabel('~'))
        price_layout.addWidget(self.spin_price_max)
        basic_layout.addRow('价格区间:', price_layout)
        
        # 市值区间
        self.spin_cap_min = QDoubleSpinBox()
        self.spin_cap_min.setRange(0, 10000)
        self.spin_cap_min.setValue(30)
        self.spin_cap_min.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        self.spin_cap_max = QDoubleSpinBox()
        self.spin_cap_max.setRange(0, 10000)
        self.spin_cap_max.setValue(230)
        self.spin_cap_max.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        cap_layout = QHBoxLayout()
        cap_layout.addWidget(self.spin_cap_min)
        cap_layout.addWidget(QLabel('~'))
        cap_layout.addWidget(self.spin_cap_max)
        basic_layout.addRow('市值(亿):', cap_layout)
        
        # 换手率
        self.spin_turnover_min = QDoubleSpinBox()
        self.spin_turnover_min.setRange(0, 100)
        self.spin_turnover_min.setValue(5)
        self.spin_turnover_min.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        self.spin_turnover_max = QDoubleSpinBox()
        self.spin_turnover_max.setRange(0, 100)
        self.spin_turnover_max.setValue(20)
        self.spin_turnover_max.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        turnover_layout = QHBoxLayout()
        turnover_layout.addWidget(self.spin_turnover_min)
        turnover_layout.addWidget(QLabel('~'))
        turnover_layout.addWidget(self.spin_turnover_max)
        basic_layout.addRow('换手率(%):', turnover_layout)
        
        # 量比
        self.spin_volume_ratio_min = QDoubleSpinBox()
        self.spin_volume_ratio_min.setRange(0, 50)
        self.spin_volume_ratio_min.setValue(1.2)
        self.spin_volume_ratio_min.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;')
        basic_layout.addRow('量比>:', self.spin_volume_ratio_min)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # 技术条件
        tech_group = QGroupBox('📈 技术条件')
        tech_group.setStyleSheet(f"QGroupBox {{ color: {ACCENT_BLUE}; font-weight: 700; border: 1px solid {BORDER}; border-radius: 8px; margin-top: 8px; background: {BG_CARD}; }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {TEXT_SECONDARY}; }}")
        tech_layout = QVBoxLayout()
        tech_layout.setSpacing(4)
        
        self.check_ma_bullish = QCheckBox('MA多头排列 (MA5>MA10>MA20)')
        self.check_ma_bullish.setStyleSheet(f'color: {TEXT_PRIMARY};')
        tech_layout.addWidget(self.check_ma_bullish)
        
        self.check_macd_golden = QCheckBox('MACD金叉')
        self.check_macd_golden.setStyleSheet(f'color: {TEXT_PRIMARY};')
        tech_layout.addWidget(self.check_macd_golden)
        
        self.check_kdj_golden = QCheckBox('KDJ金叉 (J值低位)')
        self.check_kdj_golden.setStyleSheet(f'color: {TEXT_PRIMARY};')
        tech_layout.addWidget(self.check_kdj_golden)
        
        self.check_above_ma20 = QCheckBox('价格站上MA20')
        self.check_above_ma20.setStyleSheet(f'color: {TEXT_PRIMARY};')
        tech_layout.addWidget(self.check_above_ma20)
        
        self.check_limit_up_history = QCheckBox('一年内涨停≥3次')
        self.check_limit_up_history.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.check_limit_up_history.setChecked(True)
        tech_layout.addWidget(self.check_limit_up_history)
        
        self.check_high_position = QCheckBox('近8个月高位区间 (85%~130%)')
        self.check_high_position.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.check_high_position.setChecked(True)
        tech_layout.addWidget(self.check_high_position)
        
        tech_group.setLayout(tech_layout)
        layout.addWidget(tech_group)
        
        # 板块条件
        sector_group = QGroupBox('🏭 板块条件')
        sector_group.setStyleSheet(f"QGroupBox {{ color: {ACCENT_BLUE}; font-weight: 700; border: 1px solid {BORDER}; border-radius: 8px; margin-top: 8px; background: {BG_CARD}; }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {TEXT_SECONDARY}; }}")
        sector_layout = QVBoxLayout()
        sector_layout.setSpacing(4)
        
        self.check_main_board = QCheckBox('仅主板 (排除创业板/科创板)')
        self.check_main_board.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.check_main_board.setChecked(True)
        sector_layout.addWidget(self.check_main_board)
        
        self.check_not_st = QCheckBox('排除ST')
        self.check_not_st.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.check_not_st.setChecked(True)
        sector_layout.addWidget(self.check_not_st)
        
        self.combo_sector = QComboBox()
        self.combo_sector.addItem('全部行业')
        self.combo_sector.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 6px; padding: 4px;')
        sector_layout.addWidget(self.combo_sector)
        
        sector_group.setLayout(sector_layout)
        layout.addWidget(sector_group)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.btn_filter = QPushButton('🔍 开始筛选')
        self.btn_filter.setStyleSheet(f"""
            QPushButton {{ background: {STATUS_SUCCESS}; border: 1px solid {ACCENT_GREEN}; border-radius: 6px;
                color: {TEXT_PRIMARY}; padding: 8px; font-weight: 700; }}
            QPushButton:hover {{ background: {ACCENT_GREEN}; }}
        """)
        self.btn_filter.clicked.connect(self._do_filter)
        btn_layout.addWidget(self.btn_filter)
        
        self.btn_reset = QPushButton('🔄 重置')
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{ background: {BG_INTERACTIVE}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
                color: {TEXT_SECONDARY}; padding: 8px; }}
            QPushButton:hover {{ background: {BG_PANEL_ALT}; color: {TEXT_PRIMARY}; }}
        """)
        self.btn_reset.clicked.connect(self._reset_filters)
        btn_layout.addWidget(self.btn_reset)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        return panel
    
    def _create_result_panel(self) -> QWidget:
        """创建结果面板"""
        panel = QFrame()
        panel.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 10px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # 结果统计
        self.result_label = QLabel('共 0 只股票符合条件')
        self.result_label.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 13px; font-weight: 700;')
        layout.addWidget(self.result_label)
        
        # 结果表格
        self.table = QTableWidget()
        self.table.setStyleSheet(f"""
            QTableWidget {{ background: {BG_CONTAINER}; color: {TEXT_PRIMARY}; gridline-color: {BORDER};
                border: 1px solid {BORDER}; border-radius: 8px; alternate-background-color: {BG_PANEL_ALT}; }}
            QTableWidget::item {{ padding: 4px; border-bottom: 1px solid {BORDER}; }}
            QHeaderView::section {{ background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY}; padding: 6px;
                border: 1px solid {BORDER}; font-weight: 700; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); color: {TEXT_PRIMARY}; }}
        """)
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            '代码', '名称', '价格', '涨跌幅', '市值(亿)', '换手率', '量比',
            '涨停次数', '行业', '信号'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)
        
        return panel
    
    def set_stock_list(self, stocks: List[Dict]):
        """设置股票列表"""
        self.all_stocks = stocks
        self.result_label.setText(f'已加载 {len(stocks)} 只股票，点击「开始筛选」')
        
        # 更新行业列表
        industries = set()
        for s in stocks:
            ind = s.get('industry', s.get('sector', ''))
            if ind:
                industries.add(ind)
        self.combo_sector.clear()
        self.combo_sector.addItem('全部行业')
        for ind in sorted(industries):
            self.combo_sector.addItem(ind)
    
    def _do_filter(self):
        """执行筛选"""
        if not self.all_stocks:
            QMessageBox.warning(self, '提示', '请先加载股票数据')
            return
        
        self.filtered_stocks = []
        for stock in self.all_stocks:
            if self._check_stock(stock):
                self.filtered_stocks.append(stock)
        
        self._update_table()
        self.result_label.setText(f'共 {len(self.filtered_stocks)} 只股票符合条件')
    
    def _check_stock(self, stock: Dict) -> bool:
        """检查单只股票是否符合条件"""
        code = stock.get('code', '')
        name = stock.get('name', '')
        price = stock.get('price', 0)
        market_cap = stock.get('market_cap', 0)
        turnover = stock.get('turnover', 0)
        volume_ratio = stock.get('volume_ratio', stock.get('量比', 1))
        industry = stock.get('industry', stock.get('sector', ''))
        
        # 价格区间
        if not (self.spin_price_min.value() <= price <= self.spin_price_max.value()):
            return False
        
        # 市值区间
        if not (self.spin_cap_min.value() <= market_cap <= self.spin_cap_max.value()):
            return False
        
        # 换手率
        if not (self.spin_turnover_min.value() <= turnover <= self.spin_turnover_max.value()):
            return False
        
        # 量比
        if volume_ratio < self.spin_volume_ratio_min.value():
            return False
        
        # 主板
        if self.check_main_board.isChecked():
            if code.startswith('300') or code.startswith('301') or code.startswith('688'):
                return False
        
        # 非ST
        if self.check_not_st.isChecked():
            if 'ST' in name or 'st' in name:
                return False
        
        # 行业
        selected_sector = self.combo_sector.currentText()
        if selected_sector != '全部行业' and industry != selected_sector:
            return False
        
        # 涨停历史
        if self.check_limit_up_history.isChecked():
            limit_count = stock.get('limit_up_count', 0)
            if limit_count < 3:
                return False
        
        # 高位区间
        if self.check_high_position.isChecked():
            high_8m = stock.get('high_8m', 0)
            if high_8m > 0:
                ratio = price / high_8m
                if not (0.85 <= ratio <= 1.30):
                    return False
        
        # MA多头（如果有数据）
        if self.check_ma_bullish.isChecked():
            ma5 = stock.get('ma5', 0)
            ma10 = stock.get('ma10', 0)
            ma20 = stock.get('ma20', 0)
            if ma5 > 0 and ma10 > 0 and ma20 > 0:
                if not (ma5 > ma10 > ma20):
                    return False
        
        # 站上MA20
        if self.check_above_ma20.isChecked():
            ma20 = stock.get('ma20', 0)
            if ma20 > 0 and price < ma20:
                return False
        
        return True
    
    def _update_table(self):
        """更新结果表格"""
        self.table.setRowCount(0)
        for i, stock in enumerate(self.filtered_stocks):
            self.table.insertRow(i)
            
            code = stock.get('code', '')
            name = stock.get('name', '')
            price = stock.get('price', 0)
            pct_chg = stock.get('pct_chg', 0)
            market_cap = stock.get('market_cap', 0)
            turnover = stock.get('turnover', 0)
            volume_ratio = stock.get('volume_ratio', stock.get('量比', 0))
            limit_count = stock.get('limit_up_count', 0)
            industry = stock.get('industry', stock.get('sector', ''))
            signals = stock.get('signals', [])
            if isinstance(signals, list):
                signal_text = ','.join(signals[:3])
            else:
                signal_text = str(signals)
            
            items = [
                code, name, f'{price:.2f}', f'{pct_chg:+.2f}%',
                f'{market_cap:.1f}', f'{turnover:.2f}%', f'{volume_ratio:.2f}',
                str(limit_count), industry, signal_text
            ]
            
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 涨跌幅颜色
                if j == 3:
                    if pct_chg >= 0:
                        item.setForeground(QColor(ACCENT_RED))
                    else:
                        item.setForeground(QColor(ACCENT_GREEN))
                
                self.table.setItem(i, j, item)
        
        self.table.resizeColumnsToContents()
    
    def _reset_filters(self):
        """重置筛选条件"""
        self.spin_price_min.setValue(5)
        self.spin_price_max.setValue(60)
        self.spin_cap_min.setValue(30)
        self.spin_cap_max.setValue(230)
        self.spin_turnover_min.setValue(5)
        self.spin_turnover_max.setValue(20)
        self.spin_volume_ratio_min.setValue(1.2)
        self.check_ma_bullish.setChecked(False)
        self.check_macd_golden.setChecked(False)
        self.check_kdj_golden.setChecked(False)
        self.check_above_ma20.setChecked(False)
        self.check_limit_up_history.setChecked(True)
        self.check_high_position.setChecked(True)
        self.check_main_board.setChecked(True)
        self.check_not_st.setChecked(True)
        self.combo_sector.setCurrentIndex(0)
