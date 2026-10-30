# -*- coding: utf-8 -*-
import io, sys, shutil, py_compile
sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6\\"
JOBS = [
 (r"services\board_anomaly_engine.py", [
  ("        codes = [c for c in codes if c.startswith(('60', '00'))]",
   "        # 2026-10-10：放行 30（创业板）\n        codes = [c for c in codes if c.startswith(('60', '00', '30'))]"),
  ("            if not code.startswith(('60', '00')):\n                continue",
   "            if not code.startswith(('60', '00', '30')):\n                continue"),
 ]),
 (r"services\picks_tracking_service.py", [
  ("            if not code.startswith(('60', '00')):\n                continue",
   "            if not code.startswith(('60', '00', '30')):\n                continue"),
 ]),
]
for rel, pairs in JOBS:
    P = ROOT + rel
    raw = open(P, "rb").read()
    crlf = raw.count(b"\r\n"); lf = raw.count(b"\n") - crlf
    if crlf and not lf: eol, nm = "\r\n", "CRLF"
    elif lf and not crlf: eol, nm = "\n", "LF"
    else:
        print("!! %s 行尾混合，跳过" % rel); continue
    shutil.copy2(P, P + ".bak_before_cyb")
    s = raw.decode("utf-8").replace("\r\n", "\n")
    ok = True
    for old, new in pairs:
        n = s.count(old)
        if n == 0:
            print("!! %s 锚点未命中: %r" % (rel, old[:40])); ok = False; continue
        s = s.replace(old, new)   # 出现多次就全改（都是同一过滤）
        print("   %s 替换 %d 处" % (rel, n))
    if not ok: continue
    io.open(P, "w", encoding="utf-8", newline="").write(s.replace("\n", eol) if eol == "\r\n" else s)
    r2 = open(P, "rb").read(); c2 = r2.count(b"\r\n"); l2 = r2.count(b"\n") - c2
    try:
        py_compile.compile(P, doraise=True); comp = "OK"
    except Exception as e: comp = "FAIL %s" % e
    print("OK %-42s 行尾 %s->CRLF=%d/LF=%d 编译=%s" % (rel, nm, c2, l2, comp))
