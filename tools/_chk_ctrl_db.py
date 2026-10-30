import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
n = con.execute("SELECT COUNT(*) FROM pattern_record").fetchone()[0]
pop = con.execute("SELECT COUNT(*) FROM pattern_record WHERE control_score IS NOT NULL AND control_score>0").fetchone()[0]
print("pattern_record 共 %d 条，control_score 已填充 %d 条" % (n, pop))
print()
print("--- 控盘分布 ---")
for r in con.execute("SELECT CASE WHEN control_score>=90 THEN '>=90' WHEN control_score>=85 THEN '85~90' "
                     "WHEN control_score>=75 THEN '75~85' WHEN control_score>=70 THEN '70~75' "
                     "WHEN control_score>=60 THEN '60~70' ELSE '<60' END g, COUNT(*) FROM pattern_record "
                     "WHERE control_score>0 GROUP BY g ORDER BY g DESC"):
    print("   %-8s %d 条" % r)
print()
print("--- stage_guess ---")
for r in con.execute("SELECT stage_guess, COUNT(*) FROM pattern_record WHERE control_score>0 GROUP BY stage_guess ORDER BY 2 DESC"):
    print("   %-12s %d 条" % r)
print()
print("--- 触发控盘提醒的个股 ---")
for r in con.execute("SELECT code,name,pattern_id,signal_level,control_score,stage_guess,note FROM pattern_record "
                     "WHERE note LIKE '%[控盘]%' ORDER BY control_score DESC"):
    tip = r[6].split('[控盘]')[-1].strip().replace('\n',' ')
    print("   %s %-6s 模式%s %-5s 控盘%5.1f %-11s %s" % (r[0], (r[1] or '')[:6], r[2], r[3] or '', r[4] or 0, r[5] or '', tip))
con.close()
