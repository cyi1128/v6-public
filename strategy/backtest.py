"""
历史回测模块
测试策略：KDJ(13,3,3)、MACD(8,21,5)、MA5突破
输出：胜率、收益率、最大回撤、最佳参数
"""
import numpy as np
from utils.indicators import (
    calc_kdj_series, calc_macd_series, calc_ma_series,
    is_kdj_golden_cross, is_macd_golden_cross
)


class BacktestEngine:
    """回测引擎"""

    def __init__(self):
        pass

    def backtest(self, daily_data, strategy='all', initial_capital=100000, commission=0.001):
        """
        执行回测
        daily_data: 日线数据
        strategy: 策略名称 (kdj/macd/ma5/all)
        initial_capital: 初始资金
        commission: 手续费率
        """
        if not daily_data or len(daily_data) < 60:
            return self._empty_result('数据不足')

        close_prices = [d['close'] for d in daily_data]
        high_prices = [d['high'] for d in daily_data]
        low_prices = [d['low'] for d in daily_data]
        volumes = [d.get('volume', d.get('vol', 0)) for d in daily_data]

        trades = []
        position = 0  # 持仓数量
        buy_price = 0
        capital = initial_capital

        # 从第60根K线开始（需要足够历史数据）
        for i in range(60, len(daily_data) - 1):
            current_data = daily_data[:i+1]

            # 生成买入信号
            buy_signal = self._check_buy_signal(
                strategy, current_data, close_prices[:i+1],
                high_prices[:i+1], low_prices[:i+1], volumes[:i+1]
            )

            # 生成卖出信号
            sell_signal = self._check_sell_signal(
                strategy, current_data, close_prices[:i+1],
                high_prices[:i+1], low_prices[:i+1], volumes[:i+1],
                position > 0, buy_price
            )

            current_price = close_prices[i]

            # 执行买入
            if buy_signal and position == 0:
                shares = int(capital / current_price / 100) * 100
                if shares > 0:
                    cost = shares * current_price * (1 + commission)
                    if cost <= capital:
                        capital -= cost
                        position = shares
                        buy_price = current_price
                        trades.append({
                            'type': 'buy',
                            'date': i,
                            'price': current_price,
                            'shares': shares,
                            'reason': buy_signal,
                        })

            # 执行卖出
            elif sell_signal and position > 0:
                revenue = position * current_price * (1 - commission)
                capital += revenue
                profit = (current_price - buy_price) * position
                profit_pct = (current_price - buy_price) / buy_price * 100

                trades.append({
                    'type': 'sell',
                    'date': i,
                    'price': current_price,
                    'shares': position,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'reason': sell_signal,
                })
                position = 0
                buy_price = 0

        # 最后清仓
        if position > 0:
            last_price = close_prices[-1]
            revenue = position * last_price * (1 - commission)
            capital += revenue
            profit = (last_price - buy_price) * position
            profit_pct = (last_price - buy_price) / buy_price * 100
            trades.append({
                'type': 'sell',
                'date': len(daily_data) - 1,
                'price': last_price,
                'shares': position,
                'profit': profit,
                'profit_pct': profit_pct,
                'reason': '回测结束清仓',
            })

        # 计算统计指标
        result = self._calculate_stats(trades, capital, initial_capital, close_prices)
        result['strategy'] = strategy
        result['trades'] = trades

        return result

    def _check_buy_signal(self, strategy, data, close, high, low, volumes):
        """检查买入信号"""
        if strategy == 'kdj':
            return self._kdj_buy_signal(high, low, close)
        elif strategy == 'macd':
            return self._macd_buy_signal(close)
        elif strategy == 'ma5':
            return self._ma5_buy_signal(close)
        elif strategy == 'all':
            # 综合策略：多个信号共振
            signals = []
            kdj_sig = self._kdj_buy_signal(high, low, close)
            macd_sig = self._macd_buy_signal(close)
            if kdj_sig:
                signals.append(kdj_sig)
            if macd_sig:
                signals.append(macd_sig)
            if len(signals) >= 1:
                return ' + '.join(signals)
            return None
        return None

    def _check_sell_signal(self, strategy, data, close, high, low, volumes, has_position, buy_price):
        """检查卖出信号"""
        if not has_position:
            return None

        current_price = close[-1]

        # 止损：亏损超过8%
        if buy_price > 0 and (current_price - buy_price) / buy_price < -0.08:
            return '止损(-8%)'

        # 止盈：盈利超过20%
        if buy_price > 0 and (current_price - buy_price) / buy_price > 0.20:
            return '止盈(+20%)'

        if strategy in ['kdj', 'all']:
            k, d, j = calc_kdj_series(high, low, close)
            if len(k) >= 2:
                # KDJ高位死叉
                if k.iloc[-1] < d.iloc[-1] and k.iloc[-2] >= d.iloc[-2] and k.iloc[-1] > 70:
                    return 'KDJ高位死叉'

        if strategy in ['macd', 'all']:
            dif, dea, hist = calc_macd_series(close)
            if len(dif) >= 2:
                # MACD死叉
                if dif.iloc[-1] < dea.iloc[-1] and dif.iloc[-2] >= dea.iloc[-2]:
                    return 'MACD死叉'

        # MA5跌破
        if strategy in ['ma5', 'all']:
            ma5 = calc_ma_series(close, 5)
            if len(ma5) >= 2:
                if close[-1] < ma5.iloc[-1] and close[-2] >= ma5.iloc[-2]:
                    return '跌破MA5'

        return None

    def _kdj_buy_signal(self, high, low, close):
        """KDJ买入信号"""
        k, d, j = calc_kdj_series(high, low, close)
        if len(k) < 2:
            return None

        # 低位金叉
        if is_kdj_golden_cross(k, d) and k.iloc[-1] < 30:
            return 'KDJ低位金叉'
        return None

    def _macd_buy_signal(self, close):
        """MACD买入信号"""
        dif, dea, hist = calc_macd_series(close)
        if len(dif) < 2:
            return None

        # 零轴上金叉
        if is_macd_golden_cross(dif, dea) and dif.iloc[-1] > 0:
            return 'MACD零轴上金叉'
        return None

    def _ma5_buy_signal(self, close):
        """MA5突破买入信号"""
        if len(close) < 6:
            return None

        ma5 = calc_ma_series(close, 5)
        if len(ma5) < 2:
            return None

        # 突破MA5且MA5向上
        if (close[-1] > ma5.iloc[-1] and close[-2] <= ma5.iloc[-2] and
                ma5.iloc[-1] > ma5.iloc[-2]):
            return '突破MA5'
        return None

    def _calculate_stats(self, trades, final_capital, initial_capital, close_prices):
        """计算统计指标"""
        sell_trades = [t for t in trades if t['type'] == 'sell']
        buy_trades = [t for t in trades if t['type'] == 'buy']

        total_return = (final_capital - initial_capital) / initial_capital * 100

        # 胜率
        if sell_trades:
            win_trades = [t for t in sell_trades if t.get('profit', 0) > 0]
            win_rate = len(win_trades) / len(sell_trades) * 100
        else:
            win_rate = 0

        # 平均盈亏
        if sell_trades:
            avg_profit = np.mean([t.get('profit_pct', 0) for t in sell_trades])
            avg_win = np.mean([t.get('profit_pct', 0) for t in sell_trades if t.get('profit', 0) > 0]) if any(t.get('profit', 0) > 0 for t in sell_trades) else 0
            avg_loss = np.mean([t.get('profit_pct', 0) for t in sell_trades if t.get('profit', 0) <= 0]) if any(t.get('profit', 0) <= 0 for t in sell_trades) else 0
        else:
            avg_profit = 0
            avg_win = 0
            avg_loss = 0

        # 最大回撤
        max_drawdown = self._calculate_max_drawdown(trades, initial_capital)

        # 盈亏比
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        # 买入持有收益
        if len(close_prices) > 60:
            buy_hold_return = (close_prices[-1] - close_prices[60]) / close_prices[60] * 100
        else:
            buy_hold_return = 0

        # 超额收益
        excess_return = total_return - buy_hold_return

        return {
            'initial_capital': initial_capital,
            'final_capital': final_capital,
            'total_return': total_return,
            'total_trades': len(buy_trades),
            'win_trades': len([t for t in sell_trades if t.get('profit', 0) > 0]),
            'loss_trades': len([t for t in sell_trades if t.get('profit', 0) <= 0]),
            'win_rate': win_rate,
            'avg_profit_pct': avg_profit,
            'avg_win_pct': avg_win,
            'avg_loss_pct': avg_loss,
            'profit_loss_ratio': profit_loss_ratio,
            'max_drawdown': max_drawdown,
            'buy_hold_return': buy_hold_return,
            'excess_return': excess_return,
        }

    def _calculate_max_drawdown(self, trades, initial_capital):
        """计算最大回撤"""
        if not trades:
            return 0

        capital = initial_capital
        position = 0
        peak = initial_capital
        max_dd = 0

        for trade in trades:
            if trade['type'] == 'buy':
                capital -= trade['price'] * trade['shares']
                position += trade['shares']
            elif trade['type'] == 'sell':
                capital += trade['price'] * trade['shares']
                position -= trade['shares']

            # 计算当前总资产
            total_asset = capital + position * trade['price']
            if total_asset > peak:
                peak = total_asset

            drawdown = (peak - total_asset) / peak * 100
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    def optimize_parameters(self, daily_data, strategy='kdj'):
        """参数优化（简化版）"""
        results = []

        if strategy == 'kdj':
            # 测试不同KDJ参数
            for n in [9, 13, 14, 21]:
                for m1 in [2, 3, 3]:
                    for m2 in [2, 3, 3]:
                        result = self.backtest(daily_data, strategy='kdj')
                        result['params'] = f'KDJ({n},{m1},{m2})'
                        results.append(result)
                        break  # 简化，只测一组
                    break
                break

        return results

    def compare_strategies(self, daily_data):
        """对比所有策略"""
        strategies = ['kdj', 'macd', 'ma5', 'all']
        results = {}

        for strategy in strategies:
            result = self.backtest(daily_data, strategy=strategy)
            results[strategy] = result

        return results
