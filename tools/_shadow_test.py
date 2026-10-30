# -*- coding: utf-8 -*-
import sys, os, importlib.util, json, tempfile
sys.argv = ['x', '--dry-run']
s = importlib.util.spec_from_file_location('m', 'tools/cloud_daily_review.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

# 1. 去重：临时状态文件
tmp = tempfile.mktemp(suffix='.json')
m.ALERT_PATH = tmp
al = m.load_alerts()
print('初始:', al)
for i in range(3):
    if '测试股|异动' not in al.get('fired', []):
        print(f'第{i+1}次: 新信号，记录')
        al.setdefault('date', m.datetime.now().strftime('%Y-%m-%d'))
        al.setdefault('fired', []).append('测试股|异动')
        m.save_alerts(al)
    else:
        print(f'第{i+1}次: 已去重，跳过')

# 2. 不同信号
al = m.load_alerts()
print('不同信号检查:', '测试股|回落' not in al.get('fired', []))

# 3. dry-run push
import urllib.request
urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError('禁外部'))
ok, msg = m.push('<p>x</p>', '隔离测试')
print('push dry-run:', ok, msg)
os.remove(tmp)
print('ISOLATED OK')
