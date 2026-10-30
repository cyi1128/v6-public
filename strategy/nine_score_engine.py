# -*- coding: utf-8 -*-
"""
九重共振选股中心 - 综合评分引擎 V1.0

评分维度：
  资金面 40%（量比/大单净量/成交额/换手率）
  趋势面 40%（MA排列/RPS20/突破60日/筹码峰）
  情绪面 20%（市场情绪周期/涨停基因/连板高度）

输出等级：
  S+  90-100
  S   80-90
  A   70-80
  B   60-70
  C   60以下
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


def _safe_native(value):
    """将numpy类型安全转换为Python原生类型"""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, dict):
        return {k: _safe_native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_native(v) for v in value]
    return value


# ============================================================
# 评分等级常量
# ============================================================
GRADE_S_PLUS = "S+"
GRADE_S = "S"
GRADE_A = "A"
GRADE_B = "B"
GRADE_C = "C"

GRADE_THRESHOLDS = [
    (90, GRADE_S_PLUS),
    (80, GRADE_S),
    (70, GRADE_A),
    (60, GRADE_B),
    (0, GRADE_C),
]

# 权重配置
WEIGHT_FUND = 40      # 资金面
WEIGHT_TREND = 40     # 趋势面
WEIGHT_SENTIMENT = 20  # 情绪面


@dataclass
class NineScoreResult:
    """九重评分结果"""
    total: float = 0.0
    grade: str = GRADE_C
    fund_score: float = 0.0       # 资金面得分（0-40）
    trend_score: float = 0.0      # 趋势面得分（0-40）
    sentiment_score: float = 0.0  # 情绪面得分（0-20）
    fund_breakdown: Dict = field(default_factory=dict)
    trend_breakdown: Dict = field(default_factory=dict)
    sentiment_breakdown: Dict = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    nine_pass_count: int = 0      # 通过九重数量

    def to_dict(self) -> Dict:
        return {
            "total": round(float(self.total), 1),
            "grade": self.grade,
            "fund_score": round(float(self.fund_score), 1),
            "trend_score": round(float(self.trend_score), 1),
            "sentiment_score": round(float(self.sentiment_score), 1),
            "fund_breakdown": _safe_native(self.fund_breakdown),
            "trend_breakdown": _safe_native(self.trend_breakdown),
            "sentiment_breakdown": _safe_native(self.sentiment_breakdown),
            "reasons": list(self.reasons),
            "nine_pass_count": int(self.nine_pass_count),
        }


class NineScoreEngine:
    """九重共振综合评分引擎"""

    def __init__(self):
        self.weight_fund = WEIGHT_FUND
        self.weight_trend = WEIGHT_TREND
        self.weight_sentiment = WEIGHT_SENTIMENT

    # ============================================================
    # 资金面评分（0-40分）
    # ============================================================
    def score_fund(self, volume_ratio: float = 1.0,
                   big_order_net: float = 0.0,
                   amount: float = 0.0,
                   turnover_rate: float = 0.0,
                   amount_rank_pct: float = 50.0) -> Tuple[float, Dict]:
        """
        资金面评分

        Args:
            volume_ratio: 量比（近5日均量/前5日均量）
            big_order_net: 大单净量（手，正为净流入）
            amount: 成交额（元）
            turnover_rate: 换手率（%）
            amount_rank_pct: 成交额全市场排名百分位（0-100，越高越活跃）

        Returns:
            (得分0-40, 明细dict)
        """
        breakdown = {}
        score = 0.0

        # 1. 量比评分（0-12分）
        # >=2.0: 12分, 1.5-2.0: 8-12分, 1.0-1.5: 4-8分, <1.0: 0-4分
        if volume_ratio >= 2.0:
            vr_score = 12.0
        elif volume_ratio >= 1.5:
            vr_score = 8.0 + (volume_ratio - 1.5) / 0.5 * 4.0
        elif volume_ratio >= 1.0:
            vr_score = 4.0 + (volume_ratio - 1.0) / 0.5 * 4.0
        else:
            vr_score = max(0, volume_ratio * 4.0)
        breakdown['volume_ratio'] = round(vr_score, 1)
        score += vr_score

        # 2. 大单净量评分（0-12分）
        # 连续为正且逐步放大得高分
        if big_order_net > 0:
            # 归一化：假设大单净量>5000手为极强
            bo_score = min(12.0, 4.0 + big_order_net / 5000.0 * 8.0)
        elif big_order_net == 0:
            bo_score = 2.0
        else:
            bo_score = max(0, 2.0 + big_order_net / 5000.0 * 2.0)
        breakdown['big_order_net'] = round(bo_score, 1)
        score += bo_score

        # 3. 成交额排名评分（0-8分）
        # 排名百分位越高（越活跃）得分越高
        ar_score = amount_rank_pct / 100.0 * 8.0
        breakdown['amount_rank'] = round(ar_score, 1)
        score += ar_score

        # 4. 换手率评分（0-8分）
        # 3-8%为最佳，过高(>15%)可能出货，过低(<1%)不活跃
        if 3.0 <= turnover_rate <= 8.0:
            tr_score = 8.0
        elif 1.0 <= turnover_rate < 3.0:
            tr_score = 4.0 + (turnover_rate - 1.0) / 2.0 * 4.0
        elif 8.0 < turnover_rate <= 15.0:
            tr_score = 8.0 - (turnover_rate - 8.0) / 7.0 * 3.0
        elif turnover_rate > 15.0:
            tr_score = max(2.0, 5.0 - (turnover_rate - 15.0) / 10.0 * 3.0)
        else:
            tr_score = turnover_rate * 4.0
        breakdown['turnover_rate'] = round(tr_score, 1)
        score += tr_score

        return round(min(score, 40.0), 1), breakdown

    # ============================================================
    # 趋势面评分（0-40分）
    # ============================================================
    def score_trend(self, ma_alignment: bool = False,
                    break_ma60: bool = False,
                    rps20: float = 50.0,
                    chip_peak_score: float = 50.0,
                    ma5_above_ma10: bool = False,
                    price_above_ma20: bool = False) -> Tuple[float, Dict]:
        """
        趋势面评分

        Args:
            ma_alignment: MA5>MA10>MA20 多头排列
            break_ma60: 首次突破60日线
            rps20: RPS20相对强度（0-100）
            chip_peak_score: 筹码峰评分（0-100，单峰密集+价格在峰上为高）
            ma5_above_ma10: MA5在MA10之上
            price_above_ma20: 价格在MA20之上

        Returns:
            (得分0-40, 明细dict)
        """
        breakdown = {}
        score = 0.0

        # 1. MA排列评分（0-10分）
        if ma_alignment:
            ma_score = 10.0
        elif ma5_above_ma10 and price_above_ma20:
            ma_score = 7.0
        elif ma5_above_ma10:
            ma_score = 5.0
        elif price_above_ma20:
            ma_score = 3.0
        else:
            ma_score = 1.0
        breakdown['ma_alignment'] = round(ma_score, 1)
        score += ma_score

        # 2. 突破60日线评分（0-8分）
        if break_ma60:
            b60_score = 8.0
        elif price_above_ma20:
            b60_score = 4.0
        else:
            b60_score = 1.0
        breakdown['break_ma60'] = round(b60_score, 1)
        score += b60_score

        # 3. RPS20评分（0-12分）
        # >=90: 12分, 80-90: 9-12分, 70-80: 6-9分, <70: 0-6分
        if rps20 >= 90:
            rps_score = 12.0
        elif rps20 >= 80:
            rps_score = 9.0 + (rps20 - 80) / 10.0 * 3.0
        elif rps20 >= 70:
            rps_score = 6.0 + (rps20 - 70) / 10.0 * 3.0
        else:
            rps_score = rps20 / 70.0 * 6.0
        breakdown['rps20'] = round(rps_score, 1)
        score += rps_score

        # 4. 筹码峰评分（0-10分）
        chip_score = chip_peak_score / 100.0 * 10.0
        breakdown['chip_peak'] = round(chip_score, 1)
        score += chip_score

        return round(min(score, 40.0), 1), breakdown

    # ============================================================
    # 情绪面评分（0-20分）
    # ============================================================
    def score_sentiment(self, market_cycle: str = "混沌期",
                        limit_up_gene: bool = False,
                        consecutive_board_height: int = 0,
                        sentiment_temperature: float = 50.0,
                        stock_in_hot_sector: bool = False) -> Tuple[float, Dict]:
        """
        情绪面评分

        Args:
            market_cycle: 市场情绪周期（上升期/混沌期/退潮期/冰点期）
            limit_up_gene: 是否有涨停基因（10日内涨停过）
            consecutive_board_height: 连板高度（0=非连板，1=首板，2=2连板...）
            sentiment_temperature: 情绪温度（0-100）
            stock_in_hot_sector: 是否在热门板块

        Returns:
            (得分0-20, 明细dict)
        """
        breakdown = {}
        score = 0.0

        # 1. 市场周期评分（0-8分）
        cycle_scores = {
            "上升期": 8.0,
            "混沌期": 5.0,
            "退潮期": 2.0,
            "冰点期": 1.0,
        }
        cycle_score = cycle_scores.get(market_cycle, 4.0)
        breakdown['market_cycle'] = round(cycle_score, 1)
        score += cycle_score

        # 2. 涨停基因评分（0-6分）
        if limit_up_gene:
            if consecutive_board_height >= 3:
                gene_score = 6.0
            elif consecutive_board_height == 2:
                gene_score = 5.0
            elif consecutive_board_height == 1:
                gene_score = 4.0
            else:
                gene_score = 3.0  # 有涨停基因但非连板
        else:
            gene_score = 1.0
        breakdown['limit_up_gene'] = round(gene_score, 1)
        score += gene_score

        # 3. 情绪温度评分（0-4分）
        temp_score = sentiment_temperature / 100.0 * 4.0
        breakdown['sentiment_temperature'] = round(temp_score, 1)
        score += temp_score

        # 4. 热门板块评分（0-2分）
        hot_score = 2.0 if stock_in_hot_sector else 0.5
        breakdown['hot_sector'] = round(hot_score, 1)
        score += hot_score

        return round(min(score, 20.0), 1), breakdown

    # ============================================================
    # 综合评分
    # ============================================================
    def calculate(self, fund_params: Optional[Dict] = None,
                  trend_params: Optional[Dict] = None,
                  sentiment_params: Optional[Dict] = None,
                  nine_pass_count: int = 0) -> NineScoreResult:
        """
        计算综合评分

        Args:
            fund_params: 资金面参数字典
            trend_params: 趋势面参数字典
            sentiment_params: 情绪面参数字典
            nine_pass_count: 通过九重过滤的数量

        Returns:
            NineScoreResult
        """
        result = NineScoreResult()
        result.nine_pass_count = nine_pass_count

        # 资金面
        fund_params = fund_params or {}
        fund_score, fund_bd = self.score_fund(**fund_params)
        result.fund_score = fund_score
        result.fund_breakdown = fund_bd

        # 趋势面
        trend_params = trend_params or {}
        trend_score, trend_bd = score_trend = self.score_trend(**trend_params)
        result.trend_score = trend_score
        result.trend_breakdown = trend_bd

        # 情绪面
        sentiment_params = sentiment_params or {}
        sent_score, sent_bd = self.score_sentiment(**sentiment_params)
        result.sentiment_score = sent_score
        result.sentiment_breakdown = sent_bd

        # 总分
        result.total = round(fund_score + trend_score + sent_score, 1)

        # 等级
        result.grade = self._get_grade(result.total)

        # 生成理由
        result.reasons = self._generate_reasons(result)

        return result

    @staticmethod
    def _get_grade(total: float) -> str:
        for threshold, grade in GRADE_THRESHOLDS:
            if total >= threshold:
                return grade
        return GRADE_C

    @staticmethod
    def _generate_reasons(result: NineScoreResult) -> List[str]:
        reasons = []
        if result.fund_score >= 30:
            reasons.append("资金面强劲")
        elif result.fund_score >= 20:
            reasons.append("资金面良好")
        if result.trend_score >= 30:
            reasons.append("趋势面强势")
        elif result.trend_score >= 20:
            reasons.append("趋势面良好")
        if result.sentiment_score >= 15:
            reasons.append("情绪面积极")
        if result.nine_pass_count >= 8:
            reasons.append(f"九重过滤通过{result.nine_pass_count}/9")
        return reasons


# ============================================================
# 单例
# ============================================================
_default_engine = None


def get_nine_score_engine() -> NineScoreEngine:
    """获取九重评分引擎单例"""
    global _default_engine
    if _default_engine is None:
        _default_engine = NineScoreEngine()
    return _default_engine
