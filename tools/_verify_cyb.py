# -*- coding: utf-8 -*-
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")

print("=== 1. 日K建仓过滤 ===")
from services.band_pattern_engine import _is_main_a_share as f1, _load_bars
for c, want in [("600000", True), ("000001", True), ("002594", True),
                ("300001", True), ("301001", True), ("688001", False),
                ("830799", False), ("920001", False)]:
    got = f1(c)
    print("   %s -> %-5s %s" % (c, got, "OK" if got == want else "!! 期望 %s" % want))

print("=== 2. 竞价过滤 ===")
from ui.battle_widgets.auction_filter_widget import _is_main_a_share as f2
for c, want in [("300001", True), ("301001", True), ("600000", True), ("688001", False)]:
    got = f2(c)
    print("   %s -> %-5s %s" % (c, got, "OK" if got == want else "!! 期望 %s" % want))

print("=== 3. 盘中机会/异动池 前缀 ===")
from services.intraday_opportunity_engine import MAIN_PREFIX
print("   MAIN_PREFIX = %s" % (MAIN_PREFIX,))
print("   含300=%s 含301=%s 不含688=%s" % ("300" in MAIN_PREFIX, "301" in MAIN_PREFIX, "688" not in MAIN_PREFIX))

print("=== 4. 市场节奏 ===")
from services.market_rhythm_engine import is_main_board
for c, want in [("300001", True), ("301001", True), ("600000", True), ("688001", False), ("830799", False)]:
    got = is_main_board(c)
    print("   %s -> %-5s %s" % (c, got, "OK" if got == want else "!! 期望 %s" % want))

print("=== 5. 日K建仓 真实取数（创业板股票能否拿到 >=120 根本地K线）===")
for c in ["300001", "300002", "300003", "300004", "300005"]:
    bars = _load_bars(c)
    print("   %s -> %3d 根  最新 %s  收 %s" % (
        c, len(bars), bars[-1]["date"] if bars else "-", bars[-1]["close"] if bars else "-"))
