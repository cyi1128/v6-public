# -*- coding: utf-8 -*-
"""
B6重组并购信号识别模块
V1.1-3.2.5-A 新增

职责：
1. 判断公告是否属于重组并购事件
2. 区分重大重组和普通收购
3. 判断重组等级
4. 输出标准事件格式

不负责评分，只做识别。

识别规则：
- 强信号：重大资产重组、发行股份购买资产、吸收合并
- 中等信号：重大资产收购、股权收购
- 弱信号：普通对外投资、设立子公司（不加分）
- 排除：战略合作、意向协议、框架协议、小额投资
"""

import re


class RestructureSignalDetector:
    """重组并购信号识别器"""

    def __init__(self):
        # 重大重组关键词（强信号）
        self.major_keywords = [
            '重大资产重组', '发行股份购买资产', '吸收合并',
            '重大资产购买', '重大资产出售', '重大资产置换',
            '资产重组', '并购重组', '借壳上市',
            '重大资产注入', '整体上市',
        ]

        # 普通收购关键词（中等信号）
        self.normal_keywords = [
            '收购股权', '收购公司', '购买资产',
            '股权收购', '资产收购', '收购资产',
            '对外投资', '增资',
        ]

        # 排除词（即使有关键词也排除）
        self.exclude_keywords = [
            '战略合作', '意向协议', '框架协议',
            '合作框架', '合作意向', '战略合作协议',
            '拟投资', '投资计划', '投资意向',
            '设立子公司', '设立分公司',
            '日常经营', '日常关联交易',
            '正在论证', '拟筹划', '筹划中', '论证中',
            '初步意向', '有意向', '商讨中',
        ]

    def detect_restructure(self, announcement):
        """
        检测公告是否包含重组并购事件

        参数：
            announcement: 公告字典（title, date, ...）

        返回：
            dict: 重组信号识别结果
        """
        result = {
            'has_restructure': False,
            'restructure_type': '',  # major: 重大重组, normal: 普通收购
            'title': '',
            'date': '',
            'level': '',
            'confidence': 0,
            'source': '巨潮资讯网',
            'detail': '',
        }

        if not announcement:
            return result

        title = announcement.get('title', '')
        date = announcement.get('date', '')

        if not title:
            return result

        result['date'] = date
        result['title'] = title

        # 检查排除词（优先排除）
        for keyword in self.exclude_keywords:
            if keyword in title:
                # 有排除词，直接返回
                return result

        # 检查是否是重大重组
        is_major = False
        for keyword in self.major_keywords:
            if keyword in title:
                is_major = True
                break

        # 检查是否是普通收购
        is_normal = False
        if not is_major:
            for keyword in self.normal_keywords:
                if keyword in title:
                    is_normal = True
                    break

        if not is_major and not is_normal:
            return result

        if is_major:
            result['has_restructure'] = True
            result['restructure_type'] = 'major'
            result['confidence'] = 0.9
            result['level'] = 'S'
            result['detail'] = '重大资产重组事件，强催化'
        elif is_normal:
            result['has_restructure'] = True
            result['restructure_type'] = 'normal'
            result['confidence'] = 0.6
            result['level'] = 'B'
            result['detail'] = '普通收购/投资事件，催化一般'

        return result

    def detect_restructures_batch(self, announcements):
        """
        批量检测公告列表中的重组事件

        参数：
            announcements: 公告列表

        返回：
            list: 重组信号列表（只返回重大重组）
        """
        restructures = []
        for ann in announcements:
            restructure = self.detect_restructure(ann)
            if restructure.get('has_restructure') and restructure.get('restructure_type') == 'major':
                # 只返回重大重组
                restructures.append(restructure)
        return restructures

    def get_restructure_score(self, restructure, days_ago=0):
        """
        计算重组信号得分

        注意：只有重大重组才加分，普通收购不加分

        参数：
            restructure: 重组信号
            days_ago: 公告距今多少天（用于时间衰减）

        返回：
            int: 得分
        """
        if not restructure.get('has_restructure'):
            return 0

        # 普通收购不加分
        if restructure.get('restructure_type') != 'major':
            return 0

        # 基础分（重大重组）
        level = restructure.get('level', '')
        base_score = {
            'S': 35,  # 重大资产重组
            'A': 25,
            'B': 15,
            'C': 5,
        }.get(level, 20)

        # 置信度调整
        confidence = restructure.get('confidence', 0.5)
        base_score = int(base_score * confidence)

        # 时间衰减
        if days_ago <= 30:
            decay = 1.0
        elif days_ago <= 90:
            decay = 0.7
        elif days_ago <= 180:
            decay = 0.3
        else:
            decay = 0.1

        final_score = int(base_score * decay)
        return max(0, final_score)


# 单例
_restructure_detector = None


def get_restructure_signal_detector():
    """获取重组并购信号识别器单例"""
    global _restructure_detector
    if _restructure_detector is None:
        _restructure_detector = RestructureSignalDetector()
    return _restructure_detector
