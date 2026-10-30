# -*- coding: utf-8 -*-
"""
V7.1 精准买点引擎 (BuyPointEngine)

目标：从"找到好股票"升级到"找到可以买的位置"。

核心能力：
  1. 四个买点类型检测：A主升启动 / B涨停回调 / C五买确认 / D横盘突破
  2. 多因子评分100分制：趋势30 + 资金30 + 形态20 + 情绪20
  3. 买入位置计算：最佳区间 / 突破价 / 止损 / 目标价（基于ATR/支撑位/前高压力）
  4. 买点解释系统：为什么买 / 风险 / 满足条件 / 未满足条件

接入现有模块（不重写，通过接口调用）：
  - strategy.base.TechnicalIndicators / VolumeAnalyzer / KlineDataParser
  - strategy.models.limit_up_pullback.LimitUpPullbackModel
  - strategy.models.box_breakout.BoxBreakoutModel
  - strategy.models.volume_breakout.VolumeBreakoutModel
  - strategy.chanlun_core.ChanlunCore（缠论买卖点）
  - strategy.ai_composite_score.AICompositeScoreEngine（综合评分参考）
  - strategy.market_environment.MarketEnvironment（市场环境）
  - backtest.strategy.five_buy 逻辑（独立适配，不依赖回测框架）

最高原则：
  - 保留所有原选股逻辑，不推翻
  - 不删除已有策略
  - 不改变数据中心
  - 不修改K线显示
  - 只开发买点引擎，不开发UI
  - 所有新增功能独立模块化
  - 保持向后兼容
  - 禁止使用模拟数据、随机数据、固定评分
  - 所有评分必须可以追溯来源
"""
import os
import sys
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

# 确保项目根目录在 path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from strategy.base import (
    KlineBar, ModelMatch, TechnicalIndicators, VolumeAnalyzer, KlineDataParser,
    LIMIT_UP_THRESHOLD, BIG_YANG_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================

# 买点等级
GRADE_A = "A"   # 主升启动点 - 强烈买点
GRADE_B = "B"   # 涨停回调低吸 - 二次启动买点
GRADE_C = "C"   # 五买确认 - 观察/试仓
GRADE_D = "D"   # 横盘突破 - 突破确认
GRADE_NONE = "N"  # 无明显买点

# 买点类型
BUY_TYPE_MAIN_LAUNCH = "主升启动"
BUY_TYPE_LIMIT_PULLBACK = "涨停回调"
BUY_TYPE_FIVE_BUY = "五买确认"
BUY_TYPE_BOX_BREAKOUT = "横盘突破"
BUY_TYPE_NONE = "无明显买点"

# 评分维度满分
SCORE_TREND_MAX = 30.0
SCORE_CAPITAL_MAX = 30.0
SCORE_PATTERN_MAX = 20.0
SCORE_SENTIMENT_MAX = 20.0
SCORE_TOTAL_MAX = 100.0

# 星级阈值
STARS_THRESHOLDS = [(90, 5), (80, 4), (70, 3), (60, 2), (0, 1)]

# 风险等级阈值
RISK_LOW_MAX = 30   # 评分>=70且止损空间<8% → 低风险
RISK_MID_MAX = 50   # 评分50-70 → 中风险


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ScoreBreakdown:
    """多因子评分明细（每项可追溯来源）"""
    trend: float = 0.0           # 趋势因子 0-30
    trend_detail: Dict = field(default_factory=dict)  # 趋势评分明细
    capital: float = 0.0         # 资金因子 0-30
    capital_detail: Dict = field(default_factory=dict)  # 资金评分明细
    pattern: float = 0.0         # 形态因子 0-20
    pattern_detail: Dict = field(default_factory=dict)  # 形态评分明细
    sentiment: float = 0.0       # 情绪因子 0-20
    sentiment_detail: Dict = field(default_factory=dict)  # 情绪评分明细
    total: float = 0.0           # 综合评分 0-100

    def to_dict(self) -> Dict:
        return {
            "trend": round(self.trend, 1),
            "trend_detail": self.trend_detail,
            "capital": round(self.capital, 1),
            "capital_detail": self.capital_detail,
            "pattern": round(self.pattern, 1),
            "pattern_detail": self.pattern_detail,
            "sentiment": round(self.sentiment, 1),
            "sentiment_detail": self.sentiment_detail,
            "total": round(self.total, 1),
        }


@dataclass
class PriceLevels:
    """买入位置计算结果"""
    current_price: float = 0.0
    best_buy_low: float = 0.0      # 最佳买入区间下限
    best_buy_high: float = 0.0     # 最佳买入区间上限
    breakout_price: float = 0.0    # 强势突破价
    stop_loss: float = 0.0         # 止损价
    target_low: float = 0.0        # 目标价下限
    target_high: float = 0.0       # 目标价上限
    atr: float = 0.0               # ATR(14)波动值
    support: float = 0.0           # 支撑位
    resistance: float = 0.0        # 前高压力位
    risk_reward_ratio: float = 0.0  # 盈亏比

    def to_dict(self) -> Dict:
        return {
            "current_price": round(self.current_price, 2),
            "best_buy_range": [round(self.best_buy_low, 2), round(self.best_buy_high, 2)],
            "breakout_price": round(self.breakout_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_range": [round(self.target_low, 2), round(self.target_high, 2)],
            "atr": round(self.atr, 2),
            "support": round(self.support, 2),
            "resistance": round(self.resistance, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
        }


@dataclass
class BuyPointResult:
    """买点分析完整结果"""
    code: str = ""
    name: str = ""
    date: str = ""

    # 买点等级与类型
    grade: str = GRADE_NONE            # A/B/C/D/N
    buy_type: str = BUY_TYPE_NONE      # 主升启动/涨停回调/五买确认/横盘突破/无明显买点

    # 评分
    score: float = 0.0                 # 综合评分 0-100
    score_breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    stars: int = 1                     # 星级 1-5

    # 风险
    risk_level: str = "高"             # 低/中/高

    # 价格计算
    price_levels: PriceLevels = field(default_factory=PriceLevels)

    # 解释系统
    reasons: List[str] = field(default_factory=list)           # 为什么买
    risks: List[str] = field(default_factory=list)             # 风险在哪里
    conditions_met: List[str] = field(default_factory=list)    # 满足条件
    conditions_not_met: List[str] = field(default_factory=list)  # 未满足条件

    # 计算依据（可追溯）
    calculation_basis: Dict = field(default_factory=dict)

    # 各买点类型检测结果（用于调试和追溯）
    buy_point_checks: Dict = field(default_factory=dict)

    # 外部模块接入结果
    chanlun_result: Dict = field(default_factory=dict)
    model_results: Dict = field(default_factory=dict)
    market_env: Dict = field(default_factory=dict)

    # ===== V7.2 增强：完整操作理由链（6个维度）=====
    # 1. 买点逻辑详解
    buy_point_logic: Dict = field(default_factory=dict)
    # 2. 买点位置描述
    position_context: Dict = field(default_factory=dict)
    # 3. 为什么这个位置买（3-5条，每条含指标名+当前值+阈值+判断）
    why_this_position: List[Dict] = field(default_factory=list)
    # 4. 为什么这个价格买（价格计算详解）
    why_this_price: Dict = field(default_factory=dict)
    # 5. 为什么选择这个股票（选股优势分析）
    why_this_stock: Dict = field(default_factory=dict)
    # 6. 操作理由（综合建议）
    action_advice: Dict = field(default_factory=dict)
    # 自然语言操作理由摘要（200-300字）
    action_summary: str = ""

    @staticmethod
    def _json_safe(obj):
        """递归转换 numpy 类型为 Python 原生类型，确保 JSON 可序列化"""
        if isinstance(obj, dict):
            return {k: BuyPointResult._json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [BuyPointResult._json_safe(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return [BuyPointResult._json_safe(v) for v in obj.tolist()]
        return obj

    def to_dict(self) -> Dict:
        return self._json_safe({
            "code": self.code,
            "name": self.name,
            "date": self.date,
            "grade": self.grade,
            "buy_type": self.buy_type,
            "score": round(self.score, 1),
            "score_breakdown": self.score_breakdown.to_dict(),
            "stars": self.stars,
            "risk_level": self.risk_level,
            "price_levels": self.price_levels.to_dict(),
            "reasons": self.reasons,
            "risks": self.risks,
            "conditions_met": self.conditions_met,
            "conditions_not_met": self.conditions_not_met,
            "calculation_basis": self.calculation_basis,
            "buy_point_checks": self.buy_point_checks,
            "chanlun_result": self.chanlun_result,
            "model_results": self.model_results,
            "market_env": self.market_env,
            # V7.2 增强：完整操作理由链
            "buy_point_logic": self.buy_point_logic,
            "position_context": self.position_context,
            "why_this_position": self.why_this_position,
            "why_this_price": self.why_this_price,
            "why_this_stock": self.why_this_stock,
            "action_advice": self.action_advice,
            "action_summary": self.action_summary,
        })


# ============================================================
# 买点引擎核心类
# ============================================================

class BuyPointEngine:
    """
    V7.1 精准买点引擎

    输入：
      kline_data: K线数据（支持 dict 格式 {'close':[],...} 或 list[dict] 格式）
      code: 股票代码（可选，用于接入外部模块）
      name: 股票名称（可选）
      market_env_data: 市场环境数据（可选，不传则自动获取）
      annotation_data: K线形态标注数据（可选）

    输出：
      BuyPointResult 对象，包含买点等级、类型、评分、价格区间、解释等完整信息

    使用示例：
      engine = BuyPointEngine()
      result = engine.analyze(kline_data, code="600000", name="浦发银行")
      print(result.to_dict())
    """

    def __init__(self):
        # 延迟初始化外部模块（避免导入时依赖失败）
        self._chanlun = None
        self._limit_up_model = None
        self._box_model = None
        self._volume_model = None
        self._composite_engine = None
        self._market_env = None
        self._pattern_analyzer = None

        # 参数配置（可追溯，非硬编码评分）
        self.params = {
            # A型主升启动参数
            "a_ma_cross_lookback": 3,       # MA5上穿MA10的回看天数
            "a_volume_ratio_min": 1.5,      # 成交量倍数最低要求
            "a_kdj_max": 50.0,              # KDJ金叉时K值上限
            "a_breakout_buffer": 0.005,     # 突破压力位缓冲(0.5%)

            # B型涨停回调参数
            "b_pullback_min": 5.0,          # 最小回撤幅度%
            "b_pullback_max": 15.0,         # 最大回撤幅度%
            "b_ma20_tolerance": 0.02,       # 不破20日线容差(2%)
            "b_volume_shrink_ratio": 0.75,  # 缩量阈值(前5日均量的75%)

            # C型五买确认参数
            "c_kdj_golden_max": 30.0,       # KDJ低位金叉K值上限
            "c_volume_recover_ratio": 0.8,  # 量能恢复阈值(前5日均量的80%)

            # D型横盘突破参数
            "d_box_min_days": 20,           # 横盘最小天数
            "d_box_max_days": 60,           # 横盘最大天数
            "d_box_amplitude_max": 25.0,    # 横盘最大振幅%
            "d_breakout_volume_ratio": 1.3, # 突破量比最低要求

            # 价格计算参数
            "atr_period": 14,               # ATR周期
            "best_buy_atr_mult": 0.5,       # 最佳买入区间 = 当前价 ± 0.5*ATR
            "stop_loss_atr_mult": 1.5,      # 止损 = 支撑位 - 1.5*ATR
            "target_rr_min": 2.0,           # 最小盈亏比
            "target_rr_max": 3.0,           # 最大盈亏比
        }

    # ============================================================
    # 主入口
    # ============================================================

    def analyze(self, kline_data, code: str = "", name: str = "",
                market_env_data: Optional[Dict] = None,
                annotation_data: Optional[Dict] = None) -> BuyPointResult:
        """
        分析单只股票的精准买点

        Args:
            kline_data: K线数据（dict 或 list[dict] 格式）
            code: 股票代码
            name: 股票名称
            market_env_data: 市场环境数据（可选）
            annotation_data: K线形态标注数据（可选）

        Returns:
            BuyPointResult
        """
        result = BuyPointResult(code=code, name=name)

        # 1. 解析K线数据
        parsed = self._parse_kline(kline_data)
        if parsed is None:
            result.reasons.append("数据不足，无法分析")
            result.conditions_not_met.append("K线数据不足30根")
            return result

        bars, opens, highs, lows, closes, volumes = parsed
        result.date = bars[-1].date if bars else ""
        result.price_levels.current_price = float(closes[-1])

        # 2. 计算技术指标（所有评分的基础，可追溯）
        indicators = self._calc_indicators(closes, highs, lows, volumes)
        result.calculation_basis["indicators"] = {
            "ma5": round(float(indicators["ma5"][-1]), 2) if not np.isnan(indicators["ma5"][-1]) else None,
            "ma10": round(float(indicators["ma10"][-1]), 2) if not np.isnan(indicators["ma10"][-1]) else None,
            "ma20": round(float(indicators["ma20"][-1]), 2) if not np.isnan(indicators["ma20"][-1]) else None,
            "ma60": round(float(indicators["ma60"][-1]), 2) if not np.isnan(indicators["ma60"][-1]) else None,
            "macd_dif": round(float(indicators["dif"][-1]), 4) if not np.isnan(indicators["dif"][-1]) else None,
            "macd_dea": round(float(indicators["dea"][-1]), 4) if not np.isnan(indicators["dea"][-1]) else None,
            "kdj_k": round(float(indicators["k"][-1]), 2) if not np.isnan(indicators["k"][-1]) else None,
            "kdj_d": round(float(indicators["d"][-1]), 2) if not np.isnan(indicators["d"][-1]) else None,
            "kdj_j": round(float(indicators["j"][-1]), 2) if not np.isnan(indicators["j"][-1]) else None,
            "volume_ratio_5d": round(float(indicators["vol_ratio"]), 2),
            "atr_14": round(float(indicators["atr"]), 2),
        }

        # 3. 接入外部模块（缠论、模型库、市场环境）
        self._integrate_external_modules(result, bars, closes, highs, lows, volumes,
                                         kline_data, market_env_data, annotation_data)

        # 4. 四个买点类型检测
        checks = self._detect_all_buy_points(bars, closes, highs, lows, volumes, indicators)
        result.buy_point_checks = checks

        # 5. 确定主买点类型和等级
        self._determine_buy_point(result, checks)

        # 6. 多因子评分（趋势30 + 资金30 + 形态20 + 情绪20）
        self._calc_multi_factor_score(result, bars, closes, highs, lows, volumes,
                                      indicators, checks)

        # 7. 买入位置计算（ATR/支撑位/前高压力）
        self._calc_price_levels(result, closes, highs, lows, indicators, checks)

        # 8. 风险等级
        self._calc_risk_level(result)

        # 9. 星级
        self._calc_stars(result)

        # 10. 买点解释系统
        self._generate_explanation(result, checks, indicators)

        # 11. V7.2 增强：完整操作理由链（6个维度 + 自然语言摘要）
        self._generate_action_chain(result, bars, closes, highs, lows, volumes,
                                    indicators, checks)

        return result

    # ============================================================
    # 步骤1：K线数据解析
    # ============================================================

    def _parse_kline(self, kline_data):
        """统一解析K线数据，返回 (bars, opens, highs, lows, closes, volumes)"""
        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
        except Exception as e:
            logger.warning(f"[BuyPoint] K线解析失败: {e}")
            return None

        if len(bars) < 30:
            return None
        return bars, opens, highs, lows, closes, volumes

    # ============================================================
    # 步骤2：技术指标计算
    # ============================================================

    def _calc_indicators(self, closes, highs, lows, volumes) -> Dict:
        """计算所有技术指标（基于真实数据，无硬编码）"""
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        ma60 = TechnicalIndicators.ma(closes, 60)
        dif, dea, macd_bar = TechnicalIndicators.macd(closes)
        k, d, j = TechnicalIndicators.kdj(highs, lows, closes)

        # 量比（近5日均量 / 前5日均量）
        vol_ratio = VolumeAnalyzer.volume_ratio(volumes, period=5)

        # ATR(14)
        atr = self._calc_atr(highs, lows, closes, period=self.params["atr_period"])

        return {
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "dif": dif, "dea": dea, "macd_bar": macd_bar,
            "k": k, "d": d, "j": j,
            "vol_ratio": vol_ratio, "atr": atr,
        }

    @staticmethod
    def _calc_atr(highs, lows, closes, period=14) -> float:
        """计算ATR(Average True Range)"""
        if len(closes) < period + 1:
            return 0.0
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_list.append(tr)
        if len(tr_list) < period:
            return float(np.mean(tr_list)) if tr_list else 0.0
        return float(np.mean(tr_list[-period:]))

    # ============================================================
    # 步骤3：接入外部模块
    # ============================================================

    def _integrate_external_modules(self, result, bars, closes, highs, lows, volumes,
                                    kline_data, market_env_data, annotation_data):
        """接入现有模块（缠论、模型库、市场环境、K线形态），全部容错"""
        # 3.1 缠论模块
        try:
            chanlun = self._get_chanlun()
            if chanlun:
                # 构造缠论需要的 dict 格式
                chanlun_input = self._to_chanlun_format(kline_data, bars)
                cl_result = chanlun.analyze(chanlun_input, period='day')
                result.chanlun_result = {
                    "score": cl_result.get("score", 0),
                    "level": cl_result.get("level", ""),
                    "trend": cl_result.get("trend", {}).get("status", ""),
                    "signals": [s.get("name", "") for s in cl_result.get("signals", [])],
                    "beichi": cl_result.get("beichi", {}).get("type", "") if cl_result.get("beichi") else "",
                    "zhongshu_type": cl_result.get("zhongshu", {}).get("type", "") if cl_result.get("zhongshu") else "",
                    "suggestion": cl_result.get("suggestion", ""),
                }
        except Exception as e:
            logger.debug(f"[BuyPoint] 缠论接入失败: {e}")
            result.chanlun_result = {"error": str(e)}

        # 3.2 三个模型库（涨停回调/箱体突破/量价突破）
        try:
            # 涨停回调模型
            lup_model = self._get_limit_up_model()
            if lup_model:
                lup = lup_model.analyze(bars, closes, highs, lows, volumes)
                result.model_results["limit_up_pullback"] = {
                    "matched": lup.matched,
                    "stage": lup.stage,
                    "score": lup.score,
                    "signals": lup.signals,
                    "support": lup.support,
                    "pressure": lup.pressure,
                }
        except Exception as e:
            logger.debug(f"[BuyPoint] 涨停回调模型接入失败: {e}")
            result.model_results["limit_up_pullback"] = {"error": str(e)}

        try:
            box_model = self._get_box_model()
            if box_model:
                box = box_model.analyze(bars, closes, highs, lows, volumes)
                result.model_results["box_breakout"] = {
                    "matched": box.matched,
                    "stage": box.stage,
                    "score": box.score,
                    "signals": box.signals,
                    "support": box.support,
                    "pressure": box.pressure,
                }
        except Exception as e:
            logger.debug(f"[BuyPoint] 箱体突破模型接入失败: {e}")
            result.model_results["box_breakout"] = {"error": str(e)}

        try:
            vol_model = self._get_volume_model()
            if vol_model:
                vol = vol_model.analyze(bars, closes, highs, lows, volumes)
                result.model_results["volume_breakout"] = {
                    "matched": vol.matched,
                    "stage": vol.stage,
                    "score": vol.score,
                    "signals": vol.signals,
                    "support": vol.support,
                    "pressure": vol.pressure,
                }
        except Exception as e:
            logger.debug(f"[BuyPoint] 量价突破模型接入失败: {e}")
            result.model_results["volume_breakout"] = {"error": str(e)}

        # 3.3 市场环境
        try:
            if market_env_data:
                result.market_env = market_env_data
            else:
                me = self._get_market_env()
                if me:
                    env = me.get_current_env()
                    if env:
                        result.market_env = {
                            "score": env.score,
                            "env_type": env.env_type,
                            "factor": env.factor,
                            "chase_allowed": env.chase_allowed,
                            "limit_up_count": env.limit_up_count,
                            "up_count": env.up_count,
                            "down_count": env.down_count,
                        }
        except Exception as e:
            logger.debug(f"[BuyPoint] 市场环境接入失败: {e}")
            result.market_env = {"error": str(e)}

        # 3.4 K线形态分析（可选，需要 annotation_data）
        if annotation_data:
            try:
                analyzer = self._get_pattern_analyzer()
                if analyzer:
                    pat = analyzer.analyze_annotation(
                        self._to_chanlun_format(kline_data, bars), annotation_data
                    )
                    result.calculation_basis["pattern_analysis"] = pat
            except Exception as e:
                logger.debug(f"[BuyPoint] K线形态分析失败: {e}")

    def _to_chanlun_format(self, kline_data, bars) -> Dict:
        """将K线数据转为缠论模块需要的 dict 格式"""
        if isinstance(kline_data, dict) and "close" in kline_data:
            return kline_data
        # 从 bars 构造
        return {
            "dates": [b.date for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }

    # ============================================================
    # 外部模块延迟初始化
    # ============================================================

    def _get_chanlun(self):
        if self._chanlun is None:
            try:
                from strategy.chanlun_core import get_chanlun_core
                self._chanlun = get_chanlun_core()
            except Exception:
                self._chanlun = False
        return self._chanlun if self._chanlun is not False else None

    def _get_limit_up_model(self):
        if self._limit_up_model is None:
            try:
                from strategy.models.limit_up_pullback import LimitUpPullbackModel
                self._limit_up_model = LimitUpPullbackModel()
            except Exception:
                self._limit_up_model = False
        return self._limit_up_model if self._limit_up_model is not False else None

    def _get_box_model(self):
        if self._box_model is None:
            try:
                from strategy.models.box_breakout import BoxBreakoutModel
                self._box_model = BoxBreakoutModel()
            except Exception:
                self._box_model = False
        return self._box_model if self._box_model is not False else None

    def _get_volume_model(self):
        if self._volume_model is None:
            try:
                from strategy.models.volume_breakout import VolumeBreakoutModel
                self._volume_model = VolumeBreakoutModel()
            except Exception:
                self._volume_model = False
        return self._volume_model if self._volume_model is not False else None

    def _get_composite_engine(self):
        if self._composite_engine is None:
            try:
                from strategy.ai_composite_score import get_composite_engine
                self._composite_engine = get_composite_engine()
            except Exception:
                self._composite_engine = False
        return self._composite_engine if self._composite_engine is not False else None

    def _get_market_env(self):
        if self._market_env is None:
            try:
                from strategy.market_environment import get_market_environment
                self._market_env = get_market_environment()
            except Exception:
                self._market_env = False
        return self._market_env if self._market_env is not False else None

    def _get_pattern_analyzer(self):
        if self._pattern_analyzer is None:
            try:
                from kline_annotation_training.ai_pattern_analyzer import AIPatternAnalyzer
                self._pattern_analyzer = AIPatternAnalyzer()
            except Exception:
                self._pattern_analyzer = False
        return self._pattern_analyzer if self._pattern_analyzer is not False else None

    # ============================================================
    # 步骤4：四个买点类型检测
    # ============================================================

    def _detect_all_buy_points(self, bars, closes, highs, lows, volumes, indicators) -> Dict:
        """
        检测四个买点类型，每个返回 {matched: bool, conditions: {...}, score: float}
        """
        return {
            "A_main_launch": self._detect_a_main_launch(bars, closes, highs, lows, volumes, indicators),
            "B_limit_pullback": self._detect_b_limit_pullback(bars, closes, highs, lows, volumes, indicators),
            "C_five_buy": self._detect_c_five_buy(bars, closes, highs, lows, volumes, indicators),
            "D_box_breakout": self._detect_d_box_breakout(bars, closes, highs, lows, volumes, indicators),
        }

    # ---------- A型：主升启动点 ----------

    def _detect_a_main_launch(self, bars, closes, highs, lows, volumes, indicators) -> Dict:
        """
        买点A：主升启动点
        条件：
          1. MA5上穿MA10（近3天内）
          2. 成交量 ≥ 1.5倍（近5日均量比）
          3. MACD(8,21,5)金叉（近3天内）
          4. KDJ(13,3,3) K值<50 且金叉
          5. 突破近期压力位（近20日高点）
        """
        result = {"matched": False, "conditions": {}, "score": 0.0, "details": {}}
        last_idx = len(bars) - 1
        cond = result["conditions"]

        ma5 = indicators["ma5"]
        ma10 = indicators["ma10"]
        dif = indicators["dif"]
        dea = indicators["dea"]
        k_arr = indicators["k"]
        d_arr = indicators["d"]
        vol_ratio = indicators["vol_ratio"]

        # 条件1：MA5上穿MA10（近3天内发生金叉）
        ma_cross = False
        cross_idx = None
        lookback = self.params["a_ma_cross_lookback"]
        for i in range(max(1, last_idx - lookback + 1), last_idx + 1):
            if (not np.isnan(ma5[i]) and not np.isnan(ma10[i]) and
                    not np.isnan(ma5[i - 1]) and not np.isnan(ma10[i - 1])):
                if ma5[i - 1] <= ma10[i - 1] and ma5[i] > ma10[i]:
                    ma_cross = True
                    cross_idx = i
                    break
        # 也接受当前MA5>MA10且刚形成（3天内MA5从下方穿越）
        if not ma_cross and last_idx >= 1:
            if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx]) and
                    ma5[last_idx] > ma10[last_idx]):
                # 检查是否在3天内刚上穿
                for i in range(max(1, last_idx - 2), last_idx):
                    if (not np.isnan(ma5[i]) and not np.isnan(ma10[i]) and
                            ma5[i] <= ma10[i]):
                        ma_cross = True
                        cross_idx = last_idx
                        break
        cond["ma5_cross_ma10"] = ma_cross

        # 条件2：成交量放大（量比 ≥ 1.5）
        vol_expand = vol_ratio >= self.params["a_volume_ratio_min"]
        cond["volume_expand"] = vol_expand
        result["details"]["volume_ratio"] = round(float(vol_ratio), 2)

        # 条件3：MACD金叉（近3天内）
        macd_cross = TechnicalIndicators.is_macd_golden(dif, dea, last_idx)
        if not macd_cross:
            for i in range(max(1, last_idx - 2), last_idx):
                if TechnicalIndicators.is_macd_golden(dif, dea, i):
                    macd_cross = True
                    break
        cond["macd_golden"] = macd_cross

        # 条件4：KDJ K值<50 且金叉
        kdj_ok = False
        if not np.isnan(k_arr[last_idx]) and not np.isnan(d_arr[last_idx]):
            kdj_golden = TechnicalIndicators.is_kdj_golden(k_arr, d_arr, last_idx)
            if not kdj_golden:
                for i in range(max(1, last_idx - 2), last_idx):
                    if TechnicalIndicators.is_kdj_golden(k_arr, d_arr, i):
                        kdj_golden = True
                        break
            kdj_ok = kdj_golden and k_arr[last_idx] < self.params["a_kdj_max"]
        cond["kdj_golden_below_50"] = kdj_ok
        result["details"]["kdj_k"] = round(float(k_arr[last_idx]), 2) if not np.isnan(k_arr[last_idx]) else None

        # 条件5：突破近期压力位（近20日高点，不含当日）
        breakout = False
        if last_idx >= 20:
            recent_high = float(np.max(highs[-20:-1]))
            buffer = self.params["a_breakout_buffer"]
            if closes[last_idx] > recent_high * (1 - buffer):
                breakout = True
            result["details"]["recent_20d_high"] = round(recent_high, 2)
        cond["breakout_pressure"] = breakout

        # 评分：满足条件数 / 5 * 100
        met_count = sum(1 for v in cond.values() if v)
        result["score"] = round(met_count / 5.0 * 100, 1)
        result["matched"] = met_count >= 4  # 满足4个以上条件视为A型买点
        result["details"]["conditions_met"] = met_count

        return result

    # ---------- B型：涨停回调低吸 ----------

    def _detect_b_limit_pullback(self, bars, closes, highs, lows, volumes, indicators) -> Dict:
        """
        买点B：涨停回调低吸（二次启动买点）
        条件：
          1. 近30日内有涨停（或大阳≥5%）
          2. 从高点回撤 5%-15%
          3. 缩量调整（近5日均量 < 前5日75%）
          4. 不破20日线（当前价 ≥ MA20 * 0.98）
          5. 再次放量迹象（近3日量能回升）
        """
        result = {"matched": False, "conditions": {}, "score": 0.0, "details": {}}
        last_idx = len(bars) - 1
        cond = result["conditions"]
        ma20 = indicators["ma20"]

        # 条件1：近30日内有涨停或大阳线
        has_limit_up = False
        launch_idx = None
        for i in range(max(0, last_idx - 29), last_idx + 1):
            if bars[i].pct_chg >= LIMIT_UP_THRESHOLD:
                has_limit_up = True
                launch_idx = i
                break
        if not has_limit_up:
            for i in range(max(0, last_idx - 29), last_idx + 1):
                if bars[i].pct_chg >= BIG_YANG_THRESHOLD:
                    has_limit_up = True
                    launch_idx = i
                    break
        cond["has_recent_launch"] = has_limit_up
        if launch_idx is not None:
            result["details"]["launch_date"] = bars[launch_idx].date
            result["details"]["launch_pct"] = round(bars[launch_idx].pct_chg, 2)

        # 条件2：从高点回撤 5%-15%
        drawdown_ok = False
        drawdown = 0.0
        if launch_idx is not None and last_idx > launch_idx:
            peak_after = float(np.max(highs[launch_idx:]))
            current = float(closes[last_idx])
            if peak_after > 0:
                drawdown = (peak_after - current) / peak_after * 100
                if self.params["b_pullback_min"] <= drawdown <= self.params["b_pullback_max"]:
                    drawdown_ok = True
            result["details"]["peak_after_launch"] = round(peak_after, 2)
        cond["drawdown_5_15pct"] = drawdown_ok
        result["details"]["drawdown_pct"] = round(drawdown, 2)

        # 条件3：缩量调整
        is_shrinking = VolumeAnalyzer.is_volume_shrinking(volumes, period=5)
        cond["volume_shrinking"] = is_shrinking

        # 条件4：不破20日线
        ma20_support = False
        if not np.isnan(ma20[last_idx]) and ma20[last_idx] > 0:
            tol = self.params["b_ma20_tolerance"]
            if closes[last_idx] >= ma20[last_idx] * (1 - tol):
                ma20_support = True
            result["details"]["ma20"] = round(float(ma20[last_idx]), 2)
        cond["above_ma20"] = ma20_support

        # 条件5：再次放量迹象（近3日量能 > 近5日缩量阶段均量）
        volume_recover = False
        if last_idx >= 8:
            recent_3d_vol = float(np.mean(volumes[-3:]))
            shrink_5d_vol = float(np.mean(volumes[-8:-3]))
            if shrink_5d_vol > 0 and recent_3d_vol > shrink_5d_vol * 1.05:
                volume_recover = True
            result["details"]["recent_3d_vol_ratio"] = round(
                recent_3d_vol / shrink_5d_vol, 2) if shrink_5d_vol > 0 else 0
        cond["volume_recovering"] = volume_recover

        # 评分
        met_count = sum(1 for v in cond.values() if v)
        result["score"] = round(met_count / 5.0 * 100, 1)
        result["matched"] = met_count >= 4
        result["details"]["conditions_met"] = met_count

        return result

    # ---------- C型：五买确认 ----------

    def _detect_c_five_buy(self, bars, closes, highs, lows, volumes, indicators) -> Dict:
        """
        买点C：五买确认（观察/试仓）
        条件：
          1. 底背离（价格创新低，MACD力度减弱）或 下跌结束（近5日不再创新低）
          2. MACD改善（DIF拐头向上 或 MACD柱缩短）
          3. KDJ低位金叉（K值<30）
          4. 量能恢复（近3日量能 > 近5日缩量阶段80%）
          5. 倍量启动后回踩五日线承接（五买核心逻辑）
        """
        result = {"matched": False, "conditions": {}, "score": 0.0, "details": {}}
        last_idx = len(bars) - 1
        cond = result["conditions"]
        dif = indicators["dif"]
        dea = indicators["dea"]
        macd_bar = indicators["macd_bar"]
        k_arr = indicators["k"]
        d_arr = indicators["d"]
        ma5 = indicators["ma5"]

        # 条件1：底背离 或 下跌结束
        bottom_signal = False
        # 1a. 底背离检测：近20日内价格创新低但MACD未创新低
        if last_idx >= 20:
            # 找近期两个低点
            recent_low_idx = int(np.argmin(lows[-20:])) + last_idx - 19
            if recent_low_idx >= 5:
                prev_low_idx = int(np.argmin(lows[max(0, recent_low_idx - 15):recent_low_idx]))
                prev_low_idx = prev_low_idx + max(0, recent_low_idx - 15)
                if (lows[recent_low_idx] < lows[prev_low_idx] and
                        not np.isnan(dif[recent_low_idx]) and not np.isnan(dif[prev_low_idx]) and
                        dif[recent_low_idx] > dif[prev_low_idx]):
                    bottom_signal = True
                    result["details"]["bottom_beichi"] = True
        # 1b. 下跌结束：近5日最低价 > 前10日最低价
        if not bottom_signal and last_idx >= 15:
            recent_5d_low = float(np.min(lows[-5:]))
            prev_10d_low = float(np.min(lows[-15:-5]))
            if recent_5d_low > prev_10d_low:
                bottom_signal = True
                result["details"]["decline_ended"] = True
        cond["bottom_or_decline_end"] = bottom_signal

        # 条件2：MACD改善（DIF拐头向上 或 绿柱缩短）
        macd_improve = False
        if last_idx >= 3 and not np.isnan(dif[last_idx]) and not np.isnan(dif[last_idx - 2]):
            if dif[last_idx] > dif[last_idx - 2]:
                macd_improve = True
        if not macd_improve and last_idx >= 3 and len(macd_bar) > 3:
            # 绿柱缩短（负值绝对值减小）
            if (macd_bar[last_idx] < 0 and macd_bar[last_idx - 1] < 0 and
                    macd_bar[last_idx] > macd_bar[last_idx - 1]):
                macd_improve = True
        cond["macd_improving"] = macd_improve

        # 条件3：KDJ低位金叉（K值<30）
        kdj_low_golden = False
        if not np.isnan(k_arr[last_idx]) and not np.isnan(d_arr[last_idx]):
            if TechnicalIndicators.is_kdj_golden(k_arr, d_arr, last_idx):
                if k_arr[last_idx] < self.params["c_kdj_golden_max"]:
                    kdj_low_golden = True
            # 近3天内金叉也接受
            if not kdj_low_golden:
                for i in range(max(1, last_idx - 2), last_idx):
                    if TechnicalIndicators.is_kdj_golden(k_arr, d_arr, i):
                        if not np.isnan(k_arr[last_idx]) and k_arr[last_idx] < 40:
                            kdj_low_golden = True
                            break
        cond["kdj_low_golden"] = kdj_low_golden
        result["details"]["kdj_k"] = round(float(k_arr[last_idx]), 2) if not np.isnan(k_arr[last_idx]) else None

        # 条件4：量能恢复
        volume_recover = False
        if last_idx >= 8:
            recent_3d = float(np.mean(volumes[-3:]))
            shrink_5d = float(np.mean(volumes[-8:-3]))
            if shrink_5d > 0:
                ratio = recent_3d / shrink_5d
                if ratio >= self.params["c_volume_recover_ratio"]:
                    volume_recover = True
                result["details"]["volume_recover_ratio"] = round(ratio, 2)
        cond["volume_recover"] = volume_recover

        # 条件5：五买核心逻辑 - 倍量启动后缩量回踩五日线承接
        five_buy_confirm = self._check_five_buy_logic(bars, closes, volumes, ma5, last_idx)
        cond["five_buy_ma5_support"] = five_buy_confirm

        # 评分
        met_count = sum(1 for v in cond.values() if v)
        result["score"] = round(met_count / 5.0 * 100, 1)
        result["matched"] = met_count >= 3  # C型要求较低，3个条件即可
        result["details"]["conditions_met"] = met_count

        return result

    def _check_five_buy_logic(self, bars, closes, volumes, ma5, last_idx) -> bool:
        """
        五买核心逻辑检测（适配自 backtest/strategy/five_buy.py）：
        1. 近20日内有倍量启动K线（量比≥1.2，阳线）
        2. 启动后上涨确认（最高价 > 启动收盘价×1.02）
        3. 缩量回踩（当前量 < 启动日量）
        4. 回踩不破启动低点
        5. MA5接近启动价 或 价格站回MA5
        """
        if last_idx < 10:
            return False

        # 1. 找倍量启动K线（近20日内）
        start_idx = None
        for i in range(max(1, last_idx - 19), last_idx - 4):
            if volumes[i - 1] > 0 and volumes[i] >= volumes[i - 1] * 1.2:
                if closes[i] > bars[i].open:  # 阳线
                    start_idx = i
                    break

        if start_idx is None:
            return False

        start_price = closes[start_idx]
        start_low = lows[start_idx] if 'lows' in dir() else bars[start_idx].low
        start_volume = volumes[start_idx]

        # 2. 启动后上涨确认
        future_high = float(np.max([b.high for b in bars[start_idx + 1:min(start_idx + 10, last_idx + 1)]]))
        if future_high < start_price * 1.02:
            return False

        # 3. 当前缩量
        if volumes[last_idx] >= start_volume:
            return False

        # 4. 回踩不破启动低点
        pullback_low = float(np.min([b.low for b in bars[start_idx + 1:last_idx + 1]]))
        if pullback_low < start_low:
            return False

        # 5. MA5承接：价格接近MA5 或 站回MA5
        if not np.isnan(ma5[last_idx]) and ma5[last_idx] > 0:
            # 价格在MA5附近（±2%）或站上MA5
            if abs(closes[last_idx] - ma5[last_idx]) / ma5[last_idx] < 0.03:
                return True
            if closes[last_idx] > ma5[last_idx]:
                return True

        return False

    # ---------- D型：横盘突破 ----------

    def _detect_d_box_breakout(self, bars, closes, highs, lows, volumes, indicators) -> Dict:
        """
        买点D：横盘突破
        条件：
          1. 横盘20-60天（近期有明确整理区间）
          2. 波动收窄（横盘区间振幅 < 25%）
          3. 放量突破（突破日量比 ≥ 1.3）
          4. 突破箱体上沿
          5. 均线粘合后发散（MA5/MA10/MA20差距收窄后开始发散）
        """
        result = {"matched": False, "conditions": {}, "score": 0.0, "details": {}}
        last_idx = len(bars) - 1
        cond = result["conditions"]
        ma5 = indicators["ma5"]
        ma10 = indicators["ma10"]
        ma20 = indicators["ma20"]

        # 条件1+2：检测横盘区间（20-60天，振幅<25%）
        box_info = self._detect_consolidation(highs, lows, closes, last_idx)
        has_box = box_info["found"]
        cond["consolidation_20_60d"] = has_box
        result["details"]["box_days"] = box_info.get("days", 0)
        result["details"]["box_amplitude"] = box_info.get("amplitude", 0)
        result["details"]["box_top"] = box_info.get("top", 0)
        result["details"]["box_bottom"] = box_info.get("bottom", 0)

        # 条件3：放量突破
        vol_breakout = False
        if has_box:
            box_avg_vol = float(np.mean(volumes[box_info["start"]:box_info["end"] + 1]))
            if box_avg_vol > 0 and volumes[last_idx] >= box_avg_vol * self.params["d_breakout_volume_ratio"]:
                vol_breakout = True
            result["details"]["breakout_volume_ratio"] = round(
                volumes[last_idx] / box_avg_vol, 2) if box_avg_vol > 0 else 0
        cond["volume_breakout"] = vol_breakout

        # 条件4：突破箱体上沿
        price_breakout = False
        if has_box and box_info["top"] > 0:
            if closes[last_idx] > box_info["top"] * 0.995:
                price_breakout = True
        cond["price_breakout_box"] = price_breakout

        # 条件5：均线粘合后发散
        ma_divergence = False
        if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx]) and
                not np.isnan(ma20[last_idx]) and ma20[last_idx] > 0):
            # 当前均线开始发散（MA5>MA10>MA20）
            if ma5[last_idx] > ma10[last_idx] > ma20[last_idx]:
                # 横盘期间均线粘合（差距<5%）
                if has_box:
                    mid = (box_info["start"] + box_info["end"]) // 2
                    if (not np.isnan(ma5[mid]) and not np.isnan(ma10[mid]) and
                            not np.isnan(ma20[mid]) and ma20[mid] > 0):
                        gap = (ma5[mid] - ma20[mid]) / ma20[mid] * 100
                        if abs(gap) < 8:  # 横盘期间粘合
                            ma_divergence = True
                else:
                    ma_divergence = True
        cond["ma_divergence"] = ma_divergence

        # 评分
        met_count = sum(1 for v in cond.values() if v)
        result["score"] = round(met_count / 5.0 * 100, 1)
        result["matched"] = met_count >= 3
        result["details"]["conditions_met"] = met_count

        return result

    def _detect_consolidation(self, highs, lows, closes, last_idx) -> Dict:
        """检测横盘整理区间"""
        result = {"found": False, "start": 0, "end": 0, "days": 0,
                  "top": 0.0, "bottom": 0.0, "amplitude": 0.0}

        min_days = self.params["d_box_min_days"]
        max_days = self.params["d_box_max_days"]
        max_amp = self.params["d_box_amplitude_max"]

        # 从最近往前找横盘区间
        for days in range(min_days, min(max_days, last_idx) + 1):
            start = last_idx - days
            if start < 0:
                break
            seg_high = float(np.max(highs[start:last_idx]))
            seg_low = float(np.min(lows[start:last_idx]))
            if seg_low <= 0:
                continue
            amplitude = (seg_high - seg_low) / seg_low * 100
            if amplitude <= max_amp:
                # 波动收窄：后半段振幅 < 前半段振幅的1.5倍
                mid = (start + last_idx) // 2
                first_amp = float(np.max(highs[start:mid]) - np.min(lows[start:mid]))
                second_amp = float(np.max(highs[mid:last_idx]) - np.min(lows[mid:last_idx]))
                if first_amp > 0 and second_amp < first_amp * 1.5:
                    result.update({
                        "found": True, "start": start, "end": last_idx - 1,
                        "days": days, "top": seg_high, "bottom": seg_low,
                        "amplitude": round(amplitude, 2),
                    })
                    return result
        return result

    # ============================================================
    # 步骤5：确定主买点类型和等级
    # ============================================================

    def _determine_buy_point(self, result: BuyPointResult, checks: Dict):
        """根据四个买点检测结果，确定主买点类型和等级"""
        # 按优先级和匹配度排序
        candidates = []
        type_map = {
            "A_main_launch": (GRADE_A, BUY_TYPE_MAIN_LAUNCH),
            "B_limit_pullback": (GRADE_B, BUY_TYPE_LIMIT_PULLBACK),
            "C_five_buy": (GRADE_C, BUY_TYPE_FIVE_BUY),
            "D_box_breakout": (GRADE_D, BUY_TYPE_BOX_BREAKOUT),
        }

        for key, (grade, btype) in type_map.items():
            check = checks.get(key, {})
            if check.get("matched", False):
                candidates.append((grade, btype, check.get("score", 0), key))

        if candidates:
            # 取评分最高的作为主买点
            candidates.sort(key=lambda x: x[2], reverse=True)
            grade, btype, score, key = candidates[0]
            result.grade = grade
            result.buy_type = btype
        else:
            # 没有匹配的买点，取最接近的类型
            best_key = max(checks.keys(), key=lambda k: checks[k].get("score", 0))
            best_score = checks[best_key].get("score", 0)
            if best_score >= 40:
                grade, btype = type_map[best_key]
                result.grade = grade
                result.buy_type = btype + "(形成中)"
            else:
                result.grade = GRADE_NONE
                result.buy_type = BUY_TYPE_NONE

    # ============================================================
    # 步骤6：多因子评分（趋势30 + 资金30 + 形态20 + 情绪20）
    # ============================================================

    def _calc_multi_factor_score(self, result, bars, closes, highs, lows, volumes,
                                 indicators, checks):
        """计算多因子评分，每项可追溯来源"""
        breakdown = ScoreBreakdown()

        # ---- 趋势因子 30分 ----
        trend_score, trend_detail = self._calc_trend_score(closes, indicators)
        breakdown.trend = trend_score
        breakdown.trend_detail = trend_detail

        # ---- 资金因子 30分 ----
        capital_score, capital_detail = self._calc_capital_score(bars, closes, volumes, indicators)
        breakdown.capital = capital_score
        breakdown.capital_detail = capital_detail

        # ---- 形态因子 20分 ----
        pattern_score, pattern_detail = self._calc_pattern_score(result, checks)
        breakdown.pattern = pattern_score
        breakdown.pattern_detail = pattern_detail

        # ---- 情绪因子 20分 ----
        sentiment_score, sentiment_detail = self._calc_sentiment_score(result, bars, closes)
        breakdown.sentiment = sentiment_score
        breakdown.sentiment_detail = sentiment_detail

        # 综合评分
        breakdown.total = round(
            breakdown.trend + breakdown.capital + breakdown.pattern + breakdown.sentiment, 1)
        breakdown.total = max(0.0, min(SCORE_TOTAL_MAX, breakdown.total))

        result.score_breakdown = breakdown
        result.score = breakdown.total

    def _calc_trend_score(self, closes, indicators) -> Tuple[float, Dict]:
        """
        趋势因子 30分：
          - 多头排列 MA5>MA10>MA20: +10
          - 股价站上20日线: +10
          - 60日趋势向上（MA60上行 或 近60日涨幅>0）: +10
        """
        detail = {"bullish_alignment": 0.0, "above_ma20": 0.0, "ma60_uptrend": 0.0}
        score = 0.0
        last_idx = len(closes) - 1
        ma5 = indicators["ma5"]
        ma10 = indicators["ma10"]
        ma20 = indicators["ma20"]
        ma60 = indicators["ma60"]

        # 1. 多头排列 +10
        if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx]) and
                not np.isnan(ma20[last_idx])):
            if ma5[last_idx] > ma10[last_idx] > ma20[last_idx]:
                score += 10.0
                detail["bullish_alignment"] = 10.0
            elif ma5[last_idx] > ma10[last_idx]:
                score += 5.0  # 部分多头
                detail["bullish_alignment"] = 5.0

        # 2. 站上20日线 +10
        if not np.isnan(ma20[last_idx]) and ma20[last_idx] > 0:
            if closes[last_idx] > ma20[last_idx]:
                score += 10.0
                detail["above_ma20"] = 10.0
            elif closes[last_idx] > ma20[last_idx] * 0.97:
                score += 5.0  # 接近20日线
                detail["above_ma20"] = 5.0

        # 3. 60日趋势向上 +10
        if not np.isnan(ma60[last_idx]) and last_idx >= 10 and not np.isnan(ma60[last_idx - 10]):
            if ma60[last_idx] > ma60[last_idx - 10]:
                score += 10.0
                detail["ma60_uptrend"] = 10.0
            elif ma60[last_idx] > ma60[last_idx - 5] if not np.isnan(ma60[last_idx - 5]) else False:
                score += 5.0
                detail["ma60_uptrend"] = 5.0
        elif last_idx >= 60 and closes[last_idx - 60] > 0:
            # 没有MA60时用60日涨幅判断
            rise_60d = (closes[last_idx] - closes[last_idx - 60]) / closes[last_idx - 60] * 100
            if rise_60d > 0:
                score += 10.0
                detail["ma60_uptrend"] = 10.0

        return min(score, SCORE_TREND_MAX), detail

    def _calc_capital_score(self, bars, closes, volumes, indicators) -> Tuple[float, Dict]:
        """
        资金因子 30分：
          - 量能持续流入（近3日阳线放量）: +10
          - 量比1.2-3（健康放量）: +10
          - 成交额增长（近5日均额 > 前5日）: +10
        """
        detail = {"sustained_inflow": 0.0, "healthy_volume_ratio": 0.0, "amount_growth": 0.0}
        score = 0.0
        last_idx = len(bars) - 1
        vol_ratio = indicators["vol_ratio"]

        # 1. 量能持续流入 +10（近3日阳线多于阴线且放量）
        if last_idx >= 3:
            recent = bars[-3:]
            up_days = sum(1 for b in recent if b.pct_chg > 0)
            vol_increasing = volumes[last_idx] > volumes[last_idx - 1] > volumes[last_idx - 2]
            if up_days >= 2 and vol_increasing:
                score += 10.0
                detail["sustained_inflow"] = 10.0
            elif up_days >= 2:
                score += 5.0
                detail["sustained_inflow"] = 5.0

        # 2. 量比1.2-3（健康放量）+10
        if 1.2 <= vol_ratio <= 3.0:
            score += 10.0
            detail["healthy_volume_ratio"] = 10.0
        elif vol_ratio > 3.0:
            score += 5.0  # 爆量，风险较高
            detail["healthy_volume_ratio"] = 5.0
        elif vol_ratio >= 0.9:
            score += 3.0  # 量能平稳
            detail["healthy_volume_ratio"] = 3.0

        # 3. 成交额增长 +10
        if last_idx >= 10:
            # 用成交量代替成交额（本地数据可能没有amount）
            recent_5d_vol = float(np.mean(volumes[-5:]))
            prev_5d_vol = float(np.mean(volumes[-10:-5]))
            if prev_5d_vol > 0:
                growth = (recent_5d_vol - prev_5d_vol) / prev_5d_vol * 100
                if growth > 20:
                    score += 10.0
                    detail["amount_growth"] = 10.0
                elif growth > 0:
                    score += 5.0
                    detail["amount_growth"] = 5.0
                detail["volume_growth_pct"] = round(growth, 2)

        return min(score, SCORE_CAPITAL_MAX), detail

    def _calc_pattern_score(self, result: BuyPointResult, checks: Dict) -> Tuple[float, Dict]:
        """
        形态因子 20分：
          - 接入模式库评分（涨停回调/箱体突破/量价突破的最高分）: +10
          - 买点类型匹配度（当前检测到的买点类型评分）: +10
        """
        detail = {"model_library_score": 0.0, "buy_point_match": 0.0}
        score = 0.0

        # 1. 模式库评分（取三个模型的最高分，归一化到0-10）
        model_scores = []
        for key in ["limit_up_pullback", "box_breakout", "volume_breakout"]:
            mr = result.model_results.get(key, {})
            if "score" in mr and isinstance(mr["score"], (int, float)):
                model_scores.append(mr["score"])
        if model_scores:
            best_model_score = max(model_scores)
            normalized = best_model_score / 100.0 * 10.0
            score += normalized
            detail["model_library_score"] = round(normalized, 1)
            detail["best_model"] = max(
                result.model_results.items(),
                key=lambda x: x[1].get("score", 0) if isinstance(x[1], dict) else 0
            )[0]

        # 2. 买点类型匹配度（取四个买点检测中最高分，归一化到0-10）
        check_scores = [checks[k].get("score", 0) for k in checks]
        if check_scores:
            best_check = max(check_scores)
            normalized = best_check / 100.0 * 10.0
            score += normalized
            detail["buy_point_match"] = round(normalized, 1)

        # 3. 缠论结构加分（如果有缠论买点信号）
        cl = result.chanlun_result
        if cl and not cl.get("error"):
            buy_signals = [s for s in cl.get("signals", []) if "买" in s]
            if buy_signals:
                extra = min(2.0, len(buy_signals) * 1.0)
                score += extra * 0.5  # 额外加分但不超过总分
                detail["chanlun_buy_signals"] = buy_signals

        return min(score, SCORE_PATTERN_MAX), detail

    def _calc_sentiment_score(self, result: BuyPointResult, bars, closes) -> Tuple[float, Dict]:
        """
        情绪因子 20分：
          - 涨停历史（近60日涨停次数）: +5
          - 个股热度（近期涨幅/波动率）: +5
          - 市场环境（市场环境评分）: +5
          - 板块强度（无法获取时用市场环境替代）: +5
        """
        detail = {"limit_up_history": 0.0, "stock_heat": 0.0,
                  "market_environment": 0.0, "sector_strength": 0.0}
        score = 0.0
        last_idx = len(bars) - 1

        # 1. 涨停历史 +5（近60日涨停次数）
        lookback = min(60, last_idx + 1)
        limit_count = sum(1 for i in range(last_idx - lookback + 1, last_idx + 1)
                          if bars[i].pct_chg >= LIMIT_UP_THRESHOLD)
        if limit_count >= 5:
            score += 5.0
            detail["limit_up_history"] = 5.0
        elif limit_count >= 3:
            score += 3.5
            detail["limit_up_history"] = 3.5
        elif limit_count >= 1:
            score += 2.0
            detail["limit_up_history"] = 2.0
        detail["limit_up_count_60d"] = limit_count

        # 2. 个股热度 +5（近20日涨幅和波动率）
        if last_idx >= 20 and closes[last_idx - 20] > 0:
            rise_20d = (closes[last_idx] - closes[last_idx - 20]) / closes[last_idx - 20] * 100
            # 适度涨幅（5-30%）热度最高
            if 5 <= rise_20d <= 30:
                score += 5.0
                detail["stock_heat"] = 5.0
            elif 0 < rise_20d < 5 or 30 < rise_20d <= 50:
                score += 3.0
                detail["stock_heat"] = 3.0
            elif rise_20d > 50:
                score += 1.0  # 过热
                detail["stock_heat"] = 1.0
            detail["rise_20d_pct"] = round(rise_20d, 2)

        # 3. 市场环境 +5
        me = result.market_env
        if me and not me.get("error"):
            env_score = me.get("score", 50)
            if env_score >= 70:
                score += 5.0
                detail["market_environment"] = 5.0
            elif env_score >= 50:
                score += 3.5
                detail["market_environment"] = 3.5
            elif env_score >= 30:
                score += 2.0
                detail["market_environment"] = 2.0
            detail["env_score"] = env_score
            detail["env_type"] = me.get("env_type", "")
        else:
            # 无市场环境数据时给中性分
            score += 2.5
            detail["market_environment"] = 2.5
            detail["note"] = "无市场环境数据，使用中性分"

        # 4. 板块强度 +5（无法直接获取板块数据，用市场环境+个股表现综合估算）
        # 这里用市场环境系数和个股相对强度估算
        if me and not me.get("error"):
            factor = me.get("factor", 1.0)
            if factor >= 1.2:
                score += 5.0
                detail["sector_strength"] = 5.0
            elif factor >= 1.0:
                score += 3.5
                detail["sector_strength"] = 3.5
            else:
                score += 2.0
                detail["sector_strength"] = 2.0
        else:
            score += 2.5
            detail["sector_strength"] = 2.5

        return min(score, SCORE_SENTIMENT_MAX), detail

    # ============================================================
    # 步骤7：买入位置计算
    # ============================================================

    def _calc_price_levels(self, result, closes, highs, lows, indicators, checks):
        """
        计算买入位置：
          - 最佳买入区间 = 当前价 ± 0.5*ATR
          - 突破价 = 前高压力位 × 1.005
          - 止损 = min(支撑位 - 1.5*ATR, MA20×0.97)
          - 目标价 = 突破价 + (突破价-止损) × 盈亏比(2-3)
        """
        pl = PriceLevels()
        last_idx = len(closes) - 1
        current = float(closes[-1])
        atr = indicators["atr"]
        ma20 = indicators["ma20"]

        pl.current_price = current
        pl.atr = atr

        # 1. 支撑位计算（取多个支撑的最小值）
        support_candidates = []
        # MA20支撑
        if not np.isnan(ma20[last_idx]) and ma20[last_idx] > 0:
            support_candidates.append(float(ma20[last_idx]))
        # 近20日低点
        if last_idx >= 20:
            support_candidates.append(float(np.min(lows[-20:])))
        # 模型库支撑位
        for key in ["limit_up_pullback", "box_breakout", "volume_breakout"]:
            mr = result.model_results.get(key, {})
            sup = mr.get("support", 0)
            if sup and sup > 0:
                support_candidates.append(sup)
        # 缠论支撑
        cl = result.chanlun_result
        if cl and not cl.get("error"):
            cl_sup = cl.get("price_levels", {}).get("support", 0)
            if cl_sup and cl_sup > 0:
                support_candidates.append(cl_sup)
        # 横盘箱体底部
        d_check = checks.get("D_box_breakout", {})
        if d_check.get("details", {}).get("box_bottom", 0) > 0:
            support_candidates.append(d_check["details"]["box_bottom"])

        support = min(support_candidates) if support_candidates else current * 0.95
        pl.support = round(support, 2)

        # 2. 前高压力位
        resistance_candidates = []
        if last_idx >= 20:
            resistance_candidates.append(float(np.max(highs[-20:-1])))
        # 模型库压力位
        for key in ["limit_up_pullback", "box_breakout", "volume_breakout"]:
            mr = result.model_results.get(key, {})
            pres = mr.get("pressure", 0)
            if pres and pres > 0:
                resistance_candidates.append(pres)
        # 横盘箱体顶部
        if d_check.get("details", {}).get("box_top", 0) > 0:
            resistance_candidates.append(d_check["details"]["box_top"])

        resistance = min(resistance_candidates) if resistance_candidates else current * 1.1
        pl.resistance = round(resistance, 2)

        # 3. 最佳买入区间 = 当前价 ± 0.5*ATR
        atr_mult = self.params["best_buy_atr_mult"]
        if atr > 0:
            pl.best_buy_low = round(current - atr * atr_mult, 2)
            pl.best_buy_high = round(current + atr * atr_mult * 0.5, 2)  # 上限偏紧
        else:
            pl.best_buy_low = round(current * 0.98, 2)
            pl.best_buy_high = round(current * 1.01, 2)

        # 4. 突破价 = 前高压力位 × 1.005
        pl.breakout_price = round(resistance * 1.005, 2)

        # 5. 止损 = 支撑位 - 1.5*ATR（但不低于当前价的92%）
        sl_atr = support - atr * self.params["stop_loss_atr_mult"] if atr > 0 else support * 0.97
        sl_ma20 = ma20[last_idx] * 0.97 if not np.isnan(ma20[last_idx]) and ma20[last_idx] > 0 else current * 0.92
        stop_loss = min(sl_atr, sl_ma20)
        stop_loss = max(stop_loss, current * 0.85)  # 止损不超过15%
        pl.stop_loss = round(stop_loss, 2)

        # 6. 目标价 = 突破价 + (突破价-止损) × 盈亏比
        risk_per_share = pl.breakout_price - pl.stop_loss
        if risk_per_share > 0:
            pl.target_low = round(pl.breakout_price + risk_per_share * self.params["target_rr_min"], 2)
            pl.target_high = round(pl.breakout_price + risk_per_share * self.params["target_rr_max"], 2)
            # 盈亏比
            avg_target = (pl.target_low + pl.target_high) / 2
            pl.risk_reward_ratio = round((avg_target - current) / (current - pl.stop_loss), 2) if current > pl.stop_loss else 0
        else:
            pl.target_low = round(current * 1.1, 2)
            pl.target_high = round(current * 1.2, 2)
            pl.risk_reward_ratio = 0

        result.price_levels = pl

        # 记录计算依据
        result.calculation_basis["price_calc"] = {
            "support_candidates": [round(s, 2) for s in support_candidates],
            "resistance_candidates": [round(r, 2) for r in resistance_candidates],
            "atr_used": round(atr, 2),
            "stop_loss_atr_mult": self.params["stop_loss_atr_mult"],
            "target_rr_range": [self.params["target_rr_min"], self.params["target_rr_max"]],
        }

    # ============================================================
    # 步骤8：风险等级
    # ============================================================

    def _calc_risk_level(self, result: BuyPointResult):
        """根据评分和止损空间计算风险等级"""
        score = result.score
        pl = result.price_levels
        current = pl.current_price
        stop_loss = pl.stop_loss

        # 止损空间
        stop_space = (current - stop_loss) / current * 100 if current > 0 else 100

        # 风险等级判断
        if score >= 70 and stop_space <= 8:
            result.risk_level = "低"
        elif score >= 50 and stop_space <= 12:
            result.risk_level = "中"
        else:
            result.risk_level = "高"

        # 额外风险因素
        cl = result.chanlun_result
        if cl and not cl.get("error"):
            if cl.get("level") == "回避" or "卖" in "".join(cl.get("signals", [])):
                if result.risk_level == "低":
                    result.risk_level = "中"

    # ============================================================
    # 步骤9：星级
    # ============================================================

    def _calc_stars(self, result: BuyPointResult):
        """根据综合评分计算星级（1-5星）"""
        score = result.score
        for threshold, stars in STARS_THRESHOLDS:
            if score >= threshold:
                result.stars = stars
                return
        result.stars = 1

    # ============================================================
    # 步骤10：买点解释系统
    # ============================================================

    def _generate_explanation(self, result: BuyPointResult, checks: Dict, indicators: Dict):
        """生成买点解释：为什么买 / 风险 / 满足条件 / 未满足条件"""
        grade = result.grade
        btype = result.buy_type
        score = result.score
        pl = result.price_levels
        bd = result.score_breakdown

        # ---- 为什么买 ----
        reasons = []
        if grade != GRADE_NONE:
            reasons.append(f"检测到【{btype}】买点（等级{grade}），综合评分{score:.1f}分")
        else:
            reasons.append(f"当前未检测到明确买点，综合评分{score:.1f}分")

        # 趋势面
        if bd.trend >= 20:
            reasons.append(f"趋势面较强（{bd.trend:.0f}/30分）：{self._trend_reason(bd.trend_detail)}")
        # 资金面
        if bd.capital >= 20:
            reasons.append(f"资金面活跃（{bd.capital:.0f}/30分）：{self._capital_reason(bd.capital_detail)}")
        # 形态面
        if bd.pattern >= 12:
            reasons.append(f"形态面配合（{bd.pattern:.0f}/20分）：{self._pattern_reason(bd.pattern_detail)}")

        # 价格优势
        if pl.risk_reward_ratio >= 2.0:
            reasons.append(f"盈亏比{pl.risk_reward_ratio:.1f}:1，止损{pl.stop_loss:.2f}，目标{pl.target_low:.2f}-{pl.target_high:.2f}")

        # 缠论确认
        cl = result.chanlun_result
        if cl and not cl.get("error"):
            buy_sigs = [s for s in cl.get("signals", []) if "买" in s]
            if buy_sigs:
                reasons.append(f"缠论确认：{', '.join(buy_sigs)}")

        result.reasons = reasons

        # ---- 风险 ----
        risks = []
        if result.risk_level == "高":
            risks.append("综合风险等级较高，建议观望")
        if bd.trend < 15:
            risks.append("趋势面较弱，均线未形成多头排列")
        if bd.capital < 15:
            risks.append("资金面不足，量能未有效放大")
        if pl.stop_loss > 0 and pl.current_price > 0:
            stop_pct = (pl.current_price - pl.stop_loss) / pl.current_price * 100
            if stop_pct > 10:
                risks.append(f"止损空间较大（{stop_pct:.1f}%），需控制仓位")
        # 缠论风险
        if cl and not cl.get("error"):
            sell_sigs = [s for s in cl.get("signals", []) if "卖" in s]
            if sell_sigs:
                risks.append(f"缠论提示：{', '.join(sell_sigs)}")
            if cl.get("beichi") == "top_beichi":
                risks.append("存在顶背驰风险，上涨动能可能衰竭")
        # 市场环境风险
        me = result.market_env
        if me and not me.get("error"):
            if me.get("score", 50) < 30:
                risks.append("市场环境处于风险区，禁止追涨")
            elif me.get("score", 50) < 50:
                risks.append("市场环境偏弱，谨慎操作")

        if not risks:
            risks.append("暂无明显风险信号")
        result.risks = risks

        # ---- 满足条件 / 未满足条件 ----
        met = []
        not_met = []

        # 根据主买点类型列出条件
        type_conditions = {
            GRADE_A: [
                ("MA5上穿MA10", "A_main_launch", "ma5_cross_ma10"),
                ("成交量放大(≥1.5倍)", "A_main_launch", "volume_expand"),
                ("MACD金叉", "A_main_launch", "macd_golden"),
                ("KDJ低位金叉(K<50)", "A_main_launch", "kdj_golden_below_50"),
                ("突破压力位", "A_main_launch", "breakout_pressure"),
            ],
            GRADE_B: [
                ("近期涨停/大阳启动", "B_limit_pullback", "has_recent_launch"),
                ("回撤5%-15%", "B_limit_pullback", "drawdown_5_15pct"),
                ("缩量调整", "B_limit_pullback", "volume_shrinking"),
                ("不破20日线", "B_limit_pullback", "above_ma20"),
                ("再次放量", "B_limit_pullback", "volume_recovering"),
            ],
            GRADE_C: [
                ("底背离/下跌结束", "C_five_buy", "bottom_or_decline_end"),
                ("MACD改善", "C_five_buy", "macd_improving"),
                ("KDJ低位金叉(K<30)", "C_five_buy", "kdj_low_golden"),
                ("量能恢复", "C_five_buy", "volume_recover"),
                ("五买MA5承接", "C_five_buy", "five_buy_ma5_support"),
            ],
            GRADE_D: [
                ("横盘20-60天", "D_box_breakout", "consolidation_20_60d"),
                ("放量突破", "D_box_breakout", "volume_breakout"),
                ("突破箱体上沿", "D_box_breakout", "price_breakout_box"),
                ("均线粘合后发散", "D_box_breakout", "ma_divergence"),
            ],
        }

        conditions = type_conditions.get(grade, [])
        for desc, check_key, cond_key in conditions:
            check = checks.get(check_key, {})
            cond_val = check.get("conditions", {}).get(cond_key, False)
            if cond_val:
                met.append(desc)
            else:
                not_met.append(desc)

        # 如果没有匹配任何类型，列出各类型的满足情况
        if not conditions:
            for check_key, check in checks.items():
                type_name = {
                    "A_main_launch": "主升启动",
                    "B_limit_pullback": "涨停回调",
                    "C_five_buy": "五买确认",
                    "D_box_breakout": "横盘突破",
                }.get(check_key, check_key)
                cmet = check.get("details", {}).get("conditions_met", 0)
                not_met.append(f"{type_name}：满足{cmet}/5个条件")

        result.conditions_met = met
        result.conditions_not_met = not_met

    def _trend_reason(self, detail: Dict) -> str:
        parts = []
        if detail.get("bullish_alignment", 0) >= 10:
            parts.append("MA5>MA10>MA20多头排列")
        elif detail.get("bullish_alignment", 0) > 0:
            parts.append("MA5>MA10短期多头")
        if detail.get("above_ma20", 0) >= 10:
            parts.append("股价站上20日线")
        if detail.get("ma60_uptrend", 0) >= 10:
            parts.append("60日趋势向上")
        return "，".join(parts) if parts else "趋势一般"

    def _capital_reason(self, detail: Dict) -> str:
        parts = []
        if detail.get("sustained_inflow", 0) >= 10:
            parts.append("近3日持续放量上涨")
        if detail.get("healthy_volume_ratio", 0) >= 10:
            parts.append("量比健康(1.2-3)")
        if detail.get("amount_growth", 0) >= 10:
            parts.append("成交额显著增长")
        return "，".join(parts) if parts else "资金面一般"

    def _pattern_reason(self, detail: Dict) -> str:
        parts = []
        if detail.get("model_library_score", 0) > 0:
            parts.append(f"模式库匹配({detail.get('best_model', '')})")
        if detail.get("buy_point_match", 0) > 0:
            parts.append("买点形态匹配")
        if detail.get("chanlun_buy_signals"):
            parts.append(f"缠论{','.join(detail['chanlun_buy_signals'])}")
        return "，".join(parts) if parts else "形态一般"

    # ============================================================
    # V7.2 增强：完整操作理由链（6个维度）
    # ============================================================

    def _generate_action_chain(self, result, bars, closes, highs, lows, volumes,
                               indicators, checks):
        """生成完整操作理由链：6个维度 + 自然语言摘要"""
        # 1. 买点逻辑
        result.buy_point_logic = self._gen_buy_point_logic(result, checks)
        # 2. 买点位置
        result.position_context = self._gen_position_context(result, bars, closes, highs, lows, indicators)
        # 3. 为什么这个位置买
        result.why_this_position = self._gen_why_this_position(result, bars, closes, highs, lows, volumes, indicators, checks)
        # 4. 为什么这个价格买
        result.why_this_price = self._gen_why_this_price(result, indicators)
        # 5. 为什么选择这个股票
        result.why_this_stock = self._gen_why_this_stock(result, bars, closes, volumes)
        # 6. 操作理由
        result.action_advice = self._gen_action_advice(result, checks)
        # 自然语言摘要
        result.action_summary = self._gen_action_summary(result)

    # ---------- 维度1：买点逻辑 ----------

    def _gen_buy_point_logic(self, result: BuyPointResult, checks: Dict) -> Dict:
        """
        买点逻辑详解：
        - 类型
        - 核心触发条件（必须满足的）
        - 辅助确认条件（加分项）
        - 失效条件
        """
        grade = result.grade
        btype = result.buy_type

        # 各类型的核心触发条件和辅助确认条件定义
        logic_defs = {
            GRADE_A: {
                "core_conditions": [
                    ("MA5上穿MA10", "A_main_launch", "ma5_cross_ma10", "短期均线金叉，趋势启动信号"),
                    ("成交量≥1.5倍", "A_main_launch", "volume_expand", "放量确认资金进场"),
                    ("MACD金叉", "A_main_launch", "macd_golden", "动量转强确认"),
                ],
                "aux_conditions": [
                    ("KDJ低位金叉(K<50)", "A_main_launch", "kdj_golden_below_50", "低位金叉避免追高"),
                    ("突破压力位", "A_main_launch", "breakout_pressure", "突破前高打开空间"),
                ],
                "invalid_conditions": [
                    "MA5重新跌破MA10且放量",
                    "MACD死叉且DIF下穿0轴",
                    "跌破突破位（前高压力位）且3天内无法收回",
                    "成交量骤降至均量50%以下",
                ],
            },
            GRADE_B: {
                "core_conditions": [
                    ("近期涨停/大阳启动", "B_limit_pullback", "has_recent_launch", "有主力启动痕迹"),
                    ("回撤5%-15%", "B_limit_pullback", "drawdown_5_15pct", "健康回调幅度"),
                    ("不破20日线", "B_limit_pullback", "above_ma20", "趋势支撑有效"),
                ],
                "aux_conditions": [
                    ("缩量调整", "B_limit_pullback", "volume_shrinking", "抛压减轻"),
                    ("再次放量", "B_limit_pullback", "volume_recovering", "二次启动信号"),
                ],
                "invalid_conditions": [
                    "跌破20日线且3天内无法收回",
                    "回撤幅度超过20%（趋势可能反转）",
                    "反弹时量能持续萎缩（无资金关注）",
                    "MACD死叉且DIF持续下行",
                ],
            },
            GRADE_C: {
                "core_conditions": [
                    ("底背离/下跌结束", "C_five_buy", "bottom_or_decline_end", "下跌动能衰竭"),
                    ("MACD改善", "C_five_buy", "macd_improving", "动量底部回升"),
                    ("五买MA5承接", "C_five_buy", "five_buy_ma5_support", "倍量启动后回踩承接"),
                ],
                "aux_conditions": [
                    ("KDJ低位金叉(K<30)", "C_five_buy", "kdj_low_golden", "超卖区金叉"),
                    ("量能恢复", "C_five_buy", "volume_recover", "资金重新关注"),
                ],
                "invalid_conditions": [
                    "跌破近期低点（底背离失效）",
                    "MACD绿柱重新放大",
                    "KDJ金叉后迅速死叉（假金叉）",
                    "量能恢复后再次萎缩至均量60%以下",
                ],
            },
            GRADE_D: {
                "core_conditions": [
                    ("横盘20-60天", "D_box_breakout", "consolidation_20_60d", "充分整理蓄势"),
                    ("放量突破", "D_box_breakout", "volume_breakout", "资金推动突破"),
                    ("突破箱体上沿", "D_box_breakout", "price_breakout_box", "价格确认突破"),
                ],
                "aux_conditions": [
                    ("均线粘合后发散", "D_box_breakout", "ma_divergence", "趋势从整理转启动"),
                ],
                "invalid_conditions": [
                    "突破后3天内跌回箱体内（假突破）",
                    "突破日量能不足（量比<1.2）",
                    "箱体上沿附近出现长上影线（抛压重）",
                    "跌破箱体下沿",
                ],
            },
        }

        logic = logic_defs.get(grade, {
            "core_conditions": [],
            "aux_conditions": [],
            "invalid_conditions": ["当前无明确买点，需等待信号形成"],
        })

        # 填充每个条件的当前满足状态
        def fill_conditions(cond_list):
            filled = []
            for desc, check_key, cond_key, explanation in cond_list:
                check = checks.get(check_key, {})
                met = check.get("conditions", {}).get(cond_key, False)
                # 获取该条件的实际值
                detail = check.get("details", {})
                actual_value = None
                if cond_key == "volume_expand":
                    actual_value = f"量比{detail.get('volume_ratio', 'N/A')}"
                elif cond_key == "drawdown_5_15pct":
                    actual_value = f"回撤{detail.get('drawdown_pct', 'N/A')}%"
                elif cond_key == "kdj_golden_below_50" or cond_key == "kdj_low_golden":
                    actual_value = f"K={detail.get('kdj_k', 'N/A')}"
                elif cond_key == "consolidation_20_60d":
                    actual_value = f"横盘{detail.get('box_days', 0)}天,振幅{detail.get('box_amplitude', 0)}%"
                elif cond_key == "volume_breakout":
                    actual_value = f"突破量比{detail.get('breakout_volume_ratio', 'N/A')}"
                filled.append({
                    "condition": desc,
                    "explanation": explanation,
                    "met": bool(met),
                    "actual_value": actual_value,
                })
            return filled

        return {
            "buy_type": btype,
            "grade": grade,
            "core_conditions": fill_conditions(logic["core_conditions"]),
            "aux_conditions": fill_conditions(logic["aux_conditions"]),
            "invalid_conditions": logic["invalid_conditions"],
            "core_met_count": sum(1 for c in fill_conditions(logic["core_conditions"]) if c["met"]),
            "core_total": len(logic["core_conditions"]),
        }

    # ---------- 维度2：买点位置 ----------

    def _gen_position_context(self, result, bars, closes, highs, lows, indicators) -> Dict:
        """
        买点位置描述：
        - 趋势阶段：启动期/主升期/调整期/下跌期
        - 价格位置：距20日线%、距60日高点%、距近期低点%
        - 形态位置：涨停后第N天/横盘第N天/下跌后第N天
        - 支撑压力位
        """
        last_idx = len(closes) - 1
        current = float(closes[-1])
        ma5 = indicators["ma5"]
        ma10 = indicators["ma10"]
        ma20 = indicators["ma20"]
        ma60 = indicators["ma60"]

        # 1. 趋势阶段判断
        trend_stage = "未知"
        if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx]) and
                not np.isnan(ma20[last_idx]) and not np.isnan(ma60[last_idx])):
            if ma5[last_idx] > ma10[last_idx] > ma20[last_idx] > ma60[last_idx]:
                # 完全多头排列
                if last_idx >= 10 and ma5[last_idx - 10] <= ma10[last_idx - 10]:
                    trend_stage = "启动期（刚形成多头排列）"
                else:
                    trend_stage = "主升期（多头排列延续）"
            elif ma5[last_idx] > ma10[last_idx] > ma20[last_idx]:
                trend_stage = "启动期（短期多头，中期待确认）"
            elif current > ma20[last_idx] and ma5[last_idx] < ma10[last_idx]:
                trend_stage = "调整期（上升趋势中回调）"
            elif current < ma20[last_idx] and ma20[last_idx] > ma60[last_idx]:
                trend_stage = "调整期（跌破20日线但中期趋势未坏）"
            else:
                trend_stage = "下跌期（均线空头排列）"

        # 2. 价格位置
        price_position = {}
        if not np.isnan(ma20[last_idx]) and ma20[last_idx] > 0:
            price_position["距MA20"] = round((current - ma20[last_idx]) / ma20[last_idx] * 100, 2)
        if not np.isnan(ma60[last_idx]) and ma60[last_idx] > 0:
            price_position["距MA60"] = round((current - ma60[last_idx]) / ma60[last_idx] * 100, 2)
        if last_idx >= 60:
            high_60d = float(np.max(highs[-60:]))
            low_60d = float(np.min(lows[-60:]))
            price_position["距60日高点"] = round((current - high_60d) / high_60d * 100, 2)
            price_position["距60日低点"] = round((current - low_60d) / low_60d * 100, 2)
            # 60日位置百分位（0=最低，100=最高）
            if high_60d > low_60d:
                price_position["60日位置百分位"] = round(
                    (current - low_60d) / (high_60d - low_60d) * 100, 1)

        # 3. 形态位置
        pattern_position = self._detect_pattern_position(bars, closes, highs, lows, last_idx)

        # 4. 支撑压力位
        pl = result.price_levels
        support_pressure = {
            "最近支撑位": pl.support,
            "最近压力位": pl.resistance,
            "MA20支撑": round(float(ma20[last_idx]), 2) if not np.isnan(ma20[last_idx]) else None,
            "MA60压力/支撑": round(float(ma60[last_idx]), 2) if not np.isnan(ma60[last_idx]) else None,
        }

        return {
            "trend_stage": trend_stage,
            "price_position": price_position,
            "pattern_position": pattern_position,
            "support_pressure": support_pressure,
        }

    def _detect_pattern_position(self, bars, closes, highs, lows, last_idx) -> Dict:
        """检测形态位置：涨停后第N天/横盘第N天/下跌后第N天"""
        # 找最近涨停/大阳
        limit_up_idx = None
        for i in range(last_idx, max(0, last_idx - 30), -1):
            if bars[i].pct_chg >= LIMIT_UP_THRESHOLD or bars[i].pct_chg >= BIG_YANG_THRESHOLD:
                limit_up_idx = i
                break

        # 找近期高点
        recent_high_idx = last_idx
        if last_idx >= 20:
            recent_high_idx = int(np.argmax(highs[-20:])) + last_idx - 19

        # 横盘检测
        box_days = 0
        if last_idx >= 20:
            for d in range(20, min(60, last_idx)):
                seg = highs[last_idx - d:last_idx]
                seg_low = lows[last_idx - d:last_idx]
                if max(seg) > 0 and min(seg_low) > 0:
                    amp = (max(seg) - min(seg_low)) / min(seg_low) * 100
                    if amp <= 25:
                        box_days = d
                    else:
                        break

        result = {}
        if limit_up_idx is not None:
            days_after = last_idx - limit_up_idx
            result["涨停后天数"] = days_after
            result["涨停日涨幅"] = round(bars[limit_up_idx].pct_chg, 2)
        if recent_high_idx < last_idx:
            result["距近期高点天数"] = last_idx - recent_high_idx
        if box_days >= 20:
            result["横盘天数"] = box_days

        # 下跌后反弹检测
        if last_idx >= 10:
            recent_low_idx = int(np.argmin(lows[-10:])) + last_idx - 9
            if recent_low_idx < last_idx and closes[last_idx] > lows[recent_low_idx]:
                rebound_pct = (closes[last_idx] - lows[recent_low_idx]) / lows[recent_low_idx] * 100
                result["下跌后反弹天数"] = last_idx - recent_low_idx
                result["反弹幅度"] = round(rebound_pct, 2)

        if not result:
            result["形态"] = "无明显形态特征"
        return result

    # ---------- 维度3：为什么这个位置买 ----------

    def _gen_why_this_position(self, result, bars, closes, highs, lows, volumes,
                               indicators, checks) -> List[Dict]:
        """
        为什么这个位置买：3-5条理由，每条含指标名+当前值+阈值+判断
        按重要性排序
        """
        reasons = []
        last_idx = len(closes) - 1
        current = float(closes[-1])
        ma5 = indicators["ma5"]
        ma10 = indicators["ma10"]
        ma20 = indicators["ma20"]
        ma60 = indicators["ma60"]
        dif = indicators["dif"]
        dea = indicators["dea"]
        k_arr = indicators["k"]
        d_arr = indicators["d"]
        vol_ratio = indicators["vol_ratio"]

        # 理由1：均线趋势（最重要）
        if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx]) and
                not np.isnan(ma20[last_idx])):
            if ma5[last_idx] > ma10[last_idx] > ma20[last_idx]:
                reasons.append({
                    "indicator": "均线多头排列",
                    "current_value": f"MA5={ma5[last_idx]:.2f} > MA10={ma10[last_idx]:.2f} > MA20={ma20[last_idx]:.2f}",
                    "threshold": "MA5>MA10>MA20",
                    "passed": True,
                    "score_contribution": "+10分（趋势因子）",
                    "explanation": "短期、中期均线多头排列，趋势向上确立",
                })
            elif ma5[last_idx] > ma10[last_idx]:
                reasons.append({
                    "indicator": "短期均线金叉",
                    "current_value": f"MA5={ma5[last_idx]:.2f} > MA10={ma10[last_idx]:.2f}",
                    "threshold": "MA5>MA10",
                    "passed": True,
                    "score_contribution": "+5分（趋势因子）",
                    "explanation": "5日线上穿10日线，短期趋势转强",
                })
            elif current > ma20[last_idx]:
                reasons.append({
                    "indicator": "站上20日线",
                    "current_value": f"现价{current:.2f} > MA20={ma20[last_idx]:.2f}",
                    "threshold": "收盘价>MA20",
                    "passed": True,
                    "score_contribution": "+10分（趋势因子）",
                    "explanation": "股价站上20日生命线，中期趋势支撑有效",
                })

        # 理由2：MACD动量
        if not np.isnan(dif[last_idx]) and not np.isnan(dea[last_idx]):
            if TechnicalIndicators.is_macd_golden(dif, dea, last_idx):
                reasons.append({
                    "indicator": "MACD金叉",
                    "current_value": f"DIF={dif[last_idx]:.4f} 上穿 DEA={dea[last_idx]:.4f}",
                    "threshold": "DIF上穿DEA",
                    "passed": True,
                    "score_contribution": "A型买点核心条件",
                    "explanation": "MACD金叉确认动量转强，上涨动能增强",
                })
            elif dif[last_idx] > dea[last_idx] and dif[last_idx] > 0:
                reasons.append({
                    "indicator": "MACD多头区域",
                    "current_value": f"DIF={dif[last_idx]:.4f} > DEA={dea[last_idx]:.4f} > 0",
                    "threshold": "DIF>DEA>0",
                    "passed": True,
                    "score_contribution": "动量确认",
                    "explanation": "MACD在零轴上方运行，多头趋势中",
                })
            elif dif[last_idx] > dif[last_idx - 2] if last_idx >= 2 else False:
                reasons.append({
                    "indicator": "MACD改善",
                    "current_value": f"DIF={dif[last_idx]:.4f} > 2日前{dif[last_idx-2]:.4f}",
                    "threshold": "DIF拐头向上",
                    "passed": True,
                    "score_contribution": "C型买点核心条件",
                    "explanation": "DIF拐头向上，下跌动量减弱",
                })

        # 理由3：KDJ位置
        if not np.isnan(k_arr[last_idx]) and not np.isnan(d_arr[last_idx]):
            if TechnicalIndicators.is_kdj_golden(k_arr, d_arr, last_idx):
                if k_arr[last_idx] < 30:
                    reasons.append({
                        "indicator": "KDJ低位金叉",
                        "current_value": f"K={k_arr[last_idx]:.2f} 上穿 D={d_arr[last_idx]:.2f}",
                        "threshold": "K<30且金叉",
                        "passed": True,
                        "score_contribution": "C型买点核心条件",
                        "explanation": "超卖区金叉，反弹概率高",
                    })
                elif k_arr[last_idx] < 50:
                    reasons.append({
                        "indicator": "KDJ中位金叉",
                        "current_value": f"K={k_arr[last_idx]:.2f} 上穿 D={d_arr[last_idx]:.2f}",
                        "threshold": "K<50且金叉",
                        "passed": True,
                        "score_contribution": "A型买点辅助条件",
                        "explanation": "中位金叉，趋势延续概率高",
                    })

        # 理由4：量能
        if vol_ratio >= 1.2:
            reasons.append({
                "indicator": "成交量放大",
                "current_value": f"近5日均量比={vol_ratio:.2f}",
                "threshold": "量比≥1.2",
                "passed": True,
                "score_contribution": "+10分（资金因子）",
                "explanation": "量能放大确认资金进场，非无量空涨",
            })
        elif vol_ratio >= 0.9:
            reasons.append({
                "indicator": "成交量平稳",
                "current_value": f"近5日均量比={vol_ratio:.2f}",
                "threshold": "量比≥0.9",
                "passed": True,
                "score_contribution": "+3分（资金因子）",
                "explanation": "量能平稳，无明显出货迹象",
            })

        # 理由5：缠论确认（如果有）
        cl = result.chanlun_result
        if cl and not cl.get("error"):
            buy_sigs = [s for s in cl.get("signals", []) if "买" in s]
            if buy_sigs:
                reasons.append({
                    "indicator": "缠论买点确认",
                    "current_value": f"信号: {', '.join(buy_sigs)}",
                    "threshold": "缠论买卖点信号",
                    "passed": True,
                    "score_contribution": "形态因子加分",
                    "explanation": f"缠论结构确认{buy_sigs[0]}，结构级买点",
                })
            if cl.get("beichi") == "bottom_beichi":
                reasons.append({
                    "indicator": "缠论底背驰",
                    "current_value": "价格创新低但MACD力度减弱",
                    "threshold": "底背驰",
                    "passed": True,
                    "score_contribution": "C型买点确认",
                    "explanation": "底背驰确认下跌动能衰竭，反弹在即",
                })

        # 限制最多5条，按重要性排序（已按顺序添加）
        return reasons[:5]

    # ---------- 维度4：为什么这个价格买 ----------

    def _gen_why_this_price(self, result: BuyPointResult, indicators: Dict) -> Dict:
        """
        为什么这个价格买：价格计算详解
        每个价格都有：公式 + 代入值 + 结果 + 依据
        """
        pl = result.price_levels
        current = pl.current_price
        atr = pl.atr
        support = pl.support
        resistance = pl.resistance
        calc_basis = result.calculation_basis.get("price_calc", {})

        # 最佳买入区间计算
        atr_mult = self.params["best_buy_atr_mult"]
        best_buy_calc = {
            "公式": f"下限 = 当前价 - {atr_mult}×ATR; 上限 = 当前价 + {atr_mult*0.5}×ATR",
            "代入值": f"下限 = {current:.2f} - {atr_mult}×{atr:.2f}; 上限 = {current:.2f} + {atr_mult*0.5}×{atr:.2f}",
            "结果": f"{pl.best_buy_low:.2f} - {pl.best_buy_high:.2f}",
            "依据": "基于ATR(14)波动率，在当前价附近给出低吸区间，上限偏紧避免追高",
            "ATR值": atr,
        }

        # 突破价计算
        breakout_calc = {
            "公式": "突破价 = 前高压力位 × 1.005",
            "代入值": f"突破价 = {resistance:.2f} × 1.005",
            "结果": f"{pl.breakout_price:.2f}",
            "依据": f"前高压力位取多个候选最小值: {calc_basis.get('resistance_candidates', [])}，加0.5%缓冲确认有效突破",
            "压力位候选": calc_basis.get("resistance_candidates", []),
        }

        # 止损价计算
        sl_atr_mult = self.params["stop_loss_atr_mult"]
        ma20_val = indicators["ma20"][-1] if len(indicators["ma20"]) > 0 else 0
        sl_atr = support - atr * sl_atr_mult if atr > 0 else support * 0.97
        sl_ma20 = ma20_val * 0.97 if not np.isnan(ma20_val) and ma20_val > 0 else current * 0.92
        stop_loss_calc = {
            "公式": "止损 = min(支撑位 - 1.5×ATR, MA20×0.97)，且不低于当前价×0.85",
            "代入值": (
                f"ATR止损 = {support:.2f} - 1.5×{atr:.2f} = {sl_atr:.2f}; "
                f"MA20止损 = {ma20_val:.2f}×0.97 = {sl_ma20:.2f}"
            ),
            "结果": f"{pl.stop_loss:.2f}",
            "依据": "取ATR止损和MA20止损中较紧者，确保止损空间可控；最大不超过15%",
            "支撑位候选": calc_basis.get("support_candidates", []),
            "ATR止损价": round(sl_atr, 2),
            "MA20止损价": round(sl_ma20, 2),
            "止损空间%": round((current - pl.stop_loss) / current * 100, 2) if current > 0 else 0,
        }

        # 目标价计算
        risk_per_share = pl.breakout_price - pl.stop_loss
        rr_min = self.params["target_rr_min"]
        rr_max = self.params["target_rr_max"]
        target_calc = {
            "公式": f"目标下限 = 突破价 + 风险×{rr_min}; 目标上限 = 突破价 + 风险×{rr_max}",
            "代入值": (
                f"风险/股 = {pl.breakout_price:.2f} - {pl.stop_loss:.2f} = {risk_per_share:.2f}; "
                f"下限 = {pl.breakout_price:.2f} + {risk_per_share:.2f}×{rr_min}; "
                f"上限 = {pl.breakout_price:.2f} + {risk_per_share:.2f}×{rr_max}"
            ),
            "结果": f"{pl.target_low:.2f} - {pl.target_high:.2f}",
            "依据": "基于2:1到3:1盈亏比计算目标位，确保盈利空间至少是风险的2倍",
            "盈亏比": pl.risk_reward_ratio,
        }

        return {
            "current_price": current,
            "best_buy_range": best_buy_calc,
            "breakout_price": breakout_calc,
            "stop_loss": stop_loss_calc,
            "target_price": target_calc,
            "summary": (
                f"当前价{current:.2f}，建议在{pl.best_buy_low:.2f}-{pl.best_buy_high:.2f}区间低吸，"
                f"突破{pl.breakout_price:.2f}加仓，止损{pl.stop_loss:.2f}（空间{stop_loss_calc['止损空间%']}%），"
                f"目标{pl.target_low:.2f}-{pl.target_high:.2f}，盈亏比{pl.risk_reward_ratio:.1f}:1"
            ),
        }

    # ---------- 维度5：为什么选择这个股票 ----------

    def _gen_why_this_stock(self, result: BuyPointResult, bars, closes, volumes) -> Dict:
        """
        为什么选择这个股票：
        - 评分亮点（四个维度中得分最高的1-2个）
        - 同类排名（在筛选股票中的百分位）
        - 行业地位
        - 资金关注度
        """
        bd = result.score_breakdown

        # 1. 评分亮点
        dimensions = [
            ("趋势因子", bd.trend, 30, bd.trend_detail),
            ("资金因子", bd.capital, 30, bd.capital_detail),
            ("形态因子", bd.pattern, 20, bd.pattern_detail),
            ("情绪因子", bd.sentiment, 20, bd.sentiment_detail),
        ]
        dimensions.sort(key=lambda x: x[1] / x[2], reverse=True)

        highlights = []
        for name, score, max_score, detail in dimensions[:2]:
            pct = round(score / max_score * 100, 1)
            highlights.append({
                "dimension": name,
                "score": f"{score:.1f}/{max_score}",
                "percentage": f"{pct}%",
                "detail": detail,
            })

        # 2. 资金关注度（基于量比和换手率）
        last_idx = len(bars) - 1
        vol_ratio = result.calculation_basis.get("indicators", {}).get("volume_ratio_5d", 0)
        capital_attention = {
            "5日量比": vol_ratio,
            "量能状态": "放量" if vol_ratio >= 1.5 else ("温和放量" if vol_ratio >= 1.2 else ("平稳" if vol_ratio >= 0.9 else "缩量")),
            "近3日阳线数": sum(1 for b in bars[-3:] if b.pct_chg > 0) if last_idx >= 3 else 0,
        }

        # 3. 涨停基因
        limit_count = bd.sentiment_detail.get("limit_up_count_60d", 0)
        limit_gene = {
            "近60日涨停次数": limit_count,
            "涨停基因": "强" if limit_count >= 5 else ("中" if limit_count >= 3 else ("弱" if limit_count >= 1 else "无")),
        }

        # 4. 综合优势描述
        top_dim = dimensions[0]
        advantage_desc = f"{top_dim[0]}突出（{top_dim[1]:.0f}/{top_dim[2]}分，占比{top_dim[1]/top_dim[2]*100:.0f}%）"
        if len(dimensions) > 1 and dimensions[1][1] / dimensions[1][2] >= 0.6:
            advantage_desc += f"，{dimensions[1][0]}也较强（{dimensions[1][1]:.0f}/{dimensions[1][2]}分）"

        return {
            "score_highlights": highlights,
            "top_dimension": top_dim[0],
            "advantage_description": advantage_desc,
            "capital_attention": capital_attention,
            "limit_up_gene": limit_gene,
            "total_score": f"{bd.total:.1f}/100",
            "stars": result.stars,
            "note": "同类排名和行业地位需结合选股扫描结果计算，可在调用时传入scan_context参数补充",
        }

    # ---------- 维度6：操作理由 ----------

    def _gen_action_advice(self, result: BuyPointResult, checks: Dict) -> Dict:
        """
        操作理由：
        - 操作建议：强烈买入/买入/试仓/观望/回避
        - 仓位建议
        - 持有周期
        - 关键观察点
        - 失效信号
        """
        grade = result.grade
        score = result.score
        risk = result.risk_level
        btype = result.buy_type

        # 1. 操作建议
        if grade == GRADE_A and score >= 70 and risk == "低":
            suggestion = "强烈买入"
        elif grade in (GRADE_A, GRADE_B) and score >= 60 and risk in ("低", "中"):
            suggestion = "买入"
        elif grade in (GRADE_C, GRADE_D) and score >= 50:
            suggestion = "试仓"
        elif score >= 40:
            suggestion = "观望"
        else:
            suggestion = "回避"

        # 2. 仓位建议
        if risk == "低":
            position = "30%-50%"
        elif risk == "中":
            position = "15%-30%"
        else:
            position = "5%-15%（轻仓试错）" if suggestion in ("买入", "试仓") else "0%（观望）"

        # 3. 持有周期
        holding_map = {
            GRADE_A: "5-15个交易日（主升浪持有）",
            GRADE_B: "3-10个交易日（二次启动持有）",
            GRADE_C: "10-20个交易日（底部反转持有）",
            GRADE_D: "5-15个交易日（突破后持有）",
            GRADE_NONE: "不建议持有",
        }
        holding = holding_map.get(grade, "不建议持有")

        # 4. 关键观察点
        key_watchpoints = []
        pl = result.price_levels
        if grade == GRADE_A:
            key_watchpoints = [
                f"MA5是否持续在MA10上方（当前MA5={result.calculation_basis.get('indicators',{}).get('ma5')}）",
                f"成交量是否维持在均量1.2倍以上",
                f"能否站稳突破价{pl.breakout_price:.2f}",
            ]
        elif grade == GRADE_B:
            key_watchpoints = [
                f"20日线{pl.support:.2f}是否持续支撑",
                "回调是否缩量、反弹是否放量",
                f"前高压力{pl.resistance:.2f}能否突破",
            ]
        elif grade == GRADE_C:
            key_watchpoints = [
                "MACD绿柱是否持续缩短",
                "KDJ金叉后是否持续向上",
                f"近期低点是否守住（支撑{pl.support:.2f}）",
            ]
        elif grade == GRADE_D:
            key_watchpoints = [
                f"突破后3天内是否跌回箱体（箱体上沿{pl.resistance:.2f}）",
                "突破日量能是否持续",
                "均线是否从粘合转向发散",
            ]
        else:
            key_watchpoints = [
                "等待明确买点信号形成",
                "关注MA5/MA10金叉机会",
                "量能是否出现放大迹象",
            ]

        # 5. 失效信号
        invalid_signals = result.buy_point_logic.get("invalid_conditions", [
            "跌破关键支撑位且放量",
            "核心技术指标出现死叉",
        ])

        return {
            "suggestion": suggestion,
            "position": position,
            "holding_period": holding,
            "key_watchpoints": key_watchpoints,
            "invalid_signals": invalid_signals,
            "risk_level": risk,
            "confidence": f"{result.stars}星（{score:.0f}分）",
        }

    # ---------- 自然语言操作理由摘要 ----------

    def _gen_action_summary(self, result: BuyPointResult) -> str:
        """生成200-300字自然语言操作理由摘要"""
        pl = result.price_levels
        bd = result.score_breakdown
        aa = result.action_advice
        pc = result.position_context
        logic = result.buy_point_logic

        lines = []
        lines.append("【操作理由】")

        # 开头：类型+位置
        btype = result.buy_type
        trend = pc.get("trend_stage", "未知")
        lines.append(f"该股属于【{btype}】，当前处于{trend}。")

        # 价格位置
        pp = pc.get("price_position", {})
        if "距MA20" in pp:
            ma20_dist = pp["距MA20"]
            pos_desc = f"现价{pl.current_price:.2f}，距20日线{ma20_dist:+.2f}%"
            if "60日位置百分位" in pp:
                pos_desc += f"，60日位置百分位{pp['60日位置百分位']}%"
            lines.append(pos_desc + "。")

        # 为什么买
        lines.append("")
        lines.append("为什么买：")
        for i, reason in enumerate(result.why_this_position[:3], 1):
            lines.append(f"{i}. {reason['indicator']}：{reason['current_value']}（{reason['explanation']}）")

        # 买入策略
        lines.append("")
        lines.append("买入策略：")
        lines.append(f"- 最佳买入区间：{pl.best_buy_low:.2f}-{pl.best_buy_high:.2f}，依据ATR({pl.atr:.2f})波动率计算")
        lines.append(f"- 突破确认价：{pl.breakout_price:.2f}，突破后可加仓")
        lines.append(f"- 止损位：{pl.stop_loss:.2f}，跌破立即离场")
        lines.append(f"- 目标位：{pl.target_low:.2f}-{pl.target_high:.2f}，盈亏比{pl.risk_reward_ratio:.1f}:1")

        # 仓位和持有
        lines.append("")
        lines.append(f"操作建议：{aa.get('suggestion', '观望')}，仓位{aa.get('position', '0%')}，持有周期{aa.get('holding_period', '不建议')}。")

        # 风险提示
        if result.risks:
            lines.append(f"风险提示：{result.risks[0]}")

        # 关键观察
        if aa.get("key_watchpoints"):
            lines.append(f"关键观察：{aa['key_watchpoints'][0]}")

        return "\n".join(lines)

    # ============================================================
    # 批量分析
    # ============================================================

    def batch_analyze(self, stock_list: List[Dict]) -> List[BuyPointResult]:
        """
        批量分析多只股票

        Args:
            stock_list: [{"code": "", "name": "", "kline_data": ...}, ...]

        Returns:
            List[BuyPointResult]，按评分降序
        """
        results = []
        for stock in stock_list:
            try:
                r = self.analyze(
                    kline_data=stock.get("kline_data"),
                    code=stock.get("code", ""),
                    name=stock.get("name", ""),
                    market_env_data=stock.get("market_env_data"),
                    annotation_data=stock.get("annotation_data"),
                )
                results.append(r)
            except Exception as e:
                logger.warning(f"[BuyPoint] 批量分析异常 {stock.get('code', '?')}: {e}")
                results.append(BuyPointResult(
                    code=stock.get("code", ""),
                    name=stock.get("name", ""),
                    reasons=[f"分析异常: {e}"],
                ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results


# ============================================================
# 便捷函数
# ============================================================

_default_engine = None


def get_buy_point_engine() -> BuyPointEngine:
    """获取买点引擎单例"""
    global _default_engine
    if _default_engine is None:
        _default_engine = BuyPointEngine()
    return _default_engine


def analyze_buy_point(kline_data, code: str = "", name: str = "",
                      market_env_data: Optional[Dict] = None) -> BuyPointResult:
    """
    便捷函数：分析单只股票买点

    Args:
        kline_data: K线数据
        code: 股票代码
        name: 股票名称
        market_env_data: 市场环境数据

    Returns:
        BuyPointResult
    """
    return get_buy_point_engine().analyze(kline_data, code, name, market_env_data)
