# -*- coding: utf-8 -*-
"""
涨停原因增强引擎
V1.3-A-3 新增

定位：
原因整合解释层，只回答"为什么涨停"，不判断强弱、不做买卖建议。

原则：
- 只做接口整合，不做智能推断
- 第一版原因可信度全部来自真实数据（公告/新闻/概念/主营）
- 独立模块，可删除，不影响A-1/A-2及任何现有冻结模块
- 不修改AI评分、R2评级、B1-B6事件、综合确认度

输入：
- 股票代码、名称
- A-1涨停事实数据（可选，用于辅助判断首板/连板背景）

输出：
{
    "limit_up_reason": "AI服务器需求增长+主营业务匹配",
    "limit_up_reason_tags": ["AI", "行业催化", "主营相关"],
    "limit_up_reason_confidence": 85,
    "limit_up_reason_level": "A",
    "limit_up_reason_source": ["F10主营", "概念", "新闻"],
    "evidence": ["主营包含服务器业务", "AI板块当日上涨"],
    "core_theme": "人工智能",
    "theme_score": 85,
    "announcement_catalyst": null,
    "news_catalyst": null,
    "data_source": "limit_up_reason_engine",
    "timestamp": 时间戳
}
"""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ========== 公告刺激关键词 ==========
ANNOUNCEMENT_CATALYST_KEYWORDS = {
    '合同订单': ['签订', '合同', '订单', '中标', '合作', '战略合作', '框架协议', '采购'],
    '业绩增长': ['业绩预告', '业绩增长', '净利润', '预增', '扭亏', '盈利', '营收增长'],
    '重组并购': ['重组', '并购', '收购', '资产注入', '借壳', '重大资产', '发行股份'],
    '政策利好': ['政策', '补贴', '扶持', '规划', '入选', '试点', '示范'],
    '资本运作': ['回购', '增持', '股权激励', '分红', '定增', '募资'],
}

# ========== 新闻催化关键词（热点题材） ==========
NEWS_CATALYST_KEYWORDS = [
    'AI', '人工智能', '大模型', '算力', '芯片', '半导体', '机器人', '人形机器人',
    '新能源', '光伏', '储能', '固态电池', '智能驾驶', '无人驾驶', '华为', '鸿蒙',
    '军工', '航天', '低空经济', '创新药', '国产替代', '信创', '数据要素', '数字经济',
]


class LimitUpReasonEngine:
    """涨停原因增强引擎"""

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
        self._business_cache = {}
        self._business_cache_time = {}
        self._cache_expire = 3600 * 24  # 缓存24小时
        print("[LimitUpReason] 涨停原因增强引擎初始化完成")

    def analyze(self, code, name, limit_up_data=None):
        """
        分析涨停原因

        参数：
            code: 股票代码
            name: 股票名称
            limit_up_data: A-1涨停事实数据（可选）

        返回：
            dict: 涨停原因分析结果
        """
        result = {
            'limit_up_reason': '',
            'limit_up_reason_tags': [],
            'limit_up_reason_confidence': 0,
            'limit_up_reason_level': 'C',
            'limit_up_reason_source': [],
            'evidence': [],
            'core_theme': '',
            'theme_score': 0,
            'announcement_catalyst': None,
            'news_catalyst': None,
            'data_source': 'limit_up_reason_engine',
            'timestamp': time.time(),
        }

        try:
            # ========== 1. 获取概念数据 ==========
            from service.concept_service import get_stock_concepts
            concepts, concept_source = get_stock_concepts(code)
            if concepts:
                result['limit_up_reason_source'].append('概念')
                result['evidence'].append(f'概念来源: {concept_source}，共{len(concepts)}个概念')

            # ========== 2. 获取主营业务 ==========
            business = self._get_business_scope(code)
            if business:
                result['limit_up_reason_source'].append('F10主营')

            # ========== 3. 题材关联分析（复用已有模块） ==========
            from strategy.theme_reason_analyzer import analyze_stock_theme
            pct = 10.0  # 涨停股默认涨幅10%
            if limit_up_data:
                pct = limit_up_data.get('pct_chg', 10.0)

            theme_result = analyze_stock_theme(code, name, concepts, pct, business)
            raw_core_theme = theme_result.get('core_theme', '')
            # 标准化：去掉"概念"/"概念股"后缀，避免原因描述重复
            core_theme = raw_core_theme
            if core_theme.endswith('概念股'):
                core_theme = core_theme[:-3]
            elif core_theme.endswith('概念'):
                core_theme = core_theme[:-2]
            result['core_theme'] = core_theme
            result['theme_score'] = theme_result.get('theme_score', 0)

            if core_theme:
                result['limit_up_reason_tags'].append(core_theme)
                result['evidence'].extend(theme_result.get('evidence', [])[:3])

            if theme_result.get('is_hot_topic'):
                result['limit_up_reason_tags'].append('市场热点')

            # ========== 4. 公告刺激检查 ==========
            announcement_catalyst = self._check_announcement_catalyst(code)
            result['announcement_catalyst'] = announcement_catalyst
            if announcement_catalyst:
                result['limit_up_reason_source'].append('公告')
                result['limit_up_reason_tags'].append(announcement_catalyst['type'])
                result['evidence'].append(f"公告催化: {announcement_catalyst['title'][:50]}")

            # ========== 5. 新闻催化检查 ==========
            news_catalyst = self._check_news_catalyst(code, name)
            result['news_catalyst'] = news_catalyst
            if news_catalyst:
                result['limit_up_reason_source'].append('新闻')
                result['limit_up_reason_tags'].append('新闻催化')
                result['evidence'].append(f"新闻催化: {news_catalyst['title'][:50]}")

            # ========== 6. 计算可信度 ==========
            confidence, level = self._calc_confidence(
                theme_score=result['theme_score'],
                is_hot=theme_result.get('is_hot_topic', False),
                has_announcement=announcement_catalyst is not None,
                has_news=news_catalyst is not None,
                has_business=bool(business),
                business_match=self._check_business_match(business, result['core_theme']),
                has_concepts=bool(concepts),
            )
            result['limit_up_reason_confidence'] = confidence
            result['limit_up_reason_level'] = level

            # ========== 7. 生成主要原因描述 ==========
            result['limit_up_reason'] = self._generate_main_reason(
                core_theme=result['core_theme'],
                is_hot=theme_result.get('is_hot_topic', False),
                announcement=announcement_catalyst,
                news=news_catalyst,
                business_match=self._check_business_match(business, result['core_theme']),
                level=level,
            )

            # 去重标签
            result['limit_up_reason_tags'] = list(dict.fromkeys(result['limit_up_reason_tags']))
            result['limit_up_reason_source'] = list(dict.fromkeys(result['limit_up_reason_source']))

        except Exception as e:
            print(f"[LimitUpReason] 分析异常({code}): {e}")
            result['limit_up_reason'] = f'原因分析异常: {e}'
            result['limit_up_reason_confidence'] = 0
            result['limit_up_reason_level'] = 'C'

        return result

    def _get_business_scope(self, code):
        """
        获取主营业务范围（从东方财富F10 CompanySurvey接口）

        返回：
            str: 主营业务描述文本，失败返回空字符串
        """
        # 缓存检查
        cache_key = f'business_{code}'
        if cache_key in self._business_cache:
            if time.time() - self._business_cache_time.get(cache_key, 0) < self._cache_expire:
                return self._business_cache[cache_key]

        try:
            market = 'SH' if code.startswith('6') else 'SZ'
            url = f'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={market}{code}'
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return ''

            data = r.json()
            if data.get('jbzl') and len(data['jbzl']) > 0:
                jbzl = data['jbzl'][0]
                business = jbzl.get('BUSINESS_SCOPE', '')
                if business:
                    # 截断过长文本
                    business = business[:500]
                    self._business_cache[cache_key] = business
                    self._business_cache_time[cache_key] = time.time()
                    return business
        except Exception as e:
            print(f"[LimitUpReason] 获取主营业务失败({code}): {e}")

        return ''

    def _check_announcement_catalyst(self, code):
        """
        检查是否有公告刺激

        返回：
            dict or None: {'type': '合同订单', 'title': '...', 'date': '...'}
        """
        try:
            from data.announcement_provider import get_announcement_provider
            provider = get_announcement_provider()
            announcements = provider.get_announcements(code, count=10)
            if not announcements:
                return None

            # 只看最近7天的公告
            from datetime import datetime, timedelta
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            for ann in announcements:
                ann_date = ann.get('date', '')
                if ann_date and ann_date < seven_days_ago:
                    continue

                title = ann.get('title', '')
                if not title:
                    continue

                # 匹配刺激关键词
                for cat_type, keywords in ANNOUNCEMENT_CATALYST_KEYWORDS.items():
                    for kw in keywords:
                        if kw in title:
                            return {
                                'type': cat_type,
                                'title': title,
                                'date': ann_date,
                                'url': ann.get('url', ''),
                            }
        except Exception as e:
            print(f"[LimitUpReason] 公告检查异常({code}): {e}")

        return None

    def _check_news_catalyst(self, code, name):
        """
        检查是否有新闻催化

        返回：
            dict or None: {'title': '...', 'source': '...'}
        """
        try:
            from news_engine.news_manager import get_news_manager
            manager = get_news_manager()
            news_list = manager.get_news(code, name, use_cache=True)
            if not news_list:
                return None

            # 只看最近3天的新闻，匹配热点关键词
            from datetime import datetime, timedelta
            three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

            for news in news_list[:10]:
                news_date = news.get('date', '') or news.get('publish_time', '')
                if news_date and str(news_date)[:10] < three_days_ago:
                    continue

                title = news.get('title', '') or news.get('content', '')[:100]
                if not title:
                    continue

                for kw in NEWS_CATALYST_KEYWORDS:
                    if kw in title:
                        return {
                            'title': title,
                            'source': news.get('source', ''),
                            'keyword': kw,
                        }
        except Exception as e:
            print(f"[LimitUpReason] 新闻检查异常({code}): {e}")

        return None

    def _check_business_match(self, business, core_theme):
        """
        检查主营业务是否与核心题材匹配

        返回：
            bool: 是否匹配
        """
        if not business or not core_theme:
            return False

        # 用concept_service的业务关键词提取逻辑判断
        try:
            from service.concept_service import extract_concepts_from_business
            extracted = extract_concepts_from_business(business)
            for item in extracted:
                if item.get('name') == core_theme or core_theme in item.get('name', '') or item.get('name', '') in core_theme:
                    return True
                # 模糊匹配
                if item.get('confidence', 0) >= 0.6 and item.get('keyword', '') in business:
                    # 检查提取的概念是否与核心题材相关
                    if any(kw in core_theme for kw in [item.get('keyword', '')]):
                        return True
        except Exception:
            pass

        # 简单关键词匹配
        theme_keywords = {
            '人工智能': ['AI', '人工智能', '大模型', '算法', '智能'],
            '算力': ['算力', '服务器', '数据中心', 'IDC', '云计算'],
            '芯片': ['芯片', '半导体', '集成电路', '封装', '测试'],
            '机器人': ['机器人', '减速器', '伺服', '电机', '自动化'],
            '储能': ['储能', '电池', '锂电', '光伏'],
            '新能源汽车': ['汽车', '新能源', '电动车', '整车'],
            '军工': ['军工', '国防', '航天', '航空', '兵器'],
            '华为产业链': ['华为', '鸿蒙', '昇腾', '鲲鹏'],
            '创新药': ['创新药', '生物医药', '制药', '医药'],
            '光伏': ['光伏', '太阳能', '组件', '硅料'],
        }

        if core_theme in theme_keywords:
            for kw in theme_keywords[core_theme]:
                if kw in business:
                    return True

        return False

    def _calc_confidence(self, theme_score, is_hot, has_announcement, has_news,
                         has_business, business_match, has_concepts):
        """
        计算原因可信度（0-100）

        算法设计：
        - 基础分：20分（有基本数据）
        - 概念匹配度：theme_score降权，最多18分（避免题材关联度直接等于原因可信度）
        - 主营匹配：+12分
        - 市场热点：+15分
        - 公告刺激：+25分（A级必要条件之一）
        - 新闻催化：+10分
        - 上限100

        分级：
        - A级（≥80）：必须有公告刺激 或 市场热点+主营匹配
        - B级（60-79）：有概念+主营，或有新闻催化
        - C级（<60）：只有概念标签，无明确催化
        """
        score = 20  # 基础分

        # 概念匹配度（降权，最多18分）
        concept_score = min(theme_score, 60) * 0.3
        score += concept_score

        # 主营匹配
        if business_match:
            score += 12
        elif has_business:
            score += 3  # 有主营但不匹配，少量加分

        # 市场热点
        if is_hot:
            score += 15

        # 公告刺激（权重最高）
        if has_announcement:
            score += 25

        # 新闻催化
        if has_news:
            score += 10

        # 有概念数据
        if has_concepts:
            score += 2

        score = min(score, 100)
        score = max(score, 0)
        score = round(score, 1)

        if score >= 80:
            level = 'A'
        elif score >= 60:
            level = 'B'
        else:
            level = 'C'

        return score, level

    def _generate_main_reason(self, core_theme, is_hot, announcement, news,
                              business_match, level):
        """生成主要原因描述"""
        parts = []

        # 核心题材
        if core_theme:
            if is_hot:
                parts.append(f'{core_theme}方向市场热点')
            else:
                parts.append(f'{core_theme}概念')

        # 主营匹配
        if business_match:
            parts.append('主营业务相关')

        # 公告刺激
        if announcement:
            parts.append(f'{announcement["type"]}公告刺激')

        # 新闻催化
        if news:
            parts.append('新闻催化')

        if not parts:
            return '暂无明确涨停原因，可能为个股独立行情或资金推动'

        # 根据可信度调整语气
        if level == 'A':
            prefix = '主要原因：'
        elif level == 'B':
            prefix = '可能原因：'
        else:
            prefix = '推测原因：'

        return prefix + '，'.join(parts)


# 单例获取函数
_limit_up_reason_engine = None


def get_limit_up_reason_engine():
    """获取涨停原因增强引擎单例"""
    global _limit_up_reason_engine
    if _limit_up_reason_engine is None:
        _limit_up_reason_engine = LimitUpReasonEngine()
    return _limit_up_reason_engine


if __name__ == '__main__':
    print('=' * 60)
    print('V1.3-A-3 涨停原因增强引擎 测试')
    print('=' * 60)

    engine = get_limit_up_reason_engine()

    test_stocks = [
        ('000402', '金融街'),
        ('300750', '宁德时代'),
        ('688981', '中芯国际'),
    ]

    for code, name in test_stocks:
        print(f'\n{"="*60}')
        print(f'{name} ({code})')
        print('=' * 60)

        result = engine.analyze(code, name)

        print(f'主要原因: {result["limit_up_reason"]}')
        print(f'可信度: {result["limit_up_reason_confidence"]} ({result["limit_up_reason_level"]}级)')
        print(f'核心题材: {result["core_theme"]} (题材分:{result["theme_score"]})')
        print(f'原因标签: {result["limit_up_reason_tags"]}')
        print(f'数据来源: {result["limit_up_reason_source"]}')
        print(f'公告催化: {result["announcement_catalyst"]}')
        print(f'新闻催化: {result["news_catalyst"]}')
        print(f'判断依据:')
        for e in result['evidence'][:5]:
            print(f'  - {e}')

    print('\n' + '=' * 60)
    print('测试完成')
