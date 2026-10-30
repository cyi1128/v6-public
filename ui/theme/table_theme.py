# -*- coding: utf-8 -*-
"""
表格主题组件
统一所有QTableWidget的样式和行为
"""

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont
from ui.theme.theme_colors import (
    BG_TABLE, BG_TABLE_ALT, BG_HEADER, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY,
    UP_COLOR, DOWN_COLOR, FLAT_COLOR,
    AI_SCORE_HIGH, AI_SCORE_MID_HIGH, AI_SCORE_MID, AI_SCORE_LOW,
    LIMIT_UP_COLOR, LIMIT_DOWN_COLOR,
    get_ai_score_color, get_change_color, format_change
)


class StyledTableWidget(QTableWidget):
    """统一样式的表格组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_style()
        self._setup_behavior()

    def _setup_style(self):
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {BG_TABLE};
                alternate-background-color: {BG_TABLE_ALT};
                gridline-color: #21262D;
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
                selection-background-color: #21262D;
                selection-color: {TEXT_PRIMARY};
                outline: none;
            }}
            QTableWidget::item {{
                padding: 6px 8px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: #21262D;
                color: {TEXT_PRIMARY};
            }}
            QTableWidget::item:hover {{
                background-color: #1C2128;
            }}
            QHeaderView::section {{
                background-color: {BG_HEADER};
                color: {TEXT_SECONDARY};
                padding: 8px 8px;
                border: none;
                border-right: 1px solid #21262D;
                border-bottom: 1px solid {BORDER_DEFAULT};
                font-weight: 600;
                font-size: 11px;
            }}
            QHeaderView::section:hover {{
                background-color: #21262D;
                color: {UP_COLOR};
            }}
        """)

    def _setup_behavior(self):
        self.setAlternatingRowColors(True)
        self.setShowGrid(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def set_columns(self, headers, widths=None):
        """设置列头和宽度"""
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        if widths:
            for i, w in enumerate(widths):
                if i < len(headers):
                    self.setColumnWidth(i, w)

    def add_row(self, values, cell_styles=None):
        """添加一行数据"""
        row = self.rowCount()
        self.insertRow(row)
        for col, val in enumerate(values):
            item = QTableWidgetItem(str(val) if val is not None else '')
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if cell_styles and col < len(cell_styles) and cell_styles[col]:
                style = cell_styles[col]
                if 'color' in style:
                    item.setForeground(QBrush(QColor(style['color'])))
                if 'bold' in style and style['bold']:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if 'align' in style:
                    align_map = {
                        'left': Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        'center': Qt.AlignmentFlag.AlignCenter,
                        'right': Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    }
                    item.setTextAlignment(align_map.get(style['align'], Qt.AlignmentFlag.AlignCenter))

            self.setItem(row, col, item)
        return row

    def set_change_cell(self, row, col, value):
        """设置涨跌幅单元格（自动红绿）"""
        item = self.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, col, item)

        try:
            val = float(value)
            color = get_change_color(val)
            item.setText(format_change(val))
            item.setForeground(QBrush(QColor(color)))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        except (ValueError, TypeError):
            item.setText(str(value))

    def set_score_cell(self, row, col, score):
        """设置AI评分单元格（按分数着色）"""
        item = self.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, col, item)

        try:
            val = float(score)
            color = get_ai_score_color(val)
            item.setText(f'{val:.1f}')
            item.setForeground(QBrush(QColor(color)))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        except (ValueError, TypeError):
            item.setText(str(score))

    def set_limit_cell(self, row, col, is_limit_up=True):
        """设置涨跌停单元格"""
        item = self.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, col, item)

        if is_limit_up:
            item.setText('涨停')
            item.setForeground(QBrush(QColor(LIMIT_UP_COLOR)))
        else:
            item.setText('跌停')
            item.setForeground(QBrush(QColor(LIMIT_DOWN_COLOR)))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def clear_all(self):
        """清空所有数据"""
        self.setRowCount(0)
        self.clearContents()
