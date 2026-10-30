import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
print("tables:", [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type=\"table\"")])
row = con.execute("SELECT code,name,signal_level,shake_dip,shake_shadow,shake_probe,shake_amp,shake_ok,note FROM pattern_record WHERE code=\"603210\"").fetchone()
print("603210:", row)
if row: print("note:", repr(row[8]))
con.close()
