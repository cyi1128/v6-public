"""
HTTP行情数据备用源（V2.9.2）
当通达信(pytdx)数据源不可用时，自动降级到以下HTTP数据源：
- K线：腾讯 web.ifzq.gtimg.cn（fqkline必须web前缀，V2.9.5实测）→ 新浪 quotes.sina.cn → 本地kline_cache.duckdb
  （V2.9.5：日K fqkline 必须 web.ifzq 前缀（无前缀501）；分钟K mkline 用无前缀；东财push2his被屏蔽、push2delay不支持K线，已从K线链移除）
- 实时行情：腾讯 qt.gtimg.cn（批量，速度快）→ 本地缓存兜底
- 全市场快照：腾讯批量（基于本地股票代码缓存）
- 指数行情：腾讯 qt.gtimg.cn
- 通用：http_get_with_retry（重试+按域名熔断），eastmoney_request（东财专用熔断）
"""
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# 全量股票代码缓存（模块级，避免重复读文件）
_STOCK_CODE_CACHE = None


def _http_get(url, encoding='utf-8', referer=None, timeout=10):
    """HTTP GET 请求，失败抛异常由调用方兜底"""
    headers = {'User-Agent': _UA}
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, errors='ignore')
    except urllib.error.HTTPError as e:
        # 【V2.9.6修复】腾讯WAF对 fqkline 日K接口返回 501（waf.tencent.com 挑战页），
        # 重试无意义且会拖慢降级链。标记为 WAF 拦截并快速抛错，让调用方立即切新浪。
        if e.code == 501:
            try:
                body = e.read().decode('utf-8', 'ignore')
                if 'waf.tencent' in body or '501page' in body:
                    raise _WafBlockedError(url)
            except _WafBlockedError:
                raise
            except Exception:
                pass
        raise


class _WafBlockedError(Exception):
    """腾讯WAF拦截（HTTP 501 挑战页），重试无意义，应立即切换数据源"""


# 通用HTTP请求失败日志去重（避免循环刷屏）
_HTTP_FAIL_LOG_CACHE = {}  # {url_prefix: last_log_time}
_HTTP_FAIL_LOG_INTERVAL = 30  # 同一域名30秒内只打印一次失败日志

# 通用按域名熔断（V2.9.2）：失败3次后冷却60秒
_GENERAL_CB = {}  # {host: {'fail_count': int, 'cooldown_until': float}}
_GENERAL_CB_LOCK = None  # 延迟初始化，避免import时依赖threading
_GENERAL_CB_THRESHOLD = 3
_GENERAL_CB_COOLDOWN = 60


def _get_general_cb_lock():
    global _GENERAL_CB_LOCK
    if _GENERAL_CB_LOCK is None:
        import threading
        _GENERAL_CB_LOCK = threading.Lock()
    return _GENERAL_CB_LOCK


def _general_cb_is_open(host):
    import time as _t
    lock = _get_general_cb_lock()
    with lock:
        state = _GENERAL_CB.get(host)
        if state and state['cooldown_until'] > _t.time():
            return True
        if state and state['cooldown_until'] > 0:
            state['fail_count'] = 0
            state['cooldown_until'] = 0
    return False


def _general_cb_record(host, success):
    import time as _t
    lock = _get_general_cb_lock()
    with lock:
        state = _GENERAL_CB.setdefault(host, {'fail_count': 0, 'cooldown_until': 0})
        if success:
            state['fail_count'] = 0
            state['cooldown_until'] = 0
        else:
            state['fail_count'] += 1
            if state['fail_count'] >= _GENERAL_CB_THRESHOLD:
                state['cooldown_until'] = _t.time() + _GENERAL_CB_COOLDOWN


def get_general_circuit_breaker_status():
    """获取通用熔断状态（用于健康监控）"""
    lock = _get_general_cb_lock()
    with lock:
        return {h: dict(s) for h, s in _GENERAL_CB.items()}


def http_get_with_retry(url, encoding='utf-8', referer=None, timeout=10, max_retries=2):
    """
    通用HTTP GET请求，内置指数退避重试（0.5s, 1s）和异常捕获。
    V2.9.2：新增按域名熔断（连续3次失败冷却60秒），熔断期间直接跳过不等待。
    保留与 _http_get 相同的返回值语义：成功返回解码后的文本，全部重试失败后抛异常。

    Args:
        url: 请求URL
        encoding: 响应编码，默认utf-8
        referer: Referer头
        timeout: 超时秒数，默认10
        max_retries: 最大重试次数，默认2（即最多请求3次）

    Returns:
        str: 解码后的响应文本

    Raises:
        Exception: 所有重试均失败时抛出最后一次异常
    """
    import time as _time
    from urllib.parse import urlparse
    host = urlparse(url).netloc or url[:60]

    # 熔断检查：如果该域名处于冷却期，直接抛异常不等待
    if _general_cb_is_open(host):
        raise Exception('circuit_breaker_open: %s（连续失败后冷却中）' % host)

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            result = _http_get(url, encoding=encoding, referer=referer, timeout=timeout)
            _general_cb_record(host, True)
            return result
        except _WafBlockedError as _waf:
            # 【V2.9.6修复】WAF拦截（501）重试无意义，直接抛出不等待
            _general_cb_record(host, False)
            raise _waf
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                backoff = 0.5 * (2 ** attempt)  # 0.5s, 1s
                _time.sleep(backoff)
    # 全部重试失败，记录熔断
    _general_cb_record(host, False)
    # 按域名去重打印日志（30秒内同一域名只打印一次）
    now = _time.time()
    last_log = _HTTP_FAIL_LOG_CACHE.get(host, 0)
    if now - last_log >= _HTTP_FAIL_LOG_INTERVAL:
        _HTTP_FAIL_LOG_CACHE[host] = now
        print(f'[HTTP重试] {host} 请求失败（已重试{max_retries}次）: {last_exc}', flush=True)
    raise last_exc


def normalize_code(code):
    """统一为6位数字代码"""
    if not code:
        return ''
    s = str(code).strip().upper()
    if '.' in s:
        s = s.split('.')[0]
    for p in ('SH', 'SZ', 'BJ'):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s if len(s) == 6 and s.isdigit() else ''


def _to_qq_symbol(code):
    return ('sh' if code.startswith(('6', '9')) else 'sz') + code


def _to_sina_symbol(code):
    return ('sh' if code.startswith(('6', '9')) else 'sz') + code


def _to_em_secid(code):
    return ('1.' if code.startswith(('6', '9')) else '0.') + code


# ============================================================
# K线（腾讯 → 东方财富 → 新浪）
# ============================================================
_EM_KLT = {'1min': 1, '5min': 5, '15min': 15, '30min': 30, '60min': 60,
           'day': 101, 'week': 102, 'month': 103}


def _kline_from_eastmoney(code, count, period):
    klt = _EM_KLT.get(period)
    if klt is None:
        return []
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?'
           'secid=%s&fields1=f1,f2,f3,f4,f5,f6'
           '&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'
           '&klt=%d&fqt=1&beg=0&end=20500101&lmt=%d'
           % (_to_em_secid(code), klt, count))
    d = json.loads(http_get_with_retry(url, referer='https://quote.eastmoney.com/'))
    klines = (d.get('data') or {}).get('klines') or []
    bars = []
    for line in klines:
        p = line.split(',')
        if len(p) < 6:
            continue
        bars.append({
            'date': p[0],
            'open': float(p[1]),
            'close': float(p[2]),
            'high': float(p[3]),
            'low': float(p[4]),
            'volume': float(p[5]),
        })
    return bars


def _kline_from_tencent(code, count, period):
    sym = _to_qq_symbol(code)
    if period in ('1min', '5min', '15min', '30min', '60min'):
        m = {'1min': 'm1', '5min': 'm5', '15min': 'm15',
             '30min': 'm30', '60min': 'm60'}[period]
        url = ('https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=%s,%s,,320'
               % (sym, m))
        d = json.loads(http_get_with_retry(url, referer='https://gu.qq.com/'))
        arr = (d.get('data') or {}).get(sym) or {}
        rows = arr.get(m) or []
        bars = []
        for r in rows:
            if len(r) < 6:
                continue
            bars.append({
                'date': str(r[0])[:10],
                'open': float(r[1]),
                'close': float(r[2]),
                'high': float(r[3]),
                'low': float(r[4]),
                'volume': float(r[5]),
            })
        return bars

    # 日/周/月K
    # V2.9.5修复（2026-09-18实测）：fqkline/get 必须使用 web.ifzq.gtimg.cn 前缀，
    # 无前缀 ifzq.gtimg.cn 实测返回 HTTP 501 Not Implemented。
    # （注意：分钟K mkline 接口与日K fqkline 的可用域名恰好相反，不可混用。）
    tmap = {'day': 'day', 'week': 'week', 'month': 'month'}
    t = tmap.get(period, 'day')
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,%s,,,%d,qfq'
           % (sym, t, count))
    d = json.loads(http_get_with_retry(url, referer='https://gu.qq.com/'))
    arr = (d.get('data') or {}).get(sym) or {}
    rows = arr.get('qfq' + t) or arr.get(t) or []
    bars = []
    for r in rows:
        if len(r) < 6:
            continue
        bars.append({
            'date': str(r[0])[:10],
            'open': float(r[1]),
            'close': float(r[2]),
            'high': float(r[3]),
            'low': float(r[4]),
            'volume': float(r[5]),
        })
    return bars


def _kline_from_sina(code, count, period):
    if period != 'day':
        return []
    sym = _to_sina_symbol(code)
    url = ('https://quotes.sina.cn/cn/api/jsonp_v2.php/var%%20_%s=/'
           'CN_MarketDataService.getKLineData?symbol=%s&scale=240&ma=no&datalen=%d'
           % (sym, sym, count))
    raw = http_get_with_retry(url, referer='https://finance.sina.com.cn')
    # JSONP: /*..*/ var _sym=([...]);
    start = raw.find('([')
    end = raw.rfind('])')
    if start < 0 or end < 0:
        return []
    arr = json.loads(raw[start + 1:end + 1])
    bars = []
    for r in arr:
        bars.append({
            'date': r.get('day', '')[:10],
            'open': float(r.get('open', 0) or 0),
            'close': float(r.get('close', 0) or 0),
            'high': float(r.get('high', 0) or 0),
            'low': float(r.get('low', 0) or 0),
            'volume': float(r.get('volume', 0) or 0),
        })
    return bars


def _kline_from_local_cache(code, count, period):
    """
    从本地kline_cache.duckdb读取K线（最终兜底源）
    仅支持日K线（缓存表只存日K）
    Returns:
        list: [{'date':, 'open':, 'close':, 'high':, 'low':, 'volume':}, ...] 按日期升序
    """
    if period != 'day':
        return []
    try:
        import duckdb
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'data', 'cache', 'kline_cache.duckdb')
        if not os.path.exists(db_path):
            return []
        con = duckdb.connect(db_path, read_only=True)
        rows = con.execute("""
            SELECT date, open, high, low, close, volume
            FROM kline_cache
            WHERE TRIM(code) = ?
            ORDER BY date DESC
            LIMIT ?
        """, (code, count)).fetchall()
        con.close()
        if not rows:
            return []
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
        print('[K线缓存] %s 本地缓存读取失败: %s' % (code, e), flush=True)
        return []


# K线源失败日志去重（30秒内同一股票+源只打印一次）
_KLINE_FAIL_LOG_CACHE = {}
_KLINE_FAIL_LOG_INTERVAL = 30


def _log_kline_fail(code, source, err):
    """K线源失败日志，30秒去重"""
    import time as _t
    key = '%s|%s' % (code, source)
    now = _t.time()
    last = _KLINE_FAIL_LOG_CACHE.get(key, 0)
    if now - last >= _KLINE_FAIL_LOG_INTERVAL:
        _KLINE_FAIL_LOG_CACHE[key] = now
        print('[K线HTTP] %s %s失败: %s' % (code, source, err), flush=True)


# 最近一次K线请求的元数据（供调用方读取data_source/is_cache）
_kline_last_meta = {'data_source': '', 'is_cache': False}


def get_kline_http(code, count=250, period='day'):
    """
    通过HTTP备用源获取K线（V2.9.2降级链：腾讯ifzq → 新浪 → 本地缓存）

    实测状态(2026-09-18)：
    - 腾讯 web.ifzq.gtimg.cn（fqkline日K）: ✅ 可用（无前缀ifzq返回501，V2.9.5已回正为web前缀）
    - 腾讯 ifzq.gtimg.cn（mkline分钟K）: ✅ 可用（web前缀反而DNS失败，分钟K保持无前缀）
    - 东方财富 push2his: ❌ 被屏蔽 RemoteDisconnected；push2delay不支持K线（返回空klines）
    - 新浪 quotes.sina.cn: ✅ 可用（仅日K）
    - 本地kline_cache.duckdb: ✅ 757827行，3017只股票

    Returns:
        list: [{'date':, 'open':, 'close':, 'high':, 'low':, 'volume':}, ...] 按日期升序
        元数据通过 get_kline_http.last_meta 获取: {'data_source': str, 'is_cache': bool}
    """
    code = normalize_code(code)
    if not code:
        _kline_last_meta['data_source'] = ''
        _kline_last_meta['is_cache'] = False
        return []

    # V2.9.6降级链：新浪（实测稳定）→ 腾讯（2026-09-18被WAF 501拦截，快速失败）→ 本地缓存
    # 东方财富K线已从主链移除（push2his被屏蔽，push2delay无K线数据）
    sources = [
        ('新浪', _kline_from_sina, False),
        ('腾讯', _kline_from_tencent, False),
        ('本地缓存', _kline_from_local_cache, True),
    ]
    for name, fn, is_cache in sources:
        try:
            bars = fn(code, count, period)
            if bars:
                _kline_last_meta['data_source'] = name
                _kline_last_meta['is_cache'] = is_cache
                print('[K线HTTP] %s 从%s获取%d条(%s)%s' % (
                    code, name, len(bars), period,
                    ' [缓存]' if is_cache else ''), flush=True)
                return bars
        except Exception as e:
            _log_kline_fail(code, name, str(e)[:100])
    _kline_last_meta['data_source'] = 'none'
    _kline_last_meta['is_cache'] = False
    print('[K线HTTP] %s 全部源失败（含本地缓存），返回空列表' % code, flush=True)
    return []


# 绑定元数据到函数属性，方便调用方读取
get_kline_http.last_meta = _kline_last_meta


# ============================================================
# 实时行情（腾讯批量）
# ============================================================
def _parse_qq_quote(line):
    """解析腾讯行情单行，返回 {code: quote_dict} 或 None"""
    line = line.strip()
    if not line or '=' not in line:
        return None
    key, val = line.split('=', 1)
    if not key.startswith('v_'):
        return None
    code = key.split('_')[-1]
    if len(code) < 6 or not code[-6:].isdigit():
        return None
    code = code[-6:]
    parts = val.strip('"').split('~')
    if len(parts) < 38:
        return None
    try:
        price = float(parts[3] or 0)
        last_close = float(parts[4] or 0)
        pct_chg = 0.0
        if last_close > 0:
            pct_chg = round((price - last_close) / last_close * 100, 2)

        def _f(idx):
            try:
                return float(parts[idx] or 0)
            except (ValueError, IndexError):
                return 0.0

        # 振幅(parts[43])、换手率(parts[38])、流通市值(parts[44],亿)、总市值(parts[45],亿)
        # 均为新增字段，不影响既有按 key 取值的调用方
        # 量比(parts[49])：V2.9.6 新增。实测验证见下——
        #   平安银行 2026-09-24 13:50
        #   腾讯字段[49]=1.42；当日量 813624 手 / (5日均量 814320 手 x 已交易占比 0.708) = 1.41，吻合。
        return {
            'price': price,
            'last_close': last_close,
            'open': float(parts[5] or 0),
            'high': float(parts[33] or 0),
            'low': float(parts[34] or 0),
            'volume': float(parts[6] or 0),        # 手
            'amount': float(parts[37] or 0) * 10000,  # 万元→元
            'pct_chg': pct_chg,
            'name': parts[1],
            'turnover': _f(38),       # 换手率%
            'amplitude': _f(43),      # 振幅%
            'circ_mv': _f(44),        # 流通市值(亿)
            'total_mv': _f(45),       # 总市值(亿)
            'vol_ratio': _f(49),      # 量比（V2.9.6 新增，字段49）
        }
    except (ValueError, IndexError):
        return None


def get_realtime_quotes_http(codes):
    """
    腾讯批量实时行情（HTTP备用源）
    Args:
        codes: 股票代码列表 ['000001', '600000']
    Returns:
        dict: {code: {'price':, 'last_close':, 'open':, 'high':, 'low':,
                      'volume':, 'amount':, 'pct_chg':, 'name':}, ...}
    """
    codes = [normalize_code(c) for c in codes]
    codes = [c for c in codes if c]
    if not codes:
        return {}

    result = {}

    def fetch(batch):
        syms = [_to_qq_symbol(c) for c in batch]
        return http_get_with_retry('https://qt.gtimg.cn/q=' + ','.join(syms), encoding='gbk')

    BATCH = 100
    batches = [codes[i:i + BATCH] for i in range(0, len(codes), BATCH)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch, b): b for b in batches}
        for f in as_completed(futures):
            batch = futures[f]
            try:
                text = f.result()
            except Exception:
                continue
            batch_set = set(batch)
            for line in text.split(';'):
                q = _parse_qq_quote(line)
                if not q:
                    continue
                # 腾讯行键形如 v_sz002213，取末6位即股票代码
                k = line.strip().split('=', 1)[0].split('_')[-1]
                code = k[-6:] if len(k) >= 6 else ''
                if code in batch_set:
                    result[code] = q

    # V2.9.2：在线行情失败时，降级到本地kline_cache.duckdb最新收盘价
    missing = [c for c in codes if c not in result]
    if missing:
        cached = _realtime_from_local_cache(missing)
        if cached:
            result.update(cached)
            print('[行情HTTP] %d只股票在线行情缺失，从本地缓存补齐' % len(cached), flush=True)

    return result


def _realtime_from_local_cache(codes):
    """
    从本地kline_cache.duckdb读取最新收盘价作为实时行情兜底
    Returns:
        dict: {code: {'price':, 'last_close':, 'close':, 'is_cache': True, ...}}
    """
    if not codes:
        return {}
    try:
        import duckdb
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'data', 'cache', 'kline_cache.duckdb')
        if not os.path.exists(db_path):
            return {}
        con = duckdb.connect(db_path, read_only=True)
        result = {}
        for code in codes:
            try:
                row = con.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM kline_cache
                    WHERE TRIM(code) = ?
                    ORDER BY date DESC
                    LIMIT 2
                """, [code]).fetchall()
                if not row or len(row) < 1:
                    continue
                latest = row[0]
                prev_close = row[1][4] if len(row) > 1 else latest[4]
                price = float(latest[4])  # close
                pct = 0.0
                if prev_close and prev_close > 0:
                    pct = round((price - prev_close) / prev_close * 100, 2)
                result[code] = {
                    'price': price,
                    'last_close': float(prev_close),
                    'open': float(latest[1]),
                    'high': float(latest[2]),
                    'low': float(latest[3]),
                    'volume': float(latest[5]),
                    'amount': 0,
                    'pct_chg': pct,
                    'name': code,
                    'is_cache': True,
                    'cache_date': str(latest[0]),
                    'data_source': 'local_cache',
                }
            except Exception:
                continue
        con.close()
        return result
    except Exception as e:
        print('[行情缓存] 本地缓存读取失败: %s' % e, flush=True)
        return {}


# ============================================================
# 全市场快照（腾讯批量，基于本地股票代码缓存）
# ============================================================
def _load_stock_codes():
    """从本地缓存加载全量A股代码列表（与 tdx_stock_list 返回格式一致）"""
    global _STOCK_CODE_CACHE
    if _STOCK_CODE_CACHE is not None:
        return _STOCK_CODE_CACHE

    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'data', 'cache', 'stock_identity.json'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'data', 'stock_names_cache.json'),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                codes = []
                for k, v in d.items():
                    c = normalize_code(k)
                    if not c:
                        continue
                    name = ''
                    if isinstance(v, dict):
                        name = str(v.get('name', ''))
                    elif isinstance(v, str):
                        name = v
                    codes.append({'code': c, 'name': name, 'market': 1 if c.startswith(('6', '9')) else 0})
                _STOCK_CODE_CACHE = codes
                return codes
        except Exception as e:
            print('[HTTP行情] 读取股票代码缓存失败 %s: %s' % (path, e), flush=True)
    _STOCK_CODE_CACHE = []
    return []


def get_full_market_quotes_http(progress_callback=None, main_board_only=False,
                                exclude_st=False):
    """
    全市场行情快照（HTTP备用源）
    返回格式与 utils.tdx_stock_list.get_full_market_quotes 一致（不含财务信息）
    """
    stock_list = _load_stock_codes()
    if not stock_list:
        if progress_callback:
            progress_callback(0, 3, '本地股票代码缓存为空')
        return []

    if main_board_only or exclude_st:
        filtered = []
        for s in stock_list:
            code = s.get('code', '')
            name = s.get('name', '')
            if main_board_only and not (code.startswith('60') or code.startswith('00')):
                continue
            if exclude_st and ('ST' in name.upper()):
                continue
            filtered.append(s)
        stock_list = filtered

    codes = [s['code'] for s in stock_list]
    if progress_callback:
        progress_callback(1, 3, '正在获取实时行情(%d只)...' % len(codes))
    quotes = get_realtime_quotes_http(codes)

    result = []
    for s in stock_list:
        code = s['code']
        q = quotes.get(code)
        if not q:
            continue
        result.append({
            'code': code,
            'name': s.get('name', '') or q.get('name', ''),
            'price': q['price'],
            'pct_chg': q['pct_chg'],
            'change': q['pct_chg'],
            'last_close': q['last_close'],
            'open': q['open'],
            'high': q['high'],
            'low': q['low'],
            'volume': q['volume'],
            'amount': q['amount'],
            'market_cap': 0,
            'turnover': 0,
            'industry': '',
        })
    if progress_callback:
        progress_callback(2, 3, '全市场HTTP行情获取完成，共%d只' % len(result))
    return result


# ============================================================
# 指数行情（东方财富 ulist）
# ============================================================
def get_index_quotes_http():
    """
    指数行情：上证指数(000001)、深证成指(399001)、沪深300(000300)、中证1000(000852)、上证50(000016)、创业板指(399006)
    使用腾讯行情接口（与实时行情同源，可靠）
    Returns:
        dict: {'000001': 涨跌幅%, '399001': ..., '000300': ..., '000852': ..., '000016': ..., '399006': ...}
    """
    # 腾讯代码：上证=sh000001、深证=sz399001、沪深300=sh000300、中证1000=sh000852、上证50=sh000016、创业板指=sz399006
    url = 'https://qt.gtimg.cn/q=sh000001,sz399001,sh000300,sh000852,sh000016,sz399006'
    text = http_get_with_retry(url, encoding='gbk')
    result = {}
    for line in text.split(';'):
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, val = line.split('=', 1)
        if not key.startswith('v_'):
            continue
        parts = val.strip('"').split('~')
        if len(parts) < 38:
            continue
        try:
            price = float(parts[3] or 0)
            last_close = float(parts[4] or 0)
            if last_close <= 0:
                continue
            code = key.split('_')[-1]
            if len(code) >= 6:
                code = code[-6:]
            result[code] = round((price - last_close) / last_close * 100, 2)
        except (ValueError, IndexError):
            continue
    return result


# ============================================================
# 统一东方财富请求函数（V2.9.1）
# 自动使用 push2delay.eastmoney.com（push2 已被屏蔽）
# 内置：超时 + 重试 + 熔断 + 异常捕获
# ============================================================
import time as _time
import threading as _threading

# 熔断状态：{host_prefix: {'fail_count': int, 'cooldown_until': float, 'last_error': str}}
_EM_CIRCUIT_BREAKER = {}
_CB_LOCK = _threading.Lock()
_CB_FAIL_THRESHOLD = 3       # 连续失败3次触发熔断
_CB_COOLDOWN_SECONDS = 60    # 熔断冷却60秒
_CB_RETRY_COUNT = 2           # 每次请求最多重试2次
_CB_RETRY_INTERVAL = 0.5      # 重试间隔0.5秒

# 东方财富可用域名优先级（push2 被屏蔽，push2delay 可用）
_EM_HOSTS = [
    'https://push2delay.eastmoney.com',
    'https://push2.eastmoney.com',
]


def _em_get_circuit_state(host):
    """获取指定host的熔断状态"""
    with _CB_LOCK:
        return _EM_CIRCUIT_BREAKER.get(host, {'fail_count': 0, 'cooldown_until': 0, 'last_error': ''})


def _em_record_success(host):
    """记录请求成功，重置失败计数"""
    with _CB_LOCK:
        if host in _EM_CIRCUIT_BREAKER:
            _EM_CIRCUIT_BREAKER[host]['fail_count'] = 0
            _EM_CIRCUIT_BREAKER[host]['cooldown_until'] = 0


def _em_record_failure(host, error_msg):
    """记录请求失败，达到阈值触发熔断"""
    with _CB_LOCK:
        state = _EM_CIRCUIT_BREAKER.setdefault(host, {'fail_count': 0, 'cooldown_until': 0, 'last_error': ''})
        state['fail_count'] += 1
        state['last_error'] = str(error_msg)[:200]
        if state['fail_count'] >= _CB_FAIL_THRESHOLD:
            state['cooldown_until'] = _time.time() + _CB_COOLDOWN_SECONDS


def _em_is_circuit_open(host):
    """检查host是否处于熔断冷却期"""
    state = _em_get_circuit_state(host)
    if state['cooldown_until'] > 0 and _time.time() < state['cooldown_until']:
        return True
    # 冷却期结束，重置失败计数
    if state['cooldown_until'] > 0 and _time.time() >= state['cooldown_until']:
        with _CB_LOCK:
            state['fail_count'] = 0
            state['cooldown_until'] = 0
    return False


def eastmoney_request(api_path, params=None, timeout=10, referer='https://quote.eastmoney.com/', encoding='utf-8'):
    """
    统一东方财富HTTP请求函数。
    
    自动使用 push2delay.eastmoney.com（push2已被屏蔽），
    内置超时、重试（2次）、熔断（连续3次失败冷却60秒）、异常捕获。
    
    Args:
        api_path: API路径，如 '/api/qt/clist/get' 或 'https://push2delay.eastmoney.com/api/qt/clist/get'
        params: dict, 查询参数
        timeout: 超时秒数，默认10
        referer: Referer头
        encoding: 响应编码
    
    Returns:
        dict: 解析后的JSON数据；失败返回 None（不抛异常）
    
    Example:
        data = eastmoney_request('/api/qt/clist/get', {'fs': 'm:90+t:2', 'fields': 'f12,f14,f3'})
    """
    # 处理完整URL或路径
    if api_path.startswith('http'):
        # 从完整URL中提取路径，并强制替换host为可用域名
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(api_path)
        api_path = parsed.path
        if parsed.query:
            api_path = api_path + '?' + parsed.query
    
    # 构建查询字符串
    query_string = ''
    if params:
        from urllib.parse import urlencode
        query_string = urlencode(params)
    
    last_error = None
    for host in _EM_HOSTS:
        # 熔断检查
        if _em_is_circuit_open(host):
            continue
        
        # 构建完整URL
        if '?' in api_path:
            url = host + api_path + ('&' + query_string if query_string else '')
        else:
            url = host + api_path + ('?' + query_string if query_string else '')
        
        # 重试机制
        for attempt in range(_CB_RETRY_COUNT + 1):
            try:
                text = _http_get(url, encoding=encoding, referer=referer, timeout=timeout)
                data = json.loads(text)
                _em_record_success(host)
                return data
            except Exception as e:
                last_error = e
                if attempt < _CB_RETRY_COUNT:
                    _time.sleep(_CB_RETRY_INTERVAL)
                    continue
                # 所有重试失败，记录熔断
                _em_record_failure(host, str(e))
                break  # 尝试下一个host
    
    # 所有host均失败
    if last_error:
        print(f'[EastMoney] 请求失败: {api_path} - {last_error}', flush=True)
    return None


def get_em_circuit_breaker_status():
    """获取东方财富熔断状态（用于健康监控）"""
    with _CB_LOCK:
        return {host: dict(state) for host, state in _EM_CIRCUIT_BREAKER.items()}


if __name__ == '__main__':
    import time
    print('测试K线(002213):')
    t0 = time.time()
    k = get_kline_http('002213', 10, 'day')
    print('  %d条, %.2fs, 首: %s, 末: %s' % (len(k), time.time() - t0, k[0] if k else '', k[-1] if k else ''))

    print('测试实时行情:')
    q = get_realtime_quotes_http(['002213', '000811', '600000'])
    for c, v in q.items():
        print('  %s %s 价=%s 涨跌=%s%% 高=%s 低=%s 额=%s' %
              (c, v['name'], v['price'], v['pct_chg'], v['high'], v['low'], v['amount']))

    print('测试指数:')
    print(' ', get_index_quotes_http())
