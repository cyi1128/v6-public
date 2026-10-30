# -*- coding: utf-8 -*-
"""
AI个股投资逻辑解释模块
V1.1 新增功能

原则：
- AI只能翻译已有数据，不能编造
- 按固定模板生成，不自由发挥
- 独立层，不修改缠论核心
- 所有推荐必须有数据依据

生成内容：
1. 股票定位
2. AI推荐理由（行业/题材/业绩/资金/技术，五个维度）
3. 操作计划（买入/持仓/减仓/止盈条件）
4. T策略判断
5. 投资逻辑评分（机构风格）
6. 风险提示
"""


class AIStockReason:
    """AI个股投资逻辑解释器"""

    def __init__(self):
        pass

    def generate_report(self, stock_data):
        """
        生成完整的AI投资逻辑报告

        参数：
            stock_data: 股票数据字典
                - basic: 基本信息（name, code, price, change_pct, industry, business, concepts）
                - tech: 技术指标（ma5, ma10, ma20, macd_dif, macd_dea, macd_bar, kdj_k, kdj_d, kdj_j, volume_ratio, turnover）
                - chanlun: 缠论数据（current_state, state_detail, signals, zhongshu, final_score, position）
                - finance: 财务数据（可选，revenue, profit, profit_growth, gross_margin等）
                - fund: 资金数据（可选，main_net_inflow, super_large, large, medium, small）

        返回：
            report: 投资逻辑报告字典
        """
        report = {}

        basic = stock_data.get('basic', {})
        tech = stock_data.get('tech', {})
        chanlun = stock_data.get('chanlun', {})
        finance = stock_data.get('finance', {})
        fund = stock_data.get('fund', {})

        # 1. 股票定位
        report['stock_position'] = self._generate_stock_position(basic)

        # 2. 推荐理由（五个维度）
        report['reasons'] = self._generate_reasons(basic, tech, chanlun, finance, fund)

        # 3. 操作计划
        report['operation_plan'] = self._generate_operation_plan(basic, tech, chanlun)

        # 4. T策略判断
        report['t_strategy'] = self._generate_t_strategy(chanlun)

        # 5. 投资逻辑评分
        report['score'] = self._generate_score(basic, tech, chanlun, finance, fund)

        # 6. 风险提示
        report['risks'] = self._generate_risks(basic, tech, chanlun, finance)

        # 7. 综合结论
        report['conclusion'] = self._generate_conclusion(report['score'], chanlun)

        return report

    def _generate_stock_position(self, basic):
        """生成股票定位"""
        position = {
            'name': basic.get('name', ''),
            'code': basic.get('code', ''),
            'industry': basic.get('industry', '未知'),
            'business': basic.get('business', '暂无公开主营业务数据'),
            'concepts': basic.get('concepts', []),
            'market_position': '',
        }

        # 根据行业和概念生成市场定位
        industry = basic.get('industry', '')
        concepts = basic.get('concepts', [])
        concepts_str = '、'.join(concepts[:3]) if isinstance(concepts, list) else ''

        if industry and concepts_str:
            position['market_position'] = (
                f"公司属于{industry}行业，涉及{concepts_str}等概念。"
                f"需结合行业景气度和题材热度综合判断投资价值。"
            )
        elif industry:
            position['market_position'] = (
                f"公司属于{industry}行业。"
                f"需结合行业发展周期和公司基本面综合判断。"
            )
        else:
            position['market_position'] = "行业和概念数据待补充，暂无法准确定位。"

        return position

    def _generate_reasons(self, basic, tech, chanlun, finance, fund):
        """生成推荐理由（五个维度）"""
        reasons = []

        # 1. 行业逻辑
        industry_reason = self._generate_industry_reason(basic)
        reasons.append({'type': '行业逻辑', **industry_reason})

        # 2. 题材逻辑
        theme_reason = self._generate_theme_reason(basic)
        reasons.append({'type': '题材逻辑', **theme_reason})

        # 3. 业绩逻辑
        performance_reason = self._generate_performance_reason(finance)
        reasons.append({'type': '业绩逻辑', **performance_reason})

        # 4. 资金逻辑
        fund_reason = self._generate_fund_reason(tech, fund, basic)
        reasons.append({'type': '资金逻辑', **fund_reason})

        # 5. 技术逻辑
        tech_reason = self._generate_tech_reason(tech, chanlun)
        reasons.append({'type': '技术逻辑', **tech_reason})

        return reasons

    def _generate_industry_reason(self, basic):
        """行业逻辑"""
        industry = basic.get('industry', '')
        result = {
            'trend': '中性',
            'policy': '暂无明确政策方向数据',
            'cycle': '暂无明确产业周期数据',
            'summary': '',
        }

        if not industry:
            result['summary'] = "暂无行业分类数据，无法判断行业逻辑"
            return result

        # 行业趋势判断（基于行业名称的通用判断，不编造具体数据）
        industry_keywords = {
            '半导体': {'trend': '成长', 'cycle': '国产替代周期', 'policy': '国家战略支持'},
            '芯片': {'trend': '成长', 'cycle': '国产替代周期', 'policy': '国家战略支持'},
            '新能源': {'trend': '成长', 'cycle': '能源转型周期', 'policy': '双碳目标支持'},
            '光伏': {'trend': '成长', 'cycle': '能源转型周期', 'policy': '双碳目标支持'},
            '锂电': {'trend': '成长', 'cycle': '能源转型周期', 'policy': '双碳目标支持'},
            'AI': {'trend': '高成长', 'cycle': '技术革命周期', 'policy': '数字经济支持'},
            '人工智能': {'trend': '高成长', 'cycle': '技术革命周期', 'policy': '数字经济支持'},
            '软件': {'trend': '成长', 'cycle': '数字化转型周期', 'policy': '数字经济支持'},
            '机器人': {'trend': '成长', 'cycle': '智能制造周期', 'policy': '制造业升级支持'},
            '自动化': {'trend': '成长', 'cycle': '智能制造周期', 'policy': '制造业升级支持'},
            '医药': {'trend': '稳健', 'cycle': '人口老龄化周期', 'policy': '医疗改革'},
            '医疗': {'trend': '稳健', 'cycle': '人口老龄化周期', 'policy': '医疗改革'},
            '消费': {'trend': '稳健', 'cycle': '消费升级周期', 'policy': '扩大内需'},
            '白酒': {'trend': '稳健', 'cycle': '消费升级周期', 'policy': '扩大内需'},
            '银行': {'trend': '稳健', 'cycle': '经济周期', 'policy': '金融稳定'},
            '证券': {'trend': '周期', 'cycle': '牛市周期', 'policy': '资本市场改革'},
            '地产': {'trend': '下行', 'cycle': '调整周期', 'policy': '房住不炒'},
        }

        for keyword, info in industry_keywords.items():
            if keyword in industry:
                result['trend'] = info['trend']
                result['policy'] = info['policy']
                result['cycle'] = info['cycle']
                break

        result['summary'] = (
            f"行业趋势：{result['trend']}，"
            f"产业周期：{result['cycle']}，"
            f"政策方向：{result['policy']}。"
        )

        return result

    def _generate_theme_reason(self, basic):
        """题材逻辑"""
        concepts = basic.get('concepts', [])
        result = {
            'main_theme': '',
            'catalyst': '',
            'market_focus': '',
            'summary': '',
        }

        if not concepts or not isinstance(concepts, list) or len(concepts) == 0:
            result['summary'] = "暂无概念标签数据，无法判断题材逻辑"
            return result

        # 核心题材
        main_theme = concepts[0]
        result['main_theme'] = main_theme

        # 题材催化（通用描述，不编造具体消息）
        theme_catalysts = {
            'AI': 'AI技术革命推动相关产业链需求增长',
            '人工智能': 'AI技术革命推动相关产业链需求增长',
            '算力': '大模型训练和推理需求爆发，算力基础设施持续扩容',
            '芯片': '国产替代加速，芯片自主可控需求提升',
            '半导体': '国产替代加速，半导体产业链景气度提升',
            '机器人': '制造业智能化升级，机器人需求持续增长',
            '新能源': '双碳目标推动，新能源产业快速发展',
            '光伏': '全球能源转型，光伏装机量持续增长',
            '锂电': '新能源车渗透率提升，锂电池需求增长',
            '储能': '新能源消纳需求，储能市场快速增长',
            '医药': '人口老龄化和健康消费升级，医药需求稳定增长',
            '消费': '消费升级和内需扩大，消费板块韧性较强',
        }

        for keyword, catalyst in theme_catalysts.items():
            if any(keyword in c for c in concepts):
                result['catalyst'] = catalyst
                break

        if not result['catalyst']:
            result['catalyst'] = "暂无明确题材催化数据"

        # 市场关注度
        if len(concepts) >= 5:
            result['market_focus'] = "概念标签较多，市场关注度较高"
        elif len(concepts) >= 3:
            result['market_focus'] = "有一定概念属性，市场关注度中等"
        else:
            result['market_focus'] = "概念标签较少，市场关注度一般"

        result['summary'] = (
            f"核心题材：{result['main_theme']}。"
            f"题材催化：{result['catalyst']}。"
            f"市场关注：{result['market_focus']}。"
        )

        return result

    def _generate_performance_reason(self, finance):
        """业绩逻辑"""
        result = {
            'revenue': '暂无数据',
            'profit': '暂无数据',
            'margin': '暂无数据',
            'roe': '暂无数据',
            'scale': '未知',
            'summary': '',
            'has_data': False,
        }

        if not finance or not finance.get('has_data'):
            result['summary'] = (
                "暂无最新财务数据验证业绩改善情况。"
                "建议结合最新财报、行业景气度和公司公告综合判断。"
            )
            return result

        result['has_data'] = True

        # 营收规模
        scale = finance.get('revenue_scale', '未知')
        result['scale'] = scale

        # 营收（用规模描述，不用精确数字）
        revenue = finance.get('revenue', 0)
        if revenue > 0:
            result['revenue'] = f"{scale}企业"

        # 净利润（用规模描述）
        net_profit = finance.get('net_profit', 0)
        if net_profit > 0:
            if net_profit >= 100:
                result['profit'] = "百亿级"
            elif net_profit >= 10:
                result['profit'] = "十亿级"
            else:
                result['profit'] = "亿元级"

        # 净利率
        net_margin = finance.get('net_margin', 0)
        if net_margin > 0:
            result['margin'] = f"{net_margin:.1f}%"

        # ROE
        roe = finance.get('roe', 0)
        if roe > 0:
            result['roe'] = f"{roe:.1f}%"

        # 业绩评价（基于净利率、ROE）
        score = 0
        if net_margin > 30:
            score += 2
        elif net_margin > 15:
            score += 1

        if roe > 15:
            score += 2
        elif roe > 8:
            score += 1

        if score >= 3:
            quality = "优秀"
            desc = "盈利能力较强，基本面质量较高"
        elif score >= 2:
            quality = "良好"
            desc = "盈利能力尚可，基本面有一定支撑"
        elif score >= 1:
            quality = "一般"
            desc = "盈利能力一般，需关注业绩改善情况"
        else:
            quality = "较弱"
            desc = "盈利能力较弱，需注意业绩风险"

        result['summary'] = (
            f"公司为{scale}企业，"
            f"净利率{result['margin']}，ROE{result['roe']}。"
            f"整体盈利质量{quality}，{desc}。"
        )

        return result

    def _generate_fund_reason(self, tech, fund, basic):
        """资金逻辑"""
        result = {
            'volume_status': '',
            'turnover_status': '',
            'main_flow': '暂无主力资金数据',
            'summary': '',
        }

        volume_ratio = tech.get('volume_ratio', 0)
        turnover = tech.get('turnover', 0)
        change_pct = basic.get('change_pct', 0)

        # 成交量状态
        if volume_ratio > 2:
            result['volume_status'] = "明显放量"
        elif volume_ratio > 1.5:
            result['volume_status'] = "温和放量"
        elif volume_ratio > 0.8:
            result['volume_status'] = "量能平稳"
        else:
            result['volume_status'] = "缩量"

        # 换手率状态
        if turnover > 10:
            result['turnover_status'] = "高换手"
        elif turnover > 5:
            result['turnover_status'] = "换手活跃"
        elif turnover > 2:
            result['turnover_status'] = "换手适中"
        else:
            result['turnover_status'] = "换手较低"

        # 主力资金
        main_net = fund.get('main_net_inflow')
        if main_net is not None:
            if main_net > 0:
                result['main_flow'] = f"主力净流入{main_net/10000:.2f}万"
            else:
                result['main_flow'] = f"主力净流出{abs(main_net)/10000:.2f}万"

        # 综合判断
        if volume_ratio > 1.5 and change_pct > 0:
            fund_desc = "放量上涨，资金流入迹象明显"
        elif volume_ratio > 1.5 and change_pct < 0:
            fund_desc = "放量下跌，注意资金出逃风险"
        elif volume_ratio < 0.8 and change_pct > 0:
            fund_desc = "缩量上涨，资金参与度不高"
        elif turnover > 8:
            fund_desc = "高换手，多空分歧较大"
        else:
            fund_desc = "量能平稳，资金面相对均衡"

        result['summary'] = (
            f"成交量：{result['volume_status']}，"
            f"换手率：{result['turnover_status']}。"
            f"{fund_desc}。"
        )

        return result

    def _generate_tech_reason(self, tech, chanlun):
        """技术逻辑"""
        result = {
            'chanlun_state': '',
            'ma_status': '',
            'macd_status': '',
            'kdj_status': '',
            'summary': '',
        }

        # 缠论状态
        current_state = chanlun.get('current_state', '未知')
        state_detail = chanlun.get('state_detail', '')
        result['chanlun_state'] = current_state

        # 均线状态
        ma5 = tech.get('ma5', 0)
        ma10 = tech.get('ma10', 0)
        ma20 = tech.get('ma20', 0)
        price = tech.get('price', 0)

        if ma5 > 0 and ma10 > 0 and ma20 > 0 and price > 0:
            if price > ma5 > ma10 > ma20:
                result['ma_status'] = "多头排列"
            elif price < ma5 < ma10 < ma20:
                result['ma_status'] = "空头排列"
            else:
                result['ma_status'] = "均线交织"
        else:
            result['ma_status'] = "数据不足"

        # MACD状态
        macd_bar = tech.get('macd_bar', 0)
        macd_dif = tech.get('macd_dif', 0)
        macd_dea = tech.get('macd_dea', 0)
        if macd_dif != 0 or macd_dea != 0:
            if macd_dif > macd_dea and macd_bar > 0:
                result['macd_status'] = "红柱多头"
            elif macd_dif < macd_dea and macd_bar < 0:
                result['macd_status'] = "绿柱空头"
            else:
                result['macd_status'] = "接近零轴"
        else:
            result['macd_status'] = "数据不足"

        # KDJ状态
        kdj_j = tech.get('kdj_j', 0)
        kdj_k = tech.get('kdj_k', 0)
        if kdj_k > 0:
            if kdj_j > 80:
                result['kdj_status'] = "高位超买"
            elif kdj_j < 20:
                result['kdj_status'] = "低位超卖"
            else:
                result['kdj_status'] = "中性区域"
        else:
            result['kdj_status'] = "数据不足"

        # 综合技术判断
        tech_parts = []
        if current_state:
            tech_parts.append(f"缠论：{current_state}")
        if result['ma_status'] != "数据不足":
            tech_parts.append(f"均线：{result['ma_status']}")
        if result['macd_status'] != "数据不足":
            tech_parts.append(f"MACD：{result['macd_status']}")
        if result['kdj_status'] != "数据不足":
            tech_parts.append(f"KDJ：{result['kdj_status']}")

        result['summary'] = (
            '，'.join(tech_parts) + '。'
            if tech_parts else "技术面数据不足。"
        )

        # 增加风险提示
        if '三买' in current_state or '趋势' in current_state:
            result['summary'] += " 技术结构偏多，但需注意追高风险。"
        elif '顶背驰' in current_state or '顶部' in current_state:
            result['summary'] += " 技术结构偏空，注意调整风险。"
        elif '震荡' in current_state:
            result['summary'] += " 技术面中性，等待方向选择。"
        elif '底部' in current_state or '二买' in current_state:
            result['summary'] += " 技术结构逐步转多，可关注企稳信号。"

        return result

    def _generate_operation_plan(self, basic, tech, chanlun):
        """生成操作计划（条件式，不直接说买卖）"""
        plan = {
            'buy_condition': '',
            'hold_condition': '',
            'reduce_condition': '',
            'take_profit_condition': '',
        }

        current_state = chanlun.get('current_state', '')
        zhongshu = chanlun.get('zhongshu', {})
        ma5 = tech.get('ma5', 0)
        zg = zhongshu.get('zg', 0) if zhongshu else 0
        zd = zhongshu.get('zd', 0) if zhongshu else 0

        # 买入条件
        if '三买' in current_state:
            plan['buy_condition'] = (
                f"回踩中枢上沿（约{zg:.2f}元）附近企稳，"
                f"且成交量保持活跃，可考虑轻仓介入。"
                if zg > 0 else
                "回踩关键支撑位企稳，且量能配合，可考虑轻仓试错。"
            )
        elif '二买' in current_state or '底部' in current_state:
            plan['buy_condition'] = (
                "二次回调不创新低，且出现止跌信号（底分型/量能萎缩），"
                "可考虑轻仓布局。"
            )
        elif '中枢震荡' in current_state and '下沿' in current_state:
            plan['buy_condition'] = (
                f"接近中枢下沿（约{zd:.2f}元）且出现支撑，"
                f"可考虑低吸，快进快出。"
                if zd > 0 else
                "接近震荡区间下沿且企稳，可考虑低吸。"
            )
        elif '趋势延伸' in current_state:
            plan['buy_condition'] = (
                "不建议追高，等待回调至关键支撑位再考虑。"
            )
        elif '顶背驰' in current_state:
            plan['buy_condition'] = (
                "顶背驰阶段，不建议买入，等待调整充分后再看。"
            )
        else:
            plan['buy_condition'] = (
                "等待更明确的买入信号，不急操作。"
            )

        # 持仓条件
        if '三买' in current_state or '趋势' in current_state:
            plan['hold_condition'] = (
                f"保持在5日线（约{ma5:.2f}元）上方，"
                f"且缠论上涨笔未结束，可继续持有。"
                if ma5 > 0 else
                "上涨趋势未破坏，可继续持有。"
            )
        elif '中枢震荡' in current_state:
            plan['hold_condition'] = (
                "震荡市不宜长持，高抛低吸为主，控制仓位。"
            )
        elif '底部' in current_state or '二买' in current_state:
            plan['hold_condition'] = (
                "底部区域可耐心持有，等待趋势确认，设好止损。"
            )
        else:
            plan['hold_condition'] = (
                "根据走势灵活调整，严格执行止损纪律。"
            )

        # 减仓条件
        if '三买' in current_state:
            plan['reduce_condition'] = (
                f"跌破中枢上沿（约{zg:.2f}元），三买结构失效，"
                f"建议减仓或止损。"
                if zg > 0 else
                "跌破关键支撑位，结构破坏，建议减仓。"
            )
        elif '中枢震荡' in current_state:
            plan['reduce_condition'] = (
                f"跌破中枢下沿（约{zd:.2f}元），震荡格局打破，"
                f"建议减仓观望。"
                if zd > 0 else
                "跌破震荡区间下沿，建议减仓。"
            )
        elif '趋势延伸' in current_state:
            plan['reduce_condition'] = (
                "出现顶分型或MACD死叉，短期调整信号出现，可减仓锁定利润。"
            )
        elif '顶背驰' in current_state:
            plan['reduce_condition'] = (
                "顶背驰信号确认，建议逐步减仓，控制风险。"
            )
        else:
            plan['reduce_condition'] = (
                "跌破关键支撑位或走势不及预期，建议减仓。"
            )

        # 止盈条件
        if '三买' in current_state:
            plan['take_profit_condition'] = (
                "到达目标位或出现顶背驰信号，可考虑分批止盈。"
            )
        elif '中枢震荡' in current_state:
            plan['take_profit_condition'] = (
                f"接近中枢上沿（约{zg:.2f}元）可考虑高抛，"
                f"不恋战。"
                if zg > 0 else
                "接近震荡区间上沿可考虑高抛。"
            )
        elif '趋势延伸' in current_state:
            plan['take_profit_condition'] = (
                "趋势股可持有跟随，出现明确见顶信号再止盈。"
            )
        elif '底部' in current_state or '二买' in current_state:
            plan['take_profit_condition'] = (
                "反弹至重要压力位可分批止盈，或持有等待趋势确认。"
            )
        else:
            plan['take_profit_condition'] = (
                "根据个人盈利目标和风险承受能力，制定止盈计划。"
            )

        return plan

    def _generate_t_strategy(self, chanlun):
        """T策略判断"""
        result = {
            'suitable': False,
            'reason': '',
            'high_zone': '',
            'low_zone': '',
        }

        current_state = chanlun.get('current_state', '')
        zhongshu = chanlun.get('zhongshu', {})

        if '中枢震荡' in current_state:
            result['suitable'] = True
            result['reason'] = (
                "当前处于中枢震荡阶段，价格在区间内波动，"
                "适合高抛低吸做T降低成本。"
            )
            if zhongshu:
                zg = zhongshu.get('zg', 0)
                zd = zhongshu.get('zd', 0)
                if zg > 0 and zd > 0:
                    result['high_zone'] = f"{zg * 0.98:.2f} - {zg * 1.01:.2f}元（中枢上沿附近）"
                    result['low_zone'] = f"{zd * 0.99:.2f} - {zd * 1.02:.2f}元（中枢下沿附近）"
        elif '三买' in current_state or '趋势' in current_state:
            result['suitable'] = False
            result['reason'] = (
                "当前处于趋势阶段，以持股为主，"
                "不建议频繁做T以免踏空主升浪。"
            )
        elif '底部' in current_state or '二买' in current_state:
            result['suitable'] = False
            result['reason'] = (
                "底部区域以布局为主，耐心持有等待趋势确认，"
                "做T容易丢失筹码。"
            )
        elif '顶背驰' in current_state or '顶部' in current_state:
            result['suitable'] = False
            result['reason'] = (
                "顶背驰风险阶段，建议减仓而非做T，"
                "优先控制风险。"
            )
        else:
            result['suitable'] = False
            result['reason'] = "当前状态不明确，建议先观望。"

        return result

    def _generate_score(self, basic, tech, chanlun, finance, fund):
        """投资逻辑评分（机构风格，各20分）"""
        score = {
            'industry': 10,  # 行业（默认中性）
            'theme': 10,     # 题材（默认中性）
            'performance': 10,  # 业绩（默认中性，无数据给中等）
            'fund': 10,      # 资金（默认中性）
            'tech': 10,      # 技术（默认中性）
            'total': 50,
            'rating': '中性',
        }

        # 行业评分
        industry = basic.get('industry', '')
        industry_scores = {
            'AI': 18, '人工智能': 18, '算力': 18,
            '半导体': 16, '芯片': 16,
            '新能源': 15, '光伏': 15, '锂电': 15, '储能': 15,
            '机器人': 16, '自动化': 15,
            '医药': 12, '医疗': 12,
            '消费': 12, '白酒': 12,
            '银行': 10, '证券': 10,
            '地产': 6,
        }
        for keyword, s in industry_scores.items():
            if keyword in industry:
                score['industry'] = s
                break

        # 题材评分
        concepts = basic.get('concepts', [])
        if isinstance(concepts, list):
            if len(concepts) >= 8:
                score['theme'] = 18
            elif len(concepts) >= 5:
                score['theme'] = 15
            elif len(concepts) >= 3:
                score['theme'] = 12
            else:
                score['theme'] = 8

        # 业绩评分（主要基于净利率，ROE作为辅助参考）
        if finance and finance.get('has_data'):
            perf_score = 0
            net_margin = finance.get('net_margin', 0)
            roe = finance.get('roe', 0)

            # 净利率（15分，主要指标，比值准确）
            if net_margin > 40:
                perf_score += 15
            elif net_margin > 25:
                perf_score += 12
            elif net_margin > 15:
                perf_score += 9
            elif net_margin > 8:
                perf_score += 6
            elif net_margin > 3:
                perf_score += 3
            else:
                perf_score += 1

            # ROE（5分，辅助指标，绝对值有偏差，只做相对参考）
            if roe > 80:
                perf_score += 5
            elif roe > 50:
                perf_score += 4
            elif roe > 20:
                perf_score += 3
            elif roe > 10:
                perf_score += 2
            else:
                perf_score += 1

            score['performance'] = min(20, perf_score)
        else:
            score['performance'] = 10  # 无数据给中性分

        # 资金评分
        volume_ratio = tech.get('volume_ratio', 1)
        change_pct = basic.get('change_pct', 0)
        if volume_ratio > 2 and change_pct > 0:
            score['fund'] = 17
        elif volume_ratio > 1.5 and change_pct > 0:
            score['fund'] = 14
        elif volume_ratio > 0.8:
            score['fund'] = 11
        else:
            score['fund'] = 8

        # 技术评分（基于缠论评分换算，拉开差距）
        chanlun_score = chanlun.get('final_score', 50)
        # 技术分换算：缠论20分→0分，缠论80分→20分，让技术分差距更明显
        tech_score = max(0, min(20, int((chanlun_score - 20) / 60 * 20)))
        score['tech'] = tech_score

        # 总分
        total = score['industry'] + score['theme'] + score['performance'] + score['fund'] + score['tech']
        score['total'] = total

        # 评级
        if total >= 60:
            score['rating'] = '重点关注'
        elif total >= 52:
            score['rating'] = '适度关注'
        elif total >= 45:
            score['rating'] = '中性观望'
        else:
            score['rating'] = '谨慎回避'

        return score

    def _generate_risks(self, basic, tech, chanlun, finance):
        """风险提示"""
        risks = []

        current_state = chanlun.get('current_state', '')
        ma20 = tech.get('ma20', 0)
        zhongshu = chanlun.get('zhongshu', {})

        # 1. 技术风险
        if ma20 > 0:
            price = tech.get('price', 0)
            if price < ma20:
                risks.append({
                    'type': '技术风险',
                    'level': '中',
                    'content': f"股价已跌破20日线（{ma20:.2f}元），短期趋势走弱，需警惕进一步调整。"
                })
            else:
                risks.append({
                    'type': '技术风险',
                    'level': '低',
                    'content': f"目前在20日线（{ma20:.2f}元）上方，短期趋势尚可，跌破需警惕。"
                })
        else:
            risks.append({
                'type': '技术风险',
                'level': '未知',
                'content': "技术指标数据不足，无法准确判断技术风险。"
            })

        # 2. 结构风险
        if '三买' in current_state and zhongshu:
            zg = zhongshu.get('zg', 0)
            if zg > 0:
                risks.append({
                    'type': '结构风险',
                    'level': '中',
                    'content': f"跌破中枢上沿（{zg:.2f}元）则三买结构失效，需止损。"
                })
        elif '中枢震荡' in current_state and zhongshu:
            zd = zhongshu.get('zd', 0)
            if zd > 0:
                risks.append({
                    'type': '结构风险',
                    'level': '中',
                    'content': f"跌破中枢下沿（{zd:.2f}元）则震荡格局打破，方向可能向下。"
                })
        elif '趋势延伸' in current_state:
            risks.append({
                'type': '结构风险',
                'level': '高',
                'content': "价格远离中枢，追高风险较大，注意回调风险，不宜重仓。"
            })
        elif '顶背驰' in current_state:
            risks.append({
                'type': '结构风险',
                'level': '高',
                'content': "顶背驰信号出现，上涨动能可能衰竭，注意调整风险。"
            })
        else:
            risks.append({
                'type': '结构风险',
                'level': '中',
                'content': "缠论结构不明确，注意控制仓位，等待方向清晰。"
            })

        # 3. 业绩风险
        if not finance or not finance.get('has_data'):
            risks.append({
                'type': '业绩风险',
                'level': '未知',
                'content': "暂无最新财务数据验证，业绩改善存在不确定性，需关注公司公告。"
            })
        else:
            roe = finance.get('roe', 0)
            net_margin = finance.get('net_margin', 0)

            if roe < 5 or net_margin < 5:
                risks.append({
                    'type': '业绩风险',
                    'level': '中高',
                    'content': "盈利能力较弱，需警惕业绩下滑风险。"
                })
            elif roe < 10 or net_margin < 10:
                risks.append({
                    'type': '业绩风险',
                    'level': '中',
                    'content': "盈利能力一般，需关注业绩改善情况。"
                })
            else:
                risks.append({
                    'type': '业绩风险',
                    'level': '低',
                    'content': "盈利能力较强，基本面有一定支撑。"
                })

        # 4. 行业风险
        industry = basic.get('industry', '')
        if industry:
            risks.append({
                'type': '行业风险',
                'level': '中',
                'content': f"需关注{industry}行业景气度变化、政策调整和竞争加剧风险。"
            })
        else:
            risks.append({
                'type': '行业风险',
                'level': '未知',
                'content': "行业数据不足，无法准确判断行业风险。"
            })

        # 5. 市场风险
        risks.append({
            'type': '市场风险',
            'level': '中',
            'content': "大盘环境、市场情绪和资金面变化可能影响个股走势，需结合指数综合判断。"
        })

        return risks

    def _generate_conclusion(self, score, chanlun):
        """综合结论"""
        total = score.get('total', 50)
        rating = score.get('rating', '中性')
        current_state = chanlun.get('current_state', '未知')

        conclusion = {
            'rating': rating,
            'total_score': total,
            'summary': '',
        }

        if total >= 80:
            conclusion['summary'] = (
                f"综合评分{total}分，{rating}。"
                f"当前处于{current_state}，投资逻辑较清晰，"
                f"可重点关注，按交易计划执行。"
            )
        elif total >= 70:
            conclusion['summary'] = (
                f"综合评分{total}分，{rating}。"
                f"当前处于{current_state}，有一定投资逻辑，"
                f"可适度关注，控制仓位参与。"
            )
        elif total >= 55:
            conclusion['summary'] = (
                f"综合评分{total}分，{rating}。"
                f"当前处于{current_state}，投资逻辑一般，"
                f"建议观望为主，等待更明确信号。"
            )
        else:
            conclusion['summary'] = (
                f"综合评分{total}分，{rating}。"
                f"当前处于{current_state}，投资逻辑偏弱，"
                f"建议谨慎回避，注意风险控制。"
            )

        return conclusion

    def format_report_text(self, report):
        """格式化为文本报告"""
        lines = []

        # 综合评级
        score = report.get('score', {})
        total = score.get('total', 0)
        rating = score.get('rating', '中性')

        lines.append("=" * 60)
        lines.append("AI个股投资逻辑报告")
        lines.append("=" * 60)
        lines.append("")

        # 股票定位
        pos = report.get('stock_position', {})
        lines.append("【一、股票定位】")
        lines.append(f"  股票：{pos.get('name', '')}（{pos.get('code', '')}）")
        lines.append(f"  行业：{pos.get('industry', '未知')}")
        lines.append(f"  主营业务：{pos.get('business', '暂无数据')}")
        concepts = pos.get('concepts', [])
        if isinstance(concepts, list) and concepts:
            lines.append(f"  核心概念：{'、'.join(concepts[:5])}")
        lines.append(f"  市场定位：{pos.get('market_position', '')}")
        lines.append("")

        # 推荐理由
        lines.append("【二、AI推荐理由】")
        reasons = report.get('reasons', [])
        for i, r in enumerate(reasons, 1):
            lines.append(f"  {i}. {r.get('type', '')}")
            lines.append(f"     {r.get('summary', '')}")
        lines.append("")

        # 操作计划
        lines.append("【三、操作计划】")
        plan = report.get('operation_plan', {})
        lines.append(f"  买入条件：{plan.get('buy_condition', '')}")
        lines.append(f"  持仓条件：{plan.get('hold_condition', '')}")
        lines.append(f"  减仓条件：{plan.get('reduce_condition', '')}")
        lines.append(f"  止盈条件：{plan.get('take_profit_condition', '')}")
        lines.append("")

        # T策略
        lines.append("【四、T策略判断】")
        t = report.get('t_strategy', {})
        if t.get('suitable'):
            lines.append(f"  是否适合做T：是")
            lines.append(f"  原因：{t.get('reason', '')}")
            if t.get('high_zone'):
                lines.append(f"  高抛区域：{t.get('high_zone', '')}")
            if t.get('low_zone'):
                lines.append(f"  低吸区域：{t.get('low_zone', '')}")
        else:
            lines.append(f"  是否适合做T：否")
            lines.append(f"  原因：{t.get('reason', '')}")
        lines.append("")

        # 投资逻辑评分
        lines.append("【五、投资逻辑评分】")
        lines.append(f"  行业逻辑：{score.get('industry', 0)}/20分")
        lines.append(f"  题材逻辑：{score.get('theme', 0)}/20分")
        lines.append(f"  业绩逻辑：{score.get('performance', 0)}/20分")
        lines.append(f"  资金逻辑：{score.get('fund', 0)}/20分")
        lines.append(f"  技术逻辑：{score.get('tech', 0)}/20分")
        lines.append(f"  综合评分：{total}/100分")
        lines.append(f"  投资评级：{rating}")
        lines.append("")

        # 风险提示
        lines.append("【六、风险提示】")
        risks = report.get('risks', [])
        for i, r in enumerate(risks, 1):
            level = r.get('level', '')
            level_mark = f"[{level}]" if level else ""
            lines.append(f"  {i}. {r.get('type', '')}{level_mark}：{r.get('content', '')}")
        lines.append("")

        # 综合结论
        conclusion = report.get('conclusion', {})
        lines.append("【七、综合结论】")
        lines.append(f"  {conclusion.get('summary', '')}")
        lines.append("")

        lines.append("=" * 60)
        lines.append("免责声明：")
        lines.append("  本报告由AI基于公开数据生成，仅供参考，不构成投资建议。")
        lines.append("  AI只做数据整理和逻辑翻译，不确保完全准确。")
        lines.append("  投资有风险，入市需谨慎，请独立判断和决策。")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_ai_stock_reason = None


def get_ai_stock_reason():
    """获取AI投资逻辑单例"""
    global _ai_stock_reason
    if _ai_stock_reason is None:
        _ai_stock_reason = AIStockReason()
    return _ai_stock_reason
