# -*- coding: utf-8 -*-
"""核查「去掉 排出货/价格≥6/剔ST 三个勾」后的最大池，并按板块拆待补（只读）。"""
import os
import sys
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS  # noqa: E402


def board(code):
    c = str(code)
    if c.startswith(('60', '00')):
        return '主板'
    if c.startswith(('300', '301')):
        return '创业板'
    if c.startswith(('688', '689')):
        return '科创板'
    if c.startswith(('8', '4', '920')):
        return '北交所'
    return '其他'


snap = SS.load_snapshot()
rows = snap['rows']
items = SS.load_extras()

print('-- 页面允许的全部勾选组合下，池子上限 --')
_all = SS.apply_filters(rows, min_score=0.0, pos_max=None, exclude_dist=False,
                        min_price=0.0, drop_st=False, obs=SS.OBS_ALL)
print('   min_score=0 且三勾全不勾：池=%d（快照行数=%d）' % (len(_all), len(rows)))
for b in ('主板', '创业板'):
    sub = [r for r in _all if board(str(r['code'])) == b]
    has = sum(1 for r in sub if str(r['code']) in items)
    print('   %-6s 池=%5d 已有=%5d 待补=%5d' % (b, len(sub), has, len(sub) - has))
print('   %-6s 池=%5d 已有=%5d 待补=%5d'
      % ('合计', len(_all), sum(1 for r in _all if str(r['code']) in items),
         len([r for r in _all if str(r['code']) not in items])))

print('\n-- 那 1110 只差在哪（同一门槛逐勾拆）--')
_base = SS.apply_filters(rows, min_score=0.0, pos_max=None, exclude_dist=False,
                         min_price=0.0, drop_st=False, obs=SS.OBS_ALL)
for name, kw in (('+排出货', dict(exclude_dist=True)),
                 ('+排出货+价≥6', dict(exclude_dist=True, min_price=6.0)),
                 ('+排出货+价≥6+剔ST', dict(exclude_dist=True, min_price=6.0, drop_st=True))):
    _p = SS.apply_filters(rows, min_score=0.0, pos_max=None, obs=SS.OBS_ALL, **kw)
    print('   门槛=0 %-20s 池=%5d（比上一档少 %d）' % (name, len(_p), len(_base) - len(_p)))
    _base = _p

print('\n-- 三勾全不勾时的待补板块构成 --')
_miss = [c for c in [str(r['code']) for r in rows] if c not in items]
print('   待补=%d ｜ 板块：%s' % (len(_miss), dict(Counter(board(c) for c in _miss))))
