import sys, os, json, urllib.request, time
sys.path.insert(0, r"D:\QuantMonitorV6")

# 1) 拉全市场涨幅榜，挑涨停（>=9.8%）
url_tpl = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=%d&num=80&sort=changepercent&asc=0&node=hs_a&symbol=&_s_r_a=auto"
hdr = {"User-Agent":"Mozilla/5.0", "Referer":"https://finance.sina.com.cn"}
allrows = []
for pn in range(1, 16):
    try:
        req = urllib.request.Request(url_tpl % pn, headers=hdr)
        t = urllib.request.urlopen(req, timeout=10).read().decode("gbk", "ignore")
        arr = json.loads(t) if t.strip() else []
    except Exception as e:
        print("  第%d页失败: %s" % (pn, e)); break
    if not arr: break
    allrows.extend(arr)
    last = float(arr[-1].get("changepercent") or 0)
    if last < 9.0: break

print("  涨幅榜抓取 = %d 只" % len(allrows))
zt = [x for x in allrows if float(x.get("changepercent") or 0) >= 9.8]
print("  其中涨停(>=9.8%%) = %d 只" % len(zt))

def board(c):
    if c[:3] in ("600","601","603","605"): return "沪主板"
    if c[:3] in ("000","001","002","003"): return "深主板"
    if c[:3] in ("300","301"): return "创业板"
    if c[:2] == "68": return "科创板"
    if c[:2] in ("83","87","92","43"): return "北交所"
    return "其他"

def is_st(n): return ("ST" in (n or "")) or ("*" in (n or ""))

print("")
print("  %-8s %-9s %-7s %8s %10s %10s" % ("code","name","板块","涨幅%","成交额(亿)","换手%"))
lz = []
for x in zt:
    c = x.get("code",""); n = x.get("name","") or ""
    lz.append({
        "code": c, "name": n, "board": board(c), "st": is_st(n),
        "pct": float(x.get("changepercent") or 0),
        "amt": float(x.get("amount") or 0)/1e8,
        "turn": float(x.get("turnoverratio") or 0),
    })
for z in sorted(lz, key=lambda a:-a["amt"])[:30]:
    print("  %-8s %-9s %-7s %8.2f %10.2f %10.2f" % (
        z["code"], z["name"][:7], z["board"], z["pct"], z["amt"], z["turn"]))

json.dump(lz, open("_zt.json","w",encoding="utf-8"), ensure_ascii=False)
print("")
print("  已存 _zt.json，共 %d 条" % len(lz))
