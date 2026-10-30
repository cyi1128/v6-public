# -*- coding: utf-8 -*-
"""把「主营失败标记」的剩余个股重补一遍（清标记 → 重取 → 落盘 → 报覆盖）。"""
import os
import sys
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

snap = SS.load_snapshot()
rows = snap['rows']
pool = [str(r['code']) for r in rows
        if float(r.get('score') or 0) >= 0.0
        and str(r.get('stage')) != 'distribute'
        and float(r.get('price') or 0) >= 6.0 and not SS.is_st_name(r.get('name'))]
items = SS.load_extras()
_retry = [c for c in pool if not (items.get(c) or {}).get('biz')]
print('待重补 %d 只：%s' % (len(_retry), _retry), flush=True)
for c in _retry:
    items.pop(c, None)
if _retry:
    items, st = SS.fetch_extras(_retry, items, workers=3, path=SS.EXTRAS_PATH)
    print('结果: %s' % st, flush=True)
items = SS.load_extras()
_b = sum(1 for c in pool if (items.get(c) or {}).get('biz'))
_a = sum(1 for c in pool if (items.get(c) or {}).get('ann'))
print('最终覆盖：主营 %d/%d=%.1f%% ｜公告 %d/%d=%.1f%%'
      % (_b, len(pool), 100.0 * _b / len(pool), _a, len(pool), 100.0 * _a / len(pool)),
      flush=True)
_left = [c for c in pool if not (items.get(c) or {}).get('biz')]
print('仍无主营 %d 只：%s' % (len(_left), _left), flush=True)
for c in _left:
    _nm = next((r['name'] for r in rows if str(r['code']) == c), '')
    rec, ok = SS.fetch_biz(c, timeout=12)
    print('   %s %-6s 直查 ok=%s rec=%s'
          % (c, _nm, ok, bool(rec)), flush=True)
print('缓存 %.2f MB ｜ extras_missing=%d'
      % (os.path.getsize(SS.EXTRAS_PATH) / 1048576.0,
         len(SS.extras_missing(pool, items))), flush=True)
print('公告来源：%s'
      % Counter(str((items.get(c) or {}).get('ann_src') or '空') for c in pool), flush=True)
