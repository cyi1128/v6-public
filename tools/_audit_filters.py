# -*- coding: utf-8 -*-
"""QuantMonitorV6 全项目反推审计 v2：只扫真正的「过滤/阈值判断」语句。

收紧正则：只匹配带比较运算符或显式剔除的语句，避免 watchlist/persist 这类误报。
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"

TARGETS = [
    ("1. 自选 / 自选评分", [r"ui\watchlist_panel.py", r"ui\battle_widgets\watchlist_widget.py"]),
    ("2. 今日涨停", [r"ui\battle_widgets\limit_up_widget.py"]),
    ("3. 竞价筛选", [r"ui\battle_widgets\auction_filter_widget.py"]),
    ("4. 竞价追踪", [r"ui\battle_widgets\picks_track_widget.py", r"services\picks_tracking_service.py"]),
    ("5. 分时做T", [r"ui\battle_widgets\atr_t_widget.py"]),
    ("6. 日K建仓引擎", [r"services\band_pattern_engine.py"]),
    ("7. 基准阳跟踪", [r"services\anchor_tracker.py"]),
    ("8. 市场节奏", [r"ui\battle_widgets\market_rhythm_widget.py", r"services\market_rhythm_engine.py"]),
    ("9. 可介入引擎", [r"services\board_anomaly_engine.py"]),
    ("10. 异动池引擎", [r"services\intraday_opportunity_engine.py"]),
    ("11. 涨停原因采集/查询", [r"services\limit_up_collector.py", r"data\limit_up_reason_db.py"]),
    ("12. 控盘度", [r"services\control_profile.py"]),
    ("13. K线缓存", [r"services\kline_cache_service.py"]),
]

RULES = [
    ("A 板性白名单定义", re.compile(r"MAIN_(?:BOARD_)?PREFIX\w*\s*=|MAIN_PREFIX\s*=\s*\(|CYB_PREFIXES\s*=")),
    ("B 板性判定调用", re.compile(r"is_main_board\s*\(|_is_main_a_share\s*\(|_is_cyb\s*\(|_is_main_board_code\s*\(")),
    ("C 板性前缀字面量", re.compile(r"startswith\(\s*\(\s*['\"](?:60|00|30|301|688|689|8|4|920)")),
    ("D ST 剔除", re.compile(r"['\"]\*?ST['\"]|is_st|_st_stocks|退市|退市整理")),
    ("E 涨停阈值", re.compile(r"9\.8|9\.9|19\.5|29\.5|limit_threshold|涨停判定")),
    ("F 个股涨跌幅阈值", re.compile(r"\bpct\w*\s*[<>]=?\s*-?\d")),
    ("G 股价门槛", re.compile(r"(?:price|现价|收盘价|close)\s*[<>]=?\s*\d+\.\d")),
    ("H 市值门槛", re.compile(r"(?:mv|market_cap|市值)\s*[<>]=?\s*\d")),
    ("I 换手率门槛", re.compile(r"(?:turnover|换手率|换手)\s*[<>]=?\s*\d")),
    ("J 成交额门槛", re.compile(r"(?:amount|成交额)\s*[<>]=?\s*\d")),
    ("K 上市天数", re.compile(r"上市\s*\d+|list_days|上市不足|days_listed")),
    ("L 大盘指数", re.compile(r"1\.000001")),
]


def lines_of(p):
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "MIXED")
    txt = raw.decode("utf-8-sig", errors="replace")
    return txt.splitlines(), eol


for group, files in TARGETS:
    print()
    print("### %s" % group)
    for rel in files:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print("   !! 不存在: %s" % rel)
            continue
        lines, eol = lines_of(p)
        hits = {}
        for i, line in enumerate(lines, 1):
            st = line.strip()
            if not st or st.startswith("#"):
                continue
            for cat, rx in RULES:
                if rx.search(line):
                    hits.setdefault(cat, []).append((i, st[:130]))
        print("   %-46s [%s %d行]" % (rel, eol, len(lines)))
        if not hits:
            print("        无命中")
        for cat, _rx in RULES:
            if cat in hits:
                print("        · %s —— %d 处" % (cat, len(hits[cat])))
                for ln, txt in hits[cat][:8]:
                    print("             L%-5d %s" % (ln, txt))
                if len(hits[cat]) > 8:
                    print("             ...另外 %d 处" % (len(hits[cat]) - 8))
