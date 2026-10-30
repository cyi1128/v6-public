# -*- coding: utf-8 -*-
"""决策页 + 主线过滤 验证（离屏渲染 + 截图）。"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

# 1) 服务层
from services.decision_page_service import (compute_decision, load_main_themes,
                                            filter_rows_by_themes)
r = compute_decision()
assert r['state'] == '退潮期' and r['sentiment'] == 26
assert r['cards'] is not None
print('PASS 决策服务: 状态%s 情绪%d 总分%s 共振%s' % (
    r['state'], r['sentiment'], r['total'], r['resonance']))
# 退潮期闸门：结论不能再喊进攻
assert '不新开仓' in r['concl']
print('PASS 退潮期闸门:', r['concl'])
# 持仓预警只有真实成本的
assert all(h['cost'] for h in r['holdings'])
codes = [h['code'] for h in r['holdings']]
print('PASS 持仓预警只含真持仓:', codes)

# 2) 主线过滤
themes = load_main_themes()
print('主线:', [(t['theme'], t['cluster']) for t in themes])
snap = r
# 控盘默认结果
import services.control_screen_service as SS
bars = SS.load_all_bars()
rows, stats = SS.scan_market(bars=bars)
base = SS.apply_filters(rows)
print('默认筛选: %d 只' % len(base))
sub = filter_rows_by_themes(base)
print('仅看主线: %d 只' % len(sub))
assert len(sub) < len(base)

# 3) 离屏渲染决策页
from ui.battle_widgets.decision_page_widget import DecisionPageWidget
w = DecisionPageWidget()
w.resize(1700, 900)
w.show()
app.processEvents()
w._render(compute_decision())
app.processEvents()
w.grab().save(os.path.join(ROOT, 'tools', '_shot_decision.png'))
print('PASS 决策页渲染截图')

# 4) 控盘页 + 开关
from ui.battle_widgets.control_screen_widget import ControlScreenWidget
cw = ControlScreenWidget()
cw._all_rows = list(rows)
cw._stats = dict(stats)
cw._apply_and_render(fill=False)
n0 = len(cw._rows)
cw._ck_mainline.setChecked(True)
n1 = len(cw._rows)
cw._ck_mainline.setChecked(False)
n2 = len(cw._rows)
print('PASS 开关: 默认%d → 主线%d → 关闭%d' % (n0, n1, n2))
assert n0 == n2 and n1 < n0
cw.resize(1700, 900)
cw.show()
cw._ck_mainline.setChecked(True)
cw._apply_and_render(fill=False)
app.processEvents()
cw.grab().save(os.path.join(ROOT, 'tools', '_shot_control_mainline.png'))
print('PASS 控盘页渲染截图')
print('ALL VERIFY PASS')
