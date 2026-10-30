import io, py_compile, sys
sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\ui\watchlist_panel.py"
s = io.open(P, encoding="utf-8", newline="").read()
old = ("            if not need:\r\n"
       "                return\r\n"
       "            self._ctrl_busy = True\r\n")
new = ("            if not need:\r\n"
       "                return\r\n"
       "            self._ctrl_busy = True\r\n"
       "            import threading\r\n")
assert s.count(old) == 1, "锚点 %d" % s.count(old)
io.open(P, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
py_compile.compile(P, doraise=True)
print("OK 已补 import threading")
