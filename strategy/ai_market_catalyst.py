# -*- coding: utf-8 -*-
"""
AI市场催化分析模块
V1.1-3.1 新增

定位：判断"为什么现在市场可能炒它"

与AI投资逻辑的关系：
- AI投资逻辑：为什么值得研究（公司价值）
- AI市场催化：为什么现在可能炒（市场热点）
- 缠论结构：什么时候买卖（技术位置）

原则：
- 独立模块，不融合
- 不修改缠论核心
- 不修改风险模型
- 只增加展示和解释层
- 没有数据明确显示暂无，不编造
"""


class AIMarketCatalyst:
    """AI市场催化分析器"""

    def __init__(self):
        pass

    def generate_report(self, stock_data):
        """
        生成市场催化分析报告

        参数：
            stock_data: 股票数据字典（与AI投资逻辑共用数据格式）

        返回：
            report: 市场催化分析报告字典
        """
        report = {
            'policy': self._analyze_policy(stock_data),
            'cooperation': self._analyze_cooperation(stock_data),
            'limit_up': self._analyze_limit_up(stock_data),
            'capital': self._analyze_capital(stock_data),
            'stage': self._analyze_stage(stock_data),
            'score': self._calc_score(stock_data),
            'summary': '',
        }

        # 生成总结
        report['summary'] = self._generate_summary(report)

        return report

    def _analyze_policy(self, stock_data):
        """政策催化分析"""
        result = {
            'has_data': False,
            'policy_direction': '',
            'impact_level': 0,
            'impact_stars': '☆☆☆☆☆',
            'summary': '',
        }

        basic = stock_data.get('basic', {})
        industry = basic.get('industry', '')
        concepts = basic.get('concepts', [])

        if not industry and not concepts:
            result['summary'] = "暂无政策数据，建议结合最新政策公告综合判断。"
            return result

        result['has_data'] = True

        # 基于行业和概念推断政策方向
        policy_keywords = {
            '人工智能': '国家大力支持人工智能产业发展，算力基础设施建设持续推进',
            'AI': 'AI产业政策持续加码，大模型应用加速落地',
            '算力': '算力网络建设纳入新基建，政策支持力度大',
            '芯片': '半导体国产替代政策持续推进，自主可控是长期方向',
            '半导体': '芯片产业政策支持力度大，国产替代加速',
            '新能源': '双碳目标下新能源产业政策持续支持',
            '光伏': '光伏装机目标上调，行业政策利好不断',
            '储能': '新型储能政策密集出台，行业进入快速发展期',
            '锂电': '新能源汽车产业政策支持，动力电池需求增长',
            '机器人': '机器人产业政策持续加码，人形机器人加速发展',
            '军工': '国防建设持续推进，军工行业政策支持稳定',
            '医药': '医药创新政策支持，医疗新基建持续推进',
            '创新药': '创新药审评审批加速，政策支持医药创新',
            '消费': '促消费政策持续发力，内需复苏是主线',
            '白酒': '消费升级大趋势，品牌消费持续受益',
            '汽车': '新能源汽车下乡政策，汽车消费持续支持',
            '新能源车': '新能源汽车产业政策持续支持',
            '数字经济': '数字经济政策持续推进，产业数字化加速',
            '信创': '信创产业政策支持，国产替代加速推进',
            '国企改革': '国企改革深化提升，央企估值重塑',
            '一带一路': '一带一路倡议持续推进，国际合作深化',
            '乡村振兴': '乡村振兴战略全面推进，农业农村现代化',
        }

        # 匹配政策关键词
        matched_policies = []
        for concept in concepts:
            for keyword, desc in policy_keywords.items():
                if keyword in concept:
                    matched_policies.append(desc)
                    break

        if matched_policies:
            result['policy_direction'] = matched_policies[0]
            result['impact_level'] = min(5, len(matched_policies) + 2)
        elif industry:
            result['policy_direction'] = f"{industry.split('-')[-1] if '-' in industry else industry}行业政策整体稳定"
            result['impact_level'] = 2
        else:
            result['policy_direction'] = '暂无明确政策催化'
            result['impact_level'] = 1

        # 星级
        result['impact_stars'] = '★' * result['impact_level'] + '☆' * (5 - result['impact_level'])

        result['summary'] = (
            f"政策方向：{result['policy_direction']}\n"
            f"政策影响：{result['impact_stars']}（{result['impact_level']}/5）\n"
            f"（注：基于行业和概念推断，仅供参考，需结合最新政策公告验证）"
        )

        return result

    def _analyze_cooperation(self, stock_data):
        """合作订单催化分析"""
        result = {
            'has_data': False,
            'cooperation_list': [],
            'impact_level': 0,
            'impact_stars': '☆☆☆☆☆',
            'summary': '',
        }

        try:
            # 获取股票代码
            basic = stock_data.get('basic', {})
            code = basic.get('code', '')

            if not code:
                result['summary'] = "暂无股票代码，无法获取公告数据。"
                return result

            # 调用公告数据提供器
            from data.announcement_provider import get_announcement_provider
            announcement_provider = get_announcement_provider()

            announcements = announcement_provider.get_announcements(code, count=30)

            if not announcements:
                result['summary'] = (
                    "暂无最新公司公告数据。\n"
                    "建议关注：\n"
                    "  - 公司公告（战略合作、重大合同）\n"
                    "  - 大客户订单情况\n"
                    "  - 业务进展和产能扩张\n"
                    "  - 行业展会和产品发布"
                )
                return result

            # 筛选合作/订单/合同相关公告
            cooperation_keywords = [
                '合同', '订单', '合作', '战略合作', '框架协议',
                '中标', '签约', '采购', '销售合同', '重大合同',
                '业务合作', '项目合作', '联合', '协议',
            ]

            cooperation_announcements = []
            for ann in announcements:
                title = ann.get('title', '')
                # 检查是否包含合作相关关键词
                for keyword in cooperation_keywords:
                    if keyword in title:
                        cooperation_announcements.append(ann)
                        break

            if not cooperation_announcements:
                result['has_data'] = True
                result['impact_level'] = 1
                result['impact_stars'] = '★☆☆☆☆'
                result['summary'] = (
                    f"近30条公告中未发现明显合作订单类公告。\n"
                    f"（已获取{len(announcements)}条公告，暂无重大合同/战略合作信息）"
                )
                return result

            # 分析合作公告的影响程度
            result['has_data'] = True
            result['cooperation_list'] = cooperation_announcements[:5]  # 最多显示5条

            # 根据合作公告数量和类型判断影响
            coop_count = len(cooperation_announcements)

            if coop_count >= 5:
                impact_level = 4
                impact_stars = '★★★★☆'
                impact_desc = "合作订单密集，业务拓展活跃"
            elif coop_count >= 3:
                impact_level = 3
                impact_stars = '★★★☆☆'
                impact_desc = "有一定合作订单，业务稳步推进"
            elif coop_count >= 2:
                impact_level = 2
                impact_stars = '★★☆☆☆'
                impact_desc = "有少量合作订单，需关注后续进展"
            else:
                impact_level = 1
                impact_stars = '★☆☆☆☆'
                impact_desc = "有个别合作公告，影响有限"

            result['impact_level'] = impact_level
            result['impact_stars'] = impact_stars

            # 生成总结
            summary_lines = []
            summary_lines.append(f"近期发现{coop_count}条合作订单相关公告：")
            summary_lines.append("")

            for i, ann in enumerate(cooperation_announcements[:3]):
                title = ann.get('title', '')
                date = ann.get('date', '')
                if len(title) > 40:
                    title = title[:40] + "..."
                summary_lines.append(f"  {i+1}. [{date}] {title}")

            if len(cooperation_announcements) > 3:
                summary_lines.append(f"  ... 等共{coop_count}条相关公告")

            summary_lines.append("")
            summary_lines.append(f"影响程度：{impact_desc}")

            result['summary'] = "\n".join(summary_lines)

        except Exception as e:
            result['summary'] = (
                f"公告数据获取失败：{str(e)}\n"
                "建议关注公司官方公告信息。"
            )

        return result

    def _analyze_limit_up(self, stock_data):
        """涨停异动分析"""
        result = {
            'has_data': False,
            'limit_up_count_1y': 0,
            'last_limit_up_date': '',
            'last_limit_up_reason': '',
            'persistence': '未知',
            'summary': '',
        }

        # 目前没有历史涨停数据，用概念和资金数据推断
        basic = stock_data.get('basic', {})
        concepts = basic.get('concepts', [])
        fund = stock_data.get('fund', {})
        vol_ratio = fund.get('volume_ratio', 1)
        turnover = fund.get('turnover', 3)

        result['has_data'] = True

        # 基于概念数量和资金活跃度推断异动可能性
        concept_count = len(concepts)
        if concept_count >= 6 and vol_ratio > 1.5:
            activity_level = '高'
            persistence = '较强'
        elif concept_count >= 4 and vol_ratio > 1.2:
            activity_level = '中'
            persistence = '中等'
        else:
            activity_level = '低'
            persistence = '较弱'

        result['persistence'] = persistence

        result['summary'] = (
            f"概念数量：{concept_count}个核心概念\n"
            f"资金活跃度：{activity_level}（量比{vol_ratio:.2f}，换手{turnover:.1f}%）\n"
            f"异动持续性：{persistence}\n"
            f"（注：历史涨停数据待接入，当前基于概念和资金活跃度推断）"
        )

        return result

    def _analyze_capital(self, stock_data):
        """资金异动分析"""
        result = {
            'has_data': True,
            'volume_ratio': 0,
            'turnover': 0,
            'amount': 0,
            'capital_score': 0,
            'summary': '',
        }

        fund = stock_data.get('fund', {})
        tech = stock_data.get('tech', {})

        vol_ratio = fund.get('volume_ratio', 1)
        turnover = fund.get('turnover', 3)
        amount = fund.get('amount', 0)

        result['volume_ratio'] = vol_ratio
        result['turnover'] = turnover
        result['amount'] = amount

        # 资金评分
        score = 0
        if vol_ratio > 1.5:
            score += 4
        elif vol_ratio > 1.2:
            score += 3
        elif vol_ratio > 1.0:
            score += 2
        elif vol_ratio > 0.8:
            score += 1

        if turnover > 5:
            score += 3
        elif turnover > 2:
            score += 2
        elif turnover > 0.5:
            score += 1

        if amount > 50:
            score += 3
        elif amount > 10:
            score += 2
        elif amount > 1:
            score += 1

        result['capital_score'] = min(100, score * 10)

        # 资金行为描述
        if vol_ratio > 2 and turnover > 8:
            behavior = "成交量显著放大，资金关注度大幅提升，需关注资金持续性"
        elif vol_ratio > 1.5 and turnover > 5:
            behavior = "成交量明显放大，资金关注度提升，有资金进场迹象"
        elif vol_ratio > 1.2:
            behavior = "成交量温和放大，资金关注度有所提升"
        elif vol_ratio > 0.8:
            behavior = "成交量基本平稳，资金关注度稳定"
        else:
            behavior = "成交量萎缩，资金关注度较低"

        result['summary'] = (
            f"量比：{vol_ratio:.2f}\n"
            f"换手率：{turnover:.2f}%\n"
            f"成交额：{amount:.2f}亿\n"
            f"资金评分：{result['capital_score']}分\n"
            f"资金行为：{behavior}"
        )

        return result

    def _analyze_stage(self, stock_data):
        """题材炒作阶段判断"""
        result = {
            'stage': '未知',
            'stage_desc': '',
            'confidence': 0,
            'summary': '',
        }

        fund = stock_data.get('fund', {})
        tech = stock_data.get('tech', {})
        chanlun = stock_data.get('chanlun', {})

        vol_ratio = fund.get('volume_ratio', 1)
        turnover = fund.get('turnover', 3)
        state = chanlun.get('current_state', '')

        # 判断炒作阶段
        # 启动阶段：低位、量开始放大、概念开始发酵
        # 发酵阶段：量持续放大、价格上涨、关注度提升
        # 加速阶段：量价齐升、连续上涨、情绪高涨
        # 分歧阶段：高位震荡、量放大但涨不动、多空分歧
        # 退潮阶段：量缩价跌、资金离场、情绪降温

        if '底部' in state or '下跌' in state:
            if vol_ratio > 1.2:
                stage = '启动阶段'
                stage_desc = "题材处于启动初期，资金开始关注，后续需观察持续性"
                confidence = 60
            else:
                stage = '酝酿阶段'
                stage_desc = "题材尚未明显启动，资金关注度较低，需等待催化"
                confidence = 50
        elif '三买' in state or '突破' in state:
            if vol_ratio > 2 and turnover > 8:
                stage = '加速阶段'
                stage_desc = "题材处于加速阶段，资金关注度高，情绪高涨，注意追高风险"
                confidence = 70
            elif vol_ratio > 1.5:
                stage = '发酵阶段'
                stage_desc = "题材处于发酵阶段，资金持续流入，关注度逐步提升"
                confidence = 75
            else:
                stage = '启动阶段'
                stage_desc = "题材刚启动，资金开始关注，后续空间需观察"
                confidence = 65
        elif '趋势延伸' in state or '顶部' in state:
            if vol_ratio > 2:
                stage = '高位分歧'
                stage_desc = "题材处于高位分歧阶段，多空博弈激烈，注意风险"
                confidence = 70
            else:
                stage = '加速末期'
                stage_desc = "题材处于加速末期，随时可能进入分歧，注意止盈"
                confidence = 65
        elif '震荡' in state:
            if vol_ratio > 1.5:
                stage = '发酵阶段'
                stage_desc = "题材震荡整理，资金关注度尚可，等待方向选择"
                confidence = 60
            else:
                stage = '震荡蓄势'
                stage_desc = "题材震荡蓄势，资金关注度一般，需等待催化"
                confidence = 55
        else:
            stage = '观察阶段'
            stage_desc = "题材阶段不明确，建议持续观察"
            confidence = 40

        result['stage'] = stage
        result['stage_desc'] = stage_desc
        result['confidence'] = confidence

        result['summary'] = (
            f"当前阶段：{stage}\n"
            f"判断依据：{stage_desc}\n"
            f"置信度：{confidence}%\n"
            f"（注：基于技术形态和资金数据推断，仅供参考）"
        )

        return result

    def _calc_score(self, stock_data):
        """计算市场催化综合评分"""
        score = {
            'policy': 0,
            'cooperation': 0,
            'limit_up': 0,
            'capital': 0,
            'stage': 0,
            'total': 0,
            'rating': '',
        }

        # 政策催化（20分）
        policy = self._analyze_policy(stock_data)
        score['policy'] = policy['impact_level'] * 4  # 5级×4=20分

        # 合作订单（20分）- 暂无数据，给基础分
        score['cooperation'] = 8  # 暂无数据，给8分基础分

        # 涨停异动（20分）
        limit_up = self._analyze_limit_up(stock_data)
        concepts = stock_data.get('basic', {}).get('concepts', [])
        concept_count = len(concepts)
        if concept_count >= 8:
            score['limit_up'] = 18
        elif concept_count >= 6:
            score['limit_up'] = 15
        elif concept_count >= 4:
            score['limit_up'] = 12
        else:
            score['limit_up'] = 8

        # 资金异动（20分）
        capital = self._analyze_capital(stock_data)
        score['capital'] = int(capital['capital_score'] / 5)  # 100分→20分

        # 题材阶段（20分）
        stage = self._analyze_stage(stock_data)
        stage_scores = {
            '加速阶段': 18,
            '发酵阶段': 16,
            '启动阶段': 14,
            '高位分歧': 10,
            '加速末期': 12,
            '震荡蓄势': 10,
            '酝酿阶段': 8,
            '观察阶段': 10,
            '未知': 10,
        }
        score['stage'] = stage_scores.get(stage['stage'], 10)

        # 总分
        total = score['policy'] + score['cooperation'] + score['limit_up'] + score['capital'] + score['stage']
        score['total'] = min(100, total)

        # 评级
        if total >= 80:
            score['rating'] = '催化强烈'
        elif total >= 65:
            score['rating'] = '催化明显'
        elif total >= 50:
            score['rating'] = '催化一般'
        else:
            score['rating'] = '催化较弱'

        return score

    def _generate_summary(self, report):
        """生成总结"""
        score = report['score']
        stage = report['stage']['stage']

        summary_parts = []
        summary_parts.append(f"市场催化评级：{score['rating']}（{score['total']}分）")
        summary_parts.append(f"当前题材阶段：{stage}")
        summary_parts.append("")
        summary_parts.append("催化维度：")
        summary_parts.append(f"  政策催化：{report['policy']['impact_stars']}")
        summary_parts.append(f"  资金异动：{report['capital']['capital_score']}分")
        summary_parts.append(f"  概念数量：{len(report.get('limit_up', {}).get('summary', '').split('概念数量：'))}")

        return "\n".join(summary_parts)

    def format_report_text(self, report):
        """格式化报告为文本"""
        lines = []
        lines.append("=" * 60)
        lines.append("🔥 AI市场催化分析报告")
        lines.append("=" * 60)

        # 一、政策催化
        lines.append("")
        lines.append("【一、政策催化】")
        policy = report['policy']
        if policy['has_data']:
            lines.append(f"  政策方向：{policy['policy_direction']}")
            lines.append(f"  影响等级：{policy['impact_stars']}")
        else:
            lines.append("  暂无政策数据")
        lines.append("")

        # 二、合作订单
        lines.append("【二、合作订单催化】")
        coop = report['cooperation']
        if coop['has_data']:
            for item in coop.get('cooperation_list', []):
                lines.append(f"  - {item}")
        else:
            lines.append("  暂无最新公告和订单数据")
            lines.append("  （后续将接入公司公告接口）")
        lines.append("")

        # 三、涨停异动
        lines.append("【三、涨停异动分析】")
        limit_up = report['limit_up']
        if limit_up['has_data']:
            lines.append(f"  异动持续性：{limit_up['persistence']}")
        else:
            lines.append("  暂无历史涨停数据")
        lines.append("")

        # 四、资金异动
        lines.append("【四、资金异动分析】")
        capital = report['capital']
        lines.append(f"  量比：{capital['volume_ratio']:.2f}")
        lines.append(f"  换手率：{capital['turnover']:.2f}%")
        lines.append(f"  成交额：{capital['amount']:.2f}亿")
        lines.append(f"  资金评分：{capital['capital_score']}分")
        lines.append("")

        # 五、题材阶段
        lines.append("【五、题材炒作阶段】")
        stage = report['stage']
        lines.append(f"  当前阶段：{stage['stage']}")
        lines.append(f"  阶段说明：{stage['stage_desc']}")
        lines.append(f"  判断置信度：{stage['confidence']}%")
        lines.append("")

        # 综合评分
        lines.append("【六、市场催化综合评分】")
        score = report['score']
        lines.append(f"  政策催化：{score['policy']}/20")
        lines.append(f"  合作订单：{score['cooperation']}/20")
        lines.append(f"  涨停异动：{score['limit_up']}/20")
        lines.append(f"  资金异动：{score['capital']}/20")
        lines.append(f"  题材阶段：{score['stage']}/20")
        lines.append(f"  ─────────────")
        lines.append(f"  综合评分：{score['total']}/100")
        lines.append(f"  催化评级：{score['rating']}")
        lines.append("")

        lines.append("=" * 60)
        lines.append("⚠️ 免责声明")
        lines.append("  本报告基于公开数据和技术指标分析，仅供参考。")
        lines.append("  市场有风险，投资需谨慎。")
        lines.append("=" * 60)

        return "\n".join(lines)


# 单例
_catalyst_ai = None


def get_market_catalyst_ai():
    """获取市场催化分析器单例"""
    global _catalyst_ai
    if _catalyst_ai is None:
        _catalyst_ai = AIMarketCatalyst()
    return _catalyst_ai
