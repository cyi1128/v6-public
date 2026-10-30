# -*- coding: utf-8 -*-
"""
AI买入信号引擎
V1.1-3.2.1 第一阶段：基础信号

定位：自动扫描"可能产生行情的催化因素"，给缠论买点提供外部驱动
不是替代缠论买点，而是增强。

关系：
催化出现 + 技术结构成立 + 风险允许 = 高质量交易机会

第一阶段信号：
1. 涨停异动信号
2. 资金异动信号
3. 财务超预期信号

原则：
- 独立模块，不融合
- 不修改缠论核心
- 不修改风险模型
- 不修改投资逻辑和市场催化
- 只增加展示和解释层
"""


class AIBuySignalEngine:
    """AI买入信号引擎"""

    # V0.6.1 动态权重开关（默认关闭，兼容旧模式）
    DYNAMIC_WEIGHT_ENABLED = False

    def __init__(self):
        self._weight_adapter = None  # 懒加载

    def _get_weight_adapter(self):
        """懒加载权重适配器"""
        if self._weight_adapter is None:
            try:
                from strategy.weight_adapter import get_weight_adapter
                self._weight_adapter = get_weight_adapter(enable=self.DYNAMIC_WEIGHT_ENABLED)
            except Exception:
                self._weight_adapter = None
        return self._weight_adapter

    def generate_report(self, stock_data):
        """
        生成买入信号分析报告

        参数：
            stock_data: 股票数据字典

        返回：
            report: 信号分析报告字典
        """
        report = {
            'signals': [],  # 命中的信号列表
            'hard_signals': [],  # 硬信号
            'soft_signals': [],  # 软信号
            'event_signals': [],  # 事件信号（B1/B2等）
            'score': 0,
            'max_score': 100,
            'rating': '',
            'direction': '',
            'trigger_conditions': {
                'catalyst_ok': False,
                'structure_ok': False,
                'risk_ok': False,
            },
            'summary': '',
        }

        # 1. 检测基础信号（第一阶段三个信号）
        self._detect_limit_up_signal(stock_data, report)
        self._detect_capital_signal(stock_data, report)
        self._detect_finance_signal(stock_data, report)
        self._detect_announcement_signal(stock_data, report)  # 公告软信号

        # 2. 检测事件信号（第二阶段硬信号）
        self._detect_event_signals(stock_data, report)

        # 3. 计算基础分
        base_score = 0
        for signal in report['signals']:
            base_score += signal.get('score', 0)

        # 3.5 事件信号最高贡献限制（防止单事件推太高）
        event_total = sum(s.get('score', 0) for s in report.get('event_signals', []))
        max_event_score = 40  # 事件信号最高贡献40分
        if event_total > max_event_score:
            # 按比例压缩
            ratio = max_event_score / event_total
            for signal in report['event_signals']:
                signal['score'] = int(signal['score'] * ratio)
            # 重新计算基础分
            base_score = sum(s.get('score', 0) for s in report['signals'])

        # 4. 多信号叠加加分
        signal_count = len(report['signals'])
        if signal_count >= 4:
            base_score += 30
        elif signal_count >= 3:
            base_score += 15
        elif signal_count >= 2:
            base_score += 5

        # 5. 事件共振加分
        event_count = len(report['event_signals'])
        if event_count >= 2:
            base_score += 10
        elif event_count >= 1:
            base_score += 5

        # 6. 风险扣分（基于缠论状态）
        chanlun = stock_data.get('chanlun', {})
        state = chanlun.get('current_state', '')
        risk_deduction = 0

        # 高位/顶部状态扣分
        if '顶背驰' in state or '顶部' in state or '趋势延伸' in state:
            risk_deduction = 20
            report['trigger_conditions']['structure_ok'] = False
        elif '下跌' in state or '底部背驰' in state:
            risk_deduction = 5
            report['trigger_conditions']['structure_ok'] = True
        else:
            report['trigger_conditions']['structure_ok'] = True

        # 7. 最终评分
        final_score = base_score - risk_deduction
        final_score = max(0, min(100, final_score))
        report['score'] = final_score
        report['original_score'] = final_score  # V0.6.1 保存原始评分

        # 7.5 V0.6.1 动态权重调整（AI学习反馈接入）
        report['dynamic_weight_info'] = None
        if self.DYNAMIC_WEIGHT_ENABLED:
            try:
                adapter = self._get_weight_adapter()
                if adapter is not None and adapter.enable:
                    # 用主要信号名称作为策略名（取第一个硬信号或事件信号）
                    raw_signal_name = 'AI综合评分'
                    if report.get('event_signals'):
                        raw_signal_name = report['event_signals'][0].get('name', 'AI综合评分')
                    elif report.get('hard_signals'):
                        raw_signal_name = report['hard_signals'][0].get('name', 'AI综合评分')
                    elif report.get('signals'):
                        raw_signal_name = report['signals'][0].get('name', 'AI综合评分')

                    weight_result = adapter.adjust_score(raw_signal_name, final_score)
                    report['dynamic_weight_info'] = weight_result

                    if weight_result['enabled']:
                        report['score'] = weight_result['adjusted_score']
                        final_score = weight_result['adjusted_score']

                    # V0.6.1.1 增强日志：显示映射策略、历史胜率、权重
                    mapped_strategy = weight_result.get('strategy', raw_signal_name)
                    print(f"[AI学习增强] {stock_data.get('code', '?')} "
                          f"信号:{raw_signal_name} "
                          f"映射:{mapped_strategy} "
                          f"历史:{weight_result['sample']}次 "
                          f"胜率:{weight_result['win_rate']}% "
                          f"权重:{weight_result['weight']} "
                          f"评分:{weight_result['original_score']}→{weight_result['adjusted_score']}"
                          f"{' [已生效]' if weight_result['enabled'] else ' [未生效]'}")
            except Exception as e:
                print(f"[V0.6.1动态权重] 调整异常: {e}")

        # 8. 评级（R2标准）
        if final_score >= 80:
            report['rating'] = '强烈关注'
            report['direction'] = '📈 重点关注'
        elif final_score >= 75:
            report['rating'] = '适度关注'
            report['direction'] = '📈 买入关注'
        elif final_score >= 50:
            report['rating'] = '观察'
            report['direction'] = '👀 等待观察'
        else:
            report['rating'] = '暂无明显信号'
            report['direction'] = '⏸️ 暂无信号'

        # 9. 事件共振分析（新增策略层，不修改已有评分）
        try:
            from strategy.event_resonance import get_event_resonance_analyzer
            resonance_analyzer = get_event_resonance_analyzer()
            resonance_result = resonance_analyzer.analyze_resonance(report['event_signals'])
            report['resonance'] = resonance_result
        except Exception as e:
            report['resonance'] = {
                'has_resonance': False,
                'resonance_name': '单事件',
                'confidence': '普通',
                'detail': f'共振分析暂不可用: {str(e)}',
            }

        # 9. 催化评分是否达标
        report['trigger_conditions']['catalyst_ok'] = final_score >= 40

        # 10. 风险是否允许（暂时都算允许，后续接入风险模型）
        report['trigger_conditions']['risk_ok'] = True

        # 11. 生成总结
        report['summary'] = self._generate_summary(report, state)

        return report

    def _detect_limit_up_signal(self, stock_data, report):
        """检测涨停异动信号"""
        basic = stock_data.get('basic', {})
        concepts = basic.get('concepts', [])
        fund = stock_data.get('fund', {})
        vol_ratio = fund.get('volume_ratio', 1)

        # 基于概念数量和量比判断异动可能性
        concept_count = len(concepts)
        signal_strength = 0
        signal_desc = ''

        if concept_count >= 6 and vol_ratio > 1.5:
            signal_strength = 20
            # 全部列出概念
            concept_text = '、'.join(concepts)
            signal_desc = f"核心概念：{concept_text}（共{concept_count}个），量比{vol_ratio:.2f}，资金活跃度高，存在异动可能"
        elif concept_count >= 4 and vol_ratio > 1.2:
            signal_strength = 15
            concept_text = '、'.join(concepts)
            signal_desc = f"核心概念：{concept_text}（共{concept_count}个），量比{vol_ratio:.2f}，有一定异动基础"
        elif concept_count >= 3:
            signal_strength = 10
            concept_text = '、'.join(concepts)
            signal_desc = f"核心概念：{concept_text}（共{concept_count}个），题材属性尚可"
        else:
            signal_strength = 5
            signal_desc = "概念数量较少，题材属性一般"

        signal = {
            'type': '涨停异动',
            'category': 'hard',
            'name': '涨停异动信号',
            'icon': '📊',
            'score': signal_strength,
            'strength': '★' * min(5, signal_strength // 4 + 1),
            'description': signal_desc,
            'detail': f"核心概念{concept_count}个，量比{vol_ratio:.2f}",
        }

        report['signals'].append(signal)
        report['hard_signals'].append(signal)

    def _detect_capital_signal(self, stock_data, report):
        """检测资金异动信号"""
        fund = stock_data.get('fund', {})
        tech = stock_data.get('tech', {})

        vol_ratio = fund.get('volume_ratio', 1)
        turnover = fund.get('turnover', 3)
        amount = fund.get('amount', 0)

        signal_strength = 0
        signal_desc = ''

        # 综合判断资金强度
        score = 0
        if vol_ratio > 2:
            score += 3
        elif vol_ratio > 1.5:
            score += 2
        elif vol_ratio > 1.2:
            score += 1

        if turnover > 8:
            score += 3
        elif turnover > 5:
            score += 2
        elif turnover > 2:
            score += 1

        if amount > 50:
            score += 3
        elif amount > 10:
            score += 2
        elif amount > 1:
            score += 1

        if score >= 7:
            signal_strength = 25
            signal_desc = "资金大幅流入，成交量显著放大，关注度快速提升"
        elif score >= 5:
            signal_strength = 20
            signal_desc = "资金明显流入，成交量放大，关注度提升"
        elif score >= 3:
            signal_strength = 15
            signal_desc = "资金温和流入，成交量有所放大"
        else:
            signal_strength = 10
            signal_desc = "资金流入不明显，成交量平稳"

        signal = {
            'type': '资金异动',
            'category': 'hard',
            'name': '资金异动信号',
            'icon': '💰',
            'score': signal_strength,
            'strength': '★' * min(5, score),
            'description': signal_desc,
            'detail': f"量比{vol_ratio:.2f}，换手{turnover:.2f}%，成交{amount:.2f}亿",
        }

        report['signals'].append(signal)
        report['hard_signals'].append(signal)

    def _detect_finance_signal(self, stock_data, report):
        """检测财务超预期信号"""
        finance = stock_data.get('finance', {})

        if not finance or not finance.get('has_data'):
            signal = {
                'type': '财务信号',
                'category': 'soft',
                'name': '财务数据待验证',
                'icon': '📈',
                'score': 5,
                'strength': '★☆☆☆☆',
                'description': '暂无完整财务数据验证业绩超预期',
                'detail': '后续接入财报数据后可自动检测',
            }
            report['signals'].append(signal)
            report['soft_signals'].append(signal)
            return

        net_margin = finance.get('net_margin', 0)
        roe = finance.get('roe', 0)
        revenue_scale = finance.get('revenue_scale', '')

        signal_strength = 0
        signal_desc = ''

        # 基于盈利能力判断
        score = 0
        if net_margin > 30:
            score += 3
        elif net_margin > 20:
            score += 2
        elif net_margin > 10:
            score += 1

        if roe > 20:
            score += 3
        elif roe > 15:
            score += 2
        elif roe > 10:
            score += 1

        if revenue_scale == '超大型' or revenue_scale == '大型':
            score += 2
        elif revenue_scale == '中大型':
            score += 1

        if score >= 6:
            signal_strength = 20
            signal_desc = "盈利能力优秀，业绩质量高，基本面支撑强"
        elif score >= 4:
            signal_strength = 15
            signal_desc = "盈利能力良好，业绩有一定支撑"
        elif score >= 2:
            signal_strength = 10
            signal_desc = "盈利能力一般，业绩支撑一般"
        else:
            signal_strength = 5
            signal_desc = "盈利能力较弱，需关注业绩风险"

        signal = {
            'type': '财务质量',
            'category': 'soft',
            'name': '财务质量信号',
            'icon': '📊',
            'score': signal_strength,
            'strength': '★' * min(5, score),
            'description': signal_desc,
            'detail': f"净利率{net_margin:.1f}%，ROE {roe:.1f}%，营收规模：{revenue_scale}",
        }

        report['signals'].append(signal)
        report['soft_signals'].append(signal)

    def _detect_announcement_signal(self, stock_data, report):
        """检测公告软信号"""
        try:
            basic = stock_data.get('basic', {})
            code = basic.get('code', '')

            if not code:
                return

            # 调用公告数据提供器
            from data.announcement_provider import get_announcement_provider
            announcement_provider = get_announcement_provider()

            announcements = announcement_provider.get_announcements(code, count=30)

            if not announcements:
                signal = {
                    'type': '公告信号',
                    'category': 'soft',
                    'name': '公告数据待获取',
                    'icon': '📋',
                    'score': 3,
                    'strength': '★☆☆☆☆',
                    'description': '暂无最新公告数据',
                    'detail': '后续接入更多公告数据源',
                }
                report['signals'].append(signal)
                report['soft_signals'].append(signal)
                return

            # 筛选重要公告
            important_keywords = [
                '合同', '订单', '合作', '战略合作', '框架协议',
                '中标', '签约', '重大合同', '业务合作',
                '增持', '回购', '业绩预告', '业绩快报',
                '重组', '并购', '资产注入',
            ]

            important_announcements = []
            for ann in announcements:
                title = ann.get('title', '')
                for keyword in important_keywords:
                    if keyword in title:
                        important_announcements.append(ann)
                        break

            if not important_announcements:
                signal = {
                    'type': '公告信号',
                    'category': 'soft',
                    'name': '公告信号',
                    'icon': '📋',
                    'score': 5,
                    'strength': '★☆☆☆☆',
                    'description': f'近期{len(announcements)}条公告中无重大利好公告',
                    'detail': '暂无合同/合作/增持等重要公告',
                }
                report['signals'].append(signal)
                report['soft_signals'].append(signal)
                return

            # 根据重要公告数量判断强度
            ann_count = len(important_announcements)

            if ann_count >= 5:
                signal_strength = 15
                strength_stars = '★★★☆☆'
                signal_desc = f"近期有{ann_count}条重要公告，事件催化较强"
            elif ann_count >= 3:
                signal_strength = 10
                strength_stars = '★★☆☆☆'
                signal_desc = f"近期有{ann_count}条重要公告，有一定事件催化"
            elif ann_count >= 2:
                signal_strength = 7
                strength_stars = '★★☆☆☆'
                signal_desc = f"近期有{ann_count}条重要公告，需关注后续进展"
            else:
                signal_strength = 5
                strength_stars = '★☆☆☆☆'
                signal_desc = f"近期有1条重要公告，影响有限"

            # 生成详情
            detail_lines = []
            for ann in important_announcements[:3]:
                title = ann.get('title', '')
                date = ann.get('date', '')
                if len(title) > 30:
                    title = title[:30] + "..."
                detail_lines.append(f"[{date}] {title}")

            if len(important_announcements) > 3:
                detail_lines.append(f"... 等共{ann_count}条重要公告")

            signal = {
                'type': '公告信号',
                'category': 'soft',
                'name': '公告催化信号',
                'icon': '📋',
                'score': signal_strength,
                'strength': strength_stars,
                'description': signal_desc,
                'detail': "\n".join(detail_lines),
            }

            report['signals'].append(signal)
            report['soft_signals'].append(signal)

        except Exception as e:
            signal = {
                'type': '公告信号',
                'category': 'soft',
                'name': '公告数据获取失败',
                'icon': '⚠️',
                'score': 0,
                'strength': '☆☆☆☆☆',
                'description': f'公告数据获取失败: {str(e)}',
                'detail': '不影响其他信号分析',
            }
            report['signals'].append(signal)
            report['soft_signals'].append(signal)

    def _detect_event_signals(self, stock_data, report):
        """检测事件信号（第二阶段硬信号）"""
        try:
            from data.event_data_provider import get_event_data_provider
            event_provider = get_event_data_provider()

            code = stock_data.get('basic', {}).get('code', '')
            if not code:
                return

            events = event_provider.get_all_events(code)

            # B1 大额订单信号
            order_signal = events.get('order_signal', {})
            if order_signal.get('has_data') and order_signal.get('status'):
                signal = {
                    'type': '大额订单',
                    'category': 'event',
                    'name': 'B1大额订单催化',
                    'icon': '📢',
                    'score': order_signal.get('score', 0),
                    'strength': '★★★★★' if order_signal.get('level') == 'S' else '★★★★',
                    'description': order_signal.get('title', ''),
                    'detail': order_signal.get('detail', ''),
                }
                report['signals'].append(signal)
                report['event_signals'].append(signal)
                report['hard_signals'].append(signal)
            else:
                # 暂无数据，不加入信号列表，只在详情中说明
                pass

            # B2 业绩超预期信号
            profit_signal = events.get('profit_signal', {})
            if profit_signal.get('has_data') and profit_signal.get('status'):
                signal = {
                    'type': '业绩超预期',
                    'category': 'event',
                    'name': 'B2业绩超预期催化',
                    'icon': '📈',
                    'score': profit_signal.get('score', 0),
                    'strength': '★★★★★',
                    'description': profit_signal.get('level', ''),
                    'detail': profit_signal.get('detail', ''),
                }
                report['signals'].append(signal)
                report['event_signals'].append(signal)
                report['hard_signals'].append(signal)

            # B3 大股东增持信号
            increase_signal = events.get('increase_signal', {})
            if increase_signal.get('has_data') and increase_signal.get('status'):
                signal = {
                    'type': '股东增持',
                    'category': 'event',
                    'name': 'B3大股东增持催化',
                    'icon': '💎',
                    'score': increase_signal.get('score', 0),
                    'strength': '★★★★' if increase_signal.get('level') in ['S', 'A'] else '★★★',
                    'description': increase_signal.get('holder_type', ''),
                    'detail': increase_signal.get('detail', ''),
                }
                report['signals'].append(signal)
                report['event_signals'].append(signal)
                report['hard_signals'].append(signal)

            # B4 注销式回购信号
            buyback_signal = events.get('buyback_signal', {})
            if buyback_signal.get('has_data') and buyback_signal.get('status'):
                signal = {
                    'type': '注销回购',
                    'category': 'event',
                    'name': 'B4注销式回购催化',
                    'icon': '🔄',
                    'score': buyback_signal.get('score', 0),
                    'strength': '★★★★' if buyback_signal.get('level') in ['S', 'A'] else '★★★',
                    'description': '注销式回购',
                    'detail': buyback_signal.get('detail', ''),
                }
                report['signals'].append(signal)
                report['event_signals'].append(signal)
                report['hard_signals'].append(signal)

            # B6 重组并购信号
            restructure_signal = events.get('restructure_signal', {})
            if restructure_signal.get('has_data') and restructure_signal.get('status'):
                signal = {
                    'type': '重组并购',
                    'category': 'event',
                    'name': 'B6重组并购催化',
                    'icon': '🏗️',
                    'score': restructure_signal.get('score', 0),
                    'strength': '★★★★★' if restructure_signal.get('level') == 'S' else '★★★★',
                    'description': '重大资产重组',
                    'detail': restructure_signal.get('detail', ''),
                }
                report['signals'].append(signal)
                report['event_signals'].append(signal)
                report['hard_signals'].append(signal)
            else:
                # 暂无数据，不加入信号列表
                pass

        except ImportError:
            # 事件数据模块不存在，跳过
            pass
        except Exception as e:
            print(f"[买入信号引擎] 事件信号检测失败: {e}")

    def _generate_summary(self, report, chanlun_state):
        """生成总结"""
        lines = []

        lines.append(f"综合评分：{report['score']}分")
        lines.append(f"信号评级：{report['rating']}")
        lines.append(f"操作方向：{report['direction']}")
        lines.append("")

        # 命中的核心信号
        lines.append(f"命中信号：{len(report['signals'])}个")
        for i, signal in enumerate(report['signals'][:5], 1):
            lines.append(f"  {i}. {signal['icon']} {signal['name']} +{signal['score']}分")
        lines.append("")

        # 触发条件检查
        lines.append("触发条件检查：")
        tc = report['trigger_conditions']
        lines.append(f"  催化评分：{'✅ 达标' if tc['catalyst_ok'] else '❌ 不足'}")
        lines.append(f"  技术结构：{'✅ 支持' if tc['structure_ok'] else '❌ 不支持'}")
        lines.append(f"  风险控制：{'✅ 允许' if tc['risk_ok'] else '❌ 不允许'}")
        lines.append("")

        # 结论
        if tc['catalyst_ok'] and tc['structure_ok'] and tc['risk_ok']:
            lines.append("结论：催化、结构、风险三条件满足，可重点关注")
        elif tc['catalyst_ok'] and not tc['structure_ok']:
            lines.append("结论：有催化，但技术结构不支持，等待观察")
        elif not tc['catalyst_ok'] and tc['structure_ok']:
            lines.append("结论：技术结构可以，但催化不足，等待催化")
        else:
            lines.append("结论：暂无明显交易信号，继续观察")

        return "\n".join(lines)

    def format_report_text(self, report):
        """格式化报告为文本"""
        lines = []
        lines.append("=" * 60)
        lines.append("🚀 AI买入信号扫描")
        lines.append("=" * 60)

        # 综合评分
        lines.append("")
        lines.append("【综合评分】")
        lines.append(f"  信号评分：{report['score']} / 100")
        lines.append(f"  信号评级：{report['rating']}")
        lines.append(f"  操作方向：{report['direction']}")
        
        # 评分构成简要说明
        base_count = len([s for s in report['signals'] if s.get('category') != 'event'])
        event_count = len(report.get('event_signals', []))
        event_total = sum(s.get('score', 0) for s in report.get('event_signals', []))
        base_total = report['score'] - event_total
        
        lines.append("")
        lines.append("【评分构成】")
        lines.append(f"  基础信号：{base_total}分（{base_count}个信号）")
        if event_count > 0:
            lines.append(f"  事件催化：{event_total}分（{event_count}个事件）")
        else:
            lines.append(f"  事件催化：暂无重大事件信号")
        lines.append("")
        
        # 事件共振分析
        resonance = report.get('resonance', {})
        if resonance.get('has_resonance'):
            lines.append("【事件共振】")
            lines.append(f"  共振等级：{resonance.get('resonance_name', '')}")
            lines.append(f"  信号可信度：{resonance.get('confidence', '')}")
            if resonance.get('classic_combos'):
                lines.append(f"  经典组合：")
                for combo in resonance['classic_combos']:
                    lines.append(f"    ✅ {combo['name']} - {combo['description']}")
            lines.append(f"  {resonance.get('detail', '')}")
            lines.append("")

        # 核心信号
        lines.append("【核心信号】")
        for i, signal in enumerate(report['signals'], 1):
            lines.append(f"  {i}. {signal['icon']} {signal['name']}  +{signal['score']}分")
            lines.append(f"     强度：{signal['strength']}")
            lines.append(f"     {signal['description']}")
            lines.append(f"     {signal['detail']}")
            lines.append("")

        # 事件信号说明（如果没有事件数据）
        event_count = len(report.get('event_signals', []))
        if event_count == 0:
            lines.append("【公司事件信号】")
            lines.append("  📋 暂无重大事件信号（公告数据已接入）")
            lines.append("  （大额订单、业绩超预期、增持回购等信号）")
            lines.append("")

        # 触发条件
        lines.append("【触发条件检查】")
        tc = report['trigger_conditions']
        lines.append(f"  催化评分 ≥40：{'✅ 达标' if tc['catalyst_ok'] else '❌ 不足'}")
        lines.append(f"  技术结构支持：{'✅ 支持' if tc['structure_ok'] else '❌ 不支持'}")
        lines.append(f"  风险控制允许：{'✅ 允许' if tc['risk_ok'] else '❌ 不允许'}")
        lines.append("")

        # 详细说明
        lines.append("【信号说明】")

        # 动态显示硬信号
        hard_signals = report.get('hard_signals', [])
        if hard_signals:
            hard_names = "、".join([s.get('name', '').replace('信号', '') for s in hard_signals[:5]])
            lines.append(f"  硬信号：{hard_names}")
        else:
            lines.append("  硬信号：暂无")

        # 动态显示软信号
        soft_signals = report.get('soft_signals', [])
        if soft_signals:
            soft_names = "、".join([s.get('name', '').replace('信号', '') for s in soft_signals[:5]])
            lines.append(f"  软信号：{soft_names}")
        else:
            lines.append("  软信号：暂无")

        lines.append("")

        # 结论
        lines.append("【结论】")
        if tc['catalyst_ok'] and tc['structure_ok'] and tc['risk_ok']:
            lines.append("  催化、结构、风险三条件满足，可重点关注")
        elif tc['catalyst_ok'] and not tc['structure_ok']:
            lines.append("  有催化，但技术结构不支持，等待观察")
        elif not tc['catalyst_ok'] and tc['structure_ok']:
            lines.append("  技术结构可以，但催化不足，等待催化")
        else:
            lines.append("  暂无明显交易信号，继续观察")
        lines.append("")

        lines.append("=" * 60)
        lines.append("⚠️ 免责声明")
        lines.append("  本报告基于公开数据和技术指标分析，仅供参考。")
        lines.append("  不构成投资建议，市场有风险，投资需谨慎。")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_signal_engine = None


def get_buy_signal_engine():
    """获取买入信号引擎单例"""
    global _signal_engine
    if _signal_engine is None:
        _signal_engine = AIBuySignalEngine()
    return _signal_engine
