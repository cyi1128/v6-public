# -*- coding: utf-8 -*-
import py_compile, sys
sys.stdout.reconfigure(encoding="utf-8")
FILES = [
    r"services\control_profile.py",
    r"ui\battle_widgets\base.py",
    r"ui\battle_widgets\limit_up_widget.py",
    r"ui\battle_widgets\watchlist_widget.py",
    r"ui\battle_widgets\atr_t_widget.py",
    r"ui\battle_widgets\auction_filter_widget.py",
    r"ui\battle_widgets\picks_track_widget.py",
    r"ui\watchlist_panel.py",
]
print("%-46s %-8s %-16s %s" % ("文件", "编译", "行尾", "控盘列"))
print("-" * 92)
for f in FILES:
    p = f
    raw = open(p, "rb").read()
    c = raw.count(b"\r\n"); l = raw.count(b"\n") - c
    eol = "CRLF(纯)" if c and not l else ("LF(纯)" if l and not c else "CRLF=%d LF=%d" % (c, l))
    try:
        py_compile.compile(p, doraise=True)
        ok = "OK"
    except Exception as e:
        ok = "FAIL"
        print(e)
    has = "有" if ("\u63a7\u76d8" in raw.decode("utf-8", "ignore")) else "-"
    print("%-46s %-8s %-16s %s" % (f, ok, eol, has))
