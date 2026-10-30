# -*- coding: utf-8 -*-
"""取本次所有改动的最终真实行号，用于交付文档。"""
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

TARGETS = {
    r"services\band_pattern_engine.py": [
        r"^def _lu_threshold", r"_lu_threshold\(c\)", r"def _is_limit_up",
        r"def _is_main_a_share", r"if not _is_main_a_share\(code\) or _is_st",
    ],
    r"ui\watchlist_panel.py": [
        r"_lu_th", r"limit_up_count \+= 1", r"is_limit_up = \(close_p == high_p\)",
    ],
    r"ui\trading_dashboard_panel.py": [r"'limit_up': sum", r"'limit_down': sum"],
    r"services\intraday_opportunity_engine.py": [
        r"拉全市场行情", r"^MAIN_PREFIX", r"_low_price_codes = ", r"MIN_PRICE",
    ],
    r"ui\battle_widgets\atr_t_widget.py": [
        r"^CYB_PREFIXES", r"def _pct_thresholds", r"_lock_pct, _mainup_pct",
        r"elif pct >= _lock_pct", r"elif pct >= _mainup_pct", r"_pct_thresholds\(code\)\[2\]",
    ],
    r"ui\battle_widgets\limit_up_widget.py": [r"limit_threshold = 19\.5", r"limit_threshold = 9\.8"],
    r"ui\battle_widgets\auction_filter_widget.py": [
        r"^MAIN_BOARD_PREFIXES", r"^CYB_PREFIXES", r"_is_st\(name\)", r"jj_turnover < 0\.5",
    ],
    r"services\market_rhythm_engine.py": [r"^def is_main_board", r"只留主板|主板 \+ 创业板", r"均涨幅"],
    r"services\board_anomaly_engine.py": [r"startswith\(\('60', '00', '30'\)\)"],
    r"services\picks_tracking_service.py": [r"startswith\(\('60', '00', '30'\)\)"],
}

NOT_FIXED = {
    r"ui\watchlist_panel.py": [r"is_limit_up = \(close_p == high_p\)"],
    r"ui\echarts_kline.py": [r"isLimitUp = ", r"pct >= 19\.8", r"pct >= 9\.8"],
    r"ui\market_sentiment_panel.py": [r"pct_chg >= 9\.8", r"pct_chg >= 19\.8", r"7 <= pct_chg"],
}

for label, D in (("【已改】", TARGETS), ("【未改·待定】", NOT_FIXED)):
    print("=" * 74)
    print(label)
    print("=" * 74)
    for rel, pats in D.items():
        p = ROOT + rel
        try:
            lines = io.open(p, encoding="utf-8-sig").read().splitlines()
        except Exception as e:
            print("  !! %s 读取失败 %s" % (rel, e))
            continue
        print("\n  %s  (%d 行)" % (rel, len(lines)))
        for pat in pats:
            hit = None
            for i, ln in enumerate(lines, 1):
                if re.search(pat, ln):
                    hit = (i, ln.strip())
                    break
            if hit:
                print("     L%-5d %-72s" % (hit[0], hit[1][:72]))
            else:
                print("     ----  %s（无命中）" % pat[:50])
