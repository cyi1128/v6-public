# -*- coding: utf-8 -*-
"""
模块1：竞价强度分析
数据来源：pytdx竞价行情 + 本地历史成交量
核心指标：竞价量/昨日成交量比值、竞价涨幅、委买委卖盘比值、竞价撮合量占比
强度评级：极强/强/中性/弱/虚拉 五级
输出格式：⏰竞价强度：竞价量比2.8 高开1.2% 放量承接 评级【强】
"""
import os
import sys
import time
import logging
from typing import Dict, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.market_analysis_config import AUCTION_STRENGTH_CONFIG, GENERAL_CONFIG

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    if GENERAL_CONFIG.get('log_enabled', True):
        print(f"[竞价强度] {msg}", flush=True)


class AuctionStrengthAnalyzer:
    """竞价强度分析器"""

    def __init__(self):
        self.config = AUCTION_STRENGTH_CONFIG
        self._cache: Dict[str, Dict] = {}
        self._last_update = 0

    def analyze(self, code: str, name: str = '') -> Optional[Dict]:
        """
        分析单只股票竞价强度
        Returns: {volume_ratio, auction_pct, bid_ask_ratio, match_ratio,
                  rating, anomaly_tag, formatted_text}
        异常时返回None（调用方自动降级）
        """
        if not self.config.get('enabled', False):
            return None

        start_time = time.time()
        try:
            # 1. 获取竞价数据（pytdx）
            auction_data = self._fetch_auction_data(code)
            if not auction_data:
                _log(f"{code} 竞价数据获取失败，跳过", 'WARN')
                return None

            # 2. 获取昨日成交量
            yesterday_vol = self._get_yesterday_volume(code)

            # 3. 计算指标
            volume_ratio = auction_data.get('volume', 0) / yesterday_vol if yesterday_vol > 0 else 0
            auction_pct = auction_data.get('pct_chg', 0)
            bid_ask_ratio = auction_data.get('bid_ask_ratio', 1.0)
            match_ratio = auction_data.get('match_ratio', 0)

            # 4. 强度评级
            rating, anomaly_tag = self._rate_strength(
                volume_ratio, auction_pct, bid_ask_ratio
            )

            # 5. 格式化输出
            formatted = self._format_output(
                volume_ratio, auction_pct, bid_ask_ratio, rating, anomaly_tag
            )

            result = {
                'volume_ratio': round(volume_ratio, 2),
                'auction_pct': round(auction_pct, 2),
                'bid_ask_ratio': round(bid_ask_ratio, 2),
                'match_ratio': round(match_ratio, 2),
                'rating': rating,
                'anomaly_tag': anomaly_tag,
                'formatted_text': formatted,
            }

            elapsed = time.time() - start_time
            if GENERAL_CONFIG.get('log_performance', True):
                _log(f"{code} 分析完成 耗时{elapsed:.2f}s 评级={rating}")

            return result

        except Exception as e:
            _log(f"{code} 分析异常: {e}", 'ERROR')
            return None  # 异常自动降级

    def _fetch_auction_data(self, code: str) -> Optional[Dict]:
        """获取竞价数据（pytdx）"""
        try:
            from utils.kline_fetcher import fetch_kline_pytdx
            # 获取最近2根K线（昨日+今日）
            kline = fetch_kline_pytdx(code, days=2)
            if not kline or len(kline) < 1:
                return None

            today = kline[-1]
            # 从K线推算竞价数据（简化实现，实际可接入pytdx竞价接口）
            open_price = today.get('open', 0)
            pre_close = today.get('close', 0) if len(kline) < 2 else kline[-2].get('close', 0)
            pct_chg = (open_price - pre_close) / pre_close * 100 if pre_close > 0 else 0

            return {
                'volume': today.get('volume', 0),
                'pct_chg': pct_chg,
                'bid_ask_ratio': 1.2,  # 简化：实际从竞价盘口获取
                'match_ratio': 0.15,   # 简化：竞价撮合量占比
            }
        except Exception as e:
            _log(f"获取{code}竞价数据失败: {e}", 'WARN')
            return None

    def _get_yesterday_volume(self, code: str) -> float:
        """获取昨日成交量（从DuckDB缓存）"""
        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return 0
            con = duckdb.connect(db_path, read_only=True)
            row = con.execute(
                "SELECT volume FROM kline_cache WHERE code = ? ORDER BY date DESC LIMIT 1 OFFSET 1",
                [code]
            ).fetchone()
            con.close()
            return float(row[0]) if row and row[0] else 0
        except Exception:
            return 0

    def _rate_strength(self, volume_ratio: float, pct_chg: float,
                        bid_ask_ratio: float) -> Tuple[str, str]:
        """
        竞价强度评级
        Returns: (rating, anomaly_tag)
        rating: 极强/强/中性/弱/虚拉
        anomaly_tag: 主力抢筹/无量虚拉/放量承接/缩量观望/''
        """
        threshold = self.config.get('auction_volume_ratio_threshold', 3.0)
        virtual_pct = self.config.get('virtual_rally_pct', 2.0)

        anomaly_tag = ''

        # 异动标注
        if volume_ratio >= threshold and pct_chg > 0:
            anomaly_tag = '主力抢筹'
        elif pct_chg >= virtual_pct and volume_ratio < 1.0:
            anomaly_tag = '无量虚拉'
        elif volume_ratio >= 1.5 and pct_chg > 0:
            anomaly_tag = '放量承接'
        elif volume_ratio < 0.5:
            anomaly_tag = '缩量观望'

        # 评级
        if volume_ratio >= threshold and pct_chg > 1.0 and bid_ask_ratio >= 1.5:
            rating = '极强'
        elif volume_ratio >= 2.0 and pct_chg > 0:
            rating = '强'
        elif volume_ratio >= 0.8 and volume_ratio <= 1.5:
            rating = '中性'
        elif volume_ratio < 0.8 and pct_chg < 0:
            rating = '弱'
        else:
            rating = '虚拉' if pct_chg >= virtual_pct and volume_ratio < 1.0 else '中性'

        return rating, anomaly_tag

    def _format_output(self, volume_ratio: float, pct_chg: float,
                       bid_ask_ratio: float, rating: str, anomaly_tag: str) -> str:
        """格式化输出"""
        parts = [f"⏰竞价强度：竞价量比{volume_ratio:.1f}"]
        pct_sign = '+' if pct_chg >= 0 else ''
        parts.append(f"高开{pct_sign}{pct_chg:.1f}%")
        if anomaly_tag:
            parts.append(anomaly_tag)
        parts.append(f"评级【{rating}】")
        return ' '.join(parts)


# 全局单例
_analyzer: Optional[AuctionStrengthAnalyzer] = None


def get_auction_analyzer() -> AuctionStrengthAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = AuctionStrengthAnalyzer()
    return _analyzer


def analyze_auction(code: str, name: str = '') -> Optional[Dict]:
    """便捷函数：分析单只股票竞价强度"""
    return get_auction_analyzer().analyze(code, name)


if __name__ == '__main__':
    # 测试
    result = analyze_auction('000001', '平安银行')
    if result:
        print(result['formatted_text'])
    else:
        print("竞价强度模块未启用或分析失败")
