import io, re
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_col.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace("cls._daily_render_table(o)", "o._daily_render_table()")
io.open(P, "w", encoding="utf-8").write(s)
print("OK 已把 cls._daily_render_table(o) 换成 o._daily_render_table()")
