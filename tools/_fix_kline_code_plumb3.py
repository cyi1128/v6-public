# -*- coding: utf-8 -*-
"""[一次性补丁·收尾] pro_stock_pool.py：记住 K线代码 + 推送时透传。"""
import os
import re
import subprocess
import sys

p = os.path.join(r'D:\QuantMonitorV6', 'ui', 'pro_stock_pool.py')
src = open(p, newline='', encoding='utf-8').read()
crlf, lf = src.count('\r\n'), src.count('\n') - src.count('\r\n')
assert crlf > 0 and lf == 0, '不是纯 CRLF'
t = src.replace('\r\n', '\n')

pat1 = (r"(            code = self\.stock_data\.get\('code', ''\)\n"
        r"            if not code:\n"
        r"                return\n)"
        r"(\n            # 获取500根日K\n)")
t, n1 = re.subn(pat1,
                "\\1            self._kline_code = code        # 供 _set_kline_data 透传给 K 线控件\\2",
                t)
print('记住 K线代码：%d 处' % n1)

pat2 = r'(\s+)self\.kline_widget\.set_kline_data\(kline_data\)\n'
t, n2 = re.subn(pat2, "\\1self.kline_widget.set_kline_data(kline_data, getattr(self, '_kline_code', ''))\n", t)
print('推送带上 code：%d 处' % n2)

if n1 == 1 and n2 == 1:
    open(p, 'w', newline='', encoding='utf-8').write(t.replace('\n', '\r\n'))
    chk = open(p, newline='', encoding='utf-8').read()
    c2, l2 = chk.count('\r\n'), chk.count('\n') - chk.count('\r\n')
    r = subprocess.run([sys.executable, '-m', 'py_compile', p], capture_output=True, text=True)
    print('改后：CRLF=%d 裸LF=%d py_compile=%s' % (c2, l2, 'OK' if r.returncode == 0 else (r.stderr or '')[:200]))
    for ln in chk.replace('\r\n', '\n').split('\n'):
        if '_kline_code' in ln:
            print('   ' + ln.strip())
else:
    print('命中数不符，未写入')
