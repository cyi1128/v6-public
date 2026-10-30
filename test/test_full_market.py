# -*- coding: utf-8 -*-
"""测试全市场行情获取"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tdx_stock_list import get_full_market_quotes

print('正在获取全市场行情...')
stocks = get_full_market_quotes()
print(f'全市场股票数量: {len(stocks)}')
if stocks:
    print(f'前5只:')
    for s in stocks[:5]:
        print(f'  {s["code"]} {s["name"]} 价格={s["price"]} 涨幅={s["pct_chg"]}%')
