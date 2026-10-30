"""
盘中实时监控模块
"""
from config.settings import REALTIME_CONFIG
from utils.indicators import calc_avg_price


class RealtimeMonitor:
    """实时监控器"""

    def __init__(self):
        self.config = REALTIME_CONFIG
        self.watch_list = []  # 监控列表
        self.price_history = {}  # 价格历史 {ts_code: [prices]}
        self.volume_history = {}  # 成交量历史

    def set_watch_list(self, stock_list):
        """设置监控股票列表"""
        self.watch_list = stock_list
        for stock in stock_list:
            ts_code = stock.get('ts_code', '')
            if ts_code not in self.price_history:
                self.price_history[ts_code] = []
            if ts_code not in self.volume_history:
                self.volume_history[ts_code] = []

    def update(self, realtime_quotes):
        """
        更新实时数据并分析
        返回: 分析结果列表
        """
        results = []
        for quote in realtime_quotes:
            ts_code = quote.get('ts_code', '')
            price = quote.get('price', 0)
            volume = quote.get('volume', 0)
            avg_price = quote.get('avg_price', 0)

            # 记录历史
            if ts_code not in self.price_history:
                self.price_history[ts_code] = []
            self.price_history[ts_code].append(price)
            if len(self.price_history[ts_code]) > 100:
                self.price_history[ts_code].pop(0)

            if ts_code not in self.volume_history:
                self.volume_history[ts_code] = []
            self.volume_history[ts_code].append(volume)
            if len(self.volume_history[ts_code]) > 100:
                self.volume_history[ts_code].pop(0)

            # 分析
            analysis = self._analyze_stock(quote)
            results.append(analysis)

        return results

    def _analyze_stock(self, quote):
        """分析单只股票实时状态"""
        ts_code = quote.get('ts_code', '')
        price = quote.get('price', 0)
        avg_price = quote.get('avg_price', 0)
        volume = quote.get('volume', 0)
        pct_chg = quote.get('pct_chg', 0)

        # 1. 股价站上均价线
        above_avg = price > avg_price if avg_price > 0 else False

        # 2. 成交量增加(对比前几分钟均量)
        vol_increasing = self._check_volume_increase(ts_code, volume)

        # 3. 突破确认(价格创近期新高)
        breakout = self._check_breakout(ts_code, price)

        # 资金强弱判断
        money_strength = self._calc_money_strength(quote, above_avg, vol_increasing)

        # 综合状态
        status = '正常'
        if above_avg and vol_increasing and breakout:
            status = '强势突破'
        elif above_avg and vol_increasing:
            status = '量价齐升'
        elif above_avg:
            status = '站上均价'
        elif not above_avg and pct_chg < 0:
            status = '弱势调整'

        return {
            'ts_code': ts_code,
            'name': quote.get('name', ''),
            'price': price,
            'pct_chg': pct_chg,
            'avg_price': avg_price,
            'volume': volume,
            'amount': quote.get('amount', 0),
            'turnover_rate': quote.get('turnover_rate', 0),
            'above_avg': above_avg,
            'vol_increasing': vol_increasing,
            'breakout': breakout,
            'money_strength': money_strength,
            'status': status,
        }

    def _check_volume_increase(self, ts_code, current_volume):
        """检查成交量是否增加"""
        vol_history = self.volume_history.get(ts_code, [])
        if len(vol_history) < 5:
            return False

        # 取前几分钟均量
        prev_avg = sum(vol_history[-6:-1]) / 5 if len(vol_history) >= 6 else sum(vol_history[:-1]) / max(1, len(vol_history) - 1)
        if prev_avg == 0:
            return False

        # 当前成交量(增量) vs 前几分钟均量(增量)
        prev_increment = vol_history[-1] - vol_history[-2] if len(vol_history) >= 2 else 0
        current_increment = current_volume - vol_history[-1] if vol_history else 0

        if prev_increment <= 0:
            return current_increment > 0

        ratio = current_increment / prev_increment
        threshold = self.config.get('price_above_avg_vol_increase', 1.2)
        return ratio >= threshold

    def _check_breakout(self, ts_code, current_price):
        """检查是否突破(创近期新高)"""
        price_history = self.price_history.get(ts_code, [])
        if len(price_history) < 10:
            return False

        recent_high = max(price_history[-20:-1]) if len(price_history) >= 20 else max(price_history[:-1])
        return current_price > recent_high * 1.001  # 超过0.1%算突破

    def _calc_money_strength(self, quote, above_avg, vol_increasing):
        """计算资金强弱指数 0-100"""
        score = 50  # 基准分

        pct_chg = quote.get('pct_chg', 0)
        turnover = quote.get('turnover_rate', 0)

        # 涨跌幅贡献
        score += pct_chg * 3

        # 站上均价线
        if above_avg:
            score += 10

        # 量增
        if vol_increasing:
            score += 10

        # 换手率
        if turnover > 5:
            score += 10
        elif turnover > 3:
            score += 5

        return max(0, min(100, score))

    def get_strong_stocks(self, min_strength=70):
        """获取强势股票"""
        # 需要先有update数据
        return []
