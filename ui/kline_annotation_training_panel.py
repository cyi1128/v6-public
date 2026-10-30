# -*- coding: utf-8 -*-
"""
K线人工标注训练面板
人工标注B/S买卖点 → 走势数据采集 → AI分析 → 生成策略规则
"""
import os
import json
from typing import Optional, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QSplitter, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal

from backtest.annotation.kline_editor import KlineEditorWidget
from kline_annotation_training.annotation_manager import AnnotationManager
from kline_annotation_training.pattern_extractor import PatternExtractor
from kline_annotation_training.ai_pattern_analyzer import AIPatternAnalyzer


class KlineAnnotationTrainingPanel(QWidget):
    """K线人工标注训练面板"""

    annotation_saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.annotation_manager = AnnotationManager()
        self.pattern_extractor = PatternExtractor()
        self.ai_analyzer = AIPatternAnalyzer()
        self.current_kline_data = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ===== 顶部工具栏 =====
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel('股票代码:'))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText('输入股票代码，如 000678')
        self.code_input.setFixedWidth(120)
        toolbar.addWidget(self.code_input)

        self.load_btn = QPushButton('📥 加载K线')
        self.load_btn.clicked.connect(self._on_load_kline)
        toolbar.addWidget(self.load_btn)

        toolbar.addStretch()

        self.save_btn = QPushButton('💾 保存标注')
        self.save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(self.save_btn)

        self.load_anno_btn = QPushButton('📂 加载标注')
        self.load_anno_btn.clicked.connect(self._on_load_annotation)
        toolbar.addWidget(self.load_anno_btn)

        self.complete_btn = QPushButton('✅ 完成标注')
        self.complete_btn.clicked.connect(self._on_complete)
        toolbar.addWidget(self.complete_btn)

        self.ai_btn = QPushButton('🤖 上传AI分析')
        self.ai_btn.setStyleSheet('background: #1f6feb; color: white;')
        self.ai_btn.clicked.connect(self._on_ai_analyze)
        toolbar.addWidget(self.ai_btn)

        self.validate_btn = QPushButton('🧪 回测验证')
        self.validate_btn.setStyleSheet('background: #238636; color: white;')
        self.validate_btn.clicked.connect(self._on_validate)
        toolbar.addWidget(self.validate_btn)

        self.save_case_btn = QPushButton('📚 存入案例库')
        self.save_case_btn.setStyleSheet('background: #8957e5; color: white;')
        self.save_case_btn.clicked.connect(self._on_save_to_case_db)
        toolbar.addWidget(self.save_case_btn)

        self.compare_btn = QPushButton('📊 成败对比')
        self.compare_btn.setStyleSheet('background: #d29922; color: black;')
        self.compare_btn.clicked.connect(self._on_compare_cases)
        toolbar.addWidget(self.compare_btn)

        layout.addLayout(toolbar)

        # ===== 主体：左侧K线 + 右侧标注信息 =====
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：K线标注编辑器
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.kline_editor = KlineEditorWidget()
        left_layout.addWidget(self.kline_editor)

        splitter.addWidget(left_widget)

        # 右侧：标注信息
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # 买卖点列表
        points_group = QGroupBox('📌 标注的买卖点')
        points_layout = QVBoxLayout(points_group)

        self.points_table = QTableWidget(0, 4)
        self.points_table.setHorizontalHeaderLabels(['类型', '日期', '价格', '理由'])
        self.points_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.points_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        points_layout.addWidget(self.points_table)

        right_layout.addWidget(points_group, stretch=2)

        # 买入理由
        buy_group = QGroupBox('🟢 买入理由')
        buy_layout = QVBoxLayout(buy_group)
        self.buy_reason_input = QTextEdit()
        self.buy_reason_input.setPlaceholderText(
            '填写买入理由，例如：\n- 五日线上穿九日线\n- 回踩MA20\n- 缩量调整\n- 放量突破\n- 缠论二买'
        )
        self.buy_reason_input.setFixedHeight(80)
        buy_layout.addWidget(self.buy_reason_input)
        right_layout.addWidget(buy_group)

        # 卖出理由
        sell_group = QGroupBox('🔴 卖出理由')
        sell_layout = QVBoxLayout(sell_group)
        self.sell_reason_input = QTextEdit()
        self.sell_reason_input.setPlaceholderText(
            '填写卖出理由，例如：\n- 跌破MA5\n- MACD死叉\n- 放量滞涨\n- 跌破MA20'
        )
        self.sell_reason_input.setFixedHeight(80)
        sell_layout.addWidget(self.sell_reason_input)
        right_layout.addWidget(sell_group)

        # AI分析结果
        ai_group = QGroupBox('🤖 AI分析结果')
        ai_layout = QVBoxLayout(ai_group)
        self.ai_result_text = QTextEdit()
        self.ai_result_text.setReadOnly(True)
        self.ai_result_text.setPlaceholderText('点击「上传AI分析」后显示分析结果...')
        ai_layout.addWidget(self.ai_result_text)
        right_layout.addWidget(ai_group, stretch=3)

        splitter.addWidget(right_widget)
        splitter.setSizes([700, 400])

        layout.addWidget(splitter)

        # 连接标注编辑器的信号
        self.kline_editor.annotation_changed.connect(self._on_annotation_changed)

    def _on_load_kline(self):
        """加载K线数据（复用现有K线数据服务）"""
        user_input = self.code_input.text().strip()
        if not user_input:
            QMessageBox.warning(self, '提示', '请输入股票代码或名称')
            return

        try:
            # 第一步：统一代码格式（支持6位代码、带后缀、带前缀）
            from utils.kline_provider import normalize_stock_code
            code = normalize_stock_code(user_input)

            # 第二步：如果不是6位数字，尝试用名称查找代码
            stock_name = ''
            if not (len(code) == 6 and code.isdigit()):
                print(f"[标注训练] 输入'{user_input}'不是标准代码，尝试名称查找...")
                code, stock_name = self._find_code_by_name(user_input)
                if not code:
                    QMessageBox.warning(self, '提示',
                        f'未找到股票「{user_input}」，请输入6位股票代码')
                    return
                print(f"[标注训练] 名称查找成功: {user_input} -> {code} {stock_name}")
            else:
                # 尝试获取股票名称
                stock_name = self._get_stock_name(code)

            print(f"[标注训练] 加载股票: {code} {stock_name}")

            # 第三步：复用现有K线数据服务（通达信）
            from utils.kline_provider import get_daily_kline
            kline_data = get_daily_kline(code, count=500)

            if not kline_data or not kline_data.get('dates'):
                print(f"[标注训练] 通达信接口返回空，尝试DuckDB...")
                # 降级：尝试DuckDB
                kline_data = self._load_from_duckdb(code)

            if not kline_data or not kline_data.get('dates'):
                QMessageBox.warning(self, '提示',
                    f'未找到股票 {code} {stock_name} 的K线数据')
                return

            print(f"[标注训练] K线加载成功: {len(kline_data['dates'])}根, "
                  f"日期范围: {kline_data['dates'][0]} ~ {kline_data['dates'][-1]}")

            self.current_kline_data = kline_data
            self.annotation_manager.set_stock(code, stock_name or code)
            self.kline_editor.load_kline(kline_data, code, stock_name or code)
            self._refresh_points_table()

            # 自动显示当前股票指标概览（真实数据）
            self._show_stock_overview(kline_data, code, stock_name)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'加载K线失败: {str(e)}')

    def _find_code_by_name(self, name: str) -> tuple:
        """通过股票名称查找代码

        Returns:
            (code, name) 或 ('', '')
        """
        try:
            from data.duckdb_adapter import DuckDBAdapter
            adapter = DuckDBAdapter()
            df = adapter.get_stock_basic()
            if df.empty:
                return '', ''

            # 模糊匹配名称
            mask = df['name'].str.contains(name, na=False)
            matched = df[mask]
            if matched.empty:
                return '', ''

            row = matched.iloc[0]
            ts_code = str(row.get('ts_code', ''))
            # ts_code格式如 000001.SZ，取前6位
            code = ts_code.split('.')[0] if '.' in ts_code else ts_code
            stock_name = str(row.get('name', ''))
            return code, stock_name
        except Exception as e:
            print(f"[标注训练] 名称查找失败: {e}")
            return '', ''

    def _get_stock_name(self, code: str) -> str:
        """通过代码获取股票名称"""
        try:
            from data.duckdb_adapter import DuckDBAdapter
            adapter = DuckDBAdapter()
            return adapter.get_stock_name(code)
        except Exception:
            return code

    def _load_from_duckdb(self, code: str) -> Dict:
        """降级方案：从DuckDB加载K线"""
        try:
            import duckdb
            db_path = r'D:\应用\huicexitong\runtime\sj\gpsj.duckdb'
            con = duckdb.connect(db_path, read_only=True)

            # 处理代码格式
            db_code = code
            if '.' not in code:
                rows = con.execute(
                    f"SELECT DISTINCT 股票代码 FROM daily_data.日线数据 WHERE 股票代码 LIKE '%{code}%' LIMIT 1"
                ).fetchall()
                if rows:
                    db_code = rows[0][0]

            df = con.execute(f"""
                SELECT * FROM (
                    SELECT 交易日期, 开盘价, 收盘价, 最高价, 最低价, "成交量(手)" as 成交量
                    FROM daily_data.日线数据
                    WHERE 股票代码 = '{db_code}' AND 收盘价 IS NOT NULL
                    ORDER BY 交易日期 DESC
                    LIMIT 500
                ) ORDER BY 交易日期 ASC
            """).fetchdf()
            con.close()

            if df.empty:
                return None

            return {
                'dates': df['交易日期'].astype(str).tolist(),
                'open': df['开盘价'].tolist(),
                'close': df['收盘价'].tolist(),
                'high': df['最高价'].tolist(),
                'low': df['最低价'].tolist(),
                'volume': df['成交量'].tolist()
            }
        except Exception as e:
            print(f"[标注训练] DuckDB加载失败: {e}")
            return None

    def _show_stock_overview(self, kline_data: Dict, code: str, name: str):
        """显示当前股票指标概览（真实计算数据）"""
        try:
            from kline_annotation_training.pattern_extractor import PatternExtractor
            extractor = PatternExtractor()

            closes = kline_data.get('close', [])
            dates = [str(d)[:10] for d in kline_data.get('dates', [])]

            if len(closes) < 120:
                self.ai_result_text.setPlainText('K线数据不足120根，无法计算完整指标')
                return

            # 计算指标
            ma5 = extractor.calc_ma(closes, 5)
            ma9 = extractor.calc_ma(closes, 9)
            ma10 = extractor.calc_ma(closes, 10)
            ma20 = extractor.calc_ma(closes, 20)
            ma60 = extractor.calc_ma(closes, 60)
            ma120 = extractor.calc_ma(closes, 120)
            macd = extractor.calc_macd(closes)
            kdj = extractor.calc_kdj(kline_data)

            # 最新一日数据
            idx = len(closes) - 1
            latest_close = closes[idx]
            latest_date = dates[idx]

            # 均线趋势
            ma5_trend = '↑' if ma5[idx] > ma5[idx-1] else '↓'
            ma20_trend = '↑' if ma20[idx] > ma20[idx-1] else '↓'

            # 均线排列
            if ma5[idx] > ma9[idx] > ma20[idx]:
                ma_align = '多头排列（MA5>MA9>MA20）'
            elif ma5[idx] < ma9[idx] < ma20[idx]:
                ma_align = '空头排列（MA5<MA9<MA20）'
            else:
                ma_align = '交叉整理'

            # MACD状态
            macd_hist = macd['macd'][idx]
            macd_status = '红柱（多头）' if macd_hist > 0 else '绿柱（空头）'
            macd_trend = '↑扩大' if abs(macd_hist) > abs(macd['macd'][idx-1]) else '↓缩小'

            # KDJ状态
            kdj_k = kdj['k'][idx]
            kdj_d = kdj['d'][idx]
            kdj_j = kdj['j'][idx]
            if kdj_j > 80:
                kdj_status = '超买区（J>80）'
            elif kdj_j < 20:
                kdj_status = '超卖区（J<20）'
            else:
                kdj_status = '正常区间'

            # 成交量
            volumes = kline_data.get('volume', [])
            vol_ma5 = extractor.calc_ma(volumes, 5)
            latest_vol = volumes[idx]
            vol_ratio = latest_vol / vol_ma5[idx] if vol_ma5[idx] > 0 else 1
            vol_type = extractor.classify_volume(latest_vol, vol_ma5[idx])

            # 近期涨跌
            chg_5d = (closes[idx] - closes[idx-5]) / closes[idx-5] * 100 if idx >= 5 else 0
            chg_20d = (closes[idx] - closes[idx-20]) / closes[idx-20] * 100 if idx >= 20 else 0

            # 近期高低点
            high_20d = max(kline_data.get('high', [])[idx-19:idx+1]) if idx >= 19 else 0
            low_20d = min(kline_data.get('low', [])[idx-19:idx+1]) if idx >= 19 else 0
            pos_in_range = (latest_close - low_20d) / (high_20d - low_20d) * 100 if high_20d > low_20d else 50

            lines = []
            lines.append('=' * 55)
            lines.append(f'📊 {name}({code}) 指标概览')
            lines.append(f'   最新交易日: {latest_date}')
            lines.append('=' * 55)
            lines.append('')
            lines.append('【价格】')
            lines.append(f'  收盘价: {latest_close:.2f}')
            lines.append(f'  5日涨跌: {chg_5d:+.2f}%')
            lines.append(f'  20日涨跌: {chg_20d:+.2f}%')
            lines.append(f'  20日区间: {low_20d:.2f} ~ {high_20d:.2f}')
            lines.append(f'  当前位置: {pos_in_range:.0f}% (0%=最低, 100%=最高)')
            lines.append('')
            lines.append('【均线系统】')
            lines.append(f'  MA5:   {ma5[idx]:.2f}  {ma5_trend}')
            lines.append(f'  MA9:   {ma9[idx]:.2f}')
            lines.append(f'  MA10:  {ma10[idx]:.2f}')
            lines.append(f'  MA20:  {ma20[idx]:.2f}  {ma20_trend}')
            lines.append(f'  MA60:  {ma60[idx]:.2f}')
            lines.append(f'  MA120: {ma120[idx]:.2f}')
            lines.append(f'  排列: {ma_align}')
            lines.append('')
            lines.append('【MACD(8,21,5)】')
            lines.append(f'  DIF:  {macd["dif"][idx]:.4f}')
            lines.append(f'  DEA:  {macd["dea"][idx]:.4f}')
            lines.append(f'  MACD柱: {macd_hist:.4f}  {macd_status} {macd_trend}')
            lines.append('')
            lines.append('【KDJ(13,3,3)】')
            lines.append(f'  K: {kdj_k:.2f}')
            lines.append(f'  D: {kdj_d:.2f}')
            lines.append(f'  J: {kdj_j:.2f}  {kdj_status}')
            lines.append('')
            lines.append('【成交量】')
            lines.append(f'  当日成交量: {latest_vol:.0f}')
            lines.append(f'  5日均量:   {vol_ma5[idx]:.0f}')
            lines.append(f'  量比:       {vol_ratio:.2f}')
            lines.append(f'  量能状态:   {vol_type}')
            lines.append('')
            lines.append('---')
            lines.append('💡 使用说明:')
            lines.append('  1. 点击「🟢编辑B点」后，点击K线柱添加买点')
            lines.append('  2. 点击「🔴编辑S点」后，点击K线柱添加卖点')
            lines.append('  3. 填写买卖理由后点击「🤖上传AI分析」')
            lines.append('  4. 分析完成后点击「🧪回测验证」验证规则')
            lines.append('  5. 点击「📚存入案例库」积累学习样本')

            self.ai_result_text.setPlainText('\n'.join(lines))

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.ai_result_text.setPlainText(f'指标概览计算失败: {str(e)}')

    def _on_annotation_changed(self):
        """标注变化时刷新表格"""
        self._refresh_points_table()

    def _refresh_points_table(self):
        """刷新买卖点表格"""
        buy_points = self.kline_editor.annotation_manager.buy_points
        sell_points = self.kline_editor.annotation_manager.sell_points

        self.points_table.setRowCount(0)
        row = 0

        for p in buy_points:
            self.points_table.insertRow(row)
            self.points_table.setItem(row, 0, QTableWidgetItem('🟢 B买入'))
            self.points_table.setItem(row, 1, QTableWidgetItem(p['date']))
            self.points_table.setItem(row, 2, QTableWidgetItem(f"{p['price']:.2f}"))
            self.points_table.setItem(row, 3, QTableWidgetItem(p.get('reason', '')))
            row += 1

        for p in sell_points:
            self.points_table.insertRow(row)
            self.points_table.setItem(row, 0, QTableWidgetItem('🔴 S卖出'))
            self.points_table.setItem(row, 1, QTableWidgetItem(p['date']))
            self.points_table.setItem(row, 2, QTableWidgetItem(f"{p['price']:.2f}"))
            self.points_table.setItem(row, 3, QTableWidgetItem(p.get('reason', '')))
            row += 1

    def _on_save(self):
        """保存标注"""
        if not self.current_kline_data:
            QMessageBox.warning(self, '提示', '请先加载K线数据')
            return

        # 同步理由
        self.kline_editor.annotation_manager.set_buy_reason(self.buy_reason_input.toPlainText())
        self.kline_editor.annotation_manager.set_sell_reason(self.sell_reason_input.toPlainText())

        try:
            filepath = self.kline_editor.annotation_manager.save_to_file()
            self.annotation_saved.emit(filepath)
            QMessageBox.information(self, '保存成功', f'标注已保存到:\n{filepath}')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'保存失败: {str(e)}')

    def _on_load_annotation(self):
        """加载标注文件"""
        save_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'kline_annotations'
        )
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        filepath, _ = QFileDialog.getOpenFileName(
            self, '加载标注文件', save_dir, 'JSON文件 (*.json)'
        )
        if not filepath:
            return

        try:
            mgr = AnnotationManager.load_from_file(filepath)
            self.kline_editor.annotation_manager = mgr
            self.buy_reason_input.setPlainText(mgr.buy_reason)
            self.sell_reason_input.setPlainText(mgr.sell_reason)
            self.code_input.setText(mgr.stock_code)

            # 如果有K线数据，同步显示
            if self.current_kline_data:
                self.kline_editor._sync_points()

            self._refresh_points_table()
            QMessageBox.information(self, '加载成功', f'已加载标注: {mgr.annotation_id}')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'加载失败: {str(e)}')

    def _on_complete(self):
        """完成标注"""
        buy_count = len(self.kline_editor.annotation_manager.buy_points)
        sell_count = len(self.kline_editor.annotation_manager.sell_points)

        if buy_count == 0 and sell_count == 0:
            QMessageBox.warning(self, '提示', '请至少标注一个买卖点')
            return

        # 同步理由
        self.kline_editor.annotation_manager.set_buy_reason(self.buy_reason_input.toPlainText())
        self.kline_editor.annotation_manager.set_sell_reason(self.sell_reason_input.toPlainText())
        self.kline_editor.annotation_manager.complete()

        QMessageBox.information(
            self, '标注完成',
            f'标注已完成！\n\n买点: {buy_count}个\n卖点: {sell_count}个\n\n可以点击「上传AI分析」生成策略规则。'
        )

    def _on_ai_analyze(self):
        """上传AI分析"""
        if not self.current_kline_data:
            QMessageBox.warning(self, '提示', '请先加载K线数据')
            return

        buy_count = len(self.kline_editor.annotation_manager.buy_points)
        sell_count = len(self.kline_editor.annotation_manager.sell_points)
        if buy_count == 0 and sell_count == 0:
            QMessageBox.warning(self, '提示', '请先标注买卖点')
            return

        # 同步理由
        self.kline_editor.annotation_manager.set_buy_reason(self.buy_reason_input.toPlainText())
        self.kline_editor.annotation_manager.set_sell_reason(self.sell_reason_input.toPlainText())

        try:
            self.ai_result_text.setPlainText('AI分析中，请稍候...')

            # 分析标注
            annotation_dict = self.kline_editor.annotation_manager.to_dict()
            analysis = self.ai_analyzer.analyze_annotation(self.current_kline_data, annotation_dict)

            # 生成规则
            rules = self.ai_analyzer.generate_rules([analysis])

            # 生成报告
            report = self.ai_analyzer.generate_report(analysis, rules)
            self.ai_result_text.setPlainText(report)

            # 标记为已分析
            self.kline_editor.annotation_manager.status = 'analyzed'

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.ai_result_text.setPlainText(f'AI分析失败: {str(e)}')
            QMessageBox.critical(self, '错误', f'AI分析失败: {str(e)}')

    def _on_validate(self):
        """回测验证候选规则"""
        if not self.current_kline_data:
            QMessageBox.warning(self, '提示', '请先加载K线数据')
            return

        # 先做AI分析
        self._on_ai_analyze()

        try:
            from kline_annotation_training.validation_bridge import ValidationBridge

            # 重新分析获取规则
            annotation_dict = self.kline_editor.annotation_manager.to_dict()
            analysis = self.ai_analyzer.analyze_annotation(self.current_kline_data, annotation_dict)
            rules = self.ai_analyzer.generate_rules([analysis])

            # 回测验证
            bridge = ValidationBridge()
            report = bridge.validate_and_report(rules.get('candidate_rules', {}), [self.current_kline_data])

            # 显示验证结果
            result_text = self.ai_result_text.toPlainText()
            result_text += '\n\n' + '=' * 60 + '\n'
            result_text += '🧪 回测验证结果\n'
            result_text += '=' * 60 + '\n\n'

            if 'error' in report:
                result_text += f"错误: {report['error']}\n"
            else:
                result_text += f"测试股票数: {report['test_stocks']}\n"
                result_text += f"总交易次数: {report['total_trades']}\n"
                result_text += f"平均收益率: {report['avg_return_pct']}%\n"
                result_text += f"平均胜率: {report['avg_win_rate']}%\n"
                result_text += f"\n建议: {report['recommendation']}\n"

                # 显示每笔交易
                if report.get('individual_results'):
                    result_text += '\n--- 交易明细 ---\n'
                    for r in report['individual_results']:
                        result_text += f"\n策略: {r['strategy_name']}\n"
                        result_text += f"总收益: {r['total_return_pct']}%\n"
                        result_text += f"交易次数: {r['total_trades']}\n"
                        result_text += f"胜率: {r['win_rate']}%\n"
                        result_text += f"平均收益: {r['avg_profit_pct']}%\n"
                        for t in r.get('trades', []):
                            if t['type'] == 'BUY':
                                result_text += f"  买入 {t['date']} @ {t['price']}\n"
                            else:
                                result_text += f"  卖出 {t['date']} @ {t['price']} "
                                result_text += f"({t.get('profit_pct', 0)}%, {t.get('hold_days', 0)}天, {t.get('reason', '')})\n"

            self.ai_result_text.setPlainText(result_text)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'回测验证失败: {str(e)}')

    def _on_save_to_case_db(self):
        """保存标注到案例库"""
        if not self.current_kline_data:
            QMessageBox.warning(self, '提示', '请先加载K线数据')
            return

        buy_count = len(self.kline_editor.annotation_manager.buy_points)
        if buy_count == 0:
            QMessageBox.warning(self, '提示', '请至少标注一个买点')
            return

        try:
            from kline_annotation_training.case_database import CaseDatabase

            # 同步理由
            self.kline_editor.annotation_manager.set_buy_reason(self.buy_reason_input.toPlainText())
            self.kline_editor.annotation_manager.set_sell_reason(self.sell_reason_input.toPlainText())

            # AI分析
            annotation_dict = self.kline_editor.annotation_manager.to_dict()
            analysis = self.ai_analyzer.analyze_annotation(self.current_kline_data, annotation_dict)

            # 存入案例库
            db = CaseDatabase()
            case_ids = db.add_cases_from_analysis(
                analysis,
                stock_code=self.code_input.text().strip(),
                stock_name=self.code_input.text().strip()
            )

            stats = db.get_case_stats()
            QMessageBox.information(
                self, '保存成功',
                f'已存入 {len(case_ids)} 个案例\n\n'
                f'案例库统计：\n'
                f'总案例: {stats["total_cases"]}\n'
                f'成功: {stats["success_count"]}\n'
                f'失败: {stats["failure_count"]}\n'
                f'待观察: {stats["pending_count"]}'
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'存入案例库失败: {str(e)}')

    def _on_compare_cases(self):
        """成败对比分析"""
        try:
            from kline_annotation_training.case_database import CaseDatabase

            db = CaseDatabase()
            report = db.generate_comparison_report()

            # 追加到AI结果区域
            result_text = self.ai_result_text.toPlainText()
            result_text += '\n\n' + report
            self.ai_result_text.setPlainText(result_text)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'成败对比失败: {str(e)}')
