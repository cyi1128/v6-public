# -*- coding: utf-8 -*-
"""
模块4：实时市场情绪
指标：涨跌家数比、涨停数、跌停数、连板高度、炸板率、两市成交额预估、量能同比
情绪定级：大赚/小赚/平衡/小亏/大亏
嵌入所有个股推送末尾的市场简报区域，盘中每小时更新一次
输出格式：😀市场情绪：涨跌比2890:2110 涨停47家 连板4板 炸板率24% 情绪【偏强】 💸量能：半日成交5200亿 较昨日同期+8%
"""
import os
import sys
import time
import logging
from typing import Dict, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.market_analysis_config import MARKET_SENTIMENT_CONFIG, GENERAL_CONFIG

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    if GENERAL_CONFIG.get('log_enabled', True):
        print(f"[市场情绪] {msg}", flush=True)


class MarketSentimentAnalyzer:
    """实时市场情绪分析器"""

    def __init__(self):
        self.config = MARKET_SENTIMENT_CONFIG
        self._cache: Optional[Dict] = None
        self._last_update = 0

    def analyze(self, force_refresh: bool = False) -> Optional[Dict]:
        """
        分析全市场情绪
        每小时更新一次（可强制刷新）
        Returns: {advance_count, decline_count, limit_up, limit_down,
                  max_consecutive_boards, broken_board_rate, turnover_estimate,
                  turnover_yoy, sentiment_level, sentiment_label, formatted_text}
        """
        if not self.config.get('enabled', False):
            return None

        # 缓存检查（每小时更新）
        interval = self.config.get('update_interval', 3600)
        now = time.time()
        if not force_refresh and self._cache and (now - self._last_update) < interval:
            return self._cache

        start_time = time.time()
        try:
            # 1. 获取市场数据
            market_data = self._fetch_market_data()
            if not market_data:
                return self._cache  # 返回缓存

            # 2. 情绪定级
            level, label = self._calc_sentiment(market_data)

            # 3. 格式化输出
            formatted = self._format_output(market_data, level, label)

            result = {
                'advance_count': market_data.get('advance', 0),
                'decline_count': market_data.get('decline', 0),
                'limit_up': market_data.get('limit_up', 0),
                'limit_down': market_data.get('limit_down', 0),
                'max_consecutive_boards': market_data.get('max_consecutive', 0),
                'broken_board_rate': market_data.get('broken_rate', 0),
                'turnover_estimate': market_data.get('turnover', 0),
                'turnover_yoy': market_data.get('turnover_yoy', 0),
                'sentiment_level': level,
                'sentiment_label': label,
                'formatted_text': formatted,
                'update_time': time.strftime('%H:%M:%S'),
            }

            self._cache = result
            self._last_update = now

            elapsed = time.time() - start_time
            if GENERAL_CONFIG.get('log_performance', True):
                _log(f"市场情绪分析完成 耗时{elapsed:.2f}s 情绪={label}")

            return result

        except Exception as e:
            _log(f"市场情绪分析异常: {e}", 'ERROR')
            return self._cache

    def _fetch_market_data(self) -> Optional[Dict]:
        """获取全市场真实数据（涨跌家数/涨停数/连板/炸板率/成交额）。

        数据源优先级：
        1. MarketRiskEngine._fetch_market_stats()（基于全市场行情+K线缓存，含连板数）
        2. get_full_market_quotes_http() 自行统计（涨跌家数/涨停/炸板/成交额）
        API失败返回None，禁止回退假数据。
        """
        # ---- 方式1：MarketRiskEngine 全市场统计 ----
        # 【2026-09-24 清理 v28 死引用】原数据源 v28.core.market_risk.MarketRiskEngine
        # 已下线（v28 包不存在），此前每次都抛 ModuleNotFoundError 并降级到方式2。
        # 现直接从方式2（HTTP 全市场行情自行统计）开始，行为与之前一致。

        # ---- 方式2：HTTP全市场行情自行统计 ----
        try:
            from utils.http_market_data import get_full_market_quotes_http
            quotes = get_full_market_quotes_http()
            if not quotes:
                _log("HTTP全市场行情为空，返回None", 'WARN')
                return None

            advance = decline = flat = 0
            limit_up = limit_down = broken = 0
            total_amount_yuan = 0.0
            for q in quotes:
                try:
                    pct = float(q.get('pct_chg', 0) or 0)
                    price = float(q.get('price', 0) or 0)
                    last_close = float(q.get('last_close', 0) or 0)
                    high = float(q.get('high', 0) or 0)
                    amount = float(q.get('amount', 0) or 0)
                    total_amount_yuan += amount

                    if pct > 0.001:
                        advance += 1
                    elif pct < -0.001:
                        decline += 1
                    else:
                        flat += 1

                    # 涨停/跌停/炸板判断（涨幅>=9.8%为涨停阈值）
                    if last_close > 0 and price > 0:
                        code = str(q.get('code', ''))
                        name = str(q.get('name', ''))
                        if 'ST' in name.upper():
                            limit_pct = 0.05
                        elif code.startswith(('300', '301', '688')):
                            limit_pct = 0.20
                        else:
                            limit_pct = 0.10
                        limit_up_price = round(last_close * (1 + limit_pct), 2)
                        limit_down_price = round(last_close * (1 - limit_pct), 2)
                        tol = max(0.01, limit_up_price * 0.001)
                        is_at_limit_up = price >= (limit_up_price - tol)
                        was_at_limit_up = high >= (limit_up_price - tol)
                        is_at_limit_down = price <= (limit_down_price + tol)
                        if is_at_limit_up:
                            limit_up += 1
                        elif was_at_limit_up and not is_at_limit_up:
                            broken += 1
                        if is_at_limit_down:
                            limit_down += 1
                except Exception:
                    continue

            total_sealed = limit_up + broken
            broken_rate = round(broken / total_sealed * 100, 1) if total_sealed > 0 else 0.0
            turnover = round(total_amount_yuan / 100000000, 0)  # 亿
            _log(f"真实市场统计(HTTP): 涨{advance} 跌{decline} 涨停{limit_up} 跌停{limit_down} 炸板率{broken_rate}% 成交{turnover:.0f}亿")
            return {
                'advance': advance,
                'decline': decline,
                'limit_up': limit_up,
                'limit_down': limit_down,
                'max_consecutive': 0,
                'broken_rate': broken_rate,
                'turnover': turnover,
                'turnover_yoy': 0.0,
            }
        except Exception as e:
            _log(f"HTTP全市场统计异常: {e}", 'WARN')
            return None

    def _calc_sentiment(self, data: Dict) -> Tuple[str, str]:
        """
        情绪定级
        Returns: (level, label)
        level: 大赚/小赚/平衡/小亏/大亏
        label: 极强/偏强/中性/偏弱/极弱
        """
        advance = data.get('advance', 0)
        decline = data.get('decline', 1)
        limit_up = data.get('limit_up', 0)
        ratio = advance / (advance + decline) if (advance + decline) > 0 else 0.5

        if ratio >= 0.7 and limit_up >= 50:
            return '大赚', '极强'
        elif ratio >= 0.55 and limit_up >= 30:
            return '小赚', '偏强'
        elif ratio >= 0.45 and limit_up >= 15:
            return '平衡', '中性'
        elif ratio >= 0.35 and limit_up >= 10:
            return '小亏', '偏弱'
        else:
            return '大亏', '极弱'

    def _format_output(self, data: Dict, level: str, label: str) -> str:
        """格式化输出"""
        emoji = '😀' if level in ('大赚', '小赚') else '😐' if level == '平衡' else '😟'
        parts = [
            f"{emoji}市场情绪：涨跌比{data.get('advance', 0)}:{data.get('decline', 0)}",
            f"涨停{data.get('limit_up', 0)}家",
            f"连板{data.get('max_consecutive', 0)}板",
            f"炸板率{data.get('broken_rate', 0):.0f}%",
            f"情绪【{label}】",
        ]

        turnover = data.get('turnover', 0)
        yoy = data.get('turnover_yoy', 0)
        if turnover > 0:
            yoy_sign = '+' if yoy >= 0 else ''
            parts.append(f"💸量能：半日成交{turnover}亿 较昨日同期{yoy_sign}{yoy:.0f}%")

        return ' '.join(parts)


_analyzer: Optional[MarketSentimentAnalyzer] = None


def get_sentiment_analyzer() -> MarketSentimentAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = MarketSentimentAnalyzer()
    return _analyzer


def analyze_sentiment(force_refresh: bool = False) -> Optional[Dict]:
    return get_sentiment_analyzer().analyze(force_refresh)
