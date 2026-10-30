import sys
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import services.band_pattern_engine as B
print("门槛: _CTRL_HIGH=%.0f  _CTRL_CAND=%.0f  _CTRL_DIST=%.0f  _CTRL_POS_LOW=%.1f" % (
    B._CTRL_HIGH, B._CTRL_CAND, B._CTRL_DIST, B._CTRL_POS_LOW))
print()
print("--- 四条规则单测（对照预期）---")
cases = [
 (86.0,'wash',0.90, ''),   # 2026-10-11 wash 文案关闭
 (80.0,'wash',0.90, ''),
 (90.0,'wash',0.30, ''),   # 2026-10-11 wash 文案关闭（C3 后 pos 0.30 也进不了候选区）
 (70.0,'distribute',0.90, '出货风险警示'),
 (60.0,'distribute',0.90, '出货风险警示'),
 (59.9,'distribute',0.90, '出货风险警示'),   # C1(2026-10-10) 出货改为位置主导 pos>=0.65，不再看分数
 (55.0,'distribute',0.90, '出货风险警示'),   # 同上
 (95.0,'distribute',0.35, ''),   # pos 0.35 既不到出货 0.65，也不在候选区 <0.25
 (95.0,'unknown',0.35, ''),   # C3(2026-10-10) 候选位置门槛改为 <0.25
 (95.0,'unknown',0.90, ''),
 (86.0,'unknown',0.90, ''),
]
ok = 0
for ctrl, st, pos, exp in cases:
    got = B._ctrl_note(ctrl, st, pos)
    flag = "OK " if got == exp else "!! "
    if got == exp: ok += 1
    print("  %sctrl=%-5.1f %-11s pos=%.2f -> '%s'" % (flag, ctrl, st, pos, got))
print()
print("单测 %d/%d 通过" % (ok, len(cases)))
