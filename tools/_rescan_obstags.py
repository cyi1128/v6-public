# -*- coding: utf-8 -*-
"""重跑一次「控盘选股页」的全市场扫描，把五阶段标签写进快照，页面上直接能看到。

背景：快照 data/cache/control_screen.json 是 17:34 生成的，里面的行没有
stack_ok / brk_type / vreg_tags 等字段 —— 不重扫的话，打开页面看不到新建的
「建仓/洗盘/出货」类标签（只能看到旧快照里已有的 试盘/C4/C6）。
本次只是重算，不改任何阈值与筛选口径。
"""
import io
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')
import services.control_screen_service as SS

_t0 = time.time()
_las = [0.0]


def _prog(done, total, msg=''):
    now = time.time()
    if now - _las[0] >= 3.0 or done >= total:
        _las[0] = now
        print('  [%4.0fs] %d/%d %s' % (now - _t0, done, total, msg), flush=True)


rows, stats = SS.scan_market(progress_cb=_prog)
print('扫描完成：%d 只 / 耗时 %.0fs' % (len(rows), time.time() - _t0))
print('stats =', {k: stats[k] for k in list(stats)[:8]})

SS.save_snapshot(rows, stats)

from collections import Counter
_c = Counter()
_cs = Counter()
_any = 0
for r in rows:
    if r.get('observe'):
        _any += 1
    for t in (r.get('observe') or []):
        _c[t.split(':')[0]] += 1
    for s in (r.get('stages') or []):
        _cs[s] += 1
print('快照已更新 → %s' % SS.SNAPSHOT_PATH)
print('有 ≥1 标签的行 %d/%d' % (_any, len(rows)))
print('标签分布：', dict(_c.most_common()))
print('阶段分布：', dict(_cs.most_common()))

# 默认筛选下（85 分 / 排除出货 / 价格>=6 / 剔ST）页面会显示什么
_dv = SS.apply_filters(rows, min_score=85.0, pos_max=None, exclude_dist=True,
                       min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
_dv_any = sum(1 for r in _dv if r.get('observe'))
print('默认筛选后 %d 行，其中带标签 %d 行' % (len(_dv), _dv_any))
for st in SS.STAGE_OPTIONS:
    if st == '全部':
        continue
    n = len(SS.apply_filters(rows, min_score=85.0, exclude_dist=False, min_price=6.0,
                             drop_st=True, stage=st))
    print('  阶段=%-4s -> %d 行（该阶段松开排除出货后）' % (st, n))
