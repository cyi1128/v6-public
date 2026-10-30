# -*- coding: utf-8 -*-
"""
策略名称：三日回调 + 今日放量突破模型（STR-NEW-012）
独立信号源，零侵入原有策略代码。

核心逻辑：
T-4高点 > T-3高点 → T-3阴线 → T-2阴线 → T-1涨跌幅-3%~+2%且收盘<T-2收盘
→ T0阳线 + 放量(>=5日均量1.2倍) + 收盘突破T-1最高价

信号等级：
- A级：放量>=1.5倍
- B级：放量>=1.2倍且<1.5倍

禁止加入的过滤（第一版）：MA/MACD/KDJ/RSI/市值/换手率/板块资金/新闻/RPS
"""
import os
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class Strategy3DayCallbackBreakout:
    """三日回调 + 今日放量突破模型（独立策略）"""

    STRATEGY_NAME = "三日回调 + 今日放量突破模型"
    SIGNAL_SOURCE_TAG = "三日回调突破"
    STRATEGY_ID = "STR-NEW-012"

    # 信号标签
    MAIN_TAG = "三日回调放量突破"
    SUB_TAGS = ["回调完成", "阳线启动", "放量", "突破前高"]

    def __init__(self):
        self._scan_logs = []  # 扫描日志

    def _log(self, msg: str):
        """记录扫描日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] {msg}"
        self._scan_logs.append(log_msg)
        print(log_msg, flush=True)

    def calc_5day_vol_ma(self, kline: List[Dict]) -> float:
        """计算5日均量（不含未来数据，使用T0及之前4天）"""
        if len(kline) < 5:
            return 0.0
        # 取最后5根K线的成交量
        recent_5 = kline[-5:]
        total_vol = sum(float(k.get('volume', 0)) for k in recent_5)
        return total_vol / 5.0

    def calc_pct_change(self, kline: List[Dict]) -> List[float]:
        """计算每根K线的涨跌幅（基于前一日收盘价）"""
        pct_changes = []
        for i in range(len(kline)):
            if i == 0:
                pct_changes.append(0.0)
            else:
                prev_close = float(kline[i - 1].get('close', 0))
                curr_close = float(kline[i].get('close', 0))
                if prev_close > 0:
                    pct_changes.append((curr_close - prev_close) / prev_close)
                else:
                    pct_changes.append(0.0)
        return pct_changes

    def run_single_stock(self, kline: List[Dict], stock_code: str, stock_name: str,
                          verbose: bool = False) -> Optional[Dict]:
        """
        单只股票扫描。

        Args:
            kline: K线数据列表，每根包含date/open/close/high/low/volume
            stock_code: 股票代码
            stock_name: 股票名称
            verbose: 是否输出详细条件日志

        Returns:
            信号字典或None
        """
        # K线前置校验：长度不足5根
        if not kline or len(kline) < 5:
            if verbose:
                self._log(f"[三日回调模型] {stock_code} {stock_name} 跳过：K线不足5根(实际{len(kline) if kline else 0})")
            return None

        # 取最近5根：T-4, T-3, T-2, T-1, T0
        t4 = kline[-5]
        t3 = kline[-4]
        t2 = kline[-3]
        t1 = kline[-2]
        t0 = kline[-1]

        # 数据缺失校验：任意一根所需字段为空或0
        required_fields = ['high', 'open', 'close', 'volume']
        for idx, bar in enumerate([t4, t3, t2, t1, t0]):
            for field in required_fields:
                val = bar.get(field)
                if val is None or val == '' or float(val) <= 0:
                    if verbose:
                        self._log(f"[三日回调模型] {stock_code} {stock_name} 跳过：T-{4-idx} {field}数据缺失({val})")
                    return None

        # 转换为float
        t4_high = float(t4['high'])
        t3_high = float(t3['high'])
        t3_open = float(t3['open'])
        t3_close = float(t3['close'])
        t2_open = float(t2['open'])
        t2_close = float(t2['close'])
        t1_close = float(t1['close'])
        t1_high = float(t1['high'])
        t0_open = float(t0['open'])
        t0_close = float(t0['close'])
        t0_volume = float(t0['volume'])

        # 计算涨跌幅
        pct_changes = self.calc_pct_change(kline)
        t3_pct = pct_changes[-4] if len(pct_changes) >= 4 else 0.0
        t2_pct = pct_changes[-3] if len(pct_changes) >= 3 else 0.0
        t1_pct = pct_changes[-2] if len(pct_changes) >= 2 else 0.0
        t0_pct = pct_changes[-1] if len(pct_changes) >= 1 else 0.0

        # 5日均量
        vol_5ma = self.calc_5day_vol_ma(kline)
        if vol_5ma <= 0:
            if verbose:
                self._log(f"[三日回调模型] {stock_code} {stock_name} 跳过：5日均量为0")
            return None

        vol_multiple = t0_volume / vol_5ma

        # ===== 8项核心条件逐条校验 =====
        # 条件1：high[T-4] > high[T-3]
        cond1 = t4_high > t3_high
        if verbose:
            self._log(f"[三日回调模型-条件1] {stock_code} {'通过' if cond1 else '失败'}: T-4高{t4_high:.2f} {'>' if cond1 else '<='} T-3高{t3_high:.2f}")

        # 条件2：close[T-3] < open[T-3]（T-3阴线）
        cond2 = t3_close < t3_open
        if verbose:
            self._log(f"[三日回调模型-条件2] {stock_code} {'通过' if cond2 else '失败'}: T-3收{t3_close:.2f} {'<' if cond2 else '>='} 开{t3_open:.2f}")

        # 条件3：close[T-2] < open[T-2]（T-2阴线）
        cond3 = t2_close < t2_open
        if verbose:
            self._log(f"[三日回调模型-条件3] {stock_code} {'通过' if cond3 else '失败'}: T-2收{t2_close:.2f} {'<' if cond3 else '>='} 开{t2_open:.2f}")

        # 条件4：-0.03 <= pct_change[T-1] <= 0.02
        cond4 = -0.03 <= t1_pct <= 0.02
        if verbose:
            self._log(f"[三日回调模型-条件4] {stock_code} {'通过' if cond4 else '失败'}: T-1涨跌{t1_pct*100:.2f}% 范围[-3%,+2%]")

        # 条件5：close[T-1] < close[T-2]
        cond5 = t1_close < t2_close
        if verbose:
            self._log(f"[三日回调模型-条件5] {stock_code} {'通过' if cond5 else '失败'}: T-1收{t1_close:.2f} {'<' if cond5 else '>='} T-2收{t2_close:.2f}")

        # 条件6：close[T0] > open[T0]（T0收阳线）
        cond6 = t0_close > t0_open
        if verbose:
            self._log(f"[三日回调模型-条件6] {stock_code} {'通过' if cond6 else '失败'}: T0收{t0_close:.2f} {'>' if cond6 else '<='} 开{t0_open:.2f}")

        # 条件7：volume[T0] >= MA(volume,5)[T0] * 1.20
        cond7 = t0_volume >= vol_5ma * 1.20
        if verbose:
            self._log(f"[三日回调模型-条件7] {stock_code} {'通过' if cond7 else '失败'}: T0量{t0_volume:.0f} {'>=' if cond7 else '<'} 5日均量{vol_5ma:.0f}*1.2={vol_5ma*1.2:.0f}")

        # 条件8：close[T0] > high[T-1]（核心突破确认）
        cond8 = t0_close > t1_high
        if verbose:
            self._log(f"[三日回调模型-条件8] {stock_code} {'通过' if cond8 else '失败'}: T0收{t0_close:.2f} {'>' if cond8 else '<='} T-1高{t1_high:.2f}")

        # 全部条件必须同时成立
        all_pass = cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7 and cond8
        if not all_pass:
            failed = [i + 1 for i, c in enumerate([cond1, cond2, cond3, cond4, cond5, cond6, cond7, cond8]) if not c]
            if verbose:
                self._log(f"[三日回调模型] {stock_code} {stock_name} 未通过，失败条件: {failed}")
            return None

        # 信号等级
        if t0_volume >= vol_5ma * 1.5:
            signal_level = "A"
        else:
            signal_level = "B"

        # 衍生字段（仅展示）
        breakout_pct = (t0_close - t1_high) / t1_high * 100 if t1_high > 0 else 0.0

        result = {
            "strategy_id": self.STRATEGY_ID,
            "strategy_name": self.STRATEGY_NAME,
            "signal_source": self.SIGNAL_SOURCE_TAG,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "today_pct": round(t0_pct * 100, 2),
            "today_close": round(t0_close, 2),
            "today_open": round(t0_open, 2),
            "t1_high": round(t1_high, 2),
            "today_volume": round(t0_volume, 0),
            "vol_5ma": round(vol_5ma, 0),
            "vol_multiple": round(vol_multiple, 2),
            "t4_high": round(t4_high, 2),
            "t3_high": round(t3_high, 2),
            "t3_pct": round(t3_pct * 100, 2),
            "t2_pct": round(t2_pct * 100, 2),
            "t1_pct": round(t1_pct * 100, 2),
            "signal_level": signal_level,
            "breakout_pct": round(breakout_pct, 2),
            "main_tag": self.MAIN_TAG,
            "sub_tags": self.SUB_TAGS.copy(),
            "scan_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "kline_date": t0.get('date', ''),
        }

        self._log(f"[三日回调模型] ✅ {stock_code} {stock_name} 信号生成！等级{signal_level} 放量{vol_multiple:.2f}倍 突破{breakout_pct:.2f}%")
        return result

    def scan_stock_list(self, stocks: List[Dict], kline_provider, days: int = 30,
                        verbose: bool = False) -> List[Dict]:
        """
        批量扫描股票列表。

        Args:
            stocks: 股票列表，每个包含code/name
            kline_provider: K线获取函数，签名 func(code, days) -> List[Dict]
            days: 获取K线天数
            verbose: 是否输出详细日志

        Returns:
            信号列表
        """
        signals = []
        total = len(stocks)
        self._log(f"[三日回调模型] 开始批量扫描，共{total}只股票，K线天数{days}")

        for i, stock in enumerate(stocks):
            code = stock.get('code', '')
            name = stock.get('name', '')
            if not code:
                continue

            try:
                kline = kline_provider(code, days)
                if kline and len(kline) >= 5:
                    result = self.run_single_stock(kline, code, name, verbose=verbose)
                    if result:
                        signals.append(result)
            except Exception as e:
                self._log(f"[三日回调模型] {code} {name} 扫描异常: {e}")

            # 每20只输出一次进度
            if (i + 1) % 20 == 0:
                self._log(f"[三日回调模型] 扫描进度 {i+1}/{total}，已发现信号{len(signals)}只")

        self._log(f"[三日回调模型] 批量扫描完成：{total}只股票，生成信号{len(signals)}只")
        return signals

    def get_scan_logs(self) -> List[str]:
        """获取扫描日志"""
        return self._scan_logs.copy()

    def clear_logs(self):
        """清空日志"""
        self._scan_logs = []


# ============================================================
# 回测引擎
# ============================================================
class Strategy3DayBacktest:
    """三日回调模型回测引擎"""

    def __init__(self, strategy: Strategy3DayCallbackBreakout):
        self.strategy = strategy

    def run_backtest(self, kline: List[Dict], stock_code: str = "", stock_name: str = "",
                     hold_days: int = 5) -> Optional[Dict]:
        """
        对单只股票历史K线进行回测。
        从第5根K线开始，逐日检查是否产生信号，然后计算后续hold_days收益。

        Args:
            kline: 完整历史K线
            stock_code: 股票代码
            stock_name: 股票名称
            hold_days: 持有天数

        Returns:
            回测结果字典
        """
        if not kline or len(kline) < 5 + hold_days:
            return None

        signals = []
        pct_changes = self.strategy.calc_pct_change(kline)

        # 从第5根开始（索引4），到倒数hold_days根
        for i in range(4, len(kline) - hold_days):
            # 取最近5根（以i为T0）
            window = kline[i - 4:i + 1]
            window_pct = pct_changes[i - 4:i + 1]

            t4 = window[0]
            t3 = window[1]
            t2 = window[2]
            t1 = window[3]
            t0 = window[4]

            # 数据校验
            try:
                t4_high = float(t4['high'])
                t3_high = float(t3['high'])
                t3_open = float(t3['open'])
                t3_close = float(t3['close'])
                t2_open = float(t2['open'])
                t2_close = float(t2['close'])
                t1_close = float(t1['close'])
                t1_high = float(t1['high'])
                t0_open = float(t0['open'])
                t0_close = float(t0['close'])
                t0_volume = float(t0['volume'])
            except (KeyError, ValueError, TypeError):
                continue

            if any(v <= 0 for v in [t4_high, t3_high, t3_open, t3_close, t2_open, t2_close, t1_close, t1_high, t0_open, t0_close, t0_volume]):
                continue

            # 5日均量
            vol_5ma = sum(float(k.get('volume', 0)) for k in window) / 5.0
            if vol_5ma <= 0:
                continue

            t3_pct = window_pct[1] if len(window_pct) > 1 else 0
            t2_pct = window_pct[2] if len(window_pct) > 2 else 0
            t1_pct = window_pct[3] if len(window_pct) > 3 else 0

            # 8项条件
            cond1 = t4_high > t3_high
            cond2 = t3_close < t3_open
            cond3 = t2_close < t2_open
            cond4 = -0.03 <= t1_pct <= 0.02
            cond5 = t1_close < t2_close
            cond6 = t0_close > t0_open
            cond7 = t0_volume >= vol_5ma * 1.20
            cond8 = t0_close > t1_high

            if not (cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7 and cond8):
                continue

            # 信号生成日（T0收盘），下一个交易日开仓
            signal_date = t0.get('date', '')
            entry_price = float(kline[i + 1].get('open', t0_close))  # 次日开盘买入

            # 计算hold_days收益
            returns = {}
            for hd in [1, 3, 5, 10]:
                if i + 1 + hd < len(kline):
                    exit_price = float(kline[i + 1 + hd].get('close', entry_price))
                    returns[f'{hd}d_return'] = round((exit_price - entry_price) / entry_price * 100, 2)
                else:
                    returns[f'{hd}d_return'] = None

            vol_multiple = t0_volume / vol_5ma
            signal_level = "A" if t0_volume >= vol_5ma * 1.5 else "B"

            signals.append({
                'signal_date': signal_date,
                'entry_price': round(entry_price, 2),
                'signal_level': signal_level,
                'vol_multiple': round(vol_multiple, 2),
                **returns,
            })

        if not signals:
            return None

        # 统计
        all_returns_1d = [s['1d_return'] for s in signals if s['1d_return'] is not None]
        all_returns_3d = [s['3d_return'] for s in signals if s['3d_return'] is not None]
        all_returns_5d = [s['5d_return'] for s in signals if s['5d_return'] is not None]
        all_returns_10d = [s['10d_return'] for s in signals if s['10d_return'] is not None]

        def calc_stats(rets):
            if not rets:
                return {'count': 0, 'win_rate': 0, 'avg_return': 0, 'median_return': 0,
                        'max_return': 0, 'max_loss': 0, 'profit_loss_ratio': 0}
            wins = [r for r in rets if r > 0]
            losses = [r for r in rets if r <= 0]
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = abs(sum(losses) / len(losses)) if losses else 0
            sorted_rets = sorted(rets)
            median = sorted_rets[len(sorted_rets) // 2]
            return {
                'count': len(rets),
                'win_rate': round(len(wins) / len(rets) * 100, 2),
                'avg_return': round(sum(rets) / len(rets), 2),
                'median_return': round(median, 2),
                'max_return': round(max(rets), 2),
                'max_loss': round(min(rets), 2),
                'profit_loss_ratio': round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
            }

        return {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'total_signals': len(signals),
            'signals': signals,
            'stats_1d': calc_stats(all_returns_1d),
            'stats_3d': calc_stats(all_returns_3d),
            'stats_5d': calc_stats(all_returns_5d),
            'stats_10d': calc_stats(all_returns_10d),
        }


# ============================================================
# 便捷函数
# ============================================================
def get_strategy_3day_callback_breakout() -> Strategy3DayCallbackBreakout:
    """获取策略单例"""
    return Strategy3DayCallbackBreakout()


def scan_3day_callback_breakout(stocks: List[Dict], kline_provider, days: int = 30,
                                 verbose: bool = False) -> Tuple[List[Dict], List[str]]:
    """
    便捷扫描函数。

    Returns:
        (信号列表, 日志列表)
    """
    strategy = Strategy3DayCallbackBreakout()
    signals = strategy.scan_stock_list(stocks, kline_provider, days=days, verbose=verbose)
    logs = strategy.get_scan_logs()
    return signals, logs


if __name__ == '__main__':
    # 快速自测
    print("=" * 60)
    print("三日回调 + 今日放量突破模型（STR-NEW-012）自测")
    print("=" * 60)

    strategy = Strategy3DayCallbackBreakout()

    # 构造测试K线（满足全部条件）
    test_kline = [
        {'date': '2026-08-25', 'open': 10.5, 'high': 11.0, 'low': 10.4, 'close': 10.8, 'volume': 100000},  # T-4 高点11.0
        {'date': '2026-08-26', 'open': 10.9, 'high': 10.95, 'low': 10.2, 'close': 10.3, 'volume': 90000},   # T-3 阴线 收10.3<开10.9 高点10.95<11.0
        {'date': '2026-08-27', 'open': 10.4, 'high': 10.5, 'low': 9.8, 'close': 9.9, 'volume': 80000},      # T-2 阴线 收9.9<开10.4
        {'date': '2026-08-28', 'open': 10.0, 'high': 10.1, 'low': 9.7, 'close': 9.8, 'volume': 70000},      # T-1 涨跌-1.01% 收9.8<T-2收9.9 高点10.1
        {'date': '2026-08-29', 'open': 9.9, 'high': 10.5, 'low': 9.85, 'close': 10.3, 'volume': 150000},    # T0 阳线 收10.3>开9.9 放量1.875倍 收10.3>T-1高10.1
    ]

    print("\n测试K线（5根）：")
    for k in test_kline:
        print(f"  {k['date']} 开{k['open']} 高{k['high']} 低{k['low']} 收{k['close']} 量{k['volume']}")

    print("\n执行单股扫描（verbose=True）：")
    result = strategy.run_single_stock(test_kline, '000001', '平安银行', verbose=True)

    print("\n扫描结果：")
    if result:
        for k, v in result.items():
            print(f"  {k}: {v}")
    else:
        print("  无信号（测试数据应满足条件，请检查）")

    print("\n自测完成。")
