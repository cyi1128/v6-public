# -*- coding: utf-8 -*-
"""
V1.3-A-5-DEV Step1：模拟涨停股票数据生成器
生成100只模拟涨停股票，用于压力测试。

不修改任何FROZEN模块，仅用于测试。
"""
import random
from datetime import datetime


# 模拟股票名称池
STOCK_NAMES = [
    '传智教育', '美利云', '奥瑞德', '欣天科技', '科大讯飞', '中科曙光',
    '浪潮信息', '紫光股份', '中兴通讯', '烽火通信', '亨通光电', '中天科技',
    '工业富联', '沪电股份', '深南电路', '生益科技', '鹏鼎控股', '立讯精密',
    '歌尔股份', '蓝思科技', '领益智造', '信维通信', '硕贝德', '麦捷科技',
    '顺络电子', '三环集团', '风华高科', '国瓷材料', '洁美科技', '长盈精密',
    '精研科技', '科森科技', '恒铭达', '智动力', '飞荣达', '中石科技',
    '碳元科技', '思泉新材', '中光防雷', '金信诺', '盛路通信', '武汉凡谷',
    '大富科技', '春兴精工', '世嘉科技', '通宇通讯', '摩比发展', '鸿博股份',
    '金溢科技', '聚龙股份', '神思电子', '东方网力', '佳都科技', '云从科技',
    '商汤科技', '旷视科技', '依图科技', '格灵深瞳', '虹软科技', '当虹科技',
    '数码视讯', '捷成股份', '华策影视', '光线传媒', '华谊兄弟', '唐德影视',
    '慈文传媒', '欢瑞世纪', '新文化', '华录百纳', '北京文化', '当代文体',
    '中体产业', '莱茵体育', '探路者', '信隆健康', '牧高笛', '三夫户外',
    '雪人股份', '冰轮环境', '汉钟精机', '开山股份', '通裕重工', '金雷股份',
    '日月股份', '天顺风能', '泰胜风能', '金风科技', '明阳智能', '运达股份',
    '电气风电', '三一重能', '禾望电气', '盛弘股份', '科华数据', '英维克',
    '申菱环境', '高澜股份', '飞荣达', '中石科技', '碳元科技', '思泉新材',
]

# 模拟行业/概念池
INDUSTRIES = [
    'AI算力', '人工智能', '数据中心', '云计算', '大数据', '5G概念',
    '通信设备', '芯片', '半导体', '消费电子', '新能源', '光伏概念',
    '储能', '充电桩', '新能源车', '机器人', '工业母机', '军工',
    '医药生物', '医疗器械', '白酒', '食品饮料', '房地产', '基建',
]

# 连板高度分布（模拟真实市场）
CONSECUTIVE_DIST = [1] * 60 + [2] * 20 + [3] * 10 + [4] * 5 + [5] * 3 + [6] * 1 + [7] * 1


def generate_mock_limit_up_stocks(count=100, seed=None):
    """
    生成模拟涨停股票列表

    参数：
        count: 生成数量，默认100只
        seed: 随机种子，用于复现测试结果

    返回：
        list: 涨停股票列表，格式与 market.limit_up_center.get_today_limit_up_stocks() 一致
    """
    if seed is not None:
        random.seed(seed)

    stocks = []
    used_codes = set()
    used_names = set()

    for i in range(count):
        # 生成唯一股票代码
        while True:
            code = f"{random.choice(['00', '30', '60'])}{random.randint(0, 9999):04d}"
            if code not in used_codes:
                used_codes.add(code)
                break

        # 生成唯一股票名称
        while True:
            name = random.choice(STOCK_NAMES)
            if name not in used_names:
                used_names.add(name)
                break

        # 连板高度
        lbc = random.choice(CONSECUTIVE_DIST)

        # 涨跌幅（涨停，9.9%-10.1%之间）
        pct_chg = round(random.uniform(9.9, 10.1), 2)
        if code.startswith('30'):  # 创业板20%涨停
            pct_chg = round(random.uniform(19.9, 20.1), 2)

        # 价格
        price = round(random.uniform(5, 100), 2)

        # 换手率
        turnover = round(random.uniform(1, 30), 2)

        # 成交额（亿元）
        amount = random.randint(1, 100) * 100000000

        # 行业/概念
        industry = random.choice(INDUSTRIES)

        stock = {
            'code': code,
            'name': name,
            'price': price,
            'pct_chg': pct_chg,
            'turnover': turnover,
            'amount': amount,
            'industry': industry,
            'reason': industry,
            'lbc': lbc,
            'pool': '今日涨停',
            # 模拟涨停时间（09:30 - 14:55）
            'first_limit_time': f"{random.randint(9, 14):02d}:{random.randint(0, 59):02d}",
        }
        stocks.append(stock)

    # 按连板高度降序排序（模拟真实涨停池排序）
    stocks.sort(key=lambda x: (-x['lbc'], x['first_limit_time']))

    return stocks


def generate_mock_card_data(code, name, industry='算力', lbc=1):
    """
    生成模拟卡片数据（用于快速UI渲染测试，不调用实际分析引擎）

    参数：
        code: 股票代码
        name: 股票名称
        industry: 行业
        lbc: 连板数

    返回：
        dict: 与 analyze_and_format() 返回格式一致的 card_data
    """
    score = random.randint(40, 95)
    if score >= 80:
        level = 'A'
    elif score >= 60:
        level = 'B'
    else:
        level = 'C'

    business_levels = ['S', 'A', 'B', 'C']
    business_texts = {
        'S': '主营高度匹配',
        'A': '主营相关度高',
        'B': '主营部分相关',
        'C': '主营关联度低',
    }
    business_level = random.choice(business_levels)
    business_score = {'S': 15, 'A': 12, 'B': 8, 'C': 4}[business_level]

    hot_score = random.randint(0, 12)
    announcement_levels = ['L0', 'L1', 'L2', 'L3']
    announcement_level = random.choice(announcement_levels)
    announcement_score = {'L0': 0, 'L1': 5, 'L2': 10, 'L3': 15}[announcement_level]
    news_score = random.randint(0, 10)

    return {
        'code': code,
        'name': name,
        'basic_info': {
            'code': code,
            'name': name,
            'reason_text': f'{name}因{industry}概念涨停',
        },
        'confidence': {
            'level': level,
            'score': score,
            'description': f'{level}级可信度',
        },
        'core_theme': {
            'theme': industry,
            'theme_score': 15,
            'related_concepts': [industry, '人工智能', '大数据'],
        },
        'business': {
            'level': business_level,
            'text': business_texts[business_level],
            'score': business_score,
            'is_supported': business_level in ['S', 'A'],
            'icon': '✅' if business_level in ['S', 'A'] else '❌',
            'main_business': f'{name}主营{industry}相关业务',
        },
        'hot': {
            'is_hot': hot_score > 0,
            'hot_score': hot_score,
            'hot_level': f'H{min(3, (hot_score + 3) // 4)}' if hot_score > 0 else '无',
            'reason': f'{industry}板块今日涨停{random.randint(3, 20)}家',
            'source': '涨停池统计',
            'limit_up_count': random.randint(3, 20),
            'relation_text': f'强度H{min(3, (hot_score + 3) // 4)}' if hot_score > 0 else '非热点',
        },
        'announcement': {
            'level': announcement_level,
            'score': announcement_score,
            'text': '无重大公告' if announcement_level == 'L0' else f'存在{announcement_level}级公告催化',
            'icon': '📋' if announcement_level == 'L0' else '⭐',
            'is_level1': announcement_level != 'L0',
            'catalyst': None if announcement_level == 'L0' else '重大合同签订',
        },
        'news': {
            'has_news': news_score > 0,
            'score': news_score,
            'text': '暂无重大催化' if news_score == 0 else '存在新闻催化',
            'icon': '📰' if news_score > 0 else '📰',
            'news_count': random.randint(0, 10),
        },
        'score_breakdown': [
            {'label': '基础分', 'score': 15},
            {'label': '主题分', 'score': 15},
            {'label': '主营匹配', 'score': business_score},
            {'label': '热点分', 'score': hot_score},
            {'label': '公告分', 'score': announcement_score},
            {'label': '新闻分', 'score': news_score},
            {'label': '连板加成', 'score': min(lbc * 2, 10)},
        ],
        'total_score': score,
        'risk_warnings': [
            {'level': 'warning', 'text': '⚠ 涨停封单不稳定，注意开板风险'} if random.random() > 0.5 else {'level': 'info', 'text': 'ℹ 当前市场情绪偏谨慎'},
            {'level': 'info', 'text': f'ℹ {industry}板块近期波动较大'} if random.random() > 0.5 else {'level': 'warning', 'text': '⚠ 短期涨幅较大，注意回调风险'},
        ],
        'evidence_chain': [
            {'step': 1, 'text': f'{industry}板块今日强势', 'source': '涨停池统计'},
            {'step': 2, 'text': f'{name}主营{business_texts[business_level]}', 'source': '主营匹配'},
            {'step': 3, 'text': f'涨停原因：{industry}概念催化', 'source': '综合分析'},
        ],
    }


if __name__ == '__main__':
    # 测试生成
    stocks = generate_mock_limit_up_stocks(100, seed=42)
    print(f"生成 {len(stocks)} 只模拟涨停股票")
    print(f"连板分布:")
    from collections import Counter
    lbc_counter = Counter(s['lbc'] for s in stocks)
    for lbc in sorted(lbc_counter.keys(), reverse=True):
        print(f"  {lbc}连板: {lbc_counter[lbc]}只")
    print(f"\n前5只:")
    for s in stocks[:5]:
        print(f"  {s['name']} ({s['code']}) {s['lbc']}连板 {s['industry']} +{s['pct_chg']}%")
