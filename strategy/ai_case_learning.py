# -*- coding: utf-8 -*-
"""
V6.5 阶段6：AI复盘学习系统

新增独立模块，不修改现有标注/策略核心逻辑。
功能：
  - 案例库存储（DuckDB）
  - 从K线标注/回测/扫描结果自动生成案例
  - 相似案例匹配（形态40% + 量价30% + 指标30%）
  - 案例统计（成功率、平均涨幅、最大回撤）
  - 特征权重动态优化

核心类：AICaseLearning
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

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

from strategy.base import TechnicalIndicators

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================

@dataclass
class CaseFeatures:
    """案例特征向量"""
    # 基础信息
    stock_code: str = ""
    stock_name: str = ""
    case_date: str = ""
    case_type: str = "buy"        # buy / sell
    signal_type: str = ""         # B1/B2/B3/S1/S2/S3/S4

    # K线形态
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    volume: float = 0.0
    amount: float = 0.0

    # 均线状态
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    ma_alignment: str = ""        # 多头/空头/粘合

    # 技术指标
    kdj_k: float = 0.0
    kdj_d: float = 0.0
    kdj_j: float = 0.0
    macd_dif: float = 0.0
    macd_dea: float = 0.0
    macd_hist: float = 0.0
    rps20: float = 0.0

    # 量价特征
    volume_ratio: float = 0.0     # 量比（当日量/5日均量）
    turnover_rate: float = 0.0    # 换手率（估算）
    price_change_pct: float = 0.0 # 当日涨跌幅

    # 近5日K线形态编码（用于相似度计算）
    kline_pattern_5d: str = ""    # 5日阴阳线+影线编码
    price_trend_10d: float = 0.0  # 10日价格走势斜率
    volume_pattern_5d: str = ""   # 5日量能模式编码

    # 后续涨跌标签
    next_5d_return: float = 0.0
    next_10d_return: float = 0.0
    next_20d_return: float = 0.0
    next_5d_max_drawdown: float = 0.0
    next_10d_max_drawdown: float = 0.0
    next_20d_max_drawdown: float = 0.0
    is_success: int = 0           # 后续5日涨幅>3%

    # 元数据
    source: str = "auto"          # manual/auto/backtest
    created_at: str = ""
    feature_weight: float = 1.0   # 动态权重

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SimilarCaseResult:
    """相似案例匹配结果"""
    case_id: int = 0
    stock_code: str = ""
    stock_name: str = ""
    case_date: str = ""
    similarity: float = 0.0
    morphology_sim: float = 0.0
    volume_sim: float = 0.0
    indicator_sim: float = 0.0
    next_5d_return: float = 0.0
    next_10d_return: float = 0.0
    next_20d_return: float = 0.0
    is_success: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CaseStatistics:
    """案例统计结果"""
    total_cases: int = 0
    buy_cases: int = 0
    sell_cases: int = 0
    success_rate: float = 0.0
    avg_5d_return: float = 0.0
    avg_10d_return: float = 0.0
    avg_20d_return: float = 0.0
    avg_5d_drawdown: float = 0.0
    avg_10d_drawdown: float = 0.0
    avg_20d_drawdown: float = 0.0
    signal_type_dist: Dict = field(default_factory=dict)
    similar_count: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# AI案例学习引擎
# ============================================================

class AICaseLearning:
    """
    V6.5 AI复盘学习系统

    案例库：DuckDB，表 ai_case_library
    相似度：形态40% + 量价30% + 指标30%
    """

    # 相似度权重
    W_MORPHOLOGY = 0.40
    W_VOLUME = 0.30
    W_INDICATOR = 0.30

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(PROJECT_ROOT, "data", "cache", "ai_case_library.duckdb")
        self.db_path = db_path
        self._ensure_dir()
        self.conn = None
        self._init_db()

    def _ensure_dir(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    # ============================================================
    # 数据库初始化
    # ============================================================

    def _init_db(self):
        """初始化案例库表"""
        if not HAS_DUCKDB:
            logger.warning("DuckDB不可用，案例库功能受限")
            return
        self.conn = duckdb.connect(self.db_path)
        # 先创建序列
        try:
            self.conn.execute("CREATE SEQUENCE IF NOT EXISTS case_seq START 1")
        except Exception:
            pass
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_case_library (
                id INTEGER PRIMARY KEY DEFAULT nextval('case_seq'),
                stock_code VARCHAR,
                stock_name VARCHAR,
                case_date VARCHAR,
                case_type VARCHAR,
                signal_type VARCHAR,
                open_price DOUBLE,
                high_price DOUBLE,
                low_price DOUBLE,
                close_price DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                ma5 DOUBLE,
                ma10 DOUBLE,
                ma20 DOUBLE,
                ma60 DOUBLE,
                ma_alignment VARCHAR,
                kdj_k DOUBLE,
                kdj_d DOUBLE,
                kdj_j DOUBLE,
                macd_dif DOUBLE,
                macd_dea DOUBLE,
                macd_hist DOUBLE,
                rps20 DOUBLE,
                volume_ratio DOUBLE,
                turnover_rate DOUBLE,
                price_change_pct DOUBLE,
                kline_pattern_5d VARCHAR,
                price_trend_10d DOUBLE,
                volume_pattern_5d VARCHAR,
                next_5d_return DOUBLE,
                next_10d_return DOUBLE,
                next_20d_return DOUBLE,
                next_5d_max_drawdown DOUBLE,
                next_10d_max_drawdown DOUBLE,
                next_20d_max_drawdown DOUBLE,
                is_success INTEGER,
                source VARCHAR,
                created_at VARCHAR,
                feature_weight DOUBLE DEFAULT 1.0
            )
        """)
        # 创建索引
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_case_type ON ai_case_library(case_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_type ON ai_case_library(signal_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_case_date ON ai_case_library(case_date)")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    # ============================================================
    # 案例添加
    # ============================================================

    def add_case(self, case: CaseFeatures) -> int:
        """添加单个案例，返回case_id"""
        if not self.conn:
            return -1
        if not case.created_at:
            case.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute("""
            INSERT INTO ai_case_library (
                stock_code, stock_name, case_date, case_type, signal_type,
                open_price, high_price, low_price, close_price, volume, amount,
                ma5, ma10, ma20, ma60, ma_alignment,
                kdj_k, kdj_d, kdj_j, macd_dif, macd_dea, macd_hist, rps20,
                volume_ratio, turnover_rate, price_change_pct,
                kline_pattern_5d, price_trend_10d, volume_pattern_5d,
                next_5d_return, next_10d_return, next_20d_return,
                next_5d_max_drawdown, next_10d_max_drawdown, next_20d_max_drawdown,
                is_success, source, created_at, feature_weight
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case.stock_code, case.stock_name, case.case_date, case.case_type, case.signal_type,
            case.open_price, case.high_price, case.low_price, case.close_price,
            case.volume, case.amount,
            case.ma5, case.ma10, case.ma20, case.ma60, case.ma_alignment,
            case.kdj_k, case.kdj_d, case.kdj_j,
            case.macd_dif, case.macd_dea, case.macd_hist, case.rps20,
            case.volume_ratio, case.turnover_rate, case.price_change_pct,
            case.kline_pattern_5d, case.price_trend_10d, case.volume_pattern_5d,
            case.next_5d_return, case.next_10d_return, case.next_20d_return,
            case.next_5d_max_drawdown, case.next_10d_max_drawdown, case.next_20d_max_drawdown,
            case.is_success, case.source, case.created_at, case.feature_weight,
        ))
        # 获取刚插入的ID（DuckDB用currval）
        try:
            result = self.conn.execute("SELECT currval('case_seq')").fetchone()
            return result[0] if result else -1
        except Exception:
            return -1

    def batch_add_cases(self, cases: List[CaseFeatures]) -> int:
        """批量添加案例，返回成功数量"""
        count = 0
        for case in cases:
            cid = self.add_case(case)
            if cid > 0:
                count += 1
        return count

    # ============================================================
    # 特征提取
    # ============================================================

    @staticmethod
    def extract_features(
        kline_data: List[Dict],
        idx: int,
        stock_code: str = "",
        stock_name: str = "",
        case_type: str = "buy",
        signal_type: str = "",
        source: str = "auto",
    ) -> Optional[CaseFeatures]:
        """
        从K线数据中提取指定位置的特征向量。

        Args:
            kline_data: K线列表 [{date, open, high, low, close, volume, amount}, ...]
            idx: 提取特征的索引位置
            stock_code: 股票代码
            stock_name: 股票名称
            case_type: buy/sell
            signal_type: B1/B2/B3/S1/S2/S3/S4
            source: manual/auto/backtest

        Returns:
            CaseFeatures 或 None（数据不足时）
        """
        if not kline_data or idx < 20 or idx >= len(kline_data):
            return None

        closes = np.array([k.get("close", 0) for k in kline_data], dtype=float)
        highs = np.array([k.get("high", 0) for k in kline_data], dtype=float)
        lows = np.array([k.get("low", 0) for k in kline_data], dtype=float)
        volumes = np.array([k.get("volume", 0) for k in kline_data], dtype=float)

        bar = kline_data[idx]
        case = CaseFeatures()
        case.stock_code = stock_code
        case.stock_name = stock_name
        case.case_date = str(bar.get("date", ""))
        case.case_type = case_type
        case.signal_type = signal_type
        case.source = source

        # K线基础
        case.open_price = float(bar.get("open", 0))
        case.high_price = float(bar.get("high", 0))
        case.low_price = float(bar.get("low", 0))
        case.close_price = float(bar.get("close", 0))
        case.volume = float(bar.get("volume", 0))
        case.amount = float(bar.get("amount", 0))

        # 均线
        ma5_arr = TechnicalIndicators.ma(closes, 5)
        ma10_arr = TechnicalIndicators.ma(closes, 10)
        ma20_arr = TechnicalIndicators.ma(closes, 20)
        ma60_arr = TechnicalIndicators.ma(closes, 60)

        case.ma5 = float(ma5_arr[idx]) if not np.isnan(ma5_arr[idx]) else 0
        case.ma10 = float(ma10_arr[idx]) if not np.isnan(ma10_arr[idx]) else 0
        case.ma20 = float(ma20_arr[idx]) if not np.isnan(ma20_arr[idx]) else 0
        case.ma60 = float(ma60_arr[idx]) if not np.isnan(ma60_arr[idx]) else 0

        # 均线排列
        if case.ma5 > 0 and case.ma10 > 0 and case.ma20 > 0:
            if case.ma5 > case.ma10 > case.ma20:
                case.ma_alignment = "多头"
            elif case.ma5 < case.ma10 < case.ma20:
                case.ma_alignment = "空头"
            else:
                case.ma_alignment = "粘合"

        # KDJ
        k_arr, d_arr, j_arr = TechnicalIndicators.kdj(highs, lows, closes)
        case.kdj_k = float(k_arr[idx]) if not np.isnan(k_arr[idx]) else 50
        case.kdj_d = float(d_arr[idx]) if not np.isnan(d_arr[idx]) else 50
        case.kdj_j = float(j_arr[idx]) if not np.isnan(j_arr[idx]) else 50

        # MACD
        dif_arr, dea_arr, hist_arr = TechnicalIndicators.macd(closes)
        case.macd_dif = float(dif_arr[idx]) if not np.isnan(dif_arr[idx]) else 0
        case.macd_dea = float(dea_arr[idx]) if not np.isnan(dea_arr[idx]) else 0
        case.macd_hist = float(hist_arr[idx]) if not np.isnan(hist_arr[idx]) else 0

        # RPS20（简化：20日涨幅排名百分位，单股用相对自身20日涨幅）
        if idx >= 20 and closes[idx - 20] > 0:
            ret_20 = (closes[idx] - closes[idx - 20]) / closes[idx - 20] * 100
            case.rps20 = max(0, min(100, 50 + ret_20 * 2))  # 简化映射
        else:
            case.rps20 = 50

        # 量比
        if idx >= 5:
            avg_vol_5 = np.mean(volumes[idx - 5:idx])
            case.volume_ratio = float(volumes[idx] / avg_vol_5) if avg_vol_5 > 0 else 1.0
        else:
            case.volume_ratio = 1.0

        # 换手率（估算：成交量/流通股本，无数据时用0）
        case.turnover_rate = 0.0

        # 当日涨跌幅
        if idx > 0 and closes[idx - 1] > 0:
            case.price_change_pct = float((closes[idx] - closes[idx - 1]) / closes[idx - 1] * 100)

        # 近5日K线形态编码
        case.kline_pattern_5d = AICaseLearning._encode_kline_pattern(kline_data, idx, 5)

        # 10日价格走势斜率（线性回归斜率）
        if idx >= 10:
            x = np.arange(10)
            y = closes[idx - 9:idx + 1]
            if np.all(y > 0):
                slope = np.polyfit(x, y, 1)[0]
                case.price_trend_10d = float(slope / y[0] * 100) if y[0] > 0 else 0

        # 5日量能模式编码
        case.volume_pattern_5d = AICaseLearning._encode_volume_pattern(volumes, idx, 5)

        # 后续涨跌标签（如果有足够数据）
        AICaseLearning._calc_forward_labels(kline_data, idx, case)

        case.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return case

    @staticmethod
    def _encode_kline_pattern(kline_data, idx, n=5) -> str:
        """编码近N日K线形态：阴阳(Y/N)+实体大小(S/M/L)+上下影(U/D/N)"""
        if idx < n - 1:
            return ""
        codes = []
        for i in range(idx - n + 1, idx + 1):
            bar = kline_data[i]
            o = bar.get("open", 0)
            c = bar.get("close", 0)
            h = bar.get("high", 0)
            l = bar.get("low", 0)
            # 阴阳
            yin_yang = "Y" if c >= o else "N"
            # 实体大小
            body = abs(c - o)
            rng = (h - l) if (h - l) > 0 else 0.01
            body_ratio = body / rng
            if body_ratio < 0.3:
                size = "S"
            elif body_ratio < 0.6:
                size = "M"
            else:
                size = "L"
            # 影线
            upper = h - max(o, c)
            lower = min(o, c) - l
            if upper > body * 0.5 and lower > body * 0.5:
                shadow = "B"
            elif upper > body * 0.5:
                shadow = "U"
            elif lower > body * 0.5:
                shadow = "D"
            else:
                shadow = "N"
            codes.append(f"{yin_yang}{size}{shadow}")
        return "-".join(codes)

    @staticmethod
    def _encode_volume_pattern(volumes, idx, n=5) -> str:
        """编码近N日量能模式：递增(I)/递减(D)/波动(V)/平稳(F)"""
        if idx < n - 1:
            return ""
        vols = volumes[idx - n + 1:idx + 1]
        if np.any(vols <= 0):
            return ""
        # 归一化
        v_norm = vols / np.mean(vols)
        # 趋势
        x = np.arange(n)
        slope = np.polyfit(x, v_norm, 1)[0]
        std = np.std(v_norm)
        if slope > 0.05:
            trend = "I"  # 递增
        elif slope < -0.05:
            trend = "D"  # 递减
        elif std > 0.3:
            trend = "V"  # 波动
        else:
            trend = "F"  # 平稳
        # 最后一天量比
        last_ratio = v_norm[-1]
        if last_ratio > 1.5:
            level = "H"
        elif last_ratio < 0.7:
            level = "L"
        else:
            level = "M"
        return f"{trend}{level}"

    @staticmethod
    def _calc_forward_labels(kline_data, idx, case: CaseFeatures):
        """计算后续5/10/20日涨跌和最大回撤"""
        closes = [k.get("close", 0) for k in kline_data]
        highs = [k.get("high", 0) for k in kline_data]
        lows = [k.get("low", 0) for k in kline_data]
        entry = closes[idx] if idx < len(closes) else 0

        for period, ret_key, dd_key in [
            (5, "next_5d_return", "next_5d_max_drawdown"),
            (10, "next_10d_return", "next_10d_max_drawdown"),
            (20, "next_20d_return", "next_20d_max_drawdown"),
        ]:
            end_idx = min(idx + period, len(kline_data) - 1)
            if end_idx <= idx or entry <= 0:
                continue
            # 期末收益
            end_price = closes[end_idx]
            ret = (end_price - entry) / entry * 100
            setattr(case, ret_key, round(ret, 2))
            # 最大回撤（期间最低价相对入场价）
            period_lows = lows[idx + 1:end_idx + 1]
            if period_lows:
                min_low = min(period_lows)
                dd = (min_low - entry) / entry * 100
                setattr(case, dd_key, round(dd, 2))

        # 成功标签：后续5日涨幅>3%
        if case.next_5d_return > 3:
            case.is_success = 1

    # ============================================================
    # 案例自动生成
    # ============================================================

    def generate_cases_from_kline(
        self,
        stock_code: str,
        kline_data: List[Dict],
        annotations: List[Dict] = None,
        stock_name: str = "",
    ) -> List[CaseFeatures]:
        """
        从K线标注数据自动生成案例。
        如果没有标注数据，用MA交叉信号自动生成买卖点。
        """
        cases = []
        if not kline_data or len(kline_data) < 40:
            return cases

        # 如果有标注，用标注点
        if annotations:
            for ann in annotations:
                idx = ann.get("idx", ann.get("index", -1))
                if idx < 0:
                    continue
                case_type = ann.get("type", "buy")
                signal_type = ann.get("level", ann.get("signal_type", ""))
                feat = self.extract_features(
                    kline_data, idx, stock_code, stock_name,
                    case_type, signal_type, source="manual"
                )
                if feat:
                    cases.append(feat)
            return cases

        # 无标注时，用MA5/MA20交叉自动生成
        closes = np.array([k.get("close", 0) for k in kline_data], dtype=float)
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma20 = TechnicalIndicators.ma(closes, 20)

        for i in range(20, len(kline_data) - 20):
            if np.isnan(ma5[i]) or np.isnan(ma20[i]) or np.isnan(ma5[i-1]) or np.isnan(ma20[i-1]):
                continue
            # 金叉买入
            if ma5[i-1] <= ma20[i-1] and ma5[i] > ma20[i]:
                feat = self.extract_features(
                    kline_data, i, stock_code, stock_name,
                    "buy", "B2", source="auto"
                )
                if feat:
                    cases.append(feat)
            # 死叉卖出
            elif ma5[i-1] >= ma20[i-1] and ma5[i] < ma20[i]:
                feat = self.extract_features(
                    kline_data, i, stock_code, stock_name,
                    "sell", "S1", source="auto"
                )
                if feat:
                    cases.append(feat)

        return cases

    def generate_cases_from_backtest(
        self,
        backtest_trades: List[Dict],
        kline_data: List[Dict],
        stock_code: str = "",
        stock_name: str = "",
    ) -> List[CaseFeatures]:
        """从回测交易记录自动生成案例"""
        cases = []
        if not backtest_trades or not kline_data:
            return cases

        date_index = {}
        for i, k in enumerate(kline_data):
            d = str(k.get("date", ""))
            date_index[d] = i

        for trade in backtest_trades:
            sig_date = str(trade.get("signal_date", trade.get("date", "")))
            if sig_date not in date_index:
                continue
            idx = date_index[sig_date]
            case_type = trade.get("type", "buy")
            signal_type = trade.get("reason", trade.get("signal_type", ""))
            feat = self.extract_features(
                kline_data, idx, stock_code, stock_name,
                case_type, signal_type, source="backtest"
            )
            if feat:
                cases.append(feat)

        return cases

    # ============================================================
    # 相似案例匹配
    # ============================================================

    def find_similar_cases(
        self,
        current_features: CaseFeatures,
        top_n: int = 10,
        case_type: str = "buy",
    ) -> List[SimilarCaseResult]:
        """
        查找相似案例。

        Args:
            current_features: 当前股票特征
            top_n: 返回最相似的N个
            case_type: 匹配案例类型 buy/sell

        Returns:
            相似案例列表（按相似度降序）
        """
        if not self.conn:
            return []

        # 从数据库读取同类型案例
        rows = self.conn.execute("""
            SELECT id, stock_code, stock_name, case_date,
                   ma5, ma10, ma20, ma_alignment,
                   kdj_k, kdj_d, kdj_j, macd_dif, macd_dea, macd_hist, rps20,
                   volume_ratio, price_change_pct,
                   kline_pattern_5d, price_trend_10d, volume_pattern_5d,
                   next_5d_return, next_10d_return, next_20d_return,
                   next_5d_max_drawdown, is_success, feature_weight
            FROM ai_case_library
            WHERE case_type = ?
        """, (case_type,)).fetchall()

        if not rows:
            return []

        results = []
        for row in rows:
            (cid, scode, sname, sdate,
             ma5, ma10, ma20, ma_align,
             kdj_k, kdj_d, kdj_j, macd_dif, macd_dea, macd_hist, rps20,
             vol_ratio, pct_chg,
             kline_pat, price_trend, vol_pat,
             ret5, ret10, ret20, dd5, is_success, fweight) = row

            # 计算各维度相似度
            morph_sim = self._morphology_similarity(current_features, {
                "ma_alignment": ma_align,
                "kline_pattern_5d": kline_pat or "",
                "price_trend_10d": price_trend or 0,
                "ma5": ma5 or 0, "ma10": ma10 or 0, "ma20": ma20 or 0,
                "price_change_pct": pct_chg or 0,
            })
            vol_sim = self._volume_similarity(current_features, {
                "volume_ratio": vol_ratio or 0,
                "volume_pattern_5d": vol_pat or "",
            })
            ind_sim = self._indicator_similarity(current_features, {
                "kdj_k": kdj_k or 50, "kdj_d": kdj_d or 50, "kdj_j": kdj_j or 50,
                "macd_dif": macd_dif or 0, "macd_dea": macd_dea or 0,
                "macd_hist": macd_hist or 0, "rps20": rps20 or 50,
            })

            total_sim = (
                morph_sim * self.W_MORPHOLOGY
                + vol_sim * self.W_VOLUME
                + ind_sim * self.W_INDICATOR
            )

            # 应用案例权重
            total_sim *= (fweight or 1.0)

            results.append(SimilarCaseResult(
                case_id=cid,
                stock_code=scode or "",
                stock_name=sname or "",
                case_date=sdate or "",
                similarity=round(total_sim, 4),
                morphology_sim=round(morph_sim, 4),
                volume_sim=round(vol_sim, 4),
                indicator_sim=round(ind_sim, 4),
                next_5d_return=ret5 or 0,
                next_10d_return=ret10 or 0,
                next_20d_return=ret20 or 0,
                is_success=is_success or 0,
            ))

        # 按相似度降序，取Top N
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_n]

    def calculate_similarity(self, f1: CaseFeatures, f2: CaseFeatures) -> float:
        """计算两个案例的总相似度"""
        morph = self._morphology_similarity(f1, f2.to_dict())
        vol = self._volume_similarity(f1, f2.to_dict())
        ind = self._indicator_similarity(f1, f2.to_dict())
        return morph * self.W_MORPHOLOGY + vol * self.W_VOLUME + ind * self.W_INDICATOR

    # ---- 形态相似度（40%）----
    def _morphology_similarity(self, cur: CaseFeatures, other: Dict) -> float:
        """
        形态相似度：
          - 均线排列匹配（0.3权重）
          - 5日K线形态编码匹配（0.4权重）
          - 10日价格趋势接近度（0.2权重）
          - 当日涨跌幅接近度（0.1权重）
        """
        score = 0.0

        # 均线排列
        if cur.ma_alignment and other.get("ma_alignment"):
            if cur.ma_alignment == other["ma_alignment"]:
                score += 0.3
            elif (cur.ma_alignment in ["多头", "粘合"] and other["ma_alignment"] in ["多头", "粘合"]):
                score += 0.15

        # K线形态编码匹配（逐位比较）
        cur_pat = cur.kline_pattern_5d or ""
        other_pat = other.get("kline_pattern_5d", "") or ""
        if cur_pat and other_pat:
            cur_codes = cur_pat.split("-")
            other_codes = other_pat.split("-")
            n = min(len(cur_codes), len(other_codes))
            if n > 0:
                match = sum(1 for i in range(n) if cur_codes[i] == other_codes[i])
                score += 0.4 * (match / n)

        # 10日价格趋势接近度
        cur_trend = cur.price_trend_10d
        other_trend = other.get("price_trend_10d", 0)
        if cur_trend != 0 or other_trend != 0:
            diff = abs(cur_trend - other_trend)
            score += 0.2 * max(0, 1 - diff / 5)  # 差异5%以上为0

        # 当日涨跌幅接近度
        cur_pct = cur.price_change_pct
        other_pct = other.get("price_change_pct", 0)
        diff_pct = abs(cur_pct - other_pct)
        score += 0.1 * max(0, 1 - diff_pct / 10)

        return min(1.0, score)

    # ---- 量价相似度（30%）----
    def _volume_similarity(self, cur: CaseFeatures, other: Dict) -> float:
        """
        量价相似度：
          - 量比接近度（0.5权重）
          - 5日量能模式匹配（0.5权重）
        """
        score = 0.0

        # 量比接近度
        cur_vr = cur.volume_ratio
        other_vr = other.get("volume_ratio", 0)
        if cur_vr > 0 and other_vr > 0:
            ratio = min(cur_vr, other_vr) / max(cur_vr, other_vr)
            score += 0.5 * ratio

        # 量能模式匹配
        cur_vp = cur.volume_pattern_5d or ""
        other_vp = other.get("volume_pattern_5d", "") or ""
        if cur_vp and other_vp:
            if cur_vp == other_vp:
                score += 0.5
            elif cur_vp[0] == other_vp[0]:  # 趋势相同
                score += 0.25

        return min(1.0, score)

    # ---- 指标相似度（30%）----
    def _indicator_similarity(self, cur: CaseFeatures, other: Dict) -> float:
        """
        指标相似度：
          - KDJ接近度（0.4权重）
          - MACD接近度（0.3权重）
          - RPS接近度（0.3权重）
        """
        score = 0.0

        # KDJ（K/D/J综合）
        kdj_diff = (
            abs(cur.kdj_k - other.get("kdj_k", 50)) +
            abs(cur.kdj_d - other.get("kdj_d", 50)) +
            abs(cur.kdj_j - other.get("kdj_j", 50))
        ) / 3
        score += 0.4 * max(0, 1 - kdj_diff / 50)

        # MACD（DIF/DEA/HIST综合，归一化）
        macd_diff = (
            abs(cur.macd_dif - other.get("macd_dif", 0)) +
            abs(cur.macd_dea - other.get("macd_dea", 0)) +
            abs(cur.macd_hist - other.get("macd_hist", 0))
        )
        # MACD值范围较大，用相对差异
        macd_norm = abs(cur.macd_dif) + abs(cur.macd_dea) + abs(cur.macd_hist) + 0.01
        score += 0.3 * max(0, 1 - macd_diff / (macd_norm * 2))

        # RPS
        rps_diff = abs(cur.rps20 - other.get("rps20", 50))
        score += 0.3 * max(0, 1 - rps_diff / 50)

        return min(1.0, score)

    # ============================================================
    # 案例统计
    # ============================================================

    def get_case_statistics(self, similar_cases: List[SimilarCaseResult] = None) -> CaseStatistics:
        """
        统计相似案例表现。
        如果传入similar_cases，统计这些案例；否则统计全库。
        """
        stats = CaseStatistics()

        if similar_cases:
            stats.similar_count = len(similar_cases)
            if not similar_cases:
                return stats
            rets5 = [c.next_5d_return for c in similar_cases]
            rets10 = [c.next_10d_return for c in similar_cases]
            rets20 = [c.next_20d_return for c in similar_cases]
            successes = [c.is_success for c in similar_cases]
            stats.total_cases = len(similar_cases)
            stats.success_rate = sum(successes) / len(successes) * 100 if successes else 0
            stats.avg_5d_return = float(np.mean(rets5)) if rets5 else 0
            stats.avg_10d_return = float(np.mean(rets10)) if rets10 else 0
            stats.avg_20d_return = float(np.mean(rets20)) if rets20 else 0
            return stats

        # 全库统计
        if not self.conn:
            return stats

        row = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN case_type='buy' THEN 1 ELSE 0 END) as buy_cnt,
                SUM(CASE WHEN case_type='sell' THEN 1 ELSE 0 END) as sell_cnt,
                AVG(CASE WHEN is_success=1 THEN 1.0 ELSE 0.0 END) * 100 as success_rate,
                AVG(next_5d_return) as avg5,
                AVG(next_10d_return) as avg10,
                AVG(next_20d_return) as avg20,
                AVG(next_5d_max_drawdown) as dd5,
                AVG(next_10d_max_drawdown) as dd10,
                AVG(next_20d_max_drawdown) as dd20
            FROM ai_case_library
        """).fetchone()

        if row:
            stats.total_cases = row[0] or 0
            stats.buy_cases = row[1] or 0
            stats.sell_cases = row[2] or 0
            stats.success_rate = row[3] or 0
            stats.avg_5d_return = row[4] or 0
            stats.avg_10d_return = row[5] or 0
            stats.avg_20d_return = row[6] or 0
            stats.avg_5d_drawdown = row[7] or 0
            stats.avg_10d_drawdown = row[8] or 0
            stats.avg_20d_drawdown = row[9] or 0

        # 信号类型分布
        if self.conn:
            rows = self.conn.execute("""
                SELECT signal_type, COUNT(*) FROM ai_case_library
                WHERE signal_type != '' GROUP BY signal_type ORDER BY COUNT(*) DESC
            """).fetchall()
            stats.signal_type_dist = {r[0]: r[1] for r in rows}

        return stats

    def get_library_stats(self) -> CaseStatistics:
        """获取案例库整体统计"""
        return self.get_case_statistics(None)

    # ============================================================
    # 权重优化
    # ============================================================

    def update_weights(self, case_id: int, actual_result: float):
        """
        根据实际结果更新案例特征权重。

        actual_result > 0: 成功案例，增加权重
        actual_result <= 0: 失败案例，降低权重
        """
        if not self.conn:
            return
        # 获取当前权重
        row = self.conn.execute(
            "SELECT feature_weight FROM ai_case_library WHERE id = ?", (case_id,)
        ).fetchone()
        if not row:
            return
        current = row[0] or 1.0
        # 调整：成功+0.1，失败-0.1，范围[0.5, 1.5]
        if actual_result > 0:
            new_weight = min(1.5, current + 0.1)
        else:
            new_weight = max(0.5, current - 0.1)
        self.conn.execute(
            "UPDATE ai_case_library SET feature_weight = ? WHERE id = ?",
            (new_weight, case_id)
        )

    # ============================================================
    # 便捷方法
    # ============================================================

    def get_all_cases(self, case_type: str = None, limit: int = 1000) -> List[Dict]:
        """获取所有案例（用于调试）"""
        if not self.conn:
            return []
        if case_type:
            rows = self.conn.execute(
                "SELECT * FROM ai_case_library WHERE case_type = ? ORDER BY case_date DESC LIMIT ?",
                (case_type, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM ai_case_library ORDER BY case_date DESC LIMIT ?", (limit,)
            ).fetchall()
        # 获取列名
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def clear_library(self):
        """清空案例库（谨慎使用）"""
        if self.conn:
            self.conn.execute("DELETE FROM ai_case_library")


# ============================================================
# 单例
# ============================================================

_default_learner = None


def get_ai_case_learner(**kwargs) -> AICaseLearning:
    """获取AI案例学习引擎单例"""
    global _default_learner
    if _default_learner is None:
        _default_learner = AICaseLearning(**kwargs)
    return _default_learner
