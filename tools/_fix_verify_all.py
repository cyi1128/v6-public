# -*- coding: utf-8 -*-
"""修正做T测试行字段后重跑总装验证。"""
import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_all.py"
s = io.open(P, encoding="utf-8").read()
old = ("rows = [dict(code=c, name=n, price=10.0, pct=1.0, buy_point=9.8, sell_point=10.2,\n"
       "             mom_short=\"--\", risk_short=\"--\", signal=\"\", action=\"低吸\") for c, n in CODES]\n")
new = ("rows = [dict(code=c, name=n, price=10.0, pct=1.0, buy_point=9.8, sell_point=10.2,\n"
       "             momentum=\"\", risk=\"\", risk_color=\"#1a1a1a\", signal_text=\"--\",\n"
       "             signal_level=0, action=\"低吸\") for c, n in CODES]\n")
assert s.count(old) == 1, s.count(old)
io.open(P, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("测试行字段已修正")
