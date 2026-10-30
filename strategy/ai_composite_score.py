# -*- coding: utf-8 -*-
"""
AI综合评分引擎 V1.0

融合三大评分体系，输出统一最终评分：
  1. 强势主力行为选股综合评分（force_behavior_score，0-100）
  2. 九重共振选股综合评分（nine_filter_score，0-100，资金40%+趋势40%+情绪20%）
  3. AI六维度评分（ai_six_dim_score，0-100）

加权计算（权重可配置，默认）：
  强势主力评分 35% + 九重评分 35% + AI六维 30%

如果某个评分缺失，则重新分配权重给其他评分。

输出：
  - composite_score  综合评分（0-100）
  - grade             等级（S+/S/A/B/观察/风险）
  - stage             所属阶段（吸筹/启动/主升/加速/风险）
  - advantages        优势列表（最多3条）
  - risks             风险列表（最多3条）
  - suggestion        操作建议（买入/等待/观察/减仓）
  - score_breakdown   各评分明细

设计原则：
  - 独立模块，不修改现有策略核心逻辑
  - 纯计算，无副作用，可被任何模块调用
  - 所有输入通过 dict 传入，兼容现有扫描结果格式
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

# 默认权重
DEFAULT_WEIGHTS = {
    "force_behavior_score": 0.35,
    "nine_filter_score": 0.35,
    "ai_six_dim_score": 0.30,
}

# 等级划分
GRADE_S_PLUS = "S+"
GRADE_S = "S"
GRADE_A = "A"
GRADE_B = "B"
GRADE_WATCH = "观察"
GRADE_RISK = "风险"

GRADE_THRESHOLDS = [
    (90, GRADE_S_PLUS),
    (80, GRADE_S),
    (70, GRADE_A),
    (60, GRADE_B),
    (50, GRADE_WATCH),
    (0, GRADE_RISK),
]

# 阶段
STAGE_ACCUMULATION = "吸筹"
STAGE_LAUNCH = "启动"
STAGE_MAIN_RISE = "主升"
STAGE_ACCELERATION = "加速"
STAGE_RISK = "风险"

# 操作建议
SUGGEST_BUY = "买入"
SUGGEST_WAIT = "等待"
SUGGEST_OBSERVE = "观察"
SUGGEST_REDUCE = "减仓"


# ============================================================
# 综合评分结果
# ============================================================

@dataclass
class CompositeScoreResult:
    """AI综合评分结果"""
    code: str = ""
    name: str = ""
    composite_score: float = 0.0
    grade: str = GRADE_RISK
    stage: str = ""
    advantages: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    suggestion: str = SUGGEST_OBSERVE
    score_breakdown: Dict = field(default_factory=dict)
    weights_used: Dict = field(default_factory=dict)
    missing_scores: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "composite_score": round(self.composite_score, 1),
            "grade": self.grade,
            "stage": self.stage,
            "advantages": list(self.advantages),
            "risks": list(self.risks),
            "suggestion": self.suggestion,
            "score_breakdown": dict(self.score_breakdown),
            "weights_used": dict(self.weights_used),
            "missing_scores": list(self.missing_scores),
        }


# ============================================================
# AI综合评分引擎
# ============================================================

class AICompositeScore:
    """
    AI综合评分引擎

    融合强势主力评分、九重评分、AI六维评分，输出统一最终评分。

    输入 stock_data 支持的字段（兼容现有扫描结果）：
      - code, name: 股票代码/名称
      - force_behavior_score: 强势主力综合评分（0-100），
        也可从嵌套字段 score.total 提取（main_force_behavior 结果）
      - nine_filter_score: 九重综合评分（0-100），
        也可从嵌套字段 score.total 提取（nine_filter 结果）
      - ai_six_dim_score: AI六维评分（0-100），
        也可从嵌套字段 score.total 提取
      - 技术指标字段（用于阶段判定和优势/风险分析）：
        price, change_pct, ma5, ma10, ma20, ma60,
        volume_ratio, rps20, turnover_rate, amount,
        support_price, pressure_price,
        layer_pass（九重通过状态列表）, pass_count,
        best_model_score, current_stage, buy_signal,
        intraday_signal
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Args:
            weights: 自定义权重字典，键为评分名称，值为权重（0-1）。
                     为 None 时使用默认权重 35/35/30。
        """
        self.weights = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
        # 归一化权重
        total_w = sum(self.weights.values())
        if total_w > 0:
            for k in self.weights:
                self.weights[k] = self.weights[k] / total_w

    # ============================================================
    # 主入口：计算单只股票综合评分
    # ============================================================

    def calculate(self, stock_data: dict) -> dict:
        """
        计算综合评分，返回完整结果。

        Args:
            stock_data: 股票数据字典，包含三个评分和技术指标。

        Returns:
            dict，包含 composite_score, grade, stage, advantages,
                  risks, suggestion, score_breakdown 等字段。
        """
        result = CompositeScoreResult()
        result.code = str(stock_data.get("code", ""))
        result.name = str(stock_data.get("name", ""))

        # 1. 提取三个评分
        scores = self._extract_scores(stock_data)
        result.score_breakdown = {
            "force_behavior_score": scores.get("force_behavior_score"),
            "nine_filter_score": scores.get("nine_filter_score"),
            "ai_six_dim_score": scores.get("ai_six_dim_score"),
        }

        # 2. 计算有效权重（缺失评分重新分配）
        effective_weights, missing = self._compute_effective_weights(scores)
        result.weights_used = effective_weights
        result.missing_scores = missing

        # 3. 加权计算综合评分
        composite = 0.0
        for key, weight in effective_weights.items():
            val = scores.get(key)
            if val is not None:
                composite += val * weight
        result.composite_score = round(min(100.0, max(0.0, composite)), 1)

        # 4. 等级划分
        result.grade = self._get_grade(result.composite_score)

        # 5. 阶段判定
        result.stage = self._determine_stage(stock_data)

        # 6. 优势/风险分析
        result.advantages = self._extract_advantages(stock_data, scores, result)
        result.risks = self._extract_risks(stock_data, scores, result)

        # 7. 操作建议
        result.suggestion = self._generate_suggestion(result)

        return result.to_dict()

    # ============================================================
    # 批量计算
    # ============================================================

    def batch_calculate(self, stock_list: list) -> list:
        """
        批量计算多只股票的综合评分。

        Args:
            stock_list: 股票数据字典列表。

        Returns:
            综合评分结果列表，按综合评分降序排列。
        """
        results = []
        for stock_data in stock_list:
            try:
                r = self.calculate(stock_data)
                results.append(r)
            except Exception as e:
                logger.warning(f"[AI Composite] 计算异常 {stock_data.get('code', '?')}: {e}")
                # 异常时返回最低评分结果
                results.append({
                    "code": str(stock_data.get("code", "")),
                    "name": str(stock_data.get("name", "")),
                    "composite_score": 0.0,
                    "grade": GRADE_RISK,
                    "stage": "",
                    "advantages": [],
                    "risks": [f"评分计算异常: {e}"],
                    "suggestion": SUGGEST_OBSERVE,
                    "score_breakdown": {},
                    "weights_used": {},
                    "missing_scores": [],
                })

        # 按综合评分降序
        results.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
        return results

    # ============================================================
    # 评分分布统计
    # ============================================================

    @staticmethod
    def grade_distribution(results: list) -> Dict[str, int]:
        """
        统计评分结果的等级分布。

        Args:
            results: batch_calculate 返回的结果列表。

        Returns:
            {S+: count, S: count, A: count, B: count, 观察: count, 风险: count}
        """
        dist = {
            GRADE_S_PLUS: 0,
            GRADE_S: 0,
            GRADE_A: 0,
            GRADE_B: 0,
            GRADE_WATCH: 0,
            GRADE_RISK: 0,
        }
        for r in results:
            grade = r.get("grade", GRADE_RISK)
            if grade in dist:
                dist[grade] += 1
            else:
                dist[GRADE_RISK] += 1
        return dist

    # ============================================================
    # 内部方法：提取评分
    # ============================================================

    def _extract_scores(self, stock_data: dict) -> Dict[str, Optional[float]]:
        """
        从 stock_data 中提取三个评分。

        支持多种字段名兼容：
          - 直接字段：force_behavior_score, nine_filter_score, ai_six_dim_score
          - 嵌套字段：score.total（需配合 source 标记或自动推断）
        """
        scores = {}

        # 强势主力评分
        fb = stock_data.get("force_behavior_score")
        if fb is None and stock_data.get("source") == "main_force":
            fb = self._safe_get_nested(stock_data, "score", "total")
        scores["force_behavior_score"] = self._normalize_score(fb)

        # 九重评分
        nf = stock_data.get("nine_filter_score")
        if nf is None and stock_data.get("source") == "nine_filter":
            nf = self._safe_get_nested(stock_data, "score", "total")
        scores["nine_filter_score"] = self._normalize_score(nf)

        # AI六维评分
        ai = stock_data.get("ai_six_dim_score")
        if ai is None and stock_data.get("source") == "ai_six_dim":
            ai = self._safe_get_nested(stock_data, "score", "total")
        scores["ai_six_dim_score"] = self._normalize_score(ai)

        return scores

    @staticmethod
    def _safe_get_nested(data: dict, key1: str, key2: str) -> Optional[float]:
        """安全获取嵌套字典值"""
        nested = data.get(key1)
        if isinstance(nested, dict):
            return nested.get(key2)
        return None

    @staticmethod
    def _normalize_score(val) -> Optional[float]:
        """将评分值归一化为 0-100 的浮点数，无效值返回 None"""
        if val is None:
            return None
        try:
            f = float(val)
            if f < 0 or f > 100:
                return None
            return round(f, 1)
        except (TypeError, ValueError):
            return None

    # ============================================================
    # 内部方法：计算有效权重
    # ============================================================

    def _compute_effective_weights(
        self, scores: Dict[str, Optional[float]]
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        根据可用评分重新分配权重。

        如果某个评分缺失，将其权重按比例分配给其他可用评分。
        """
        available = [k for k, v in scores.items() if v is not None]
        missing = [k for k, v in scores.items() if v is None]

        if not available:
            return {}, missing

        # 计算可用评分的默认权重总和
        available_weight_sum = sum(self.weights.get(k, 0) for k in available)

        if available_weight_sum <= 0:
            # 平均分配
            effective = {k: 1.0 / len(available) for k in available}
        else:
            # 按比例归一化
            effective = {
                k: self.weights.get(k, 0) / available_weight_sum
                for k in available
            }

        return effective, missing

    # ============================================================
    # 内部方法：等级划分
    # ============================================================

    @staticmethod
    def _get_grade(score: float) -> str:
        """根据综合评分返回等级"""
        for threshold, grade in GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return GRADE_RISK

    # ============================================================
    # 内部方法：阶段判定
    # ============================================================

    def _determine_stage(self, stock_data: dict) -> str:
        """
        基于技术指标判定股票当前阶段。

        阶段规则：
          - 吸筹：低位横盘 + 缩量 + MA粘合
          - 启动：突破平台 + 放量 + MA多头排列
          - 主升：连续上涨 + MA发散 + 量能稳定
          - 加速：急涨 + 量能放大 + 偏离MA
          - 风险：高位放量滞涨 + MA拐头 + 跌破关键支撑
        """
        price = self._to_float(stock_data.get("price"))
        change_pct = self._to_float(stock_data.get("change_pct", 0))
        ma5 = self._to_float(stock_data.get("ma5"))
        ma10 = self._to_float(stock_data.get("ma10"))
        ma20 = self._to_float(stock_data.get("ma20"))
        ma60 = self._to_float(stock_data.get("ma60"))
        volume_ratio = self._to_float(stock_data.get("volume_ratio", 1.0))
        rps20 = self._to_float(stock_data.get("rps20", 50.0))
        support = self._to_float(stock_data.get("support_price"))
        pressure = self._to_float(stock_data.get("pressure_price"))

        # 如果数据不足，返回空
        if price is None or price <= 0:
            return ""

        # 计算 MA 粘合度（MA5/MA10/MA20 相对偏差）
        ma_values = [v for v in [ma5, ma10, ma20] if v and v > 0]
        ma_convergence = 0.0
        if len(ma_values) >= 2:
            ma_max = max(ma_values)
            ma_min = min(ma_values)
            if ma_min > 0:
                ma_convergence = (ma_max - ma_min) / ma_min * 100  # 百分比

        # MA 多头排列
        ma_bullish = (
            ma5 is not None and ma10 is not None and ma20 is not None
            and ma5 > 0 and ma10 > 0 and ma20 > 0
            and ma5 > ma10 > ma20
        )

        # 价格偏离 MA5 的程度
        price_vs_ma5 = 0.0
        if ma5 and ma5 > 0:
            price_vs_ma5 = (price - ma5) / ma5 * 100

        # 跌破支撑
        below_support = support is not None and support > 0 and price < support * 0.98

        # 接近压力位
        near_pressure = pressure is not None and pressure > 0 and price >= pressure * 0.97

        # ============================================================
        # 风险阶段判定（优先级最高）
        # ============================================================
        # 高位放量滞涨 + MA拐头 + 跌破支撑
        ma_turning_down = (
            ma5 is not None and ma10 is not None
            and ma5 > 0 and ma10 > 0
            and ma5 < ma10  # MA5 跌破 MA10
        )
        high_volume_stagnation = (
            volume_ratio >= 1.5 and abs(change_pct) < 1.0
        )
        if (below_support and ma_turning_down) or (high_volume_stagnation and rps20 >= 85):
            return STAGE_RISK

        # ============================================================
        # 加速阶段：急涨 + 量能放大 + 大幅偏离MA
        # ============================================================
        if (
            change_pct >= 5.0
            and volume_ratio >= 2.0
            and price_vs_ma5 >= 8.0
        ):
            return STAGE_ACCELERATION

        # ============================================================
        # 主升阶段：连续上涨 + MA发散 + 量能稳定
        # ============================================================
        if (
            ma_bullish
            and ma_convergence >= 3.0  # MA 发散
            and 0.8 <= volume_ratio <= 2.5  # 量能稳定
            and rps20 >= 80
            and 0 < price_vs_ma5 < 10
        ):
            return STAGE_MAIN_RISE

        # ============================================================
        # 启动阶段：突破平台 + 放量 + MA多头排列
        # ============================================================
        breakout_signal = (
            near_pressure  # 接近或突破压力位
            or change_pct >= 3.0  # 当日大涨
        )
        if (
            ma_bullish
            and volume_ratio >= 1.3
            and breakout_signal
            and price_vs_ma5 < 8.0  # 未过度偏离
        ):
            return STAGE_LAUNCH

        # ============================================================
        # 吸筹阶段：低位横盘 + 缩量 + MA粘合
        # ============================================================
        if (
            ma_convergence <= 3.0  # MA 粘合
            and volume_ratio <= 1.2  # 缩量
            and abs(change_pct) <= 2.0  # 横盘
            and rps20 < 70  # 非强势
        ):
            return STAGE_ACCUMULATION

        # ============================================================
        # 兜底：根据 MA 状态和涨幅判定
        # ============================================================
        if ma_bullish and change_pct > 0:
            return STAGE_MAIN_RISE
        elif ma_bullish:
            return STAGE_LAUNCH
        elif ma_turning_down or below_support:
            return STAGE_RISK
        elif ma_convergence <= 4.0 and volume_ratio <= 1.3:
            return STAGE_ACCUMULATION
        else:
            return STAGE_LAUNCH  # 默认归为启动

    # ============================================================
    # 内部方法：优势分析
    # ============================================================

    def _extract_advantages(
        self, stock_data: dict, scores: dict, result: CompositeScoreResult
    ) -> List[str]:
        """自动提取最多3条优势"""
        advantages = []

        ma5 = self._to_float(stock_data.get("ma5"))
        ma10 = self._to_float(stock_data.get("ma10"))
        ma20 = self._to_float(stock_data.get("ma20"))
        ma60 = self._to_float(stock_data.get("ma60"))
        price = self._to_float(stock_data.get("price"))
        volume_ratio = self._to_float(stock_data.get("volume_ratio", 1.0))
        change_pct = self._to_float(stock_data.get("change_pct", 0))
        rps20 = self._to_float(stock_data.get("rps20", 50.0))
        pressure = self._to_float(stock_data.get("pressure_price"))
        pass_count = stock_data.get("pass_count")

        # MA多头排列
        if (
            ma5 and ma10 and ma20
            and ma5 > ma10 > ma20
        ):
            advantages.append("MA多头排列")

        # 量价齐升
        if change_pct > 0 and volume_ratio >= 1.3:
            advantages.append("量价齐升")

        # 突破压力位
        if pressure and pressure > 0 and price and price >= pressure * 0.98:
            advantages.append("突破压力位")

        # RPS20 强势
        if rps20 >= 90:
            advantages.append(f"RPS20强度{rps20:.0f}（全市场领先）")
        elif rps20 >= 80:
            advantages.append(f"RPS20强度{rps20:.0f}（强势股）")

        # 价格在 MA60 之上
        if ma60 and ma60 > 0 and price and price > ma60:
            advantages.append("站稳MA60生命线")

        # 九重过滤通过数多
        if pass_count is not None:
            try:
                pc = int(pass_count)
                if pc >= 8:
                    advantages.append(f"九重过滤通过{pc}/9")
                elif pc >= 7:
                    advantages.append(f"九重过滤通过{pc}/9")
            except (TypeError, ValueError):
                pass

        # 综合评分高
        if result.composite_score >= 85:
            advantages.append(f"综合评分{result.composite_score:.0f}分（{result.grade}级）")

        # 量比适中（资金关注）
        if 1.5 <= volume_ratio <= 3.0:
            advantages.append(f"量比{volume_ratio:.1f}（资金持续关注）")

        # 去重并限制最多3条
        seen = set()
        unique = []
        for a in advantages:
            if a not in seen:
                seen.add(a)
                unique.append(a)
            if len(unique) >= 3:
                break
        return unique

    # ============================================================
    # 内部方法：风险分析
    # ============================================================

    def _extract_risks(
        self, stock_data: dict, scores: dict, result: CompositeScoreResult
    ) -> List[str]:
        """自动提取最多3条风险"""
        risks = []

        ma5 = self._to_float(stock_data.get("ma5"))
        ma10 = self._to_float(stock_data.get("ma10"))
        ma20 = self._to_float(stock_data.get("ma20"))
        price = self._to_float(stock_data.get("price"))
        volume_ratio = self._to_float(stock_data.get("volume_ratio", 1.0))
        change_pct = self._to_float(stock_data.get("change_pct", 0))
        support = self._to_float(stock_data.get("support_price"))
        pressure = self._to_float(stock_data.get("pressure_price"))
        turnover_rate = self._to_float(stock_data.get("turnover_rate", 0))

        # 高位放量滞涨
        if volume_ratio >= 1.8 and abs(change_pct) < 1.5:
            risks.append("高位放量滞涨（可能出货）")

        # MA死叉
        if ma5 and ma10 and ma5 > 0 and ma10 > 0 and ma5 < ma10:
            risks.append("MA5死叉MA10")

        # 跌破支撑
        if support and support > 0 and price and price < support * 0.97:
            risks.append("跌破关键支撑位")

        # 短期涨幅过大
        if ma5 and ma5 > 0 and price:
            deviation = (price - ma5) / ma5 * 100
            if deviation >= 12:
                risks.append(f"短期涨幅过大（偏离MA5 {deviation:.0f}%）")
            elif deviation >= 8:
                risks.append(f"偏离MA5较远（{deviation:.0f}%）")

        # 换手率过高
        if turnover_rate >= 18:
            risks.append(f"换手率{turnover_rate:.1f}%过高（筹码松动）")
        elif turnover_rate >= 15:
            risks.append(f"换手率{turnover_rate:.1f}%偏高")

        # 接近压力位但未突破
        if (
            pressure and pressure > 0 and price
            and pressure * 0.95 <= price < pressure
        ):
            risks.append("接近压力位（需放量突破）")

        # 缩量下跌
        if change_pct < -2 and volume_ratio < 0.8:
            risks.append("缩量下跌（无人接盘）")

        # 放量下跌
        if change_pct < -3 and volume_ratio >= 1.5:
            risks.append("放量下跌（资金出逃）")

        # 综合评分低
        if result.composite_score < 60:
            risks.append(f"综合评分{result.composite_score:.0f}分偏低")

        # 去重并限制最多3条
        seen = set()
        unique = []
        for r in risks:
            if r not in seen:
                seen.add(r)
                unique.append(r)
            if len(unique) >= 3:
                break

        # 如果没有检测到风险，给出通用提示
        if not unique:
            if result.composite_score >= 70:
                unique.append("暂无明显风险，关注量能持续性")
            else:
                unique.append("评分偏低，需进一步观察确认")
        return unique

    # ============================================================
    # 内部方法：操作建议
    # ============================================================

    @staticmethod
    def _generate_suggestion(result: CompositeScoreResult) -> str:
        """
        基于综合评分和阶段输出操作建议。

        规则：
          - 买入：S+/S级 + 启动/主升阶段
          - 等待：A级 + 吸筹阶段
          - 观察：B级
          - 减仓：风险阶段 + 评分下降
        """
        grade = result.grade
        stage = result.stage
        score = result.composite_score

        # 减仓：风险阶段
        if stage == STAGE_RISK:
            return SUGGEST_REDUCE

        # 买入：S+/S级 + 启动/主升/加速阶段
        if grade in (GRADE_S_PLUS, GRADE_S) and stage in (
            STAGE_LAUNCH, STAGE_MAIN_RISE, STAGE_ACCELERATION
        ):
            return SUGGEST_BUY

        # 等待：A级 + 吸筹阶段
        if grade == GRADE_A and stage == STAGE_ACCUMULATION:
            return SUGGEST_WAIT

        # A级 + 启动/主升也可以买入
        if grade == GRADE_A and stage in (STAGE_LAUNCH, STAGE_MAIN_RISE):
            return SUGGEST_BUY

        # B级：观察
        if grade == GRADE_B:
            return SUGGEST_OBSERVE

        # 观察级：等待
        if grade == GRADE_WATCH:
            return SUGGEST_WAIT

        # 风险级：减仓/不推荐
        if grade == GRADE_RISK:
            return SUGGEST_REDUCE

        # 加速阶段 + 高分：谨慎买入
        if stage == STAGE_ACCELERATION and score >= 80:
            return SUGGEST_BUY

        return SUGGEST_OBSERVE

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def _to_float(val) -> Optional[float]:
        """安全转换为浮点数"""
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None


# ============================================================
# 便捷函数（旧版兼容）
# ============================================================

_default_engine = None


def get_ai_composite_score(weights: Optional[Dict[str, float]] = None) -> AICompositeScore:
    """获取AI综合评分引擎单例（旧版兼容）"""
    global _default_engine
    if _default_engine is None:
        _default_engine = AICompositeScore(weights)
    return _default_engine


# ============================================================
# V6.1 阶段2：AI综合评分引擎（新版）
# ============================================================
# 融合策略层评分 → 统一因子池 → AI综合评分 → 最终交易建议
#
# 权重配置（默认）：
#   force_behavior   0.30  强势主力评分
#   nine_filter      0.30  九重共振评分
#   ai_six_dim       0.25  AI六维评分
#   market_env       0.15  市场环境（预留/校验项）
# ============================================================

# 新版默认权重
V61_DEFAULT_WEIGHTS = {
    "force_behavior": 0.30,
    "nine_filter": 0.30,
    "ai_six_dim": 0.25,
    "market_environment": 0.15,
}

# 等级定义（与旧版一致，严格区间）
V61_GRADE_THRESHOLDS = [
    (90, GRADE_S_PLUS),
    (80, GRADE_S),
    (70, GRADE_A),
    (60, GRADE_B),
    (50, GRADE_WATCH),
    (0, GRADE_RISK),
]

# 交易建议映射
V61_ADVICE_MAP = {
    GRADE_S_PLUS: "强烈推荐买入/加仓",
    GRADE_S: "推荐买入",
    GRADE_A: "可买入，建议轻仓",
    GRADE_B: "观察，等待信号确认",
    GRADE_WATCH: "继续等待",
    GRADE_RISK: "回避/减仓",
}


@dataclass
class V61CompositeResult:
    """V6.1 AI综合评分结果"""
    code: str = ""
    name: str = ""
    composite_score: float = 0.0
    grade: str = GRADE_RISK
    trading_advice: str = ""
    factors: Dict = field(default_factory=dict)       # 各维度得分明细
    weights_used: Dict = field(default_factory=dict)   # 实际使用权重
    missing_factors: List[str] = field(default_factory=list)
    validation: Dict = field(default_factory=dict)     # 基础因子校验结果
    raw_scores: Dict = field(default_factory=dict)     # 原始各策略评分

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "composite_score": round(self.composite_score, 1),
            "grade": self.grade,
            "trading_advice": self.trading_advice,
            "factors": dict(self.factors),
            "weights_used": dict(self.weights_used),
            "missing_factors": list(self.missing_factors),
            "validation": dict(self.validation),
            "raw_scores": dict(self.raw_scores),
        }


class AICompositeScoreEngine:
    """
    V6.1 AI综合评分引擎

    融合三大策略评分体系 + 市场环境，输出统一最终评分和交易建议。

    架构：
      策略层（强势主力/九重共振/五买/三倍量/回调五日线/缠论）
        → 统一因子池
          → AI综合评分（加权融合 + 因子校验）
            → 最终交易建议

    输入 stock_data 支持的字段（兼容现有扫描结果格式）：
      - code, name: 股票代码/名称
      - force_behavior_score: 强势主力评分（0-100），
        也可从嵌套字段 score.total 提取（需 source="main_force"）
      - nine_filter_score: 九重评分（0-100），
        也可从嵌套字段 score.total 提取（需 source="nine_filter"）
      - ai_six_dim_score: AI六维评分（0-100），
        六维原始总分为0-120，自动归一化
      - market_environment_score: 市场环境评分（0-100），可选
      - 技术指标字段（用于因子校验）：
        price, change_pct/pct_chg, volume_ratio, ma5, ma10, ma20, ma60,
        amount, turnover_rate, rps20, support_price/support, pressure_price/pressure
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Args:
            weights: 自定义权重字典。为 None 时使用默认权重：
                     force_behavior 0.30, nine_filter 0.30,
                     ai_six_dim 0.25, market_environment 0.15
        """
        self.weights = dict(weights) if weights else dict(V61_DEFAULT_WEIGHTS)
        # 归一化权重
        total_w = sum(self.weights.values())
        if total_w > 0:
            for k in self.weights:
                self.weights[k] = self.weights[k] / total_w

        # V6.3 市场环境系数（默认未设置，不影响原有评分逻辑）
        self._market_env_score: Optional[float] = None
        self._market_env_type: Optional[str] = None
        self._market_env_factor: Optional[float] = None

    def set_market_env(self, env_score: float, env_type: str = "", factor: float = 1.0):
        """
        V6.3 新增：设置当前市场环境，用于调整个股评分系数。

        设置后，calculate() 会在加权评分基础上乘以环境系数：
          - 牛市(≥80): ×1.2
          - 震荡(50-79): ×1.0
          - 弱势(30-49): ×0.7
          - 风险(<30): 评分上限59.9（不超过观察级），禁追涨

        Args:
            env_score: 市场环境评分（0-100）
            env_type: 环境类型（牛市/震荡/弱势/风险）
            factor: 评分系数（1.2/1.0/0.7/0.0）
        """
        self._market_env_score = float(env_score)
        self._market_env_type = env_type
        self._market_env_factor = float(factor)

    def clear_market_env(self):
        """V6.3 新增：清除市场环境设置，恢复纯策略评分模式"""
        self._market_env_score = None
        self._market_env_type = None
        self._market_env_factor = None

    # ============================================================
    # 主入口：计算单只股票综合评分
    # ============================================================

    def calculate(self, stock_data: dict) -> dict:
        """
        计算综合评分。

        Args:
            stock_data: 股票数据字典，包含各策略评分和技术指标。

        Returns:
            dict，包含 composite_score, grade, trading_advice,
                  factors, weights_used, missing_factors, validation, raw_scores
        """
        result = V61CompositeResult()
        result.code = str(stock_data.get("code", ""))
        result.name = str(stock_data.get("name", ""))

        # 1. 提取各策略评分
        raw_scores = self._extract_all_scores(stock_data)
        result.raw_scores = dict(raw_scores)

        # 2. 因子校验（价格、成交量、均线趋势等基础因子）
        validation = self._validate_factors(stock_data)
        result.validation = validation

        # 3. 计算有效权重（缺失评分自动调整）
        effective_weights, missing = self._compute_effective_weights(raw_scores)
        result.weights_used = effective_weights
        result.missing_factors = missing

        # 4. 加权计算综合评分
        composite = 0.0
        factors_detail = {}
        for key, weight in effective_weights.items():
            val = raw_scores.get(key)
            if val is not None:
                weighted = val * weight
                composite += weighted
                factors_detail[key] = {
                    "raw_score": round(val, 1),
                    "weight": round(weight, 4),
                    "weighted_score": round(weighted, 2),
                }
            else:
                factors_detail[key] = {
                    "raw_score": None,
                    "weight": 0.0,
                    "weighted_score": 0.0,
                    "status": "missing",
                }

        # 5. 因子校验微调（如果校验不通过，适当扣分）
        penalty = self._compute_validation_penalty(validation)
        composite = max(0.0, composite - penalty)

        # 5.5 V6.3 市场环境系数调整（仅在设置了市场环境时生效）
        env_adjusted = False
        env_factor_applied = 1.0
        if self._market_env_factor is not None:
            env_factor_applied = self._market_env_factor
            if self._market_env_factor == 0.0:
                # 风险环境：评分上限59.9（不超过观察级）
                composite = min(composite, 59.9)
            else:
                composite = composite * self._market_env_factor
            env_adjusted = True
            composite = max(0.0, min(100.0, composite))

        result.composite_score = round(min(100.0, max(0.0, composite)), 1)

        # 6. 等级划分
        result.grade = self.get_grade(result.composite_score)

        # 7. 交易建议
        result.trading_advice = self.get_trading_advice(
            result.composite_score, result.grade
        )

        # 8. 记录因子明细
        factors_detail["_composite"] = round(result.composite_score, 1)
        factors_detail["_validation_penalty"] = round(penalty, 2)
        # V6.3 市场环境调整信息
        if env_adjusted:
            factors_detail["_market_env"] = {
                "env_score": self._market_env_score,
                "env_type": self._market_env_type,
                "factor": env_factor_applied,
                "adjusted": True,
            }
        else:
            factors_detail["_market_env"] = {"adjusted": False}
        result.factors = factors_detail

        return result.to_dict()

    # ============================================================
    # 等级划分
    # ============================================================

    @staticmethod
    def get_grade(score: float) -> str:
        """
        根据综合评分返回等级。

        等级区间：
          S+（90-100）：强烈推荐
          S（80-89.9）：推荐
          A（70-79.9）：可买入
          B（60-69.9）：观察
          观察（50-59.9）：等待
          风险（<50）：不推荐
        """
        for threshold, grade in V61_GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return GRADE_RISK

    # ============================================================
    # 交易建议
    # ============================================================

    @staticmethod
    def get_trading_advice(score: float, grade: str) -> str:
        """
        根据评分和等级返回交易建议。

        - S+/S：买入/加仓
        - A：可买入，轻仓
        - B：观察，等待信号
        - 观察：继续等待
        - 风险：回避/减仓
        """
        return V61_ADVICE_MAP.get(grade, "观察，等待信号确认")

    # ============================================================
    # 批量计算
    # ============================================================

    def batch_calculate(self, stock_list: list) -> list:
        """
        批量计算多只股票的综合评分，按综合评分降序排列。
        """
        results = []
        for stock_data in stock_list:
            try:
                r = self.calculate(stock_data)
                results.append(r)
            except Exception as e:
                logger.warning(
                    f"[V61 Composite] 计算异常 {stock_data.get('code', '?')}: {e}"
                )
                results.append({
                    "code": str(stock_data.get("code", "")),
                    "name": str(stock_data.get("name", "")),
                    "composite_score": 0.0,
                    "grade": GRADE_RISK,
                    "trading_advice": "回避/减仓",
                    "factors": {},
                    "weights_used": {},
                    "missing_factors": [],
                    "validation": {"error": str(e)},
                    "raw_scores": {},
                })
        results.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
        return results

    # ============================================================
    # 评分分布统计
    # ============================================================

    @staticmethod
    def grade_distribution(results: list) -> Dict[str, int]:
        """统计评分结果的等级分布"""
        dist = {
            GRADE_S_PLUS: 0, GRADE_S: 0, GRADE_A: 0,
            GRADE_B: 0, GRADE_WATCH: 0, GRADE_RISK: 0,
        }
        for r in results:
            grade = r.get("grade", GRADE_RISK)
            if grade in dist:
                dist[grade] += 1
            else:
                dist[GRADE_RISK] += 1
        return dist

    # ============================================================
    # 从现有缓存数据计算单只股票综合评分
    # ============================================================

    def calculate_composite_score(self, stock_code: str) -> Optional[dict]:
        """
        从现有扫描结果缓存中读取各策略评分，计算综合评分。

        数据源：
          - 强势主力评分：data/cache/scan_result_cache.json
          - 九重共振评分：data/cache/nine_filter_scan_cache.json
          - AI六维评分：cache/ai_analysis/ 目录下的 attention_score

        Args:
            stock_code: 股票代码（如 "000001"）

        Returns:
            综合评分结果 dict，若股票不在任何缓存中返回 None
        """
        import os
        import json

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stock_data = {"code": stock_code, "name": ""}
        found_any = False

        # 1. 读取强势主力评分
        force_path = os.path.join(
            project_root, "data", "cache", "scan_result_cache.json"
        )
        if os.path.exists(force_path):
            try:
                with open(force_path, "r", encoding="utf-8") as f:
                    force_data = json.load(f)
                if isinstance(force_data, list):
                    for item in force_data:
                        if str(item.get("code", "")) == str(stock_code):
                            stock_data["name"] = item.get("name", "")
                            score_obj = item.get("score", {})
                            if isinstance(score_obj, dict):
                                stock_data["force_behavior_score"] = score_obj.get("total")
                            # 补充技术指标
                            stock_data["price"] = item.get("price")
                            stock_data["pct_chg"] = item.get("pct_chg")
                            stock_data["support"] = item.get("support")
                            stock_data["pressure"] = item.get("pressure")
                            stock_data["current_stage"] = item.get("current_stage")
                            found_any = True
                            break
            except Exception as e:
                logger.warning(f"[V61] 读取强势主力缓存失败: {e}")

        # 2. 读取九重共振评分
        nine_path = os.path.join(
            project_root, "data", "cache", "nine_filter_scan_cache.json"
        )
        if os.path.exists(nine_path):
            try:
                with open(nine_path, "r", encoding="utf-8") as f:
                    nine_data = json.load(f)
                results = nine_data.get("results", []) if isinstance(nine_data, dict) else []
                for item in results:
                    if str(item.get("code", "")) == str(stock_code):
                        if not stock_data["name"]:
                            stock_data["name"] = item.get("name", "")
                        score_obj = item.get("score", {})
                        if isinstance(score_obj, dict):
                            stock_data["nine_filter_score"] = score_obj.get("total")
                        # 补充技术指标
                        if "price" not in stock_data:
                            stock_data["price"] = item.get("price")
                        stock_data["change_pct"] = item.get("change_pct")
                        stock_data["volume_ratio"] = item.get("volume_ratio")
                        stock_data["ma5"] = item.get("ma5")
                        stock_data["ma10"] = item.get("ma10")
                        stock_data["ma20"] = item.get("ma20")
                        stock_data["ma60"] = item.get("ma60")
                        stock_data["rps20"] = item.get("rps20")
                        stock_data["turnover_rate"] = item.get("turnover_rate")
                        stock_data["amount"] = item.get("amount")
                        stock_data["support_price"] = item.get("support_price")
                        stock_data["pressure_price"] = item.get("pressure_price")
                        stock_data["pass_count"] = item.get("pass_count")
                        found_any = True
                        break
            except Exception as e:
                logger.warning(f"[V61] 读取九重缓存失败: {e}")

        # 3. 读取AI六维评分（从 ai_analysis 缓存）
        ai_dir = os.path.join(project_root, "cache", "ai_analysis")
        if os.path.isdir(ai_dir):
            try:
                # 找最新的分析文件
                latest_file = None
                latest_time = 0
                for fname in os.listdir(ai_dir):
                    if fname.startswith(stock_code) and fname.endswith(".json"):
                        fpath = os.path.join(ai_dir, fname)
                        mtime = os.path.getmtime(fpath)
                        if mtime > latest_time:
                            latest_time = mtime
                            latest_file = fpath
                if latest_file:
                    with open(latest_file, "r", encoding="utf-8") as f:
                        ai_data = json.load(f)
                    # attention_score 作为 AI 六维评分的代理（0-100）
                    att_score = ai_data.get("attention_score")
                    if att_score is not None:
                        stock_data["ai_six_dim_score"] = float(att_score)
                    # 也可以用 strategy_part + ai_part - risk_part
                    if "ai_six_dim_score" not in stock_data:
                        sp = ai_data.get("strategy_part", 0)
                        ap = ai_data.get("ai_part", 0)
                        rp = ai_data.get("risk_part", 0)
                        derived = max(0, min(100, sp + ap - rp))
                        if derived > 0:
                            stock_data["ai_six_dim_score"] = derived
                    found_any = True
            except Exception as e:
                logger.warning(f"[V61] 读取AI分析缓存失败: {e}")

        if not found_any:
            return None

        return self.calculate(stock_data)

    # ============================================================
    # 内部方法：提取所有策略评分
    # ============================================================

    def _extract_all_scores(self, stock_data: dict) -> Dict[str, Optional[float]]:
        """
        从 stock_data 中提取各策略评分，兼容多种字段名。

        Returns:
            {force_behavior: float/None, nine_filter: float/None,
             ai_six_dim: float/None, market_environment: float/None}
        """
        scores = {}

        # 强势主力评分
        fb = stock_data.get("force_behavior_score")
        if fb is None and stock_data.get("source") == "main_force":
            fb = self._safe_get_nested(stock_data, "score", "total")
        scores["force_behavior"] = self._normalize_score(fb)

        # 九重共振评分
        nf = stock_data.get("nine_filter_score")
        if nf is None and stock_data.get("source") == "nine_filter":
            nf = self._safe_get_nested(stock_data, "score", "total")
        scores["nine_filter"] = self._normalize_score(nf)

        # AI六维评分（原始可能是0-120，需要归一化）
        ai = stock_data.get("ai_six_dim_score")
        if ai is None and stock_data.get("source") == "ai_six_dim":
            ai = stock_data.get("total_score")
            # 六维原始总分0-120，归一化到0-100
            if ai is not None:
                try:
                    ai = float(ai) / 120.0 * 100.0
                except (TypeError, ValueError):
                    ai = None
        scores["ai_six_dim"] = self._normalize_score(ai)

        # 市场环境评分（可选）
        me = stock_data.get("market_environment_score")
        if me is None:
            me = stock_data.get("market_env_score")
        scores["market_environment"] = self._normalize_score(me)

        return scores

    # ============================================================
    # 内部方法：因子校验
    # ============================================================

    def _validate_factors(self, stock_data: dict) -> Dict:
        """
        基础因子校验：价格、成交量、均线趋势等。

        校验项：
          - price_valid: 价格有效（>0）
          - volume_valid: 成交量有效（量比>0）
          - ma_trend: 均线趋势（多头/空头/粘合）
          - trend_aligned: 价格与均线趋势一致
          - support_pressure: 支撑压力位有效

        Returns:
            校验结果字典
        """
        validation = {
            "price_valid": False,
            "volume_valid": False,
            "ma_trend": "unknown",
            "trend_aligned": False,
            "support_pressure_valid": False,
            "overall_pass": True,
            "warnings": [],
        }

        price = self._to_float(stock_data.get("price"))
        change_pct = self._to_float(
            stock_data.get("change_pct", stock_data.get("pct_chg", 0))
        )
        volume_ratio = self._to_float(stock_data.get("volume_ratio", 1.0))
        ma5 = self._to_float(stock_data.get("ma5"))
        ma10 = self._to_float(stock_data.get("ma10"))
        ma20 = self._to_float(stock_data.get("ma20"))
        support = self._to_float(
            stock_data.get("support_price", stock_data.get("support"))
        )
        pressure = self._to_float(
            stock_data.get("pressure_price", stock_data.get("pressure"))
        )

        # 价格校验
        if price is not None and price > 0:
            validation["price_valid"] = True
        else:
            validation["warnings"].append("价格数据无效")
            validation["overall_pass"] = False

        # 成交量校验
        if volume_ratio is not None and volume_ratio > 0:
            validation["volume_valid"] = True
        else:
            validation["warnings"].append("成交量数据无效")

        # 均线趋势
        if ma5 and ma10 and ma20 and ma5 > 0 and ma10 > 0 and ma20 > 0:
            if ma5 > ma10 > ma20:
                validation["ma_trend"] = "bullish"
            elif ma5 < ma10 < ma20:
                validation["ma_trend"] = "bearish"
            else:
                validation["ma_trend"] = "mixed"
        else:
            validation["ma_trend"] = "insufficient_data"

        # 趋势一致性（价格在MA5之上 + 均线多头 = 一致）
        if (price and ma5 and ma5 > 0 and price >= ma5
                and validation["ma_trend"] == "bullish"):
            validation["trend_aligned"] = True
        elif (price and ma5 and ma5 > 0 and price < ma5
              and validation["ma_trend"] == "bearish"):
            validation["trend_aligned"] = True  # 下跌趋势也一致
        else:
            validation["trend_aligned"] = False

        # 支撑压力位
        if (support and support > 0) or (pressure and pressure > 0):
            validation["support_pressure_valid"] = True

        return validation

    # ============================================================
    # 内部方法：校验扣分
    # ============================================================

    @staticmethod
    def _compute_validation_penalty(validation: Dict) -> float:
        """
        根据因子校验结果计算扣分。

        扣分规则：
          - 价格无效：扣20分（严重）
          - 均线空头排列：扣5分
          - 趋势不一致：扣3分
        """
        penalty = 0.0
        if not validation.get("price_valid", True):
            penalty += 20.0
        if validation.get("ma_trend") == "bearish":
            penalty += 5.0
        if not validation.get("trend_aligned", True) and validation.get("ma_trend") != "insufficient_data":
            penalty += 3.0
        return penalty

    # ============================================================
    # 内部方法：计算有效权重
    # ============================================================

    def _compute_effective_weights(
        self, scores: Dict[str, Optional[float]]
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        根据可用评分重新分配权重。

        如果某个评分缺失，将其权重按比例分配给其他可用评分。
        market_environment 缺失时不影响其他因子（因其为预留项）。
        """
        available = [k for k, v in scores.items() if v is not None]
        missing = [k for k, v in scores.items() if v is None]

        if not available:
            return {}, missing

        # 计算可用评分的默认权重总和
        available_weight_sum = sum(self.weights.get(k, 0) for k in available)

        if available_weight_sum <= 0:
            # 平均分配
            effective = {k: 1.0 / len(available) for k in available}
        else:
            # 按比例归一化
            effective = {
                k: self.weights.get(k, 0) / available_weight_sum
                for k in available
            }

        return effective, missing

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def _safe_get_nested(data: dict, key1: str, key2: str) -> Optional[float]:
        """安全获取嵌套字典值"""
        nested = data.get(key1)
        if isinstance(nested, dict):
            return nested.get(key2)
        return None

    @staticmethod
    def _normalize_score(val) -> Optional[float]:
        """将评分值归一化为 0-100 的浮点数，无效值返回 None"""
        if val is None:
            return None
        try:
            f = float(val)
            if f < 0 or f > 100:
                return None
            return round(f, 1)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(val) -> Optional[float]:
        """安全转换为浮点数"""
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None


# ============================================================
# V6.1 便捷函数
# ============================================================

_v61_engine = None


def get_composite_engine(weights: Optional[Dict[str, float]] = None) -> AICompositeScoreEngine:
    """获取V6.1 AI综合评分引擎单例"""
    global _v61_engine
    if _v61_engine is None:
        _v61_engine = AICompositeScoreEngine(weights)
    return _v61_engine


def calculate_composite_score(stock_code: str) -> Optional[dict]:
    """
    便捷函数：从现有缓存数据计算单只股票综合评分。

    Args:
        stock_code: 股票代码

    Returns:
        综合评分结果 dict，或 None
    """
    return get_composite_engine().calculate_composite_score(stock_code)
