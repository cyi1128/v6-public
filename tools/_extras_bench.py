# -*- coding: utf-8 -*-
"""压测：控盘选股「主营收入 + 最新公告」并发补数（只读快照，写独立缓存文件）。"""
import io
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

BENCH = os.path.join(ROOT, 'data', 'cache', '_bench_extras.json')
if os.path.isfile(BENCH):
    os.remove(BENCH)

snap = SS.load_snapshot()
rows = SS.apply_filters(snap['rows'], min_score=85.0)
codes = [r['code'] for r in rows[:40]]
print('样本 %d 只（控盘≥85 池前 40）：%s' % (len(codes), ','.join(codes[:8])), flush=True)

t0 = time.perf_counter()
items, stats = SS.fetch_extras(codes, {}, workers=6, path=BENCH, save_every=20,
                              progress_cb=lambda d, t, m: None)
print('统计: %s' % stats, flush=True)
print('总耗时 %.1fs ｜ 单只均 %.3fs（6 线程）'
      % (time.perf_counter() - t0, (time.perf_counter() - t0) / max(1, len(codes))), flush=True)

_bz = sum(1 for c in codes if items.get(c, {}).get('biz'))
_an = sum(1 for c in codes if items.get(c, {}).get('ann'))
print('主营命中 %d/%d ｜ 公告命中 %d/%d' % (_bz, len(codes), _an, len(codes)), flush=True)

print('抽样 6 只：', flush=True)
for c in codes[:6]:
    bt, btip = SS.fmt_biz(items.get(c))
    at, atip = SS.fmt_ann(items.get(c))
    print('   %s 主营=%s ｜ 公告=%s' % (c, bt or '--', (at or '--')[:44]), flush=True)
    if btip:
        print('        biz tip: %s' % btip.split('\n')[1][:70], flush=True)
    if atip:
        print('        ann tip: %s' % atip.split('\n')[1][:70], flush=True)

# TTL 逻辑自检
_miss = SS.extras_missing(codes, items)
print('刚补完后 extras_missing = %d 只（应为 0）' % len(_miss), flush=True)
_old = dict(items)
for c in list(_old)[:3]:
    _old[c]['ann_ts'] = 0
print('把 3 只公告时间戳归零后 extras_missing = %d（应为 3）'
      % len(SS.extras_missing(codes, _old)), flush=True)
print('缓存文件: %s (%d 字节)' % (BENCH, os.path.getsize(BENCH)), flush=True)
