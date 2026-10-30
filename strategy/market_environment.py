# -*- coding: utf-8 -*-
"""
V6.3 阶段4：市场环境过滤器

实时判断当前市场环境（牛市/震荡/弱势/风险），
并根据环境调整个股评分系数，提高实盘可靠性。

评分指标（四维度加权）：
  - 大盘趋势   30%  上证指数MA5/MA10/MA20排列，趋势方向
  - 赚钱效应   30%  上涨家数/下跌家数比例，涨停数/跌停数比例
  - 涨停数量   20%  当日涨停股票数量（连板高度加权）
  - 市场成交额 20%  沪深两市总成交额，与近20日均量对比

环境类型和系数：
  - 牛市  ≥80   ×1.2   可重仓，积极追涨
  - 震荡  50-79 ×1.0   正常仓位，精选个股
  - 弱势  30-49 ×0.7   轻仓，低吸为主
  - 风险  <30   ×0.0   空仓或观望，不追涨
"""

import os
import sys
import time
import json
import struct
import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.tdx_data_engine import get_tdx_data_engine

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

# 环境类型
ENV_BULL = "牛市"
ENV_OSCILLATION = "震荡"
ENV_WEAK = "弱势"
ENV_RISK = "风险"

# 环境颜色（UI显示用）
ENV_COLORS = {
    ENV_BULL: "#22c55e",        # 绿色
    ENV_OSCILLATION: "#eab308", # 黄色
    ENV_WEAK: "#f97316",        # 橙色
    ENV_RISK: "#ef4444",        # 红色
}

# 评分权重
WEIGHT_INDEX_TREND = 0.30
WEIGHT_PROFIT_EFFECT = 0.30
WEIGHT_LIMIT_UP = 0.20
WEIGHT_VOLUME = 0.20

# 上证指数通达信代码（999999，文件为sh999999.day）
SH_INDEX_CODE = "999999"
SH_INDEX_FILE = "sh999999.day"


# ============================================================
# 数据类
# ============================================================

@dataclass
class MarketEnvResult:
    """市场环境评分结果"""
    score: float = 0.0              # 综合评分 0-100
    env_type: str = ENV_OSCILLATION  # 环境类型
    factor: float = 1.0             # 个股评分系数
    chase_allowed: bool = True      # 是否允许追涨
    # 各维度得分
    index_trend_score: float = 0.0  # 大盘趋势分（0-30）
    profit_effect_score: float = 0.0 # 赚钱效应分（0-30）
    limit_up_score: float = 0.0     # 涨停数量分（0-20）
    volume_score: float = 0.0       # 成交额分（0-20）
    # 原始数据
    index_price: float = 0.0
    index_change_pct: float = 0.0
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    max_consecutive_boards: int = 0
    total_amount: float = 0.0       # 两市总成交额（元）
    amount_20d_avg: float = 0.0     # 20日均成交额（元）
    # 技术指标
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    # 元信息
    calc_time: str = ""
    data_source: str = ""

    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 1),
            "env_type": self.env_type,
            "factor": self.factor,
            "chase_allowed": self.chase_allowed,
            "index_trend_score": round(self.index_trend_score, 1),
            "profit_effect_score": round(self.profit_effect_score, 1),
            "limit_up_score": round(self.limit_up_score, 1),
            "volume_score": round(self.volume_score, 1),
            "index_price": round(self.index_price, 2),
            "index_change_pct": round(self.index_change_pct, 2),
            "up_count": self.up_count,
            "down_count": self.down_count,
            "flat_count": self.flat_count,
            "limit_up_count": self.limit_up_count,
            "limit_down_count": self.limit_down_count,
            "max_consecutive_boards": self.max_consecutive_boards,
            "total_amount_yi": round(self.total_amount / 1e8, 1),
            "amount_20d_avg_yi": round(self.amount_20d_avg / 1e8, 1),
            "ma5": round(self.ma5, 2),
            "ma10": round(self.ma10, 2),
            "ma20": round(self.ma20, 2),
            "calc_time": self.calc_time,
            "data_source": self.data_source,
        }


# ============================================================
# 市场环境评分引擎
# ============================================================

class MarketEnvironment:
    """
    V6.3 市场环境评分引擎

    实时判断市场环境，输出评分、环境类型和个股评分系数。
    """

    def __init__(self):
        self.tdx = get_tdx_data_engine()
        self.current_env: Optional[MarketEnvResult] = None
        self._index_kline_cache: Optional[List[Dict]] = None
        self._index_cache_time: float = 0

    # ============================================================
    # 主入口：计算市场环境
    # ============================================================

    def calculate(self) -> MarketEnvResult:
        """
        计算当前市场环境。

        Returns:
            MarketEnvResult，包含 score, env_type, factor 等
        """
        result = MarketEnvResult()
        result.calc_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 获取上证指数K线（用于趋势和成交额）
        index_kline = self._get_index_kline()
        data_sources = []

        if index_kline and len(index_kline) >= 20:
            data_sources.append("tdx_index")
            closes = [k["close"] for k in index_kline]
            amounts = [k.get("amount", 0) for k in index_kline]
            last_idx = len(closes) - 1

            result.index_price = closes[last_idx]
            if last_idx >= 1 and closes[last_idx - 1] > 0:
                result.index_change_pct = (
                    (closes[last_idx] - closes[last_idx - 1])
                    / closes[last_idx - 1] * 100
                )

            # MA
            result.ma5 = float(np.mean(closes[-5:])) if len(closes) >= 5 else 0
            result.ma10 = float(np.mean(closes[-10:])) if len(closes) >= 10 else 0
            result.ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else 0

            # 20日均成交额
            if len(amounts) >= 20:
                result.amount_20d_avg = float(np.mean(amounts[-20:]))

            # 大盘趋势分
            result.index_trend_score = self.get_index_trend_score(index_kline)
        else:
            # 无指数数据时给中性分
            result.index_trend_score = 15.0
            logger.warning("[MarketEnv] 无法获取上证指数K线，趋势分使用中性值15")

        # 2. 获取市场广度数据（涨跌家数、涨停跌停、总成交额）
        breadth = self._get_market_breadth()
        if breadth:
            data_sources.append("tdx_breadth")
            result.up_count = breadth.get("up_count", 0)
            result.down_count = breadth.get("down_count", 0)
            result.flat_count = breadth.get("flat_count", 0)
            result.limit_up_count = breadth.get("limit_up_count", 0)
            result.limit_down_count = breadth.get("limit_down_count", 0)
            result.max_consecutive_boards = breadth.get("max_consecutive_boards", 0)
            if breadth.get("total_amount", 0) > 0:
                result.total_amount = breadth["total_amount"]
        else:
            logger.warning("[MarketEnv] 无法获取市场广度数据")

        # 如果总成交额仍为0，从指数K线估算
        if result.total_amount == 0 and index_kline:
            result.total_amount = index_kline[-1].get("amount", 0) * 2  # 沪市×2估算两市

        # 3. 赚钱效应分
        result.profit_effect_score = self.get_profit_effect_score(
            result.up_count, result.down_count,
            result.limit_up_count, result.limit_down_count
        )

        # 4. 涨停数量分
        result.limit_up_score = self.get_limit_up_score(
            result.limit_up_count, result.max_consecutive_boards
        )

        # 5. 成交额分
        result.volume_score = self.get_volume_score(
            result.total_amount, result.amount_20d_avg
        )

        # 6. 加权综合评分
        result.score = round(
            result.index_trend_score
            + result.profit_effect_score
            + result.limit_up_score
            + result.volume_score,
            1
        )
        result.score = max(0.0, min(100.0, result.score))

        # 7. 判断环境类型和系数
        env_type, factor = self.get_environment_type(result.score)
        result.env_type = env_type
        result.factor = factor
        result.chase_allowed = self.is_chase_allowed(result.score)
        result.data_source = "+".join(data_sources) if data_sources else "unknown"

        self.current_env = result
        return result

    # ============================================================
    # 大盘趋势分（0-30）
    # ============================================================

    @staticmethod
    def get_index_trend_score(index_kline: List[Dict]) -> float:
        """
        大盘趋势分（满分30）。

        评分规则：
          - MA5 > MA10 > MA20（多头排列）: +30
          - MA5 > MA10 但 MA10 < MA20: +15
          - 空头排列（MA5 < MA10 < MA20）: +0
          - 近5日涨幅 > 2%: +5（叠加）
        """
        if not index_kline or len(index_kline) < 20:
            return 15.0

        closes = [k["close"] for k in index_kline]
        last_idx = len(closes) - 1

        ma5 = float(np.mean(closes[-5:]))
        ma10 = float(np.mean(closes[-10:]))
        ma20 = float(np.mean(closes[-20:]))

        score = 0.0

        # 均线排列
        if ma5 > ma10 > ma20:
            score += 30
        elif ma5 > ma10 and ma10 < ma20:
            score += 15
        elif ma5 < ma10 < ma20:
            score += 0
        else:
            # 其他排列（如MA5<MA10但MA10>MA20）
            score += 10

        # 近5日涨幅
        if last_idx >= 5 and closes[last_idx - 5] > 0:
            change_5d = (closes[last_idx] - closes[last_idx - 5]) / closes[last_idx - 5] * 100
            if change_5d > 2:
                score += 5

        return min(30.0, score)

    # ============================================================
    # 赚钱效应分（0-30）
    # ============================================================

    @staticmethod
    def get_profit_effect_score(
        up_count: int, down_count: int,
        limit_up_count: int, limit_down_count: int
    ) -> float:
        """
        赚钱效应分（满分30）。

        评分规则：
          - 上涨家数/下跌家数 > 2: +30
          - 上涨家数/下跌家数 1-2: +15
          - 上涨家数/下跌家数 < 1: +0
          - 涨停数/跌停数 > 5: +5（叠加）
        """
        score = 0.0

        # 涨跌家数比
        if down_count > 0:
            ratio = up_count / down_count
            if ratio > 2:
                score += 30
            elif ratio >= 1:
                score += 15
            else:
                score += 0
        elif up_count > 0:
            # 没有下跌股，全涨
            score += 30
        else:
            score += 15  # 无数据中性

        # 涨跌停比
        if limit_down_count > 0:
            ld_ratio = limit_up_count / limit_down_count
            if ld_ratio > 5:
                score += 5
        elif limit_up_count > 0:
            score += 5

        return min(30.0, score)

    # ============================================================
    # 涨停数量分（0-20）
    # ============================================================

    @staticmethod
    def get_limit_up_score(limit_up_count: int, max_consecutive: int = 0) -> float:
        """
        涨停数量分（满分20）。

        评分规则：
          - 涨停数 > 80: +20
          - 涨停数 50-80: +15
          - 涨停数 30-50: +10
          - 涨停数 < 30: +5
          - 连板高度 ≥ 5: +5（叠加）
        """
        score = 0.0

        if limit_up_count > 80:
            score += 20
        elif limit_up_count >= 50:
            score += 15
        elif limit_up_count >= 30:
            score += 10
        else:
            score += 5

        # 连板高度
        if max_consecutive >= 5:
            score += 5

        return min(20.0, score)

    # ============================================================
    # 成交额分（0-20）
    # ============================================================

    @staticmethod
    def get_volume_score(total_amount: float, avg_20d_amount: float = 0) -> float:
        """
        成交额分（满分20）。

        评分规则：
          - 两市成交额 > 1.5万亿: +20
          - 两市成交额 1-1.5万亿: +15
          - 两市成交额 0.8-1万亿: +10
          - 两市成交额 < 0.8万亿: +5
          - 成交额 > 20日均量 × 1.2: +5（叠加）
        """
        score = 0.0
        amount_yi = total_amount / 1e8  # 转为亿元

        if amount_yi > 15000:
            score += 20
        elif amount_yi >= 10000:
            score += 15
        elif amount_yi >= 8000:
            score += 10
        else:
            score += 5

        # 放量
        if avg_20d_amount > 0 and total_amount > avg_20d_amount * 1.2:
            score += 5

        return min(20.0, score)

    # ============================================================
    # 环境类型判断
    # ============================================================

    @staticmethod
    def get_environment_type(score: float) -> Tuple[str, float]:
        """
        根据评分判断环境类型和系数。

        Returns:
            (env_type, factor)
            - 牛市 ≥80: factor=1.2
            - 震荡 50-79: factor=1.0
            - 弱势 30-49: factor=0.7
            - 风险 <30: factor=0.0（禁追涨）
        """
        if score >= 80:
            return ENV_BULL, 1.2
        elif score >= 50:
            return ENV_OSCILLATION, 1.0
        elif score >= 30:
            return ENV_WEAK, 0.7
        else:
            return ENV_RISK, 0.0

    # ============================================================
    # 便捷方法
    # ============================================================

    def get_factor(self) -> float:
        """获取当前评分系数"""
        if self.current_env is None:
            self.calculate()
        return self.current_env.factor if self.current_env else 1.0

    def is_chase_allowed(self, score: Optional[float] = None) -> bool:
        """
        是否允许追涨。

        风险环境（<30分）禁止追涨。
        """
        if score is None:
            if self.current_env is None:
                self.calculate()
            score = self.current_env.score if self.current_env else 50
        return score >= 30

    def get_current_env(self) -> Optional[MarketEnvResult]:
        """获取当前市场环境结果（未计算则先计算）"""
        if self.current_env is None:
            self.calculate()
        return self.current_env

    # ============================================================
    # 内部方法：数据获取
    # ============================================================

    def _get_index_kline(self) -> Optional[List[Dict]]:
        """
        获取上证指数K线数据。

        由于tdx_data_engine的_get_day_file_path对999999代码处理有误
        （999999不以6开头，被误判为深市），这里直接读取sh999999.day文件。
        """
        # 缓存5分钟
        if self._index_kline_cache and (time.time() - self._index_cache_time) < 300:
            return self._index_kline_cache

        tdx_path = getattr(self.tdx, 'tdx_path', None) or getattr(self.tdx, '_tdx_path', r'C:\new_tdx')
        filepath = os.path.join(tdx_path, 'vipdoc', 'sh', 'lday', SH_INDEX_FILE)

        if not os.path.exists(filepath):
            logger.warning(f"[MarketEnv] 上证指数文件不存在: {filepath}")
            return None

        try:
            kline = self._read_index_day_file(filepath)
            if kline:
                self._index_kline_cache = kline
                self._index_cache_time = time.time()
            return kline
        except Exception as e:
            logger.error(f"[MarketEnv] 读取上证指数失败: {e}")
            return None

    @staticmethod
    def _read_index_day_file(filepath: str, days: int = 60) -> List[Dict]:
        """
        直接读取上证指数.day文件（格式: <IIIIIfII，价格除以100）。
        """
        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, 'rb') as f:
                data = f.read()
        except Exception:
            return []

        rec_size = 32
        n = len(data) // rec_size
        if n == 0:
            return []

        kline = []
        # 只取最近days条
        start = max(0, n - days)
        for i in range(start, n):
            offset = i * rec_size
            raw = data[offset:offset + rec_size]
            if len(raw) < rec_size:
                break
            try:
                d = struct.unpack('<IIIIIfII', raw)
                date_int = d[0]
                date_str = str(date_int)
                # 验证日期合理性
                if len(date_str) != 8:
                    continue
                kline.append({
                    'date': date_str,
                    'trade_date': date_str,
                    'open': d[1] / 100.0,
                    'high': d[2] / 100.0,
                    'low': d[3] / 100.0,
                    'close': d[4] / 100.0,
                    'amount': float(d[5]),
                    'volume': float(d[6]),
                })
            except Exception:
                continue

        return kline

    def _get_market_breadth(self) -> Optional[Dict]:
        """
        获取市场广度数据（涨跌家数、涨停跌停、总成交额）。

        优先从stock_pool_cache读取，其次从TDX全市场股票计算。
        """
        # 方式1：从stock_pool_cache读取（如果有足够数据）
        breadth = self._breadth_from_cache()
        if breadth and breadth.get("total_stocks", 0) >= 500:
            return breadth

        # 方式2：从TDX全市场股票计算
        breadth = self._breadth_from_tdx()
        if breadth:
            return breadth

        return None

    def _breadth_from_cache(self) -> Optional[Dict]:
        """从stock_pool_cache.json读取市场广度"""
        cache_path = os.path.join(PROJECT_ROOT, "cache", "stock_pool_cache.json")
        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            results = data.get("results", [])
            if not results:
                return None

            up = sum(1 for s in results if s.get("pct_chg", 0) > 0)
            down = sum(1 for s in results if s.get("pct_chg", 0) < 0)
            flat = sum(1 for s in results if s.get("pct_chg", 0) == 0)
            limit_up = sum(1 for s in results if s.get("pct_chg", 0) >= 9.5)
            limit_down = sum(1 for s in results if s.get("pct_chg", 0) <= -9.5)
            total_amount = sum(s.get("amount", 0) for s in results)
            max_boards = max(
                (s.get("limit_up_count", 0) for s in results), default=0
            )

            return {
                "up_count": up,
                "down_count": down,
                "flat_count": flat,
                "limit_up_count": limit_up,
                "limit_down_count": limit_down,
                "max_consecutive_boards": max_boards,
                "total_amount": total_amount,
                "total_stocks": len(results),
                "source": "stock_pool_cache",
            }
        except Exception as e:
            logger.warning(f"[MarketEnv] 从cache读取广度失败: {e}")
            return None

    def _breadth_from_tdx(self) -> Optional[Dict]:
        """从TDX全市场股票计算市场广度"""
        try:
            codes = self.tdx.get_all_main_board_codes()
            if not codes:
                return None

            up = down = flat = 0
            limit_up = limit_down = 0
            total_amount = 0.0
            max_boards = 0
            processed = 0

            # 批量读取最新K线（只读2天，计算涨跌幅）
            for code in codes:
                kline = self.tdx.get_kline(code, days=2)
                if not kline or len(kline) < 2:
                    continue
                last = kline[-1]
                prev = kline[-2]
                close = last.get("close", 0)
                prev_close = prev.get("close", 0)
                if prev_close <= 0:
                    continue

                pct = (close - prev_close) / prev_close * 100
                if pct > 0:
                    up += 1
                elif pct < 0:
                    down += 1
                else:
                    flat += 1

                if pct >= 9.5:
                    limit_up += 1
                if pct <= -9.5:
                    limit_down += 1

                total_amount += last.get("amount", 0)
                processed += 1

            if processed == 0:
                return None

            return {
                "up_count": up,
                "down_count": down,
                "flat_count": flat,
                "limit_up_count": limit_up,
                "limit_down_count": limit_down,
                "max_consecutive_boards": max_boards,
                "total_amount": total_amount,
                "total_stocks": processed,
                "source": "tdx_full_market",
            }
        except Exception as e:
            logger.warning(f"[MarketEnv] 从TDX计算广度失败: {e}")
            return None


# ============================================================
# 便捷函数
# ============================================================

_default_env = None


def get_market_environment() -> MarketEnvironment:
    """获取市场环境引擎单例"""
    global _default_env
    if _default_env is None:
        _default_env = MarketEnvironment()
    return _default_env


def calculate_market_env() -> MarketEnvResult:
    """便捷函数：计算当前市场环境"""
    return get_market_environment().calculate()
