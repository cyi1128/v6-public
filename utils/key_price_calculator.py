"""
关键价格计算器 V1.0
基于缠论结构/支撑压力位/ATR计算买入区域、止损位、压力位、目标位
可被实时监控、AI选股池、Pro选股池调用
"""
import os
import json
from datetime import datetime
from typing import Dict, Optional, List
import numpy as np


class KeyPriceCalculator:
    """关键价格计算器"""

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'cache', 'key_price'
            )
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cache = {}

    def calculate(self, code: str, price: float = 0,
                  kline_data: dict = None) -> dict:
        """
        计算关键价格

        Args:
            code: 股票代码
            price: 当前价格
            kline_data: K线数据 {close, high, low, open, volume}

        Returns:
            {
                'buy_zone': '12.50 - 12.80元',
                'buy_low': 12.50,
                'buy_high': 12.80,
                'stop_loss': 12.00,
                'stop_loss_price': 12.00,
                'resistance': 13.50,
                'resistance_price': 13.50,
                'target1': 13.80,
                'target1_price': 13.80,
                'target2': 14.50,
                'target2_price': 14.50,
                'atr': 0.35,
                'support': 12.20,
                'has_data': True,
            }
        """
        # 检查缓存
        cache_key = f"{code}_{datetime.now().strftime('%Y%m%d')}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 从缓存文件加载
        cached = self._load_cache(cache_key)
        if cached:
            self._cache[cache_key] = cached
            return cached

        # 如果没有K线数据，尝试获取
        if kline_data is None or not kline_data.get('close'):
            kline_data = self._get_kline(code)

        if not kline_data or not kline_data.get('close') or len(kline_data['close']) < 20:
            # 数据不足，用价格估算
            result = self._estimate_from_price(price)
            result['code'] = code
            result['has_data'] = False
            self._save_cache(cache_key, result)
            self._cache[cache_key] = result
            return result

        # 计算关键价格
        result = self._calc_from_kline(kline_data, price)
        result['code'] = code
        result['has_data'] = True

        # 保存缓存
        self._save_cache(cache_key, result)
        self._cache[cache_key] = result
        return result

    def _calc_from_kline(self, kline: dict, price: float = 0) -> dict:
        """从K线数据计算关键价格"""
        closes = np.array(kline['close'], dtype=float)
        highs = np.array(kline['high'], dtype=float)
        lows = np.array(kline['low'], dtype=float)

        if price <= 0:
            price = float(closes[-1])

        # 计算ATR（14日）
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                abs(highs[1:] - closes[:-1]),
                abs(lows[1:] - closes[:-1])
            )
        )
        atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))

        # 近期高低点
        recent_high = float(np.max(highs[-20:]))
        recent_low = float(np.min(lows[-20:]))

        # 支撑位：近期低点 + 前低
        supports = []
        for i in range(2, min(30, len(lows))):
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] if i+1 < len(lows) else True:
                supports.append(float(lows[i]))
        support = min(supports[-3:]) if supports else recent_low

        # 压力位：近期高点 + 前高
        resistances = []
        for i in range(2, min(30, len(highs))):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and (i+1 >= len(highs) or highs[i] > highs[i+1]):
                resistances.append(float(highs[i]))
        resistance = max(resistances[-3:]) if resistances else recent_high

        # 买入区域：支撑位附近 ±1%
        if support > 0 and price > 0:
            distance = (price - support) / price * 100
            if distance <= 15:
                # 价格离支撑不远，支撑位有效
                buy_low = round(support * 0.98, 2)
                buy_high = round(support * 1.02, 2)
            else:
                # 价格远离支撑，用回踩MA20作为买入区域
                ma20 = float(np.mean(closes[-20:]))
                if ma20 < price:
                    buy_low = round(ma20 * 0.98, 2)
                    buy_high = round(ma20 * 1.02, 2)
                else:
                    buy_low = round(price * 0.97, 2)
                    buy_high = round(price * 0.99, 2)
        else:
            buy_low = round(price * 0.97, 2)
            buy_high = round(price * 0.99, 2)

        # 止损位：支撑位下方3% 或 2倍ATR
        stop_loss_atr = round(price - 2 * atr, 2)
        stop_loss_support = round(support * 0.97, 2) if support > 0 else stop_loss_atr
        stop_loss = min(stop_loss_atr, stop_loss_support)
        stop_loss = max(stop_loss, price * 0.90)  # 最多跌10%

        # 第一目标：压力位 或 +8%
        target1_atr = round(price + atr * 2.5, 2)
        target1_resistance = round(resistance * 0.99, 2) if resistance > price else round(price * 1.08, 2)
        target1 = min(target1_atr, target1_resistance) if resistance > price else target1_atr

        # 第二目标：+15% 或 压力位上方
        target2 = round(price * 1.15, 2)
        if resistance > price:
            amplitude = resistance - support if support > 0 else atr * 3
            target2 = round(resistance + amplitude * 0.618, 2)

        return {
            'buy_zone': f"{buy_low:.2f} - {buy_high:.2f}元",
            'buy_low': buy_low,
            'buy_high': buy_high,
            'stop_loss': f"{stop_loss:.2f}元",
            'stop_loss_price': stop_loss,
            'resistance': f"{resistance:.2f}元",
            'resistance_price': resistance,
            'target1': f"{target1:.2f}元",
            'target1_price': target1,
            'target2': f"{target2:.2f}元",
            'target2_price': target2,
            'atr': round(atr, 2),
            'support': round(support, 2),
            'current_price': price,
            'risk_reward': round((target1 - price) / (price - stop_loss), 1) if price > stop_loss else 0,
        }

    def _estimate_from_price(self, price: float) -> dict:
        """价格不足时用百分比估算"""
        if price <= 0:
            price = 10.0

        atr = round(price * 0.03, 2)  # 假设3%波动

        return {
            'buy_zone': f"{price*0.97:.2f} - {price*0.99:.2f}元",
            'buy_low': round(price * 0.97, 2),
            'buy_high': round(price * 0.99, 2),
            'stop_loss': f"{price*0.93:.2f}元",
            'stop_loss_price': round(price * 0.93, 2),
            'resistance': f"{price*1.05:.2f}元",
            'resistance_price': round(price * 1.05, 2),
            'target1': f"{price*1.08:.2f}元",
            'target1_price': round(price * 1.08, 2),
            'target2': f"{price*1.15:.2f}元",
            'target2_price': round(price * 1.15, 2),
            'atr': atr,
            'support': round(price * 0.95, 2),
            'current_price': price,
            'risk_reward': 1.5,
        }

    def _get_kline(self, code: str) -> Optional[dict]:
        """获取K线数据"""
        try:
            from data.multi_period_provider import get_multi_period_provider
            provider = get_multi_period_provider()
            kline = provider.get_kline(code, period='day', count=60)
            if kline and kline.get('close'):
                return kline
        except Exception:
            pass

        # 尝试从DuckDB获取
        try:
            from data.duckdb_adapter import get_duckdb_adapter
            adapter = get_duckdb_adapter()
            df = adapter.get_daily_kline(code, limit=60)
            if df is not None and len(df) > 0:
                return {
                    'close': df['close'].tolist(),
                    'high': df['high'].tolist(),
                    'low': df['low'].tolist(),
                    'open': df['open'].tolist(),
                    'volume': df['volume'].tolist(),
                }
        except Exception:
            pass

        return None

    def _load_cache(self, key: str) -> Optional[dict]:
        """从文件加载缓存"""
        path = os.path.join(self.cache_dir, f'{key}.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_cache(self, key: str, data: dict):
        """保存缓存"""
        path = os.path.join(self.cache_dir, f'{key}.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def batch_calculate(self, stocks: List[dict]) -> Dict[str, dict]:
        """
        批量计算关键价格

        Args:
            stocks: [{'code': '000001', 'price': 10.5, 'name': '平安银行'}, ...]

        Returns:
            {code: key_price_dict}
        """
        results = {}
        for stock in stocks:
            code = stock.get('code', '')
            price = stock.get('price', 0)
            if code:
                results[code] = self.calculate(code, price)
        return results

    def format_tooltip(self, key_price: dict) -> str:
        """格式化关键价格为提示文本"""
        return (
            f"💰 关键价格\n"
            f"买入区域: {key_price.get('buy_zone', '--')}\n"
            f"止损位: {key_price.get('stop_loss', '--')}\n"
            f"压力位: {key_price.get('resistance', '--')}\n"
            f"第一目标: {key_price.get('target1', '--')}\n"
            f"第二目标: {key_price.get('target2', '--')}\n"
            f"风险回报比: 1:{key_price.get('risk_reward', 0)}"
        )


# 单例
_calculator_instance = None


def get_key_price_calculator() -> KeyPriceCalculator:
    """获取关键价格计算器单例"""
    global _calculator_instance
    if _calculator_instance is None:
        _calculator_instance = KeyPriceCalculator()
    return _calculator_instance
