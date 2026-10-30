# -*- coding: utf-8 -*-
"""国信接口第二探：批量上限 / 字段差异 / 历史多只 / Python 通道可行性。"""
import io
import json
import os
import ssl
import subprocess
import urllib.parse
import urllib.request

BASE = 'https://dgzt.guosen.com.cn/skills'
SOFT = 'agent_skills'
KEY = io.open(os.path.join(os.path.expanduser('~'), '.quantmonitor',
                           'guosen_api_key.txt'), encoding='utf-8-sig').read().strip()

POOL = ['600519', '000001', '300750', '002594', '601899', '600030', '000858', '300059',
        '002415', '603501', '601318', '600036', '000651', '002714', '600887', '601166',
        '000002', '600276', '002304', '601012', '300124', '600309', '000063', '002027',
        '600031', '601888', '300760', '002352', '600048', '601088', '000725', '002049',
        '300142', '600104', '601601', '000538', '002241', '600570', '300347', '002236',
        '600585', '601398', '000100', '002032', '300015', '600438', '601919', '000568']


def sset(code):
    if code.startswith(('6', '9')):
        return '1'
    return '0'


def call(path, params, timeout=30):
    p = dict(params)
    p['softName'] = SOFT
    p['apiKey'] = KEY
    url = BASE + path + '?' + urllib.parse.urlencode(p)
    try:
        r = subprocess.run(['curl', '-s', '-k', '--max-time', str(timeout), url],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='ignore', timeout=timeout + 10)
        return json.loads((r.stdout or '').strip())
    except Exception as e:
        return {'_error': str(e)[:160]}


print('=== A. 多只实时行情的真实上限（官方文档写 10 只）===')
for n in (10, 20, 30, 48):
    codes = ','.join(POOL[:n])
    sets = ','.join(sset(c) for c in POOL[:n])
    d = call('/gsnews/market/agentbot/queryCombHQ/1.0',
             {'code': codes, 'setCode': sets, 'target': 0})
    obj = d.get('object')
    got = len(obj) if isinstance(obj, list) else ('非列表:' + str(type(obj)))
    print('  请求 %2d 只 → 返回 %s 条  |  result=%s' % (n, got, d.get('result')))

print('\n=== B. 单只 vs 多只 的字段差异（同一只 600519）===')
one = call('/gsnews/market/agentbot/queryHQInfo/1.0',
           {'code': '600519', 'setCode': 1, 'target': 0}).get('object') or {}
multi = call('/gsnews/market/agentbot/queryCombHQ/1.0',
             {'code': '600519,000001', 'setCode': '1,0', 'target': 0}).get('object') or []
m0 = multi[0] if isinstance(multi, list) and multi else {}
print('  单只字段(%d): %s' % (len(one), sorted(one.keys())))
print('  多只字段(%d): %s' % (len(m0), sorted(m0.keys())))
print('  单只有而多只没有: %s' % sorted(set(one) - set(m0)))
print('  多只有而单只没有: %s' % sorted(set(m0) - set(one)))

print('\n=== C. 历史日K 能否一次给多只 ===')
d = call('/gsnews/market/agentbot/queryPastHQInfo/1.0',
         {'code': '600519,000001', 'setCode': '1,0', 'wantNums': 5, 'target': 0, 'mas': '5,20'})
ob = d.get('object')
print('  result=%s' % d.get('result'))
if isinstance(ob, dict):
    lst = ob.get('dailyHQList') or []
    print('  dailyHQList %d 条，字段: %s' % (len(lst), sorted(lst[0].keys()) if lst else '-'))
    print('  basicInfo: %s' % json.dumps(ob.get('basicInfo'), ensure_ascii=False)[:200])
    print('  aggregationHQList(周K?): %s' % json.dumps(ob.get('aggregationHQList'), ensure_ascii=False)[:400])
k60 = call('/gsnews/market/agentbot/queryPastHQInfo/1.0',
           {'code': '600519', 'setCode': 1, 'wantNums': 60, 'target': 0, 'mas': '5,20'})
l60 = ((k60.get('object') or {}).get('dailyHQList') or [])
if l60:
    print('  wantNums=60 实际返回 %d 根，最早 %s 最新 %s' % (len(l60), l60[0]['date'], l60[-1]['date']))

print('\n=== D. 创业板能不能查（300750）===')
d = call('/gsnews/market/agentbot/queryHQInfo/1.0', {'code': '300750', 'setCode': 0, 'target': 0})
o = d.get('object') or {}
print('  name=%s now=%s hsl=%s lb=%s date=%s' % (o.get('name'), o.get('now'), o.get('hsl'),
                                                 o.get('lb'), o.get('date')))

print('\n=== E. 涨幅排名 各 setDomain 覆盖（看是否含创业板/北交所）===')
for dom, lab in ((6, '沪深A股'), (14, '创业板'), (0, '上证A股'), (2, '深证A股')):
    d = call('/gsnews/market/agentbot/queryMultiHQ/1.0',
             {'setDomain': dom, 'wantNum': 5, 'sortType': 1, 'target': 0})
    ob = d.get('object')
    if isinstance(ob, list) and ob:
        print('  setDomain=%-3d %-8s %d 条: %s' % (dom, lab, len(ob),
              ', '.join('%s(%s %s%%)' % (x.get('name'), x.get('code'), x.get('priceChangePct'))
                        for x in ob[:5])))
        print('        字段: %s' % sorted(ob[0].keys()))
    else:
        print('  setDomain=%-3d %-8s → %s' % (dom, lab, d.get('result')))

print('\n=== F. Python 通道可行性（requests / 不校验上下文）===')
try:
    import requests
    print('  requests 已安装: %s' % requests.__version__)
    r = requests.get(BASE + '/gsnews/market/agentbot/queryHQInfo/1.0',
                     params={'code': '600519', 'setCode': 1, 'softName': SOFT, 'apiKey': KEY},
                     verify=False, timeout=20)
    print('  requests(verify=False) → HTTP %s  %s' % (r.status_code, r.text[:90]))
except ImportError:
    print('  requests 未安装')
except Exception as e:
    print('  requests 失败: %s' % str(e)[:150])

try:
    ctx = ssl._create_unverified_context()
    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    r = urllib.request.urlopen(urllib.request.Request(
        BASE + '/gsnews/market/agentbot/queryHQInfo/1.0?code=600519&setCode=1'
               '&softName=agent_skills&apiKey=' + urllib.parse.quote(KEY, safe='')),
        context=ctx, timeout=20)
    print('  urllib(_create_unverified_context+legacy) → OK %s' % r.read().decode('utf-8')[:90])
except Exception as e:
    print('  urllib(_create_unverified_context+legacy) → 失败: %s' % str(e)[:150])
