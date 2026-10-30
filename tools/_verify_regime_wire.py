import sys, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import services.band_pattern_engine as B

TEST = "pattern_record_regimetest"
B._init_db(TEST)
B._WRITE_TABLE = TEST
eng = B.BandPatternEngine()

CODES = [("603210", "泰鸿万立"), ("002105", "信隆健康"), ("001279", "强邦新材"),
         ("600587", "新华医疗"), ("600894", "广日股份")]

def run(tag):
    B._init_db(TEST)
    con = sqlite3.connect(B.DB_PATH); con.execute("DELETE FROM %s" % TEST); con.commit(); con.close()
    out = []
    for c, n in CODES:
        try:
            for r in eng.scan_stock(c, n):
                out.append((c, n, r["pattern_id"], r["signal_level"], r["trigger_type"],
                            r.get("take_profit"), (r.get("note") or "").count("状态闸门")))
        except Exception as e:
            out.append((c, n, "-", "ERR", str(e)[:60], None, 0))
    print("== %s ==" % tag)
    print("   状态=%s  allow_trigger=%s  tp=%s" % (
        B._REGIME["state"], B._REGIME["allow_trigger"], B._REGIME["tp_factor"]))
    for r in out:
        print("   %s %-6s 模式%s %-6s %-14s tp=%s 闸门标注=%d" % r)
    return out

B._load_regime(verbose=False)
B._REGIME["allow_trigger"] = True
B._REGIME["tp_factor"] = 1.03
a = run("控制组：闸门放行")

B._REGIME["allow_trigger"] = False
B._REGIME["state"] = "🧊 冰点"
b = run("实验组：强制冰点（应降为观察、带闸门标注）")

B._REGIME["allow_trigger"] = True
B._REGIME["tp_factor"] = 1.02
c = run("实验组：过热（tp 应变 1.02）")

print()
ok1 = all(x[3] != "观察" for x in a if x[3] != "ERR")
ok2 = all(x[3] == "观察" and x[6] >= 1 for x in b if x[3] != "ERR")
print("判定1 放行时不降级 :", ok1)
print("判定2 冰点时全降观察+标注 :", ok2)
con = sqlite3.connect(B.DB_PATH)
con.execute("DROP TABLE IF EXISTS %s" % TEST); con.commit(); con.close()
print("已清理测试表")
