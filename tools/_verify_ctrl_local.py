import sys, time, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.control_profile import get_ctrl_map, clear_cache
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
db = {r[0]: (r[1], r[2]) for r in con.execute(
    "SELECT code, control_score, stage_guess FROM pattern_record WHERE control_score IS NOT NULL")}
con.close()
codes = list(db)[:200]
clear_cache()
t0 = time.time(); m = get_ctrl_map(codes); dt = time.time() - t0
ok = sum(1 for c in codes if m.get(c, {}).get("ok") and abs(float(m[c]["score"]) - float(db[c][0])) < 0.15)
print("200 只 本地-only 首次 %.2fs（%.1f ms/只），与 DB 一致 %d/%d" % (dt, dt/len(codes)*1000, ok, len(codes)))
t0 = time.time(); get_ctrl_map(codes); print("   缓存命中 %.4fs" % (time.time()-t0))
t0 = time.time(); get_ctrl_map(["300750","688111","301001","999999"]); print("   含冷门/无效代码 4 只: %.2fs（无网络兜底）" % (time.time()-t0))
