import sys, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import services.band_pattern_engine as B

# 1) 真实表补列
B._init_db('pattern_record')
con = sqlite3.connect(B.DB_PATH)
cols = [r[1] for r in con.execute("PRAGMA table_info(pattern_record)")]
print("pattern_record 列数:", len(cols))
print("  新增列存在:", 'control_score' in cols, 'stage_guess' in cols)
con.close()

# 2) 真实股票跑 scan_stock
TEST = 'pattern_record_ctrltest'
B._init_db(TEST)
B._WRITE_TABLE = TEST
con = sqlite3.connect(B.DB_PATH); con.execute("DELETE FROM %s" % TEST); con.commit(); con.close()
eng = B.BandPatternEngine()
import duckdb
k = duckdb.connect(r"data\cache\kline_cache.duckdb", read_only=True)
codes = [r[0] for r in k.execute(
    "SELECT DISTINCT code FROM kline_cache WHERE substr(CAST(code AS VARCHAR),1,3) "
    "IN ('600','601','603','605','000','001','002','003') ORDER BY code LIMIT 60").fetchall()]
k.close()
B._CTRL_FUNNEL.update({k2: 0 for k2 in B._CTRL_FUNNEL})
n = 0
for c in codes:
    try:
        n += len(eng.scan_stock(c, ''))
    except Exception as e:
        print("  异常", c, e)
print()
print("扫描 %d 只 -> 落库 %d 条" % (len(codes), n))
print("漏斗:", B._CTRL_FUNNEL)
con = sqlite3.connect(B.DB_PATH); con.row_factory = sqlite3.Row
rows = con.execute("SELECT code,name,pattern_id,signal_level,control_score,stage_guess,note FROM %s" % TEST).fetchall()
print("库里 control_score 为 0 的条数:", sum(1 for r in rows if not r['control_score']))
print("库里 stage_guess 为 NULL/空的条数:", sum(1 for r in rows if not r['stage_guess']))
print("note 含 [控盘] 的条数:", sum(1 for r in rows if r['note'] and '[控盘]' in r['note']))
print()
print("--- 抽样 8 条 ---")
for r in rows[:8]:
    tip = ''
    if r['note'] and '[控盘]' in r['note']:
        tip = r['note'].split('[控盘]')[-1].strip().replace('\n', ' ')
    print("  %s %-6s 模式%s %-6s 控盘%5.1f %-10s %s" % (
        r['code'], (r['name'] or '')[:6], r['pattern_id'], r['signal_level'] or '',
        r['control_score'] or 0, r['stage_guess'] or '', tip))
con.close()

print()
print("--- 三条提醒文案规则单测 ---")
for args in [(80.0,'wash',0.9),(72.0,'unknown',0.8),(70.0,'distribute',0.9),
             (76.0,'unknown',0.35),(60.0,'unknown',0.5),(85.0,'wash',0.3)]:
    print("  ctrl=%-5.1f stage=%-11s pos=%.2f  ->  '%s'" % (
        args[0], args[1], args[2], B._ctrl_note(*args)))

con = sqlite3.connect(B.DB_PATH); con.execute("DROP TABLE IF EXISTS %s" % TEST); con.commit(); con.close()
print()
print("已清理测试表")
