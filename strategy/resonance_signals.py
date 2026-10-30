# -*- coding: utf-8 -*-
"""
共振信号模块
- 指数板块共振：指数环境 + 板块强度 + 个股同步
- 回踩二十日：趋势股回踩MA20后再次启动
所有数据来自真实接口，禁止Mock
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 缓存
_index_cache = None
_index_cache_time = 0
_sector_cache = None
_sector_cache_time = 0
CACHE_EXPIRE = 300  # 5分钟缓存


# ============================================================
# 指数板块共振信号
# ============================================================
def get_index_environment():
    """获取指数环境（上证/深证/创业板），带缓存"""
    global _index_cache, _index_cache_time
    import time
    now = time.time()
    if _index_cache and (now - _index_cache_time) < CACHE_EXPIRE:
        return _index_cache

    try:
        from strategy.market_sector_analyzer import MarketAnalyzer
        monitor = MarketAnalyzer()
        quotes = monitor.get_index_quotes()
        if quotes and len(quotes) > 0:
            _index_cache = quotes
            _index_cache_time = now
            return quotes
    except Exception as e:
        print(f"[共振信号] 获取指数数据失败: {e}")
    return []


# 缓存
_index_cache = None
_index_cache_time = 0
_sector_cache = None
_sector_cache_time = 0
_sector_fail_count = 0  # 板块数据失败次数统计
CACHE_EXPIRE = 300  # 5分钟缓存
SECTOR_CACHE_LONG = 86400  # 板块数据长期缓存24小时（当天有效）


def get_sector_ranking():
    """获取板块涨幅排名，快速失败（1次重试，不阻塞）"""
    global _sector_cache, _sector_cache_time, _sector_fail_count
    import time
    now = time.time()

    # 1. 优先使用有效缓存（5分钟内）
    if _sector_cache and (now - _sector_cache_time) < CACHE_EXPIRE:
        return _sector_cache

    # 2. 只重试1次，间隔0.5秒，快速失败不阻塞
    max_retries = 1
    last_error = None
    for attempt in range(max_retries):
        try:
            from strategy.market_sector_analyzer import get_sector_analyzer
            analyzer = get_sector_analyzer()
            sectors = analyzer.get_sector_ranking()
            if sectors and len(sectors) > 0:
                _sector_cache = sectors
                _sector_cache_time = now
                _sector_fail_count = 0
                return sectors
            else:
                last_error = '返回空数据'
        except Exception as e:
            last_error = str(e)
        if attempt < max_retries - 1:
            time.sleep(0.5)

    # 3. 失败降级
    _sector_fail_count += 1
    if _sector_fail_count == 1 or _sector_fail_count % 20 == 0:
        print(f"[共振信号] 板块数据获取失败（第{_sector_fail_count}次）: {last_error}")

    # 优先返回长期缓存
    if _sector_cache and (now - _sector_cache_time) < SECTOR_CACHE_LONG:
        return _sector_cache

    return []


def calc_index_score(index_quotes):
    """计算指数环境得分（0-30分）"""
    if not index_quotes or len(index_quotes) == 0:
        return 15, '指数数据暂不可用'

    up_count = sum(1 for idx in index_quotes if idx.get('pct_chg', 0) > 0)
    avg_pct = sum(idx.get('pct_chg', 0) for idx in index_quotes) / len(index_quotes)

    # 评分：平均涨幅越高分越高，上涨指数数量越多分越高
    score = 15  # 基础分
    if avg_pct > 1.0:
        score += 15
    elif avg_pct > 0.5:
        score += 10
    elif avg_pct > 0:
        score += 5
    elif avg_pct > -0.5:
        score += 0
    else:
        score -= 5

    if up_count == 3:
        score += 5
    elif up_count == 2:
        score += 2

    score = max(0, min(30, score))

    if avg_pct > 0.5 and up_count >= 2:
        env = '指数强势上涨'
    elif avg_pct > 0:
        env = '指数偏强震荡'
    elif avg_pct > -0.5:
        env = '指数弱势震荡'
    else:
        env = '指数下跌'

    return score, env


def calc_sector_score(stock_concepts, sector_ranking):
    """计算板块强度得分（0-40分）"""
    if not stock_concepts or not sector_ranking:
        return 20, '板块数据暂不可用'

    # 将股票概念与板块排名匹配
    concept_set = set()
    for c in stock_concepts:
        if isinstance(c, str):
            concept_set.add(c.strip())

    matched_sectors = []
    for sector in sector_ranking:
        sector_name = sector.get('name', '')
        # 模糊匹配：板块名包含概念名，或概念名包含板块名
        for concept in concept_set:
            if concept and (concept in sector_name or sector_name in concept):
                matched_sectors.append(sector)
                break

    if not matched_sectors:
        return 15, '未匹配到强势板块'

    # 取匹配板块中涨幅最高的
    best = max(matched_sectors, key=lambda x: x.get('pct_chg', 0))
    best_pct = best.get('pct_chg', 0)
    best_name = best.get('name', '')

    # 评分：板块涨幅越高分越高
    score = 20
    if best_pct > 3.0:
        score += 20
    elif best_pct > 2.0:
        score += 15
    elif best_pct > 1.0:
        score += 10
    elif best_pct > 0:
        score += 5
    else:
        score -= 5

    # 板块排名前10加分
    sorted_sectors = sorted(sector_ranking, key=lambda x: x.get('pct_chg', 0), reverse=True)
    for i, s in enumerate(sorted_sectors[:10]):
        if s.get('name') == best_name:
            score += min(5, 10 - i)
            break

    score = max(0, min(40, score))
    return score, f'{best_name}上涨{best_pct:.1f}%'


def calc_stock_sync_score(stock):
    """计算个股同步得分（0-30分）"""
    pct_chg = stock.get('pct_chg', 0)
    volume = stock.get('volume', 0)
    turnover = stock.get('turnover', 0)

    score = 15
    # 个股上涨
    if pct_chg > 3.0:
        score += 15
    elif pct_chg > 2.0:
        score += 12
    elif pct_chg > 1.0:
        score += 8
    elif pct_chg > 0:
        score += 4
    elif pct_chg > -2:
        score -= 2
    else:
        score -= 8

    # 成交量放大（换手率>3%）
    if turnover > 5:
        score += 5
    elif turnover > 3:
        score += 3
    elif turnover > 1:
        score += 1

    score = max(0, min(30, score))

    if pct_chg > 2:
        sync = '个股强势上涨'
    elif pct_chg > 0:
        sync = '个股偏强'
    elif pct_chg > -2:
        sync = '个股横盘'
    else:
        sync = '个股下跌'

    return score, sync


def calc_resonance_signal(stock):
    """
    计算指数板块共振信号
    返回: {has_signal, score, level, reason, index_score, sector_score, stock_score}
    """
    # 获取指数和板块数据
    index_quotes = get_index_environment()
    sector_ranking = get_sector_ranking()

    # 股票概念
    concepts = stock.get('concept', [])
    if isinstance(concepts, str):
        concepts = [concepts]
    elif not isinstance(concepts, (list, tuple)):
        concepts = []

    # 三维度评分
    index_score, index_desc = calc_index_score(index_quotes)
    sector_score, sector_desc = calc_sector_score(concepts, sector_ranking)
    stock_score, stock_desc = calc_stock_sync_score(stock)

    total_score = index_score + sector_score + stock_score

    # 信号等级
    if total_score >= 70:
        level = '强'
        has_signal = True
    elif total_score >= 55:
        level = '中'
        has_signal = True
    elif total_score >= 45:
        level = '弱'
        has_signal = True
    else:
        level = '无'
        has_signal = False

    reason = f'{index_desc} + {sector_desc} + {stock_desc}'

    return {
        'has_signal': has_signal,
        'score': total_score,
        'level': level,
        'reason': reason,
        'index_score': index_score,
        'sector_score': sector_score,
        'stock_score': stock_score,
    }


# ============================================================
# 回踩二十日信号
# ============================================================
def calc_ma20_pullback_signal(stock, kline_data=None):
    """
    计算回踩二十日信号
    条件：
    1. 近7个交易日内最低价或收盘价接触MA20（距离<=2%）
    2. 当天或之后股价重新向上
    3. 当前收盘价接近MA5（距离<=2%）
    4. MA5 > MA9 > MA20

    Args:
        stock: 股票数据字典
        kline_data: K线数据（DataFrame或list），如果为None则尝试从stock获取
    Returns:
        dict: {has_signal, pullback_date, pullback_price, ma20, ma5, ma9, ma_structure, reason}
    """
    # 尝试获取K线数据
    df = kline_data
    if df is None:
        df = stock.get('kline_data')
    if df is None:
        # 尝试从code加载（使用TdxDataEngine直接获取，返回List[Dict]）
        code = stock.get('code', '')
        if code:
            try:
                from data.tdx_data_engine import TdxDataEngine
                engine = TdxDataEngine()
                df = engine.get_kline(code, days=60)
            except Exception:
                pass

    if df is None or len(df) < 30:
        return {'has_signal': False, 'reason': 'K线数据不足'}

    # 转换为列表格式（兼容DataFrame和list）
    try:
        if hasattr(df, 'iloc'):
            # DataFrame
            closes = df['close'].tolist() if 'close' in df.columns else []
            lows = df['low'].tolist() if 'low' in df.columns else closes
            dates = df['date'].tolist() if 'date' in df.columns else []
        else:
            # list of dict
            closes = [d.get('close', 0) for d in df]
            lows = [d.get('low', d.get('close', 0)) for d in df]
            dates = [d.get('date', '') for d in df]
    except Exception as e:
        return {'has_signal': False, 'reason': f'K线解析失败: {e}'}

    if len(closes) < 30:
        return {'has_signal': False, 'reason': 'K线数据不足'}

    # 计算均线
    def ma(data, n):
        if len(data) < n:
            return []
        result = []
        for i in range(n - 1, len(data)):
            result.append(sum(data[i - n + 1:i + 1]) / n)
        return result

    ma5_list = ma(closes, 5)
    ma9_list = ma(closes, 9)
    ma20_list = ma(closes, 20)

    if not ma5_list or not ma9_list or not ma20_list:
        return {'has_signal': False, 'reason': '均线计算失败'}

    # 当前值
    current_close = closes[-1]
    current_ma5 = ma5_list[-1]
    current_ma9 = ma9_list[-1]
    current_ma20 = ma20_list[-1]

    # 条件4：MA5 > MA9 > MA20
    ma_structure_ok = current_ma5 > current_ma9 > current_ma20
    ma_structure = f'MA5({current_ma5:.2f}) > MA9({current_ma9:.2f}) > MA20({current_ma20:.2f})' if ma_structure_ok else f'MA5({current_ma5:.2f}) MA9({current_ma9:.2f}) MA20({current_ma20:.2f}) 非多头'

    # 条件3：当前收盘价接近MA5（距离<=2%）
    dist_ma5 = abs(current_close - current_ma5) / current_ma5 * 100 if current_ma5 > 0 else 999
    near_ma5 = dist_ma5 <= 2.0

    # 条件1：近7个交易日内接触MA20（距离<=2%）
    # 需要对齐索引：ma20_list从第19个元素开始（索引19对应closes索引19）
    # 近7天对应closes的最后7个元素，对应ma20_list的最后7个元素
    lookback = min(7, len(ma20_list), len(closes) - 19)
    pullback_found = False
    pullback_date = ''
    pullback_price = 0
    pullback_ma20 = 0

    for i in range(lookback):
        # 从最近往前找
        idx = -(i + 1)
        if abs(idx) > len(ma20_list) or abs(idx) > len(closes):
            continue
        day_close = closes[idx]
        day_low = lows[idx] if abs(idx) <= len(lows) else day_close
        day_ma20 = ma20_list[idx]

        if day_ma20 <= 0:
            continue

        # 最低价或收盘价接触MA20
        dist_close = abs(day_close - day_ma20) / day_ma20 * 100
        dist_low = abs(day_low - day_ma20) / day_ma20 * 100

        if dist_close <= 2.0 or dist_low <= 2.0:
            pullback_found = True
            pullback_date = dates[idx] if abs(idx) <= len(dates) else ''
            pullback_price = day_low if dist_low < dist_close else day_close
            pullback_ma20 = day_ma20
            break

    # 条件2：回踩后股价重新向上（当前收盘价 > 回踩日收盘价）
    rebounding = False
    if pullback_found and pullback_price > 0:
        rebounding = current_close > pullback_price

    # 综合判断
    has_signal = pullback_found and rebounding and near_ma5 and ma_structure_ok

    reason_parts = []
    if pullback_found:
        reason_parts.append(f'近7日回踩MA20({pullback_ma20:.2f})，回踩价{pullback_price:.2f}')
    else:
        reason_parts.append('近7日未回踩MA20')
    if rebounding:
        reason_parts.append('股价重新向上')
    else:
        reason_parts.append('未确认反弹')
    if near_ma5:
        reason_parts.append(f'当前接近MA5(距离{dist_ma5:.1f}%)')
    else:
        reason_parts.append(f'当前远离MA5(距离{dist_ma5:.1f}%)')
    if ma_structure_ok:
        reason_parts.append('均线多头排列')
    else:
        reason_parts.append('均线非多头')

    return {
        'has_signal': has_signal,
        'pullback_date': str(pullback_date) if pullback_date else '',
        'pullback_price': round(pullback_price, 2),
        'ma20': round(current_ma20, 2),
        'ma5': round(current_ma5, 2),
        'ma9': round(current_ma9, 2),
        'ma_structure': ma_structure,
        'reason': ' + '.join(reason_parts),
    }


# ============================================================
# 统一信号计算入口
# ============================================================
def calc_all_resonance_signals(stock, kline_data=None):
    """
    计算所有共振类信号
    返回: {signals: [{'name':, 'score':, 'level':, 'reason':, 'detail':}], ...}
    """
    signals = []

    # 1. 指数板块共振
    try:
        resonance = calc_resonance_signal(stock)
        if resonance.get('has_signal'):
            signals.append({
                'name': '共振',
                'score': resonance.get('score', 0),
                'level': resonance.get('level', ''),
                'reason': resonance.get('reason', ''),
                'detail': resonance,
            })
    except Exception as e:
        print(f"[共振信号] 计算共振信号失败: {e}")

    # 2. 回踩二十日
    try:
        pullback = calc_ma20_pullback_signal(stock, kline_data)
        if pullback.get('has_signal'):
            signals.append({
                'name': '回踩二十日',
                'score': 75,  # 回踩二十日是较强信号，固定75分
                'level': '强',
                'reason': pullback.get('reason', ''),
                'detail': pullback,
            })
    except Exception as e:
        print(f"[共振信号] 计算回踩二十日失败: {e}")

    return signals
