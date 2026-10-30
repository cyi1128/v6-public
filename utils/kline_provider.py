"""
K线数据获取工具
统一使用通达信pytdx数据源，稳定优先
V2.8.1：新增本地DuckDB缓存兜底，非交易时段优先从缓存读取
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.tdx_connector import get_daily_kline_tdx, get_kline_tdx, get_minute_time_data_tdx
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.kline_cache import get_kline_cache


def _get_kline_from_duckdb(code, count=250):
    """
    从本地DuckDB K线缓存读取（V2.8.1新增：非交易时段兜底）
    Args:
        code: 股票代码（6位，自动去除前缀）
        count: 获取数量
    Returns:
        list: [{'date':, 'open':, 'close':, 'high':, 'low':, 'volume':}, ...] 按日期升序
    """
    try:
        import duckdb
        # 标准化代码：去除sh/sz/bj前缀
        clean_code = code
        for prefix in ['sh', 'sz', 'bj', 'SH', 'SZ', 'BJ']:
            if clean_code.startswith(prefix):
                clean_code = clean_code[len(prefix):]
                break

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'cache', 'kline_cache.duckdb')
        if not os.path.exists(db_path):
            return []

        con = duckdb.connect(db_path, read_only=True)
        rows = con.execute("""
            SELECT date, open, high, low, close, volume
            FROM kline_cache
            WHERE TRIM(code) = ?
            ORDER BY date DESC
            LIMIT ?
        """, (clean_code, count)).fetchall()
        con.close()

        if not rows:
            return []

        # 转换为升序
        bars = []
        for row in reversed(rows):
            bars.append({
                'date': str(row[0]),
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': float(row[5]),
            })
        return bars
    except Exception as e:
        print(f"[K线缓存] {code} 读取失败: {e}", flush=True)
        return []


def get_daily_kline(code, count=250):
    """
    获取日K线数据（通达信优先，稳定可靠）
    Args:
        code: 股票代码（6位）
        count: 获取数量
    Returns:
        dict: {'open': [], 'close': [], 'high': [], 'low': [], 'volume': [], 'pct_chg': [], 'dates': []}
    """
    return get_kline_by_period(code, count, period='day')


def get_kline_by_period(code, count=250, period='day'):
    """
    获取指定周期的K线数据
    Args:
        code: 股票代码（6位）
        count: 获取数量
        period: 周期：'1min', '5min', '15min', '30min', '60min', 'day', 'week', 'month'
    Returns:
        dict: {'open': [], 'close': [], 'high': [], 'low': [], 'volume': [], 'pct_chg': [], 'dates': []}
    """
    # V2.8.1：日K线优先从本地DuckDB缓存读取（非交易时段通达信可能无法连接）
    if period == 'day':
        cached_data = _get_kline_from_duckdb(code, count)
        if cached_data and len(cached_data) >= min(20, count):
            print(f"[K线缓存] {code} 从本地缓存读取{len(cached_data)}条数据", flush=True)
            result = _convert_kline_format(cached_data)
            if result:
                result['period'] = period
                result['source'] = 'duckdb_cache'
            return result

    # 缓存不足或非日K线，使用通达信在线获取
    data = get_kline_tdx(code, count, period)
    if data:
        result = _convert_kline_format(data)
        if result:
            result['period'] = period
            result['source'] = 'pytdx_online'
        return result

    # V2.9.0：通达信不可用时，降级到HTTP备用源（东方财富→腾讯→新浪）
    from utils.http_market_data import get_kline_http
    data = get_kline_http(code, count, period)
    if data:
        result = _convert_kline_format(data)
        if result:
            result['period'] = period
            result['source'] = 'http'
        return result

    return None


def get_minute_time_data(code):
    """
    获取分时数据
    Args:
        code: 股票代码（6位）
    Returns:
        dict: {'times': [], 'prices': [], 'volumes': [], 'avg_prices': [], 'pre_close': 0}
    """
    data = get_minute_time_data_tdx(code)
    if not data:
        return None

    result = {
        'times': [],
        'prices': [],
        'volumes': [],
        'avg_prices': [],
        'pre_close': 0,
        'period': 'time'
    }

    for d in data:
        result['times'].append(d['time'])
        result['prices'].append(d['price'])
        result['volumes'].append(d['volume'])
        result['avg_prices'].append(d['avg_price'])

    # 昨收价（用第一根分钟K线的前一天收盘价，暂时用第一个价格作为参考）
    if len(data) > 0:
        # TODO: 从行情接口获取昨收价
        result['pre_close'] = data[0]['price']

    return result


def get_daily_kline_batch(codes, count=250, max_workers=5, progress_callback=None):
    """
    批量获取日K线数据（多线程并行 + 缓存）
    Args:
        codes: 股票代码列表
        count: 获取数量
        max_workers: 最大线程数
        progress_callback: 进度回调 callback(done, total, code)
    Returns:
        dict: {code: kline_data, ...}
    """
    result = {}
    total = len(codes)
    done = 0

    # 第一步：先从缓存获取
    cache = get_kline_cache()
    miss_codes = []
    hit_count = 0

    for code in codes:
        cached = cache.get(code, count=count, period='day')
        if cached:
            result[code] = cached
            hit_count += 1
            done += 1
            if progress_callback:
                progress_callback(done, total, code)
        else:
            miss_codes.append(code)

    print(f"[K线缓存] 命中{hit_count}只，需请求{len(miss_codes)}只")

    # 第二步：缓存没命中的，去API获取
    if miss_codes:
        def _fetch(code):
            return code, get_daily_kline(code, count)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch, code): code for code in miss_codes}
            for future in as_completed(futures):
                try:
                    code, kline = future.result()
                    if kline:
                        result[code] = kline
                        # 写入缓存
                        cache.set(code, kline, count=count, period='day')
                except Exception:
                    pass
                done += 1
                if progress_callback:
                    progress_callback(done, total, futures[future])

    return result


def _convert_kline_format(kline_list):
    """将list格式的K线转换为dict格式（统一格式）"""
    if not kline_list:
        return None

    result = {
        'open': [],
        'close': [],
        'high': [],
        'low': [],
        'volume': [],
        'pct_chg': [],
        'dates': [],
    }

    for i, k in enumerate(kline_list):
        result['open'].append(float(k['open']))
        result['close'].append(float(k['close']))
        result['high'].append(float(k['high']))
        result['low'].append(float(k['low']))
        result['volume'].append(float(k['volume']))

        # 日期字段（兼容不同字段名，统一格式化为YYYY-MM-DD）
        date_val = k.get('date') or k.get('datetime') or k.get('time') or ''
        date_str = str(date_val)
        # 处理各种日期格式
        if len(date_str) >= 8 and date_str[:8].isdigit():
            # 纯数字格式：20250801...
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        elif ' ' in date_str:
            # 带时间格式：2025-08-01 15:00:00
            date_str = date_str.split(' ')[0]
        elif len(date_str) > 10 and date_str[4] == '-' and date_str[7] == '-':
            # 已经是YYYY-MM-DD格式但后面还有内容
            date_str = date_str[:10]
        result['dates'].append(date_str)

        # 计算涨跌幅
        if i > 0:
            prev_close = kline_list[i - 1]['close']
            if prev_close > 0:
                pct = (k['close'] - prev_close) / prev_close * 100
                result['pct_chg'].append(round(pct, 2))
            else:
                result['pct_chg'].append(0)
        else:
            result['pct_chg'].append(0)

    return result


def normalize_stock_code(code):
    """
    统一股票代码格式，转换为6位数字
    支持：002174、002174.SZ、sz002174、SZ002174等
    """
    if not code:
        return ''

    code_str = str(code).strip().upper()

    # 去掉后缀 .SH / .SZ / .BJ
    if '.' in code_str:
        code_str = code_str.split('.')[0]

    # 去掉前缀 SH / SZ / BJ
    if code_str.startswith(('SH', 'SZ', 'BJ')):
        code_str = code_str[2:]

    # 确保6位
    if len(code_str) == 6 and code_str.isdigit():
        return code_str

    return code_str
