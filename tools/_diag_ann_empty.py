# -*- coding: utf-8 -*-
"""诊断：978 只里 478 只公告为空 —— 是限流/暂时失败，还是上游真没公告？"""
import io
import json
import os
import random
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

items = SS.load_extras()
codes = list(items.keys())
empty = [c for c in codes if not (items[c].get('ann') or [])]
got = [c for c in codes if (items[c].get('ann') or [])]
print('总 %d ｜ 有公告 %d ｜ 空 %d' % (len(codes), len(got), len(empty)))

# 快照顺序（= 补数顺序）上看空/有是否成段
snap = SS.load_snapshot()
rows = SS.apply_filters(snap['rows'], min_score=85.0)
order = [str(r['code']) for r in rows if str(r['code']) in items]
_seq = ''.join('1' if (items[c].get('ann') or []) else '0' for c in order)
print('补数顺序上的「有/空」序列（1=有，0=空，共 %d）：' % len(_seq))
for i in range(0, len(_seq), 98):
    print('   %4d-%4d %s' % (i + 1, min(i + 98, len(_seq)), _seq[i:i + 98]))

print()
print('=== 对 12 只「空」的现在单独重查（各 2 次，间隔 0.4s）===')
random.seed(7)
_pick = empty[:6] + random.sample(empty, 6)
for c in _pick:
    r1 = SS.fetch_ann_em(c, count=3)
    time.sleep(0.4)
    r2 = SS.fetch_ann_em(c, count=3)
    print('   %s  第1次=%-5s 第2次=%-5s  条数=%s'
          % (c, ('None' if r1 is None else len(r1)), ('None' if r2 is None else len(r2)),
             (len(r2) if r2 else 0)))

print()
print('=== 对照：对 6 只「有」的重查是否稳定 ===')
for c in got[:6]:
    r = SS.fetch_ann_em(c, count=3)
    print('   %s 条数=%s' % (c, ('None' if r is None else len(r))))

print()
print('=== 直接打原始 HTTP 看返回内容（1 只空的）===')
import requests   # noqa: E402
c = empty[0]
u = SS.ANN_URL % (3, c)
resp = requests.get(u, headers=SS.ANN_HDR, timeout=8)
print('   code=%s status=%s len=%d' % (c, resp.status_code, len(resp.text)))
print('   body: %s' % resp.text[:300].replace('\n', ' '))
j = resp.json()
print('   data=%s' % (str(j.get('data'))[:200] if j.get('data') else 'None'))
print('   success=%s error=%s' % (j.get('success'), str(j.get('error'))[:100]))
