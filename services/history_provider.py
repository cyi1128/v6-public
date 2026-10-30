# -*- coding: utf-8 -*-
"""
历史分钟数据适配层（双轨架构之"长期历史库"）
================================
对外暴露：
    get_history_minute(code, start_date, end_date, frequency='5m') -> pd.DataFrame
    get_history_coverage() -> dict   # 供 UI 展示历史扩展数据库范围

数据优先级（2026-09-16 重构，接入本地通达信数据）：
    1. 本地 duckdb 缓存：data/cache/minute_kline.duckdb（read_only=True）
    2. 本地通达信分钟文件：C:\\new_tdx\\vipdoc\\{sz,sh}\\fzline\\*.lc5（5分钟）
       和 minline\\*.lc1（1分钟），通过 mootdx 读取
    3. 本地通达信日线文件：C:\\new_tdx\\vipdoc\\{sz,sh}\\lday\\*.day（mootdx 读取）
       —— 当分钟线缺失时，日线可作为"粗粒度历史"降级返回（列结构对齐）
    4. 远端降级：腾讯财经 ifzq（现有 _mk.fetch_minute_5m，约 17 个交易日）
       并增量写回 minute_kline.duckdb 作为缓存

所有外部依赖均包 try/except，未安装/接口失败时优雅回退，绝不抛出到主程序。
"""
import os
import struct
from datetime import datetime as _dt

import pandas as pd

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:
    from services import minute_kline as _mk
except Exception:  # pragma: no cover
    _mk = None

# —— mootdx：本地通达信数据读取 ——
try:
    from mootdx.reader import Reader as _MootdxReader  # type: ignore
except Exception as _e:  # noqa
    _MootdxReader = None
    _MOOTDX_IMPORT_ERR = _e
else:
    _MOOTDX_IMPORT_ERR = None

# —— free-stockdb 可选依赖（保留旧分支，默认未安装）——
try:
    import free_stockdb as _fsdb  # type: ignore
except Exception as _e:  # noqa
    _fsdb = None
    _FSDB_IMPORT_ERR = _e
else:
    _FSDB_IMPORT_ERR = None

# —— BaoStock 可选依赖（远端历史补齐，当前未安装）——
try:
    import baostock as _bs  # type: ignore
except Exception as _e:  # noqa
    _bs = None
    _BS_IMPORT_ERR = _e
else:
    _BS_IMPORT_ERR = None


_COLS = ['code', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'amount']

# 本机通达信安装路径（自动探测常见位置）
_TDX_CANDIDATES = [
    r"C:\new_tdx", r"D:\new_tdx",
    r"C:\zd_ztzq", r"D:\zd_ztzq",
    r"C:\通达信", r"D:\通达信",
]


def _detect_tdx_dir() -> str:
    """找到本机含 vipdoc 目录的通达信根路径；找不到返回空串。"""
    for p in _TDX_CANDIDATES:
        if os.path.isdir(os.path.join(p, "vipdoc")):
            return p
    return ""


_TDX_DIR = _detect_tdx_dir()


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLS)


def _tdx_market_dir(code: str) -> str:
    """6 开头 -> sh，其余 -> sz"""
    code = str(code).zfill(6)
    return "sh" if code.startswith("6") else "sz"


# ============================================================
# 优先级 1：本地 duckdb 缓存（read_only）
# ============================================================
def _read_local_cache(code: str, start_date: str, end_date: str,
                      db_path: str = None) -> pd.DataFrame:
    if _mk is not None:
        db_path = db_path or getattr(_mk, 'STORE_PATH', None)
    if db_path is None or duckdb is None:
        return _empty_df()
    if not os.path.exists(db_path):
        return _empty_df()
    try:
        con = duckdb.connect(db_path, read_only=True)
        try:
            df = con.execute(
                "SELECT code, datetime, open, high, low, close, volume, amount "
                "FROM minute_kline WHERE code=? "
                " AND substr(datetime,1,10)>=? AND substr(datetime,1,10)<=? "
                "ORDER BY datetime",
                [str(code).zfill(6), start_date, end_date],
            ).df()
        finally:
            con.close()
        if df is None or df.empty:
            return _empty_df()
        df = df[_COLS].reset_index(drop=True)
        return df
    except Exception as e:  # noqa
        print(f"[history_provider] local cache read {code} failed: {type(e).__name__}: {e}")
        return _empty_df()


# ============================================================
# 优先级 2：本地通达信分钟文件（.lc5=5分钟 / .lc1=1分钟）
# ============================================================
def _read_local_tdx_minute(code: str, start_date: str, end_date: str,
                           frequency: str = "5m") -> pd.DataFrame:
    """
    直接解析本机通达信 fzline/minline 目录下的 .lc5/.lc1 二进制文件。
    若 mootdx 可用则用 mootdx.Reader；否则手写二进制解析兜底。
    frequency: '5m' -> .lc5 (fzline), '1m' -> .lc1 (minline)
    """
    code = str(code).zfill(6)
    if not _TDX_DIR:
        return _empty_df()

    market = _tdx_market_dir(code)
    if frequency == "5m":
        sub_dir, ext = "fzline", ".lc5"
    else:
        sub_dir, ext = "minline", ".lc1"

    fname = f"{market}{code}{ext}"
    fpath = os.path.join(_TDX_DIR, "vipdoc", market, sub_dir, fname)
    if not os.path.exists(fpath):
        return _empty_df()

    # —— 优先用 mootdx ——
    if _MootdxReader is not None:
        try:
            reader = _MootdxReader.factory(market='std', tdxdir=_TDX_DIR)
            if frequency == "5m":
                df = reader.fzline(symbol=code)   # 5分钟
            else:
                df = reader.minute(symbol=code)    # 1分钟
            if df is None or df.empty:
                return _empty_df()
            # mootdx 返回 DataFrame，index 是 datetime
            df = df.copy()
            df = df.reset_index().rename(columns={df.index.name or 'index': 'datetime'})
            if 'datetime' not in df.columns:
                df.columns = ['datetime'] + list(df.columns[1:])
            df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
            df = df.dropna(subset=['datetime'])
            # 列名对齐
            rename = {}
            for c in df.columns:
                cl = str(c).lower()
                if cl in ('open', 'high', 'low', 'close'):
                    rename[c] = cl
                elif cl in ('vol', 'volume', 'volum'):
                    rename[c] = 'volume'
                elif cl == 'amount':
                    rename[c] = 'amount'
            df = df.rename(columns=rename)
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            # 过滤日期区间
            df = df[(df['datetime'].dt.strftime('%Y-%m-%d') >= start_date) &
                    (df['datetime'].dt.strftime('%Y-%m-%d') <= end_date)]
            df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M')
            df['code'] = code
            if 'amount' not in df.columns or df['amount'].isna().all():
                typical = (df['high'] + df['low'] + df['close']) / 3.0
                df['amount'] = typical * df['volume'] * 100.0
            return df[_COLS].sort_values('datetime').reset_index(drop=True)
        except Exception as e:  # noqa
            print(f"[history_provider] mootdx minute {code} failed: {type(e).__name__}: {e}")
            return _empty_df()

    # —— 手写二进制解析兜底（通达信 .lc5/.lc1 格式，每条32字节）——
    try:
        rows = []
        with open(fpath, 'rb') as f:
            buf = f.read()
        rec_size = 32
        for off in range(0, len(buf) - rec_size + 1, rec_size):
            chunk = buf[off:off + rec_size]
            # 前2字节: 日期 = (year-2004)*2048 + month*100 + day  （通达信1分钟格式）
            # 5分钟线格式：前4字节为 int32 YYYYMMDDHHMM 风格
            date_int, time_int = struct.unpack('<HH', chunk[0:4])
            # 通达信 .lc5/.lc1 日期编码：((year-2004)<<11) + (month<<7) + day
            y = (date_int >> 11) + 2004
            m = (date_int >> 7) & 0x0F
            d = date_int & 0x7F
            # time_int: 分钟数（从0开始）或 HHMM
            if time_int > 2000:
                hh = time_int // 100
                mm = time_int % 100
            else:
                # 分钟数从 09:30 起算
                total_min = int(time_int)
                hh = (total_min // 60) + 9
                mm = (total_min % 60) + 30
                if mm >= 60:
                    mm -= 60
                    hh += 1
            o, h, l, c, amt = struct.unpack('<fffff', chunk[4:24])
            vol = struct.unpack('<I', chunk[24:28])[0]
            rows.append((f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}",
                         o, h, l, c, float(vol), amt))
        if not rows:
            return _empty_df()
        df = pd.DataFrame(rows, columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
        df = df.dropna(subset=['datetime'])
        df = df[(df['datetime'].dt.strftime('%Y-%m-%d') >= start_date) &
                (df['datetime'].dt.strftime('%Y-%m-%d') <= end_date)]
        df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M')
        df['code'] = code
        return df[_COLS].sort_values('datetime').reset_index(drop=True)
    except Exception as e:  # noqa
        print(f"[history_provider] raw lc5 parse {code} failed: {type(e).__name__}: {e}")
        return _empty_df()


# ============================================================
# 优先级 3：本地通达信日线（.day 文件，mootdx 读取）
# ============================================================
def _read_local_tdx_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    读本机通达信日线 .day 文件。作为分钟线缺失时的粗粒度历史补充。
    返回的 DataFrame 列结构与 _COLS 对齐（datetime 仅到日）。
    """
    code = str(code).zfill(6)
    if not _TDX_DIR or _MootdxReader is None:
        return _empty_df()
    try:
        reader = _MootdxReader.factory(market='std', tdxdir=_TDX_DIR)
        df = reader.daily(symbol=code)
        if df is None or df.empty:
            return _empty_df()
        df = df.copy()
        df = df.reset_index()
        df.columns = ['datetime' if 'index' in str(c).lower() or str(c) == 'datetime' else str(c).lower()
                      for c in df.columns]
        if 'datetime' not in df.columns:
            df.columns = ['datetime'] + list(df.columns[1:])
        df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
        df = df.dropna(subset=['datetime'])
        df = df[(df['datetime'].dt.strftime('%Y-%m-%d') >= start_date) &
                (df['datetime'].dt.strftime('%Y-%m-%d') <= end_date)]
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        # volume 单位：通达信 .day 是"手"，统一为"手"与 duckdb 对齐
        df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d 15:00')
        df['code'] = code
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        if 'amount' not in df.columns:
            typical = (df['high'] + df['low'] + df['close']) / 3.0
            df['amount'] = typical * df['volume'] * 100.0
        return df[_COLS].sort_values('datetime').reset_index(drop=True)
    except Exception as e:  # noqa
        print(f"[history_provider] local tdx daily {code} failed: {type(e).__name__}: {e}")
        return _empty_df()


# ============================================================
# 优先级 4：远端腾讯（现有 _mk.fetch_minute_5m，约 17 个交易日）
# ============================================================
def _read_remote_tencent(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    if _mk is None:
        return _empty_df()
    try:
        df = _mk.fetch_minute_5m(code)
        if df is None or df.empty:
            return _empty_df()
        df = df[df['datetime'].str.slice(0, 10) >= start_date]
        df = df[df['datetime'].str.slice(0, 10) <= end_date]
        return df.reset_index(drop=True)
    except Exception as e:  # noqa
        print(f"[history_provider] tencent fallback {code} failed: {type(e).__name__}: {e}")
        return _empty_df()


# ============================================================
# 对外主入口
# ============================================================
def get_history_minute(code: str, start_date: str, end_date: str,
                       frequency: str = "5m",
                       allow_remote: bool = True) -> pd.DataFrame:
    """
    按优先级获取区间内分钟线：
        1. 本地 minute_kline.duckdb（read_only）
        2. 本地通达信分钟文件（.lc5/.lc1，mootdx 读取）
        3. 远端腾讯财经（约 17 个交易日），写回 duckdb
        4. 本地通达信日线（.day）—— 粗粒度降级，datetime 仅到日

    返回 DataFrame[code, datetime, open, high, low, close, volume, amount]；
    无数据时返回空表（列结构与 _COLS 一致），绝不抛异常。
    """
    code = str(code).zfill(6)

    # —— 优先级 1：本地 duckdb ——
    df_local = _read_local_cache(code, start_date, end_date)
    if not df_local.empty:
        return df_local

    # —— 优先级 2：本地通达信分钟文件 ——
    df_tdx_min = _read_local_tdx_minute(code, start_date, end_date, frequency)
    if not df_tdx_min.empty:
        try:
            if _mk is not None:
                _mk.upsert_minute_incremental(df_tdx_min)
        except Exception as e:  # noqa
            print(f"[history_provider] writeback tdx minute failed: {e}")
        return df_tdx_min

    # —— 优先级 3：远端腾讯 ——
    if allow_remote:
        df_remote = _read_remote_tencent(code, start_date, end_date)
        if not df_remote.empty:
            try:
                if _mk is not None:
                    _mk.upsert_minute_incremental(df_remote)
            except Exception as e:  # noqa
                print(f"[history_provider] writeback remote failed: {e}")
            return df_remote

    # —— 优先级 4：本地通达信日线降级 ——
    df_daily = _read_local_tdx_daily(code, start_date, end_date)
    if not df_daily.empty:
        return df_daily

    return _empty_df()


# ============================================================
# 供 UI 展示的历史数据覆盖范围
# ============================================================
def _scan_tdx_minute_files() -> dict:
    """扫描本地通达信 fzline/minline 目录，统计分钟文件覆盖。"""
    info = dict(tdx_dir=_TDX_DIR, has_minute=False, n_5m_files=0, n_1m_files=0,
                sample_5m_date=None)
    if not _TDX_DIR:
        return info
    for sub, key in [("fzline", "n_5m_files"), ("minline", "n_1m_files")]:
        for market in ("sz", "sh"):
            d = os.path.join(_TDX_DIR, "vipdoc", market, sub)
            if os.path.isdir(d):
                try:
                    files = [f for f in os.listdir(d) if f.endswith((".lc5", ".lc1"))]
                    info[key] += len(files)
                except Exception:
                    pass
    info["has_minute"] = (info["n_5m_files"] > 0 or info["n_1m_files"] > 0)
    return info


def get_history_coverage() -> dict:
    """
    返回历史数据覆盖范围（供 UI 显示）：
      - minute_duckdb: 本地 duckdb 分钟线覆盖
      - tdx_local: 本机通达信数据状态（日线文件数 + 分钟文件数）
      - remote: 远端腾讯可用状态
    """
    base = dict(
        available=False,
        date_min=None, date_max=None, n_days=0,
        source="local-tdx+tencent",
        tdx_dir=_TDX_DIR or None,
        tdx_daily_files=0,
        tdx_5m_files=0,
        tdx_1m_files=0,
        duckdb_minutes=None,
        note="",
    )

    # —— 本地 duckdb 分钟线覆盖 ——
    try:
        if _mk is not None:
            cov = _mk.get_coverage_stats()
            base["duckdb_minutes"] = cov
            if cov and cov.get("date_min") and cov.get("date_max"):
                base["available"] = True
                base["date_min"] = cov["date_min"]
                base["date_max"] = cov["date_max"]
                base["n_days"] = cov.get("n_days", 0)
    except Exception as e:  # noqa
        base["note"] = f"duckdb查询失败: {e}"

    # —— 本地通达信日线/分钟文件统计 ——
    if _TDX_DIR:
        try:
            # 日线文件数
            daily_count = 0
            for market in ("sz", "sh"):
                d = os.path.join(_TDX_DIR, "vipdoc", market, "lday")
                if os.path.isdir(d):
                    daily_count += len([f for f in os.listdir(d) if f.endswith(".day")])
            base["tdx_daily_files"] = daily_count

            # 分钟文件统计
            minute_info = _scan_tdx_minute_files()
            base["tdx_5m_files"] = minute_info["n_5m_files"]
            base["tdx_1m_files"] = minute_info["n_1m_files"]

            # 抽样一只股票的日线最早/最新（取 002838）
            if _MootdxReader is not None and daily_count > 0:
                try:
                    reader = _MootdxReader.factory(market='std', tdxdir=_TDX_DIR)
                    df = reader.daily(symbol='002838')
                    if df is not None and len(df):
                        dmin = str(df.index[0])[:10]
                        dmax = str(df.index[-1])[:10]
                        base["tdx_daily_min"] = dmin
                        base["tdx_daily_max"] = dmax
                        base["tdx_daily_rows_002838"] = len(df)
                except Exception:
                    pass
        except Exception as e:  # noqa
            base["note"] = (base["note"] + f"; tdx扫描失败: {e}").strip("; ")

    # —— mootdx/腾讯 可用性 ——
    base["mootdx_available"] = (_MootdxReader is not None)
    base["tencent_available"] = (_mk is not None)

    return base


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print('=== history_provider self-test ===')
    print('TDX_DIR:', _TDX_DIR or 'NOT FOUND')
    print('mootdx:', 'installed' if _MootdxReader else f'NOT installed ({_MOOTDX_IMPORT_ERR})')
    print('duckdb:', 'installed' if duckdb else 'NOT installed')
    print()
    print('--- get_history_coverage() ---')
    cov = get_history_coverage()
    for k, v in cov.items():
        print(f'  {k}: {v}')
    print()
    print('--- get_history_minute(002838, 2026-03-16, 2026-09-16) ---')
    df = get_history_minute('002838', '2026-03-16', '2026-09-16')
    print(f'rows: {len(df)}, cols: {list(df.columns)}')
    if not df.empty:
        print(f'范围: {df["datetime"].iloc[0]} ~ {df["datetime"].iloc[-1]}')
        print(df.head(3))
        print('...')
        print(df.tail(3))
