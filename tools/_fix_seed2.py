# -*- coding: utf-8 -*-
import io, sys
sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\tools\seed_cyb_kline.py"
s = io.open(P, encoding="utf-8", newline="").read()

# 1) 抓取只走 sina/tencent，快速失败；不碰 pytdx/eastmoney（两只都慢且对创业板常无数据）
old = """    def _fetch_one(code):
        # sina 0.13s/只（实测），最稳最快；失败再走腾讯 / 完整链路
        for fn in (fetch_kline_sina, fetch_kline_tencent, fetch_kline):
            try:
                kl = fn(code, days=a.days)
            except Exception:
                kl = None
            if kl and len(kl) >= 60:
                return kl
        return None"""
new = """    def _fetch_one(code):
        # 只走 sina / 腾讯：实测 0.13s/只，失败也快速返回。
        # 不走 pytdx（对创业板常无数据，每次白等超时）和东财（当前网络必失败）。
        for fn in (fetch_kline_sina, fetch_kline_tencent):
            try:
                kl = fn(code, days=a.days, timeout=6)
            except TypeError:
                try:
                    kl = fn(code, days=a.days)
                except Exception:
                    kl = None
            except Exception:
                kl = None
            if kl and len(kl) >= 60:
                return kl
        return None"""
assert s.count(old) == 1, "锚点1"
s = s.replace(old, new, 1)

s = s.replace("WORKERS = 12", "WORKERS = 16", 1)

# 2) 已知无数据的代码记录到跳过文件
old2 = """    cyb = get_cyb_codes()
    log("创业板代码总数: %d" % len(cyb))"""
new2 = """    SKIP_FILE = os.path.join(ROOT, "tools", "_cyb_nodata.txt")
    skip = set()
    if os.path.exists(SKIP_FILE):
        skip = {x.strip() for x in io.open(SKIP_FILE, encoding="utf-8") if x.strip()}
    cyb = get_cyb_codes()
    if skip:
        cyb = {c: n for c, n in cyb.items() if c not in skip}
    log("创业板代码总数: %d（已知无数据跳过 %d）" % (len(cyb), len(skip)))"""
assert s.count(old2) == 1, "锚点2"
s = s.replace(old2, new2, 1)

# 记录无数据
old3 = """            if i % 50 == 0 or i == len(todo):"""
new3 = """            if i % 100 == 0 or i == len(todo):"""
assert s.count(old3) == 1
s = s.replace(old3, new3, 1)

old4 = """    if failed:
        log("失败样例(前20): %s" % failed[:20])"""
new4 = """    if failed:
        log("失败样例(前20): %s" % failed[:20])
        try:
            with io.open(SKIP_FILE, "a", encoding="utf-8") as f:
                for c in failed:
                    f.write(c + "\\n")
            log("已记入跳过表 %s（共 %d 只）" % (SKIP_FILE, len(failed)))
        except Exception as e:
            log("写跳过表失败: %s" % e)"""
assert s.count(old4) == 1, "锚点4"
s = s.replace(old4, new4, 1)

# 需要 io
s = s.replace("import os, sys, time, argparse, threading",
              "import os, sys, io, time, argparse, threading", 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK 已改为快速失败版（sina/腾讯，16 并发，跳过表）")
