# -*- coding: utf-8 -*-
"""
自选股自动复盘分析模块
V1.1-3.5-A 新增

定位：
对自选股进行每日自动复盘，跟踪评分、事件、共振、风险等变化。

原则：
- 不修改冻结模块
- 不修改AI评分
- 不修改B1-B6事件
- 不修改机会池逻辑
- 只读取已有结果
- 独立模块，可删除
"""

from datetime import datetime


class WatchlistReviewAnalyzer:
    """自选股复盘分析器"""

    def __init__(self):
        # 变化分类阈值
        self.big_score_change = 8  # 评分大幅变化阈值
        self.medium_score_change = 5  # 评分中等变化阈值

    def analyze_stock_review(self, code, name, current_data, changes):
        """
        分析单只股票的复盘情况

        参数：
            code: 股票代码
            name: 股票名称
            current_data: 当前数据（来自机会池分析）
            changes: 变化数据（来自daily_review_provider）

        返回：
            dict: 复盘分析结果
        """
        result = {
            'code': code,
            'name': name,
            'score': current_data.get('score', 0),
            'rating': current_data.get('rating', ''),
            'event_count': current_data.get('event_count', 0),
            'event_list': current_data.get('event_list', []),
            'resonance_name': current_data.get('resonance_name', ''),
            'resonance_confidence': current_data.get('resonance_confidence', ''),
            'chanlun_state': current_data.get('chanlun_state', ''),
            'risk_level': current_data.get('risk_level', ''),
            'changes': changes,
            'change_type': 'normal',  # big_up / event_added / risk_down / normal
            'change_summary': '',
            'ai_conclusion': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        # 判断变化类型
        result['change_type'] = self._classify_change(changes)

        # 生成变化摘要
        result['change_summary'] = self._generate_change_summary(changes)

        # 生成AI结论
        result['ai_conclusion'] = self._generate_conclusion(current_data, changes)

        return result

    def _classify_change(self, changes):
        """
        对变化进行分类

        返回：
            str: 变化类型
        """
        score_change = changes.get('score_change', 0)
        event_added = changes.get('event_added', [])
        event_removed = changes.get('event_removed', [])
        rating_change = changes.get('rating_change', '')

        # 评分大幅提升
        if score_change >= self.big_score_change:
            return 'big_up'

        # 新增事件
        if len(event_added) > 0:
            return 'event_added'

        # 评级下降或事件消失（风险下降）
        if '下降' in rating_change or len(event_removed) > 0:
            return 'risk_down'

        # 评分中等提升
        if score_change >= self.medium_score_change:
            return 'medium_up'

        # 正常
        return 'normal'

    def _generate_change_summary(self, changes):
        """生成变化摘要"""
        parts = []

        score_change = changes.get('score_change', 0)
        if score_change != 0:
            direction = '+' if score_change > 0 else ''
            parts.append(f"评分{direction}{score_change}分")

        rating_change = changes.get('rating_change', '')
        if rating_change and rating_change != '无变化':
            parts.append(f"评级{rating_change}")

        event_added = changes.get('event_added', [])
        if event_added:
            parts.append(f"新增事件: {', '.join(event_added)}")

        event_removed = changes.get('event_removed', [])
        if event_removed:
            parts.append(f"事件消失: {', '.join(event_removed)}")

        resonance_change = changes.get('resonance_change', '')
        if resonance_change and resonance_change != '无变化':
            parts.append(f"共振{resonance_change}")

        chanlun_change = changes.get('chanlun_change', '')
        if chanlun_change and chanlun_change != '无变化':
            parts.append(f"缠论{chanlun_change}")

        if not parts:
            return "无明显变化"

        return "；".join(parts)

    def _generate_conclusion(self, current_data, changes):
        """生成AI复盘结论"""
        conclusions = []

        score = current_data.get('score', 0)
        rating = current_data.get('rating', '')
        event_count = current_data.get('event_count', 0)
        resonance_name = current_data.get('resonance_name', '')
        chanlun_state = current_data.get('chanlun_state', '')
        risk_level = current_data.get('risk_level', '')

        # 基于当前状态的结论
        if rating == '强烈关注':
            conclusions.append('当前处于强烈关注区间')
        elif rating == '适度关注':
            conclusions.append('当前处于适度关注区间')
        elif rating == '观察':
            conclusions.append('当前处于观察区间，等待确认')

        # 事件情况
        if event_count >= 2:
            conclusions.append(f"{event_count}个事件催化，{resonance_name}")
        elif event_count == 1:
            conclusions.append("有1个事件催化")

        # 缠论状态
        if '三买' in chanlun_state:
            conclusions.append('缠论三买结构，技术面支持')
        elif '趋势延伸' in chanlun_state:
            conclusions.append('趋势延伸阶段，注意节奏')
        elif '背驰' in chanlun_state:
            conclusions.append('出现背驰信号，注意风险')

        # 风险提示
        if risk_level == '高':
            conclusions.append('注意高位风险')

        # 变化情况
        score_change = changes.get('score_change', 0)
        if score_change > 0:
            conclusions.append(f"评分提升{score_change}分，关注度上升")
        elif score_change < 0:
            conclusions.append(f"评分下降{abs(score_change)}分，需警惕")

        if not changes.get('has_previous', False):
            conclusions.append('首次纳入复盘，建立基准')

        return "，".join(conclusions) if conclusions else "暂无明显变化"

    def build_review_report(self, review_items):
        """
        构建复盘报告

        参数：
            review_items: 复盘分析结果列表

        返回：
            dict: 分类后的复盘报告
        """
        # 按变化类型分类
        big_up = []
        event_added = []
        risk_down = []
        normal = []

        for item in review_items:
            change_type = item.get('change_type', 'normal')
            if change_type == 'big_up':
                big_up.append(item)
            elif change_type == 'event_added':
                event_added.append(item)
            elif change_type == 'risk_down':
                risk_down.append(item)
            else:
                normal.append(item)

        # 每个分类内按评分降序排列
        for category in [big_up, event_added, risk_down, normal]:
            category.sort(key=lambda x: x['score'], reverse=True)

        return {
            'big_up': big_up,
            'event_added': event_added,
            'risk_down': risk_down,
            'normal': normal,
            'total': len(review_items),
            'big_up_count': len(big_up),
            'event_added_count': len(event_added),
            'risk_down_count': len(risk_down),
            'normal_count': len(normal),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def format_review_text(self, report):
        """
        格式化复盘报告为文本

        参数：
            report: build_review_report的结果

        返回：
            str: 格式化的复盘报告文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append("📊 自选股每日复盘报告")
        lines.append("=" * 60)
        lines.append(f"更新时间：{report['update_time']}")
        lines.append(f"复盘股票：{report['total']}只")
        lines.append(f"  🔥 评分大幅提升：{report['big_up_count']}只")
        lines.append(f"  ⭐ 新增事件催化：{report['event_added_count']}只")
        lines.append(f"  ⚠️  风险/评级下降：{report['risk_down_count']}只")
        lines.append(f"  📋 正常波动：{report['normal_count']}只")
        lines.append("")

        # 评分大幅提升
        if report['big_up']:
            lines.append("【🔥 评分大幅提升】")
            lines.append("-" * 40)
            for i, item in enumerate(report['big_up'], 1):
                lines.append(f"{i}. {item['name']}({item['code']})")
                lines.append(f"   评分：{item['score']}分 | 评级：{item['rating']}")
                lines.append(f"   变化：{item['change_summary']}")
                lines.append(f"   AI结论：{item['ai_conclusion']}")
                lines.append("")
            lines.append("")

        # 新增事件催化
        if report['event_added']:
            lines.append("【⭐ 新增事件催化】")
            lines.append("-" * 40)
            for i, item in enumerate(report['event_added'], 1):
                lines.append(f"{i}. {item['name']}({item['code']})")
                lines.append(f"   评分：{item['score']}分 | 评级：{item['rating']}")
                lines.append(f"   事件：{item['event_count']}个 | 共振：{item['resonance_name']}")
                lines.append(f"   变化：{item['change_summary']}")
                lines.append(f"   AI结论：{item['ai_conclusion']}")
                lines.append("")
            lines.append("")

        # 风险/评级下降
        if report['risk_down']:
            lines.append("【⚠️ 风险/评级下降】")
            lines.append("-" * 40)
            for i, item in enumerate(report['risk_down'], 1):
                lines.append(f"{i}. {item['name']}({item['code']})")
                lines.append(f"   评分：{item['score']}分 | 评级：{item['rating']}")
                lines.append(f"   变化：{item['change_summary']}")
                lines.append(f"   AI结论：{item['ai_conclusion']}")
                lines.append("")
            lines.append("")

        # 正常波动（只显示前5只）
        if report['normal']:
            lines.append(f"【📋 正常波动】（共{report['normal_count']}只，显示前5只）")
            lines.append("-" * 40)
            for i, item in enumerate(report['normal'][:5], 1):
                lines.append(f"{i}. {item['name']}({item['code']}) - {item['score']}分 - {item['rating']}")
            if len(report['normal']) > 5:
                lines.append(f"   ... 还有{len(report['normal'])-5}只")
            lines.append("")

        lines.append("=" * 60)
        lines.append("说明：")
        lines.append("  - 评分大幅提升：评分增加≥8分")
        lines.append("  - 新增事件催化：新增B1-B6事件信号")
        lines.append("  - 风险/评级下降：评级下降或事件消失")
        lines.append("  - 仅供研究参考，不构成投资建议")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_watchlist_reviewer = None


def get_watchlist_review_analyzer():
    """获取自选股复盘分析器单例"""
    global _watchlist_reviewer
    if _watchlist_reviewer is None:
        _watchlist_reviewer = WatchlistReviewAnalyzer()
    return _watchlist_reviewer
