# -*- coding: utf-8 -*-
"""事实提取：把 13 组模块的结构、过滤条件、阈值行全部抓出来（供生成可复核明细）。"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

FILES = [
    r"services\band_pattern_engine.py",
    r"services\intraday_opportunity_engine.py",
    r"services\market_rhythm_engine.py",
    r"services\board_anomaly_engine.py",
    r"services\picks_tracking_service.py",
    r"services\anchor_tracker.py",
    r"services\control_profile.py",
    r"services\kline_cache_service.py",
    r"services\limit_up_collector.py",
    r"data\limit_up_reason_db.py",
    r"ui\watchlist_panel.py",
    r"ui\trading_dashboard_panel.py",
    r"ui\echarts_kline.py",
    r"ui\market_sentiment_panel.py",
    r"ui\battle_widgets\auction_filter_widget.py",
    r"ui\battle_widgets\atr_t_widget.py",
    r"ui\battle_widgets\limit_up_widget.py",
    r"ui\battle_widgets\market_rhythm_widget.py",
    r"ui\battle_widgets\picks_track_widget.py",
    r"ui\battle_widgets\base.py",
]

KEY = re.compile(
    r"startswith\(|_is_main|_is_st|MAIN_PREFIX|MAIN_BOARD_PREFIXES|CYB_PREFIXES|"
    r"_lu_threshold|limit_threshold|9\.8|19\.5|19\.8|29\.5|9\.5|=== |<= -9\.5|"
    r"MIN_PRICE|_turnover_max|TURNOVER_MAX|GAP_BAND|GAP_SCORE|"
    r"PCT_LOCK|PCT_MAINUP|PCT_WEAK|_pct_thresholds|"
    r"INCREMENTAL_FETCH_DAYS|MAX_WORKERS|_CTRL_|CTRL_COL_TITLE|"
    r"get_ctrl_map|cached_only|"
    r"MIN_STOCK|is_main_board|_SHAKE_MIN_OK"
)

for rel in FILES:
    p = ROOT + rel
    if not os.path.exists(p):
        print("!! 缺失 %s" % rel)
        continue
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "MIXED")
    lines = raw.decode("utf-8-sig").splitlines()
    print("\n" + "=" * 78)
    print("%s   [%s]  %d 行" % (rel, eol, len(lines)))
    print("=" * 78)
    for i, ln in enumerate(lines, 1):
        if KEY.search(ln):
            print("  L%-5d %s" % (i, ln.rstrip()[:150]))
