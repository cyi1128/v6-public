import sys
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.market_rhythm_engine import get_rhythm, MIN_STOCK, _recent_dates
print("MIN_STOCK =", MIN_STOCK)
print("最近日期:", _recent_dates(5))
d = get_rhythm(force=True)
print("ok =", d.get("ok"), "| 数据日 =", d.get("date"))
bs = d.get("boards") or []
print("板块总数 =", len(bs))
attr = [b for b in bs if b.get("is_attribute")]
print("其中属性词(国资/半年报增长这类) =", len(attr), [b["theme"] for b in attr])
print()
print("前 30 个真题材:")
for b in [x for x in bs if not x.get("is_attribute")][:30]:
    print("   %-14s %s %2d家 均涨%+5.2f%% 主线=%s" % (b["theme"], b["state"], b["count"], b["avg_pct"], b["mainline"] or "-"))
