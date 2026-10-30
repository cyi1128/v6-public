# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from utils.kline_fetcher import fetch_kline, fetch_kline_sina, fetch_kline_tencent, fetch_kline_eastmoney
for name, fn in [("sina", fetch_kline_sina), ("tencent", fetch_kline_tencent),
                 ("eastmoney", fetch_kline_eastmoney), ("fetch_kline(带pytdx)", fetch_kline)]:
    t = time.time(); kl = fn("300004", days=300); dt = time.time() - t
    print("%-20s %6.2fs  返回 %4d 根  %s" % (name, dt, len(kl or []),
          (kl[-1].get("date"), kl[-1].get("close")) if kl else None))
# 再测 3 只 sina 的均速
t0 = time.time()
for c in ["300005", "300006", "300007"]:
    kl = fetch_kline_sina(c, days=300)
    print("   %s -> %d 根" % (c, len(kl or [])))
print("sina 3 只串行耗时 %.2fs (均 %.2fs/只)" % (time.time()-t0, (time.time()-t0)/3))
