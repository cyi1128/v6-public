# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.1 - 公共基础模块
包含：技术指标计算、K线数据解析、成交量分析、常量定义
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


def _clamp100(v, lo=0.0, hi=100.0):
    """把评分夹到 [lo, hi]；NaN 一律返回 lo。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return lo
    if v != v:
        return lo
    return max(lo, min(hi, v))

# ============================================================
# 常量定义
# ============================================================

# ---- V20 建仓阶段专门因子阈值（2026-10-10）----
# 实测标定见 tools\build_factor_calibration.txt；改「是否满足」门槛前先重跑标定。
BUILD_STACK_RATIO_LO = 1.15     # 底部堆量：近10日均量 / 紧邻前20日均量 的下限
BUILD_STACK_RATIO_HI = 3.50     # 上限（超过视为单日爆量/异动，不算「堆量」）
BUILD_STACK_POS_MAX = 0.45      # 底部堆量：近120日位置必须 < 该值
BUILD_STACK_CONT_MIN = 0.50     # 底部堆量：近10日内量>基准均量的天数占比下限
BUILD_HIT_STACK = 70.0          # 堆量分 >= 该值 -> 报「疑似底部堆量」
BUILD_REDFAT_RATIO = 1.30       # 红肥绿瘦：上涨日均量 / 下跌日均量 的下限
BUILD_HIT_REDFAT = 65.0         # 红肥绿瘦分 >= 该值 -> 报「红肥绿瘦建仓特征」

# ---- C4 观察规则阈值（2026-10-10）----
# 「低位 + 上涨放量 + 下跌缩量 + 适中振幅 + 控盘分」五条 AND。
# 实测（tools\buildfactor_wide.csv：17570 条滚动观测 / 4401 只 / 锚点 k=20/40/60/80，
# 每个锚点只喂截断到 T 的 120 根，严格无未来数据）：
#   命中口径 pos<0.25 & up>1.15 & dn<0.95 & amp∈[2.5%,5.5%] & ctrl>=85
#     -> n=219  未来20日 +1.57%  胜率 59.4%  t=+1.98
#   ctrl>=80 的口径同向略强 -> n=300  +1.82%  胜率 61.0%  t=+2.81
#   （门槛取 85 是为了与全项目唯一的「高度控盘线」_CTRL_HIGH 对齐，改 80 只需改这一行。）
# 【重要】该组合【未通过逐锚点检验】：同锚点增量 k20 +0.21 ｜ k40 样本不足 ｜
#   k60 +5.01 ｜ k80 -3.14 —— 汇总为正主要来自样本集中在 k60（锚点构成偏差）。
#   同时「上涨放量+下跌缩量」单独用是 -1.66%（t=-6.31，n=2821），是负向条件。
#   因此 C4 只能当【观察】用，禁止参与 signal_level / 建仓价 / 排序。
#   去掉量价结构、只留 pos<0.25 & amp∈[2.5%,5.5%] 才是统计上更结实的口径
#   （n=7749 r20=+0.66% t=+5.24），但那是另一个组合，改动前先与用户确认。
C4_POS_MAX = 0.25       # 近120根收盘位置上限
C4_UP_MIN = 1.15        # 上涨日量比下限（上涨日均量 / 窗口均量，近20根）
C4_DN_MAX = 0.95        # 下跌日量比上限
C4_AMP_LO = 0.025       # 20日均振幅下限 (high-low)/close
C4_AMP_HI = 0.055       # 20日均振幅上限
C4_CTRL_MIN = 85.0      # 控盘分下限（与 band_pattern_engine._CTRL_HIGH 对齐）
C4_MIN_BARS = 120       # 位置/振幅/量比窗口要求的最少K线根数（不足直接判不可用）

# ---- C6 观察规则阈值（2026-10-10）----
# 「低位 + 适中振幅」两条 AND —— 就是 C4 去掉量价结构那两条之后的子集。
# 实测（tools\buildfactor_wide.csv：17570 条滚动观测 / 4401 只；复现脚本 tools\_c6_calib.py）：
#   全样本基准        n=17570  r20=-0.80%  胜率 45.2%
#   仅低位 pos<0.25   n=10598  r20=+0.43%  胜率 49.5%  t=+3.73
#   仅适中振幅        n=10982  r20=+0.28%  胜率 49.2%  t=+2.63
#   ★ C6 两条叠加    n= 7749  r20=+0.66%  胜率 52.0%  t=+5.24  中位=+0.62%
#   （叠加后 > 两个分量的单独表现，说明两条不是重复计同一件事）
#   12 个「位置×振幅」阈值档位全部同向为正（+0.49% ~ +0.83%，t 4.1~6.0），
#   不是靠单一阈值凑出来的 —— 这一点比 C4 结实（C4 只有 219 条样本、t=+1.98）。
# 【重要】但逐锚点增量检验同样【未通过】：k20 -0.41 ｜ k40 -0.07 ｜ k60 +6.43 ｜ k80 -1.33
#   —— 4 个锚点里 3 个约为 0 或为负，正贡献几乎全部来自 k60（等权后增量 +1.15pp）。
#   所以 C6 和 C4 一样只能当【观察】用，禁止参与 signal_level / 建仓价 / 排序 / 等级。
# 反向证据（用来判断方向是否可信，不是巧合）：
#   低位 + 过低振幅(<2%)   n=254  r20=-0.76%  胜率 33.5%   <- 「死票」明显负
#   低位 + 过高振幅(>7%)   n=554  r20=+0.80%  胜率 44.8%   <- 靠少数暴涨拉起来，中位 -1.25%
#   低位区内振幅分档呈帐篷形：[3.5%,4.5%) 最好(+1.12%/54.6%)，两侧递减。
C6_POS_MAX = 0.25       # 近120根收盘位置上限（与 C4 同口径，勿单独改）
C6_AMP_LO = 0.025       # 20日均振幅下限 (high-low)/close
C6_AMP_HI = 0.055       # 20日均振幅上限
C6_MIN_BARS = 120       # 位置/振幅窗口要求的最少K线根数（不足直接判不可用）

# ---- 试盘识别（观察规则）阈值（2026-10-10）----
# 「主力测试抛压」的量化近似：放量冲高收长上影 -> 随后缩量回调/横盘不破。
# 实盘标定见 tools\\probe_dist_calib.txt（tools\\_calib_probe_dist.py 生成）。
# 只做【观察】不进 signal_level / 建仓价 / 排序；依据见函数 docstring。
PROBE_LOOKBACK = 11      # 在最近这么多根里找「试盘日」（不含最后一根时才算确认过）
PROBE_POS_MAX = 0.35     # 位置上限：只保留低位有效子集（滚动观测里 pos>=0.35 的试盘为负期望）
                         # 标定 tools\probe_dist_calib.txt：pos<0.35 +2.02%/55.0%/t=+3.41；pos∈[0.55,0.75) -5.87%
                         # 高位长上影归「出货形态」，不按试盘计
PROBE_SHADOW_MIN = 0.50  # 上影线占当日全幅 (high-low) 的比例下限
PROBE_SPIKE_MIN = 0.05   # 冲高幅度下限：(当日最高 - 昨收) / 昨收
PROBE_VOL_MIN = 1.20     # 试盘日量比下限：当日量 / 前5日均量
PROBE_AFTER_SHRINK = 0.80  # 试盘后均量 / 试盘日量 的上限（缩量）
PROBE_HOLD_TOL = 0.03    # 试盘后允许跌破试盘日低点的容忍度
PROBE_SCORE_OK = 70.0    # ok=True 时的最低分（分数两段不重叠：ok>=70，未通过<=60）
PROBE_MIN_BARS = 60      # 最少K线根数

# ---- 出货形态确认（观察规则）阈值（2026-10-10）----
# 在「高位 + stage_guess=distribute」之上加形态级确认，用来降低误报。
# 三种形态：① 高位放量滞涨 ② 高位破位 ③ 双顶雏形。只做【观察】。
DIST_POS_HIGH = 0.65     # ① 高位口径（近120根收盘位置）
DIST_NEWHIGH_TOL = 0.98  # ① 当日最高 >= 近60日最高 x 该值 = 创新高/接近前高
DIST_STALL_CLOSE_WEAK = 0.45  # ① 收盘位于当日振幅的位置上限（<= 视为收弱）
DIST_STALL_VOL = 1.80    # ① 量比下限（当日量 / 前5日均量）
DIST_POS_BREAK = 0.40    # ② 破位口径的位置下限
DIST_PLATFORM_AMP = 0.18  # ② 平台振幅上限（近20根不含当日）
DIST_BREAK_VOL = 1.50    # ② 破位当日量比下限
DIST_DT_WINDOW = 40      # ③ 双顶搜索窗口
DIST_DT_GAP = 6          # ③ 两个高点最小间隔（根）
DIST_DT_BACK = 12        # ③ 第二个高点必须落在最近这么多根内
DIST_DT_DIFF = 0.03      # ③ 两个高点接近程度 |h2-h1|/h1 上限
DIST_DT_DIP = 0.06       # ③ 中间回撤幅度下限（相对两顶较低者）
DIST_DT_VOLFADE = 0.90   # ③ 二次冲高量能 / 一次冲高量能 的上限（力度减弱）
DIST_DT_POS_MIN = 0.55   # ③ 双顶的位置下限
DIST_SCORE_OK = 70.0     # 同 PROBE_SCORE_OK：ok>=70，未通过<=60
DIST_MIN_BARS = 60       # 最少K线根数
# ---- 拉升阶段识别（观察规则）阈值（2026-10-11）----
# 识别「主力已经进入拉升阶段」的三种可量化形态（与试盘/出货形态同族，只做【观察】）：
#   ① 阶梯式上行（趋势型拉升）：均线多头排列 + 整体抬升 + 上涨放量/回调缩量 + 回调不破 MA20
#   ② 缩量强势（锁仓式拉升）：连续收阳/低点抬高 + 量能反而萎缩或维持低位 + 位置偏高
#   ③ 加速迹象（末段急拉）  ：短窗口涨幅大 + 量能放大 + 接近或创阶段新高
# ⚠ 方向说明（别用反）：C4 / C6 / 试盘找的是「低位、启动前」；本函数找的是「已经拉起来」。
#   在本项目「买在启动前、不接飞刀」的框架下，它是【追高提示 / 排他标记】，不是买入提示。
# 标定见 tools\markup_calib.txt（tools\_calib_markup.py 生成；锚点 k=20/40/60/80，无未来数据）。
MARKUP_MA_FAST = 5          # ① 均线多头排列：MA5 > MA10 > MA20
MARKUP_MA_MID = 10
MARKUP_MA_SLOW = 20
MARKUP_TREND_WIN = 10       # ① 近 10 根做「整体抬升 / 上涨放量回调缩量 / 不破 MA20」判定
MARKUP_TREND_GAIN = 0.06    # ① 近窗口累计涨幅下限（收盘口径）
MARKUP_HOLD_WIN = 5         # ① 「回调不破均线」只看最近 5 根（发动那根不算回调）
MARKUP_PULLBACK_TOL = 0.03  # ① 回调容忍度：最近 MARKUP_HOLD_WIN 根最低价 >= MA20 x (1-该值)
MARKUP_UP_DN_VOL = 1.00     # ① 上涨日均量 / 下跌日均量 下限
MARKUP_LOCK_WIN = 8         # ② 锁仓式窗口
MARKUP_LOCK_YANG_MIN = 0.60  # ② 阳线占比下限（连续收阳/稳步抬升）
MARKUP_LOCK_VOL_MAX = 1.00  # ② 近窗口均量 / 更早窗口均量 上限（萎缩或维持低位）
MARKUP_LOCK_POS_MIN = 0.00  # ② 位置下限：2026-10-11 由 0.55 改为 0.00（依据 tools\markup2_pos_calib.txt）
                                #   原值 0.55 把 ② 锁在唯一为负的区间：pos∈[0.55,0.75) -2.83%/t=-2.89；
                                #   放开下限后 pos<0.35 = +2.36%/胜率58.1%/t=+11.66、[0.35,0.45) +1.48%/t=+2.18。
                                #   全局门槛 MARKUP_POS_MAX=0.45 仍在，故 ② 只在 pos<0.45（正期望区）生效。
MARKUP_ACC_WIN = 5          # ③ 加速窗口
MARKUP_ACC_GAIN = 0.12      # ③ 近窗口累计涨幅下限
MARKUP_ACC_VOL = 1.30       # ③ 近窗口均量 / 前窗口均量 下限（量能放大）
MARKUP_ACC_HI_TOL = 0.98    # ③ 收盘 >= 近60日最高 x 该值 = 接近/创阶段新高
MARKUP_SCORE_OK = 70.0      # 同 PROBE_SCORE_OK：ok=True 必 >=70，未通过必 <=60
MARKUP_MIN_BARS = 60        # 最少K线根数
MARKUP_POS_MAX = 0.45       # 位置门槛（1010m 新增）：只保留 pos120 < 0.45 的低位子集

# ------------------------------------------------------------------
# 破位—收复 双向判据（BRK_*，2026-10-11 A 项新增）
# 出处：主力手法里「洗盘 vs 出货」的分水岭 ——
#   破位【缩量】后 N 根内快速收回支撑位、且收回那天放量  -> 洗盘
#   破位【放量】且始终收不回                              -> 出货
# 只用 open/high/low/close/volume，全部取「当日及之前」的窗口，无未来数据。
# 位置上限 BRK_POS_LOW：高位破位交给出货形态（detect_distribution_pattern）判，
# 避免两个因子在同一位置区间重复报警。
# ------------------------------------------------------------------
BRK_LOOKBACK = 12         # 在最近这么多根里找「破位日」
BRK_SUPPORT_WIN = 20      # 支撑位 = 破位日之前 20 根的最低价最小值
BRK_RECOVER_WIN = 5       # 破位后最多 5 根内要收回支撑位
BRK_SHRINK_MAX = 1.00     # 破位日「缩量」上限：当日量 / 前5日均量 <= 该值
BRK_EXPAND_MIN = 1.50     # 破位日「放量」下限：当日量 / 前5日均量 >= 该值
BRK_RECOVER_VOL = 1.20    # 收回日「放量」下限：当日量 / 前5日均量 >= 该值
BRK_POS_LOW = 0.55        # 位置上限（>= 该值不判，交给出货形态）
BRK_SCORE_OK = 70.0       # 同 PROBE_SCORE_OK：ok=True 必 >=70，未通过必 <=60
BRK_MIN_BARS = 60         # 最少K线根数

# ------------------------------------------------------------------
# 量能分位 / 缩量上涨（VR_*，2026-10-11 B 项新增）
# 出处：材料里的「地量见地价、天量见顶」「缩量上涨 = 高度控盘」。
# 现有口径只有「对前 5 日均量」的短口径，这里补长周期分位。
# 分位只用「当日及之前 VR_WIN 根」，不含未来。
# ------------------------------------------------------------------
VR_WIN = 60               # 分位窗口
VR_LOW_PCT = 20.0         # 地量：分位 <= 该值
VR_HIGH_PCT = 80.0        # 天量：分位 >= 该值
VR_SU_WIN = 5             # 「缩量上涨」窗口
VR_SU_VOL_MAX = 0.90      # 窗口内阳线均量 / 窗口前5日均量 的上限
VR_SU_GAIN_MIN = 0.03     # 窗口累计涨幅下限
VR_SU_YANG_MIN = 0.60     # 窗口阳线占比下限
VR_SCORE_OK = 70.0        # ok=True 必 >=70，未通过必 <=60
VR_MIN_BARS = 60          # 最少K线根数
                            # 依据 tools\markup_calib.txt（17516 条滚动观测 / 无未来数据）：
                            #   pos < 0.45      n=1250  +1.10% / 胜率54.3% / t=+3.31  <- 唯一正期望档
                            #   pos 0.45~0.60   n=266   -2.79% / t=-3.90
                            #   pos 0.60~0.75   n=211   -4.25% / t=-4.48
                            #   pos >= 0.75     n=384   -3.32% / t=-3.30
                            #   全部命中的均值相对基准只有 +0.06pp（=噪音），高分档更差（score>=90 为 -4.18%）
                            # 边界口径：0.45 归入负期望档 [0.45,0.60)，所以写 pos >= MARKUP_POS_MAX 即拦。
                            # ⚠ 连带后果：形态②缩量强势自带 pos >= MARKUP_LOCK_POS_MIN(0.55)，
                            #   被本门槛完全覆盖后【不可达】——②在现参数下不会再产生命中。
                            #   常量保留，回退门槛（改 1.01）即可恢复。

MODEL_LIMIT_PULLBACK = "涨停回调"
MODEL_BOX_BREAKOUT = "箱体突破"
MODEL_VOLUME_BREAKOUT = "量价突破"

# 阶段标签
STAGE_LAUNCH = "强势启动"
STAGE_PULLBACK = "回调整理"
STAGE_SHRINK = "缩量洗盘"
STAGE_SUPPORT = "关键支撑"
STAGE_RELAUNCH = "再次启动"
STAGE_PLATFORM = "平台蓄势"
STAGE_BREAKOUT = "突破区域"
STAGE_CONFIRM = "回踩确认"
STAGE_BOTTOM = "极限缩量筑底"
STAGE_VOL_PRICE_UP = "量价齐升"

# 区域颜色（K线标注）
REGION_SHRINK = "shrink"       # 绿色：缩量区域
REGION_BOX = "box"             # 黄色：箱体区域
REGION_BREAKOUT = "breakout"   # 红色：突破区域
REGION_CONFIRM = "confirm"     # 蓝色：回踩确认区域
REGION_ACCUMULATION = "accumulation"  # 紫色：主力吸筹区域
REGION_RISK = "risk"           # 橙色：风险区域

REGION_COLORS = {
    'shrink': '#22c55e',
    'box': '#eab308',
    'breakout': '#ef4444',
    'confirm': '#3b82f6',
    'accumulation': '#a855f7',
    'risk': '#f97316',
}

REGION_NAMES = {
    'shrink': '缩量区域',
    'box': '箱体区域',
    'breakout': '突破区域',
    'confirm': '回踩确认区域',
    'accumulation': '主力吸筹',
    'risk': '风险区域',
}

# 技术指标参数
KDJ_N = 13
KDJ_M1 = 3
KDJ_M2 = 3
MACD_FAST = 8
MACD_SLOW = 21
MACD_SIGNAL = 5

# 扫描参数
MIN_KLINE_COUNT = 20  # V1.1.1放宽：从40降到20，数据不足也尝试分析
LIMIT_UP_THRESHOLD = 9.5  # V1.1.1：从9.8降到9.5，统一阈值不区分板块
BIG_YANG_THRESHOLD = 5.0
STRONG_RISE_THRESHOLD = 10.0  # V1.1新增：近期涨幅超10%也算强势启动
DEFAULT_SCAN_COUNT = 120

# 买点等级
BUY_B1 = "B1观察"
BUY_B2 = "B2确认"
BUY_B3 = "B3强势"
SELL_S1 = "S1破MA5"
SELL_S2 = "S2破箱体"
SELL_S3 = "S3滞涨"
SELL_S4 = "S4突破失败"

# 评分等级（V1.1调整）
SCORE_LAUNCH_CANDIDATE = "启动候选"    # 90-100
SCORE_STRONG_CANDIDATE = "强势候选"    # 80-90
SCORE_KEY_WATCH = "重点观察"            # 70-80
SCORE_WATCH = "观察池"                  # 60-70
SCORE_LOW = "低关注"                    # 60以下


# ============================================================
# 数据结构
# ============================================================

@dataclass
class KlineBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0
    pct_chg: float = 0.0


@dataclass
class ModelMatch:
    model_name: str
    matched: bool
    stage: str
    score: float = 0.0  # V1.1新增：模型独立评分
    signals: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    support: float = 0.0  # V1.1新增：支撑位
    pressure: float = 0.0  # V1.1新增：压力位
    detail: Dict = field(default_factory=dict)


@dataclass
class AIScore:
    total: float = 0.0
    main_force_structure: float = 0.0
    volume_price: float = 0.0
    trend_ma: float = 0.0
    limit_up_gene: float = 0.0
    tech_indicator: float = 0.0
    market_env: float = 0.0
    level: str = SCORE_LOW
    breakdown: Dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class BuySellSignal:
    buy_level: str = ""  # B1/B2/B3
    sell_level: str = ""  # S1/S2/S3/S4
    buy_reasons: List[str] = field(default_factory=list)
    sell_reasons: List[str] = field(default_factory=list)
    risk_level: str = "低"  # 低/中/高


@dataclass
class KlineAnnotation:
    regions: List[Dict] = field(default_factory=list)
    markers: List[Dict] = field(default_factory=list)
    model_labels: List[Dict] = field(default_factory=list)


@dataclass
class StockScanResult:
    code: str
    name: str
    price: float
    pct_chg: float
    industry: str
    matched_models: List[ModelMatch] = field(default_factory=list)
    best_model: str = ""  # V1.1新增：最高分模型
    best_model_score: float = 0.0
    current_stage: str = ""
    buy_signal: BuySellSignal = field(default_factory=BuySellSignal)
    risk_warnings: List[str] = field(default_factory=list)
    support: float = 0.0
    pressure: float = 0.0
    score: AIScore = field(default_factory=AIScore)
    annotation: KlineAnnotation = field(default_factory=KlineAnnotation)
    kline_data: Dict = field(default_factory=dict)
    scan_time: str = ""
    funnel_stage: str = ""  # V1.1新增：漏斗阶段标记

    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return {
            "code": self.code, "name": self.name, "price": self.price,
            "pct_chg": self.pct_chg, "industry": self.industry,
            "matched_models": [asdict(m) for m in self.matched_models],
            "best_model": self.best_model, "best_model_score": self.best_model_score,
            "current_stage": self.current_stage,
            "buy_signal": asdict(self.buy_signal),
            "risk_warnings": self.risk_warnings,
            "support": self.support, "pressure": self.pressure,
            "score": asdict(self.score), "annotation": asdict(self.annotation),
            "scan_time": self.scan_time, "funnel_stage": self.funnel_stage,
        }


# ============================================================
# 技术指标计算
# ============================================================

class TechnicalIndicators:
    @staticmethod
    def ma(closes: np.ndarray, period: int) -> np.ndarray:
        if len(closes) < period:
            return np.full(len(closes), np.nan)
        result = np.full(len(closes), np.nan)
        for i in range(period - 1, len(closes)):
            result[i] = np.mean(closes[i - period + 1:i + 1])
        return result

    @staticmethod
    def kdj(highs, lows, closes, n=KDJ_N, m1=KDJ_M1, m2=KDJ_M2):
        length = len(closes)
        if length < n:
            return (np.full(length, np.nan),) * 3
        rsv = np.full(length, np.nan)
        for i in range(n - 1, length):
            hh = np.max(highs[i - n + 1:i + 1])
            ll = np.min(lows[i - n + 1:i + 1])
            rsv[i] = (closes[i] - ll) / (hh - ll) * 100 if hh != ll else 50.0
        k = d = j = np.full(length, np.nan)
        kv = dv = 50.0
        for i in range(length):
            if np.isnan(rsv[i]):
                continue
            kv = (m1 - 1) / m1 * kv + 1 / m1 * rsv[i]
            dv = (m2 - 1) / m2 * dv + 1 / m2 * kv
            k[i] = kv; d[i] = dv; j[i] = 3 * kv - 2 * dv
        return k, d, j

    @staticmethod
    def macd(closes, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
        length = len(closes)
        if length < slow:
            return (np.full(length, np.nan),) * 3
        def ema(data, period):
            result = np.full(len(data), np.nan)
            if len(data) < period:
                return result
            mult = 2 / (period + 1)
            result[period - 1] = np.mean(data[:period])
            for i in range(period, len(data)):
                result[i] = (data[i] - result[i - 1]) * mult + result[i - 1]
            return result
        ef = ema(closes, fast)
        es = ema(closes, slow)
        dif = ef - es
        dea = np.full(length, np.nan)
        valid = dif[~np.isnan(dif)]
        if len(valid) >= signal:
            si = np.where(~np.isnan(dif))[0][0]
            mult = 2 / (signal + 1)
            dea[si + signal - 1] = np.mean(valid[:signal])
            for i in range(si + signal, length):
                if np.isnan(dif[i]):
                    continue
                dea[i] = (dif[i] - dea[i - 1]) * mult + dea[i - 1]
        return dif, dea, 2 * (dif - dea)

    @staticmethod
    def is_kdj_golden(k, d, idx=-1):
        if idx < 0:
            idx = len(k) - 1
        if idx < 1 or np.isnan(k[idx]) or np.isnan(k[idx - 1]):
            return False
        return k[idx - 1] <= d[idx - 1] and k[idx] > d[idx]

    @staticmethod
    def is_macd_golden(dif, dea, idx=-1):
        if idx < 0:
            idx = len(dif) - 1
        if idx < 1 or np.isnan(dif[idx]) or np.isnan(dif[idx - 1]):
            return False
        return dif[idx - 1] <= dea[idx - 1] and dif[idx] > dea[idx]


    @staticmethod
    def estimate_control_score(df, window=20):
        """估算控盘评分 0~100，越高越可能高度控盘。

        纯技术指标：换手中枢 + 量价配合 + 振幅收敛 + 位置加权。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low / volume；若含 turnover 列则优先用真实换手率。
        window : int
            换手中枢与量价配合的观察窗口，默认 20。

        返回
        ----
        float : 0.0 ~ 100.0；df 为空、长度不足 60 或字段缺失时返回 0.0。

        实现说明（相对初稿的三处必要修正，均经 591 只主板实测）
        --------------------------------------------------------
        1. 无 turnover 列时，量能中枢取【整段 df】的近 window 日均量 / 近 60 日均量。
           初稿写的是 df.tail(20)['volume'].rolling(60) —— 在 20 行切片上 rolling(60)
           恒为 NaN，导致占 40% 权重的换手分量永远等于 0；实测 591 只主板
           分数被压在 [28.79, 65.95]，理论上限 67.8，使得「>=70」「>=75」
           两条规则数学上不可能触发。
        2. 量价配合中「下跌放量」记为 -15 分。初稿为 +15 分，既与本函数
           第 3 条判据（下跌缩量才加分）自相矛盾，也与引擎既定的
           「上涨日放量 / 下跌日缩量」口径相反。
        3. 所有中间量做 NaN / 除零 / 缺列防护。
        4. C5（2026-10-10）：振幅分量原为「100 - amp*300」，即振幅越低分越高；
           实测方向是反的（低位区 amp<2.5% 未来20日收益为负、胜率仅 29~41%，
           峰值在 amp≈3.75~4.5%）。已改为峰值 4.0% 的帐篷函数。
        """
        try:
            if df is None or len(df) < 60:
                return 0.0
            for c in ('close', 'high', 'low', 'volume'):
                if c not in df.columns:
                    return 0.0
            recent = df.tail(window)

            # ---- 1. 换手中枢（越低分越高）----
            if 'turnover' in df.columns:
                avg_turnover = float(recent['turnover'].mean())
                turnover_score = _clamp100(100.0 - avg_turnover * 8.0)
            else:
                vm20 = float(df['volume'].tail(window).mean())
                vm60 = float(df['volume'].tail(60).mean())
                if not vm60 or vm60 != vm60:
                    return 0.0
                p = vm20 / (vm60 + 1e-8)
                # 比值 0.70 -> 100 分，1.20 -> 0 分，线性内插
                turnover_score = _clamp100((1.2 - p) / 0.5 * 100.0)

            # ---- 2. 量价配合 ----
            seg = df.tail(window + 1)
            up_days = seg[seg['close'] > seg['close'].shift(1)]
            down_days = seg[seg['close'] < seg['close'].shift(1)]
            vol_mean = float(seg['volume'].mean()) + 1e-8
            up_vol_ratio = (float(up_days['volume'].mean()) / vol_mean
                            if len(up_days) > 0 else 1.0)
            down_vol_ratio = (float(down_days['volume'].mean()) / vol_mean
                              if len(down_days) > 0 else 1.0)
            vol_score = 50.0
            if up_vol_ratio < 0.85:
                vol_score += 25.0      # 缩量上涨：筹码锁定良好
            if down_vol_ratio > 1.15:
                vol_score -= 15.0      # 下跌放量：有人在抛，扣分
            vol_score = _clamp100(vol_score)

            # ---- 3. 振幅适中度（C5：原「振幅越小分越高」方向是反的）----
            #   17570 条滚动观测实测（低位区 pos<0.25，未来20日）：
            #     amp < 1.5%    -> r20 -1.16% 胜率 28.9%（死票）
            #     amp 2.5~3%    -> r20 +0.23% 胜率 49.2%
            #     amp 3.75~4.5% -> r20 +1.19% 胜率 54.7%（峰值）
            #     amp 4.5~5.5%  -> r20 +0.29% 胜率 50.0%
            #     amp 5.5~7%    -> r20 -0.42% 胜率 44.1%
            #   故改为「峰值 4.0% 的帐篷」：过低（死票）与过高同样降分。
            amp = ((recent['high'] - recent['low'])
                   / (recent['close'] + 1e-8)).mean()
            amp20 = float(amp)
            if amp20 <= 0.040:
                amp_score = 100.0 - (0.040 - amp20) * 2300.0
            else:
                amp_score = 100.0 - (amp20 - 0.040) * 1200.0
            amp_score = _clamp100(amp_score)

            # ---- 4. 位置加权（低位更有价值）----
            tail120 = df['close'].tail(120)
            lo, hi = float(tail120.min()), float(tail120.max())
            pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
            pos_weight = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)

            score = (turnover_score * 0.40 + vol_score * 0.35
                     + amp_score * 0.25) * pos_weight
            return float(_clamp100(score))
        except Exception:
            return 0.0

    @staticmethod
    def judge_wash_or_distribute(df, lookback=10):
        """判断当前更可能是洗盘还是出货。

        返回
        ----
        str : 'wash' | 'distribute' | 'unknown'

        判据
        ----
        wash       : 阴线缩量（< 近5日均量 x0.70）+ 已有回升 + 近60日位置 < 0.65
        distribute : 阴线放量（> 近5日均量 x1.00）+ 近60日位置 > 0.70
        unknown    : 其余情况，含区间内无阴线、数据不足、异常

        实现说明（相对初稿的两处必要修正，均经 591 只主板实测）
        --------------------------------------------------------
        1. 区间内一只阴线都没有时返回 'unknown'。初稿把 down_vol 记为 0.0，
           而 0 < 5日均量x0.70 恒成立，纯上涨趋势会被误判为 'wash'。
        2. distribute 增加「阴线确实放量」这一条。初稿只要求 not is_shrinking
           （即 >= 0.70 倍），条件过松——实测 591 只主板里 20.3% 被判出货；
           收紧到 > 1.00 倍后为 6.5%。
        """
        try:
            if df is None or len(df) < lookback + 5:
                return 'unknown'
            for c in ('close', 'open', 'low', 'volume'):
                if c not in df.columns:
                    return 'unknown'
            recent = df.tail(lookback)
            vol_ma5 = float(df['volume'].rolling(5).mean().iloc[-1]) + 1e-8
            if vol_ma5 != vol_ma5:
                return 'unknown'
            down = recent[recent['close'] < recent['open']]
            if len(down) == 0:
                return 'unknown'
            down_vol = float(down['volume'].mean())
            is_shrinking = down_vol < vol_ma5 * 0.70
            has_recovery = (float(recent['close'].iloc[-1])
                            > float(recent['low'].min()) * 1.03)
            tail60 = df['close'].tail(60)
            lo, hi = float(tail60.min()), float(tail60.max())
            pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
            if is_shrinking and has_recovery and pos < 0.65:
                return 'wash'
            if (not is_shrinking) and down_vol > vol_ma5 * 1.00 and pos > 0.70:
                return 'distribute'
            return 'unknown'
        except Exception:
            return 'unknown'


    # ========================================================
    # V20 建仓阶段专门因子（2026-10-10）
    # ========================================================

    @staticmethod
    def bottom_volume_stack(df, recent_win=10, base_win=20):
        """底部堆量：近端量能是否相对更早时期堆高，且股价仍在相对低位。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low / volume。
        recent_win : int
            近端观察窗口（堆量区），默认 10。
        base_win : int
            对比基准窗口（堆量之前的存量区），默认 20。

        返回
        ----
        dict : {'ok': bool, 'score': float, 'ratio': float,
                'pos120': float, 'cont': float}
            df 为空 / 长度不足 / 缺列 / 抛异常 -> ok=False、score=0.0，其余给中性值。

        判据（四段，全部满足才 ok）
        ----
        1. ratio >= BUILD_STACK_RATIO_LO    堆量倍数达标
        2. ratio <= BUILD_STACK_RATIO_HI    不是单日爆量 / 异动
        3. pos120 < BUILD_STACK_POS_MAX     仍在底部
        4. cont >= BUILD_STACK_CONT_MIN     近端窗口内量能持续在基准均量之上

        实现说明
        --------
        1. 基准窗口取「紧邻近端窗口之前」的 base_win 日，与近端窗口**不重叠**。
           若把近端窗口也算进分母，量能会同时进分子分母，把比值压向 1，
           于是「堆量」永远测不出来。
        2. 位置用 120 日 low/high 区间，不用 close 区间 —— 堆量判断关心的是
           「有没有打出过新低/新高」，用高低点不容易被单根影线糊掉。
        3. score 三段加权：量能帐篷 0.45 + 连续性 0.30 + 低位程度 0.25。
        4. 除零 / NaN / 缺列 / 异常全部防护，绝不抛异常。
        """
        _bad = {'ok': False, 'score': 0.0, 'ratio': 0.0, 'pos120': 1.0, 'cont': 0.0}
        try:
            if df is None or len(df) < 60 or len(df) < recent_win + base_win + 1:
                return dict(_bad)
            for _c in ('close', 'high', 'low', 'volume'):
                if _c not in df.columns:
                    return dict(_bad)
            vol = df['volume']
            base_vol = float(vol.iloc[-(recent_win + base_win):-recent_win].mean())
            recent_vol = float(vol.iloc[-recent_win:].mean())
            if base_vol != base_vol or base_vol <= 0 or recent_vol != recent_vol:
                return dict(_bad)
            ratio = recent_vol / (base_vol + 1e-8)
            if ratio != ratio:
                return dict(_bad)
            cont = float((vol.iloc[-recent_win:] > base_vol).sum()) / float(recent_win)
            t120 = df.tail(120)
            _lo = float(t120['low'].min())
            _hi = float(t120['high'].max())
            cur = float(df['close'].iloc[-1])
            if _hi != _hi or _lo != _lo or _hi <= _lo:
                pos120 = 1.0
            else:
                pos120 = (cur - _lo) / (_hi - _lo + 1e-8)
            # 量能帐篷：峰值 1.60 倍（堆量温和放大的位置），下坡 100/倍，上坡 22/倍
            if ratio <= 1.60:
                r_sc = 100.0 - (1.60 - ratio) * 100.0
            else:
                r_sc = 100.0 - (ratio - 1.60) * 22.0
            r_sc = _clamp100(r_sc)
            c_sc = _clamp100(cont * 100.0)
            p_sc = _clamp100((1.0 - pos120) * 100.0)
            score = _clamp100(r_sc * 0.45 + c_sc * 0.30 + p_sc * 0.25)
            ok = (ratio >= BUILD_STACK_RATIO_LO and ratio <= BUILD_STACK_RATIO_HI
                  and pos120 < BUILD_STACK_POS_MAX and cont >= BUILD_STACK_CONT_MIN)
            return {'ok': bool(ok), 'score': float(score), 'ratio': float(ratio),
                    'pos120': float(pos120), 'cont': float(cont)}
        except Exception:
            return dict(_bad)

    @staticmethod
    def red_fat_green_thin(df, window=20):
        """红肥绿瘦：上涨日平均成交量是否明显大于下跌日平均成交量。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / volume。
        window : int
            观察窗口（含末根 K 线），默认 20。

        返回
        ----
        dict : {'ok': bool, 'score': float, 'ratio': float, 'up_days': int,
                'down_days': int, 'up_vol': float, 'down_vol': float}
            数据不足 / 缺列 / 某一侧没有交易日 / 异常 -> ok=False、score=0.0。

        判据
        ----
        ratio = 上涨日平均量 / 下跌日平均量
        ok    = ratio >= BUILD_REDFAT_RATIO 且 上涨日 >= 3 且 下跌日 >= 3

        实现说明
        --------
        1. 涨跌按「收盘 vs 前收」判定，与 estimate_control_score 的量价配合口径一致；
           不用「收盘 vs 开盘」—— 建仓特征看的是承接力度，不是当日实体方向。
        2. 某一侧交易日不足 3 天时返回 ok=False，而不是 ok=True。
           这与 judge_wash_or_distribute「无阴线不判 wash」是同一个教训：
           缺失一侧时比值没有意义，不能默认通过（否则纯上涨段会被误报成红肥绿瘦）。
        3. score 的帐篷峰值放在 ratio=1.50（明显红肥绿瘦），ratio=1.0 给 0 分。
        """
        _bad = {'ok': False, 'score': 0.0, 'ratio': 0.0, 'up_days': 0,
                'down_days': 0, 'up_vol': 0.0, 'down_vol': 0.0}
        try:
            if df is None or len(df) < window + 1 or len(df) < 21:
                return dict(_bad)
            for _c in ('close', 'volume'):
                if _c not in df.columns:
                    return dict(_bad)
            seg = df.tail(window + 1)
            chg = seg['close'].diff().values
            up = seg[(chg > 0)]
            dn = seg[(chg < 0)]
            if len(up) < 3 or len(dn) < 3:
                return dict(_bad)
            up_vol = float(up['volume'].mean())
            down_vol = float(dn['volume'].mean())
            if down_vol != down_vol or down_vol <= 0 or up_vol != up_vol:
                return dict(_bad)
            ratio = up_vol / (down_vol + 1e-8)
            if ratio != ratio:
                return dict(_bad)
            if ratio <= 1.50:
                score = (ratio - 1.0) * 200.0
            else:
                score = 100.0 - (ratio - 1.50) * 40.0
            score = _clamp100(score)
            return {'ok': bool(ratio >= BUILD_REDFAT_RATIO), 'score': float(score),
                    'ratio': float(ratio), 'up_days': int(len(up)),
                    'down_days': int(len(dn)), 'up_vol': up_vol, 'down_vol': down_vol}
        except Exception:
            return dict(_bad)


    @staticmethod
    def is_c4_candidate(df, ctrl_score=None):
        """C4 观察规则：低位 + 上涨放量 + 下跌缩量 + 适中振幅 + 控盘分过滤。

        这是【观察】规则，不是建仓触发：只用来看这批形态后续怎么走。
        历史标定【未通过逐锚点检验】（见 C4_* 常量注释），禁止当买入信号使用。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low / volume，且不少于 C4_MIN_BARS(120) 根。
        ctrl_score : float | None
            已算好的控盘分，传入可省一次 estimate_control_score；None 则内部计算。

        返回
        ----
        dict : {'ok': bool, 'n_ok': int, 'score': float, 'hits': list[bool],
                'pos120': float|None, 'up_vol_ratio': float|None,
                'down_vol_ratio': float|None, 'amp': float|None,
                'ctrl_score': float|None, 'reason': str}
            ok      —— 5 个子条件是否全部满足
            n_ok    —— 满足的子条件个数 0~5
            score   —— n_ok * 20（0~100 的纯计数强度分，不带任何权重）
            hits    —— [位置, 上涨放量, 下跌缩量, 振幅, 控盘] 逐个 bool
            reason  —— 数据不足/异常时给出原因，正常为空字符串

        判据（全部为近端窗口口径，与标定脚本 tools\\_calib_buildfactor_wide.py 逐位一致）
        ------------------------------------------------------------------
        1. pos120 < C4_POS_MAX(0.25)          近120根收盘位置 (close-min)/(max-min)
        2. up_vol_ratio  > C4_UP_MIN(1.15)    近20根上涨日均量 / 该窗口均量
        3. down_vol_ratio < C4_DN_MAX(0.95)   近20根下跌日均量 / 该窗口均量
        4. C4_AMP_LO <= amp <= C4_AMP_HI      近20根 (high-low)/close 均值 ∈ [2.5%, 5.5%]
        5. ctrl_score >= C4_CTRL_MIN(85.0)

        实现说明
        --------
        1. 涨跌按「收盘 vs 前收」判定（不用「收盘 vs 开盘」），且量能切片对齐到
           后 19 根（np.diff 比切片少一根）—— 与 estimate_control_score 的量价配合
           口径完全一致，否则标定数字会与线上对不上。
        2. 某一侧（上涨日/下跌日）一根都没有时，对应子条件判为不满足并返回 None；
           与 red_fat_green_thin「缺一侧不判通过」是同一个教训。
        3. 少于 C4_MIN_BARS 根直接返回 reason='bars<N'，不硬算：位置窗口被截短会
           与标定口径（固定 120 根）不符，宁可判为不可用。
        """
        _bad = {'ok': False, 'n_ok': 0, 'score': 0.0, 'hits': [False] * 5,
                'pos120': None, 'up_vol_ratio': None, 'down_vol_ratio': None,
                'amp': None, 'ctrl_score': None, 'reason': ''}
        try:
            if df is None or len(df) < C4_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % C4_MIN_BARS
                return r
            for _c in ('close', 'high', 'low', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            closes = np.asarray(df['close'].values, dtype=float)
            highs = np.asarray(df['high'].values, dtype=float)
            lows = np.asarray(df['low'].values, dtype=float)
            vols = np.asarray(df['volume'].values, dtype=float)
            # 1) 位置：近 120 根收盘
            c120 = closes[-120:]
            _lo, _hi = float(np.min(c120)), float(np.max(c120))
            pos = (float(closes[-1]) - _lo) / (_hi - _lo + 1e-8)
            # 2)3) 量价配合：近 20 根，涨跌按 close vs 前收，量能对齐到后 19 根
            c20, v20 = closes[-20:], vols[-20:]
            dchg = np.diff(c20)
            v19 = v20[1:]
            vm = float(np.mean(v20)) + 1e-8
            up_m, dn_m = dchg > 0, dchg < 0
            up_r = float(np.mean(v19[up_m])) / vm if up_m.sum() > 0 else None
            dn_r = float(np.mean(v19[dn_m])) / vm if dn_m.sum() > 0 else None
            # 4) 振幅：近 20 根 (high-low)/close 均值
            amp = float(np.mean((highs[-20:] - lows[-20:]) / (closes[-20:] + 1e-8)))
            # 5) 控盘分：可外部传入，避免重复计算
            ctrl = (float(ctrl_score) if ctrl_score is not None
                    else float(TechnicalIndicators.estimate_control_score(df)))
            hits = [bool(pos < C4_POS_MAX),
                    bool(up_r is not None and up_r > C4_UP_MIN),
                    bool(dn_r is not None and dn_r < C4_DN_MAX),
                    bool(C4_AMP_LO <= amp <= C4_AMP_HI),
                    bool(ctrl >= C4_CTRL_MIN)]
            n_ok = int(sum(1 for x in hits if x))
            return {'ok': bool(n_ok == 5), 'n_ok': n_ok,
                    'score': float(n_ok * 20.0), 'hits': hits,
                    'pos120': float(pos), 'up_vol_ratio': up_r,
                    'down_vol_ratio': dn_r, 'amp': float(amp),
                    'ctrl_score': float(ctrl), 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r


    @staticmethod
    def is_c6_candidate(df):
        """C6 观察规则：低位 + 适中振幅（= C4 去掉「上涨放量+下跌缩量」后的子集）。

        这是【观察】规则，不是建仓触发：只用来看这批形态后续怎么走。
        历史标定见 C6_* 常量注释 —— 样本量是 C4 的 35 倍、t 值高 2.6 倍、
        12 个阈值档位同向为正，但逐锚点增量 3/4 为负，所以仍然禁止当买入信号。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low，且不少于 C6_MIN_BARS(120) 根。
            （不需要 volume —— 本规则不含量价条件。）

        返回
        ----
        dict : {'ok': bool, 'n_ok': int, 'score': float, 'hits': list[bool],
                'pos120': float|None, 'amp': float|None, 'reason': str}
            ok     —— 位置与振幅两条是否都满足
            n_ok   —— 满足条数 0~2
            score  —— n_ok * 50（0/50/100 的纯计数强度分，不带权重）
            hits   —— [位置, 振幅] 逐个 bool
            reason —— 数据不足/异常时给出原因，正常为空字符串

        判据（与 tools\\_c6_calib.py 的口径逐位一致）
        ------------------------------------------
        1. pos120 < C6_POS_MAX(0.25)         近120根收盘位置 (close-min)/(max-min)
        2. C6_AMP_LO <= amp <= C6_AMP_HI     近20根 (high-low)/close 均值 ∈ [2.5%, 5.5%]
        """
        _bad = {'ok': False, 'n_ok': 0, 'score': 0.0, 'hits': [False, False],
                'pos120': None, 'amp': None, 'reason': ''}
        try:
            if df is None or len(df) < C6_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % C6_MIN_BARS
                return r
            for _c in ('close', 'high', 'low'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            closes = np.asarray(df['close'].values, dtype=float)
            highs = np.asarray(df['high'].values, dtype=float)
            lows = np.asarray(df['low'].values, dtype=float)
            # 1) 位置：近 120 根收盘
            c120 = closes[-120:]
            _lo, _hi = float(np.min(c120)), float(np.max(c120))
            pos = (float(closes[-1]) - _lo) / (_hi - _lo + 1e-8)
            # 2) 振幅：近 20 根 (high-low)/close 均值
            amp = float(np.mean((highs[-20:] - lows[-20:]) / (closes[-20:] + 1e-8)))
            hits = [bool(pos < C6_POS_MAX),
                    bool(C6_AMP_LO <= amp <= C6_AMP_HI)]
            n_ok = int(sum(1 for x in hits if x))
            return {'ok': bool(n_ok == 2), 'n_ok': n_ok,
                    'score': float(n_ok * 50.0), 'hits': hits,
                    'pos120': float(pos), 'amp': float(amp), 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r


    @staticmethod
    def detect_probe(df):
        """试盘识别（观察规则）：长上影放量冲高 -> 缩量回调/横盘不破。

        主力「测试抛压」的量化近似：某日放量冲高（最高价相对昨收明显跳升，
        冲击涨停后回落更好），收出长上影（上影占当日全幅 >= 50% 且不短于实体），
        随后 1~11 个交易日缩量回调或横盘、且不有效跌破试盘日低点。

        这是【观察】规则，不是建仓触发 —— 只说明「这里可能发生过一次试盘」，
        禁止参与 signal_level / 建仓价 / 排序 / 等级。

        参数
        ----
        df : pandas.DataFrame
            至少含 open/high/low/close/volume，且不少于 PROBE_MIN_BARS(60) 根。

        返回
        ----
        dict :
            {'ok': bool, 'stage': str, 'score': float, 'hits': list[bool],
             'n_ok': int, 'shadow_ratio': float|None, 'spike': float|None,
             'vol_ratio': float|None, 'post_vol_ratio': float|None,
             'probe_idx': int|None, 'bars_after': int, 'pos120': float|None,
             'reason': str}
            ok       —— P1~P6 全部满足（「缩量回调/横盘不破」已由后续K线确认）
            stage    —— 'confirmed' 已确认；'pending' 试盘日就是最后一根、还没后续K线
                        （pending 只写分数、不出文案）；'' 未发现试盘形态
            score    —— 0~100 两段不重叠：ok=True 必 >= PROBE_SCORE_OK(70)，
                        未通过必 <= 60
            hits     —— [P1..P6] 逐个 bool
            probe_idx—— 试盘日在 df 里的行号（0 基）

        判据
        ----
        P1 长上影：upper/(high-low) >= PROBE_SHADOW_MIN(0.50) 且 上影 >= 实体
        P2 冲高：  (high - prev_close)/prev_close >= PROBE_SPIKE_MIN(0.05)
        P3 放量：  当日量 / 前5日均量 >= PROBE_VOL_MIN(1.20)
        P4 回落：  收盘 <= 当日最高 x 0.97
        P5 缩量：  试盘后均量 <= 试盘日量 x PROBE_AFTER_SHRINK(0.80)，或单日量都不超过试盘日
        P6 不破：  试盘后最低价 >= min(试盘日最低, 试盘日收盘) x (1 - PROBE_HOLD_TOL)
        前置：位置 pos120 <= PROBE_POS_MAX(0.35)（2026-10-11 由 0.75 收紧，pos>=0.35 的试盘为负期望）。
        高位长上影不按试盘计，由 detect_distribution_pattern() 承接。
        """
        _bad = {'ok': False, 'stage': '', 'score': 0.0, 'hits': [], 'n_ok': 0,
                'shadow_ratio': None, 'spike': None, 'vol_ratio': None,
                'post_vol_ratio': None, 'probe_idx': None, 'bars_after': 0,
                'pos120': None, 'reason': ''}
        try:
            if df is None or len(df) < PROBE_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % PROBE_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            h = np.asarray(df['high'].values, dtype=float)
            lw = np.asarray(df['low'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            r = dict(_bad)
            r['pos120'] = float(pos)
            if pos > PROBE_POS_MAX:
                r['reason'] = 'pos>%.2f' % PROBE_POS_MAX
                return r

            def _c01(x):
                return min(1.0, max(0.0, float(x)))

            # 找最靠后的一根「试盘日」
            p = None
            for i in range(n - 1, max(n - 1 - PROBE_LOOKBACK, 5) - 1, -1):
                rng = h[i] - lw[i]
                pc = c[i - 1]
                if rng <= 0 or pc <= 0:
                    continue
                upper = h[i] - max(o[i], c[i])
                body = abs(c[i] - o[i])
                sr = upper / rng
                spike = (h[i] - pc) / pc
                v5 = float(np.mean(v[max(0, i - 5):i]))
                vr = v[i] / (v5 + 1e-9)
                if (sr >= PROBE_SHADOW_MIN and upper >= body
                        and spike >= PROBE_SPIKE_MIN and vr >= PROBE_VOL_MIN
                        and c[i] <= h[i] * 0.97):
                    p = int(i)
                    break
            if p is None:
                r['reason'] = 'no_probe'
                return r

            rng = h[p] - lw[p]
            pc = c[p - 1]
            upper = h[p] - max(o[p], c[p])
            body = abs(c[p] - o[p])
            sr = upper / (rng + 1e-9)
            spike = (h[p] - pc) / pc
            v5 = float(np.mean(v[max(0, p - 5):p]))
            vr = v[p] / (v5 + 1e-9)
            bars_after = int(n - 1 - p)
            lo_next = lw[p + 1:] if bars_after >= 1 else np.array([])
            post_vol = v[p + 1:] if bars_after >= 1 else np.array([])
            post_mean = float(np.mean(post_vol)) if bars_after >= 1 else 0.0
            post_max = float(np.max(post_vol)) if bars_after >= 1 else 0.0
            post_ratio = post_mean / (v[p] + 1e-9) if bars_after >= 1 else 0.0
            p5_ok = bool(bars_after >= 1
                         and (post_mean <= PROBE_AFTER_SHRINK * v[p]
                              or post_max <= v[p]))
            floor = min(lw[p], c[p]) * (1.0 - PROBE_HOLD_TOL)
            p6_ok = bool(bars_after >= 1 and float(np.min(lo_next)) >= floor)
            hits = [True, True, True, True, p5_ok, p6_ok]   # P1~P4 是候选门槛，必为 True
            n_ok = int(sum(1 for x in hits if x))
            if p == n - 1:
                stage, ok = 'pending', False
            else:
                ok = bool(p5_ok and p6_ok)
                stage = 'confirmed' if ok else ''
            if ok:
                extra = (0.30 * _c01((sr - PROBE_SHADOW_MIN) / 0.35)
                         + 0.30 * _c01((spike - PROBE_SPIKE_MIN) / 0.06)
                         + 0.25 * _c01((vr - PROBE_VOL_MIN) / 1.30)
                         + 0.15 * _c01((PROBE_AFTER_SHRINK - post_ratio) / 0.40))
                score = PROBE_SCORE_OK + 30.0 * _c01(extra)
            else:
                part = (0.28 * _c01((sr - 0.30) / 0.45)
                        + 0.27 * _c01((spike - 0.02) / 0.08)
                        + 0.20 * _c01((vr - 0.90) / 1.10)
                        + 0.15 * (1.0 if p5_ok else 0.30)
                        + 0.10 * (1.0 if p6_ok else 0.20))
                score = 60.0 * _c01(part)
            return {'ok': bool(ok), 'stage': stage, 'score': float(score),
                    'hits': hits, 'n_ok': n_ok,
                    'shadow_ratio': float(sr), 'spike': float(spike),
                    'vol_ratio': float(vr), 'post_vol_ratio': float(post_ratio),
                    'probe_idx': p, 'bars_after': bars_after,
                    'pos120': float(pos), 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

    @staticmethod
    def detect_distribution_pattern(df):
        """出货形态确认（观察规则）：在「高位 + distribute」之上做形态级确认。

        三种形态，命中多个时取分数最高的那个：
          ① 高位放量滞涨 —— 创/近前高，但收盘弱势、量能显著放大
          ② 高位破位     —— 平台下沿被有效跌破且放量
          ③ 双顶雏形     —— 两个高点接近、中间明显回撤、二次冲高力度减弱

        这是【观察】规则：作用是给现有「出货风险警示」加一层形态确认、降低误报，
        不参与 signal_level / 建仓价 / 排序。不依赖 judge_wash_or_distribute 的结果，
        可以独立调用，也可以与它交叉使用。

        参数
        ----
        df : pandas.DataFrame
            至少含 open/high/low/close/volume，且不少于 DIST_MIN_BARS(60) 根。

        返回
        ----
        dict :
            {'ok': bool, 'type': str, 'score': float, 'n_ok': int,
             'hits': list[bool], 'pos120': float|None, 'vol_ratio': float|None,
             'detail': dict, 'reason': str}
            ok     —— 三种形态至少一种成立
            type   —— '高位放量滞涨' / '高位破位' / '双顶雏形' / ''（未命中）
            score  —— 0~100 两段不重叠：ok=True 必 >= DIST_SCORE_OK(70)，未通过 <= 60
            hits   —— 命中形态的逐条判据 bool 列表
            detail —— 关键中间值（close_pos / 平台上下沿 / 两顶价格与回撤等）

        判据
        ----
        ① A1 pos120 >= DIST_POS_HIGH(0.65)；A2 当日最高 >= 近60日最高 x 0.98；
           A3 收盘位于当日振幅下 DIST_STALL_CLOSE_WEAK(0.45) 或收阴；
           A4 量比 >= DIST_STALL_VOL(1.80)；A5 未涨停收盘（涨幅 < 9.5%）
        ② B1 平台振幅 <= 0.18；B2 收盘 < 平台下沿 x 0.98；
           B3 量比 >= DIST_BREAK_VOL(1.50)；B4 pos120 >= DIST_POS_BREAK(0.40)
        ③ C1 两顶间隔 >= 6 根且第二顶在最近12根内；C2 |h2-h1|/h1 <= 0.03；
           C3 中间回撤 >= 0.06；C4 二次冲高量能 <= 一次 x 0.90 或 h2 < h1；
           C5 pos120 >= 0.55；C6 当前收盘 <= 颈线 x 1.03（仍在颈线附近/之下）
        """
        _bad = {'ok': False, 'type': '', 'score': 0.0, 'n_ok': 0, 'hits': [],
                'pos120': None, 'vol_ratio': None, 'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < DIST_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % DIST_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            h = np.asarray(df['high'].values, dtype=float)
            lw = np.asarray(df['low'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            v5 = float(np.mean(v[max(0, n - 6):n - 1]))
            vr = float(v[n - 1] / (v5 + 1e-9))
            pct = float((c[-1] - c[-2]) / (c[-2] + 1e-9))
            rng = float(h[-1] - lw[-1])
            close_pos = float((c[-1] - lw[-1]) / (rng + 1e-9))

            def _c01(x):
                return min(1.0, max(0.0, float(x)))

            # ---------------- ① 高位放量滞涨 ----------------
            hi60 = float(np.max(h[-60:]))
            a = [bool(pos >= DIST_POS_HIGH),
                 bool(h[-1] >= hi60 * DIST_NEWHIGH_TOL),
                 bool(close_pos <= DIST_STALL_CLOSE_WEAK or c[-1] < o[-1]),
                 bool(vr >= DIST_STALL_VOL),
                 bool(pct < 0.095)]
            a_ok = all(a)
            if a_ok:
                a_sc = DIST_SCORE_OK + 30.0 * _c01(
                    0.40 * _c01((vr - DIST_STALL_VOL) / 2.20)
                    + 0.30 * _c01((DIST_STALL_CLOSE_WEAK - close_pos) / 0.45)
                    + 0.30 * _c01((pos - DIST_POS_HIGH) / 0.30))
            else:
                a_sc = 60.0 * _c01(0.30 * _c01((vr - 1.30) / 1.50)
                                   + 0.25 * _c01((0.55 - close_pos) / 0.45)
                                   + 0.25 * _c01((pos - 0.50) / 0.35)
                                   + 0.20 * _c01((h[-1] / (hi60 + 1e-9) - 0.90) / 0.12))
            # ---------------- ② 高位破位 ----------------
            plat_lo = float(np.min(lw[-21:-1]))
            plat_hi = float(np.max(h[-21:-1]))
            plat_amp = float((plat_hi - plat_lo) / (plat_lo + 1e-9))
            b = [bool(plat_amp <= DIST_PLATFORM_AMP),
                 bool(c[-1] < plat_lo * 0.98),
                 bool(vr >= DIST_BREAK_VOL),
                 bool(pos >= DIST_POS_BREAK)]
            b_ok = all(b)
            if b_ok:
                b_sc = DIST_SCORE_OK + 30.0 * _c01(
                    0.45 * _c01(((plat_lo * 0.98) - c[-1]) / (plat_lo * 0.06 + 1e-9))
                    + 0.35 * _c01((vr - DIST_BREAK_VOL) / 1.50)
                    + 0.20 * _c01((DIST_PLATFORM_AMP - plat_amp) / 0.12))
            else:
                b_sc = 60.0 * _c01(0.35 * _c01(((plat_lo * 1.01) - c[-1])
                                               / (plat_lo * 0.06 + 1e-9))
                                   + 0.30 * _c01((vr - 1.10) / 1.20)
                                   + 0.20 * _c01((0.22 - plat_amp) / 0.14)
                                   + 0.15 * _c01((pos - 0.35) / 0.40))
            # ---------------- ③ 双顶雏形 ----------------
            m = int(min(DIST_DT_WINDOW, n))
            off = n - m
            seg = h[off:]
            loc = [i for i in range(2, m - 2)
                   if seg[i] >= max(seg[i - 2], seg[i - 1], seg[i + 1], seg[i + 2])]
            c_best = None
            for _x in range(len(loc)):
                for _y in range(_x + 1, len(loc)):
                    i, j = loc[_x], loc[_y]
                    if j - i < DIST_DT_GAP or j < m - DIST_DT_BACK:
                        continue
                    h1, h2 = float(seg[i]), float(seg[j])
                    if h1 <= 0 or h2 <= 0:
                        continue
                    diff = abs(h2 - h1) / h1
                    if diff > DIST_DT_DIFF:
                        continue
                    gi, gj = off + i, off + j
                    dip_low = float(np.min(lw[gi:gj + 1]))
                    dip = (min(h1, h2) - dip_low) / (min(h1, h2) + 1e-9)
                    if dip < DIST_DT_DIP:
                        continue
                    va = float(np.mean(v[max(0, gi - 1):gi + 2]))
                    vb = float(np.mean(v[max(0, gj - 1):gj + 2]))
                    fade = (vb <= va * DIST_DT_VOLFADE) or (h2 < h1 * 0.995)
                    neck = dip_low
                    c = [True, True, True, bool(fade),
                         bool(pos >= DIST_DT_POS_MIN),
                         bool(c[-1] <= neck * 1.03)]
                    if not all(c):
                        continue
                    sc = DIST_SCORE_OK + 30.0 * _c01(
                        0.35 * _c01((DIST_DT_DIFF - diff) / 0.03)
                        + 0.35 * _c01((dip - DIST_DT_DIP) / 0.10)
                        + 0.30 * _c01(1.0 - vb / (va + 1e-9)))
                    if c_best is None or sc > c_best[0]:
                        c_best = (sc, c, {'h1': h1, 'h2': h2, 'diff': float(diff),
                                          'dip': float(dip), 'neckline': float(neck),
                                          'idx1': int(gi), 'idx2': int(gj)})
            if c_best is not None:
                c_ok, c_sc, c_hits, c_det = True, c_best[0], c_best[1], c_best[2]
            else:
                c_ok, c_sc, c_hits, c_det = False, 0.0, [], {}

            cands = []
            if a_ok:
                cands.append(('高位放量滞涨', a_sc, a))
            if b_ok:
                cands.append(('高位破位', b_sc, b))
            if c_ok:
                cands.append(('双顶雏形', c_sc, c_hits))
            detail = {'close_pos': float(close_pos), 'hi60': hi60,
                      'platform_low': plat_lo, 'platform_high': plat_hi,
                      'platform_amp': plat_amp, 'pct': float(pct)}
            if c_det:
                detail.update(c_det)
            if cands:
                cands.sort(key=lambda x: -x[1])
                _t, _sc, _hits = cands[0]
                return {'ok': True, 'type': _t, 'score': float(_sc),
                        'n_ok': int(sum(1 for x in _hits if x)), 'hits': list(_hits),
                        'pos120': float(pos), 'vol_ratio': vr,
                        'detail': detail, 'reason': ''}
            return {'ok': False, 'type': '', 'score': float(max(a_sc, b_sc, c_sc)),
                    'n_ok': max(int(sum(1 for x in a if x)), int(sum(1 for x in b if x)),
                                len(c_hits)), 'hits': a, 'pos120': float(pos),
                    'vol_ratio': vr, 'detail': detail, 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r


    @staticmethod
    def detect_markup(df):
        """拉升阶段识别（观察规则）：阶梯式上行 / 缩量强势 / 加速迹象。

        与 detect_probe（试盘）、detect_distribution_pattern（出货形态）同族：
        都是【观察】规则，禁止参与 signal_level / 建仓价 / 排序 / 等级。

        ⚠ 方向说明（重要，别用反）
        --------------------------
        C4 / C6 / 试盘找的是「低位、启动前」；本函数找的是「已经拉起来」的票。
        结合本项目「买在启动前、不接飞刀」的建仓框架，这个标记的现实用途是
        【追高提示 / 排他标记】——告诉你「这只已经不便宜了」，而不是「可以买」。
        标定结果（tools\\markup_calib.txt）必须按这个口径解读。

        参数
        ----
        df : pandas.DataFrame
            至少含 open/high/low/close/volume，且不少于 MARKUP_MIN_BARS(60) 根。

        返回
        ----
        dict :
            {'ok': bool, 'type': str, 'score': float, 'n_ok': int, 'hits': list[bool],
             'pos120': float|None, 'gain': float|None, 'vol_ratio': float|None,
             'detail': dict, 'reason': str}
            ok     —— 三种形态至少一种成立
            type   —— '阶梯式上行' / '缩量强势' / '加速迹象' / ''（未命中）
            score  —— 0~100 两段不重叠：ok=True 必 >= MARKUP_SCORE_OK(70)，未通过必 <= 60
            hits   —— 命中形态（未命中时为 ① 的判据）逐条 bool
            gain   —— 命中形态对应的窗口累计涨幅（收盘口径）
            vol_ratio —— 命中形态对应的量能比（① 上涨/下跌均量比；② 近/前均量比；③ 加速量比）
            detail —— 关键中间值（均线 / 各形态涨幅与量能比 / 阳线占比 / 近60日最高）

        前置：位置 pos120 < MARKUP_POS_MAX(0.45)（1010m 新增）。
        依据 tools\\markup_calib.txt：整体命中的均值增量只有 +0.06pp（噪音），
        只有 pos<0.45 那一段是正期望（+1.10% / 胜率 54.3% / t=+3.31），
        pos>=0.45 三档全部显著为负 -> 高位一律不判「拉升」。
        边界：0.45 归入负期望档，故判定写 pos >= MARKUP_POS_MAX 即拦。
        ⚠ 形态②缩量强势自 2026-10-11 起位置下限改为 MARKUP_LOCK_POS_MIN=0.00（依据 tools\\markup2_pos_calib.txt），
        在本门槛（pos<0.45）内可正常命中，且标定显示它在该区间是正期望。

        判据
        ----
        ① 阶梯式上行（趋势型拉升）
           A1 MA5 > MA10 > MA20（多头排列）
           A2 近 MARKUP_TREND_WIN(10) 根累计涨幅 >= MARKUP_TREND_GAIN(6%)
           A3 近窗口「上涨日均量 / 下跌日均量」>= MARKUP_UP_DN_VOL(1.00)
              （没有下跌日时该条不成立 —— 不把「无回调」当成放量上涨）
           A4 最近 MARKUP_HOLD_WIN(5) 根的最低价 >= MA20 x (1 - MARKUP_PULLBACK_TOL(3%))
              （「回调不破关键均线」只能算发动之后那几根：发动当天的低点本来就在均线附近，
                把它算进来会让所有快速发动的票都不通过）
        ② 缩量强势（锁仓式拉升）
           B1 近 MARKUP_LOCK_WIN(8) 根阳线占比 >= MARKUP_LOCK_YANG_MIN(60%)
           B2 近窗口均量 / 更早窗口均量 <= MARKUP_LOCK_VOL_MAX(1.00)（缩量或低位维持）
           B3 pos120 >= MARKUP_LOCK_POS_MIN(0.55)（锁仓拉升必然已离开底部）
           B4 低点抬高：后半窗口最低价 >= 前半窗口最低价
        ③ 加速迹象（末段急拉）
           C1 近 MARKUP_ACC_WIN(5) 根累计涨幅 >= MARKUP_ACC_GAIN(12%)
           C2 近窗口均量 / 前窗口均量 >= MARKUP_ACC_VOL(1.30)（量能放大）
           C3 收盘 >= 近60日最高 x MARKUP_ACC_HI_TOL(0.98)（接近/创阶段新高）

        命中多个形态时取分数最高的那个（与出货形态同一策略）。
        """
        _bad = {'ok': False, 'type': '', 'score': 0.0, 'n_ok': 0, 'hits': [],
                'pos120': None, 'gain': None, 'vol_ratio': None,
                'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < MARKUP_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % MARKUP_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            h = np.asarray(df['high'].values, dtype=float)
            lw = np.asarray(df['low'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)

            def _c01(x):
                return min(1.0, max(0.0, float(x)))

            def _mav(a, k):
                return float(np.mean(a[-k:])) if len(a) >= k else 0.0

            ma5 = _mav(c, MARKUP_MA_FAST)
            ma10 = _mav(c, MARKUP_MA_MID)
            ma20 = _mav(c, MARKUP_MA_SLOW)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            # 位置门槛（1010m）：只保留低位有效子集，高位一律不判拉升（依据见 MARKUP_POS_MAX 注释）
            r = dict(_bad)
            r['pos120'] = float(pos)
            if pos >= MARKUP_POS_MAX:
                r['reason'] = 'pos>=%.2f' % MARKUP_POS_MAX
                return r
            hi60 = float(np.max(h[-60:]))

            # ---------------- ① 阶梯式上行 ----------------
            tw = MARKUP_TREND_WIN
            base_t = float(c[max(0, n - 1 - tw)])
            gain_t = (float(c[-1]) - base_t) / (base_t + 1e-9)
            up_v, dn_v = [], []
            for i in range(max(1, n - tw), n):
                if c[i] > c[i - 1]:
                    up_v.append(float(v[i]))
                elif c[i] < c[i - 1]:
                    dn_v.append(float(v[i]))
            udv = (float(np.mean(up_v)) / (float(np.mean(dn_v)) + 1e-9)
                   if (up_v and dn_v) else 0.0)
            trend_ma = bool(ma5 > ma10 > ma20)
            trend_up = bool(gain_t >= MARKUP_TREND_GAIN)
            trend_vol = bool(up_v and dn_v and udv >= MARKUP_UP_DN_VOL)
            trend_hold = bool(float(np.min(lw[-MARKUP_HOLD_WIN:]))
                              >= ma20 * (1.0 - MARKUP_PULLBACK_TOL))
            aa = [trend_ma, trend_up, trend_vol, trend_hold]
            a_ok = all(aa)
            if a_ok:
                a_sc = MARKUP_SCORE_OK + 30.0 * _c01(
                    0.30 * _c01((ma5 / (ma20 + 1e-9) - 1.0) / 0.06)
                    + 0.30 * _c01((gain_t - MARKUP_TREND_GAIN) / 0.14)
                    + 0.25 * _c01((udv - MARKUP_UP_DN_VOL) / 0.60)
                    + 0.15 * _c01((pos - 0.35) / 0.45))
            else:
                a_sc = 60.0 * _c01(
                    0.25 * _c01((ma5 / (ma20 + 1e-9) - 0.99) / 0.05)
                    + 0.25 * _c01((gain_t - 0.01) / 0.09)
                    + 0.25 * _c01((udv - 0.70) / 0.60)
                    + 0.25 * _c01(1.0 - abs(float(np.min(lw[-MARKUP_HOLD_WIN:]))
                                            / (ma20 + 1e-9) - 1.0) / 0.10))

            # ---------------- ② 缩量强势 ----------------
            wl = MARKUP_LOCK_WIN
            yang = (sum(1 for i in range(max(0, n - wl), n) if c[i] > o[i]) / float(wl))
            v_rec = float(np.mean(v[-wl:]))
            v_prev = (float(np.mean(v[max(0, n - 3 * wl):n - wl]))
                      if n > wl else v_rec)
            lock_vr = v_rec / (v_prev + 1e-9)
            lock_yang = bool(yang >= MARKUP_LOCK_YANG_MIN)
            lock_vol = bool(lock_vr <= MARKUP_LOCK_VOL_MAX)
            lock_pos = bool(pos >= MARKUP_LOCK_POS_MIN)
            half = max(1, wl // 2)
            lo_prev = float(np.min(lw[max(0, n - wl):max(0, n - half)]))
            lo_last = float(np.min(lw[max(0, n - half):]))
            lock_rise = bool(lo_last >= lo_prev)
            base_l = float(c[max(0, n - 1 - wl)])
            lock_gain = (float(c[-1]) - base_l) / (base_l + 1e-9)
            bb = [lock_yang, lock_vol, lock_pos, lock_rise]
            b_ok = all(bb)
            if b_ok:
                b_sc = MARKUP_SCORE_OK + 30.0 * _c01(
                    0.30 * _c01((yang - MARKUP_LOCK_YANG_MIN) / 0.35)
                    + 0.35 * _c01((MARKUP_LOCK_VOL_MAX - lock_vr) / 0.45)
                    + 0.20 * _c01((pos - MARKUP_LOCK_POS_MIN) / 0.35)
                    + 0.15 * _c01(lock_gain / 0.20))
            else:
                b_sc = 60.0 * _c01(
                    0.30 * _c01((yang - 0.40) / 0.40)
                    + 0.30 * _c01((1.20 - lock_vr) / 0.60)
                    + 0.20 * _c01((pos - 0.40) / 0.40)
                    + 0.20 * (1.0 if lock_rise else 0.30))

            # ---------------- ③ 加速迹象 ----------------
            aw = MARKUP_ACC_WIN
            base_a = float(c[max(0, n - 1 - aw)])
            gain_a = (float(c[-1]) - base_a) / (base_a + 1e-9)
            v_a = v[-aw:]
            v_b = v[max(0, n - 2 * aw):max(0, n - aw)]
            acc_vr = (float(np.mean(v_a) / (np.mean(v_b) + 1e-9))
                      if len(v_b) else 0.0)
            acc_gain = bool(gain_a >= MARKUP_ACC_GAIN)
            acc_vol = bool(acc_vr >= MARKUP_ACC_VOL)
            acc_high = bool(c[-1] >= hi60 * MARKUP_ACC_HI_TOL)
            cc = [acc_gain, acc_vol, acc_high]
            c_ok = all(cc)
            if c_ok:
                c_sc = MARKUP_SCORE_OK + 30.0 * _c01(
                    0.40 * _c01((gain_a - MARKUP_ACC_GAIN) / 0.15)
                    + 0.35 * _c01((acc_vr - MARKUP_ACC_VOL) / 1.20)
                    + 0.25 * _c01((c[-1] / (hi60 + 1e-9) - MARKUP_ACC_HI_TOL) / 0.06))
            else:
                c_sc = 60.0 * _c01(
                    0.40 * _c01((gain_a - 0.03) / 0.12)
                    + 0.35 * _c01((acc_vr - 0.90) / 1.00)
                    + 0.25 * _c01((c[-1] / (hi60 + 1e-9) - 0.90) / 0.10))

            cands = []
            if a_ok:
                cands.append(('阶梯式上行', a_sc, aa))
            if b_ok:
                cands.append(('缩量强势', b_sc, bb))
            if c_ok:
                cands.append(('加速迹象', c_sc, cc))
            detail = {'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
                      'gain_trend': float(gain_t), 'up_dn_vol': float(udv),
                      'yang_ratio': float(yang), 'lock_vr': float(lock_vr),
                      'lock_gain': float(lock_gain), 'gain_acc': float(gain_a),
                      'acc_vr': float(acc_vr), 'hi60': hi60}
            if cands:
                cands.sort(key=lambda x: -x[1])
                _t, _sc, _hits = cands[0]
                if _t == '阶梯式上行':
                    _g, _vr = float(gain_t), float(udv)
                elif _t == '缩量强势':
                    _g, _vr = float(lock_gain), float(lock_vr)
                else:
                    _g, _vr = float(gain_a), float(acc_vr)
                return {'ok': True, 'type': _t, 'score': float(_sc),
                        'n_ok': int(sum(1 for x in _hits if x)), 'hits': list(_hits),
                        'pos120': float(pos), 'gain': _g, 'vol_ratio': _vr,
                        'detail': detail, 'reason': ''}
            return {'ok': False, 'type': '', 'score': float(max(a_sc, b_sc, c_sc)),
                    'n_ok': max(int(sum(1 for x in aa if x)),
                                int(sum(1 for x in bb if x)),
                                int(sum(1 for x in cc if x))),
                    'hits': aa, 'pos120': float(pos), 'gain': float(gain_t),
                    'vol_ratio': float(udv), 'detail': detail, 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

    @staticmethod
    def detect_breakdown_recover(df):
        """破位—收复 双向判据（观察规则）：区分「洗盘」与「出货」。

        纯量价，无未来数据；只判非高位（pos120 < BRK_POS_LOW），高位破位交给
        detect_distribution_pattern。禁止参与 signal_level / 建仓价 / 排序。

        dict:
            {'ok': bool, 'type': str, 'score': float, 'n_ok': int, 'hits': list[bool],
             'pos120': float|None, 'vol_ratio': float|None, 'recovered': bool,
             'detail': dict, 'reason': str}
            type —— '洗盘收复'（破位缩量 + N 根内收回 + 收回日放量）
                    '破位未收'（破位放量 + 始终收不回）
                    ''（破位成立但不满足任何一侧）
            score —— 0~100 两段不重叠：ok=True 必 >= BRK_SCORE_OK(70)，未通过必 <= 60
        """
        _bad = {'ok': False, 'type': '', 'score': 0.0, 'n_ok': 0, 'hits': [],
                'pos120': None, 'vol_ratio': None, 'recovered': False,
                'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < BRK_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % BRK_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            h = np.asarray(df['high'].values, dtype=float)
            lw = np.asarray(df['low'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            r = dict(_bad)
            r['pos120'] = float(pos)
            if pos >= BRK_POS_LOW:
                r['reason'] = 'pos>=%.2f' % BRK_POS_LOW
                return r

            # ---- 找最近的破位日：当日最低 < 之前 BRK_SUPPORT_WIN 根的最低价最小值
            i_brk, sup = -1, 0.0
            _lo_i = max(BRK_SUPPORT_WIN, n - BRK_LOOKBACK)
            for i in range(n - 1, _lo_i - 1, -1):
                _s = float(np.min(lw[i - BRK_SUPPORT_WIN:i]))
                if lw[i] < _s:
                    i_brk, sup = i, _s
                    break
            if i_brk < 5:
                r['reason'] = 'no_break'
                return r
            _b5 = float(np.mean(v[i_brk - 5:i_brk]))
            vr = float(v[i_brk] / (_b5 + 1e-9))

            # ---- 破位后是否收回支撑位（只看已发生的K线，取第一根收回的）
            rec_j, rec_vr = -1, 0.0
            for j in range(i_brk + 1, min(i_brk + BRK_RECOVER_WIN, n - 1) + 1):
                if c[j] >= sup:
                    rec_j = j
                    if j >= 5:
                        _bv = float(np.mean(v[j - 5:j]))
                        rec_vr = float(v[j] / (_bv + 1e-9))
                    break
            shrink = bool(vr <= BRK_SHRINK_MAX)
            expand = bool(vr >= BRK_EXPAND_MIN)
            r['vol_ratio'] = vr
            r['recovered'] = bool(rec_j >= 0)
            r['detail'] = {'support': float(sup), 'brk_bars_ago': int(n - 1 - i_brk),
                           'brk_low': float(lw[i_brk]), 'brk_vr': float(vr),
                           'recover_bars_ago': int(n - 1 - rec_j) if rec_j >= 0 else -1,
                           'recover_vr': float(rec_vr), 'shrink': shrink,
                           'expand': expand}
            if shrink and rec_j >= 0 and rec_vr >= BRK_RECOVER_VOL:
                r['ok'] = True
                r['type'] = '洗盘收复'
                r['score'] = float(_clamp100(
                    BRK_SCORE_OK + min(20.0, (BRK_SHRINK_MAX - vr) * 40.0)
                    + min(10.0, (rec_vr - BRK_RECOVER_VOL) * 25.0),
                    BRK_SCORE_OK, 100.0))
                r['hits'] = [True, True, True, True]
                r['n_ok'] = 4
                return r
            if expand and rec_j < 0:
                r['ok'] = True
                r['type'] = '破位未收'
                r['score'] = float(_clamp100(
                    BRK_SCORE_OK + min(30.0, (vr - BRK_EXPAND_MIN) * 20.0),
                    BRK_SCORE_OK, 100.0))
                r['hits'] = [True, True, True, False]
                r['n_ok'] = 3
                return r
            # 破位成立但不满足任何一侧：给「半程」分（必须 <= 60）
            _half = 30.0 + (15.0 if shrink else 0.0) + (15.0 if rec_j >= 0 else 0.0)
            r['type'] = ''
            r['score'] = float(min(60.0, _half))
            r['hits'] = [True, bool(shrink), bool(rec_j >= 0), bool(rec_vr >= BRK_RECOVER_VOL)]
            r['n_ok'] = sum(1 for x in r['hits'] if x)
            return r
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

    @staticmethod
    def volume_percentile(df, win=VR_WIN):
        """当日成交量在「最近 win 根（含当日）」里的分位（0~100，无未来数据）。

        地量 = 分位很低（量能萎缩到区间下沿）；天量 = 分位很高。
        数据不足或全为 0 时返回 None。
        """
        try:
            if df is None or 'volume' not in df.columns:
                return None
            v = np.asarray(df['volume'].values, dtype=float)
            if len(v) < win:
                return None
            w = v[-win:]
            if float(np.max(w)) <= 0:
                return None
            cur = float(v[-1])
            return float((w <= cur).sum()) / float(win) * 100.0
        except Exception:
            return None

    @staticmethod
    def detect_volume_regime(df):
        """量能状态（观察规则）：地量 / 天量 / 缩量上涨。

        出处：主力手法里「地量见地价、天量见顶」「缩量上涨 = 高度控盘」。
        本函数只描述**当前量能处在什么档位**，不含位置条件；位置请配合
        pos120 / detect_breakdown_recover / detect_distribution_pattern 一起看。
        禁止参与 signal_level / 建仓价 / 排序。

        dict:
            {'ok': bool, 'tags': list[str], 'score': float, 'pct': float|None,
             'detail': dict, 'reason': str}
            tags —— '地量' / '天量' / '缩量上涨'（可同时出现多个）
        """
        _bad = {'ok': False, 'tags': [], 'score': 0.0, 'pct': None,
                'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < VR_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % VR_MIN_BARS
                return r
            for _c in ('open', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            r = dict(_bad)
            pct = TechnicalIndicators.volume_percentile(df, VR_WIN)
            tags, detail = [], {}
            if pct is not None:
                detail['pct'] = float(pct)
                if pct <= VR_LOW_PCT:
                    tags.append('地量')
                if pct >= VR_HIGH_PCT:
                    tags.append('天量')

            # ---- 缩量上涨：近 VR_SU_WIN 根阳线占比够、阳线均量萎缩、累计有涨幅
            su_ok, su_vr, su_gain, su_yang = False, 0.0, 0.0, 0.0
            ws = n - VR_SU_WIN
            if ws >= 5:
                _base = float(np.mean(v[ws - 5:ws]))
                _yang = [i for i in range(ws, n) if c[i] > o[i]]
                su_yang = len(_yang) / float(VR_SU_WIN)
                su_gain = (float(c[-1]) - float(c[ws - 1])) / (float(c[ws - 1]) + 1e-9)
                if _yang:
                    su_vr = float(np.mean([v[i] for i in _yang]) / (_base + 1e-9))
                su_ok = bool(su_yang >= VR_SU_YANG_MIN and su_vr <= VR_SU_VOL_MAX
                             and su_gain >= VR_SU_GAIN_MIN)
                if su_ok:
                    tags.append('缩量上涨')
                detail.update({'su_vol_ratio': float(su_vr),
                               'su_gain': float(su_gain),
                               'su_yang_ratio': float(su_yang)})
            r['pct'] = pct
            r['tags'] = tags
            r['detail'] = detail
            r['ok'] = bool(tags)
            if r['ok']:
                _sc = VR_SCORE_OK + 10.0 * len(tags)
                if pct is not None and pct <= VR_LOW_PCT:
                    _sc += min(10.0, (VR_LOW_PCT - pct) * 0.5)
                r['score'] = float(_clamp100(_sc, VR_SCORE_OK, 100.0))
            else:
                r['score'] = 60.0
            return r
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

# ============================================================
# K线数据解析
# ============================================================

class KlineDataParser:
    """K线数据解析器 - V1.1.1 格式兼容层

    自动识别两种数据格式：
    1. Dict格式：{'dates': [...], 'open': [...], 'high': [...], ...}
    2. List[Dict]格式：[{'date':..., 'open':..., 'high':..., ...}, ...]

    字段名兼容（至少3种命名变体）：
    - 日期：dates / date / trade_date / 日期 / datetime
    - 开盘：open / 开盘价 / open_price
    - 最高：high / 最高价 / high_price
    - 最低：low / 最低价 / low_price
    - 收盘：close / 收盘价 / close_price
    - 成交量：volume / vol / 成交量 / volume_ratio
    - 成交额：amount / 成交额 / turnover
    """

    # 字段名映射表（优先级从高到低）
    FIELD_ALIASES = {
        'dates': ['dates', 'date', 'trade_date', 'datetime', '日期', 'time', 'timestamp'],
        'open': ['open', '开盘价', 'open_price', 'o'],
        'high': ['high', '最高价', 'high_price', 'h'],
        'low': ['low', '最低价', 'low_price', 'l'],
        'close': ['close', '收盘价', 'close_price', 'c', 'last', 'last_price'],
        'volume': ['volume', 'vol', '成交量', 'volume_ratio', 'v', 'vol_amount'],
        'amount': ['amount', '成交额', 'turnover', 'amt', 'turnover_value'],
    }

    @staticmethod
    def _extract_field(data: Dict, field: str, default=None):
        """从Dict中按别名优先级提取字段"""
        for alias in KlineDataParser.FIELD_ALIASES.get(field, [field]):
            if alias in data and data[alias] is not None:
                return data[alias]
        return default

    @staticmethod
    def _normalize_format(kline_data):
        """统一转换为Dict数组格式

        Returns:
            (dates, opens, highs, lows, closes, volumes, amounts) 元组
        """
        # 格式1：List[Dict] - 每根K线一个字典
        if isinstance(kline_data, list):
            if len(kline_data) == 0:
                return [], [], [], [], [], [], []
            # 取第一个元素判断是否为Dict
            first = kline_data[0]
            if isinstance(first, dict):
                dates = [KlineDataParser._extract_field(d, 'dates', '') for d in kline_data]
                opens = [KlineDataParser._extract_field(d, 'open', 0) for d in kline_data]
                highs = [KlineDataParser._extract_field(d, 'high', 0) for d in kline_data]
                lows = [KlineDataParser._extract_field(d, 'low', 0) for d in kline_data]
                closes = [KlineDataParser._extract_field(d, 'close', 0) for d in kline_data]
                volumes = [KlineDataParser._extract_field(d, 'volume', 0) for d in kline_data]
                amounts = [KlineDataParser._extract_field(d, 'amount', 0) for d in kline_data]
                return dates, opens, highs, lows, closes, volumes, amounts
            # List但元素不是Dict，尝试按位置解析
            elif isinstance(first, (list, tuple)) and len(first) >= 6:
                dates = [d[0] if len(d) > 0 else '' for d in kline_data]
                opens = [d[1] if len(d) > 1 else 0 for d in kline_data]
                highs = [d[2] if len(d) > 2 else 0 for d in kline_data]
                lows = [d[3] if len(d) > 3 else 0 for d in kline_data]
                closes = [d[4] if len(d) > 4 else 0 for d in kline_data]
                volumes = [d[5] if len(d) > 5 else 0 for d in kline_data]
                amounts = [d[6] if len(d) > 6 else 0 for d in kline_data]
                return dates, opens, highs, lows, closes, volumes, amounts

        # 格式2：Dict - 包含数组
        if isinstance(kline_data, dict):
            dates = KlineDataParser._extract_field(kline_data, 'dates', [])
            opens = KlineDataParser._extract_field(kline_data, 'open', [])
            highs = KlineDataParser._extract_field(kline_data, 'high', [])
            lows = KlineDataParser._extract_field(kline_data, 'low', [])
            closes = KlineDataParser._extract_field(kline_data, 'close', [])
            volumes = KlineDataParser._extract_field(kline_data, 'volume', [])
            amounts = KlineDataParser._extract_field(kline_data, 'amount', [])
            # 兼容：vol字段被误当作amount的情况
            if not volumes and 'vol' in kline_data:
                volumes = kline_data['vol']
            return dates, opens, highs, lows, closes, volumes, amounts

        # 未知格式
        return [], [], [], [], [], [], []

    @staticmethod
    def parse(kline_data):
        """解析K线数据为bars和numpy数组

        Args:
            kline_data: Dict格式 或 List[Dict]格式

        Returns:
            (bars, opens, highs, lows, closes, volumes) 元组
        """
        dates, opens, highs, lows, closes, volumes, amounts = KlineDataParser._normalize_format(kline_data)

        # 转换numpy数组为list
        for arr_name in ['dates', 'opens', 'highs', 'lows', 'closes', 'volumes', 'amounts']:
            arr = locals()[arr_name]
            if hasattr(arr, 'tolist'):
                locals()[arr_name] = arr.tolist()

        # 重新获取（locals修改在某些情况下不生效，直接重新赋值）
        if hasattr(dates, 'tolist'): dates = dates.tolist()
        if hasattr(opens, 'tolist'): opens = opens.tolist()
        if hasattr(highs, 'tolist'): highs = highs.tolist()
        if hasattr(lows, 'tolist'): lows = lows.tolist()
        if hasattr(closes, 'tolist'): closes = closes.tolist()
        if hasattr(volumes, 'tolist'): volumes = volumes.tolist()
        if hasattr(amounts, 'tolist'): amounts = amounts.tolist()

        bars = []
        for i in range(len(closes)):
            pct = 0.0
            if i > 0 and closes[i - 1] > 0:
                pct = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
            bars.append(KlineBar(
                date=str(dates[i]) if i < len(dates) else f"day_{i}",
                open=float(opens[i]) if i < len(opens) and opens[i] else float(closes[i]),
                high=float(highs[i]) if i < len(highs) and highs[i] else float(closes[i]),
                low=float(lows[i]) if i < len(lows) and lows[i] else float(closes[i]),
                close=float(closes[i]),
                volume=float(volumes[i]) if i < len(volumes) and volumes[i] else 0.0,
                amount=float(amounts[i]) if i < len(amounts) and amounts[i] else 0.0,
                pct_chg=pct,
            ))
        return (bars,
                np.array([b.open for b in bars], dtype=float),
                np.array([b.high for b in bars], dtype=float),
                np.array([b.low for b in bars], dtype=float),
                np.array([b.close for b in bars], dtype=float),
                np.array([b.volume for b in bars], dtype=float))


# ============================================================
# 成交量分析
# ============================================================

class VolumeAnalyzer:
    @staticmethod
    def is_volume_shrinking(volumes, period=5):
        if len(volumes) < period * 2:
            return False
        return np.mean(volumes[-period:]) < np.mean(volumes[-period * 2:-period]) * 0.75  # V1.1放宽0.7→0.75

    @staticmethod
    def is_volume_expanding(volumes, period=5):
        if len(volumes) < period * 2:
            return False
        return np.mean(volumes[-period:]) > np.mean(volumes[-period * 2:-period]) * 1.25  # V1.1放宽1.3→1.25

    @staticmethod
    def volume_ratio(volumes, period=5):
        if len(volumes) < period * 2:
            return 1.0
        prev = np.mean(volumes[-period * 2:-period])
        return np.mean(volumes[-period:]) / prev if prev > 0 else 1.0

    @staticmethod
    def find_extreme_shrink(volumes, lookback=60):
        if len(volumes) < lookback:
            lookback = len(volumes)
        if lookback < 10:
            return None
        segment = volumes[-lookback:]
        min_idx = np.argmin(segment)
        abs_idx = len(volumes) - lookback + min_idx
        if abs_idx < 3 or abs_idx >= len(volumes) - 2:
            return None
        local_avg = np.mean(volumes[max(0, abs_idx - 5):abs_idx + 5])
        if volumes[abs_idx] < local_avg * 0.55:  # V1.1放宽0.5→0.55
            return abs_idx
        return None


# ============================================================
# 第一层：主力行为候选池检测器
# ============================================================

class BehaviorCandidateDetector:
    """
    第一层：主力行为候选池检测
    目的：发现正在形成机会的股票，不判断是否已买入。
    OR逻辑：满足任意条件即进入候选池。
    禁止因没有完整买点而过滤。
    """

    @staticmethod
    def detect(bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
               lows: np.ndarray, volumes: np.ndarray) -> Dict:
        """
        检测是否存在主力行为候选特征

        Returns:
            {
                'is_candidate': bool,
                'behaviors': [行为标签列表],
                'details': {...}
            }
        """
        result = {'is_candidate': False, 'behaviors': [], 'details': {}}
        if len(bars) < 10:
            result['details']['error'] = f'数据不足({len(bars)}根<10根)'
            return result

        last_idx = len(bars) - 1
        last_bar = bars[-1]
        behaviors = []

        # 1. 近期涨停或强势大阳启动（近30日）
        has_launch = False
        launch_days = 0
        for i in range(max(0, last_idx - 29), last_idx + 1):
            if bars[i].pct_chg >= LIMIT_UP_THRESHOLD:
                has_launch = True
                launch_days += 1
            elif bars[i].pct_chg >= BIG_YANG_THRESHOLD:
                has_launch = True
        # V1.1新增：近期涨幅超10%也算强势启动
        if last_idx >= 10 and closes[last_idx - 10] > 0:
            rise_10d = (closes[last_idx] - closes[last_idx - 10]) / closes[last_idx - 10] * 100
            if rise_10d >= STRONG_RISE_THRESHOLD:
                has_launch = True
                result['details']['rise_10d'] = round(rise_10d, 2)
        if has_launch:
            behaviors.append('强势启动')
            result['details']['launch_days'] = launch_days

        # 2. 上涨趋势形成（MA5>MA10>MA20 或 近20日涨幅>5%）
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        has_uptrend = False
        if not np.isnan(ma5[-1]) and not np.isnan(ma10[-1]) and not np.isnan(ma20[-1]):
            if ma5[-1] > ma10[-1] > ma20[-1]:
                has_uptrend = True
        if last_idx >= 20 and closes[last_idx - 20] > 0:
            rise_20d = (closes[last_idx] - closes[last_idx - 20]) / closes[last_idx - 20] * 100
            if rise_20d > 5:
                has_uptrend = True
        if has_uptrend:
            behaviors.append('上涨趋势')

        # 3. 横盘整理（近10-20日振幅<15%）
        has_consolidation = False
        if last_idx >= 15:
            segment_high = np.max(highs[-15:])
            segment_low = np.min(lows[-15:])
            if segment_low > 0:
                amplitude = (segment_high - segment_low) / segment_low * 100
                if 3 < amplitude < 18:  # V1.1放宽
                    has_consolidation = True
                    result['details']['amplitude_15d'] = round(amplitude, 2)
        if has_consolidation:
            behaviors.append('横盘整理')

        # 4. 成交量缩量（近5日均量<前5日75%）
        if VolumeAnalyzer.is_volume_shrinking(volumes, period=5):
            behaviors.append('成交量缩量')

        # 5. 平台形成（近10日高低点稳定，波动<10%）
        has_platform = False
        if last_idx >= 10:
            seg_h = np.max(highs[-10:])
            seg_l = np.min(lows[-10:])
            if seg_l > 0:
                amp = (seg_h - seg_l) / seg_l * 100
                if amp < 12:  # V1.1放宽
                    has_platform = True
        if has_platform:
            behaviors.append('平台形成')

        # 6. 突破迹象（近3日价格创近20日新高 或 放量上涨）
        has_breakout_sign = False
        if last_idx >= 20:
            recent_high = np.max(highs[-20:-1]) if last_idx >= 21 else np.max(highs[:-1])
            if closes[last_idx] > recent_high * 0.99:
                has_breakout_sign = True
        if last_bar.pct_chg > 2 and VolumeAnalyzer.is_volume_expanding(volumes, period=3):
            has_breakout_sign = True
        if has_breakout_sign:
            behaviors.append('突破迹象')

        # 7. 量价转强（近5日阳线多于阴线，量能温和放大）
        has_vp_strong = False
        if last_idx >= 5:
            recent_bars = bars[-5:]
            up_days = sum(1 for b in recent_bars if b.pct_chg > 0)
            if up_days >= 3 and VolumeAnalyzer.volume_ratio(volumes, period=5) > 0.9:
                has_vp_strong = True
        if has_vp_strong:
            behaviors.append('量价转强')

        result['behaviors'] = behaviors
        result['is_candidate'] = len(behaviors) >= 1  # V1.1：满足任意1个即候选
        result['details']['behavior_count'] = len(behaviors)
        return result
