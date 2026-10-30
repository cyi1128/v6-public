# -*- coding: utf-8 -*-
"""
策略源码编辑器与新策略上传模块
V0.6.3.7 - 策略源码编辑 + 动态注册新策略
"""
import os
import sys
import importlib
import inspect
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QLineEdit, QMessageBox, QFileDialog, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor

# 深色主题
DARK_BG = '#0d1117'
DARK_PANEL = '#161b22'
DARK_BORDER = '#30363d'
TEXT_PRIMARY = '#e6edf3'
TEXT_SECONDARY = '#8b949e'
ACCENT_GREEN = '#238636'
ACCENT_BLUE = '#1f6feb'
ACCENT_RED = '#da3633'
ACCENT_ORANGE = '#d29922'


class PythonHighlighter(QSyntaxHighlighter):
    """Python语法高亮"""
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        # 关键字
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor('#ff7b72'))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = ['def', 'class', 'import', 'from', 'return', 'if', 'elif',
                    'else', 'for', 'while', 'try', 'except', 'with', 'as',
                    'lambda', 'yield', 'raise', 'pass', 'break', 'continue',
                    'and', 'or', 'not', 'in', 'is', 'None', 'True', 'False',
                    'self', 'super']
        for kw in keywords:
            self.rules.append((f'\\b{kw}\\b', keyword_format))
        # 字符串
        str_format = QTextCharFormat()
        str_format.setForeground(QColor('#a5d6ff'))
        self.rules.append(('"[^"]*"', str_format))
        self.rules.append(("'[^']*'", str_format))
        # 注释
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor('#8b949e'))
        comment_format.setFontItalic(True)
        self.rules.append(('#[^\n]*', comment_format))
        # 数字
        num_format = QTextCharFormat()
        num_format.setForeground(QColor('#79c0ff'))
        self.rules.append(('\\b\\d+\\.?\\d*\\b', num_format))

    def highlightBlock(self, text):
        import re
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class StrategyCodeEditorDialog(QDialog):
    """策略源码编辑器"""
    def __init__(self, strategy_name, strategy_file, parent=None):
        super().__init__(parent)
        self.strategy_name = strategy_name
        self.strategy_file = strategy_file
        self.original_code = ''
        self.setWindowTitle(f'📝 编辑策略源码 - {strategy_name}')
        self.setMinimumSize(800, 600)
        self.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
        self._init_ui()
        self._load_code()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 提示
        tip = QLabel('⚠️ 修改源码后点击"保存并应用"，将覆盖原策略文件。建议先备份。')
        tip.setStyleSheet(f'color: {ACCENT_ORANGE}; font-size: 12px; padding: 6px;')
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 代码编辑器
        self.editor = QTextEdit()
        self.editor.setStyleSheet(f'''
            QTextEdit {{
                background: {DARK_PANEL}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                font-family: Consolas, "Courier New", monospace; font-size: 13px;
                selection-background-color: {ACCENT_BLUE};
            }}
        ''')
        self.editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.highlighter = PythonHighlighter(self.editor.document())
        layout.addWidget(self.editor)

        # 状态栏
        self.status = QLabel('就绪')
        self.status.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        layout.addWidget(self.status)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_check = QPushButton('✓ 语法检查')
        btn_check.setStyleSheet(self._btn_style(ACCENT_BLUE))
        btn_check.clicked.connect(self._check_syntax)
        btn_layout.addWidget(btn_check)

        btn_reload = QPushButton('↺ 重新加载')
        btn_reload.setStyleSheet(self._btn_style(TEXT_SECONDARY))
        btn_reload.clicked.connect(self._load_code)
        btn_layout.addWidget(btn_reload)

        btn_layout.addStretch()

        btn_cancel = QPushButton('取消')
        btn_cancel.setStyleSheet(self._btn_style(ACCENT_RED))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton('💾 保存并应用')
        btn_save.setStyleSheet(self._btn_style(ACCENT_GREEN))
        btn_save.clicked.connect(self._save_code)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _btn_style(self, color):
        return f'''
            QPushButton {{
                background: {color}; color: white; border: none;
                padding: 8px 16px; border-radius: 4px; font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {color}; opacity: 0.85; }}
        '''

    def _load_code(self):
        try:
            if os.path.exists(self.strategy_file):
                with open(self.strategy_file, 'r', encoding='utf-8') as f:
                    self.original_code = f.read()
                self.editor.setPlainText(self.original_code)
                self.status.setText(f'已加载: {self.strategy_file} ({len(self.original_code)}字符)')
            else:
                self.status.setText(f'文件不存在: {self.strategy_file}')
        except Exception as e:
            self.status.setText(f'加载失败: {e}')

    def _check_syntax(self):
        code = self.editor.toPlainText()
        try:
            compile(code, self.strategy_file, 'exec')
            self.status.setText('✓ 语法检查通过')
            QMessageBox.information(self, '语法检查', '代码语法正确，可以保存。')
            return True
        except SyntaxError as e:
            self.status.setText(f'✗ 语法错误: 第{e.lineno}行 - {e.msg}')
            QMessageBox.critical(self, '语法错误', f'第 {e.lineno} 行:\n{e.msg}\n\n请修正后再保存。')
            return False

    def _save_code(self):
        if not self._check_syntax():
            return
        code = self.editor.toPlainText()
        try:
            # 备份原文件
            backup = self.strategy_file + '.bak'
            if os.path.exists(self.strategy_file):
                with open(self.strategy_file, 'r', encoding='utf-8') as f:
                    with open(backup, 'w', encoding='utf-8') as bf:
                        bf.write(f.read())
            # 写入新代码
            with open(self.strategy_file, 'w', encoding='utf-8') as f:
                f.write(code)
            self.status.setText('✓ 保存成功，已重新加载模块')
            QMessageBox.information(self, '保存成功',
                f'策略 {self.strategy_name} 源码已更新。\n\n'
                f'备份文件: {backup}\n\n'
                f'下次回测将使用新代码。\n'
                f'如遇导入错误，可从备份恢复。')
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, '保存失败', str(e))


class NewStrategyDialog(QDialog):
    """上传新策略对话框"""
    strategy_created = pyqtSignal(str, str, str)  # name, class_name, file_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('➕ 上传新策略')
        self.setMinimumSize(750, 650)
        self.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 策略信息
        info_group = QGroupBox('策略信息')
        info_group.setStyleSheet(f'''
            QGroupBox {{ color: {TEXT_PRIMARY}; border: 1px solid {DARK_BORDER};
                border-radius: 4px; margin-top: 10px; padding-top: 15px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
        ''')
        form = QFormLayout(info_group)
        form.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText('例如：我的突破策略')
        self.name_input.setStyleSheet(self._input_style())
        form.addRow('策略名称:', self.name_input)

        self.class_input = QLineEdit()
        self.class_input.setPlaceholderText('例如：MyBreakoutStrategy')
        self.class_input.setStyleSheet(self._input_style())
        form.addRow('类名:', self.class_input)

        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText('例如：my_breakout.py')
        self.file_input.setStyleSheet(self._input_style())
        form.addRow('文件名:', self.file_input)

        layout.addWidget(info_group)

        # AI自然语言策略生成
        ai_group = QGroupBox('🤖 AI自然语言策略（输入描述自动生成代码）')
        ai_group.setStyleSheet(f'''
            QGroupBox {{ color: {ACCENT_BLUE}; border: 1px solid {ACCENT_BLUE};
                border-radius: 4px; margin-top: 10px; padding-top: 15px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
        ''')
        ai_layout = QVBoxLayout(ai_group)
        ai_layout.setSpacing(6)

        ai_input_layout = QHBoxLayout()
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText('描述你的策略，例如：当5日均线上穿10日均线且成交量放大1.5倍时买入，跌破20日均线卖出')
        self.ai_input.setStyleSheet(self._input_style())
        ai_input_layout.addWidget(self.ai_input, 1)

        self.ai_generate_btn = QPushButton('✨ AI生成代码')
        self.ai_generate_btn.setStyleSheet(f'''
            QPushButton {{
                background: linear-gradient(135deg, #8957e5, #1f6feb);
                color: white; border: none; border-radius: 4px;
                padding: 6px 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: linear-gradient(135deg, #a371f7, #388bfd); }}
        ''')
        self.ai_generate_btn.clicked.connect(self._ai_generate_strategy)
        ai_input_layout.addWidget(self.ai_generate_btn)
        ai_layout.addLayout(ai_input_layout)

        self.ai_status = QLabel('')
        self.ai_status.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        self.ai_status.setWordWrap(True)
        ai_layout.addWidget(self.ai_status)

        layout.addWidget(ai_group)

        # 源码模板提示
        template_tip = QLabel(
            '策略类必须继承 BaseStrategy，实现 generate_signals(kline_data) 方法。\n'
            '返回信号列表: [{"date": "2024-01-02", "signal": "buy"/"sell", "price": 10.5}, ...]'
        )
        template_tip.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 11px; padding: 6px;')
        template_tip.setWordWrap(True)
        layout.addWidget(template_tip)

        # 源码编辑器
        code_label = QLabel('策略源代码:')
        code_label.setStyleSheet(f'color: {TEXT_PRIMARY}; font-weight: bold;')
        layout.addWidget(code_label)

        self.editor = QTextEdit()
        self.editor.setStyleSheet(f'''
            QTextEdit {{
                background: {DARK_PANEL}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                font-family: Consolas, "Courier New", monospace; font-size: 13px;
            }}
        ''')
        self.editor.setPlaceholderText('# 在此粘贴或编写策略代码...')
        self.highlighter = PythonHighlighter(self.editor.document())
        # 默认模板
        self.editor.setPlainText(self._get_template())
        layout.addWidget(self.editor)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_template = QPushButton('📋 加载模板')
        btn_template.setStyleSheet(self._btn_style(ACCENT_BLUE))
        btn_template.clicked.connect(lambda: self.editor.setPlainText(self._get_template()))
        btn_layout.addWidget(btn_template)

        btn_import = QPushButton('📂 导入文件')
        btn_import.setStyleSheet(self._btn_style(TEXT_SECONDARY))
        btn_import.clicked.connect(self._import_file)
        btn_layout.addWidget(btn_import)

        btn_check = QPushButton('✓ 语法检查')
        btn_check.setStyleSheet(self._btn_style(ACCENT_ORANGE))
        btn_check.clicked.connect(self._check_syntax)
        btn_layout.addWidget(btn_check)

        btn_layout.addStretch()

        btn_cancel = QPushButton('取消')
        btn_cancel.setStyleSheet(self._btn_style(ACCENT_RED))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_create = QPushButton('🚀 创建策略')
        btn_create.setStyleSheet(self._btn_style(ACCENT_GREEN))
        btn_create.clicked.connect(self._create_strategy)
        btn_layout.addWidget(btn_create)

        layout.addLayout(btn_layout)

    def _input_style(self):
        return f'''
            QLineEdit {{
                background: {DARK_PANEL}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                padding: 6px 8px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_BLUE}; }}
        '''

    def _btn_style(self, color):
        return f'''
            QPushButton {{
                background: {color}; color: white; border: none;
                padding: 8px 14px; border-radius: 4px; font-size: 12px;
                font-weight: bold;
            }}
        '''

    def _get_template(self):
        return '''# -*- coding: utf-8 -*-
"""
自定义策略模板
继承 BaseStrategy，实现 generate_signals 方法
"""
from backtest.strategy.base import BaseStrategy


class MyCustomStrategy(BaseStrategy):
    """我的自定义策略"""

    name = "自定义策略"

    def __init__(self, params=None):
        super().__init__(params)
        # 策略参数
        self.ma_period = self.params.get('ma_period', 5)
        self.volume_ratio = self.params.get('volume_ratio', 2.0)

    def generate_signals(self, kline_data):
        """
        生成交易信号
        Args:
            kline_data: dict, 包含 open/close/high/low/volume/dates
        Returns:
            list: [{"date": "2024-01-02", "signal": "buy", "price": 10.5}, ...]
        """
        signals = []
        closes = kline_data.get('close', [])
        volumes = kline_data.get('volume', [])
        dates = kline_data.get('dates', [])

        if len(closes) < self.ma_period + 1:
            return signals

        # 计算均线
        ma = []
        for i in range(len(closes)):
            if i >= self.ma_period - 1:
                ma.append(sum(closes[i-self.ma_period+1:i+1]) / self.ma_period)
            else:
                ma.append(None)

        # 生成信号
        for i in range(1, len(closes)):
            if ma[i] is None or ma[i-1] is None:
                continue
            # 均量突破
            avg_vol = sum(volumes[max(0,i-5):i]) / 5 if i >= 5 else volumes[i]
            vol_break = volumes[i] > avg_vol * self.volume_ratio

            # 上穿均线买入
            if closes[i-1] < ma[i-1] and closes[i] > ma[i] and vol_break:
                signals.append({
                    "date": str(dates[i])[:10],
                    "signal": "buy",
                    "price": closes[i]
                })
            # 跌破均线卖出
            elif closes[i-1] > ma[i-1] and closes[i] < ma[i]:
                signals.append({
                    "date": str(dates[i])[:10],
                    "signal": "sell",
                    "price": closes[i]
                })

        return signals
'''

    def _ai_generate_strategy(self):
        """AI自然语言生成策略代码"""
        description = self.ai_input.text().strip()
        if not description:
            QMessageBox.warning(self, '提示', '请输入策略描述')
            return

        self.ai_status.setText('⏳ AI正在分析策略描述并生成代码...')
        self.ai_generate_btn.setEnabled(False)

        def _do_generate():
            try:
                # 优先使用Ollama本地大模型
                code, strategy_name = self._generate_with_ollama(description)
                if not code:
                    # 降级：使用规则解析
                    code, strategy_name = self._generate_with_rules(description)

                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._on_ai_generated(code, strategy_name))
            except Exception as e:
                print(f"[AI策略生成] 失败: {e}")
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.ai_status.setText(f'❌ 生成失败: {e}'))
            finally:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.ai_generate_btn.setEnabled(True))

        import threading
        threading.Thread(target=_do_generate, daemon=True).start()

    def _generate_with_ollama(self, description):
        """使用Ollama本地大模型生成策略代码"""
        try:
            import requests
            prompt = f"""你是一个量化交易策略开发专家。请根据以下策略描述，生成一个完整的Python策略类。

要求：
1. 继承 BaseStrategy
2. 实现 __init__ 和 generate_signals(kline_data) 方法
3. generate_signals 返回信号列表: [{{"date": "2024-01-02", "signal": "buy"/"sell", "price": 10.5}}]
4. kline_data 是字典，包含 keys: dates, open, high, low, close, volume
5. 使用MA5/MA10/MA20等均线，成交量等指标
6. 类名使用大驼峰命名，如 MyStrategy
7. 只输出Python代码，不要输出解释

策略描述：{description}

请输出完整的Python代码："""

            resp = requests.post('http://localhost:11434/api/generate', json={
                'model': 'qwen2.5:7b',
                'prompt': prompt,
                'stream': False
            }, timeout=120)

            if resp.status_code == 200:
                result = resp.json()
                code = result.get('response', '')
                # 提取代码块
                if '```python' in code:
                    code = code.split('```python')[1].split('```')[0]
                elif '```' in code:
                    code = code.split('```')[1].split('```')[0]
                code = code.strip()

                # 提取类名
                class_name = 'AIGeneratedStrategy'
                for line in code.split('\n'):
                    if 'class ' in line and '(BaseStrategy)' in line:
                        class_name = line.split('class ')[1].split('(')[0].strip()
                        break

                strategy_name = description[:20] + '策略'
                return code, strategy_name
            return None, None
        except Exception as e:
            print(f"[Ollama] 调用失败: {e}")
            return None, None

    def _generate_with_rules(self, description):
        """使用规则解析生成策略代码（降级方案）"""
        desc_lower = description.lower()

        # 简单规则匹配
        buy_conditions = []
        sell_conditions = []
        strategy_name = '自定义策略'

        if '5日' in description and '10日' in description and ('金叉' in description or '上穿' in description):
            buy_conditions.append('ma5[i] > ma10[i] and ma5[i-1] <= ma10[i-1]')
            strategy_name = '均线金叉策略'
        if '成交量' in description and ('放大' in description or '放量' in description):
            buy_conditions.append('volume[i] > volume_ma5[i] * 1.5')
        if '20日' in description and ('跌破' in description or '下破' in description):
            sell_conditions.append('close[i] < ma20[i]')
        if '5日' in description and ('死叉' in description or '下穿' in description):
            sell_conditions.append('ma5[i] < ma10[i] and ma5[i-1] >= ma10[i-1]')

        if not buy_conditions:
            buy_conditions.append('ma5[i] > ma20[i] and close[i] > ma5[i]')
            strategy_name = '趋势跟踪策略'
        if not sell_conditions:
            sell_conditions.append('close[i] < ma20[i]')

        buy_expr = ' and '.join(buy_conditions)
        sell_expr = ' and '.join(sell_conditions)

        code = f'''# -*- coding: utf-8 -*-
"""
AI生成策略: {strategy_name}
描述: {description}
"""
from backtest.strategy.base import BaseStrategy

class AIGeneratedStrategy(BaseStrategy):
    """{strategy_name}"""

    name = "{strategy_name}"

    def __init__(self, params=None):
        super().__init__(params)
        self.ma_period_fast = self.params.get("ma_fast", 5)
        self.ma_period_slow = self.params.get("ma_slow", 10)
        self.ma_period_long = self.params.get("ma_long", 20)

    def generate_signals(self, kline_data):
        dates = kline_data["dates"]
        close = kline_data["close"]
        high = kline_data["high"]
        low = kline_data["low"]
        volume = kline_data["volume"]
        n = len(dates)

        # 计算均线
        ma5 = self._calc_ma(close, 5)
        ma10 = self._calc_ma(close, 10)
        ma20 = self._calc_ma(close, 20)
        volume_ma5 = self._calc_ma(volume, 5)

        signals = []
        position = 0

        for i in range(20, n):
            if position == 0:
                # 买入条件
                if {buy_expr}:
                    signals.append({{
                        "date": str(dates[i])[:10],
                        "signal": "buy",
                        "price": float(close[i])
                    }})
                    position = 1
            elif position == 1:
                # 卖出条件
                if {sell_expr}:
                    signals.append({{
                        "date": str(dates[i])[:10],
                        "signal": "sell",
                        "price": float(close[i])
                    }})
                    position = 0

        return signals

    def _calc_ma(self, data, period):
        result = [None] * len(data)
        for i in range(period - 1, len(data)):
            result[i] = sum(data[i-period+1:i+1]) / period
        return result
'''
        return code, strategy_name

    def _on_ai_generated(self, code, strategy_name):
        """AI生成完成回调"""
        if code:
            self.editor.setPlainText(code)
            self.name_input.setText(strategy_name)
            # 自动填充类名和文件名
            class_name = 'AIGeneratedStrategy'
            for line in code.split('\n'):
                if 'class ' in line and '(BaseStrategy)' in line:
                    class_name = line.split('class ')[1].split('(')[0].strip()
                    break
            self.class_input.setText(class_name)
            self.file_input.setText(class_name.lower() + '.py')
            self.ai_status.setText(f'✅ AI生成成功！策略名称: {strategy_name}，类名: {class_name}')
        else:
            self.ai_status.setText('❌ AI生成失败，请手动编写代码')

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择策略文件', '', 'Python文件 (*.py);;所有文件 (*.*)'
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.editor.setPlainText(f.read())
                # 自动填充文件名
                fname = os.path.basename(path)
                self.file_input.setText(fname)
            except Exception as e:
                QMessageBox.critical(self, '导入失败', str(e))

    def _check_syntax(self):
        code = self.editor.toPlainText()
        try:
            compile(code, '<new_strategy>', 'exec')
            QMessageBox.information(self, '语法检查', '代码语法正确。')
            return True
        except SyntaxError as e:
            QMessageBox.critical(self, '语法错误',
                f'第 {e.lineno} 行:\n{e.msg}\n\n请修正后再创建。')
            return False

    def _create_strategy(self):
        name = self.name_input.text().strip()
        class_name = self.class_input.text().strip()
        file_name = self.file_input.text().strip()
        code = self.editor.toPlainText()

        if not name:
            QMessageBox.warning(self, '提示', '请输入策略名称')
            return
        if not class_name:
            QMessageBox.warning(self, '提示', '请输入策略类名')
            return
        if not file_name:
            file_name = class_name.lower() + '.py'
        if not file_name.endswith('.py'):
            file_name += '.py'
        if not code.strip():
            QMessageBox.warning(self, '提示', '请输入策略源代码')
            return

        if not self._check_syntax():
            return

        # 保存策略文件
        strategy_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     'backtest', 'strategy')
        file_path = os.path.join(strategy_dir, file_name)

        if os.path.exists(file_path):
            reply = QMessageBox.question(
                self, '文件已存在',
                f'文件 {file_name} 已存在，是否覆盖？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)

            # 注册到策略配置
            self._register_strategy(name, class_name, file_name)

            # 发送策略创建信号
            self.strategy_created.emit(name, class_name, file_name)

            QMessageBox.information(self, '创建成功',
                f'策略 "{name}" 已创建并注册！\n\n'
                f'文件: {file_path}\n'
                f'类名: {class_name}\n\n'
                f'已自动添加到策略下拉框，可直接选择使用。')
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, '创建失败', str(e))

    def _register_strategy(self, name, class_name, file_name):
        """注册策略到 strategy_config.py 的 STRATEGY_REGISTRY"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                    'backtest', 'strategy', 'strategy_config.py')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 检查是否已存在
            if f'"{class_name}"' in content:
                print(f"[策略注册] {class_name} 已存在，跳过")
                return True

            # 在 STRATEGY_REGISTRY 的最后一个策略后面插入新策略
            # 找到最后一个 "}" 之前的位置
            new_strategy = f'''
    "{class_name}": {{
        "title": "{name}",
        "class": "backtest.strategy.{file_name[:-3]}.{class_name}",
        "params": {{
            "ma_period": {{
                "name": "MA周期", "type": "int", "default": 5,
                "min": 3, "max": 60, "step": 1, "unit": "日",
            }},
            "take_profit_pct": {{
                "name": "止盈", "type": "float", "default": 20.0,
                "min": 1.0, "max": 100.0, "step": 1.0, "unit": "%",
            }},
            "stop_loss_pct": {{
                "name": "止损", "type": "float", "default": 5.0,
                "min": 1.0, "max": 50.0, "step": 1.0, "unit": "%",
            }},
            "max_hold_days": {{
                "name": "最大持仓天数", "type": "int", "default": 20,
                "min": 1, "max": 60, "step": 1, "unit": "天",
            }},
        }},
    }},
'''

            # 找到 STRATEGY_REGISTRY = { 之后，最后一个 } 之前的位置
            # 简单方法：在文件末尾的 "}" 之前插入
            # 找到最后一个 "}" 的位置
            last_brace = content.rfind('}')
            if last_brace > 0:
                # 确保这个 } 是 STRATEGY_REGISTRY 的结束
                content = content[:last_brace] + new_strategy + content[last_brace:]

                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[策略注册] 已注册: {name} ({class_name})")
                return True
            return False
        except Exception as e:
            print(f"[策略注册] 失败: {e}")
            return False
