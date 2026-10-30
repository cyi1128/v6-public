# -*- coding: utf-8 -*-
"""测腾讯 m5 最大可取根数 + 字段/成交额确认"""
import sys, io, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')

for cnt in [640, 2000, 5000]:
    try:
        url = f"http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000811,m5,,{cnt}"
        j = json.loads(http_get(url))
        node = j['data']['sz000811']['m5']
        print(f"requested={cnt} returned={len(node)} first={node[0][0]} last={node[-1][0]}")
    except Exception as e:
        print(f"requested={cnt} ERROR {type(e).__name__}: {e}")

# 看一条完整记录的所有字段
j = json.loads(http_get("http://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sz000811,m5,,10"))
node = j['data']['sz000811']['m5']
print("\nfull record example:")
print(json.dumps(node[-1], ensure_ascii=False))
# 校验金额：vol(手)*100*典型价 与 末字段
rec = node[-1]
o,c,h,l = float(rec[1]),float(rec[2]),float(rec[3]),float(rec[4])
vol = float(rec[5]);
print(f"o={o} c={c} h={h} l={l} vol(手)={vol} field6={rec[6]} field7={rec[7]}")
print(f"自行估算成交额(元)= {vol*100*(h+l+c)/3:.0f}")
