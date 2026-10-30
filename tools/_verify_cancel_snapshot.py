# -*- coding: utf-8 -*-
"""验证：中止扫描不覆盖快照、正常扫描照旧覆盖（可重跑，离屏）。

背景（2026-10-12 实测踩到）：点「停止扫描」后 scan_market 返回残缺/0 行，
而 _on_scan_ok 原来无条件 save_snapshot → 上一次的完整快照被换成 122 字节空壳，
下次打开控盘选股页看到的是空表。本脚本验证修复后的两种行为。
"""
import json
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

SNAP = 'data/cache/control_screen.json'
P, F = [], []


def ck(name, cond, extra=''):
    (P if cond else F).append(name)
    print('%s %s %s' % ('PASS' if cond else 'FAIL', name, extra), flush=True)


def snap_info():
    d = json.load(open(SNAP, encoding='utf-8'))
    return {'mtime': os.path.getmtime(SNAP), 'rows': len(d.get('rows') or []),
            'date': d.get('data_date'), 'size': os.path.getsize(SNAP),
            'saved_at': d.get('saved_at')}


s0 = snap_info()
print('初始快照: rows=%d data_date=%s %dB' % (s0['rows'], s0['date'], s0['size']), flush=True)
ck('前置：快照里有完整结果', s0['rows'] > 1000, str(s0))

from PyQt6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from ui.battle_widgets.control_screen_widget import ControlScreenWidget  # noqa: E402


def _wait(limit=180):
    t0 = time.time()
    while w._scanning and time.time() - t0 < limit:
        app.processEvents()
        time.sleep(0.15)
    for _ in range(10):
        app.processEvents()
    return time.time() - t0


# ---------- 1) 中止扫描：不许动快照 ----------
w = ControlScreenWidget()
for cb in ('_ck_auto', '_ck_extra', '_ck_seed'):
    try:
        getattr(w, cb).setChecked(False)
    except Exception:
        pass
w.resize(1600, 800)
w.show()
for _ in range(8):
    app.processEvents()
_ui_rows0 = w.table.rowCount()
ck('打开页面已载入快照', _ui_rows0 > 0, '表格行数=%d' % _ui_rows0)

w._start_scan()
w._cancel = True                     # 立刻中止
_dt = _wait()
s1 = snap_info()
ck('中止后快照未被覆盖', s1['mtime'] == s0['mtime'] and s1['rows'] == s0['rows'],
   'mtime %s→%s rows %s→%s' % (s0['mtime'], s1['mtime'], s0['rows'], s1['rows']))
ck('中止后列表仍是上一次结果', w.table.rowCount() == _ui_rows0,
   '表格 %d→%d' % (_ui_rows0, w.table.rowCount()))
ck('中止有明确提示', '中止' in w.update_time_label.text(), w.update_time_label.text())
ck('中止后可以再扫（_cancel 已复位）', w._cancel is False)

# ---------- 2) 正常扫描：照旧覆盖快照 ----------
w._btn_scan.click()                  # 走按钮路径，验证与手动停止不冲突
_dt2 = _wait()
s2 = snap_info()
ck('正常扫描跑完', (not w._scanning) and w.table.rowCount() > 0,
   '耗时 %.0fs 行数=%d' % (_dt2, w.table.rowCount()))
# 快照存的是**全量**扫描结果（4404 行），表格显示的是筛选后的行（1071 行），两者本就不等
ck('正常扫描覆盖了快照', s2['saved_at'] != s1['saved_at'] and s2['mtime'] > s1['mtime']
   and s2['rows'] == len(w._all_rows) and s2['rows'] > 1000,
   'saved_at %s→%s ｜ 快照 %s 行 vs 全量缓存 %s 行 vs 表格 %s 行'
   % (s1['saved_at'], s2['saved_at'], s2['rows'], len(w._all_rows), w.table.rowCount()))
ck('快照数据日仍是今天', s2['date'] == time.strftime('%Y-%m-%d'), str(s2['date']))
w.close()

print('=' * 60)
print('结果：%d PASS / %d FAIL' % (len(P), len(F)))
if F:
    print('失败项:', F)
print('=' * 60)
sys.exit(1 if F else 0)
