import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
cols = [r[1] for r in con.execute("PRAGMA table_info(pattern_record)")]
n = con.execute("SELECT COUNT(*) FROM pattern_record").fetchone()[0]
pop = con.execute("SELECT COUNT(*) FROM pattern_record WHERE control_score>0").fetchone()[0]
tip = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%[控盘]%'").fetchone()[0]
print("pattern_record 列数 %d ｜ control_score=%s stage_guess=%s" % (
      len(cols), 'control_score' in cols, 'stage_guess' in cols))
print("共 %d 条 ｜ control_score 已填充 %d 条 ｜ 带 [控盘] 提醒 %d 条" % (n, pop, tip))
print("stage_guess:", dict(con.execute("SELECT stage_guess,COUNT(*) FROM pattern_record GROUP BY stage_guess")))
print()
print("最近一条扫描时间:", con.execute("SELECT MAX(updated_at) FROM pattern_record").fetchone()[0])
con.close()
