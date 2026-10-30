# -*- coding: utf-8 -*-
"""
V6.0 Pro 手动条件筛选引擎
支持14种筛选条件，后台线程执行，不修改自动选股策略
"""
import os
import json
from datetime import datetime


class ManualFilterConfig:
    """手动筛选条件配置"""

    def __init__(self):
        # 1. 行业板块（多选，空列表表示不限制）
        self.industries = []
        self.industry_enabled = False

        # 2. 股价范围
        self.price_min = 5.0
        self.price_max = 60.0
        self.price_enabled = False

        # 3. 总市值范围（亿）
        self.market_cap_min = 30.0
        self.market_cap_max = 300.0
        self.market_cap_enabled = False

        # 4. 换手率范围（%）
        self.turnover_min = 5.0
        self.turnover_max = 20.0
        self.turnover_enabled = False

        # 5. 量比范围
        self.volume_ratio_min = 1.2
        self.volume_ratio_max = 3.0
        self.volume_ratio_enabled = False

        # 6. 当日涨幅范围（%）
        self.pct_min = 2.0
        self.pct_max = 8.0
        self.pct_enabled = False

        # 7. 振幅范围（%）
        self.amplitude_min = 3.0
        self.amplitude_max = 15.0
        self.amplitude_enabled = False

        # 8. 成交量突破倍数（成交量/5日均量）
        self.volume_break_min = 1.5
        self.volume_break_max = 10.0
        self.volume_break_enabled = False

        # 9. 均线多头排列 MA5>MA9>MA20
        self.ma_bullish_enabled = False

        # 10. KDJ J值范围
        self.kdj_j_min = -20.0
        self.kdj_j_max = 10.0
        self.kdj_enabled = False

        # 11. MA5上穿MA9（穿九）
        self.ma5_cross_ma9_enabled = False

        # 12. 收盘价与MA9距离（元）
        self.ma9_distance_min = 0.02
        self.ma9_distance_max = 0.10
        self.ma9_distance_enabled = False

        # 13. 收盘价与MA5距离（元）
        self.ma5_distance_min = 0.02
        self.ma5_distance_max = 0.10
        self.ma5_distance_enabled = False

        # 14. 连续上涨（连续3日涨幅≥1%）
        self.continuous_up_days = 3
        self.continuous_up_min_pct = 1.0
        self.continuous_up_enabled = False

        # 筛选模式
        self.strict_mode = True  # True: 全部符合才保留; False: 按命中率排序
        self.min_hit_rate = 0.5  # 宽松模式下最低命中率（0-1）

        # 方案名称
        self.name = '未命名方案'

    def to_dict(self):
        """转为字典用于保存"""
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data):
        """从字典加载"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def save_to_file(self, filepath):
        """保存到文件"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath):
        """从文件加载"""
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


class ManualFilterEngine:
    """手动筛选引擎"""

    def __init__(self):
        self._stop = False

    def stop(self):
        self._stop = True

    def filter(self, config, stock_list=None, progress_callback=None):
        """
        执行手动筛选

        Args:
            config: ManualFilterConfig 筛选条件
            stock_list: 预筛选股票列表（None表示全市场）
            progress_callback: 进度回调 callback(current, total, message)
        Returns:
            list: 筛选结果
        """
        self._stop = False
        results = []

        try:
            from utils.tdx_stock_list import get_full_market_quotes, enrich_finance_info
            from utils.kline_provider import get_daily_kline
            from utils.indicators import calc_ma_series, calc_kdj_series
            import pandas as pd

            # 第一步：获取股票列表
            if progress_callback:
                progress_callback(0, 5, '正在获取股票行情...')

            if stock_list is None:
                all_stocks = get_full_market_quotes()
            else:
                all_stocks = stock_list

            if not all_stocks:
                return []

            if progress_callback:
                progress_callback(1, 5, f'共{len(all_stocks)}只，开始行情条件过滤...')

            # 第二步：行情条件过滤（不需要财务信息，price/pct/high/low都有）
            quote_filtered = []
            for i, s in enumerate(all_stocks):
                if self._stop:
                    return []

                code = s.get('code', '')
                name = s.get('name', '')
                price = s.get('price', 0)
                pct = s.get('pct_chg', 0)
                high = s.get('high', 0)
                low = s.get('low', 0)
                last_close = s.get('last_close', price)

                # ST过滤（始终过滤）
                if 'ST' in name or 'st' in name.lower() or '*ST' in name:
                    continue

                # 价格范围
                if config.price_enabled:
                    if price < config.price_min or price > config.price_max:
                        continue

                # 涨幅范围
                if config.pct_enabled:
                    if pct < config.pct_min or pct > config.pct_max:
                        continue

                # 振幅范围
                if config.amplitude_enabled and last_close > 0:
                    amplitude = (high - low) / last_close * 100
                    if amplitude < config.amplitude_min or amplitude > config.amplitude_max:
                        continue

                quote_filtered.append(s)

                if progress_callback and (i + 1) % 500 == 0:
                    progress_callback(1, 5, f'行情过滤中... {i+1}/{len(all_stocks)}')

            if progress_callback:
                progress_callback(2, 5, f'行情过滤后剩余{len(quote_filtered)}只，获取财务信息...')

            # 第三步：获取财务信息（补充market_cap, turnover, industry）
            if stock_list is None:
                enriched = enrich_finance_info(quote_filtered)
            else:
                enriched = quote_filtered

            if not enriched:
                return []

            if progress_callback:
                progress_callback(3, 5, f'财务信息获取完成，开始市值/换手率/行业过滤...')

            # 第四步：财务条件过滤（需要market_cap, turnover, industry）
            finance_filtered = []
            for i, s in enumerate(enriched):
                if self._stop:
                    return []

                market_cap = s.get('market_cap', 0)
                turnover = s.get('turnover', 0)
                industry = s.get('industry', '')

                # 行业筛选
                if config.industry_enabled and config.industries:
                    if not any(ind in industry for ind in config.industries):
                        continue

                # 市值范围
                if config.market_cap_enabled:
                    if market_cap < config.market_cap_min or market_cap > config.market_cap_max:
                        continue

                # 换手率范围
                if config.turnover_enabled:
                    if turnover < config.turnover_min or turnover > config.turnover_max:
                        continue

                finance_filtered.append(s)

            if progress_callback:
                progress_callback(3, 5, f'财务过滤后剩余{len(finance_filtered)}只')

            # 第三步：获取K线并计算技术指标
            need_kline = any([
                config.volume_ratio_enabled,
                config.volume_break_enabled,
                config.ma_bullish_enabled,
                config.kdj_enabled,
                config.ma5_cross_ma9_enabled,
                config.ma9_distance_enabled,
                config.ma5_distance_enabled,
                config.continuous_up_enabled,
            ])

            if not need_kline:
                # 不需要K线，直接返回财务过滤结果
                for s in finance_filtered:
                    s['ma_status'] = '--'
                    s['kdj_status'] = '--'
                    s['macd_status'] = '--'
                    s['volume_ratio'] = s.get('volume_ratio', 0)
                    s['volume_break'] = 0
                    s['condition_hits'] = []
                    s['hit_count'] = 0
                    s['total_conditions'] = 0
                    s['hit_rate'] = 100.0
                    results.append(s)
                if progress_callback:
                    progress_callback(5, 5, f'筛选完成，共{len(results)}只')
                return results

            if progress_callback:
                progress_callback(4, 5, f'开始K线技术指标筛选，共{len(finance_filtered)}只...')

            # 计算启用的K线条件总数
            kline_conditions = []
            if config.volume_ratio_enabled: kline_conditions.append('量比')
            if config.volume_break_enabled: kline_conditions.append('成交量突破')
            if config.ma_bullish_enabled: kline_conditions.append('均线多头')
            if config.kdj_enabled: kline_conditions.append('KDJ')
            if config.ma5_cross_ma9_enabled: kline_conditions.append('穿九')
            if config.ma9_distance_enabled: kline_conditions.append('距MA9')
            if config.ma5_distance_enabled: kline_conditions.append('距MA5')
            if config.continuous_up_enabled: kline_conditions.append('连续上涨')
            total_kline_conditions = len(kline_conditions)

            total = len(finance_filtered)
            for i, s in enumerate(finance_filtered):
                if self._stop:
                    return []

                code = s.get('code', '')
                price = s.get('price', 0)

                try:
                    kline = get_daily_kline(code)
                    if not kline:
                        continue

                    closes = kline.get('close', [])
                    volumes = kline.get('volume', [])
                    highs = kline.get('high', [])
                    lows = kline.get('low', [])

                    if len(closes) < 30:
                        continue

                    # 计算MA
                    ma5 = calc_ma_series(closes, 5)
                    ma9 = calc_ma_series(closes, 9)
                    ma20 = calc_ma_series(closes, 20)

                    def _last(series):
                        if series is None or len(series) == 0:
                            return None
                        v = series.iloc[-1] if hasattr(series, 'iloc') else series[-1]
                        return float(v) if not pd.isna(v) else None

                    ma5_val = _last(ma5)
                    ma9_val = _last(ma9)
                    ma20_val = _last(ma20)

                    # 计算KDJ
                    kdj = calc_kdj_series(highs, lows, closes, n=13, m1=3, m2=3)
                    k_val = _last(kdj[0]) if kdj else None
                    d_val = _last(kdj[1]) if kdj else None
                    j_val = _last(kdj[2]) if kdj else None

                    # 计算量比
                    volume_ratio = 0
                    if len(volumes) >= 6:
                        avg_vol_5 = sum(volumes[-6:-1]) / 5
                        if avg_vol_5 > 0:
                            volume_ratio = volumes[-1] / avg_vol_5

                    # 成交量突破倍数
                    volume_break = 0
                    if len(volumes) >= 6:
                        avg_vol_5 = sum(volumes[-5:]) / 5
                        if avg_vol_5 > 0:
                            volume_break = volumes[-1] / avg_vol_5

                    # ===== 技术条件命中检查（记录每个条件是否命中）=====
                    hits = []  # 命中的条件列表

                    # 量比范围
                    if config.volume_ratio_enabled:
                        if config.volume_ratio_min <= volume_ratio <= config.volume_ratio_max:
                            hits.append('量比')

                    # 成交量突破倍数
                    if config.volume_break_enabled:
                        if config.volume_break_min <= volume_break <= config.volume_break_max:
                            hits.append('成交量突破')

                    # 均线多头排列 MA5>MA9>MA20
                    if config.ma_bullish_enabled:
                        if ma5_val and ma9_val and ma20_val and ma5_val > ma9_val > ma20_val:
                            hits.append('均线多头')

                    # KDJ J值范围
                    if config.kdj_enabled:
                        if j_val is not None and config.kdj_j_min <= j_val <= config.kdj_j_max:
                            hits.append('KDJ')

                    # MA5上穿MA9
                    if config.ma5_cross_ma9_enabled:
                        if ma5_val and ma9_val and len(closes) >= 2:
                            prev_ma5 = _last(ma5.iloc[:-1]) if hasattr(ma5, 'iloc') and len(ma5) > 1 else None
                            prev_ma9 = _last(ma9.iloc[:-1]) if hasattr(ma9, 'iloc') and len(ma9) > 1 else None
                            if prev_ma5 and prev_ma9 and prev_ma5 <= prev_ma9 and ma5_val > ma9_val:
                                hits.append('穿九')

                    # 收盘价与MA9距离
                    if config.ma9_distance_enabled:
                        if ma9_val:
                            dist = abs(price - ma9_val)
                            if config.ma9_distance_min <= dist <= config.ma9_distance_max:
                                hits.append('距MA9')

                    # 收盘价与MA5距离
                    if config.ma5_distance_enabled:
                        if ma5_val:
                            dist = abs(price - ma5_val)
                            if config.ma5_distance_min <= dist <= config.ma5_distance_max:
                                hits.append('距MA5')

                    # 连续上涨
                    if config.continuous_up_enabled:
                        if len(closes) >= config.continuous_up_days + 1:
                            continuous = True
                            for j in range(config.continuous_up_days):
                                idx = len(closes) - 1 - j
                                if closes[idx-1] <= 0:
                                    continuous = False
                                    break
                                daily_pct = (closes[idx] - closes[idx-1]) / closes[idx-1] * 100
                                if daily_pct < config.continuous_up_min_pct:
                                    continuous = False
                                    break
                            if continuous:
                                hits.append('连续上涨')

                    # ===== 根据模式决定是否保留 =====
                    if config.strict_mode:
                        # 严格模式：必须全部命中
                        if len(hits) != total_kline_conditions:
                            continue
                    else:
                        # 宽松模式：命中率 >= min_hit_rate
                        hit_rate = len(hits) / total_kline_conditions if total_kline_conditions > 0 else 1
                        if hit_rate < config.min_hit_rate:
                            continue

                    # ===== 通过筛选，添加技术指标状态 =====
                    # MA状态
                    if ma5_val and ma9_val and ma20_val:
                        if ma5_val > ma9_val > ma20_val:
                            s['ma_status'] = '多头排列'
                        elif ma5_val < ma9_val < ma20_val:
                            s['ma_status'] = '空头排列'
                        else:
                            s['ma_status'] = '交叉'
                    else:
                        s['ma_status'] = '--'

                    # KDJ状态
                    if k_val and d_val and j_val is not None:
                        if k_val > d_val and j_val > 50:
                            s['kdj_status'] = '金叉强势'
                        elif k_val < d_val and j_val < 50:
                            s['kdj_status'] = '死叉弱势'
                        else:
                            s['kdj_status'] = f'J={j_val:.1f}'
                    else:
                        s['kdj_status'] = '--'

                    # MACD状态（简化）
                    s['macd_status'] = '--'

                    s['volume_ratio'] = round(volume_ratio, 2)
                    s['volume_break'] = round(volume_break, 2)
                    s['signals'] = []

                    # 信号标签
                    if '穿九' in hits:
                        s['signals'].append('穿九')
                    if '连续上涨' in hits:
                        s['signals'].append('连续上涨')
                    if '均线多头' in hits:
                        s['signals'].append('多头排列')

                    # 条件命中率
                    s['condition_hits'] = hits
                    s['hit_count'] = len(hits)
                    s['total_conditions'] = total_kline_conditions
                    s['hit_rate'] = round(len(hits) / total_kline_conditions * 100, 1) if total_kline_conditions > 0 else 100.0

                    s['update_time'] = datetime.now().strftime('%H:%M:%S')
                    results.append(s)

                except Exception as e:
                    print(f"筛选{code}技术指标失败: {e}")

                if progress_callback and (i + 1) % 10 == 0:
                    progress_callback(4, 5, f'技术指标筛选中... {i+1}/{total}')

            # 宽松模式下按命中率排序
            if not config.strict_mode and results:
                results.sort(key=lambda x: (x.get('hit_rate', 0), x.get('hit_count', 0)), reverse=True)

            if progress_callback:
                progress_callback(5, 5, f'筛选完成，共发现{len(results)}只股票')

        except Exception as e:
            print(f"手动筛选引擎异常: {e}")
            import traceback
            traceback.print_exc()

        return results


# 预设筛选方案
PRESET_CONFIGS = {
    '短线突破': {
        'name': '短线突破',
        'price_enabled': True, 'price_min': 5, 'price_max': 50,
        'pct_enabled': True, 'pct_min': 2, 'pct_max': 8,
        'volume_break_enabled': True, 'volume_break_min': 1.5, 'volume_break_max': 10,
        'ma5_cross_ma9_enabled': True,
    },
    '低吸反弹': {
        'name': '低吸反弹',
        'price_enabled': True, 'price_min': 5, 'price_max': 40,
        'kdj_enabled': True, 'kdj_j_min': -20, 'kdj_j_max': 10,
        'ma5_distance_enabled': True, 'ma5_distance_min': 0.02, 'ma5_distance_max': 0.15,
    },
    '量价启动': {
        'name': '量价启动',
        'price_enabled': True, 'price_min': 5, 'price_max': 60,
        'turnover_enabled': True, 'turnover_min': 3, 'turnover_max': 25,
        'volume_ratio_enabled': True, 'volume_ratio_min': 1.5, 'volume_ratio_max': 5,
        'continuous_up_enabled': True, 'continuous_up_days': 2, 'continuous_up_min_pct': 0.5,
    },
}
