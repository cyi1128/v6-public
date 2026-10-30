# -*- coding: utf-8 -*-
"""
V1.3-A-4-DEV Step1：涨停原因卡片字段读取接口
独立UI层模块，只读取FROZEN版本的分析结果，不修改核心算法。

功能：
1. 调用 limit_up_reason_engine.analyze() 获取原始数据
2. 格式化为UI可展示的结构化数据
3. 提供主营/热点/公告/风险的展示文本映射

原则：
- 不修改 limit_up_reason_engine.py（FROZEN）
- 不修改评分公式
- 只做数据读取和格式化
"""

import time
from typing import Dict, List, Optional, Any


# ========== 展示文本映射表 ==========

# 主营匹配等级 → 展示文本
BUSINESS_LEVEL_TEXT = {
    'S': '主营高度匹配',
    'A': '产业链相关',
    'B': '行业相关',
    'C': '无直接支撑',
}

# 主营匹配等级 → 图标
BUSINESS_LEVEL_ICON = {
    'S': '✅',
    'A': '✅',
    'B': '⚠️',
    'C': '❌',
}

# 可信度等级 → 颜色
CONFIDENCE_LEVEL_COLOR = {
    'A': '#FF4444',  # 红色
    'B': '#FFAA00',  # 黄色
    'C': '#888888',  # 灰色
}

# 可信度等级 → 描述
CONFIDENCE_LEVEL_DESC = {
    'A': '主线龙头，逻辑充分',
    'B': '有一定支撑，可重点观察',
    'C': '逻辑证据不足，需谨慎',
}

# 公告等级 → 展示文本
ANNOUNCEMENT_LEVEL_TEXT = {
    0: '无公告催化',
    1: '一级催化（强催化）',
    2: '二级催化（中等催化）',
    3: '三级公告（仅展示，不加分）',
}

# 公告等级 → 图标
ANNOUNCEMENT_LEVEL_ICON = {
    0: '➖',
    1: '⭐⭐⭐',
    2: '⭐⭐',
    3: '📋',
}

# 热点关联等级 → 展示文本
HOT_RELATION_TEXT = {
    'H1': '核心龙头',
    'H2': '板块中军',
    'H3': '板块跟风',
    '': '未关联',
}

# 评分项 → 中文名称
SCORE_BREAKDOWN_LABELS = {
    'base': '基础分',
    'theme': '题材分',
    'business': '主营分',
    'hot': '热点分',
    'announcement': '公告分',
    'news': '新闻分',
    'chain': '连板分',
}


def get_reason_analysis(code: str, name: str, limit_up_data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    获取涨停原因分析结果（调用FROZEN核心引擎）

    参数：
        code: 股票代码
        name: 股票名称
        limit_up_data: 涨停事实数据（可选）

    返回：
        dict: 原始分析结果
    """
    from strategy.limit_up_reason_engine import get_limit_up_reason_engine
    engine = get_limit_up_reason_engine()
    return engine.analyze(code, name, limit_up_data)


def _format_catalyst_text(catalyst):
    """
    将公告/新闻催化字典格式化为可读文本
    避免在UI上显示原始字典数据

    参数：
        catalyst: 催化字典或None

    返回：
        str: 可读的催化描述文本
    """
    if catalyst is None:
        return ''

    # 如果已经是字符串，直接返回
    if isinstance(catalyst, str):
        return catalyst

    # 如果是字典，格式化
    if isinstance(catalyst, dict):
        title = catalyst.get('title', '')
        ann_type = catalyst.get('type', '')
        date = catalyst.get('date', '')
        score = catalyst.get('score', 0)
        evidence = catalyst.get('evidence', '')

        # 优先使用evidence（已经格式化好的文本），但清理重复表述
        if evidence and isinstance(evidence, str) and len(evidence) < 100:
            # 清理"例行公告公告"这种重复
            cleaned = evidence.replace('公告公告', '公告')
            return cleaned

        # 否则拼接title + date + type
        parts = []
        if title:
            parts.append(title)
        if date:
            parts.append(date)
        if ann_type and ann_type != title:
            parts.append(ann_type)

        if parts:
            return ' | '.join(parts)

        # 最后兜底：返回type或空字符串
        return ann_type if ann_type else ''

    # 其他类型，转字符串但截断
    text = str(catalyst)
    return text[:80] + '...' if len(text) > 80 else text


def format_reason_card(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将原始分析结果格式化为UI卡片可展示的结构化数据

    参数：
        raw_data: limit_up_reason_engine.analyze() 的返回值

    返回：
        dict: 格式化后的卡片数据，结构如下：
        {
            'basic_info': {...},           # 基本信息
            'confidence': {...},           # 可信度展示
            'core_theme': {...},           # 核心题材
            'business': {...},             # 主营逻辑
            'hot': {...},                  # 热点逻辑
            'announcement': {...},         # 公告催化
            'news': {...},                 # 新闻催化
            'score_breakdown': [...],      # 评分拆解列表
            'risk_warnings': [...],        # 风险提示列表
            'evidence_list': [...],        # 证据列表
        }
    """
    # 基本信息
    basic_info = {
        'code': raw_data.get('code', ''),
        'name': raw_data.get('name', ''),
        'reason_text': raw_data.get('limit_up_reason', ''),
        'reason_tags': raw_data.get('limit_up_reason_tags', []),
        'data_sources': raw_data.get('limit_up_reason_source', []),
        'timestamp': raw_data.get('timestamp', time.time()),
    }

    # 可信度展示
    confidence_level = raw_data.get('limit_up_reason_level', 'C')
    confidence_score = raw_data.get('limit_up_reason_confidence', 0)
    confidence = {
        'level': confidence_level,
        'score': confidence_score,
        'color': CONFIDENCE_LEVEL_COLOR.get(confidence_level, '#888888'),
        'description': CONFIDENCE_LEVEL_DESC.get(confidence_level, ''),
    }

    # 核心题材
    core_theme = {
        'theme': raw_data.get('core_theme', ''),
        'theme_score': raw_data.get('theme_score', 0),
    }

    # 主营逻辑
    business_level = raw_data.get('business_match_level', 'C')
    business_score = raw_data.get('business_match_score', 0)
    business = {
        'level': business_level,
        'score': business_score,
        'text': BUSINESS_LEVEL_TEXT.get(business_level, '未知'),
        'icon': BUSINESS_LEVEL_ICON.get(business_level, '❓'),
        'is_supported': business_level in ['S', 'A'],
    }

    # 热点逻辑
    hot_score = raw_data.get('hot_score', 0)
    hot_source = raw_data.get('hot_source', '')
    hot_confidence = raw_data.get('hot_confidence', '')
    hot_reason = raw_data.get('hot_reason', '')
    hot_relation = raw_data.get('hot_relation_level', '')
    hot = {
        'score': hot_score,
        'source': hot_source,
        'confidence': hot_confidence,
        'reason': hot_reason,
        'relation_level': hot_relation,
        'relation_text': HOT_RELATION_TEXT.get(hot_relation, '未关联'),
        'is_hot': hot_score > 0,
        'is_p0': hot_source == '涨停池统计',
    }

    # 公告催化
    ann_level = raw_data.get('announcement_level', 0)
    ann_catalyst = raw_data.get('announcement_catalyst')
    # 格式化catalyst为可读文本（避免显示原始字典）
    ann_catalyst_text = _format_catalyst_text(ann_catalyst)
    announcement = {
        'level': ann_level,
        'text': ANNOUNCEMENT_LEVEL_TEXT.get(ann_level, '未知'),
        'icon': ANNOUNCEMENT_LEVEL_ICON.get(ann_level, '❓'),
        'catalyst': ann_catalyst,
        'catalyst_text': ann_catalyst_text,
        'is_level1': ann_level == 1,
        'is_scored': ann_level in [1, 2],  # 三级公告不加分
    }

    # 新闻催化 - 补充详情
    news_catalyst = raw_data.get('news_catalyst')
    news = {
        'has_news': news_catalyst is not None,
        'catalyst': news_catalyst,
    }
    # 提取新闻详情
    if news_catalyst and isinstance(news_catalyst, dict):
        news['title'] = news_catalyst.get('title', '')
        news['source'] = news_catalyst.get('source', '')
        news['keyword'] = news_catalyst.get('keyword', '')
        news['url'] = news_catalyst.get('url', '')
        news['time'] = news_catalyst.get('time', '')

    # 评分拆解
    score_breakdown_raw = raw_data.get('score_breakdown', {})
    score_breakdown = []
    for key, label in SCORE_BREAKDOWN_LABELS.items():
        if key in score_breakdown_raw:
            score_breakdown.append({
                'key': key,
                'label': label,
                'score': score_breakdown_raw[key],
            })
    total_score = sum(item['score'] for item in score_breakdown)

    # 风险提示（自动生成）
    risk_warnings = _generate_risk_warnings(raw_data)

    # 证据列表 - 格式化
    evidence_raw = raw_data.get('evidence_list', raw_data.get('evidence', []))
    evidence_detail = []
    for ev in evidence_raw:
        if isinstance(ev, str):
            evidence_detail.append({'text': ev, 'type': 'info'})
        elif isinstance(ev, dict):
            evidence_detail.append({
                'text': ev.get('text', ev.get('evidence', str(ev))),
                'type': ev.get('type', 'info'),
            })

    # 概念标签
    concepts = raw_data.get('concepts', [])
    concept_source = raw_data.get('concept_source', '')

    # 股票基本信息
    stock_info = raw_data.get('stock_info', {})

    return {
        'basic_info': basic_info,
        'confidence': confidence,
        'core_theme': core_theme,
        'business': business,
        'hot': hot,
        'announcement': announcement,
        'news': news,
        'score_breakdown': score_breakdown,
        'total_score': total_score,
        'risk_warnings': risk_warnings,
        'evidence_list': evidence_raw,
        'evidence_detail': evidence_detail,
        'reason_evidence': raw_data.get('reason_evidence', {}),
        'concepts': concepts,
        'concept_source': concept_source,
        'stock_info': stock_info,
    }


def _generate_risk_warnings(raw_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    根据分析结果自动生成风险提示

    参数：
        raw_data: 原始分析结果

    返回：
        list: 风险提示列表，每项包含 {'level': 'warning'/'info', 'text': '...'}
    """
    warnings = []

    # 主营C级
    business_level = raw_data.get('business_match_level', 'C')
    if business_level == 'C':
        warnings.append({
            'level': 'warning',
            'text': '⚠ 主营无直接支撑，涨停逻辑偏弱',
        })
    elif business_level == 'B':
        warnings.append({
            'level': 'info',
            'text': 'ℹ 主营仅行业相关，需关注业务关联度',
        })

    # 无一级公告
    ann_level = raw_data.get('announcement_level', 0)
    if ann_level != 1:
        if ann_level == 3:
            warnings.append({
                'level': 'info',
                'text': 'ℹ 仅有常规公告（三级，不加分）',
            })
        elif ann_level == 0:
            warnings.append({
                'level': 'warning',
                'text': '⚠ 暂无公告催化',
            })

    # 无新闻
    news_catalyst = raw_data.get('news_catalyst')
    if news_catalyst is None:
        warnings.append({
            'level': 'info',
            'text': 'ℹ 暂无新闻催化',
        })

    # 热点低
    hot_score = raw_data.get('hot_score', 0)
    if hot_score == 0:
        warnings.append({
            'level': 'warning',
            'text': '⚠ 未检测到板块热点',
        })
    elif hot_score < 5:
        warnings.append({
            'level': 'info',
            'text': 'ℹ 板块热度较低',
        })

    # 可信度C级
    confidence_level = raw_data.get('limit_up_reason_level', 'C')
    if confidence_level == 'C':
        warnings.append({
            'level': 'warning',
            'text': '⚠ 综合可信度C级，逻辑证据不足',
        })

    # 跟风股（热点H3 + 主营C）
    hot_relation = raw_data.get('hot_relation_level', '')
    if hot_relation == 'H3' and business_level == 'C':
        warnings.append({
            'level': 'warning',
            'text': '⚠ 板块跟风股，主营无支撑，追高风险大',
        })

    return warnings


def get_card_summary(card_data: Dict[str, Any]) -> str:
    """
    生成卡片摘要文本（用于列表展示）

    参数：
        card_data: format_reason_card() 的返回值

    返回：
        str: 摘要文本
    """
    confidence = card_data['confidence']
    business = card_data['business']
    hot = card_data['hot']

    parts = []
    parts.append(f"{confidence['level']}级 {confidence['score']}分")
    parts.append(f"题材：{card_data['core_theme']['theme']}")
    parts.append(f"主营：{business['text']}")
    if hot['is_hot']:
        parts.append(f"热点：{hot['reason'][:20]}")

    return ' | '.join(parts)


def analyze_and_format(code: str, name: str, limit_up_data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    一站式接口：分析 + 格式化 + 补充真实数据

    参数：
        code: 股票代码
        name: 股票名称
        limit_up_data: 涨停事实数据（可选）

    返回：
        dict: 格式化后的卡片数据
    """
    raw_data = get_reason_analysis(code, name, limit_up_data)
    # 补充code和name（engine返回中可能没有）
    raw_data['code'] = code
    raw_data['name'] = name

    # 补充股票基本信息（从limit_up_data提取）
    if limit_up_data:
        raw_data['stock_info'] = {
            'industry': limit_up_data.get('industry', ''),
            'pct_chg': limit_up_data.get('pct_chg', 0),
            'turnover_rate': limit_up_data.get('turnover_rate', limit_up_data.get('turnover', 0)),
            'amount': limit_up_data.get('amount', 0),
            'consecutive_days': limit_up_data.get('consecutive_days', limit_up_data.get('lbc', 1)),
            'price': limit_up_data.get('price', 0),
        }
    else:
        raw_data['stock_info'] = {}

    # 补充概念标签列表（从概念服务获取，有缓存）
    try:
        from service.concept_service import get_stock_concepts, D_LEVEL_TAGS, AREA_TAGS
        concepts, concept_source = get_stock_concepts(code)
        # 过滤掉D级禁止标签和地域标签
        filtered_concepts = [
            c.strip() for c in concepts
            if c.strip() and c.strip() not in D_LEVEL_TAGS and c.strip() not in AREA_TAGS
        ]
        raw_data['concepts'] = filtered_concepts
        raw_data['concept_source'] = concept_source
    except Exception as e:
        print(f"[limit_up_reason_card] 获取概念标签失败: {e}")
        raw_data['concepts'] = []
        raw_data['concept_source'] = '获取失败'

    return format_reason_card(raw_data)


# ========== 测试代码 ==========
if __name__ == '__main__':
    print('=' * 80)
    print('V1.3-A-4-DEV Step1：字段读取接口测试')
    print('=' * 80)

    # 测试样本
    test_cases = [
        ('000815', '美利云', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 3, 'trade_date': '20260804'}),
        ('600666', '奥瑞德', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 1, 'trade_date': '20260804'}),
        ('300615', '欣天科技', {'is_limit_up': True, 'pct_chg': 10.0, 'consecutive_days': 2, 'trade_date': '20260804'}),
    ]

    for code, name, limit_data in test_cases:
        print(f'\n{"─" * 80}')
        print(f'测试：{name}({code})')
        print(f'{"─" * 80}')

        try:
            card = analyze_and_format(code, name, limit_data)

            print(f'\n【基本信息】')
            print(f"  股票：{card['basic_info']['name']}({card['basic_info']['code']})")
            print(f"  涨停原因：{card['basic_info']['reason_text']}")
            print(f"  数据来源：{', '.join(card['basic_info']['data_sources'])}")

            print(f'\n【可信度】')
            print(f"  等级：{card['confidence']['level']}级")
            print(f"  分数：{card['confidence']['score']}")
            print(f"  颜色：{card['confidence']['color']}")
            print(f"  描述：{card['confidence']['description']}")

            print(f'\n【核心题材】')
            print(f"  题材：{card['core_theme']['theme']}")
            print(f"  题材分：{card['core_theme']['theme_score']}")

            print(f'\n【主营逻辑】')
            print(f"  等级：{card['business']['level']}")
            print(f"  分数：{card['business']['score']}")
            print(f"  展示：{card['business']['icon']} {card['business']['text']}")
            print(f"  有支撑：{card['business']['is_supported']}")

            print(f'\n【热点逻辑】')
            print(f"  热点分：{card['hot']['score']}")
            print(f"  来源：{card['hot']['source']}")
            print(f"  置信度：{card['hot']['confidence']}")
            print(f"  原因：{card['hot']['reason']}")
            print(f"  关联：{card['hot']['relation_text']}({card['hot']['relation_level']})")
            print(f"  P0来源：{card['hot']['is_p0']}")

            print(f'\n【公告催化】')
            print(f"  等级：L{card['announcement']['level']}")
            print(f"  展示：{card['announcement']['icon']} {card['announcement']['text']}")
            print(f"  一级催化：{card['announcement']['is_level1']}")
            print(f"  加分：{card['announcement']['is_scored']}")

            print(f'\n【新闻催化】')
            print(f"  有新闻：{card['news']['has_news']}")

            print(f'\n【评分拆解】')
            for item in card['score_breakdown']:
                print(f"  {item['label']}：{item['score']}")
            print(f"  总分：{card['total_score']}")

            print(f'\n【风险提示】')
            for w in card['risk_warnings']:
                print(f"  [{w['level']}] {w['text']}")

            print(f'\n【卡片摘要】')
            print(f"  {get_card_summary(card)}")

        except Exception as e:
            print(f'  ❌ 失败：{e}')
            import traceback
            traceback.print_exc()

    print(f'\n{"=" * 80}')
    print('Step1 字段读取接口测试完成')
    print('=' * 80)
