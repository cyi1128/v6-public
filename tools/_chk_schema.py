import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
for db, tb in [(r"data\cache\band_pattern.db", "pattern_record"),
               (r"data\limit_up_reason.db", "limit_up_reasons")]:
    print("=" * 70)
    print(db, "->", tb)
    con = sqlite3.connect(db)
    for c in con.execute("PRAGMA table_info(%s)" % tb):
        print("   %-18s %s" % (c[1], c[2]))
    print("   行数:", con.execute("SELECT COUNT(*) FROM %s" % tb).fetchone()[0])
    con.close()
