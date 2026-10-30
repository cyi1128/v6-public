import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_cached.py"
s = io.open(P, encoding="utf-8").read()
old = """    w, setrows, render, colidx = build(mod)
    rows = [base_row(c, n) for c, n, _ in CODES]"""
new = """    w, setrows, render, colidx = build(mod)
    if mod == 'track':
        # 追踪表用真实行数据（字段多且会被格式化，宽字典不适用）
        from services.picks_tracking_service import fetch_tracking
        from services.control_profile import ctrl_cell
        real = fetch_tracking()
        allc = [c for c, _, _ in CODES]
        rows = []
        for r in real:
            if r.get('code') in allc and r['code'] not in [x.get('code') for x in rows]:
                rows.append(r)
            if len(rows) == 4:
                break
        assert len(rows) == 4, '追踪库没取满 4 只'
        rows.sort(key=lambda r: allc.index(r['code']))
        cm = get_ctrl_map([r['code'] for r in rows])
        global EXP_TRACK
        EXP_TRACK = [ctrl_cell(cm.get(r['code']))[0] for r in rows]
        for r in rows:
            r['ctrl'] = None
    else:
        rows = [base_row(c, n) for c, n, _ in CODES]"""
assert s.count(old) == 1, "%d" % s.count(old)
s = s.replace(old, new, 1)
old2 = """    for i, (c, n, exp) in enumerate(CODES):
        it = w.table.item(i, colidx)
        txt = it.text() if it else None
        if txt != exp:
            bad.append((c, txt, exp))
        print('   row%d %-6s %-8s 控盘=%r' % (i, c, n, txt))"""
new2 = """    for i, r in enumerate(rows):
        c = r['code']; n = r.get('name')
        exp = EXP_TRACK[i] if mod == 'track' else CODES[i][2]
        it = w.table.item(i, colidx)
        txt = it.text() if it else None
        if txt != exp:
            bad.append((c, txt, exp))
        print('   row%d %-6s %-8s 控盘=%r (期望 %s)' % (i, c, n, txt, exp))"""
assert s.count(old2) == 1, "%d" % s.count(old2)
s = s.replace(old2, new2, 1)
s = s.replace("assert all('ctrl' not in r for r in rows), '构造的行不应带 ctrl'\n",
              "assert all(not r.get('ctrl') for r in rows), '构造的行不应带 ctrl'\n", 1)
s = s.replace("CODES = [", "EXP_TRACK = []\nCODES = [", 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
