# -*- coding: utf-8 -*-
import shutil, sys
P = r"D:\QuantMonitorV6\AGENTS.md"
sys.stdout.reconfigure(encoding="utf-8")
shutil.copy2(P, P + ".bak_before_dist")
s = open(P, "rb").read().decode("utf-8")
assert "\r\n" not in s, "AGENTS.md 应为纯 LF"

old = "提醒阈值 `_CTRL_HIGH = 85.0` / `_CTRL_CAND = 90.0`（L301-302），文案追加进 `note`，日K建仓表「触发条件」列悬停可见。\n"
new = ("提醒阈值 `_CTRL_HIGH = 85.0` / `_CTRL_CAND = 90.0`（L302-303），"
       "出货警示另有 `_CTRL_DIST = 60.0` 门槛（L305）；文案追加进 `note`，"
       "日K建仓表「触发条件」列悬停可见。\n"
       "  > 注意：`backups\\backup_20261010_005808` 是在**加 `_CTRL_DIST` 出货门槛之前**打的快照。"
       "恢复它 = 没有出货门槛（出货提示会从 9 条回到 33 条）。要含出货门槛的还原点需重新 `python scripts\\backup.py`。\n")
assert s.count(old) == 1, "锚点命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)
open(P, "wb").write(s.encode("utf-8"))
print("OK  AGENTS.md 已补充 _CTRL_DIST 说明（纯 LF）")
