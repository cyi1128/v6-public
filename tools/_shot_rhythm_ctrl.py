# -*- coding: utf-8 -*-
"""给「市场节奏」两个 Tab 截离屏图，用于交付前的肉眼自检（列宽/截断/颜色）。

真实数据：股票代码+名称取自 data\\cache\\band_pattern.db，控盘分由本地K线真实算出；
行结构（题材/家数/可介入候选等）按引擎契约构造 —— 截图只用于看版式，不代表当日扫描结果。
"""
import os
import sqlite3
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

conn = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
rows = conn.execute('SELECT DISTINCT code, name FROM pattern_record').fetchall()
pairs = [(str(c), n) for c, n in rows if c and n]
print('样本股票 %d 只' % len(pairs), flush=True)

from services.control_profile import get_ctrl_map          # noqa: E402

need = pairs[:24]
get_ctrl_map([c for c, _ in need])          # 预热真实控盘分

picks_pool = need[:16]
lad_pool = need[16:24] or need[:6]


def mk(i):
    c, n = picks_pool[i % len(picks_pool)]
    return [c, n, 1.2 + i * 0.9, 1.3 + i * 0.15, 8.6 + i, 1.1 + i,
            2.6e8 + i * 8e7, 32.0 + i * 3, 3.1 + i * 0.4, 0.18, 1 if i % 2 else 0]


pick_rows = []
_NP = [5, 4, 3, 2, 0, 1]
names = ['机器人', '固态电池', '算力租赁', '汽车零部件', '化学制品', '光伏设备']
for k, nm in enumerate(names):
    ps = [mk(k * 2 + j) for j in range(_NP[k])]   # 故意含 5 只（上限）与 0 只，检验是否被截断
    pick_rows.append({
        'kind': 'theme' if k % 2 == 0 else 'industry', 'name': nm,
        'count': 6 - k, 'avg_pct': 7.4 - k * 1.9, 'max_pct': 10.0,
        'lead_name': ps[0][1] if ps else '--',
        'lead_code': ps[0][0] if ps else '',
        'lead_pct': 9.98, 'dragons': [],
        'members': [[c, n, 3.0] for c, n in need[k:k + 5]],
        'picks': ps,
    })

rhythm_rows = []
for k, nm in enumerate(names[:4]):
    lad = lad_pool[k * 2:k * 2 + 3] or lad_pool[:2]
    rhythm_rows.append({
        'theme': nm, 'mainline': '主线' if k == 0 else '', 'state': ['加速', '持续', '启动', '分歧'][k],
        'count': 6 - k, 'prev_count': 3, 'run': k + 1, 'lbc_max': 3 - k % 3,
        'lead': lad[0][1], 'lead_code': lad[0][0], 'lead_lbc': 3,
        'lead_time': '09:35', 'is_attribute': 0,
        'trend': [1, 2, 4, 6 - k], 'cluster': ['国资改革', '机器人'],
        'ladder': [{'code': c, 'name': n, 'lbc': 2 + i, 'time': '09:3%d' % i,
                    'reason': '机器人+固态电池'} for i, (c, n) in enumerate(lad)],
    })

from PyQt6.QtWidgets import QApplication               # noqa: E402

app = QApplication.instance() or QApplication([])
from ui.battle_widgets import market_rhythm_widget as MW   # noqa: E402

MW.MarketRhythmWidget.refresh = lambda self, force=False: None
w = MW.MarketRhythmWidget()
try:
    w.stop_timer()
except Exception:
    pass
w.resize(int(os.environ.get('SHOT_W', '1850')), 470)
w._rows = rhythm_rows
w._pick_rows = pick_rows
w._render_rhythm_rows(rhythm_rows)
w._render_pick_rows(pick_rows)
w.show()
app.processEvents()
w._switch_tab(0)
app.processEvents()
w.grab().save(r'D:\QuantMonitorV6\tools\_shot_rhythm_tab1.png')
w._switch_tab(1)
app.processEvents()
w.grab().save(r'D:\QuantMonitorV6\tools\_shot_rhythm_tab2.png')
print('截图: tools\\_shot_rhythm_tab1.png / tools\\_shot_rhythm_tab2.png', flush=True)
