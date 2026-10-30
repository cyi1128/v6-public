import sys
sys.stdout.reconfigure(encoding="utf-8")
raw = open(r"D:\QuantMonitorV6\ui\watchlist_panel.py", "rb").read()
c = raw.count(b"\r\n"); l = raw.count(b"\n") - c
print("watchlist_panel.py 行尾: CRLF=%d 裸LF=%d" % (c, l))
