import py_compile, sys
sys.stdout.reconfigure(encoding="utf-8")
F = [r"services\control_profile.py", r"ui\battle_widgets\base.py",
     r"ui\battle_widgets\limit_up_widget.py", r"ui\battle_widgets\auction_filter_widget.py",
     r"ui\battle_widgets\atr_t_widget.py", r"ui\battle_widgets\picks_track_widget.py",
     r"ui\battle_widgets\watchlist_widget.py", r"ui\watchlist_panel.py"]
print("%-46s %-6s %-11s %s" % ("文件", "编译", "行尾", "缓存填充/后台补算"))
print("-" * 96)
for f in F:
    raw = open(f, "rb").read()
    c, l = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
    eol = "CRLF(纯)" if c and not l else ("LF(纯)" if l and not c else "混%d/%d" % (c, l))
    try:
        py_compile.compile(f, doraise=True); ok = "OK"
    except Exception as e:
        ok = "FAIL"
    t = raw.decode("utf-8", "ignore")
    print("%-46s %-6s %-11s cached=%d async=%d" % (
        f, ok, eol, t.count("fetch_ctrl_cached"),
        t.count("ctrl_async_fill") + t.count("ctrl_fill_and_async")))
