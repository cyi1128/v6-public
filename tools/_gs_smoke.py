# -*- coding: utf-8 -*-
"""国信证券 skill 接口冒烟测试（只读，不改动 QuantMonitorV6 任何文件）。

key 读取顺序（永不打印 key 本身）：
  1) 环境变量 GS_API_KEY
  2) C:\\Users\\<用户>\\.quantmonitor\\guosen_api_key.txt   （放项目外，不进 backups/）
  3) <项目>\\config\\guosen_api_key.txt

输出：每个接口的耗时、成功与否、关键字段摘要；完整原始返回落 tools\\_gs_smoke_raw.json。
"""
import io
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

BASE = 'https://dgzt.guosen.com.cn/skills'
SOFT = 'agent_skills'
ROOT = r'D:\QuantMonitorV6'
RAW = {}


def load_key():
    k = os.environ.get('GS_API_KEY', '').strip()
    if k:
        return k, 'env:GS_API_KEY'
    cands = [
        os.path.join(os.path.expanduser('~'), '.quantmonitor', 'guosen_api_key.txt'),
        os.path.join(ROOT, 'config', 'guosen_api_key.txt'),
    ]
    for p in cands:
        if os.path.isfile(p):
            with io.open(p, encoding='utf-8-sig') as f:
                v = f.read().strip()
            if v:
                return v, p
    return '', '(未找到)'


KEY, KEY_SRC = load_key()
print('key 来源: %s ｜ 长度 %d ｜ 前 4 位 %s' % (KEY_SRC, len(KEY), KEY[:4] + '...' if KEY else '-'))

_CTX = None


def _make_ctx(verify=True):
    """国信服务端是老 TLS，需要 OP_LEGACY_SERVER_CONNECT。
    先试「保留证书校验」，只有握手仍失败才降级为不校验（与原脚本一致）。"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    except Exception:
        pass
    try:
        ctx.set_ciphers('ALL:@SECLEVEL=0')
    except Exception:
        pass
    if verify:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


for _v in (True, False):
    try:
        _t = urllib.request.urlopen(
            urllib.request.Request(BASE + '/gsnews/market/agentbot/queryHQInfo/1.0'
                                   '?code=600519&setCode=1&softName=agent_skills&apiKey=ping'),
            context=_make_ctx(_v), timeout=15)
        _t.read()
        _CTX = _make_ctx(_v)
        print('TLS 模式: %s' % ('校验证书（正常）' if _v else '关闭证书校验（服务端强制，与官方脚本一致）'))
        break
    except ssl.SSLError:
        continue
    except Exception:
        # 非 TLS 错误（能拿到响应）也算握手成功
        _CTX = _make_ctx(_v)
        print('TLS 模式: %s' % ('校验证书（正常）' if _v else '关闭证书校验（服务端强制，与官方脚本一致）'))
        break
if _CTX is None:
    _CTX = _make_ctx(False)
    print('TLS 模式: 关闭证书校验（兜底）')


def call(path, params, name, timeout=20):
    p = dict(params)
    p['softName'] = SOFT
    p['apiKey'] = KEY
    url = BASE + path + '?' + urllib.parse.urlencode(p)
    safe = {k: v for k, v in p.items() if k != 'apiKey'}
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QuantMonitorV6-smoke/1.0'})
        with urllib.request.urlopen(req, context=_CTX, timeout=timeout) as r:
            body = r.read().decode('utf-8', 'ignore')
            code = r.status
    except Exception as e:
        ms = (time.time() - t0) * 1000
        msg = str(e)[:200]
        print('[%s] 失败 %.0fms  %s' % (name, ms, msg))
        RAW[name] = {'endpoint': path, 'params': safe, 'error': msg}
        return None
    ms = (time.time() - t0) * 1000
    try:
        d = json.loads(body)
    except Exception:
        d = {'_raw': body[:800]}
    RAW[name] = {'endpoint': path, 'params': safe, 'http': code, 'elapsed_ms': round(ms),
                 'resp': d}
    txt = json.dumps(d, ensure_ascii=False)[:420]
    print('[%s] %.0fms  %s' % (name, ms, txt))
    return d


print('\n' + '=' * 96)
call('/gsnews/market/agentbot/queryHQInfo/1.0',
     {'code': '600519', 'setCode': 1, 'target': 0}, '1_单只实时行情_600519')

call('/gsnews/market/agentbot/queryCombHQ/1.0',
     {'code': '600519,000001,300750', 'setCode': '1,0,0', 'target': 0}, '2_多只实时行情_3只')

call('/gsnews/market/agentbot/queryPastHQInfo/1.0',
     {'code': '600519', 'setCode': 1, 'wantNums': 20, 'target': 0, 'mas': '5,10,20'},
     '3_历史日K_20根带MA')

call('/gsnews/market/agentbot/queryFundFlow/1.0',
     {'code': '600519', 'setCode': 1, 'period': 5}, '4_资金流_5日')

call('/gsnews/market/agentbot/queryMultiHQ/1.0',
     {'setDomain': 6, 'wantNum': 5, 'sortType': 1, 'target': 0}, '5_涨幅排名_沪深A股前5')

call('/gsnews/market/agentbot/queryRelatedCombHQ/1.0',
     {'code': '600519', 'setCode': 1, 'target': 0}, '6_个股关联板块_600519')

call('/gsnews/gsf10/financial/incomeStatement/1.0',
     {'code': '600519', 'market': 'SH', 'reportType': 'Q0', 'count': '1'}, '7_利润表_600519最新')

call('/agent/mcp/smart_stock_picking',
     {'searchstring': '市盈率小于20的银行股', 'searchtype': 'stock'}, '8_智能选股_条件查询')

call('/agent/adapter/query', {'text': '最新CPI数据'}, '9_宏观_最新CPI', timeout=40)

with io.open(os.path.join(ROOT, 'tools', '_gs_smoke_raw.json'), 'w', encoding='utf-8') as f:
    json.dump(RAW, f, ensure_ascii=False, indent=1)
print('\n原始返回已存: tools\\_gs_smoke_raw.json  （不含 apiKey）')

# 顺带核一下国信日K和本地 kline_cache 的新鲜度差
try:
    d = RAW.get('3_历史日K_20根带MA', {}).get('resp') or {}
    s = json.dumps(d, ensure_ascii=False)
    import re
    ds = re.findall(r'20\d{2}-\d{2}-\d{2}', s)
    print('国信日K 返回日期范围: %s ~ %s（共 %d 个日期串）'
          % (min(ds) if ds else '-', max(ds) if ds else '-', len(ds)))
except Exception as e:
    print('日期解析失败:', e)
