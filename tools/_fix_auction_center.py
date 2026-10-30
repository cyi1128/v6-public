import py_compile, sys, io
P = r"D:\QuantMonitorV6\ui\battle_widgets\auction_filter_widget.py"
sys.stdout.reconfigure(encoding="utf-8")
s = io.open(P, encoding="utf-8", newline="").read()
old = ("            _ct, _cc = ctrl_cell(_ci)\r\n"
       "            set_table_item(self.table, row, COL_CTRL, _ct, _cc, align=center)\r\n")
new = ("            _ct, _cc = ctrl_cell(_ci)\r\n"
       "            _ctr = (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)\r\n"
       "            set_table_item(self.table, row, COL_CTRL, _ct, _cc, align=_ctr)\r\n")
assert s.count(old) == 1, "锚点命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
py_compile.compile(P, doraise=True)
print("OK 已修 center 未定义")
