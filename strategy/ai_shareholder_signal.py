# -*- coding: utf-8 -*-
"""
B3大股东增持信号识别模块
V1.1-3.2.3-A 新增

职责：
1. 判断公告是否属于大股东增持事件
2. 提取增持金额/数量
3. 判断增持等级
4. 输出标准事件格式

不负责评分，只做识别。

识别规则：
- 正向：控股股东增持、实际控制人增持、大股东增持
- 排除：董监高普通买入、员工持股、股权激励、减持
"""

import re


class ShareholderIncreaseDetector:
    """大股东增持信号识别器"""

    def __init__(self):
        # 强增持关键词（大股东级别）
        self.strong_keywords = [
            '控股股东增持', '实际控制人增持', '大股东增持',
            '控股股东及一致行动人增持', '实际控制人及一致行动人增持',
            '公司控股股东增持', '公司实际控制人增持',
            '控股股东拟增持', '实际控制人拟增持', '大股东拟增持',
            '控股股东累计增持', '实际控制人累计增持', '大股东累计增持',
            '第一大股东增持', '第一大股东拟增持', '第一大股东累计增持',
            '第一大股东完成增持', '第一大股东增持计划',
        ]

        # 中等增持关键词（需要确认主体）
        self.medium_keywords = [
            '股东增持', '增持公司股份', '增持股份',
            '关于增持', '增持计划', '增持进展',
            '拟增持', '累计增持',
        ]

        # 排除词（即使有关键词也排除）
        self.exclude_keywords = [
            '减持', '董监高', '董事增持', '监事增持', '高管增持',
            '员工持股', '股权激励', '员工持股计划',
            '拟减持', '减持计划', '减持进展',
            '回购', '回购股份',  # 回购不算增持
        ]

        # 金额提取正则
        self.amount_patterns = [
            r'增持金额[^\d]*(\d+\.?\d*)\s*亿元',
            r'增持金额[^\d]*(\d+\.?\d*)\s*亿',
            r'增持金额[^\d]*(\d+\.?\d*)\s*万元',
            r'增持金额[^\d]*(\d+\.?\d*)\s*万',
            r'累计增持[^\d]*(\d+\.?\d*)\s*亿元',
            r'累计增持[^\d]*(\d+\.?\d*)\s*亿',
            r'累计增持[^\d]*(\d+\.?\d*)\s*万元',
            r'累计增持[^\d]*(\d+\.?\d*)\s*万',
            r'拟增持[^\d]*(\d+\.?\d*)\s*亿元',
            r'拟增持[^\d]*(\d+\.?\d*)\s*亿',
            r'拟增持[^\d]*(\d+\.?\d*)\s*万元',
            r'拟增持[^\d]*(\d+\.?\d*)\s*万',
            r'增持[^\d]*(\d+\.?\d*)\s*亿元',
            r'增持[^\d]*(\d+\.?\d*)\s*亿',
            r'增持[^\d]*(\d+\.?\d*)\s*万元',
            r'增持[^\d]*(\d+\.?\d*)\s*万',
        ]

    def detect_increase(self, announcement):
        """
        检测公告是否包含大股东增持

        参数：
            announcement: 公告字典（title, date, ...）

        返回：
            dict: 增持信号识别结果
        """
        result = {
            'has_increase': False,
            'title': '',
            'date': '',
            'amount': 0,  # 亿元
            'increase_type': '',
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

        # 检查强关键词（大股东级别）
        has_strong = False
        for keyword in self.strong_keywords:
            if keyword in title:
                has_strong = True
                result['increase_type'] = '大股东增持'
                break

        # 检查中等关键词
        has_medium = False
        if not has_strong:
            for keyword in self.medium_keywords:
                if keyword in title:
                    has_medium = True
                    result['increase_type'] = '股东增持'
                    break

        if not has_strong and not has_medium:
            return result

        # 提取金额
        amount = self._extract_amount(title)

        # 强关键词 + 有金额 → 高置信度
        if has_strong and amount > 0:
            result['has_increase'] = True
            result['confidence'] = 0.9
            result['amount'] = amount
        # 强关键词 + 无金额 → 中置信度
        elif has_strong and amount == 0:
            result['has_increase'] = True
            result['confidence'] = 0.6
            result['amount'] = 0
        # 中等关键词 + 有金额 → 中置信度
        elif has_medium and amount > 0:
            result['has_increase'] = True
            result['confidence'] = 0.7
            result['amount'] = amount
        # 中等关键词 + 无金额 → 低置信度，不算
        else:
            return result

        # 判断等级
        if amount > 0:
            if amount >= 5:
                result['level'] = 'S'
                result['detail'] = f'大股东增持{amount:.2f}亿元，金额较大'
            elif amount >= 1:
                result['level'] = 'A'
                result['detail'] = f'大股东增持{amount:.2f}亿元，金额适中'
            elif amount >= 0.3:
                result['level'] = 'B'
                result['detail'] = f'大股东增持{amount:.2f}亿元，金额一般'
            else:
                result['level'] = 'C'
                result['detail'] = f'大股东增持{amount:.2f}亿元，金额较小'
        else:
            result['level'] = '未知'
            result['detail'] = '未提取到具体增持金额'

        return result

    def detect_increases_batch(self, announcements):
        """
        批量检测公告列表中的增持事件

        参数：
            announcements: 公告列表

        返回：
            list: 增持信号列表
        """
        increases = []
        for ann in announcements:
            increase = self.detect_increase(ann)
            if increase.get('has_increase'):
                increases.append(increase)
        return increases

    def _extract_amount(self, text):
        """
        从文本中提取增持金额（亿元）

        参数：
            text: 文本

        返回：
            float: 金额（亿元），提取失败返回0
        """
        for pattern in self.amount_patterns:
            match = re.search(pattern, text)
            if match:
                amount_str = match.group(1)
                try:
                    amount = float(amount_str)
                    # 判断单位
                    if '亿' in pattern:
                        return amount
                    elif '万' in pattern:
                        return amount / 10000  # 万元转亿元
                except:
                    continue
        return 0

    def get_increase_score(self, increase, days_ago=0):
        """
        计算增持信号得分

        参数：
            increase: 增持信号
            days_ago: 公告距今多少天（用于时间衰减）

        返回：
            int: 得分
        """
        if not increase.get('has_increase'):
            return 0

        # 基础分
        level = increase.get('level', '')
        base_score = {
            'S': 20,  # >5亿
            'A': 15,  # 1-5亿
            'B': 10,  # 0.3-1亿
            'C': 5,   # <0.3亿
            '未知': 5,
        }.get(level, 5)

        # 置信度调整
        confidence = increase.get('confidence', 0.5)
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
_increase_detector = None


def get_shareholder_increase_detector():
    """获取大股东增持信号识别器单例"""
    global _increase_detector
    if _increase_detector is None:
        _increase_detector = ShareholderIncreaseDetector()
    return _increase_detector
