"""
智能复盘模块
每日自动生成：市场温度、热点板块、资金方向、涨停分析、个人股票分析、策略触发记录
"""
from datetime import datetime
import json
import os


class DailyReview:
    """每日复盘类"""

    def __init__(self, review_dir='reviews'):
        self.review_dir = review_dir
        os.makedirs(review_dir, exist_ok=True)

    def generate_review(self, market_data=None, my_stocks=None, signal_logs=None):
        """
        生成每日复盘报告
        market_data: 市场整体数据
        my_stocks: 我的股票池数据
        signal_logs: 信号触发记录
        """
        review = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M:%S'),
            'market_temperature': self._analyze_market_temperature(market_data),
            'hot_sectors': self._analyze_hot_sectors(market_data),
            'capital_flow': self._analyze_capital_flow(market_data),
            'limit_up_analysis': self._analyze_limit_up(market_data),
            'my_stocks_analysis': self._analyze_my_stocks(my_stocks),
            'signal_triggers': self._analyze_signal_triggers(signal_logs),
            'summary': '',
        }

        review['summary'] = self._generate_summary(review)

        return review

    def _analyze_market_temperature(self, market_data):
        """分析市场温度"""
        if not market_data:
            return {
                'level': '数据不足',
                'score': 50,
                'description': '暂无市场数据',
                'up_count': 0,
                'down_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0,
            }

        up_count = market_data.get('up_count', 0)
        down_count = market_data.get('down_count', 0)
        total = up_count + down_count

        if total == 0:
            temp_score = 50
        else:
            up_ratio = up_count / total
            temp_score = int(up_ratio * 100)

        if temp_score >= 70:
            level = '火热'
            desc = '市场情绪高涨，赚钱效应强'
        elif temp_score >= 55:
            level = '偏暖'
            desc = '市场情绪偏多，可积极操作'
        elif temp_score >= 45:
            level = '中性'
            desc = '市场震荡，精选个股'
        elif temp_score >= 30:
            level = '偏冷'
            desc = '市场情绪偏弱，谨慎操作'
        else:
            level = '寒冷'
            desc = '市场低迷，控制仓位'

        return {
            'level': level,
            'score': temp_score,
            'description': desc,
            'up_count': up_count,
            'down_count': down_count,
            'limit_up_count': market_data.get('limit_up_count', 0),
            'limit_down_count': market_data.get('limit_down_count', 0),
        }

    def _analyze_hot_sectors(self, market_data):
        """分析热点板块"""
        if not market_data or 'sectors' not in market_data:
            return [
                {'name': '数据不足', 'change': 0, 'leader': '-', 'reason': '暂无板块数据'}
            ]

        sectors = market_data['sectors']
        # 按涨幅排序
        sorted_sectors = sorted(sectors, key=lambda x: x.get('change', 0), reverse=True)

        result = []
        for sector in sorted_sectors[:5]:
            result.append({
                'name': sector.get('name', ''),
                'change': sector.get('change', 0),
                'leader': sector.get('leader', ''),
                'reason': sector.get('reason', ''),
            })

        return result

    def _analyze_capital_flow(self, market_data):
        """分析资金方向"""
        if not market_data:
            return {
                'main_inflow': 0,
                'main_outflow': 0,
                'net_flow': 0,
                'direction': '未知',
                'hot_money_direction': '未知',
            }

        main_inflow = market_data.get('main_inflow', 0)
        main_outflow = market_data.get('main_outflow', 0)
        net_flow = main_inflow - main_outflow

        if net_flow > 100:
            direction = '大幅流入'
        elif net_flow > 0:
            direction = '小幅流入'
        elif net_flow > -100:
            direction = '小幅流出'
        else:
            direction = '大幅流出'

        return {
            'main_inflow': main_inflow,
            'main_outflow': main_outflow,
            'net_flow': net_flow,
            'direction': direction,
            'hot_money_direction': market_data.get('hot_money_direction', '未知'),
        }

    def _analyze_limit_up(self, market_data):
        """涨停分析"""
        if not market_data or 'limit_up_stocks' not in market_data:
            return {
                'count': 0,
                'new_high_count': 0,
                'sectors': [],
                'characteristics': '暂无涨停数据',
            }

        limit_up_stocks = market_data['limit_up_stocks']

        # 统计涨停板块分布
        sector_count = {}
        for stock in limit_up_stocks:
            sector = stock.get('sector', '其他')
            sector_count[sector] = sector_count.get(sector, 0) + 1

        top_sectors = sorted(sector_count.items(), key=lambda x: x[1], reverse=True)[:3]

        return {
            'count': len(limit_up_stocks),
            'new_high_count': sum(1 for s in limit_up_stocks if s.get('is_new_high', False)),
            'sectors': [{'name': s[0], 'count': s[1]} for s in top_sectors],
            'characteristics': f'涨停{len(limit_up_stocks)}家，主要集中在{", ".join([s[0] for s in top_sectors])}',
        }

    def _analyze_my_stocks(self, my_stocks):
        """我的股票分析"""
        if not my_stocks:
            return {
                'total': 0,
                'buy_signals': 0,
                'watch_signals': 0,
                'risk_signals': 0,
                'top_scored': [],
            }

        buy_count = 0
        watch_count = 0
        risk_count = 0
        scored_stocks = []

        for stock in my_stocks:
            signals = stock.get('signals', [])
            score = stock.get('total_score', 0)

            for sig in signals:
                sig_name = sig.get('name', '') if isinstance(sig, dict) else str(sig)
                if '买' in sig_name or '启动' in sig_name:
                    buy_count += 1
                elif '观察' in sig_name or '回踩' in sig_name:
                    watch_count += 1
                elif '风险' in sig_name or '死叉' in sig_name:
                    risk_count += 1

            scored_stocks.append({
                'name': stock.get('name', ''),
                'ts_code': stock.get('ts_code', ''),
                'score': score,
                'price': stock.get('price', 0),
                'suggestion': stock.get('suggestion', ''),
            })

        # 按评分排序
        top_scored = sorted(scored_stocks, key=lambda x: x['score'], reverse=True)[:5]

        return {
            'total': len(my_stocks),
            'buy_signals': buy_count,
            'watch_signals': watch_count,
            'risk_signals': risk_count,
            'top_scored': top_scored,
        }

    def _analyze_signal_triggers(self, signal_logs):
        """策略触发记录"""
        if not signal_logs:
            return {
                'total': 0,
                'by_type': {},
                'today_triggers': [],
            }

        today = datetime.now().strftime('%Y-%m-%d')
        today_logs = [log for log in signal_logs if log.get('time', '').startswith(today)]

        by_type = {}
        for log in today_logs:
            sig_type = log.get('signal', '未知')
            by_type[sig_type] = by_type.get(sig_type, 0) + 1

        return {
            'total': len(today_logs),
            'by_type': by_type,
            'today_triggers': today_logs[:20],
        }

    def _generate_summary(self, review):
        """生成复盘总结"""
        temp = review['market_temperature']
        capital = review['capital_flow']
        my_stocks = review['my_stocks_analysis']
        signals = review['signal_triggers']

        summary_parts = []

        summary_parts.append(f'市场温度: {temp["level"]}({temp["score"]}分)')
        summary_parts.append(f'资金方向: {capital["direction"]}')

        if my_stocks['total'] > 0:
            summary_parts.append(f'股票池: {my_stocks["total"]}只')
            if my_stocks['buy_signals'] > 0:
                summary_parts.append(f'买入信号: {my_stocks["buy_signals"]}个')
            if my_stocks['risk_signals'] > 0:
                summary_parts.append(f'风险提示: {my_stocks["risk_signals"]}个')

        if signals['total'] > 0:
            summary_parts.append(f'今日触发信号: {signals["total"]}次')

        return ' | '.join(summary_parts)

    def save_review(self, review):
        """保存复盘报告"""
        date_str = review['date']
        filepath = os.path.join(self.review_dir, f'review_{date_str}.json')

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(review, f, ensure_ascii=False, indent=2)

        return filepath

    def generate_text_report(self, review):
        """生成文本格式复盘报告"""
        lines = []
        lines.append('=' * 70)
        lines.append('量化盯盘系统 V6.0 Pro - 每日复盘报告')
        lines.append(f'日期: {review["date"]} {review["time"]}')
        lines.append('=' * 70)
        lines.append('')

        # 市场温度
        temp = review['market_temperature']
        lines.append('【市场温度】')
        lines.append(f'  温度等级: {temp["level"]} ({temp["score"]}分)')
        lines.append(f'  {temp["description"]}')
        lines.append(f'  上涨: {temp["up_count"]}家 | 下跌: {temp["down_count"]}家')
        lines.append(f'  涨停: {temp["limit_up_count"]}家 | 跌停: {temp["limit_down_count"]}家')
        lines.append('')

        # 热点板块
        lines.append('【热点板块】')
        for i, sector in enumerate(review['hot_sectors'][:5], 1):
            lines.append(f'  {i}. {sector["name"]} 涨幅:{sector["change"]:+.2f}% 龙头:{sector["leader"]}')
        lines.append('')

        # 资金方向
        capital = review['capital_flow']
        lines.append('【资金方向】')
        lines.append(f'  主力净流入: {capital["net_flow"]:+.0f}亿 ({capital["direction"]})')
        lines.append(f'  游资方向: {capital["hot_money_direction"]}')
        lines.append('')

        # 涨停分析
        limit_up = review['limit_up_analysis']
        lines.append('【涨停分析】')
        lines.append(f'  涨停家数: {limit_up["count"]}家')
        lines.append(f'  {limit_up["characteristics"]}')
        lines.append('')

        # 我的股票
        my_stocks = review['my_stocks_analysis']
        if my_stocks['total'] > 0:
            lines.append('【我的股票池】')
            lines.append(f'  股票数量: {my_stocks["total"]}只')
            lines.append(f'  买入信号: {my_stocks["buy_signals"]}个')
            lines.append(f'  观察信号: {my_stocks["watch_signals"]}个')
            lines.append(f'  风险信号: {my_stocks["risk_signals"]}个')
            lines.append('')
            lines.append('  评分TOP5:')
            for i, stock in enumerate(my_stocks['top_scored'], 1):
                lines.append(f'    {i}. {stock["name"]}({stock["ts_code"]}) '
                           f'{stock["score"]}分 {stock["price"]:.2f}元 - {stock["suggestion"]}')
            lines.append('')

        # 信号触发
        signals = review['signal_triggers']
        if signals['total'] > 0:
            lines.append('【今日信号触发】')
            lines.append(f'  总触发次数: {signals["total"]}次')
            for sig_type, count in signals['by_type'].items():
                lines.append(f'    {sig_type}: {count}次')
            lines.append('')

        # 总结
        lines.append('【复盘总结】')
        lines.append(f'  {review["summary"]}')
        lines.append('')
        lines.append('=' * 70)
        lines.append('免责声明: 本报告仅供参考，不构成投资建议。')

        return '\n'.join(lines)
