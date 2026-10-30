# -*- coding: utf-8 -*-
"""把 AGENTS.md 里追高文案的行号对齐到实测值（L1472/L1474）。"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\AGENTS.md"
raw = open(P, "rb").read()
assert raw.count(b"\r\n") == 0
s = raw.decode("utf-8")
old = "`intraday_opportunity_engine.py` L1471/L1473（追高提示文案）"
new = "`intraday_opportunity_engine.py` L1472/L1474（追高提示文案）"
assert s.count(old) == 1, "锚点命中 %d 次" % s.count(old)
shutil.copy2(P, P + ".bak_before_lufix")
io.open(P, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
print("OK AGENTS.md 行号已对齐")
