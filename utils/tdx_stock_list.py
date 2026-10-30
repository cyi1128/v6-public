"""
通达信股票列表和实时行情获取工具
用于选股模块获取股票列表和基本行情数据
全部使用通达信(pytdx)数据源
V2.9.2：统一使用tdx_connector的熔断版get_tdx_api（连续2次空数据→60秒冷却）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
from pytdx.hq import TdxHq_API
from utils.tdx_connector import get_tdx_api as _get_tdx_api_cb, pytdx_is_circuit_open

# V2.8.1：全局pytdx操作锁
_PYTDX_LOCK = threading.Lock()


# 可用服务器列表（按优先级）—— 实际连接逻辑由tdx_connector.get_tdx_api处理
TDX_SERVERS = [
    ('180.153.18.170', 7709),
    ('119.147.212.81', 7709),
    ('112.74.214.43', 7709),
    ('221.231.141.60', 7709),
]

# 财务信息缓存（总股本/流通股本不会经常变化）
_finance_cache = {}
_stock_list_cache = None

# 行业代码映射（通达信行业分类）
INDUSTRY_MAP = {
    1: '银行', 2: '保险', 3: '证券', 4: '多元金融',
    5: '房地产', 6: '建筑工程', 7: '建筑材料', 8: '装修装饰',
    9: '钢铁', 10: '有色金属', 11: '煤炭', 12: '石油',
    13: '化工', 14: '化学制药', 15: '生物制药', 16: '中药',
    17: '医药商业', 18: '医疗服务', 19: '医疗器械', 20: '农业',
    21: '林业', 22: '畜牧业', 23: '渔业', 24: '饲料',
    25: '白酒', 26: '啤酒', 27: '饮料', 28: '食品',
    29: '家电', 30: '汽车', 31: '汽车零部件', 32: '摩托车',
    33: '纺织', 34: '服装', 35: '造纸', 36: '印刷',
    37: '日用化工', 38: '化学纤维', 39: '塑料', 40: '橡胶',
    41: '电子', 42: '半导体', 43: '元器件', 44: '通信设备',
    45: '通信服务', 46: '计算机硬件', 47: '软件', 48: '互联网',
    49: '传媒', 50: '游戏', 51: '旅游', 52: '酒店',
    53: '餐饮', 54: '零售', 55: '批发', 56: '物流',
    57: '港口', 58: '航运', 59: '航空', 60: '公路',
    61: '铁路', 62: '电力', 63: '水务', 64: '燃气',
    65: '环保', 66: '军工', 67: '机械', 68: '电气设备',
    69: '仪器仪表', 70: '通用设备', 71: '专用设备', 72: '运输设备',
}

# 行业分类本地覆盖映射（修正外部数据源中的已知错误）
INDUSTRY_OVERRIDE = {
    '605169': '公用事业',
}


def get_industry_name(code):
    """行业代码转名称"""
    return INDUSTRY_MAP.get(code, '')


def get_tdx_api():
    """
    获取已连接的通达信API对象（V2.9.2：委托给tdx_connector熔断版）
    单台超时2秒，总超时≤5秒，连续2次空数据触发60秒熔断
    """
    return _get_tdx_api_cb()


def get_stock_list_tdx(force_refresh=False):
    """
    通过通达信获取A股股票列表
    带缓存，避免重复获取
    """
    global _stock_list_cache
    if _stock_list_cache is not None and not force_refresh:
        return _stock_list_cache

    api = get_tdx_api()
    if not api:
        return _stock_list_cache or []

    stocks = []
    try:
        # 深圳A股
        count = api.get_security_count(0)
        for i in range(0, count, 1000):
            data = api.get_security_list(0, i)
            if data:
                for item in data:
                    code = item.get('code', '')
                    name = item.get('name', '')
                    if code and code.startswith(('000', '001', '002', '003', '300', '301')):
                        stocks.append({'code': code, 'name': name, 'market': 0})

        # 上海A股
        count = api.get_security_count(1)
        for i in range(0, count, 1000):
            data = api.get_security_list(1, i)
            if data:
                for item in data:
                    code = item.get('code', '')
                    name = item.get('name', '')
                    if code and code.startswith(('600', '601', '603', '605', '688')):
                        stocks.append({'code': code, 'name': name, 'market': 1})
    except Exception as e:
        print(f"获取股票列表失败: {e}")
    finally:
        try:
            api.disconnect()
        except Exception:
            pass

    _stock_list_cache = stocks
    return stocks


def get_realtime_quotes_tdx(codes):
    """
    通过通达信获取实时行情，失败自动降级到HTTP（腾讯批量行情）
    V2.9.2：pytdx熔断期间直接走HTTP，不等待连接
    """
    if not codes:
        return {}

    # V2.9.2：熔断期间直接降级HTTP
    if pytdx_is_circuit_open():
        try:
            from utils.http_market_data import get_realtime_quotes_http
            http_result = get_realtime_quotes_http(codes)
            if http_result:
                print(f"[行情HTTP] pytdx熔断中，直接降级获取{len(http_result)}只实时行情", flush=True)
            return http_result
        except Exception as e:
            print(f"[行情HTTP] 备用源失败: {e}", flush=True)
        return {}

    api = get_tdx_api()
    # 快速健康检查——服务器可连但行情命令无数据时直接降级HTTP
    if api is not None:
        try:
            probe = api.get_security_bars(9, 0, '000001', 0, 3)
        except Exception:
            probe = None
        if not probe:
            try:
                api.disconnect()
            except Exception:
                pass
            api = None
    if not api:
        try:
            from utils.http_market_data import get_realtime_quotes_http
            http_result = get_realtime_quotes_http(codes)
            if http_result:
                print(f"[行情HTTP] 通达信不可用，直接降级获取{len(http_result)}只实时行情", flush=True)
            return http_result
        except Exception as e:
            print(f"[行情HTTP] 备用源失败: {e}", flush=True)
        return {}

    result = {}
    try:
        tdx_codes = []
        for code in codes:
            market = 1 if code.startswith(('6', '9')) else 0
            tdx_codes.append((market, code))

        for i in range(0, len(tdx_codes), 50):
            batch = tdx_codes[i:i+50]
            data = api.get_security_quotes(batch)
            if data:
                for j, item in enumerate(data):
                    if item:
                        code = codes[i + j]
                        price = item.get('price', 0)
                        last_close = item.get('last_close', 0)
                        if price == 0 and last_close > 0:
                            price = last_close
                        pct_chg = 0
                        if last_close > 0:
                            pct_chg = round((price - last_close) / last_close * 100, 2)

                        result[code] = {
                            'price': price,
                            'last_close': last_close,
                            'open': item.get('open', 0),
                            'high': item.get('high', 0),
                            'low': item.get('low', 0),
                            'volume': item.get('vol', 0),
                            'amount': item.get('amount', 0),
                            'pct_chg': pct_chg,
                            'name': item.get('name', ''),
                        }
    except Exception as e:
        print(f"获取实时行情失败: {e}")
    finally:
        try:
            api.disconnect()
        except Exception:
            pass

    # 通达信失败时降级到HTTP备用源（腾讯批量行情）
    if not result:
        try:
            from utils.http_market_data import get_realtime_quotes_http
            result = get_realtime_quotes_http(codes)
            if result:
                print(f"[行情HTTP] 通达信失败，降级获取{len(result)}只实时行情", flush=True)
        except Exception as e:
            print(f"[行情HTTP] 备用源失败: {e}", flush=True)

    return result


def get_finance_info_batch(codes):
    """
    批量获取财务信息（总股本、流通股本、行业）
    带缓存，避免重复获取
    """
    if not codes:
        return {}

    result = {}
    need_fetch = []
    for code in codes:
        if code in _finance_cache:
            result[code] = _finance_cache[code]
        else:
            need_fetch.append(code)

    if not need_fetch:
        return result

    api = get_tdx_api()
    if api is not None:
        try:
            probe = api.get_security_bars(9, 0, '000001', 0, 3)
        except Exception:
            probe = None
        if not probe:
            try:
                api.disconnect()
            except Exception:
                pass
            api = None
    if not api:
        return result

    try:
        for code in need_fetch:
            try:
                market = 1 if code.startswith(('6', '9')) else 0
                data = api.get_finance_info(market, code)
                if data:
                    ind_name = get_industry_name(data.get('industry', 0))
                    if code in INDUSTRY_OVERRIDE:
                        ind_name = INDUSTRY_OVERRIDE[code]
                    fin = {
                        'zongguben': data.get('zongguben', 0),
                        'liutongguben': data.get('liutongguben', 0),
                        'industry': data.get('industry', 0),
                        'industry_name': ind_name,
                    }
                    result[code] = fin
                    _finance_cache[code] = fin
            except Exception:
                continue
    except Exception as e:
        print(f"获取财务信息失败: {e}")
    finally:
        try:
            api.disconnect()
        except Exception:
            pass

    return result


def get_stocks_with_quotes_tdx(max_stocks=500, sort_by='pct_chg', desc=True, progress_callback=None):
    """
    获取股票列表并附带实时行情（全部使用通达信数据源）
    """
    if progress_callback:
        progress_callback(0, 4, '正在获取股票列表...')
    stock_list = get_stock_list_tdx()
    if not stock_list:
        return []

    if progress_callback:
        progress_callback(1, 4, '正在获取实时行情...')
    fetch_count = min(len(stock_list), max_stocks * 2, 3000)
    codes = [s['code'] for s in stock_list[:fetch_count]]
    code_name_map = {s['code']: s['name'] for s in stock_list}
    quotes = get_realtime_quotes_tdx(codes)
    if not quotes:
        return []

    if progress_callback:
        progress_callback(2, 4, '正在排序并筛选...')
    quote_list = []
    for code, q in quotes.items():
        quote_list.append({
            'code': code,
            'name': code_name_map.get(code, q.get('name', '')),
            'price': q['price'],
            'pct_chg': q['pct_chg'],
            'change': q['pct_chg'],
            'volume': q['volume'],
            'amount': q['amount'],
        })

    if sort_by == 'pct_chg':
        quote_list.sort(key=lambda x: x['pct_chg'], reverse=desc)
    elif sort_by == 'amount':
        quote_list.sort(key=lambda x: x['amount'], reverse=desc)

    top_count = min(len(quote_list), max_stocks * 2)
    top_codes = [q['code'] for q in quote_list[:top_count]]

    if progress_callback:
        progress_callback(3, 4, f'正在获取财务信息（{top_count}只）...')
    finance = get_finance_info_batch(top_codes)

    if progress_callback:
        progress_callback(4, 4, '正在合并数据...')
    result = []
    for q in quote_list[:top_count]:
        code = q['code']
        price = q['price']
        volume = q['volume']

        market_cap = 0
        turnover = 0
        industry = ''
        if code in finance:
            fin = finance[code]
            zongguben = fin['zongguben']
            liutongguben = fin['liutongguben']
            if zongguben > 0:
                market_cap = round(price * zongguben / 100000000, 2)
            if liutongguben > 0:
                turnover = round(volume * 100 / liutongguben * 100, 2)
            industry = fin['industry_name']

        result.append({
            'code': code,
            'name': q['name'],
            'price': price,
            'pct_chg': q['pct_chg'],
            'change': q['pct_chg'],
            'volume': volume,
            'amount': q['amount'],
            'market_cap': market_cap,
            'turnover': turnover,
            'industry': industry,
        })

    return result[:max_stocks]


def get_full_market_quotes(progress_callback=None, main_board_only=False, exclude_st=False):
    """
    获取全市场A股股票列表+实时行情（不含财务信息，速度快）
    """
    if progress_callback:
        progress_callback(0, 3, '正在获取全市场股票列表...')
    stock_list = get_stock_list_tdx()
    if not stock_list:
        return []

    if main_board_only or exclude_st:
        filtered = []
        for s in stock_list:
            code = s.get('code', '')
            name = s.get('name', '')
            if main_board_only and not (code.startswith('60') or code.startswith('00')):
                continue
            if exclude_st and ('ST' in name or 'st' in name.lower() or '*ST' in name):
                continue
            filtered.append(s)
        stock_list = filtered
        if progress_callback:
            progress_callback(0, 3, f'预过滤后剩余{len(stock_list)}只（主板+非ST）')

    total = len(stock_list)
    if progress_callback:
        progress_callback(1, 3, f'共{total}只股票，正在获取实时行情...')

    codes = [s['code'] for s in stock_list]
    code_name_map = {s['code']: s['name'] for s in stock_list}
    quotes = get_realtime_quotes_tdx(codes)

    if progress_callback:
        progress_callback(2, 3, f'获取到{len(quotes)}条行情，正在合并数据...')

    result = []
    for code, q in quotes.items():
        result.append({
            'code': code,
            'name': code_name_map.get(code, q.get('name', '')),
            'price': q['price'],
            'pct_chg': q['pct_chg'],
            'change': q['pct_chg'],
            'last_close': q.get('last_close', 0),
            'open': q.get('open', 0),
            'high': q.get('high', 0),
            'low': q.get('low', 0),
            'volume': q['volume'],
            'amount': q['amount'],
            'market_cap': 0,
            'turnover': 0,
            'industry': '',
        })

    if progress_callback:
        progress_callback(3, 4, f'正在获取{len(result)}只股票的财务信息（换手率等）...')
    result = enrich_finance_info(result, progress_callback=lambda c, t, m: progress_callback(3, 4, m) if progress_callback else None)

    if progress_callback:
        progress_callback(4, 4, f'全市场行情获取完成，共{len(result)}只')

    return result


def enrich_finance_info(stocks, progress_callback=None):
    """为股票列表补充财务信息（市值、换手率、行业）"""
    if not stocks:
        return []

    codes = [s['code'] for s in stocks]
    total = len(codes)

    if progress_callback:
        progress_callback(0, total, f'正在获取{total}只股票的财务信息...')

    finance = get_finance_info_batch(codes)

    if progress_callback:
        progress_callback(total, total, f'财务信息获取完成，共{len(finance)}条')

    for s in stocks:
        code = s['code']
        price = s.get('price', 0)
        volume = s.get('volume', 0)

        if code in finance:
            fin = finance[code]
            zongguben = fin.get('zongguben', 0)
            liutongguben = fin.get('liutongguben', 0)

            if zongguben > 0:
                s['market_cap'] = round(price * zongguben / 100000000, 2)

            if liutongguben > 0:
                s['turnover'] = round(volume * 100 / liutongguben * 100, 2)

            s['industry'] = fin.get('industry_name', '')

    return stocks


# 测试
if __name__ == '__main__':
    print("测试通达信股票列表...")
    stocks = get_stock_list_tdx()
    print(f"获取到 {len(stocks)} 只股票")
    if stocks:
        print(f"前5只: {[(s['code'], s['name']) for s in stocks[:5]]}")

    print("\n测试实时行情...")
    quotes = get_realtime_quotes_tdx(['000001', '600000', '000002'])
    for code, q in quotes.items():
        print(f"  {code}: 价格={q['price']}, 涨跌幅={q['pct_chg']}%")

    print("\n测试带行情的股票列表（涨幅前20）...")
    stocks_q = get_stocks_with_quotes_tdx(max_stocks=20)
    print(f"获取到 {len(stocks_q)} 只")
    for s in stocks_q[:10]:
        print(f"  {s['name']}({s['code']}): 价格={s['price']}, 涨幅={s['change']}%")
