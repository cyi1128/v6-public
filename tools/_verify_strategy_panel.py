# -*- coding: utf-8 -*-
"""策略看板页验证：信号造数单测 + 全市场实扫 + 离屏渲染截图。"""
import os, sys, json, time
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

import services.strategy_scan_service as SS
from services.strategy_scan_service import compute_signals, scan_market, KEYS_ALL

PASS, FAIL = [], []
def ck(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print('PASS %s %s' % (name, extra) if cond else 'FAIL %s %s' % (name, extra))

# ---------- [A] 造数单测 ----------
def mk_bars(closes, vols=None):
    n = len(closes)
    vols = vols or [1000.0] * n
    bars = []
    for i, c in enumerate(closes):
        bars.append({'date': '2026-%02d-%02d' % (i % 12 + 1, i % 28 + 1),
                     'open': c, 'high': c * 1.01, 'low': c * 0.99,
                     'close': c, 'volume': vols[i]})
    return bars

# A1: 缓涨 100 根 —— 多头排列 + 无金叉
cl = [10 + i * 0.05 for i in range(100)]
hits, info = compute_signals(mk_bars(cl))
ck('造数-多头排列命中', 'ma_long' in hits, 'hits=%s' % sorted(hits))
ck('造数-多头排列当天无金叉', 'ma_gold' not in hits, 'hits=%s' % sorted(hits))

# A2: 前 80 根横盘在 10，后 20 根逐步上穿制造 MA5 上穿 MA20
cl = [10.0] * 80 + [10.05, 10.1, 10.18, 10.3, 10.45, 10.6, 10.8,
                    11.0, 11.2, 11.35, 11.5, 11.65, 11.8, 11.9,
                    12.0, 12.05, 12.1, 12.15, 12.2, 12.25]
hits, info = compute_signals(mk_bars(cl))
ck('造数-MACD金叉/多头可命中', ('ma_gold' in hits or 'macd_gold' in hits or 'ma_long' in hits),
   'hits=%s' % sorted(hits))

# A3: 横盘 90+10 根后突然放量突破20日新高
base = [10.0] * 90
cl = base + [10.0] * 10 + [11.5, 11.8, 12.0, 12.3, 12.6]
vols = [1000.0] * 100 + [3000.0, 3000.0, 3000.0, 3000.0, 4500.0]
hits, info = compute_signals(mk_bars(cl, vols))
ck('造数-放量突破命中', 'brk_vol' in hits, 'hits=%s' % sorted(hits))

# A4: 不足60根 → 空
hits, info = compute_signals(mk_bars([10.0] * 30))
ck('短数据不命中', hits == set())

# ---------- [B] 全市场实扫 ----------
t0 = time.time()
res = scan_market(keys=KEYS_ALL)
rows = res['rows']
print('\n=== 实扫：%d 只命中 / %d 只 数据日=%s 耗时=%.1fs ==='
      % (len(rows), res['stats']['total'], res['data_date'], time.time() - t0))
for k in KEYS_ALL:
    print('  %-12s %d' % (k, res['stats']['per_strategy'].get(k, 0)))
ck('实扫-有命中', len(rows) > 0, 'rows=%d' % len(rows))
ck('实扫-数据日新鲜', res['data_date'] >= '2026-10-14', res['data_date'])
ck('实扫-每只至少命中一个', all(r['hits'] for r in rows))
ck('实扫-快照可写', SS.save_snapshot(res))

# ---------- [C] 离屏渲染 ----------
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication([])
from ui.battle_widgets.strategy_panel_widget import StrategyPanelWidget
w = StrategyPanelWidget()
ck('页面-7个策略勾选', len(w._chks) == 7, 'chks=%d' % len(w._chks))
ck('页面-表格7列', w.table.columnCount() == 7)
ck('页面-载入快照后有数据行', w.table.rowCount() > 100, 'rows=%d' % w.table.rowCount())
w.resize(1500, 800)
w.show()
app.processEvents()
shot = r'D:\QuantMonitorV6\tools\_shot_strategy_panel.png'
QTimer.singleShot(400, lambda: (w.grab().save(shot), app.quit()))
app.exec()
ck('截图已存', os.path.exists(shot) and os.path.getsize(shot) > 10000,
   '%s %dB' % (shot, os.path.getsize(shot) if os.path.exists(shot) else 0))

print('\n结果：%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项:', FAIL)
