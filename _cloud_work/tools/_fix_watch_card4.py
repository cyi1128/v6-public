# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
lines = io.open(P, encoding='utf-8').read().split('\n')
# 1) 删除裸 {_ai_block} 行（在 return f""" 之前）
for i, l in enumerate(lines):
    if l == '{_ai_block}':
        lines.pop(i)
        break
# 2) 把 f-string 内 🧠 行替换为 {_ai_block}
for i, l in enumerate(lines):
    if '🧠 {ai_tag}：{why_txt}' in l:
        lines[i] = '{_ai_block}'
        break
io.open(P, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
print('moved ai_block into f-string')
