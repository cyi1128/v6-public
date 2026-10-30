# -*- coding: utf-8 -*-
"""
源代码编辑器对话框
支持文件选择、语法高亮、行号、语法检查、保存
"""
import os
import sys
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QPlainTextEdit, QLabel, QMessageBox, QFileDialog, QWidget
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont, QPainter, QColor, QTextCharFormat, QSyntaxHighlighter, QTextDocument


# ============================================================
# Python语法高亮
# ============================================================
class PythonHighlighter(QSyntaxHighlighter):
    """Python语法高亮器"""
    KEYWORDS = {
        'def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while',
        'break', 'continue', 'pass', 'import', 'from', 'as', 'try', 'except',
        'finally', 'raise', 'with', 'lambda', 'yield', 'global', 'nonlocal',
        'assert', 'del', 'in', 'is', 'not', 'and', 'or', 'True', 'False',
        'None', 'self', 'async', 'await',
    }
    BUILTINS = {
        'print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict',
        'set', 'tuple', 'bool', 'type', 'isinstance', 'hasattr', 'getattr',
        'setattr', 'open', 'input', 'enumerate', 'zip', 'map', 'filter',
        'sorted', 'reversed', 'sum', 'min', 'max', 'abs', 'round',
    }

    def __init__(self, document):
        super().__init__(document)
        self._formats = {}
        # 关键字
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#c678dd'))
        fmt.setFontWeight(700)
        self._formats['keyword'] = fmt
        # 内置函数
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#56b6c2'))
        self._formats['builtin'] = fmt
        # 字符串
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#98c379'))
        self._formats['string'] = fmt
        # 注释
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#7f848e'))
        fmt.setFontItalic(True)
        self._formats['comment'] = fmt
        # 数字
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#d19a66'))
        self._formats['number'] = fmt
        # 装饰器
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#e5c07b'))
        self._formats['decorator'] = fmt

    def highlightBlock(self, text):
        import re
        # 注释
        comment_pos = text.find('#')
        if comment_pos >= 0:
            # 检查是否在字符串中
            in_string = False
            quote_char = None
            for i in range(comment_pos):
                if text[i] in ('"', "'"):
                    if not in_string:
                        in_string = True
                        quote_char = text[i]
                    elif text[i] == quote_char:
                        in_string = False
            if not in_string:
                self.setFormat(comment_pos, len(text) - comment_pos, self._formats['comment'])
                text = text[:comment_pos]

        # 字符串（简单匹配）
        for match in re.finditer(r'["\'][^"\']*["\']', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['string'])

        # 装饰器
        for match in re.finditer(r'@\w+', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['decorator'])

        # 数字
        for match in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self._formats['number'])

        # 关键字和内置函数
        for match in re.finditer(r'\b\w+\b', text):
            word = match.group()
            if word in self.KEYWORDS:
                self.setFormat(match.start(), match.end() - match.start(), self._formats['keyword'])
            elif word in self.BUILTINS:
                self.setFormat(match.start(), match.end() - match.start(), self._formats['builtin'])


# ============================================================
# 行号区域
# ============================================================
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return self.editor.line_number_area_width()

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


# ============================================================
# 代码编辑器（带行号）
# ============================================================
class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)
        # 等宽字体
        font = QFont('Consolas', 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        # 制表符宽度
        self.setTabStopDistance(40)
        # 语法高亮
        self.highlighter = PythonHighlighter(self.document())

    def line_number_area_width(self):
        digits = max(1, len(str(self.blockCount())))
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits + 10
        return space

    def _update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor('#1e222a'))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor('#5c6370'))
                painter.drawText(
                    0, top, self.line_number_area.width() - 5,
                    self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1


# ============================================================
# 源代码编辑器对话框
# ============================================================
class CodeEditorDialog(QDialog):
    """源代码编辑器对话框"""

    # 可编辑文件列表
    EDITABLE_FILES = [
        ('ui/monitor_hall.py', '实时监控大厅'),
        ('strategy/resonance_signals.py', '共振+回踩二十日信号'),
        ('strategies/v76_optimized_strategy.py', 'V7.6-A策略'),
        ('strategies/kdj_strategy.py', 'KDJ策略'),
        ('strategies/v75_optimized_strategy.py', 'V7.5评分引擎'),
        ('strategy/indicator_scanner.py', '指标信号扫描'),
        ('strategy/signal_config.py', '信号参数配置'),
        ('strategy/market_sector_analyzer.py', '板块指数分析'),
        ('ui/main_window.py', '主窗口'),
    ]

    def __init__(self, parent=None, default_file=None):
        super().__init__(parent)
        self.setWindowTitle('📝 源代码编辑器')
        self.resize(1000, 700)
        self._current_file = None
        self._base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._init_ui(default_file)

    def _init_ui(self, default_file):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel('文件：'))
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(300)
        for path, desc in self.EDITABLE_FILES:
            full_path = os.path.join(self._base_dir, path)
            self.file_combo.addItem(f'{desc} ({path})', full_path)
        self.file_combo.currentIndexChanged.connect(self._on_file_changed)
        toolbar.addWidget(self.file_combo)

        # 打开其他文件
        self.open_btn = QPushButton('📂 打开其他文件')
        self.open_btn.clicked.connect(self._open_other_file)
        toolbar.addWidget(self.open_btn)
        toolbar.addStretch()

        # 状态标签
        self.status_label = QLabel('')
        self.status_label.setStyleSheet('color: #8b949e; font-size: 12px;')
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        # 代码编辑区
        self.editor = CodeEditor()
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                background: #282c34; color: #abb2bf;
                border: 1px solid #3e4451; border-radius: 4px;
                padding: 4px;
            }
        """)
        layout.addWidget(self.editor, 1)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton('💾 保存（语法检查）')
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #238636; color: white; border: none;
                border-radius: 4px; padding: 8px 20px; font-size: 13px;
            }
            QPushButton:hover { background: #2ea043; }
        """)
        self.save_btn.clicked.connect(self._save)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 8px 20px; font-size: 13px;
            }
            QPushButton:hover { background: #30363d; }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()

        # 提示
        tip = QLabel('⚠️ 保存后需重启程序生效。保存前自动进行Python语法检查。')
        tip.setStyleSheet('color: #d29922; font-size: 11px;')
        btn_layout.addWidget(tip)
        layout.addLayout(btn_layout)

        # 加载默认文件
        if default_file:
            for i in range(self.file_combo.count()):
                if default_file in self.file_combo.itemData(i):
                    self.file_combo.setCurrentIndex(i)
                    break
        else:
            self._on_file_changed(0)

    def _on_file_changed(self, index):
        file_path = self.file_combo.itemData(index)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.editor.setPlainText(content)
                self._current_file = file_path
                self.status_label.setText(f'已加载: {os.path.basename(file_path)} ({len(content)}字符)')
                self.status_label.setStyleSheet('color: #58a6ff; font-size: 12px;')
            except Exception as e:
                self.status_label.setText(f'加载失败: {e}')
                self.status_label.setStyleSheet('color: #f85149; font-size: 12px;')

    def _open_other_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, '打开Python文件', self._base_dir, 'Python文件 (*.py);;所有文件 (*.*)'
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.editor.setPlainText(content)
                self._current_file = file_path
                self.status_label.setText(f'已加载: {file_path} ({len(content)}字符)')
                self.status_label.setStyleSheet('color: #58a6ff; font-size: 12px;')
            except Exception as e:
                self.status_label.setText(f'加载失败: {e}')
                self.status_label.setStyleSheet('color: #f85149; font-size: 12px;')

    def _save(self):
        if not self._current_file:
            QMessageBox.warning(self, '提示', '请先选择文件')
            return

        content = self.editor.toPlainText()

        # 语法检查
        self.status_label.setText('正在语法检查...')
        self.status_label.setStyleSheet('color: #d29922; font-size: 12px;')
        QApplication.processEvents() if hasattr(QApplication, 'processEvents') else None

        # 写入临时文件进行语法检查
        import tempfile
        tmp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
        tmp_file.write(content)
        tmp_file.close()

        try:
            result = subprocess.run(
                [sys.executable, '-m', 'py_compile', tmp_file.name],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                # 语法错误
                error_msg = result.stderr.replace(tmp_file.name, os.path.basename(self._current_file))
                self.status_label.setText('❌ 语法错误，未保存')
                self.status_label.setStyleSheet('color: #f85149; font-size: 12px;')
                QMessageBox.critical(self, '语法错误', f'保存失败，存在语法错误：\n\n{error_msg}')
                return
        except Exception as e:
            self.status_label.setText(f'语法检查异常: {e}')
            self.status_label.setStyleSheet('color: #f85149; font-size: 12px;')
            return
        finally:
            os.unlink(tmp_file.name)

        # 语法正确，保存
        try:
            # 备份原文件
            backup_path = self._current_file + '.bak'
            if os.path.exists(self._current_file):
                with open(self._current_file, 'r', encoding='utf-8') as f:
                    old_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(old_content)

            # 写入新内容
            with open(self._current_file, 'w', encoding='utf-8') as f:
                f.write(content)

            self.status_label.setText(f'✅ 保存成功！备份: {os.path.basename(backup_path)}，重启程序后生效')
            self.status_label.setStyleSheet('color: #3fb950; font-size: 12px;')
            QMessageBox.information(
                self, '保存成功',
                f'文件已保存：{os.path.basename(self._current_file)}\n\n'
                f'备份文件：{os.path.basename(backup_path)}\n\n'
                f'请重启程序使修改生效。'
            )
        except Exception as e:
            self.status_label.setText(f'保存失败: {e}')
            self.status_label.setStyleSheet('color: #f85149; font-size: 12px;')
            QMessageBox.critical(self, '保存失败', str(e))


# 延迟导入避免循环
from PyQt6.QtWidgets import QApplication
