# -*- coding: utf-8 -*-
import os, sys, py_compile
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
F = [r"services\band_pattern_engine.py", r"ui\battle_widgets\auction_filter_widget.py",
     r"services\intraday_opportunity_engine.py", r"services\market_rhythm_engine.py",
     r"services\board_anomaly_engine.py", r"services\picks_tracking_service.py"]
print("%-44s %-6s %-11s %s" % ("文件", "编译", "行尾", "含 300/301"))
print("-" * 88)
for f in F:
    raw = open(f, "rb").read(); c, l = raw.count(b"\r\n"), raw.count(b"\n") - c if False else raw.count(b"\n") - raw.count(b"\r\n")
    eol = "CRLF(纯)" if c and not l else ("LF(纯)" if l and not c else "混合")
    try: py_compile.compile(f, doraise=True); ok = "OK"
    except Exception as e: ok = "FAIL"
    t = raw.decode("utf-8", "ignore")
    mark = ("'300'" in t or "300" in t)
    print("%-44s %-6s %-11s %s" % (f, ok, eol, "是" if mark else "否"))
print()
print("=== 备份脚本是否覆盖新 bat ===")
s = open(r"scripts\backup.py", encoding="utf-8").read()
print("   含 '灌创业板K线缓存.bat':", "灌创业板K线缓存.bat" in s)
for kw in ["盘后扫描_波段四模式.bat", "start.bat"]:
    print("   含 %s: %s" % (kw, kw in s))
print()
print("=== 是否还有残留灌数据进程 ===")
import subprocess
