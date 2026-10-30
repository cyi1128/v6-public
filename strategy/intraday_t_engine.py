# -*- coding: utf-8 -*-
"""机构级分时做T引擎（成本可控 + 流动性可控 + 对手盘可预期）。

设计口径（与 ui\\battle_widgets\\atr_t_widget.py 现有模块完全解耦，纯逻辑、无 Qt、无网络）：

  1) 持仓成本偏离（最核心）
     - 反T（先卖后买）：要求 price 相对 cost 有正偏离（≥ REV_MIN_DEV），否则"卖了就回不来成本"。
     - 正T（先买后卖）：要求 price 相对 cost 有负偏离（≤ FWD_MAX_DEV），否则摊薄意义不足。
     - 深套（偏离超过 DEEP_LOSS_DEV）不给"低吸摊薄"信号，只提示先判断是否该止损。
  2) 真实日内 VWAP
     - vwap = 今日成交额(元) / (今日成交量(手) × 100)。实测 5 只（600519/300750/000001/601318/002594）
       全部落在当日 low~high 之内，口径正确。成交额缺失时退回 (H+L+C)/3 并置 vwap_src='fallback'。
     - 低于 VWAP 低吸、高于 VWAP 高抛，且必须结合成本与 ATR 偏离幅度，不用固定百分比。
  3) 量价结构（用券商行情里的真实量比 vol_ratio）
     - 放量上攻不持续（冲高回落）→ 优先高抛
     - 下跌缩量且有承接（不破当日低点/跌幅收窄）→ 优先低吸
     - 放量下跌 → 硬阻断低吸（这是接飞刀，不是低吸）
  4) 时间窗口过滤：只在流动性好的时段做T，其余时段降权或直接不做。
  5) 反T 优先于正T：反T 卖出的是底仓（T+1 可用部分），不需要额外资金。
  6) 强度量化：0~100 分 + 建议做T比例 + 做T后成本预估 + 盈亏平衡价差。

对外只暴露三样东西：
  - THolding / TQuote：输入
  - IntradayTEngine.evaluate()：产出 plan（dict）
  - apply_plan_to_row(row, plan)：把 plan 写回现有表格行（字段名沿用模块既有命名）

作者备注：所有阈值集中在 TParams，可按实盘分布整档调整；不要把阈值硬编码进判断分支。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, time as dtime
from typing import Optional, Dict, Any, List, Tuple


# ============================================================
# 参数（唯一阈值来源，改这里就够）
# ============================================================
@dataclass
class TParams:
    # ---- 成本偏离 ----
    rev_min_dev: float = 0.010          # 反T：价格至少高于成本 1.0% 才先卖
    fwd_max_dev: float = -0.010         # 正T：价格至少低于成本 1.0% 才先买
    deep_loss_dev: float = -0.080       # 低于成本 8% 视为深套，不做"摊薄式"低吸
    cost_full_dev: float = 0.020        # 成本维度满分所需的偏离幅度（2%）

    # ---- VWAP 偏离（以 ATR 为单位，不用固定百分比）----
    k_vwap: float = 0.60                # 价格需偏离 VWAP 0.6×ATR 才计入满分
    atr_pct_fallback: float = 0.020     # ATR 缺失时用 prev_close×2% 兜底
    vwap_break_pct: float = 0.985       # 跌破 VWAP×0.985 视为趋弱单边下跌 → 禁低吸

    # ---- 量价结构 ----
    vol_expand: float = 1.50            # 量比 ≥1.5 视为放量
    vol_shrink: float = 0.70            # 量比 ≤0.7 视为缩量
    stall_ratio: float = 0.995          # 现价 ≤ 当日最高×0.995 视为"冲高回落/上攻不持续"

    # ---- 评分与仓位 ----
    w_cost: float = 0.30
    w_vwap: float = 0.25
    w_vol: float = 0.20
    w_time: float = 0.10
    w_struct: float = 0.15
    min_score_action: float = 65.0      # 低于此分只观察不提示执行
    min_score_strong: float = 80.0
    ratio_ladder: Tuple[Tuple[float, float], ...] = (   # (分数下限, 建议做T比例)
        (88.0, 0.30), (80.0, 0.25), (72.0, 0.20), (65.0, 0.12),
    )
    forward_ratio_discount: float = 0.7  # 正T 需要额外资金，比例打折

    # ---- 费用与滑点（默认按常见券商：佣金万2.5、最低5元；印花税卖出0.05%；过户费0.001%双向）----
    comm_rate: float = 0.00025
    comm_min: float = 5.0
    stamp_rate: float = 0.00050          # 仅卖出
    transfer_rate: float = 0.00001       # 双向
    tick: float = 0.01
    slippage_ticks: int = 1              # 单边滑点（跳）

    def __post_init__(self):
        # 数字健全性：权重归一由代码内部处理，这里只防呆
        for name in ('rev_min_dev', 'k_vwap', 'min_score_action'):
            if float(getattr(self, name)) <= 0:
                raise ValueError('TParams.%s 必须为正数' % name)


# ============================================================
# 输入结构
# ============================================================
@dataclass
class THolding:
    """持仓（来自 holding 表；cost/qty 允许为 None —— 表示只有自选没有持仓）"""
    code: str
    name: str = ''
    cost: Optional[float] = None
    qty: Optional[float] = None
    qty_avail: Optional[float] = None   # 手工覆盖：可用（T+1 已解禁）数量
    buy_time: Any = None                # 最近一次买入时间，用于 T+1 推断可用量

    def available_qty(self, today: Optional[Any] = None) -> float:
        """T+1 可用数量推断：当日买入部分不可卖。

        限制（如实说明）：holding 表是「一个代码一行」的成本/数量聚合，
        如果同一只票今天买过、昨天也有底仓，本函数拿不到拆分后的可用量，
        此时请用 qty_avail 手工指定，否则会**低估**可用量（偏保守，不会造成违规卖出）。
        """
        if self.qty_avail is not None:
            try:
                return max(0.0, float(self.qty_avail))
            except (TypeError, ValueError):
                return 0.0
        qty = float(self.qty or 0.0)
        if qty <= 0:
            return 0.0
        bt = self.buy_time
        if not bt:
            return qty                     # 没有买入时间信息：按全部可用（保守度已知）
        try:
            if isinstance(bt, str):
                bt_date = bt.replace('/', '-').split(' ')[0]
            else:
                bt_date = bt.strftime('%Y-%m-%d')
        except Exception:
            return qty
        ref = today or datetime.now()
        ref_date = ref.strftime('%Y-%m-%d') if hasattr(ref, 'strftime') else str(ref)[:10]
        return 0.0 if bt_date == ref_date else qty


@dataclass
class TQuote:
    """实时行情（字段与 utils\\http_market_data.get_realtime_quotes_http 对齐）"""
    price: float
    prev_close: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume_lots: float = 0.0            # 成交量（手）
    amount: float = 0.0                 # 成交额（元）
    vol_ratio: float = 0.0              # 量比
    turnover: float = 0.0               # 换手率 %

    def intraday_vwap(self, fallback: bool = True) -> Tuple[float, str]:
        """真实日内 VWAP。返回 (vwap, 来源标记)。"""
        try:
            if self.volume_lots and self.volume_lots > 0 and self.amount and self.amount > 0:
                v = float(self.amount) / (float(self.volume_lots) * 100.0)
                lo, hi = float(self.low or 0), float(self.high or 0)
                # 合理性闸门：明显越界说明字段口径变了，宁可退回也不给错数
                if v > 0 and (lo <= 0 or v >= lo * 0.97) and (hi <= 0 or v <= hi * 1.03):
                    return v, 'amount/volume'
        except Exception:
            pass
        if not fallback:
            return 0.0, 'none'
        return (float(self.high or 0) + float(self.low or 0) + float(self.price or 0)) / 3.0, 'fallback(HLC/3)'


# ============================================================
# 时间窗口
# ============================================================
# (起, 止, 代号, 中文名, 权重, 是否利于"买回/低吸")
TIME_WINDOWS: Tuple[Tuple[str, str, str, str, float, bool], ...] = (
    ('09:15', '09:25', 'auction',    '集合竞价',        0.0, False),
    ('09:25', '09:30', 'pre_open',   '开盘前',          0.0, False),
    ('09:30', '09:35', 'open_spike', '开盘瞬时',        0.3, False),
    ('09:35', '10:00', 'open_30',    '开盘30分钟',      1.0, True),
    ('10:00', '10:15', 'lull_1',     '10:00-10:15 回落', 0.6, False),
    ('10:15', '10:45', 'am_core',    '10:30 前后',      1.0, True),
    ('10:45', '11:30', 'am_late',    '午前尾段',        0.5, False),
    ('11:30', '13:00', 'lunch',      '午间休市',        0.0, False),
    ('13:00', '13:30', 'pm_open',    '13:00-13:30',     1.0, True),
    ('13:30', '14:00', 'lull_2',     '13:30-14:00 回落', 0.6, False),
    ('14:00', '14:40', 'pm_core',    '14:00-14:40',     1.0, True),
    ('14:40', '15:00', 'pm_close',   '14:40-15:00 回补', 0.7, True),
)


def _hm(s: str) -> dtime:
    h, m = s.split(':')
    return dtime(int(h), int(m))


def resolve_window(now: datetime) -> Dict[str, Any]:
    """把当前时刻映射到时间窗口。落在窗口外（收盘后/周末）返回 weight=0 的 closed。"""
    t = now.time()
    for a, b, key, cn, w, favor_buy in TIME_WINDOWS:
        if _hm(a) <= t < _hm(b):
            return dict(key=key, cn=cn, weight=w, favor_buy=favor_buy)
    return dict(key='closed', cn='非交易时段', weight=0.0, favor_buy=False)


# ============================================================
# 硬闸门短标签（信号灯列窄，长句会被截断；这里给每个闸门一个完整可读的短名）
# ============================================================
_HARD_SHORT = {
    '涨停/接近涨停锁仓': '涨停锁仓',
    '跌停/接近跌停，流动性枯竭': '跌停',
    '跌破VWAP 1.5%，趋弱单边下跌': '跌破VWAP',
    '非交易时段(非交易时段)': '非交易时段',
}


def hard_label(hard: str) -> str:
    """把硬闸门的整句原因压成「完整的短标签」，不做字符截断。"""
    if not hard:
        return ''
    if hard in _HARD_SHORT:
        return _HARD_SHORT[hard]
    if hard.startswith('非交易时段'):
        return '非交易时段'
    for head in ('放量下跌', '放量滞涨', '量价结构禁止'):
        if head in hard:
            return head
    return hard.split('，')[0].split('(')[0].split('（')[0][:12]


# ============================================================
# 引擎
# ============================================================
class IntradayTEngine:
    """机构级分时做T判定。evaluate() 是唯一入口，纯函数式（不读系统时间，除非 now 未传）。"""

    def __init__(self, params: Optional[TParams] = None):
        self.p = params or TParams()

    # ---------- 费用 ----------
    def trade_fee(self, qty: float, price: float, is_sell: bool) -> float:
        """单笔费用（佣金 + 印花税 + 过户费）。"""
        amt = max(0.0, float(qty)) * max(0.0, float(price))
        if amt <= 0:
            return 0.0
        comm = max(amt * self.p.comm_rate, self.p.comm_min)
        stamp = amt * self.p.stamp_rate if is_sell else 0.0
        transfer = amt * self.p.transfer_rate
        return comm + stamp + transfer

    def slippage_cost(self, qty: float) -> float:
        """单边滑点成本（跳数 × 最小变动价位 × 数量）。"""
        return max(0.0, float(qty)) * self.p.tick * self.p.slippage_ticks

    def round_trip_cost(self, qty: float, sell_price: float, buy_price: float) -> Dict[str, float]:
        """一次 T 的总摩擦：卖费 + 买费 + 双边滑点。"""
        sell_fee = self.trade_fee(qty, sell_price, True)
        buy_fee = self.trade_fee(qty, buy_price, False)
        slip = self.slippage_cost(qty) * 2
        return dict(sell_fee=sell_fee, buy_fee=buy_fee, slippage=slip,
                    total=sell_fee + buy_fee + slip)

    def breakeven_spread(self, qty: float, price: float) -> float:
        """盈亏平衡价差（元/股）：价差低于它，做T就是白交手续费。

        按真实价格计算比例费（佣金含最低 5 元/笔的摊薄、印花税、过户费）+ 双边滑点。
        手算校验：qty=2000、price=10 时 = 2×max(10×0.00025, 5/2000) + 10×(0.0005+0.00002) + 0.02 = 0.0302 元/股。
        """
        qty = max(1.0, float(qty))
        price = float(price or 0.0)
        if price <= 0:
            return 0.0
        comm_share = max(price * self.p.comm_rate, self.p.comm_min / qty)
        per_share = 2 * comm_share + price * (self.p.stamp_rate + self.p.transfer_rate * 2)
        return per_share + self.p.tick * self.p.slippage_ticks * 2

    # ---------- 成本预估 ----------
    def estimate_cost(self, holding: THolding, t_qty: float,
                      sell_price: float, buy_price: float,
                      side: str) -> Dict[str, float]:
        """做T后的综合成本预估。

        反T：先卖 sell_price、后买回 buy_price  —— 成本变化 = (买回价 - 卖出价)×qty + 费用
        正T：先买 buy_price、后卖 sell_price     —— 公式同形（先买价即 buy_price）
        返回 new_cost / delta(元) / delta_pct(%) / extra_cash(正T 需要追加的资金)。
        """
        cost = float(holding.cost or 0.0)
        total_qty = float(holding.qty or 0.0)
        if cost <= 0 or total_qty <= 0:
            return dict(new_cost=0.0, delta=0.0, delta_pct=0.0, extra_cash=0.0,
                        fees=0.0, note='缺成本/数量，无法预估')
        t_qty = min(max(0.0, float(t_qty)), total_qty)
        rc = self.round_trip_cost(t_qty, sell_price, buy_price)
        delta_total = (buy_price - sell_price) * t_qty + rc['total']
        new_cost = (cost * total_qty + delta_total) / total_qty
        extra = (buy_price * t_qty + rc['buy_fee'] + self.slippage_cost(t_qty)) if side == 'forward' else 0.0
        return dict(new_cost=round(new_cost, 4),
                    delta=round(new_cost - cost, 4),
                    delta_pct=round((new_cost - cost) / cost * 100.0, 4),
                    extra_cash=round(extra, 2),
                    fees=round(rc['total'], 2),
                    note='')

    # ---------- 量价结构 ----------
    def volume_price_state(self, q: TQuote, vwap: float, n_high: float = 0.0) -> Dict[str, Any]:
        """量价结构判定（券商行情里的真实量比 + 价格位置）。

        返回 state/label/rev_hint(高抛加成 0~1)/fwd_hint(低吸加成 0~1)/hard_block/notes
        """
        p = self.p
        price = float(q.price or 0)
        pct = ((price - q.prev_close) / q.prev_close * 100.0) if q.prev_close else 0.0
        vr = float(q.vol_ratio or 0)
        hi = float(q.high or 0) or n_high or price
        lo = float(q.low or 0) or price
        out = dict(state='neutral', label='量价中性', rev_hint=0.5, fwd_hint=0.5,
                   hard_block=None, notes=[])
        rally_stall = price <= hi * p.stall_ratio       # 冲高回落 / 上攻不持续
        near_low = lo > 0 and price <= lo * 1.01        # 贴近当日低点
        above_low = lo > 0 and price >= lo * 1.005      # 未破当日低点

        if vr >= p.vol_expand and pct > 0:
            if rally_stall:
                out.update(state='up_expand_stall', label='放量上攻不持续',
                           rev_hint=1.0, fwd_hint=0.15)
                out['notes'].append('放量冲高但收盘价未跟上 → 对手盘在派发，优先高抛')
            else:
                out.update(state='up_expand_break', label='放量上攻延续',
                           rev_hint=0.20, fwd_hint=0.30)
                out['notes'].append('放量且顶在高位 → 可能是主升，别急着卖')
        elif vr <= p.vol_shrink and pct < 0:
            if above_low:
                out.update(state='down_shrink_absorb', label='下跌缩量有承接',
                           rev_hint=0.30, fwd_hint=1.0)
                out['notes'].append('下跌缩量且未破当日低点 → 抛压衰竭，优先低吸')
            else:
                out.update(state='down_shrink_weak', label='缩量下跌破位',
                           rev_hint=0.35, fwd_hint=0.25)
                out['notes'].append('缩量但已破当日低点 → 承接不足，等止跌')
        elif vr >= p.vol_expand and pct < 0:
            out.update(state='down_expand', label='放量下跌',
                       rev_hint=0.10, fwd_hint=0.0, hard_block='buy')
            out['notes'].append('放量下跌 = 接飞刀，禁止低吸')
        elif vr <= p.vol_shrink and pct > 0:
            out.update(state='up_shrink', label='缩量上涨(惜售)',
                       rev_hint=0.55, fwd_hint=0.35)
            out['notes'].append('缩量上涨多为惜售，可小仓位高抛')
        elif near_low and vr >= p.vol_expand:
            out.update(state='down_probe', label='低位放量试探',
                       rev_hint=0.25, fwd_hint=0.45)
        return out

    # ---------- 结构（复用现有日线结论，作为加分项而非主判据）----------
    @staticmethod
    def structure_scores(structure: Optional[Dict[str, Any]]) -> Tuple[float, float, List[str]]:
        """返回 (高抛结构分 0~1, 低吸结构分 0~1, 说明)。"""
        s = structure or {}
        rev = fwd = 0.5
        notes: List[str] = []
        if s.get('near_resist'):
            rev = min(1.0, rev + 0.35); notes.append('触及日线压力')
        if s.get('td_high9') or s.get('div') == 'top':
            rev = min(1.0, rev + 0.30); notes.append('TD高9/顶背离')
        if s.get('cross') == 'dead_above_zero':
            rev = min(1.0, rev + 0.20); notes.append('MACD零轴上死叉')
        if s.get('near_support'):
            fwd = min(1.0, fwd + 0.35); notes.append('触及日线支撑')
        if s.get('td_low9') or s.get('div') == 'bottom':
            fwd = min(1.0, fwd + 0.30); notes.append('TD低9/底背离')
        if s.get('cross') == 'golden_below_zero':
            fwd = min(1.0, fwd + 0.20); notes.append('MACD零轴下金叉')
        return rev, fwd, notes

    # ---------- 建议比例 ----------
    def suggest_ratio(self, score: float, side: str, avail_ratio: float = 1.0) -> float:
        r = 0.0
        for low, ratio in self.p.ratio_ladder:
            if score >= low:
                r = ratio
                break
        if side == 'forward':
            r *= self.p.forward_ratio_discount
        if side == 'reverse':
            r = min(r, 0.30 * max(0.0, min(1.0, avail_ratio)))   # 卖出不得超过可用底仓比例
        return round(r, 3)

    @staticmethod
    def _clamp01(x: float) -> float:
        return 0.0 if x < 0 else (1.0 if x > 1 else x)

    # ---------- 主入口 ----------
    def evaluate(self, holding: THolding, quote: TQuote,
                 now: Optional[datetime] = None, atr: Optional[float] = None,
                 structure: Optional[Dict[str, Any]] = None,
                 market: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = self.p
        now = now or datetime.now()
        market = market or {}
        price = float(quote.price or 0)
        prev_close = float(quote.prev_close or 0)
        reasons: List[str] = []
        warnings: List[str] = []

        vwap, vwap_src = quote.intraday_vwap()
        if vwap <= 0:
            vwap = price
        if vwap_src.startswith('fallback'):
            warnings.append('成交额缺失，VWAP 退化为典型价(HLC/3)，可靠性下降')

        atr = float(atr or 0) or (prev_close * p.atr_pct_fallback if prev_close else price * p.atr_pct_fallback)
        if atr <= 0:
            atr = max(price * 0.01, 0.01)

        pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
        cost = float(holding.cost or 0.0)
        dev = (price - cost) / cost if cost > 0 else None

        win = resolve_window(now)
        vp = self.volume_price_state(quote, vwap)
        s_rev, s_fwd, s_notes = self.structure_scores(structure)

        # ---- 硬闸门（任何一条成立都不做T）----
        limit_pct = 19.5 if str(holding.code).startswith(('300', '301', '688', '689')) else 9.8
        hard = None
        if limit_pct - 0.5 <= abs(pct) and pct > 0:
            hard = '涨停/接近涨停锁仓'
        elif pct <= -limit_pct + 0.5:
            hard = '跌停/接近跌停，流动性枯竭'
        elif price < vwap * p.vwap_break_pct:
            hard = '跌破VWAP 1.5%，趋弱单边下跌'
        elif vp.get('hard_block'):
            hard = vp['notes'][-1] if vp['notes'] else '量价结构禁止'
        elif win['weight'] <= 0:
            hard = '非交易时段(%s)' % win['cn']

        # ---- 成本维度 ----
        cost_rev = cost_fwd = 0.0
        if dev is None:
            warnings.append('无持仓成本，成本维度按中性处理（请先在持仓表补 cost）')
            cost_rev = cost_fwd = 0.5
        else:
            cost_rev = self._clamp01((dev - p.rev_min_dev) / p.cost_full_dev)
            cost_fwd = self._clamp01((p.fwd_max_dev - dev) / p.cost_full_dev)
            if dev >= 0.10:
                warnings.append('浮盈已超 10%，做T卖飞概率高，建议只做半仓反T')
            if dev <= p.deep_loss_dev:
                cost_fwd = 0.0
                warnings.append('已深套(偏离 %.1f%%)，不要用做T摊薄替代止损判断' % (dev * 100))

        # ---- VWAP 维度 ----
        vwap_rev = self._clamp01((price - vwap) / (p.k_vwap * atr))
        vwap_fwd = self._clamp01((vwap - price) / (p.k_vwap * atr))

        wsum = p.w_cost + p.w_vwap + p.w_vol + p.w_time + p.w_struct
        def _score(cost_s, vwap_s, vol_s, struct_s) -> float:
            raw = (p.w_cost * cost_s + p.w_vwap * vwap_s + p.w_vol * vol_s
                   + p.w_time * win['weight'] + p.w_struct * struct_s) / (wsum or 1.0)
            return round(max(0.0, min(100.0, raw * 100.0)), 1)

        score_rev = _score(cost_rev, vwap_rev, vp['rev_hint'], s_rev)
        score_fwd = _score(cost_fwd, vwap_fwd, vp['fwd_hint'], s_fwd)

        # ---- 降权项 ----
        if market.get('weak'):
            score_fwd = round(score_fwd * 0.55, 1)
            score_rev = round(score_rev * 0.90, 1)
            warnings.append('大盘/板块退潮：低吸降权（沿用原「退潮停低吸」口径）')
        if str(win['key']).startswith(('lull', 'am_late', 'pm_close')):
            warnings.append('当前处于次级流动性时段(%s)，成交稀疏，滑点会放大' % win['cn'])

        # ---- 方向选择：反T 优先（不需额外资金）----
        qty_avail = holding.available_qty(now)
        total_qty = float(holding.qty or 0.0)
        avail_ratio = (qty_avail / total_qty) if total_qty > 0 else 0.0
        side = 'none'
        side_cn = '不做'
        score = max(score_rev, score_fwd)
        if hard is None:
            if score_rev >= p.min_score_action and qty_avail > 0:
                side, side_cn, score = 'reverse', '反T(先卖后买)', score_rev
            elif score_fwd >= p.min_score_action:
                side, side_cn, score = 'forward', '正T(先买后卖)', score_fwd
            elif score_rev >= p.min_score_action and qty_avail <= 0:
                warnings.append('反T分够但今日无可用底仓(T+1)，无法先卖')
        else:
            reasons.append('硬闸门：%s' % hard)

        # ---- 目标价：以 VWAP ± k×ATR 为主，结合成本偏离 ----
        sell_target = round(max(vwap + p.k_vwap * atr, price if side == 'reverse' else 0.0), 2)
        buy_target = round(min(vwap - p.k_vwap * atr, price if side == 'forward' else 10 ** 9), 2)
        if side == 'reverse':
            sell_price, buy_price = max(price, sell_target), buy_target
        elif side == 'forward':
            buy_price, sell_price = min(price, buy_target), sell_target
        else:
            buy_price, sell_price = buy_target, sell_target

        # ---- 建议数量 + 成本预估 ----
        ratio = self.suggest_ratio(score, side, avail_ratio) if side != 'none' else 0.0
        base_qty = qty_avail if side == 'reverse' else total_qty
        suggest_qty = int(base_qty * ratio / 100.0) * 100 if base_qty > 0 else 0
        est = self.estimate_cost(holding, suggest_qty, sell_price, buy_price, side) if suggest_qty > 0 \
            else dict(new_cost=0.0, delta=0.0, delta_pct=0.0, extra_cash=0.0, fees=0.0, note='无建议数量')
        be = self.breakeven_spread(suggest_qty, sell_price) if suggest_qty > 0 else 0.0

        # ---- "做T必须降成本"护栏 ----
        if side != 'none':
            spread = sell_price - buy_price          # 反T=卖价-买回价；正T=卖出价-买入价
            if spread <= be:
                warnings.append('预估价差 %.3f ≤ 盈亏平衡 %.3f，做T等于白交手续费' % (spread, be))
                side, side_cn, score, ratio, suggest_qty = 'none', '不做(价差不足)', max(score_rev, score_fwd), 0.0, 0
            elif est['delta'] >= 0:
                warnings.append('预估不能降低成本(Δ%+.3f%%)，仅在纪律允许时执行' % est['delta_pct'])

        # ---- 文案与等级 ----
        if hard:
            level, text = 'red', '🔴 %s' % hard_label(hard)
            action = '不做T，等条件恢复'
        elif side == 'reverse':
            level = 'red' if score >= p.min_score_strong else 'orange'
            text = ('🔴' if level == 'red' else '🟠') + ' 反T %.0f分' % score
            action = '先卖后买 %.0f股：卖 %.2f → 回落买回 %.2f，成本 → %.3f (%+.3f%%)' % (
                suggest_qty, sell_price, buy_price, est['new_cost'], est['delta_pct'])
        elif side == 'forward':
            level = 'red' if score >= p.min_score_strong else 'orange'
            text = ('🔴' if level == 'red' else '🟠') + ' 正T %.0f分' % score
            action = '先买后卖 %.0f股：买 %.2f → 反弹卖出 %.2f，成本 → %.3f (%+.3f%%)，需资金 %.0f元' % (
                suggest_qty, buy_price, sell_price, est['new_cost'], est['delta_pct'], est['extra_cash'])
        elif score >= max(45.0, p.min_score_action - 15):
            level, text = 'yellow', '🟡 观察 %.0f分' % score
            action = '接近条件，等 VWAP/量价配合'
        else:
            level, text = 'gray', '⚪ 待机'
            action = '观望'

        reasons.extend(vp['notes'] + s_notes)
        if dev is not None:
            reasons.append('成本偏离 %+.2f%%（成本 %.3f / 现价 %.2f）' % (dev * 100, cost, price))
        reasons.append('VWAP %.3f（%s），现价偏离 %+.2fATR' % (vwap, vwap_src, (price - vwap) / atr if atr else 0))
        reasons.append('时段 %s（权重 %.1f）' % (win['cn'], win['weight']))

        risk_status = ('VWAP%s · %s' % ('上方' if price >= vwap else '下方', vp['label']))
        if hard:
            risk_status = '⛔ %s' % hard

        return dict(
            side=side, side_cn=side_cn, score=score,
            score_rev=score_rev, score_fwd=score_fwd,
            level=level, text=text, action=action, risk_status=risk_status,
            vwap=round(vwap, 3), vwap_src=vwap_src,
            dev_pct=None if dev is None else round(dev * 100, 2),
            atr=round(atr, 3), pct=round(pct, 2),
            window=win['key'], window_cn=win['cn'], time_weight=win['weight'],
            vol_state=vp['state'], vol_state_cn=vp['label'],
            suggest_qty=suggest_qty, suggest_ratio=ratio,
            sell_target=sell_target, buy_target=buy_target,
            breakeven_spread=round(be, 4),
            est_cost_after=est['new_cost'], est_cost_delta=est['delta'],
            est_cost_delta_pct=est['delta_pct'], est_extra_cash=est['extra_cash'],
            est_fees=est['fees'],
            hard_block=hard,
            reasons=reasons, warnings=warnings,
            ts=now.strftime('%Y-%m-%d %H:%M:%S'),
        )


# ============================================================
# 写回表格行（字段名沿用 atr_t_widget 既有命名，UI 无需改列即可显示）
# ============================================================
def apply_plan_to_row(row: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    """把引擎产出写回行对象。只覆盖信号/风控/操作三列所需字段，其余原样保留。"""
    row['signal_level'] = plan.get('level', row.get('signal_level'))
    row['signal_text'] = plan.get('text', row.get('signal_text'))
    row['signal_dir'] = {'reverse': 'sell', 'forward': 'buy'}.get(plan.get('side'), None)
    row['action'] = plan.get('action', row.get('action'))
    row['risk_status'] = plan.get('risk_status', row.get('risk_status'))
    row['t_plan'] = plan                      # 供 tooltip / 导出使用
    row['t_score'] = plan.get('score')
    row['t_side'] = plan.get('side')
    row['vwap'] = plan.get('vwap') or row.get('vwap')
    row['vwap_src'] = plan.get('vwap_src')
    row['cost_dev_pct'] = plan.get('dev_pct')
    row['t_window'] = plan.get('window_cn')
    row['vol_state'] = plan.get('vol_state_cn')
    row['est_cost_after'] = plan.get('est_cost_after')
    row['est_cost_delta_pct'] = plan.get('est_cost_delta_pct')
    if plan.get('side') == 'reverse':
        row['sell_point'] = plan.get('sell_target', row.get('sell_point'))
        row['buy_point'] = plan.get('buy_target', row.get('buy_point'))
    elif plan.get('side') == 'forward':
        row['buy_point'] = plan.get('buy_target', row.get('buy_point'))
        row['sell_point'] = plan.get('sell_target', row.get('sell_point'))
    return row


_ENGINE: Optional[IntradayTEngine] = None


def get_engine(params: Optional[TParams] = None) -> IntradayTEngine:
    """进程内单例（UI 线程/后台线程共用一份参数）。"""
    global _ENGINE
    if _ENGINE is None or params is not None:
        _ENGINE = IntradayTEngine(params)
    return _ENGINE
