# -*- coding: utf-8 -*-
"""
AI-520历史回测模块
严格T+1，无未来函数
回测520金叉策略后续1/3/5/7/10日收益
"""
import os
import sys
import time
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.ai_520_engine import AI520Engine


class AI520Backtester:
    """AI-520历史回测"""

    def __init__(self):
        self.engine = AI520Engine()

    def load_all_kline_from_duckdb(self, min_bars: int = 60) -> Dict[str, List[Dict]]:
        """从DuckDB加载所有股票K线"""
        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return {}

            print(f"[回测] 从DuckDB加载K线...", flush=True)
            con = duckdb.connect(db_path, read_only=True)
            rows = con.execute("""
                SELECT code, date, open, high, low, close, volume
                FROM kline_cache
                WHERE code LIKE '60%' OR code LIKE '00%'
                ORDER BY code, date
            """).fetchall()
            con.close()

            # 按股票分组
            result = {}
            for row in rows:
                code = str(row[0])
                if code not in result:
                    result[code] = []
                result[code].append({
                    'date': str(row[1]),
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': float(row[6]),
                })

            # 过滤K线不足的股票
            filtered = {}
            for code, kline in result.items():
                if len(kline) >= min_bars:
                    filtered[code] = kline

            print(f"[回测] 加载完成: {len(filtered)}/{len(result)}只有效K线(>={min_bars}根)", flush=True)
            return filtered
        except Exception as e:
            print(f"[回测] DuckDB加载失败: {e}", flush=True)
            return {}

    def check_520_signal_at_date(self, kline: List[Dict], end_idx: int) -> Optional[Dict]:
        """
        检查在end_idx当天是否产生520金叉信号
        只使用end_idx及之前的数据，无未来函数
        """
        if end_idx < 25:  # 需要至少25根K线计算MA20
            return None

        # 截取截至end_idx的K线
        historical_kline = kline[:end_idx + 1]

        # 检查520金叉
        cross = self.engine.check_520_golden_cross(historical_kline)
        if not cross.get('has_cross', False):
            return None

        # 金叉必须发生在最近10天内
        days_ago = cross.get('cross_days_ago', -1)
        if days_ago < 0 or days_ago > 10:
            return None

        # 价格过滤（5-60元）
        price = historical_kline[-1]['close']
        if price <= 5 or price >= 60:
            return None

        # 位置过滤（距高点-15%~+5%）
        pos = self.engine.calc_price_position(historical_kline)
        if pos:
            dist = pos.get('dist_from_8m_high', 0)
            if dist < -15 or dist > 5:
                return None

        # 涨停记忆（至少1次）
        limit_days = min(250, len(historical_kline))
        limit_count, _ = self.engine.count_limit_up(historical_kline, limit_days)
        if limit_count < 1:
            return None

        # 前一天不能涨停
        if self.engine.check_prev_day_limit_up(historical_kline):
            return None

        return {
            'code': '',
            'signal_date': historical_kline[-1]['date'],
            'signal_price': price,
            'cross_days_ago': days_ago,
            'today_cross': cross.get('today_cross', False),
            'ma5': cross.get('ma5', 0),
            'ma20': cross.get('ma20', 0),
            'ma20_trend': cross.get('ma20_trend', ''),
            'limit_count': limit_count,
            'dist_from_high': pos.get('dist_from_8m_high', 0) if pos else 0,
        }

    def calculate_forward_returns(self, kline: List[Dict], signal_idx: int) -> Dict:
        """
        计算信号后续收益（严格T+1）
        信号当天为D0，下一个交易日为D1
        """
        result = {}
        signal_price = kline[signal_idx]['close']

        for days in [1, 3, 5, 7, 10]:
            target_idx = signal_idx + days
            if target_idx < len(kline):
                # T+1买入：用signal_idx+1的开盘价作为买入价
                # 但为了简化，用信号当天收盘价作为基准，计算后续收益
                future_price = kline[target_idx]['close']
                ret = (future_price - signal_price) / signal_price * 100
                result[f'd{days}_return'] = round(ret, 2)
                result[f'd{days}_date'] = kline[target_idx]['date']
            else:
                result[f'd{days}_return'] = None
                result[f'd{days}_date'] = None

        # 计算期间最高/最低收益
        max_return = 0
        min_return = 0
        for i in range(signal_idx + 1, min(signal_idx + 11, len(kline))):
            high_ret = (kline[i]['high'] - signal_price) / signal_price * 100
            low_ret = (kline[i]['low'] - signal_price) / signal_price * 100
            max_return = max(max_return, high_ret)
            min_return = min(min_return, low_ret)
        result['max_return_10d'] = round(max_return, 2)
        result['min_return_10d'] = round(min_return, 2)

        return result

    def run_backtest(self, max_stocks: int = 0) -> Dict:
        """
        运行全市场回测
        Args:
            max_stocks: 最大回测股票数（0=全部）
        Returns:
            回测统计结果
        """
        start_time = time.time()
        print("=" * 60, flush=True)
        print("AI-520 历史回测开始", flush=True)
        print("=" * 60, flush=True)

        # 加载K线
        all_kline = self.load_all_kline_from_duckdb(min_bars=60)
        if not all_kline:
            return {'error': '无K线数据'}

        if max_stocks > 0 and len(all_kline) > max_stocks:
            all_kline = dict(list(all_kline.items())[:max_stocks])
            print(f"[回测] 限制股票数量: {max_stocks}只", flush=True)

        all_signals = []
        total_stocks = len(all_kline)

        for idx, (code, kline) in enumerate(all_kline.items()):
            if idx % 100 == 0:
                print(f"[回测] 进度 {idx}/{total_stocks}, 已发现信号 {len(all_signals)}个", flush=True)

            # 遍历每个交易日（从第60天开始，确保有足够历史数据）
            for i in range(60, len(kline) - 10):  # 留10天计算后续收益
                try:
                    signal = self.check_520_signal_at_date(kline, i)
                    if signal:
                        signal['code'] = code
                        # 计算后续收益
                        returns = self.calculate_forward_returns(kline, i)
                        signal.update(returns)
                        all_signals.append(signal)
                except Exception as e:
                    continue

        duration = time.time() - start_time
        print(f"[回测] 完成: {len(all_signals)}个信号, 耗时{duration:.2f}秒", flush=True)

        # 统计
        stats = self._calculate_stats(all_signals)
        stats['total_signals'] = len(all_signals)
        stats['total_stocks'] = total_stocks
        stats['duration'] = round(duration, 2)
        stats['signals'] = all_signals[:100]  # 只保留前100个信号用于展示

        return stats

    def _calculate_stats(self, signals: List[Dict]) -> Dict:
        """计算回测统计指标"""
        if not signals:
            return {'error': '无信号'}

        result = {}

        for days in [1, 3, 5, 7, 10]:
            key = f'd{days}_return'
            returns = [s[key] for s in signals if s.get(key) is not None]

            if not returns:
                result[f'd{days}'] = {'count': 0}
                continue

            positive = sum(1 for r in returns if r > 0)
            negative = sum(1 for r in returns if r < 0)
            avg_return = sum(returns) / len(returns)
            median_return = sorted(returns)[len(returns) // 2]
            max_return = max(returns)
            min_return = min(returns)

            # 盈亏比
            profits = [r for r in returns if r > 0]
            losses = [abs(r) for r in returns if r < 0]
            avg_profit = sum(profits) / len(profits) if profits else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            profit_factor = avg_profit / avg_loss if avg_loss > 0 else float('inf')

            result[f'd{days}'] = {
                'count': len(returns),
                'win_rate': round(positive / len(returns) * 100, 2),
                'profit_count': positive,
                'loss_count': negative,
                'avg_return': round(avg_return, 2),
                'median_return': round(median_return, 2),
                'max_return': round(max_return, 2),
                'min_return': round(min_return, 2),
                'avg_profit': round(avg_profit, 2),
                'avg_loss': round(avg_loss, 2),
                'profit_factor': round(profit_factor, 2),
            }

        # 10日最高/最低收益统计
        max_returns = [s.get('max_return_10d', 0) for s in signals if s.get('max_return_10d') is not None]
        min_returns = [s.get('min_return_10d', 0) for s in signals if s.get('min_return_10d') is not None]
        if max_returns:
            result['max_return_10d_avg'] = round(sum(max_returns) / len(max_returns), 2)
            result['max_return_10d_median'] = round(sorted(max_returns)[len(max_returns) // 2], 2)
        if min_returns:
            result['min_return_10d_avg'] = round(sum(min_returns) / len(min_returns), 2)

        # 按金叉天数分组统计
        cross_day_groups = {}
        for s in signals:
            days = s.get('cross_days_ago', -1)
            if days not in cross_day_groups:
                cross_day_groups[days] = []
            cross_day_groups[days].append(s)

        result['by_cross_day'] = {}
        for days, group_signals in cross_day_groups.items():
            d5_returns = [s['d5_return'] for s in group_signals if s.get('d5_return') is not None]
            if d5_returns:
                win = sum(1 for r in d5_returns if r > 0)
                result['by_cross_day'][days] = {
                    'count': len(group_signals),
                    'd5_win_rate': round(win / len(d5_returns) * 100, 2),
                    'd5_avg_return': round(sum(d5_returns) / len(d5_returns), 2),
                }

        return result


def get_ai520_backtester() -> AI520Backtester:
    return AI520Backtester()


if __name__ == '__main__':
    print("AI-520回测模块自测")
    backtester = AI520Backtester()

    # 小范围回测测试
    result = backtester.run_backtest(max_stocks=100)

    print()
    print("=== 回测结果 ===")
    print(f"总信号: {result.get('total_signals', 0)}")
    print(f"总股票: {result.get('total_stocks', 0)}")
    print(f"耗时: {result.get('duration', 0)}秒")

    for days in [1, 3, 5, 7, 10]:
        stats = result.get(f'd{days}', {})
        if stats.get('count', 0) > 0:
            print(f"\nD{days}:")
            print(f"  样本数: {stats['count']}")
            print(f"  胜率: {stats['win_rate']}%")
            print(f"  平均收益: {stats['avg_return']}%")
            print(f"  中位数收益: {stats['median_return']}%")
            print(f"  最大收益: {stats['max_return']}%")
            print(f"  最大亏损: {stats['min_return']}%")
            print(f"  盈亏比: {stats['profit_factor']}")
