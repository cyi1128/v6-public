# -*- coding: utf-8 -*-
import py_compile, shutil, sys
P = r"D:\QuantMonitorV6\services\band_pattern_engine.py"
BAK = P + ".bak_before_ctrl_th8590"
sys.stdout.reconfigure(encoding="utf-8")
shutil.copy2(P, BAK)
s = open(P, "rb").read().decode("utf-8")
assert "\r\n" not in s, "应为纯 LF"

old = ("# 提醒文案的触发阈值。实测 591 只主板（kline_cache）control_score 分位：\n"
       "#   中位 73.7 / 75分位 91.9 / 90分位 96.4 —— 分数偏挤在高位，区分度一般。\n"
       "#   按下面默认值：>=70 命中 54.0%，>=75 命中 48.7%（偏多，几乎人人达标）。\n"
       "#   想更聚焦可改成 85（32.7%）/ 90（27.1%），改这两行即可。\n"
       "_CTRL_HIGH = 70.0        # 高度控盘线\n"
       "_CTRL_CAND = 75.0        # 高度控盘候选线\n")
new = ("# 提醒文案的触发阈值。实测 591 只主板（kline_cache）control_score 分位：\n"
       "#   中位 73.7 / 75分位 91.9 / 90分位 96.4 —— 分数偏挤在高位，区分度一般。\n"
       "#   2026-10-10 由 70/75 上调到 85/90（命中率 32.7% / 27.1%），\n"
       "#   原因是 70/75 时全市场命中 57.7%，列表里一半以上都带提示，等于没提示。\n"
       "#   想再放宽可回调到 80（40.3%）/ 85，改这两行即可。\n"
       "_CTRL_HIGH = 85.0        # 高度控盘线\n"
       "_CTRL_CAND = 90.0        # 高度控盘候选线\n")
assert s.count(old) == 1, "锚点命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)
open(P, "wb").write(s.encode("utf-8"))
py_compile.compile(P, doraise=True)
print("OK 阈值已改为 85.0 / 90.0")
print("  备份:", BAK)
