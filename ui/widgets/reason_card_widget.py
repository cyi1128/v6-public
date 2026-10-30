# -*- coding: utf-8 -*-
"""
V1.3-A-4-DEV Step2：涨停原因卡片组件（PyQt）
独立UI展示组件，只负责渲染，不修改FROZEN核心算法。

通过 ui/limit_up_reason_card.py 提供的 card_data 结构渲染。
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QPalette


# ========== 颜色配置 ==========
COLORS = {
    'bg_card': '#1E1E2E',
    'bg_section': '#252538',
    'bg_header': '#2D2D44',
    'border': '#3A3A5C',
    'text_primary': '#E0E0E0',
    'text_secondary': '#A0A0B0',
    'text_muted': '#707080',
    'level_A': '#FF4444',
    'level_A_bg': '#3D1A1A',
    'level_B': '#FFAA00',
    'level_B_bg': '#3D2E1A',
    'level_C': '#888888',
    'level_C_bg': '#2A2A2A',
    'success': '#44DD44',
    'warning': '#FFAA00',
    'danger': '#FF4444',
    'info': '#44AAFF',
    'hot': '#FF6644',
}


class ReasonCardWidget(QWidget):
    """
    涨停原因卡片组件

    输入：ui.limit_up_reason_card.format_reason_card() 返回的 card_data
    输出：可视化卡片
    """

    def __init__(self, card_data=None, parent=None):
        super().__init__(parent)
        self.card_data = card_data or {}
        self._init_ui()
        if card_data:
            self.set_data(card_data)

    def _init_ui(self):
        """初始化UI结构"""
        self.setMinimumWidth(380)
        self.setMaximumWidth(480)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['bg_card']};
                color: {COLORS['text_primary']};
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
        """)

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. 头部区域（股票信息 + 可信度）
        self.header = self._create_header()
        self.main_layout.addWidget(self.header)

        # 2. 涨停方向
        self.theme_section = self._create_section('涨停方向')
        self.theme_label = QLabel('--')
        self.theme_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 16px;
            font-weight: bold;
            padding: 8px 16px;
            background-color: {COLORS['bg_section']};
        """)
        self.theme_section.layout().addWidget(self.theme_label)
        self.main_layout.addWidget(self.theme_section)

        # 2.5 概念题材标签
        self.concept_section = self._create_section('概念题材')
        self.concept_layout = QVBoxLayout()
        self.concept_layout.setContentsMargins(16, 8, 16, 8)
        self.concept_layout.setSpacing(6)
        self.concept_section.layout().addLayout(self.concept_layout)
        self.main_layout.addWidget(self.concept_section)

        # 2.6 涨停强度（V1.3-A-4.1新增，仅展示，不参与评分）
        self.strength_section = self._create_section('涨停强度')
        self.strength_layout = QGridLayout()
        self.strength_layout.setContentsMargins(16, 8, 16, 8)
        self.strength_layout.setHorizontalSpacing(16)
        self.strength_layout.setVerticalSpacing(6)
        self.strength_section.layout().addLayout(self.strength_layout)
        self.main_layout.addWidget(self.strength_section)

        # 3. 核心依据
        self.evidence_section = self._create_section('核心依据')
        self.evidence_layout = QVBoxLayout()
        self.evidence_layout.setContentsMargins(16, 8, 16, 8)
        self.evidence_layout.setSpacing(4)
        self.evidence_section.layout().addLayout(self.evidence_layout)
        self.main_layout.addWidget(self.evidence_section)

        # 3.5 详细依据
        self.detail_section = self._create_section('详细依据')
        self.detail_layout = QVBoxLayout()
        self.detail_layout.setContentsMargins(16, 8, 16, 8)
        self.detail_layout.setSpacing(4)
        self.detail_section.layout().addLayout(self.detail_layout)
        self.main_layout.addWidget(self.detail_section)

        # 4. 评分拆解
        self.score_section = self._create_section('评分拆解')
        self.score_grid = QGridLayout()
        self.score_grid.setContentsMargins(16, 8, 16, 8)
        self.score_grid.setHorizontalSpacing(16)
        self.score_grid.setVerticalSpacing(4)
        self.score_section.layout().addLayout(self.score_grid)
        self.main_layout.addWidget(self.score_section)

        # 4.5 AI短线总结（V1.3-A-4.1 Step2，规则生成，仅展示）
        self.ai_section = self._create_section('AI短线总结')
        self.ai_layout = QVBoxLayout()
        self.ai_layout.setContentsMargins(16, 8, 16, 8)
        self.ai_layout.setSpacing(6)
        self.ai_section.layout().addLayout(self.ai_layout)
        self.main_layout.addWidget(self.ai_section)

        # 5. 风险提示
        self.risk_section = self._create_section('风险提示')
        self.risk_layout = QVBoxLayout()
        self.risk_layout.setContentsMargins(16, 8, 16, 8)
        self.risk_layout.setSpacing(4)
        self.risk_section.layout().addLayout(self.risk_layout)
        self.main_layout.addWidget(self.risk_section)

        # 底部间距
        self.main_layout.addStretch()

    def _create_header(self):
        """创建头部区域"""
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_header']};
                border-bottom: 2px solid {COLORS['border']};
            }}
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 左侧：股票名称+代码
        left_layout = QVBoxLayout()
        left_layout.setSpacing(2)

        self.stock_name_label = QLabel('--')
        self.stock_name_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 18px;
            font-weight: bold;
        """)

        self.stock_code_label = QLabel('--')
        self.stock_code_label.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
        """)

        left_layout.addWidget(self.stock_name_label)
        left_layout.addWidget(self.stock_code_label)
        # 股票基本信息（行业、涨跌幅、换手、连板）
        self.stock_info_label = QLabel('')
        self.stock_info_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 11px;
            padding-top: 2px;
        """)
        self.stock_info_label.setWordWrap(True)
        left_layout.addWidget(self.stock_info_label)
        layout.addLayout(left_layout)

        layout.addStretch()

        # 右侧：可信度标签
        self.confidence_label = QLabel('--')
        self.confidence_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.confidence_label.setMinimumWidth(90)
        self.confidence_label.setMinimumHeight(40)
        self.confidence_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
            border-radius: 6px;
            padding: 6px 12px;
            background-color: {COLORS['level_C_bg']};
            border: 1px solid {COLORS['level_C']};
        """)
        layout.addWidget(self.confidence_label)

        return header

    def _create_section(self, title):
        """创建分区容器"""
        section = QFrame()
        section.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_section']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 11px;
            font-weight: bold;
            padding: 6px 16px;
            background-color: {COLORS['bg_card']};
            border-bottom: 1px solid {COLORS['border']};
            letter-spacing: 1px;
        """)
        layout.addWidget(title_label)

        return section

    def set_data(self, card_data):
        """设置卡片数据并刷新显示"""
        self.card_data = card_data
        self._refresh()

    def _refresh(self):
        """刷新所有区域显示"""
        data = self.card_data
        if not data:
            return

        # 1. 头部
        basic = data.get('basic_info', {})
        self.stock_name_label.setText(basic.get('name', '--'))
        self.stock_code_label.setText(basic.get('code', '--'))
        # 股票基本信息
        self._build_stock_info(data)

        confidence = data.get('confidence', {})
        level = confidence.get('level', 'C')
        score = confidence.get('score', 0)
        self._set_confidence_style(level, score)

        # 2. 涨停方向
        core_theme = data.get('core_theme', {})
        theme = core_theme.get('theme', '--')
        self.theme_label.setText(f"  {theme}")

        # 2.5 概念题材标签
        self._build_concepts(data)

        # 2.6 涨停强度（V1.3-A-4.1新增）
        self._build_limit_up_strength(data)

        # 3. 核心依据
        self._build_evidence(data)

        # 3.5 详细依据
        self._build_detail_evidence(data)

        # 4. 评分拆解
        self._build_score_breakdown(data)

        # 4.5 AI短线总结
        self._build_ai_summary(data)

        # 5. 风险提示
        self._build_risk_warnings(data)

    def _set_confidence_style(self, level, score):
        """设置可信度标签样式"""
        color_key = f'level_{level}'
        bg_key = f'level_{level}_bg'
        color = COLORS.get(color_key, COLORS['level_C'])
        bg = COLORS.get(bg_key, COLORS['level_C_bg'])

        level_text = {'A': 'A级', 'B': 'B级', 'C': 'C级'}.get(level, 'C级')
        self.confidence_label.setText(f"{level_text}\n{int(score)}分")
        self.confidence_label.setStyleSheet(f"""
            color: {color};
            font-size: 13px;
            font-weight: bold;
            border-radius: 6px;
            padding: 4px 10px;
            background-color: {bg};
            border: 2px solid {color};
        """)

    def _build_evidence(self, data):
        """构建核心依据列表"""
        # 清空旧内容
        while self.evidence_layout.count():
            item = self.evidence_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 主营依据
        business = data.get('business', {})
        if business:
            icon = business.get('icon', '❓')
            text = business.get('text', '--')
            level = business.get('level', '--')
            score = business.get('score', 0)
            self._add_evidence_item(
                f"{icon} 主营：{text}（{level}级 +{score}）",
                COLORS['success'] if business.get('is_supported') else COLORS['danger']
            )

        # 热点依据
        hot = data.get('hot', {})
        if hot and hot.get('is_hot'):
            reason = hot.get('reason', '')
            source = hot.get('source', '')
            relation = hot.get('relation_text', '')
            self._add_evidence_item(f"🔥 热点：{reason}", COLORS['hot'])
            self._add_evidence_item(
                f"   来源：{source} | 强度：{relation}",
                COLORS['text_muted'], small=True
            )

        # 公告依据
        announcement = data.get('announcement', {})
        if announcement:
            icon = announcement.get('icon', '❓')
            text = announcement.get('text', '--')
            # 使用预格式化的catalyst_text，避免显示原始字典
            catalyst_text = announcement.get('catalyst_text', '')
            catalyst_display = f"（{catalyst_text}）" if catalyst_text else ''
            color = COLORS['success'] if announcement.get('is_level1') else COLORS['text_secondary']
            self._add_evidence_item(f"{icon} 公告：{text}{catalyst_display}", color)

        # 新闻依据
        news = data.get('news', {})
        if news and news.get('has_news'):
            news_title = news.get('title', '')
            news_source = news.get('source', '')
            news_keyword = news.get('keyword', '')
            if news_title:
                # 有具体新闻标题，显示详细内容
                display = f"📰 新闻：{news_title}"
                self._add_evidence_item(display, COLORS['info'])
                if news_source or news_keyword:
                    source_text = f"   来源：{news_source}" if news_source else ''
                    if news_keyword:
                        source_text += f" | 关键词：{news_keyword}"
                    self._add_evidence_item(source_text, COLORS['text_muted'], small=True)
            else:
                self._add_evidence_item(f"📰 新闻：存在新闻催化", COLORS['info'])

    def _add_evidence_item(self, text, color, small=False):
        """添加一条核心依据"""
        label = QLabel(text)
        font_size = 11 if small else 13
        label.setStyleSheet(f"""
            color: {color};
            font-size: {font_size}px;
            padding: 2px 0;
        """)
        label.setWordWrap(True)
        self.evidence_layout.addWidget(label)

    def _build_stock_info(self, data):
        """构建股票基本信息栏"""
        stock_info = data.get('stock_info', {})
        if not stock_info:
            self.stock_info_label.setText('')
            return

        industry = stock_info.get('industry', '')
        pct_chg = stock_info.get('pct_chg', 0)
        turnover = stock_info.get('turnover_rate', 0)
        amount = stock_info.get('amount', 0)
        consecutive = stock_info.get('consecutive_days', 1)
        price = stock_info.get('price', 0)

        # 格式化成交额（亿元）
        if amount >= 100000000:
            amount_str = f"{amount/100000000:.1f}亿"
        elif amount >= 10000:
            amount_str = f"{amount/10000:.0f}万"
        else:
            amount_str = f"{amount:.0f}"

        parts = []
        if industry:
            parts.append(f"行业：{industry}")
        if price:
            parts.append(f"现价：{price:.2f}")
        if pct_chg:
            parts.append(f"涨幅：+{pct_chg:.2f}%")
        if turnover:
            parts.append(f"换手：{turnover:.1f}%")
        if amount:
            parts.append(f"成交额：{amount_str}")
        if consecutive > 1:
            parts.append(f"{consecutive}连板")

        self.stock_info_label.setText(' | '.join(parts))

    def _build_concepts(self, data):
        """构建概念题材标签"""
        # 清空旧内容
        while self.concept_layout.count():
            item = self.concept_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        concepts = data.get('concepts', [])
        if not concepts:
            empty_label = QLabel('暂无概念标签')
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
            self.concept_layout.addWidget(empty_label)
            return

        # 概念标签颜色循环
        concept_colors = [
            ('#FF6B6B', '#3D1A1A'),  # 红
            ('#4ECDC4', '#1A3D3A'),  # 青
            ('#FFE66D', '#3D3A1A'),  # 黄
            ('#95E1D3', '#1A3D35'),  # 绿
            ('#DDA0DD', '#3D1A3D'),  # 紫
            ('#87CEEB', '#1A2E3D'),  # 蓝
            ('#FFA07A', '#3D281A'),  # 橙
        ]

        # 每行最多4个标签
        row_layout = None
        for i, concept in enumerate(concepts):
            if i % 4 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(6)
                self.concept_layout.addLayout(row_layout)

            color_idx = i % len(concept_colors)
            text_color, bg_color = concept_colors[color_idx]

            tag = QLabel(concept)
            tag.setStyleSheet(f"""
                color: {text_color};
                background-color: {bg_color};
                border: 1px solid {text_color};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            """)
            tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(tag)

        # 数据来源
        source = data.get('concept_source', '')
        if source:
            source_label = QLabel(f"数据来源：{source}")
            source_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; padding-top: 4px;")
            self.concept_layout.addWidget(source_label)

    def _build_limit_up_strength(self, data):
        """构建涨停强度展示（V1.3-A-4.1新增，仅展示，不参与评分）"""
        # 清空旧内容
        while self.strength_layout.count():
            item = self.strength_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        strength = data.get('limit_up_strength', {})
        if not strength:
            empty_label = QLabel('暂无涨停强度数据')
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
            self.strength_layout.addWidget(empty_label, 0, 0, 1, 4)
            return

        # 格式化封单金额
        seal_amount = strength.get('seal_amount', 0)
        if seal_amount >= 100000000:
            seal_text = f"{seal_amount / 100000000:.2f}亿"
        elif seal_amount >= 10000:
            seal_text = f"{seal_amount / 10000:.0f}万"
        else:
            seal_text = f"{seal_amount:.0f}"

        # 封板质量星级（纯展示，根据炸板次数和封板时间计算）
        break_count = strength.get('break_count', 0)
        first_time = strength.get('first_limit_time', '')
        if break_count == 0:
            if first_time and first_time < '10:00:00':
                quality_stars = '★★★★★'
                quality_text = '强势一字板'
            else:
                quality_stars = '★★★★☆'
                quality_text = '封板稳定'
        elif break_count <= 1:
            quality_stars = '★★★★☆'
            quality_text = '封板较稳'
        elif break_count <= 3:
            quality_stars = '★★★☆☆'
            quality_text = '有反复'
        else:
            quality_stars = '★★☆☆☆'
            quality_text = '分歧较大'

        # 展示字段：连板、首次封板、最后封板、封单、封单强度、炸板、封板质量
        seal_ratio = strength.get('seal_ratio', 0)
        seal_ratio_text = f"{seal_ratio:.2f}%" if seal_ratio > 0 else '--'

        items = [
            ('连板高度', f"{strength.get('consecutive_days', 1)}板"),
            ('首次封板', first_time or '--'),
            ('最后封板', strength.get('last_limit_time', '') or '--'),
            ('封单金额', seal_text),
            ('封单强度', seal_ratio_text),
            ('炸板次数', f"{break_count}次"),
            ('封板质量', f"{quality_stars} {quality_text}"),
        ]

        for i, (label, value) in enumerate(items):
            row = i // 2
            col = (i % 2) * 2

            label_widget = QLabel(label)
            label_widget.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
            self.strength_layout.addWidget(label_widget, row, col)

            value_widget = QLabel(value)
            # 封板质量用金色
            if label == '封板质量':
                value_widget.setStyleSheet(f"color: #FFD700; font-size: 12px; font-weight: bold;")
            elif label == '炸板次数' and break_count > 2:
                value_widget.setStyleSheet(f"color: #FF6B6B; font-size: 12px; font-weight: bold;")
            elif label == '连板高度' and strength.get('consecutive_days', 1) >= 3:
                value_widget.setStyleSheet(f"color: #FF6B6B; font-size: 12px; font-weight: bold;")
            elif label == '封单强度' and seal_ratio >= 1.0:
                value_widget.setStyleSheet(f"color: #FF6B6B; font-size: 12px; font-weight: bold;")
            elif label == '封单强度' and seal_ratio >= 0.3:
                value_widget.setStyleSheet(f"color: #FFD700; font-size: 12px; font-weight: bold;")
            else:
                value_widget.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 12px; font-weight: bold;")
            self.strength_layout.addWidget(value_widget, row, col + 1)

    def _build_detail_evidence(self, data):
        """构建详细依据列表"""
        # 清空旧内容
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        evidence_detail = data.get('evidence_detail', [])
        if not evidence_detail:
            empty_label = QLabel('暂无详细依据')
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
            self.detail_layout.addWidget(empty_label)
            return

        for ev in evidence_detail:
            text = ev.get('text', '') if isinstance(ev, dict) else str(ev)
            if not text:
                continue
            # 截断过长文本
            if len(text) > 120:
                text = text[:120] + '...'

            label = QLabel(f"• {text}")
            label.setStyleSheet(f"""
                color: {COLORS['text_secondary']};
                font-size: 11px;
                padding: 1px 0;
            """)
            label.setWordWrap(True)
            self.detail_layout.addWidget(label)

    def _build_score_breakdown(self, data):
        """构建评分拆解网格"""
        # 清空旧内容
        while self.score_grid.count():
            item = self.score_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        breakdown = data.get('score_breakdown', [])
        total = data.get('total_score', 0)

        row = 0
        for item in breakdown:
            label = item.get('label', '--')
            score = item.get('score', 0)

            # 标签
            label_widget = QLabel(label)
            label_widget.setStyleSheet(f"""
                color: {COLORS['text_secondary']};
                font-size: 12px;
            """)
            self.score_grid.addWidget(label_widget, row, 0)

            # 分数
            score_widget = QLabel(f"+{score}")
            score_color = COLORS['success'] if score > 0 else COLORS['text_muted']
            score_widget.setStyleSheet(f"""
                color: {score_color};
                font-size: 12px;
                font-weight: bold;
            """)
            score_widget.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.score_grid.addWidget(score_widget, row, 1)

            row += 1

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLORS['border']};")
        self.score_grid.addWidget(sep, row, 0, 1, 2)
        row += 1

        # 总分
        total_label = QLabel('总分')
        total_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 13px;
            font-weight: bold;
        """)
        self.score_grid.addWidget(total_label, row, 0)

        total_score = QLabel(f"{total}")
        total_score.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        total_score.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.score_grid.addWidget(total_score, row, 1)

    def _build_ai_summary(self, data):
        """构建AI短线总结（规则生成，仅展示，不参与评分）"""
        # 清空旧内容
        while self.ai_layout.count():
            item = self.ai_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        ai = data.get('ai_summary', {})
        if not ai:
            empty_label = QLabel('暂无AI总结')
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
            self.ai_layout.addWidget(empty_label)
            return

        # 定位标签
        position = ai.get('position', '')
        if position:
            pos_label = QLabel(f"定位：{position}")
            pos_label.setStyleSheet(f"""
                color: {COLORS['text_primary']};
                font-size: 13px;
                font-weight: bold;
                padding-bottom: 4px;
            """)
            self.ai_layout.addWidget(pos_label)

        # 四维度星级
        stars_grid = QGridLayout()
        stars_grid.setHorizontalSpacing(16)
        stars_grid.setVerticalSpacing(4)

        dimensions = [
            ('上涨逻辑', ai.get('logic_stars', 0), ai.get('logic_desc', '')),
            ('热点强度', ai.get('hot_stars', 0), ai.get('hot_desc', '')),
            ('资金认可', ai.get('fund_stars', 0), ai.get('fund_desc', '')),
            ('风险等级', ai.get('risk_stars', 0), ai.get('risk_desc', '')),
        ]

        for i, (label, stars, stars_text) in enumerate(dimensions):
            row = i // 2
            col = (i % 2) * 2

            label_widget = QLabel(label)
            label_widget.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
            stars_grid.addWidget(label_widget, row, col)

            # 风险星级用红色，其他用金色
            if label == '风险等级':
                star_color = '#FF6B6B' if stars >= 4 else '#FFD700'
            else:
                star_color = '#FFD700' if stars >= 4 else COLORS['text_secondary']

            stars_widget = QLabel(stars_text)
            stars_widget.setStyleSheet(f"color: {star_color}; font-size: 13px; font-weight: bold;")
            stars_grid.addWidget(stars_widget, row, col + 1)

        self.ai_layout.addLayout(stars_grid)

        # 综合总结
        summary = ai.get('summary', '')
        if summary:
            summary_label = QLabel(summary)
            summary_label.setStyleSheet(f"""
                color: {COLORS['text_secondary']};
                font-size: 12px;
                padding-top: 6px;
                line-height: 1.5;
            """)
            summary_label.setWordWrap(True)
            self.ai_layout.addWidget(summary_label)

        # 免责声明
        disclaimer = QLabel('※ 以上为规则推理总结，仅供参考，不构成投资建议')
        disclaimer.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; padding-top: 4px;")
        self.ai_layout.addWidget(disclaimer)

    def _build_risk_warnings(self, data):
        """构建风险提示列表"""
        # 清空旧内容
        while self.risk_layout.count():
            item = self.risk_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        warnings = data.get('risk_warnings', [])
        if not warnings:
            label = QLabel("✅ 无明显风险提示")
            label.setStyleSheet(f"""
                color: {COLORS['success']};
                font-size: 12px;
                padding: 4px 0;
            """)
            self.risk_layout.addWidget(label)
            return

        for w in warnings:
            level = w.get('level', 'info')
            text = w.get('text', '')
            color = {
                'warning': COLORS['warning'],
                'danger': COLORS['danger'],
                'info': COLORS['info'],
            }.get(level, COLORS['text_secondary'])

            label = QLabel(text)
            label.setStyleSheet(f"""
                color: {color};
                font-size: 12px;
                padding: 2px 0;
            """)
            label.setWordWrap(True)
            self.risk_layout.addWidget(label)


# ========== 测试代码 ==========
if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget

    # 导入数据接口
    sys.path.insert(0, '.')
    from ui.limit_up_reason_card import analyze_and_format

    app = QApplication(sys.argv)

    # 测试样本
    test_cases = [
        ('000815', '美利云', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 3, 'trade_date': '20260804'}),
        ('600666', '奥瑞德', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 1, 'trade_date': '20260804'}),
        ('300615', '欣天科技', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 2, 'trade_date': '20260804'}),
    ]

    # 主窗口
    window = QMainWindow()
    window.setWindowTitle('V1.3-A-4 Step2 原因卡片组件测试')
    window.setMinimumSize(1500, 700)

    central = QWidget()
    layout = QHBoxLayout(central)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(20)

    print('=' * 80)
    print('V1.3-A-4-DEV Step2：原因卡片组件测试')
    print('=' * 80)

    for code, name, limit_data in test_cases:
        print(f'\n正在分析：{name}({code})...')
        try:
            card_data = analyze_and_format(code, name, limit_data)
            card_data['code'] = code
            card_data['name'] = name

            card = ReasonCardWidget(card_data)
            layout.addWidget(card)

            confidence = card_data.get('confidence', {})
            print(f"  ✅ {name}: {confidence.get('level')}级 {confidence.get('score')}分")
        except Exception as e:
            print(f"  ❌ {name} 失败: {e}")
            import traceback
            traceback.print_exc()

    window.setCentralWidget(central)
    window.show()

    print(f'\n{"=" * 80}')
    print('组件渲染完成，窗口已显示')
    print('关闭窗口后退出测试')
    print('=' * 80)

    sys.exit(app.exec_())
