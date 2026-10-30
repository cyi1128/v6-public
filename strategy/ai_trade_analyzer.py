# -*- coding: utf-8 -*-
"""
AI交易分析模块
综合技术指标、K线形态、成交量等生成交易分析
优先使用豆包AI，没有配置则使用规则匹配
"""
import pandas as pd
import numpy as np
import time
from utils.indicators import (
    calc_ma_series, calc_kdj_series, calc_macd_series,
    calc_avg_volume, calc_volume_ratio
)
from strategy.kline_scanner import get_scanner
from strategy.indicator_scanner import get_indicator_scanner
from strategy.main_trend_scanner import get_main_trend_scanner
from strategy.wencai_ai import get_wencai_ai

# 问财AI开关（默认关闭，避免影响核心扫描速度）
ENABLE_WENCAI_AI = False
# AI调用超时时间（秒）
AI_TIMEOUT = 3


class AITradeAnalyzer:
    """AI交易分析器"""

    def analyze(self, stock_info, kline_data, market_sentiment=0, use_ai=None):
        """
        生成AI交易分析

        Args:
            stock_info: dict {'code', 'name', 'price', 'pct_chg', ...}
            kline_data: dict {'open', 'high', 'low', 'close', 'volume'}
            market_sentiment: float, 市场整体情绪分数（-1到1），正数偏多，负数偏空
            use_ai: bool, 是否使用AI分析（None则使用全局配置）

        Returns:
            dict: 分析结果
        """
        if not kline_data or len(kline_data.get('close', [])) < 30:
            return self._empty_result(stock_info)

        # 使用全局配置
        if use_ai is None:
            use_ai = ENABLE_WENCAI_AI

        code = stock_info.get('code', '')
        name = stock_info.get('name', '')

        closes = kline_data['close']
        highs = kline_data['high']
        lows = kline_data['low']
        volumes = kline_data['volume']

        # 计算指标
        ma5 = calc_ma_series(closes, 5)
        ma10 = calc_ma_series(closes, 10)
        ma20 = calc_ma_series(closes, 20)
        k, d, j = calc_kdj_series(highs, lows, closes, n=13, m1=3, m2=3)
        dif, dea, macd_hist = calc_macd_series(closes, fast=8, slow=21, signal=5)

        current_price = closes[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else current_price
        current_ma20 = ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else current_price
        current_k = k.iloc[-1] if not pd.isna(k.iloc[-1]) else 50
        current_d = d.iloc[-1] if not pd.isna(d.iloc[-1]) else 50
        current_j = j.iloc[-1] if not pd.isna(j.iloc[-1]) else 50
        current_dif = dif.iloc[-1] if not pd.isna(dif.iloc[-1]) else 0
        current_dea = dea.iloc[-1] if not pd.isna(dea.iloc[-1]) else 0
        current_hist = macd_hist.iloc[-1] if not pd.isna(macd_hist.iloc[-1]) else 0

        # 扫描信号
        kline_signals = get_scanner().scan(kline_data)
        indicator_signals = get_indicator_scanner().scan_all(kline_data)
        main_trend = get_main_trend_scanner().scan(kline_data)

        all_signals = kline_signals + indicator_signals
        if main_trend:
            all_signals.append(main_trend)

        # 技术评分（0-100）
        score = self._calc_score(
            current_price, current_ma5, current_ma20,
            current_k, current_d, current_j, current_dif, current_hist,
            volumes, all_signals, market_sentiment
        )

        # 趋势判断
        trend = self._judge_trend(current_price, current_ma5, current_ma20, current_k, current_dif)

        # 买入条件
        buy_conditions = self._get_buy_conditions(all_signals, current_k, current_j, current_dif, current_hist)

        # 风险提示
        risks = self._get_risks(current_price, current_ma5, current_ma20, current_k, current_j, current_dif)

        # 操作建议
        suggestion = self._get_suggestion(score, trend, buy_conditions, risks)

        # 基础结果
        result = {
            'code': code,
            'name': name,
            'price': current_price,
            'pct_chg': stock_info.get('pct_chg', 0),
            'trend': trend,
            'score': score,
            'signals': all_signals,
            'buy_conditions': buy_conditions,
            'risks': risks,
            'suggestion': suggestion,
            'indicators': {
                'ma5': current_ma5,
                'ma10': ma10.iloc[-1] if not pd.isna(ma10.iloc[-1]) else current_price,
                'ma20': current_ma20,
                'k': current_k,
                'd': current_d,
                'j': current_j,
                'dif': current_dif,
                'dea': current_dea,
                'macd_hist': current_hist,
                'vol_ratio': calc_volume_ratio(volumes),
            },
            'use_ai': False,
            'ai_summary': '',
            'ai_analysis': '',
            'ai_suggestion': '',
        }

        base_score = score
        ai_status = '关闭'

        # 使用同花顺问财AI（异常隔离，失败不影响基础评分）
        if use_ai and ENABLE_WENCAI_AI:
            ai_status = '失败'
            try:
                wencai_ai = get_wencai_ai()
                if wencai_ai and wencai_ai.is_available():
                    start_time = time.time()
                    wencai_result = wencai_ai.get_stock_ai_analysis(code, name)
                    elapsed = time.time() - start_time

                    if wencai_result and elapsed < AI_TIMEOUT:
                        ai_status = '成功'
                        result['use_ai'] = True
                        result['ai_source'] = 'wencai'
                        result['ai_summary'] = wencai_result.get('summary', '')
                        result['ai_analysis'] = wencai_result.get('analysis', '')
                        result['ai_suggestion'] = wencai_result.get('suggestion', '')
                        if wencai_result.get('score'):
                            result['score'] = wencai_result['score']
                        if wencai_result.get('trend'):
                            result['trend'] = wencai_result['trend']
                        if wencai_result.get('buy_conditions'):
                            result['buy_conditions'] = wencai_result['buy_conditions']
                        if wencai_result.get('risks'):
                            result['risks'] = wencai_result['risks']
                        if wencai_result.get('suggestion'):
                            result['suggestion'] = wencai_result['suggestion']
            except Exception as e:
                # AI调用失败，使用基础评分，不影响核心流程
                ai_status = f'失败({str(e)[:20]})'
                pass

        # 打印AI评分日志（已禁用：逐只打印2993次会阻塞UI导致程序未响应）
        # print(f"[AI评分] 股票:{code} 基础评分:{base_score:.0f} AI:{ai_status} 最终评分:{result['score']:.0f}")

        return result

    def _calc_score(self, price, ma5, ma20, k, d, j, dif, hist, volumes, signals, market_sentiment=0):
        """计算技术评分0-100"""
        score = 50  # 基础分

        # 均线位置（20分）
        if price > ma5:
            score += 8
        if price > ma20:
            score += 7
        if ma5 > ma20:
            score += 5

        # KDJ（20分）
        if 20 <= k <= 80:
            score += 5
        if k > d:
            score += 5
        if j > 0:
            score += 5
        if 30 <= k <= 60:
            score += 5

        # MACD（20分）
        if dif > 0:
            score += 7
        if hist > 0:
            score += 7
        if hist > 0 and len(volumes) >= 2 and hist > (macd_hist_prev := hist):  # 红柱扩大
            score += 6

        # 成交量（10分）
        vol_ratio = calc_volume_ratio(volumes)
        if 1.0 <= vol_ratio <= 3.0:
            score += 10
        elif vol_ratio > 3.0:
            score += 5

        # 信号加分（20分）
        for sig in signals:
            if sig.get('signal') in ('cross_three', 'main_trend_start', 'buy_point'):
                score += 6
            elif sig.get('signal') in ('cross_5_10', 'double_volume', 'kdj_golden'):
                score += 4
            elif sig.get('signal') in ('horizontal_base', 'pullback', 'macd_golden_below'):
                score += 2

        # 市场情绪因子（10分权重）
        # market_sentiment: -1到1，映射到-10到+10分
        sentiment_score = market_sentiment * 10
        score += sentiment_score

        return min(100, max(0, int(score)))
    
    def _calc_concept_strength(self, ai_concepts, stock_info):
        """
        计算概念强度评分（0-100分）
        
        只使用ai_concepts（高可信概念），不读取concept字段
        避免低置信度概念污染AI决策
        
        评分构成：
        - 概念真实性：50分（A级50分，B级30分，C级0分）
        - 市场热度：30分（概念板块涨幅）
        - 资金表现：20分（个股量价配合）
        
        Args:
            ai_concepts: list, AI实际读取的概念列表（高可信）
            stock_info: dict, 股票信息
        
        Returns:
            int: 概念强度评分（0-100）
        """
        if not ai_concepts or not isinstance(ai_concepts, list) or len(ai_concepts) == 0:
            return 0
        
        score = 0
        
        # 1. 概念真实性（50分）
        # 注意：这里只使用ai_concepts，已经是过滤后的高可信概念
        # 数量越多，真实性越强
        concept_count = len(ai_concepts)
        if concept_count >= 5:
            score += 50
        elif concept_count >= 3:
            score += 40
        elif concept_count >= 2:
            score += 30
        elif concept_count >= 1:
            score += 20
        
        # 2. 市场热度（30分）
        try:
            from strategy.theme_analyzer import get_concept_market
            market_concepts = get_concept_market()
            
            if market_concepts and len(market_concepts) > 0:
                # 计算股票所有AI概念的平均涨幅
                total_pct = 0
                match_count = 0
                
                for mc in market_concepts:
                    mc_name = mc.get('name', '')
                    mc_pct = mc.get('change_pct', 0)
                    
                    for ai_concept in ai_concepts:
                        if mc_name and (mc_name in ai_concept or ai_concept in mc_name):
                            total_pct += mc_pct
                            match_count += 1
                            break
                
                if match_count > 0:
                    avg_pct = total_pct / match_count
                    if avg_pct > 5:
                        score += 30
                    elif avg_pct > 3:
                        score += 25
                    elif avg_pct > 2:
                        score += 20
                    elif avg_pct > 1:
                        score += 15
                    elif avg_pct > 0:
                        score += 10
        except Exception:
            # 市场热度获取失败，不加分也不减分
            pass
        
        # 3. 资金表现（20分）
        pct_chg = stock_info.get('pct_chg', 0)
        if pct_chg >= 9.9:  # 涨停
            score += 20
        elif pct_chg >= 5:
            score += 15
        elif pct_chg >= 3:
            score += 10
        elif pct_chg >= 1:
            score += 5
        
        return min(100, max(0, int(score)))

    def _judge_trend(self, price, ma5, ma20, k, dif):
        """判断趋势强弱"""
        strong_count = 0
        if price > ma5:
            strong_count += 1
        if price > ma20:
            strong_count += 1
        if ma5 > ma20:
            strong_count += 1
        if k > 50:
            strong_count += 1
        if dif > 0:
            strong_count += 1

        if strong_count >= 4:
            return '强势'
        elif strong_count >= 2:
            return '中性'
        else:
            return '弱势'

    def _get_buy_conditions(self, signals, k, j, dif, hist):
        """获取满足的买入条件"""
        conditions = []
        signal_names = [s.get('name', '') for s in signals]

        for name in signal_names:
            if name:
                conditions.append(name)

        if k < 20:
            conditions.append('KDJ低位')
        if j < 0:
            conditions.append('J值超卖')
        if dif < 0 and hist > 0:
            conditions.append('MACD轴下金叉')

        return conditions

    def _get_risks(self, price, ma5, ma20, k, j, dif):
        """获取风险提示"""
        risks = []

        if price < ma5:
            risks.append('股价在5日线下')
        if price < ma20:
            risks.append('股价在20日线下')
        if k > 80:
            risks.append('KDJ高位超买')
        if j > 100:
            risks.append('J值超买')
        if dif < 0:
            risks.append('MACD在零轴下')

        return risks

    def _get_suggestion(self, score, trend, buy_conditions, risks):
        """获取操作建议"""
        if score >= 80 and trend == '强势' and len(buy_conditions) >= 3:
            return '买入机会'
        elif score >= 65 and len(buy_conditions) >= 2:
            return '关注'
        elif score >= 50:
            return '观察'
        else:
            return '等待'

    def _empty_result(self, stock_info):
        return {
            'code': stock_info.get('code', ''),
            'name': stock_info.get('name', ''),
            'price': stock_info.get('price', 0),
            'pct_chg': stock_info.get('pct_chg', 0),
            'trend': '未知',
            'score': 0,
            'signals': [],
            'buy_conditions': [],
            'risks': ['数据不足'],
            'suggestion': '等待',
            'indicators': {},
            'use_ai': False,
            'ai_summary': '',
            'ai_analysis': '',
            'ai_suggestion': '',
        }


_analyzer = None


def get_ai_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = AITradeAnalyzer()
    return _analyzer
