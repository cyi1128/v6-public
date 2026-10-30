# -*- coding: utf-8 -*-
"""
回测报告生成模块
V1.1-3.7-A 新增

职责：
生成格式化的回测报告，包含胜率、收益、回撤等统计。
"""

from datetime import datetime


class BacktestReportGenerator:
    """回测报告生成器"""

    def __init__(self):
        pass

    def generate_event_report(self, event_name, summary_data, period='t10'):
        """
        生成单事件回测报告

        参数：
            event_name: 事件名称
            summary_data: 汇总统计数据
            period: 统计周期

        返回：
            str: 格式化的报告文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"📊 {event_name} 回测报告")
        lines.append("=" * 60)
        lines.append(f"统计周期：{period.replace('t', 'T+')}日")
        lines.append(f"样本数量：{summary_data['sample_count']}个")
        lines.append("")

        if summary_data['sample_count'] == 0:
            lines.append("⚠️  样本不足，无法统计")
            lines.append("")
            return "\n".join(lines)

        lines.append("【胜率统计】")
        lines.append(f"  上涨概率：{summary_data['win_rate']}%")
        lines.append("")

        lines.append("【收益统计】")
        lines.append(f"  平均收益：{summary_data['avg_return']}%")
        lines.append(f"  最大涨幅：{summary_data['max_return']}%")
        lines.append(f"  最小涨幅：{summary_data['min_return']}%")
        lines.append("")

        lines.append("【风险统计】")
        lines.append(f"  平均最大上涨：{summary_data['avg_max_up']}%")
        lines.append(f"  平均最大回撤：{summary_data['avg_max_drawdown']}%")
        lines.append("")

        # 简单评价
        lines.append("【简单评价】")
        win_rate = summary_data['win_rate']
        avg_return = summary_data['avg_return']
        
        if win_rate >= 60 and avg_return > 5:
            evaluation = "✅ 效果较好，胜率和收益都不错"
        elif win_rate >= 55 and avg_return > 3:
            evaluation = "🟡 效果一般，有一定参考价值"
        elif win_rate >= 50:
            evaluation = "⚠️  效果较弱，接近随机"
        else:
            evaluation = "❌ 效果不佳，胜率低于50%"
        
        lines.append(f"  {evaluation}")
        lines.append("")

        lines.append("=" * 60)
        lines.append("说明：")
        lines.append("  - 回测基于历史数据，不代表未来表现")
        lines.append("  - 样本数量较少时，统计结果可能有偏差")
        lines.append("  - 仅供研究参考，不构成投资建议")
        lines.append("=" * 60)

        return "\n".join(lines)

    def generate_comparison_report(self, event_summaries, period='t10'):
        """
        生成多事件对比报告

        参数：
            event_summaries: dict，key是事件名称，value是summary_data
            period: 统计周期

        返回：
            str: 格式化的对比报告
        """
        lines = []
        lines.append("=" * 70)
        lines.append("📊 AI事件驱动策略回测对比报告")
        lines.append("=" * 70)
        lines.append(f"统计周期：{period.replace('t', 'T+')}日")
        lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 表格头
        lines.append(f"{'事件名称':<15} {'样本数':>6} {'胜率':>8} {'平均收益':>10} {'最大上涨':>10} {'最大回撤':>10}")
        lines.append("-" * 70)

        # 按胜率排序
        sorted_events = sorted(
            event_summaries.items(),
            key=lambda x: x[1].get('win_rate', 0),
            reverse=True
        )

        for event_name, summary in sorted_events:
            sample_count = summary.get('sample_count', 0)
            if sample_count == 0:
                lines.append(f"{event_name:<15} {'0':>6} {'-':>8} {'-':>10} {'-':>10} {'-':>10}")
            else:
                lines.append(
                    f"{event_name:<15} "
                    f"{summary['sample_count']:>6} "
                    f"{summary['win_rate']:>7.1f}% "
                    f"{summary['avg_return']:>9.2f}% "
                    f"{summary['avg_max_up']:>9.2f}% "
                    f"{summary['avg_max_drawdown']:>9.2f}%"
                )

        lines.append("")
        lines.append("=" * 70)
        lines.append("说明：")
        lines.append("  - 按胜率从高到低排序")
        lines.append("  - 样本数量较少时，统计结果可能有偏差")
        lines.append("  - 仅供研究参考，不构成投资建议")
        lines.append("=" * 70)

        return "\n".join(lines)

    def generate_resonance_report(self, resonance_summaries, period='t10'):
        """
        生成共振对比报告

        参数：
            resonance_summaries: dict，key是共振等级，value是summary_data
            period: 统计周期

        返回：
            str: 格式化的共振报告
        """
        lines = []
        lines.append("=" * 60)
        lines.append("📊 事件共振策略回测报告")
        lines.append("=" * 60)
        lines.append(f"统计周期：{period.replace('t', 'T+')}日")
        lines.append("")

        lines.append("【共振等级对比】")
        lines.append(f"{'共振等级':<15} {'样本数':>6} {'胜率':>8} {'平均收益':>10}")
        lines.append("-" * 50)

        resonance_order = ['超强共振', '四事件共振', '三事件共振', '双事件共振', '单事件']

        for level in resonance_order:
            if level in resonance_summaries:
                summary = resonance_summaries[level]
                if summary['sample_count'] == 0:
                    lines.append(f"{level:<15} {'0':>6} {'-':>8} {'-':>10}")
                else:
                    lines.append(
                        f"{level:<15} "
                        f"{summary['sample_count']:>6} "
                        f"{summary['win_rate']:>7.1f}% "
                        f"{summary['avg_return']:>9.2f}%"
                    )

        lines.append("")

        # 验证共振是否有效
        if '单事件' in resonance_summaries and '双事件共振' in resonance_summaries:
            single_win = resonance_summaries['单事件'].get('win_rate', 0)
            double_win = resonance_summaries['双事件共振'].get('win_rate', 0)
            
            if double_win > single_win:
                lines.append("【结论】")
                lines.append(f"  ✅ 双事件共振胜率（{double_win}%）高于单事件（{single_win}%）")
                lines.append(f"  ✅ 事件共振策略有效，多事件确认能提高胜率")
            else:
                lines.append("【结论】")
                lines.append(f"  ⚠️  双事件共振胜率（{double_win}%）未明显高于单事件（{single_win}%）")
                lines.append(f"  ⚠️  需要更多样本验证")

        lines.append("")
        lines.append("=" * 60)
        lines.append("说明：")
        lines.append("  - 验证共振策略是否能提高胜率")
        lines.append("  - 样本数量较少时，结论可能不稳定")
        lines.append("  - 仅供研究参考，不构成投资建议")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_report_generator = None


def get_backtest_report_generator():
    """获取回测报告生成器单例"""
    global _report_generator
    if _report_generator is None:
        _report_generator = BacktestReportGenerator()
    return _report_generator
