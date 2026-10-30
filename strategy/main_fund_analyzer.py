"""
AI主力资金分析系统
自动判断主力阶段：吸筹、洗盘、启动、拉升、出货
颜色标识：绿色吸筹、红色攻击、黄色观察、黑色风险
"""
from datetime import datetime
import numpy as np


class MainFundAnalyzer:
    """AI主力资金分析系统"""

    # 主力阶段常量
    STAGE_ACCUMULATION = '吸筹'
    STAGE_WASHING = '洗盘'
    STAGE_STARTING = '启动'
    STAGE_RISING = '拉升'
    STAGE_DISTRIBUTION = '出货'

    # 阶段颜色
    STAGE_COLORS = {
        STAGE_ACCUMULATION: '#00e676',  # 绿色
        STAGE_WASHING: '#ffea00',       # 黄色
        STAGE_STARTING: '#ff9100',      # 橙色
        STAGE_RISING: '#ff1744',        # 红色（攻击）
        STAGE_DISTRIBUTION: '#757575',  # 黑色/灰色（风险）
    }

    def __init__(self):
        pass

    def analyze(self, stock_data, daily_data, stock_info=None):
        """
        分析主力资金阶段

        Args:
            stock_data: 股票数据
            daily_data: 日线数据
            stock_info: 股票信息

        Returns:
            dict: 主力分析结果
        """
        if stock_info is None:
            stock_info = {}

        if len(daily_data) < 30:
            return {
                'stage': '数据不足',
                'stage_color': '#8b949e',
                'confidence': 0,
                'fund_flow': '未知',
                'signals': [],
                'analysis': '数据不足，无法判断主力阶段',
            }

        closes = [d.get('close', 0) for d in daily_data]
        volumes = [d.get('volume', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]
        lows = [d.get('low', 0) for d in daily_data]

        # 计算各维度指标
        volume_trend = self._analyze_volume_trend(volumes)
        price_trend = self._analyze_price_trend(closes)
        fund_flow = self._analyze_fund_flow(closes, volumes)
        turnover = stock_info.get('turnover_rate', 0)
        volatility = self._calc_volatility(closes)

        # 判断阶段
        stage, confidence = self._determine_stage(
            volume_trend, price_trend, fund_flow, turnover, volatility, closes
        )

        # 生成信号
        signals = self._generate_signals(
            stage, volume_trend, price_trend, fund_flow, turnover
        )

        # 分析文字
        analysis = self._generate_analysis(stage, fund_flow, signals)

        return {
            'stage': stage,
            'stage_color': self.STAGE_COLORS.get(stage, '#8b949e'),
            'confidence': confidence,
            'fund_flow': fund_flow,
            'volume_trend': volume_trend,
            'price_trend': price_trend,
            'turnover': turnover,
            'volatility': volatility,
            'signals': signals,
            'analysis': analysis,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _analyze_volume_trend(self, volumes):
        """分析量能趋势"""
        if len(volumes) < 20:
            return '平稳'

        vol_5 = np.mean(volumes[-5:])
        vol_10 = np.mean(volumes[-10:])
        vol_20 = np.mean(volumes[-20:])

        if vol_20 == 0:
            return '平稳'

        ratio_5_20 = vol_5 / vol_20
        ratio_10_20 = vol_10 / vol_20

        if ratio_5_20 > 2.0:
            return '急剧放大'
        elif ratio_5_20 > 1.5:
            return '明显放大'
        elif ratio_5_20 > 1.2:
            return '温和放大'
        elif ratio_5_20 < 0.6:
            return '急剧萎缩'
        elif ratio_5_20 < 0.8:
            return '明显萎缩'
        else:
            return '平稳'

    def _analyze_price_trend(self, closes):
        """分析价格趋势"""
        if len(closes) < 20:
            return '横盘'

        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        if ma5 > ma10 > ma20:
            return '上升趋势'
        elif ma5 < ma10 < ma20:
            return '下降趋势'
        elif ma5 > ma10:
            return '短期偏强'
        elif ma5 < ma10:
            return '短期偏弱'
        else:
            return '横盘震荡'

    def _analyze_fund_flow(self, closes, volumes):
        """分析资金流向（量价配合）"""
        if len(closes) < 10 or len(volumes) < 10:
            return '未知'

        up_volume = 0
        down_volume = 0

        for i in range(-1, -11, -1):
            if abs(i) >= len(closes):
                break
            if closes[i] > closes[i-1]:
                up_volume += volumes[i]
            elif closes[i] < closes[i-1]:
                down_volume += volumes[i]

        total = up_volume + down_volume
        if total == 0:
            return '未知'

        ratio = up_volume / total

        if ratio > 0.65:
            return '主力大幅流入'
        elif ratio > 0.55:
            return '主力净流入'
        elif ratio > 0.45:
            return '资金博弈'
        elif ratio > 0.35:
            return '主力净流出'
        else:
            return '主力大幅流出'

    def _calc_volatility(self, closes):
        """计算波动率"""
        if len(closes) < 20:
            return 0

        returns = []
        for i in range(1, min(20, len(closes))):
            if closes[-i-1] > 0:
                returns.append(abs((closes[-i] - closes[-i-1]) / closes[-i-1]))

        return np.mean(returns) * 100 if returns else 0

    def _determine_stage(self, volume_trend, price_trend, fund_flow, turnover, volatility, closes):
        """判断主力阶段"""
        score = 0  # 0-100，分数越高越偏向拉升

        # 量能评分
        volume_scores = {
            '急剧放大': 30,
            '明显放大': 25,
            '温和放大': 15,
            '平稳': 10,
            '明显萎缩': 5,
            '急剧萎缩': 0,
        }
        score += volume_scores.get(volume_trend, 10)

        # 价格趋势评分
        price_scores = {
            '上升趋势': 30,
            '短期偏强': 20,
            '横盘震荡': 10,
            '短期偏弱': 5,
            '下降趋势': 0,
        }
        score += price_scores.get(price_trend, 10)

        # 资金流向评分
        fund_scores = {
            '主力大幅流入': 25,
            '主力净流入': 20,
            '资金博弈': 10,
            '主力净流出': 5,
            '主力大幅流出': 0,
        }
        score += fund_scores.get(fund_flow, 10)

        # 换手率评分
        if 5 <= turnover <= 15:
            score += 10  # 健康换手
        elif turnover > 20:
            score += 5   # 高换手，可能出货
        elif turnover < 2:
            score += 5   # 低换手，可能吸筹

        # 波动率评分
        if volatility > 3:
            score += 5
        elif volatility < 1.5:
            score += 5

        # 判断阶段
        if score >= 75:
            stage = self.STAGE_RISING
            confidence = min(95, 60 + (score - 75) * 2)
        elif score >= 55:
            stage = self.STAGE_STARTING
            confidence = min(85, 50 + (score - 55) * 2)
        elif score >= 40:
            # 需要进一步判断是洗盘还是吸筹
            if '萎缩' in volume_trend and price_trend in ['横盘震荡', '短期偏弱']:
                stage = self.STAGE_WASHING
                confidence = 70
            else:
                stage = self.STAGE_WASHING
                confidence = 60
        elif score >= 25:
            if '萎缩' in volume_trend and '流入' in fund_flow:
                stage = self.STAGE_ACCUMULATION
                confidence = 75
            else:
                stage = self.STAGE_ACCUMULATION
                confidence = 60
        else:
            stage = self.STAGE_DISTRIBUTION
            confidence = min(90, 50 + (25 - score) * 2)

        return stage, int(confidence)

    def _generate_signals(self, stage, volume_trend, price_trend, fund_flow, turnover):
        """生成交易信号"""
        signals = []

        if stage == self.STAGE_ACCUMULATION:
            signals.append('主力低位吸筹')
            if '萎缩' in volume_trend:
                signals.append('缩量整理，筹码稳定')
            if '流入' in fund_flow:
                signals.append('资金悄悄流入')
        elif stage == self.STAGE_WASHING:
            signals.append('主力洗盘中')
            if '萎缩' in volume_trend:
                signals.append('缩量洗盘，健康调整')
            signals.append('等待洗盘结束信号')
        elif stage == self.STAGE_STARTING:
            signals.append('主力启动迹象')
            if '放大' in volume_trend:
                signals.append('放量突破，关注')
            if '流入' in fund_flow:
                signals.append('资金加速流入')
        elif stage == self.STAGE_RISING:
            signals.append('主力拉升中')
            if '急剧放大' in volume_trend:
                signals.append('放量攻击，强势')
            signals.append('持股待涨，注意止盈')
        elif stage == self.STAGE_DISTRIBUTION:
            signals.append('主力出货风险')
            if '流出' in fund_flow:
                signals.append('资金持续流出')
            if turnover > 20:
                signals.append('高换手，警惕出货')
            signals.append('建议减仓或回避')

        return signals

    def _generate_analysis(self, stage, fund_flow, signals):
        """生成分析文字"""
        stage_desc = {
            self.STAGE_ACCUMULATION: '当前处于主力吸筹阶段，股价低位震荡，成交量萎缩，资金悄悄流入。这是主力建仓的典型特征，可以逢低关注。',
            self.STAGE_WASHING: '当前处于主力洗盘阶段，股价短期调整，成交量萎缩。这是拉升前的洗盘动作，耐心等待洗盘结束。',
            self.STAGE_STARTING: '当前处于主力启动阶段，成交量开始放大，资金流入加速。这是突破前的信号，可以重点关注。',
            self.STAGE_RISING: '当前处于主力拉升阶段，股价强势上涨，成交量放大，资金大幅流入。这是主升浪行情，持股待涨。',
            self.STAGE_DISTRIBUTION: '当前处于主力出货阶段，资金持续流出，高换手。这是风险信号，建议减仓或回避。',
        }

        return stage_desc.get(stage, '主力阶段不明，观望为主。')

    def get_stage_color(self, stage):
        """获取阶段颜色"""
        return self.STAGE_COLORS.get(stage, '#8b949e')
