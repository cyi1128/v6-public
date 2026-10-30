# -*- coding: utf-8 -*-
import shutil, sys
P = r"D:\QuantMonitorV6\AGENTS.md"
sys.stdout.reconfigure(encoding="utf-8")
shutil.copy2(P, P + ".bak_before_ctrlcol")
s = open(P, "rb").read().decode("utf-8")
assert "\r\n" not in s
old = "\u6587\u6848\u8ffd\u52a0\u8fdb `note`\uff0c\u65e5K\u5efa\u4ed3\u8868\u300c\u89e6\u53d1\u6761\u4ef6\u300d\u5217\u60ac\u505c\u53ef\u89c1\u3002\n"
new = ("\u6587\u6848\u8ffd\u52a0\u8fdb `note`\u3002\u65e5K\u5efa\u4ed3\u8868\u65b0\u589e\u7b2c 10 \u5217\u300c\u63a7\u76d8\u300d"
       "\uff08`COL_D_CTRL`\uff09\uff1a\u663e\u793a\u300c\u5206\u6570\u00b7\u6807\u7b7e\u300d\uff08\u7eff=\u5019\u9009 / \u7ea2=\u51fa\u8d27 / "
       "\u6a59=\u6d17\u76d8\uff0c\u65e0\u63d0\u793a\u53ea\u663e\u793a\u7070\u8272\u5206\u6570\uff09\uff0c\u60ac\u505c\u770b\u5b8c\u6574\u6587\u6848"
       "\u3002\u6539\u8fd9\u5217\u8981\u540c\u6b65 5 \u5904\uff1a\u5217\u5e38\u91cf `range(12)`\uff0f`HEADER_DAILY`\uff0f"
       "`DAILY_WIDTHS`\uff0f`make_table(12, ...)`\uff0f\u884c\u6620\u5c04 + `_daily_render_table` \u54cd\u5e94\u5355\u5143\u683c\uff0c"
       "\u5c11\u4e00\u5904\u5217\u5c31\u662f\u7a7a\u7684\u3002\n")
assert s.count(old) == 1, "锚点命中 %d 次" % s.count(old)
open(P, "wb").write(s.replace(old, new, 1).encode("utf-8"))
print("OK AGENTS.md 已补充「控盘」列说明")
