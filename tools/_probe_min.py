# -*- coding: utf-8 -*-
"""测试 AkShare 分钟线接口可用性与历史深度"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak
print("akshare", ak.__version__)

# 测试1: 东财分钟线（历史范围）
for period in ["5", "1"]:
    try:
        t0 = time.time()
        df = ak.stock_zh_a_hist_min_em(symbol="000811", period=period,
                                       start_date="2024-01-01 09:30:00",
                                       end_date="2024-01-10 15:00:00")
        print(f"\n[EM period={period}] rows={len(df)} cols={list(df.columns)} "
              f"elapsed={time.time()-t0:.1f}s")
        if not df.empty:
            print(df.head(2).to_string())
            print("...tail...")
            print(df.tail(2).to_string())
    except Exception as e:
        print(f"\n[EM period={period}] ERROR: {type(e).__name__}: {e}")
