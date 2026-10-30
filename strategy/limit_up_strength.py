# -*- coding: utf-8 -*-
"""
涨停强度分析器
V1.3-A-2 新增

定位：
基于V1.3-A-1涨停基础数据，分析涨停质量，输出独立的涨停强度评分。

原则：
- 只读取limit_up_data_provider的数据，不重新计算涨停事实
- 输出独立的limit_up_strength_score，不接入AI评分
- 不修改R2评级、B1-B6事件、缠论、多周期共振、综合确认
- 独立模块，可删除，不影响任何现有冻结模块

评分维度（100分制）：
1. 封单强度   30% - 封单比例为核心，考虑流通市值匹配
2. 首封时间   25% - 越早封板越强
3. 换手质量   20% - 5%-15%最佳，过高过低都有风险
4. 成交量     15% - 量比为核心
5. 连板高度   10% - 描述情绪高度，不代表买入
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class LimitUpStrengthAnalyzer:
    """涨停强度分析器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 评分权重
        self.weights = {
            'seal': 30,      # 封单强度
            'time': 25,      # 首封时间
            'turnover': 20,  # 换手质量
            'volume': 15,    # 成交量
            'chain': 10,     # 连板高度
        }

        print("[LimitUpStrength] 涨停强度分析器初始化完成")

    def analyze(self, limit_up_data):
        """
        分析涨停强度

        参数：
            limit_up_data: V1.3-A-1的涨停数据字典

        返回：
            dict: 涨停强度分析结果
                {
                    'limit_up_strength_score': 85,  # 综合强度评分（0-100）
                    'strength_level': '强势涨停',    # 强度等级
                    'heat_level': 4,                # 热度等级（1-5）
                    'limit_quality': '优质',         # 涨停质量
                    'components': {
                        'seal_score': 90,           # 封单强度得分
                        'time_score': 85,           # 首封时间得分
                        'turnover_score': 80,       # 换手质量得分
                        'volume_score': 90,         # 成交量得分
                        'chain_score': 70,          # 连板高度得分
                    },
                    'summary': '早盘快速封板，封单稳定，资金强度较高',
                    'risk_warning': [],             # 风险提示列表
                    'data_source': 'limit_up_strength',
                    'timestamp': 时间戳,
                }
        """
        result = {
            'limit_up_strength_score': 0,
            'strength_level': '',
            'heat_level': 0,
            'limit_quality': '',
            'components': {
                'seal_score': 0,
                'time_score': 0,
                'turnover_score': 0,
                'volume_score': 0,
                'chain_score': 0,
            },
            'summary': '',
            'risk_warning': [],
            'data_source': 'limit_up_strength',
            'timestamp': time.time(),
        }

        try:
            if not limit_up_data:
                result['summary'] = '无涨停数据'
                return result

            # 如果未涨停，直接返回
            is_limit_up = limit_up_data.get('is_limit_up', False)
            if not is_limit_up:
                result['strength_level'] = '非涨停'
                result['limit_quality'] = '无'
                result['summary'] = '当前未涨停，不计算强度'
                return result

            # 1. 封单强度评分
            seal_score = self._calc_seal_score(limit_up_data)
            result['components']['seal_score'] = seal_score

            # 2. 首封时间评分
            time_score = self._calc_time_score(limit_up_data)
            result['components']['time_score'] = time_score

            # 3. 换手质量评分
            turnover_score = self._calc_turnover_score(limit_up_data)
            result['components']['turnover_score'] = turnover_score

            # 4. 成交量评分
            volume_score = self._calc_volume_score(limit_up_data)
            result['components']['volume_score'] = volume_score

            # 5. 连板高度评分
            chain_score = self._calc_chain_score(limit_up_data)
            result['components']['chain_score'] = chain_score

            # 综合评分（加权）
            total_score = (
                seal_score * self.weights['seal'] / 100 +
                time_score * self.weights['time'] / 100 +
                turnover_score * self.weights['turnover'] / 100 +
                volume_score * self.weights['volume'] / 100 +
                chain_score * self.weights['chain'] / 100
            )
            result['limit_up_strength_score'] = round(total_score, 1)

            # 强度等级
            result['strength_level'] = self._get_strength_level(total_score)

            # 热度等级
            result['heat_level'] = self._get_heat_level(total_score)

            # 涨停质量
            result['limit_quality'] = self._get_limit_quality(total_score)

            # 风险提示
            result['risk_warning'] = self._get_risk_warning(limit_up_data, total_score)

            # 总结
            result['summary'] = self._generate_summary(limit_up_data, result)

        except Exception as e:
            print(f"[LimitUpStrength] 分析异常: {e}")
            result['summary'] = f'分析异常: {e}'

        return result

    def analyze_stock(self, code):
        """
        分析单只股票的涨停强度（自动获取数据）

        参数：
            code: 股票代码

        返回：
            dict: 涨停强度分析结果
        """
        try:
            from data.limit_up_data_provider import get_limit_up_data_provider
            provider = get_limit_up_data_provider()
            limit_up_data = provider.get_limit_up_data(code)
            return self.analyze(limit_up_data)
        except Exception as e:
            print(f"[LimitUpStrength] 分析股票异常: {code} - {e}")
            return {
                'limit_up_strength_score': 0,
                'strength_level': '分析失败',
                'summary': f'分析异常: {e}',
                'risk_warning': [],
            }

    def _calc_seal_score(self, data):
        """
        计算封单强度得分（0-100）

        核心指标：封单比例（封单金额/流通市值）
        考虑：流通市值匹配（大市值要求低一些）
        """
        seal_ratio = data.get('seal_ratio', 0)
        float_market_cap = data.get('float_market_cap', 0)

        if seal_ratio <= 0:
            return 0

        # 基础评分（基于封单比例）
        if seal_ratio >= 5:
            base_score = 100
        elif seal_ratio >= 3:
            base_score = 90
        elif seal_ratio >= 1:
            base_score = 75
        elif seal_ratio >= 0.5:
            base_score = 60
        else:
            base_score = 40

        # 流通市值调整（大市值股票封单比例要求适当降低）
        # 100亿以下：不调整
        # 100-500亿：+3分
        # 500-1000亿：+5分
        # 1000亿以上：+8分
        cap_bonus = 0
        if float_market_cap > 0:
            cap_yi = float_market_cap / 100000000
            if cap_yi >= 1000:
                cap_bonus = 8
            elif cap_yi >= 500:
                cap_bonus = 5
            elif cap_yi >= 100:
                cap_bonus = 3

        final_score = min(100, base_score + cap_bonus)
        return round(final_score, 1)

    def _calc_time_score(self, data):
        """
        计算首封时间得分（0-100）

        越早封板越强：
        09:25-09:35  100分（集合竞价/开盘秒板）
        09:35-10:00  90分（早盘快速封板）
        10:00-11:00  75分（上午中段）
        11:00-13:00  65分（上午尾盘/午盘）
        13:00-14:00  55分（下午中段）
        14:00以后    40分（尾盘抢筹）
        """
        first_limit_time = data.get('first_limit_time', '')

        if not first_limit_time or ':' not in first_limit_time:
            return 0

        try:
            parts = first_limit_time.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            total_minute = hour * 60 + minute

            # 09:25-09:35
            if 565 <= total_minute <= 575:
                return 100
            # 09:35-10:00
            elif 575 < total_minute <= 600:
                return 90
            # 10:00-11:00
            elif 600 < total_minute <= 660:
                return 75
            # 11:00-13:00
            elif 660 < total_minute <= 780:
                return 65
            # 13:00-14:00
            elif 780 < total_minute <= 840:
                return 55
            # 14:00以后
            elif total_minute > 840:
                return 40
            else:
                return 50
        except Exception:
            return 0

    def _calc_turnover_score(self, data):
        """
        计算换手质量得分（0-100）

        5%-15%最佳，过高过低都有风险：
        5%-15%    100分（最佳）
        3%-5%     85分（偏低但正常）
        15%-20%   85分（偏高但正常）
        2%-3%     70分（偏低，锁仓）
        20%-25%   70分（偏高，抛压）
        <2%       50分（过低，流动性差）
        >25%      50分（过高，抛压大）
        无数据    60分（默认中性）
        """
        turnover_rate = data.get('turnover_rate', 0)

        if turnover_rate <= 0:
            return 60  # 无数据，中性

        if 5 <= turnover_rate <= 15:
            return 100
        elif 3 <= turnover_rate < 5:
            return 85
        elif 15 < turnover_rate <= 20:
            return 85
        elif 2 <= turnover_rate < 3:
            return 70
        elif 20 < turnover_rate <= 25:
            return 70
        elif turnover_rate < 2:
            return 50
        elif turnover_rate > 25:
            return 50
        else:
            return 60

    def _calc_volume_score(self, data):
        """
        计算成交量得分（0-100）

        核心指标：量比
        >=3    100分（大幅放量）
        2-3    90分（明显放量）
        1.5-2  80分（温和放量）
        1-1.5  70分（正常）
        0.8-1  60分（略缩量）
        <0.8   50分（缩量）
        无数据 60分
        """
        volume_ratio = data.get('volume_ratio', 0)

        if volume_ratio <= 0:
            return 60

        if volume_ratio >= 3:
            return 100
        elif volume_ratio >= 2:
            return 90
        elif volume_ratio >= 1.5:
            return 80
        elif volume_ratio >= 1:
            return 70
        elif volume_ratio >= 0.8:
            return 60
        else:
            return 50

    def _calc_chain_score(self, data):
        """
        计算连板高度得分（0-100）

        描述情绪高度，不代表买入：
        首板    60分
        二板    80分
        三板    90分
        四板+   100分
        未涨停  0分
        """
        consecutive_days = data.get('consecutive_days', 0)

        if consecutive_days <= 0:
            return 0
        elif consecutive_days == 1:
            return 60
        elif consecutive_days == 2:
            return 80
        elif consecutive_days == 3:
            return 90
        else:
            return 100

    def _get_strength_level(self, score):
        """获取强度等级"""
        if score >= 85:
            return '强势涨停'
        elif score >= 70:
            return '普通涨停'
        elif score >= 50:
            return '弱势涨停'
        else:
            return '无效涨停'

    def _get_heat_level(self, score):
        """获取热度等级（1-5）"""
        if score >= 90:
            return 5
        elif score >= 80:
            return 4
        elif score >= 70:
            return 3
        elif score >= 60:
            return 2
        else:
            return 1

    def _get_limit_quality(self, score):
        """获取涨停质量"""
        if score >= 85:
            return '优质'
        elif score >= 70:
            return '良好'
        elif score >= 50:
            return '一般'
        else:
            return '较差'

    def _get_risk_warning(self, data, score):
        """
        获取风险提示列表

        风险维度：
        - 高位连板风险
        - 尾盘封板风险
        - 高换手风险
        - 低封单风险
        - 重复封板风险
        """
        warnings = []

        # 高位连板风险
        consecutive_days = data.get('consecutive_days', 0)
        if consecutive_days >= 3:
            warnings.append(f'高位连板（{consecutive_days}板），情绪过热，追高风险大')

        # 尾盘封板风险
        limit_up_period = data.get('limit_up_period', '')
        if limit_up_period == '尾盘抢筹':
            warnings.append('尾盘封板，资金信心不足，次日溢价可能较低')

        # 高换手风险
        turnover_rate = data.get('turnover_rate', 0)
        if turnover_rate > 25:
            warnings.append(f'换手率过高（{turnover_rate}%），抛压较大')

        # 低封单风险
        seal_ratio = data.get('seal_ratio', 0)
        if 0 < seal_ratio < 0.5:
            warnings.append(f'封单比例过低（{seal_ratio}%），炸板风险高')

        # 重复封板风险
        limit_up_status = data.get('limit_up_status', '')
        if limit_up_status == '重复封板':
            warnings.append('盘中开板后回封，资金分歧较大')

        # 缩量涨停风险
        volume_ratio = data.get('volume_ratio', 0)
        if 0 < volume_ratio < 0.8:
            warnings.append('缩量涨停，流动性不足，持续性存疑')

        return warnings

    def _generate_summary(self, data, result):
        """生成总结描述"""
        parts = []

        # 封板时间
        first_time = data.get('first_limit_time', '')
        limit_up_period = data.get('limit_up_period', '')
        if first_time:
            if limit_up_period:
                parts.append(f'{limit_up_period}（{first_time}封板）')
            else:
                parts.append(f'{first_time}封板')

        # 封板类型
        limit_up_style = data.get('limit_up_style', '')
        if limit_up_style:
            parts.append(limit_up_style)

        # 连板
        consecutive_days = data.get('consecutive_days', 0)
        limit_chain_type = data.get('limit_chain_type', '')
        if consecutive_days > 0:
            if limit_chain_type:
                parts.append(limit_chain_type)
            else:
                parts.append(f'{consecutive_days}连板')

        # 封单情况
        seal_ratio = data.get('seal_ratio', 0)
        if seal_ratio > 0:
            if seal_ratio >= 3:
                parts.append('封单强劲')
            elif seal_ratio >= 1:
                parts.append('封单稳定')
            else:
                parts.append('封单较弱')

        # 强度等级
        strength_level = result.get('strength_level', '')
        if strength_level:
            parts.append(f'综合评估：{strength_level}')

        if parts:
            return '，'.join(parts)
        else:
            return '涨停强度分析完成'


# 单例获取函数
_limit_up_strength_analyzer = None


def get_limit_up_strength_analyzer():
    """获取涨停强度分析器单例"""
    global _limit_up_strength_analyzer
    if _limit_up_strength_analyzer is None:
        _limit_up_strength_analyzer = LimitUpStrengthAnalyzer()
    return _limit_up_strength_analyzer
