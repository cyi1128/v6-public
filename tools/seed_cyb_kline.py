# -*- coding: utf-8 -*-
"""给本地 kline_cache.duckdb 灌创业板(300/301)日K（一次性任务）。
- 直连主库写入，主库被占用则报错退出，绝不写备用文件
- 只走 sina(0.13s) / 腾讯，失败快速跳过，并把无数据的代码记进 tools\\_cyb_nodata.txt
用法: python tools\\seed_cyb_kline.py [--workers 32] [--limit N]
"""
import os, sys, io, time, argparse, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")
DB = os.path.join(ROOT, "data", "cache", "kline_cache.duckdb")
SKIP_FILE = os.path.join(ROOT, "tools", "_cyb_nodata.txt")
KEEP_BARS, FETCH_DAYS, WORKERS = 250, 300, 32


def log(m):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), m), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--days", type=int, default=FETCH_DAYS)
    a = ap.parse_args()

    import duckdb
    try:
        con = duckdb.connect(DB, read_only=False)
        con.execute("SELECT 1 FROM kline_cache LIMIT 1")
    except Exception as e:
        log("!! 主库无法写入：%s" % str(e)[:120])
        log("!! 请先关闭 QuantMonitorV6 主程序，再重跑本脚本")
        return 2

    from utils.stock_name_manager import get_all_stock_names
    from utils.kline_fetcher import fetch_kline_sina, fetch_kline_tencent
    raw = get_all_stock_names()
    c2n = {}
    for nm, cd in raw.items():
        c2n.setdefault(cd, nm)
    cyb = {c: n for c, n in c2n.items() if str(c).startswith(("300", "301"))}
    skip = set()
    if os.path.exists(SKIP_FILE):
        skip = {x.strip() for x in io.open(SKIP_FILE, encoding="utf-8") if x.strip()}
    cyb = {c: n for c, n in cyb.items() if c not in skip}
    have = {r[0]: r[1] for r in con.execute(
        "SELECT code, COUNT(*) FROM kline_cache WHERE code LIKE '30%' GROUP BY code").fetchall()}
    todo = [c for c in cyb if have.get(c, 0) < KEEP_BARS]
    log("创业板 %d 只（跳过表 %d）；已有>=%d根 %d 只；待灌 %d 只"
        % (len(cyb), len(skip), KEEP_BARS, len(cyb) - len(todo), len(todo)))
    if a.limit:
        todo = todo[:a.limit]; log("试跑只处理 %d 只" % len(todo))
    if not todo:
        con.close(); log("没有需要处理的"); return 0

    wlock, stat, failed, t0 = threading.Lock(), {"ok": 0, "empty": 0, "fail": 0, "bars": 0}, [], time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def fetch(code):
        best = None
        for fn in (fetch_kline_sina, fetch_kline_tencent):
            try:
                kl = fn(code, days=a.days, timeout=6)
            except Exception:
                kl = None
            if kl and len(kl) >= 60:
                return kl
            if kl and len(kl) > len(best or []):
                best = kl
        return best

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch, c): c for c in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            code = futs[fu]
            try:
                kl = fu.result()
            except Exception:
                kl = None
            rows = []
            for k in (kl or []):
                d = str(k.get("date") or k.get("trade_date") or "")
                if not d:
                    continue
                if len(d) == 8 and d.isdigit():
                    d = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
                rows.append((code, d, float(k.get("open", 0) or 0), float(k.get("high", 0) or 0),
                             float(k.get("low", 0) or 0), float(k.get("close", 0) or 0),
                             float(k.get("volume", 0) or 0), float(k.get("amount", 0) or 0), now))
            if len(rows) < 60:
                stat["empty"] += 1
                failed.append(code)
            else:
                with wlock:
                    try:
                        con.executemany(
                            "INSERT INTO kline_cache VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (code,date) "
                            "DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,"
                            "close=excluded.close,volume=excluded.volume,amount=excluded.amount,"
                            "update_time=excluded.update_time", rows)
                        con.execute(
                            "INSERT INTO kline_cache_meta VALUES (?,?,?,?,?,?) ON CONFLICT (code) "
                            "DO UPDATE SET last_date=excluded.last_date,kline_count=excluded.kline_count,"
                            "last_update=excluded.last_update,source=excluded.source,"
                            "update_status=excluded.update_status",
                            [code, rows[-1][1], len(rows), now, "seed_cyb", "ok"])
                        stat["ok"] += 1; stat["bars"] += len(rows)
                    except Exception as e:
                        stat["fail"] += 1; failed.append(code)
                        log("写库失败 %s: %s" % (code, str(e)[:80]))
            if i % 50 == 0 or i == len(todo):
                el = time.time() - t0
                log("进度 %d/%d 成功%d 无数据%d 写失败%d 均%.2fs/只 预计剩余%.1f分"
                    % (i, len(todo), stat["ok"], stat["empty"], stat["fail"], el / i,
                       (len(todo) - i) * el / i / 60))
                if failed:
                    try:
                        with io.open(SKIP_FILE, "a", encoding="utf-8") as f:
                            f.write("\n".join(failed) + "\n")
                        failed.clear()
                    except Exception:
                        pass

    con.execute("CHECKPOINT"); con.close()
    log("完成：成功 %d 只 / %d 根K线 / 无数据 %d / 写失败 %d / 耗时 %.1f 分"
        % (stat["ok"], stat["bars"], stat["empty"], stat["fail"], (time.time() - t0) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
