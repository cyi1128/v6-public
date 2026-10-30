# -*- coding: utf-8 -*-
"""看新浪公告页真实结构（打印含日期的片段）。"""
import os
import re
import sys

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests   # noqa: E402

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
       'Referer': 'https://vip.stock.finance.sina.com.cn/'}

u = ('https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/600338.phtml'
     '?Page=1')
r = requests.get(u, headers=HDR, timeout=10)
r.encoding = 'gbk'
t = r.text
print('len=%d' % len(t))
ids = [m.start() for m in re.finditer(r'\d{4}-\d{2}-\d{2}', t)][:3]
for i in ids:
    print('---- 片段 @%d ----' % i)
    print(t[max(0, i - 420):i + 160].replace('\r', ''))
    print()
print('=== 是否存在 vCB_AllBulletinDetail 链接 ===',
      t.count('vCB_AllBulletinDetail'))
print('=== datelist / 公告列表容器 ===',
      [k for k in ('datelist', 'bulletin', '公告标题', 'news_list') if k in t])
