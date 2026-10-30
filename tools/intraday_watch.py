# -*- coding: utf-8 -*-
"""盘中异动监控薄入口：python tools/intraday_watch.py
复用 cloud_daily_review.build_intraday（东财涨停池指纹门 → 六步 → PushPlus 推送）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloud_daily_review import build_intraday

if __name__ == '__main__':
    build_intraday()
