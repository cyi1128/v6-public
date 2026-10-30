# -*- coding: utf-8 -*-
import io, sys
sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\tools\seed_cyb_kline.py"
s = io.open(P, encoding="utf-8", newline="").read()

old = """    from utils.kline_fetcher import fetch_kline
    wlock = threading.Lock()"""
new = """    from utils.kline_fetcher import fetch_kline_sina, fetch_kline_tencent, fetch_kline
    wlock = threading.Lock()

    def _fetch_one(code):
        # sina 0.13s/只（实测），最稳最快；失败再走腾讯 / 完整链路
        for fn in (fetch_kline_sina, fetch_kline_tencent, fetch_kline):
            try:
                kl = fn(code, days=a.days)
            except Exception:
                kl = None
            if kl and len(kl) >= 60:
                return kl
        return None"""
assert s.count(old) == 1, "锚点1 %d" % s.count(old)
s = s.replace(old, new, 1)

old2 = """    def work(code):
        try:
            return code, fetch_kline(code, days=a.days)
        except Exception as e:
            return code, None"""
new2 = """    def work(code):
        try:
            return code, _fetch_one(code)
        except Exception:
            return code, None"""
assert s.count(old2) == 1, "锚点2 %d" % s.count(old2)
s = s.replace(old2, new2, 1)

old3 = "WORKERS = 6"
new3 = "WORKERS = 12"
assert s.count(old3) == 1
s = s.replace(old3, new3, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK 已改为 sina 优先 + 12 并发")
