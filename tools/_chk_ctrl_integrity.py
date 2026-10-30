import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
cols = [r[1] for r in con.execute("PRAGMA table_info(pattern_record)")]
print("列数 %d" % len(cols))
print()
print("--- 各列非空条数（全为 0 说明该列错位/没写进去）---")
bad = []
for c in cols:
    n = con.execute("SELECT COUNT(*) FROM pattern_record WHERE %s IS NOT NULL AND CAST(%s AS TEXT)<>''" % (c, c)).fetchone()[0]
    flag = ""
    if n == 0 and c not in ('invalid_price','weekly_confirm','shake_ok','gap_pct'):
        flag = "  <== 可疑"; bad.append(c)
    if c in ('control_score','stage_guess','signal_level','trigger_type','note','ma20','push_price','struct_pos','shake_dip','env_score','created_at'):
        print("   %-16s %3d%s" % (c, n, flag))
print()
print("可疑列:", bad if bad else "无")
print()
print("--- 两个新列与已有关键列的值抽查（确认没错位）---")
for r in con.execute("SELECT code,name,control_score,stage_guess,ma20,push_price,env_score,struct_pos "
                     "FROM pattern_record ORDER BY control_score DESC LIMIT 6"):
    print("   %s %-6s 控盘%-6.1f %-11s MA20=%-7s 现价=%-7s 环境分=%-2s 结构位=%s" % (
        r[0], (r[1] or '')[:6], r[2], r[3], r[4], r[5], r[6], r[7]))
con.close()
