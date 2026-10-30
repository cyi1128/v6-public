# -*- coding: utf-8 -*-
"""探五：限频恢复时间 / 安全并发 / 串行真实速率 / 各板块覆盖。"""
import io
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = 'https://dgzt.guosen.com.cn/skills'
SOFT = 'agent_skills'
KEY = io.open(os.path.join(os.path.expanduser('~'), '.quantmonitor',
                           'guosen_api_key.txt'), encoding='utf-8-sig').read().strip()
_CTX = ssl._create_unverified_context()
try:
    _CTX.options |= ssl.OP_LEGACY_SERVER_CONNECT
except Exception:
    pass


def call(code, setc=1, timeout=15):
    url = (BASE + '/gsnews/market/agentbot/queryHQInfo/1.0?' +
           urllib.parse.urlencode({'code': code, 'setCode': setc, 'target': 0,
                                   'softName': SOFT, 'apiKey': KEY}))
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url), context=_CTX, timeout=timeout)
        d = json.loads(r.read().decode('utf-8', 'ignore'))
        o = d.get('object') if isinstance(d.get('object'), dict) else {}
        return (bool(o.get('name')), round((time.time() - t0) * 1000), o.get('name'))
    except Exception as e:
        return (False, round((time.time() - t0) * 1000), str(e)[:40])


print('=== 1) 立即打一次（检查刚才 240 并发后是否仍被封）===')
print('  600519 → %s' % str(call('600519')))

print('\n=== 2) 冷却 60s 后，各板块覆盖 ===')
time.sleep(60)
for c, sc, lab in (('600519', 1, '沪主板'), ('300750', 0, '创业板'), ('688981', 1, '科创板'),
                   ('920157', 2, '北交所'), ('000001', 0, '深主板'), ('001979', 0, '深主板001')):
    ok, ms, nm = call(c, sc)
    print('  %-8s %s setCode=%d → ok=%s %s (%dms)' % (lab, c, sc, ok, nm, ms))
    time.sleep(1)

print('\n=== 3) 串行 30 次（真实可持续速率）===')
POOL = ['600519', '000001', '300750', '002594', '601899', '600030', '000858', '300059',
        '002415', '603501', '601318', '600036', '000651', '002714', '600887', '601166',
        '000002', '600276', '002304', '601012', '300124', '600309', '000063', '002027',
        '600031', '601888', '300760', '002352', '600048', '601088']
t0 = time.time()
rs = [call(c, 1 if c.startswith('6') else 0) for c in POOL]
el = time.time() - t0
ok = sum(1 for a, _, _ in rs if a)
lat = sorted(b for a, b, _ in rs)
print('  30 次串行：成功 %d/30 ｜ 总 %.1fs ｜ 平均 %.0fms ｜ P95 %.0fms'
      % (ok, el, el / 30 * 1000, lat[int(29 * 0.95)]))
print('  → 4400 只串行约 %.1f 分钟' % (el / 30 * 4400 / 60))

print('\n=== 4) 并发 2 线程 × 20 只（找安全并发）===')
time.sleep(10)
codes = POOL[:20]
t0 = time.time()
with ThreadPoolExecutor(max_workers=2) as ex:
    rs2 = list(ex.map(lambda c: call(c, 1 if c.startswith('6') else 0), codes))
el2 = time.time() - t0
print('  2 线程 20 次：成功 %d/20 ｜ 总 %.1fs ｜ 平均 %.0fms'
      % (sum(1 for a, _, _ in rs2 if a), el2, el2 / 20 * 1000))

print('\n=== 5) 并发 4 线程 × 20 只 ===')
time.sleep(10)
t0 = time.time()
with ThreadPoolExecutor(max_workers=4) as ex:
    rs3 = list(ex.map(lambda c: call(c, 1 if c.startswith('6') else 0), codes))
el3 = time.time() - t0
fail = [x for x in rs3 if not x[0]]
print('  4 线程 20 次：成功 %d/20 ｜ 总 %.1fs ｜ 失败样本: %s'
      % (sum(1 for a, _, _ in rs3 if a), el3, fail[:3]))
