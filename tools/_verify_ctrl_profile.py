# -*- coding: utf-8 -*-
import sys, time, random, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.control_profile import get_ctrl_map, ctrl_cell, ctrl_tooltip

# 1) 与 DB 里已存的分数交叉对账（同一口径应该完全一致）
con = sqlite3.connect(r"D:\QuantMonitorV6\data\cache\band_pattern.db")
db = {r[0]: (r[1], r[2]) for r in con.execute(
    "SELECT code, control_score, stage_guess FROM pattern_record WHERE control_score IS NOT NULL")}
con.close()
probe = ['600845', '600587', '002847', '601089', '605196', '301001']
probe = [c for c in probe if c in db] or list(db)[:5]
t0 = time.time()
m = get_ctrl_map(probe)
dt = time.time() - t0
print("=== 与 DB 对账（%d 只，耗时 %.2fs）===" % (len(probe), dt))
ok = 0
for c in probe:
    d = db.get(c)
    p = m.get(c) or {}
    same = d and p.get('ok') and abs(float(p['score']) - float(d[0])) < 0.15 and p['stage'] == d[1]
    ok += 1 if same else 0
    print("   %s  provider=%.1f/%-11s  db=%.1f/%-11s  %s" % (
        c, p.get('score') or -1, p.get('stage') or '-', d[0] if d else -1,
        d[1] if d else '-', 'OK' if same else '不一致'))
print("   一致 %d/%d" % (ok, len(probe)))

# 2) ctrl_cell / tooltip 形态
print()
print("=== 单元格形态 ===")
for c in probe:
    t, col = ctrl_cell(m.get(c))
    print("   %s -> '%s' 色=%s" % (c, t, col))
print("   无数据 ->", ctrl_cell(None))
print("   样例 tooltip:", ctrl_tooltip(m.get(probe[0])).replace("\n", " / "))

# 3) 速度压测：200 只
import itertools
codes200 = list(db)[:200]
t0 = time.time()
m2 = get_ctrl_map(codes200)
dt = time.time() - t0
print()
print("=== 速度 ===  200 只首次 %.2fs（%.1f ms/只）" % (dt, dt / max(1, len(codes200)) * 1000))
t0 = time.time()
get_ctrl_map(codes200)
print("   200 只命中缓存 %.4fs" % (time.time() - t0))
