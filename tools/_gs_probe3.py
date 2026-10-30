# -*- coding: utf-8 -*-
"""探三：多只接口是偶发失败还是频率/配额限制？附带确认最省事的 Python 通道。"""
import io
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

BASE = 'https://dgzt.guosen.com.cn/skills'
SOFT = 'agent_skills'
KEY = io.open(os.path.join(os.path.expanduser('~'), '.quantmonitor',
                           'guosen_api_key.txt'), encoding='utf-8-sig').read().strip()

_CTX = ssl._create_unverified_context()
try:
    _CTX.options |= ssl.OP_LEGACY_SERVER_CONNECT
except Exception:
    pass


def call(path, params, timeout=25):
    p = dict(params)
    p['softName'] = SOFT
    p['apiKey'] = KEY
    url = BASE + path + '?' + urllib.parse.urlencode(p)
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url), context=_CTX, timeout=timeout)
        body = r.read().decode('utf-8', 'ignore')
        return round((time.time() - t0) * 1000), json.loads(body)
    except Exception as e:
        return round((time.time() - t0) * 1000), {'_error': str(e)[:150]}


def show(tag, path, params, note=''):
    ms, d = call(path, params)
    res = d.get('result')
    if isinstance(res, list):
        res = res[0] if res else None
    obj = d.get('object')
    n = len(obj) if isinstance(obj, list) else ('dict' if isinstance(obj, dict) else str(obj))
    print('%-34s %5dms  code=%s  返回=%s  %s' % (
        tag, ms, (res or {}).get('code'), n, note))
    if not isinstance(obj, (list, dict)):
        print('      原始: %s' % json.dumps(d, ensure_ascii=False)[:230])
    return obj


print('=== 1) 单只接口重复 3 次（看是否稳定/限频）')
for i in range(3):
    show('单只 600519 #%d' % (i + 1), '/gsnews/market/agentbot/queryHQInfo/1.0',
         {'code': '600519', 'setCode': 1, 'target': 0})
    time.sleep(3)

print('\n=== 2) 多只接口重复 3 次，每次间隔 5s')
for i in range(3):
    show('多只 10 只 #%d' % (i + 1), '/gsnews/market/agentbot/queryCombHQ/1.0',
         {'code': ','.join(['600519', '000001', '300750', '002594', '601899',
                            '600030', '000858', '300059', '002415', '603501']),
          'setCode': '1,0,0,0,1,1,0,0,0,1', 'target': 0})
    time.sleep(5)

print('\n=== 3) 多只小批量 2 只 / 3 只')
show('多只 2 只', '/gsnews/market/agentbot/queryCombHQ/1.0',
     {'code': '600519,000001', 'setCode': '1,0', 'target': 0})
time.sleep(4)
show('多只 3 只', '/gsnews/market/agentbot/queryCombHQ/1.0',
     {'code': '600519,000001,300750', 'setCode': '1,0,0', 'target': 0})

print('\n=== 4) 等 45s 后再试一次多只 10 只（验证是不是短时限频）')
time.sleep(45)
show('多只 10 只（冷却后）', '/gsnews/market/agentbot/queryCombHQ/1.0',
     {'code': ','.join(['600519', '000001', '300750', '002594', '601899',
                        '600030', '000858', '300059', '002415', '603501']),
      'setCode': '1,0,0,0,1,1,0,0,0,1', 'target': 0})

print('\n=== 5) 涨幅排名（冷却后再试）')
for dom in (6, 14):
    show('排名 setDomain=%d' % dom, '/gsnews/market/agentbot/queryMultiHQ/1.0',
         {'setDomain': dom, 'wantNum': 5, 'sortType': 1, 'target': 0})
    time.sleep(4)

print('\n=== 6) 关联板块 / 资金流 各再试一次')
show('关联板块 600519', '/gsnews/market/agentbot/queryRelatedCombHQ/1.0',
     {'code': '600519', 'setCode': 1, 'target': 0})
time.sleep(3)
show('资金流 600519', '/gsnews/market/agentbot/queryFundFlow/1.0',
     {'code': '600519', 'setCode': 1, 'period': 5})
