# -*- coding: utf-8 -*-
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from ui.battle_widgets.base import fetch_ctrl_for

CODES = [("600845", "宝信软件"), ("600587", "新华医疗"), ("605196", "华通线缆"), ("002847", "盐津铺子")]
OK, BAD = [], []

def chk(name, tbl, col, rows):
    got = []
    for i in range(len(rows)):
        it = tbl.item(i, col)
        got.append(it.text() if it else None)
    want = []
    for c, n in rows:
        want.append(c)
    exp = {"600845": "98·候选", "600587": "44", "605196": "91·出货", "002847": "97·候选"}
    exp = [exp.get(c) for c, _ in rows]
    ok = got == exp
    (OK if ok else BAD).append(name)
    print("  %-22s 列%d 表头'%s'  行数%d  值=%s  %s" % (
        name, col, tbl.horizontalHeaderItem(col).text(), tbl.rowCount(), got,
        "OK" if ok else "期望 %s 不符!" % exp))

print("=" * 88)
print("A. 个股列表模块 控盘列总装验证（同一批真实代码，2只候选 / 1只出货 / 1只无提示）")
print("=" * 88)

# 1 日K建仓
from ui.battle_widgets.atr_t_widget import AtrTWidget, COL_D_CTRL, COL_H_CTRL
w = AtrTWidget()
r = [dict(code=c, name=n, price=10.0, pct=1.0, trigger_price=9.5, take_profit=11.0,
          theme="测试", pattern_name="激进", trigger_text="精准建仓", base_date="2026-09-20",
          control_score={"600845":97.8,"600587":44.1,"605196":91.0,"002847":96.7}[c],
          stage_guess={"600845":"unknown","600587":"distribute","605196":"distribute","002847":"unknown"}[c],
          note=("x [控盘] 高度控盘候选" if c in ("600845","002847") else
                ("x [控盘] 出货风险警示 ｜ 高度控盘候选" if c=="605196" else "")),
          env_score=3) for c, n in CODES]
w._daily_rows = r
w._daily_render_table()
chk("日K建仓", w.daily_table, COL_D_CTRL, CODES)

# 2 分时做T
rows = [dict(code=c, name=n, price=10.0, pct=1.0, buy_point=9.8, sell_point=10.2,
             momentum="", risk="", risk_color="#1a1a1a", signal_text="--",
             signal_level=0, action="低吸") for c, n in CODES]
fetch_ctrl_for(rows)
w._hold_rows = rows
w._render_hold_table()
chk("分时做T", w.table, COL_H_CTRL, CODES)

# 3 今日涨停
from ui.battle_widgets.limit_up_widget import LimitUpWidget, COL_CTRL as LZ
w2 = LimitUpWidget()
rows = [dict(code=c, name=n, price=10.0, pct=10.0, mv=100.0, industry="x", _theme="t") for c, n in CODES]
fetch_ctrl_for(rows); w2._stocks = rows; w2._render_rows()
chk("今日涨停", w2.table, LZ, CODES)

# 4 自选评分
from ui.battle_widgets.watchlist_widget import WatchlistWidget, COL_CTRL as WL
w3 = WatchlistWidget()
w3._watchlist = [dict(code=c, name=n) for c, n in CODES]
q = {c: dict(price=10.0, pct_chg=1.0, amplitude=3.0, total_mv=100.0, name=n) for c, n in CODES}
fetch_ctrl_for([dict(code=c) for c, n in CODES])
from services.control_profile import get_ctrl_map
m = get_ctrl_map([c for c, _ in CODES])
for c in q: q[c]["ctrl"] = m.get(c)
w3._themes = {c: "t" for c, _ in CODES}
w3._populate_table(q)
chk("自选评分", w3.table, WL, CODES)

# 5 竞价 今日 + 6 竞价追踪
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget, COL_CTRL as AU, C_TRACK_CTRL as AUT
w4 = AuctionFilterWidget()
rows = [dict(code=c, name=n, score=66.0, gap=3.0, jj_turnover=1.0, open=10.0,
             cur_price=10.5, cur_pct=2.0, theme_display="t") for c, n in CODES]
fetch_ctrl_for(rows); w4._rows = rows; w4._render_rows()
chk("竞价·今日竞价", w4.table, AU, CODES)
w4.track_list = [dict(trade_date="2026-10-09", name=n, code=c, theme="t", base_price=10.0,
                      cur_price=11.0, r5=5.0, r30=None, cum_pnl=5.0) for c, n in CODES]
fetch_ctrl_for(w4.track_list); w4._render_tracking()
chk("竞价·竞价追踪", w4.track_table, AUT, CODES)

# 7 市场节奏·追踪
from ui.battle_widgets.picks_track_widget import PicksTrackWidget, T_CTRL
w5 = PicksTrackWidget()
w5._shown = [dict(trade_date="2026-10-09", name=n, code=c, board="测试", kind="概念",
                  base_price=10.0, cur_price=11.0, pct0=3.0, vol_ratio=1.5,
                  r5=5.0, r30=None, cum=5.0) for c, n in CODES]
fetch_ctrl_for(w5._shown); w5._render()
chk("市场节奏·追踪", w5.table, T_CTRL, CODES)

print()
print("=" * 88)
print("B. 整页构建（清一盘：自选+竞价+涨停+日K建仓/做T+市场节奏）")
print("=" * 88)
try:
    from ui.battle_widgets.battle_console_home import BattleConsoleHome
    home = BattleConsoleHome()
    print("  BattleConsoleHome 构建成功")
    print("   自选 %d 列 | 竞价 %d 列 | 涨停 %d 列" % (
        home.watchlist.table.columnCount(), home.auction_filter.table.columnCount(),
        home.limit_up.table.columnCount()))
    print("   日K建仓 %d 列 | 分时做T %d 列 | 市场节奏 %d 列" % (
        home.atr_t.daily_table.columnCount(), home.atr_t.table.columnCount(),
        home.market_rhythm.table.columnCount()))
except Exception as e:
    import traceback; traceback.print_exc()
    BAD.append("整页构建")

print()
print("=" * 88)
print("结果：通过 %d 项 %s" % (len(OK), "全部通过" if not BAD else "｜失败: %s" % BAD))
