# -*- coding: utf-8 -*-
"""
20日涨停记忆·回调后启动雷达

核心目标：寻找过去20个交易日出现过涨停 → 涨停后经历回调/横盘 → 当前重新转强
→ 今日涨幅0.3%～7% → 站上5日线或创10日新高 → 同时获得板块资金、新闻或同板块个股联动确认。

数据源：复用现有程序的真实行情、K线、概念接口，禁止模拟数据。
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# 复用现有指标计算
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.indicators import calc_ma_series, is_price_above_ma


# ============================================================
# 基础工具函数
# ============================================================

def is_limit_up(open_price: float, high: float, low: float, close: float,
                prev_close: float, code: str = '') -> bool:
    """
    判断是否涨停（主板10%，ST 5%，创业板/科创板20%）
    复用简单判断逻辑，不依赖外部模块。
    """
    if prev_close <= 0 or close <= 0:
        return False
    pct = (close - prev_close) / prev_close * 100
    # 主板10%（允许0.5%误差）
    if code.startswith(('60', '000', '001')):
        return pct >= 9.5
    # 创业板/科创板20%
    elif code.startswith(('300', '688')):
        return pct >= 19.5
    # 其他默认10%
    else:
        return pct >= 9.5


def is_one_word_board(open_price: float, high: float, low: float, close: float) -> bool:
    """
    判断是否一字板：开盘=最高=最低=收盘
    """
    if open_price <= 0:
        return False
    return (abs(open_price - high) < 0.01 and
            abs(open_price - low) < 0.01 and
            abs(open_price - close) < 0.01)


def is_st_stock(name: str) -> bool:
    """判断是否ST股票"""
    name_upper = name.upper()
    return 'ST' in name_upper or '*ST' in name_upper


def is_main_board(code: str) -> bool:
    """判断是否主板股票（60沪市主板，000/001深市主板）"""
    return code.startswith(('60', '000', '001'))


# ============================================================
# 20日涨停记忆识别
# ============================================================

def find_limit_up_in_20d(kline: List[Dict], code: str = '') -> Optional[Dict]:
    """
    在最近20个交易日中寻找涨停记录。

    Args:
        kline: K线数据列表，每根包含 date/open/high/low/close/volume
        code: 股票代码

    Returns:
        涨停信息字典，包含：
        - has_limit_up: 是否有涨停
        - limit_up_count_20d: 20日涨停次数
        - last_limit_up_date: 最近一次涨停日期
        - last_limit_up_price: 最近一次涨停价格
        - last_limit_up_idx: 最近一次涨停在kline中的索引
        - last_limit_is_one_word: 最近一次涨停是否一字板
        - days_after_limit_up: 距离最近涨停的交易日数
        - post_limit_high: 涨停后最高价
        - post_limit_low: 涨停后最低价
        没有涨停返回None
    """
    if not kline or len(kline) < 5:
        return None

    # 取最近20根
    recent = kline[-20:] if len(kline) >= 20 else kline
    start_idx = len(kline) - len(recent)

    limit_up_records = []
    for i, bar in enumerate(recent):
        if i == 0:
            continue  # 第一根没有前收盘
        prev_close = recent[i - 1].get('close', 0)
        open_p = bar.get('open', 0)
        high = bar.get('high', 0)
        low = bar.get('low', 0)
        close = bar.get('close', 0)

        if is_limit_up(open_p, high, low, close, prev_close, code):
            is_one_word = is_one_word_board(open_p, high, low, close)
            limit_up_records.append({
                'idx': start_idx + i,
                'date': bar.get('date', ''),
                'price': close,
                'is_one_word': is_one_word,
                'open': open_p,
                'high': high,
                'low': low,
                'close': close,
            })

    if not limit_up_records:
        return None

    # 找最近一次非一字板涨停（有效涨停）
    valid_limit_ups = [r for r in limit_up_records if not r['is_one_word']]
    if not valid_limit_ups:
        # 全部是一字板，没有有效涨停
        return {
            'has_limit_up': True,
            'has_valid_limit_up': False,
            'limit_up_count_20d': len(limit_up_records),
            'last_limit_up_date': limit_up_records[-1]['date'],
            'last_limit_up_price': limit_up_records[-1]['price'],
            'last_limit_up_idx': limit_up_records[-1]['idx'],
            'last_limit_is_one_word': True,
            'days_after_limit_up': len(kline) - 1 - limit_up_records[-1]['idx'],
            'post_limit_high': 0,
            'post_limit_low': 0,
        }

    last_valid = valid_limit_ups[-1]
    last_idx = last_valid['idx']

    # 计算涨停后最高价和最低价
    post_bars = kline[last_idx + 1:]
    post_high = max([b.get('high', 0) for b in post_bars]) if post_bars else 0
    post_low = min([b.get('low', 0) for b in post_bars]) if post_bars else 0

    return {
        'has_limit_up': True,
        'has_valid_limit_up': True,
        'limit_up_count_20d': len(limit_up_records),
        'last_limit_up_date': last_valid['date'],
        'last_limit_up_price': last_valid['price'],
        'last_limit_up_idx': last_idx,
        'last_limit_is_one_word': False,
        'days_after_limit_up': len(kline) - 1 - last_idx,
        'post_limit_high': post_high,
        'post_limit_low': post_low,
    }


# ============================================================
# 涨停后回调/整理判断
# ============================================================

def check_pullback_after_limit(kline: List[Dict], limit_info: Dict) -> Dict:
    """
    判断涨停后是否存在回调/整理。

    条件：
    A. 至少经过2个交易日 days_after_limit_up >= 2
    B. 出现过回撤 pullback >= 3%
    C. 横盘整理：涨停后至少3个交易日 + 价格围绕MA5/MA10震荡 + 当前重新站上MA5

    Returns:
        回调信息字典：
        - has_pullback: 是否有有效回调
        - pullback_type: '明显回撤' / '横盘整理' / '无'
        - pullback_pct: 最大回撤幅度(%)
        - days_after_limit: 涨停后天数
        - current_above_ma5: 当前是否站上MA5
    """
    if not limit_info or not limit_info.get('has_valid_limit_up'):
        return {'has_pullback': False, 'pullback_type': '无', 'pullback_pct': 0,
                'days_after_limit': 0, 'current_above_ma5': False}

    days_after = limit_info.get('days_after_limit_up', 0)
    post_high = limit_info.get('post_limit_high', 0)
    current_close = kline[-1].get('close', 0) if kline else 0

    # 计算MA5
    closes = [b.get('close', 0) for b in kline]
    ma5_series = calc_ma_series(closes, 5)
    # 安全访问pandas Series
    try:
        current_ma5 = float(ma5_series.iloc[-1]) if ma5_series is not None else 0
        if current_ma5 != current_ma5:  # NaN检查
            current_ma5 = 0
    except (IndexError, TypeError):
        current_ma5 = 0
    current_above_ma5 = is_price_above_ma(current_close, current_ma5)

    # 计算最大回撤
    pullback_pct = 0
    if post_high > 0 and current_close > 0:
        pullback_pct = (post_high - current_close) / post_high * 100

    # 条件A：至少2个交易日
    if days_after < 2:
        return {'has_pullback': False, 'pullback_type': '无', 'pullback_pct': pullback_pct,
                'days_after_limit': days_after, 'current_above_ma5': current_above_ma5}

    # 条件B：明显回撤 >= 3%
    if pullback_pct >= 3:
        return {'has_pullback': True, 'pullback_type': '明显回撤', 'pullback_pct': pullback_pct,
                'days_after_limit': days_after, 'current_above_ma5': current_above_ma5}

    # 条件C：横盘整理（涨停后至少3天 + 当前站上MA5）
    if days_after >= 3 and current_above_ma5:
        # 检查涨停后价格是否围绕MA5/MA10震荡（振幅不大）
        post_bars = kline[limit_info['last_limit_up_idx'] + 1:]
        if len(post_bars) >= 3:
            post_closes = [b.get('close', 0) for b in post_bars]
            post_high_local = max(post_closes)
            post_low_local = min(post_closes)
            if post_high_local > 0:
                oscillation = (post_high_local - post_low_local) / post_high_local * 100
                if oscillation <= 15:  # 振幅在15%以内视为横盘
                    return {'has_pullback': True, 'pullback_type': '横盘整理',
                            'pullback_pct': pullback_pct, 'days_after_limit': days_after,
                            'current_above_ma5': current_above_ma5}

    return {'has_pullback': False, 'pullback_type': '无', 'pullback_pct': pullback_pct,
            'days_after_limit': days_after, 'current_above_ma5': current_above_ma5}


# ============================================================
# MA计算和5日线启动判断
# ============================================================

def calc_ma_values(kline: List[Dict]) -> Dict:
    """
    计算MA5、MA10、MA20及5日线状态。

    Returns:
        - ma5: 当前MA5
        - ma10: 当前MA10
        - ma20: 当前MA20
        - ma5_status: '今日刚站' / '已站' / '未站'
        - above_ma5: 是否站上MA5
        - above_ma10: 是否站上MA10
        - above_ma20: 是否站上MA20
        - ma_arrangement: MA5>MA10>MA20 多头排列
    """
    if not kline or len(kline) < 20:
        return {'ma5': 0, 'ma10': 0, 'ma20': 0, 'ma5_status': '数据不足',
                'above_ma5': False, 'above_ma10': False, 'above_ma20': False,
                'ma_arrangement': False}

    closes = [b.get('close', 0) for b in kline]
    ma5_series = calc_ma_series(closes, 5)
    ma10_series = calc_ma_series(closes, 10)
    ma20_series = calc_ma_series(closes, 20)

    current_close = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else 0

    # 正确处理pandas Series
    def _safe_last(series, default=0):
        if series is None:
            return default
        try:
            val = series.iloc[-1]
            return float(val) if val == val else default  # NaN检查
        except (IndexError, TypeError):
            return default

    def _safe_prev(series, default=0):
        if series is None or len(series) < 2:
            return default
        try:
            val = series.iloc[-2]
            return float(val) if val == val else default
        except (IndexError, TypeError):
            return default

    ma5 = _safe_last(ma5_series)
    ma10 = _safe_last(ma10_series)
    ma20 = _safe_last(ma20_series)
    prev_ma5 = _safe_prev(ma5_series)

    above_ma5 = is_price_above_ma(current_close, ma5)
    above_ma10 = is_price_above_ma(current_close, ma10)
    above_ma20 = is_price_above_ma(current_close, ma20)

    # 5日线状态
    if above_ma5:
        if prev_close <= prev_ma5 and current_close > ma5:
            ma5_status = '今日刚站'
        else:
            ma5_status = '已站'
    else:
        ma5_status = '未站'

    # 多头排列
    ma_arrangement = ma5 > ma10 > ma20 if (ma5 > 0 and ma10 > 0 and ma20 > 0) else False

    return {
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'ma5_status': ma5_status,
        'above_ma5': above_ma5,
        'above_ma10': above_ma10,
        'above_ma20': above_ma20,
        'ma_arrangement': ma_arrangement,
    }


# ============================================================
# 10日新高判断
# ============================================================

def check_10day_new_high(kline: List[Dict]) -> Dict:
    """
    判断是否创10日新高（收盘价）。

    Returns:
        - is_new_high: 是否创10日新高
        - high_10d: 最近10日最高收盘价
        - current_close: 当前收盘价
    """
    if not kline or len(kline) < 11:
        return {'is_new_high': False, 'high_10d': 0, 'current_close': 0}

    closes = [b.get('close', 0) for b in kline]
    current_close = closes[-1]
    # 最近10日（不含今天）的最高收盘价
    prev_10_closes = closes[-11:-1]
    high_10d = max(prev_10_closes) if prev_10_closes else 0

    is_new_high = current_close > high_10d if high_10d > 0 else False

    return {
        'is_new_high': is_new_high,
        'high_10d': round(high_10d, 2),
        'current_close': round(current_close, 2),
    }


# ============================================================
# 25日涨幅风险过滤
# ============================================================

def calc_25day_change(kline: List[Dict]) -> Dict:
    """
    计算25日累计涨幅。

    Returns:
        - change_25d: 25日累计涨幅(%)
        - risk_level: '最佳' / '正常' / '高位风险'
        - exclude: 是否排除（>=22%）
    """
    if not kline or len(kline) < 25:
        return {'change_25d': 0, 'risk_level': '数据不足', 'exclude': False}

    closes = [b.get('close', 0) for b in kline]
    close_25d_ago = closes[-25]
    current_close = closes[-1]

    if close_25d_ago <= 0:
        return {'change_25d': 0, 'risk_level': '数据异常', 'exclude': False}

    change_25d = (current_close - close_25d_ago) / close_25d_ago * 100

    if change_25d < 15:
        risk_level = '最佳'
        exclude = False
    elif change_25d < 22:
        risk_level = '正常'
        exclude = False
    else:
        risk_level = '高位风险'
        exclude = True

    return {
        'change_25d': round(change_25d, 2),
        'risk_level': risk_level,
        'exclude': exclude,
    }


# ============================================================
# 今日涨幅判断
# ============================================================

def check_today_change(pct_chg: float) -> Dict:
    """
    判断今日涨幅是否在0.3%～7%范围内。

    Returns:
        - in_range: 是否在范围内
        - level: '最优' / '正常' / '风险提高' / '追高风险' / '不触发'
        - pct_chg: 今日涨幅
    """
    if pct_chg < 0.3:
        return {'in_range': False, 'level': '不触发', 'pct_chg': pct_chg}
    elif pct_chg <= 3:
        return {'in_range': True, 'level': '最优', 'pct_chg': pct_chg}
    elif pct_chg <= 5:
        return {'in_range': True, 'level': '正常', 'pct_chg': pct_chg}
    elif pct_chg <= 7:
        return {'in_range': True, 'level': '风险提高', 'pct_chg': pct_chg}
    else:
        return {'in_range': False, 'level': '追高风险', 'pct_chg': pct_chg}


# ============================================================
# 板块共振（概念、资金流、新闻、联动）
# ============================================================

def get_stock_concepts_safe(code: str) -> List[str]:
    """
    安全获取股票所属概念，复用现有接口。
    失败返回空列表，不影响主程序。
    """
    try:
        from service.concept_service import get_stock_concepts
        result = get_stock_concepts(code)
        # get_stock_concepts返回tuple: (概念列表, 数据源名称)
        if isinstance(result, tuple):
            concepts = result[0]
        elif isinstance(result, list):
            concepts = result
        else:
            concepts = []
        if isinstance(concepts, list):
            return [str(c) for c in concepts if c]
        return []
    except Exception as e:
        print(f"[雷达] 获取概念失败 {code}: {e}", flush=True)
        return []


def get_stock_industry_safe(code: str) -> str:
    """
    安全获取股票所属行业。
    """
    try:
        from service.concept_service import get_stock_industry_f10
        industry = get_stock_industry_f10(code)
        return str(industry) if industry else ''
    except Exception as e:
        print(f"[雷达] 获取行业失败 {code}: {e}", flush=True)
        return ''


def analyze_sector_resonance(code: str, all_stocks: Optional[List[Dict]] = None) -> Dict:
    """
    分析板块共振情况。

    Args:
        code: 股票代码
        all_stocks: 全市场股票列表（用于统计同板块联动），格式 [{code, name, pct_chg, ...}]

    Returns:
        - industry: 所属行业
        - concepts: 所属概念列表
        - main_concept: 主要概念
        - sector_fund_flow: 板块资金流（'流入'/'流出'/'暂无数据'）
        - sector_fund_rank: 板块资金排名
        - news_catalyst: 是否有新闻催化
        - same_sector_up_count: 同板块上涨股票数量
        - same_sector_strong_count: 同板块强势股数量（涨幅>3%）
        - same_sector_limit_up_count: 同板块涨停数量
        - resonance_level: 共振等级0-5
        - resonance_desc: 共振描述
    """
    industry = get_stock_industry_safe(code)
    concepts = get_stock_concepts_safe(code)
    main_concept = concepts[0] if concepts else industry

    # 板块资金流（暂无统一接口，标记为暂无数据）
    sector_fund_flow = '暂无数据'
    sector_fund_rank = 0

    # 新闻催化（暂无统一接口，标记为暂无数据）
    news_catalyst = False

    # 同板块联动统计
    same_sector_up_count = 0
    same_sector_strong_count = 0
    same_sector_limit_up_count = 0

    if all_stocks and concepts:
        # 找出同概念股票
        for stock in all_stocks:
            s_code = stock.get('code', '')
            if s_code == code:
                continue
            s_concepts = stock.get('concepts', [])
            if not s_concepts:
                # 如果没有预加载概念，跳过（避免实时请求）
                continue
            # 判断是否有共同概念
            has_common = any(c in s_concepts for c in concepts)
            if has_common:
                s_pct = stock.get('pct_chg', 0)
                if s_pct > 0:
                    same_sector_up_count += 1
                if s_pct > 3:
                    same_sector_strong_count += 1
                if s_pct >= 9.5:
                    same_sector_limit_up_count += 1

    # 共振等级
    if same_sector_limit_up_count > 0 and sector_fund_flow == '流入' and news_catalyst:
        resonance_level = 5
        resonance_desc = '板块资金流入+新闻催化+同板块涨停'
    elif same_sector_limit_up_count > 0 and sector_fund_flow == '流入':
        resonance_level = 4
        resonance_desc = '板块资金流入+同板块涨停'
    elif same_sector_limit_up_count > 0:
        resonance_level = 3
        resonance_desc = '同板块出现涨停'
    elif same_sector_strong_count >= 3:
        resonance_level = 2
        resonance_desc = '同板块至少3只强势股'
    elif same_sector_up_count >= 2:
        resonance_level = 1
        resonance_desc = '同板块至少2只上涨'
    else:
        resonance_level = 0
        resonance_desc = '只有个股自己上涨'

    return {
        'industry': industry,
        'concepts': concepts,
        'main_concept': main_concept,
        'sector_fund_flow': sector_fund_flow,
        'sector_fund_rank': sector_fund_rank,
        'news_catalyst': news_catalyst,
        'same_sector_up_count': same_sector_up_count,
        'same_sector_strong_count': same_sector_strong_count,
        'same_sector_limit_up_count': same_sector_limit_up_count,
        'resonance_level': resonance_level,
        'resonance_desc': resonance_desc,
    }


# ============================================================
# RadarScore评分（总分100）
# ============================================================

def calculate_radar_score(limit_info: Dict, pullback_info: Dict, ma_info: Dict,
                           new_high_info: Dict, today_change: Dict,
                           sector_info: Dict, risk_25d: Dict) -> Dict:
    """
    计算雷达评分 RadarScore（总分100）。

    评分项：
    1. 20日涨停记忆：15分
    2. 回调/整理质量：15分
    3. 今日站5日线：15分
    4. 10日新高：15分
    5. 今日涨幅：10分
    6. 板块资金：10分
    7. 同板块联动：10分
    8. 新闻催化：5分

    风险扣分：
    - 25日涨幅15%～22%：-5
    - 今日涨幅5%～7%：-2
    - 距离最近涨停过近（<2天）：-2

    Returns:
        - score: 总分
        - grade: S/A/B/C/不显示
        - signal: 信号标签
        - score_detail: 各项得分明细
        - deductions: 扣分明细
    """
    score_detail = {}
    deductions = {}

    # 1. 20日涨停记忆：15分
    if limit_info and limit_info.get('has_valid_limit_up'):
        score_detail['涨停记忆'] = 15
    else:
        score_detail['涨停记忆'] = 0

    # 2. 回调/整理质量：15分
    pullback_score = 0
    if pullback_info.get('has_pullback'):
        pullback_score += 10  # 有效回调
        if pullback_info.get('current_above_ma5'):
            pullback_score += 5  # 回调后重新转强
    score_detail['回调质量'] = pullback_score

    # 3. 今日站5日线：15分
    ma_score = 0
    if ma_info.get('above_ma5'):
        ma_score += 10  # 站上MA5
        if ma_info.get('ma5_status') == '今日刚站':
            ma_score += 5  # 今日刚站MA5
    score_detail['站5日线'] = ma_score

    # 4. 10日新高：15分
    score_detail['10日新高'] = 15 if new_high_info.get('is_new_high') else 0

    # 5. 今日涨幅：10分
    change_score = 0
    if today_change.get('in_range'):
        level = today_change.get('level', '')
        if level == '最优':
            change_score = 10
        elif level == '正常':
            change_score = 8
        elif level == '风险提高':
            change_score = 5
    score_detail['今日涨幅'] = change_score

    # 6. 板块资金：10分
    fund_score = 0
    if sector_info.get('sector_fund_flow') == '流入':
        fund_score += 5
        if sector_info.get('sector_fund_rank', 0) > 0 and sector_info['sector_fund_rank'] <= 10:
            fund_score += 5
    score_detail['板块资金'] = fund_score

    # 7. 同板块联动：10分
    linkage_score = 0
    up_count = sector_info.get('same_sector_up_count', 0)
    strong_count = sector_info.get('same_sector_strong_count', 0)
    limit_up_count = sector_info.get('same_sector_limit_up_count', 0)
    if limit_up_count > 0:
        linkage_score = 10
    elif strong_count >= 3:
        linkage_score = 6
    elif up_count >= 2:
        linkage_score = 3
    score_detail['板块联动'] = linkage_score

    # 8. 新闻催化：5分
    score_detail['新闻催化'] = 5 if sector_info.get('news_catalyst') else 0

    # 计算总分
    total_score = sum(score_detail.values())

    # 风险扣分
    # 25日涨幅15%～22%：-5
    if risk_25d.get('risk_level') == '正常':
        deductions['25日涨幅偏高'] = 5
        total_score -= 5

    # 今日涨幅5%～7%：-2
    if today_change.get('level') == '风险提高':
        deductions['今日涨幅偏高'] = 2
        total_score -= 2

    # 距离最近涨停过近（<2天）：-2
    if limit_info and limit_info.get('days_after_limit_up', 99) < 2:
        deductions['距涨停过近'] = 2
        total_score -= 2

    total_score = max(0, min(100, total_score))

    # 等级
    if total_score >= 80:
        grade = 'S'
    elif total_score >= 70:
        grade = 'A'
    elif total_score >= 60:
        grade = 'B'
    elif total_score >= 50:
        grade = 'C'
    else:
        grade = '不显示'

    # 信号标签
    signals = []
    if limit_info and limit_info.get('has_valid_limit_up'):
        signals.append('20日涨停记忆')
    if pullback_info.get('has_pullback'):
        signals.append('回调完成')
    if ma_info.get('ma5_status') == '今日刚站':
        signals.append('今日刚站5')
    elif ma_info.get('above_ma5'):
        signals.append('站上5日线')
    if new_high_info.get('is_new_high'):
        signals.append('创10日新高')
    if sector_info.get('sector_fund_flow') == '流入':
        signals.append('板块资金流入')
    if sector_info.get('news_catalyst'):
        signals.append('板块新闻催化')
    if sector_info.get('same_sector_up_count') >= 2:
        signals.append('同板块联动')
    if sector_info.get('same_sector_limit_up_count') > 0:
        signals.append('板块涨停')

    # 核心信号
    if (limit_info and limit_info.get('has_valid_limit_up') and
            pullback_info.get('has_pullback') and
            today_change.get('in_range') and
            ma_info.get('above_ma5') and
            new_high_info.get('is_new_high')):
        signals.append('回调后启动')

    if ma_info.get('ma5_status') == '今日刚站':
        signals.append('今日启动')

    if today_change.get('level') == '追高风险':
        signals.append('追高风险')

    return {
        'score': round(total_score, 1),
        'grade': grade,
        'signal': signals,
        'score_detail': score_detail,
        'deductions': deductions,
    }


# ============================================================
# 主入口：单只股票雷达分析
# ============================================================

def analyze_stock_radar(stock: Dict, kline: List[Dict],
                         all_stocks: Optional[List[Dict]] = None) -> Optional[Dict]:
    """
    对单只股票进行20日涨停记忆·回调后启动雷达分析。

    Args:
        stock: 股票信息，包含 code/name/price/pct_chg/volume 等
        kline: K线数据列表
        all_stocks: 全市场股票列表（用于板块联动统计）

    Returns:
        雷达分析结果字典，不满足基本条件返回None
    """
    code = stock.get('code', '')
    name = stock.get('name', '')
    pct_chg = stock.get('pct_chg', 0)

    # 基本过滤：主板、非ST
    if not is_main_board(code):
        return None
    if is_st_stock(name):
        return None

    # K线数据检查
    if not kline or len(kline) < 25:
        return None

    # 1. 20日涨停记忆
    limit_info = find_limit_up_in_20d(kline, code)
    if not limit_info or not limit_info.get('has_valid_limit_up'):
        return None

    # 2. 涨停后回调/整理
    pullback_info = check_pullback_after_limit(kline, limit_info)

    # 3. MA计算和5日线状态
    ma_info = calc_ma_values(kline)

    # 4. 10日新高
    new_high_info = check_10day_new_high(kline)

    # 5. 今日涨幅
    today_change = check_today_change(pct_chg)

    # 6. 25日涨幅风险
    risk_25d = calc_25day_change(kline)
    if risk_25d.get('exclude'):
        return None  # 25日涨幅>=22%直接排除

    # 7. 板块共振
    sector_info = analyze_sector_resonance(code, all_stocks)

    # 8. 评分
    radar_result = calculate_radar_score(
        limit_info, pullback_info, ma_info, new_high_info,
        today_change, sector_info, risk_25d
    )

    # 不显示等级（<50分）不返回
    if radar_result['grade'] == '不显示':
        return None

    # 组装完整结果
    result = {
        'code': code,
        'name': name,
        'price': stock.get('price', 0),
        'pct_chg': pct_chg,
        'volume': stock.get('volume', 0),
        'turnover': stock.get('turnover', 0),
        # 涨停记忆
        'limit_up_count_20d': limit_info.get('limit_up_count_20d', 0),
        'last_limit_up_date': limit_info.get('last_limit_up_date', ''),
        'last_limit_up_price': limit_info.get('last_limit_up_price', 0),
        'days_after_limit_up': limit_info.get('days_after_limit_up', 0),
        # 回调
        'pullback_pct': pullback_info.get('pullback_pct', 0),
        'pullback_type': pullback_info.get('pullback_type', ''),
        'has_pullback': pullback_info.get('has_pullback', False),
        # MA
        'ma5': ma_info.get('ma5', 0),
        'ma10': ma_info.get('ma10', 0),
        'ma20': ma_info.get('ma20', 0),
        'ma5_status': ma_info.get('ma5_status', ''),
        'above_ma5': ma_info.get('above_ma5', False),
        'ma_arrangement': ma_info.get('ma_arrangement', False),
        # 10日新高
        'is_10day_new_high': new_high_info.get('is_new_high', False),
        'high_10d': new_high_info.get('high_10d', 0),
        # 25日涨幅
        'change_25d': risk_25d.get('change_25d', 0),
        'risk_25d': risk_25d.get('risk_level', ''),
        # 今日涨幅
        'today_change_level': today_change.get('level', ''),
        'today_in_range': today_change.get('in_range', False),
        # 板块
        'industry': sector_info.get('industry', ''),
        'concepts': sector_info.get('concepts', []),
        'main_concept': sector_info.get('main_concept', ''),
        'sector_fund_flow': sector_info.get('sector_fund_flow', ''),
        'sector_fund_rank': sector_info.get('sector_fund_rank', 0),
        'news_catalyst': sector_info.get('news_catalyst', False),
        'same_sector_up_count': sector_info.get('same_sector_up_count', 0),
        'same_sector_strong_count': sector_info.get('same_sector_strong_count', 0),
        'same_sector_limit_up_count': sector_info.get('same_sector_limit_up_count', 0),
        'resonance_level': sector_info.get('resonance_level', 0),
        'resonance_desc': sector_info.get('resonance_desc', ''),
        # 评分
        'radar_score': radar_result['score'],
        'radar_grade': radar_result['grade'],
        'radar_signals': radar_result['signal'],
        'score_detail': radar_result['score_detail'],
        'deductions': radar_result['deductions'],
        # 核心信号标签（用于监控大厅signal_names）
        'signal_names': ['回调后启动'] if '回调后启动' in radar_result['signal'] else
                         (['今日启动'] if '今日启动' in radar_result['signal'] else
                          ['20日涨停记忆'] if '20日涨停记忆' in radar_result['signal'] else []),
    }

    return result


# ============================================================
# 批量扫描
# ============================================================

def scan_radar_batch(stocks: List[Dict], kline_map: Dict[str, List[Dict]],
                      all_stocks: Optional[List[Dict]] = None) -> List[Dict]:
    """
    批量扫描雷达信号。

    Args:
        stocks: 股票列表
        kline_map: 股票代码 -> K线数据映射
        all_stocks: 全市场股票列表（用于板块联动）

    Returns:
        雷达结果列表，按评分降序排列
    """
    results = []
    for stock in stocks:
        code = stock.get('code', '')
        kline = kline_map.get(code)
        if not kline:
            continue
        try:
            result = analyze_stock_radar(stock, kline, all_stocks)
            if result:
                results.append(result)
        except Exception as e:
            print(f"[雷达] 分析失败 {code}: {e}", flush=True)
            continue

    # 排序：S级↓ A级↓ B级↓ 评分↓ 共振等级↓ 涨幅↓
    grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3}
    results.sort(key=lambda x: (
        grade_order.get(x.get('radar_grade', 'C'), 99),
        -x.get('radar_score', 0),
        -x.get('resonance_level', 0),
        -x.get('pct_chg', 0),
    ))

    return results


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    # 简单测试
    print("=" * 60)
    print("20日涨停记忆·回调后启动雷达 - 模块测试")
    print("=" * 60)

    # 测试1：涨停判断
    print("\n[测试1] 涨停判断")
    print(f"  主板涨停(10%): {is_limit_up(10, 11, 10, 11, 10, '600000')}")
    print(f"  非涨停(5%): {is_limit_up(10, 10.5, 10, 10.5, 10, '600000')}")
    print(f"  一字板: {is_one_word_board(11, 11, 11, 11)}")

    # 测试2：MA计算
    print("\n[测试2] MA计算")
    test_closes = list(range(1, 31))
    test_kline = [{'close': c, 'open': c, 'high': c + 1, 'low': c - 1, 'volume': 1000,
                    'date': f'2026-01-{i+1:02d}'} for i, c in enumerate(test_closes)]
    ma_info = calc_ma_values(test_kline)
    print(f"  MA5={ma_info['ma5']}, MA10={ma_info['ma10']}, MA20={ma_info['ma20']}")
    print(f"  5日线状态={ma_info['ma5_status']}, 多头排列={ma_info['ma_arrangement']}")

    # 测试3：10日新高
    print("\n[测试3] 10日新高")
    new_high = check_10day_new_high(test_kline)
    print(f"  创10日新高={new_high['is_new_high']}, 10日最高={new_high['high_10d']}")

    # 测试4：25日涨幅
    print("\n[测试4] 25日涨幅")
    risk = calc_25day_change(test_kline)
    print(f"  25日涨幅={risk['change_25d']}%, 风险等级={risk['risk_level']}, 排除={risk['exclude']}")

    # 测试5：今日涨幅
    print("\n[测试5] 今日涨幅")
    for pct in [0.2, 1.5, 4, 6, 8]:
        tc = check_today_change(pct)
        print(f"  涨幅{pct}%: in_range={tc['in_range']}, level={tc['level']}")

    print("\n" + "=" * 60)
    print("基础功能测试完成")
    print("=" * 60)
