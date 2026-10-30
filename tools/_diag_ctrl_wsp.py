# -*- coding: utf-8 -*-
import os, sys, time, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
from PyQt6.QtWidgets import QApplication
from ui.watchlist_panel import WatchlistWidget
app = QApplication([])
out = []
w = WatchlistWidget()
time.sleep(3)
out.append("busy=%r" % getattr(w, "_ctrl_busy", "ATTR不存在"))
stocks = [dict(code=c, name=n, price=10.0, pct_chg=1.0, signals=[], trend="--",
               limit_up_count=0, sector="--") for c, n in [("600845","宝信软件"),("600587","新华医疗")]]
out.append("调用前 hasattr(_ctrl_async)=%s" % hasattr(w, "_ctrl_async"))
try:
    r = w._ctrl_async(stocks)
    out.append("调用返回 %r | busy=%r" % (r, getattr(w, "_ctrl_busy", None)))
except Exception as e:
    import traceback
    out.append("调用异常: %s\n%s" % (e, traceback.format_exc()))
t0 = time.time()
while time.time() - t0 < 20 and not all(s.get("ctrl") for s in stocks):
    time.sleep(0.5)
out.append("20s 后: %s" % [s.get("ctrl") for s in stocks])
out.append("活线程: %s" % [t.name for t in threading.enumerate()])
out.append("直接调 provider: %s" % {k: (round(v["score"],1) if v else None) for k, v in
           __import__("services.control_profile", fromlist=["x"]).get_ctrl_map(["600845","600587"]).items()})
open(r"D:\QuantMonitorV6\tools\_diag_ctrl_wsp.txt", "w", encoding="utf-8").write("\n".join(out))
os._exit(0)
