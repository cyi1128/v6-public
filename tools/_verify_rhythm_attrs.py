import sys, importlib
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import services.market_rhythm_engine as M
importlib.reload(M)

print("== 1) 属性词判定自测（应 True = 剔掉）==")
bad = ["国资", "上海国资", "半年报增长", "半年增长", "业绩增长", "中报预增",
       "国企改革", "股权转让", "高送转", "摘帽", "超跌反弹", "次新股",
       "中标订单", "机构调研", "预盈预增", "净利大增", "营收增长", "年报预增"]
for w in bad:
    print("   %-12s -> %s" % (w, M._is_attribute(w)))

print()
print("== 2) 真题材反测（必须全部 False，否则误杀）==")
good = ["创新药", "AI漫剧", "AI应用", "商业综合体", "网络安全", "抗生素",
        "玉米种业", "AI安全", "AI短剧", "微短剧", "固态电池", "储能",
        "汽车零部", "化学制品", "生物制品", "病原体防治", "新能源车", "电池",
        "人形机器人", "算力租赁", "液冷服务器", "光模块", "CPO", "创新药出海",
        "航空航天", "低空经济", "固态电池材料", "光伏", "军工", "船舶",
        "抗原检测", "合成生物", "可控核聚变", "稳定币", "AI眼镜", "全息概念",
        "IP经济", "谷子经济", "算力", "存储芯片", "机器人减速器", "种业"]
killed = [w for w in good if M._is_attribute(w)]
print("   误杀:", killed if killed else "无")

print()
d = M.get_rhythm(force=True)
bs = d.get("boards") or []
print("== 3) 今日板块表（改后）==")
print("   板块总数 =", len(bs), " 其中属性词 =", sum(1 for b in bs if b.get("is_attribute")))
for i, b in enumerate(bs, 1):
    print("   %2d %-12s %s %2d家 均涨%+5.2f%% 主线=%s 龙头=%s" % (
        i, b["theme"], b["state"], b["count"], b["avg_pct"],
        b["mainline"] or "-", b["lead"]))
print()
print("   题材记忆 series 条数 =", len(d["memory"]["series"]) if isinstance(d.get("memory"), dict) else "-")
print("   轮动 new_in =", [x["name"] for x in (d.get("rotation") or {}).get("new_in") or []])
print("   轮动 fade   =", [x["name"] for x in (d.get("rotation") or {}).get("fade") or []])
print("   轮动 dead   =", [x["name"] for x in (d.get("rotation") or {}).get("dead") or []])
