import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
n = con.execute("SELECT COUNT(*) FROM pattern_record").fetchone()[0]
tip = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%[控盘]%'").fetchone()[0]
cand = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%高度控盘候选%'").fetchone()[0]
dist = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%出货风险警示%'").fetchone()[0]
wash = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%疑似洗盘%'").fetchone()[0]
print("pattern_record 共 %d 条" % n)
print("  带 [控盘] 提醒      : %d 条   （原始 66 → 阈值85/90后 48 → 加出货门槛后 %d）" % (tip, tip))
print("   ├ 高度控盘候选     : %d 条" % cand)
print("   ├ 出货风险警示     : %d 条   （原 33 → 现在 %d）" % (dist, dist))
print("   └ 高度控盘+疑似洗盘 : %d 条" % wash)
print()
print("--- 被门槛挡掉的 distribute（控盘分<60，已不再提示）---")
d = con.execute("SELECT code,name,signal_level,control_score FROM pattern_record "
                "WHERE stage_guess='distribute' AND control_score<60 ORDER BY control_score DESC").fetchall()
print("   共 %d 条，控盘分区间 %.1f ~ %.1f" % (len(d), d[-1][3], d[0][3]))
for r in d[:6]:
    print("     %s %-6s %-5s 控盘%.1f" % (r[0], (r[1] or '')[:6], r[2] or '', r[3]))
print("     ...")
print()
print("--- 仍保留提示的（出货风险警示）---")
for r in con.execute("SELECT code,name,signal_level,control_score,stage_guess,note FROM pattern_record "
                     "WHERE note LIKE '%出货风险警示%' ORDER BY control_score DESC"):
    t = r[5].split('[控盘]')[-1].strip().replace('\n',' ')
    print("   %s %-6s %-5s 控盘%5.1f %-11s %s" % (r[0], (r[1] or '')[:6], r[2] or '', r[3] or 0, r[4] or '', t))
print()
print("--- 现在全部带 [控盘] 提示的个股 ---")
for r in con.execute("SELECT code,name,signal_level,control_score,stage_guess,note FROM pattern_record "
                     "WHERE note LIKE '%[控盘]%' ORDER BY control_score DESC"):
    t = r[5].split('[控盘]')[-1].strip().replace('\n',' ')
    print("   %s %-6s %-5s 控盘%5.1f %-11s %s" % (r[0], (r[1] or '')[:6], r[2] or '', r[3] or 0, r[4] or '', t))
con.close()
