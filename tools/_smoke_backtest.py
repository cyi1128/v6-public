# -*- coding: utf-8 -*-
"""端到端冒烟测试：不启动GUI，直接调用 run_backtest，确认分钟VWAP生效"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

from ui.backtest_page import run_backtest, load_watchlist
import numpy as np

codes = load_watchlist()
print("股票池:", codes)

# 用日线实际覆盖区间的近段（分钟数据覆盖 2026-08-27~09-15）
res = run_backtest('2026-06-01', '2026-09-15', 100000.0, codes,
                   progress_cb=lambda p: None)
print("\n=== 回测结果 ===")
print("交易日数:", len(res['dates']))
print("成交笔数:", len(res['trades']))
print("期末净值:", round(res['nav_df']['nav'].iloc[-1], 4) if 'nav_df' in res else 'n/a')

# 校验：直接比对某只股票最近一天的VWAP是分钟值
from ui.backtest_page import load_stock_df
from services import minute_kline as mk
code = '000811'
day_vwap = mk.load_day_vwap(code, '2026-08-27', '2026-09-15')
print(f"\n=== {code} 分钟当日VWAP抽查 ===")
print("2026-09-15 分钟VWAP =", round(day_vwap.get('2026-09-15', float('nan')), 4))
print("2026-09-15 日线收盘价 =", load_stock_df(code, '2026-09-15', '2026-09-15')['close'].iloc[0])
print("\nSMOKE OK")
