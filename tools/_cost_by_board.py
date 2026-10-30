# -*- coding: utf-8 -*-
"""按板块拆解控盘选股页的池子与待补数（只读）。板块判定用与页面一致的口径。"""
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
    return '其他:' + c[:3]


snap = SS.load_snapshot()
rows = snap['rows']
items = SS.load_extras()
codes = [str(c) for c in (snap.get('codes') or [])] or [str(r['code']) for r in rows]

print('快照 saved_at=%s ｜ 行数=%d ｜ codes=%d'
      % (snap.get('saved_at'), len(rows), len(codes)))
print('\n-- 快照全市场的板块构成（证明池子到底是哪些板）--')
for b, n in Counter(board(c) for c in codes).most_common():
    print('   %-8s %5d' % (b, n))

print('\n-- 全市场可达上限（控盘分门槛=0，其余条件同页面默认）--')
pool0 = SS.apply_filters(rows, min_score=0.0, pos_max=None, exclude_dist=True,
                         min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
for b in ('主板', '创业板'):
    sub = [r for r in pool0 if board(str(r['code'])) == b]
    has = sum(1 for r in sub if str(r['code']) in items)
    print('   %-8s 池=%5d ｜ 已有=%5d ｜ 待补=%5d' % (b, len(sub), has, len(sub) - has))
print('   %-8s 池=%5d ｜ 已有=%5d ｜ 待补=%5d'
      % ('合计', len(pool0), sum(1 for r in pool0 if str(r['code']) in items),
         len([r for r in pool0 if str(r['code']) not in items])))

print('\n-- 待补清单里根本没算控盘分的（任何条件都进不了表）--')
_notin = [c for c in codes if c not in {str(r['code']) for r in rows}]
print('   待补总数(全市场)=%d ｜ 进不了表的=%d'
      % (len(SS.extras_missing(codes, items)), len(_notin)))
print('   进不了表的板块构成：', dict(Counter(board(c) for c in _notin)))

print('\n-- 各门槛下按板块的池子 / 待补 --')
print('   %-12s %-16s %-16s %-10s' % ('门槛', '主板 池/待补', '创业板 池/待补', '合计待补'))
for th in (0.0, 70.0, 80.0, 85.0, 90.0):
    p = SS.apply_filters(rows, min_score=th, pos_max=None, exclude_dist=True,
                         min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
    _m = [r for r in p if board(str(r['code'])) == '主板']
    _c = [r for r in p if board(str(r['code'])) == '创业板']
    _md = len([r for r in _m if str(r['code']) not in items])
    _cd = len([r for r in _c if str(r['code']) not in items])
    print('   >=%-10.0f %-16s %-16s %-10d'
          % (th, '%d/%d' % (len(_m), _md), '%d/%d' % (len(_c), _cd), _md + _cd))

print('\n-- 已补 993 只的板块与来源 --')
_by = Counter(board(c) for c in items)
print('   已补板块：', dict(_by))
print('   公告来源：', dict(Counter(str(v.get('ann_src') or '?')
                                   for v in items.values() if v.get('ann'))))
