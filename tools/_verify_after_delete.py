# -*- coding: utf-8 -*-
"""旧模块删除后的完整验证（三模块合并 + 金铲子辅助清理）"""
import os
import sys
import traceback

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication           # noqa: E402
from PyQt6.QtGui import QFont                      # noqa: E402

app = QApplication(sys.argv)
app.setFont(QFont('Microsoft YaHei', 10))
ROOT = r'D:\QuantMonitorV6'
bad = 0


def sec(t):
    print()
    print('=' * 80)
    print(t)
    print('=' * 80)


sec('① 已删除的文件是否真的不在了')
for rel in [r'ui\battle_widgets\opportunity_widget.py',
            r'ui\battle_widgets\leading_theme_widget.py',
            r'services\golden_shovel_scanner.py',
            r'services\golden_spade_pool.py',
            r'data\cache\golden_spade.duckdb']:
    p = os.path.join(ROOT, rel)
    ok = not os.path.exists(p)
    print('  %-52s %s' % (rel, '已删除 ✓' if ok else '仍存在 ✗'))
    if not ok:
        bad += 1

sec('② 全项目还有没有指向它们的引用')
skip = {'backups', '.git', '__pycache__', '.preview', 'logs', 'tools'}
targets = ['opportunity_widget', 'leading_theme_widget', 'golden_shovel_scanner',
           'golden_spade_pool']
n = 0
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in skip and 'backup_' not in d]
    for fn in fns:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(dp, fn)
        try:
            s = open(p, encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        for t in targets:
            if t in s:
                for i, line in enumerate(s.splitlines(), 1):
                    if t in line:
                        n += 1
                        print('  残留 %s:%d  %s'
                              % (p.replace(ROOT + '\\', ''), i, line.strip()[:70]))
print('  残留数: %d  %s' % (n, '✓' if n == 0 else '✗'))
bad += n

sec('③ atr_t_widget 里的金铲子死代码是否清干净')
src = open(os.path.join(ROOT, r'ui\battle_widgets\atr_t_widget.py'),
           encoding='utf-8').read()
for k in ('golden_spade', '_gs_timer', '_daily_gs_', '_check_golden_spade'):
    c = src.count(k)
    print('  %-22s = %d  %s' % (k, c, '✓' if c == 0 else '✗'))
    if c:
        bad += 1
print('  行数 = %d（清理前 2306）' % len(src.splitlines()))

sec('④ 分时做T / 日K建仓（被改过的文件）还能不能跑')
try:
    from ui.battle_widgets.atr_t_widget import AtrTWidget
    w = AtrTWidget()
    print('  AtrTWidget 实例化 OK')
    for a in ('_gs_timer', '_daily_gs_timer', '_daily_gs_pool'):
        v = hasattr(w, a)
        print('    hasattr(%-18s)= %s (期望 False) %s' % (a, v, '✓' if not v else '✗'))
        if v:
            bad += 1
    for a in ('_flash_timer', '_daily_timer'):
        v = hasattr(w, a)
        print('    hasattr(%-18s)= %s (期望 True) %s' % (a, v, '✓' if v else '✗'))
        if not v:
            bad += 1
    w._switch_tab(1)
    w._switch_tab(0)
    print('    两个 Tab 来回切换 OK  active=%d' % w._tab_active)
except Exception:
    traceback.print_exc()
    bad += 1

sec('⑤ 整页 BattleConsoleHome')
try:
    from ui.battle_widgets.battle_console_home import BattleConsoleHome
    h = BattleConsoleHome()
    for a, exp in (('market_rhythm', True), ('atr_t', True),
                   ('opportunity', False), ('leading_theme', False)):
        v = hasattr(h, a)
        print('  hasattr(%-16s)= %-5s (期望 %s) %s'
              % (a, v, exp, '✓' if v == exp else '✗'))
        if v != exp:
            bad += 1
except Exception:
    traceback.print_exc()
    bad += 1

sec('⑥ 异动检测来源（日K建仓的信号源）')
try:
    from services.intraday_opportunity_engine import get_engine
    get_engine().scan()
    print('  get_engine().scan() OK —— anchor_tracker 的异动池仍有来源 ✓')
except Exception:
    traceback.print_exc()
    bad += 1

print()
print('=' * 80)
print('结果: %s' % ('全部通过 ✓' if bad == 0 else '有 %d 个问题 ✗' % bad))
print('=' * 80)
sys.exit(1 if bad else 0)
