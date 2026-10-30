"""
全局QSS样式表 - 科技感量化终端风格
参考React量化应用设计：渐变卡片、发光效果、等宽数字、红涨绿跌
"""

GLOBAL_QSS = """
/* ===== 全局 ===== */
QWidget {
    background-color: #0a0e17;
    color: #e2e8f0;
    font-family: "Noto Sans SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
}

QMainWindow {
    background-color: #060912;
}

/* ===== 菜单栏 ===== */
QMenuBar {
    background-color: #0d1320;
    color: #94a3b8;
    border-bottom: 1px solid #1e293b;
    padding: 2px 0px;
    font-size: 12px;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 14px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #1e293b;
    color: #38bdf8;
}

QMenu {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #1e293b;
    color: #38bdf8;
}

/* ===== TabWidget ===== */
QTabWidget::pane {
    border: 1px solid #1e293b;
    border-radius: 0px;
    background-color: #0a0e17;
    top: -1px;
}

QTabBar::tab {
    background-color: #0a0e17;
    color: #64748b;
    padding: 10px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 0px;
    font-size: 12px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #0f172a;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #0f172a;
    color: #cbd5e1;
}

/* ===== 表格 ===== */
QTableWidget {
    background-color: #0a0e17;
    alternate-background-color: #0f172a;
    gridline-color: #1e293b;
    border: 1px solid #1e293b;
    border-radius: 4px;
    selection-background-color: #1e3a5f;
    selection-color: #f1f5f9;
    outline: none;
}

QTableWidget::item {
    padding: 5px 6px;
    border: none;
}

QTableWidget::item:selected {
    background-color: #1e3a5f;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #0f172a;
    color: #64748b;
    padding: 7px 8px;
    border: none;
    border-right: 1px solid #1e293b;
    border-bottom: 1px solid #1e293b;
    font-weight: 600;
    font-size: 11px;
}

QHeaderView::section:hover {
    background-color: #1e293b;
    color: #38bdf8;
}

/* ===== 按钮 ===== */
QPushButton {
    background-color: #0f172a;
    color: #cbd5e1;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 500;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #1e293b;
    border-color: #38bdf8;
    color: #38bdf8;
}

QPushButton:pressed {
    background-color: #0f172a;
}

QPushButton:disabled {
    color: #475569;
    border-color: #1e293b;
}

/* 主操作按钮 - 青色渐变 */
QPushButton[class="primary"] {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0891b2, stop:1 #0e7490);
    color: #ffffff;
    border: 1px solid #22d3ee;
    font-weight: 600;
}

QPushButton[class="primary"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #06b6d4, stop:1 #0891b2);
    color: #ffffff;
    border: 1px solid #67e8f9;
}

/* 危险按钮 - 红色渐变 */
QPushButton[class="danger"] {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #dc2626, stop:1 #b91c1c);
    color: #ffffff;
    border: 1px solid #ef4444;
}

QPushButton[class="danger"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ef4444, stop:1 #dc2626);
}

/* 成功按钮 - 绿色渐变 */
QPushButton[class="success"] {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #059669, stop:1 #047857);
    color: #ffffff;
    border: 1px solid #10b981;
}

QPushButton[class="success"]:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #10b981, stop:1 #059669);
}

/* ===== 输入框 ===== */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: #0891b2;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #38bdf8;
}

/* ===== 下拉框 ===== */
QComboBox {
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 5px 8px;
}

QComboBox:hover {
    border-color: #38bdf8;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    selection-background-color: #1e293b;
    color: #e2e8f0;
}

/* ===== 滚动条 ===== */
QScrollBar:vertical {
    background-color: #0a0e17;
    width: 6px;
    border-radius: 3px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #334155;
    border-radius: 3px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #38bdf8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #0a0e17;
    height: 6px;
    border-radius: 3px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background-color: #334155;
    border-radius: 3px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #38bdf8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ===== GroupBox ===== */
QGroupBox {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    color: #e2e8f0;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0px 8px;
    color: #38bdf8;
}

/* ===== 标签 ===== */
QLabel {
    background: transparent;
    color: #e2e8f0;
}

QLabel[class="title"] {
    font-size: 16px;
    font-weight: 700;
    color: #fbbf24;
}

QLabel[class="subtitle"] {
    font-size: 12px;
    color: #64748b;
}

QLabel[class="up"] {
    color: #ef4444;
    font-weight: 700;
}

QLabel[class="down"] {
    color: #22c55e;
    font-weight: 700;
}

QLabel[class="ai_score"] {
    color: #ef4444;
    font-size: 20px;
    font-weight: 700;
    font-family: "IBM Plex Mono", "Consolas", monospace;
}

QLabel[class="mono"] {
    font-family: "IBM Plex Mono", "Consolas", "Courier New", monospace;
}

/* ===== 状态栏 ===== */
QStatusBar {
    background-color: #060912;
    color: #64748b;
    border-top: 1px solid #1e293b;
    font-size: 11px;
}

QStatusBar::item {
    border: none;
}

/* ===== 分割线 ===== */
QSplitter::handle {
    background-color: #1e293b;
}

QSplitter::handle:horizontal {
    width: 1px;
}

QSplitter::handle:vertical {
    height: 1px;
}

/* ===== 复选框/单选框 ===== */
QCheckBox, QRadioButton {
    color: #cbd5e1;
    spacing: 6px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #334155;
    border-radius: 3px;
    background-color: #0f172a;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #0891b2;
    border-color: #22d3ee;
}

/* ===== 进度条 ===== */
QProgressBar {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
    text-align: center;
    color: #e2e8f0;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0891b2, stop:1 #06b6d4);
    border-radius: 3px;
}

/* ===== ToolTip ===== */
QToolTip {
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #38bdf8;
    border-radius: 4px;
    padding: 4px 8px;
}

/* ===== SpinBox ===== */
QSpinBox, QDoubleSpinBox {
    background-color: #0f172a;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 3px 6px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #38bdf8;
}

/* ===== ListWidget ===== */
QListWidget {
    background-color: #0a0e17;
    border: 1px solid #1e293b;
    border-radius: 4px;
    outline: none;
}

QListWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #1e293b;
}

QListWidget::item:selected {
    background-color: #1e3a5f;
    color: #ffffff;
}

QListWidget::item:hover {
    background-color: #0f172a;
}
"""


def apply_theme(app):
    """应用全局主题样式"""
    app.setStyleSheet(GLOBAL_QSS)
