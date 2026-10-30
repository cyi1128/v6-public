# -*- coding: utf-8 -*-
"""诊断：各模块真实取数的 code 格式，以及控盘查询命中率。"""
import sys
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.control_profile import get_ctrl_map

def report(name, codes):
    codes = [c for c in codes if c]
    uniq = list(dict.fromkeys(codes))
    print("\n【%s】行数=%d 去重=%d" % (name, len(codes), len(uniq)))
    print("   样例 code: %r" % uniq[:6])
    m = get_ctrl_map(uniq[:60])
    ok = [c for c in uniq[:60] if m.get(c) and m[c].get('ok')]
    print("   控盘命中: %d/%d   未命中样例: %r" % (len(ok), len(uniq[:60]), [c for c in uniq[:60] if c not in ok][:6]))

# 1 追踪库
try:
    from services.picks_tracking_service import fetch_tracking
    rows = fetch_tracking()
    report("市场节奏·追踪(fetch_tracking)", [r.get('code') for r in rows])
except Exception as e:
    print("追踪库读取失败: %s" % e)

# 2 自选
try:
    from core.watchlist import get_watchlist_manager
    wm = get_watchlist_manager()
    items = wm.get_all() if hasattr(wm, 'get_all') else wm.get_watchlist()
    codes = []
    for it in items:
        codes.append(it.get('code') if isinstance(it, dict) else getattr(it, 'code', None))
    report("自选评分(watchlist)", codes)
except Exception as e:
    print("自选读取失败: %s" % e)
