# -*- coding: utf-8 -*-
"""重新全市场扫描控盘选股快照（含涨停题材）。可重跑。

只读 kline_cache.duckdb + 只读 data/limit_up_reason.db，写 data/cache/control_screen.json。
"""
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

import services.control_screen_service as SS   # noqa: E402

t0 = time.perf_counter()
bars = SS.load_all_bars()
print('批量读K线: %d 只 / %.1fs' % (len(bars), time.perf_counter() - t0), flush=True)

rows, stats = SS.scan_market(bars=bars)
print('扫描: %s' % stats, flush=True)

p = SS.save_snapshot(rows, stats)
print('快照: %s (%d 字节)' % (p, os.path.getsize(p) if p else -1), flush=True)

_n = sum(1 for r in rows if r.get('theme'))
print('有题材: %d / %d (%.1f%%)' % (_n, len(rows), _n * 100.0 / max(1, len(rows))), flush=True)
print('抽样 8 只:')
for r in rows[:8]:
    print('   %s %s 控盘%s 题材=%s (%s, %s连板, %s)'
          % (r['code'], r['name'], r['score'], r.get('theme') or '--',
             r.get('theme_date') or '-', r.get('theme_lbc') or 0,
             r.get('theme_ind') or '-'), flush=True)
_f = SS.apply_filters(rows, min_score=85.0)
_t = sum(1 for r in _f if r.get('theme'))
print('控盘≥85 排出货后: %d 只，其中有题材 %d 只 (%.1f%%)'
      % (len(_f), _t, _t * 100.0 / max(1, len(_f))), flush=True)
print('总耗时 %.1fs' % (time.perf_counter() - t0), flush=True)
