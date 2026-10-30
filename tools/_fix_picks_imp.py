import io, shutil, py_compile, sys
sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\ui\battle_widgets\picks_track_widget.py"   # 纯 LF
raw = open(P, "rb").read()
c, l = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
assert c == 0 and l > 0, "不是纯 LF: CRLF=%d LF=%d" % (c, l)
shutil.copy2(P, P + ".bak_before_cached")
s = raw.decode("utf-8")
old = "from .base import make_table, set_table_item, BC, HeaderSorter, CTRL_COL_TITLE\n"
new = "from .base import (make_table, set_table_item, BC, HeaderSorter, CTRL_COL_TITLE,\n                      fetch_ctrl_cached)\n"
assert s.count(old) == 1, "锚点 %d" % s.count(old)
io.open(P, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
py_compile.compile(P, doraise=True)
r2 = open(P, "rb").read()
c2, l2 = r2.count(b"\r\n"), r2.count(b"\n") - r2.count(b"\r\n")
print("OK picks_track：cached=%d  行尾 CRLF=%d LF=%d" % (r2.decode("utf-8").count("fetch_ctrl_cached"), c2, l2))
