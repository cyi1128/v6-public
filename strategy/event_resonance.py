# -*- coding: utf-8 -*-
"""
事件共振策略模块
V1.1-3.3-A 新增

定位：
在5个独立事件信号基础上，检测多事件共振组合，提高信号可信度。

原则：
- 不修改已有事件信号
- 不修改评分模型
- 只新增共振分析层
- 可独立删除

核心逻辑：
- 单事件：普通信号
- 双事件共振：可信度提升
- 三事件共振：强信号
- 四事件及以上：机构级机会
"""


class EventResonanceAnalyzer:
    """事件共振分析器"""

    def __init__(self):
        # 共振等级定义
        self.resonance_levels = {
            'single': {'name': '单事件', 'level': 1, 'confidence': '普通'},
            'double': {'name': '双事件共振', 'level': 2, 'confidence': '较高'},
            'triple': {'name': '三事件共振', 'level': 3, 'confidence': '高'},
            'quad': {'name': '四事件共振', 'level': 4, 'confidence': '极高'},
            'super': {'name': '超强共振', 'level': 5, 'confidence': '机构级'},
        }

        # 经典共振组合（机构常用）
        self.classic_combos = [
            {
                'combo': ['B1', 'B2'],
                'name': '业绩+订单共振',
                'description': '业绩增长+大额订单，基本面与未来共振',
                'strength': '强',
            },
            {
                'combo': ['B2', 'B3'],
                'name': '业绩+增持共振',
                'description': '业绩改善+大股东增持，内外信心共振',
                'strength': '强',
            },
            {
                'combo': ['B2', 'B4'],
                'name': '业绩+回购共振',
                'description': '业绩增长+注销式回购，价值回归信号',
                'strength': '强',
            },
            {
                'combo': ['B1', 'B3'],
                'name': '订单+增持共振',
                'description': '订单落地+内部增持，未来与信心共振',
                'strength': '中',
            },
            {
                'combo': ['B3', 'B4'],
                'name': '增持+回购共振',
                'description': '股东增持+公司回购，内外资金共振',
                'strength': '中',
            },
            {
                'combo': ['B1', 'B2', 'B3'],
                'name': '业绩+订单+增持',
                'description': '三重基本面共振，高置信机会',
                'strength': '极强',
            },
            {
                'combo': ['B2', 'B3', 'B4'],
                'name': '业绩+增持+回购',
                'description': '价值回归三重信号，底部确认',
                'strength': '极强',
            },
        ]

    def analyze_resonance(self, event_signals):
        """
        分析事件共振情况

        参数：
            event_signals: 事件信号列表，每个信号包含name字段

        返回：
            dict: 共振分析结果
        """
        result = {
            'has_resonance': False,
            'resonance_level': 'single',
            'resonance_name': '单事件',
            'confidence': '普通',
            'event_count': 0,
            'classic_combos': [],
            'resonance_bonus': 0,
            'detail': '',
        }

        if not event_signals:
            result['detail'] = '暂无事件信号'
            return result

        # 统计事件数量
        event_count = len(event_signals)
        result['event_count'] = event_count

        if event_count <= 1:
            result['detail'] = '单事件信号，无共振'
            return result

        # 判断共振等级
        if event_count >= 5:
            level = 'super'
        elif event_count == 4:
            level = 'quad'
        elif event_count == 3:
            level = 'triple'
        else:
            level = 'double'

        result['has_resonance'] = True
        result['resonance_level'] = level
        level_info = self.resonance_levels.get(level, {})
        result['resonance_name'] = level_info.get('name', '')
        result['confidence'] = level_info.get('confidence', '')

        # 共振加分（额外的可信度加分）
        bonus_map = {
            'double': 3,
            'triple': 7,
            'quad': 12,
            'super': 15,
        }
        result['resonance_bonus'] = bonus_map.get(level, 0)

        # 检测经典共振组合
        event_codes = []
        for s in event_signals:
            name = s.get('name', '')
            if 'B1' in name or '订单' in name:
                event_codes.append('B1')
            elif 'B2' in name or '业绩' in name:
                event_codes.append('B2')
            elif 'B3' in name or '增持' in name:
                event_codes.append('B3')
            elif 'B4' in name or '回购' in name:
                event_codes.append('B4')
            elif 'B6' in name or '重组' in name:
                event_codes.append('B6')

        for combo in self.classic_combos:
            combo_events = combo['combo']
            if all(e in event_codes for e in combo_events):
                result['classic_combos'].append({
                    'name': combo['name'],
                    'description': combo['description'],
                    'strength': combo['strength'],
                })

        # 生成详情
        if result['classic_combos']:
            combo_names = [c['name'] for c in result['classic_combos']]
            result['detail'] = f"检测到{result['resonance_name']}（{', '.join(combo_names)}），信号可信度{result['confidence']}"
        else:
            result['detail'] = f"检测到{result['resonance_name']}，信号可信度{result['confidence']}"

        return result

    def get_resonance_score_bonus(self, resonance_result):
        """
        获取共振加分

        注意：这个加分是"可信度加分"，不算在事件贡献上限里
        但也要受总分100分限制

        参数：
            resonance_result: 共振分析结果

        返回：
            int: 共振加分
        """
        return resonance_result.get('resonance_bonus', 0)


# 单例
_resonance_analyzer = None


def get_event_resonance_analyzer():
    """获取事件共振分析器单例"""
    global _resonance_analyzer
    if _resonance_analyzer is None:
        _resonance_analyzer = EventResonanceAnalyzer()
    return _resonance_analyzer
