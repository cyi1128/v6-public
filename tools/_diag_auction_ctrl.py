# -*- coding: utf-8 -*-
"""
诊断：竞价模块的「控盘」列到底是一个都不符合，还是数据异常。

走的就是 UI 同一条路：services.control_profile.compute_one / get_ctrl_map。

三类样本分别测：
  A. 今日竞价快照里的真实代码（data\intraday_snapshots\*.json 的 auction.rows）
  B. 竞价追踪库里的真实代码（data\cache\auction_tracking.duckdb）
  C. 对照组：kline_cache 里随机 200 只（看整体能不能算出分）

对每个样本统计：
  有K线(>=60根) / 算得出分 / 命中提示(85阈值) / 没数据(--)
并把分数分布打出来，判断是「没数据」还是「阈值太严」。
"""
import glob
import json
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

KLINE_DB = os.path.join(ROOT, "data", "cache", "kline_cache.duckdb")
AUCTION_DB = os.path.join(ROOT, "data", "cache", "auction_tracking.duckdb")
SNAP_DIR = os.path.join(ROOT, "data", "intraday_snapshots")


def bars_count_map():
    con = duckdb.connect(KLINE_DB, read_only=True)
    d = {}
    for c, n in con.execute(
            "SELECT code, COUNT(*) FROM kline_cache GROUP BY code").fetchall():
        d[str(c)] = int(n)
    last = con.execute("SELECT MAX(date) FROM kline_cache").fetchone()[0]
    con.close()
    return d, last


def section(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


BARS, LAST_DATE = bars_count_map()
print("kline_cache 最新日期：%s ｜ 覆盖 %d 只" % (LAST_DATE, len(BARS)))


def probe(label, codes):
    codes = [str(c) for c in dict.fromkeys(codes) if c]
    print()
    print("--- %s ---" % label)
    print("  代码数：%d" % len(codes))
    if not codes:
        print("  （空，跳过）")
        return
    no_bars = [c for c in codes if BARS.get(c, 0) < 60]
    print("  kline_cache 里不足 60 根K线的：%d 只（这些必然显示 --）" % len(no_bars))
    if no_bars[:10]:
        print("    例：%s" % " ".join(
            "%s(%d根)" % (c, BARS.get(c, 0)) for c in no_bars[:10]))

    from services.control_profile import compute_one
    ok = tip = 0
    scores = []
    fails = []
    for c in codes:
        info = compute_one(c)
        if info.get("ok") and info.get("score") is not None:
            ok += 1
            scores.append(float(info["score"]))
            if info.get("tip"):
                tip += 1
        else:
            fails.append(c)
    print("  算得出分：%d / %d  （显示灰色分数）" % (ok, len(codes)))
    print("  命中提示（有颜色/文字）：%d / %d" % (tip, len(codes)))
    print("  完全没数据（显示 --）：%d" % len(fails))
    if fails[:10]:
        print("    例：%s" % " ".join(fails[:10]))
    if scores:
        scores.sort()
        n = len(scores)
        print("  控盘分：min %.1f  25%% %.1f  中位 %.1f  75%% %.1f  max %.1f  均值 %.1f"
              % (scores[0], scores[int(n * .25)], scores[n // 2],
                 scores[int(n * .75)], scores[-1], sum(scores) / n))
        for th in (60, 70, 75, 80, 85, 90):
            k = sum(1 for s in scores if s >= th)
            print("    >= %d 分：%d 只（%.1f%%）" % (th, k, k / n * 100.0))
    return ok, tip, len(fails)


# ---------------- A. 今日竞价快照 ----------------
section("A. 今日竞价：data\\intraday_snapshots 里最新的 auction.rows")
snaps = sorted(glob.glob(os.path.join(SNAP_DIR, "*.json")))
print("快照文件共 %d 个" % len(snaps))
auction_codes = []
if snaps:
    for p in snaps[-3:][::-1]:
        try:
            doc = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print("  %s 读取失败: %s" % (os.path.basename(p), e))
            continue
        au = doc.get("auction") or {}
        rows = au.get("rows") or []
        print("  %s：auction.rows = %d 条，saved_at=%s"
              % (os.path.basename(p), len(rows), au.get("saved_at")))
        if rows and not auction_codes:
            auction_codes = [r.get("code") for r in rows]
            print("    首行 keys：%s" % sorted(list(rows[0].keys()))[:14])
probe("A. 今日竞价快照里的股票", auction_codes)

# ---------------- B. 竞价追踪库 ----------------
section("B. 竞价追踪：data\\cache\\auction_tracking.duckdb")
track_codes = []
if os.path.exists(AUCTION_DB):
    con = duckdb.connect(AUCTION_DB, read_only=True)
    try:
        tbs = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables").fetchall()]
        print("表：%s" % tbs)
        for t in tbs:
            try:
                cols = [r[1] for r in con.execute(
                    'PRAGMA table_info("%s")' % t).fetchall()]
                n = con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                print("  %s：%d 行，列 %s" % (t, n, cols[:12]))
                if "code" in cols and n:
                    track_codes += [r[0] for r in con.execute(
                        'SELECT DISTINCT code FROM "%s"' % t).fetchall()]
            except Exception as e:
                print("  %s 读取失败: %s" % (t, e))
    finally:
        con.close()
else:
    print("  库不存在")
probe("B. 竞价追踪库里的股票", track_codes)

# ---------------- C. 对照组 ----------------
section("C. 对照组：kline_cache 里随机 200 只（>=60根）")
pool = [c for c, n in BARS.items() if n >= 60]
random.seed(7)
probe("C. 随机 200 只", random.sample(pool, min(200, len(pool))))

section("结论指引")
print("如果 A/B 的『算得出分』≈ 0 而 C 正常 → 竞价的代码不在本地K线缓存（数据问题，不是阈值问题）")
print("如果 A/B 也算得出分、只是『命中提示』= 0 → 是 85/90 阈值太严（不是数据异常）")
print("如果 A/B 命中提示的比例和 C 差不多 → 竞价模块的控盘列本身就是正常的")
