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


# ========== 题材标签三级分类（V1.3-A-3.1 新增） ==========
# 一级：有效产业题材（可作为涨停原因核心方向）
TAG_CATEGORY_INDUSTRY = [
    # 科技
    '人工智能', 'AI应用', 'AI智能体', '大模型', '算力', '服务器', '数据中心', '云计算',
    '芯片', '半导体', '集成电路', '国产芯片', 'PCB', '光模块', 'CPO', 'F5G',
    '通信设备', '5G概念', '6G概念', '量子科技', '机器人', '人形机器人', '减速器',
    '自动驾驶', '无人驾驶', '智能驾驶', '车联网', '边缘计算', '信创', '国产软件',
    '数字经济', '数据要素', '网络安全', '虚拟现实', '元宇宙',
    # 新能源
    '储能', '锂电', '锂电池', '固态电池', '光伏', '太阳能', '氢能源', '燃料电池',
    '新能源车', '新能源汽车', '充电桩', '换电概念', '超级电容',
    # 高端制造
    '军工', '国防军工', '航空航天', '大飞机', '商业航天', '工业母机', '智能制造',
    '高端装备', '自动化设备', '工业机器人',
    # 医药
    '创新药', '生物医药', '医疗器械', 'CXO', '体外诊断', 'CAR-T细胞疗法',
    '辅助生殖', '医美概念', '精准医疗',
    # 消费（仅催化时）
    '白酒', '食品饮料', '免税概念',
    # 教育（V1.3-A-3.1-OPT Step5 补全）
    '教育', '职业教育', '在线教育', '教育信息化', '培训',
]

# 二级：辅助标签（不能单独作为涨停原因，必须结合产业题材）
TAG_CATEGORY_AUXILIARY = [
    '央企改革', '央国企改革', '国企改革', '沪企改革', '专精特新', '高新技术企业',
    '华为概念', '鸿蒙概念', '昇腾', '鲲鹏', '华为汽车', '华为产业链',
    '百度概念', '阿里概念', '腾讯概念', '字节概念', '抖音概念',
    '一带一路', '雄安新区', '长三角', '成渝特区', '深圳特区', '江苏板块', '浙江板块',
    '上证380', '中证500', '创业板指', '转债标的',
    '储能概念', '新能源车', '人工智能',  # 带"概念"后缀的变体，统一处理
]

# 三级：禁止标签（直接过滤，不参与原因分析）
TAG_CATEGORY_FORBIDDEN = [
    # 资金/股东类
    '举牌', '破净', '破发股', '融资融券', '深股通', '沪股通', '北向资金',
    '机构持仓', '基金重仓', '股东增持', '股东减持', '股权质押',
    # 行情/技术类
    '昨日涨停', '昨日连板', '近期新高', '百日新高', '近期摘帽', '高市净率',
    '低市盈率', '高股息', '低价股', '小盘股', '大盘股',
    # 财报类（非催化）
    '2026中报预增', '2026中报预减', '2026中报扭亏', '2026中报首亏',
    '2026中报预增', '业绩预告', '财报披露',
    # 地域/指数类
    '上证380', '中证500', '创业板综', '深证成指', '沪深300',
    # 其他
    'ST板块', '退市风险', '昨日打二板以上表现', '题材股', '独角兽',
]


def _classify_tag(tag):
    """
    分类单个题材标签（V1.3-A-3.1 新增）

    返回：
        str: 'industry' / 'auxiliary' / 'forbidden' / 'unknown'
    """
    if not tag:
        return 'unknown'
    tag_clean = tag.strip()
    # 精确匹配禁止标签
    for f in TAG_CATEGORY_FORBIDDEN:
        if tag_clean == f or f in tag_clean:
            return 'forbidden'
    # 精确匹配产业标签
    for i in TAG_CATEGORY_INDUSTRY:
        if tag_clean == i or i in tag_clean or tag_clean in i:
            return 'industry'
    # 精确匹配辅助标签
    for a in TAG_CATEGORY_AUXILIARY:
        if tag_clean == a or a in tag_clean or tag_clean in a:
            return 'auxiliary'
    return 'unknown'


# ========== 公告催化三级分类（V1.3-A-3.1 第3步重构） ==========
# 一级催化⭐⭐⭐：+25分，可进入A级原因
ANNOUNCEMENT_LEVEL_1 = {
    '重大重组': ['重大资产重组', '发行股份购买资产', '借壳', '控制权变更', '实控人变更'],
    '并购收购': ['收购资产', '并购', '资产注入', '吸收合并'],
    '重大合同': ['重大合同', '重大订单', '中标重大', '签订重大', '重大项目中标', '框架协议(重大)'],
    '业绩超预期': ['业绩大幅增长', '净利润大幅增长', '业绩预增', '扭亏为盈', '营收大幅增长'],
    '政策受益': ['重大政策', '国家扶持', '入选国家', '国家级项目', '重大补贴'],
}

# 二级催化⭐⭐：+12分，进入B级原因
ANNOUNCEMENT_LEVEL_2 = {
    '战略合作': ['战略合作', '产业合作', '技术合作', '合作框架', '联合研发'],
    '技术突破': ['技术突破', '研发成功', '专利获得', '新产品发布', '量产'],
    '股权变化': ['股权转让', '引入战略投资者', '定增', '募资', '股权激励'],
    '增持回购': ['股东增持', '增持计划', '回购方案', '回购预案'],
}

# 三级公告⭐：+0分，仅展示不加分
ANNOUNCEMENT_LEVEL_3 = {
    '常规回购': ['回购股份', '首次回购', '回购完成', '回购进展'],
    '分红': ['分红', '利润分配', '中期分红', '年度分红', '权益分派'],
    '例行公告': ['股东持股', '前十大股东', '会计政策变更', '定期报告', '季报', '年报', '半年报',
                '年度报告', '半年度报告', '季度报告', '业绩预告', '业绩快报'],
    '董监高变动': ['董事长辞职', '高管变动', '董事变动', '监事变动'],
    '重组进展': ['重组进展', '重组问询', '重组回复', '延期复牌', '停牌公告'],
    '减持': ['股东减持', '减持计划', '减持进展', '减持股份', '减持比例'],
}

# 程序性公告过滤：即使包含一级关键词，也不进入一级
# 用于过滤"重大资产重组进展公告""重大资产购买问询函回复"等程序性公告
ANNOUNCEMENT_PROCEDURAL_KEYWORDS = [
    '进展', '问询', '回复', '延期', '停牌', '复牌', '更正', '补充',
    '提示性', '风险提示', '核查', '监管', '关注函', '告知函',
    '股东减持', '减持计划', '减持进展',
]


def _classify_announcement(title):
    """
    公告标题三级分类（V1.3-A-3.1 第3步新增）

    参数：
        title: str，公告标题

    返回：
        dict: {'level': 1/2/3, 'type': str, 'score': 25/12/0}
        无匹配返回 None
    """
    if not title:
        return None

    # 先检查程序性公告关键词（优先降级）
    is_procedural = any(kw in title for kw in ANNOUNCEMENT_PROCEDURAL_KEYWORDS)

    # 一级匹配
    for cat_type, keywords in ANNOUNCEMENT_LEVEL_1.items():
        for kw in keywords:
            if kw in title:
                if is_procedural:
                    # 程序性公告降级为三级
                    return {'level': 3, 'type': f'{cat_type}(程序性)', 'score': 0}
                return {'level': 1, 'type': cat_type, 'score': 25}

    # 二级匹配
    for cat_type, keywords in ANNOUNCEMENT_LEVEL_2.items():
        for kw in keywords:
            if kw in title:
                if is_procedural:
                    return {'level': 3, 'type': f'{cat_type}(程序性)', 'score': 0}
                return {'level': 2, 'type': cat_type, 'score': 12}

    # 三级匹配
    for cat_type, keywords in ANNOUNCEMENT_LEVEL_3.items():
        for kw in keywords:
            if kw in title:
                return {'level': 3, 'type': cat_type, 'score': 0}

    return None


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
            'announcement_level': 0,
            'news_catalyst': None,
            'business_match_level': 'C',
            'business_match_score': 0,
            'score_breakdown': {},
            'reason_evidence': {},
            # V1.3-A-3.1-OPT Step3 新增：市场热点检测字段
            'hot_score': 0,
            'hot_source': '',
            'hot_confidence': '',
            'hot_reason': '',
            'hot_relation_level': '',
            'data_source': 'limit_up_reason_engine',
            'timestamp': time.time(),
        }

        try:
            # ========== 1. 获取概念数据 + 三级过滤（V1.3-A-3.1） ==========
            from service.concept_service import get_stock_concepts
            concepts, concept_source = get_stock_concepts(code)
            if concepts:
                result['limit_up_reason_source'].append('概念')
                result['evidence'].append(f'概念来源: {concept_source}，共{len(concepts)}个概念')

            # V1.3-A-3.1 新增：题材标签三级过滤
            filter_result = self._filter_concepts(concepts)
            concepts_for_analysis = filter_result['filtered_concepts']
            industry_tags = filter_result['industry_tags']
            auxiliary_tags = filter_result['auxiliary_tags']
            forbidden_tags = filter_result['forbidden_tags']

            if forbidden_tags:
                result['evidence'].append(f'已过滤禁止标签: {", ".join(forbidden_tags[:5])}')
            if auxiliary_tags:
                result['evidence'].append(f'辅助标签(不能单独成原因): {", ".join(auxiliary_tags[:5])}')

            # ========== 2. 获取主营业务 ==========
            business = self._get_business_scope(code)
            if business:
                result['limit_up_reason_source'].append('F10主营')

            # ========== 3. 题材关联分析（复用已有模块） ==========
            from strategy.theme_reason_analyzer import analyze_stock_theme
            pct = 10.0  # 涨停股默认涨幅10%
            if limit_up_data:
                pct = limit_up_data.get('pct_chg', 10.0)

            theme_result = analyze_stock_theme(code, name, concepts_for_analysis, pct, business)
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

            # ========== 3.5 市场热点检测（V1.3-A-3.1-OPT Step3 集成） ==========
            # 使用 market_hot_detector 替代原有的 theme_analyzer 热点判断
            # P0涨停池统计优先，P1概念行情降级，不修改评分公式
            from strategy.market_hot_detector import calc_stock_hot_score
            # 从limit_up_data中推断日期（如果有），否则默认当天
            hot_date = None
            if limit_up_data and limit_up_data.get('trade_date'):
                hot_date = limit_up_data['trade_date']
            # 热点检测需要包含行业板块标签（P0涨停池统计基于行业板块）
            hot_concepts_for_detection = list(set(concepts_for_analysis + industry_tags))
            hot_info = calc_stock_hot_score(
                stock_concepts=hot_concepts_for_detection,
                business_match_level=result['business_match_level'],
                date=hot_date,
                limit_up_pool=None,  # 后续可从外部传入涨停池优化
            )
            # 用新模块的热点判断覆盖原有theme_result的is_hot_topic
            theme_result['is_hot_topic'] = hot_info['is_hot_topic']
            # 保存热点详细信息到result
            result['hot_score'] = hot_info['hot_score']
            result['hot_source'] = hot_info['hot_source']
            result['hot_confidence'] = hot_info['hot_confidence']
            result['hot_reason'] = hot_info['hot_reason']
            result['hot_relation_level'] = hot_info['hot_relation_level']
            if hot_info['hot_reason']:
                result['evidence'].append(f"热点检测({hot_info['hot_source']}): {hot_info['hot_reason']}")

            if theme_result.get('is_hot_topic'):
                result['limit_up_reason_tags'].append('市场热点')

            # ========== 4. 公告催化等级检查（V1.3-A-3.1 第3步重构） ==========
            announcement_catalyst = self._check_announcement_catalyst(code)
            result['announcement_catalyst'] = announcement_catalyst
            if announcement_catalyst:
                ann_level = announcement_catalyst.get('level', 0)
                result['announcement_level'] = ann_level
                result['limit_up_reason_source'].append('公告')
                if ann_level in [1, 2]:
                    # 一级/二级：有效催化，加入标签
                    result['limit_up_reason_tags'].append(announcement_catalyst['type'])
                    result['evidence'].append(
                        f"公告催化(L{ann_level}, +{announcement_catalyst.get('score', 0)}分): {announcement_catalyst['title'][:50]}"
                    )
                else:
                    # 三级：仅展示不加分
                    result['evidence'].append(
                        f"公告记录(L3, 不加分): {announcement_catalyst['title'][:50]}"
                    )

            # ========== 5. 新闻催化检查 ==========
            news_catalyst = self._check_news_catalyst(code, name)
            result['news_catalyst'] = news_catalyst
            if news_catalyst:
                result['limit_up_reason_source'].append('新闻')
                result['limit_up_reason_tags'].append('新闻催化')
                result['evidence'].append(f"新闻催化: {news_catalyst['title'][:50]}")

            # ========== 6. 主营匹配等级检查（V1.3-A-3.1 第2步重构） ==========
            business_match_result = self._check_business_match(business, result['core_theme'])
            result['business_match_level'] = business_match_result['level']
            result['business_match_score'] = business_match_result['score']
            if business_match_result.get('evidence'):
                result['evidence'].append(
                    f"主营匹配({business_match_result['level']}级): {business_match_result['evidence']}"
                )

            # ========== 7. 计算可信度（V1.3-A-3.1 第4步重构） ==========
            # 连板天数
            consecutive_days = 0
            if limit_up_data:
                consecutive_days = limit_up_data.get('consecutive_days', 0) or 0

            # 新闻是否匹配核心产业题材
            news_matches_theme = False
            if news_catalyst:
                news_kw = news_catalyst.get('keyword', '')
                core = result['core_theme']
                if news_kw and (news_kw in core or core in news_kw):
                    news_matches_theme = True
                elif core in ['人工智能', 'AI', '算力', '芯片', '半导体', '机器人', '储能', '光伏', '新能源车', '军工', '创新药', '数据中心', '云计算', 'CPO', '光模块', 'PCB', '鸿蒙', '华为']:
                    news_matches_theme = True  # 核心题材本身就是产业方向，新闻默认匹配

            confidence, level, score_breakdown = self._calc_confidence(
                theme_score=result['theme_score'],
                is_hot=theme_result.get('is_hot_topic', False),
                has_announcement=announcement_catalyst.get('has_catalyst', False) if announcement_catalyst else False,
                has_news=news_catalyst is not None,
                has_business=bool(business),
                business_match=business_match_result['level'] in ['S', 'A'],
                has_concepts=bool(concepts),
                # 第4步新增参数
                business_match_score=result['business_match_score'],
                announcement_score=announcement_catalyst.get('score', 0) if announcement_catalyst else 0,
                consecutive_days=consecutive_days,
                has_industry_theme=len(industry_tags) > 0,
                news_matches_theme=news_matches_theme,
                business_match_level=result['business_match_level'],
                announcement_level=result['announcement_level'],
            )
            result['limit_up_reason_confidence'] = confidence
            result['limit_up_reason_level'] = level
            result['score_breakdown'] = score_breakdown

            # ========== 8. 生成主要原因描述（V1.3-A-3.1 第5步增强） ==========
            result['limit_up_reason'] = self._generate_main_reason(
                core_theme=result['core_theme'],
                is_hot=theme_result.get('is_hot_topic', False),
                announcement=announcement_catalyst,
                news=news_catalyst,
                business_match=business_match_result['level'] in ['S', 'A', 'B'],
                level=level,
                business_match_level=result['business_match_level'],
                announcement_level=result['announcement_level'],
            )

            # 构建结构化原因依据
            result['reason_evidence'] = self._build_reason_evidence(
                core_theme=result['core_theme'],
                is_hot=theme_result.get('is_hot_topic', False),
                announcement=announcement_catalyst,
                news=news_catalyst,
                business_match_level=result['business_match_level'],
                announcement_level=result['announcement_level'],
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

    def _filter_concepts(self, concepts):
        """
        题材标签三级过滤（V1.3-A-3.1 新增）

        对concept_service返回的全部标签进行分类过滤：
        - 一级产业题材：保留，参与核心题材选择
        - 二级辅助标签：保留但标记，不能单独作为原因
        - 三级禁止标签：直接移除

        参数：
            concepts: list[str]，原始概念标签列表

        返回：
            dict: {
                'industry_tags': list,    # 一级产业题材
                'auxiliary_tags': list,   # 二级辅助标签
                'forbidden_tags': list,   # 被过滤的三级标签
                'unknown_tags': list,     # 未分类标签（保留但低权重）
                'filtered_concepts': list # 过滤后用于theme分析的标签（一级+二级+unknown）
            }
        """
        if not concepts:
            return {
                'industry_tags': [],
                'auxiliary_tags': [],
                'forbidden_tags': [],
                'unknown_tags': [],
                'filtered_concepts': [],
            }

        industry_tags = []
        auxiliary_tags = []
        forbidden_tags = []
        unknown_tags = []

        for tag in concepts:
            category = _classify_tag(tag)
            if category == 'forbidden':
                forbidden_tags.append(tag)
            elif category == 'industry':
                industry_tags.append(tag)
            elif category == 'auxiliary':
                auxiliary_tags.append(tag)
            else:
                unknown_tags.append(tag)

        # 过滤后用于theme分析的标签：一级产业 + 二级辅助 + 未分类
        # 注意：辅助标签和unknown标签保留，但后续核心题材选择时产业标签优先
        filtered_concepts = industry_tags + auxiliary_tags + unknown_tags

        return {
            'industry_tags': industry_tags,
            'auxiliary_tags': auxiliary_tags,
            'forbidden_tags': forbidden_tags,
            'unknown_tags': unknown_tags,
            'filtered_concepts': filtered_concepts,
        }

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
        检查公告催化等级（V1.3-A-3.1 第3步重构）

        由返回简单dict改为返回带level/score的结构化结果。
        三级公告仅展示不加分，一级/二级才算有效催化。

        时间窗口：
        - 一级：涨停日前≤3个交易日
        - 二级：涨停日前≤7天
        - 三级：不限时间，仅展示

        返回：
            dict or None: {
                'has_catalyst': bool,   # 是否有催化（一级/二级为True，三级为False）
                'level': 1/2/3,         # 公告等级
                'type': str,            # 公告类型
                'score': 25/12/0,       # 对应可信度加分
                'title': str,           # 公告标题
                'date': str,            # 公告日期
                'url': str,             # 公告链接
                'evidence': str,        # 催化依据描述
            }
            无匹配公告返回 None
        """
        try:
            from data.announcement_provider import get_announcement_provider
            from datetime import datetime, timedelta

            provider = get_announcement_provider()
            announcements = provider.get_announcements(code, count=15)
            if not announcements:
                return None

            now = datetime.now()
            three_days_ago = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            seven_days_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')

            # 按日期倒序遍历，优先找最近的有效公告
            level1_result = None
            level2_result = None
            level3_result = None

            for ann in announcements:
                ann_date = ann.get('date', '')
                title = ann.get('title', '')
                if not title:
                    continue

                # 分类公告
                classified = _classify_announcement(title)
                if not classified:
                    continue

                level = classified['level']
                cat_type = classified['type']
                score = classified['score']

                # 时间窗口检查
                if level == 1 and ann_date and ann_date < three_days_ago:
                    continue  # 一级公告超过3天，无效
                if level == 2 and ann_date and ann_date < seven_days_ago:
                    continue  # 二级公告超过7天，无效
                # 三级公告不限时间

                result = {
                    'has_catalyst': level in [1, 2],
                    'level': level,
                    'type': cat_type,
                    'score': score,
                    'title': title,
                    'date': ann_date,
                    'url': ann.get('url', ''),
                    'evidence': f'{cat_type}公告(level{level}, +{score}分): {title[:40]}',
                }

                if level == 1 and not level1_result:
                    level1_result = result
                elif level == 2 and not level2_result:
                    level2_result = result
                elif level == 3 and not level3_result:
                    level3_result = result

                # 找到一级公告即可提前返回（优先级最高）
                if level1_result:
                    return level1_result

            # 没有一级，返回二级
            if level2_result:
                return level2_result
            # 没有二级，返回三级（仅展示）
            if level3_result:
                return level3_result

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
        检查主营业务与核心题材匹配等级（V1.3-A-3.1 第2步重构）

        由返回bool改为返回dict，支持S/A/B/C四级匹配。

        参数：
            business: str，主营业务描述
            core_theme: str，核心题材

        返回：
            dict: {
                'level': 'S'/'A'/'B'/'C',  # 匹配等级
                'score': 0-15,              # 对应可信度加分（S=15,A=10,B=5,C=0）
                'evidence': str,            # 匹配依据描述
                'matched_keywords': list,   # 命中的关键词
            }

        等级定义：
            S级(+15)：主营直接包含核心题材关键词
            A级(+10)：主营包含产业链上下游关键词
            B级(+5)：主营属于相关大行业
            C级(+0)：主营无支撑
        """
        default_result = {
            'level': 'C',
            'score': 0,
            'evidence': '主营无直接支撑，仅概念标签关联',
            'matched_keywords': [],
        }

        if not business or not core_theme:
            return default_result

        # ========== 产业链分级映射表 ==========
        # S: 主营直接相关  A: 产业链上下游  B: 行业相关
        business_match_map = {
            '芯片': {
                'S': ['芯片设计', '芯片制造', '半导体', '集成电路', '晶圆', '封测', '封装测试', 'EDA', '芯片'],
                'A': ['电子元器件', 'PCB', '印制电路板', '封装材料', '半导体设备', '光刻', '靶材', '电子特气'],
                'B': ['电子制造', '电子信息', '通信设备', '电子'],
            },
            '半导体': {
                'S': ['半导体', '芯片', '集成电路', '晶圆', '封测', 'EDA'],
                'A': ['电子元器件', 'PCB', '半导体设备', '光刻', '封装材料'],
                'B': ['电子制造', '电子信息', '通信设备'],
            },
            '算力': {
                'S': ['算力', '服务器', '数据中心', 'IDC', '云计算', 'GPU', 'AI芯片', '超算'],
                'A': ['服务器配件', '电源', '散热', '液冷', '光模块', '网络设备', '存储', '交换机', 'IT基础设施'],
                'B': ['电子制造', '通信设备', 'IT服务', '计算机', '软件'],
            },
            '人工智能': {
                'S': ['人工智能', 'AI', '大模型', '算法', '机器学习', '深度学习', '智能体', 'AIGC'],
                'A': ['软件', '计算机', '数据服务', '云计算', '智能硬件', '机器人', '视觉识别', '语音识别'],
                'B': ['电子信息', '通信', '自动化', 'IT服务'],
            },
            'AI应用': {
                'S': ['人工智能', 'AI', '大模型', '智能体', 'AIGC', 'AI应用'],
                'A': ['软件', '计算机', '数据服务', '云计算', '教育科技', '金融科技'],
                'B': ['电子信息', '通信', 'IT服务'],
            },
            '机器人': {
                'S': ['机器人', '工业机器人', '服务机器人', '人形机器人', '减速器', '伺服系统', '伺服电机'],
                'A': ['自动化设备', '工业控制', 'PLC', '电机', '精密制造', '机械臂'],
                'B': ['机械制造', '电子制造', '智能制造'],
            },
            '人形机器人': {
                'S': ['人形机器人', '机器人', '减速器', '伺服', '灵巧手'],
                'A': ['自动化设备', '工业控制', '电机', '精密制造', '传感器'],
                'B': ['机械制造', '电子制造', '智能制造'],
            },
            '储能': {
                'S': ['储能', '储能系统', '电化学储能', 'PCS', 'BMS', '电池管理'],
                'A': ['电池', '锂电', '锂电池', '光伏', '新能源', '电源', '逆变器'],
                'B': ['电力设备', '电子制造', '新能源汽车'],
            },
            '光伏': {
                'S': ['光伏', '太阳能', '组件', '硅料', '硅片', '电池片', '逆变器'],
                'A': ['新能源', '电力设备', '储能', '玻璃', '胶膜', '银浆'],
                'B': ['电力', '电子制造', '建材'],
            },
            '新能源车': {
                'S': ['新能源汽车', '电动车', '整车', '电动汽车', '新能源车'],
                'A': ['汽车零部件', '电池', '锂电', '电机', '电控', '充电桩', '汽车电子'],
                'B': ['汽车', '机械制造', '电子制造'],
            },
            '新能源汽车': {
                'S': ['新能源汽车', '电动车', '整车', '电动汽车'],
                'A': ['汽车零部件', '电池', '锂电', '电机', '电控', '充电桩'],
                'B': ['汽车', '机械制造', '电子制造'],
            },
            '军工': {
                'S': ['军工', '国防', '兵器', '航空航天', '导弹', '军用'],
                'A': ['航空', '航天', '电子对抗', '雷达', '通信', '特种材料'],
                'B': ['机械制造', '电子信息', '新材料'],
            },
            '创新药': {
                'S': ['创新药', '生物医药', '生物制药', '抗体', '基因治疗', 'CXO', 'CDMO'],
                'A': ['制药', '医药', '医疗器械', '体外诊断', '医疗服务'],
                'B': ['化工', '生物科技', '健康'],
            },
            '医疗器械': {
                'S': ['医疗器械', '医疗设备', '体外诊断', 'IVD', '影像设备'],
                'A': ['医药', '生物科技', '电子制造', '精密制造'],
                'B': ['化工', '健康', '电子信息'],
            },
            '数据中心': {
                'S': ['数据中心', 'IDC', '服务器', '云计算', '算力'],
                'A': ['网络设备', '存储', '电源', '散热', '光模块', 'IT基础设施'],
                'B': ['IT服务', '通信设备', '电子制造'],
            },
            '云计算': {
                'S': ['云计算', '云服务', '数据中心', '服务器', '算力', '虚拟化'],
                'A': ['软件', 'IT服务', '网络设备', '存储', '数据库'],
                'B': ['计算机', '电子信息', '通信'],
            },
            'CPO': {
                'S': ['CPO', '光模块', '光通信', '硅光', '共封装光学'],
                'A': ['通信设备', '光器件', '芯片', '电子元器件'],
                'B': ['电子制造', '通信', '计算机'],
            },
            '光模块': {
                'S': ['光模块', '光通信', '光器件', 'CPO', '硅光'],
                'A': ['通信设备', '芯片', '电子元器件', 'PCB'],
                'B': ['电子制造', '通信', '计算机'],
            },
            'PCB': {
                'S': ['PCB', '印制电路板', '电路板', 'FPC', '柔性电路板'],
                'A': ['电子元器件', '封装', '半导体', '通信设备', '消费电子'],
                'B': ['电子制造', '电子信息', '化工'],
            },
            '华为': {
                'S': ['华为', '鸿蒙', '昇腾', '鲲鹏', '华为产业链'],
                'A': ['通信设备', '芯片', '软件', '智能硬件', '汽车电子'],
                'B': ['电子制造', '通信', '计算机'],
            },
            '鸿蒙': {
                'S': ['鸿蒙', 'HarmonyOS', '华为', '操作系统'],
                'A': ['软件', '智能硬件', '物联网', '汽车电子'],
                'B': ['电子制造', '通信', '计算机'],
            },
            '环保': {
                'S': ['环保', '节能环保', '环境治理', '污水处理', '固废处理', '大气治理'],
                'A': ['新能源', '节能设备', '化工', '电力'],
                'B': ['机械制造', '公用事业', '建材'],
            },
            '房地产': {
                'S': ['房地产', '地产开发', '物业', '房地产开发'],
                'A': ['建筑', '建材', '家居', '装修'],
                'B': ['金融', '公用事业', '商业'],
            },
        }

        # 标准化core_theme（去掉"概念""概念股"后缀）
        theme_clean = core_theme
        if theme_clean.endswith('概念股'):
            theme_clean = theme_clean[:-3]
        elif theme_clean.endswith('概念'):
            theme_clean = theme_clean[:-2]

        # 查找映射表
        mapping = business_match_map.get(theme_clean)
        if not mapping:
            # 尝试模糊匹配映射表的key
            for key in business_match_map:
                if theme_clean in key or key in theme_clean:
                    mapping = business_match_map[key]
                    break

        if mapping:
            # S级匹配：主营直接相关
            for kw in mapping.get('S', []):
                if kw in business:
                    return {
                        'level': 'S',
                        'score': 15,
                        'evidence': f'主营直接相关：包含"{kw}"',
                        'matched_keywords': [kw],
                    }
            # A级匹配：产业链上下游
            for kw in mapping.get('A', []):
                if kw in business:
                    return {
                        'level': 'A',
                        'score': 10,
                        'evidence': f'产业链相关：包含"{kw}"',
                        'matched_keywords': [kw],
                    }
            # B级匹配：行业相关
            for kw in mapping.get('B', []):
                if kw in business:
                    return {
                        'level': 'B',
                        'score': 5,
                        'evidence': f'行业相关：包含"{kw}"',
                        'matched_keywords': [kw],
                    }

        # ========== 辅助：用concept_service提取主营概念判断 ==========
        try:
            from service.concept_service import extract_concepts_from_business
            extracted = extract_concepts_from_business(business)
            for item in extracted:
                item_name = item.get('name', '')
                if item_name == theme_clean or theme_clean in item_name or item_name in theme_clean:
                    if item.get('confidence', 0) >= 0.8:
                        return {
                            'level': 'S',
                            'score': 15,
                            'evidence': f'主营提取概念匹配：{item_name}',
                            'matched_keywords': [item_name],
                        }
                    elif item.get('confidence', 0) >= 0.5:
                        return {
                            'level': 'A',
                            'score': 10,
                            'evidence': f'主营提取概念相关：{item_name}',
                            'matched_keywords': [item_name],
                        }
        except Exception:
            pass

        # 无匹配 → C级
        return default_result

    def _calc_confidence(self, theme_score, is_hot, has_announcement, has_news,
                         has_business, business_match, has_concepts,
                         business_match_score=0, announcement_score=0,
                         consecutive_days=0, has_industry_theme=False,
                         news_matches_theme=False, business_match_level='C',
                         announcement_level=0):
        """
        计算原因可信度（0-100）V1.3-A-3.1 第4步重构

        新算法：
        - 基础分：15分（降低无催化股票基础可信度）
        - 产业题材匹配：theme_score * 0.25，最高15分（需产业标签有效）
        - 主营匹配：business_match_score（S=15/A=10/B=5/C=0，来自第2步）
        - 市场热点：+12分（需有产业题材匹配才生效）
        - 公告催化：announcement_score（一级25/二级12/三级0，来自第3步）
        - 新闻催化：+10分（需新闻匹配核心产业题材）
        - 连板背景：0/3/5/8分（反映市场关注度，非强弱判断）
        - 有概念数据：+2分
        - 上限100

        A级硬条件（不满足则最高79分）：
        - 评分 >= 80
        - 主营匹配 >= A级（S或A）
        - 且满足以下任意一个：
          - 一级公告
          - 市场热点 + 新闻催化
          - 市场热点 + 连板 >= 3

        返回：
            tuple: (score, level, score_breakdown)
        """
        breakdown = {
            'base': 15,
            'theme': 0,
            'business': 0,
            'hot': 0,
            'announcement': 0,
            'news': 0,
            'chain': 0,
            'concept': 0,
        }

        score = 15  # 基础分

        # 产业题材匹配（降权，最多15分）
        concept_score = min(theme_score, 60) * 0.25
        score += concept_score
        breakdown['theme'] = round(concept_score, 1)

        # 主营匹配（使用第2步分级结果）
        score += business_match_score
        breakdown['business'] = business_match_score

        # 市场热点（需有产业题材匹配才生效）
        if is_hot and has_industry_theme:
            score += 12
            breakdown['hot'] = 12

        # 公告催化（使用第3步分级结果）
        score += announcement_score
        breakdown['announcement'] = announcement_score

        # 新闻催化（需匹配核心产业题材）
        if has_news and news_matches_theme:
            score += 10
            breakdown['news'] = 10

        # 连板背景辅助分（反映市场关注度，非强弱判断）
        if consecutive_days >= 4:
            chain_score = 8
        elif consecutive_days == 3:
            chain_score = 5
        elif consecutive_days == 2:
            chain_score = 3
        else:
            chain_score = 0
        score += chain_score
        breakdown['chain'] = chain_score

        # 有概念数据
        if has_concepts:
            score += 2
            breakdown['concept'] = 2

        score = min(score, 100)
        score = max(score, 0)
        score = round(score, 1)

        # ========== A级硬条件判断 ==========
        if score >= 80:
            # 条件1：主营匹配 >= A级
            business_ok = business_match_level in ['S', 'A']
            # 条件2：催化来源
            catalyst_ok = (
                announcement_level == 1 or
                (is_hot and has_news) or
                (is_hot and consecutive_days >= 3)
            )
            if not (business_ok and catalyst_ok):
                # 不满足硬条件，降级为B级上限
                score = min(score, 79)
                breakdown['a_level_blocked'] = True
                breakdown['a_level_block_reason'] = (
                    f'主营={business_match_level}(需S/A), '
                    f'公告L{announcement_level}, 热点={is_hot}, 新闻={has_news}, 连板={consecutive_days}'
                )

        # 分级
        if score >= 80:
            level = 'A'
        elif score >= 60:
            level = 'B'
        else:
            level = 'C'

        breakdown['total'] = score
        breakdown['level'] = level

        return score, level, breakdown

    def _build_reason_evidence(self, core_theme, is_hot, announcement, news,
                               business_match_level='C', announcement_level=0):
        """
        构建原因依据结构化数据（V1.3-A-3.1 第5步新增）

        参数：
            core_theme: 核心题材
            is_hot: 是否市场热点
            announcement: 公告dict或None
            news: 新闻dict或None
            business_match_level: 主营匹配等级S/A/B/C
            announcement_level: 公告等级0/1/2/3

        返回：
            dict: {
                'theme': str,        # 产业方向
                'business': str,     # 主营匹配说明
                'announcement': str, # 公告催化说明
                'news': str,         # 新闻催化说明
                'hot': str,          # 热点说明
                'warning': str,      # 风险提示（可选）
            }
        """
        evidence = {}

        # 产业方向
        if core_theme:
            evidence['theme'] = f'{core_theme}产业方向'
        else:
            evidence['theme'] = '未明确产业方向'

        # 主营匹配说明
        business_desc = {
            'S': '主营高度匹配',
            'A': '主营产业链相关',
            'B': '主营弱相关',
            'C': '主营无直接支撑',
        }
        evidence['business'] = business_desc.get(business_match_level, '主营无直接支撑')

        # 公告催化说明
        if announcement_level == 1:
            ann_type = announcement.get('type', '重大') if announcement else '重大'
            evidence['announcement'] = f'一级公告催化：{ann_type}'
        elif announcement_level == 2:
            ann_type = announcement.get('type', '合作') if announcement else '合作'
            evidence['announcement'] = f'二级公告催化：{ann_type}'
        elif announcement_level == 3:
            evidence['announcement'] = '常规公告，不计催化'
        else:
            evidence['announcement'] = '无公告催化'

        # 新闻催化说明
        if news:
            evidence['news'] = '存在新闻催化'
        else:
            evidence['news'] = '无新闻催化'

        # 热点说明
        if is_hot:
            evidence['hot'] = '市场热点支持'
        else:
            evidence['hot'] = '非市场热点'

        # 风险提示（C级且缺少催化时）
        if business_match_level == 'C' and announcement_level == 0 and not news:
            evidence['warning'] = '当前涨停原因缺少直接催化证据，仅为概念推测'

        return evidence

    def _generate_main_reason(self, core_theme, is_hot, announcement, news,
                              business_match, level, business_match_level='C',
                              announcement_level=0):
        """
        生成主要原因描述（V1.3-A-3.1 第5步增强）

        输出格式：
        - A级：主要原因：XX方向 | 依据：主营S级、一级公告、热点、新闻
        - B级：可能原因：XX方向 | 依据：主营A级、热点支持
        - C级：推测原因：XX方向 | 依据：概念匹配、无主营支撑 | 提示：缺少催化

        参数：
            core_theme: 核心题材
            is_hot: 是否市场热点
            announcement: 公告dict或None
            news: 新闻dict或None
            business_match: bool，是否主营匹配（S/A级）
            level: A/B/C
            business_match_level: 主营匹配等级
            announcement_level: 公告等级

        返回：
            str: 原因描述文本
        """
        # 原因前缀
        level_prefix = {
            'A': '主要原因',
            'B': '可能原因',
            'C': '推测原因',
        }
        prefix = level_prefix.get(level, '推测原因')

        # 核心方向
        if core_theme:
            direction = f'{core_theme}方向'
        else:
            direction = '未明确方向'

        # 构建依据列表
        basis = []

        # 主营依据
        business_desc = {
            'S': '主营高度匹配',
            'A': '主营产业链相关',
            'B': '主营弱相关',
            'C': '主营无直接支撑',
        }
        basis.append(business_desc.get(business_match_level, '主营无直接支撑'))

        # 公告依据
        if announcement_level == 1:
            ann_type = announcement.get('type', '重大') if announcement else '重大'
            basis.append(f'一级公告：{ann_type}')
        elif announcement_level == 2:
            ann_type = announcement.get('type', '合作') if announcement else '合作'
            basis.append(f'二级公告：{ann_type}')
        elif announcement_level == 3:
            basis.append('常规公告（不计催化）')

        # 热点依据
        if is_hot:
            basis.append('市场热点支持')

        # 新闻依据
        if news:
            basis.append('新闻催化')

        # 组装文本
        reason_text = f'{prefix}：{direction}'
        if basis:
            reason_text += f' | 依据：{"、".join(basis)}'

        # C级风险提示
        if level == 'C' and business_match_level == 'C' and announcement_level == 0 and not news:
            reason_text += ' | 提示：缺少直接催化证据，仅为概念推测'

        return reason_text


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
