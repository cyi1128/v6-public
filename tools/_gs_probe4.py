# -*- coding: utf-8 -*-
"""探四：批量真正上限 / 字段差异 / 并发吞吐（决定能不能用于批量场景）。"""
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

POOL = ['600519', '000001', '300750', '002594', '601899', '600030', '000858', '300059',
        '002415', '603501', '601318', '600036', '000651', '002714', '600887', '601166',
        '000002', '600276', '002304', '601012', '300124', '600309', '000063', '002027',
        '600031', '601888', '300760', '002352', '600048', '601088', '000725', '002049',
        '300142', '600104', '601601', '000538', '002241', '600570', '300347', '002236',
        '600585', '601398', '000100', '002032', '300015', '600438', '601919', '000568',
        '688981', '603259', '002050', '300274', '600941', '601728', '000733', '002812',
        '300316', '600460', '601865', '002271', '300450', '600745', '002460', '603986',
        '000776', '300433', '600183', '002475', '300496', '600584', '002371', '603160',
        '300699', '600089', '002916', '300033', '600111', '601138', '000988', '002241']


def sset(c):
    return '1' if c.startswith(('6', '9')) else '0'


def call(path, params, timeout=25):
    p = dict(params)
    p['softName'] = SOFT
    p['apiKey'] = KEY
    url = BASE + path + '?' + urllib.parse.urlencode(p)
    try:
        r = urllib.request.urlopen(urllib.request.Request(url), context=_CTX, timeout=timeout)
        return json.loads(r.read().decode('utf-8', 'ignore'))
    except Exception as e:
        return {'_error': str(e)[:120]}


def rows(d):
    if isinstance(d.get('data'), list):
        return d['data']
    o = d.get('object')
    return o if isinstance(o, list) else []


print('=== A. 多只实时行情真实上限（正确读 data）===')
for n in (10, 20, 30, 48, 80):
    codes = POOL[:n]
    d = call('/gsnews/market/agentbot/queryCombHQ/1.0',
             {'code': ','.join(codes), 'setCode': ','.join(sset(c) for c in codes), 'target': 0})
    r = rows(d)
    nm = [x.get('name') for x in r[-2:]] if r else []
    print('  请求 %2d 只 → 返回 %2d 条 ｜ 末尾: %s ｜ result=%s'
          % (n, len(r), nm, (d.get('result') or {}).get('code')))

print('\n=== B. 单只 vs 多只 字段差异（600519）===')
one = call('/gsnews/market/agentbot/queryHQInfo/1.0',
           {'code': '600519', 'setCode': 1, 'target': 0}).get('object') or {}
multi = rows(call('/gsnews/market/agentbot/queryCombHQ/1.0',
                  {'code': '600519,000001', 'setCode': '1,0', 'target': 0}))
m0 = multi[0] if multi else {}
print('  单只 %d 字段: %s' % (len(one), sorted(one.keys())))
print('  多只 %d 字段: %s' % (len(m0), sorted(m0.keys())))
print('  ★单只独有（多只拿不到）: %s' % sorted(set(one) - set(m0)))

print('\n=== C. 涨幅排名 wantNum 上限 ===')
for wn in (10, 80, 200):
    d = call('/gsnews/market/agentbot/queryMultiHQ/1.0',
             {'setDomain': 6, 'wantNum': wn, 'sortType': 1, 'target': 0})
    r = rows(d)
    print('  wantNum=%-3d → %d 条 ｜ 首行 %s ｜ 字段 %d 个'
          % (wn, len(r), (r[0].get('name') + ' ' + str(r[0].get('code'))) if r else '-',
             len(r[0]) if r else 0))

print('\n=== D. 并发吞吐（单只接口，8 线程 × 200 只）===')
codes = POOL[:80] * 3      # 240 次请求


def one_call(c):
    t0 = time.time()
    d = call('/gsnews/market/agentbot/queryHQInfo/1.0', {'code': c, 'setCode': sset(c), 'target': 0})
    o = d.get('object') if isinstance(d.get('object'), dict) else {}
    return (bool(o.get('now')), round((time.time() - t0) * 1000))


t0 = time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    rs = list(ex.map(one_call, codes))
el = time.time() - t0
ok = sum(1 for a, _ in rs if a)
lat = sorted(b for a, b in rs if a)
print('  请求 %d 次 ｜ 成功 %d ｜ 失败 %d ｜ 总耗时 %.1fs ｜ 平均 %.0fms/只 '
      '｜ P50 %.0fms ｜ P95 %.0fms'
      % (len(codes), ok, len(codes) - ok, el, el / len(codes) * 1000,
         lat[len(lat) // 2] if lat else -1, lat[int(len(lat) * 0.95)] if lat else -1))
print('  → 按此速率推算：100 只约 %.0fs，1000 只约 %.1f 分钟，4400 只约 %.1f 分钟'
      % (el / len(codes) * 100, el / len(codes) * 1000 / 60, el / len(codes) * 4400 / 60))

print('\n=== E. 其他板块覆盖（科创板 688981 / 北交所 920157）===')
for c, sc in (('688981', 1), ('920157', 2), ('603259', 1)):
    o = call('/gsnews/market/agentbot/queryHQInfo/1.0',
             {'code': c, 'setCode': sc, 'target': 0}).get('object') or {}
    print('  %s → name=%s now=%s hsl=%s lb=%s' % (c, o.get('name'), o.get('now'),
                                                  o.get('hsl'), o.get('lb')))
