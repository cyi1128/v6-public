# -*- coding: utf-8 -*-
"""
分钟级K线数据获取与存储模块
================================
数据源：腾讯财经 ifzq.gtimg.cn 的 5 分钟线（非 web 前缀，已验证可用）
存储  ：data/cache/minute_kline.duckdb，表 minute_kline（与日线 kline_cache 完全隔离）

表结构：
    code      VARCHAR   证券代码，如 000811
    datetime  VARCHAR   'YYYY-MM-DD HH:MM'（bar 结束时间）
    open      FLOAT
    high      FLOAT
    low       FLOAT
    close     FLOAT
    volume    FLOAT     成交量（手）
    amount    FLOAT     成交额（元）≈ typical * volume * 100

设计原则：
- 所有异常内部捕获并返回空/部分结果，绝不向上抛导致主程序崩溃；
- 免费接口历史深度有限（单次约 640 根 5 分钟 bar ≈ 14 个交易日），
  无分钟数据的交易日由回测引擎自动回退到日线近似。
"""
import os
import json
import time
import urllib.request
from datetime import datetime as _dt

import pandas as pd

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.join(_ROOT, 'data', 'cache', 'minute_kline.duckdb')
WATCHLIST_PATH = os.path.join(_ROOT, 'data', 'watchlist.json')

# 腾讯单只一次最多返回 640 根 5 分钟 bar（实测请求更多会回退到 320）
TX_M5_COUNT = 640


def tencent_symbol(code: str) -> str:
    """6 开头 -> 上交所 sh，其余 -> 深交所 sz"""
    code = str(code).zfill(6)
    return ('sh' if code.startswith('6') else 'sz') + code


def _http_get(url: str, timeout: int = 15, retries: int = 3) -> str:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8', 'ignore')
        except Exception as e:  # noqa
            last = e
            time.sleep(0.6 * (i + 1))
    raise last if last else RuntimeError('http_get failed')


def fetch_minute_5m(code: str, count: int = TX_M5_COUNT) -> pd.DataFrame:
    """
    拉取单只股票 5 分钟线。
    返回 DataFrame[code, datetime, open, high, low, close, volume, amount]，失败返回空表。
    腾讯字段顺序：[时间, 开, 收, 高, 低, 量(手), {}, 涨跌]
    """
    cols = ['code', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']
    empty = pd.DataFrame(columns=cols)
    try:
        sym = tencent_symbol(code)
        url = f"http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={sym},m5,,{count}"
        j = json.loads(_http_get(url))
        node = j['data'][sym]['m5']
        rows = []
        for rec in node:
            # rec: ['202609151500','36.34','36.33','36.34','36.29','5107.0',{},'5.22']
            tstr = rec[0]              # YYYYMMDDHHMM
            o, c, h, l = float(rec[1]), float(rec[2]), float(rec[3]), float(rec[4])
            vol = float(rec[5])        # 手
            typical = (h + l + c) / 3.0
            amount = typical * vol * 100.0   # 元
            # 转 'YYYY-MM-DD HH:MM'
            dt = f"{tstr[0:4]}-{tstr[4:6]}-{tstr[6:8]} {tstr[8:10]}:{tstr[10:12]}"
            rows.append([str(code).zfill(6), dt, o, h, l, c, vol, amount])
        if not rows:
            return empty
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:  # noqa
        print(f"[minute_kline] fetch {code} failed: {type(e).__name__}: {e}")
        return empty


def _ensure_table(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS minute_kline ("
        " code VARCHAR, datetime VARCHAR, open FLOAT, high FLOAT, low FLOAT,"
        " close FLOAT, volume FLOAT, amount FLOAT)"
    )


def upsert_minute(df: pd.DataFrame, db_path: str = STORE_PATH) -> int:
    """整只股票先删后插（幂等）。返回写入条数。失败返回 0。"""
    if duckdb is None or df is None or df.empty:
        return 0
    try:
        con = duckdb.connect(db_path)
        try:
            _ensure_table(con)
            codes = df['code'].unique().tolist()
            for c in codes:
                con.execute("DELETE FROM minute_kline WHERE code=?", [c])
            con.register('_mk_df', df)
            con.execute("INSERT INTO minute_kline SELECT * FROM _mk_df")
            con.unregister('_mk_df')
            con.execute("CREATE INDEX IF NOT EXISTS idx_mk_code_dt ON minute_kline(code, datetime)")
            return int(len(df))
        finally:
            con.close()
    except Exception as e:  # noqa
        print(f"[minute_kline] upsert failed: {type(e).__name__}: {e}")
        return 0


def load_watchlist_codes():
    try:
        with open(WATCHLIST_PATH, encoding='utf-8') as f:
            return [d.get('code', '').zfill(6) for d in json.load(f) if d.get('code')]
    except Exception:
        return []


def download_all(codes=None, progress_cb=None, log_cb=None):
    """
    下载自选股 5 分钟线并入 DuckDB。
    progress_cb(done, total, code)：进度回调
    log_cb(msg)：日志回调
    返回 dict 统计。
    """
    codes = codes or load_watchlist_codes()
    stats = dict(n_stock=0, total_rows=0, per_stock={}, date_min=None, date_max=None)
    if not codes:
        (log_cb or print)("[minute_kline] 自选股为空，跳过下载")
        return stats

    for i, code in enumerate(codes):
        df = fetch_minute_5m(code)
        n = 0
        days = 0
        if not df.empty:
            n = upsert_minute(df)
            days = df['datetime'].str.slice(0, 10).nunique()
        stats['per_stock'][code] = dict(rows=n, days=days)
        if n > 0:
            stats['n_stock'] += 1
            stats['total_rows'] += n
            dmin = df['datetime'].min()[:10]
            dmax = df['datetime'].max()[:10]
            stats['date_min'] = dmin if stats['date_min'] is None else min(stats['date_min'], dmin)
            stats['date_max'] = dmax if stats['date_max'] is None else max(stats['date_max'], dmax)
        (log_cb or print)(f"[minute_kline] {code}: {n} 条 / {days} 个交易日")
        if progress_cb:
            progress_cb(i + 1, len(codes), code)
        time.sleep(0.3)  # 礼貌限速
    (log_cb or print)(
        f"[minute_kline] 完成：{stats['n_stock']} 只 / {stats['total_rows']} 条 / "
        f"{stats['date_min']} ~ {stats['date_max']}")
    return stats


def get_coverage_stats(db_path: str = STORE_PATH):
    """
    查询 minute_kline.duckdb 的整体覆盖范围（read_only）。
    返回 dict: {date_min, date_max, n_days, n_stock, total_rows}
    数据库不存在 / 查询失败 / 无数据时，对应字段为 None 或 0，绝不抛异常。
    """
    empty = dict(date_min=None, date_max=None, n_days=0, n_stock=0, total_rows=0)
    if duckdb is None:
        return empty
    if not os.path.exists(db_path):
        return empty
    try:
        con = duckdb.connect(db_path, read_only=True)
        try:
            row = con.execute(
                "SELECT MIN(datetime), MAX(datetime), "
                " COUNT(DISTINCT substr(datetime,1,10)), "
                " COUNT(DISTINCT code), COUNT(*) "
                "FROM minute_kline"
            ).fetchone()
            if not row or row[0] is None:
                return empty
            dmin = str(row[0])[:10]
            dmax = str(row[1])[:10]
            return dict(date_min=dmin, date_max=dmax,
                        n_days=int(row[2] or 0),
                        n_stock=int(row[3] or 0),
                        total_rows=int(row[4] or 0))
        finally:
            con.close()
    except Exception as e:  # noqa
        print(f"[minute_kline] get_coverage_stats failed: {type(e).__name__}: {e}")
        return empty


def load_day_vwap(code: str, start_date: str, end_date: str, db_path: str = STORE_PATH):
    """
    从 minute_kline 计算每只股票每个交易日的【当日 VWAP】（当日 5 分钟 bar 累计）。
    VWAP = Σ(典型价 * 成交量) / Σ(成交量)，每日开盘从 0 累加。
    返回 dict: { 'YYYY-MM-DD': vwap_float }；无数据/失败返回空 dict。
    """
    if duckdb is None:
        return {}
    if not os.path.exists(db_path):
        return {}
    try:
        con = duckdb.connect(db_path, read_only=True)
        try:
            q = (
                "SELECT substr(datetime,1,10) AS d, "
                " SUM((high+low+close)/3.0 * volume) / NULLIF(SUM(volume),0) AS vwap "
                "FROM minute_kline WHERE code=? AND substr(datetime,1,10)>=? "
                " AND substr(datetime,1,10)<=? GROUP BY d ORDER BY d"
            )
            rows = con.execute(q, [str(code).zfill(6), start_date, end_date]).fetchall()
            return {r[0]: (float(r[1]) if r[1] is not None else None) for r in rows}
        finally:
            con.close()
    except Exception as e:  # noqa
        print(f"[minute_kline] load_day_vwap {code} failed: {type(e).__name__}: {e}")
        return {}


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    st = download_all()
    print("\n=== 下载统计 ===")
    print(json.dumps(st, ensure_ascii=False, indent=2))
