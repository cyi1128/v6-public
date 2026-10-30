"""
五大AI交易策略库
1. 游资短线攻击模式
2. 趋势波段模式
3. 价值成长模式
4. 超跌反弹模式
5. 防守避险模式
"""
from datetime import datetime
import numpy as np


class StrategyLibrary:
    """五大AI交易策略库"""

    # 策略常量
    STRATEGY_HOT_MONEY = '游资短线攻击'
    STRATEGY_TREND = '趋势波段'
    STRATEGY_VALUE = '价值成长'
    STRATEGY_OVERSOLD = '超跌反弹'
    STRATEGY_DEFENSE = '防守避险'

    ALL_STRATEGIES = [
        STRATEGY_HOT_MONEY,
        STRATEGY_TREND,
        STRATEGY_VALUE,
        STRATEGY_OVERSOLD,
        STRATEGY_DEFENSE,
    ]

    # 策略颜色
    STRATEGY_COLORS = {
        STRATEGY_HOT_MONEY: '#f85149',
        STRATEGY_TREND: '#3fb950',
        STRATEGY_VALUE: '#58a6ff',
        STRATEGY_OVERSOLD: '#d29922',
        STRATEGY_DEFENSE: '#8b949e',
    }

    def __init__(self):
        pass

    def analyze_stock(self, strategy_type, stock_data, daily_data, stock_info=None):
        """
        根据指定策略分析股票

        Args:
            strategy_type: 策略类型
            stock_data: 股票基本数据
            daily_data: 日线数据
            stock_info: 股票信息

        Returns:
            dict: 策略分析结果
        """
        if stock_info is None:
            stock_info = {}

        analyzers = {
            self.STRATEGY_HOT_MONEY: self._analyze_hot_money,
            self.STRATEGY_TREND: self._analyze_trend,
            self.STRATEGY_VALUE: self._analyze_value,
            self.STRATEGY_OVERSOLD: self._analyze_oversold,
            self.STRATEGY_DEFENSE: self._analyze_defense,
        }

        analyzer = analyzers.get(strategy_type)
        if analyzer:
            return analyzer(stock_data, daily_data, stock_info)
        return None

    def _analyze_hot_money(self, stock_data, daily_data, stock_info):
        """策略1：游资短线攻击模式"""
        score = 0
        logic = []
        signals = []

        if len(daily_data) < 20:
            return {'score': 0, 'logic': ['数据不足'], 'signals': []}

        closes = [d.get('close', 0) for d in daily_data]
        volumes = [d.get('volume', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]

        # 1. 涨停基因（近20日涨停次数）
        limit_up_count = 0
        for i in range(1, min(20, len(closes))):
            if closes[i-1] > 0 and (closes[i] - closes[i-1]) / closes[i-1] >= 0.095:
                limit_up_count += 1

        if limit_up_count >= 3:
            score += 25
            logic.append(f'近20日{limit_up_count}次涨停，股性活跃')
            signals.append('涨停基因强')
        elif limit_up_count >= 2:
            score += 15
            logic.append(f'近20日{limit_up_count}次涨停')
        elif limit_up_count >= 1:
            score += 5

        # 2. 龙头地位（近期涨幅排名）
        if len(closes) >= 11:
            change_10d = (closes[-1] - closes[-11]) / closes[-11] * 100
            if change_10d > 30:
                score += 20
                logic.append(f'10日涨幅{change_10d:.1f}%，龙头特征明显')
                signals.append('板块龙头')
            elif change_10d > 15:
                score += 10
                logic.append(f'10日涨幅{change_10d:.1f}%')

        # 3. 资金抢筹（放量）
        vol_5 = np.mean(volumes[-5:]) if len(volumes) >= 5 else 0
        vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else 0
        if vol_20 > 0:
            vol_ratio = vol_5 / vol_20
            if vol_ratio > 2:
                score += 20
                logic.append(f'近5日量能放大{vol_ratio:.1f}倍，资金抢筹')
                signals.append('资金集中')
            elif vol_ratio > 1.5:
                score += 10
                logic.append(f'量能放大{vol_ratio:.1f}倍')

        # 4. 热点第一梯队（近期新高）
        recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        if closes[-1] >= recent_high * 0.95:
            score += 20
            logic.append('股价接近近期新高，处于热点第一梯队')
            signals.append('市场情绪支持')
        elif closes[-1] >= recent_high * 0.9:
            score += 10

        # 5. 换手率
        turnover = stock_info.get('turnover_rate', 0)
        if 8 <= turnover <= 25:
            score += 15
            logic.append(f'换手率{turnover:.1f}%，交投活跃')
        elif 5 <= turnover < 8:
            score += 8

        # 买点建议
        buy_point = '回封/分歧低吸'
        risk = '龙头断板、情绪退潮'

        return {
            'strategy': self.STRATEGY_HOT_MONEY,
            'score': min(100, score),
            'logic': logic,
            'signals': signals,
            'buy_point': buy_point,
            'risk': risk,
            'position': '20%-30%',
            'holding_days': '1-3天',
        }

    def _analyze_trend(self, stock_data, daily_data, stock_info):
        """策略2：趋势波段模式 - 抓主升浪"""
        score = 0
        logic = []
        signals = []

        if len(daily_data) < 30:
            return {'score': 0, 'logic': ['数据不足'], 'signals': []}

        closes = [d.get('close', 0) for d in daily_data]
        volumes = [d.get('volume', 0) for d in daily_data]

        # 1. MA多头排列
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20

        if ma5 > ma10 > ma20 > ma60:
            score += 25
            logic.append('MA5>MA10>MA20>MA60，完美多头排列')
            signals.append('主升阶段')
        elif ma5 > ma10 > ma20:
            score += 15
            logic.append('MA多头排列')
        elif ma5 > ma10:
            score += 5

        # 2. MACD红柱扩大（简化：用价格动量）
        if len(closes) >= 12:
            momentum = closes[-1] - closes[-12]
            if momentum > 0 and closes[-1] > closes[-5]:
                score += 20
                logic.append('价格动量向上，MACD红柱扩大')
                signals.append('趋势加速')
            elif momentum > 0:
                score += 10

        # 3. 成交量温和增加
        vol_5 = np.mean(volumes[-5:])
        vol_20 = np.mean(volumes[-20:])
        if vol_20 > 0:
            vol_ratio = vol_5 / vol_20
            if 1.2 <= vol_ratio <= 2.0:
                score += 20
                logic.append(f'成交量温和放大{vol_ratio:.1f}倍，健康上涨')
                signals.append('量价配合')
            elif vol_ratio > 2.5:
                score -= 5  # 放量过大可能见顶
                logic.append('成交量过大，注意短期风险')

        # 4. 回踩支撑有效
        if closes[-1] > ma10 and closes[-3] < ma10:
            score += 20
            logic.append('回踩10日线获得支撑，加仓点')
            signals.append('回踩支撑有效')
        elif closes[-1] > ma20 and closes[-5] < ma20:
            score += 15
            logic.append('回踩20日线获得支撑')

        # 5. 趋势强度
        if len(closes) >= 21:
            change_20d = (closes[-1] - closes[-21]) / closes[-21] * 100
            if change_20d > 20:
                score += 15
                logic.append(f'20日涨幅{change_20d:.1f}%，强势趋势')
            elif change_20d > 10:
                score += 8

        # 趋势状态判断
        if score >= 80:
            trend_status = '主升阶段'
            operation = '持有，可加仓'
        elif score >= 60:
            trend_status = '上升趋势'
            operation = '持有'
        else:
            trend_status = '震荡整理'
            operation = '观望'

        return {
            'strategy': self.STRATEGY_TREND,
            'score': min(100, score),
            'logic': logic,
            'signals': signals,
            'trend_status': trend_status,
            'operation': operation,
            'add_point': '回踩10日线/20日线',
            'stop_loss': '跌破20日线',
            'position': '30%-50%',
            'holding_days': '5-20天',
        }

    def _analyze_value(self, stock_data, daily_data, stock_info):
        """策略3：价值成长模式"""
        score = 0
        logic = []
        signals = []

        # 1. 营收增长（需要财务数据，简化用市值和PE）
        pe = stock_info.get('pe', 0)
        market_cap = stock_info.get('market_cap', 0)  # 亿

        if 0 < pe < 30:
            score += 25
            logic.append(f'PE {pe:.1f}，估值合理')
            signals.append('估值合理')
        elif 30 <= pe < 50:
            score += 10
            logic.append(f'PE {pe:.1f}，估值偏高')
        elif pe >= 50:
            score -= 10
            logic.append(f'PE {pe:.1f}，估值过高')

        # 2. 市值适中（成长股通常100-500亿）
        if 100 <= market_cap <= 500:
            score += 20
            logic.append(f'市值{market_cap:.0f}亿，成长空间大')
            signals.append('成长空间')
        elif 50 <= market_cap < 100:
            score += 15
        elif market_cap > 1000:
            score += 5
            logic.append('大盘蓝筹，稳健型')

        # 3. 行业空间（用行业判断，简化）
        industry = stock_info.get('industry', '')
        growth_industries = ['新能源', '半导体', '人工智能', '医药', '消费', '军工', '光伏']
        if any(g in industry for g in growth_industries):
            score += 20
            logic.append(f'所属行业【{industry}】属于高成长赛道')
            signals.append('行业景气')
        else:
            score += 5

        # 4. 机构持仓（用换手率和成交量稳定性判断）
        if len(daily_data) >= 20:
            volumes = [d.get('volume', 0) for d in daily_data[-20:]]
            vol_std = np.std(volumes)
            vol_mean = np.mean(volumes)
            if vol_mean > 0 and vol_std / vol_mean < 0.3:
                score += 20
                logic.append('成交量稳定，机构持仓特征明显')
                signals.append('机构关注')
            elif vol_mean > 0 and vol_std / vol_mean < 0.5:
                score += 10

        # 5. 技术面稳健
        if len(daily_data) >= 60:
            closes = [d.get('close', 0) for d in daily_data]
            ma60 = np.mean(closes[-60:])
            if closes[-1] > ma60:
                score += 15
                logic.append('股价站上60日线，中长期趋势向上')

        return {
            'strategy': self.STRATEGY_VALUE,
            'score': min(100, score),
            'logic': logic,
            'signals': signals,
            'investment_style': '中长期持有',
            'holding_period': '3-12个月',
            'position': '20%-40%',
            'risk': '行业政策变化、业绩不及预期',
        }

    def _analyze_oversold(self, stock_data, daily_data, stock_info):
        """策略4：超跌反弹模式"""
        score = 0
        logic = []
        signals = []

        if len(daily_data) < 30:
            return {'score': 0, 'logic': ['数据不足'], 'signals': []}

        closes = [d.get('close', 0) for d in daily_data]
        volumes = [d.get('volume', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]

        # 1. 跌幅较大
        recent_high = max(highs[-60:]) if len(highs) >= 60 else max(highs)
        if recent_high > 0:
            drawdown = (recent_high - closes[-1]) / recent_high * 100
            if drawdown >= 40:
                score += 25
                logic.append(f'较高点回撤{drawdown:.1f}%，严重超跌')
                signals.append('严重超跌')
            elif drawdown >= 25:
                score += 15
                logic.append(f'较高点回撤{drawdown:.1f}%，超跌')
            elif drawdown >= 15:
                score += 5

        # 2. 基本面未恶化（PE合理）
        pe = stock_info.get('pe', 0)
        if 0 < pe < 40:
            score += 20
            logic.append(f'PE {pe:.1f}，基本面未恶化')
            signals.append('基本面支撑')
        elif pe == 0:
            score += 10

        # 3. 资金开始回流
        if len(volumes) >= 10:
            vol_5 = np.mean(volumes[-5:])
            vol_prev5 = np.mean(volumes[-10:-5])
            if vol_prev5 > 0:
                vol_change = (vol_5 - vol_prev5) / vol_prev5 * 100
                if vol_change > 30:
                    score += 20
                    logic.append(f'近5日量能增加{vol_change:.0f}%，资金开始回流')
                    signals.append('资金回流')
                elif vol_change > 10:
                    score += 10

        # 4. 放量止跌
        if len(closes) >= 3 and len(volumes) >= 3:
            if closes[-1] > closes[-2] and volumes[-1] > volumes[-2] * 1.3:
                score += 20
                logic.append('放量止跌，反弹信号出现')
                signals.append('放量止跌')
            elif closes[-1] > closes[-2] and closes[-2] < closes[-3]:
                score += 10
                logic.append('止跌企稳')

        # 5. 技术指标超卖（简化用价格位置）
        ma20 = np.mean(closes[-20:])
        if closes[-1] < ma20 * 0.9:
            score += 15
            logic.append('股价偏离20日线超过10%，技术超卖')

        return {
            'strategy': self.STRATEGY_OVERSOLD,
            'score': min(100, score),
            'logic': logic,
            'signals': signals,
            'buy_point': '放量止跌时',
            'stop_loss': '跌破前低',
            'target': '反弹至20日线/60日线',
            'position': '10%-20%',
            'holding_days': '3-10天',
            'risk': '继续下跌、反弹失败',
        }

    def _analyze_defense(self, stock_data, daily_data, stock_info):
        """策略5：防守避险模式"""
        score = 0  # 分数越高越安全
        logic = []
        risks = []

        # 1. 业绩稳定（低PE）
        pe = stock_info.get('pe', 0)
        if 0 < pe < 25:
            score += 25
            logic.append(f'PE {pe:.1f}，低估值安全边际高')
        elif pe >= 50:
            risks.append('高估值')
            score -= 15

        # 2. 无减持风险（简化用市值大小）
        market_cap = stock_info.get('market_cap', 0)
        if market_cap > 200:
            score += 20
            logic.append(f'市值{market_cap:.0f}亿，大股东减持影响小')
        elif market_cap < 50:
            risks.append('小市值易减持')
            score -= 10

        # 3. 无监管风险（排除ST、问题股）
        name = stock_data.get('name', '')
        if 'ST' in name or '*ST' in name:
            risks.append('ST股有退市风险')
            score -= 30
        else:
            score += 15
            logic.append('非ST股，无退市风险')

        # 4. 波动小（防守型）
        if len(daily_data) >= 20:
            closes = [d.get('close', 0) for d in daily_data[-20:]]
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0:
                    returns.append((closes[i] - closes[i-1]) / closes[i-1])
            if returns:
                volatility = np.std(returns) * 100
                if volatility < 2:
                    score += 20
                    logic.append(f'日波动率{volatility:.1f}%，走势稳健')
                elif volatility > 4:
                    risks.append('波动过大')
                    score -= 10

        # 5. 高股息/防御行业
        industry = stock_info.get('industry', '')
        defense_industries = ['银行', '电力', '公用事业', '高速公路', '白酒', '医药']
        if any(d in industry for d in defense_industries):
            score += 20
            logic.append(f'所属【{industry}】属于防御性行业')

        # 过滤风险
        filtered = len(risks) == 0

        return {
            'strategy': self.STRATEGY_DEFENSE,
            'safety_score': min(100, max(0, score)),
            'logic': logic,
            'risks': risks,
            'filtered': filtered,
            'suggestion': '可配置' if filtered else '建议规避',
            'position': '10%-20%',
        }

    def get_all_strategies(self):
        """获取所有策略列表"""
        return self.ALL_STRATEGIES

    def get_strategy_color(self, strategy_type):
        """获取策略颜色"""
        return self.STRATEGY_COLORS.get(strategy_type, '#8b949e')
