import sys, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.control_profile import get_ctrl_map, clear_cache
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
db = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
    "SELECT code, control_score, stage_guess, name FROM pattern_record WHERE control_score IS NOT NULL")}
con.close()
clear_cache()
m = get_ctrl_map(list(db))
print("不一致明细：")
n = 0
for c, (sc, st, nm) in db.items():
    p = m.get(c) or {}
    if not p.get("ok"):
        n += 1; print("   %s %s  provider=None(本地无K线)  db=%.1f/%s" % (c, nm, sc, st))
    elif abs(float(p["score"]) - float(sc)) >= 0.15 or p["stage"] != st:
        n += 1; print("   %s %s  provider=%.1f/%-11s db=%.1f/%-11s" % (c, nm, p["score"], p["stage"], sc, st))
print("   共 %d 条差异 / 总 %d 条" % (n, len(db)))
