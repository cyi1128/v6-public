"""
因子综合评分引擎 - V0.7 新增
============================
8因子评分模型，作为AI决策中心的增强评分层。
不修改现有核心策略，仅提供综合评分和仓位建议。

8个因子：
    技术面（40%）：CCI + KDJ(13,3,3) + MACD(8,21,5) + 趋势(MA5/10/20/60)
    因子面（25%）：量比 + 换手率
    市场情绪（20%）：涨停数/炸板率/连板高度
    基本面（15%）：市值 + 财务

使用示例：
    from strategy.factor_score import FactorScorer
    scorer = FactorScorer()
    result = scorer.score(
        kdj_k=25.3, kdj_d=20.1, kdj_j=35.7, kdj_golden=True,
        macd_dif=0.15, macd_dea=0.10, macd_bar=0.05, macd_golden=True,
        cci=-150,
        ma5=10.5, ma10=10.2, ma20=9.8, ma60=9.0, close=10.6,
        volume_ratio=1.8, turnover=8.5,
        market_cap=80,  # 亿元
        roe=12.5, net_profit_growth=15.0,
        market_emotion={'limit_up_count': 65, 'zhaban_rate': 35, 'max_lianban': 5}
    )
    print(result['score'], result['level'], result['reason'])
"""
import logging
from typing import Dict, Any, Optional, List, Tuple

from .factor_config import (
    SCORE_WEIGHTS, TECHNICAL_WEIGHTS, FACTOR_WEIGHTS, FINANCE_WEIGHTS,
    CCI_SCORES, KDJ_SCORES, MACD_SCORES, TREND_SCORES,
    VOLUME_RATIO_SCORES, TURNOVER_SCORES, MARKET_CAP_SCORES,
    MARKET_EMOTION_SCORES, FINANCIAL_SCORES,
    get_score_by_range, get_score_level, get_position_by_score,
    MARKET_ENV_MULTIPLIER,
)

logger = logging.getLogger(__name__)


class FactorScorer:
    """8因子综合评分引擎"""

    def __init__(self):
        self.weights = SCORE_WEIGHTS

    # ================================================================
    # 1. CCI 评分
    # ================================================================
    def score_cci(self, cci: float) -> Tuple[float, str]:
        """CCI形态评分"""
        if cci is None:
            return 50, 'CCI数据缺失'
        return get_score_by_range(cci, CCI_SCORES)

    # ================================================================
    # 2. KDJ 评分（参数13,3,3）
    # ================================================================
    def score_kdj(
        self,
        k: Optional[float] = None,
        d: Optional[float] = None,
        j: Optional[float] = None,
        golden: Optional[bool] = None,
        dead: Optional[bool] = None,
    ) -> Tuple[float, str]:
        """KDJ评分（使用用户参数13,3,3）"""
        if k is None:
            return 50, 'KDJ数据缺失'

        if golden and k < 20:
            return 90, 'KDJ低位金叉，强买入信号'
        if golden and 20 <= k < 50:
            return 70, 'KDJ弱势区金叉'
        if dead and k > 80:
            return 25, 'KDJ高位死叉，卖出信号'
        if dead and 50 <= k < 80:
            return 40, 'KDJ强势区死叉，减仓'
        if k < 20:
            return 75, 'KDJ超卖区域，关注反弹'
        if k > 80:
            return 35, 'KDJ超买区域，注意风险'
        if 50 <= k < 80:
            return 55, 'KDJ强势区持有'
        return 50, 'KDJ中性'

    # ================================================================
    # 3. MACD 评分（参数8,21,5）
    # ================================================================
    def score_macd(
        self,
        dif: Optional[float] = None,
        dea: Optional[float] = None,
        bar: Optional[float] = None,
        golden: Optional[bool] = None,
        dead: Optional[bool] = None,
        prev_bar: Optional[float] = None,
    ) -> Tuple[float, str]:
        """MACD评分（使用用户参数8,21,5）"""
        if dif is None and bar is None:
            return 50, 'MACD数据缺失'

        # 金叉判断
        if golden:
            if dif is not None and dif > 0:
                return 90, 'MACD零轴上方金叉，强趋势'
            if dif is not None and dif <= 0:
                return 75, 'MACD零轴下方金叉，反弹信号'
            return 70, 'MACD零轴附近金叉，启动信号'

        # 死叉判断
        if dead:
            if dif is not None and dif > 0:
                return 35, 'MACD零轴上方死叉，回调风险'
            return 25, 'MACD零轴下方死叉，弱势'

        # 红柱/绿柱变化
        if bar is not None and prev_bar is not None:
            if bar > 0 and bar > prev_bar:
                return 80, 'MACD红柱扩大，多头增强'
            if bar > 0 and bar < prev_bar:
                return 55, 'MACD红柱缩小，动能减弱'
            if bar < 0 and bar > prev_bar:  # 绿柱缩小（bar更接近0）
                return 60, 'MACD绿柱缩小，空头减弱'
            if bar < 0 and bar < prev_bar:
                return 30, 'MACD绿柱扩大，空头增强'

        if bar is not None:
            if bar > 0:
                return 60, 'MACD红柱，多头占优'
            if bar < 0:
                return 40, 'MACD绿柱，空头占优'

        return 50, 'MACD中性'

    # ================================================================
    # 4. 趋势评分（MA5/MA10/MA20/MA60）
    # ================================================================
    def score_trend(
        self,
        close: Optional[float] = None,
        ma5: Optional[float] = None,
        ma10: Optional[float] = None,
        ma20: Optional[float] = None,
        ma60: Optional[float] = None,
    ) -> Tuple[float, str]:
        """均线趋势评分"""
        if close is None or ma5 is None:
            return 50, '均线数据缺失'

        # 完整多头排列
        if all(v is not None for v in [ma5, ma10, ma20, ma60]):
            if ma5 > ma10 > ma20 > ma60:
                return 90, '均线多头排列（MA5>MA10>MA20>MA60）'
            if ma5 < ma10 < ma20 < ma60:
                return 20, '均线空头排列'

        # 站上MA20
        if ma20 is not None:
            if close > ma20:
                if ma5 is not None and ma10 is not None and ma5 > ma10:
                    return 75, '站上MA20且短期多头'
                return 65, '股价站上MA20'
            else:
                if ma60 is not None and close > ma60:
                    return 45, '跌破MA20但在MA60上方'
                return 35, '股价跌破MA20'

        # MA5上穿MA10
        if ma5 is not None and ma10 is not None and ma5 > ma10:
            return 60, 'MA5上穿MA10'

        return 50, '趋势中性'

    # ================================================================
    # 5. 量比评分
    # ================================================================
    def score_volume_ratio(self, volume_ratio: Optional[float]) -> Tuple[float, str]:
        """量比评分"""
        if volume_ratio is None or volume_ratio <= 0:
            return 50, '量比数据缺失'
        return get_score_by_range(volume_ratio, VOLUME_RATIO_SCORES)

    # ================================================================
    # 6. 换手率评分
    # ================================================================
    def score_turnover(self, turnover: Optional[float]) -> Tuple[float, str]:
        """换手率评分（%）"""
        if turnover is None or turnover < 0:
            return 50, '换手率数据缺失'
        return get_score_by_range(turnover, TURNOVER_SCORES)

    # ================================================================
    # 7. 市值评分
    # ================================================================
    def score_market_cap(self, market_cap_yi: Optional[float]) -> Tuple[float, str]:
        """市值评分（单位：亿元）"""
        if market_cap_yi is None or market_cap_yi <= 0:
            return 50, '市值数据缺失'
        return get_score_by_range(market_cap_yi, MARKET_CAP_SCORES)

    # ================================================================
    # 8. 市场情绪评分
    # ================================================================
    def score_market_emotion(
        self,
        emotion_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, str]:
        """
        市场情绪评分

        emotion_data 可包含：
            limit_up_count: 涨停数量
            zhaban_rate: 炸板率（%）
            max_lianban: 最高连板数
            limit_down_count: 跌停数量
        """
        if not emotion_data:
            return 50, '市场情绪数据缺失，使用中性评分'

        limit_up = emotion_data.get('limit_up_count', 0)
        zhaban_rate = emotion_data.get('zhaban_rate', 0)
        max_lianban = emotion_data.get('max_lianban', 0)

        # 炸板率过高
        if zhaban_rate and zhaban_rate > 50:
            return 30, f'炸板率过高（{zhaban_rate:.0f}%），情绪差'

        # 涨停数评分
        if limit_up >= 80 and (not zhaban_rate or zhaban_rate < 40):
            return 85, f'市场情绪高涨（涨停{limit_up}只，炸板率{zhaban_rate:.0f}%）'
        if 50 <= limit_up < 80:
            return 70, f'市场情绪偏暖（涨停{limit_up}只）'
        if 30 <= limit_up < 50:
            return 55, f'市场情绪中性（涨停{limit_up}只）'
        if 20 <= limit_up < 30:
            return 40, f'市场情绪偏弱（涨停{limit_up}只）'
        if limit_up < 20:
            return 25, f'市场情绪低迷（涨停{limit_up}只）'

        return 50, '市场情绪中性'

    # ================================================================
    # 9. 财务评分
    # ================================================================
    def score_financial(
        self,
        roe: Optional[float] = None,
        net_profit_growth: Optional[float] = None,
        gross_margin: Optional[float] = None,
        is_loss: Optional[bool] = None,
    ) -> Tuple[float, str]:
        """财务评分（简化版）"""
        if is_loss:
            return 20, '亏损股，风险高'

        if roe is not None:
            if roe >= 15 and (net_profit_growth is None or net_profit_growth > 0):
                return 90, f'高ROE({roe:.1f}%)+正增长，优质标的'
            if 10 <= roe < 15:
                return 75, f'ROE良好（{roe:.1f}%）'
            if 5 <= roe < 10:
                return 60, f'ROE一般（{roe:.1f}%）'
            if roe < 5:
                return 40, f'ROE偏低（{roe:.1f}%）'

        if net_profit_growth is not None and net_profit_growth > 20:
            return 70, f'净利润高增长（{net_profit_growth:.1f}%）'

        return 55, '财务中性'

    # ================================================================
    # 综合评分
    # ================================================================
    def score(
        self,
        # KDJ（13,3,3）
        kdj_k: Optional[float] = None,
        kdj_d: Optional[float] = None,
        kdj_j: Optional[float] = None,
        kdj_golden: Optional[bool] = None,
        kdj_dead: Optional[bool] = None,
        # MACD（8,21,5）
        macd_dif: Optional[float] = None,
        macd_dea: Optional[float] = None,
        macd_bar: Optional[float] = None,
        macd_prev_bar: Optional[float] = None,
        macd_golden: Optional[bool] = None,
        macd_dead: Optional[bool] = None,
        # CCI
        cci: Optional[float] = None,
        # 趋势均线
        close: Optional[float] = None,
        ma5: Optional[float] = None,
        ma10: Optional[float] = None,
        ma20: Optional[float] = None,
        ma60: Optional[float] = None,
        # 因子面
        volume_ratio: Optional[float] = None,
        turnover: Optional[float] = None,
        # 基本面
        market_cap: Optional[float] = None,  # 亿元
        roe: Optional[float] = None,
        net_profit_growth: Optional[float] = None,
        gross_margin: Optional[float] = None,
        is_loss: Optional[bool] = None,
        # 市场情绪
        market_emotion: Optional[Dict[str, Any]] = None,
        # 股票信息
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        8因子综合评分

        Returns:
            {
                'score': 0-100,
                'level': '强关注/关注/观察/观望/回避',
                'level_desc': 等级描述,
                'technical': 技术面得分,
                'factor': 因子面得分,
                'emotion': 市场情绪得分,
                'finance': 基本面得分,
                'factor_details': {各因子详情},
                'reason': [评分理由列表],
                'position': 建议仓位,
                'position_label': 仓位描述,
            }
        """
        reasons: List[str] = []
        factor_details: Dict[str, Dict] = {}

        # ---- 技术面 ----
        cci_score, cci_reason = self.score_cci(cci)
        kdj_score, kdj_reason = self.score_kdj(kdj_k, kdj_d, kdj_j, kdj_golden, kdj_dead)
        macd_score, macd_reason = self.score_macd(
            macd_dif, macd_dea, macd_bar, macd_golden, macd_dead, macd_prev_bar
        )
        trend_score, trend_reason = self.score_trend(close, ma5, ma10, ma20, ma60)

        technical = (
            cci_score * TECHNICAL_WEIGHTS['cci']
            + kdj_score * TECHNICAL_WEIGHTS['kdj']
            + macd_score * TECHNICAL_WEIGHTS['macd']
            + trend_score * TECHNICAL_WEIGHTS['trend']
        )

        factor_details['cci'] = {'score': cci_score, 'reason': cci_reason}
        factor_details['kdj'] = {'score': kdj_score, 'reason': kdj_reason}
        factor_details['macd'] = {'score': macd_score, 'reason': macd_reason}
        factor_details['trend'] = {'score': trend_score, 'reason': trend_reason}

        # 技术面高分理由
        if cci_score >= 70: reasons.append(cci_reason)
        if kdj_score >= 70: reasons.append(kdj_reason)
        if macd_score >= 70: reasons.append(macd_reason)
        if trend_score >= 70: reasons.append(trend_reason)

        # ---- 因子面 ----
        vr_score, vr_reason = self.score_volume_ratio(volume_ratio)
        to_score, to_reason = self.score_turnover(turnover)
        factor = (
            vr_score * FACTOR_WEIGHTS['volume_ratio']
            + to_score * FACTOR_WEIGHTS['turnover']
        )
        factor_details['volume_ratio'] = {'score': vr_score, 'reason': vr_reason}
        factor_details['turnover'] = {'score': to_score, 'reason': to_reason}
        if vr_score >= 70: reasons.append(vr_reason)
        if to_score >= 70: reasons.append(to_reason)

        # ---- 市场情绪 ----
        emotion, emotion_reason = self.score_market_emotion(market_emotion)
        factor_details['emotion'] = {'score': emotion, 'reason': emotion_reason}
        if emotion >= 70: reasons.append(emotion_reason)

        # ---- 基本面 ----
        cap_score, cap_reason = self.score_market_cap(market_cap)
        fin_score, fin_reason = self.score_financial(roe, net_profit_growth, gross_margin, is_loss)
        finance = (
            cap_score * FINANCE_WEIGHTS['market_cap']
            + fin_score * FINANCE_WEIGHTS['financial']
        )
        factor_details['market_cap'] = {'score': cap_score, 'reason': cap_reason}
        factor_details['financial'] = {'score': fin_score, 'reason': fin_reason}
        if cap_score >= 70: reasons.append(cap_reason)
        if fin_score >= 70: reasons.append(fin_reason)

        # ---- 综合评分 ----
        total_score = (
            technical * self.weights['technical']
            + factor * self.weights['factor']
            + emotion * self.weights['emotion']
            + finance * self.weights['finance']
        )
        total_score = round(total_score, 1)

        level, level_desc = get_score_level(total_score)

        # ---- 仓位建议 ----
        base_position, position_label = get_position_by_score(total_score)
        # 市场环境乘数
        if emotion >= 70:
            env = 'bull'
        elif emotion < 40:
            env = 'bear'
        else:
            env = '震荡'
        multiplier = MARKET_ENV_MULTIPLIER.get(env, 1.0)
        final_position = round(min(base_position * multiplier, 0.30), 2)  # 最高3成

        # 风险提示（低分因子）
        risk_warnings = []
        if cci_score <= 35: risk_warnings.append(cci_reason)
        if kdj_score <= 35: risk_warnings.append(kdj_reason)
        if macd_score <= 35: risk_warnings.append(macd_reason)
        if trend_score <= 35: risk_warnings.append(trend_reason)
        if emotion <= 35: risk_warnings.append(emotion_reason)

        return {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'score': total_score,
            'level': level,
            'level_desc': level_desc,
            'technical': round(technical, 1),
            'factor': round(factor, 1),
            'emotion': round(emotion, 1),
            'finance': round(finance, 1),
            'factor_details': factor_details,
            'reason': reasons[:6],  # 最多6条理由
            'risk_warnings': risk_warnings,
            'position': final_position,
            'position_label': position_label,
            'market_env': env,
        }

    # ================================================================
    # 从DuckDB数据自动评分（便捷方法）
    # ================================================================
    def score_from_duckdb(
        self,
        stock_code: str,
        trade_date: Optional[str] = None,
        duckdb_adapter=None,
    ) -> Dict[str, Any]:
        """
        从DuckDB数据源自动获取数据并评分

        Args:
            stock_code: 股票代码
            trade_date: 交易日期，None取最新
            duckdb_adapter: DuckDBAdapter实例，None则自动创建
        """
        if duckdb_adapter is None:
            try:
                from data.duckdb_adapter import get_duckdb
                duckdb_adapter = get_duckdb()
            except Exception:
                return {'score': 50, 'level': '观望', 'reason': ['DuckDB不可用']}

        if not duckdb_adapter.available:
            return {'score': 50, 'level': '观望', 'reason': ['DuckDB数据源不可用']}

        # 获取日线数据
        if trade_date:
            daily = duckdb_adapter.get_daily_data(
                stock_code, end_date=trade_date, limit=2,
                columns=['股票代码', '交易日期', '收盘价', '涨跌幅',
                         'MACD_DIF', 'MACD_DEA', 'MACD', 'KDJ_K', 'KDJ_D', 'KDJ_J',
                         'CCI', '量比', '换手率(%)', '总市值(万元)']
            )
        else:
            daily = duckdb_adapter.get_daily_data(
                stock_code, limit=2,
                columns=['股票代码', '交易日期', '收盘价', '涨跌幅',
                         'MACD_DIF', 'MACD_DEA', 'MACD', 'KDJ_K', 'KDJ_D', 'KDJ_J',
                         'CCI', '量比', '换手率(%)', '总市值(万元)']
            )

        if daily.empty:
            return {'score': 50, 'level': '观望', 'reason': ['无日线数据']}

        row = daily.iloc[-1]
        prev_row = daily.iloc[-2] if len(daily) >= 2 else None

        # MACD金叉/死叉判断
        macd_golden = None
        macd_dead = None
        if prev_row is not None:
            prev_dif = prev_row.get('MACD_DIF')
            prev_dea = prev_row.get('MACD_DEA')
            cur_dif = row.get('MACD_DIF')
            cur_dea = row.get('MACD_DEA')
            if prev_dif is not None and prev_dea is not None and cur_dif is not None and cur_dea is not None:
                if prev_dif <= prev_dea and cur_dif > cur_dea:
                    macd_golden = True
                elif prev_dif >= prev_dea and cur_dif < cur_dea:
                    macd_dead = True

        # KDJ金叉/死叉
        kdj_golden = None
        kdj_dead = None
        if prev_row is not None:
            prev_k = prev_row.get('KDJ_K')
            prev_d = prev_row.get('KDJ_D')
            cur_k = row.get('KDJ_K')
            cur_d = row.get('KDJ_D')
            if prev_k is not None and prev_d is not None and cur_k is not None and cur_d is not None:
                if prev_k <= prev_d and cur_k > cur_d:
                    kdj_golden = True
                elif prev_k >= prev_d and cur_k < cur_d:
                    kdj_dead = True

        # 市值（万元→亿元）
        market_cap_yi = None
        if row.get('总市值(万元)'):
            market_cap_yi = row['总市值(万元)'] / 10000

        # 市场情绪
        emotion = None
        try:
            emotion_df = duckdb_adapter.get_market_emotion(days=1)
            if not emotion_df.empty:
                e_row = emotion_df.iloc[-1]
                emotion = {
                    'limit_up_count': e_row.get('涨停数', 0),
                    'zhaban_rate': e_row.get('炸板率', 0),
                }
        except Exception:
            pass

        return self.score(
            kdj_k=row.get('KDJ_K'),
            kdj_d=row.get('KDJ_D'),
            kdj_j=row.get('KDJ_J'),
            kdj_golden=kdj_golden,
            kdj_dead=kdj_dead,
            macd_dif=row.get('MACD_DIF'),
            macd_dea=row.get('MACD_DEA'),
            macd_bar=row.get('MACD'),
            macd_prev_bar=prev_row.get('MACD') if prev_row is not None else None,
            macd_golden=macd_golden,
            macd_dead=macd_dead,
            cci=row.get('CCI'),
            close=row.get('收盘价'),
            volume_ratio=row.get('量比'),
            turnover=row.get('换手率(%)'),
            market_cap=market_cap_yi,
            market_emotion=emotion,
            stock_code=stock_code,
        )


# ================================================================
# 便捷函数
# ================================================================
def score_stock(**kwargs) -> Dict[str, Any]:
    """便捷函数：单只股票评分"""
    return FactorScorer().score(**kwargs)


def score_stock_from_duckdb(stock_code: str, **kwargs) -> Dict[str, Any]:
    """便捷函数：从DuckDB数据评分"""
    return FactorScorer().score_from_duckdb(stock_code, **kwargs)


if __name__ == '__main__':
    # 自检
    scorer = FactorScorer()

    # 测试1：强势股
    result = scorer.score(
        kdj_k=25.3, kdj_d=20.1, kdj_golden=True,
        macd_dif=0.15, macd_dea=0.10, macd_bar=0.05, macd_golden=True,
        cci=-150,
        close=10.6, ma5=10.5, ma10=10.2, ma20=9.8, ma60=9.0,
        volume_ratio=1.8, turnover=8.5,
        market_cap=80, roe=12.5, net_profit_growth=15.0,
        market_emotion={'limit_up_count': 65, 'zhaban_rate': 35},
        stock_code='600580', stock_name='卧龙电驱',
    )
    print('=== 测试1：强势股 ===')
    print(f'评分: {result["score"]} 等级: {result["level"]}')
    print(f'技术:{result["technical"]} 因子:{result["factor"]} 情绪:{result["emotion"]} 财务:{result["finance"]}')
    print(f'仓位: {result["position"]*100:.0f}% ({result["position_label"]})')
    print(f'理由: {result["reason"]}')

    # 测试2：弱势股
    result2 = scorer.score(
        kdj_k=85.3, kdj_dead=True,
        macd_dif=-0.1, macd_dead=True,
        cci=250,
        close=8.0, ma5=7.8, ma10=8.2, ma20=8.5, ma60=9.0,
        volume_ratio=6.0, turnover=35.0,
        market_cap=15, roe=2.0, is_loss=True,
        market_emotion={'limit_up_count': 15, 'zhaban_rate': 60},
        stock_code='000001', stock_name='测试弱势',
    )
    print('\n=== 测试2：弱势股 ===')
    print(f'评分: {result2["score"]} 等级: {result2["level"]}')
    print(f'技术:{result2["technical"]} 因子:{result2["factor"]} 情绪:{result2["emotion"]} 财务:{result2["finance"]}')
    print(f'风险: {result2["risk_warnings"]}')

    print('\n=== 自检完成 ===')
