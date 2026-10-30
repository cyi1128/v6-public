import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
n = con.execute("SELECT COUNT(*) FROM pattern_record").fetchone()[0]
tip = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%[控盘]%'").fetchone()[0]
cand = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%高度控盘候选%'").fetchone()[0]
dist = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%出货风险警示%'").fetchone()[0]
wash = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%疑似洗盘%'").fetchone()[0]
ge85 = con.execute("SELECT COUNT(*) FROM pattern_record WHERE control_score>=85").fetchone()[0]
ge90 = con.execute("SELECT COUNT(*) FROM pattern_record WHERE control_score>=90").fetchone()[0]
print("pattern_record 共 %d 条（与改动前一致）" % n)
print("  带 [控盘] 提醒        : %d 条   （改动前 66 条）" % tip)
print("   ├ 高度控盘候选       : %d 条" % cand)
print("   ├ 出货风险警示       : %d 条" % dist)
print("   └ 高度控盘+疑似洗盘  : %d 条" % wash)
print("  control_score >=85    : %d 条" % ge85)
print("  control_score >=90    : %d 条" % ge90)
print()
print("--- 现在会带提示的个股（前 25）---")
for r in con.execute("SELECT code,name,signal_level,control_score,stage_guess,note FROM pattern_record "
                     "WHERE note LIKE '%[控盘]%' ORDER BY control_score DESC LIMIT 25"):
    t = r[5].split('[控盘]')[-1].strip().replace('\n',' ')
    print("   %s %-6s %-5s 控盘%5.1f %-11s %s" % (r[0], (r[1] or '')[:6], r[2] or '', r[3] or 0, r[4] or '', t))
con.close()
