# -*- coding: utf-8 -*-
"""
验证 MA20 门槛与追踪表新列（走真实代码，不用模拟实现）。

一、board_anomaly_engine._pick_candidates 的门槛行为
    A 在均线上      -> 应通过
    B 跌破均线      -> 应剔除
    C 表里没有它    -> 应剔除（本次新增，堵洞）
    D 恰好等于均线  -> 应通过（用户要求「等于或大于」）
    E 整表为空      -> 应通过（加载失败的兜底，不能把候选全清空）
二、picks_tracking_service.fetch_tracking 是否真的带出 ma20
三、picks_track_widget 离屏渲染：列数、距MA20% 单元格内容
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = FAIL = 0


def chk(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("   [PASS] %s" % msg)
    else:
        FAIL += 1
        print("   [FAIL] %s" % msg)


# ===================================================================
print("=" * 96)
print("一、_pick_candidates 的 MA20 硬门槛")
import services.board_anomaly_engine as E  # noqa: E402

MIN_PCT = E._PICK_MIN_PCT
MAX_PCT = E._PICK_MAX_PCT
MIN_VR = E._PICK_MIN_VR
MIN_PX = E._PICK_MIN_PRICE
MIN_AMT = E._PICK_MIN_AMOUNT
MIN_CMV = E._PICK_MIN_CMV
print("   引擎门槛：涨幅 [%.2f, %.2f) ｜ 量比>=%.2f ｜ 价>=%.2f ｜ 成交额>=%.1f亿 ｜ 流通市值>=%.0f亿"
      % (MIN_PCT, MAX_PCT, MIN_VR, MIN_PX, MIN_AMT / 1e8, MIN_CMV))

PRICE = max(MIN_PX + 4.0, 10.0)
PCT = MIN_PCT + (MAX_PCT - MIN_PCT) / 2.0          # 落在区间正中
VR = MIN_VR + 0.8


def q(name):
    """造一条能通过所有非 MA20 条件的行情（vwap 贴近价格，避免 inst 干扰）。"""
    return {'name': name, 'pct_chg': PCT, 'price': PRICE, 'vol_ratio': VR,
            'amount': MIN_AMT * 3.0, 'circ_mv': MIN_CMV * 4.0, 'turnover': 3.0,
            'volume': (MIN_AMT * 3.0) / (PRICE * 100.0)}


QUOTES = {'600001': q('甲在均线上'), '600002': q('乙跌破均线'),
          '600003': q('丙无均线数据'), '600004': q('丁恰好等于均线'),
          '600005': q('戊整表为空')}
CODES = list(QUOTES.keys())
MA20_OK = {'600001': PRICE * 0.95,          # 在均线上
           '600002': PRICE * 1.05,          # 跌破均线
           '600004': PRICE}                 # 恰好等于
out = E._pick_candidates(CODES, QUOTES, set(), MA20_OK)
got = {r[0]: r for r in out}
print("   命中：%s" % (sorted(got.keys())))
chk('600001' in got, "A 在均线上 -> 通过")
chk('600002' not in got, "B 跌破均线 -> 剔除")
chk('600003' not in got, "C 表里没有它（K线不足20根） -> 剔除（本次堵的洞）")
chk('600004' in got, "D 现价恰好等于 MA20 -> 通过（「等于或大于」）")
chk(got.get('600004', [None] * 6)[5] == 0.0, "D 的「距MA20」是 0.0，不是 None")
chk(got.get('600001', [None] * 6)[5] is not None and got['600001'][5] > 0,
    "A 的「距MA20」记录了正值（%.2f%%）" % (got.get('600001', [0] * 6)[5] or -999))

out2 = E._pick_candidates(CODES, QUOTES, set(), {})     # 整表为空
got2 = {r[0] for r in out2}
chk('600005' in got2 and '600002' in got2 and '600003' in got2,
    "E MA20 整表为空 -> 全部放行（兜底，防止候选被清空）：%s" % sorted(got2))

# 再加一条：真实 _load_ma20 能不能取到数
_m = E._load_ma20()
print()
print("   真实 _load_ma20()：取到 %d 只" % len(_m))
chk(len(_m) > 1000, "MA20 聚合表真的取到数（否则门槛等于没生效）")
if _m:
    _k = list(_m.keys())[0]
    print("   例：%s -> MA20 %.2f" % (_k, _m[_k]))

# ===================================================================
print()
print("=" * 96)
print("二、fetch_tracking 是否带出 ma20")
from services.picks_tracking_service import fetch_tracking  # noqa: E402

rows = fetch_tracking()
print("   追踪样本：%d 条" % len(rows))
chk(len(rows) > 0, "追踪库有数据")
if rows:
    with_m = [r for r in rows if r.get('ma20')]
    print("   带出 ma20 的：%d / %d" % (len(with_m), len(rows)))
    chk(len(with_m) > 0, "ma20 字段真的被算出（不是全 None）")
    for r in rows[:3]:
        m = r.get('ma20')
        cur = r.get('cur_price') or 0
        g = ('%+.2f%%' % ((cur - m) / m * 100.0)) if (m and cur) else '--'
        print("      %s %s 入选%s 当前%.2f MA20 %s 距MA20 %s"
              % (r['trade_date'], r['code'], r['base_price'], cur,
                 ('%.2f' % m) if m else '--', g))
    # 入选时应该在 MA20 上（等于或大于）—— 抽查入选价 vs 入选日 MA20 无法直接取，
    # 但至少当前价与 MA20 的关系要能算出来
    ok_calc = all((r.get('ma20') is None) or (r['ma20'] > 0) for r in rows)
    chk(ok_calc, "所有 ma20 要么 None 要么 > 0")

# ===================================================================
print()
print("=" * 96)
print("三、追踪表离屏渲染（列数与「距MA20%」单元格）")
from PyQt6.QtWidgets import QApplication  # noqa: E402
from ui.battle_widgets.picks_track_widget import (  # noqa: E402
    PicksTrackWidget, TRACK_COL_N, T_M20, T_NOW, T_CTRL)

app = QApplication.instance() or QApplication([])
w = PicksTrackWidget()
w._rows = [
    {'trade_date': '2026-09-29', 'code': '600001', 'name': '甲', 'board': '储能',
     'kind': '题材', 'pct0': 3.1, 'vol_ratio': 2.0, 'base_price': 10.0,
     'cur_price': 12.0, 'ma20': 10.0, 'r5': 5.0, 'r30': None, 'cum': 20.0,
     'ctrl': {'ok': True, 'score': 91.2, 'stage': 'wash', 'pos': 0.3,
              'tip': '高度控盘 + 疑似洗盘，关注启动', 'data_date': '2026-10-09'}},
    {'trade_date': '2026-09-28', 'code': '600002', 'name': '乙', 'board': '汽车',
     'kind': '行业', 'pct0': 2.0, 'vol_ratio': 1.5, 'base_price': 20.0,
     'cur_price': 18.0, 'ma20': 19.0, 'r5': -5.0, 'r30': 1.0, 'cum': -10.0,
     'ctrl': None},
    {'trade_date': '2026-09-25', 'code': '600003', 'name': '丙（无K线）', 'board': '--',
     'kind': '', 'pct0': 1.0, 'vol_ratio': 1.3, 'base_price': 8.0,
     'cur_price': 0.0, 'ma20': None, 'r5': None, 'r30': None, 'cum': None,
     'ctrl': None},
]
w._shown = w._rows
w._render()
print("   表格列数：%d（TRACK_COL_N=%d）" % (w.table.columnCount(), TRACK_COL_N))
chk(w.table.columnCount() == TRACK_COL_N == 11, "列数 = 11")
hdr = [w.table.horizontalHeaderItem(i).text() for i in range(w.table.columnCount())]
print("   表头：%s" % hdr)
chk(hdr[6] == '距MA20%', "第 7 列是「距MA20%」")
chk(hdr[-1] == '控盘', "最后一列仍是控盘")

for i in range(3):
    it = w.table.item(i, T_M20)
    print("   第%d行 距MA20%% = %r" % (i + 1, it.text() if it else None))
chk(w.table.item(0, T_M20).text() == '+20.00%', "甲：现价12 / MA20 10 -> +20.00%")
chk(w.table.item(1, T_M20).text() == '-5.26%', "乙：现价18 / MA20 19 -> -5.26%")
chk(w.table.item(2, T_M20).text() == '--', "丙无 MA20 -> --")
chk(w.table.item(0, T_NOW).text() == '12.00', "当前价列正常")
chk(w.table.item(0, T_CTRL).text() == '91·洗盘', "控盘列正常：%r" % w.table.item(0, T_CTRL).text())
# 实时刷新一格里距MA20
# 注意 _on_rt 有 `if not self.isVisible()` 守卫，离屏测试必须先 show() 否则永远提前返回
w.show()
app.processEvents()
chk(w.isVisible(), "离屏下窗口已 show()（否则实时刷新会被守卫挡掉）")
w._rt_token += 1
w._on_rt(w._rt_token, {'600001': {'price': 9.0}})
print("   实时价改成 9.00 后，距MA20%% = %r" % w.table.item(0, T_M20).text())
chk(w.table.item(0, T_M20).text() == '-10.00%', "距MA20% 跟随实时价刷新 -> -10.00%")
w.deleteLater()

print()
print("=" * 96)
print("结果：通过 %d 项，失败 %d 项" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
