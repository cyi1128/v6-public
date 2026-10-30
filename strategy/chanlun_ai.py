# -*- coding: utf-8 -*-
"""
AI缠论智能解释层
注意：AI只负责解释，不参与计算。
所有判断都来自chanlun_core.py的输出。
本模块只负责把结构化数据翻译成自然语言。
"""
import json
import os
from datetime import datetime


class ChanlunAI:
    """缠论AI解释器"""

    def __init__(self):
        self.report_dir = 'data/chanlun_reports'
        os.makedirs(self.report_dir, exist_ok=True)

    def generate_report(self, stock_info, multi_period_result):
        """
        生成AI缠论分析报告
        Args:
            stock_info: dict, 股票基本信息 {'name': '', 'code': '', 'price': 0, ...}
            multi_period_result: dict, 多周期缠论分析结果
        Returns:
            dict: 分析报告
        """
        periods = multi_period_result.get('periods', {})
        overall = multi_period_result.get('overall', {})

        # 1. 趋势判断
        trend_analysis = self._analyze_trend(periods)

        # 2. 缠论结构分析
        structure_analysis = self._analyze_structure(periods)

        # 3. 买卖点判断
        signal_analysis = self._analyze_signals(periods)

        # 4. 操作建议
        operation_advice = self._generate_operation_advice(periods, overall, stock_info)

        # 5. 风险控制
        risk_control = self._generate_risk_control(periods, stock_info)

        # 6. 综合评分
        ai_score, score_detail = self._calc_ai_score(periods, overall, stock_info)

        # 7. 操作评级
        rating = self._calc_rating(ai_score)

        # 组装报告
        report = {
            'stock_name': stock_info.get('name', ''),
            'stock_code': stock_info.get('code', ''),
            'current_price': stock_info.get('price', 0),
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'trend_analysis': trend_analysis,
            'structure_analysis': structure_analysis,
            'signal_analysis': signal_analysis,
            'operation_advice': operation_advice,
            'risk_control': risk_control,
            'ai_score': ai_score,
            'score_detail': score_detail,
            'rating': rating,
            'overall': overall,
        }

        # 保存报告
        self._save_report(report)

        return report

    def _analyze_trend(self, periods):
        """分析趋势（月线→周线→日线）"""
        lines = []

        # 月线
        month = periods.get('month', {})
        if month.get('status') == '分析完成':
            month_dir = month.get('direction', 'unknown')
            month_struct = month.get('structure', '')
            if month_dir == 'up':
                lines.append(f"月线级别保持上涨趋势结构，长期方向向好。")
            elif month_dir == 'down':
                lines.append(f"月线级别处于下跌趋势，长期方向偏弱。")
            else:
                lines.append(f"月线级别处于震荡整理阶段，长期方向待选择。")
        else:
            lines.append(f"月线数据不足，长期趋势待观察。")

        # 周线
        week = periods.get('week', {})
        if week.get('status') == '分析完成':
            week_dir = week.get('direction', 'unknown')
            week_zs = week.get('zhongshu')
            if week_dir == 'up':
                if week_zs:
                    lines.append(f"周线处于上涨趋势中的中枢震荡阶段，中期趋势保持向上。")
                else:
                    lines.append(f"周线处于上涨趋势中，中期方向向好。")
            elif week_dir == 'down':
                if week_zs:
                    lines.append(f"周线处于下跌趋势中的反弹阶段，中期趋势仍偏空。")
                else:
                    lines.append(f"周线处于下跌趋势中，中期方向偏弱。")
            else:
                lines.append(f"周线处于盘整阶段，中期方向待确认。")

        # 日线
        day = periods.get('day', {})
        if day.get('status') == '分析完成':
            day_dir = day.get('direction', 'unknown')
            day_zs = day.get('zhongshu')
            day_stroke = day.get('strokes', [])
            last_stroke = day_stroke[-1] if day_stroke else None

            if day_dir == 'up':
                if day_zs:
                    current_price = day.get('current_price', 0)
                    if current_price > day_zs.get('zg', 0):
                        lines.append(f"日线处于上涨趋势，已突破中枢，当前在中枢上方运行。")
                    else:
                        lines.append(f"日线处于上涨趋势中的中枢震荡，价格在中枢区间内运行。")
                else:
                    lines.append(f"日线处于上涨趋势中，短期方向向上。")
            elif day_dir == 'down':
                if day_zs:
                    current_price = day.get('current_price', 0)
                    if current_price < day_zs.get('zd', 0):
                        lines.append(f"日线处于下跌趋势，已跌破中枢，当前在中枢下方运行。")
                    else:
                        lines.append(f"日线处于下跌趋势中的反弹，价格仍在中枢区间内。")
                else:
                    lines.append(f"日线处于下跌趋势中，短期方向向下。")
            else:
                if day_zs:
                    lines.append(f"日线处于中枢震荡阶段，多空力量相对平衡。")
                else:
                    lines.append(f"日线处于盘整阶段，短期方向待选择。")

        return "\n".join(lines)

    def _analyze_structure(self, periods):
        """分析缠论结构"""
        lines = []

        day = periods.get('day', {})
        if day.get('status') != '分析完成':
            return "日线数据不足，结构分析待补充。"

        zs = day.get('zhongshu')
        strokes = day.get('strokes', [])
        segments = day.get('segments', [])
        beichi = day.get('beichi')

        # 线段
        if segments:
            last_seg = segments[-1]
            seg_dir = '上涨' if last_seg.get('direction') == 'up' else '下跌'
            lines.append(f"日线当前运行在第{len(segments)}个{seg_dir}线段中。")
        else:
            lines.append(f"日线线段结构待形成。")

        # 中枢
        if zs:
            zg = zs.get('zg', 0)
            zd = zs.get('zd', 0)
            zs_type = '上涨' if zs.get('type') == 'up' else '下跌'
            amplitude = zs.get('amplitude', 0)
            lines.append(f"当前{zs_type}中枢区间：{zd:.2f} - {zg:.2f}元，幅度{amplitude:.1f}%。")

            current_price = day.get('current_price', 0)
            if current_price > zg:
                lines.append(f"当前价格{current_price:.2f}元，位于中枢上方，属于中枢离开段。")
            elif current_price < zd:
                lines.append(f"当前价格{current_price:.2f}元，位于中枢下方，属于中枢跌破状态。")
            else:
                lines.append(f"当前价格{current_price:.2f}元，位于中枢区间内，属于中枢震荡。")
        else:
            lines.append(f"日线当前无明显中枢结构。")

        # 笔
        if strokes:
            last_stroke = strokes[-1]
            stroke_dir = '上涨' if last_stroke.get('direction') == 'up' else '下跌'
            stroke_amp = last_stroke.get('amplitude', 0)
            lines.append(f"最新一笔为{stroke_dir}笔，幅度{stroke_amp:.1f}%。")

        # 背驰
        if beichi:
            bc_type = '顶背驰' if beichi.get('type') == 'top_beichi' else '底背驰'
            bc_level = beichi.get('level', '中')
            lines.append(f"日线出现{bc_level}级别{bc_type}，注意趋势转折风险。")

        return "\n".join(lines)

    def _analyze_signals(self, periods):
        """分析买卖点"""
        lines = []

        day = periods.get('day', {})
        if day.get('status') != '分析完成':
            return "日线数据不足，买卖点分析待补充。"

        signals = day.get('signals', [])
        buy_signals = [s for s in signals if s.get('type') == 'buy']
        sell_signals = [s for s in signals if s.get('type') == 'sell']

        if not buy_signals and not sell_signals:
            lines.append("日线当前无明确买卖点信号，建议观望等待。")
        else:
            if buy_signals:
                strong_buy = [s for s in buy_signals if s.get('level') == '强']
                mid_buy = [s for s in buy_signals if s.get('level') == '中']
                weak_buy = [s for s in buy_signals if s.get('level') == '弱']

                if strong_buy:
                    names = '、'.join(s['name'] for s in strong_buy)
                    lines.append(f"【强买入信号】出现{names}，属于较高确定性的买入机会。")
                if mid_buy:
                    names = '、'.join(s['name'] for s in mid_buy)
                    lines.append(f"【中买入信号】出现{names}，可考虑逢低布局。")
                if weak_buy:
                    names = '、'.join(s['name'] for s in weak_buy)
                    lines.append(f"【弱买入信号】出现{names}，属于震荡操作机会，注意快进快出。")

            if sell_signals:
                strong_sell = [s for s in sell_signals if s.get('level') == '强']
                mid_sell = [s for s in sell_signals if s.get('level') == '中']
                weak_sell = [s for s in sell_signals if s.get('level') == '弱']

                if strong_sell:
                    names = '、'.join(s['name'] for s in strong_sell)
                    lines.append(f"【强卖出信号】出现{names}，建议减仓或离场。")
                if mid_sell:
                    names = '、'.join(s['name'] for s in mid_sell)
                    lines.append(f"【中卖出信号】出现{names}，注意控制仓位。")
                if weak_sell:
                    names = '、'.join(s['name'] for s in weak_sell)
                    lines.append(f"【弱卖出信号】出现{names}，属于震荡高抛机会。")

        # 60分钟级别确认
        hour60 = periods.get('60min', {})
        if hour60.get('status') == '分析完成':
            hour_signals = hour60.get('signals', [])
            hour_buy = [s for s in hour_signals if s.get('type') == 'buy']
            hour_sell = [s for s in hour_signals if s.get('type') == 'sell']

            if hour_buy:
                lines.append(f"60分钟级别出现买入信号，可作为日线买点的次级别确认。")
            elif hour_sell:
                lines.append(f"60分钟级别出现卖出信号，短期注意回调风险。")

        return "\n".join(lines)

    def _generate_operation_advice(self, periods, overall, stock_info):
        """生成操作建议"""
        advice = {}

        day = periods.get('day', {})
        current_price = stock_info.get('price', 0)

        # 提前获取买卖点信号（供后续判断使用）
        signals = day.get('signals', [])
        signal_names = [s.get('name', '') for s in signals]
        has_sanmai = any('三买' in name for name in signal_names)
        has_yimai = any('一买' in name for name in signal_names)
        has_ermai = any('二买' in name for name in signal_names)
        has_yimai_sell = any('一卖' in name for name in signal_names)
        has_ermai_sell = any('二卖' in name for name in signal_names)

        # 买入区域
        buy_low = 0
        buy_high = 0

        zs = day.get('zhongshu')
        if zs:
            zd = zs.get('zd', 0)
            zg = zs.get('zg', 0)

            # 计算价格距离中枢的距离
            if current_price > 0 and zg > 0:
                distance_pct = (current_price - zg) / zg * 100
            else:
                distance_pct = 0

            # 价格远离中枢（>20%）时，原中枢失效，不用来计算买入区域
            if abs(distance_pct) > 20:
                # 用最近的结构计算，但必须是近期的回调
                strokes = day.get('strokes', [])
                if strokes and len(strokes) >= 1:
                    # 找最近的回调低点
                    last_stroke = strokes[-1]
                    if last_stroke.get('direction') == 'down':
                        # 最近一笔是下跌
                        recent_low = last_stroke.get('end_price', current_price)
                        # 回调低点距离现价不能太远（15%以内才算有效回调）
                        if current_price > 0 and (current_price - recent_low) / current_price * 100 <= 15:
                            buy_low = recent_low * 0.98
                            buy_high = recent_low * 1.02
                        else:
                            # 回调太久远，原结构失效
                            buy_low = 0
                            buy_high = 0
                    else:
                        # 最近一笔是上涨，没有回调，暂无明确买入区域
                        buy_low = 0
                        buy_high = 0
                else:
                    buy_low = 0
                    buy_high = 0
            else:
                # 价格在中枢附近，用中枢计算
                if day.get('direction') == 'up':
                    # 上涨趋势：回踩中枢上沿买入
                    buy_low = zg * 0.98
                    buy_high = zg * 1.02
                elif day.get('direction') == 'down':
                    # 下跌趋势：不建议买入
                    buy_low = 0
                    buy_high = 0
                else:
                    # 震荡：中枢下沿买入
                    buy_low = zd * 0.99
                    buy_high = zd * 1.01
        else:
            # 无中枢，用最近底分型
            fractals = day.get('fractals', [])
            bottom_fractals = [f for f in fractals if f.get('type') == 'bottom']
            if bottom_fractals:
                last_bottom = bottom_fractals[-1]['price']
                # 底分型不能离现价太远
                if current_price > 0 and (current_price - last_bottom) / last_bottom * 100 <= 20:
                    buy_low = last_bottom * 0.98
                    buy_high = last_bottom * 1.03
                else:
                    buy_low = 0
                    buy_high = 0

        # 顶背驰时不输出买入区域
        if has_yimai_sell:
            buy_low = 0
            buy_high = 0

        advice['buy_zone'] = f"{buy_low:.2f} - {buy_high:.2f}元" if buy_low > 0 else "暂无明确买入区域"

        # 止损位置
        if zs and abs(distance_pct) <= 20:
            # 价格在中枢附近，用中枢下沿止损
            stop_loss = zs.get('zd', 0) * 0.97
        else:
            # 价格远离中枢，用最近低点或现价的5%止损
            strokes = day.get('strokes', [])
            if strokes:
                last_stroke = strokes[-1]
                if last_stroke.get('direction') == 'down':
                    stop_loss = last_stroke.get('end_price', current_price) * 0.97
                else:
                    stop_loss = current_price * 0.95
            else:
                stop_loss = current_price * 0.95
        advice['stop_loss'] = f"{stop_loss:.2f}元"

        # 目标位（分阶段）
        if zs and abs(distance_pct) <= 20:
            zg = zs.get('zg', 0)
            zd = zs.get('zd', 0)
            amplitude = zg - zd

            # 判断是中枢内震荡还是突破后
            if distance_pct < 0 and abs(distance_pct) < 15:
                # 价格在中枢内（震荡阶段）
                # 第一目标：中枢上沿
                first_target = zg * 0.99
                # 第二目标：突破中枢后的0.618倍幅度
                second_target = zg + amplitude * 0.618
                advice['target_stage'] = "震荡阶段，目标分两级"
            elif distance_pct >= 0 and distance_pct < 20:
                # 刚突破中枢（三买阶段）
                first_target = zg + amplitude * 0.618
                second_target = zg + amplitude
                advice['target_stage'] = "突破阶段，看中枢幅度目标"
            else:
                # 其他情况
                first_target = zg + amplitude * 0.618
                second_target = zg + amplitude
                advice['target_stage'] = "正常阶段"

            advice['first_target'] = f"{first_target:.2f}元"
            advice['second_target'] = f"{second_target:.2f}元"
        else:
            # 价格远离中枢，用现价计算目标
            advice['first_target'] = f"{current_price * 1.08:.2f}元"  # 第一目标：8%
            advice['second_target'] = f"{current_price * 1.15:.2f}元"  # 第二目标：15%
            advice['target_stage'] = "趋势阶段，看百分比目标"

        # 仓位建议（增加位置风险和涨幅风险调整）
        base_score = overall.get('overall_score', 50)

        # 1. 位置风险评分（距离中枢越远，风险越高）
        position_risk = 0
        risk_level = "低"
        if zs and zg > 0 and current_price > 0:
            distance_pct = abs((current_price - zg) / zg * 100)
            if distance_pct < 20:
                position_risk = 0
                risk_level = "低（中枢附近）"
            elif distance_pct < 40:
                position_risk = 5
                risk_level = "中低（轻度离开）"
            elif distance_pct < 60:
                position_risk = 10
                risk_level = "中高（明显离开）"
            else:
                position_risk = 20
                risk_level = "高（远离中枢）"

        # 2. 涨幅风险（最近上涨线段涨幅）
        rise_risk = 0
        recent_rise_pct = 0
        strokes = day.get('strokes', [])
        if strokes:
            # 找最近的上涨线段/笔
            for s in reversed(strokes):
                if s.get('direction') == 'up':
                    start_p = s.get('start_price', 0)
                    end_p = s.get('end_price', 0)
                    if start_p > 0:
                        recent_rise_pct = (end_p - start_p) / start_p * 100
                    break

        # 涨幅风险调整
        if recent_rise_pct > 60:
            rise_risk = 15  # 涨幅过大，禁止重仓
        elif recent_rise_pct > 30:
            rise_risk = 8  # 涨幅较大，降低仓位

        # 3. 最终评分 = 基础分 - 位置风险 - 涨幅风险
        final_score = max(0, base_score - position_risk - rise_risk)

        # 4. 仓位规则（更保守）
        if final_score >= 90:
            position = "重仓（50%-70%）"
        elif final_score >= 75:
            position = "半仓（30%-50%）"
        elif final_score >= 60:
            position = "轻仓（10%-30%）"
        else:
            position = "观望（<10%或空仓）"

        advice['position'] = position
        advice['base_score'] = base_score
        advice['final_score'] = final_score
        advice['position_risk'] = position_risk
        advice['risk_level'] = risk_level
        advice['recent_rise_pct'] = recent_rise_pct
        advice['rise_risk'] = rise_risk

        # 当前缠论状态（交易阶段判断）
        current_state = "未知"
        state_detail = ""

        # 获取最后一笔和买卖点
        last_stroke = strokes[-1] if strokes else None
        signals = day.get('signals', [])

        # 先判断买卖点（优先级最高）
        signal_names = [s.get('name', '') for s in signals]
        has_sanmai = any('三买' in name for name in signal_names)
        has_yimai = any('一买' in name for name in signal_names)
        has_ermai = any('二买' in name for name in signal_names)
        has_yimai_sell = any('一卖' in name for name in signal_names)
        has_ermai_sell = any('二卖' in name for name in signal_names)

        if zs:
            zg = zs.get('zg', 0)
            zd = zs.get('zd', 0)
            zs_type = zs.get('type', 'up')

            # 判断价格位置
            if distance_pct < -10:
                # 价格在中枢下方较远
                if zs_type == 'down':
                    current_state = "下跌中枢震荡"
                    state_detail = "价格在下跌中枢内，等待方向选择"
                else:
                    current_state = "回调阶段"
                    state_detail = "价格回调至中枢下方，观察支撑"
            elif abs(distance_pct) <= 10:
                # 价格在中枢内
                if has_sanmai:
                    # 有三买，优先显示三买状态
                    current_state = "三买启动阶段"
                    state_detail = "中枢附近回踩确认，三买形成"
                elif last_stroke and last_stroke.get('direction') == 'down':
                    current_state = "中枢震荡（下沿测试）"
                    state_detail = "价格测试中枢下沿，观察低吸机会"
                else:
                    current_state = "中枢震荡（上沿测试）"
                    state_detail = "价格测试中枢上沿，观察突破情况"
            elif distance_pct <= 30:
                # 刚突破中枢
                has_sanmai = any('三买' in s.get('name', '') for s in signals)
                if has_sanmai:
                    current_state = "三买启动阶段"
                    state_detail = "突破中枢后回踩确认，三买形成"
                else:
                    current_state = "中枢突破初期"
                    state_detail = "刚突破中枢，等待回踩确认三买"
            else:
                # 远离中枢
                current_state = "趋势延伸阶段"
                state_detail = "价格远离中枢，注意背驰风险"
        else:
            # 无中枢
            if beichi and beichi.get('type') == 'bottom_beichi':
                current_state = "底部背驰阶段"
                state_detail = "下跌动能衰竭，底背驰出现"
            elif beichi and beichi.get('type') == 'top_beichi':
                current_state = "顶部背驰阶段"
                state_detail = "上涨动能衰竭，顶背驰出现"
            else:
                current_state = "趋势运行中"
                state_detail = "无明确中枢，沿趋势运行"

        advice['current_state'] = current_state
        advice['state_detail'] = state_detail

        # 操作策略
        day_dir = day.get('direction', 'unknown')
        if day_dir == 'up':
            advice['strategy'] = "顺势做多，回踩买入，持有为主"
        elif day_dir == 'down':
            advice['strategy'] = "逆势谨慎，反弹减仓，空仓观望"
        else:
            advice['strategy'] = "震荡操作，高抛低吸，控制仓位"

        return advice

    def _generate_risk_control(self, periods, stock_info):
        """生成风险控制提示"""
        risks = []

        day = periods.get('day', {})
        current_price = stock_info.get('price', 0)

        zs = day.get('zhongshu')
        if zs:
            zd = zs.get('zd', 0)
            zg = zs.get('zg', 0)

            if current_price > zg:
                risks.append(f"1. 跌破中枢上沿{zg:.2f}元，三买结构失效，注意减仓。")
            elif current_price < zd:
                risks.append(f"1. 反弹无法重回中枢下沿{zd:.2f}元，确认三卖，及时离场。")
            else:
                risks.append(f"1. 跌破中枢下沿{zd:.2f}元，中枢震荡结束，方向选择向下。")
                risks.append(f"2. 突破中枢上沿{zg:.2f}元，中枢震荡结束，方向选择向上。")

        # 背驰风险
        beichi = day.get('beichi')
        if beichi:
            if beichi.get('type') == 'top_beichi':
                risks.append(f"3. 顶背驰出现，上涨动能衰竭，注意见顶风险。")
            else:
                risks.append(f"3. 底背驰出现，下跌动能衰竭，可能见底反弹。")

        # 周线风险
        week = periods.get('week', {})
        if week.get('direction') == 'down':
            risks.append(f"4. 周线级别处于下跌趋势，日线反弹需谨慎，大周期向下风险较大。")

        if not risks:
            risks.append("1. 当前无明显风险信号，保持分析完成风控即可。")

        return "\n".join(risks)

    def _calc_ai_score(self, periods, overall, stock_info):
        """计算AI缠论综合评分（0-100）"""
        score = 50  # 基础分
        detail = {}

        # 1. 周期共振（30分）
        consistency = overall.get('consistency_score', 50)
        resonance_score = int(consistency * 0.3)  # 0-30分
        detail['周期共振'] = resonance_score
        score += resonance_score - 15  # 基准15分

        # 2. 结构质量（30分）
        day = periods.get('day', {})
        structure_score = 15
        if day.get('zhongshu'):
            structure_score += 5  # 有中枢+5分
            zs = day['zhongshu']
            if 3 <= zs.get('amplitude', 0) <= 15:
                structure_score += 5  # 中枢幅度合理+5分
        if day.get('direction') == 'up':
            structure_score += 5
        elif day.get('direction') == 'down':
            structure_score -= 5

        structure_score = max(0, min(30, structure_score))
        detail['结构质量'] = structure_score
        score += structure_score - 15

        # 3. 买卖点（20分）
        signals = day.get('signals', [])
        signal_score = 10
        buy_signals = [s for s in signals if s.get('type') == 'buy']
        sell_signals = [s for s in signals if s.get('type') == 'sell']

        if buy_signals:
            max_level = max({'强': 3, '中': 2, '弱': 1}.get(s['level'], 0) for s in buy_signals)
            signal_score += max_level * 3
        if sell_signals:
            max_level = max({'强': 3, '中': 2, '弱': 1}.get(s['level'], 0) for s in sell_signals)
            signal_score -= max_level * 3

        signal_score = max(0, min(20, signal_score))
        detail['买卖点'] = signal_score
        score += signal_score - 10

        # 4. 技术指标（10分）
        indicator_score = 5
        # 这里可以加入MA、MACD、KDJ等指标判断
        # 暂时给中性分
        detail['技术指标'] = indicator_score

        # 5. 量价（10分）
        volume_score = 5
        # 这里可以加入成交量、换手率判断
        # 暂时给中性分
        detail['量价关系'] = volume_score

        # 总分
        score = max(0, min(100, int(score)))

        return score, detail

    def _calc_rating(self, score):
        """计算操作评级"""
        if score >= 85:
            return {
                'stars': 5,
                'text': '★★★★★ 强势关注',
                'desc': '多周期共振，结构完美，可重点参与',
            }
        elif score >= 70:
            return {
                'stars': 4,
                'text': '★★★★ 机会观察',
                'desc': '结构较好，有一定机会，可择机参与',
            }
        elif score >= 55:
            return {
                'stars': 3,
                'text': '★★★ 等待确认',
                'desc': '结构一般，等待更明确信号，观望为主',
            }
        elif score >= 40:
            return {
                'stars': 2,
                'text': '★★ 风险增加',
                'desc': '结构偏弱，风险较大，谨慎操作',
            }
        else:
            return {
                'stars': 1,
                'text': '★ 回避',
                'desc': '结构很差，风险很高，建议回避',
            }

    def _save_report(self, report):
        """保存分析报告"""
        try:
            code = report.get('stock_code', '')
            date = datetime.now().strftime('%Y%m%d')
            filename = f"{self.report_dir}/{code}_{date}.json"

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存报告失败: {e}")

    def format_report_text(self, report):
        """格式化报告为文本"""
        lines = []
        lines.append("=" * 50)
        lines.append(f"AI缠论分析报告")
        lines.append(f"股票：{report['stock_name']} ({report['stock_code']})")
        lines.append(f"当前价格：{report['current_price']:.2f}元")
        lines.append(f"分析时间：{report['analysis_time']}")
        lines.append("=" * 50)

        lines.append(f"\n【操作评级】")
        lines.append(f"  {report['rating']['text']}")
        lines.append(f"  {report['rating']['desc']}")
        lines.append(f"  AI评分：{report['ai_score']}分")

        lines.append(f"\n【一、趋势判断】")
        lines.append(f"  {report['trend_analysis']}")

        lines.append(f"\n【二、缠论结构分析】")
        lines.append(f"  {report['structure_analysis']}")

        lines.append(f"\n【三、买卖点判断】")
        lines.append(f"  {report['signal_analysis']}")

        lines.append(f"\n【四、当前状态】")
        advice = report['operation_advice']
        lines.append(f"  {advice.get('current_state', '未知')}")
        if advice.get('state_detail'):
            lines.append(f"  {advice['state_detail']}")
        if advice.get('target_stage'):
            lines.append(f"  目标阶段：{advice['target_stage']}")

        lines.append(f"\n【五、操作建议】")
        lines.append(f"  操作策略：{advice['strategy']}")
        lines.append(f"  买入区域：{advice['buy_zone']}")
        lines.append(f"  止损位置：{advice['stop_loss']}")
        lines.append(f"  第一目标：{advice['first_target']}")
        lines.append(f"  第二目标：{advice['second_target']}")
        lines.append(f"  仓位建议：{advice['position']}")

        lines.append(f"\n【六、风险控制】")
        lines.append(f"  {report['risk_control']}")

        lines.append(f"\n【评分明细】")
        for k, v in report['score_detail'].items():
            lines.append(f"  {k}: {v}分")

        lines.append("\n" + "=" * 50)
        lines.append("免责声明：本报告仅供参考，不构成投资建议")
        lines.append("=" * 50)

        return "\n".join(lines)


# 单例
_ai = None

def get_chanlun_ai():
    global _ai
    if _ai is None:
        _ai = ChanlunAI()
    return _ai
