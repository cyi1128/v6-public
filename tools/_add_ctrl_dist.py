# -*- coding: utf-8 -*-
import py_compile, shutil, sys
P = r"D:\QuantMonitorV6\services\band_pattern_engine.py"
BAK = P + ".bak_before_ctrl_dist"
sys.stdout.reconfigure(encoding="utf-8")
shutil.copy2(P, BAK)
s = open(P, "rb").read().decode("utf-8")
assert "\r\n" not in s, "应为纯 LF"

def rep(old, new, tag):
    global s
    assert s.count(old) == 1, "%s 命中 %d 次" % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print("  OK", tag)

# 1) 新增出货门槛常量
rep("_CTRL_POS_LOW = 0.4      # 「位置较低」= 近120日位置 < 0.4（与评分里的加权阈值一致）\n",
    "_CTRL_POS_LOW = 0.4      # 「位置较低」= 近120日位置 < 0.4（与评分里的加权阈值一致）\n"
    "_CTRL_DIST = 60.0        # 出货风险警示的控盘分门槛：低于此分不出货警示\n"
    "                         # （2026-10-10 加。不加时全市场 161 只出货、列表里 33 条，占全部提示的七成）\n",
    'E1 新增 _CTRL_DIST')

# 2) 出货规则加门槛
rep("        if stage == 'distribute':\n"
    "            out.append('出货风险警示')\n",
    "        if stage == 'distribute' and ctrl >= _CTRL_DIST:\n"
    "            out.append('出货风险警示')\n",
    'E2 出货规则加门槛')

# 3) 注释同步
rep("#   想再放宽可回调到 80（40.3%）/ 85，改这两行即可。\n",
    "#   想再放宽可回调到 80（40.3%）/ 85，改这两行即可。\n"
    "#   出货警示另有 _CTRL_DIST 门槛（见下），与这两条独立。\n",
    'E3 注释同步')

open(P, "wb").write(s.encode("utf-8"))
py_compile.compile(P, doraise=True)
print("OK 出货警示已加控盘分门槛 60")
print("  备份:", BAK)
