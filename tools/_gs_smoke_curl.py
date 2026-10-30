# -*- coding: utf-8 -*-
"""国信证券 skill 接口冒烟测试（curl 通道；官方脚本同款兜底）。

- 只读，不改动 QuantMonitorV6 任何业务文件
- key 从 ~/.quantmonitor/guosen_api_key.txt 读，全程不打印 key
- 结果落 tools\\_gs_smoke_raw.json
"""
import io
import json
import os
import subprocess
import time
import urllib.parse

BASE = 'https://dgzt.guosen.com.cn/skills'
SOFT = 'agent_skills'
ROOT = r'D:\QuantMonitorV6'

KEY = io.open(os.path.join(os.path.expanduser('~'), '.quantmonitor',
                           'guosen_api_key.txt'), encoding='utf-8-sig').read().strip()
print('key 长度 %d ｜ 前 4 位 %s...\n' % (len(KEY), KEY[:4]))
RAW = {}


def call(name, path, params, timeout=30):
    p = dict(params)
    p['softName'] = SOFT
    p['apiKey'] = KEY
    url = BASE + path + '?' + urllib.parse.urlencode(p)
    safe = {k: v for k, v in params.items()}
    t0 = time.time()
    try:
        r = subprocess.run(['curl', '-s', '-k', '--max-time', str(timeout), url],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='ignore', timeout=timeout + 10)
        ms = (time.time() - t0) * 1000
        body = (r.stdout or '').strip()
        try:
            d = json.loads(body)
        except Exception:
            d = {'_raw': body[:600]}
    except Exception as e:
        ms = (time.time() - t0) * 1000
        d = {'_error': str(e)[:200]}
    RAW[name] = {'endpoint': path, 'params': safe, 'elapsed_ms': round(ms), 'resp': d}

    res = d.get('result')
    if isinstance(res, list):
        res = res[0] if res else res
    code = res.get('code') if isinstance(res, dict) else None
    msg = res.get('msg') if isinstance(res, dict) else ''
    obj = d.get('object') if 'object' in d else d.get('data')
    shape = ''
    if isinstance(obj, dict):
        shape = 'object字典(%d键): %s' % (len(obj), list(obj.keys())[:10])
    elif isinstance(obj, list):
        shape = 'object列表(%d条)' % len(obj)
    print('── %-28s %.0fms  code=%s %s  %s' % (name, ms, code, msg, shape))
    print('   %s' % json.dumps(obj if obj is not None else d, ensure_ascii=False)[:520].replace('\n', ' '))
    return d


print('=' * 108)
call('1_单只实时行情', '/gsnews/market/agentbot/queryHQInfo/1.0',
     {'code': '600519', 'setCode': 1, 'target': 0})

call('2_多只实时行情_10只', '/gsnews/market/agentbot/queryCombHQ/1.0',
     {'code': '600519,000001,300750,002594,601899,600030,000858,300059,002415,603501',
      'setCode': '1,0,0,0,1,1,0,0,0,1', 'target': 0})

call('3_多只实时行情_11只超限', '/gsnews/market/agentbot/queryCombHQ/1.0',
     {'code': '600519,000001,300750,002594,601899,600030,000858,300059,002415,603501,601318',
      'setCode': '1,0,0,0,1,1,0,0,0,1,1', 'target': 0})

call('4_历史日K_20根带MA', '/gsnews/market/agentbot/queryPastHQInfo/1.0',
     {'code': '600519', 'setCode': 1, 'wantNums': 20, 'target': 0, 'mas': '5,10,20'})

call('5_资金流_5日', '/gsnews/market/agentbot/queryFundFlow/1.0',
     {'code': '600519', 'setCode': 1, 'period': 5})

call('6_涨幅排名_沪深A股前10', '/gsnews/market/agentbot/queryMultiHQ/1.0',
     {'setDomain': 6, 'wantNum': 10, 'sortType': 1, 'target': 0})

call('7_个股关联板块', '/gsnews/market/agentbot/queryRelatedCombHQ/1.0',
     {'code': '600519', 'setCode': 1, 'target': 0})

call('8_利润表_最新', '/gsnews/gsf10/financial/incomeStatement/1.0',
     {'code': '600519', 'market': 'SH', 'reportType': 'Q0', 'count': '1'})

call('9_智能选股', '/agent/mcp/smart_stock_picking',
     {'searchstring': '市盈率小于20的银行股', 'searchtype': 'stock'})

call('10_宏观_CPI', '/agent/adapter/query', {'text': '最新CPI数据'}, timeout=45)

with io.open(os.path.join(ROOT, 'tools', '_gs_smoke_raw.json'), 'w', encoding='utf-8') as f:
    json.dump(RAW, f, ensure_ascii=False, indent=1)
print('\n原始返回: tools\\_gs_smoke_raw.json（已剔除 apiKey）')
