# -*- coding: utf-8 -*-
"""验证：竞价门槛与高开分是否真的按板性分流（主板口径必须一字不变）。"""
import sys

sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")

try:
    from ui.battle_widgets.auction_filter_widget import (
        _is_cyb, _gap_band, _turnover_max, _gap_score_bands,
        AuctionFilterWidget,
    )
except Exception as e:
    print("!! 导入失败: %s" % e)
    raise SystemExit(1)

print("=== 1. 板性判定 ===")
for code in ('600000', '000001', '002594', '300001', '301001', '688001', '830799'):
    print("   %s  创业板=%-5s 高开区间=%-12s 换手上限=%s"
          % (code, _is_cyb(code), _gap_band(code), _turnover_max(code)))

print()
print("=== 2. 高开幅度分（右侧括号是改之前的值）===")
MAIN = '600000'
CYB = '300001'


def row(code, gap, vr=1.0):
    return {'code': code, 'gap': gap, 'jj_turnover': 3.0, 'jj_vol_shares': 1e6,
            'avg_vol5': 1e7, 'ref_vol': 1e7, 'price': 10.0, 'low60': 5.0,
            'hist_days': 300, 'theme_score': 60, 'em_vol_ratio': vr,
            'open': 10.0, 'last_close': 10.0}


def gap_score_of(code, gap, vr=1.0):
    r = row(code, gap, vr)
    base, risk, shape = AuctionFilterWidget._score_volume_price(r)
    return base, shape


for code, tag in ((MAIN, '主板'), (CYB, '创业板')):
    print("   [%s]" % tag)
    for g in (1.9, 2.5, 3.5, 4.5, 6.0, 7.0, 9.0, 12.0, 15.0):
        base, shape = gap_score_of(code, g)
        print("      高开 %5.1f%%  → 基础分 %3d  形态[%s]" % (g, base, shape))

print()
print("=== 3. 关键对照（同一高开幅度，两板待遇必须不同）===")
for g in (3.5, 7.0):
    bm, sm = gap_score_of(MAIN, g)
    bc, sc = gap_score_of(CYB, g)
    print("   高开 %.1f%%：主板 %d 分[%s] ｜ 创业板 %d 分[%s]" % (g, bm, sm, bc, sc))
