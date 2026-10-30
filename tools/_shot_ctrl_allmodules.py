# -*- coding: utf-8 -*-
"""把多张表真实渲染后的「控盘」列读回来，画成一张对照图（数据取自真实渲染，非编造）。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication

app = QApplication([])
from ui.battle_widgets.base import fetch_ctrl_for
from services.control_profile import get_ctrl_map
from PIL import Image, ImageDraw, ImageFont

CODES = [("600845", "宝信软件"), ("002847", "盐津铺子"), ("605196", "华通线缆"), ("600587", "新华医疗")]
M = get_ctrl_map([c for c, _ in CODES])
panels = []


def cells(tbl, row, spec):
    """spec: [(列号, 颜色)] -> [(文字, 颜色)]"""
    out = []
    for col, color in spec:
        it = tbl.item(row, col)
        out.append((it.text() if it else "", color))
    return out


# 1 今日涨停
from ui.battle_widgets.limit_up_widget import LimitUpWidget

w = LimitUpWidget()
rows = [dict(code=c, name=n, price=10.0, pct=10.0, mv=100.0, industry="x", _theme="测试题材") for c, n in CODES]
fetch_ctrl_for(rows)
w._stocks = rows
w._render_rows()
cc = w.table.columnCount() - 1
heads = [w.table.horizontalHeaderItem(i).text() for i in (0, 5, cc)]
body = [cells(w.table, i, [(0, "#c62828"), (5, "#c62828"),
                           (cc, w.table.item(i, cc).foreground().color().name())]) for i in range(4)]
panels.append(("今日涨停", heads, body))

# 2 自选评分
from ui.battle_widgets.watchlist_widget import WatchlistWidget, COL_CTRL as WC

w2 = WatchlistWidget()
w2._watchlist = [dict(code=c, name=n) for c, n in CODES]
q = {c: dict(price=12.34, pct_chg=1.5, amplitude=3.0, total_mv=100.0, name=n, ctrl=M.get(c)) for c, n in CODES}
w2._themes = {c: "测试题材" for c, _ in CODES}
w2._populate_table(q)
heads = [w2.table.horizontalHeaderItem(i).text() for i in (0, 3, WC)]
body = [cells(w2.table, i, [(0, "#1a1b1c"), (3, "#c62828"),
                            (WC, w2.table.item(i, WC).foreground().color().name())]) for i in range(4)]
panels.append(("自选评分", heads, body))

# 3 市场节奏 · 追踪
from ui.battle_widgets.picks_track_widget import PicksTrackWidget, T_CTRL

w3 = PicksTrackWidget()
w3._shown = [dict(trade_date="10-09", name=n, code=c, board="测试板块", kind="概念", base_price=10.0,
                  cur_price=11.0, pct0=3.0, vol_ratio=1.5, r5=5.0, r30=None, cum=5.0)
             for c, n in CODES]
fetch_ctrl_for(w3._shown)
w3._render()
heads = [w3.table.horizontalHeaderItem(i).text() for i in (1, 6, T_CTRL)]
body = [cells(w3.table, i, [(1, "#1a1b1c"), (6, "#c62828"),
                            (T_CTRL, w3.table.item(i, T_CTRL).foreground().color().name())]) for i in range(4)]
panels.append(("市场节奏·追踪", heads, body))

# 4 分时做T
from ui.battle_widgets.atr_t_widget import AtrTWidget, COL_H_CTRL

w4 = AtrTWidget()
hr = [dict(code=c, name=n, price=10.0, pct=1.0, buy_point=9.8, sell_point=10.2, momentum="",
           risk="", risk_color="#1a1a1a", signal_text="--", signal_level=0, action="低吸") for c, n in CODES]
fetch_ctrl_for(hr)
w4._hold_rows = hr
w4._render_hold_table()
heads = [w4.table.horizontalHeaderItem(i).text() for i in (0, 3, COL_H_CTRL)]
body = [cells(w4.table, i, [(0, "#1a1b1c"), (3, "#c62828"),
                            (COL_H_CTRL, w4.table.item(i, COL_H_CTRL).foreground().color().name())]) for i in range(4)]
panels.append(("分时做T（持仓表）", heads, body))

# 5 竞价筛选 · 今日竞价
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget, COL_CTRL as AU, C_TRACK_CTRL as AUT

w5 = AuctionFilterWidget()
ar = [dict(code=c, name=n, score=66.0, gap=3.0, jj_turnover=1.0, open=10.0, cur_price=10.5,
           cur_pct=2.0, theme_display="测试题材") for c, n in CODES]
fetch_ctrl_for(ar)
w5._rows = ar
w5._render_rows()
heads = [w5.table.horizontalHeaderItem(i).text() for i in (0, 7, AU)]
body = [cells(w5.table, i, [(0, "#1a1b1c"), (7, "#4a4a4a"),
                            (AU, w5.table.item(i, AU).foreground().color().name())]) for i in range(4)]
panels.append(("竞价筛选·今日竞价", heads, body))

# 6 竞价追踪
w5.track_list = [dict(trade_date="10-09", name=n, code=c, theme="测试", base_price=10.0, cur_price=11.0,
                      r5=5.0, r30=None, cum_pnl=5.0) for c, n in CODES]
fetch_ctrl_for(w5.track_list)
w5._render_tracking()
heads = [w5.track_table.horizontalHeaderItem(i).text() for i in (1, 8, AUT)]
body = [cells(w5.track_table, i, [(1, "#1a1b1c"), (8, "#c62828"),
                                  (AUT, w5.track_table.item(i, AUT).foreground().color().name())])
        for i in range(4)]
panels.append(("竞价筛选·竞价追踪", heads, body))

# ---- 画图 ----
FB = "C:/Windows/Fonts/msyhbd.ttc"
F = "C:/Windows/Fonts/msyh.ttc"
f_t = ImageFont.truetype(FB, 22)
f_h = ImageFont.truetype(FB, 15)
f_c = ImageFont.truetype(F, 15)
f_n = ImageFont.truetype(F, 12)
CW = [190, 150, 96]
RH, HD, PAD, GAP = 30, 30, 20, 18
W = PAD * 2 + sum(CW)
H = PAD + 34 + len(panels) * (20 + HD + RH * 4 + GAP + 10) + 26
img = Image.new("RGB", (W, H), "#FFFFFF")
d = ImageDraw.Draw(img)
y = PAD
d.text((PAD, y), "控盘列已铺到各列表模块（真实渲染读回）", font=f_t, fill="#1a1b1c")
y += 36
for title, heads, body in panels:
    d.text((PAD, y), title, font=f_n, fill="#6b7280")
    y += 20
    d.rectangle([PAD, y, PAD + sum(CW), y + HD], fill="#f4f3ee")
    x = PAD
    for i, h in enumerate(heads):
        d.text((x + 10, y + 7), h, font=f_h, fill="#4a4a4a")
        x += CW[i]
    y += HD
    for r in body:
        x = PAD
        for i, (txt, col) in enumerate(r):
            d.text((x + 10, y + 6), txt, font=f_c, fill=col)
            x += CW[i]
        y += RH
    d.line([PAD, y, PAD + sum(CW), y], fill="#e4e3dd")
    y += GAP + 10
d.text((PAD, y), "口径：services/control_profile.py 只读本地 kline_cache，与日K建仓完全相同",
       font=f_n, fill="#9e9e9e")
out = r"D:\QuantMonitorV6\_shot_ctrl_allmodules.png"
img.save(out)
print("已出图 %s  %dx%d" % (out, W, H))
