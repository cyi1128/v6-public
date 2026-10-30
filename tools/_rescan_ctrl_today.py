# -*- coding: utf-8 -*-
"""重扫控盘选股快照，并用今天的数据对照昨天的数据（可重跑）。
只读 kline_cache + 重算 + 覆写 data/cache/control_screen.json，不改任何阈值/口径。
"""
import collections
import io
import json
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

SNAP = 'data/cache/control_screen.json'

# 1) 先把旧快照的关键数字记下来（对照用）
old = json.load(io.open(SNAP, 'r', encoding='utf-8')) if os.path.exists(SNAP) else {}
old_rows = old.get('rows') or []
tgt = ('000811', '002838', '600172', '600519', '603011')
old_sample = {c: next(((r.get('price'), r.get('pct'), r.get('score')) for r in old_rows
                       if r.get('code') == c), None) for c in tgt}
print('【改前】saved_at=%s data_date=%s rows=%d' % (old.get('saved_at'), old.get('data_date'), len(old_rows)))
for c, v in old_sample.items():
    print('   %s -> %s' % (c, v))

# 2) 重扫（读本地 kline_cache，只读）
import services.control_screen_service as SS  # noqa: E402

_t0 = time.time()
_las = [0.0]


def _prog(done, total, msg=''):
    now = time.time()
    if now - _las[0] >= 5.0 or done >= total:
        _las[0] = now
        print('  [%5.0fs] %d/%d %s' % (now - _t0, done, total, msg), flush=True)


rows, stats = SS.scan_market(progress_cb=_prog)
print('重扫完成: %d 只 / %.0fs / stats.data_date=%s' % (len(rows), time.time() - _t0, stats.get('data_date')))
SS.save_snapshot(rows, stats)

# 3) 对照
new = json.load(io.open(SNAP, 'r', encoding='utf-8'))
print('=' * 78)
print('【改后】saved_at=%s data_date=%s rows=%d' % (new.get('saved_at'), new.get('data_date'), len(new.get('rows') or [])))
dd = collections.Counter(r.get('data_date') for r in rows)
print('行内 data_date 分布(前5):', dd.most_common(5))
sc_old = sorted([r.get('score') or 0 for r in old_rows])
sc_new = sorted([r.get('score') or 0 for r in rows])
if sc_old:
    print('控盘分 中位 %.1f -> %.1f | >=85: %d -> %d 只' % (
        sc_old[len(sc_old) // 2], sc_new[len(sc_new) // 2],
        sum(1 for x in sc_old if x >= 85), sum(1 for x in sc_new if x >= 85)))
for c in tgt:
    nv = next(((r.get('name'), r.get('price'), r.get('pct'), r.get('score')) for r in rows
               if r.get('code') == c), None)
    print('   %s: %s  ->  %s' % (c, old_sample.get(c), nv))
_c = collections.Counter()
for r in rows:
    for t in (r.get('observe') or []):
        _c[t.split(':')[0]] += 1
print('标签分布:', dict(_c.most_common()))
