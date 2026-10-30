"""
主力吸筹识别模块
三阶段识别: 首次放量上涨 -> 缩量回调 -> 二次放量突破
"""
from config.settings import ACCUMULATION_CONFIG
from utils.indicators import detect_accumulation_pattern


class AccumulationDetector:
    """主力吸筹识别器"""

    def __init__(self):
        self.config = ACCUMULATION_CONFIG

    def detect(self, daily_data):
        """
        识别主力吸筹形态
        返回: (stage, description, confidence)
        """
        if not daily_data or len(daily_data) < 20:
            return None, "数据不足", 0

        high_prices = [d['high'] for d in daily_data]
        low_prices = [d['low'] for d in daily_data]
        close_prices = [d['close'] for d in daily_data]
        volumes = [d['volume'] for d in daily_data]

        return detect_accumulation_pattern(
            high_prices, low_prices, close_prices, volumes, self.config
        )

    def scan_stocks(self, stock_data_list):
        """
        批量扫描股票
        返回: 有吸筹形态的股票列表,按置信度排序
        """
        results = []
        for stock in stock_data_list:
            daily_data = stock.get('daily_data', [])
            stage, desc, confidence = self.detect(daily_data)
            if stage and confidence >= 40:
                results.append({
                    'ts_code': stock['ts_code'],
                    'name': stock['name'],
                    'industry': stock.get('industry', ''),
                    'stage': stage,
                    'description': desc,
                    'confidence': confidence,
                    'current_price': daily_data[-1]['close'] if daily_data else 0,
                })

        results.sort(key=lambda x: x['confidence'], reverse=True)
        return results
