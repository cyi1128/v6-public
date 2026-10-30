# -*- coding: utf-8 -*-
"""
交易决策中心模块
V1.1-3.6-A 新增

定位：
纯决策解释层，把已有分析结果转化为可执行的交易行动建议。

原则：
- 不修改任何冻结模块
- 不改变评分模型
- 不改变B1-B6事件逻辑
- 不改变R2评级
- 不改变机会池规则
- 只读取已有结果
- 独立模块，可删除
"""

from datetime import datetime


class TradeDecisionCenter:
    """交易决策中心"""

    def __init__(self):
        # 决策等级定义
        self.decision_levels = {
            'focus_buy': {
                'name': '关注买入',
                'icon': '🟢',
                'description': '基本面+技术面共振，等待买点确认',
            },
            'watch_closely': {
                'name': '重点观察',
                'icon': '🟡',
                'description': '有事件催化，等待技术确认',
            },
            'keep_tracking': {
                'name': '持续跟踪',
                'icon': '🔵',
                'description': '有潜力因素，等待催化',
            },
            'avoid_risk': {
                'name': '风险回避',
                'icon': '🔴',
                'description': '高位风险或结构破坏，降低关注',
            },
        }

        # 仓位建议（仅供参考）
        self.position_suggestions = {
            '强烈关注': {'min': 10, 'max': 20, 'unit': '%'},
            '适度关注': {'min': 5, 'max': 10, 'unit': '%'},
            '观察': {'min': 0, 'max': 5, 'unit': '%'},
            '暂无明显信号': {'min': 0, 'max': 0, 'unit': '%'},
        }

    def analyze_decision(self, stock_data):
        """
        分析交易决策

        参数：
            stock_data: 股票数据dict，包含：
                - code: 股票代码
                - name: 股票名称
                - score: 综合评分
                - rating: R2评级
                - event_count: 事件数量
                - event_list: 事件列表
                - resonance_name: 共振名称
                - resonance_confidence: 共振可信度
                - chanlun_state: 缠论状态
                - risk_level: 风险等级
                - current_price: 当前价格
                - ma5: 5日均线
                - ma10: 10日均线
                - ma20: 20日均线
                - macd: MACD状态
                - kdj: KDJ状态
                - volume_ratio: 量比

        返回：
            dict: 决策分析结果
        """
        result = {
            'code': stock_data.get('code', ''),
            'name': stock_data.get('name', ''),
            'score': stock_data.get('score', 0),
            'rating': stock_data.get('rating', ''),
            'event_count': stock_data.get('event_count', 0),
            'event_list': stock_data.get('event_list', []),
            'resonance_name': stock_data.get('resonance_name', ''),
            'resonance_confidence': stock_data.get('resonance_confidence', ''),
            'decision_level': 'keep_tracking',
            'decision_name': '持续跟踪',
            'decision_icon': '🔵',
            'decision_description': '',
            'position_suggestion': '',
            'buy_conditions': [],
            'risk_conditions': [],
            'ai_reason': '',
            'action_suggestion': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # 1. 判断决策等级
        result['decision_level'] = self._classify_decision(stock_data)
        level_info = self.decision_levels.get(result['decision_level'], {})
        result['decision_name'] = level_info.get('name', '持续跟踪')
        result['decision_icon'] = level_info.get('icon', '🔵')
        result['decision_description'] = level_info.get('description', '')

        # 2. 仓位建议
        result['position_suggestion'] = self._get_position_suggestion(stock_data)

        # 3. 买入条件
        result['buy_conditions'] = self._generate_buy_conditions(stock_data)

        # 4. 风险条件
        result['risk_conditions'] = self._generate_risk_conditions(stock_data)

        # 5. AI决策理由
        result['ai_reason'] = self._generate_ai_reason(stock_data, result)

        # 6. 行动建议
        result['action_suggestion'] = self._generate_action_suggestion(stock_data, result)

        return result

    def _classify_decision(self, stock_data):
        """
        对决策进行分级

        返回：
            str: 决策等级
        """
        score = stock_data.get('score', 0)
        rating = stock_data.get('rating', '')
        event_count = stock_data.get('event_count', 0)
        risk_level = stock_data.get('risk_level', '中')
        chanlun_state = stock_data.get('chanlun_state', '')

        # 风险回避：高位风险或顶部结构
        if risk_level == '高' or '顶背驰' in chanlun_state or '顶部' in chanlun_state or '三卖' in chanlun_state:
            return 'avoid_risk'

        # 关注买入：评分≥80 + 有事件 + 技术支持
        if score >= 80 and event_count >= 1 and self._has_tech_support(chanlun_state):
            return 'focus_buy'

        # 重点观察：评分70-79 或 有事件但技术未确认
        if 70 <= score <= 79 or (event_count >= 1 and not self._has_tech_support(chanlun_state)):
            return 'watch_closely'

        # 持续跟踪：评分50-69 或 有潜力因素
        if 50 <= score <= 69:
            return 'keep_tracking'

        # 默认：持续跟踪
        return 'keep_tracking'

    def _has_tech_support(self, chanlun_state):
        """判断是否有技术面支持"""
        support_states = ['三买', '二买', '一买', '趋势延伸', '底部背驰', '中枢震荡（下沿测试）']
        for s in support_states:
            if s in chanlun_state:
                return True
        return False

    def _get_position_suggestion(self, stock_data):
        """获取仓位建议"""
        rating = stock_data.get('rating', '')
        risk_level = stock_data.get('risk_level', '中')

        pos_info = self.position_suggestions.get(rating, {'min': 0, 'max': 0, 'unit': '%'})
        
        # 高位风险降低仓位
        if risk_level == '高':
            return f"≤{pos_info['min']}%（注意高位风险）"
        
        if pos_info['min'] == 0 and pos_info['max'] == 0:
            return "暂不建议建仓"
        
        return f"{pos_info['min']}%-{pos_info['max']}%"

    def _generate_buy_conditions(self, stock_data):
        """生成买入等待条件"""
        conditions = []
        
        ma5 = stock_data.get('ma5', 0)
        ma20 = stock_data.get('ma20', 0)
        current_price = stock_data.get('current_price', 0)
        chanlun_state = stock_data.get('chanlun_state', '')

        # 均线条件
        if ma5 and ma20 and current_price:
            if current_price < ma5:
                conditions.append(f"股价重新站上MA5（{ma5:.2f}）")
            else:
                conditions.append(f"MA5（{ma5:.2f}）保持向上")

        # 成交量条件
        volume_ratio = stock_data.get('volume_ratio', 0)
        if volume_ratio > 0:
            conditions.append(f"成交量放大（量比>{volume_ratio:.1f}）")
        else:
            conditions.append("成交量温和放大")

        # MACD条件
        macd = stock_data.get('macd', '')
        if macd:
            conditions.append(f"MACD {macd}")
        else:
            conditions.append("MACD红柱扩大")

        # KDJ条件
        kdj = stock_data.get('kdj', '')
        if kdj:
            conditions.append(f"KDJ {kdj}")
        else:
            conditions.append("KDJ金叉向上")

        # 缠论条件
        if '三买' in chanlun_state:
            conditions.append("缠论三买结构确认")
        elif '二买' in chanlun_state:
            conditions.append("缠论二买结构确认")
        elif '中枢' in chanlun_state:
            conditions.append("中枢震荡结束，方向选择")

        return conditions[:5]  # 最多显示5个条件

    def _generate_risk_conditions(self, stock_data):
        """生成风险条件"""
        risks = []
        
        ma20 = stock_data.get('ma20', 0)
        current_price = stock_data.get('current_price', 0)
        chanlun_state = stock_data.get('chanlun_state', '')

        # 均线风险
        if ma20 and current_price:
            risks.append(f"跌破MA20（{ma20:.2f}）")

        # 缠论风险
        if '背驰' in chanlun_state:
            risks.append("顶背驰确认")
        elif '顶部' in chanlun_state:
            risks.append("顶部结构形成")
        elif '三卖' in chanlun_state:
            risks.append("缠论三卖出现")

        # 事件风险
        event_count = stock_data.get('event_count', 0)
        if event_count > 0:
            risks.append("事件催化衰减（超过90天）")

        # 通用风险
        risks.append("成交量持续萎缩")
        risks.append("大盘系统性风险")

        return risks[:5]  # 最多显示5个风险

    def _generate_ai_reason(self, stock_data, result):
        """生成AI决策理由"""
        reasons = []

        score = stock_data.get('score', 0)
        rating = stock_data.get('rating', '')
        event_count = stock_data.get('event_count', 0)
        resonance_name = stock_data.get('resonance_name', '')
        chanlun_state = stock_data.get('chanlun_state', '')
        risk_level = stock_data.get('risk_level', '中')

        # 评分理由
        if score >= 80:
            reasons.append(f"综合评分{score}分，处于{rating}区间")
        elif score >= 70:
            reasons.append(f"综合评分{score}分，处于{rating}区间")
        else:
            reasons.append(f"综合评分{score}分，暂不构成买入条件")

        # 事件理由
        if event_count >= 2:
            reasons.append(f"{event_count}个事件催化，{resonance_name}")
        elif event_count == 1:
            reasons.append("有1个事件催化")
        else:
            reasons.append("暂无明显事件催化")

        # 技术理由
        if self._has_tech_support(chanlun_state):
            reasons.append(f"缠论{chanlun_state}，技术面支持")
        else:
            reasons.append(f"缠论{chanlun_state}，等待技术确认")

        # 风险理由
        if risk_level == '高':
            reasons.append("注意高位风险")
        elif risk_level == '中':
            reasons.append("风险中等")
        else:
            reasons.append("风险较低")

        return "，".join(reasons)

    def _generate_action_suggestion(self, stock_data, result):
        """生成行动建议"""
        level = result['decision_level']
        rating = stock_data.get('rating', '')
        chanlun_state = stock_data.get('chanlun_state', '')

        if level == 'focus_buy':
            if '三买' in chanlun_state:
                return "缠论三买确认，可逢低分批建仓，不追高"
            elif '二买' in chanlun_state:
                return "缠论二买确认，等待回踩确认后介入"
            else:
                return "基本面+技术面共振，等待回踩买点确认"
        
        elif level == 'watch_closely':
            return "有事件催化，加入重点观察，等待技术面确认"
        
        elif level == 'keep_tracking':
            return "持续跟踪，等待催化因素出现"
        
        elif level == 'avoid_risk':
            return "高位风险或结构破坏，降低关注，回避为主"
        
        return "持续观察"

    def format_decision_report(self, decision):
        """
        格式化决策报告为文本

        参数：
            decision: analyze_decision的结果

        返回：
            str: 格式化的报告文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"{decision['decision_icon']} AI交易决策中心")
        lines.append("=" * 60)
        lines.append(f"股票：{decision['name']}({decision['code']})")
        lines.append(f"综合评分：{decision['score']}分")
        lines.append(f"信号评级：{decision['rating']}")
        lines.append("")

        # 事件驱动
        lines.append("【事件驱动】")
        lines.append(f"  事件数量：{decision.get('event_count', 0)}个")
        if decision.get('resonance_name'):
            lines.append(f"  共振等级：{decision['resonance_name']}")
        lines.append("")

        # 当前状态
        lines.append("【当前状态】")
        lines.append(f"  决策等级：{decision['decision_icon']} {decision['decision_name']}")
        lines.append(f"  {decision['decision_description']}")
        lines.append("")

        # 交易建议
        lines.append("【交易建议】")
        lines.append(f"  {decision['action_suggestion']}")
        lines.append(f"  建议仓位：{decision['position_suggestion']}")
        lines.append("")

        # 买入条件
        if decision['buy_conditions']:
            lines.append("【买入等待条件】")
            for i, cond in enumerate(decision['buy_conditions'], 1):
                lines.append(f"  {i}. {cond}")
            lines.append("")

        # 风险条件
        if decision['risk_conditions']:
            lines.append("【风险警示】")
            for i, risk in enumerate(decision['risk_conditions'], 1):
                lines.append(f"  ⚠️  {risk}")
            lines.append("")

        # AI理由
        lines.append("【AI决策理由】")
        lines.append(f"  {decision['ai_reason']}")
        lines.append("")

        lines.append("=" * 60)
        lines.append("说明：")
        lines.append("  - 仅供研究参考，不构成投资建议")
        lines.append("  - 决策基于已有数据，市场有风险")
        lines.append("  - 请结合自身风险承受能力决策")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_trade_decision_center = None


def get_trade_decision_center():
    """获取交易决策中心单例"""
    global _trade_decision_center
    if _trade_decision_center is None:
        _trade_decision_center = TradeDecisionCenter()
    return _trade_decision_center
