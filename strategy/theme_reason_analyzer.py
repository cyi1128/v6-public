"""
涨停关联题材识别模块
实时判断股票当天上涨/涨停的核心炒作题材

与F10概念的区别：
- F10概念 = 公司历史标签（静态）
- 涨停题材 = 当天市场炒作热点（动态）

功能：
1. 获取概念板块实时行情
2. 建立题材词库（产业链关键词）
3. 个股-热点题材关联算法
4. 上涨原因分析
"""

import time
from datetime import datetime

# 导入已有模块
from strategy.theme_analyzer import get_concept_market

# ========== 题材词库 ==========
# 每个题材包含：名称、产业链关键词、业务关键词
THEME_LIBRARY = {
    # AI/算力方向
    '液冷技术': {
        'keywords': ['液冷', '冷却', '散热', '温控', '热管理', '数据中心散热', '服务器散热'],
        'business': ['冷却系统', '散热设备', '温控设备', '热管理', '液冷机组'],
    },
    '算力': {
        'keywords': ['算力', 'AI服务器', '数据中心', 'IDC', '云计算', '智算'],
        'business': ['服务器', '数据中心', '云计算', 'IDC', '算力服务'],
    },
    '人工智能': {
        'keywords': ['AI', '人工智能', '大模型', 'AIGC', 'ChatGPT', '机器学习', '深度学习'],
        'business': ['AI', '人工智能', '大模型', '算法', '智能'],
    },
    '芯片': {
        'keywords': ['芯片', '半导体', '集成电路', '晶圆', '封测', '光刻'],
        'business': ['芯片', '半导体', '集成电路', '封装', '测试'],
    },
    'CPO概念': {
        'keywords': ['CPO', '光模块', '光通信', '硅光'],
        'business': ['光模块', '光通信', '光器件'],
    },
    
    # 机器人方向
    '人形机器人': {
        'keywords': ['人形机器人', '机器人', '减速器', '伺服电机', '丝杠', '关节'],
        'business': ['机器人', '减速器', '伺服', '电机', '关节'],
    },
    '工业母机': {
        'keywords': ['工业母机', '机床', '数控', '加工中心'],
        'business': ['机床', '数控', '加工中心', '精密机械'],
    },
    
    # 新能源方向
    '储能': {
        'keywords': ['储能', '电池', '锂电', '光伏', '风电', '新能源'],
        'business': ['储能', '电池', '光伏', '风电', '新能源'],
    },
    '固态电池': {
        'keywords': ['固态电池', '固态', '电解质', '锂金属电池'],
        'business': ['电池', '固态', '电解质'],
    },
    '光伏': {
        'keywords': ['光伏', '太阳能', '组件', '硅料', '硅片', '电池片'],
        'business': ['光伏', '太阳能', '组件', '硅料'],
    },
    
    # 电力/电网方向
    '虚拟电厂': {
        'keywords': ['虚拟电厂', 'VPP', '电网', '电力', '能源互联网'],
        'business': ['电网', '电力', '能源', '自动化'],
    },
    '特高压': {
        'keywords': ['特高压', '高压', '输变电', '电网设备'],
        'business': ['特高压', '高压', '输变电', '电网'],
    },
    '智能电网': {
        'keywords': ['智能电网', '电网', '电力自动化', '配网'],
        'business': ['电网', '电力', '自动化', '配网'],
    },
    
    # 汽车方向
    '智能驾驶': {
        'keywords': ['智能驾驶', '自动驾驶', '无人驾驶', '智驾', 'ADAS'],
        'business': ['智能驾驶', '自动驾驶', '无人驾驶', '汽车电子'],
    },
    '新能源车': {
        'keywords': ['新能源车', '新能源汽车', '电动车', '电动汽车', '整车'],
        'business': ['汽车', '新能源', '电动车', '整车'],
    },
    '华为汽车': {
        'keywords': ['华为汽车', '问界', '智界', '鸿蒙智行', '华为HI'],
        'business': ['汽车', '华为', '智能驾驶'],
    },
    
    # 军工/航天方向
    '军工': {
        'keywords': ['军工', '国防', '航天', '航空', '兵器', '船舶'],
        'business': ['军工', '国防', '航天', '航空', '兵器'],
    },
    '商业航天': {
        'keywords': ['商业航天', '卫星', '火箭', '太空', '低轨卫星'],
        'business': ['航天', '卫星', '火箭'],
    },
    '低空经济': {
        'keywords': ['低空经济', '无人机', 'eVTOL', '通用航空', '低空'],
        'business': ['无人机', '通用航空', '低空', '飞行器'],
    },
    
    # 华为/国产替代方向
    '华为概念': {
        'keywords': ['华为', '鸿蒙', '昇腾', '鲲鹏', '华为产业链'],
        'business': ['华为', '鸿蒙', '昇腾', '鲲鹏'],
    },
    '国产替代': {
        'keywords': ['国产替代', '信创', '自主可控', '国产化'],
        'business': ['国产', '信创', '自主', '国产化'],
    },
    
    # 政策/主题方向
    '国企改革': {
        'keywords': ['国企改革', '央企改革', '中特估', '国资', '央企'],
        'business': ['国企', '央企', '国资'],
    },
    '一带一路': {
        'keywords': ['一带一路', '中亚', '中东', '出海'],
        'business': ['一带一路', '海外', '国际工程'],
    },
    '化债': {
        'keywords': ['化债', 'AMC', '债务化解', '地方债'],
        'business': ['AMC', '资产管理', '债务'],
    },
    '碳交易': {
        'keywords': ['碳交易', '碳中和', '碳达峰', '碳排放'],
        'business': ['碳交易', '碳中和', '环保'],
    },
    
    # 医药方向
    '创新药': {
        'keywords': ['创新药', '新药', 'CXO', '生物医药', 'ADC'],
        'business': ['创新药', '生物医药', 'CXO', '制药'],
    },
    '医疗器械': {
        'keywords': ['医疗器械', '医疗设备', '医用', '诊断'],
        'business': ['医疗器械', '医疗设备', '医用'],
    },
    '医美': {
        'keywords': ['医美', '美容', '玻尿酸', '肉毒素'],
        'business': ['医美', '美容', '化妆品'],
    },
    
    # 消费方向
    '白酒': {
        'keywords': ['白酒', '酒类', '酿酒', '酱酒'],
        'business': ['白酒', '酿酒', '酒类'],
    },
    '食品饮料': {
        'keywords': ['食品', '饮料', '消费', '零食', '调味品'],
        'business': ['食品', '饮料', '消费'],
    },
    '零售': {
        'keywords': ['零售', '超市', '百货', '电商'],
        'business': ['零售', '超市', '百货', '电商'],
    },
    
    # 传媒/游戏方向
    '游戏': {
        'keywords': ['游戏', '手游', '网游', '电竞'],
        'business': ['游戏', '手游', '网游'],
    },
    '元宇宙': {
        'keywords': ['元宇宙', 'VR', 'AR', '虚拟现实', '增强现实'],
        'business': ['VR', 'AR', '虚拟现实', '元宇宙'],
    },
    'AIGC': {
        'keywords': ['AIGC', '生成式AI', 'AI生成', '文生图', '文生视频'],
        'business': ['AI', '人工智能', '生成式'],
    },
    
    # 金融方向
    '券商': {
        'keywords': ['券商', '证券', '经纪', '投行'],
        'business': ['证券', '券商', '经纪'],
    },
    '银行': {
        'keywords': ['银行', '商业银行', '城商行', '农商行'],
        'business': ['银行', '商业'],
    },
    
    # 地产方向
    '房地产': {
        'keywords': ['房地产', '地产', '物业', '开发'],
        'business': ['房地产', '地产', '开发', '物业'],
    },
}


# ========== 关联评分算法 ==========

def get_theme_market_data():
    """获取概念板块实时行情数据"""
    try:
        concepts = get_concept_market()
        if concepts and len(concepts) > 0:
            return concepts
    except Exception as e:
        print(f"[题材识别] 获取概念行情失败: {e}")
    
    return []


def match_theme_by_keywords(stock_name, stock_concepts, stock_business=''):
    """
    通过关键词匹配题材
    
    Args:
        stock_name: 股票名称
        stock_concepts: F10概念列表
        stock_business: 主营业务描述
    
    Returns:
        list: 匹配到的题材列表，按匹配度排序
    """
    matched_themes = []
    
    for theme_name, theme_info in THEME_LIBRARY.items():
        score = 0
        match_reasons = []
        
        # 1. F10概念匹配（权重最高）
        for concept in stock_concepts:
            if not isinstance(concept, str):
                continue
            # 概念名包含题材关键词
            for keyword in theme_info['keywords']:
                if keyword in concept or concept in keyword:
                    score += 40
                    match_reasons.append(f'F10概念匹配: {concept}')
                    break
        
        # 2. 股票名称匹配
        for keyword in theme_info['keywords']:
            if keyword in stock_name:
                score += 20
                match_reasons.append(f'名称匹配: {keyword}')
                break
        
        # 3. 主营业务匹配
        if stock_business:
            for keyword in theme_info['business']:
                if keyword in stock_business:
                    score += 30
                    match_reasons.append(f'业务匹配: {keyword}')
                    break
        
        if score > 0:
            matched_themes.append({
                'theme': theme_name,
                'score': score,
                'match_reasons': match_reasons,
                'source': '关键词匹配',
            })
    
    # 按分数排序
    matched_themes.sort(key=lambda x: x['score'], reverse=True)
    return matched_themes


def match_theme_by_market(stock_concepts, stock_change_pct):
    """
    通过市场行情匹配题材（当天强势概念）
    
    Args:
        stock_concepts: F10概念列表
        stock_change_pct: 股票涨跌幅%
    
    Returns:
        list: 匹配到的市场热点题材列表
    """
    matched_themes = []
    
    # 获取概念板块行情
    market_concepts = get_theme_market_data()
    if not market_concepts or len(market_concepts) == 0:
        return matched_themes
    
    # 遍历市场强势概念，看股票是否属于这些概念
    for mc in market_concepts:
        concept_name = mc.get('name', '')
        concept_pct = mc.get('change_pct', 0)
        concept_rank = mc.get('rank', 999)
        concept_amount = mc.get('amount', 0)

        # 确保是数字类型（避免字符串与数字比较报错）
        try:
            concept_pct = float(concept_pct)
        except (ValueError, TypeError):
            concept_pct = 0
        try:
            concept_rank = int(concept_rank)
        except (ValueError, TypeError):
            concept_rank = 999
        try:
            concept_amount = float(concept_amount)
        except (ValueError, TypeError):
            concept_amount = 0
        
        # 只看涨幅前50的概念
        if concept_rank > 50:
            continue
        
        # 检查股票是否属于这个概念（模糊匹配）
        is_match = False
        for stock_concept in stock_concepts:
            if not isinstance(stock_concept, str):
                continue
            # 模糊匹配
            if stock_concept in concept_name or concept_name in stock_concept:
                is_match = True
                break
        
        if is_match:
            # 计算市场热度分（满分40分）
            market_score = 0
            
            # 1. 涨幅加分（15分）
            if concept_pct > 5:
                market_score += 15
            elif concept_pct > 3:
                market_score += 12
            elif concept_pct > 2:
                market_score += 8
            elif concept_pct > 1:
                market_score += 5
            elif concept_pct > 0:
                market_score += 2
            
            # 2. 排名加分（15分）
            if concept_rank <= 5:
                market_score += 15
            elif concept_rank <= 10:
                market_score += 12
            elif concept_rank <= 20:
                market_score += 8
            elif concept_rank <= 30:
                market_score += 5
            
            # 3. 成交额加分（10分）
            # 成交额大于100亿算放量
            if concept_amount > 100000000000:  # 1000亿
                market_score += 10
            elif concept_amount > 50000000000:  # 500亿
                market_score += 8
            elif concept_amount > 10000000000:  # 100亿
                market_score += 5
            
            # 4. 个股同步性加分（额外加分，不计入40分上限）
            sync_bonus = 0
            if stock_change_pct > 0 and concept_pct > 0:
                ratio = min(stock_change_pct, concept_pct) / max(stock_change_pct, concept_pct) if max(stock_change_pct, concept_pct) > 0 else 0
                sync_bonus = int(ratio * 10)
            
            total_score = min(market_score + sync_bonus, 50)
            
            matched_themes.append({
                'theme': concept_name,
                'score': total_score,
                'market_score': market_score,
                'sync_bonus': sync_bonus,
                'concept_pct': concept_pct,
                'concept_rank': concept_rank,
                'concept_amount': concept_amount,
                'source': '市场行情',
            })
    
    # 按分数排序
    matched_themes.sort(key=lambda x: x['score'], reverse=True)
    return matched_themes


def analyze_stock_theme(stock_code, stock_name, stock_concepts, stock_change_pct=0, stock_business=''):
    """
    综合分析股票的涨停关联题材
    
    评分权重：
    - F10概念关联：30分
    - 主营业务产业链关联：30分
    - 当天市场热点强度：40分
    （个股同步性额外加分，最高10分）
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        stock_concepts: F10概念列表
        stock_change_pct: 股票涨跌幅%
        stock_business: 主营业务描述
    
    Returns:
        dict: 题材分析结果
            {
                'core_theme': '核心题材名称',
                'theme_score': 0-100,
                'theme_level': 'S/A/B/C/D',
                'all_themes': [...],  # 所有匹配的题材
                'up_reason': '上涨原因分析',
                'evidence': [...],  # 判断依据
                'is_hot_topic': True/False,  # 是否是当天热点
            }
    """
    result = {
        'core_theme': '',
        'theme_score': 0,
        'theme_level': 'D',
        'all_themes': [],
        'up_reason': '未发现当天明确炒作题材',
        'evidence': [],
        'is_hot_topic': False,
        'update_time': datetime.now().strftime('%H:%M:%S'),
    }

    if not stock_concepts or len(stock_concepts) == 0:
        result['up_reason'] = '暂无概念数据，无法判断题材'
        result['evidence'].append('无F10概念数据')
        return result

    # 1. 关键词匹配题材（F10概念 + 主营业务）
    keyword_themes = match_theme_by_keywords(stock_name, stock_concepts, stock_business)

    # 2. 市场行情匹配题材（当天热点）
    market_themes = match_theme_by_market(stock_concepts, stock_change_pct)

    # 3. 合并两个来源的题材
    theme_scores = {}
    
    for kt in keyword_themes:
        name = kt['theme']
        if name not in theme_scores:
            theme_scores[name] = {
                'theme': name,
                'total_score': 0,
                'keyword_score': 0,  # F10 + 主营业务，满分60分
                'market_score': 0,   # 市场热点，满分40分
                'sync_bonus': 0,     # 个股同步性，额外加分
                'match_reasons': [],
                'market_info': None,
            }
        theme_scores[name]['keyword_score'] = kt['score']
        theme_scores[name]['total_score'] += kt['score']
        theme_scores[name]['match_reasons'].extend(kt['match_reasons'])
    
    for mt in market_themes:
        name = mt['theme']
        if name not in theme_scores:
            theme_scores[name] = {
                'theme': name,
                'total_score': 0,
                'keyword_score': 0,
                'market_score': 0,
                'sync_bonus': 0,
                'match_reasons': [],
                'market_info': None,
            }
        theme_scores[name]['market_score'] = mt['market_score']
        theme_scores[name]['sync_bonus'] = mt.get('sync_bonus', 0)
        theme_scores[name]['total_score'] += mt['market_score'] + mt.get('sync_bonus', 0)
        theme_scores[name]['market_info'] = {
            'pct': mt['concept_pct'],
            'rank': mt['concept_rank'],
            'amount': mt['concept_amount'],
        }

    # 转换为列表并排序
    all_themes = list(theme_scores.values())
    
    # 排序规则：优先按市场热度排序，再按总分排序
    # 因为我们要找的是"当天炒作题材"，而不是"产业关联最强的题材"
    all_themes.sort(key=lambda x: (x['market_score'], x['total_score']), reverse=True)
    result['all_themes'] = all_themes

    # 取最高分作为核心题材（优先有市场热点的）
    if all_themes and len(all_themes) > 0:
        top_theme = all_themes[0]
        result['core_theme'] = top_theme['theme']
        result['theme_score'] = min(top_theme['total_score'], 100)

        # 分级
        score = result['theme_score']
        if score >= 80:
            result['theme_level'] = 'S'
        elif score >= 60:
            result['theme_level'] = 'A'
        elif score >= 40:
            result['theme_level'] = 'B'
        elif score >= 20:
            result['theme_level'] = 'C'
        else:
            result['theme_level'] = 'D'
        
        # 题材状态分类
        keyword_score = top_theme['keyword_score']
        market_score = top_theme['market_score']
        
        if keyword_score >= 20 and market_score > 0:
            # 产业关联 + 市场热点 = 当天热点
            result['theme_status'] = 'hot'
            result['theme_status_text'] = '当天热点'
        elif keyword_score >= 20 and market_score == 0:
            # 有产业关联，但当天板块没涨 = 潜在题材
            result['theme_status'] = 'potential'
            result['theme_status_text'] = '潜在题材'
        else:
            # 只有F10概念匹配 = 普通概念
            result['theme_status'] = 'normal'
            result['theme_status_text'] = '普通概念'
        
        result['is_hot_topic'] = (result['theme_status'] == 'hot')
        # 生成上涨原因（根据不同状态）
        reasons = []
        evidence = []

        theme_status = result.get('theme_status', 'normal')
        theme_name = top_theme['theme']

        if theme_status == 'hot':
            # 当天热点
            if top_theme['market_info']:
                pct = top_theme['market_info']['pct']
                rank = top_theme['market_info']['rank']
                reasons.append(f'{theme_name}板块今日走强')
                evidence.append(f'① 市场热点: {theme_name} +{pct:.2f}%，涨幅排名第{rank}位')
            
            if top_theme['keyword_score'] > 0:
                reasons.append('公司属于相关产业链')
                evidence.append(f'② 产业关联: {", ".join(top_theme["match_reasons"][:2])}')
            
            if stock_change_pct > 0:
                if top_theme['sync_bonus'] > 0:
                    reasons.append('个股与板块同步上涨')
                    evidence.append(f'③ 个股表现: +{stock_change_pct:.2f}%，与板块同步性强')
                else:
                    reasons.append('个股跟随板块上涨')
                    evidence.append(f'③ 个股表现: +{stock_change_pct:.2f}%')
            
            result['up_reason'] = f'{theme_name}方向资金集中流入，公司属于相关产业链，个股同步走强。'

        elif theme_status == 'potential':
            # 潜在题材
            if top_theme['keyword_score'] > 0:
                reasons.append(f'公司属于{theme_name}相关产业链')
                evidence.append(f'① 产业关联: {", ".join(top_theme["match_reasons"][:2])}')
            
            reasons.append('但相关板块今日表现一般')
            evidence.append('② 市场表现: 相关板块今日无明显异动')
            
            if stock_change_pct > 0:
                reasons.append('个股上涨可能为独立行情')
                evidence.append(f'③ 个股表现: +{stock_change_pct:.2f}%，板块联动性较弱')
            
            result['up_reason'] = f'公司业务与{theme_name}方向相关，但相关板块今日未明显走强，暂未形成板块效应。'

        else:
            # 普通概念
            if top_theme['keyword_score'] > 0:
                reasons.append(f'公司属于{theme_name}概念')
                evidence.append(f'① 概念匹配: {", ".join(top_theme["match_reasons"][:2])}')
            
            if stock_change_pct > 0:
                reasons.append('个股上涨，但无明显板块热点')
                evidence.append(f'② 个股表现: +{stock_change_pct:.2f}%，可能为个股独立行情')
            else:
                reasons.append('暂无明显炒作迹象')
                evidence.append('② 市场表现: 无明显热点特征')
            
            result['up_reason'] = f'公司属于{theme_name}概念，但今日无明显板块热点，暂未形成炒作效应。'

        result['evidence'] = evidence

    return result


def get_theme_display(theme_result, max_count=3):
    """
    获取题材显示文本（用于UI显示）
    
    Args:
        theme_result: analyze_stock_theme返回的结果
        max_count: 最多显示几个题材
    
    Returns:
        str: 显示文本
    """
    if not theme_result or not theme_result.get('all_themes'):
        return '暂无核心题材'

    themes = theme_result['all_themes'][:max_count]
    theme_names = [t['theme'] for t in themes]

    return ' | '.join(theme_names)


if __name__ == '__main__':
    # 测试
    print("=" * 60)
    print("涨停关联题材识别测试")
    print("=" * 60)

    test_stocks = [
        ('002272', '川润股份', ['工程机械概念', '储能概念', '特高压', '风能', '智能电网'], 10.01, '液压、润滑、冷却系统'),
        ('002173', '创新医疗', ['华为昇腾', '人工智能', '医疗服务', '人脑工程'], 8.5, '医疗服务'),
        ('002803', '吉宏股份', ['抖音概念', '华为概念', '区块链', '人工智能'], 6.2, '包装、电商'),
    ]

    for code, name, concepts, pct, business in test_stocks:
        print(f"\n{'='*60}")
        print(f"{name} ({code})")
        print(f"  涨幅: {pct}%")
        print(f"  F10概念: {concepts}")
        print(f"  主营业务: {business}")
        print(f"{'='*60}")

        result = analyze_stock_theme(code, name, concepts, pct, business)

        print(f"\n核心题材: {result['core_theme']}")
        print(f"题材评分: {result['theme_score']} ({result['theme_level']}级)")
        print(f"是否热点: {'是' if result['is_hot_topic'] else '否'}")
        print(f"上涨原因: {result['up_reason']}")
        print(f"\n判断依据:")
        for i, e in enumerate(result['evidence']):
            print(f"  {i+1}. {e}")

        print(f"\n所有匹配题材:")
        for t in result['all_themes'][:5]:
            print(f"  {t['theme']}: {t['total_score']}分 (关键词:{t['keyword_score']}, 行情:{t['market_score']})")

    print("\n" + "=" * 60)
    print("测试完成")
