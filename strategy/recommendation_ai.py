# -*- coding: utf-8 -*-
"""
AI个股推荐理由与操作理由解释模块
V1.1 新增功能

原则：
- 只解释已有数据，不编造消息
- 所有推荐必须有数据依据
- 独立层，不修改缠论核心
- 保持现有缠论报告结构不变，作为增强层

数据来源：
1. 实时行情：价格、涨跌幅、成交量、换手率、成交额
2. 技术指标：MA5/10/20、MACD、KDJ、成交量变化
3. 缠论结构：当前状态、买卖点、中枢
4. 公司信息：行业、概念、题材
5. 市场热点：板块强度、热门题材
"""

import re


class RecommendationAI:
    """AI个股推荐理由解释器"""

    def __init__(self):
        pass

    def generate_recommendation(self, stock_info, tech_data, chanlun_data, theme_data=None):
        """
        生成完整的AI推荐理由报告

        参数：
            stock_info: 股票基本信息
                - name: 股票名称
                - code: 股票代码
                - price: 当前价格
                - change_pct: 涨跌幅
                - volume: 成交量
                - turnover: 换手率
                - amount: 成交额
                - industry: 所属行业
                - concepts: 所属概念列表
            tech_data: 技术指标数据
                - ma5, ma10, ma20: 均线价格
                - macd_dif, macd_dea, macd_bar: MACD指标
                - kdj_k, kdj_d, kdj_j: KDJ指标
                - volume_ratio: 量比
                - volume_change: 成交量变化
            chanlun_data: 缠论分析结果
                - current_state: 当前状态
                - state_detail: 状态说明
                - signals: 买卖点列表
                - zhongshu: 中枢信息
                - final_score: 最终评分
                - position: 仓位建议
            theme_data: 题材分析数据（可选）
                - main_theme: 核心题材
                - theme_reasons: 题材理由列表
                - theme_strength: 题材强度

        返回：
            recommendation: 推荐理由报告字典
        """
        result = {}

        # 1. 生成推荐理由
        result['recommend_reasons'] = self._generate_recommend_reasons(
            stock_info, tech_data, chanlun_data, theme_data
        )

        # 2. 生成操作理由
        result['operation_reason'] = self._generate_operation_reason(
            stock_info, tech_data, chanlun_data
        )

        # 3. 生成短线策略
        result['short_term_strategy'] = self._generate_short_term_strategy(
            stock_info, tech_data, chanlun_data
        )

        # 4. 生成T策略
        result['t_strategy'] = self._generate_t_strategy(
            stock_info, tech_data, chanlun_data
        )

        # 5. 生成风险提示
        result['risk_warnings'] = self._generate_risk_warnings(
            stock_info, tech_data, chanlun_data
        )

        # 6. 综合评级
        result['overall_rating'] = self._generate_overall_rating(
            stock_info, tech_data, chanlun_data
        )

        return result

    def _generate_recommend_reasons(self, stock_info, tech_data, chanlun_data, theme_data):
        """生成推荐理由（5个维度）"""
        reasons = []

        # 1. 行业逻辑
        industry = stock_info.get('industry', '')
        if industry:
            industry_reason = f"公司属于{industry}行业"
            # 可以根据行业名称补充一些通用逻辑
            if any(k in industry for k in ['半导体', '芯片', '电子']):
                industry_reason += "，受益于国产替代和科技自主可控大趋势"
            elif any(k in industry for k in ['新能源', '光伏', '锂电', '储能']):
                industry_reason += "，受益于双碳目标和能源转型大趋势"
            elif any(k in industry for k in ['医药', '医疗', '生物']):
                industry_reason += "，受益于人口老龄化和健康消费升级"
            elif any(k in industry for k in ['AI', '人工智能', '软件', '计算机']):
                industry_reason += "，受益于AI技术革命和数字化转型"
            elif any(k in industry for k in ['机器人', '自动化', '智能制造']):
                industry_reason += "，受益于制造业智能化升级和人工替代"
            reasons.append({'type': '行业逻辑', 'content': industry_reason})

        # 2. 题材逻辑
        if theme_data:
            main_theme = theme_data.get('main_theme', '')
            theme_reasons = theme_data.get('theme_reasons', [])
            if main_theme:
                theme_content = f"核心题材：{main_theme}"
                if theme_reasons:
                    theme_content += f"，{theme_reasons[0]}"
                reasons.append({'type': '题材逻辑', 'content': theme_content})
        elif stock_info.get('concepts'):
            concepts = stock_info['concepts']
            if isinstance(concepts, list) and concepts:
                top_concepts = concepts[:3]
                concepts_str = '、'.join(top_concepts)
                reasons.append({
                    'type': '题材逻辑',
                    'content': f"涉及{concepts_str}等概念，具备一定题材弹性"
                })

        # 3. 业绩逻辑（简化版，后续可接入真实财务数据）
        # 这里先用占位，后续可以接入真实业绩数据
        reasons.append({
            'type': '业绩逻辑',
            'content': '需结合最新财报和行业景气度进一步验证业绩改善情况'
        })

        # 4. 资金逻辑
        volume_ratio = tech_data.get('volume_ratio', 0)
        turnover = stock_info.get('turnover', 0)
        change_pct = stock_info.get('change_pct', 0)

        if volume_ratio > 1.5 and change_pct > 0:
            fund_reason = f"近期量比{volume_ratio:.1f}，成交量明显放大，资金关注度提升"
        elif turnover > 5:
            fund_reason = f"换手率{turnover:.1f}%，交投活跃，市场关注度较高"
        elif change_pct > 3 and volume_ratio > 1.2:
            fund_reason = "放量上涨，资金流入迹象明显"
        else:
            fund_reason = "成交量平稳，资金面相对均衡"
        reasons.append({'type': '资金逻辑', 'content': fund_reason})

        # 5. 技术逻辑
        tech_reason = self._generate_tech_reason(stock_info, tech_data, chanlun_data)
        reasons.append({'type': '技术逻辑', 'content': tech_reason})

        return reasons

    def _generate_tech_reason(self, stock_info, tech_data, chanlun_data):
        """生成技术逻辑描述"""
        parts = []

        # 缠论状态
        current_state = chanlun_data.get('current_state', '未知')
        state_detail = chanlun_data.get('state_detail', '')
        if current_state:
            parts.append(f"缠论结构：{current_state}")

        # 均线状态
        ma5 = tech_data.get('ma5', 0)
        ma10 = tech_data.get('ma10', 0)
        ma20 = tech_data.get('ma20', 0)
        price = stock_info.get('price', 0)

        if ma5 > 0 and ma10 > 0 and ma20 > 0 and price > 0:
            if price > ma5 > ma10 > ma20:
                parts.append("均线多头排列，短期趋势向上")
            elif price < ma5 < ma10 < ma20:
                parts.append("均线空头排列，短期趋势向下")
            elif ma5 > ma10 > price > ma20:
                parts.append("均线交织，短期方向待确认")
            else:
                parts.append("均线系统处于整理状态")

        # MACD状态
        macd_bar = tech_data.get('macd_bar', 0)
        macd_dif = tech_data.get('macd_dif', 0)
        macd_dea = tech_data.get('macd_dea', 0)
        if macd_dif != 0 or macd_dea != 0:
            if macd_dif > macd_dea and macd_bar > 0:
                parts.append("MACD红柱，多头动能占优")
            elif macd_dif < macd_dea and macd_bar < 0:
                parts.append("MACD绿柱，空头动能占优")
            else:
                parts.append("MACD接近零轴，方向待选择")

        # KDJ状态
        kdj_j = tech_data.get('kdj_j', 0)
        kdj_k = tech_data.get('kdj_k', 0)
        if kdj_k > 0:
            if kdj_j < 20:
                parts.append("KDJ处于低位，存在超跌反弹可能")
            elif kdj_j > 80:
                parts.append("KDJ处于高位，注意回调风险")
            else:
                parts.append("KDJ处于中性区域")

        return '，'.join(parts) if parts else "技术面中性"

    def _generate_operation_reason(self, stock_info, tech_data, chanlun_data):
        """生成操作理由"""
        current_state = chanlun_data.get('current_state', '未知')
        position = chanlun_data.get('position', '观望')
        final_score = chanlun_data.get('final_score', 0)

        reason = ""

        # 根据不同状态生成操作理由
        if '三买' in current_state or '三买启动' in current_state:
            reason = (
                f"当前处于{current_state}，日线中枢完成突破，"
                f"回踩确认后形成第三类买点，短线趋势向上。"
                f"缠论评分{final_score}分，建议{position}参与。"
            )
        elif '二买' in current_state or '底部' in current_state:
            reason = (
                f"当前处于{current_state}，下跌动能衰竭，"
                f"二次回调不创新低，第二类买点逐步确认。"
                f"缠论评分{final_score}分，建议{position}布局。"
            )
        elif '一买' in current_state or '底背驰' in current_state:
            reason = (
                f"当前处于{current_state}，底背驰信号出现，"
                f"下跌趋势可能进入尾声。"
                f"缠论评分{final_score}分，建议{position}试错。"
            )
        elif '中枢震荡' in current_state:
            if '下沿' in current_state:
                reason = (
                    f"当前处于{current_state}，价格测试中枢下沿支撑，"
                    f"可考虑低吸高抛的震荡操作。"
                    f"缠论评分{final_score}分，建议{position}。"
                )
            elif '上沿' in current_state:
                reason = (
                    f"当前处于{current_state}，价格测试中枢上沿压力，"
                    f"关注能否有效突破。"
                    f"缠论评分{final_score}分，建议{position}。"
                )
            else:
                reason = (
                    f"当前处于{current_state}，多空力量相对平衡，"
                    f"等待方向明确后再操作。"
                    f"缠论评分{final_score}分，建议{position}。"
                )
        elif '趋势延伸' in current_state or '主升' in current_state:
            reason = (
                f"当前处于{current_state}，价格远离中枢，"
                f"趋势延续但追高风险增加。"
                f"缠论评分{final_score}分，建议{position}。"
            )
        elif '顶背驰' in current_state or '顶部' in current_state:
            reason = (
                f"当前处于{current_state}，上涨动能衰竭，"
                f"顶背驰风险显现，不适合追高。"
                f"缠论评分{final_score}分，建议{position}。"
            )
        elif '回调' in current_state or '下跌' in current_state:
            reason = (
                f"当前处于{current_state}，短期调整中，"
                f"等待企稳信号。"
                f"缠论评分{final_score}分，建议{position}。"
            )
        else:
            reason = (
                f"当前状态：{current_state}。"
                f"缠论评分{final_score}分，建议{position}。"
            )

        return reason

    def _generate_short_term_strategy(self, stock_info, tech_data, chanlun_data):
        """生成短线策略"""
        strategy = {
            'buy_logic': '',
            'hold_logic': '',
            'sell_logic': '',
        }

        current_state = chanlun_data.get('current_state', '')
        zhongshu = chanlun_data.get('zhongshu', {})
        price = stock_info.get('price', 0)

        # 买入逻辑
        if '三买' in current_state:
            strategy['buy_logic'] = "回踩中枢上沿附近企稳，且成交量配合时，可考虑轻仓介入"
        elif '二买' in current_state or '底部' in current_state:
            strategy['buy_logic'] = "二次回调不创新低，且出现止跌信号时，可考虑轻仓试错"
        elif '中枢震荡' in current_state and '下沿' in current_state:
            strategy['buy_logic'] = "接近中枢下沿且出现支撑时，可考虑低吸"
        elif '趋势延伸' in current_state:
            strategy['buy_logic'] = "不建议追高，等待回调后再考虑"
        elif '顶背驰' in current_state:
            strategy['buy_logic'] = "顶背驰阶段，不建议买入"
        else:
            strategy['buy_logic'] = "等待更明确的买入信号"

        # 持仓逻辑
        if '三买' in current_state or '趋势' in current_state:
            strategy['hold_logic'] = "持有为主，跌破5日线或出现顶分型时减仓"
        elif '中枢震荡' in current_state:
            strategy['hold_logic'] = "震荡市不宜长持，高抛低吸为主"
        elif '底部' in current_state or '二买' in current_state:
            strategy['hold_logic'] = "底部区域可耐心持有，等待趋势确认"
        else:
            strategy['hold_logic'] = "根据走势灵活调整仓位"

        # 卖出逻辑
        if '三买' in current_state:
            strategy['sell_logic'] = "到达目标位或出现顶背驰信号时止盈，跌破中枢上沿止损"
        elif '二买' in current_state:
            strategy['sell_logic'] = "反弹至压力位减仓，跌破前低止损"
        elif '中枢震荡' in current_state:
            strategy['sell_logic'] = "接近中枢上沿时高抛，跌破下沿止损"
        elif '顶背驰' in current_state:
            strategy['sell_logic'] = "顶背驰阶段建议减仓或清仓，控制风险"
        else:
            strategy['sell_logic'] = "根据止损止盈纪律执行"

        return strategy

    def _generate_t_strategy(self, stock_info, tech_data, chanlun_data):
        """生成T策略判断"""
        result = {
            'suitable': False,
            'reason': '',
            'high_sell_zone': '',
            'low_buy_zone': '',
        }

        current_state = chanlun_data.get('current_state', '')
        zhongshu = chanlun_data.get('zhongshu', {})
        turnover = stock_info.get('turnover', 0)

        # 判断是否适合做T
        if '中枢震荡' in current_state:
            # 震荡市适合做T
            result['suitable'] = True
            result['reason'] = "当前处于中枢震荡阶段，波动率适中，适合高抛低吸做T"

            # 计算高抛低吸区域
            if zhongshu:
                zg = zhongshu.get('zg', 0)
                zd = zhongshu.get('zd', 0)
                if zg > 0 and zd > 0:
                    result['high_sell_zone'] = f"{zg * 0.98:.2f} - {zg * 1.01:.2f}元（中枢上沿附近）"
                    result['low_buy_zone'] = f"{zd * 0.99:.2f} - {zd * 1.02:.2f}元（中枢下沿附近）"
            else:
                result['high_sell_zone'] = "近期高点附近"
                result['low_buy_zone'] = "近期低点附近"

        elif '趋势延伸' in current_state or '三买启动' in current_state:
            # 趋势市不适合做T
            result['suitable'] = False
            result['reason'] = "当前处于趋势阶段，以持股为主，不建议频繁做T以免踏空"

        elif '底部' in current_state or '二买' in current_state:
            result['suitable'] = False
            result['reason'] = "底部区域以布局为主，耐心持有等待趋势确认"

        elif '顶背驰' in current_state:
            result['suitable'] = False
            result['reason'] = "顶背驰风险阶段，建议减仓而非做T"

        else:
            result['suitable'] = False
            result['reason'] = "当前状态不明确，建议先观望"

        return result

    def _generate_risk_warnings(self, stock_info, tech_data, chanlun_data):
        """生成风险提示"""
        risks = []

        current_state = chanlun_data.get('current_state', '')
        final_score = chanlun_data.get('final_score', 0)

        # 1. 技术风险
        ma20 = tech_data.get('ma20', 0)
        price = stock_info.get('price', 0)
        if ma20 > 0:
            if price < ma20:
                risks.append({
                    'type': '技术风险',
                    'content': f"股价已跌破20日线（{ma20:.2f}元），短期趋势走弱"
                })
            else:
                risks.append({
                    'type': '技术风险',
                    'content': f"跌破20日线（{ma20:.2f}元）需警惕短期调整"
                })

        # 2. 结构风险
        if '三买' in current_state:
            zhongshu = chanlun_data.get('zhongshu', {})
            zg = zhongshu.get('zg', 0)
            if zg > 0:
                risks.append({
                    'type': '结构风险',
                    'content': f"跌破中枢上沿（{zg:.2f}元）则三买结构失效"
                })
        elif '中枢震荡' in current_state:
            zhongshu = chanlun_data.get('zhongshu', {})
            zd = zhongshu.get('zd', 0)
            if zd > 0:
                risks.append({
                    'type': '结构风险',
                    'content': f"跌破中枢下沿（{zd:.2f}元）则震荡格局可能打破"
                })
        elif '趋势延伸' in current_state:
            risks.append({
                'type': '结构风险',
                'content': "价格远离中枢，追高风险较大，注意回调风险"
            })
        elif '顶背驰' in current_state:
            risks.append({
                'type': '结构风险',
                'content': "顶背驰信号出现，上涨动能可能衰竭"
            })
        else:
            risks.append({
                'type': '结构风险',
                'content': "结构不明确，注意控制仓位"
            })

        # 3. 行业风险
        industry = stock_info.get('industry', '')
        if industry:
            risks.append({
                'type': '行业风险',
                'content': f"需关注{industry}行业景气度变化和政策风险"
            })

        # 4. 市场风险
        risks.append({
            'type': '市场风险',
            'content': "大盘环境变化可能影响个股走势，需结合指数环境综合判断"
        })

        # 5. 评分风险提示
        if final_score < 60:
            risks.append({
                'type': '综合风险',
                'content': f"缠论综合评分{final_score}分，评分较低，建议谨慎"
            })

        return risks

    def _generate_overall_rating(self, stock_info, tech_data, chanlun_data):
        """生成综合评级"""
        final_score = chanlun_data.get('final_score', 0)
        current_state = chanlun_data.get('current_state', '')

        # 星级评级
        if final_score >= 85:
            stars = 5
            rating_text = "强烈关注"
        elif final_score >= 75:
            stars = 4
            rating_text = "重点关注"
        elif final_score >= 65:
            stars = 3
            rating_text = "适度关注"
        elif final_score >= 55:
            stars = 2
            rating_text = "观望为主"
        else:
            stars = 1
            rating_text = "暂不关注"

        return {
            'score': final_score,
            'stars': stars,
            'rating_text': rating_text,
            'current_state': current_state,
        }

    def format_report_text(self, recommendation):
        """格式化为文本报告"""
        lines = []

        # 综合评级
        rating = recommendation.get('overall_rating', {})
        stars = '★' * rating.get('stars', 0) + '☆' * (5 - rating.get('stars', 0))
        lines.append(f"【综合评级】")
        lines.append(f"  {stars} {rating.get('rating_text', '未知')}")
        lines.append(f"  缠论评分：{rating.get('score', 0)}分")
        lines.append(f"  当前状态：{rating.get('current_state', '未知')}")
        lines.append("")

        # AI推荐理由
        lines.append(f"【AI推荐理由】")
        reasons = recommendation.get('recommend_reasons', [])
        for r in reasons:
            lines.append(f"  {r.get('type', '')}：")
            lines.append(f"    {r.get('content', '')}")
        lines.append("")

        # AI操作理由
        lines.append(f"【AI操作理由】")
        lines.append(f"  {recommendation.get('operation_reason', '')}")
        lines.append("")

        # 短线策略
        lines.append(f"【短线策略】")
        strategy = recommendation.get('short_term_strategy', {})
        lines.append(f"  买入逻辑：{strategy.get('buy_logic', '')}")
        lines.append(f"  持仓逻辑：{strategy.get('hold_logic', '')}")
        lines.append(f"  卖出逻辑：{strategy.get('sell_logic', '')}")
        lines.append("")

        # T策略
        lines.append(f"【T策略】")
        t_strategy = recommendation.get('t_strategy', {})
        if t_strategy.get('suitable'):
            lines.append(f"  是否适合：是")
            lines.append(f"  原因：{t_strategy.get('reason', '')}")
            lines.append(f"  高抛区域：{t_strategy.get('high_sell_zone', '')}")
            lines.append(f"  低吸区域：{t_strategy.get('low_buy_zone', '')}")
        else:
            lines.append(f"  是否适合：否")
            lines.append(f"  原因：{t_strategy.get('reason', '')}")
        lines.append("")

        # 风险提示
        lines.append(f"【风险提示】")
        risks = recommendation.get('risk_warnings', [])
        for i, r in enumerate(risks, 1):
            lines.append(f"  {i}. {r.get('type', '')}：{r.get('content', '')}")
        lines.append("")

        lines.append("=" * 50)
        lines.append("免责声明：本报告仅供参考，不构成投资建议")
        lines.append("AI分析基于历史数据，市场有风险，投资需谨慎")
        lines.append("=" * 50)

        return "\n".join(lines)


# 单例
_recommendation_ai = None


def get_recommendation_ai():
    """获取推荐理由AI单例"""
    global _recommendation_ai
    if _recommendation_ai is None:
        _recommendation_ai = RecommendationAI()
    return _recommendation_ai
