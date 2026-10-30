"""
概念数据服务（高质量版）
获取股票所属概念板块（真实数据，非关键词匹配）

数据来源优先级：
1. 东方财富核心题材接口（数据质量最高）
2. 同花顺概念接口（备用）
3. 东方财富F10核心概念（最后备用）

功能：
- 获取股票所属概念
- 获取股票所属行业（F10）
- 自动过滤地域标签
- 自动过滤行业重复标签
- 显示数据来源
"""

import requests
import time

# 缓存
_concept_cache = {}
_cache_time = {}
CACHE_EXPIRE = 3600  # 缓存1小时

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
    '创业板综', '创业板指', '上证50', '沪深300', '中证500', '中证1000',
    '茅指数', '宁组合', 'AH股', 'B股', 'H股',
}

# 地域标签黑名单（过滤掉）
AREA_TAGS = {
    '北京', '上海', '广东', '深圳', '浙江', '江苏', '山东', '河北', '河南', '四川',
    '湖北', '湖南', '安徽', '福建', '江西', '辽宁', '吉林', '黑龙江', '陕西', '甘肃',
    '青海', '宁夏', '新疆', '西藏', '内蒙古', '广西', '云南', '贵州', '海南', '重庆',
    '天津', '山西', '京津冀', '长三角', '珠三角', '粤港澳', '雄安', '西部大开发',
    '东北振兴', '中部崛起', '东部沿海',
}

# 行业标签黑名单（过滤掉，避免和sector重复）
INDUSTRY_TAGS = {
    '房地产', '银行', '证券', '保险', '医药', '汽车', '电子', '计算机', '传媒',
    '通信', '电力', '煤炭', '钢铁', '有色', '化工', '建材', '机械', '轻工',
    '纺织', '服装', '食品', '饮料', '农业', '林业', '牧业', '渔业',
}


# 高优先级热门题材（真正影响股价的概念）
HOT_THEMES = {
    # AI/科技
    '人工智能': 100, 'AI': 100, '大模型': 95, '算力': 95, '液冷技术': 95, '液冷': 95,
    '数据中心': 90, '云计算': 90, '大数据': 85, '数字经济': 85, '信创': 85,
    '国产软件': 80, '国产操作系统': 80, '网络安全': 80, '数据安全': 80,
    # 芯片/半导体
    '芯片': 100, '半导体': 95, '集成电路': 90, '存储芯片': 90, '先进封装': 90,
    '光刻机': 95, '光刻胶': 90, '中芯国际概念': 85, '华为芯片': 90,
    # 机器人
    '机器人': 100, '人形机器人': 95, '减速器': 90, '伺服电机': 85, '工业母机': 85,
    '智能制造': 80, '工业4.0': 75, '3D打印': 75,
    # 新能源
    '新能源': 90, '光伏': 90, '储能': 90, '固态电池': 95, '锂电池': 85,
    '动力电池': 80, '充电桩': 80, '换电概念': 80, '氢能源': 85,
    '燃料电池': 80, '钒电池': 85, '钠电池': 85,
    # 电力/电网
    '智能电网': 80, '虚拟电厂': 85, '特高压': 80, '电力物联网': 75,
    '碳交易': 75, '碳中和': 75, '环保': 70,
    # 汽车
    '智能驾驶': 90, '无人驾驶': 90, '自动驾驶': 90, '新能源车': 85,
    '汽车零部件': 75, '一体化压铸': 80, '特斯拉概念': 80, '华为汽车': 85,
    # 军工/航天
    '军工': 85, '国防军工': 80, '商业航天': 90, '低空经济': 90, '通用航空': 80,
    '卫星导航': 80, '北斗导航': 75, '无人机': 80,
    # 华为/国产替代
    '华为概念': 95, '华为产业链': 90, '鸿蒙概念': 90, '国产替代': 85,
    '中特估': 80, '央企改革': 75, '国企改革': 70,
    # 政策/主题
    '一带一路': 75, '雄安新区': 70, '粤港澳大湾区': 70, '长三角一体化': 65,
    '化债': 80, '化债(AMC)概念': 80, 'AMC概念': 75,
    'REITs': 70, 'PPP模式': 65, '海绵城市': 60,
    # 医药
    '创新药': 80, '生物医药': 75, '医疗器械': 70, 'CXO概念': 75,
    '中药': 70, '医美': 75, '养老概念': 65,
    # 消费
    '白酒': 70, '食品饮料': 65, '零售': 60, '电商': 65,
    '直播电商': 70, '网红经济': 65,
    # 传媒/游戏
    '游戏': 75, '元宇宙': 80, 'VR/AR': 75, '虚拟现实': 75,
    '传媒': 70, '影视': 65, 'AIGC': 90, 'ChatGPT概念': 90,
    # 金融
    '券商': 70, '银行': 60, '保险': 60, '多元金融': 65,
    # 地产
    '房地产开发': 50, '地产': 50, '物业管理': 45, '租售同权': 50,
    # 周期
    '煤炭': 40, '钢铁': 40, '有色': 45, '化工': 45,
    '建筑材料': 40, '建筑装饰': 40, '工程机械': 50,
}

# 低优先级标签（尽量不显示）
LOW_PRIORITY_TAGS = {
    # 地域
    '北京板块', '上海板块', '广东板块', '深圳板块', '浙江板块', '江苏板块',
    '山东板块', '河北板块', '河南板块', '四川板块', '湖北板块',
    '湖南板块', '安徽板块', '福建板块', '江西板块', '辽宁板块',
    '吉林板块', '黑龙江板块', '陕西板块', '甘肃板块', '青海板块',
    '宁夏板块', '新疆板块', '西藏板块', '内蒙古板块', '广西板块',
    '云南板块', '贵州板块', '海南板块', '重庆板块', '天津板块',
    '山西板块',
    # 估值/财务
    '低市净率', '高市净率', '低市盈率', '高市盈率', '破净股', '长期破净',
    '预盈预增', '预亏预减', '业绩预增', '业绩预降',
    '高股息', '低股息', '现金分红',
    # 其他
    '商业地产', '住宅开发', '园林工程', '基础建设', '通用设备',
    '节能环保', '专业工程',
}


def get_theme_score(concept):
    """获取概念的热度评分（0-100）"""
    # 精确匹配
    if concept in HOT_THEMES:
        return HOT_THEMES[concept]

    # 模糊匹配
    for hot_theme, score in HOT_THEMES.items():
        if hot_theme in concept or concept in hot_theme:
            return score - 10  # 模糊匹配减10分

    # 默认分数
    return 30


def sort_concepts_by_priority(concepts):
    """按优先级排序概念，返回排序后的列表"""
    scored = []
    for c in concepts:
        score = get_theme_score(c)
        scored.append((c, score))

    # 按分数降序排序
    scored.sort(key=lambda x: x[1], reverse=True)

    # 返回排序后的概念名
    return [c for c, s in scored]


def get_core_themes(concepts, max_count=10):
    """获取核心题材（前N个高优先级概念）
    
    过滤规则：
    - 必须过滤：D级标签（指数、资金、身份标签）
    - 必须过滤：地域标签（XX板块、XX省）
    - 保留：所有其他真实概念，按热度排序
    """
    sorted_concepts = sort_concepts_by_priority(concepts)

    # 过滤掉D级标签和地域标签，其他都保留
    core = []
    for c in sorted_concepts:
        # 跳过D级标签
        if c in D_LEVEL_TAGS:
            continue
        is_d_level = False
        for d_tag in D_LEVEL_TAGS:
            if d_tag in c or c in d_tag:
                is_d_level = True
                break
        if is_d_level:
            continue

        # 跳过地域标签
        if c in AREA_TAGS:
            continue
        is_area = False
        for area_tag in AREA_TAGS:
            if area_tag in c or c in area_tag:
                is_area = True
                break
        if is_area:
            continue

        # 其他都保留，按热度排序
        core.append(c)
        if len(core) >= max_count:
            break

    return core


# 概念标准化映射（不同表述映射到标准概念名）
CONCEPT_STANDARD_MAP = {
    # 液冷相关
    '液冷技术': '液冷服务器',
    '液冷': '液冷服务器',
    '服务器液冷': '液冷服务器',
    '冷板式液冷': '液冷服务器',
    '浸没式液冷': '液冷服务器',
    '数据中心液冷': '液冷服务器',
    '液冷数据中心': '液冷服务器',
    '冷却系统': '液冷服务器',
    '散热设备': '液冷服务器',
    '温控设备': '液冷服务器',
    
    # 算力相关
    '算力': '算力基础设施',
    'AI算力': '算力基础设施',
    '智算': '算力基础设施',
    '数据中心': '算力基础设施',
    'IDC': '算力基础设施',
    '云计算': '算力基础设施',
    
    # 服务器相关
    '服务器': '高端服务器',
    'AI服务器': '高端服务器',
    '国产服务器': '高端服务器',
    '高端计算机': '高端服务器',
    
    # 人工智能相关
    '人工智能': '人工智能',
    'AI': '人工智能',
    '大模型': '人工智能',
    'AIGC': '人工智能',
    'ChatGPT概念': '人工智能',
    '机器学习': '人工智能',
    '深度学习': '人工智能',
    '智能算法': '人工智能',
    
    # 机器人相关
    '机器人': '人形机器人',
    '人形机器人': '人形机器人',
    '工业机器人': '人形机器人',
    '减速器': '人形机器人',
    '伺服电机': '人形机器人',
    
    # 储能相关
    '储能': '储能',
    '储能概念': '储能',
    '电化学储能': '储能',
    '储能系统': '储能',
    '储能设备': '储能',
    
    # 特高压相关
    '特高压': '特高压',
    '特高压概念': '特高压',
    '输变电': '特高压',
    
    # 智能电网相关
    '智能电网': '智能电网',
    '电网': '智能电网',
    '电力自动化': '智能电网',
    '配网': '智能电网',
    
    # 虚拟电厂相关
    '虚拟电厂': '虚拟电厂',
    'VPP': '虚拟电厂',
    '能源互联网': '虚拟电厂',
    
    # 华为相关
    '华为概念': '华为产业链',
    '华为': '华为产业链',
    '鸿蒙': '华为产业链',
    '昇腾': '华为产业链',
    '鲲鹏': '华为产业链',
    '华为昇腾': '华为产业链',
    
    # 国产替代相关
    '国产替代': '国产替代',
    '信创': '国产替代',
    '自主可控': '国产替代',
    '国产化': '国产替代',
    
    # 医疗相关
    '医疗服务': '医疗服务',
    '医疗器械': '医疗器械',
    '医疗器械概念': '医疗器械',
    '创新药': '创新药',
    '生物医药': '生物医药',
    'CXO': '创新药',
    
    # 军工相关
    '军工': '军工',
    '国防军工': '军工',
    '航天': '军工',
    '航空': '军工',
    
    # 新能源相关
    '新能源车': '新能源汽车',
    '新能源汽车': '新能源汽车',
    '电动车': '新能源汽车',
    '光伏': '光伏',
    '风能': '风电',
    '风电': '风电',
    '固态电池': '固态电池',
    
    # 芯片相关
    '芯片': '半导体芯片',
    '半导体': '半导体芯片',
    '集成电路': '半导体芯片',
    '光刻': '半导体芯片',
    '封测': '半导体芯片',
    
    # 游戏传媒相关
    '游戏': '游戏',
    '手游': '游戏',
    '网游': '游戏',
    '元宇宙': '元宇宙',
    'VR': '元宇宙',
    'AR': '元宇宙',
    'AIGC': 'AIGC',
    
    # 金融相关
    '券商': '券商',
    '证券': '券商',
    '银行': '银行',
    '保险': '保险',
    
    # 地产相关
    '房地产': '房地产',
    '地产': '房地产',
    '房地产开发': '房地产',
    
    # 消费相关
    '白酒': '白酒',
    '食品饮料': '食品饮料',
    '零售': '零售',
    '电商': '电商',
    
    # 环保相关
    '环保': '环保',
    '节能环保': '环保',
    '碳交易': '碳交易',
    '碳中和': '碳交易',
    
    # 工程机械
    '工程机械': '工程机械',
    '工程机械概念': '工程机械',
    '通用设备': '工程机械',
}

# 业务关键词 → 概念映射（从主营业务提取关键词，生成概念）
BUSINESS_KEYWORD_TO_CONCEPT = {
    # 液冷/散热/冷却
    '液冷': '液冷服务器',
    '冷却': '液冷服务器',
    '散热': '液冷服务器',
    '温控': '液冷服务器',
    '热管理': '液冷服务器',
    '冷板': '液冷服务器',
    '浸没式': '液冷服务器',
    
    # 服务器/算力
    '服务器': '高端服务器',
    '高端计算机': '高端服务器',
    '数据中心': '算力基础设施',
    'IDC': '算力基础设施',
    '云计算': '算力基础设施',
    '算力': '算力基础设施',
    '智算': '算力基础设施',
    
    # 人工智能
    '人工智能': '人工智能',
    'AI': '人工智能',
    '大模型': '人工智能',
    '算法': '人工智能',
    '智能': '人工智能',
    
    # 机器人
    '机器人': '人形机器人',
    '减速器': '人形机器人',
    '伺服': '人形机器人',
    '电机': '人形机器人',
    
    # 储能
    '储能': '储能',
    '电池': '储能',
    '锂电': '储能',
    
    # 电力电网
    '特高压': '特高压',
    '电网': '智能电网',
    '电力': '智能电网',
    '输变电': '特高压',
    '配电': '智能电网',
    '虚拟电厂': '虚拟电厂',
    
    # 华为
    '华为': '华为产业链',
    '鸿蒙': '华为产业链',
    '昇腾': '华为产业链',
    
    # 国产替代
    '国产': '国产替代',
    '信创': '国产替代',
    '自主可控': '国产替代',
    
    # 医疗
    '医疗': '医疗服务',
    '医院': '医疗服务',
    '器械': '医疗器械',
    '医药': '生物医药',
    '创新药': '创新药',
    
    # 军工
    '军工': '军工',
    '国防': '军工',
    '航天': '军工',
    '航空': '军工',
    
    # 新能源
    '新能源': '新能源汽车',
    '电动车': '新能源汽车',
    '光伏': '光伏',
    '风电': '风电',
    '风能': '风电',
    
    # 芯片
    '芯片': '半导体芯片',
    '半导体': '半导体芯片',
    '集成电路': '半导体芯片',
    
    # 工程机械
    '工程机械': '工程机械',
    '液压': '工程机械',
    '机械': '工程机械',
    '设备': '工程机械',
    
    # 环保
    '环保': '环保',
    '节能': '环保',
    '碳交易': '碳交易',
    
    # 房地产
    '房地产': '房地产',
    '地产': '房地产',
    '开发': '房地产',
    
    # 零售电商
    '零售': '零售',
    '电商': '电商',
    '超市': '零售',
    '百货': '零售',
    
    # 游戏传媒
    '游戏': '游戏',
    '传媒': '传媒',
    '影视': '传媒',
    
    # 金融
    '证券': '券商',
    '券商': '券商',
    '银行': '银行',
    '保险': '保险',
}


def standardize_concept(concept_name):
    """概念标准化：将不同表述映射到标准概念名"""
    if not concept_name or not isinstance(concept_name, str):
        return concept_name
    
    # 直接匹配
    if concept_name in CONCEPT_STANDARD_MAP:
        return CONCEPT_STANDARD_MAP[concept_name]
    
    # 部分匹配
    for key, value in CONCEPT_STANDARD_MAP.items():
        if key in concept_name or concept_name in key:
            return value
    
    return concept_name


def extract_concepts_from_business(business_text):
    """
    从主营业务文本中提取概念
    
    注意：这里提取的是"可能相关"的概念，置信度不如F10官方概念
    需要标记来源和置信度，避免过度推断
    
    Args:
        business_text: 主营业务描述文本
    
    Returns:
        list: 提取到的概念列表（带来源和置信度）
        [{'name': '液冷服务器', 'source': '主营业务', 'confidence': 0.6}, ...]
    """
    if not business_text or not isinstance(business_text, str):
        return []
    
    extracted = []
    
    for keyword, concept in BUSINESS_KEYWORD_TO_CONCEPT.items():
        if keyword in business_text:
            # 根据关键词的匹配程度设置置信度
            # 直接匹配业务核心词：高置信度
            # 间接匹配：低置信度
            confidence = 0.6  # 默认中等置信度
            
            # 一些容易过度推断的关键词，降低置信度
            easy_over_infer = ['冷却', '散热', '温控', '智能', '机械', '设备', '系统', '技术']
            if keyword in easy_over_infer:
                confidence = 0.4  # 降低置信度，避免过度推断
            
            # 一些明确的业务词，提高置信度
            clear_business = ['液冷', '服务器', '算力', '数据中心', '人工智能', '机器人', '储能', '光伏', '芯片']
            if keyword in clear_business:
                confidence = 0.8
            
            extracted.append({
                'name': concept,
                'source': '主营业务',
                'confidence': confidence,
                'keyword': keyword,
            })
    
    # 去重（同名概念取最高置信度）
    result = {}
    for item in extracted:
        name = item['name']
        if name not in result or item['confidence'] > result[name]['confidence']:
            result[name] = item
    
    return list(result.values())


def get_complete_concepts(f10_concepts, business_text='', stock_name=''):
    """
    获取完整的概念列表（F10概念 + 业务关键词提取）
    
    Args:
        f10_concepts: F10原始概念列表
        business_text: 主营业务文本
        stock_name: 股票名称
    
    Returns:
        list: 完整的概念列表（带来源和置信度）
        [{'name': '储能', 'source': 'F10', 'confidence': 1.0}, ...]
    """
    all_concepts = {}
    
    # 1. F10概念（第一优先，置信度最高）
    if f10_concepts and isinstance(f10_concepts, list):
        for c in f10_concepts:
            if isinstance(c, str) and c:
                std_c = standardize_concept(c)
                all_concepts[std_c] = {
                    'name': std_c,
                    'source': 'F10官方',
                    'confidence': 1.0,  # F10官方概念，置信度最高
                    'original': c,
                }
    
    # 2. 主营业务关键词提取（第二优先，置信度中等）
    if business_text and isinstance(business_text, str):
        business_concepts = extract_concepts_from_business(business_text)
        for item in business_concepts:
            name = item['name']
            if name not in all_concepts:
                # 只有F10没有的概念才添加业务提取的
                all_concepts[name] = item
    
    # 3. 股票名称关键词提取（第三优先，置信度最低）
    if stock_name and isinstance(stock_name, str):
        name_concepts = extract_concepts_from_business(stock_name)
        for item in name_concepts:
            name = item['name']
            if name not in all_concepts:
                item['source'] = '股票名称'
                item['confidence'] = 0.3  # 名称匹配置信度最低
                all_concepts[name] = item
    
    # 4. 给每个概念设置等级
    for name, item in all_concepts.items():
        confidence = item.get('confidence', 0.5)
        source = item.get('source', '')
        
        if confidence >= 0.8 or source == 'F10官方':
            item['level'] = 'A'  # A级，参与AI决策
        elif confidence >= 0.6:
            item['level'] = 'B'  # B级，辅助参考
        else:
            item['level'] = 'C'  # C级，只显示
    
    return list(all_concepts.values())


def get_ai_scoring_concepts(f10_concepts, business_text='', stock_name=''):
    """
    获取用于AI评分的概念列表（只包含A级和B级，置信度>=0.6）
    
    低置信度概念（C级）只用于UI显示，不参与AI决策，避免误判
    
    Args:
        f10_concepts: F10原始概念列表
        business_text: 主营业务文本
        stock_name: 股票名称
    
    Returns:
        list: 用于AI评分的概念名称列表
    """
    try:
        complete = get_complete_concepts(f10_concepts, business_text, stock_name)
        
        # 只保留A级和B级（置信度>=0.6）
        ai_concepts = []
        for item in complete:
            if item.get('level') in ['A', 'B'] or item.get('confidence', 0) >= 0.6:
                ai_concepts.append(item['name'])
        
        return ai_concepts
    except Exception as e:
        print(f"[AI概念] 异常: {e}")
        # 降级：返回F10原始列表
        if f10_concepts and isinstance(f10_concepts, list):
            return [standardize_concept(c) for c in f10_concepts if isinstance(c, str)]
        return []


def calc_concept_accuracy(concept_info, f10_concepts=None, business_text='', stock_name=''):
    """
    计算概念准确度评分（0-100分）
    
    评分权重：
    - F10直接匹配：40分
    - 主营业务关键词匹配：40分（乘以置信度，避免过度推断）
    - 股票名称匹配：15分
    - 市场热度：5分
    
    注意：市场热度只占5%，因为我们要的是"公司真实属性"，不是追热点
    业务匹配权重很高，但要乘以置信度，避免过度推断
    
    Args:
        concept_info: 概念信息（dict，包含name, source, confidence）或字符串
        f10_concepts: F10概念列表
        business_text: 主营业务文本
        stock_name: 股票名称
    
    Returns:
        int: 准确度评分（0-100）
    """
    # 兼容字符串输入
    if isinstance(concept_info, str):
        concept_name = concept_info
        source = 'unknown'
        confidence = 0.5
    else:
        concept_name = concept_info.get('name', '')
        source = concept_info.get('source', 'unknown')
        confidence = concept_info.get('confidence', 0.5)
    
    score = 0
    
    # 1. F10直接匹配（40分）
    f10_score = 0
    if f10_concepts and isinstance(f10_concepts, list):
        for c in f10_concepts:
            if isinstance(c, str):
                std_c = standardize_concept(c)
                if std_c == concept_name or c == concept_name:
                    f10_score = 40
                    break
                # 部分匹配
                elif concept_name in c or c in concept_name:
                    f10_score = 25
                    break
    score += f10_score
    
    # 2. 主营业务关键词匹配（40分）- 乘以置信度，避免过度推断
    business_score = 0
    if business_text and isinstance(business_text, str):
        business_concepts = extract_concepts_from_business(business_text)
        for item in business_concepts:
            if item['name'] == concept_name:
                # 基础分40分，乘以置信度
                business_score = int(40 * item['confidence'])
                break
    score += business_score
    
    # 3. 股票名称匹配（15分）
    name_score = 0
    if stock_name and isinstance(stock_name, str):
        name_concepts = extract_concepts_from_business(stock_name)
        for item in name_concepts:
            if item['name'] == concept_name:
                name_score = int(15 * item['confidence'])
                break
    score += name_score
    
    # 4. 市场热度（5分）- 权重很低，只作为微调
    market_score = 0
    try:
        from strategy.theme_analyzer import get_concept_market
        market_concepts = get_concept_market()
        
        if market_concepts and len(market_concepts) > 0:
            for mc in market_concepts:
                mc_name = mc.get('name', '')
                mc_pct = mc.get('change_pct', 0)
                
                if mc_name and (mc_name in concept_name or concept_name in mc_name):
                    if mc_pct > 5:
                        market_score = 5
                    elif mc_pct > 3:
                        market_score = 4
                    elif mc_pct > 1:
                        market_score = 2
                    elif mc_pct > 0:
                        market_score = 1
                    break
    except Exception:
        pass
    
    score += market_score
    
    return min(score, 100)


def sort_concepts_by_accuracy(f10_concepts, business_text='', stock_name=''):
    """
    按照准确度评分对概念列表排序
    
    Args:
        f10_concepts: F10原始概念列表
        business_text: 主营业务文本
        stock_name: 股票名称
    
    Returns:
        list: 排序后的概念列表（按准确度从高到低）
    """
    if not f10_concepts and not business_text:
        return []
    
    try:
        # 1. 获取完整概念列表（F10 + 业务提取）
        complete_concepts = get_complete_concepts(f10_concepts, business_text, stock_name)
        
        if not complete_concepts or len(complete_concepts) == 0:
            return f10_concepts if isinstance(f10_concepts, list) else []
        
        # 2. 计算每个概念的准确度评分
        scored_concepts = []
        for concept_info in complete_concepts:
            if not isinstance(concept_info, dict):
                continue
            
            score = calc_concept_accuracy(
                concept_info,
                f10_concepts=f10_concepts,
                business_text=business_text,
                stock_name=stock_name
            )
            
            scored_concepts.append((concept_info['name'], score, concept_info))
        
        # 3. 按评分从高到低排序
        scored_concepts.sort(key=lambda x: x[1], reverse=True)
        
        # 4. 返回排序后的概念名称
        return [c[0] for c in scored_concepts]
    
    except Exception as e:
        print(f"[概念排序] 异常: {e}")
        # 降级：返回原始F10列表
        return f10_concepts if isinstance(f10_concepts, list) else []


def get_stock_concepts(code):
    """
    获取单只股票的所属概念列表（高质量）
    
    Args:
        code: 股票代码，如 '000402'
    
    Returns:
        tuple: (concepts, source)
            concepts: 概念列表
            source: 数据来源（'东方财富核心题材'/'同花顺'/'F10核心概念'/'接口异常'）
    """
    # 检查缓存
    cache_key = f'concepts_{code}'
    if cache_key in _concept_cache and cache_key in _cache_time:
        if time.time() - _cache_time[cache_key] < CACHE_EXPIRE:
            return _concept_cache[cache_key]

    concepts = []
    source = '接口异常'

    # ========== 优先级1：东方财富核心题材接口 ==========
    try:
        concepts = _get_concepts_from_eastmoney_core(code)
        if concepts and len(concepts) >= 2:
            source = '东方财富核心题材'
            _concept_cache[cache_key] = (concepts, source)
            _cache_time[cache_key] = time.time()
            return concepts, source
    except Exception as e:
        print(f"[概念服务] 东方财富核心题材接口失败: {e}")

    # ========== 优先级2：东方财富push2接口 ==========
    try:
        concepts = _get_concepts_from_eastmoney_push2(code)
        if concepts and len(concepts) >= 2:
            source = '东方财富行情'
            _concept_cache[cache_key] = (concepts, source)
            _cache_time[cache_key] = time.time()
            return concepts, source
    except Exception as e:
        print(f"[概念服务] 东方财富push2接口失败: {e}")

    # ========== 优先级3：F10核心概念接口 ==========
    try:
        concepts = _get_concepts_from_f10(code)
        if concepts:
            source = '东方财富F10'
            _concept_cache[cache_key] = (concepts, source)
            _cache_time[cache_key] = time.time()
            return concepts, source
    except Exception as e:
        print(f"[概念服务] F10核心概念接口失败: {e}")

    # 都失败
    _concept_cache[cache_key] = ([], source)
    _cache_time[cache_key] = time.time()
    return [], source


def _filter_concepts(concepts):
    """过滤概念：去除地域标签、行业标签、D级指数/资金标签"""
    filtered = []
    for c in concepts:
        # 过滤地域标签
        if c in AREA_TAGS:
            continue
        # 过滤行业标签
        if c in INDUSTRY_TAGS:
            continue
        # 过滤D级标签（指数、资金、身份标签）
        if c in D_LEVEL_TAGS:
            continue
        # 模糊匹配D级标签（包含关键词的也过滤）
        is_d_level = False
        for d_tag in D_LEVEL_TAGS:
            if d_tag in c or c in d_tag:
                is_d_level = True
                break
        if is_d_level:
            continue
        # 过滤太短的标签（单字）
        if len(c) <= 1:
            continue
        filtered.append(c)
    # 去重
    filtered = list(dict.fromkeys(filtered))
    return filtered[:8]  # 最多8个


def _get_concepts_from_eastmoney_core(code):
    """从东方财富核心题材接口获取概念（数据质量最高）"""
    # 判断市场
    if code.startswith('6'):
        market = 'SH'
    else:
        market = 'SZ'

    url = f'https://datacenter-web.eastmoney.com/api/data/v1/get'
    params = {
        'reportName': 'RPT_F10_CORETHEME_BOARDTYPE',
        'columns': 'ALL',
        'filter': f'(SECUCODE="{code}.{market}")',
        'pageSize': '50',
        'pageNumber': '1',
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []

        data = r.json()
        if not data.get('result') or not data['result'].get('data'):
            return []

        items = data['result']['data']
        concepts = []

        for item in items:
            # 核心题材名称
            name = item.get('BOARD_NAME', '')
            if name:
                concepts.append(name)

        # 过滤
        concepts = _filter_concepts(concepts)

        print(f"[概念服务] 东方财富核心题材返回 {code}: {concepts[:5]}")
        return concepts

    except Exception as e:
        print(f"[概念服务] 东方财富核心题材接口异常: {e}")
        return []


def _get_concepts_from_eastmoney_push2(code):
    """从东方财富push2行情接口获取概念"""
    # 判断市场
    if code.startswith('6'):
        secid = f'1.{code}'
    else:
        secid = f'0.{code}'

    # 尝试https和http
    urls = [
        f'https://push2delay.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f127,f128,f129,f130',
        f'http://push2delay.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f127,f128,f129,f130',
    ]

    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue

            data = r.json()
            if not data.get('data'):
                continue

            d = data['data']
            concepts = []

            # f127: 行业
            industry = d.get('f127', '')
            if industry and industry != '-':
                concepts.append(industry)

            # f129: 概念
            concept_str = d.get('f129', '')
            if concept_str and concept_str != '-':
                concept_list = concept_str.split(',')
                concepts.extend([c.strip() for c in concept_list if c.strip()])

            # f130: 风格
            style = d.get('f130', '')
            if style and style != '-':
                style_list = style.split(',')
                concepts.extend([s.strip() for s in style_list if s.strip()])

            # 过滤
            concepts = _filter_concepts(concepts)

            print(f"[概念服务] 东方财富push2返回 {code}: {concepts[:5]}")
            return concepts

        except Exception as e:
            print(f"[概念服务] push2接口失败: {e}")
            continue

    return []


def _get_concepts_from_f10(code):
    """从东方财富F10核心概念接口获取概念（备用）"""
    if code.startswith('6'):
        market = 'SH'
    else:
        market = 'SZ'

    url = f'https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={market}{code}'

    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []

        data = r.json()
        concepts = []

        # 核心概念
        if data.get('hxgn') and len(data['hxgn']) > 0:
            for item in data['hxgn']:
                name = item.get('BOARD_NAME', '')
                if name:
                    concepts.append(name)

        # 所属板块
        if data.get('ssbk') and len(data['ssbk']) > 0:
            for item in data['ssbk']:
                name = item.get('BOARD_NAME', '')
                if name:
                    concepts.append(name)

        # 过滤
        concepts = _filter_concepts(concepts)

        print(f"[概念服务] F10核心概念返回 {code}: {concepts[:5]}")
        return concepts

    except Exception as e:
        print(f"[概念服务] F10核心概念接口异常: {e}")
        return []


def get_stock_industry_f10(code):
    """
    从东方财富F10获取行业分类（用于sector字段）
    
    Args:
        code: 股票代码
    
    Returns:
        str: 行业分类
    """
    cache_key = f'industry_{code}'
    if cache_key in _concept_cache and cache_key in _cache_time:
        if time.time() - _cache_time[cache_key] < CACHE_EXPIRE:
            return _concept_cache[cache_key]

    try:
        if code.startswith('6'):
            market = 'SH'
        else:
            market = 'SZ'

        url = f'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={market}{code}'
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return '--'

        data = r.json()

        if data.get('jbzl') and len(data['jbzl']) > 0:
            jbzl = data['jbzl'][0]
            industry = jbzl.get('INDUSTRYCSRC1', '')
            if industry:
                _concept_cache[cache_key] = industry
                _cache_time[cache_key] = time.time()
                return industry

    except Exception as e:
        print(f"[概念服务] 获取F10行业失败: {e}")

    return '--'


def batch_get_concepts(codes):
    """
    批量获取多只股票的概念
    
    Args:
        codes: 股票代码列表
    
    Returns:
        dict: {code: ([concepts], source)}
    """
    result = {}
    for code in codes:
        result[code] = get_stock_concepts(code)
        time.sleep(0.2)  # 避免请求过快
    return result


if __name__ == '__main__':
    # 测试
    print("测试概念数据服务（高质量版）...")
    print("=" * 60)

    test_codes = ['000402', '300355', '002146']
    for code in test_codes:
        concepts, source = get_stock_concepts(code)
        industry = get_stock_industry_f10(code)
        print(f"\n{code}:")
        print(f"  行业(F10): {industry}")
        print(f"  概念来源: {source}")
        print(f"  概念数量: {len(concepts)}")
        print(f"  概念列表: {concepts}")

    print("\n" + "=" * 60)
    print("测试完成")
