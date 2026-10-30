"""
实时风险监控模块
检测：高位放巨量、MACD顶背离、跌破MA20、主力资金流出、换手异常
提示：风险增加、减仓、退出观察
"""
import numpy as np
from utils.indicators import calc_ma, calc_macd_series, calc_macd


class RiskMonitor:
    """风险监控类"""

    # 风险等级
    RISK_LOW = '低风险'
    RISK_MEDIUM = '风险增加'
    RISK_HIGH = '建议减仓'
    RISK_CRITICAL = '退出观察'

    def __init__(self):
        self.risk_signals = []

    def check(self, daily_data, realtime_data=None):
        """
        检查风险
        返回: 风险信号列表
        """
        self.risk_signals = []

        if not daily_data or len(daily_data) < 20:
            return self.risk_signals

        close_prices = [d['close'] for d in daily_data]
        high_prices = [d['high'] for d in daily_data]
        low_prices = [d['low'] for d in daily_data]
        volumes = [d.get('volume', d.get('vol', 0)) for d in daily_data]

        # 1. 高位放巨量
        self._check_high_volume(close_prices, volumes)

        # 2. MACD顶背离
        self._check_macd_divergence(close_prices, high_prices)

        # 3. 跌破MA20
        self._check_break_ma20(close_prices)

        # 4. 换手异常
        self._check_turnover_anomaly(daily_data)

        # 5. 连续下跌
        self._check_consecutive_down(close_prices, volumes)

        return self.risk_signals

    def _check_high_volume(self, close, volumes):
        """高位放巨量检测"""
        if len(volumes) < 10:
            return

        n = len(close)
        avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        if avg_vol_20 == 0:
            return

        current_vol = volumes[-1]
        vol_ratio = current_vol / avg_vol_20

        # 近期涨幅较大（10日内涨幅超过15%）
        if n >= 10:
            gain = (close[-1] - close[-10]) / close[-10] * 100
        else:
            gain = 0

        # 高位放巨量（量比>3 且 近期涨幅>15%）
        if vol_ratio > 3 and gain > 15:
            self.risk_signals.append({
                'type': 'high_volume',
                'level': self.RISK_HIGH,
                'name': '高位放巨量',
                'description': f'近期涨幅{gain:.1f}%，今日量比{vol_ratio:.1f}倍，可能主力出货',
                'action': '建议减仓，警惕见顶',
                'score': 8,
            })
        elif vol_ratio > 2 and gain > 10:
            self.risk_signals.append({
                'type': 'high_volume_warn',
                'level': self.RISK_MEDIUM,
                'name': '放量滞涨',
                'description': f'近期涨幅{gain:.1f}%，量比{vol_ratio:.1f}倍，注意风险',
                'action': '密切关注，若滞涨则减仓',
                'score': 5,
            })

    def _check_macd_divergence(self, close, high):
        """MACD顶背离检测"""
        if len(close) < 30:
            return

        dif, dea, macd_hist = calc_macd_series(close)

        n = len(close)

        # 找最近两个高点
        # 简化版：股价创新高但MACD红柱缩小
        recent_high_idx = n - 1
        for i in range(n-2, max(0, n-15), -1):
            if high[i] > high[recent_high_idx]:
                recent_high_idx = i
                break

        if recent_high_idx == n - 1:
            return  # 当前就是最高点

        # 比较MACD
        if recent_high_idx < len(macd_hist) and n-1 < len(macd_hist):
            hist_at_high = macd_hist.iloc[recent_high_idx]
            hist_now = macd_hist.iloc[n-1]

            if not np.isnan(hist_at_high) and not np.isnan(hist_now):
                # 股价更高但MACD红柱更小 = 顶背离
                if high[n-1] > high[recent_high_idx] and hist_now < hist_at_high and hist_now > 0:
                    self.risk_signals.append({
                        'type': 'macd_top_divergence',
                        'level': self.RISK_HIGH,
                        'name': 'MACD顶背离',
                        'description': f'股价创新高{high[n-1]:.2f}，但MACD红柱缩小，顶背离信号',
                        'action': '建议减仓，顶背离后易回调',
                        'score': 9,
                    })

    def _check_break_ma20(self, close):
        """跌破MA20检测"""
        if len(close) < 21:
            return

        ma20 = calc_ma(close, 20)
        ma20_yesterday = calc_ma(close[:-1], 20)

        # 今日跌破MA20（昨日在MA20上方，今日在下方）
        if close[-2] >= ma20_yesterday and close[-1] < ma20:
            self.risk_signals.append({
                'type': 'break_ma20',
                'level': self.RISK_HIGH,
                'name': '跌破MA20',
                'description': f'股价{close[-1]:.2f}跌破20日均线{ma20:.2f}，趋势转弱',
                'action': '建议减仓或止损',
                'score': 7,
            })
        elif close[-1] < ma20 and close[-1] < close[-2]:
            self.risk_signals.append({
                'type': 'below_ma20',
                'level': self.RISK_MEDIUM,
                'name': '运行在MA20下方',
                'description': f'股价{close[-1]:.2f}在20日均线{ma20:.2f}下方，趋势偏弱',
                'action': '谨慎操作，不宜追高',
                'score': 4,
            })

    def _check_turnover_anomaly(self, daily_data):
        """换手异常检测"""
        if len(daily_data) < 10:
            return

        turnovers = [d.get('turnover_rate', 0) for d in daily_data]
        current_turnover = turnovers[-1]

        if current_turnover == 0:
            return

        avg_turnover = np.mean([t for t in turnovers[-10:] if t > 0])
        if avg_turnover == 0:
            return

        turnover_ratio = current_turnover / avg_turnover

        # 换手率异常高（超过20%或为近期3倍）
        if current_turnover > 20 or turnover_ratio > 3:
            self.risk_signals.append({
                'type': 'turnover_anomaly',
                'level': self.RISK_MEDIUM,
                'name': '换手异常',
                'description': f'今日换手率{current_turnover:.1f}%，为近期{turnover_ratio:.1f}倍',
                'action': '关注资金动向，高换手后易变盘',
                'score': 5,
            })

    def _check_consecutive_down(self, close, volumes):
        """连续下跌检测"""
        if len(close) < 5:
            return

        # 连续3日下跌
        down_days = 0
        for i in range(len(close)-1, max(0, len(close)-5), -1):
            if close[i] < close[i-1]:
                down_days += 1
            else:
                break

        if down_days >= 3:
            # 放量下跌
            avg_vol = np.mean(volumes[-5:-1])
            vol_increase = volumes[-1] / avg_vol if avg_vol > 0 else 1

            if vol_increase > 1.5:
                self.risk_signals.append({
                    'type': 'consecutive_down_volume',
                    'level': self.RISK_HIGH,
                    'name': '连续放量下跌',
                    'description': f'连续{down_days}日下跌，今日放量{vol_increase:.1f}倍',
                    'action': '建议止损出局',
                    'score': 8,
                })
            else:
                self.risk_signals.append({
                    'type': 'consecutive_down',
                    'level': self.RISK_MEDIUM,
                    'name': '连续下跌',
                    'description': f'连续{down_days}日下跌，注意支撑',
                    'action': '关注支撑位，破位则减仓',
                    'score': 4,
                })

    def get_risk_level(self, daily_data):
        """获取综合风险等级"""
        signals = self.check(daily_data)

        if not signals:
            return self.RISK_LOW, 0

        max_score = max(s['score'] for s in signals)

        if max_score >= 8:
            return self.RISK_CRITICAL, max_score
        elif max_score >= 6:
            return self.RISK_HIGH, max_score
        elif max_score >= 4:
            return self.RISK_MEDIUM, max_score
        else:
            return self.RISK_LOW, max_score

    def get_risk_summary(self, daily_data):
        """获取风险摘要"""
        signals = self.check(daily_data)
        level, score = self.get_risk_level(daily_data)

        return {
            'level': level,
            'score': score,
            'signals': signals,
            'count': len(signals),
        }
