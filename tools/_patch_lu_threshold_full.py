# -*- coding: utf-8 -*-
"""把 _lu_threshold 补全到科创板/北交所（当前引擎不扫这两板，但函数应自洽）。"""
import io
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\services\band_pattern_engine.py"

raw = open(P, "rb").read()
assert raw.count(b"\r\n") == 0, "应为纯 LF"
shutil.copy2(P, P + ".bak_before_lu_sh")
s = raw.decode("utf-8-sig").replace("\r\n", "\n")

old = '''    return 19.5 if str(code).startswith(('300', '301')) else 9.5'''
new = '''    c = str(code)
    if c.startswith(('300', '301', '688', '689')):
        return 19.5      # 创业板 / 科创板 20cm
    if c.startswith(('8', '4', '920')):
        return 29.5      # 北交所 30cm
    return 9.5           # 主板 10cm'''
assert s.count(old) == 1, "锚点命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
r2 = open(P, "rb").read()
print("OK %s ｜CRLF=%d 裸LF=%d" % (P, r2.count(b"\r\n"),
                                   r2.count(b"\n") - r2.count(b"\r\n")))
