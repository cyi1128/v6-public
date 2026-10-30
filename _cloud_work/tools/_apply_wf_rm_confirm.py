# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\.github\workflows\daily-review2.yml'
s = io.open(P, encoding='utf-8').read()
old1 = "options: ['pre', 'auction', 'hourly', 'noon', 'eod', 'watch', 'warn', 'confirm', 'ext', 'news', 'evening', 'news2h']"
new1 = "options: ['pre', 'auction', 'hourly', 'noon', 'eod', 'watch', 'warn', 'ext', 'news', 'evening', 'news2h']"
assert s.count(old1) == 1, old1
s = s.replace(old1, new1)
old2 = "    - cron: '28 1 * * 1-5'         # 09:28 北京 竞价确认（原09:25；让位给 auction，纯规则零DS）\n"
assert s.count(old2) == 1, old2
s = s.replace(old2, '')
old3 = '            01:2[8-9])   T=confirm ;;   # 09:28-09:29 竞价确认（重跑双打分TOP5，纯规则零DS）\n'
assert s.count(old3) == 1, old3
s = s.replace(old3, '')
io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('workflow OK: confirm 已移除（并入 auction 09:25）')
