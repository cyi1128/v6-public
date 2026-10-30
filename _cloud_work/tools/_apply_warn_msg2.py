# -*- coding: utf-8 -*-
"""按行号替换 build_warn 函数。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
newf = io.open(r'D:\QuantMonitorV6\_cloud_work\tools\_new_warn_func.py', encoding='utf-8').read().rstrip('\n')
lines = io.open(P, encoding='utf-8').read().split('\n')
start = next(i for i, l in enumerate(lines, 1) if l.startswith('def build_warn():'))
end = next(i for i, l in enumerate(lines, 1) if l.startswith('TITLES = {'))
assert start < end, (start, end)
# 校验旧函数确实到 end-1（TITLES 前一行为空行）
assert lines[end-2].strip() == '', 'end-2 非空行: %r' % lines[end-2]
# 校验 end 行前一行（5496）为空
newlines = lines[:start-1] + [newf] + lines[end-2:]
io.open(P, 'w', encoding='utf-8', newline='').write('\n'.join(newlines))
print('替换完成 start=%d end=%d 新行数=%d' % (start, end, len(newf.split('\n'))))
