import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_wsp.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace('from PyQt6.QtWidgets import QApplication\napp = QApplication([])\nfrom ui.watchlist_panel import WatchlistWidget\n',
              'from PyQt6.QtWidgets import QApplication\nfrom ui.watchlist_panel import WatchlistWidget  # 必须先于 QApplication 导入（QtWebEngine 要求）\napp = QApplication([])\n')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
