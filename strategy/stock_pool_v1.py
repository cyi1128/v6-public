# -*- coding: utf-8 -*-
"""
智能选股池
策略1：趋势突破池
策略2：强势突破池（20日线突破）
策略3：稳健低吸池
优先使用同花顺问财AI选股，失败则用规则匹配
"""
import pandas as pd
import numpy as np
from utils.indicators import calc_ma_series, calc_avg_volume, calc_limit_up_count, calc_rsi, calc_amplitude, calc_week_volume_ratio
from strategy.wencai_ai import get_wencai_ai


class StockPoolFilter:
    """选股池过滤器"""

    # 排除行业
    EXCLUDE_INDUSTRIES = ['地产', '农业', '酒', '保险']

    def _calc_signals_and_score(self, stock, kline):
        """
        计算股票的信号标签和AI评分
        Args:
            stock: 股票基本信息
            kline: K线数据
        Returns:
            (signal_names, ai_score, trend)
        """
        try:
            from strategy.kline_scanner import get_scanner
            from strategy.indicator_scanner import get_indicator_scanner
            from strategy.main_trend_scanner import get_main_trend_scanner
            from strategy.ai_trade_analyzer import get_ai_analyzer

            signal_names = []

            # K线形态信号
            kline_signals = get_scanner().scan(kline)
            for sig in kline_signals:
                signal_names.append(sig.get('name', ''))

            # 指标信号
            indicator_signals = get_indicator_scanner().scan_all(kline)
            for sig in indicator_signals:
                signal_names.append(sig.get('name', ''))

            # 主升启动信号
            main_trend = get_main_trend_scanner().scan(kline)
            if main_trend:
                signal_names.append(main_trend.get('name', '主升启动买点'))

            # AI评分
            ai_result = get_ai_analyzer().analyze(stock, kline)
            ai_score = ai_result.get('score', 0)
            trend = ai_result.get('trend', '中性')

            return signal_names, ai_score, trend
        except Exception as e:
            print(f"计算信号和评分失败: {e}")
            return [], 0, '中性'

    def _filter_single_trend(self, stock, kline):
        """
        单只股票趋势突破池筛选（已通过基础过滤后调用）
        Args:
            stock: 股票基本信息
            kline: K线数据（dict格式）
        Returns:
            dict or None
        """
        code = stock.get('code', '')
        name = stock.get('name', '')
        price = stock.get('price', 0)
        market_cap = stock.get('market_cap', 0)
        industry = stock.get('industry', '')

        if not kline or len(kline.get('close', [])) < 30:
            return None

        closes = kline['close']
        highs = kline['high']
        pct_changes = kline.get('pct_chg', [])

        # 近8个月最高价（约168个交易日）
        high_8m = max(highs[-168:]) if len(highs) >= 168 else max(highs)

        # 当前价格 > 最高价85% 且 < 最高价130%
        if not (price > high_8m * 0.85 and price < high_8m * 1.30):
            return None

        # 前一天没有涨停
        if len(pct_changes) >= 2 and pct_changes[-2] >= 9.8:
            return None

        # 一年涨停次数≥3
        limit_count = calc_limit_up_count(closes, pct_changes, days=252)
        if limit_count < 3:
            return None

        # 计算信号和AI评分
        signal_names, ai_score, trend = self._calc_signals_and_score(stock, kline)

        return {
            'code': code,
            'name': name,
            'price': price,
            'pct_chg': stock.get('pct_chg', stock.get('change', 0)),
            'volume': stock.get('volume', 0),
            'turnover': stock.get('turnover', 0),
            'market_cap': market_cap,
            'industry': industry,
            'high_8m': high_8m,
            'limit_count': limit_count,
            'ai_score': ai_score,
            'trend': trend,
            'signal_names': signal_names,
            'pool': '趋势突破池'
        }

    def _filter_single_by_strategy(self, stock, kline, strategy_conditions, strategy_name='自定义', skip_ai_score=True):
        """
        通用策略筛选（根据策略条件动态筛选）

        Args:
            stock: 股票基本信息
            kline: K线数据
            strategy_conditions: 策略条件字典
            strategy_name: 策略名称
            skip_ai_score: 是否跳过AI评分计算（自定义策略默认跳过，提升速度）

        Returns:
            dict or None
        """
        code = stock.get('code', '')
        name = stock.get('name', '')
        price = stock.get('price', 0)
        market_cap = stock.get('market_cap', 0)
        industry = stock.get('industry', '')
        turnover = stock.get('turnover', 0)

        if not kline or len(kline.get('close', [])) < 30:
            return None

        closes = kline['close']
        highs = kline['high']
        lows = kline.get('low', [])
        volumes = kline.get('volume', [])
        pct_changes = kline.get('pct_chg', [])

        cond = strategy_conditions or {}

        # 1. 高点比例条件
        high_ratio_range = cond.get('high_ratio_range', [0, 99])
        high_period_days = cond.get('high_period_days', 160)

        if high_ratio_range[0] > 0 or high_ratio_range[1] < 99:
            period = min(high_period_days, len(highs))
            high_n = max(highs[-period:]) if period > 0 else max(highs)
            ratio = price / high_n if high_n > 0 else 0
            if ratio < high_ratio_range[0] or ratio > high_ratio_range[1]:
                return None

        # 2. 前一天未涨停
        if cond.get('no_limit_up_yesterday', False):
            if len(pct_changes) >= 2 and pct_changes[-2] >= 9.8:
                return None

        # 3. 涨停次数（优先从缓存读取）
        limit_count_min = cond.get('limit_up_count_min', 0)
        if limit_count_min > 0:
            # 尝试从缓存读取
            try:
                from strategy.limit_up_cache import get_limit_up_cache
                cache = get_limit_up_cache()
                if cache.has_cache(code):
                    limit_count = cache.get_limit_up_count(code)
                else:
                    # 缓存未命中，计算并写入缓存
                    limit_count = calc_limit_up_count(closes, pct_changes, days=252)
                    cache.refresh_single(code, kline)
            except Exception:
                limit_count = calc_limit_up_count(closes, pct_changes, days=252)

            if limit_count < limit_count_min:
                return None
        else:
            limit_count = 0

        # 4. 换手率范围
        turnover_range = cond.get('turnover_range', [0, 100])
        if turnover_range[0] > 0 or turnover_range[1] < 100:
            if turnover < turnover_range[0] or turnover > turnover_range[1]:
                return None

        # 5. 量比
        volume_ratio_min = cond.get('volume_ratio_min', 0)
        if volume_ratio_min > 0 and len(volumes) >= 6:
            avg_vol_5 = sum(volumes[-6:-1]) / 5
            vol_ratio = volumes[-1] / avg_vol_5 if avg_vol_5 > 0 else 0
            if vol_ratio < volume_ratio_min:
                return None

        # 6. 振幅
        amplitude_max = cond.get('amplitude_max', 100)
        if amplitude_max < 100 and len(highs) >= 2 and len(lows) >= 2:
            yesterday_close = closes[-2] if len(closes) >= 2 else closes[-1]
            if yesterday_close > 0:
                amplitude = (highs[-1] - lows[-1]) / yesterday_close * 100
                if amplitude > amplitude_max:
                    return None

        # 计算信号和AI评分（自定义策略默认跳过，提升速度）
        if skip_ai_score:
            signal_names, ai_score, trend = [], 0, ''
        else:
            signal_names, ai_score, trend = self._calc_signals_and_score(stock, kline)

        return {
            'code': code,
            'name': name,
            'price': price,
            'pct_chg': stock.get('pct_chg', stock.get('change', 0)),
            'volume': stock.get('volume', 0),
            'turnover': turnover,
            'market_cap': market_cap,
            'industry': industry,
            'limit_count': limit_count,
            'ai_score': ai_score,
            'trend': trend,
            'signal_names': signal_names,
            'pool': strategy_name
        }

    def filter_trend_breakout(self, stock_list, kline_provider):
        """
        策略1：趋势突破池

        条件：
        - 当前价格 > 近8个月最高价85%
        - 当前价格 < 近8个月最高价130%
        - 前一天没有涨停
        - 一年涨停次数≥3
        - 主板（排除创业板300/301、科创板688）
        - 非ST
        - 剔除行业：地产、农业、酒、保险
        - 市值：>30亿 且 <=230亿
        """
        results = []

        for stock in stock_list:
            code = stock.get('code', '')
            name = stock.get('name', '')

            # 主板过滤
            if code.startswith(('300', '301', '688')):
                continue

            # ST过滤
            if 'ST' in name or 'st' in name:
                continue

            # 价格
            price = stock.get('price', 0)
            if price <= 0:
                continue

            # 市值过滤（>30亿 且 <=230亿）
            market_cap = stock.get('market_cap', 0)
            if market_cap <= 30 or market_cap > 230:
                continue

            # 行业过滤
            industry = stock.get('industry', '')
            if any(ind in industry for ind in self.EXCLUDE_INDUSTRIES):
                continue

            # 获取K线数据
            kline = kline_provider(code, count=180)
            if not kline:
                continue

            r = self._filter_single_trend(stock, kline)
            if r:
                results.append(r)

        return results

    def _filter_single_strong(self, stock, kline):
        """
        单只股票强势突破池筛选（已通过基础过滤后调用）
        Args:
            stock: 股票基本信息
            kline: K线数据（dict格式）
        Returns:
            dict or None
        """
        code = stock.get('code', '')
        name = stock.get('name', '')

        if not kline or len(kline.get('close', [])) < 30:
            return None

        closes = kline['close']
        highs = kline['high']
        volumes = kline['volume']
        pct_changes = kline.get('pct_chg', [])

        ma20 = calc_ma_series(closes, 20)

        # 15个交易日内出现连续4天站稳20日均线上方
        found_breakout = False
        breakout_idx = -1
        for i in range(-15, -3):
            if abs(i) + 3 >= len(closes):
                break
            consecutive = 0
            for j in range(i, i + 4):
                if abs(j) >= len(closes):
                    break
                m = ma20.iloc[j] if not pd.isna(ma20.iloc[j]) else closes[j]
                if closes[j] > m:
                    consecutive += 1
                else:
                    break
            if consecutive >= 4:
                found_breakout = True
                breakout_idx = i + 3
                break

        if not found_breakout:
            return None

        # 突破期间或后5个交易日：成交量>120日均量，换手率>7%
        vol_120 = calc_avg_volume(volumes, 120) if len(volumes) >= 120 else np.mean(volumes)
        turnover = stock.get('turnover', 0)

        vol_condition = False
        for i in range(breakout_idx - 3, breakout_idx + 5):
            if abs(i) >= len(volumes):
                continue
            if vol_120 > 0 and volumes[i] > vol_120:
                vol_condition = True
                break

        if not (vol_condition and turnover > 7):
            return None

        # 7日内出现涨停或大涨
        strong_move = False
        for i in range(-7, 0):
            if abs(i) >= len(pct_changes):
                break
            pct = pct_changes[i]
            if pct >= 9.8:
                strong_move = True
                break
            if pct > 7:
                strong_move = True
                break
            if abs(i) < len(highs) and abs(i) < len(closes):
                prev_close = closes[i - 1] if abs(i - 1) < len(closes) else closes[i]
                if prev_close > 0:
                    high_pct = (highs[i] - prev_close) / prev_close * 100
                    if high_pct >= 7 and pct >= 5:
                        strong_move = True
                        break

        if not strong_move:
            return None

        # 计算信号和AI评分
        signal_names, ai_score, trend = self._calc_signals_and_score(stock, kline)

        return {
            'code': code,
            'name': name,
            'price': stock.get('price', 0),
            'pct_chg': stock.get('pct_chg', 0),
            'volume': stock.get('volume', 0),
            'turnover': turnover,
            'market_cap': stock.get('market_cap', 0),
            'industry': stock.get('industry', ''),
            'ai_score': ai_score,
            'trend': trend,
            'signal_names': signal_names,
            'pool': '强势突破池'
        }

    def filter_strong_breakout(self, stock_list, kline_provider):
        """
        策略2：强势突破池（20日线突破）

        条件：
        - 15个交易日内出现收盘价连续4天站稳20日均线上方
        - 突破期间或后5个交易日：成交量>120日均量，换手率>7%
        - 7日内出现涨停或收盘涨幅>7%或盘中涨幅≥7%且收盘≥5%
        - 主板、去ST、去科创板
        """
        results = []

        for stock in stock_list:
            code = stock.get('code', '')
            name = stock.get('name', '')

            # 主板过滤（排除创业板、科创板）
            if code.startswith(('300', '301', '688')):
                continue

            # ST过滤
            if 'ST' in name or 'st' in name:
                continue

            # 获取K线数据
            kline = kline_provider(code, count=150)
            if not kline:
                continue

            r = self._filter_single_strong(stock, kline)
            if r:
                results.append(r)

        return results

    def _filter_single_steady(self, stock, kline):
        """
        单只股票稳健低吸池筛选（策略3）
        条件：
        - 只看主板
        - 近2日涨跌幅<7%且当日涨幅<3%
        - 振幅<5%
        - 换手率>1%且<7%
        - RSI 30-70
        - 按周成交量比从高到低排序
        """
        code = stock.get('code', '')
        name = stock.get('name', '')

        if not kline or len(kline.get('close', [])) < 20:
            return None

        closes = kline['close']
        highs = kline['high']
        lows = kline['low']
        volumes = kline['volume']
        pct_changes = kline.get('pct_chg', [])

        # 近2日累计涨跌幅<7%
        if len(pct_changes) >= 2:
            pct_2d = pct_changes[-1] + pct_changes[-2]
            if abs(pct_2d) >= 7:
                return None

        # 当日涨幅<3%
        if len(pct_changes) >= 1 and pct_changes[-1] >= 3:
            return None

        # 振幅<5%
        if len(highs) >= 1 and len(lows) >= 1 and len(closes) >= 2:
            amplitude = calc_amplitude(highs[-1], lows[-1], closes[-2])
            if amplitude >= 5:
                return None

        # 换手率>1%且<7%
        turnover = stock.get('turnover', 0)
        if turnover <= 1 or turnover >= 7:
            return None

        # RSI 30-70
        rsi = calc_rsi(closes, period=14)
        if rsi < 30 or rsi > 70:
            return None

        # 周成交量比（近5日/前5日）
        vol_ratio = calc_week_volume_ratio(volumes)

        # 计算信号和AI评分
        signal_names, ai_score, trend = self._calc_signals_and_score(stock, kline)

        return {
            'code': code,
            'name': name,
            'price': stock.get('price', 0),
            'pct_chg': stock.get('pct_chg', 0),
            'volume': stock.get('volume', 0),
            'turnover': turnover,
            'market_cap': stock.get('market_cap', 0),
            'industry': stock.get('industry', ''),
            'rsi': round(rsi, 2),
            'amplitude': amplitude if 'amplitude' in dir() else 0,
            'vol_ratio': vol_ratio,
            'ai_score': ai_score,
            'trend': trend,
            'signal_names': signal_names,
            'pool': '稳健低吸池'
        }

    def filter_steady_low(self, stock_list, kline_provider):
        """
        策略3：稳健低吸池
        按周成交量比从高到低排序
        """
        results = []

        for stock in stock_list:
            code = stock.get('code', '')
            name = stock.get('name', '')

            # 主板过滤
            if code.startswith(('300', '301', '688')):
                continue

            # ST过滤
            if 'ST' in name or 'st' in name:
                continue

            # 获取K线数据
            kline = kline_provider(code, count=60)
            if not kline:
                continue

            r = self._filter_single_steady(stock, kline)
            if r:
                results.append(r)

        # 按周成交量比从高到低排序
        results.sort(key=lambda x: x.get('vol_ratio', 0), reverse=True)
        return results

    # ==================== 问财AI选股 ====================

    def _convert_wencai_stocks(self, wencai_stocks):
        """
        转换问财返回的股票数据为标准格式

        Args:
            wencai_stocks: 问财返回的股票列表

        Returns:
            list: 标准格式的股票列表
        """
        results = []
        for stock in wencai_stocks:
            try:
                # 尝试提取代码和名称
                code = ''
                name = ''
                price = 0
                pct_chg = 0
                turnover = 0
                market_cap = 0

                # 遍历所有字段，尝试匹配
                for key, value in stock.items():
                    key_str = str(key).lower()
                    if value is None or str(value) == 'nan':
                        continue

                    # 股票代码
                    if '代码' in key_str or 'code' in key_str:
                        if not code:
                            code = str(value).zfill(6) if str(value).isdigit() else str(value)

                    # 股票名称
                    if '名称' in key_str or 'name' in key_str:
                        if not name:
                            name = str(value)

                    # 现价
                    if '现价' in key_str or '价格' in key_str or 'price' in key_str:
                        if not price:
                            try:
                                price = float(value)
                            except (ValueError, TypeError):
                                pass

                    # 涨跌幅
                    if '涨跌幅' in key_str or '涨幅' in key_str or 'pct' in key_str:
                        if not pct_chg:
                            try:
                                pct_chg = float(value)
                            except (ValueError, TypeError):
                                pass

                    # 换手率
                    if '换手' in key_str or 'turnover' in key_str:
                        if not turnover:
                            try:
                                turnover = float(value)
                            except (ValueError, TypeError):
                                pass

                    # 市值
                    if '总市值' in key_str or '市值' in key_str or 'market_cap' in key_str:
                        if not market_cap:
                            try:
                                # 问财返回的市值可能是亿元单位
                                val = float(value)
                                if val > 1000000000:  # 元
                                    market_cap = val / 100000000
                                else:  # 亿元
                                    market_cap = val
                            except (ValueError, TypeError):
                                pass

                if code:
                    results.append({
                        'code': code,
                        'name': name,
                        'price': price,
                        'pct_chg': pct_chg,
                        'turnover': turnover,
                        'market_cap': market_cap,
                        'ai_score': 0,
                        'signal_tags': [],
                        'pool': '问财选股',
                        'source': 'wencai',
                    })
            except Exception as e:
                print(f"转换问财股票数据失败: {e}")
                continue

        return results

    def filter_trend_breakout_wencai(self):
        """
        问财版趋势突破池选股

        Returns:
            list: 股票列表
        """
        try:
            wencai_ai = get_wencai_ai()
            if not wencai_ai.is_available():
                return []

            print("[StockPool] 使用问财AI选股 - 趋势突破池")
            wencai_stocks = wencai_ai.get_trend_breakout_stocks()
            if wencai_stocks:
                results = self._convert_wencai_stocks(wencai_stocks)
                print(f"[StockPool] 问财选股完成，共 {len(results)} 只")
                return results
            return []
        except Exception as e:
            print(f"问财趋势突破选股失败: {e}")
            return []

    def filter_strong_breakout_wencai(self):
        """
        问财版强势突破池选股

        Returns:
            list: 股票列表
        """
        try:
            wencai_ai = get_wencai_ai()
            if not wencai_ai.is_available():
                return []

            print("[StockPool] 使用问财AI选股 - 强势突破池")
            wencai_stocks = wencai_ai.get_strong_breakout_stocks()
            if wencai_stocks:
                results = self._convert_wencai_stocks(wencai_stocks)
                print(f"[StockPool] 问财选股完成，共 {len(results)} 只")
                return results
            return []
        except Exception as e:
            print(f"问财强势突破选股失败: {e}")
            return []

    def filter_steady_low_wencai(self):
        """
        问财版稳健低吸池选股

        Returns:
            list: 股票列表
        """
        try:
            wencai_ai = get_wencai_ai()
            if not wencai_ai.is_available():
                return []

            print("[StockPool] 使用问财AI选股 - 稳健低吸池")
            wencai_stocks = wencai_ai.get_steady_low_stocks()
            if wencai_stocks:
                results = self._convert_wencai_stocks(wencai_stocks)
                print(f"[StockPool] 问财选股完成，共 {len(results)} 只")
                return results
            return []
        except Exception as e:
            print(f"问财稳健低吸选股失败: {e}")
            return []


_filter = None


def get_stock_pool_filter():
    global _filter
    if _filter is None:
        _filter = StockPoolFilter()
    return _filter
