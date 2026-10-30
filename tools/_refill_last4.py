# -*- coding: utf-8 -*-
"""把最后 4 只重取一次，并用正确的键（biz_items）判定上游到底有没有。"""
import os
import sys

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

snap = SS.load_snapshot()
pool = [str(r['code']) for r in snap['rows']
        if float(r.get('score') or 0) >= 0.0
        and str(r.get('stage')) != 'distribute'
        and float(r.get('price') or 0) >= 6.0
        and not SS.is_st_name(r.get('name'))]
items = SS.load_extras()
_left = [c for c in pool if not (items.get(c) or {}).get('biz')]
print('重取前仍无主营：%s' % _left, flush=True)
for c in _left:
    items.pop(c, None)
if _left:
    items, st = SS.fetch_extras(_left, items, workers=2, path=SS.EXTRAS_PATH)
    print('重取结果: %s' % st, flush=True)
items = SS.load_extras()
print(flush=True)
for c in _left:
    _r = items.get(c) or {}
    _n = len(_r.get('biz_items') or [])
    _nm = next((r['name'] for r in snap['rows'] if str(r['code']) == c), '')
    print('   %s %-6s biz=%-8s biz_items=%d report=%s fail=%s'
          % (c, _nm, repr(_r.get('biz')), _n, _r.get('biz_date'), _r.get('biz_fail')),
          flush=True)
_b = sum(1 for c in pool if (items.get(c) or {}).get('biz'))
_a = sum(1 for c in pool if (items.get(c) or {}).get('ann'))
print(flush=True)
print('最终覆盖：主营 %d/%d=%.1f%% ｜ 公告 %d/%d=%.1f%%'
      % (_b, len(pool), 100.0 * _b / len(pool), _a, len(pool), 100.0 * _a / len(pool)),
      flush=True)
print('仍无主营：%s' % [c for c in pool if not (items.get(c) or {}).get('biz')], flush=True)
print('extras_missing=%d ｜ 缓存 %.2f MB'
      % (len(SS.extras_missing(pool, items)),
         os.path.getsize(SS.EXTRAS_PATH) / 1048576.0), flush=True)
