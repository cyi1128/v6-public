# -*- coding: utf-8 -*-
"""
K线缓存增量更新服务
- incremental_update_kline(codes): 只获取缓存最后日期之后的新K线
- 用于下次开盘时快速更新最新1-5根K线
V2.9.2：新增 get_latest_kline / get_latest_quote 公开兜底接口
"""
import os
import sys
import time
import duckdb
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
INCREMENTAL_FETCH_DAYS = 15  # 增量更新时获取最近15根K线(足够覆盖节假日)
MAX_WORKERS = 2  # V2.8：从5降低到2，避免pytdx多线程竞争
RETRY_TIMES = 2

_db_lock = Lock()


def get_db_connection():
    """获取数据库连接"""
    return duckdb.connect(DB_PATH)


def get_all_cached_codes():
    """获取缓存中所有股票代码"""
    con = get_db_connection()
    try:
        codes = [r[0] for r in con.execute("SELECT DISTINCT code FROM kline_cache_meta ORDER BY code").fetchall()]
        return codes
    finally:
        con.close()


def get_last_date(code):
    """获取某只股票缓存中的最后日期"""
    con = get_db_connection()
    try:
        row = con.execute("SELECT last_date FROM kline_cache_meta WHERE code = ?", [code]).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _fetch_incremental_kline(code, last_date):
    """获取单只股票增量K线(只保留last_date之后的)"""
    from utils.kline_fetcher import fetch_kline

    for attempt in range(RETRY_TIMES):
        try:
            kline_data = fetch_kline(code, days=INCREMENTAL_FETCH_DAYS)
            if kline_data:
                # 过滤只保留last_date之后的新K线
                new_kline = []
                for k in kline_data:
                    date = k.get('date', '')
                    # 统一日期格式
                    if len(date) == 8 and date.isdigit():
                        date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                    # 包含最后一根及之后的K线，确保陈旧未完成的当日bar被修正
                    if last_date is None or date >= last_date:
                        k['date'] = date
                        new_kline.append(k)
                return new_kline, None
            else:
                error = f"返回空数据(尝试{attempt+1}/{RETRY_TIMES})"
        except Exception as e:
            error = f"{type(e).__name__}: {e}(尝试{attempt+1}/{RETRY_TIMES})"

        if attempt < RETRY_TIMES - 1:
            time.sleep(0.3)

    return None, error


def _write_incremental_kline(con, code, kline_data):
    """将增量K线写入缓存(ON CONFLICT更新)"""
    if not kline_data:
        return 0

    # 按日期去重
    seen = {}
    for k in kline_data:
        date = k.get('date', '')
        if date:
            seen[date] = k

    rows = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for date, k in seen.items():
        rows.append((
            code, date,
            float(k.get('open', 0)), float(k.get('high', 0)),
            float(k.get('low', 0)), float(k.get('close', 0)),
            float(k.get('volume', 0)),
            float(k.get('amount', k.get('vol', 0)) * float(k.get('close', 0))),
            now,
        ))

    if not rows:
        return 0

    con.executemany("""
        INSERT INTO kline_cache (code, date, open, high, low, close, volume, amount, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (code, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, volume=excluded.volume, amount=excluded.amount,
            update_time=excluded.update_time
    """, rows)

    # 更新meta表
    last_date = max(seen.keys())
    total_count = con.execute("SELECT COUNT(*) FROM kline_cache WHERE code = ?", [code]).fetchone()[0]
    con.execute("""
        INSERT INTO kline_cache_meta (code, last_date, kline_count, last_update, source, update_status)
        VALUES (?, ?, ?, ?, 'pytdx_incremental', 'success')
        ON CONFLICT (code) DO UPDATE SET
            last_date=excluded.last_date, kline_count=excluded.kline_count,
            last_update=excluded.last_update, source=excluded.source,
            update_status=excluded.update_status
    """, (code, last_date, total_count, now))

    return len(rows)


def seed_today_bar(codes=None, progress_cb=None, only_in_session=True, sleep_per_batch=0.0):
    """盘中用批量实时行情把「今天的 bar」写进 K 线缓存（幂等，可重复运行）。

    为什么需要（2026-10-12 盘中实测）：日线接口是逐个代码抓的 ——
      · pytdx 服务器可连但无数据；
      · 新浪日线**不含当天未收盘 bar**（末根=上一交易日）；
      · 腾讯日线有当天 bar，但批量高频请求会被 WAF 限流（4427 只里 3242 只被打回）；
      · 东方财富连接被断。
    于是盘中缓存长期只有「上一交易日」的 bar，控盘选股/日K建仓 的数据日停在昨天。
    本函数走另一条不会被限流的通道：腾讯**批量实时行情**（qt.gtimg.cn，80 只/请求，
    全市场约 56 个请求、1 分钟内跑完），用当日快照拼出今天这根**未收盘** bar：
        open/high/low = 当日快照，close = 最新价，
        volume = 成交量(手) × 100（与缓存单位一致），amount = volume × close，
        date = 今天。
    ON CONFLICT(code, date) 直接更新；收盘后跑正规增量更新会自然覆盖成正式数据，不污染历史。
    停牌 / 当日无成交（价格或成交量为 0）的代码跳过，不写假 bar。

    Args:
        codes: 只补这些代码；None = 缓存内全部代码
        progress_cb: 可选进度回调 progress_cb(done, total, msg)
        only_in_session: True 时只在交易日 09:15~15:05 执行，其余时段直接跳过
        sleep_per_batch: 每批行情之间额外等待秒数（默认 0）

    Returns:
        dict: {ok, reason, today, requested, quotes, written, skipped_quote, before, after}
    """
    today = datetime.now().strftime('%Y-%m-%d')
    out = {'ok': False, 'reason': '', 'today': today, 'requested': 0, 'quotes': 0,
           'written': 0, 'skipped_quote': 0, 'before': 0, 'after': 0}

    if only_in_session:
        try:
            from utils.trade_calendar import is_market_open
            if not is_market_open():
                out['reason'] = '非交易时段，跳过补当日K线'
                return out
        except Exception:
            pass

    try:
        from utils.fast_realtime import get_realtime_prices_tencent
    except Exception as e:
        out['reason'] = '实时行情模块不可用: %s' % e
        return out

    if codes is None:
        codes = get_all_cached_codes()
    codes = [str(c).strip() for c in codes if str(c).strip()]
    out['requested'] = len(codes)
    if not codes:
        out['reason'] = '没有可补的代码'
        return out

    # 1) 批量取当日快照（80 只/请求）
    quotes = {}
    batch = 80
    for i in range(0, len(codes), batch):
        try:
            quotes.update(get_realtime_prices_tencent(codes[i:i + batch]) or {})
        except Exception:
            pass
        if sleep_per_batch:
            time.sleep(sleep_per_batch)
        if progress_cb:
            try:
                done = min(i + batch, len(codes))
                progress_cb(done, len(codes), '补当日K线 %d/%d' % (done, len(codes)))
            except Exception:
                pass
    out['quotes'] = len(quotes)

    # 2) 拼今天这根未收盘 bar
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows, metas = [], []
    for code in codes:
        q = quotes.get(code) or {}
        px = float(q.get('price') or 0)
        vol_lots = float(q.get('volume') or 0)
        if px <= 0 or vol_lots <= 0:          # 停牌 / 当日无成交：不写假 bar
            out['skipped_quote'] += 1
            continue
        o = float(q.get('open') or 0) or px
        h = float(q.get('high') or 0) or px
        lo = float(q.get('low') or 0) or px
        vol = vol_lots * 100.0                # 手 → 股（与缓存单位一致）
        rows.append((code, today, o, max(h, px), min(lo, px), px, vol, vol * px, now))
        metas.append(code)
    if not rows:
        out['reason'] = '没有取到有效行情，未写入'
        return out

    # 3) 落库（主程序可能正独占库文件，退避重试）
    con = None
    for attempt in range(6):
        try:
            con = get_db_connection()
            break
        except Exception as e:
            if attempt >= 5:
                out['reason'] = '数据库被占用: %s' % str(e)[:80]
                return out
            time.sleep(2.0)
    with _db_lock:
        try:
            out['before'] = con.execute(
                'SELECT COUNT(DISTINCT code) FROM kline_cache WHERE date = ?',
                [today]).fetchone()[0]
            con.executemany("""
                INSERT INTO kline_cache (code, date, open, high, low, close, volume, amount, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (code, date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                    update_time=excluded.update_time
            """, rows)
            for code in metas:
                total_count = con.execute(
                    'SELECT COUNT(*) FROM kline_cache WHERE code = ?', [code]).fetchone()[0]
                con.execute("""
                    INSERT INTO kline_cache_meta (code, last_date, kline_count, last_update, source, update_status)
                    VALUES (?, ?, ?, ?, 'realtime_seed', 'success')
                    ON CONFLICT (code) DO UPDATE SET
                        last_date=excluded.last_date, kline_count=excluded.kline_count,
                        last_update=excluded.last_update, source=excluded.source,
                        update_status=excluded.update_status
                """, (code, today, total_count, now))
            con.commit()
            out['written'] = len(rows)
            out['after'] = con.execute(
                'SELECT COUNT(DISTINCT code) FROM kline_cache WHERE date = ?',
                [today]).fetchone()[0]
            out['ok'] = True
        except Exception as e:
            try:
                con.rollback()
            except Exception:
                pass
            out['reason'] = '写库失败: %s' % str(e)[:120]
        finally:
            try:
                con.close()
            except Exception:
                pass
    return out


def _process_single_incremental(code, last_date):
    """处理单只股票增量更新"""
    new_kline, error = _fetch_incremental_kline(code, last_date)

    if new_kline is not None:
        if len(new_kline) == 0:
            return code, 0, None  # 无新数据
        with _db_lock:
            con = get_db_connection()
            try:
                count = _write_incremental_kline(con, code, new_kline)
                con.commit()
                return code, count, None
            except Exception as e:
                try:
                    con.rollback()
                except Exception:
                    pass
                return code, 0, f"DB写入失败: {e}"
            finally:
                try:
                    con.close()
                except Exception:
                    pass
    else:
        return code, 0, error


def incremental_update_kline(codes=None, max_workers=MAX_WORKERS, verbose=True):
    """
    增量更新K线：只获取缓存最后日期之后的新K线

    Args:
        codes: 股票代码列表，None表示更新缓存中所有股票
        max_workers: 并发线程数
        verbose: 是否打印进度

    Returns:
        dict: {
            'total': 总股票数,
            'updated': 有新K线的股票数,
            'no_new_data': 无新数据的股票数,
            'failed': 失败股票数,
            'new_kline_total': 新增K线总数,
            'details': {code: 新增K线数量},
            'failed_list': [{'code': ..., 'error': ...}]
        }
    """
    if codes is None:
        codes = get_all_cached_codes()

    if verbose:
        print(f"[增量更新] 开始更新 {len(codes)} 只股票...")

    # 预读取所有last_date
    last_dates = {}
    con = get_db_connection()
    try:
        for code in codes:
            row = con.execute("SELECT last_date FROM kline_cache_meta WHERE code = ?", [code]).fetchone()
            last_dates[code] = row[0] if row else None
    finally:
        con.close()

    result = {
        'total': len(codes),
        'updated': 0,
        'no_new_data': 0,
        'failed': 0,
        'new_kline_total': 0,
        'details': {},
        'failed_list': [],
    }

    start_time = time.time()
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_single_incremental, code, last_dates.get(code)): code
            for code in codes
        }

        for future in as_completed(futures):
            code, new_count, error = future.result()
            completed += 1

            if error:
                result['failed'] += 1
                result['failed_list'].append({'code': code, 'error': error})
            elif new_count > 0:
                result['updated'] += 1
                result['new_kline_total'] += new_count
                result['details'][code] = new_count
            else:
                result['no_new_data'] += 1

            if verbose and (completed % 200 == 0 or completed == len(codes)):
                elapsed = time.time() - start_time
                print(f"[增量更新] {completed}/{len(codes)} "
                      f"更新={result['updated']} 无新数据={result['no_new_data']} "
                      f"失败={result['failed']} 新增K线={result['new_kline_total']} "
                      f"耗时={elapsed:.1f}s")

    elapsed = time.time() - start_time
    if verbose:
        print(f"[增量更新] 完成! 总耗时={elapsed:.1f}s "
              f"更新={result['updated']} 无新数据={result['no_new_data']} "
              f"失败={result['failed']} 新增K线={result['new_kline_total']}")

    return result


def run_full_incremental_update():
    """运行全量增量更新(所有缓存股票)的便捷入口"""
    codes = get_all_cached_codes()
    print(f"[全量增量更新] 共 {len(codes)} 只股票需要检查")
    result = incremental_update_kline(codes)
    return result


def get_latest_kline(code, count=100):
    """
    从本地kline_cache.duckdb读取最新N根日K线（公开兜底接口）
    V2.9.2：所有在线K线源失败时的最终兜底，禁止返回空列表

    Args:
        code: 股票代码（6位，自动标准化）
        count: 获取数量，默认100

    Returns:
        list: [{'date':, 'open':, 'high':, 'low':, 'close':, 'volume':, 'amount':}, ...]
              按日期升序排列；无数据返回空列表
    """
    if not code:
        return []
    clean_code = str(code).strip()
    for prefix in ['sh', 'sz', 'bj', 'SH', 'SZ', 'BJ']:
        if clean_code.startswith(prefix):
            clean_code = clean_code[len(prefix):]
            break
    if '.' in clean_code:
        clean_code = clean_code.split('.')[0]

    try:
        con = get_db_connection()
        rows = con.execute("""
            SELECT date, open, high, low, close, volume, amount
            FROM kline_cache
            WHERE TRIM(code) = ?
            ORDER BY date DESC
            LIMIT ?
        """, (clean_code, count)).fetchall()
        con.close()

        if not rows:
            return []

        bars = []
        for row in reversed(rows):
            bars.append({
                'date': str(row[0]),
                'open': float(row[1] or 0),
                'high': float(row[2] or 0),
                'low': float(row[3] or 0),
                'close': float(row[4] or 0),
                'volume': float(row[5] or 0),
                'amount': float(row[6] or 0),
            })
        return bars
    except Exception as e:
        print(f"[K线缓存] get_latest_kline({code}) 失败: {e}", flush=True)
        return []


def get_latest_quote(code):
    """
    从本地缓存读取最新收盘价作为实时行情兜底
    V2.9.2：在线行情失败时使用

    Returns:
        dict: {'price':, 'last_close':, 'pct_chg':, 'date':, 'is_cache': True} 或 None
    """
    bars = get_latest_kline(code, count=2)
    if not bars or len(bars) < 1:
        return None
    latest = bars[-1]
    prev_close = bars[-2]['close'] if len(bars) > 1 else latest['close']
    price = latest['close']
    pct = 0.0
    if prev_close and prev_close > 0:
        pct = round((price - prev_close) / prev_close * 100, 2)
    return {
        'price': price,
        'last_close': prev_close,
        'open': latest['open'],
        'high': latest['high'],
        'low': latest['low'],
        'close': price,
        'volume': latest['volume'],
        'pct_chg': pct,
        'date': latest['date'],
        'is_cache': True,
        'data_source': 'local_cache',
    }


if __name__ == '__main__':
    # 测试：增量更新前10只股票
    test_codes = get_all_cached_codes()[:10]
    print(f"测试增量更新前10只: {test_codes}")
    result = incremental_update_kline(test_codes)
    print(f"\n结果: {result['updated']}只更新, {result['no_new_data']}只无新数据, {result['failed']}只失败")
    for code, cnt in result['details'].items():
        print(f"  {code}: +{cnt}根")
