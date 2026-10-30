# -*- coding: utf-8 -*-
"""
B4注销式回购信号识别模块
V1.1-3.2.4-A 新增

职责：
1. 判断公告是否属于回购事件
2. 区分注销式回购和普通回购
3. 提取回购金额
4. 判断回购等级
5. 输出标准事件格式

不负责评分，只做识别。

识别规则：
- 强信号：注销式回购（回购股份并注销、减少注册资本）
- 弱信号：普通回购（员工持股、股权激励等，不加分）
- 排除：回购预案、提议回购、拟回购（只有计划，没实施）
"""

import re


class BuybackSignalDetector:
    """回购信号识别器"""

    def __init__(self):
        # 注销式回购关键词（强信号）
        self.cancel_keywords = [
            '回购股份并注销', '注销回购股份', '减少注册资本',
            '用于注销', '注销部分股份', '股份注销',
            '回购注销', '注销回购',
            '股份变动公告（注销）', '注销部分已回购股份',
            '回购股份注销', '注销已回购股份',
            '股份回购并注销', '实施股份回购并注销',
            '注销式回购',
        ]

        # 普通回购关键词（弱信号，不加分）
        self.normal_keywords = [
            '回购股份', '回购公司股份', '股份回购',
            '以集中竞价方式回购', '以集合竞价方式回购',
        ]

        # 普通回购用途（确认是普通回购）
        self.normal_use_keywords = [
            '员工持股计划', '股权激励', '转换可转债',
            '用于员工持股', '用于股权激励', '用于转换',
        ]

        # 排除词（只有计划，没实施）
        self.exclude_keywords = [
            '提议回购', '拟回购', '董事会授权', '回购预案',
            '回购方案', '回购报告书', '提示性公告',
            '董事长提议', '审议回购',
        ]

        # 金额提取正则
        self.amount_patterns = [
            r'回购金额[^\d]*(\d+\.?\d*)\s*亿元',
            r'回购金额[^\d]*(\d+\.?\d*)\s*亿',
            r'回购金额[^\d]*(\d+\.?\d*)\s*万元',
            r'回购金额[^\d]*(\d+\.?\d*)\s*万',
            r'回购资金[^\d]*(\d+\.?\d*)\s*亿元',
            r'回购资金[^\d]*(\d+\.?\d*)\s*亿',
            r'回购资金[^\d]*(\d+\.?\d*)\s*万元',
            r'回购资金[^\d]*(\d+\.?\d*)\s*万',
            r'累计回购[^\d]*(\d+\.?\d*)\s*亿元',
            r'累计回购[^\d]*(\d+\.?\d*)\s*亿',
            r'累计回购[^\d]*(\d+\.?\d*)\s*万元',
            r'累计回购[^\d]*(\d+\.?\d*)\s*万',
            r'注销式回购[^\d]*(\d+\.?\d*)\s*亿元',
            r'注销式回购[^\d]*(\d+\.?\d*)\s*亿',
            r'回购[^\d]*(\d+\.?\d*)\s*亿元',
            r'回购[^\d]*(\d+\.?\d*)\s*亿',
            r'回购[^\d]*(\d+\.?\d*)\s*万元',
            r'回购[^\d]*(\d+\.?\d*)\s*万',
        ]

    def detect_buyback(self, announcement):
        """
        检测公告是否包含回购事件

        参数：
            announcement: 公告字典（title, date, ...）

        返回：
            dict: 回购信号识别结果
        """
        result = {
            'has_buyback': False,
            'buyback_type': '',  # cancel: 注销式, normal: 普通回购
            'title': '',
            'date': '',
            'amount': 0,  # 亿元
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

        # 检查排除词（优先排除：只有计划的不算）
        for keyword in self.exclude_keywords:
            if keyword in title:
                # 有排除词，直接返回
                # 但"进展"、"实施"、"首次"等说明已经开始实施了，不算排除
                if '进展' in title or '实施' in title or '首次' in title or '完成' in title:
                    break
                else:
                    return result

        # 检查是否是注销式回购
        is_cancel = False
        for keyword in self.cancel_keywords:
            if keyword in title:
                is_cancel = True
                break

        # 检查是否是普通回购
        is_normal = False
        if not is_cancel:
            for keyword in self.normal_keywords:
                if keyword in title:
                    is_normal = True
                    break

        if not is_cancel and not is_normal:
            return result

        # 提取金额
        amount = self._extract_amount(title)

        if is_cancel:
            result['has_buyback'] = True
            result['buyback_type'] = 'cancel'
            result['confidence'] = 0.9 if amount > 0 else 0.6
            result['amount'] = amount
        elif is_normal:
            result['has_buyback'] = True
            result['buyback_type'] = 'normal'
            result['confidence'] = 0.7 if amount > 0 else 0.5
            result['amount'] = amount

        # 判断等级（只对注销式回购评级）
        if is_cancel and amount > 0:
            if amount >= 10:
                result['level'] = 'S'
                result['detail'] = f'注销式回购{amount:.2f}亿元，金额较大'
            elif amount >= 5:
                result['level'] = 'A'
                result['detail'] = f'注销式回购{amount:.2f}亿元，金额适中'
            elif amount >= 1:
                result['level'] = 'B'
                result['detail'] = f'注销式回购{amount:.2f}亿元，金额一般'
            else:
                result['level'] = 'C'
                result['detail'] = f'注销式回购{amount:.2f}亿元，金额较小'
        elif is_cancel:
            result['level'] = '未知'
            result['detail'] = '注销式回购，未提取到具体金额'
        elif is_normal:
            result['level'] = 'normal'
            result['detail'] = '普通回购（用于员工持股/股权激励等），不进入买入评分'

        return result

    def detect_buybacks_batch(self, announcements):
        """
        批量检测公告列表中的回购事件

        参数：
            announcements: 公告列表

        返回：
            list: 回购信号列表（只返回注销式回购）
        """
        buybacks = []
        for ann in announcements:
            buyback = self.detect_buyback(ann)
            if buyback.get('has_buyback') and buyback.get('buyback_type') == 'cancel':
                # 只返回注销式回购
                buybacks.append(buyback)
        return buybacks

    def _extract_amount(self, text):
        """
        从文本中提取回购金额（亿元）

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

    def get_buyback_score(self, buyback, days_ago=0):
        """
        计算回购信号得分

        注意：只有注销式回购才加分，普通回购不加分

        参数：
            buyback: 回购信号
            days_ago: 公告距今多少天（用于时间衰减）

        返回：
            int: 得分
        """
        if not buyback.get('has_buyback'):
            return 0

        # 普通回购不加分
        if buyback.get('buyback_type') != 'cancel':
            return 0

        # 基础分（注销式回购）
        level = buyback.get('level', '')
        base_score = {
            'S': 25,  # >10亿
            'A': 15,  # 5-10亿
            'B': 10,  # 1-5亿
            'C': 5,   # <1亿
            '未知': 5,
        }.get(level, 5)

        # 置信度调整
        confidence = buyback.get('confidence', 0.5)
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
_buyback_detector = None


def get_buyback_signal_detector():
    """获取回购信号识别器单例"""
    global _buyback_detector
    if _buyback_detector is None:
        _buyback_detector = BuybackSignalDetector()
    return _buyback_detector
