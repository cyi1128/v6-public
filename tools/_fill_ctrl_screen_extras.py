# -*- coding: utf-8 -*-
"""为「控盘选股」当前筛选结果补「主营收入 + 最新公告」并落盘（可重跑）。

写 data/cache/ctrl_screen_extras.json（主营 TTL 30 天 / 公告 TTL 6 小时）。
只读快照 data/cache/control_screen.json，不改任何选股逻辑。
"""
import io
import os
import sys
import time
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

snap = SS.load_snapshot()
if not snap:
    print('没有快照 data/cache/control_screen.json，先跑 tools\\_rescan_ctrl_screen.py')
    sys.exit(1)

rows = SS.apply_filters(snap['rows'], min_score=85.0, pos_max=None, exclude_dist=True,
                        min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
codes = [str(r['code']) for r in rows]
print('筛选池 %d 只（控盘≥85 / 排除出货 / 价≥6 / 剔ST）｜全量 %d 只'
      % (len(codes), len(snap['rows'])), flush=True)

items = SS.load_extras()
print('补数缓存已有 %d 条' % len(items), flush=True)
miss = SS.extras_missing(codes, items)
print('需要补/过期的 %d 只' % len(miss), flush=True)

t0 = time.perf_counter()
_buf = {'n': 0}


def _p(done, total, msg):
    if done - _buf['n'] >= 100 or done == total:
        _buf['n'] = done
        print('   %s ｜ 已用 %.0fs' % (msg, time.perf_counter() - t0), flush=True)


items, stats = SS.fetch_extras(miss, items, workers=6, path=SS.EXTRAS_PATH,
                              progress_cb=_p, save_every=100)
el = time.perf_counter() - t0
print('完成: %s ｜ 墙钟 %.1fs' % (stats, el), flush=True)

print(flush=True)
print('=== 覆盖率（筛选池 %d 只）===' % len(codes), flush=True)
_biz = [c for c in codes if (items.get(c) or {}).get('biz')]
_ann = [c for c in codes if (items.get(c) or {}).get('ann')]
print('主营有数据 %d/%d = %.1f%%' % (len(_biz), len(codes), 100.0 * len(_biz) / max(1, len(codes))))
print('公告有数据 %d/%d = %.1f%%' % (len(_ann), len(codes), 100.0 * len(_ann) / max(1, len(codes))))
print('公告来源分布: %s' % Counter((items.get(c) or {}).get('ann_src') or '空' for c in codes))
print('主营报告期分布: %s' % Counter((items.get(c) or {}).get('biz_date') or '空' for c in codes))
_by_board = Counter('创业板' if c.startswith(('300', '301')) else '主板' for c in codes)
print('池内板性: %s' % dict(_by_board))
for b, pre in (('主板', ('60', '00')), ('创业板', ('30',))):
    _sub = [c for c in codes if c.startswith(pre)]
    _b = sum(1 for c in _sub if (items.get(c) or {}).get('biz'))
    _a = sum(1 for c in _sub if (items.get(c) or {}).get('ann'))
    print('   %s %d 只：主营 %d（%.0f%%）｜公告 %d（%.0f%%）'
          % (b, len(_sub), _b, 100.0 * _b / max(1, len(_sub)), _a, 100.0 * _a / max(1, len(_sub))))

print(flush=True)
print('=== 抽样 12 只（快照顺序，控盘分降序）===', flush=True)
for c in codes[:12]:
    _nm = next((r['name'] for r in rows if str(r['code']) == c), '')
    _bt, _ = SS.fmt_biz(items.get(c))
    _at, _ = SS.fmt_ann(items.get(c))
    print('   %s %-6s 主营=%-26s 公告=%s' % (c, _nm, _bt or '--', (_at or '--')[:40]), flush=True)

print(flush=True)
print('缓存文件 %s ｜ %d 字节'
      % (SS.EXTRAS_PATH, os.path.getsize(SS.EXTRAS_PATH)
         if os.path.isfile(SS.EXTRAS_PATH) else -1), flush=True)
_after = SS.extras_missing(codes, items)
print('补完后 extras_missing = %d 只（应只剩「空结果但未到重试期」以外的 0 只）' % len(_after), flush=True)
