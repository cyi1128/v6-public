# -*- coding: utf-8 -*-
"""从通达信接口生成完整的股票名称映射文件"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.tdx_stock_list import get_stocks_with_quotes_tdx

print("正在从通达信获取完整股票列表...")
stocks = get_stocks_with_quotes_tdx(max_stocks=6000, sort_by='code', desc=False)
print(f"获取到 {len(stocks)} 只股票")

# 生成名称映射
name_map = {}
for s in stocks:
    code = s.get('code', '')
    name = s.get('name', '')
    if code and name:
        name_map[code] = name

print(f"生成名称映射 {len(name_map)} 条")

# 检查603开头的
count_603 = sum(1 for k in name_map.keys() if k.startswith('603'))
print(f"603开头: {count_603} 只")

# 检查之前缺失的
for code in ['603615', '603499', '600909', '603161', '603617', '603601']:
    print(f"  {code}: {name_map.get(code, '缺失')}")

# 保存到文件
output_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_names_full.json')
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(name_map, f, ensure_ascii=False, indent=2)
print(f"\n已保存到: {output_file}")
