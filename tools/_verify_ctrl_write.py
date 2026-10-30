import sys, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import services.band_pattern_engine as B

TEST = 'pattern_record_ctrltest'
B._init_db(TEST)
B._WRITE_TABLE = TEST
con = sqlite3.connect(B.DB_PATH); con.execute("DELETE FROM %s" % TEST); con.commit(); con.close()
eng = B.BandPatternEngine()
CODES = [("603210","泰鸿万立"),("002105","信隆健康"),("001279","强邦新材"),
         ("600587","新华医疗"),("600894","广日股份")]
B._CTRL_FUNNEL.update({k: 0 for k in B._CTRL_FUNNEL})
n = 0
for c, nm in CODES:
    n += len(eng.scan_stock(c, nm))
print("落库 %d 条   漏斗=%s" % (n, B._CTRL_FUNNEL))
print()
con = sqlite3.connect(B.DB_PATH); con.row_factory = sqlite3.Row
rows = con.execute("SELECT code,name,pattern_id,signal_level,control_score,stage_guess,note,"
                   "trigger_type,ma20,push_price FROM %s ORDER BY code" % TEST).fetchall()
print("--- 读回验证（44 占位符写入是否对齐）---")
for r in rows:
    tip = ''
    if r['note'] and '[控盘]' in r['note']:
        tip = r['note'].split('[控盘]')[-1].strip().replace('\n',' ')
    print("  %s %-6s 模式%s %-5s 现价%-7s MA20=%-7s 控盘%5.1f %-10s %s" % (
        r['code'], (r['name'] or '')[:6], r['pattern_id'], r['signal_level'] or '',
        r['push_price'], r['ma20'], r['control_score'] or 0,
        r['stage_guess'] or '', tip))
print()
print("空/错位检查：control_score 为 0 的 %d 条，stage_guess 空的 %d 条，"
      "ma20 为 None 的 %d 条，push_price 为 None 的 %d 条" % (
      sum(1 for r in rows if not r['control_score']),
      sum(1 for r in rows if not r['stage_guess']),
      sum(1 for r in rows if r['ma20'] is None),
      sum(1 for r in rows if r['push_price'] is None)))
print("note 含 [控盘]：%d 条" % sum(1 for r in rows if r['note'] and '[控盘]' in r['note']))
con.close()
con = sqlite3.connect(B.DB_PATH); con.execute("DROP TABLE IF EXISTS %s" % TEST); con.commit(); con.close()
print()
print("已清理测试表")
