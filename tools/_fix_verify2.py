# -*- coding: utf-8 -*-
import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_col.py"
s = io.open(P, encoding="utf-8").read()
old = "try:\n    o._daily_fetch_and_calc()\nexcept Exception as e:\n    print('fetch \u9014\u4e2d\u5f02\u5e38\uff08\u4e0d\u5f71\u54cd\u5df2\u586b\u597d\u7684\u884c\u6570\u636e\uff09: %s %s' % (type(e).__name__, e))"
new = ("try:\n"
       "    _rows = o._daily_fetch_and_calc()\n"
       "    print('_daily_fetch_and_calc \u8fd4\u56de: %s \u884c' % (len(_rows) if _rows else 0))\n"
       "    o._daily_rows = _rows or []\n"
       "except Exception as e:\n"
       "    print('fetch \u9014\u4e2d\u5f02\u5e38\uff08\u4e0d\u5f71\u54cd\u5df2\u586b\u597d\u7684\u884c\u6570\u636e\uff09: %s %s' % (type(e).__name__, e))")
assert s.count(old) == 1, "命中 %d 次" % s.count(old)
io.open(P, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("OK 已改成接收返回值")
