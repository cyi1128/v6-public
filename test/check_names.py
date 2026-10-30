# -*- coding: utf-8 -*-
import json
import os

base = r'C:\Users\Administrator\Doubao\chats\2026-08-10\new-chat\QuantMonitorV6'

# 检查stock_names_cache.json
with open(os.path.join(base, 'data', 'stock_names_cache.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f'stock_names_cache.json 数量: {len(data)}')
count_603 = sum(1 for k in data.keys() if k.startswith('603'))
print(f'603开头数量: {count_603}')
for code in ['603615', '603499', '600909', '603161', '603617', '603601']:
    print(f'  {code}: {data.get(code, "缺失")}')

print()

# 检查stock_names_sina.json
with open(os.path.join(base, 'data', 'stock_names_sina.json'), 'r', encoding='utf-8') as f:
    data2 = json.load(f)
print(f'stock_names_sina.json 数量: {len(data2)}')
count_603_2 = sum(1 for k in data2.keys() if k.startswith('603'))
print(f'603开头数量: {count_603_2}')
for code in ['603615', '603499', '600909', '603161', '603617', '603601']:
    print(f'  {code}: {data2.get(code, "缺失")}')
