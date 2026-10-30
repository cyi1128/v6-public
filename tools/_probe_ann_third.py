# -*- coding: utf-8 -*-
"""探第三公告通道：新浪 / 同花顺 / 东财 datasheet 是否可用（含创业板代码）。"""
import os
import re
import sys

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests   # noqa: E402

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
CODES = ['600338', '301201', '000779']

print('=== A. 新浪 vCB_AllBulletin（GBK HTML）===')
for c in CODES:
    try:
        u = 'https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/%s.phtml' % c
        r = requests.get(u, headers=HDR, timeout=10)
        r.encoding = 'gbk'
        t = r.text
        _rows = re.findall(r'<a href="([^"]+)"[^>]*>([^<]{4,60})</a>', t)
        _rows = [x for x in _rows if '公告' in x[1] or '决议' in x[1] or '报告' in x[1]]
        print('   %s status=%s len=%d 命中条目=%d 例=%s'
              % (c, r.status_code, len(t), len(_rows), (_rows[0][1][:36] if _rows else '')))
    except Exception as e:
        print('   %s 异常 %s' % (c, str(e)[:70]))

print()
print('=== B. 同花顺 basic.10jqka notice ===')
for c in CODES[:2]:
    try:
        u = 'https://basic.10jqka.com.cn/%s/notice.html' % c
        r = requests.get(u, headers=HDR, timeout=10)
        print('   %s status=%s len=%d head=%s' % (c, r.status_code, len(r.text),
                                                  r.text[:60].replace('\n', ' ')))
    except Exception as e:
        print('   %s 异常 %s' % (c, str(e)[:70]))

print()
print('=== C. 东财 datacenter 公告报表接口 ===')
for rn in ('RPT_ANNOUNCEMENT_NOTICE', 'RPT_NOTICE_BASIC', 'RPT_ANNOUNCEMENT_LIST'):
    try:
        u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=%s'
             '&columns=ALL&pageNumber=1&pageSize=3&filter=(SECURITY_CODE="600338"'
             ')(NOTICE_DATE>=\'2026-01-01\')' % rn)
        r = requests.get(u, headers=HDR, timeout=10)
        _ok = r.text[:1] == '{'
        print('   %-28s status=%s json=%s head=%s' % (rn, r.status_code, _ok,
                                                       r.text[:80].replace('\n', ' ')))
    except Exception as e:
        print('   %-28s 异常 %s' % (rn, str(e)[:60]))
