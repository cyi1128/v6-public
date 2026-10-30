# -*- coding: utf-8 -*-
"""冷缓存路径：缓存清空 -> 行数据无 ctrl -> 后台补算 -> 回调重绘"""
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
import services.control_profile as CP
app = QApplication([])
from ui.battle_widgets.picks_track_widget import PicksTrackWidget
from services.picks_tracking_service import fetch_tracking

CODES = ["600845", "002847", "605196", "600587"]
CP.clear_cache()                      # 冷缓存
real = fetch_tracking()
rows = []
for r in real:
    if r.get("code") in CODES and r["code"] not in [x.get("code") for x in rows]:
        rows.append(r)
    if len(rows) == 4:
        break
for r in rows:
    r["ctrl"] = None
print("冷缓存：行数=%d，ctrl 全为空=%s" % (len(rows), all(r["ctrl"] is None for r in rows)))

w = PicksTrackWidget()
done = {"n": 0}
def on_done():
    done["n"] += 1
t0 = time.time()
w._ctrl_fill(rows, on_done)
while time.time() - t0 < 25 and not all(r.get("ctrl") for r in rows):
    app.processEvents(); time.sleep(0.1)
for _ in range(20):
    app.processEvents(); time.sleep(0.05)
print("补算结果：耗时%.1fs ctrl 全有值=%s 回调次数=%d" % (
    time.time()-t0, all(r.get("ctrl") for r in rows), done["n"]))
from services.control_profile import ctrl_cell
for r in rows:
    print("   %s %s -> %s" % (r["code"], r.get("name"), ctrl_cell(r.get("ctrl"))[0]))
print("冷缓存路径：%s" % ("通过" if all(r.get("ctrl") for r in rows) and done["n"] >= 1 else "失败"))
sys.stdout.flush(); time.sleep(0.3); os._exit(0)
