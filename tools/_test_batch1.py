# -*- coding: utf-8 -*-
import ast, sys, importlib.util, urllib.request, subprocess
src = open('tools/cloud_daily_review.py', encoding='utf-8').read()
ast.parse(src)
print('1. 语法 OK, 行数', len(src.splitlines()))
spec = importlib.util.spec_from_file_location('m', 'tools/cloud_daily_review.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

d = m.get_pools()
print('2. 真实get_pools pool_ok=', d['pool_ok'], 'lu=', d['lu'])

orig = m._getm
m._getm = lambda *a, **k: (None, False)
d2 = m.get_pools()
print('3. 接口失败 pool_ok=', d2['pool_ok'], 'lu=', d2['lu'])
m._getm = orig

m._getm = lambda *a, **k: ('{"data":null}', True)
d3 = m.get_pools()
print('4. 空data pool_ok=', d3['pool_ok'], 'lu=', d3['lu'])
m._getm = orig


class R:
    def read(self): raise Exception('net down')
    def __enter__(self): return self
    def __exit__(self, *a): return False


urllib.request.urlopen = lambda *a, **k: R()
ok, msg = m.push('<p>t</p>', 'test')
print('5. push失败 ok=', ok, '(应False,无异常无递归)')

# 用干净子进程测卡片构建（patch push 为 no-op，不发真实推送）
runner = "import sys;sys.argv=['x','--time','pre'];import importlib.util as u;s=u.spec_from_file_location('m','tools/cloud_daily_review.py');m=u.module_from_spec(s);s.loader.exec_module(m);m.push=lambda *a,**k:(True,'mock');h=m.build_pre();assert '数据源' in h or '数据缺源' in h;print('CARD OK len',len(h))"
r = subprocess.run(['C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\python.exe',
                    '-X', 'utf8', '-c', runner],
                   capture_output=True, text=True, encoding='utf-8')
print('6. 干净进程卡片构建:', (r.stdout or r.stderr).strip()[:300])
print('HEALTH sources=', list(m.HEALTH['sources'].keys()))
print('ALL TESTS DONE')
