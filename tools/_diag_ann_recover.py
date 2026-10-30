# -*- coding: utf-8 -*-
"""探：东财公告限流恢复时间 + 巨潮兜底当前可用率（都走真实网络）。"""
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests   # noqa: E402
import services.control_screen_service as SS   # noqa: E402

print('=== 东财公告接口状态探测（每 20 秒 1 次，共 6 次）===')
for i in range(6):
    try:
        r = requests.get(SS.ANN_URL % (3, '000779'), headers=SS.ANN_HDR, timeout=8)
        body = r.text[:80].replace('\n', ' ')
        print('   [%s] 第%d次 status=%s  json可解析=%s  body=%s'
              % (time.strftime('%H:%M:%S'), i + 1, r.status_code,
                 body.startswith('{'), body[:60]), flush=True)
    except Exception as e:
        print('   [%s] 第%d次 异常 %s' % (time.strftime('%H:%M:%S'), i + 1, str(e)[:60]), flush=True)
    if i < 5:
        time.sleep(20)

print()
print('=== 巨潮兜底可用率（10 只，间隔 0.5s）===')
import json   # noqa: E402

items = SS.load_extras()
empty = [c for c in items if not (items[c].get('ann') or [])][:10]
_oem = SS.fetch_ann_em
SS.fetch_ann_em = lambda *a, **k: None      # 强制走兜底
try:
    for c in empty:
        t0 = time.perf_counter()
        lst, src = SS.fetch_ann(c)
        print('   %s  %-8s %d 条  %.2fs  %s'
              % (c, src or '(都失败)', len(lst), time.perf_counter() - t0,
                 (lst[0][1][:34] if lst else '')), flush=True)
        time.sleep(0.5)
finally:
    SS.fetch_ann_em = _oem
