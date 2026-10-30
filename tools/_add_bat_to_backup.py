# -*- coding: utf-8 -*-
import io, sys, shutil, py_compile
sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\scripts\backup.py"
raw = open(P, "rb").read()
crlf, lf = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
eol = "\r\n" if (crlf and not lf) else "\n"
print("backup.py 行尾: CRLF=%d LF=%d -> 用 %r" % (crlf, lf, eol))
shutil.copy2(P, P + ".bak_before_cyb")
s = raw.decode("utf-8").replace("\r\n", "\n")
old = "    '恢复到0924稳定版.bat', 'start.bat', '.gitignore']"
new = "    '恢复到0924稳定版.bat', 'start.bat', '.gitignore',\n    '灌创业板K线缓存.bat']"
assert s.count(old) == 1, "锚点 %d" % s.count(old)
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s.replace("\n", eol) if eol == "\r\n" else s)
py_compile.compile(P, doraise=True)
r2 = open(P, "rb").read()
print("OK backup.py 已收录新 bat，行尾 CRLF=%d LF=%d 编译 OK"
      % (r2.count(b"\r\n"), r2.count(b"\n") - r2.count(b"\r\n")))
