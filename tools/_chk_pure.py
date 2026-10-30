import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
print("== 按模式 x 等级 ==")
for r in con.execute("SELECT pattern_name, signal_level, COUNT(*) FROM pattern_record GROUP BY pattern_name, signal_level ORDER BY pattern_name, signal_level"):
    print("   %-10s %-8s %4d" % r)
print()
print("== 横盘周K 的震仓项数分布 ==")
for r in con.execute("SELECT shake_ok, signal_level, COUNT(*) FROM pattern_record WHERE pattern_id=3 GROUP BY shake_ok, signal_level ORDER BY shake_ok"):
    print("   shake_ok=%s  %-8s %4d" % r)
print()
print("== 界面实际会显示的（建仓触发+等待确认） ==")
r = con.execute("SELECT COUNT(*) FROM pattern_record WHERE signal_level IN ('建仓触发','等待确认')").fetchone()
print("   合计 %d 只" % r[0])
for r in con.execute("SELECT pattern_name, COUNT(*) FROM pattern_record WHERE signal_level IN ('建仓触发','等待确认') GROUP BY pattern_name"):
    print("   %-10s %4d" % r)
print()
print("== 横盘周K 提纯通过清单 ==")
for r in con.execute("SELECT code, name, shake_dip, shake_shadow, shake_probe, shake_amp, volume_ratio, struct_pos FROM pattern_record WHERE pattern_id=3 AND signal_level IN ('建仓触发','等待确认') ORDER BY volume_ratio DESC"):
    print("   %s %-8s 回撤%5.1f%% 下影%5.1f%% 探针%+5.2f%% 振幅%.2f 周量%.2f倍 结构位%.0f%%" % r)
con.close()
