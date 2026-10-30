# -*- coding: utf-8 -*-
"""TLS 探测：找出能连上国信服务端的 Python 配置；找出不行就改用 curl（官方脚本同款兜底）。
   全程不打印 apiKey。"""
import io
import json
import os
import ssl
import subprocess
import urllib.parse
import urllib.request

BASE = 'https://dgzt.guosen.com.cn/skills'
P = '/gsnews/market/agentbot/queryHQInfo/1.0?code=600519&setCode=1&softName=agent_skills&apiKey='

KEY = ''
for p in [os.path.join(os.path.expanduser('~'), '.quantmonitor', 'guosen_api_key.txt')]:
    if os.path.isfile(p):
        KEY = io.open(p, encoding='utf-8-sig').read().strip()
print('key 长度 %d' % len(KEY))


def mk(name, verify=True, legacy=True, seclevel0=False, maxv=None, ciphers=None):
    try:
        c = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if legacy:
            c.options |= ssl.OP_LEGACY_SERVER_CONNECT
        if seclevel0:
            c.set_ciphers('ALL:@SECLEVEL=0')
        if ciphers:
            c.set_ciphers(ciphers)
        if maxv:
            c.maximum_version = maxv
        c.check_hostname = verify
        c.verify_mode = ssl.CERT_REQUIRED if verify else ssl.CERT_NONE
        return name, c
    except Exception as e:
        return name, None


CFGS = [
    mk('A 默认上下文(不改)'),
    mk('B 默认+legacy+校验'),
    mk('C 默认+legacy+不校验'),
    mk('D legacy+SECLEVEL0+不校验'),
    mk('E legacy+不校验+TLS1.2上限', maxv=ssl.TLSVersion.TLSv1_2),
    mk('F legacy+不校验+TLS1.2上限+SECLEVEL0', seclevel0=True, maxv=ssl.TLSVersion.TLSv1_2),
]

print('\n--- Python urllib 组合测试（空 key，只看能否拿到响应）---')
for name, ctx in CFGS:
    if ctx is None:
        print('%-42s  构造失败' % name)
        continue
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + P), context=ctx, timeout=12)
        body = r.read().decode('utf-8', 'ignore')[:120]
        print('%-42s  OK  %s' % (name, body))
    except Exception as e:
        print('%-42s  %s' % (name, str(e)[:110]))

print('\n--- curl 兜底（官方脚本同款，带真实 key）---')
url = BASE + P + urllib.parse.quote(KEY, safe='')
try:
    out = subprocess.run(['curl', '-s', '-k', '--max-time', '25', url],
                         capture_output=True, text=True, encoding='utf-8',
                         errors='ignore', timeout=40)
    b = (out.stdout or '').strip()
    print('curl rc=%s  长度=%d  前 300 字: %s' % (out.returncode, len(b), b[:300]))
    if b:
        try:
            d = json.loads(b)
            print('解析成功，顶层键:', list(d.keys()))
            print(json.dumps(d, ensure_ascii=False)[:900])
        except Exception as e:
            print('非 JSON:', e)
except Exception as e:
    print('curl 调用失败:', e)
