# -*- coding: utf-8 -*-
"""综合测试：腾讯分钟线 + 东财分钟线(最近日期)"""
import sys, io, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib.request

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')

# ---- 腾讯 5分钟线 ----
print("=== TENCENT m5 ===")
try:
    url = "http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000811,m5,,640"
    t0 = time.time()
    raw = http_get(url)
    j = json.loads(raw)
    node = j['data']['sz000811']['m5']
    print("rows:", len(node), "elapsed:", round(time.time()-t0,1))
    print("first:", node[0])
    print("last :", node[-1])
except Exception as e:
    print("ERROR:", type(e).__name__, e)

# ---- 腾讯 1分钟线 ----
print("\n=== TENCENT m1 ===")
try:
    url = "http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000811,m1,,320"
    raw = http_get(url)
    j = json.loads(raw)
    node = j['data']['sz000811']['m1']
    print("rows:", len(node))
    print("first:", node[0])
    print("last :", node[-1])
except Exception as e:
    print("ERROR:", type(e).__name__, e)

# ---- 东财最近日期重试 ----
print("\n=== EM recent ===")
try:
    import akshare as ak
    df = ak.stock_zh_a_hist_min_em(symbol="000811", period="5",
                                   start_date="2026-09-01 09:30:00",
                                   end_date="2026-09-16 15:00:00")
    print("rows:", len(df), "cols:", list(df.columns))
    if not df.empty:
        print(df.head(2).to_string()); print(df.tail(2).to_string())
except Exception as e:
    print("ERROR:", type(e).__name__, e)
