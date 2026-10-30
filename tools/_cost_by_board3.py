# -*- coding: utf-8 -*-
"""把 4404 → 3294 那 1110 只按单个条件拆开（上一次拆解写错了：第一档就带了默认勾）。

每个场景都显式给全部参数，不用默认值，避免再踩同一个坑。
"""
import os
import sys
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS  # noqa: E402

snap = SS.load_snapshot()
rows = snap['rows']
items = SS.load_extras()

B = dict(min_score=0.0, pos_max=None, exclude_dist=False, min_price=0.0, drop_st=False,
         obs=SS.OBS_ALL)
_full = SS.apply_filters(rows, **B)
print('基准（门槛0 / 不排出货 / 不限价 / 不剔ST）：%d 只' % len(_full))

scen = [
    ('只加「排除出货」', dict(B, exclude_dist=True)),
    ('只加「价格≥6」', dict(B, min_price=6.0)),
    ('只加「剔除ST」', dict(B, drop_st=True)),
    ('排出货+价≥6', dict(B, exclude_dist=True, min_price=6.0)),
    ('排出货+剔ST', dict(B, exclude_dist=True, drop_st=True)),
    ('价≥6+剔ST', dict(B, min_price=6.0, drop_st=True)),
    ('三勾全开=页面默认', dict(B, exclude_dist=True, min_price=6.0, drop_st=True)),
]
for name, kw in scen:
    p = SS.apply_filters(rows, **kw)
    print('   %-22s 池=%5d（砍掉 %4d）' % (name, len(p), len(_full) - len(p)))

print('\n-- 三个条件各自真正砍掉的是哪些（互斥归属：逐个判定它被哪条规则挡掉）--')
_d = _e = _p6 = _st = 0
for r in _full:
    if str(r.get('stage')) == 'distribute':
        _d += 1
    elif SS.is_st_name(r.get('name')):
        _st += 1
    elif float(r.get('price') or 0) < 6.0:
        _p6 += 1
    else:
        _e += 1
print('   出货(distribute)=%d ｜ ST=%d ｜ 价格<6=%d ｜ 都不满足(默认池)=%d'
      % (_d, _st, _p6, _e))

print('\n-- 三勾全开时按板块 --')
p = SS.apply_filters(rows, **dict(B, exclude_dist=True, min_price=6.0, drop_st=True))
for b, pre in (('主板', ('60', '00')), ('创业板', ('300', '301'))):
    sub = [r for r in p if str(r['code']).startswith(pre)]
    has = sum(1 for r in sub if str(r['code']) in items)
    print('   %-5s 池=%5d 已有=%5d 待补=%5d' % (b, len(sub), has, len(sub) - has))

print('\n-- 全量（三勾全不勾）时按板块 --')
for b, pre in (('主板', ('60', '00')), ('创业板', ('300', '301'))):
    sub = [r for r in _full if str(r['code']).startswith(pre)]
    has = sum(1 for r in sub if str(r['code']) in items)
    print('   %-5s 池=%5d 已有=%5d 待补=%5d' % (b, len(sub), has, len(sub) - has))
