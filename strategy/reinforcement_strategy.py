# -*- coding: utf-8 -*-
"""
援军战法 V1.0（STR-V3-001）
核心思想：寻找近期出现过强势涨停/强势启动，经过回调，再次出现启动信号的股票。

评分100分：
- 涨停记忆 20分
- 回撤结构 15分
- 缩量回调 15分
- MA20趋势 10分
- 重新站MA5 10分
- 启动放量 15分
- 突破前高 10分
- 板块联动 5分

等级：80-100★★★★★强启动、70-79★★★★、60-69★★★观察、50-59★★、<50不触发
"""
import os
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class ReinforcementStrategy:
    """援军战法 V1.0"""

    STRATEGY_NAME = "援军战法"
    STRATEGY_ID = "STR-V3-001"
    SIGNAL_SOURCE_TAG = "援军战法"

    def __init__(self):
        self._scan_logs = []

    def _log(self, msg: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] [援军战法] {msg}"
        self._scan_logs.append(log_msg)
        print(log_msg, flush=True)

    def calc_ma(self, closes: List[float], period: int) -> List[float]:
        """计算移动平均线"""
        result = []
        for i in range(len(closes)):
            if i < period - 1:
                result.append(0.0)
            else:
                result.append(sum(closes[i - period + 1:i + 1]) / period)
        return result

    def calc_pct_changes(self, kline: List[Dict]) -> List[float]:
        """计算每日涨跌幅"""
        pcts = []
        for i in range(len(kline)):
            if i == 0:
                pcts.append(0.0)
            else:
                prev_close = float(kline[i - 1].get('close', 0))
                curr_close = float(kline[i].get('close', 0))
                if prev_close > 0:
                    pcts.append((curr_close - prev_close) / prev_close)
                else:
                    pcts.append(0.0)
        return pcts

    def find_limit_up_days(self, kline: List[Dict], pcts: List[float], lookback: int = 20) -> List[int]:
        """查找近lookback个交易日内的涨停日（涨幅>=9.8%）"""
        limit_up_days = []
        start = max(0, len(kline) - lookback)
        for i in range(start, len(kline)):
            if pcts[i] >= 0.098:
                # 排除一字板（开盘=最高=最低=收盘）
                o = float(kline[i].get('open', 0))
                h = float(kline[i].get('high', 0))
                l = float(kline[i].get('low', 0))
                c = float(kline[i].get('close', 0))
                if not (o == h == l == c):
                    limit_up_days.append(i)
        return limit_up_days

    def run_single_stock(self, kline: List[Dict], stock_code: str, stock_name: str,
                          sector_data: Optional[Dict] = None, verbose: bool = False) -> Optional[Dict]:
        """
        单只股票援军战法计算。

        Args:
            kline: K线数据列表
            stock_code: 股票代码
            stock_name: 股票名称
            sector_data: 板块数据（可选），包含sector_name/sector_change/limit_up_count等
            verbose: 是否输出详细日志

        Returns:
            信号字典或None
        """
        if not kline or len(kline) < 25:
            if verbose:
                self._log(f"{stock_code} {stock_name} 跳过：K线不足25根(实际{len(kline) if kline else 0})")
            return None

        # 基础数据
        closes = [float(k.get('close', 0)) for k in kline]
        volumes = [float(k.get('volume', 0)) for k in kline]
        highs = [float(k.get('high', 0)) for k in kline]
        opens = [float(k.get('open', 0)) for k in kline]
        pcts = self.calc_pct_changes(kline)

        # 均线
        ma5 = self.calc_ma(closes, 5)
        ma10 = self.calc_ma(closes, 10)
        ma20 = self.calc_ma(closes, 20)

        # 当前日（T0）
        t0_close = closes[-1]
        t0_open = opens[-1]
        t0_high = highs[-1]
        t0_volume = volumes[-1]
        t0_pct = pcts[-1]
        t0_ma5 = ma5[-1]
        t0_ma10 = ma10[-1]
        t0_ma20 = ma20[-1]

        # 前一日（T-1）
        t1_close = closes[-2]
        t1_high = highs[-2]
        t1_ma5 = ma5[-2]

        # ===== 评分项1：涨停记忆（20分）=====
        limit_up_days = self.find_limit_up_days(kline, pcts, lookback=20)
        limit_up_count = len(limit_up_days)
        limit_up_score = 0
        last_limit_up_idx = limit_up_days[-1] if limit_up_days else -1
        last_limit_up_date = kline[last_limit_up_idx].get('date', '') if last_limit_up_idx >= 0 else ''

        if limit_up_count >= 3:
            limit_up_score = 20
        elif limit_up_count == 2:
            limit_up_score = 15
        elif limit_up_count == 1:
            limit_up_score = 10
        else:
            limit_up_score = 0

        if verbose:
            self._log(f"{stock_code} 涨停记忆：近20日{limit_up_count}次涨停，得分{limit_up_score}/20")

        # 无涨停记忆不触发
        if limit_up_count == 0:
            if verbose:
                self._log(f"{stock_code} {stock_name} 无涨停记忆，不触发")
            return None

        # ===== 评分项2：回撤结构（15分）=====
        # 从最近涨停后高点到当前的回撤
        pullback_score = 0
        pullback_pct = 0.0
        if last_limit_up_idx >= 0:
            # 涨停后最高价
            post_limit_highs = highs[last_limit_up_idx:]
            post_limit_max_high = max(post_limit_highs) if post_limit_highs else t0_high
            # 涨停后最低价
            post_limit_lows = [float(k.get('low', 0)) for k in kline[last_limit_up_idx:]]
            post_limit_min_low = min(post_limit_lows) if post_limit_lows else t0_close
            # 当前回撤幅度
            if post_limit_max_high > 0:
                pullback_pct = (post_limit_max_high - t0_close) / post_limit_max_high * 100

            # 回撤3%-15%为最佳
            if 3 <= pullback_pct <= 15:
                pullback_score = 15
            elif 1 <= pullback_pct < 3 or 15 < pullback_pct <= 20:
                pullback_score = 10
            elif 0 < pullback_pct < 1 or 20 < pullback_pct <= 30:
                pullback_score = 5
            else:
                pullback_score = 0

        if verbose:
            self._log(f"{stock_code} 回撤结构：回撤{pullback_pct:.1f}%，得分{pullback_score}/15")

        # ===== 评分项3：缩量回调（15分）=====
        # 涨停后回调日成交量 vs 涨停日成交量
        shrink_score = 0
        if last_limit_up_idx >= 0 and len(kline) - last_limit_up_idx >= 3:
            limit_up_volume = volumes[last_limit_up_idx]
            # 涨停后平均成交量（不含今日）
            post_limit_volumes = volumes[last_limit_up_idx + 1:-1]
            if post_limit_volumes and limit_up_volume > 0:
                avg_post_volume = sum(post_limit_volumes) / len(post_limit_volumes)
                vol_ratio = avg_post_volume / limit_up_volume
                # 回调缩量（平均成交量为涨停日的50%-80%最佳）
                if 0.3 <= vol_ratio <= 0.8:
                    shrink_score = 15
                elif 0.2 <= vol_ratio < 0.3 or 0.8 < vol_ratio <= 1.0:
                    shrink_score = 10
                elif vol_ratio < 0.2 or 1.0 < vol_ratio <= 1.2:
                    shrink_score = 5
                else:
                    shrink_score = 0

        if verbose:
            self._log(f"{stock_code} 缩量回调：回调日均量/涨停量={vol_ratio if last_limit_up_idx >= 0 else 0:.2f}，得分{shrink_score}/15")

        # ===== 评分项4：MA20趋势（10分）=====
        ma20_trend_score = 0
        if t0_ma20 > 0 and len(ma20) >= 6:
            ma20_5ago = ma20[-6]
            if ma20_5ago > 0:
                ma20_slope = (t0_ma20 - ma20_5ago) / ma20_5ago * 100
                # MA20向上（5日涨幅>0.5%）
                if ma20_slope > 1.0:
                    ma20_trend_score = 10
                elif ma20_slope > 0.3:
                    ma20_trend_score = 7
                elif ma20_slope > -0.3:
                    ma20_trend_score = 4
                else:
                    ma20_trend_score = 0

        if verbose:
            self._log(f"{stock_code} MA20趋势：MA20={t0_ma20:.2f}，5日斜率={ma20_slope if t0_ma20 > 0 else 0:.2f}%，得分{ma20_trend_score}/10")

        # ===== 评分项5：重新站MA5（10分）=====
        stand_ma5_score = 0
        just_stand_ma5 = False
        if t0_ma5 > 0:
            if t0_close > t0_ma5 and t1_close <= t1_ma5:
                # 今日刚站上MA5
                stand_ma5_score = 10
                just_stand_ma5 = True
            elif t0_close > t0_ma5:
                # 已站上MA5
                stand_ma5_score = 7
            elif t0_close > t0_ma5 * 0.98:
                # 接近MA5
                stand_ma5_score = 3
            else:
                stand_ma5_score = 0

        if verbose:
            self._log(f"{stock_code} 重新站MA5：收{t0_close:.2f} MA5={t0_ma5:.2f} 刚站={just_stand_ma5}，得分{stand_ma5_score}/10")

        # ===== 评分项6：启动放量（15分）=====
        volume_score = 0
        vol_multiple = 0.0
        if len(volumes) >= 6:
            vol_5ma = sum(volumes[-6:-1]) / 5  # 前5日均量（不含今日）
            if vol_5ma > 0:
                vol_multiple = t0_volume / vol_5ma
                if vol_multiple >= 2.0:
                    volume_score = 15
                elif vol_multiple >= 1.5:
                    volume_score = 12
                elif vol_multiple >= 1.2:
                    volume_score = 8
                elif vol_multiple >= 1.0:
                    volume_score = 4
                else:
                    volume_score = 0

        if verbose:
            self._log(f"{stock_code} 启动放量：今日量{t0_volume:.0f} 5日均量{vol_5ma if len(volumes)>=6 else 0:.0f} 倍数{vol_multiple:.2f}，得分{volume_score}/15")

        # ===== 评分项7：突破前高（10分）=====
        breakout_score = 0
        breakout_pct = 0.0
        if t1_high > 0:
            breakout_pct = (t0_close - t1_high) / t1_high * 100
            if t0_close > t1_high and t0_pct > 0:
                # 收盘突破前一日最高价
                if breakout_pct > 2:
                    breakout_score = 10
                elif breakout_pct > 0.5:
                    breakout_score = 7
                else:
                    breakout_score = 5
            elif t0_high > t1_high:
                # 盘中突破但收盘未过
                breakout_score = 3
            else:
                breakout_score = 0

        if verbose:
            self._log(f"{stock_code} 突破前高：收{t0_close:.2f} 前高{t1_high:.2f} 突破{breakout_pct:.2f}%，得分{breakout_score}/10")

        # ===== 评分项8：板块联动（5分）=====
        sector_score = 0
        sector_name = ''
        sector_change = 0.0
        sector_limit_up = 0
        if sector_data:
            sector_name = sector_data.get('sector_name', sector_data.get('name', ''))
            sector_change = sector_data.get('sector_change', sector_data.get('change_pct', 0))
            sector_limit_up = sector_data.get('limit_up_count', sector_data.get('limit_up', 0))
            if sector_change > 2 and sector_limit_up >= 2:
                sector_score = 5
            elif sector_change > 1 and sector_limit_up >= 1:
                sector_score = 3
            elif sector_change > 0:
                sector_score = 1
            else:
                sector_score = 0

        if verbose:
            self._log(f"{stock_code} 板块联动：{sector_name} 涨幅{sector_change:.2f}% 涨停{sector_limit_up}只，得分{sector_score}/5")

        # ===== 总分 =====
        total_score = (limit_up_score + pullback_score + shrink_score + ma20_trend_score +
                       stand_ma5_score + volume_score + breakout_score + sector_score)

        if verbose:
            self._log(f"{stock_code} {stock_name} 总分：{total_score}/100 "
                      f"(涨停{limit_up_score}+回撤{pullback_score}+缩量{shrink_score}"
                      f"+MA20{ma20_trend_score}+站MA5{stand_ma5_score}+放量{volume_score}"
                      f"+突破{breakout_score}+板块{sector_score})")

        # 等级
        if total_score >= 80:
            grade = "★★★★★强启动"
            grade_level = "S"
        elif total_score >= 70:
            grade = "★★★★"
            grade_level = "A"
        elif total_score >= 60:
            grade = "★★★观察"
            grade_level = "B"
        elif total_score >= 50:
            grade = "★★"
            grade_level = "C"
        else:
            return None  # 低于50分不触发

        # 信号标签
        tags = []
        if limit_up_count >= 1:
            tags.append("涨停记忆")
        if 3 <= pullback_pct <= 15:
            tags.append("充分回调")
        if shrink_score >= 10:
            tags.append("缩量回调")
        if just_stand_ma5:
            tags.append("今日刚站MA5")
        elif stand_ma5_score >= 7:
            tags.append("站上MA5")
        if vol_multiple >= 1.5:
            tags.append("放量启动")
        if breakout_score >= 7:
            tags.append("突破前高")
        if ma20_trend_score >= 7:
            tags.append("MA20向上")
        if sector_score >= 3:
            tags.append("板块联动")

        # 风险标签
        risk_tags = []
        if pullback_pct > 20:
            risk_tags.append("回撤过深")
        if t0_pct > 0.07:
            risk_tags.append("追高风险")
        if vol_multiple > 3:
            risk_tags.append("放量过大")

        result = {
            'strategy_id': self.STRATEGY_ID,
            'strategy_name': self.STRATEGY_NAME,
            'signal_source': self.SIGNAL_SOURCE_TAG,
            'stock_code': stock_code,
            'stock_name': stock_name,
            'total_score': total_score,
            'grade': grade,
            'grade_level': grade_level,
            'today_pct': round(t0_pct * 100, 2),
            'today_close': round(t0_close, 2),
            'today_open': round(t0_open, 2),
            'today_high': round(t0_high, 2),
            'today_volume': round(t0_volume, 0),
            'ma5': round(t0_ma5, 2),
            'ma10': round(t0_ma10, 2),
            'ma20': round(t0_ma20, 2),
            'vol_multiple': round(vol_multiple, 2),
            'pullback_pct': round(pullback_pct, 2),
            'breakout_pct': round(breakout_pct, 2),
            'limit_up_count_20d': limit_up_count,
            'last_limit_up_date': last_limit_up_date,
            'just_stand_ma5': just_stand_ma5,
            'sector_name': sector_name,
            'sector_change': round(sector_change, 2),
            'sector_limit_up': sector_limit_up,
            'tags': tags,
            'risk_tags': risk_tags,
            'score_detail': {
                'limit_up': limit_up_score,
                'pullback': pullback_score,
                'shrink': shrink_score,
                'ma20_trend': ma20_trend_score,
                'stand_ma5': stand_ma5_score,
                'volume': volume_score,
                'breakout': breakout_score,
                'sector': sector_score,
            },
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'kline_date': kline[-1].get('date', ''),
        }

        self._log(f"✅ {stock_code} {stock_name} 援军战法信号！{grade} {total_score}分 标签:{','.join(tags[:5])}")
        return result

    def scan_stock_list(self, stocks: List[Dict], kline_provider, days: int = 60,
                        sector_provider=None, verbose: bool = False) -> List[Dict]:
        """批量扫描"""
        signals = []
        total = len(stocks)
        self._log(f"开始批量扫描，共{total}只股票，K线{days}天")

        for i, stock in enumerate(stocks):
            code = stock.get('code', '')
            name = stock.get('name', '')
            if not code:
                continue
            try:
                kline = kline_provider(code, days)
                if kline and len(kline) >= 25:
                    sector_data = None
                    if sector_provider:
                        try:
                            sector_data = sector_provider(code)
                        except Exception:
                            pass
                    result = self.run_single_stock(kline, code, name, sector_data=sector_data, verbose=verbose)
                    if result:
                        signals.append(result)
            except Exception as e:
                self._log(f"{code} {name} 扫描异常: {e}")

            if (i + 1) % 50 == 0:
                self._log(f"扫描进度 {i+1}/{total}，已发现信号{len(signals)}只")

        signals.sort(key=lambda x: x.get('total_score', 0), reverse=True)
        self._log(f"批量扫描完成：{total}只股票，生成信号{len(signals)}只")
        return signals

    def get_scan_logs(self) -> List[str]:
        return self._scan_logs.copy()

    def clear_logs(self):
        self._scan_logs = []


def get_reinforcement_strategy() -> ReinforcementStrategy:
    return ReinforcementStrategy()


if __name__ == '__main__':
    print("=" * 60)
    print("援军战法 V1.0 自测")
    print("=" * 60)

    strategy = ReinforcementStrategy()

    # 构造测试K线（满足援军战法）
    test_kline = []
    base_price = 10.0
    dates = ['2026-07-15', '2026-07-16', '2026-07-17', '2026-07-18', '2026-07-21',
             '2026-07-22', '2026-07-23', '2026-07-24', '2026-07-25', '2026-07-28',
             '2026-07-29', '2026-07-30', '2026-07-31', '2026-08-01', '2026-08-04',
             '2026-08-05', '2026-08-06', '2026-08-07', '2026-08-08', '2026-08-11',
             '2026-08-12', '2026-08-13', '2026-08-14', '2026-08-15', '2026-08-18']

    # 前20天横盘，第21天涨停，然后回调3天，今天放量突破
    for i in range(25):
        if i < 20:
            # 横盘
            price = base_price + (i % 3) * 0.1
            test_kline.append({
                'date': dates[i], 'open': price, 'high': price + 0.15,
                'low': price - 0.1, 'close': price + 0.05, 'volume': 80000
            })
        elif i == 20:
            # 涨停（涨幅11.4%>9.8%）
            price = base_price + 1.2
            test_kline.append({
                'date': dates[i], 'open': base_price + 0.1, 'high': price,
                'low': base_price + 0.05, 'close': price, 'volume': 200000
            })
        elif i == 21:
            # 回调第一天
            price = base_price + 0.8
            test_kline.append({
                'date': dates[i], 'open': base_price + 0.95, 'high': base_price + 0.98,
                'low': price - 0.05, 'close': price, 'volume': 120000
            })
        elif i == 22:
            # 回调第二天（缩量）
            price = base_price + 0.6
            test_kline.append({
                'date': dates[i], 'open': base_price + 0.75, 'high': base_price + 0.78,
                'low': price - 0.05, 'close': price, 'volume': 90000
            })
        elif i == 23:
            # 回调第三天（缩量，接近MA5）
            price = base_price + 0.55
            test_kline.append({
                'date': dates[i], 'open': base_price + 0.58, 'high': base_price + 0.62,
                'low': price - 0.03, 'close': price, 'volume': 70000
            })
        elif i == 24:
            # 今天：放量阳线突破前高
            price = base_price + 0.9
            test_kline.append({
                'date': dates[i], 'open': base_price + 0.6, 'high': price + 0.05,
                'low': base_price + 0.58, 'close': price, 'volume': 180000
            })

    print(f"\n测试K线：{len(test_kline)}根")
    print(f"第21天(涨停)：收{test_kline[20]['close']} 量{test_kline[20]['volume']}")
    print(f"今天(第25天)：收{test_kline[24]['close']} 量{test_kline[24]['volume']} 高{test_kline[24]['high']}")
    print(f"前一天高：{test_kline[23]['high']}")

    print("\n执行单股计算（verbose=True）：")
    result = strategy.run_single_stock(test_kline, '000001', '平安银行', verbose=True)

    print("\n计算结果：")
    if result:
        print(f"  股票：{result['stock_code']} {result['stock_name']}")
        print(f"  总分：{result['total_score']}/100")
        print(f"  等级：{result['grade']}")
        print(f"  今日涨幅：{result['today_pct']}%")
        print(f"  放量倍数：{result['vol_multiple']}")
        print(f"  回撤幅度：{result['pullback_pct']}%")
        print(f"  突破幅度：{result['breakout_pct']}%")
        print(f"  20日涨停次数：{result['limit_up_count_20d']}")
        print(f"  标签：{result['tags']}")
        print(f"  风险：{result['risk_tags']}")
        print(f"  评分明细：{result['score_detail']}")
    else:
        print("  无信号（总分<50）")

    print("\n援军战法自测完成。")
