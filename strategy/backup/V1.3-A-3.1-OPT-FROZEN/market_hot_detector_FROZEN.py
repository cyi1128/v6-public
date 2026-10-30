# -*- coding: utf-8 -*-
"""
V1.3-A-3.1-OPT 第1步：市场热点检测器
仅实现 P0 涨停池统计（最高优先级、最可靠数据源）

设计原则：
- 低侵入性：独立模块，不修改现有评分公式
- 多源降级：P0涨停池统计 > P1涨停板块强度 > P2概念行情 > P3新闻热度
- 向上兼容：保留 is_hot_topic 字段，新增 hot_relation_level
- 当日缓存：统一缓存到 data/cache/hot_theme_cache.json

P0 评分规则：
  hot_score = 涨停数量分 + 连板强度分（最高12分）
  涨停数量分：≥10家+10, 5-9家+7, 3-4家+4, 1-2家+2
  连板强度分：最高连板≥5 +3, ≥3 +2, 存在2板 +1

热点关联等级（hot_relation_level）：
  H1 强热点：主营S/A级 + 题材属于热点
  H2 普通热点：概念标签匹配 + 主营B级
  H3 弱热点：只有概念标签 + 主营C级
"""
import os
import json
import time
import requests
from datetime import datetime

# 复用现有概念板块行情接口（P1备用源）
try:
    from strategy.theme_analyzer import get_concept_market
except ImportError:
    get_concept_market = None


# ========== 缓存配置 ==========
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'hot_theme_cache.json')

# 内存缓存（当日有效）
_memory_cache = {}


# ========== 概念-行业映射表 ==========
# P0涨停池统计基于东方财富行业板块(hybk)，但F10概念是概念标签
# 此映射表用于将F10概念映射到对应的行业板块，提升P0匹配率
# 后续可逐步完善
CONCEPT_TO_INDUSTRY = {
    # IT/计算机
    '数据中心': 'IT服务Ⅱ',
    '云计算': 'IT服务Ⅱ',
    '大数据': 'IT服务Ⅱ',
    '人工智能': 'IT服务Ⅱ',
    '算力': 'IT服务Ⅱ',
    'AI': 'IT服务Ⅱ',
    '信创': 'IT服务Ⅱ',
    '软件': '软件开发',
    '国产软件': '软件开发',
    '操作系统': '软件开发',
    '网络安全': 'IT服务Ⅱ',
    '数字货币': 'IT服务Ⅱ',
    '区块链': 'IT服务Ⅱ',
    '元宇宙': 'IT服务Ⅱ',
    'AIGC': 'IT服务Ⅱ',
    'ChatGPT': 'IT服务Ⅱ',
    # 通信
    '5G': '通信设备',
    '5G概念': '通信设备',
    'F5G': '通信设备',
    '6G': '通信设备',
    '光模块': '通信设备',
    'CPO': '通信设备',
    '光通信': '通信设备',
    '通信设备': '通信设备',
    '基站': '通信设备',
    '卫星通信': '通信设备',
    '量子通信': '通信设备',
    # 半导体/电子
    '芯片': '半导体',
    '半导体': '半导体',
    '集成电路': '半导体',
    '光刻': '半导体',
    '存储芯片': '半导体',
    '第三代半导体': '半导体',
    '碳化硅': '半导体',
    '氮化镓': '半导体',
    'PCB': '元件',
    '印制电路板': '元件',
    '消费电子': '元件',
    '苹果概念': '元件',
    '华为概念': '元件',
    '鸿蒙': 'IT服务Ⅱ',
    '鸿蒙概念': 'IT服务Ⅱ',
    # 电力/新能源
    '储能': '电网设备',
    '光伏': '光伏设备',
    '光伏概念': '光伏设备',
    '风电': '电网设备',
    '新能源': '电力',
    '锂电池': '电池',
    '动力电池': '电池',
    '充电桩': '电网设备',
    '特高压': '电网设备',
    '智能电网': '电网设备',
    '虚拟电厂': '电网设备',
    # 汽车
    '新能源车': '汽车零部',
    '新能源汽车': '汽车零部',
    '汽车零部件': '汽车零部',
    '无人驾驶': '汽车零部',
    '自动驾驶': '汽车零部',
    '特斯拉': '汽车零部',
    # 机器人/自动化
    '机器人': '自动化设',
    '工业机器人': '自动化设',
    '服务机器人': '自动化设',
    '人形机器人': '自动化设',
    '自动化': '自动化设',
    '工业4.0': '自动化设',
    '智能制造': '自动化设',
    # 医药医疗
    '创新药': '化学制药',
    '生物医药': '生物制品',
    '医疗器械': '医疗服务',
    '医疗服务': '医疗服务',
    'CXO': '医疗服务',
    '医美': '医疗服务',
    '中药': '中药',
    # 教育
    '教育': '教育',
    '在线教育': '教育',
    '职业教育': '教育',
    # 房地产/建筑
    '房地产': '房地产开发',
    '地产': '房地产开发',
    '装修': '装修装饰',
    '装修装饰': '装修装饰',
    '建筑': '建筑装饰',
    # 环保
    '环保': '环保设备',
    '节能环保': '环保设备',
    '碳中和': '环保设备',
    '碳交易': '环保设备',
    # 军工
    '军工': '航天航空',
    '国防军工': '航天航空',
    '航空': '航天航空',
    '航天': '航天航空',
    # 金融
    '银行': '银行',
    '证券': '证券',
    '保险': '保险',
    # 其他
    '燃气': '燃气Ⅱ',
    '天然气': '燃气Ⅱ',
    '石油': '石油石化',
    '煤炭': '煤炭',
    '钢铁': '钢铁',
    '有色': '有色金属',
    '化工': '化学制品',
    '农业': '种植业',
    '养殖': '养殖业',
    '白酒': '白酒',
    '食品': '食品加工',
    '零售': '零售',
    '电商': '互联网电商',
    '物流': '物流',
    '快递': '物流',
    '旅游': '旅游酒店',
    '酒店': '旅游酒店',
    '传媒': '文化传媒',
    '游戏': '文化传媒',
    '影视': '文化传媒',
}


def _map_concept_to_industry(concept):
    """
    将F10概念映射到行业板块名称

    Args:
        concept: F10概念标签

    Returns:
        str: 对应的行业板块名称，无映射时返回原概念
    """
    if not concept or not isinstance(concept, str):
        return concept

    # 精确匹配
    if concept in CONCEPT_TO_INDUSTRY:
        return CONCEPT_TO_INDUSTRY[concept]

    # 模糊匹配（概念包含映射关键词）
    for keyword, industry in CONCEPT_TO_INDUSTRY.items():
        if keyword in concept:
            return industry

    return concept


def _ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache():
    """加载磁盘缓存"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache_data):
    """保存磁盘缓存"""
    _ensure_cache_dir()
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ========== P0：涨停池获取 ==========

def get_daily_limit_up_pool(date=None):
    """
    获取当日涨停池（P0数据源）

    Args:
        date: 日期，格式 'YYYYMMDD'，默认今天

    Returns:
        list: 涨停池列表，每只股票含 c(代码), n(名称), lbc(连板数), hybk(行业), fbt(首封时间) 等
    """
    if date is None:
        date = datetime.now().strftime('%Y%m%d')

    # 检查内存缓存
    cache_key = f'limit_up_pool_{date}'
    if cache_key in _memory_cache:
        return _memory_cache[cache_key]

    # 检查磁盘缓存
    disk_cache = _load_cache()
    if cache_key in disk_cache:
        cached = disk_cache[cache_key]
        # 缓存当日有效
        if cached.get('date') == date:
            _memory_cache[cache_key] = cached.get('pool', [])
            return cached.get('pool', [])

    # 从东方财富接口获取
    try:
        url = (f'http://push2ex.eastmoney.com/getTopicZTPool?'
               f'ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt'
               f'&Pageindex=0&pagesize=300&sort=fbt:asc&date={date}')
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        pool = data.get('data', {}).get('pool', [])

        if pool:
            # 写入缓存
            _memory_cache[cache_key] = pool
            disk_cache[cache_key] = {
                'date': date,
                'pool': pool,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            _save_cache(disk_cache)

        return pool

    except Exception as e:
        print(f'[热点检测] 获取涨停池失败(date={date}): {e}')
        return []


# ========== P0：涨停池热点概念统计 ==========

def _calc_count_score(count):
    """涨停数量分"""
    if count >= 10:
        return 10
    elif count >= 5:
        return 7
    elif count >= 3:
        return 4
    elif count >= 1:
        return 2
    return 0


def _calc_lbc_score(max_lbc, has_erban):
    """连板强度分"""
    if max_lbc >= 5:
        return 3
    elif max_lbc >= 3:
        return 2
    elif has_erban:
        return 1
    return 0


def calc_hot_concepts_from_pool(limit_up_pool):
    """
    从涨停池统计热点概念（P0核心算法）

    统计每只涨停股的F10概念和行业，计算每个概念的：
    - 涨停家数
    - 最高连板
    - 是否存在2板
    - hot_score = 涨停数量分 + 连板强度分

    Args:
        limit_up_pool: 涨停池列表

    Returns:
        dict: {concept_name: {count, max_lbc, has_erban, hot_score, hot_reason}}
    """
    if not limit_up_pool:
        return {}

    concept_stats = {}

    for item in limit_up_pool:
        lbc = item.get('lbc', 0)
        hybk = item.get('hybk', '')  # 行业板块

        # 收集该股票的概念标签（行业 + 其他可能的概念字段）
        concepts = []
        if hybk:
            concepts.append(hybk)

        # 部分涨停池数据可能有概念字段，尝试获取
        # 东方财富涨停池主要字段：c(代码), n(名称), lbc(连板), hybk(行业), fbt(首封), fund(封单), hs(换手), zbc(炸板)
        # 没有直接的F10概念列表，行业板块作为主要统计维度

        for concept in concepts:
            if not concept or not isinstance(concept, str):
                continue
            concept = concept.strip()
            if not concept:
                continue

            if concept not in concept_stats:
                concept_stats[concept] = {
                    'count': 0,
                    'max_lbc': 0,
                    'has_erban': False,
                    'codes': [],
                }

            stat = concept_stats[concept]
            stat['count'] += 1
            stat['max_lbc'] = max(stat['max_lbc'], lbc)
            if lbc >= 2:
                stat['has_erban'] = True
            if len(stat['codes']) < 20:  # 最多记录20只代码
                stat['codes'].append(item.get('c', ''))

    # 计算每个概念的 hot_score
    hot_concepts = {}
    for concept, stat in concept_stats.items():
        count = stat['count']
        max_lbc = stat['max_lbc']
        has_erban = stat['has_erban']

        count_score = _calc_count_score(count)
        lbc_score = _calc_lbc_score(max_lbc, has_erban)
        hot_score = min(count_score + lbc_score, 12)  # 最高12分

        # 生成原因描述
        reason_parts = [f'{concept}板块当日涨停{count}家']
        if max_lbc >= 3:
            reason_parts.append(f'最高{max_lbc}连板')
        elif has_erban:
            reason_parts.append('存在2板')

        hot_concepts[concept] = {
            'concept': concept,
            'count': count,
            'max_lbc': max_lbc,
            'has_erban': has_erban,
            'count_score': count_score,
            'lbc_score': lbc_score,
            'hot_score': hot_score,
            'hot_reason': '，'.join(reason_parts),
            'codes': stat['codes'],
        }

    return hot_concepts


def get_daily_hot_concepts(date=None, limit_up_pool=None):
    """
    获取当日热点概念列表（带缓存）

    Args:
        date: 日期 'YYYYMMDD'
        limit_up_pool: 可选，直接传入涨停池，避免重复获取

    Returns:
        dict: 热点概念统计结果
    """
    if date is None:
        date = datetime.now().strftime('%Y%m%d')

    cache_key = f'hot_concepts_{date}'

    # 内存缓存
    if cache_key in _memory_cache:
        return _memory_cache[cache_key]

    # 磁盘缓存
    disk_cache = _load_cache()
    if cache_key in disk_cache:
        cached = disk_cache[cache_key]
        if cached.get('date') == date:
            _memory_cache[cache_key] = cached.get('hot_concepts', {})
            return cached.get('hot_concepts', {})

    # 获取涨停池
    if limit_up_pool is None:
        limit_up_pool = get_daily_limit_up_pool(date)

    # 统计热点概念
    hot_concepts = calc_hot_concepts_from_pool(limit_up_pool)

    # 写入缓存
    if hot_concepts:
        _memory_cache[cache_key] = hot_concepts
        disk_cache[cache_key] = {
            'date': date,
            'hot_concepts': hot_concepts,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        _save_cache(disk_cache)

    return hot_concepts


# ========== 热点关联等级 ==========

def _calc_hot_relation_level(business_match_level, has_hot_match):
    """
    计算热点关联等级

    H1 强热点：主营S/A级 + 题材属于热点
    H2 普通热点：概念标签匹配 + 主营B级
    H3 弱热点：只有概念标签 + 主营C级

    Args:
        business_match_level: 主营匹配等级 S/A/B/C
        has_hot_match: 是否匹配到热点概念

    Returns:
        str: H1/H2/H3/None（无热点匹配时返回None）
    """
    if not has_hot_match:
        return None

    if business_match_level in ['S', 'A']:
        return 'H1'
    elif business_match_level == 'B':
        return 'H2'
    else:  # C级或未知
        return 'H3'


# ========== P1：概念板块行情（备用源） ==========

def _calc_p1_score_by_pct(change_pct):
    """
    P1概念涨幅评分（最高8分，低于P0的12分）

    概念涨幅≥5% → 8分
    3%-5% → 6分
    1%-3% → 4分
    0-1% → 2分
    """
    if change_pct >= 5:
        return 8
    elif change_pct >= 3:
        return 6
    elif change_pct >= 1:
        return 4
    elif change_pct > 0:
        return 2
    return 0


def _calc_by_concept_market(stock_concepts):
    """
    P1备用源：通过概念板块行情匹配热点

    当P0涨停池统计失败时使用。
    评分基于概念板块涨幅，最高8分（低于P0的12分）。

    Args:
        stock_concepts: 股票的F10概念列表

    Returns:
        dict: {
            'hot_theme': '',
            'hot_score': 0,
            'hot_reason': '',
            'hot_source': '概念板块行情',
            'hot_confidence': 'medium',
            'hot_detail': {},
        }
        失败时返回 None
    """
    result = {
        'hot_theme': '',
        'hot_score': 0,
        'hot_reason': '',
        'hot_source': '概念板块行情',
        'hot_confidence': 'low',
        'hot_detail': {},
    }

    if get_concept_market is None:
        print('[热点检测] P1不可用：theme_analyzer导入失败')
        return None

    if not stock_concepts:
        return None

    try:
        # 获取概念板块行情（带内部缓存）
        market_concepts = get_concept_market()
        if not market_concepts:
            print('[热点检测] P1概念行情接口返回空')
            return None

        # 匹配股票概念与市场概念
        matched = []
        for stock_concept in stock_concepts:
            if not stock_concept or not isinstance(stock_concept, str):
                continue
            stock_concept = stock_concept.strip()

            for mc in market_concepts:
                mc_name = mc.get('name', '')
                if not mc_name:
                    continue

                # 精确匹配或包含匹配
                if stock_concept == mc_name or stock_concept in mc_name or mc_name in stock_concept:
                    change_pct = mc.get('change_pct', 0)
                    # 只看上涨的概念（涨幅>0）
                    if change_pct > 0:
                        score = _calc_p1_score_by_pct(change_pct)
                        matched.append({
                            'theme': mc_name,
                            'change_pct': change_pct,
                            'rank': mc.get('rank', 999),
                            'limit_up_count': mc.get('limit_up_count', 0),
                            'score': score,
                        })
                    break  # 每个股票概念只匹配第一个市场概念

        if not matched:
            result['hot_reason'] = '所属概念无明显涨幅'
            result['hot_confidence'] = 'low'
            return result

        # 取评分最高的
        matched.sort(key=lambda x: x['score'], reverse=True)
        top = matched[0]

        hot_score = top['score']
        hot_theme = top['theme']
        change_pct = top['change_pct']

        # 置信度
        if hot_score >= 6:
            confidence = 'medium'
        elif hot_score >= 4:
            confidence = 'low'
        else:
            confidence = 'low'

        result.update({
            'hot_theme': hot_theme,
            'hot_score': hot_score,
            'hot_reason': f'{hot_theme}板块今日上涨{change_pct:.1f}%',
            'hot_source': '概念板块行情',
            'hot_confidence': confidence,
            'hot_detail': {
                'change_pct': change_pct,
                'rank': top['rank'],
                'limit_up_count': top['limit_up_count'],
                'matched_concepts': [m['theme'] for m in matched[:3]],
            },
        })

        return result

    except Exception as e:
        print(f'[热点检测] P1概念行情匹配失败: {e}')
        return None


# ========== 单只股票热点评分（P0优先，P1降级） ==========

def _calc_by_p0(stock_concepts, date=None, limit_up_pool=None):
    """
    P0主源：涨停池统计

    Returns:
        dict: 热点结果，失败时返回 None
    """
    # 获取当日热点概念
    hot_concepts = get_daily_hot_concepts(date, limit_up_pool)

    if not hot_concepts:
        return None

    # 匹配股票概念与热点概念
    matched_hot = []
    for stock_concept in stock_concepts:
        if not stock_concept or not isinstance(stock_concept, str):
            continue
        stock_concept = stock_concept.strip()

        # 1. 精确匹配
        if stock_concept in hot_concepts:
            matched_hot.append(hot_concepts[stock_concept])
            continue

        # 2. 概念-行业映射匹配（F10概念→行业板块）
        mapped_industry = _map_concept_to_industry(stock_concept)
        if mapped_industry != stock_concept and mapped_industry in hot_concepts:
            matched_hot.append(hot_concepts[mapped_industry])
            continue

        # 3. 模糊匹配（包含关系）
        for hot_name, hot_info in hot_concepts.items():
            if stock_concept in hot_name or hot_name in stock_concept:
                matched_hot.append(hot_info)
                break
            # 映射后的模糊匹配
            if mapped_industry != stock_concept and (mapped_industry in hot_name or hot_name in mapped_industry):
                matched_hot.append(hot_info)
                break

    if not matched_hot:
        return None

    # 取评分最高的热点
    matched_hot.sort(key=lambda x: x['hot_score'], reverse=True)
    top_hot = matched_hot[0]

    hot_score = top_hot['hot_score']
    hot_theme = top_hot['concept']
    hot_reason = top_hot['hot_reason']

    # 置信度评估
    if hot_score >= 8:
        confidence = 'high'
    elif hot_score >= 4:
        confidence = 'medium'
    else:
        confidence = 'low'

    return {
        'hot_theme': hot_theme,
        'hot_score': hot_score,
        'hot_reason': hot_reason,
        'hot_source': '涨停池统计',
        'hot_confidence': confidence,
        'hot_detail': {
            'limit_up_count': top_hot['count'],
            'max_lbc': top_hot['max_lbc'],
            'has_erban': top_hot['has_erban'],
            'count_score': top_hot['count_score'],
            'lbc_score': top_hot['lbc_score'],
            'matched_concepts': [h['concept'] for h in matched_hot[:3]],
        },
    }


def calc_stock_hot_score(stock_concepts, business_match_level='C',
                         date=None, limit_up_pool=None):
    """
    计算单只股票的热点评分（P0优先，P1降级）

    优先级：
    P0 涨停池统计（最高12分）→ 失败时
    P1 概念板块行情（最高8分）→ 失败时
    hot_score=0, confidence='low'

    Args:
        stock_concepts: 股票的F10概念列表（含行业）
        business_match_level: 主营匹配等级 S/A/B/C
        date: 日期 'YYYYMMDD'
        limit_up_pool: 可选，直接传入涨停池

    Returns:
        dict: {
            'hot_theme': '',           # 最热的概念名
            'hot_score': 0,            # 0-12分
            'hot_reason': '',          # 人类可读原因
            'hot_source': '涨停池统计/概念板块行情', # 数据来源
            'hot_confidence': 'high',  # high/medium/low
            'hot_relation_level': '',  # H1/H2/H3
            'is_hot_topic': False,     # 兼容现有字段（hot_score >= 5）
            'hot_detail': {},          # 详细数据
        }
    """
    result = {
        'hot_theme': '',
        'hot_score': 0,
        'hot_reason': '',
        'hot_source': '涨停池统计',
        'hot_confidence': 'low',
        'hot_relation_level': '',
        'is_hot_topic': False,
        'hot_detail': {},
    }

    if not stock_concepts:
        result['hot_reason'] = '无概念数据，无法判断热点'
        return result

    # ========== P0：涨停池统计（主源） ==========
    p0_result = _calc_by_p0(stock_concepts, date, limit_up_pool)

    if p0_result and p0_result['hot_score'] > 0:
        # P0成功，计算热点关联等级
        hot_relation_level = _calc_hot_relation_level(business_match_level, has_hot_match=True)
        p0_result['hot_relation_level'] = hot_relation_level or ''
        p0_result['is_hot_topic'] = p0_result['hot_score'] >= 5
        result.update(p0_result)
        return result

    # ========== P1：概念板块行情（备用源） ==========
    p1_result = _calc_by_concept_market(stock_concepts)

    if p1_result and p1_result.get('hot_score', 0) > 0:
        # P1成功，补充热点关联等级
        hot_relation_level = _calc_hot_relation_level(business_match_level, has_hot_match=True)
        p1_result['hot_relation_level'] = hot_relation_level or ''
        p1_result['is_hot_topic'] = p1_result['hot_score'] >= 5
        result.update(p1_result)
        return result

    # ========== P0和P1都失败 ==========
    if p0_result is None and p1_result is None:
        result['hot_reason'] = '热点数据暂不可用（P0涨停池和P1概念行情均失败）'
        result['hot_confidence'] = 'low'
    elif p0_result is None:
        result['hot_reason'] = '涨停池数据不可用，且所属概念无明显涨幅'
        result['hot_confidence'] = 'low'
    else:
        result['hot_reason'] = '所属概念非当日热点板块'
        result['hot_confidence'] = 'medium'

    return result


# ========== 测试 ==========

if __name__ == '__main__':
    print('=' * 70)
    print('market_hot_detector P0 涨停池统计 测试')
    print('=' * 70)

    # 测试1：模拟涨停池
    print('\n【测试1】模拟涨停池热点统计')
    mock_pool = [
        {'c': '000001', 'n': '测试1', 'lbc': 5, 'hybk': 'IT服务Ⅱ', 'fbt': 930},
        {'c': '000002', 'n': '测试2', 'lbc': 3, 'hybk': 'IT服务Ⅱ', 'fbt': 935},
        {'c': '000003', 'n': '测试3', 'lbc': 2, 'hybk': 'IT服务Ⅱ', 'fbt': 940},
        {'c': '000004', 'n': '测试4', 'lbc': 1, 'hybk': 'IT服务Ⅱ', 'fbt': 945},
        {'c': '000005', 'n': '测试5', 'lbc': 1, 'hybk': 'IT服务Ⅱ', 'fbt': 950},
        {'c': '000006', 'n': '测试6', 'lbc': 1, 'hybk': '通信设备', 'fbt': 930},
        {'c': '000007', 'n': '测试7', 'lbc': 1, 'hybk': '通信设备', 'fbt': 935},
        {'c': '000008', 'n': '测试8', 'lbc': 1, 'hybk': '塑料', 'fbt': 1000},
    ]

    hot_concepts = calc_hot_concepts_from_pool(mock_pool)
    print(f'  统计到 {len(hot_concepts)} 个热点概念')
    for name, info in sorted(hot_concepts.items(), key=lambda x: x[1]['hot_score'], reverse=True):
        print(f'  {name}: {info["hot_score"]}分 (涨停{info["count"]}家, 最高{info["max_lbc"]}连板) - {info["hot_reason"]}')

    # 测试2：单只股票热点评分
    print('\n【测试2】单只股票热点评分')
    test_cases = [
        (['IT服务Ⅱ', '云计算'], 'S', '主营S + IT服务热点'),
        (['IT服务Ⅱ'], 'A', '主营A + IT服务热点'),
        (['通信设备'], 'B', '主营B + 通信设备热点'),
        (['塑料'], 'C', '主营C + 塑料非热点'),
        (['IT服务Ⅱ'], 'C', '主营C + IT服务热点(H3)'),
    ]

    for concepts, bm_level, desc in test_cases:
        result = calc_stock_hot_score(concepts, bm_level, limit_up_pool=mock_pool)
        print(f'\n  {desc}')
        print(f'    概念: {concepts}, 主营: {bm_level}')
        print(f'    hot_theme: {result["hot_theme"]}')
        print(f'    hot_score: {result["hot_score"]}')
        print(f'    hot_relation_level: {result["hot_relation_level"]}')
        print(f'    is_hot_topic: {result["is_hot_topic"]}')
        print(f'    hot_reason: {result["hot_reason"]}')
        print(f'    hot_confidence: {result["hot_confidence"]}')

    # 测试3：P0优先验证（P0正常时不调用P1）
    print('\n【测试3】P0优先验证')
    result_p0 = calc_stock_hot_score(['IT服务Ⅱ'], 'S', limit_up_pool=mock_pool)
    print(f'  P0正常时: hot_source={result_p0["hot_source"]}, hot_score={result_p0["hot_score"]}')
    assert result_p0['hot_source'] == '涨停池统计', 'P0正常时应使用涨停池统计'
    print(f'  ✅ P0优先，hot_source=涨停池统计')

    # 测试4：P0失败时降级到P1
    print('\n【测试4】P0失败降级到P1（使用不存在的日期，P0返回空）')
    # 清除内存缓存，确保P0重新获取
    _memory_cache.clear()
    result_p1 = calc_stock_hot_score(['人工智能', '算力'], 'S', date='20990101')
    print(f'  P0失败时: hot_source={result_p1["hot_source"]}, hot_score={result_p1["hot_score"]}')
    print(f'  hot_theme={result_p1["hot_theme"]}, hot_reason={result_p1["hot_reason"][:40]}')
    if result_p1['hot_source'] == '概念板块行情':
        print(f'  ✅ P0失败，自动降级到P1概念板块行情')
    elif result_p1['hot_score'] == 0:
        print(f'  ⚠️ P1也不可用（接口可能失败），返回hot_score=0')
    else:
        print(f'  ⚠️ 意外结果: hot_source={result_p1["hot_source"]}')

    # 测试5：P1评分边界
    print('\n【测试5】P1评分边界验证')
    print(f'  涨幅≥5%: {_calc_p1_score_by_pct(6)}分')
    print(f'  涨幅3-5%: {_calc_p1_score_by_pct(4)}分')
    print(f'  涨幅1-3%: {_calc_p1_score_by_pct(2)}分')
    print(f'  涨幅0-1%: {_calc_p1_score_by_pct(0.5)}分')
    print(f'  涨幅≤0: {_calc_p1_score_by_pct(0)}分')
    print(f'  P1最高8分（低于P0的12分）✅')

    # 测试6：评分范围验证
    print('\n【测试6】评分范围验证')
    all_scores = []
    for concepts, bm, desc in test_cases:
        r = calc_stock_hot_score(concepts, bm, limit_up_pool=mock_pool)
        all_scores.append(r['hot_score'])
    max_score = max(all_scores)
    print(f'  P0测试最高hot_score={max_score}（应≤12）')
    assert max_score <= 12, 'hot_score不应超过12分'
    print(f'  ✅ 评分范围正确，最高≤12分')

    # 测试7：字段完整性验证
    print('\n【测试7】输出字段完整性验证')
    required_fields = ['hot_theme', 'hot_score', 'hot_reason', 'hot_source',
                       'hot_confidence', 'hot_relation_level', 'is_hot_topic', 'hot_detail']
    r = calc_stock_hot_score(['IT服务Ⅱ'], 'S', limit_up_pool=mock_pool)
    missing = [f for f in required_fields if f not in r]
    if missing:
        print(f'  ❌ 缺少字段: {missing}')
    else:
        print(f'  ✅ 所有{len(required_fields)}个字段完整')

    # 测试8：缓存验证
    print('\n【测试8】缓存验证')
    cache_key = 'hot_concepts_20260804'
    if cache_key in _memory_cache:
        print(f'  ✅ 内存缓存生效: {cache_key}')
    else:
        print(f'  ⚠️ 内存缓存未命中（可能未用真实日期测试）')
    if os.path.exists(CACHE_FILE):
        print(f'  ✅ 磁盘缓存文件存在: {CACHE_FILE}')
    else:
        print(f'  ⚠️ 磁盘缓存文件不存在')

    print('\n' + '=' * 70)
    print('Step 2 测试完成（P0+P1降级框架）')
    print('=' * 70)
