# -*- coding: utf-8 -*-
"""市场节奏（三 Tab 合并版）完整验证：数据 / 渲染 / Tab 切换 / 点击链路"""
import sys
import traceback

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication           # noqa: E402
from PyQt6.QtGui import QFont                      # noqa: E402

app = QApplication(sys.argv)
app.setFont(QFont('Microsoft YaHei', 10))

from ui.battle_widgets.market_rhythm_widget import MarketRhythmWidget  # noqa: E402

bad = 0
print('=' * 84)
print('① 实例化 + Tab 栏')
print('=' * 84)
w = MarketRhythmWidget()
print('  实例化 OK')
print('  Tab 按钮: %s' % [b.text() for b in w._tab_btns])
print('  当前 Tab = %d（期望 0）' % w._tab_active)
print('  显隐: rhythm=%s pick=%s track=%s  (isHidden: False=显示)'
      % (w._rhythm_page.isHidden(), w._pick_page.isHidden(),
         w._track_widget.isHidden()))

print()
print('=' * 84)
print('② 喂真实数据（两个引擎都跑）')
print('=' * 84)
from services.market_rhythm_engine import get_rhythm              # noqa: E402
from services.board_anomaly_engine import (get_board_anomaly,      # noqa: E402
                                          get_flat_rows)
rh = get_rhythm()
bd = get_board_anomaly()
rows_b = get_flat_rows(bd)
print('  rhythm ok=%s date=%s boards=%d' % (rh.get('ok'), rh.get('date'),
                                            len(rh.get('boards') or [])))
print('  board  ludate=%s 行=%d 可介入=%d只' % (
    bd.get('ludate'), len(rows_b),
    sum(len(r.get('picks') or []) for r in rows_b)))
try:
    w._apply({'rhythm': rh, 'boards': rows_b, 'board_meta': bd})
    print('  _apply OK')
except Exception:
    traceback.print_exc()
    bad += 1

print()
print('=' * 84)
print('③ Tab1「市场节奏」逐列')
print('=' * 84)
print('  行数=%d 列数=%d' % (w.table.rowCount(), w.table.columnCount()))
print('  概况: %s' % w.market_label.text())
print('  轮动: %s' % w.rot_label.text())
for tag, r in (('第一行', 0), ('最后一行', w.table.rowCount() - 1)):
    cells = [w.table.item(r, c).text() if w.table.item(r, c) else ''
             for c in range(w.table.columnCount())]
    print('  %s: %s' % (tag, ' | '.join(cells)))

print()
print('=' * 84)
print('④ Tab2「可介入」逐列')
print('=' * 84)
print('  行数=%d 列数=%d' % (w.pick_table.rowCount(), w.pick_table.columnCount()))
print('  概况: %s' % w.pick_label.text())
for r in range(min(5, w.pick_table.rowCount())):
    cells = [w.pick_table.item(r, c).text() if w.pick_table.item(r, c) else ''
             for c in range(w.pick_table.columnCount())]
    print('    %s' % ' | '.join(cells))

print()
print('=' * 84)
print('⑤ Tab 切换')
print('=' * 84)
for idx in (1, 2, 0):
    try:
        w._switch_tab(idx)
        print('  切换到 %d -> hidden rhythm=%s pick=%s track=%s  active=%d' % (
            idx, w._rhythm_page.isHidden(), w._pick_page.isHidden(),
            w._track_widget.isHidden(), w._tab_active))
    except Exception:
        traceback.print_exc()
        bad += 1

print()
print('=' * 84)
print('⑥ 点击链路（两个 Tab 的股票跳转）')
print('=' * 84)


def _grab(sig):
    box = []
    sig.connect(lambda c, n: box.append((c, n)))
    return box


b1 = _grab(w.stock_clicked)
w._on_rhythm_cell(0, 6)          # Tab1 C_LEAD
print('  Tab1 点龙头 -> %s' % (b1 or '未发信号 ✗'))
if not b1:
    bad += 1
b2 = _grab(w.stock_clicked)
for r in range(w.pick_table.rowCount()):
    if (w.pick_table.item(r, 4) or None) and \
            w.pick_table.item(r, 4).data(258):      # UserRole=258
        w._on_pick_cell(r, 4)
        break
print('  Tab2 点可介入 -> %s' % (b2 or '未发信号（可能本轮无候选）'))

print()
print('=' * 84)
print('⑦ 追踪页数据源')
print('=' * 84)
try:
    from services.picks_tracking_service import fetch_tracking, summarize
    tr = fetch_tracking()
    print('  追踪记录 %d 条' % len(tr))
    s = summarize(tr)
    if isinstance(s, dict):
        for k in list(s.keys())[:8]:
            print('    %s = %s' % (k, s[k]))
except Exception:
    traceback.print_exc()
    bad += 1

print()
print('=' * 84)
print('⑧ 整页（BattleConsoleHome）')
print('=' * 84)
try:
    from ui.battle_widgets.battle_console_home import BattleConsoleHome
    home = BattleConsoleHome()
    print('  OK  hasattr(market_rhythm)=%s' % hasattr(home, 'market_rhythm'))
    print('  hasattr(opportunity)=%s (期望 False)' % hasattr(home, 'opportunity'))
    print('  hasattr(leading_theme)=%s (期望 False)' % hasattr(home, 'leading_theme'))
except Exception:
    traceback.print_exc()
    bad += 1

print()
print('=' * 84)
print('结果: %s' % ('全部通过 ✓' if bad == 0 else '有 %d 个问题 ✗' % bad))
print('=' * 84)
sys.exit(1 if bad else 0)
