# -*- coding: utf-8 -*-
"""
V6.5 阶段7：股票详情AI报告生成器

新增独立模块，不修改现有核心逻辑。
整合阶段2（综合评分）、阶段4（市场环境）、阶段6（案例学习），
为每只股票生成包含评分、阶段、优势、风险、操作建议的AI报告。

核心类：StockAIReportGenerator
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.base import TechnicalIndicators
from strategy.ai_composite_score import AICompositeScoreEngine
from strategy.market_environment import MarketEnvironment
from strategy.ai_case_learning import AICaseLearning, CaseFeatures

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================

@dataclass
class AIReport:
    """股票AI报告"""
    stock_code: str = ""
    stock_name: str = ""
    composite_score: float = 0.0
    grade: str = ""
    stage: str = ""              # 吸筹/启动/主升/加速/风险
    current_price: float = 0.0
    change_pct: float = 0.0
    advantages: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    advice: str = ""
    market_env: str = ""
    market_factor: float = 1.0
    similar_cases: Optional[Dict] = None
    # 技术指标快照（用于报告展示）
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma_alignment: str = ""
    kdj_k: float = 0.0
    kdj_d: float = 0.0
    macd_hist: float = 0.0
    volume_ratio: float = 0.0
    rps20: float = 0.0
    # 阶段详情
    stage_detail: str = ""
    generated_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# AI报告生成器
# ============================================================

class StockAIReportGenerator:
    """
    V6.5 股票详情AI报告生成器

    整合：
      - 阶段2 AICompositeScoreEngine（综合评分）
      - 阶段4 MarketEnvironment（市场环境）
      - 阶段6 AICaseLearning（相似案例）
    """

    # 阶段定义
    STAGE_ACCUMULATION = "吸筹"
    STAGE_LAUNCH = "启动"
    STAGE_MAIN_RISE = "主升"
    STAGE_ACCELERATION = "加速"
    STAGE_RISK = "风险"

    def __init__(self, enable_case_matching: bool = True):
        self.score_engine = AICompositeScoreEngine()
        self.market_env = MarketEnvironment()
        self.case_learner = AICaseLearning() if enable_case_matching else None
        self._env_cache = None
        self._env_cache_time = 0
        self._stock_names = self._load_stock_names()

    def _load_stock_names(self) -> Dict[str, str]:
        """加载股票名称映射"""
        names = {}
        for path in [
            os.path.join(PROJECT_ROOT, "data", "stock_names_full.json"),
            os.path.join(PROJECT_ROOT, "data", "cache", "stock_names.json"),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        names.update(data)
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "code" in item:
                                names[item["code"]] = item.get("name", "")
                except Exception:
                    pass
        return names

    def _get_market_env(self):
        """获取市场环境（缓存5分钟）"""
        now = datetime.now().timestamp()
        if self._env_cache and (now - self._env_cache_time) < 300:
            return self._env_cache
        try:
            self._env_cache = self.market_env.calculate()
            self._env_cache_time = now
        except Exception as e:
            logger.warning(f"市场环境计算失败: {e}")
            self._env_cache = None
        return self._env_cache

    # ============================================================
    # 主入口：生成报告
    # ============================================================

    def generate_report(
        self,
        stock_code: str,
        kline_data: List[Dict] = None,
        stock_data: Dict = None,
    ) -> Optional[AIReport]:
        """
        生成股票AI报告。

        Args:
            stock_code: 股票代码
            kline_data: K线数据（可选，为None时从TDX读取）
            stock_data: 策略评分数据（可选，包含force_behavior_score等）

        Returns:
            AIReport 或 None
        """
        report = AIReport()
        report.stock_code = stock_code
        report.stock_name = self._stock_names.get(stock_code, stock_code)
        report.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 获取K线数据
        if kline_data is None:
            kline_data = self._load_kline(stock_code)
        if not kline_data or len(kline_data) < 30:
            logger.warning(f"{stock_code} K线数据不足")
            return None

        # 2. 计算技术指标
        indicators = self._calc_indicators(kline_data)
        self._fill_indicator_snapshot(report, indicators, kline_data)

        # 3. 识别阶段
        report.stage, report.stage_detail = self._identify_stage(kline_data, indicators)

        # 4. 计算综合评分
        score_result = self._calc_composite_score(stock_code, kline_data, indicators, stock_data)
        if score_result:
            report.composite_score = score_result.get("composite_score", 0)
            report.grade = score_result.get("grade", "")
        else:
            # 无策略评分时，用技术面评分替代
            report.composite_score = self._calc_technical_score(kline_data, indicators)
            report.grade = AICompositeScoreEngine.get_grade(report.composite_score)

        # 5. 市场环境
        env = self._get_market_env()
        if env:
            report.market_env = env.env_type
            report.market_factor = env.factor
        else:
            report.market_env = "未知"
            report.market_factor = 1.0

        # 6. 分析优势和风险
        report.advantages = self._analyze_advantages(kline_data, indicators, report)
        report.risks = self._analyze_risks(kline_data, indicators, report)

        # 7. 生成操作建议
        report.advice = self._generate_advice(report)

        # 8. 相似案例匹配（可选）
        if self.case_learner:
            try:
                cur_features = AICaseLearning.extract_features(
                    kline_data, len(kline_data) - 1,
                    stock_code=stock_code, stock_name=report.stock_name,
                    case_type="buy", source="report"
                )
                if cur_features:
                    similar = self.case_learner.find_similar_cases(
                        cur_features, top_n=5, case_type="buy"
                    )
                    if similar:
                        stats = self.case_learner.get_case_statistics(similar)
                        report.similar_cases = {
                            "count": stats.similar_count,
                            "success_rate": round(stats.success_rate, 1),
                            "avg_5d_return": round(stats.avg_5d_return, 2),
                            "avg_10d_return": round(stats.avg_10d_return, 2),
                            "top_cases": [
                                {
                                    "stock": f"{c.stock_code} {c.stock_name}",
                                    "date": c.case_date,
                                    "similarity": c.similarity,
                                    "next_5d": c.next_5d_return,
                                }
                                for c in similar[:3]
                            ],
                        }
            except Exception as e:
                logger.warning(f"相似案例匹配失败: {e}")

        return report

    def _load_kline(self, stock_code: str) -> List[Dict]:
        """从TDX加载K线数据"""
        try:
            from data.tdx_data_engine import get_tdx_data_engine
            tdx = get_tdx_data_engine()
            return tdx.get_kline(stock_code, days=250)
        except Exception as e:
            logger.warning(f"加载K线失败 {stock_code}: {e}")
            return []

    # ============================================================
    # 技术指标计算
    # ============================================================

    def _calc_indicators(self, kline_data: List[Dict]) -> Dict:
        """计算技术指标"""
        closes = np.array([k.get("close", 0) for k in kline_data], dtype=float)
        highs = np.array([k.get("high", 0) for k in kline_data], dtype=float)
        lows = np.array([k.get("low", 0) for k in kline_data], dtype=float)
        volumes = np.array([k.get("volume", 0) for k in kline_data], dtype=float)

        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        ma60 = TechnicalIndicators.ma(closes, 60)
        k, d, j = TechnicalIndicators.kdj(highs, lows, closes)
        dif, dea, hist = TechnicalIndicators.macd(closes)

        idx = len(kline_data) - 1
        return {
            "closes": closes, "highs": highs, "lows": lows, "volumes": volumes,
            "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
            "kdj_k": k, "kdj_d": d, "kdj_j": j,
            "macd_dif": dif, "macd_dea": dea, "macd_hist": hist,
            "idx": idx,
        }

    def _fill_indicator_snapshot(self, report: AIReport, ind: Dict, kline: List[Dict]):
        """填充指标快照到报告"""
        idx = ind["idx"]
        report.current_price = float(ind["closes"][idx])
        if idx > 0 and ind["closes"][idx - 1] > 0:
            report.change_pct = float((ind["closes"][idx] - ind["closes"][idx - 1]) / ind["closes"][idx - 1] * 100)

        report.ma5 = float(ind["ma5"][idx]) if not np.isnan(ind["ma5"][idx]) else 0
        report.ma10 = float(ind["ma10"][idx]) if not np.isnan(ind["ma10"][idx]) else 0
        report.ma20 = float(ind["ma20"][idx]) if not np.isnan(ind["ma20"][idx]) else 0

        if report.ma5 > 0 and report.ma10 > 0 and report.ma20 > 0:
            if report.ma5 > report.ma10 > report.ma20:
                report.ma_alignment = "多头"
            elif report.ma5 < report.ma10 < report.ma20:
                report.ma_alignment = "空头"
            else:
                report.ma_alignment = "粘合"

        report.kdj_k = float(ind["kdj_k"][idx]) if not np.isnan(ind["kdj_k"][idx]) else 50
        report.kdj_d = float(ind["kdj_d"][idx]) if not np.isnan(ind["kdj_d"][idx]) else 50
        report.macd_hist = float(ind["macd_hist"][idx]) if not np.isnan(ind["macd_hist"][idx]) else 0

        # 量比
        if idx >= 5:
            avg5 = np.mean(ind["volumes"][idx - 5:idx])
            report.volume_ratio = float(ind["volumes"][idx] / avg5) if avg5 > 0 else 1.0

        # RPS20简化
        if idx >= 20 and ind["closes"][idx - 20] > 0:
            ret20 = (ind["closes"][idx] - ind["closes"][idx - 20]) / ind["closes"][idx - 20] * 100
            report.rps20 = max(0, min(100, 50 + ret20 * 2))

    # ============================================================
    # 阶段识别
    # ============================================================

    def _identify_stage(self, kline: List[Dict], ind: Dict) -> Tuple[str, str]:
        """
        识别5个阶段：吸筹/启动/主升/加速/风险
        返回 (阶段, 详情说明)
        """
        idx = ind["idx"]
        closes = ind["closes"]
        volumes = ind["volumes"]
        ma5 = ind["ma5"]
        ma10 = ind["ma10"]
        ma20 = ind["ma20"]

        if idx < 20:
            return self.STAGE_ACCUMULATION, "数据不足，默认吸筹阶段"

        cur_close = closes[idx]
        cur_ma5 = ma5[idx] if not np.isnan(ma5[idx]) else cur_close
        cur_ma10 = ma10[idx] if not np.isnan(ma10[idx]) else cur_close
        cur_ma20 = ma20[idx] if not np.isnan(ma20[idx]) else cur_close

        # 近20日振幅
        high20 = np.max(ind["highs"][idx - 19:idx + 1])
        low20 = np.min(ind["lows"][idx - 19:idx + 1])
        amplitude20 = (high20 - low20) / low20 * 100 if low20 > 0 else 0

        # 近5日均量 / 近20日均量
        vol5 = np.mean(volumes[max(0, idx - 4):idx + 1])
        vol20 = np.mean(volumes[max(0, idx - 19):idx + 1])
        vol_ratio = vol5 / vol20 if vol20 > 0 else 1.0

        # 近10日涨幅
        ret10 = (cur_close - closes[idx - 10]) / closes[idx - 10] * 100 if idx >= 10 and closes[idx - 10] > 0 else 0

        # 近5日涨幅
        ret5 = (cur_close - closes[idx - 5]) / closes[idx - 5] * 100 if idx >= 5 and closes[idx - 5] > 0 else 0

        # 均线偏差（粘合判断）
        ma_dev = 0
        if cur_ma5 > 0 and cur_ma10 > 0 and cur_ma20 > 0:
            ma_avg = (cur_ma5 + cur_ma10 + cur_ma20) / 3
            ma_dev = max(abs(cur_ma5 - ma_avg), abs(cur_ma10 - ma_avg), abs(cur_ma20 - ma_avg)) / ma_avg * 100

        # MACD状态
        macd_hist = ind["macd_hist"][idx] if not np.isnan(ind["macd_hist"][idx]) else 0
        macd_hist_prev = ind["macd_hist"][idx - 1] if idx > 0 and not np.isnan(ind["macd_hist"][idx - 1]) else 0

        # 近3日涨幅和量比
        ret3 = (cur_close - closes[idx - 3]) / closes[idx - 3] * 100 if idx >= 3 and closes[idx - 3] > 0 else 0
        vol3_ratio = volumes[idx] / (np.mean(volumes[idx - 5:idx]) if idx >= 5 else 1)

        # === 加速阶段 ===
        # 近5日连续大阳或涨幅>15%，收盘价偏离MA5>10%，成交量急剧放大
        deviation_ma5 = (cur_close - cur_ma5) / cur_ma5 * 100 if cur_ma5 > 0 else 0
        if ret5 > 15 and deviation_ma5 > 8 and vol_ratio > 1.5:
            return self.STAGE_ACCELERATION, (
                f"近5日涨幅{ret5:.1f}%，偏离MA5达{deviation_ma5:.1f}%，"
                f"量比{vol_ratio:.2f}，短期加速明显"
            )

        # === 风险阶段 ===
        # 高位放量滞涨：近3日涨幅<1%但量比>1.5，或MA5拐头向下，或MACD死叉
        ma5_prev = ma5[idx - 1] if idx > 0 and not np.isnan(ma5[idx - 1]) else cur_ma5
        macd_dead_cross = (macd_hist_prev > 0 and macd_hist < 0)
        high_volume_stagnation = (ret3 < 1 and vol3_ratio > 1.5)
        ma5_turning_down = (cur_ma5 < ma5_prev)

        if (high_volume_stagnation or macd_dead_cross) and ret10 > 5:
            reasons = []
            if high_volume_stagnation:
                reasons.append(f"近3日涨幅仅{ret3:.1f}%但量比{vol3_ratio:.2f}，放量滞涨")
            if macd_dead_cross:
                reasons.append("MACD红柱转绿，死叉信号")
            if ma5_turning_down:
                reasons.append("MA5拐头向下")
            return self.STAGE_RISK, "；".join(reasons)

        # === 主升阶段 ===
        # MA5>MA10>MA20多头，近10日涨幅>10%，成交量持续放大
        if cur_ma5 > cur_ma10 > cur_ma20 and ret10 > 10 and vol_ratio >= 0.8:
            return self.STAGE_MAIN_RISE, (
                f"MA5({cur_ma5:.2f})>MA10({cur_ma10:.2f})>MA20({cur_ma20:.2f})多头排列，"
                f"近10日涨幅{ret10:.1f}%，量比{vol_ratio:.2f}"
            )

        # === 启动阶段 ===
        # 突破近20日平台（收盘>20日最高×0.98），放量（量比>1.5），MA5上穿MA10
        ma5_prev5 = ma5[idx - 1] if idx > 0 and not np.isnan(ma5[idx - 1]) else cur_ma5
        ma10_prev5 = ma10[idx - 1] if idx > 0 and not np.isnan(ma10[idx - 1]) else cur_ma10
        golden_cross = (ma5_prev5 <= ma10_prev5 and cur_ma5 > cur_ma10)
        breakout = (cur_close >= high20 * 0.98)

        if (breakout and vol_ratio > 1.2) or golden_cross:
            reasons = []
            if breakout:
                reasons.append(f"突破近20日平台（最高{high20:.2f}）")
            if golden_cross:
                reasons.append("MA5上穿MA10金叉")
            if vol_ratio > 1.2:
                reasons.append(f"放量确认（量比{vol_ratio:.2f}）")
            return self.STAGE_LAUNCH, "；".join(reasons)

        # === 吸筹阶段 ===
        # 低位横盘（振幅<15%），缩量（vol5<vol20×0.7），均线粘合（偏差<3%）
        if amplitude20 < 15 and vol_ratio < 0.8 and ma_dev < 5:
            return self.STAGE_ACCUMULATION, (
                f"近20日振幅{amplitude20:.1f}%，量比{vol_ratio:.2f}缩量，"
                f"均线偏差{ma_dev:.1f}%粘合"
            )

        # 默认：根据趋势判断
        if cur_ma5 > cur_ma10 > cur_ma20:
            return self.STAGE_MAIN_RISE, f"多头排列，近10日涨幅{ret10:.1f}%"
        elif cur_ma5 < cur_ma10 < cur_ma20:
            return self.STAGE_RISK, f"空头排列，近10日涨幅{ret10:.1f}%"
        else:
            return self.STAGE_ACCUMULATION, f"均线粘合，近20日振幅{amplitude20:.1f}%"

    # ============================================================
    # 综合评分计算
    # ============================================================

    def _calc_composite_score(
        self, stock_code: str, kline: List[Dict], ind: Dict, stock_data: Dict = None
    ) -> Optional[Dict]:
        """计算综合评分，优先从缓存读取策略评分"""
        # 尝试从stock_data获取
        if stock_data and ("force_behavior_score" in stock_data or "nine_filter_score" in stock_data):
            return self.score_engine.calculate(stock_data)

        # 从缓存读取
        fb_score = self._get_cached_score("data/cache/scan_result_cache.json", stock_code)
        nf_score = self._get_cached_score("data/cache/nine_filter_scan_cache.json", stock_code)

        if fb_score is None and nf_score is None:
            return None

        # 构建stock_data
        data = {
            "code": stock_code,
            "name": self._stock_names.get(stock_code, ""),
            "price": float(ind["closes"][ind["idx"]]),
            "change_pct": (float(ind["closes"][ind["idx"]]) - float(ind["closes"][ind["idx"] - 1])) / float(ind["closes"][ind["idx"] - 1]) * 100 if ind["idx"] > 0 else 0,
            "volume_ratio": float(np.mean(ind["volumes"][ind["idx"] - 5:ind["idx"] + 1]) / np.mean(ind["volumes"][ind["idx"] - 20:ind["idx"] + 1])) if ind["idx"] >= 20 else 1.0,
            "ma5": report_safe(ind["ma5"][ind["idx"]]),
            "ma10": report_safe(ind["ma10"][ind["idx"]]),
            "ma20": report_safe(ind["ma20"][ind["idx"]]),
        }
        if fb_score is not None:
            data["force_behavior_score"] = fb_score
        if nf_score is not None:
            data["nine_filter_score"] = nf_score

        # 设置市场环境
        env = self._get_market_env()
        if env:
            self.score_engine.set_market_env(env.score, env.env_type, env.factor)
        else:
            self.score_engine.clear_market_env()

        return self.score_engine.calculate(data)

    def _get_cached_score(self, cache_path: str, stock_code: str) -> Optional[float]:
        """从缓存文件读取股票评分"""
        full_path = os.path.join(PROJECT_ROOT, cache_path)
        if not os.path.exists(full_path):
            return None
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # scan_result_cache.json 格式: {code: {...}}
            if isinstance(data, dict) and stock_code in data:
                item = data[stock_code]
                if isinstance(item, dict):
                    score = item.get("score", {})
                    if isinstance(score, dict):
                        return score.get("total")
                    return score
            # nine_filter_scan_cache.json 格式: {results: [{code, score: {total}}]}
            if isinstance(data, dict) and "results" in data:
                for item in data["results"]:
                    if item.get("code") == stock_code:
                        score = item.get("score", {})
                        if isinstance(score, dict):
                            return score.get("total")
            # list格式
            if isinstance(data, list):
                for item in data:
                    if item.get("code") == stock_code:
                        score = item.get("score", {})
                        if isinstance(score, dict):
                            return score.get("total")
        except Exception:
            pass
        return None

    def _calc_technical_score(self, kline: List[Dict], ind: Dict) -> float:
        """无策略评分时，用技术面计算基础评分（0-100）"""
        idx = ind["idx"]
        score = 50.0  # 基准分

        # 均线排列（+20/-20）
        ma5 = report_safe(ind["ma5"][idx])
        ma10 = report_safe(ind["ma10"][idx])
        ma20 = report_safe(ind["ma20"][idx])
        if ma5 > ma10 > ma20:
            score += 20
        elif ma5 < ma10 < ma20:
            score -= 20
        elif ma5 > ma10:
            score += 8

        # 趋势（+15/-15）
        if idx >= 10 and ind["closes"][idx - 10] > 0:
            ret10 = (ind["closes"][idx] - ind["closes"][idx - 10]) / ind["closes"][idx - 10] * 100
            score += max(-15, min(15, ret10))

        # KDJ（+10/-10）
        kdj_k = report_safe(ind["kdj_k"][idx], 50)
        if 20 < kdj_k < 80:
            score += 5
        elif kdj_k >= 80:
            score -= 5  # 超买
        elif kdj_k <= 20:
            score += 3  # 超卖反弹可能

        # MACD（+10/-10）
        hist = report_safe(ind["macd_hist"][idx])
        if hist > 0:
            score += 8
        else:
            score -= 8

        # 量价配合（+5/-5）
        if idx >= 5:
            vol5 = np.mean(ind["volumes"][idx - 4:idx + 1])
            vol20 = np.mean(ind["volumes"][max(0, idx - 19):idx + 1])
            if vol5 > vol20 * 1.2 and ind["closes"][idx] > ind["closes"][idx - 1]:
                score += 5
            elif vol5 < vol20 * 0.7:
                score -= 3

        return max(0, min(100, score))

    # ============================================================
    # 优势分析
    # ============================================================

    def _analyze_advantages(self, kline: List[Dict], ind: Dict, report: AIReport) -> List[str]:
        """分析3条核心优势，基于真实数据"""
        advantages = []
        idx = ind["idx"]
        closes = ind["closes"]
        volumes = ind["volumes"]

        # 1. 均线多头排列
        if report.ma_alignment == "多头":
            advantages.append(
                f"MA5({report.ma5:.2f})>MA10({report.ma10:.2f})>MA20({report.ma20:.2f})多头排列，趋势向上"
            )
        elif report.ma_alignment == "粘合":
            advantages.append("均线粘合蓄势，方向选择在即")

        # 2. 量价配合
        if report.volume_ratio > 1.5 and report.change_pct > 0:
            advantages.append(f"当日放量上涨，量比{report.volume_ratio:.2f}，量价配合良好")
        elif report.volume_ratio > 1.2 and report.change_pct > 0:
            advantages.append(f"温和放量上涨，量比{report.volume_ratio:.2f}，资金关注度提升")

        # 3. MACD红柱
        if report.macd_hist > 0:
            advantages.append(f"MACD红柱运行（HIST={report.macd_hist:.3f}），多头动能持续")

        # 4. KDJ金叉或低位
        if report.kdj_k > report.kdj_d and report.kdj_k < 70:
            advantages.append(f"KDJ金叉向上（K={report.kdj_k:.1f}, D={report.kdj_d:.1f}），未超买")
        elif report.kdj_k < 30:
            advantages.append(f"KDJ处于低位（K={report.kdj_k:.1f}），超卖反弹空间")

        # 5. 突破平台
        if idx >= 20:
            high20 = np.max(ind["highs"][idx - 19:idx + 1])
            if closes[idx] >= high20 * 0.98:
                advantages.append(f"股价接近/突破近20日高点（{high20:.2f}），平台突破态势")

        # 6. RPS强势
        if report.rps20 > 80:
            advantages.append(f"20日相对强度RPS={report.rps20:.1f}，跑赢多数个股")

        # 7. 阶段优势
        if report.stage == "主升":
            advantages.append("处于主升阶段，趋势明确，顺势而为")
        elif report.stage == "启动":
            advantages.append(f"处于启动阶段，{report.stage_detail}")

        # 8. 相似案例成功率高
        if report.similar_cases and report.similar_cases.get("success_rate", 0) > 50:
            advantages.append(
                f"历史相似案例成功率{report.similar_cases['success_rate']:.0f}%，"
                f"平均5日涨幅{report.similar_cases['avg_5d_return']:.1f}%"
            )

        # 去重并取前3条
        return self._dedupe_and_limit(advantages, 3)

    # ============================================================
    # 风险分析
    # ============================================================

    def _analyze_risks(self, kline: List[Dict], ind: Dict, report: AIReport) -> List[str]:
        """分析3条核心风险，基于真实数据"""
        risks = []
        idx = ind["idx"]
        closes = ind["closes"]

        # 1. 短期涨幅过大
        if idx >= 5 and closes[idx - 5] > 0:
            ret5 = (closes[idx] - closes[idx - 5]) / closes[idx - 5] * 100
            if ret5 > 15:
                risks.append(f"近5日累计涨幅{ret5:.1f}%，短期超买，回调风险加大")
            elif ret5 > 10:
                risks.append(f"近5日涨幅{ret5:.1f}%，短期获利盘较多")

        # 2. 偏离均线过大
        if report.ma5 > 0:
            deviation = (closes[idx] - report.ma5) / report.ma5 * 100
            if deviation > 10:
                risks.append(f"收盘价偏离MA5达{deviation:.1f}%，回归均线压力大")
            elif deviation > 7:
                risks.append(f"收盘价偏离MA5达{deviation:.1f}%，短期有回踩需求")

        # 3. KDJ超买
        if report.kdj_k > 90:
            risks.append(f"KDJ严重超买（K={report.kdj_k:.1f}），随时可能回调")
        elif report.kdj_k > 80:
            risks.append(f"KDJ进入超买区（K={report.kdj_k:.1f}），追高风险增加")

        # 4. MACD死叉或绿柱
        if report.macd_hist < 0:
            risks.append(f"MACD绿柱运行（HIST={report.macd_hist:.3f}），空头动能释放中")
        elif idx > 0:
            hist_prev = report_safe(ind["macd_hist"][idx - 1])
            if hist_prev > 0 and report.macd_hist < hist_prev:
                risks.append("MACD红柱缩短，多头动能减弱")

        # 5. 均线空头
        if report.ma_alignment == "空头":
            risks.append("MA5<MA10<MA20空头排列，趋势向下，反弹空间有限")

        # 6. 放量滞涨
        if report.volume_ratio > 1.5 and abs(report.change_pct) < 1:
            risks.append(f"放量滞涨（量比{report.volume_ratio:.2f}，涨跌幅{report.change_pct:.1f}%），主力可能出货")

        # 7. 接近压力位
        if idx >= 60:
            high60 = np.max(ind["highs"][idx - 59:idx + 1])
            distance = (high60 - closes[idx]) / closes[idx] * 100
            if 0 < distance < 5:
                risks.append(f"距60日高点{high60:.2f}仅{distance:.1f}%，压力位附近需放量确认")

        # 8. 阶段风险
        if report.stage == "风险":
            risks.append(f"处于风险阶段：{report.stage_detail}")
        elif report.stage == "加速":
            risks.append(f"处于加速阶段：{report.stage_detail}，追高需谨慎")

        # 9. 市场环境
        if report.market_env == "弱势":
            risks.append("市场环境弱势（系数0.7），整体仓位需控制")
        elif report.market_env == "风险":
            risks.append("市场环境风险，禁止追涨，宜空仓观望")

        # 10. 相似案例成功率低
        if report.similar_cases and 0 < report.similar_cases.get("success_rate", 100) < 30:
            risks.append(
                f"历史相似案例成功率仅{report.similar_cases['success_rate']:.0f}%，"
                f"平均5日涨幅{report.similar_cases['avg_5d_return']:.1f}%"
            )

        # 兜底：确保至少有风险提示
        if not risks:
            if report.change_pct > 7:
                risks.append(f"当日涨幅{report.change_pct:.1f}%接近涨停，追高需谨慎")
            elif report.composite_score >= 80:
                risks.append("评分较高，需关注后续量能能否持续")
            else:
                risks.append("需密切关注大盘环境变化对个股的影响")

        return self._dedupe_and_limit(risks, 3)

    @staticmethod
    def _dedupe_and_limit(items: List[str], limit: int) -> List[str]:
        """去重并限制数量"""
        seen = set()
        result = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
                if len(result) >= limit:
                    break
        return result

    # ============================================================
    # 操作建议
    # ============================================================

    def _generate_advice(self, report: AIReport) -> str:
        """
        生成操作建议：买入/等待/观察/减仓

        逻辑：
          - 买入：S+/S级 +（启动/主升阶段）+ 非风险环境
          - 等待：A级 + 启动阶段 + 震荡/牛市，或B级 + 主升阶段
          - 观察：B级 + 任何阶段，或观察级 + 非弱势环境
          - 减仓：风险级 + 任何环境，或加速阶段 + 放量滞涨 + S/A级
        """
        score = report.composite_score
        grade = report.grade
        stage = report.stage
        env = report.market_env

        # 风险级 → 减仓
        if grade == "风险" or score < 50:
            return "减仓"

        # 加速阶段 + 放量滞涨 → 减仓
        if stage == "加速" and report.volume_ratio > 1.5 and abs(report.change_pct) < 2:
            return "减仓"

        # 风险阶段 → 减仓/观望
        if stage == "风险":
            if grade in ("S+", "S", "A"):
                return "减仓"
            return "观望"

        # 风险环境 → 观望
        if env == "风险":
            return "观望"

        # S+/S级 + 启动/主升 → 买入
        if grade in ("S+", "S") and stage in ("启动", "主升"):
            return "买入"

        # A级 + 启动阶段 + 非弱势 → 等待（轻仓试探）
        if grade == "A" and stage == "启动" and env in ("牛市", "震荡"):
            return "等待"

        # A级 + 主升 → 买入（顺势）
        if grade == "A" and stage == "主升":
            return "买入"

        # B级 + 主升 → 等待
        if grade == "B" and stage == "主升":
            return "等待"

        # B级 → 观察
        if grade == "B":
            return "观察"

        # 观察级 → 观察
        if grade == "观察":
            return "观察"

        # S+/S级但非启动/主升（如吸筹/加速）
        if grade in ("S+", "S"):
            if stage == "吸筹":
                return "等待"
            if stage == "加速":
                return "观察"  # 加速不追高

        # A级其他情况
        if grade == "A":
            return "观察"

        return "观察"

    # ============================================================
    # 格式化输出
    # ============================================================

    def format_report_text(self, report: AIReport) -> str:
        """格式化为文本报告"""
        lines = []
        lines.append(f"股票: {report.stock_name}")
        lines.append(f"代码: {report.stock_code}")
        lines.append(f"AI综合评分: {report.composite_score:.0f} ({report.grade}级)")
        lines.append(f"所属阶段: {report.stage}")
        lines.append(f"当前价格: {report.current_price:.2f}  涨跌幅: {report.change_pct:+.2f}%")
        lines.append(f"市场环境: {report.market_env} (系数×{report.market_factor})")
        lines.append("")
        lines.append("优势:")
        for i, adv in enumerate(report.advantages, 1):
            lines.append(f"{i}. {adv}")
        lines.append("")
        lines.append("风险:")
        for i, risk in enumerate(report.risks, 1):
            lines.append(f"{i}. {risk}")
        lines.append("")
        lines.append(f"操作建议: {report.advice}")

        if report.similar_cases:
            lines.append("")
            lines.append(f"AI案例匹配: 相似案例{report.similar_cases['count']}个，"
                         f"成功率{report.similar_cases['success_rate']:.0f}%，"
                         f"平均5日涨幅{report.similar_cases['avg_5d_return']:.1f}%")

        lines.append(f"\n生成时间: {report.generated_at}")
        return "\n".join(lines)

    def format_report_dict(self, report: AIReport) -> Dict:
        """格式化为字典（用于UI显示）"""
        return report.to_dict()


# ============================================================
# 辅助函数
# ============================================================

def report_safe(val, default=0.0):
    """安全获取数值，处理NaN"""
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return float(val)
    except Exception:
        return default


# ============================================================
# 单例
# ============================================================

_default_generator = None


def get_stock_ai_report_generator(**kwargs) -> StockAIReportGenerator:
    """获取AI报告生成器单例"""
    global _default_generator
    if _default_generator is None:
        _default_generator = StockAIReportGenerator(**kwargs)
    return _default_generator
