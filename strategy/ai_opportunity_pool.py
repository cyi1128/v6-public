# -*- coding: utf-8 -*-
"""
AI事件机会池模块
V1.1-3.4-A 新增

定位：
从全市场股票中筛选出值得关注的事件驱动机会，形成分级机会池。

原则：
- 不修改已有评分模型
- 不修改评级体系
- 只读取已有结果
- 独立模块，可删除

机会池分级：
- 一级机会池（强机会）：高评分 + 多事件共振 + 技术支持
- 二级机会池（潜力）：中高评分 + 有事件 + 无风险
- 观察池：有亮点但需等待确认
"""

import time
from datetime import datetime


class AIOpportunityPool:
    """AI事件机会池"""

    def __init__(self):
        # 机会池分级阈值
        self.tier1_min_score = 80
        self.tier1_min_events = 2
        self.tier1_min_resonance = 'double'  # 双事件及以上
        
        self.tier2_min_score = 70
        self.tier2_max_score = 79
        self.tier2_min_events = 1
        
        self.watch_min_score = 50
        self.watch_max_score = 69

        # 共振等级排序权重
        self.resonance_order = {
            'super': 5,   # 超强
            'quad': 4,    # 四事件
            'triple': 3,  # 三事件
            'double': 2,  # 双事件
            'single': 1,  # 单事件
            'none': 0,    # 无事件
        }

    def analyze_stock(self, code, name, signal_report, chanlun_advice):
        """
        分析单只股票，生成机会池条目

        参数：
            code: 股票代码
            name: 股票名称
            signal_report: AI买入信号报告
            chanlun_advice: 缠论AI建议

        返回：
            dict: 机会池条目
        """
        result = {
            'code': code,
            'name': name,
            'score': signal_report.get('score', 0),
            'rating': signal_report.get('rating', ''),
            'event_count': len(signal_report.get('event_signals', [])),
            'event_list': [s.get('name', '') for s in signal_report.get('event_signals', [])],
            'resonance_level': signal_report.get('resonance', {}).get('resonance_level', 'none'),
            'resonance_name': signal_report.get('resonance', {}).get('resonance_name', '单事件'),
            'resonance_confidence': signal_report.get('resonance', {}).get('confidence', '普通'),
            'chanlun_state': chanlun_advice.get('current_state', ''),
            'chanlun_score': chanlun_advice.get('final_score', 0),
            'tier': 'watch',  # 默认观察池
            'tier_name': '观察池',
            'sort_key': 0,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ai_reason': '',
        }

        # 判断是否高位风险
        is_high_risk = self._is_high_risk(chanlun_advice)
        result['is_high_risk'] = is_high_risk
        result['risk_level'] = '高' if is_high_risk else ('中' if result['score'] >= 70 else '低')

        # 分级判断
        tier, tier_name = self._classify_tier(result, is_high_risk)
        result['tier'] = tier
        result['tier_name'] = tier_name

        # 生成AI关注理由
        result['ai_reason'] = self._generate_reason(result)

        # 计算排序权重
        result['sort_key'] = self._calc_sort_key(result)

        return result

    def _is_high_risk(self, chanlun_advice):
        """判断是否高位风险"""
        state = chanlun_advice.get('current_state', '')
        high_risk_states = ['顶部背驰阶段', '趋势延伸阶段', '高位震荡', '顶部']
        for s in high_risk_states:
            if s in state:
                return True
        return False

    def _classify_tier(self, stock_info, is_high_risk):
        """
        对股票进行分级

        返回：
            (tier, tier_name)
        """
        score = stock_info['score']
        event_count = stock_info['event_count']
        resonance_level = stock_info['resonance_level']
        resonance_rank = self.resonance_order.get(resonance_level, 0)

        # 一级机会池（强机会）
        if (score >= self.tier1_min_score and 
            event_count >= self.tier1_min_events and 
            resonance_rank >= self.resonance_order.get(self.tier1_min_resonance, 2) and
            not is_high_risk):
            return ('tier1', '一级机会池')

        # 二级机会池（潜力）
        if (self.tier2_min_score <= score <= self.tier2_max_score and 
            event_count >= self.tier2_min_events and
            not is_high_risk):
            return ('tier2', '二级机会池')

        # 观察池
        if self.watch_min_score <= score <= self.watch_max_score:
            return ('watch', '观察池')

        # 其他：暂无明显机会
        return ('none', '暂无明显机会')

    def _generate_reason(self, stock_info):
        """生成AI关注理由"""
        reasons = []

        # 评分理由
        if stock_info['score'] >= 80:
            reasons.append('综合评分较高')
        elif stock_info['score'] >= 70:
            reasons.append('综合评分中等偏上')

        # 事件理由
        if stock_info['event_count'] >= 2:
            reasons.append(f"{stock_info['event_count']}个事件信号共振")
        elif stock_info['event_count'] == 1:
            reasons.append('有事件催化')

        # 共振理由
        if stock_info['resonance_level'] in ['triple', 'quad', 'super']:
            reasons.append(f"{stock_info['resonance_name']}，可信度{stock_info['resonance_confidence']}")

        # 技术理由
        if '三买' in stock_info['chanlun_state']:
            reasons.append('缠论三买结构')
        elif '趋势延伸' in stock_info['chanlun_state']:
            reasons.append('趋势延伸阶段')

        # 风险提示
        if stock_info.get('is_high_risk'):
            reasons.append('注意高位风险')

        return '，'.join(reasons) if reasons else '暂无明显关注理由'

    def _calc_sort_key(self, stock_info):
        """计算排序权重，越大越靠前"""
        score = stock_info['score']
        resonance_rank = self.resonance_order.get(stock_info['resonance_level'], 0)
        
        # 主排序：共振等级 * 100 + 评分
        # 这样保证高共振的股票排在前面，同共振等级内按评分排序
        sort_key = resonance_rank * 100 + score
        
        return sort_key

    def build_pool(self, stock_list):
        """
        构建机会池

        参数：
            stock_list: 股票列表，每个元素是analyze_stock的结果

        返回：
            dict: 分级机会池
        """
        tier1 = []
        tier2 = []
        watch = []
        none = []

        for stock in stock_list:
            tier = stock['tier']
            if tier == 'tier1':
                tier1.append(stock)
            elif tier == 'tier2':
                tier2.append(stock)
            elif tier == 'watch':
                watch.append(stock)
            else:
                none.append(stock)

        # 每个池子内按排序权重降序排列
        for pool in [tier1, tier2, watch, none]:
            pool.sort(key=lambda x: x['sort_key'], reverse=True)

        return {
            'tier1': tier1,
            'tier2': tier2,
            'watch': watch,
            'none': none,
            'total': len(stock_list),
            'tier1_count': len(tier1),
            'tier2_count': len(tier2),
            'watch_count': len(watch),
            'none_count': len(none),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def format_pool_report(self, pool):
        """
        格式化机会池报告为文本

        参数：
            pool: build_pool的结果

        返回：
            str: 格式化的报告文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append("🎯 AI事件机会池")
        lines.append("=" * 60)
        lines.append(f"更新时间：{pool['update_time']}")
        lines.append(f"扫描总数：{pool['total']}只")
        lines.append(f"一级机会：{pool['tier1_count']}只")
        lines.append(f"二级机会：{pool['tier2_count']}只")
        lines.append(f"观察池：{pool['watch_count']}只")
        lines.append("")

        # 一级机会池
        if pool['tier1']:
            lines.append("【⭐⭐⭐⭐⭐ 一级机会池】")
            lines.append("-" * 40)
            for i, stock in enumerate(pool['tier1'], 1):
                lines.append(f"{i}. {stock['name']}({stock['code']})")
                lines.append(f"   评分：{stock['score']}分 | 评级：{stock['rating']}")
                lines.append(f"   事件：{stock['event_count']}个 | 共振：{stock['resonance_name']}")
                lines.append(f"   缠论：{stock['chanlun_state']} | 风险：{stock['risk_level']}")
                lines.append(f"   AI关注：{stock['ai_reason']}")
                lines.append("")
            lines.append("")

        # 二级机会池
        if pool['tier2']:
            lines.append("【⭐⭐⭐⭐ 二级机会池】")
            lines.append("-" * 40)
            for i, stock in enumerate(pool['tier2'], 1):
                lines.append(f"{i}. {stock['name']}({stock['code']})")
                lines.append(f"   评分：{stock['score']}分 | 评级：{stock['rating']}")
                lines.append(f"   事件：{stock['event_count']}个 | 共振：{stock['resonance_name']}")
                lines.append(f"   缠论：{stock['chanlun_state']} | 风险：{stock['risk_level']}")
                lines.append(f"   AI关注：{stock['ai_reason']}")
                lines.append("")
            lines.append("")

        # 观察池（只显示前10只）
        if pool['watch']:
            lines.append(f"【⭐⭐⭐ 观察池】（共{pool['watch_count']}只，显示前10只）")
            lines.append("-" * 40)
            for i, stock in enumerate(pool['watch'][:10], 1):
                lines.append(f"{i}. {stock['name']}({stock['code']}) - {stock['score']}分 - {stock['rating']}")
            if len(pool['watch']) > 10:
                lines.append(f"   ... 还有{len(pool['watch'])-10}只")
            lines.append("")

        lines.append("=" * 60)
        lines.append("说明：")
        lines.append("  - 一级机会：高评分 + 多事件共振 + 技术支持 + 无高位风险")
        lines.append("  - 二级机会：中高评分 + 有事件催化 + 无顶部风险")
        lines.append("  - 观察池：有亮点但需等待确认")
        lines.append("  - 仅供研究参考，不构成投资建议")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_opportunity_pool = None


def get_ai_opportunity_pool():
    """获取AI事件机会池单例"""
    global _opportunity_pool
    if _opportunity_pool is None:
        _opportunity_pool = AIOpportunityPool()
    return _opportunity_pool
