# -*- coding: utf-8 -*-
"""
日K建仓四模式引擎 V5.0（band_pattern_engine.py）
==================================================
核心思想：不是看到大阳线就推荐买入。
识别：启动/吸筹 → 缩量整理 → 关键均线/周K确认 → 建仓试错

四个模式：
  模式一  跳空高开 → 3日不补缺口 → 等5日线建仓
  模式二  放量大阳 → 高位缩量小阳/十字星 → 等5日线建仓
  模式三  底部阳放量阴缩量 → 横盘2~4周 → 5周内放量阳试错
  模式四  底部横盘震荡向上 → 阳放阴缩 → 周K放量上车

signal_level: 观察 / 等待确认 / 建仓触发 / 失效
"""
import os, sys, json, sqlite3
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DB_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')
DB_PATH = os.path.join(DB_DIR, 'band_pattern.db')

# 模式ID
# V7（2026-09-26）：原「模式三 底部横盘」与「模式四 周K确认」形态相近，用户要求合并。
#                   合并后统一占用 pattern_id = 3，显示名「横盘周K」。pattern_id = 4 已废弃。
# V8（2026-09-27）：原「模式一 跳空高开」与「模式二 大阳整理」形态相近，用户要求合并。
#                   合并后统一占用 pattern_id = 1，显示名「激进」。pattern_id = 2 已废弃。
PATTERN_AGGRESSIVE = 1
PATTERN_BOTTOM = 3
PATTERN_GAP = PATTERN_AGGRESSIVE    # 兼容旧引用（= 1）
PATTERN_BIG_YANG = 2                # 已废弃：不再产生新记录，仅用于显示历史数据

PATTERN_NAMES = {
    PATTERN_AGGRESSIVE: '激进',
    PATTERN_BOTTOM: '横盘周K',
    PATTERN_BIG_YANG: '大阳整理',    # 历史记录显示用
}

# signal_level
LVL_WATCH = '观察'
LVL_WAIT = '等待确认'
LVL_TRIGGER = '建仓触发'
LVL_INVALID = '失效'

# ---------- V11 建仓价闸门（2026-09-27 用户确认） ----------
# 建仓价距现价过远 = 要么等不到，要么到价时已跌破 MA20 / 结构下沿，属于"接飞刀"。
# 亲历案例 600977 中国电影：现价 13.13 / 建仓 12.78（差 2.67%），到价要连穿
#   今日低 13.09 -> MA10 13.01 -> 9/21 低 12.93 -> MA20 12.86 四道支撑；
#   且止盈 13.16 只比现价高 0.23%，等于没有获利空间。
# 只作用于「建仓触发」（等待确认的股票本来买不了，不受影响）。
# 40 条实测：B<=2.5% 保留 9 条；600977/600218/001322（2.6~2.7%）被剔除。
_ENTRY_GAP_CAP = 2.5

# V16 提纯门槛（2026-10-09）：横盘周K 的「建仓触发」要求启动前震仓 4 项全过。
#   4 -> 现有 137 条里剩 40 条（砍 71%），8 只正样本全过。
#   改成 3 则为温和档：137 条里剩 122 条（砍 11%）。
#   3 项及以下一律降为「观察」，而 UI 只显示「建仓触发 + 等待确认」，等于不进表。
_SHAKE_MIN_OK = 4

# V18 三轴状态闸门（实现在 services/regime_gate.py）
#   冰点期 allow_trigger=False -> 建仓触发降为观察（不进表）
#   止盈系数按状态取：常温/退潮 1.03，过热抱团 1.02（提前止盈）
#   取不到数一律放行，绝不因为数据问题卡死选股。
_REGIME = {'state': '\u26a1 \u5e38\u6e29\u8f6e\u52a8', 'allow_trigger': True,
           'tp_factor': 1.03, 'push': True, 'note': '\u95f8\u95e8\u672a\u52a0\u8f7d',
           'blocked': 0}


def _load_regime(verbose=True):
    """扫描开始时载入一次状态闸门（模块级缓存，不重复算）"""
    global _REGIME
    try:
        from services.regime_gate import compute as _rc
        d = _rc(force=True)
        _REGIME = {'state': d.get('state', ''),
                   'allow_trigger': bool(d.get('allow_trigger', True)),
                   'tp_factor': float(d.get('tp_factor') or 1.03),
                   'push': bool(d.get('push', True)),
                   'note': d.get('note', ''), 'blocked': 0}
    except Exception as e:
        _REGIME = {'state': '\u26a1 \u5e38\u6e29\u8f6e\u52a8', 'allow_trigger': True,
                   'tp_factor': 1.03, 'push': True, 'note': '\u95f8\u95e8\u4e0d\u53ef\u7528\uff0c\u5df2\u653e\u884c',
                   'blocked': 0}
        print('[\u72b6\u6001\u95f8\u95e8] \u4e0d\u53ef\u7528\uff0c\u5df2\u653e\u884c: %s' % e, flush=True)
    if verbose:
        print('[\u72b6\u6001\u95f8\u95e8] %s\uff5c%s' % (_REGIME['state'], _REGIME['note']), flush=True)
    return _REGIME


def _valid_until(bars, i, n_days):
    """基准日之后第 n_days 个交易日的日期（超出K线则取最后一根）"""
    if i is None or i < 0:
        return ''
    j = min(i + n_days, len(bars) - 1)
    return bars[j]['date'][:10]


def _valid_until_cal(bars, days):
    """结构最后一根K线日期 + days 个自然日（近似交易日观察期）"""
    if not bars:
        return ''
    try:
        _d = datetime.strptime(bars[-1]['date'][:10], '%Y-%m-%d') + timedelta(days=days)
        return _d.strftime('%Y-%m-%d')
    except Exception:
        return bars[-1]['date'][:10]


def _is_main_a_share(code):
    # 2026-10-10：用户可买创业板，放行 300/301。
    # 科创板(688/689) / 北交所(8xx/4xx/920) 仍剔除。
    return code.startswith(('600','601','603','605','000','001','002','003',
                            '300','301'))


# 低价股下限：最新收盘价低于该值的股票不参与四模式扫描。
# 口径 = 扫描时该股最新一根日K的收盘价，与写入 DB 的 push_price 完全一致。
MIN_PRICE = 6.0


def _lu_threshold(code):
    """涨停判定阈值（%）：主板 9.5，创业板 19.5（均留 0.5% 容差）。

    创业板是 20cm 板，若统一用 9.5% 判，+10%~19.4% 的非涨停创业板股
    会被算成涨停，导致「行业涨停家数 / 大盘涨停家数」虚高，
    进而抬高环境分与题材因子。本函数是全项目唯一的口径来源。
    """
    c = str(code)
    if c.startswith(('300', '301', '688', '689')):
        return 19.5      # 创业板 / 科创板 20cm
    if c.startswith(('8', '4', '920')):
        return 29.5      # 北交所 30cm
    return 9.5           # 主板 10cm


def _is_st(name):
    n = (name or '').upper()
    return 'ST' in n or '退' in n


def _is_yang(b):
    return b['close'] > b['open']


def _is_solid_yang(b, min_body=0.02):
    """实体阳线：收 > 开，且实体涨幅 >= 2%（排除十字星/小实体）"""
    if b['open'] <= 0 or b['close'] <= b['open']:
        return False
    return (b['close'] - b['open']) / b['open'] >= min_body


def _is_limit_up(b, prev_close, threshold=0.098):
    """涨停：相对前收盘涨幅 >= threshold（默认 9.8% = 主板 10% 留 0.2% 容差）。

    注意：**本函数目前全项目无任何调用**（模式一/二的基准日改用
    「实体 >=3% 且涨幅 >=3%」判定）。创业板要按 19.5% 判，传 threshold=0.195。
    """
    if not prev_close or prev_close <= 0:
        return False
    return (b['close'] - prev_close) / prev_close >= threshold


def _is_yang_strong(b, pct=0.07):
    return _is_yang(b) and (b['close'] - b['open']) / b['open'] >= pct


def _ma(arr, n):
    if len(arr) < n:
        return None
    return sum(arr[-n:]) / n


def _cross_star(b):
    if b['high'] <= b['low']:
        return False
    return abs(b['close'] - b['open']) / b['open'] <= 0.01 if b['open'] > 0 else False


def _body(b):
    return abs(b['close'] - b['open'])


# ==================================================================
# 建仓价（Entry Price）：庄家成本视角 —— 中枢 + 波动 + 震荡边界 + 共振
#   中枢 = 20日典型价VWAP，或各模式自身的结构锚（缺口价 / 大阳收盘 / 横盘中轴）
#   波动 = 14日ATR，决定挂单价离中枢几个波动单位（越波动，挂得越远）
#   震荡 = 结构上/下沿，作为建仓价的硬边界，不许穿越（守不住就说明结构废了）
#   共振 = f ∈ [-1,1]，趋势排列 + 5日动能 + 量能放大 三者同向程度
#          强势(f>0)上移建仓价避免踏空；弱势(f<0)下移加厚安全垫
# ==================================================================
def _atr14(bars, period=14):
    """14日ATR（真实波幅均值）—— 波动单位"""
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(len(bars) - period, len(bars)):
        h, l, pc = bars[i]['high'], bars[i]['low'], bars[i - 1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _vwap20(bars, n=20):
    """n日典型价VWAP = 平均((H+L+C)/3) —— 资金加权价值中枢"""
    if len(bars) < n:
        return 0.0
    return sum((b['high'] + b['low'] + b['close']) / 3.0 for b in bars[-n:]) / n


def _resonance_f(bars):
    """共振因子 f ∈ [-1, 1]：趋势排列(±0.7) + 5日动能(±0.2) + 量能(±0.1)"""
    if len(bars) < 20:
        return 0.0
    closes = [b['close'] for b in bars]
    vols = [b['volume'] for b in bars]
    ma5 = sum(closes[-5:]) / 5.0
    ma10 = sum(closes[-10:]) / 10.0
    ma20 = sum(closes[-20:]) / 20.0
    s = 0.0
    s += 0.4 if ma5 > ma10 else -0.4
    s += 0.3 if ma10 > ma20 else -0.3
    if len(closes) >= 6 and closes[-6] > 0:
        g5 = (closes[-1] - closes[-6]) / closes[-6]
        s += max(-0.2, min(0.2, g5 * 2.0))
    v3 = sum(vols[-3:]) / 3.0
    v20 = sum(vols[-20:]) / 20.0
    if v20 > 0:
        vr = v3 / v20
        s += 0.1 if vr >= 1.2 else (-0.1 if vr <= 0.8 else 0.0)
    return max(-1.0, min(1.0, s))


def _entry_shift(f, atr):
    """共振修正量：强势上移（不必等太深），弱势下移（要更厚的安全垫）"""
    return (0.5 * f * atr) if f >= 0 else (0.8 * f * atr)


# ==================================================================
# 启动前「震仓 / 试盘」因子（V16，2026-10-09 加）
#   专业的启动链条是：吸筹 -> 震仓 -> 试盘 -> 主升。
#   横盘段已经由 struct_pos / up_rate / down_rate 覆盖了「吸筹」；
#   这里补的是紧贴启动周之前那 5 个交易日（震仓/试盘）的形态证据。
#
#   实测标定（2026-10-09，8 只可在本地K线回放的用户正样本：
#     国脉文化600640 振石股份601112 中视传媒600088 龙版传媒605577
#     德豪润达002005 内蒙新华603230 大亚圣象000910 华丽家族600503）：
#       shake_dip    回撤到箱体什么位置   中位 61.0%  范围  30.8% ~ 67.0%
#       shake_shadow 启动前最大下影线占比  中位 46.9%  范围  26.7% ~ 66.7%
#       shake_probe  最低价相对MA20       中位 -2.9%  范围  -6.2% ~ -0.04%
#                    -> 8/8 全部探到 MA20 下方（挖坑动作，无一例外）
#       shake_amp    振幅收敛比           中位 0.82   范围  0.58 ~ 1.19（6/8 <1）
#
#   被同批数据否掉、不要当因子的两条（写在这里防止以后再被加回来）：
#       A1 阳线均量 / 阴线均量：中位 1.04，范围 0.83~1.08
#          —— 启动前的吸筹期阳量与阴量基本持平，"阳线必须大于阴线"不成立
#       B1 启动前必须缩到地量（近5日均量 / 横盘均量）：中位 0.83，范围 0.51~1.37
#          —— 只是温和缩量（约 -17%），要求 <0.5 会大面积误杀
#
#   阈值按上述样本标定，所以这 8 只必然全过；它的作用不是"挑出正样本"，
#   而是把「形态上根本不是震仓/试盘」的股票从横盘周K候选里区分出来。
#   四项：回撤<=72% / 下影>=25% / 探针<=0 / 0<振幅收敛<=1.2
# ==================================================================
def _shake_factors(bars, si, hi, lo, st):
    """启动周前 5 个交易日的震仓/试盘因子。si=启动周首根下标，[st,si)=横盘窗口"""
    res = {'shake_dip': 0.0, 'shake_shadow': 0.0, 'shake_probe': 0.0,
           'shake_amp': 0.0, 'shake_ok': 0}
    if si < 8 or hi <= lo:
        return res
    seg = bars[max(st, si - 5):si]
    win = bars[st:si]
    if len(seg) < 3 or len(win) < 3:
        return res
    low5 = min(b['low'] for b in seg)
    res['shake_dip'] = round((hi - low5) / (hi - lo) * 100, 1)
    hl = [b for b in seg if b['high'] > b['low']]
    if hl:
        res['shake_shadow'] = round(max(
            (min(b['open'], b['close']) - b['low']) / (b['high'] - b['low']) * 100
            for b in hl), 1)
    ma20 = _ma([b['close'] for b in bars[:si]], 20)
    if ma20:
        res['shake_probe'] = round((low5 - ma20) / ma20 * 100, 2)
    a5 = sum((b['high'] - b['low']) / b['close'] for b in seg) / len(seg)
    aw = sum((b['high'] - b['low']) / b['close'] for b in win) / len(win)
    if aw > 0:
        res['shake_amp'] = round(a5 / aw, 2)
    ok = 0
    ok += 1 if res['shake_dip'] <= 72.0 else 0
    ok += 1 if res['shake_shadow'] >= 25.0 else 0
    ok += 1 if res['shake_probe'] <= 0.0 else 0
    ok += 1 if 0 < res['shake_amp'] <= 1.2 else 0
    res['shake_ok'] = ok
    return res


def _load_bars(code):
    """读日K：优先本地缓存，兜底腾讯在线"""
    try:
        from services.kline_cache_service import get_latest_kline
        bars = get_latest_kline(code, count=120)
        if bars and len(bars) >= 30:
            return bars
    except Exception:
        pass
    try:
        from utils.kline_fetcher import fetch_kline
        bars = fetch_kline(code, days=120)
        return bars or []
    except Exception:
        return []


# ==================================================================
# V19 控盘度 + 洗盘/出货判断（TechnicalIndicators，strategy/base.py）
# ==================================================================
# 提醒文案的触发阈值。实测 591 只主板（kline_cache）control_score 分位：
#   中位 73.7 / 75分位 91.9 / 90分位 96.4 —— 分数偏挤在高位，区分度一般。
#   2026-10-10 由 70/75 上调到 85/90（命中率 32.7% / 27.1%），
#   原因是 70/75 时全市场命中 57.7%，列表里一半以上都带提示，等于没提示。
#   想再放宽可回调到 80（40.3%）/ 85，改这两行即可。
#   出货警示原为「控盘分门槛 _CTRL_DIST=60」，2026-10-10 改为「位置门槛
#   _CTRL_DIST_POS=0.65」—— 旧口径方向是反的，依据见 _CTRL_DIST_POS 注释。
#   规则③「高度控盘候选」2026-10-10（C3）由「分数主导」改为「位置主导」，
#   位置阈值改看 _CTRL_CAND_POS=0.25，依据见该常量注释。
_CTRL_HIGH = 85.0        # 高度控盘线（规则①与规则③共用）
_CTRL_CAND = 90.0        # 【已停用 2026-10-10（C3）】原为「高度控盘候选线」（规则③的分数门槛）。
                         #   保留常量仅为兼容 tools\_*.py 旧脚本的 import；
                         #   _ctrl_note 已不再引用它，不要再用它做候选判断。
_CTRL_CAND_POS = 0.25    # 规则③「高度控盘候选」的位置上限（C3 新增）：近120日位置 < 0.25。
                         #   2026-10-10 由「分数主导(score>=90 & pos<0.4)」改为
                         #   「位置主导 + 分数过滤(pos<0.25 & ctrl>=85)」。依据（17570 条滚动观测）：
                         #     旧  score>=90 & pos<0.4  -> n=3220 r20 -0.01% 胜率44.9% t=-0.03（零区分度）
                         #     新  pos<0.25 & ctrl>=85  -> n=3474 r20 +0.22% 胜率46.5% t=+1.17
                         #   备注：纯 pos<0.25 不筛分数 t=+3.73 更强（n=10598），说明残留的
                         #   分数门槛仍偏严，留待后续评估是否放开，不要擅自改。
_CTRL_POS_LOW = 0.4      # 【已停用 2026-10-10（C3）】原为规则③的位置上限。
                         #   保留常量仅为兼容旧脚本 import；该值同时仍是评分里
                         #   pos_weight 的 1.2 倍分界（见 strategy/base.py），不要删。
_CTRL_DIST = 60.0        # 【已停用 2026-10-10】原为「出货警示的控盘分门槛」。
                         #   保留常量仅为兼容 tools\_test_ctrl_dist.py 等旧脚本的 import；
                         #   _ctrl_note 已不再引用它，不要再用它做出货判断。
_CTRL_DIST_POS = 0.65    # 出货风险警示的位置门槛：近120日位置 >= 0.65 才警示。
                         #   2026-10-10 由「ctrl>=_CTRL_DIST」改为按位置。依据（17570 条滚动观测，
                         #   n 已按 4 锚点重叠折半，t 为保守值）：
                         #     distribute & pos>=0.7 -> 20日 -4.62% 胜率35.9% 回撤-19.09%
                         #     distribute & pos<0.4  -> 20日 +1.03% 胜率53.2% 回撤 -7.13%
                         #   旧口径(ctrl>=60)命中集合回撤仅 -8.30%，比全样本(-10.76%)还好，
                         #   等于把最危险的那批（pos高但ctrl低）挡在警示之外，方向是反的。
_CTRL_FUNNEL = {'ok': 0, 'ctrl': 0, 'wash': 0, 'dist': 0, 'tip': 0}


# ---- V20 建仓阶段专门因子（2026-10-10）bottom_volume_stack / red_fat_green_thin ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators 里。
# 实测结论（tools\build_factor_calibration*.txt：17570 条观测 / 4401 只 / 4 锚点 k=20/40/60/80，
# 每个锚点只喂截断到 T 的 120 根，无未来数据）：
#   1. 【孤立使用】堆量倍数与红肥绿瘦比值都跟未来20日收益【单调负相关】
#      （rho -0.043 / -0.054）；ratio<1.0 -> -0.21%，ratio 1.6~2.2 -> -3.09%，
#      ratio>3.5 -> -6.27%；反向「红瘦绿肥」反而是 +0.31%。
#   2. 【条件使用】把它们挂进「控盘高分区」(score>=85 & pos<0.25) 也救不回来：
#      逐锚点算同锚点增量，三种样本充足的口径（s_score>=45/50 & r_ratio>=1.10、
#      s_score>=40 & r_score>=40）都是【4 个锚点全部为负】，平均 -1.6 ~ -2.4pt。
#      汇总值看起来是 +2.23%（vs 基准 +0.33%），那是锚点构成偏差 —— 该组合 59.7%
#      的样本落在 k60，而 k60 的基准本身就是 +6.89%；逐锚点看每个锚点都不如基准。
#   3. 结论：这两个因子在本样本上【没有任何可用方向】。字段照写（供观察与复盘，
#      也给后续更大的样本继续验证），但建仓类提示默认【不上线】，
#      避免往程序里塞一个已被证伪的信号。
_BUILD_NOTE_MODE = 'off'   # 'off' 只写字段不提示（默认，依据见上）
                           # 'buy' 按原始草案：堆量/红肥绿瘦 满足 -> 建仓特征文案
                           # 'warn' 按实测方向：高控盘区内堆量+红肥绿瘦 -> 过热谨慎文案
_BUILD_HIT_STACK = 70.0    # 堆量分 >= 该值算「满足」（与 strategy/base.py BUILD_HIT_STACK 对齐）
_BUILD_HIT_REDFAT = 65.0   # 红肥绿瘦分 >= 该值算「满足」（对齐 BUILD_HIT_REDFAT）
_BUILD_FUNNEL = {'ok': 0, 'stack_ok': 0, 'redfat_ok': 0, 'both_ok': 0, 'tip': 0}


# ---- C4 观察规则（2026-10-10）低位 + 量价结构 + 适中振幅 + 控盘分 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.is_c4_candidate()。
# 标定（tools\buildfactor_wide.csv：17570 条观测 / 4401 只 / 4 锚点，无未来数据）：
#   命中口径 pos<0.25 & up>1.15 & dn<0.95 & amp∈[2.5%,5.5%] & ctrl>=85
#     -> n=219  未来20日 +1.57%  胜率 59.4%  t=+1.98
#   ctrl>=80 同向略强 -> n=300  +1.82%  胜率 61.0%  t=+2.81
#   **但两个口径都没通过逐锚点检验**（k20 +0.21 ｜ k40 样本不足 ｜ k60 +5.01 ｜ k80 -3.14），
#   汇总为正主要来自样本集中在 k60，是锚点构成偏差；且「上涨放量+下跌缩量」单独用
#   是 -1.66%（t=-6.31），本身是负向条件。所以：
#     - 只做「观察」：不参与 signal_level / 建仓价 / 排序 / 等级；
#     - 文案固定为「C4观察：…」，禁止出现买入/启动/建仓类字样；
#     - 是否显示由 _C4_NOTE_MODE 控制（'off' 则只写字段不提示）。
#   统计上更结实的口径是去掉量价结构的 pos<0.25 & amp∈[2.5%,5.5%]
#   （n=7749 r20=+0.66% t=+5.24），但那不是 C4 定义，要改先与用户确认。
_C4_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_C4_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'vol': 0, 'amp': 0, 'ctrl': 0,
              'c4': 0, 'note': 0}

# ---- C6 观察规则（2026-10-10）低位 + 适中振幅 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.is_c6_candidate()。
# 标定复现见 tools\_c6_calib.py（17570 条观测 / 4401 只 / 4 锚点，无未来数据）：
#   ★ C6 两条叠加 n=7749  r20=+0.66%  胜率 52.0%  t=+5.24（全样本基准 -0.80% / 45.2%）
#   12 个「位置×振幅」档位同向为正（+0.49%~+0.83%）；低位区内振幅呈帐篷形
#   （[3.5%,4.5%) 最好 +1.12%/54.6%，<2% 的死票 -0.76%/33.5%）。
#   **但逐锚点增量 3/4 为负**（k20 -0.41 ｜ k40 -0.07 ｜ k60 +6.43 ｜ k80 -1.33），
#   正贡献几乎全在 k60 —— 与 C4 同一个毛病。所以：
#     - 只做「观察」：不参与 signal_level / 建仓价 / 排序 / 等级；
#     - 文案固定为「C6观察：…」，禁止出现买入/启动/建仓类字样；
#     - 是否显示由 _C6_NOTE_MODE 控制（'off' 则只写字段不提示）。
_C6_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_C6_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'amp': 0, 'c6': 0, 'note': 0}

# ---- 试盘识别（2026-10-10）放量冲高收长上影 -> 缩量回调不破 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.detect_probe()。
# 实盘标定见 tools\probe_dist_calib.txt（_calib_probe_dist.py 生成，无未来数据）。
# 只做【观察】：不参与 signal_level / 建仓价 / 排序 / 等级。
# 只有 stage='confirmed'（试盘之后确实缩量回调且不破试盘日低点）才出文案；
# 试盘日就是最后一根的 'pending' 只写分数，避免「当天长上影」的噪音刷屏。
_PROBE_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_PROBE_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'no': 0, 'pending': 0,
                 'hit': 0, 'note': 0}

# ---- 出货形态确认（2026-10-10）高位放量滞涨 / 高位破位 / 双顶雏形 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.detect_distribution_pattern()。
# 作用：给现有「出货风险警示」（stage_guess=distribute 且位置>=0.65）加一层
# 形态级确认，降低误报；两者并存，互不替代。只做【观察】。
_DISTP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_DISTP_FUNNEL = {'ok': 0, 'insuf': 0, 'stall': 0, 'break': 0, 'dtop': 0,
                 'hit': 0, 'note': 0}

# ---- 洗盘文案降级（2026-10-11）----
# 依据：滚动观测里「控盘分>=85 且 stage_guess='wash'」这一组的胜率约 37.9%，
# 低于全样本基准 45.2%；换过多档位置/分数门槛都跑不赢基准。
# 结论：字段有价值（stage_guess 仍记录 wash，可用于事后复盘），提示没有价值。
# 处理：文案默认关闭 —— 界面上不再出现「高度控盘 + 疑似洗盘，关注启动」；
#      判定逻辑一个字没改（still 以 judge_wash_or_distribute 的 stage_guess 为准）。
_WASH_NOTE_MODE = 'off'   # 'off' 不出洗盘文案（默认，依据见上）；'watch' 恢复旧文案

# ---- 拉升阶段识别（2026-10-11）阶梯式上行 / 缩量强势 / 加速迹象 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.detect_markup()。
# ⚠ 方向说明（别用反）：C4 / C6 / 试盘找的是「低位、启动前」；本因子找的是「已经拉起来」。
#   在本项目「买在启动前、不接飞刀」的框架下，它是【追高提示 / 排他标记】，不是买入提示。
# 实盘标定见 tools\markup_calib.txt（tools\_calib_markup.py 生成；锚点 k=20/40/60/80，无未来数据）。
# 只做【观察】：不参与 signal_level / 建仓价 / 排序 / 等级。
# 1010m：因子层加了位置门槛 MARKUP_POS_MAX=0.45（只保留 pos120<0.45 的低位子集）——
#   依据 tools\markup_calib.txt：整体命中均值增量仅 +0.06pp（噪音），pos>=0.45 三档全部显著为负，
#   只有 pos<0.45 是正期望（+1.10% / 胜率 54.3% / t=+3.31）。
#   因此 markup_ok=1 只会落在 pos120<0.45 的票上。
# 2026-10-11 修正：形态②缩量强势原来的位置下限 0.55 把它锁在唯一为负的区间
#   （[0.55,0.75) -2.83%/t=-2.89），已按 tools\markup2_pos_calib.txt 改成 0.00，
#   于是 ② 在 pos<0.45（+2.36%/胜率58.1%/t=+11.66）区间恢复可命中。
#   要看高位拉升（追高警示）就把门槛调回 1.01，或直接读 detect_markup 的 pos120。
_MARKUP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_MARKUP_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'trend': 0, 'lock': 0,
                  'acc': 0, 'hit': 0, 'note': 0}

# 破位—收复 双向判据（A 项，2026-10-11）。文案默认 'watch'：只出【风险侧】——
# 「破位未收」标定为 -3.63% / 胜率 33.9% / t=-3.76（显著负），值得提示；
# 「洗盘收复」在低位只是不显著（-0.41% / t=-0.65），按项目「无信息不出文案」只写字段。
# 依据 tools\brk_volgem_calib.txt（17516 条滚动观测 / 锚点 20/40/60/80 / 无未来数据）。
_BRK_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_BRK_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'nobreak': 0, 'wash': 0, 'dist': 0, 'note': 0}

# 量能分位 / 缩量上涨（B 项，2026-10-11）。文案默认 'watch'：
#   天量     全位置档都显著为负（-2.44% / t=-8.36）-> 出警示
#   缩量上涨 只有 pos<0.45 显著为正（+4.34% / 胜率 66.4% / t=+8.21）-> 限低位出
#   地量     整体噪音（+0.02% / t=+0.14）-> 只写字段（vreg_tags），不出文案
# 依据同上（tools\brk_volgem_calib.txt）。
_VREG_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_VREG_FUNNEL = {'ok': 0, 'insuf': 0, 'low': 0, 'high': 0, 'shrinkup': 0, 'note': 0}


def _bars_to_df(bars):
    """把引擎内部的 bars(list[dict]) 转成 DataFrame，供控盘度 / 洗盘判断使用。

    bars 来自 kline_cache（含 date/open/high/low/close/volume）；若将来行情源
    补上 turnover，这里会自动带上，estimate_control_score 会优先用真实换手率。
    长度不足 60 或异常时返回 None。
    """
    try:
        if not bars or len(bars) < 60:
            return None
        import pandas as pd
        d = {
            'open': [float(b.get('open') or 0) for b in bars],
            'high': [float(b.get('high') or 0) for b in bars],
            'low': [float(b.get('low') or 0) for b in bars],
            'close': [float(b.get('close') or 0) for b in bars],
            'volume': [float(b.get('volume') or 0) for b in bars],
        }
        if bars and 'turnover' in bars[-1]:
            d['turnover'] = [float(b.get('turnover') or 0) for b in bars]
        return pd.DataFrame(d)
    except Exception:
        return None


def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None,
               probe=None, distpat=None, markup=None, brk=None, vreg=None):
    """按控盘分 / 阶段 / 位置生成提醒文案，多条用 ' ｜ ' 连接；无提示返回 ''。

    stack / redfat
    --------------
    V20 建仓因子的两个分数（0~100），默认 None。
    只有显式传入时才会追加建仓类文案；7 张个股列表走 control_profile，
    那里只传前 3 个参数，因此它们的行为完全不受影响。
    是否真的追加由模块级 _BUILD_NOTE_MODE 控制，默认 'off'（依据见该常量注释）。

    c4
    --
    C4 观察规则的满足子条件个数（0~5，来自 TechnicalIndicators.is_c4_candidate 的 n_ok），
    默认 None。只有显式传入且 ==5 时才追加「C4观察：低位量价结构」；
    同样由模块级 _C4_NOTE_MODE 控制（默认 'watch'，依据见该常量注释）。

    c6
    --
    C6 观察规则的满足条数（0~2，来自 TechnicalIndicators.is_c6_candidate 的 n_ok），
    默认 None。只有显式传入且 ==2 时才追加「C6观察：低位适中振幅」；
    同样由模块级 _C6_NOTE_MODE 控制（默认 'watch'，依据见该常量注释）。
    与 C4 / 建仓因子互相独立，任一条不通过都不影响其他文案。

    probe / distpat
    ---------------
    probe  —— 试盘识别是否【确认】（TechnicalIndicators.detect_probe 的 ok），
              默认 None。为 True 时追加「试盘观察：长上影测试抛压」。
    distpat—— 出货形态类型（detect_distribution_pattern 的 type，字符串），
              默认 None。非空时追加「出货形态观察：<类型>」。
              两者同样受 _PROBE_NOTE_MODE / _DISTP_NOTE_MODE 控制。

    markup
    ------
    拉升阶段识别的类型（TechnicalIndicators.detect_markup 的 type），默认 None。
    非空时追加「拉升观察：<类型>」。**方向与试盘相反**：这是【追高提示 / 排他标记】，
    不是买入提示（依据见 _MARKUP_NOTE_MODE 注释）。
    """
    _low_ctrl = bool(ctrl >= _CTRL_HIGH and pos is not None and pos < _CTRL_CAND_POS)
    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)
                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl,
                                      probe, distpat, markup, brk, vreg, pos))


def _ctrl_note_tags(ctrl, stage, pos):
    """只返回「控盘提示」标签列表（就是表格里 候选 / 出货 / 洗盘 那一部分）。

    必须与 _ctrl_note 共用这同一份判定：引擎把它写进 pattern_record.ctrl_tag，
    UI 显示短标签时读那一列。**不要**拿 _ctrl_note 的整串文案去做关键词反推 ——
    C4/C6/建仓因子这些「观察类文案」混在同一串里，反推会把只命中观察规则的股票
    误标成绿色「候选」（2026-10-10 实测：控盘 72 分、无任何控盘提示的股票被标 候选，
    15 条虚增到 43 条）。

    洗盘文案自 2026-10-11 起默认关闭（_WASH_NOTE_MODE='off'，依据见该常量注释）；
    stage_guess 仍照常记录 wash / distribute / unknown。

    返回 list[str]，无提示返回 []。异常时返回 []（宁可没标签，不给错标签）。
    """
    out = []
    try:
        # 2026-10-11 降级：wash 组实测胜率 37.9% < 全样本基准 45.2%，暂不作为提示。
        # stage_guess 仍照常写 'wash'（字段保留）；要恢复旧文案把 _WASH_NOTE_MODE
        # 改回 'watch' 即可，无需改代码。
        if _WASH_NOTE_MODE != 'off' and ctrl >= _CTRL_HIGH and stage == 'wash':
            out.append('高度控盘 + 疑似洗盘，关注启动')
        if stage == 'distribute' and pos is not None and pos >= _CTRL_DIST_POS:
            out.append('出货风险警示')
        # C3（2026-10-10）：改为位置主导 —— 先看是否在低位区，再用控盘分过滤
        if pos is not None and pos < _CTRL_CAND_POS and ctrl >= _CTRL_HIGH:
            out.append('高度控盘候选')
    except Exception:
        return []
    return out


def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False,
                  probe=None, distpat=None, markup=None, brk=None, vreg=None,
                  pos=None):
    """只返回「观察类」文案（建仓因子 + C4 + C6 + 试盘 + 出货形态 + 拉升），与控盘提示分开。

    分开的唯一目的：让 UI 取标签时不必解析整串 note（见 _ctrl_note_tags 说明）。
    文案内容与拼接顺序与历史版本逐字一致，note 字段因此没有任何变化。
    """
    out = []
    try:
        # V20 建仓因子文案（默认不触发；依据见 _BUILD_NOTE_MODE 注释）
        if _BUILD_NOTE_MODE != 'off' and stack is not None and redfat is not None:
            _s_hit = float(stack) >= _BUILD_HIT_STACK
            _r_hit = float(redfat) >= _BUILD_HIT_REDFAT
            if _BUILD_NOTE_MODE == 'buy':
                if _s_hit:
                    out.append('疑似底部堆量')
                if _r_hit:
                    out.append('红肥绿瘦建仓特征')
                if _s_hit and _r_hit and low_ctrl:
                    out.append('建仓加强')
            elif _BUILD_NOTE_MODE == 'warn':
                # 按实测方向：这几个条件下同锚点增量 4/4 为负 -> 提示谨慎，而非提示买入
                if _s_hit and _r_hit and low_ctrl:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')
        # C4 观察文案（默认 'watch' 会追加；未通过逐锚点检验，只能观察，依据见常量注释）
        if _C4_NOTE_MODE != 'off' and c4 is not None and int(c4) >= 5:
            out.append('C4观察：低位量价结构')
        # C6 观察文案（默认 'watch'；C4 去掉量价结构后的更稳子集，依据见常量注释）
        if _C6_NOTE_MODE != 'off' and c6 is not None and int(c6) >= 2:
            out.append('C6观察：低位适中振幅')
        # 试盘识别文案（默认 'watch'；只有 confirmed 才出，依据见 _PROBE_NOTE_MODE 注释）
        if _PROBE_NOTE_MODE != 'off' and bool(probe):
            out.append('试盘观察：长上影测试抛压')
        # 出货形态确认文案（默认 'watch'；与「出货风险警示」并列，不替代）
        if _DISTP_NOTE_MODE != 'off' and distpat:
            out.append('出货形态观察：%s' % distpat)
        # 拉升阶段识别文案（默认 'watch'；与试盘/出货形态同为观察类，方向见常量注释）
        if _MARKUP_NOTE_MODE != 'off' and markup:
            out.append('拉升观察：%s' % markup)
        # A 破位—收复（默认 'watch'）：只出风险侧文案，洗盘侧只写字段（依据见 _BRK_NOTE_MODE）
        if _BRK_NOTE_MODE != 'off' and brk == '破位未收':
            out.append('破位警示：放量破位未收回')
        # B 量能分位（默认 'watch'）：天量出警示；缩量上涨只在 pos<0.45 出（依据见 _VREG_NOTE_MODE）
        if _VREG_NOTE_MODE != 'off' and vreg:
            _vt = [x for x in str(vreg).split('|') if x]
            if '天量' in _vt:
                out.append('天量警示')
            if '缩量上涨' in _vt and pos is not None and pos < 0.45:
                out.append('缩量上涨·疑似控盘')
    except Exception:
        return out
    return out


def _to_weekly(bars):
    """日K转周K"""
    if not bars:
        return []
    weeks = {}
    order = []
    for b in bars:
        d = b['date'][:10]
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        import datetime as _dt
        wk = _dt.date(y, m, dd).isocalendar()[1]
        key = f'{y}-W{wk:02d}'
        if key not in weeks:
            weeks[key] = {'date': d, 'open': b['open'], 'high': b['high'],
                          'low': b['low'], 'close': b['close'], 'volume': 0}
            order.append(key)
        w = weeks[key]
        w['high'] = max(w['high'], b['high'])
        w['low'] = min(w['low'], b['low'])
        w['close'] = b['close']
        w['volume'] += b['volume']
    return [weeks[k] for k in order]


# ==================================================================
# 环境分 env_score：当日可观测的市场 / 行业温度
#   目的：按市场轮动状态自动伸缩建仓力度，而不是固守一套标准。
#   依据 2025 全年 3564 条历史触发的分档实测：
#     行业涨停 >=3家 : +0.59~+0.83%   |  0家 : -0.63%
#     行业均涨 1~3%  : +0.53%         |  >3% 过热(一日游) : +0.14%
#     行业上涨占比>70%: 收益归零        |  30~70% : +0.28%
#     大盘杀跌<-1.5% : +2.05%(逆势真强) |  >1.5% 普涨 : -0.85%
#     个股振幅<4%    : +0.41%         |  >7% : -0.73%
#     个股量比<1.0   : +0.98%         |  >2.5 : 缩量更优
#   分档执行： >=6 正常建仓 / 3~5 谨慎 / <=2 不建仓
# ==================================================================
_ENV_CTX = {'ready': False, 'ind_map': {}, 'ind_stat': {}, 'market': {}}


def _build_env_context(verbose=False):
    """扫描前构建当日市场/行业环境截面。

    数据源：data/cache/kline_cache.duckdb 的最新两个交易日收盘价。
    失败时不抛异常（返回 ready=False），扫描照常进行，只是环境分退化为只看个股自身。
    """
    global _ENV_CTX
    ctx = {'ready': False, 'ind_map': {}, 'ind_stat': {}, 'market': {}}
    try:
        import duckdb
        kp = os.path.join(DB_DIR, 'kline_cache.duckdb')
        if not os.path.exists(kp):
            if verbose:
                print('[日K建仓] 未找到 kline_cache.duckdb，环境分退化为个股自身', flush=True)
            _ENV_CTX = ctx
            return ctx
        con = duckdb.connect(kp, read_only=True)
        try:
            ds = [r[0] for r in con.execute(
                'SELECT DISTINCT date FROM kline_cache ORDER BY date DESC LIMIT 2').fetchall()]
            if len(ds) < 2:
                _ENV_CTX = ctx
                return ctx
            d_now, d_prev = str(ds[0])[:10], str(ds[1])[:10]
            rows = con.execute(
                'SELECT code, date, close FROM kline_cache WHERE date IN (?, ?)',
                [d_now, d_prev]).fetchall()
        finally:
            con.close()
        px = {}
        for code, d, c in rows:
            px.setdefault(code, {})[str(d)[:10]] = c
        pcts = {}
        for code, m in px.items():
            now_c, prev_c = m.get(d_now), m.get(d_prev)
            if now_c and prev_c and prev_c > 0:
                pcts[code] = (now_c - prev_c) / prev_c * 100
        if not pcts:
            _ENV_CTX = ctx
            return ctx
        try:
            ind_map = json.load(open(os.path.join(DB_DIR, 'industry_full_map.json'),
                                     encoding='utf-8'))
        except Exception:
            ind_map = {}
        agg = {}
        for code, p in pcts.items():
            agg.setdefault(ind_map.get(code, '未知'), []).append((code, p))
        ind_stat = {}
        for ind, ps in agg.items():
            ind_stat[ind] = {
                'n': len(ps),
                'avg': sum(x for _c, x in ps) / len(ps),
                'limitup': sum(1 for c, x in ps if x >= _lu_threshold(c)),
                'up_ratio': sum(1 for _c, x in ps if x > 0) / len(ps) * 100,
            }
        allp = list(pcts.items())
        ctx.update(ready=True, ind_map=ind_map, ind_stat=ind_stat,
                   market={'avg': sum(x for _c, x in allp) / len(allp),
                           'up_ratio': sum(1 for _c, x in allp if x > 0) / len(allp) * 100,
                           'limitup': sum(1 for c, x in allp if x >= _lu_threshold(c)),
                           'date': d_now})
        _ENV_CTX = ctx
        if verbose:
            print('[日K建仓] 环境截面 date=%s 行业%d个 大盘均涨%+.2f%% 涨停%d家 上涨占比%.0f%%' % (
                d_now, len(ind_stat), ctx['market']['avg'],
                ctx['market']['limitup'], ctx['market']['up_ratio']), flush=True)
    except Exception as e:
        if verbose:
            print('[日K建仓] 环境截面构建失败(不影响扫描): %s' % e, flush=True)
        _ENV_CTX = ctx
    return ctx


def _env_score_for(code, amp=None, vr=None):
    """环境分。返回 (score, note)。score>=6 正常建仓 / 3~5 谨慎 / <=2 不建仓。"""
    s = 0
    notes = []
    ctx = _ENV_CTX
    if ctx.get('ready'):
        ind = ctx['ind_map'].get(code, '未知')
        st = ctx['ind_stat'].get(ind, {})
        lu = st.get('limitup', 0)
        if lu >= 3:
            s += 2
            notes.append('行业涨停%d家' % lu)
        elif lu == 0:
            s -= 2
            notes.append('行业无涨停')
        avg = st.get('avg', 0)
        if 1 <= avg < 3:
            s += 2
            notes.append('行业温和%+.1f%%' % avg)
        elif avg > 3:
            s -= 1
            notes.append('行业过热%+.1f%%' % avg)
        elif avg < -1:
            s -= 1
            notes.append('行业杀跌%+.1f%%' % avg)
        upr = st.get('up_ratio', 0)
        if upr > 70:
            s -= 2
            notes.append('行业普涨%.0f%%' % upr)
        elif upr >= 30:
            s += 1
        m = ctx.get('market', {})
        mavg = m.get('avg', 0)
        if mavg < -1.5:
            s += 2
            notes.append('大盘杀跌%+.1f%%' % mavg)
        elif 0.5 <= mavg <= 1.5:
            s += 1
            notes.append('大盘温和%+.1f%%' % mavg)
        elif mavg > 1.5:
            s -= 2
            notes.append('大盘普涨%+.1f%%' % mavg)
    if amp is not None:
        if amp < 4:
            s += 1
        elif amp > 7:
            s -= 1
            notes.append('振幅%.1f%%偏大' % amp)
    if vr is not None:
        if 0 < vr < 1.0:
            s += 1
            notes.append('缩量')
        elif vr > 2.5:
            s -= 1
            notes.append('巨量')
    return s, ','.join(notes)


# ==================================================================
# 题材强度（V10，2026-09-27）
# ==================================================================
# 用户确认口径：行业权重 0.4 / 概念权重 0.6，建仓价修正上限 ±0.4×ATR，
#               题材闸门 t < -0.4 直接剔除候选。
# 数据源（都不需要外网）：
#   - 行业项：_ENV_CTX['ind_stat']（来自 industry_full_map.json + kline_cache.duckdb）
#   - 概念项：data/limit_up_reason.db 表 limit_up_reasons（涨停原因历史库）
_THEME_CTX = {'ready': False, 'concept_cnt': {}, 'code_info': {}, 'date': None}
_THEME_W_IND = 0.4        # 行业权重
_THEME_W_CON = 0.6        # 概念权重
_THEME_SHIFT_CAP = 0.4    # 建仓价修正上限（×ATR）
_THEME_GATE = -0.4        # 题材闸门：t 低于此值不进候选


def _build_theme_context(verbose=False):
    """扫描前构建当日题材热度截面。

    concept_cnt : 最新交易日各题材出现次数（= 当日题材热度）
    code_info   : {code: (题材, 距今交易日数)} 每只股票最近一次涨停的题材
    date        : 最新涨停日期
    失败时 ready=False，题材因子退化为 0，不抛异常、不影响扫描。
    """
    global _THEME_CTX
    ctx = {'ready': False, 'concept_cnt': {}, 'code_info': {}, 'date': None}
    try:
        dbp = os.path.join(PROJECT_ROOT, 'data', 'limit_up_reason.db')
        if not os.path.exists(dbp):
            if verbose:
                print('[日K建仓] 未找到 limit_up_reason.db，题材因子退化为 0', flush=True)
            _THEME_CTX = ctx
            return ctx
        con = sqlite3.connect(dbp)
        con.row_factory = sqlite3.Row
        try:
            dates = [str(r[0]) for r in con.execute(
                'SELECT DISTINCT date FROM limit_up_reasons ORDER BY date ASC').fetchall()]
            if not dates:
                _THEME_CTX = ctx
                return ctx
            latest = dates[-1]
            didx = {}
            for _i, _d in enumerate(dates):
                didx[_d] = _i
            _n = len(dates)
            # 当日题材热度
            c_cnt = {}
            for r in con.execute(
                    'SELECT reason FROM limit_up_reasons WHERE date=?', (latest,)):
                for _part in str(r[0] or '').split('+'):
                    _p = _part.strip()
                    if _p:
                        c_cnt[_p] = c_cnt.get(_p, 0) + 1
            # 每只股票最近一次涨停的题材 + 距今交易日数
            info = {}
            for r in con.execute(
                    'SELECT code, reason, MAX(date) AS d'
                    ' FROM limit_up_reasons GROUP BY code'):
                _code = r['code']
                _d = str(r['d'] or '')
                if not _code or not _d:
                    continue
                _reason = str(r['reason'] or '').split('+')[0].strip()
                _ago = (_n - 1 - didx[_d]) if _d in didx else 999
                info[_code] = (_reason, _ago)
            ctx.update(ready=True, concept_cnt=c_cnt, code_info=info, date=latest)
            _THEME_CTX = ctx
            if verbose:
                print('[日K建仓] 题材截面 date=%s 题材%d个 涨停股%d只' % (
                    latest, len(c_cnt), len(info)), flush=True)
        finally:
            con.close()
    except Exception as e:
        if verbose:
            print('[日K建仓] 题材截面构建失败(不影响扫描): %s' % e, flush=True)
        _THEME_CTX = ctx
    return ctx


def _theme_strength(code):
    """题材强度 t ∈ [-1, 1]：行业项 0.4 + 概念项 0.6（概念含时效衰减）。

    行业项（来自 _ENV_CTX['ind_stat']）：
        涨停 >=3 家 +0.5 / 无涨停 -0.5 / 均涨 >=2% +0.3 / >=0.5% +0.15 / <=-1% -0.3
    概念项（来自涨停原因库，含时效衰减）：
        当日该题材涨停家数 >=8 +0.5 / >=3 +0.3 / ==2 +0.15 / ==1 +0.05 / 未上榜 -0.2
        时效：距上次涨停 <=3 日 x1.0 / <=10 日 x0.6 / <=20 日 x0.3 / 更久 x0
    无数据时返回 0.0（不改变建仓价，也不触发闸门）。
    """
    if not code or not _THEME_CTX.get('ready'):
        return 0.0
    # ---- 行业项 ----
    t_ind = 0.0
    try:
        _ind = (_ENV_CTX.get('ind_map') or {}).get(code)
        _st = (_ENV_CTX.get('ind_stat') or {}).get(_ind) if _ind else None
        if _st:
            _lu = _st.get('limitup', 0) or 0
            _avg = _st.get('avg', 0.0) or 0.0
            if _lu >= 3:
                t_ind += 0.5
            elif _lu == 0:
                t_ind -= 0.5
            if _avg >= 2.0:
                t_ind += 0.3
            elif _avg >= 0.5:
                t_ind += 0.15
            elif _avg <= -1.0:
                t_ind -= 0.3
    except Exception:
        t_ind = 0.0
    if t_ind > 1.0:
        t_ind = 1.0
    elif t_ind < -1.0:
        t_ind = -1.0
    # ---- 概念项（含时效衰减）----
    t_con = 0.0
    try:
        _ci = _THEME_CTX['code_info'].get(code)
        if _ci:
            _concept, _ago = _ci
            _cnt = _THEME_CTX['concept_cnt'].get(_concept, 0)
            if _cnt >= 8:
                t_con = 0.5
            elif _cnt >= 3:
                t_con = 0.3
            elif _cnt == 2:
                t_con = 0.15
            elif _cnt == 1:
                t_con = 0.05
            else:
                t_con = -0.2
            if _ago <= 3:
                _dec = 1.0
            elif _ago <= 10:
                _dec = 0.6
            elif _ago <= 20:
                _dec = 0.3
            else:
                _dec = 0.0
            t_con = t_con * _dec
    except Exception:
        t_con = 0.0
    _t = _THEME_W_IND * t_ind + _THEME_W_CON * t_con
    if _t > 1.0:
        return 1.0
    if _t < -1.0:
        return -1.0
    return _t


def _theme_shift(t, atr):
    """题材修正量：0.4 × t × ATR，夹在 ±0.4×ATR 内。

    题材强 -> 建仓价上移（强势不必等太深，避免踏空）
    题材弱 -> 建仓价下移（要更厚的安全垫）
    """
    if not atr:
        return 0.0
    _cap = _THEME_SHIFT_CAP * atr
    _s = _THEME_SHIFT_CAP * t * atr
    if _s > _cap:
        return _cap
    if _s < -_cap:
        return -_cap
    return _s


def _theme_note(code):
    """调试用：返回题材强度的构成明细字符串。"""
    if not code or not _THEME_CTX.get('ready'):
        return 't=0(无数据)'
    _t = _theme_strength(code)
    _ci = _THEME_CTX['code_info'].get(code)
    if _ci:
        _c, _a = _ci
        _n = _THEME_CTX['concept_cnt'].get(_c, 0)
        return 't=%.3f 题材[%s]当日%d家 距今%d日' % (_t, _c, _n, _a)
    return 't=%.3f (无涨停题材)' % _t


# ==================================================================
# DB 初始化（V5.0 新字段）
# ==================================================================
# 字段全集（CREATE 和 ALTER 共用，避免漏字段导致 INSERT 失败）
_ALL_COLS = [
    ('code', 'TEXT NOT NULL'), ('pattern_id', 'INTEGER NOT NULL'),
    ('base_date', 'TEXT NOT NULL'), ('push_date', 'TEXT'),
    ('name', 'TEXT'), ('pattern_name', 'TEXT'),
    ('base_close', 'REAL'), ('base_high', 'REAL'), ('base_low', 'REAL'),
    ('push_price', 'REAL'), ('push_pct', 'REAL'),
    ('ma5', 'REAL'), ('ma20', 'REAL'),
    ('volume_ratio', 'REAL'), ('gap_pct', 'REAL'), ('structure_days', 'INTEGER'),
    ('signal_level', 'TEXT'), ('trigger_type', 'TEXT'), ('trigger_price', 'REAL'),
    ('invalid_price', 'REAL'), ('weekly_confirm', 'INTEGER'),
    ('valid_until', 'TEXT'), ('invalid_reason', 'TEXT'),
    ('up_days', 'INTEGER'), ('up_vol_ok', 'INTEGER'), ('up_rate', 'REAL'),
    ('down_days', 'INTEGER'), ('down_vol_ok', 'INTEGER'), ('down_rate', 'REAL'),
    ('struct_pos', 'REAL'), ('recent_vol3', 'INTEGER'),
    ('shake_dip', 'REAL'), ('shake_shadow', 'REAL'), ('shake_probe', 'REAL'),
    ('shake_amp', 'REAL'), ('shake_ok', 'INTEGER'),
    ('take_profit', 'REAL'), ('env_score', 'INTEGER'), ('env_note', 'TEXT'),
    ('control_score', 'REAL'), ('stage_guess', 'TEXT'),
    ('stack_vol_score', 'REAL'), ('red_fat_score', 'REAL'),
    ('c4_ok', 'INTEGER'), ('c4_score', 'REAL'),
    ('c6_ok', 'INTEGER'), ('c6_score', 'REAL'),
    ('ctrl_tag', 'TEXT'),   # 只存「控盘提示」（候选/出货/洗盘），UI 取短标签用这列
    ('probe_ok', 'INTEGER'), ('probe_score', 'REAL'),
    ('dist_pattern_ok', 'INTEGER'), ('dist_pattern_type', 'TEXT'),
    ('dist_pattern_score', 'REAL'),
    ('markup_ok', 'INTEGER'), ('markup_type', 'TEXT'),
    ('markup_score', 'REAL'),
    ('brk_ok', 'INTEGER'), ('brk_type', 'TEXT'), ('brk_score', 'REAL'),
    ('vreg_tags', 'TEXT'), ('vreg_pct', 'REAL'),
    ('note', 'TEXT'), ('created_at', 'TEXT'), ('updated_at', 'TEXT'),
]
_KEY_COLS = {'code', 'pattern_id', 'base_date'}

# 全量扫描时先写暂存表，扫完再原子替换主表 —— 避免 UI 在扫描期间读到半截数据
_STAGE_TABLE = 'pattern_record_new'
_WRITE_TABLE = 'pattern_record'


def _init_db(table_name=None):
    table_name = table_name or 'pattern_record'
    os.makedirs(DB_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        body = ',\n            '.join(f'{n} {t}' for n, t in _ALL_COLS if n not in _KEY_COLS)
        con.execute(f"""CREATE TABLE IF NOT EXISTS {table_name} (
            code TEXT NOT NULL,
            pattern_id INTEGER NOT NULL,
            base_date TEXT NOT NULL,
            {body},
            PRIMARY KEY (code, pattern_id, base_date)
        )""")
        # 兼容旧库：逐个补齐缺失字段
        existing = {r[1] for r in con.execute(f"PRAGMA table_info({table_name})").fetchall()}
        added = []
        for col, typ in _ALL_COLS:
            if col not in existing:
                t = typ.replace(' NOT NULL', '').replace(' TEXT', ' TEXT')
                con.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {t}")
                added.append(col)
        con.commit()
        if added:
            print(f'[日K建仓] DB补齐字段({table_name}): {added}', flush=True)
    finally:
        con.close()


def _atomic_swap(stage=None, main='pattern_record'):
    """把暂存表原子替换成主表。整个 DROP+RENAME 在一个事务里完成。

    成功 -> 主表瞬间变成本次扫描结果，读者要么看到旧数据要么看到新数据，不存在中间态。
    失败 -> ROLLBACK，主表原样保留（上一次的完整结果），并打印告警。
    """
    stage = stage or _STAGE_TABLE
    con = sqlite3.connect(DB_PATH, isolation_level=None, timeout=30)
    try:
        con.execute('PRAGMA busy_timeout=30000')
        con.execute('BEGIN IMMEDIATE')
        con.execute(f'DROP TABLE IF EXISTS {main}')
        con.execute(f'ALTER TABLE {stage} RENAME TO {main}')
        con.execute('COMMIT')
        return True
    except Exception as e:
        try:
            con.execute('ROLLBACK')
        except Exception:
            pass
        print(f'[日K建仓] 结果切换失败，主表保留上一次数据: {e}', flush=True)
        return False
    finally:
        con.close()


def _save_or_update(rec, table_name=None):
    """INSERT OR REPLACE，主键存在则覆盖。
    table_name 缺省用 _WRITE_TABLE —— 全量扫描期间指向暂存表。"""
    tbl = table_name or _WRITE_TABLE
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(f"""INSERT OR REPLACE INTO {tbl}
            (code, pattern_id, base_date, push_date, name, pattern_name,
             base_close, base_high, base_low, push_price, push_pct,
             ma5, ma20, volume_ratio, gap_pct, structure_days,
             signal_level, trigger_type, trigger_price, invalid_price,
             weekly_confirm, valid_until, invalid_reason, note,
             up_days, up_vol_ok, up_rate, down_days, down_vol_ok, down_rate,
             struct_pos, recent_vol3, shake_dip, shake_shadow, shake_probe,
             shake_amp, shake_ok, take_profit, env_score, env_note,
             control_score, stage_guess,
             stack_vol_score, red_fat_score,
             c4_ok, c4_score,
             c6_ok, c6_score, ctrl_tag,
             probe_ok, probe_score,
             dist_pattern_ok, dist_pattern_type, dist_pattern_score,
             markup_ok, markup_type, markup_score,
             brk_ok, brk_type, brk_score, vreg_tags, vreg_pct,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            rec['code'], rec['pattern_id'], rec['base_date'], rec['push_date'],
            rec.get('name',''), rec.get('pattern_name',''),
            rec.get('base_close'), rec.get('base_high'), rec.get('base_low'),
            rec.get('push_price'), rec.get('push_pct'),
            rec.get('ma5'), rec.get('ma20'), rec.get('volume_ratio'),
            rec.get('gap_pct'), rec.get('structure_days'),
            rec.get('signal_level',LVL_WATCH), rec.get('trigger_type',''),
            rec.get('trigger_price'), rec.get('invalid_price'),
            rec.get('weekly_confirm',0), rec.get('valid_until',''),
            rec.get('invalid_reason',''), rec.get('note',''),
            rec.get('up_days',0), rec.get('up_vol_ok',0), rec.get('up_rate',0),
            rec.get('down_days',0), rec.get('down_vol_ok',0), rec.get('down_rate',0),
            rec.get('struct_pos',0), rec.get('recent_vol3',0),
            rec.get('shake_dip',0), rec.get('shake_shadow',0),
            rec.get('shake_probe',0), rec.get('shake_amp',0), rec.get('shake_ok',0),
            rec.get('take_profit',0), rec.get('env_score',0), rec.get('env_note',''),
            rec.get('control_score',0), rec.get('stage_guess','unknown'),
            rec.get('stack_vol_score',0), rec.get('red_fat_score',0),
            rec.get('c4_ok',0), rec.get('c4_score',0),
            rec.get('c6_ok',0), rec.get('c6_score',0),
            rec.get('ctrl_tag',''),
            rec.get('probe_ok',0), rec.get('probe_score',0),
            rec.get('dist_pattern_ok',0), rec.get('dist_pattern_type',''),
            rec.get('dist_pattern_score',0),
            rec.get('markup_ok',0), rec.get('markup_type',''),
            rec.get('markup_score',0),
            rec.get('brk_ok',0), rec.get('brk_type',''), rec.get('brk_score',0),
            rec.get('vreg_tags',''), rec.get('vreg_pct'),
            rec.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        con.commit()
    finally:
        con.close()


def expire_overdue():
    """自动失效：把已超过 valid_until 的记录标记为失效（观察/等待确认/建仓触发）"""
    today = datetime.now().strftime('%Y-%m-%d')
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute(
            "UPDATE pattern_record SET signal_level=?, invalid_reason=?, updated_at=? "
            "WHERE pattern_id = 3 AND valid_until != '' AND valid_until < ? "
            "AND signal_level IN (?,?,?)",
            (LVL_INVALID, '已超过有效观察期',
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             today, LVL_TRIGGER, LVL_WAIT, LVL_WATCH))
        n = cur.rowcount
        con.commit()
    except Exception as e:
        n = 0
        print(f'[日K建仓] 自动失效失败: {e}', flush=True)
    finally:
        con.close()
    return n


def query_signals():
    """UI读全部信号，按signal_level排序：触发>等待>观察>失效"""
    try:
        expire_overdue()
    except Exception:
        pass
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        level_order = {LVL_TRIGGER: 0, LVL_WAIT: 1, LVL_WATCH: 2, LVL_INVALID: 3}
        rows = con.execute("SELECT * FROM pattern_record").fetchall()
        result = [dict(r) for r in rows]
        result.sort(key=lambda x: (level_order.get(x.get('signal_level',''),9),
                                   -(x.get('volume_ratio') or 0)))
        return result
    finally:
        con.close()


# ==================================================================
# 四个模式状态机识别
# ==================================================================

# 模式三（合并版：横盘周K）漏斗统计（scan_all 开始时重置，detect_pattern_bottom 内累加）
#   wk      : 本周量 >= 上周量 x1.3 且 本周收阳            （第一关）
#   struct  : 再叠加 横盘窗口成立（振幅/低点/量价）          （第二关）
#   trigger : 再叠加 本周收盘 > 横盘上沿 = 最终建仓触发      （第三关）
#   invalid : 周K达标但找不到合格横盘窗口
_M4_FUNNEL = {'wk': 0, 'struct': 0, 'trigger': 0, 'invalid': 0, 'theme': 0,
               'entry_far': 0, 'ma20_below': 0}

# 模式一（合并版：激进）漏斗统计（scan_all 开始时重置，detect_pattern_aggressive 内累加）
#   s_ok    : 找到合格启动日 S（实体>=3% + 涨幅>=3% + 量>=1.0倍）
#   d_ok    : 再叠加 洗盘日 D 跳空高开（D.open > S.high）
#   struct  : 再叠加 缩量整理成立（>=5日 / 十字星 / 缩量<=1.5 / 剔除长阴 / 通则）
#   trigger : 再叠加 回踩MA5 -> 最终建仓触发
_M1_FUNNEL = {'s_ok': 0, 'd_ok': 0, 'struct': 0, 'trigger': 0, 'theme': 0,
               'entry_far': 0, 'ma20_below': 0}

# ==================================================================

def detect_pattern_aggressive(bars, code=None):
    """模式一（合并版）：【激进】
    启动大阳 S → 次日洗盘日 D 跳空高开/冲高回落 → 缩量整理 → 回踩5日线建仓

    V8 合并说明（2026-09-27）：
        原「模式一 跳空高开」与「模式二 大阳整理」形态相近，用户要求合并成一个模式，
        模式名定为「激进」，采用方案 B：D跳空 + 剔除长阴 + 回踩MA5。

    依据：2026-09-26/27 用用户圈定的 14 个真实案例逐条取证（_probe_merge12f.py）。
    关键发现：用户圈选的"基准日"是**洗盘回落日 D**（不是启动日），
              启动日 S 稳定落在 D 的前 1~2 个交易日。

    【阶段① 启动日 S】（洗盘日 D 的前 1~2 个交易日）
        实体涨幅 (close-open)/open >= 3%      —— 14 案例 14/14
        当日涨幅 (close-前收)/前收 >= 3%      —— 14 案例 14/14
        成交量 >= 前5日均量 × 1.0             —— 14 案例 13/14（p5 不含当根、不含未来）

    【阶段② 洗盘日 D = S 后第 1~2 个交易日】（V9：D 只在最近 15 个交易日内搜索）
        跳空：D.open > S.high                 —— 方案 B 硬条件（取证 D开>S高 8/14）

    【阶段③ 缩量整理（D 之后）】
        整理期 >= 5 个交易日                   —— 14 案例 14/14
        出现 >= 1 根十字星（实体<=1%）         —— 14 案例 14/14
        整理期均量 <= 启动日量 × 1.5            —— 14 案例 14/14
        剔除长阴：任一交易日 跌幅<=-5% 且 量>=启动日量×0.8 → 整个模式剔除

    【阶段④ 通则】（用户明确要求按通则处理）
        整理期最低收盘 >= 启动日的前一日收盘
        跌破 → 模式失效

    【信号】
        🟢 建仓触发：今日回踩 MA5（±1.5%）且收盘站在 MA5 上，且量比 >= 1.0
        🟡 等待确认：结构成立但尚未回踩

    【建仓价 / 失效价】
        建仓价 = MA5 - 0.3×ATR + 共振修正，夹在 [通则线×1.002, 现价×1.01]
        失效价 = 通则线（启动日前一日收盘）
    """
    if len(bars) < 30:
        return None
    closes = [b['close'] for b in bars]
    vols = [b['volume'] for b in bars]
    today = bars[-1]
    ma5_today = _ma(closes, 5)
    ma20_today = _ma(closes, 20)
    if not ma5_today or not ma20_today:
        return None

    # D（洗盘日）在最近 15 个交易日内倒序搜索（V9 收窄：原为 25 天，用户 2026-09-27 确认
    # 15 日口径）；D 之后必须还有 >=5 根，缩量整理才算数。
    # i 从 len-6 递减到 len-16 => ds = len-1-i 从 5 递增到 15
    for i in range(len(bars) - 6, max(3, len(bars) - 17), -1):
        d = bars[i]
        # ---------- 阶段①②：找启动日 S，并校验洗盘日 D ----------
        s = None
        for k in (i - 1, i - 2):
            if k < 6:
                continue
            b, p = bars[k], bars[k - 1]
            if not b['open'] or not p['close']:
                continue
            body = (b['close'] - b['open']) / b['open'] * 100
            pct = (b['close'] - p['close']) / p['close'] * 100
            if body < 3.0 or pct < 3.0:
                continue
            p5v = _ma(vols[max(0, k - 5):k], 5)
            if not p5v or b['volume'] < p5v * 1.0:
                continue
            # 洗盘日 D 必须跳空于 S 的最高价 —— 方案 B 的硬条件，对齐取证 g_high > 0
            if d['open'] <= b['high']:
                continue
            s = k
            break
        if s is None:
            continue
        sc = bars[s]
        sp = bars[s - 1]
        _M1_FUNNEL['s_ok'] += 1
        gap_pct = (d['open'] - sc['high']) / sc['high'] * 100
        _M1_FUNNEL['d_ok'] += 1

        # ---------- 阶段③：缩量整理 ----------
        seg = bars[i + 1:]
        if len(seg) < 5:
            continue
        # 剔除长阴：整理期任一交易日 跌幅<=-5% 且 量>=启动日量×0.8
        has_big_dn = False
        for b in seg:
            if not b['open']:
                continue
            drop = (b['close'] - b['open']) / b['open']
            if drop <= -0.05 and b['volume'] >= sc['volume'] * 0.8:
                has_big_dn = True
                break
        if has_big_dn:
            continue
        # 缩量：整理期均量 <= 启动日量 × 1.5
        avg_seg_vol = sum(b['volume'] for b in seg) / len(seg)
        if sc['volume'] and avg_seg_vol > sc['volume'] * 1.5:
            continue
        # 十字星 >= 1 根（实体 <= 1%，与取证 cross 口径一致）
        has_small = any(
            abs(b['close'] - b['open']) / b['open'] <= 0.01
            for b in seg if b['open'] > 0)
        if not has_small:
            continue
        # ---------- 阶段④：通则 ----------
        rule_line = sp['close']           # 启动日的前一日收盘 = 通则线
        min_close = min(b['close'] for b in seg)
        if min_close < rule_line:
            continue
        _M1_FUNNEL['struct'] += 1

        # ---------- 阶段⑤：启动前闸门（V9，2026-09-27 用户确认 15 日口径） ----------
        # 为什么加：原版只要结构成立就无条件入表，导致已涨一波 / 已连板 / 已飞离5日线 /
        #           贴顶的票全都挂在"等待确认"里，用户明确要求"买在启动前，不要接飞刀"。
        # 实测（242 只等待确认逐只读K线）：距MA5 超 ±3% 占 46.7%、近10日有涨停占 31.8%、
        #           比启动日高 >10% 占 17.8%、启动至今 >10 日占 68%。
        # 六条闸门：任一条不满足 -> continue（继续往前找更早的 D，不会误放行）
        _ds = len(bars) - 1 - s                      # 启动日距今交易日
        if _ds > 15:
            continue
        _vs = (closes[-1] - sc['close']) / sc['close'] * 100   # 现价相对启动日
        if _vs > 15:
            continue
        _d5 = (closes[-1] - ma5_today) / ma5_today * 100       # 距 MA5
        if not (-2.0 <= _d5 <= 3.0):
            continue
        _mlb = _cur = 0                              # 近 10 日最大连板
        for _j in range(max(1, len(bars) - 10), len(bars)):
            if bars[_j]['close'] >= bars[_j - 1]['close'] * 1.095:
                _cur += 1
                if _cur > _mlb:
                    _mlb = _cur
            else:
                _cur = 0
        if _mlb >= 2:
            continue
        if bars[-2]['close']:
            _tp = (today['close'] - bars[-2]['close']) / bars[-2]['close'] * 100
            if _tp >= 5:
                continue
        _hi25 = max(b['high'] for b in bars[-25:])   # 25 日结构位
        _lo25 = min(b['low'] for b in bars[-25:])
        if _hi25 > _lo25:
            _p25 = (closes[-1] - _lo25) / (_hi25 - _lo25) * 100
            if _p25 >= 95:
                continue

        # ---------- 题材闸门（V10，2026-09-27 用户确认启用） ----------
        # 题材冷（t < -0.4）= 行业无涨停 + 概念没上当日涨停榜 = 没有资金接力，
        # 形态再好也走不远。放在触发判定之前，因此对「触发」和「等待确认」同时生效。
        _th_t = _theme_strength(code)
        if _th_t < _THEME_GATE:
            _M1_FUNNEL['theme'] += 1
            continue

        # 等待确认档的参考止盈价（分时做T口径），触发档保持 0（走 建仓价x1.03）
        _t_tp = 0

        # ---------- 触发：回踩 MA5 ----------
        vol_ratio = today['volume'] / (_ma(vols[-6:-1], 5) or 1)
        touch_ma5 = abs(today['close'] - ma5_today) / ma5_today <= 0.015
        stand_ma5 = today['close'] >= ma5_today
        if touch_ma5 and stand_ma5 and vol_ratio >= 1.0:
            level = LVL_TRIGGER
            trig_type = '激进·建仓触发'
            # 建仓价：5日线是主力洗盘结束的回踩位，向下让 0.3 个ATR做缓冲；
            # 硬边界 = 通则线（跌破即结构失效）
            _atr = _atr14(bars) or (closes[-1] * 0.02)
            _f = _resonance_f(bars)
            _entry = (ma5_today - 0.3 * _atr + _entry_shift(_f, _atr)
                      + _theme_shift(_th_t, _atr))
            _entry = max(_entry, rule_line * 1.002)
            _entry = min(_entry, closes[-1] * 1.01)
            trig_price = round(_entry, 2)
            # V11 建仓价闸门：建仓价距现价过远 -> 不产生「建仓触发」
            _gap_b = ((closes[-1] - _entry) / closes[-1] * 100
                      if closes[-1] > 0 else 0)
            if _gap_b > _ENTRY_GAP_CAP:
                _M1_FUNNEL['entry_far'] += 1
                return None
            _M1_FUNNEL['trigger'] += 1
        else:
            level = LVL_WAIT
            trig_type = '等待MA5回踩'
            # V12：等待确认还没有 MA5 回踩价，借用「分时做T」口径给出参考买卖价
            #   VWAP = (最高 + 最低 + 收盘) / 3
            #   买点 = VWAP - (0.3 - 0.1f) x ATR
            #   卖点 = VWAP + (0.3 + 0.1f) x ATR
            # 与 ui/battle_widgets/atr_t_widget.py 的分时做T完全同口径
            # （分时做T的 day_high/day_low/price 在收盘后即等于当日 H/L/C）。
            _t_vwap = (today['high'] + today['low'] + today['close']) / 3.0
            _t_atr = _atr14(bars) or (closes[-1] * 0.02)
            _t_f = _resonance_f(bars)
            _t_kb = 0.3 - 0.1 * _t_f
            _t_ks = 0.3 + 0.1 * _t_f
            trig_price = round(_t_vwap - _t_kb * _t_atr, 2)
            # 封顶：等待确认档的建仓价不得高于现价
            # （收盘落在日内区间下部时 VWAP 会高于收盘，买点会略微高出现价）
            _t_cap = round(today['close'], 2)
            if trig_price > _t_cap:
                trig_price = _t_cap
            _t_tp = round(_t_vwap + _t_ks * _t_atr, 2)

        s_pct = (sc['close'] - sp['close']) / sp['close'] * 100
        return {
            'pattern_id': PATTERN_AGGRESSIVE,
            'base_date': sc['date'],
            'base_close': round(sc['close'], 2),
            'base_high': round(sc['high'], 2),
            'base_low': round(rule_line, 2),
            'gap_pct': round(gap_pct, 2),
            'structure_days': len(seg),
            'volume_ratio': round(sc['volume'] / (_ma(vols[max(0, s - 5):s], 5) or 1), 2),
            'signal_level': level,
            'trigger_type': trig_type,
            'trigger_price': trig_price,
            'take_profit': _t_tp,
            'invalid_price': round(rule_line, 2),
            'valid_until': _valid_until(bars, i, 20),
            'note': '%s启动%.2f(+%.1f%%) → %s跳空%.2f%%洗盘 → 缩量整理%d日，%s' % (
                sc['date'], sc['close'], s_pct, d['date'], gap_pct, len(seg),
                '回踩MA5站回，建仓触发' if level == LVL_TRIGGER
                else '等MA5回踩（建仓价/止盈价暂用分时做T口径 VWAP±k·ATR）'),
        }
    return None


def detect_pattern_bottom(bars, code=None):
    """模式三（合并版）：底部横盘 → 周K放量突破 → 建仓

    V7 合并说明：原「模式三 底部横盘」和「模式四 周K确认」形态相近，合并成一个模式。
    核心链条（用户 2026-09-26 确认）：
        底部横盘期：阳线成交温和放量抬升、阴线缩量回撤、价格低点逐渐抬高
        → 本周成交量 > 上周成交量（放量）且本周收阳线，且现价结构位落在 [70%,98%]
          （贴在上沿下面、还没突破 —— V9 改，原版要求"已突破"是追涨口径）
        → 建仓

    【横盘窗口】8 ~ 40 个交易日，从长到短取第一个全部通过者：
        1. 结构振幅 <= 25%
        2. 后半段最低价 > 前半段最低价（低点抬高）
        3. 上涨日 量 >= 前5日均量 x1.3  至少出现 1 次
        4. 后半段收盘均价 > 前半段收盘均价（价格逐渐抬升）
        5. 下跌日 量 <= 前5日均量 x1.0  满足率 >= 55%
        6. 前5日均量严格取该K线之前5根：p5 = sum(vols[i-5:i]) / 5.0
           —— 不含当根、不含未来

    【触发（周K确认）】三个条件同时成立：
        本周量 >= 上周量 x1.3   AND   本周收阳   AND   本周收盘 > 横盘上沿
      其中「横盘上沿」只用触发周之前的数据计算。绝不能把触发周自己算进去——
      否则当周创新高会把上沿一起顶高，条件永远不成立（前视陷阱）。

    【验证依据】2026-09-26 用 13 个用户圈定的真实案例（国脉文化600640 / 振石股份601112 /
    中视传媒600088 / 西陇科学002584 / 宜宾纸业600793 / 龙版传媒605577 / 德豪润达002005 /
    内蒙新华603230 / 金健米业600127 / 大亚圣象000910 / 北化股份002246 / 澳弘电子605058 /
    华丽家族600503）逐只实测：同一套规则 13/13 全部在用户圈定的启动周触发，零例外。
    实测分布：窗口 14~40 日、振幅 6.4~24.1%、>=1.3倍 1~7 次、
              下跌缩量率 59~100%、触发周倍数 1.48~8.26。
    其中「后半段均价 > 前半段均价」是德豪润达(002005)用出来的：它 8/14 那天既有
    32 日窗口（上沿 2.63，含 6/24 的一次冲高）也有 14 日窗口（上沿 2.45），
    缺了这条会选中 32 日窗口而永久卡死；补上后正好选中 14 日窗口并突破。

    【被数据淘汰、不再参与筛选的指标】
        - MA5 走平向上：13 案例仅 6/13 通过。启动前必有一跌，MA5 天然被压，
          要求它向上等于「等涨起来就买」，会漏掉 7 只正样本。
        - 阳线均量 > 阴线均量：13 案例仅 10/13，最小 0.79。与横盘后期放量洗盘冲突。
      这两项仅作为参考值写入 up_rate/down_rate/struct_pos，不做门槛。

    【V16 启动前震仓/试盘因子（2026-10-09 加）】
      见 _shake_factors()。紧贴启动周之前的 5 个交易日，写库并在 UI tooltip 显示：
        shake_dip / shake_shadow / shake_probe / shake_amp / shake_ok(0~4)
      阈值按 8 只正样本标定。V16 提纯：4 项全过才给「建仓触发」（_SHAKE_MIN_OK=4），
      否则降为「观察」——界面只显示触发+等待，等于不进表。
      同批数据再次否掉两条：阳线均量/阴线均量（中位 1.04）、
      启动前必须地量（中位 0.83）—— 都不要加回来。
    """
    if len(bars) < 60:
        return None
    closes = [b['close'] for b in bars]
    vols = [b['volume'] for b in bars]

    weeks = _to_weekly(bars)
    if len(weeks) < 12:
        return None

    # ---------- 第一关：本周周K放量收阳 ----------
    # 注：最后一周若尚未走完，量取「本周至今累计」，仍与上周完整周量比较。
    #     该判据随本周推进单调变宽松，不会出现中途忽真忽假。
    wi = len(weeks) - 1
    if wi < 1:
        return None
    w_now = weeks[wi]
    w_prev = weeks[wi - 1]
    if not w_prev['volume']:
        return None
    w_mult = w_now['volume'] / w_prev['volume']
    if w_mult < 1.3 or w_now['close'] <= w_now['open']:
        return None
    _M4_FUNNEL['wk'] += 1

    # 触发周第一根日K在 bars 中的下标（按日期定位）
    w_start = w_now['date'][:10]
    si = None
    for i in range(len(bars)):
        if bars[i]['date'][:10] >= w_start:
            si = i
            break
    if si is None or si < 8:
        return None

    # ---------- 第二关：横盘窗口（从长到短，取第一个全通过） ----------
    seg = None
    for length in range(40, 7, -1):
        st = si - length
        if st < 5:
            continue
        cand = bars[st:si]
        hi = max(b['high'] for b in cand)
        lo = min(b['low'] for b in cand)
        if lo <= 0:
            continue
        amp = (hi - lo) / lo
        if amp > 0.25:
            continue
        half = len(cand) // 2
        if half < 2:
            continue
        if min(b['low'] for b in cand[half:]) <= min(b['low'] for b in cand[:half]):
            continue
        # 6. 「价格逐渐抬升」的量化：后半段收盘均价必须高于前半段。
        #    少了这一条，会把「先冲高 -> 阴跌 -> 再横盘」的形态误收成横盘——
        #    前半段那个高会把箱体上沿顶高，导致真启动那周永远突破不了上沿。
        #    实测（2026-09-26）：补上后 13/13 全中，其余 12 只的窗口与上沿完全不变。
        if (sum(b['close'] for b in cand[half:]) / (len(cand) - half)
                <= sum(b['close'] for b in cand[:half]) / half):
            continue
        up_days = up_ok = dn_days = dn_ok = 0
        for gi in range(st, si):
            if gi < 5:
                continue
            p5v = sum(vols[gi - 5:gi]) / 5.0
            if p5v <= 0:
                continue
            b = bars[gi]
            if b['close'] > b['open']:
                up_days += 1
                if b['volume'] / p5v >= 1.3:
                    up_ok += 1
            else:
                dn_days += 1
                if b['volume'] <= p5v * 1.0:
                    dn_ok += 1
        if up_days == 0 or dn_days == 0:
            continue
        if up_ok < 1:
            continue
        if dn_ok * 1.0 / dn_days < 0.55:
            continue
        seg = (len(cand), cand[0]['date'], hi, lo, amp,
               up_days, up_ok, dn_days, dn_ok)
        break
    if seg is None:
        _M4_FUNNEL['invalid'] += 1
        return None
    (seg_n, seg_start, hi, lo, amp, up_days, up_ok, dn_days, dn_ok) = seg
    _M4_FUNNEL['struct'] += 1
    up_rate = up_ok * 100.0 / up_days
    dn_rate = dn_ok * 100.0 / dn_days

    # ---------- 第三关：接近横盘上沿但尚未突破（V9，2026-09-27 口径改） ----------
    # 原版要求 w_now['close'] > hi（周K收盘已经站上横盘上沿）—— 那是"突破后追入"，
    # 与用户"买在启动前"的方向相反，实测 63 只全是已经突破完的。
    # 改为：结构位 = (现价 - 下沿) / (上沿 - 下沿) 落在 [70%, 98%]
    #       即"贴在上沿下面、还没走"，周K放量确认条件（第一关）保持不动。
    if hi <= lo:
        return None
    _pos = (closes[-1] - lo) / (hi - lo) * 100
    if not (70.0 <= _pos <= 98.0):
        return None

    # ---------- 题材闸门（V10，2026-09-27 用户确认启用） ----------
    _th_t = _theme_strength(code)
    if _th_t < _THEME_GATE:
        _M4_FUNNEL['theme'] += 1
        return None

    # ---------- 建仓价 / 止盈 / 失效价 ----------
    _atr = _atr14(bars) or (closes[-1] * 0.02)
    _f = _resonance_f(bars)
    # V14：中枢从 _vwap20 改为「现价」，系数 0.6 -> 0.3（与激进模式同一骨架）。
    #   本模式语义是「周K放量确认之后上车」，建仓参考价应当是「确认那一刻的价格附近」；
    #   VWAP20 是 20 日量加权均价，横盘末期价格抬升后它天然落后现价（实测 33 条里 22 条落后 2~5%），
    #   再叠 -0.6xATR，建仓价距现价普遍 2.5~7.8%，被 V11 闸门（B<=2.5%）砍掉 94%（33 -> 2）。
    #   且 B 越大代表横盘期间放量上涨越多 = 资金介入越明显，闸门方向与形态质量相反。
    _entry = closes[-1] - 0.3 * _atr + _entry_shift(_f, _atr) + _theme_shift(_th_t, _atr)
    _entry = max(_entry, lo * 1.002)          # 跌破横盘最低 = 筑底失败
    _entry = min(_entry, closes[-1] * 1.01)   # 不追高，不高于现价 1%
    trig_price = round(_entry, 2)
    # V11 建仓价闸门：建仓价距现价过远 -> 不产生「建仓触发」
    # V14 换中枢后（现价 - 0.3xATR + 修正）本闸门基本不再触发，保留作兜底
    # （防 ATR 异常放大时给出过远的建仓价）。
    _gap_b = (closes[-1] - _entry) / closes[-1] * 100 if closes[-1] > 0 else 0
    if _gap_b > _ENTRY_GAP_CAP:
        _M4_FUNNEL['entry_far'] += 1
        return None
    _M4_FUNNEL['trigger'] += 1

    recent_vol3 = 0
    for gi in range(max(5, si - 3), si):
        p5v = sum(vols[gi - 5:gi]) / 5.0
        if p5v > 0 and bars[gi]['close'] > bars[gi]['open'] and bars[gi]['volume'] / p5v >= 1.3:
            recent_vol3 = 1
            break

    struct_pos = (round((closes[-1] - lo) / (hi - lo) * 100, 1) if hi > lo else 0)
    # V16：启动前震仓/试盘因子（紧贴启动周之前的 5 个交易日）
    _sk = _shake_factors(bars, si, hi, lo, si - seg_n)
    # V16 提纯：震仓四项全过才给「建仓触发」，否则降为「观察」
    _lvl = (LVL_TRIGGER if _sk['shake_ok'] >= _SHAKE_MIN_OK else LVL_WATCH)
    return {
        'pattern_id': PATTERN_BOTTOM,
        'base_date': seg_start,
        'base_close': round((hi + lo) / 2, 2),
        'base_high': round(hi, 2),
        'base_low': round(lo, 2),
        'structure_days': seg_n,
        'volume_ratio': round(w_mult, 2),
        'signal_level': _lvl,
        'trigger_type': '横盘周K·建仓',
        'trigger_price': trig_price,
        'invalid_price': round(lo, 2),
        'valid_until': _valid_until_cal(bars, 14),
        'weekly_confirm': 1,
        'up_days': up_days, 'up_vol_ok': up_ok, 'up_rate': round(up_rate, 1),
        'down_days': dn_days, 'down_vol_ok': dn_ok, 'down_rate': round(dn_rate, 1),
        'struct_pos': struct_pos,
        'recent_vol3': recent_vol3,
        'shake_dip': _sk['shake_dip'], 'shake_shadow': _sk['shake_shadow'],
        'shake_probe': _sk['shake_probe'], 'shake_amp': _sk['shake_amp'],
        'shake_ok': _sk['shake_ok'],
        'note': '横盘%d日(振幅%.0f%%) 上涨放量%d/%d(%.0f%%) 下跌缩量%d/%d(%.0f%%) '
                '本周%.2f倍放量阳·结构位%.0f%%近上沿%.2f'
                '\n震仓确认%d/4%s｜启动前回撤到箱体%.0f%%·最大下影%.0f%%·'
                '探针MA20%+.1f%%·振幅收敛%.2f' % (
                    seg_n, amp * 100, up_ok, up_days, up_rate,
                    dn_ok, dn_days, dn_rate, w_mult, _pos, hi,
                    _sk['shake_ok'],
                    ('·提纯通过' if _sk['shake_ok'] >= _SHAKE_MIN_OK
                     else '·震仓不足/%d项，降为观察' % _SHAKE_MIN_OK),
                    _sk['shake_dip'], _sk['shake_shadow'],
                    _sk['shake_probe'], _sk['shake_amp']),
    }


# ==================================================================
# 引擎主类
# ==================================================================
class BandPatternEngine:
    def __init__(self):
        _init_db()

    def scan_stock(self, code, name=''):
        # 基础过滤【前置】：保留主板 + 创业板（600/601/603/605/000/001/002/003/300/301），
        # 剔除 ST/退市/科创板/北交所。
        # 这一步不依赖K线，必须在 _load_bars 之前 —— 全市场 5221 只里有 1000+ 只
        # 是科创板/北交所，原先"先取数再过滤"等于每只都白跑一次在线请求
        # （通达信无数据→降级HTTP，约 1.3 秒/只），是全市场扫描慢几十倍的主因。
        if not _is_main_a_share(code) or _is_st(name):
            return []
        bars = _load_bars(code)
        if len(bars) < 30:
            return []
        closes = [b['close'] for b in bars]
        today = bars[-1]
        ma5 = _ma(closes, 5)
        ma20 = _ma(closes, 20)
        if not ma5 or not ma20:
            return []
        # 低价股过滤：最新收盘价低于 MIN_PRICE 元直接剔除
        if today['close'] < MIN_PRICE:
            return []
        # MA20 硬过滤（V15，2026-10-09 补实现）。
        # 原为一条空注释 —— ma20 只被算出来、判非空、写进记录，从未参与过滤。
        # 口径（用户 2026-09-26 确认的版本，不是"跌破就删"）：
        #   现价 >= MA20  -> 不变
        #   现价 <  MA20  -> 信号降级为「观察」，不产生建仓触发（记录保留做筑底观察）
        # 为什么不直接 return []：模式三「横盘周K」本就是底部构筑形态，
        # 启动前现价贴近 MA20 甚至短暂在其下方是常态，硬删会误杀正样本。
        _below_ma20 = today['close'] < ma20
        today_str = today['date'][:10]
        # V19 控盘度 + 洗盘/出货判断（每股算一次，两个模式共用结果）
        # V20 建仓阶段专门因子（与控盘度共用同一个 df，不额外取数）
        _ctrl, _stage, _pos = 0.0, 'unknown', None
        _stack_sc, _redfat_sc = 0.0, 0.0
        _stack_ok, _redfat_ok = False, False
        _c4_n, _c4_ok, _c4_sc = 0, False, 0.0
        _c6_n, _c6_ok, _c6_sc = 0, False, 0.0
        _probe_ok, _probe_sc, _probe_stage = False, 0.0, ''
        _distp_ok, _distp_sc, _distp_type = False, 0.0, ''
        _markup_ok, _markup_sc, _markup_type = False, 0.0, ''
        _brk_ok, _brk_type, _brk_sc = False, '', 0.0
        _vreg_tags, _vreg_pct = '', None
        try:
            from strategy.base import TechnicalIndicators as _TI
            _df = _bars_to_df(bars)
            if _df is not None:
                _ti = _TI()
                _ctrl = float(_ti.estimate_control_score(_df))
                _stage = _ti.judge_wash_or_distribute(_df)
                _t120 = _df['close'].tail(120)
                _lo, _hi = float(_t120.min()), float(_t120.max())
                _pos = (float(_df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)
                _CTRL_FUNNEL['ok'] += 1
                if _ctrl >= _CTRL_HIGH:
                    _CTRL_FUNNEL['ctrl'] += 1
                if _stage == 'wash':
                    _CTRL_FUNNEL['wash'] += 1
                elif _stage == 'distribute':
                    _CTRL_FUNNEL['dist'] += 1
                _stk = _ti.bottom_volume_stack(_df)
                _rf = _ti.red_fat_green_thin(_df)
                _stack_sc = float(_stk.get('score') or 0.0)
                _redfat_sc = float(_rf.get('score') or 0.0)
                _stack_ok = bool(_stk.get('ok'))
                _redfat_ok = bool(_rf.get('ok'))
                _BUILD_FUNNEL['ok'] += 1
                if _stack_ok:
                    _BUILD_FUNNEL['stack_ok'] += 1
                if _redfat_ok:
                    _BUILD_FUNNEL['redfat_ok'] += 1
                if _stack_ok and _redfat_ok:
                    _BUILD_FUNNEL['both_ok'] += 1
                # C4 观察规则（复用同一个 df 与已算好的控盘分，不额外取数）
                _c4r = _ti.is_c4_candidate(_df, ctrl_score=_ctrl)
                _c4_n = int(_c4r.get('n_ok') or 0)
                _c4_ok = bool(_c4r.get('ok'))
                _c4_sc = float(_c4r.get('score') or 0.0)
                _c4h = _c4r.get('hits') or [False] * 5
                if _c4r.get('reason'):
                    _C4_FUNNEL['insuf'] += 1
                else:
                    _C4_FUNNEL['ok'] += 1
                    if _c4h[0]:
                        _C4_FUNNEL['pos'] += 1
                    if _c4h[1] and _c4h[2]:
                        _C4_FUNNEL['vol'] += 1
                    if _c4h[3]:
                        _C4_FUNNEL['amp'] += 1
                    if _c4h[4]:
                        _C4_FUNNEL['ctrl'] += 1
                    if _c4_n >= 5:
                        _C4_FUNNEL['c4'] += 1
                # C6 观察规则（复用同一个 df，不额外取数；不含量价条件）
                _c6r = _ti.is_c6_candidate(_df)
                _c6_n = int(_c6r.get('n_ok') or 0)
                _c6_ok = bool(_c6r.get('ok'))
                _c6_sc = float(_c6r.get('score') or 0.0)
                _c6h = _c6r.get('hits') or [False, False]
                if _c6r.get('reason'):
                    _C6_FUNNEL['insuf'] += 1
                else:
                    _C6_FUNNEL['ok'] += 1
                    if _c6h[0]:
                        _C6_FUNNEL['pos'] += 1
                    if _c6h[1]:
                        _C6_FUNNEL['amp'] += 1
                    if _c6_n >= 2:
                        _C6_FUNNEL['c6'] += 1
                # 试盘识别（复用同一个 df；只做观察）
                _pr = _ti.detect_probe(_df)
                _probe_ok = bool(_pr.get('ok'))
                _probe_sc = float(_pr.get('score') or 0.0)
                _probe_stage = _pr.get('stage') or ''
                _prr = _pr.get('reason') or ''
                if _prr in ('bars<%d' % 60, 'no_probe'):
                    if _prr == 'no_probe':
                        _PROBE_FUNNEL['no'] += 1
                    else:
                        _PROBE_FUNNEL['insuf'] += 1
                elif _prr.startswith('pos>'):
                    _PROBE_FUNNEL['pos'] += 1
                else:
                    _PROBE_FUNNEL['ok'] += 1
                    if _probe_stage == 'pending':
                        _PROBE_FUNNEL['pending'] += 1
                    if _probe_ok:
                        _PROBE_FUNNEL['hit'] += 1
                # 出货形态确认（复用同一个 df；只做观察）
                _dr = _ti.detect_distribution_pattern(_df)
                _distp_ok = bool(_dr.get('ok'))
                _distp_sc = float(_dr.get('score') or 0.0)
                _distp_type = _dr.get('type') or ''
                if _dr.get('reason'):
                    _DISTP_FUNNEL['insuf'] += 1
                else:
                    _DISTP_FUNNEL['ok'] += 1
                    if _distp_ok:
                        _DISTP_FUNNEL['hit'] += 1
                        if _distp_type == '\u9ad8\u4f4d\u653e\u91cf\u6ede\u6da8':
                            _DISTP_FUNNEL['stall'] += 1
                        elif _distp_type == '\u9ad8\u4f4d\u7834\u4f4d':
                            _DISTP_FUNNEL['break'] += 1
                        elif _distp_type == '\u53cc\u9876\u96cf\u5f62':
                            _DISTP_FUNNEL['dtop'] += 1
                # 拉升阶段识别（复用同一个 df；只做观察）
                _mr = _ti.detect_markup(_df)
                _markup_ok = bool(_mr.get('ok'))
                _markup_sc = float(_mr.get('score') or 0.0)
                _markup_type = _mr.get('type') or ''
                _mrr = _mr.get('reason') or ''
                if _mrr.startswith('pos>'):
                    _MARKUP_FUNNEL['pos'] += 1
                elif _mrr:
                    _MARKUP_FUNNEL['insuf'] += 1
                else:
                    _MARKUP_FUNNEL['ok'] += 1
                    if _markup_ok:
                        _MARKUP_FUNNEL['hit'] += 1
                        if _markup_type == '阶梯式上行':
                            _MARKUP_FUNNEL['trend'] += 1
                        elif _markup_type == '缩量强势':
                            _MARKUP_FUNNEL['lock'] += 1
                        elif _markup_type == '加速迹象':
                            _MARKUP_FUNNEL['acc'] += 1
                # A 破位—收复 双向判据（复用同一个 df；只做观察）
                _br = _ti.detect_breakdown_recover(_df)
                _brk_ok = bool(_br.get('ok'))
                _brk_type = _br.get('type') or ''
                _brk_sc = float(_br.get('score') or 0.0)
                _brr = _br.get('reason') or ''
                if _brr.startswith('pos>'):
                    _BRK_FUNNEL['pos'] += 1
                elif _brr == 'no_break':
                    _BRK_FUNNEL['nobreak'] += 1
                elif _brr:
                    _BRK_FUNNEL['insuf'] += 1
                else:
                    _BRK_FUNNEL['ok'] += 1
                    if _brk_type == '洗盘收复':
                        _BRK_FUNNEL['wash'] += 1
                    elif _brk_type == '破位未收':
                        _BRK_FUNNEL['dist'] += 1
                # B 量能分位 / 缩量上涨（复用同一个 df；只做观察）
                _vg = _ti.detect_volume_regime(_df)
                _vreg_tags = '|'.join(_vg.get('tags') or [])
                _vreg_pct = _vg.get('pct')
                if _vg.get('reason'):
                    _VREG_FUNNEL['insuf'] += 1
                else:
                    _VREG_FUNNEL['ok'] += 1
                    _vgt = _vg.get('tags') or []
                    if '地量' in _vgt:
                        _VREG_FUNNEL['low'] += 1
                    if '天量' in _vgt:
                        _VREG_FUNNEL['high'] += 1
                    if '缩量上涨' in _vgt:
                        _VREG_FUNNEL['shrinkup'] += 1
        except Exception as _e:
            print(f'[日K建仓] {code} 控盘度计算异常: {type(_e).__name__}: {_e}', flush=True)
        # 控盘提示（决定 UI 短标签的只有这一部分；观察类文案另算）
        _ctrl_tag = ' ｜ '.join(_ctrl_note_tags(_ctrl, _stage, _pos))
        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n,
                               _c6_n, _probe_ok, _distp_type, _markup_type,
                               _brk_type, _vreg_tags)
        if _ctrl_tip and _BUILD_NOTE_MODE != 'off':
            _BUILD_FUNNEL['tip'] += 1
        if _c4_ok and _C4_NOTE_MODE != 'off':
            _C4_FUNNEL['note'] += 1
        if _c6_ok and _C6_NOTE_MODE != 'off':
            _C6_FUNNEL['note'] += 1
        if _probe_ok and _PROBE_NOTE_MODE != 'off':
            _PROBE_FUNNEL['note'] += 1
        if _distp_ok and _DISTP_NOTE_MODE != 'off':
            _DISTP_FUNNEL['note'] += 1
        if _markup_ok and _MARKUP_NOTE_MODE != 'off':
            _MARKUP_FUNNEL['note'] += 1
        if _BRK_NOTE_MODE != 'off' and _brk_type:
            _BRK_FUNNEL['note'] += 1
        if _VREG_NOTE_MODE != 'off' and _vreg_tags:
            _VREG_FUNNEL['note'] += 1
        if _ctrl_tip:
            _CTRL_FUNNEL['tip'] += 1
        found = []
        for fn in (detect_pattern_aggressive, detect_pattern_bottom):
            try:
                r = fn(bars, code)
            except Exception as e:
                print(f"[日K建仓] {code} {fn.__name__} 异常: {e}", flush=True)
                r = None
            if not r:
                continue
            # 止盈价：触发档 = 建仓价 +3% 锁定（2025 全年回测：收益 +0.07%->+0.4%，胜率 47%->69%）
            #        等待确认档 = 引擎给出的「分时做T卖点」（VWAP + k·ATR）
            _tp = r.get('take_profit') or 0
            if not _tp and r.get('trigger_price'):
                _tp = round(r['trigger_price']
                            * (_REGIME.get('tp_factor') or 1.03), 2)
            # 环境分：按当日市场/行业温度给出建仓力度建议
            _amp = ((today['high'] - today['low']) / closes[-2] * 100
                    if len(closes) > 1 and closes[-2] else 0)
            _es, _en = _env_score_for(code, _amp, r.get('volume_ratio', 0))
            rec = {
                'code': code, 'name': name,
                'pattern_id': r['pattern_id'],
                'pattern_name': PATTERN_NAMES[r['pattern_id']],
                'base_date': r['base_date'],
                'base_close': r.get('base_close'),
                'base_high': r.get('base_high'),
                'base_low': r.get('base_low'),
                'push_date': today_str,
                'push_price': round(today['close'],2),
                'push_pct': round((today['close']-closes[-2])/closes[-2]*100,2) if len(closes)>1 else 0,
                'ma5': round(ma5,2), 'ma20': round(ma20,2),
                'volume_ratio': r.get('volume_ratio',0),
                'gap_pct': r.get('gap_pct',0),
                'structure_days': r.get('structure_days',0),
                'signal_level': r.get('signal_level', LVL_WATCH),
                'trigger_type': r.get('trigger_type',''),
                'trigger_price': r.get('trigger_price',0),
                'invalid_price': r.get('invalid_price',0),
                'valid_until': r.get('valid_until',''),
                'weekly_confirm': r.get('weekly_confirm',0),
                'up_days': r.get('up_days',0), 'up_vol_ok': r.get('up_vol_ok',0),
                'up_rate': r.get('up_rate',0),
                'down_days': r.get('down_days',0), 'down_vol_ok': r.get('down_vol_ok',0),
                'down_rate': r.get('down_rate',0),
                'struct_pos': r.get('struct_pos',0),
                'recent_vol3': r.get('recent_vol3',0),
                'shake_dip': r.get('shake_dip',0),
                'shake_shadow': r.get('shake_shadow',0),
                'shake_probe': r.get('shake_probe',0),
                'shake_amp': r.get('shake_amp',0),
                'shake_ok': r.get('shake_ok',0),
                'take_profit': _tp,
                'control_score': _ctrl, 'stage_guess': _stage,
                'stack_vol_score': _stack_sc, 'red_fat_score': _redfat_sc,
                'c4_ok': 1 if _c4_ok else 0, 'c4_score': _c4_sc,
                'c6_ok': 1 if _c6_ok else 0, 'c6_score': _c6_sc,
                'ctrl_tag': _ctrl_tag,
                'probe_ok': 1 if _probe_ok else 0, 'probe_score': _probe_sc,
                'dist_pattern_ok': 1 if _distp_ok else 0,
                'dist_pattern_type': _distp_type,
                'dist_pattern_score': _distp_sc,
                'markup_ok': 1 if _markup_ok else 0,
                'markup_type': _markup_type,
                'markup_score': _markup_sc,
                'brk_ok': 1 if _brk_ok else 0,
                'brk_type': _brk_type,
                'brk_score': _brk_sc,
                'vreg_tags': _vreg_tags,
                'vreg_pct': _vreg_pct,
                'env_score': _es,
                'env_note': _en,
                'note': r.get('note',''),
            }
            # MA20 降级：现价在 20 日均线下方 -> 只观察，不给建仓触发
            # （等待确认档本来就不能买，不受影响；只针对已经给出的建仓触发）
            if _below_ma20 and rec['signal_level'] == LVL_TRIGGER:
                rec['signal_level'] = LVL_WATCH
                rec['trigger_type'] = 'MA20下方·筑底观察'
                _fn = (_M1_FUNNEL if fn is detect_pattern_aggressive
                       else _M4_FUNNEL)
                _fn['trigger'] = max(0, _fn['trigger'] - 1)
                _fn['ma20_below'] += 1
            # V18 三轴状态闸门：冰点期不放行建仓触发
            if (not _REGIME.get('allow_trigger', True)
                    and rec['signal_level'] == LVL_TRIGGER):
                rec['signal_level'] = LVL_WATCH
                rec['trigger_type'] = '\u51b0\u70b9\u671f\u00b7\u4e0d\u653e\u884c'
                rec['note'] = ((rec.get('note') or '')
                               + '\n[\u72b6\u6001\u95f8\u95e8] %s\uff0c\u51b0\u70b9\u671f\u4e0d\u653e\u884c\u5efa\u4ed3\u89e6\u53d1'
                               % _REGIME.get('state', ''))
                _REGIME['blocked'] = _REGIME.get('blocked', 0) + 1
            # V19 控盘提醒文案（note 就是 UI 里「触发条件」列的 tooltip）
            if _ctrl_tip:
                rec['note'] = ((rec.get('note') or '') + '\n[控盘] ' + _ctrl_tip)
            _save_or_update(rec)
            found.append(rec)
        return found

    def scan_all(self, verbose=True):
        global _WRITE_TABLE
        _init_db()
        _init_db(_STAGE_TABLE)
        # 全市场扫描 = 全量重算。
        # 旧做法：先 DELETE pattern_record 再逐条 INSERT —— UI 在 13 分钟扫描期间
        # 会读到空表 / 半截表。
        # 新做法：全程写暂存表 pattern_record_new，扫完再原子替换。
        # 扫描期间主表保持上一次的完整结果，UI 读到的永远是完整数据。
        try:
            _con = sqlite3.connect(DB_PATH)
            _con.execute(f'DELETE FROM {_STAGE_TABLE}')
            _con.commit()
            _con.close()
            if verbose:
                print('[日K建仓] 已清空暂存表，开始全量重扫（主表扫描期间保持完整）', flush=True)
        except Exception as _e:
            print(f'[日K建仓] 清空暂存表失败: {_e}', flush=True)
        _WRITE_TABLE = _STAGE_TABLE
        # 扫描前构建当日市场/行业环境截面（用于 env_score）
        try:
            _build_env_context(verbose=verbose)
        except Exception as _ee:
            print('[日K建仓] 环境截面异常(忽略): %s' % _ee, flush=True)
        # 扫描前构建当日题材热度截面（V10：用于题材强度 t -> 建仓价修正 + 闸门）
        try:
            _build_theme_context(verbose=verbose)
        except Exception as _ee2:
            print('[日K建仓] 题材截面异常(忽略): %s' % _ee2, flush=True)
        from utils.stock_name_manager import get_all_stock_names
        raw = get_all_stock_names()
        code2name = {}
        for _nm, _cd in raw.items():
            if _cd not in code2name:
                code2name[_cd] = _nm
        items = list(code2name.items())
        total = len(items)
        for k in _M4_FUNNEL:
            _M4_FUNNEL[k] = 0
        for k in _M1_FUNNEL:
            _M1_FUNNEL[k] = 0
        _load_regime(verbose=verbose)
        for _k in _CTRL_FUNNEL:
            _CTRL_FUNNEL[_k] = 0
        for _k in _BUILD_FUNNEL:
            _BUILD_FUNNEL[_k] = 0
        for _k in _C4_FUNNEL:
            _C4_FUNNEL[_k] = 0
        for _k in _C6_FUNNEL:
            _C6_FUNNEL[_k] = 0
        for _k in _PROBE_FUNNEL:
            _PROBE_FUNNEL[_k] = 0
        for _k in _DISTP_FUNNEL:
            _DISTP_FUNNEL[_k] = 0
        for _k in _MARKUP_FUNNEL:
            _MARKUP_FUNNEL[_k] = 0
        for _k in _BRK_FUNNEL:
            _BRK_FUNNEL[_k] = 0
        for _k in _VREG_FUNNEL:
            _VREG_FUNNEL[_k] = 0
        pat_cnt = {1: 0, 3: 0}
        err = 0
        for idx, (code, name) in enumerate(items):
            try:
                found = self.scan_stock(code, name)
                for rec in found:
                    pid = rec['pattern_id']
                    if pid in pat_cnt:
                        pat_cnt[pid] += 1
            except Exception as e:
                err += 1
                if verbose and err <= 3:
                    print(f"[日K建仓] {code} 异常: {type(e).__name__}: {e}", flush=True)
            if verbose and (idx+1) % 500 == 0:
                print(f"[日K建仓] 进度 {idx+1}/{total} 异常{err}", flush=True)
        # 扫描结束：写回主表名，并把暂存表原子替换上去
        _WRITE_TABLE = 'pattern_record'
        swap_ok = _atomic_swap()
        total_rec = sum(pat_cnt.values())
        if verbose:
            print('=' * 60, flush=True)
            print('[结果切换] ' + ('成功，主表已更新为本次扫描结果'
                                   if swap_ok else '失败，主表保留上一次数据'), flush=True)
            print('[全市场扫描结果]', flush=True)
            print(f'模式一（激进）: {pat_cnt.get(1, 0)}', flush=True)
            print(f'模式三（横盘周K）: {pat_cnt.get(3, 0)}', flush=True)
            print(f'总记录: {total_rec}', flush=True)
            print(f'异常: {err}', flush=True)
            print('[状态闸门] %s\uff5c%s' % (_REGIME.get('state', ''),
                                          _REGIME.get('note', '')), flush=True)
            print('  \u51b0\u70b9\u671f\u964d\u7ea7\u4e3a\u89c2\u5bdf: %d \u6761' % _REGIME.get('blocked', 0),
                  flush=True)
            _cf = _CTRL_FUNNEL
            print('[\u63a7\u76d8\u5ea6] \u5df2\u8ba1\u7b97 %d \u53ea \uff5c >=%.0f\u5206 %d \u53ea \uff5c '
                  '\u6d17\u76d8 %d \u53ea \uff5c \u51fa\u8d27 %d \u53ea \uff5c \u89e6\u53d1\u63d0\u9192 %d \u53ea'
                  % (_cf['ok'], _CTRL_HIGH, _cf['ctrl'], _cf['wash'],
                     _cf['dist'], _cf['tip']), flush=True)
            _c4f = _C4_FUNNEL
            print('[C4观察] 可算 %d 只 ｜ 位置达标 %d ｜ 量价达标 %d ｜ 振幅达标 %d ｜ 控盘达标 %d ｜ 五条全中 %d ｜ 文案开关 _C4_NOTE_MODE=%s'
                  % (_c4f['ok'], _c4f['pos'], _c4f['vol'], _c4f['amp'],
                     _c4f['ctrl'], _c4f['c4'], _C4_NOTE_MODE), flush=True)
            print('[C4观察] K线不足%d根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (120, _c4f['insuf'], _c4f['note']), flush=True)
            _c6f = _C6_FUNNEL
            print('[C6观察] 可算 %d 只 ｜ 位置达标 %d ｜ 振幅达标 %d ｜ 两条全中 %d ｜ 文案开关 _C6_NOTE_MODE=%s'
                  % (_c6f['ok'], _c6f['pos'], _c6f['amp'], _c6f['c6'],
                     _C6_NOTE_MODE), flush=True)
            print('[C6观察] K线不足120根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_c6f['insuf'], _c6f['note']), flush=True)
            _prf = _PROBE_FUNNEL
            print('[试盘观察] 通过K线门槛 %d 只 ｜ 位置超限跳过 %d ｜ 无试盘形态 %d ｜ '
                  '找到试盘候选 %d（当日待确认 %d / 结构未走完 %d / 已确认 %d）｜ 文案开关 _PROBE_NOTE_MODE=%s'
                  % (_prf['ok'] + _prf['pos'] + _prf['no'], _prf['pos'], _prf['no'],
                     _prf['ok'], _prf['pending'],
                     _prf['ok'] - _prf['pending'] - _prf['hit'], _prf['hit'],
                     _PROBE_NOTE_MODE), flush=True)
            print('[试盘观察] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_prf['insuf'], _prf['note']), flush=True)
            _dpf = _DISTP_FUNNEL
            print('[出货形态] 可算 %d 只 ｜ 放量滞涨 %d ｜ 高位破位 %d ｜ 双顶雏形 %d ｜ 命中合计 %d ｜ 文案开关 _DISTP_NOTE_MODE=%s'
                  % (_dpf['ok'], _dpf['stall'], _dpf['break'], _dpf['dtop'],
                     _dpf['hit'], _DISTP_NOTE_MODE), flush=True)
            print('[出货形态] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_dpf['insuf'], _dpf['note']), flush=True)
            _mkf = _MARKUP_FUNNEL
            from strategy.base import MARKUP_POS_MAX as _MPMAX
            print('[拉升观察] 可算（已过位置门槛）%d 只 ｜ 阶梯式上行 %d ｜ 缩量强势 %d ｜ 加速迹象 %d ｜ 命中合计 %d ｜ 文案开关 _MARKUP_NOTE_MODE=%s'
                  % (_mkf['ok'], _mkf['trend'], _mkf['lock'], _mkf['acc'],
                     _mkf['hit'], _MARKUP_NOTE_MODE), flush=True)
            print('[拉升观察] K线不足60根跳过 %d 只 ｜ 位置超限跳过(pos>=%.2f) %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_mkf['insuf'], _MPMAX, _mkf['pos'], _mkf['note']), flush=True)
            _bkf = _BRK_FUNNEL
            from strategy.base import BRK_POS_LOW as _BPMAX
            print('[破位收复] 可算 %d 只 ｜ 洗盘收复 %d ｜ 破位未收 %d ｜ 文案开关 _BRK_NOTE_MODE=%s'
                  % (_bkf['ok'], _bkf['wash'], _bkf['dist'], _BRK_NOTE_MODE), flush=True)
            print('[破位收复] K线不足60根跳过 %d 只 ｜ 位置超限跳过(pos>=%.2f) %d 只 ｜ '
                  '无破位日 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_bkf['insuf'], _BPMAX, _bkf['pos'], _bkf['nobreak'],
                     _bkf['note']), flush=True)
            _vgf = _VREG_FUNNEL
            print('[量能分位] 可算 %d 只 ｜ 地量 %d ｜ 天量 %d ｜ 缩量上涨 %d ｜ 文案开关 _VREG_NOTE_MODE=%s'
                  % (_vgf['ok'], _vgf['low'], _vgf['high'], _vgf['shrinkup'],
                     _VREG_NOTE_MODE), flush=True)
            print('[量能分位] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_vgf['insuf'], _vgf['note']), flush=True)
            _bf = _BUILD_FUNNEL
            print('[\u5efa\u4ed3\u56e0\u5b50] \u5df2\u8ba1\u7b97 %d \u53ea \uff5c \u5806\u91cf\u6ee1\u8db3 %d \u53ea \uff5c \u7ea2\u80a5\u7eff\u7626\u6ee1\u8db3 %d \u53ea \uff5c \u4e24\u8005\u540c\u65f6 %d \u53ea \uff5c \u65b9\u5411\u5f00\u5173 _BUILD_NOTE_MODE=%s'
                  % (_bf['ok'], _bf['stack_ok'], _bf['redfat_ok'],
                     _bf['both_ok'], _BUILD_NOTE_MODE), flush=True)
            print('-' * 60, flush=True)
            try:
                _c2 = sqlite3.connect(DB_PATH)
                _dist = _c2.execute(
                    'SELECT env_score, COUNT(*) FROM pattern_record'
                    ' GROUP BY env_score ORDER BY env_score DESC').fetchall()
                _tp_n = _c2.execute(
                    'SELECT COUNT(*) FROM pattern_record WHERE take_profit > 0').fetchone()[0]
                _c2.close()
                print('[环境分分布] (>=6 正常建仓 / 3~5 谨慎 / <=2 不建仓)', flush=True)
                for _sv, _cn in _dist:
                    print(f'  env_score={_sv}: {_cn} 条', flush=True)
                print(f'[止盈] 已给出止盈价: {_tp_n} 条', flush=True)
                print('-' * 60, flush=True)
            except Exception as _e2:
                print('[环境分分布] 读取失败: %s' % _e2, flush=True)
            _f1 = _M1_FUNNEL
            print('[模式一（激进）漏斗]', flush=True)
            print(f'  启动日S成立(实体>=3%+涨幅>=3%+量>=1.0) : {_f1["s_ok"]}', flush=True)
            print(f'  洗盘日D跳空(D开>S最高)                 : {_f1["d_ok"]}', flush=True)
            print(f'  缩量整理成立(>=5日/十字/缩量/无长阴/通则): {_f1["struct"]}', flush=True)
            print(f'  回踩MA5→建仓触发                       : {_f1["trigger"]}', flush=True)
            print(f'  题材冷剔除(t<-0.4)                     : {_f1["theme"]}', flush=True)
            print(f'  建仓价距现价>{_ENTRY_GAP_CAP}%剔除              : {_f1["entry_far"]}', flush=True)
            print(f'  现价<MA20降级为观察                    : {_f1["ma20_below"]}', flush=True)
            f = _M4_FUNNEL
            print('[模式三（横盘周K）漏斗]', flush=True)
            print(f'本周放量收阳(>=上周1.3倍) : {f["wk"]}', flush=True)
            print(f'横盘结构成立             : {f["struct"]}', flush=True)
            print(f'结构位70~98%近上沿→触发  : {f["trigger"]}', flush=True)
            print(f'题材冷剔除(t<-0.4)       : {f["theme"]}', flush=True)
            print(f'  建仓价距现价>{_ENTRY_GAP_CAP}%剔除    : {f["entry_far"]}', flush=True)
            print(f'  现价<MA20降级为观察      : {f["ma20_below"]}', flush=True)
            print(f'周K达标但无合格横盘窗口  : {f["invalid"]}', flush=True)
        return total_rec


if __name__ == '__main__':
    eng = BandPatternEngine()
    eng.scan_all()
    rows = query_signals()
    print(f'\\n=== 结果 ===')
    print(f'总数: {len(rows)}')
    for r in rows[:20]:
        print(f"  {r['code']} {r['name'][:8]:8s} {r['pattern_name']:16s} "
              f"[{r['signal_level']}] {r['trigger_type']} | {r['note']}")
