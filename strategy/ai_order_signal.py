# -*- coding: utf-8 -*-
"""
B1大额订单信号识别模块
V1.1-3.2.2-B2.2 新增

职责：
1. 判断公告是否属于订单事件
2. 提取订单金额
3. 判断订单等级
4. 输出标准事件格式

不负责评分，只做识别。

数据来源：巨潮资讯网公告
"""

import re


class OrderSignalDetector:
    """大额订单信号识别器"""

    def __init__(self):
        # 强订单关键词
        self.strong_keywords = [
            '中标', '重大合同', '销售合同', '采购合同', '供货协议',
            '项目合同', '重大订单', '签订合同', '签署合同',
            '合同公告', '重大项目', '项目中标', '工程合同',
        ]

        # 中等关键词（需要有金额才算）
        self.medium_keywords = [
            '战略合作协议', '合作协议', '框架协议',
        ]

        # 排除词（即使有关键词也排除）
        self.exclude_keywords = [
            '意向', '探讨', '交流', '战略布局', '备忘录',
            '投资计划', '拟投资', '预计', '可能', '规划',
            '框架', '意向书', '合作意向', '战略合作框架',
        ]

        # 金额提取正则
        self.amount_patterns = [
            r'(\d+\.?\d*)\s*亿元',
            r'(\d+\.?\d*)\s*亿',
            r'(\d+\.?\d*)\s*万元',
            r'(\d+\.?\d*)\s*万',
            r'人民币\s*(\d+\.?\d*)\s*亿元',
            r'人民币\s*(\d+\.?\d*)\s*万',
            r'金额\s*(\d+\.?\d*)\s*亿元',
            r'金额\s*(\d+\.?\d*)\s*万',
            r'合同金额\s*(\d+\.?\d*)\s*亿元',
            r'合同金额\s*(\d+\.?\d*)\s*万',
            r'总投资\s*(\d+\.?\d*)\s*亿元',
            r'总投资\s*(\d+\.?\d*)\s*万',
        ]

    def detect_order(self, announcement, revenue=0):
        """
        检测公告是否包含大额订单

        参数：
            announcement: 公告字典（title, date, ...）
            revenue: 公司最近一年营收（亿元），用于计算比例

        返回：
            dict: 订单信号识别结果
        """
        result = {
            'has_order': False,
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

        # 检查排除词（优先排除）
        for keyword in self.exclude_keywords:
            if keyword in title:
                # 有排除词，直接返回
                return result

        # 检查强关键词
        has_strong = False
        for keyword in self.strong_keywords:
            if keyword in title:
                has_strong = True
                break

        # 检查中等关键词
        has_medium = False
        for keyword in self.medium_keywords:
            if keyword in title:
                has_medium = True
                break

        if not has_strong and not has_medium:
            return result

        # 提取金额
        amount = self._extract_amount(title)

        # 强关键词 + 有金额 → 高置信度
        if has_strong and amount > 0:
            result['has_order'] = True
            result['confidence'] = 0.9
            result['title'] = title
            result['amount'] = amount
        # 强关键词 + 无金额 → 中置信度
        elif has_strong and amount == 0:
            result['has_order'] = True
            result['confidence'] = 0.6
            result['title'] = title
            result['amount'] = 0
        # 中等关键词 + 有金额 → 中置信度
        elif has_medium and amount > 0:
            result['has_order'] = True
            result['confidence'] = 0.7
            result['title'] = title
            result['amount'] = amount
        # 中等关键词 + 无金额 → 低置信度，不算订单
        else:
            return result

        # 计算订单等级
        if revenue > 0 and amount > 0:
            ratio = amount / revenue * 100
            if ratio >= 20:
                result['level'] = 'S'
                result['detail'] = f'订单金额{amount:.2f}亿元，占营收{ratio:.1f}%，重大订单'
            elif ratio >= 10:
                result['level'] = 'A'
                result['detail'] = f'订单金额{amount:.2f}亿元，占营收{ratio:.1f}%，重要订单'
            elif ratio >= 5:
                result['level'] = 'B'
                result['detail'] = f'订单金额{amount:.2f}亿元，占营收{ratio:.1f}%，一般订单'
            else:
                result['level'] = 'C'
                result['detail'] = f'订单金额{amount:.2f}亿元，占营收{ratio:.1f}%，影响较小'
        elif amount > 0:
            result['level'] = '未知'
            result['detail'] = f'订单金额{amount:.2f}亿元，营收数据未知'
        else:
            result['level'] = '未知'
            result['detail'] = '未提取到具体金额'

        return result

    def detect_orders_batch(self, announcements, revenue=0):
        """
        批量检测公告列表中的订单

        参数：
            announcements: 公告列表
            revenue: 公司最近一年营收（亿元）

        返回：
            list: 订单信号列表
        """
        orders = []
        for ann in announcements:
            order = self.detect_order(ann, revenue)
            if order.get('has_order'):
                orders.append(order)
        return orders

    def _extract_amount(self, text):
        """
        从文本中提取金额（亿元）

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

    def get_order_score(self, order, days_ago=0):
        """
        计算订单信号得分

        参数：
            order: 订单信号
            days_ago: 公告距今多少天（用于时间衰减）

        返回：
            int: 得分
        """
        if not order.get('has_order'):
            return 0

        # 基础分
        level = order.get('level', '')
        base_score = {
            'S': 30,
            'A': 20,
            'B': 10,
            'C': 5,
            '未知': 5,
        }.get(level, 5)

        # 置信度调整
        confidence = order.get('confidence', 0.5)
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
_order_detector = None


def get_order_signal_detector():
    """获取订单信号识别器单例"""
    global _order_detector
    if _order_detector is None:
        _order_detector = OrderSignalDetector()
    return _order_detector
