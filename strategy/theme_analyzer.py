"""
题材分析核心模块
实时判断股票上涨/涨停的核心题材和关联概念

功能：
1. 获取概念板块实时行情
2. 计算概念板块强度排名
3. 个股-概念关联评分
4. 题材联动判断
5. 上涨原因分析

数据来源：东方财富概念板块行情接口
"""

import requests
import time
from datetime import datetime

# 缓存
_concept_market_cache = None
_concept_market_cache_time = 0
CACHE_EXPIRE = 60  # 缓存60秒

# D级标签黑名单（指数/资金/身份标签，不能作为核心题材）
D_LEVEL_TAGS = {
    '标准普尔', '富时罗素', 'MSCI', '沪深港通', '深股通', '沪股通', '融资融券',
    '机构重仓', '基金重仓', 'QFII重仓', '社保重仓', '保险重仓', '券商重仓',
    '参股公司', '股权激励', '预盈预增', '预亏预减', '次新股', '新股',
    '中证指数', '上证指数', '深证指数', '创业板指', '科创板', '北交所',
    '百元股', '低价股', '高价股', '亏损股', '绩优股', '蓝筹股',
    '高股息', '低市盈率', '高市盈率', '破净股', '增持', '减持',
    '回购', '解禁', '配股', '增发', '可转债', '转融券',
    '证金持股', '汇金持股', '国家队', '养老金', '职业年金',
    '标普道琼斯', '富时罗素概念', '富时罗素概念股',
    '参股新三板', '参股银行', '参股保险', '参股券商', '参股基金',
}

# C级标签（行业分类，优先级低）
C_LEVEL_KEYWORDS = {
    '房地产', '银行', '证券', '保险', '医药', '汽车', '电子', '计算机',
    '传媒', '通信', '电力', '煤炭', '钢铁', '有色', '化工', '建材',
    '机械', '轻工', '纺织', '服装', '食品', '饮料', '农业', '林业',
    '牧业', '渔业', '建筑', '交通运输', '仓储物流', '商业贸易',
    '休闲服务', '家用电器', '食品饮料', '农林牧渔', '有色金属',
    '钢铁', '建筑材料', '建筑装饰', '电气设备', '国防军工',
    '计算机', '传媒', '通信', '电子', '医药生物', '公用事业',
    '交通运输', '房地产', '银行', '非银金融', '食品饮料',
    '家用电器', '纺织服装', '轻工制造', '商业贸易', '农林牧渔',
}


def get_concept_market(force_refresh=False):
    """
    获取概念板块实时行情
    
    Args:
        force_refresh: 是否强制刷新
    
    Returns:
        list: 概念板块列表，按涨幅排序
            [
                {
                    'code': 'BK0987',
                    'name': '液冷技术',
                    'change_pct': 4.82,  # 涨跌幅%
                    'amount': 1234567890,  # 成交额
                    'up_count': 32,  # 上涨家数
                    'down_count': 4,  # 下跌家数
                    'limit_up_count': 5,  # 涨停家数
                    'rank': 1,  # 涨幅排名
                },
                ...
            ]
    """
    global _concept_market_cache, _concept_market_cache_time

    # 检查缓存
    if not force_refresh and _concept_market_cache:
        if time.time() - _concept_market_cache_time < CACHE_EXPIRE:
            return _concept_market_cache

    try:
        # 东方财富概念板块行情接口（多个备用）
        urls = [
            # https接口
            'https://push2delay.eastmoney.com/api/qt/clist/get',
            # http接口
            'http://push2delay.eastmoney.com/api/qt/clist/get',
            # 备用域名
            'https://push2delay.eastmoney.com/api/qt/clist/get',
        ]

        params = {
            'pn': '1',
            'pz': '200',  # 取前200个概念
            'po': '1',
            'np': '1',
            'fltt': '2',
            'invt': '2',
            'fid': 'f3',  # 按涨跌幅排序
            'fs': 'm:90+t:3',  # 概念板块
            'fields': 'f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152',
        }

        concepts = None
        for url in urls:
            try:
                r = requests.get(url, params=params, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data.get('data') and data['data'].get('diff'):
                        items = data['data']['diff']
                        concepts = []
                        for i, item in enumerate(items):
                            concept = {
                                'code': item.get('f12', ''),
                                'name': item.get('f14', ''),
                                'change_pct': item.get('f3', 0),  # 涨跌幅%
                                'price': item.get('f2', 0),  # 最新价
                                'amount': item.get('f6', 0),  # 成交额
                                'volume': item.get('f5', 0),  # 成交量
                                'up_count': item.get('f104', 0),  # 上涨家数
                                'down_count': item.get('f105', 0),  # 下跌家数
                                'limit_up_count': item.get('f106', 0),  # 涨停家数
                                'rank': i + 1,  # 涨幅排名
                            }
                            concepts.append(concept)
                        print(f"[题材分析] 从 {url} 获取到 {len(concepts)} 个概念板块")
                        break
            except Exception as e:
                print(f"[题材分析] 接口 {url} 失败: {e}")
                continue

        if not concepts:
            print(f"[题材分析] 所有概念板块行情接口都失败了")
            return []

        # 缓存
        _concept_market_cache = concepts
        _concept_market_cache_time = time.time()

        return concepts

    except Exception as e:
        print(f"[题材分析] 获取概念板块行情失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_concept_strength(concept_name):
    """
    获取单个概念的强度（支持模糊匹配）
    
    Args:
        concept_name: 概念名称
    
    Returns:
        dict: 概念强度信息
    """
    concepts = get_concept_market()
    if not concepts:
        return None

    # 1. 精确匹配
    for c in concepts:
        if c['name'] == concept_name:
            return _calc_strength(c)

    # 2. 包含匹配（概念名包含目标名，或目标名包含概念名）
    best_match = None
    best_match_len = 0
    for c in concepts:
        c_name = c['name']
        # 去掉"概念"后缀再比较
        c_name_clean = c_name.replace('概念', '').replace('板块', '')
        concept_clean = concept_name.replace('概念', '').replace('板块', '')

        if concept_clean in c_name_clean or c_name_clean in concept_clean:
            # 取更短的那个作为匹配长度（更精确）
            match_len = min(len(c_name_clean), len(concept_clean))
            if match_len > best_match_len:
                best_match = c
                best_match_len = match_len

    if best_match:
        return _calc_strength(best_match)

    # 3. 关键词匹配（部分字符匹配）
    for c in concepts:
        c_name = c['name']
        # 取前2个字符匹配
        if len(concept_name) >= 2 and len(c_name) >= 2:
            if concept_name[:2] == c_name[:2]:
                return _calc_strength(c)

    return None


def _calc_strength(target):
    """计算概念强度"""
    change_pct = target['change_pct']
    rank = target['rank']
    total = 100  # 假设总共100个概念

    # 强度评分（0-100）
    score = 0
    # 涨跌幅占40分
    if change_pct > 5:
        score += 40
    elif change_pct > 3:
        score += 35
    elif change_pct > 2:
        score += 30
    elif change_pct > 1:
        score += 20
    elif change_pct > 0:
        score += 10
    else:
        score += 0

    # 排名占30分
    rank_pct = rank / total if total > 0 else 1
    if rank_pct < 0.05:  # 前5%
        score += 30
    elif rank_pct < 0.1:  # 前10%
        score += 25
    elif rank_pct < 0.2:  # 前20%
        score += 20
    elif rank_pct < 0.3:  # 前30%
        score += 15
    else:
        score += 5

    # 涨停家数占30分（暂时用涨跌幅代替）
    if change_pct > 5:
        score += 30
    elif change_pct > 3:
        score += 25
    elif change_pct > 2:
        score += 20
    else:
        score += 10

    # 分级
    if score >= 90:
        level = 'S'
    elif score >= 80:
        level = 'A'
    elif score >= 70:
        level = 'B'
    elif score >= 60:
        level = 'C'
    else:
        level = 'D'

    return {
        'name': target['name'],
        'change_pct': change_pct,
        'rank': rank,
        'level': level,
        'score': score,
        'amount': target['amount'],
    }


def analyze_stock_themes(stock_code, stock_name, stock_concepts, stock_change_pct, stock_volume_ratio=1):
    """
    分析股票的核心题材和涨停关联概念
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        stock_concepts: 股票所属概念列表
        stock_change_pct: 股票当前涨跌幅%
        stock_volume_ratio: 量比
    
    Returns:
        dict: 题材分析结果
            {
                'core_themes': [...],  # 核心题材列表（按强度排序）
                'limit_up_concept': '',  # 最相关的涨停概念
                'theme_score': 0,  # 最高题材评分
                'theme_level': 'D',  # 最高题材等级
                'linkage_type': '',  # 联动类型：核心联动/独立走强/反向
                'up_reason': '',  # 上涨原因
                'evidence': [],  # 证据列表
                'data_source': '东方财富',  # 数据来源
                'update_time': '',  # 更新时间
            }
    """
    result = {
        'core_themes': [],
        'limit_up_concept': '',
        'theme_score': 0,
        'theme_level': 'D',
        'linkage_type': '未知',
        'up_reason': '',
        'evidence': [],
        'data_source': '东方财富',
        'update_time': datetime.now().strftime('%H:%M:%S'),
    }

    if not stock_concepts or len(stock_concepts) == 0:
        result['up_reason'] = '暂无概念数据'
        return result

    # 获取概念板块行情
    concept_market = get_concept_market()
    if not concept_market:
        result['up_reason'] = '概念行情接口异常'
        result['evidence'].append('概念行情接口异常，无法判断题材强度')
        return result

    # 过滤D级标签
    filtered_concepts = []
    for c in stock_concepts:
        if c in D_LEVEL_TAGS:
            continue
        # 过滤明显的D级关键词
        is_d_level = False
        for d_tag in D_LEVEL_TAGS:
            if d_tag in c:
                is_d_level = True
                break
        if not is_d_level:
            filtered_concepts.append(c)

    if not filtered_concepts:
        result['up_reason'] = '无有效题材概念'
        return result

    # 计算每个概念的关联评分
    theme_scores = []
    for concept_name in filtered_concepts:
        strength = get_concept_strength(concept_name)
        if not strength:
            continue

        # 关联评分 = 概念强度 + 个股同步性
        concept_pct = strength['change_pct']
        sync_score = 0

        # 个股与板块同步性（15分）
        if stock_change_pct > 0 and concept_pct > 0:
            # 同涨
            ratio = min(stock_change_pct, concept_pct) / max(stock_change_pct, concept_pct) if max(stock_change_pct, concept_pct) > 0 else 0
            sync_score = int(ratio * 15)
        elif stock_change_pct < 0 and concept_pct < 0:
            # 同跌
            sync_score = 5
        else:
            # 反向
            sync_score = 0

        # 量比加成（10分）
        volume_score = min(int(stock_volume_ratio * 5), 10) if stock_volume_ratio > 0 else 0

        # 总分
        total_score = strength['score'] + sync_score + volume_score
        total_score = min(total_score, 100)

        theme_scores.append({
            'name': concept_name,
            'concept_pct': concept_pct,
            'concept_rank': strength['rank'],
            'concept_level': strength['level'],
            'concept_score': strength['score'],
            'sync_score': sync_score,
            'volume_score': volume_score,
            'total_score': total_score,
        })

    # 按总分排序
    theme_scores.sort(key=lambda x: x['total_score'], reverse=True)

    # 取前5个作为核心题材
    result['core_themes'] = theme_scores[:5]

    # 最高评分的题材
    if theme_scores:
        top = theme_scores[0]
        result['theme_score'] = top['total_score']
        result['theme_level'] = top['concept_level']
        result['limit_up_concept'] = top['name']

        # 判断联动类型
        concept_pct = top['concept_pct']
        if stock_change_pct > 0 and concept_pct > 2:
            if top['sync_score'] >= 10:
                result['linkage_type'] = '核心题材联动'
            else:
                result['linkage_type'] = '题材相关但同步性一般'
        elif stock_change_pct > 0 and concept_pct <= 0:
            result['linkage_type'] = '个股独立走强，题材联动较弱'
        elif stock_change_pct < 0 and concept_pct > 0:
            result['linkage_type'] = '板块上涨但个股下跌，反向走势'
        else:
            result['linkage_type'] = '同步下跌'

        # 生成上涨原因
        if stock_change_pct > 0:
            if result['linkage_type'] == '核心题材联动':
                result['up_reason'] = f"{top['name']}概念板块今日走强（+{concept_pct:.2f}%），个股属于该题材，与板块同步上涨"
                result['evidence'].append(f"① 股票真实概念：{top['name']}")
                result['evidence'].append(f"② {top['name']}概念板块今日上涨 +{concept_pct:.2f}%")
                result['evidence'].append(f"③ 概念板块涨幅排名第 {top['concept_rank']} 位")
                result['evidence'].append(f"④ 个股与板块同步性评分 {top['sync_score']}/15")
            elif result['linkage_type'] == '个股独立走强，题材联动较弱':
                result['up_reason'] = f"个股今日上涨，但{top['name']}概念板块表现一般，可能为个股独立行情"
                result['evidence'].append(f"① 股票真实概念：{top['name']}")
                result['evidence'].append(f"② {top['name']}概念板块涨跌幅 {concept_pct:.2f}%")
                result['evidence'].append(f"③ 个股涨幅 {stock_change_pct:.2f}%，与板块同步性较低")
                result['evidence'].append("④ 暂无明确消息催化，可能为个股独立行情")
            else:
                result['up_reason'] = f"个股上涨，相关概念{top['name']}板块表现一般"
                result['evidence'].append(f"① 相关概念：{top['name']}")
                result['evidence'].append("② 暂无明确催化证据")
        else:
            result['up_reason'] = f"个股下跌，{top['name']}概念板块{concept_pct:.2f}%"
            result['evidence'].append(f"① 相关概念：{top['name']}")
    else:
        result['up_reason'] = '未匹配到有效概念板块'
        result['evidence'].append('股票概念未在概念板块行情中匹配到')

    return result


def get_theme_display(themes, max_count=3):
    """
    获取题材显示文本（用于表格显示）
    
    Args:
        themes: 核心题材列表
        max_count: 最大显示数量
    
    Returns:
        str: 显示文本
    """
    if not themes or len(themes) == 0:
        return '--'

    display = []
    for t in themes[:max_count]:
        name = t['name']
        level = t['concept_level']
        if level == 'S':
            display.append(f"🔥{name}")
        elif level == 'A':
            display.append(f"⭐{name}")
        else:
            display.append(name)

    text = '｜'.join(display)
    if len(themes) > max_count:
        text += f' +{len(themes)-max_count}'

    return text


if __name__ == '__main__':
    # 测试
    print("测试题材分析模块...")
    print("=" * 60)

    # 测试获取概念板块行情
    concepts = get_concept_market()
    print(f"\n获取到 {len(concepts)} 个概念板块")
    if concepts:
        print("\n涨幅前10概念：")
        for i, c in enumerate(concepts[:10]):
            print(f"  {i+1}. {c['name']}: +{c['change_pct']:.2f}%")

    # 测试个股题材分析
    print("\n" + "=" * 60)
    print("测试个股题材分析...")

    test_stocks = [
        ('002272', '川润股份', ['液冷技术', '算力', '数据中心', '储能', '机器人'], 10.01, 2.5),
        ('000712', '贵绳股份', ['军工', '白酒', '借壳预期'], 5.2, 1.8),
        ('000402', '金融街', ['房地产', '央企改革', 'REITs'], 2.3, 1.2),
    ]

    for code, name, concepts, pct, vr in test_stocks:
        print(f"\n{name} ({code}):")
        result = analyze_stock_themes(code, name, concepts, pct, vr)
        print(f"  核心题材: {get_theme_display(result['core_themes'])}")
        print(f"  最高评分: {result['theme_score']} ({result['theme_level']}级)")
        print(f"  联动类型: {result['linkage_type']}")
        print(f"  上涨原因: {result['up_reason']}")
        print(f"  证据:")
        for e in result['evidence']:
            print(f"    {e}")

    print("\n" + "=" * 60)
    print("测试完成")
