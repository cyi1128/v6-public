import py_compile
F = [r"services\control_profile.py", r"ui\battle_widgets\base.py",
     r"ui\battle_widgets\limit_up_widget.py", r"ui\battle_widgets\auction_filter_widget.py",
     r"ui\battle_widgets\atr_t_widget.py", r"ui\battle_widgets\picks_track_widget.py",
     r"ui\watchlist_panel.py"]
for f in F:
    raw = open(f, "rb").read()
    c, l = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
    eol = "CRLF(纯)" if c and not l else ("LF(纯)" if l and not c else "混CRLF=%d LF=%d" % (c, l))
    try:
        py_compile.compile(f, doraise=True); ok = "OK"
    except Exception as e:
        ok = "FAIL " + str(e)[:60]
    print("%-46s %-6s %-10s cached=%d" % (f, ok, eol, raw.decode("utf-8","ignore").count("fetch_ctrl_cached")))
