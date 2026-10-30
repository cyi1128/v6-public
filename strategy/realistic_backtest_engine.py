# -*- coding: utf-8 -*-
"""
V6.4 阶段5：回测真实性增强引擎

新增独立模块，不修改现有回测核心逻辑。
提供防未来函数检测、T+1成交、滑点、手续费、印花税、成交限制，
让回测结果接近真实交易。

核心类：RealisticBacktestEngine

使用方式：
    from strategy.realistic_backtest_engine import RealisticBacktestEngine

    engine = RealisticBacktestEngine(enable_realistic=True)
    result = engine.run_backtest(signals, kline_data)

    # 关闭真实性增强（向后兼容，使用原始逻辑）
    engine_naive = RealisticBacktestEngine(enable_realistic=False)
"""

import os
import sys
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================

@dataclass
class TradeRecord:
    """单笔交易记录"""
    trade_id: int = 0
    signal_date: str = ""       # 信号产生日（T日）
    trade_date: str = ""        # 实际成交日（T+1日）
    type: str = ""              # buy / sell
    signal_price: float = 0.0   # 信号日收盘价
    open_price: float = 0.0     # 成交日开盘价
    exec_price: float = 0.0     # 实际成交价（含滑点）
    shares: int = 0             # 成交股数
    amount: float = 0.0         # 成交金额
    commission: float = 0.0     # 佣金
    stamp_tax: float = 0.0      # 印花税（仅卖出）
    slippage_cost: float = 0.0  # 滑点成本
    total_cost: float = 0.0     # 总费用（佣金+印花税+滑点）
    delay_days: int = 0         # 成交延迟天数（因涨跌停/停牌顺延）
    reason: str = ""            # 信号原因
    # 卖出时填充
    profit: float = 0.0         # 盈亏金额
    profit_pct: float = 0.0     # 盈亏比例
    holding_days: int = 0       # 持仓天数

    def to_dict(self) -> Dict:
        return {
            "trade_id": self.trade_id,
            "signal_date": self.signal_date,
            "trade_date": self.trade_date,
            "type": self.type,
            "signal_price": round(self.signal_price, 2),
            "open_price": round(self.open_price, 2),
            "exec_price": round(self.exec_price, 4),
            "shares": self.shares,
            "amount": round(self.amount, 2),
            "commission": round(self.commission, 2),
            "stamp_tax": round(self.stamp_tax, 2),
            "slippage_cost": round(self.slippage_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "delay_days": self.delay_days,
            "reason": self.reason,
            "profit": round(self.profit, 2),
            "profit_pct": round(self.profit_pct, 2),
            "holding_days": self.holding_days,
        }


@dataclass
class BacktestMetrics:
    """回测指标"""
    total_return: float = 0.0           # 总收益率 %
    annual_return: float = 0.0          # 年化收益率 %
    max_drawdown: float = 0.0           # 最大回撤 %
    win_rate: float = 0.0               # 胜率 %
    profit_loss_ratio: float = 0.0      # 盈亏比
    trade_count: int = 0                # 交易次数（完整买卖对）
    avg_holding_days: float = 0.0       # 平均持仓天数
    sharpe_ratio: float = 0.0           # 夏普比率
    total_commission: float = 0.0       # 手续费总额
    total_stamp_tax: float = 0.0        # 印花税总额
    total_slippage: float = 0.0         # 滑点成本总额
    total_cost: float = 0.0             # 总交易成本
    initial_capital: float = 0.0        # 初始资金
    final_capital: float = 0.0          # 最终资金
    # 防未来函数检测
    future_function_detected: int = 0   # 检测到的未来函数次数
    future_function_fixed: int = 0      # 修正次数
    # 成交限制
    limit_up_skip: int = 0              # 涨停无法买入次数
    limit_down_skip: int = 0            # 跌停无法卖出次数
    volume_limit_skip: int = 0          # 成交量限制跳过次数

    def to_dict(self) -> Dict:
        return {
            "total_return": round(self.total_return, 2),
            "annual_return": round(self.annual_return, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "win_rate": round(self.win_rate, 2),
            "profit_loss_ratio": round(self.profit_loss_ratio, 2),
            "trade_count": self.trade_count,
            "avg_holding_days": round(self.avg_holding_days, 1),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "total_commission": round(self.total_commission, 2),
            "total_stamp_tax": round(self.total_stamp_tax, 2),
            "total_slippage": round(self.total_slippage, 2),
            "total_cost": round(self.total_cost, 2),
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.final_capital, 2),
            "future_function_detected": self.future_function_detected,
            "future_function_fixed": self.future_function_fixed,
            "limit_up_skip": self.limit_up_skip,
            "limit_down_skip": self.limit_down_skip,
            "volume_limit_skip": self.volume_limit_skip,
        }


@dataclass
class BacktestResult:
    """回测完整结果"""
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)
    config: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "metrics": self.metrics.to_dict(),
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": self.equity_curve,
            "config": self.config,
        }


# ============================================================
# 真实性增强回测引擎
# ============================================================

class RealisticBacktestEngine:
    """
    V6.4 真实性增强回测引擎

    增强项：
      - 防未来函数检测（T日信号 → T+1成交）
      - T+1成交机制
      - 滑点（默认0.1%）
      - 手续费（万2.5，最低5元）
      - 印花税（千1，仅卖出）
      - 成交限制（量比10%、涨跌停、停牌）

    可通过 enable_realistic=False 关闭所有增强，使用原始逻辑（T日收盘价成交，无费用）。
    """

    def __init__(
        self,
        enable_realistic: bool = True,
        commission_rate: float = 0.00025,   # 万2.5
        min_commission: float = 5.0,         # 最低5元
        stamp_tax: float = 0.001,            # 千1
        slippage: float = 0.001,             # 0.1%
        max_volume_ratio: float = 0.1,       # 单笔不超过当日成交量10%
        initial_capital: float = 100000.0,   # 初始资金10万
    ):
        self.enable_realistic = enable_realistic
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax_rate = stamp_tax
        self.slippage = slippage
        self.max_volume_ratio = max_volume_ratio
        self.initial_capital = initial_capital

    # ============================================================
    # 主入口：运行回测
    # ============================================================

    def run_backtest(
        self,
        signals: List[Dict],
        kline_data: List[Dict],
    ) -> BacktestResult:
        """
        运行回测。

        Args:
            signals: 信号列表，每个元素包含:
                     - date: 信号日期 (str, YYYYMMDD)
                     - type: 'buy' / 'sell'
                     - price: 信号日价格（可选，默认取当日收盘价）
                     - volume: 信号建议成交量（可选）
                     - reason: 信号原因（可选）
            kline_data: K线数据列表，每个元素包含:
                        - date, open, high, low, close, volume

        Returns:
            BacktestResult，包含交易记录、指标、权益曲线
        """
        result = BacktestResult()
        result.config = {
            "enable_realistic": self.enable_realistic,
            "commission_rate": self.commission_rate,
            "min_commission": self.min_commission,
            "stamp_tax": self.stamp_tax_rate,
            "slippage": self.slippage,
            "max_volume_ratio": self.max_volume_ratio,
            "initial_capital": self.initial_capital,
        }

        if not signals or not kline_data:
            result.metrics.initial_capital = self.initial_capital
            result.metrics.final_capital = self.initial_capital
            return result

        # 构建日期索引
        date_index = {}
        for i, k in enumerate(kline_data):
            d = str(k.get("date", k.get("trade_date", "")))
            date_index[d] = i

        # 排序信号
        sorted_signals = sorted(signals, key=lambda s: s.get("date", ""))

        # 回测状态
        capital = self.initial_capital
        position = 0          # 持仓股数
        avg_cost = 0.0        # 持仓成本价
        buy_trade = None      # 当前持仓的买入记录
        trade_id = 0
        all_trades: List[TradeRecord] = []
        equity_curve = []

        # 防未来函数检测统计
        future_detected = 0
        future_fixed = 0
        limit_up_skip = 0
        limit_down_skip = 0
        volume_limit_skip = 0

        for sig in sorted_signals:
            sig_date = str(sig.get("date", ""))
            sig_type = sig.get("type", "").lower()
            sig_price = sig.get("price")
            sig_reason = sig.get("reason", "")

            if sig_date not in date_index:
                continue
            sig_idx = date_index[sig_date]

            # 信号日收盘价
            if sig_price is None:
                sig_price = kline_data[sig_idx].get("close", 0)

            # 确定成交日索引
            if self.enable_realistic:
                # T+1成交
                trade_idx = sig_idx + 1
                delay = 0
                # 检查成交限制，顺延
                while trade_idx < len(kline_data):
                    day = kline_data[trade_idx]
                    open_price = day.get("open", 0)
                    prev_close = kline_data[trade_idx - 1].get("close", 0)
                    day_volume = day.get("volume", 0)

                    # 停牌检测（开盘价为0或成交量为0）
                    if open_price <= 0 or day_volume <= 0:
                        trade_idx += 1
                        delay += 1
                        continue

                    # 涨停检测（买入时）
                    if sig_type == "buy" and prev_close > 0:
                        limit_up_price = round(prev_close * 1.1, 2)
                        if open_price >= limit_up_price:
                            limit_up_skip += 1
                            trade_idx += 1
                            delay += 1
                            continue

                    # 跌停检测（卖出时）
                    if sig_type == "sell" and prev_close > 0:
                        limit_down_price = round(prev_close * 0.9, 2)
                        if open_price <= limit_down_price:
                            limit_down_skip += 1
                            trade_idx += 1
                            delay += 1
                            continue

                    # 成交量限制
                    if sig_type == "buy" and position == 0:
                        max_shares_by_vol = int(day_volume * self.max_volume_ratio / 100) * 100
                        if max_shares_by_vol < 100:
                            volume_limit_skip += 1
                            trade_idx += 1
                            delay += 1
                            continue
                    break

                if trade_idx >= len(kline_data):
                    continue  # 无法成交

                # 防未来函数检测
                if not self._check_future_function(sig_date, kline_data[trade_idx].get("date", "")):
                    future_detected += 1
                    future_fixed += 1  # 已通过T+1机制修正

                trade_date = str(kline_data[trade_idx].get("date", ""))
                open_price = kline_data[trade_idx].get("open", 0)
                day_volume = kline_data[trade_idx].get("volume", 0)
            else:
                # 原始逻辑：T日收盘价成交（无真实性增强）
                trade_idx = sig_idx
                trade_date = sig_date
                open_price = sig_price  # 用收盘价
                day_volume = kline_data[sig_idx].get("volume", 0)
                delay = 0

            # 执行交易
            if sig_type == "buy" and position == 0:
                # 计算可买股数
                if self.enable_realistic:
                    exec_price = self._calculate_buy_price(open_price)
                    max_shares_by_capital = int(capital / exec_price / 100) * 100
                    max_shares_by_vol = int(day_volume * self.max_volume_ratio / 100) * 100
                    shares = min(max_shares_by_capital, max_shares_by_vol)
                else:
                    exec_price = open_price
                    shares = int(capital / exec_price / 100) * 100

                if shares < 100:
                    continue

                amount = shares * exec_price
                commission = self._calculate_commission(amount)
                stamp = 0.0
                slippage_cost = (exec_price - open_price) * shares if self.enable_realistic else 0.0
                total_cost = commission + stamp + slippage_cost

                if amount + commission > capital:
                    # 资金不足，减少股数
                    shares = int((capital - self.min_commission) / exec_price / 100) * 100
                    if shares < 100:
                        continue
                    amount = shares * exec_price
                    commission = self._calculate_commission(amount)
                    total_cost = commission

                capital -= (amount + commission)
                position = shares
                avg_cost = exec_price

                trade_id += 1
                record = TradeRecord(
                    trade_id=trade_id,
                    signal_date=sig_date,
                    trade_date=trade_date,
                    type="buy",
                    signal_price=float(sig_price),
                    open_price=float(open_price),
                    exec_price=float(exec_price),
                    shares=shares,
                    amount=round(amount, 2),
                    commission=round(commission, 2),
                    stamp_tax=0.0,
                    slippage_cost=round(slippage_cost, 2),
                    total_cost=round(total_cost, 2),
                    delay_days=delay,
                    reason=sig_reason,
                )
                all_trades.append(record)
                buy_trade = record

            elif sig_type == "sell" and position > 0:
                if self.enable_realistic:
                    exec_price = self._calculate_sell_price(open_price)
                else:
                    exec_price = open_price

                shares = position
                amount = shares * exec_price
                commission = self._calculate_commission(amount)
                stamp = self._calculate_stamp_tax(amount) if self.enable_realistic else 0.0
                slippage_cost = (open_price - exec_price) * shares if self.enable_realistic else 0.0
                total_cost = commission + stamp + slippage_cost

                capital += (amount - commission - stamp)
                profit = (exec_price - avg_cost) * shares - commission - stamp - slippage_cost
                profit_pct = (exec_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

                # 持仓天数
                holding_days = 0
                if buy_trade:
                    buy_idx = date_index.get(buy_trade.trade_date, sig_idx)
                    holding_days = trade_idx - buy_idx

                trade_id += 1
                record = TradeRecord(
                    trade_id=trade_id,
                    signal_date=sig_date,
                    trade_date=trade_date,
                    type="sell",
                    signal_price=float(sig_price),
                    open_price=float(open_price),
                    exec_price=float(exec_price),
                    shares=shares,
                    amount=round(amount, 2),
                    commission=round(commission, 2),
                    stamp_tax=round(stamp, 2),
                    slippage_cost=round(slippage_cost, 2),
                    total_cost=round(total_cost, 2),
                    delay_days=delay,
                    reason=sig_reason,
                    profit=round(profit, 2),
                    profit_pct=round(profit_pct, 2),
                    holding_days=holding_days,
                )
                all_trades.append(record)
                position = 0
                avg_cost = 0.0
                buy_trade = None

            # 记录权益曲线
            equity = capital + position * (kline_data[trade_idx].get("close", 0) if trade_idx < len(kline_data) else 0)
            equity_curve.append({
                "date": trade_date,
                "equity": round(equity, 2),
                "position": position,
            })

        # 最后清仓（按最后收盘价）
        if position > 0 and kline_data:
            last_day = kline_data[-1]
            last_price = last_day.get("close", 0)
            if self.enable_realistic:
                exec_price = self._calculate_sell_price(last_price)
            else:
                exec_price = last_price
            amount = position * exec_price
            commission = self._calculate_commission(amount)
            stamp = self._calculate_stamp_tax(amount) if self.enable_realistic else 0.0
            capital += (amount - commission - stamp)
            profit = (exec_price - avg_cost) * position - commission - stamp
            profit_pct = (exec_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0

            trade_id += 1
            all_trades.append(TradeRecord(
                trade_id=trade_id,
                signal_date="END",
                trade_date=str(last_day.get("date", "")),
                type="sell",
                signal_price=float(last_price),
                open_price=float(last_price),
                exec_price=float(exec_price),
                shares=position,
                amount=round(amount, 2),
                commission=round(commission, 2),
                stamp_tax=round(stamp, 2),
                slippage_cost=0.0,
                total_cost=round(commission + stamp, 2),
                reason="回测结束清仓",
                profit=round(profit, 2),
                profit_pct=round(profit_pct, 2),
            ))
            position = 0

        # 计算指标
        metrics = self._calculate_metrics(
            all_trades, equity_curve, capital,
            future_detected, future_fixed,
            limit_up_skip, limit_down_skip, volume_limit_skip,
        )

        result.trades = all_trades
        result.equity_curve = equity_curve
        result.metrics = metrics

        return result

    # ============================================================
    # 防未来函数检测
    # ============================================================

    @staticmethod
    def _check_future_function(signal_date: str, trade_date: str) -> bool:
        """
        防未来函数检测。

        规则：信号产生日期必须 < 成交日期（T+1）。
        如果 signal_date >= trade_date，说明存在未来函数。

        Returns:
            True: 正常（无未来函数）
            False: 检测到未来函数
        """
        if not signal_date or not trade_date:
            return False
        return signal_date < trade_date

    # ============================================================
    # 价格计算（含滑点）
    # ============================================================

    def _calculate_buy_price(self, open_price: float) -> float:
        """买入成交价 = 开盘价 × (1 + 滑点)"""
        if not self.enable_realistic:
            return open_price
        return open_price * (1 + self.slippage)

    def _calculate_sell_price(self, open_price: float) -> float:
        """卖出成交价 = 开盘价 × (1 - 滑点)"""
        if not self.enable_realistic:
            return open_price
        return open_price * (1 - self.slippage)

    # ============================================================
    # 费用计算
    # ============================================================

    def _calculate_commission(self, amount: float) -> float:
        """
        佣金计算：max(成交金额 × 佣金率, 最低佣金)
        买入和卖出都收取。
        """
        if not self.enable_realistic:
            return 0.0
        return max(amount * self.commission_rate, self.min_commission)

    def _calculate_stamp_tax(self, amount: float) -> float:
        """
        印花税：成交金额 × 税率
        仅卖出时收取。
        """
        if not self.enable_realistic:
            return 0.0
        return amount * self.stamp_tax_rate

    # ============================================================
    # 成交限制检查
    # ============================================================

    def _check_trade_limit(
        self,
        signal_volume: int,
        day_volume: float,
        is_limit_up: bool = False,
        is_limit_down: bool = False,
        is_suspended: bool = False,
    ) -> Tuple[bool, str]:
        """
        成交限制检查。

        Returns:
            (can_trade, reason)
        """
        if is_suspended:
            return False, "停牌"
        if is_limit_up:
            return False, "涨停无法买入"
        if is_limit_down:
            return False, "跌停无法卖出"
        if signal_volume > day_volume * self.max_volume_ratio:
            return False, "超过成交量限制"
        return True, "正常"

    # ============================================================
    # 回测指标计算
    # ============================================================

    def _calculate_metrics(
        self,
        trades: List[TradeRecord],
        equity_curve: List[Dict],
        final_capital: float,
        future_detected: int,
        future_fixed: int,
        limit_up_skip: int,
        limit_down_skip: int,
        volume_limit_skip: int,
    ) -> BacktestMetrics:
        """计算回测指标"""
        m = BacktestMetrics()
        m.initial_capital = self.initial_capital
        m.final_capital = final_capital

        # 总收益率
        m.total_return = (final_capital - self.initial_capital) / self.initial_capital * 100

        # 卖出交易记录（完整交易对）
        sell_trades = [t for t in trades if t.type == "sell" and t.trade_id > 0]
        m.trade_count = len(sell_trades)

        # 胜率
        if sell_trades:
            wins = [t for t in sell_trades if t.profit > 0]
            losses = [t for t in sell_trades if t.profit <= 0]
            m.win_rate = len(wins) / len(sell_trades) * 100

            # 盈亏比
            avg_win = np.mean([t.profit for t in wins]) if wins else 0
            avg_loss = abs(np.mean([t.profit for t in losses])) if losses else 0
            m.profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf") if avg_win > 0 else 0

            # 平均持仓天数
            m.avg_holding_days = np.mean([t.holding_days for t in sell_trades])

        # 最大回撤
        if equity_curve:
            equities = [e["equity"] for e in equity_curve]
            peak = equities[0]
            max_dd = 0
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
            m.max_drawdown = max_dd

        # 年化收益率
        if equity_curve and len(equity_curve) > 1:
            days = len(equity_curve)
            years = days / 252.0
            if years > 0:
                m.annual_return = (
                    (1 + m.total_return / 100) ** (1 / years) - 1
                ) * 100

        # 夏普比率（简化版：用日收益率）
        if equity_curve and len(equity_curve) > 2:
            daily_returns = []
            for i in range(1, len(equity_curve)):
                prev = equity_curve[i - 1]["equity"]
                curr = equity_curve[i]["equity"]
                if prev > 0:
                    daily_returns.append((curr - prev) / prev)
            if daily_returns:
                mean_ret = np.mean(daily_returns)
                std_ret = np.std(daily_returns)
                if std_ret > 0:
                    m.sharpe_ratio = (mean_ret / std_ret) * np.sqrt(252)

        # 费用统计
        m.total_commission = sum(t.commission for t in trades)
        m.total_stamp_tax = sum(t.stamp_tax for t in trades)
        m.total_slippage = sum(t.slippage_cost for t in trades)
        m.total_cost = m.total_commission + m.total_stamp_tax + m.total_slippage

        # 防未来函数检测
        m.future_function_detected = future_detected
        m.future_function_fixed = future_fixed
        m.limit_up_skip = limit_up_skip
        m.limit_down_skip = limit_down_skip
        m.volume_limit_skip = volume_limit_skip

        return m

    # ============================================================
    # 便捷方法：生成简单策略信号
    # ============================================================

    @staticmethod
    def generate_ma_crossover_signals(
        kline_data: List[Dict],
        short_period: int = 5,
        long_period: int = 20,
    ) -> List[Dict]:
        """
        生成均线交叉信号（用于测试）。

        金叉买入，死叉卖出。
        信号在T日收盘产生，T+1开盘成交。
        """
        if not kline_data or len(kline_data) < long_period + 1:
            return []

        closes = [k.get("close", 0) for k in kline_data]
        signals = []

        for i in range(long_period, len(kline_data) - 1):
            ma_short = np.mean(closes[i - short_period + 1:i + 1])
            ma_long = np.mean(closes[i - long_period + 1:i + 1])
            ma_short_prev = np.mean(closes[i - short_period:i])
            ma_long_prev = np.mean(closes[i - long_period:i])

            date = str(kline_data[i].get("date", ""))

            # 金叉：短期均线上穿长期均线
            if ma_short_prev <= ma_long_prev and ma_short > ma_long:
                signals.append({
                    "date": date,
                    "type": "buy",
                    "price": closes[i],
                    "reason": f"MA{short_period}上穿MA{long_period}",
                })
            # 死叉：短期均线下穿长期均线
            elif ma_short_prev >= ma_long_prev and ma_short < ma_long:
                signals.append({
                    "date": date,
                    "type": "sell",
                    "price": closes[i],
                    "reason": f"MA{short_period}下穿MA{long_period}",
                })

        return signals


# ============================================================
# 便捷函数
# ============================================================

_default_engine = None


def get_realistic_backtest_engine(**kwargs) -> RealisticBacktestEngine:
    """获取真实性增强回测引擎单例"""
    global _default_engine
    if _default_engine is None:
        _default_engine = RealisticBacktestEngine(**kwargs)
    return _default_engine
