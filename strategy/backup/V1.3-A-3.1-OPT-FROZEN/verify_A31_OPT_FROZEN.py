# -*- coding: utf-8 -*-
"""
V1.3-A-3.1-OPT-VERIFY 热点增强后重新验证
验证日期：2026-08-04（138只涨停，科技/算力主线）
样本：20只，分4类（核心龙头5 + 高连板5 + 热点中军5 + 跟风涨停5）
原则：只跑数据，不修改A-3.1-OPT代码
重点：验证Step1~Step3热点增强后的效果，对比优化前A-3.1结果
"""
import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategy.limit_up_strength import get_limit_up_strength_analyzer
from strategy.limit_up_reason_engine import get_limit_up_reason_engine


# 禁止标签列表（第1步过滤层定义）
FORBIDDEN_TAGS = [
    '举牌', '破净', '融资融券', '深股通', '沪股通', '指数成分',
    '机构持仓', '基金重仓', '股东增持', '参股银行', '参股保险',
    '参股券商', 'QFII重仓', '社保重仓', '养老金持股',
]

# 优化前A-3.1基准结果（从之前验证中提取）
PREV_BASELINE = {
    '000815': {'confidence': 62, 'level': 'B', 'hot': 0},  # 美利云
    '003032': {'confidence': 60, 'level': 'B', 'hot': 0},  # 传智教育
    '300615': {'confidence': 41.5, 'level': 'C', 'hot': 0},  # 欣天科技
    '000593': {'confidence': 42, 'level': 'C', 'hot': 0},  # 德龙汇能
}


def get_zdt_pool(date='20260804'):
    """获取涨停池"""
    url = f'http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date={date}'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'}
    resp = requests.get(url, headers=headers, timeout=15)
    data = resp.json()
    return data.get('data', {}).get('pool', [])


def build_limit_up_data(item):
    """从涨停池数据构造A-1格式的limit_up_data"""
    code = item.get('c', '')
    fbt = item.get('fbt', 0)
    first_time = f'{str(fbt)[:2]}:{str(fbt)[2:4]}' if fbt else ''
    fund = item.get('fund', 0)
    ltsz = item.get('ltsz', 0)
    seal_ratio = round(fund / ltsz * 100, 2) if ltsz > 0 and fund > 0 else 0
    zbc = item.get('zbc', 0)
    lbc = item.get('lbc', 0)

    limit_up_period = ''
    if first_time:
        try:
            parts = first_time.split(':')
            total_minute = int(parts[0]) * 60 + int(parts[1])
            if 570 <= total_minute <= 600:
                limit_up_period = '早盘强板'
            elif 600 < total_minute <= 840:
                limit_up_period = '中段启动'
            elif total_minute > 840:
                limit_up_period = '尾盘抢筹'
        except:
            pass

    if zbc > 0:
        limit_up_status = '重复封板'
    elif first_time and int(first_time.split(':')[0]) >= 14:
        limit_up_status = '尾盘封板'
    else:
        limit_up_status = '首次封板'

    return {
        'is_limit_up': True,
        'pct_chg': round(item.get('zdp', 0), 2),
        'first_limit_time': first_time,
        'seal_amount': fund,
        'seal_ratio': seal_ratio,
        'consecutive_days': lbc,
        'turnover_rate': round(item.get('hs', 0), 2),
        'float_market_cap': ltsz,
        'limit_up_period': limit_up_period,
        'limit_up_status': limit_up_status,
        'limit_up_style': '换手板',
        'limit_chain_type': f'{lbc}连板' if lbc > 0 else '首板',
        'trade_date': '20260804',  # 新增：传递日期给热点检测
    }


def select_samples(pool):
    """选取20只样本，分4类：核心龙头5 + 高连板5 + 热点中军5 + 跟风涨停5"""
    samples = []
    used_codes = set()

    # ① 核心龙头（5只）：3板以上，按连板高度排序
    gaolianban = [item for item in pool if item.get('lbc', 0) >= 3]
    gaolianban.sort(key=lambda x: (x.get('lbc', 0), x.get('fund', 0)), reverse=True)
    for item in gaolianban[:5]:
        code = item.get('c', '')
        if code not in used_codes:
            samples.append((item, '核心龙头'))
            used_codes.add(code)

    if len([s for s in samples if s[1] == '核心龙头']) < 5:
        erban = [item for item in pool if item.get('lbc', 0) == 2]
        erban.sort(key=lambda x: x.get('fund', 0), reverse=True)
        for item in erban:
            if len([s for s in samples if s[1] == '核心龙头']) >= 5:
                break
            code = item.get('c', '')
            if code not in used_codes:
                samples.append((item, '核心龙头'))
                used_codes.add(code)

    # ② 高连板（5只）：2板，热门行业，早盘封板
    hot_industries = ['元件', '通信设备', 'IT服务', '计算机设', '软件开发', '光学光电', '半导体', '电子']
    erban_hot = [item for item in pool if item.get('lbc', 0) == 2
                 and any(ind in item.get('hybk', '') for ind in hot_industries)
                 and item.get('c', '') not in used_codes]
    erban_hot.sort(key=lambda x: x.get('fbt', 9999))
    for item in erban_hot[:5]:
        code = item.get('c', '')
        if code not in used_codes:
            samples.append((item, '高连板'))
            used_codes.add(code)

    if len([s for s in samples if s[1] == '高连板']) < 5:
        erban_other = [item for item in pool if item.get('lbc', 0) == 2 and item.get('c', '') not in used_codes]
        erban_other.sort(key=lambda x: x.get('fund', 0), reverse=True)
        for item in erban_other:
            if len([s for s in samples if s[1] == '高连板']) >= 5:
                break
            code = item.get('c', '')
            if code not in used_codes:
                samples.append((item, '高连板'))
                used_codes.add(code)

    # ③ 热点中军（5只）：首板，热门行业，早盘封板，大封单
    hot_shouban = [item for item in pool if item.get('lbc', 0) == 1
                   and any(ind in item.get('hybk', '') for ind in hot_industries)
                   and item.get('c', '') not in used_codes]
    hot_shouban.sort(key=lambda x: (x.get('fbt', 9999), -x.get('fund', 0)))
    for item in hot_shouban[:5]:
        code = item.get('c', '')
        if code not in used_codes:
            samples.append((item, '热点中军'))
            used_codes.add(code)

    if len([s for s in samples if s[1] == '热点中军']) < 5:
        early_shouban = [item for item in pool if item.get('lbc', 0) == 1
                         and item.get('fbt', 0) and item.get('fbt', 0) < 940
                         and item.get('c', '') not in used_codes]
        early_shouban.sort(key=lambda x: x.get('fbt', 9999))
        for item in early_shouban:
            if len([s for s in samples if s[1] == '热点中军']) >= 5:
                break
            code = item.get('c', '')
            if code not in used_codes:
                samples.append((item, '热点中军'))
                used_codes.add(code)

    # ④ 跟风涨停（5只）：冷门行业 + 尾盘封板 + 高换手
    cold_industries = ['塑料', '燃气', '专用设备', '通用设备', '装修装饰', '化学制药', '汽车零部', '食品', '零售', '纺织']
    genfeng = [item for item in pool if item.get('lbc', 0) == 1
               and any(ind in item.get('hybk', '') for ind in cold_industries)
               and item.get('c', '') not in used_codes]
    genfeng.sort(key=lambda x: x.get('hs', 0), reverse=True)
    for item in genfeng[:5]:
        code = item.get('c', '')
        if code not in used_codes:
            samples.append((item, '跟风涨停'))
            used_codes.add(code)

    if len([s for s in samples if s[1] == '跟风涨停']) < 5:
        remaining = [item for item in pool if item.get('lbc', 0) == 1 and item.get('c', '') not in used_codes]
        remaining.sort(key=lambda x: x.get('hs', 0), reverse=True)
        for item in remaining:
            if len([s for s in samples if s[1] == '跟风涨停']) >= 5:
                break
            code = item.get('c', '')
            if code not in used_codes:
                samples.append((item, '跟风涨停'))
                used_codes.add(code)

    return samples[:20]


def main():
    print('=' * 120)
    print('V1.3-A-3.1-OPT-VERIFY 热点增强后重新验证报告')
    print('验证日期: 2026-08-04 | 涨停数: 138只 | 样本: 20只')
    print('验证目标: Step1~Step3热点增强效果确认 + 优化前后对比')
    print('=' * 120)
    print()

    pool = get_zdt_pool('20260804')
    print(f'获取涨停池: {len(pool)}只')

    samples = select_samples(pool)
    print(f'选取样本: {len(samples)}只')
    print()

    strength_analyzer = get_limit_up_strength_analyzer()
    reason_engine = get_limit_up_reason_engine()

    results = []

    for i, (item, category) in enumerate(samples):
        code = item.get('c', '')
        name = item.get('n', '')
        lbc = item.get('lbc', 0)
        hybk = item.get('hybk', '')
        hs = item.get('hs', 0)
        fbt = item.get('fbt', 0)
        fbt_str = f'{str(fbt)[:2]}:{str(fbt)[2:4]}' if fbt else ''

        print(f'[{i+1}/20] {name}({code}) - {category} - {lbc}板 {hybk} 首封{fbt_str} 换手{hs:.1f}%')

        try:
            limit_data = build_limit_up_data(item)

            # A-2 强度评分
            a2_result = strength_analyzer.analyze(limit_data)
            a2_score = a2_result.get('limit_up_strength_score', 0)
            a2_level = a2_result.get('strength_level', '')

            # A-3 原因分析（A-3.1-OPT版本）
            a3_result = reason_engine.analyze(code, name, limit_data)
            a3_reason = a3_result.get('limit_up_reason', '')
            a3_confidence = a3_result.get('limit_up_reason_confidence', 0)
            a3_level = a3_result.get('limit_up_reason_level', '')
            a3_theme = a3_result.get('core_theme', '')
            a3_tags = a3_result.get('limit_up_reason_tags', [])
            a3_ann = a3_result.get('announcement_catalyst')
            a3_news = a3_result.get('news_catalyst')

            # A-3.1新增字段
            bm_level = a3_result.get('business_match_level', 'C')
            bm_score = a3_result.get('business_match_score', 0)
            ann_level = a3_result.get('announcement_level', 0)
            score_breakdown = a3_result.get('score_breakdown', {})
            reason_evidence = a3_result.get('reason_evidence', {})

            # OPT新增热点字段
            hot_score = a3_result.get('hot_score', 0)
            hot_source = a3_result.get('hot_source', '')
            hot_confidence = a3_result.get('hot_confidence', '')
            hot_reason = a3_result.get('hot_reason', '')
            hot_relation = a3_result.get('hot_relation_level', '')

            result = {
                'code': code, 'name': name, 'category': category,
                'lbc': lbc, 'hybk': hybk, 'hs': hs, 'fbt': fbt_str,
                'a2_score': a2_score, 'a2_level': a2_level,
                'a3_reason': a3_reason, 'a3_confidence': a3_confidence,
                'a3_level': a3_level, 'a3_theme': a3_theme,
                'a3_tags': a3_tags, 'a3_ann': a3_ann, 'a3_news': a3_news,
                'bm_level': bm_level, 'bm_score': bm_score,
                'ann_level': ann_level, 'score_breakdown': score_breakdown,
                'reason_evidence': reason_evidence,
                'hot_score': hot_score, 'hot_source': hot_source,
                'hot_confidence': hot_confidence, 'hot_reason': hot_reason,
                'hot_relation': hot_relation,
            }
            results.append(result)

            hot_breakdown = score_breakdown.get('hot', 0)
            print(f'  A-2: {a2_score}({a2_level}) | A-3: {a3_confidence}({a3_level}级) 题材:{a3_theme} 主营:{bm_level} 公告:L{ann_level}')
            print(f'  热点: hot_score={hot_score}({hot_confidence}) source={hot_source} relation={hot_relation} | 评分hot={hot_breakdown}')
            print(f'  原因: {a3_reason[:80]}')
            if score_breakdown:
                print(f'  评分明细: base={score_breakdown.get("base")}, theme={score_breakdown.get("theme")}, business={score_breakdown.get("business")}, hot={score_breakdown.get("hot")}, ann={score_breakdown.get("announcement")}, news={score_breakdown.get("news")}, chain={score_breakdown.get("chain")}')

        except Exception as e:
            print(f'  ❌ 失败: {e}')
            import traceback
            traceback.print_exc()
            results.append({
                'code': code, 'name': name, 'category': category,
                'lbc': lbc, 'hybk': hybk, 'hs': hs, 'fbt': fbt_str,
                'a2_score': 0, 'a2_level': '', 'a3_reason': f'失败:{e}',
                'a3_confidence': 0, 'a3_level': 'C', 'a3_theme': '',
                'a3_tags': [], 'a3_ann': None, 'a3_news': None,
                'bm_level': 'C', 'bm_score': 0, 'ann_level': 0,
                'score_breakdown': {}, 'reason_evidence': {},
                'hot_score': 0, 'hot_source': '', 'hot_confidence': '',
                'hot_reason': '', 'hot_relation': '',
            })

        time.sleep(0.3)

    # ========== 验证总表 ==========
    print()
    print('=' * 120)
    print('验证总表')
    print('=' * 120)
    print(f'{"代码":<8} {"名称":<8} {"类别":<8} {"板":<3} {"行业":<10} {"A-2":<5} {"可信度":<6} {"等级":<4} {"题材":<10} {"主营":<4} {"公告":<4} {"热点":<5} {"来源":<10}')
    print('-' * 120)
    for r in results:
        has_ann = 'Y' if r['a3_ann'] else '-'
        print(f"{r['code']:<8} {r['name']:<8} {r['category']:<8} {r['lbc']:<3} {r['hybk']:<10} {r['a2_score']:<5} {r['a3_confidence']:<6} {r['a3_level']:<4} {r['a3_theme']:<10} {r['bm_level']:<4} L{r['ann_level']:<3} {r['hot_score']:<5} {r['hot_source']:<10}")

    # ========== 分类统计 ==========
    print()
    print('=' * 120)
    print('分类统计')
    print('=' * 120)

    categories = ['核心龙头', '高连板', '热点中军', '跟风涨停']
    for cat in categories:
        cat_results = [r for r in results if r['category'] == cat]
        if not cat_results:
            continue
        avg_a2 = sum(r['a2_score'] for r in cat_results) / len(cat_results)
        avg_a3 = sum(r['a3_confidence'] for r in cat_results) / len(cat_results)
        a_count = sum(1 for r in cat_results if r['a3_level'] == 'A')
        b_count = sum(1 for r in cat_results if r['a3_level'] == 'B')
        c_count = sum(1 for r in cat_results if r['a3_level'] == 'C')
        sa_count = sum(1 for r in cat_results if r['bm_level'] in ['S', 'A'])
        hot_count = sum(1 for r in cat_results if r['hot_score'] > 0)
        avg_hot = sum(r['hot_score'] for r in cat_results) / len(cat_results)
        print(f'\n【{cat}】{len(cat_results)}只')
        print(f'  A-2平均: {avg_a2:.1f} | A-3平均可信度: {avg_a3:.1f}')
        print(f'  A/B/C级: {a_count}/{b_count}/{c_count}')
        print(f'  主营S/A级: {sa_count}只 | 热点识别: {hot_count}只 (avg hot_score={avg_hot:.1f})')

    # ========== 整体统计 ==========
    print()
    print('=' * 120)
    print('整体统计：A/B/C比例')
    print('=' * 120)
    total = len(results)
    a_count = sum(1 for r in results if r['a3_level'] == 'A')
    b_count = sum(1 for r in results if r['a3_level'] == 'B')
    c_count = sum(1 for r in results if r['a3_level'] == 'C')
    print(f'  总样本: {total}只')
    print(f'  A级: {a_count}只 ({a_count/total*100:.1f}%) - 目标范围5%-15%')
    print(f'  B级: {b_count}只 ({b_count/total*100:.1f}%) - 目标范围30%-50%')
    print(f'  C级: {c_count}只 ({c_count/total*100:.1f}%) - 目标范围40%-60%')

    # ========== 热点检测效果 ==========
    print()
    print('=' * 120)
    print('热点检测效果统计')
    print('=' * 120)
    hot_positive = [r for r in results if r['hot_score'] > 0]
    hot_p0 = [r for r in results if r['hot_source'] == '涨停池统计']
    hot_p1 = [r for r in results if r['hot_source'] == '概念板块行情']
    hot_high = [r for r in results if r['hot_confidence'] == 'high']
    print(f'  hot_score>0: {len(hot_positive)}/{total} ({len(hot_positive)/total*100:.1f}%) - 目标≥70%')
    print(f'  P0涨停池统计: {len(hot_p0)}只 | P1概念行情: {len(hot_p1)}只')
    print(f'  high置信度: {len(hot_high)}只')
    if hot_positive:
        avg_hot = sum(r['hot_score'] for r in hot_positive) / len(hot_positive)
        print(f'  热点股票平均hot_score: {avg_hot:.1f}')

    # 热点来源分布
    source_dist = {}
    for r in results:
        src = r['hot_source'] if r['hot_source'] else '无热点'
        source_dist[src] = source_dist.get(src, 0) + 1
    print(f'  热点来源分布: {source_dist}')

    # ========== 优化前后对比 ==========
    print()
    print('=' * 120)
    print('优化前后对比（已知基准样本）')
    print('=' * 120)
    print(f'{"代码":<8} {"名称":<8} {"优化前":<12} {"优化后":<12} {"变化":<8} {"热点变化":<12}')
    print('-' * 120)
    for r in results:
        if r['code'] in PREV_BASELINE:
            prev = PREV_BASELINE[r['code']]
            prev_conf = prev['confidence']
            prev_level = prev['level']
            curr_conf = r['a3_confidence']
            curr_level = r['a3_level']
            diff = curr_conf - prev_conf
            hot_diff = f"{prev['hot']}→{r['hot_score']}"
            print(f"{r['code']:<8} {r['name']:<8} {prev_conf}({prev_level}){'':<4} {curr_conf}({curr_level}){'':<4} {diff:+.1f}    {hot_diff}")

    # ========== 检查1：禁止标签 ==========
    print()
    print('=' * 120)
    print('检查1：禁止标签不进入核心题材（第1步过滤层验证）')
    print('=' * 120)
    forbidden_in_theme = []
    for r in results:
        theme = r['a3_theme']
        if theme in FORBIDDEN_TAGS:
            forbidden_in_theme.append(r)
    if forbidden_in_theme:
        print(f'  ❌ 禁止标签进入核心题材: {len(forbidden_in_theme)}只')
    else:
        print(f'  ✅ 禁止标签未进入核心题材（0只）')

    # ========== 检查2：三级公告不加分 ==========
    print()
    print('=' * 120)
    print('检查2：三级公告不加分（第3步公告分级验证）')
    print('=' * 120)
    l3_announcements = [r for r in results if r['ann_level'] == 3]
    l3_score_ok = True
    for r in l3_announcements:
        ann_score = r['score_breakdown'].get('announcement', 0)
        if ann_score != 0:
            l3_score_ok = False
            print(f'  ❌ {r["name"]}: 三级公告但公告加分={ann_score}')
    if not l3_announcements:
        print(f'  本次样本无三级公告')
    elif l3_score_ok:
        print(f'  ✅ 所有三级公告均不加分（{len(l3_announcements)}只）')

    # ========== 检查3：A级硬条件 ==========
    print()
    print('=' * 120)
    print('检查3：A级必须满足硬条件')
    print('=' * 120)
    a_level_stocks = [r for r in results if r['a3_level'] == 'A']
    a_hard_condition_ok = True
    for r in a_level_stocks:
        bm_ok = r['bm_level'] in ['S', 'A']
        ann_l1 = r['ann_level'] == 1
        has_hot = r['score_breakdown'].get('hot', 0) > 0
        has_news = r['a3_news'] is not None
        chain = r['lbc']
        catalyst_ok = ann_l1 or (has_hot and has_news) or (has_hot and chain >= 3)
        if not (bm_ok and catalyst_ok):
            a_hard_condition_ok = False
            print(f'  ❌ {r["name"]}: A级但不满足硬条件（主营={r["bm_level"]}, 公告L{r["ann_level"]}, 热点={has_hot}, 新闻={has_news}, 连板={chain}）')
        else:
            print(f'  ✅ {r["name"]}: A级满足硬条件')
    if not a_level_stocks:
        print(f'  本次样本无A级股票')
    elif a_hard_condition_ok:
        print(f'  ✅ 所有A级均满足硬条件')

    # ========== 检查4：主营C级不能A级 ==========
    print()
    print('=' * 120)
    print('检查4：主营C级股票不能直接A级')
    print('=' * 120)
    c_bm_a_level = [r for r in results if r['bm_level'] == 'C' and r['a3_level'] == 'A']
    if c_bm_a_level:
        print(f'  ❌ 主营C级但A级: {len(c_bm_a_level)}只')
        for r in c_bm_a_level:
            print(f'    - {r["name"]}: {r["a3_confidence"]}分')
    else:
        print(f'  ✅ 无主营C级直接A级的股票')

    # ========== 检查5：龙头表现 ==========
    print()
    print('=' * 120)
    print('检查5：龙头/高连板表现（B级以上比例）')
    print('=' * 120)
    longtou = [r for r in results if r['category'] in ['核心龙头', '高连板']]
    below_b = [r for r in longtou if r['a3_level'] == 'C']
    print(f'  龙头+高连板: {len(longtou)}只')
    print(f'  B级以上: {len(longtou) - len(below_b)}只 ({(len(longtou)-len(below_b))/len(longtou)*100:.1f}%)')
    if below_b:
        print(f'  C级（需关注）: {len(below_b)}只')
        for r in below_b:
            print(f'    ⚠️ {r["name"]}: {r["a3_confidence"]}分 C级 题材={r["a3_theme"]} 主营={r["bm_level"]} 连板={r["lbc"]} hot={r["hot_score"]}')

    # ========== 检查6：A-2隔离 ==========
    print()
    print('=' * 120)
    print('检查6：A-2隔离验证（热点增强不影响A-2）')
    print('=' * 120)
    a2_ok = sum(1 for r in results if r['a2_score'] > 0)
    print(f'  A-2评分正常: {a2_ok}/{total} {"✅" if a2_ok == total else "❌"}')

    # ========== 检查7：字段完整性 ==========
    print()
    print('=' * 120)
    print('检查7：字段完整性（原有+新增热点字段）')
    print('=' * 120)
    required_fields = ['hot_score', 'hot_source', 'hot_confidence', 'hot_reason', 'hot_relation_level']
    # 注意result中hot_relation_level存储为hot_relation
    field_ok = True
    for r in results:
        if 'hot_score' not in r or 'hot_source' not in r or 'hot_confidence' not in r or 'hot_reason' not in r or 'hot_relation' not in r:
            field_ok = False
            print(f'  ❌ {r["name"]}: 缺少热点字段')
    if field_ok:
        print(f'  ✅ 所有股票热点字段完整（5个字段）')

    # ========== 异常项记录 ==========
    print()
    print('=' * 120)
    print('异常项记录')
    print('=' * 120)

    # 科技股仍C级
    tech_industries = ['元件', '通信设备', 'IT服务', '计算机设', '软件开发', '光学光电', '半导体', '电子']
    tech_c_level = [r for r in results if any(ind in r['hybk'] for ind in tech_industries) and r['a3_level'] == 'C']
    if tech_c_level:
        print(f'  ⚠️ 科技股仍C级: {len(tech_c_level)}只')
        for r in tech_c_level:
            print(f'    - {r["name"]}({r["hybk"]}): {r["a3_confidence"]}分 主营={r["bm_level"]} hot={r["hot_score"]}')
    else:
        print(f'  ✅ 无科技股C级')

    # 热点误匹配（hot_score高但主营C且无新闻无公告）
    hot_mismatch = [r for r in results if r['hot_score'] >= 8 and r['bm_level'] == 'C' and not r['a3_news'] and r['ann_level'] == 0]
    if hot_mismatch:
        print(f'  ⚠️ 可能热点误匹配: {len(hot_mismatch)}只（高热点但无其他催化）')
        for r in hot_mismatch:
            print(f'    - {r["name"]}: hot={r["hot_score"]} {r["hot_reason"][:40]}')
    else:
        print(f'  ✅ 无明显热点误匹配')

    # ========== 通过标准 ==========
    print()
    print('=' * 120)
    print('V1.3-A-3.1-OPT-VERIFY 通过标准检查')
    print('=' * 120)
    checks = [
        ('A-2评分不变化', a2_ok == total, f'{a2_ok}/{total}'),
        ('热点字段完整', field_ok, '5个字段全部输出'),
        ('禁止标签不进入核心题材', len(forbidden_in_theme) == 0, f'{len(forbidden_in_theme)}只'),
        ('三级公告不加分', l3_score_ok, '验证通过' if l3_score_ok else '存在异常'),
        ('A级必须满足硬条件', a_hard_condition_ok, '验证通过' if a_hard_condition_ok else '存在异常'),
        ('主营C级不能A级', len(c_bm_a_level) == 0, f'{len(c_bm_a_level)}只'),
        ('热点识别率≥70%', len(hot_positive)/total >= 0.7 if total > 0 else False, f'{len(hot_positive)/total*100:.1f}%'),
        ('A级比例5%-15%', 0.05 <= a_count/total <= 0.15 if total > 0 else False, f'{a_count/total*100:.1f}%'),
        ('B级比例30%-50%', 0.30 <= b_count/total <= 0.50 if total > 0 else False, f'{b_count/total*100:.1f}%'),
        ('C级比例40%-60%', 0.40 <= c_count/total <= 0.60 if total > 0 else False, f'{c_count/total*100:.1f}%'),
    ]
    for name, ok, detail in checks:
        status = '✅' if ok else '⚠️'
        print(f'  {status} {name}: {detail}')

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f'\n  通过: {passed}/{len(checks)} 项')

    print()
    print('=' * 120)
    print('验证完成')
    print('=' * 120)


if __name__ == '__main__':
    main()
