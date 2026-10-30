# -*- coding: utf-8 -*-
"""离屏真实实例化验证：日K建仓表「控盘」列不是空的，且原有列没有错位。

不用 py_compile 代替验证 —— 直接跑真实的 _daily_fetch_and_calc + _daily_render_table，
再把单元格读回来。
"""
import os
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\QuantMonitorV6')
sys.stdout.reconfigure(encoding='utf-8')

from PyQt6.QtWidgets import QApplication, QCheckBox

app = QApplication([])
import ui.battle_widgets.atr_t_widget as M

cls = None
for _n in dir(M):
    _v = getattr(M, _n)
    if isinstance(_v, type) and hasattr(_v, '_daily_render_table'):
        cls = _v
        break
assert cls is not None, '找不到 AtrTWidget 类'
print('类名:', cls.__name__)
print('列数:', len(M.HEADER_DAILY), '| 表头:', M.HEADER_DAILY)
print('宽度:', M.DAILY_WIDTHS, '| COL_D_CTRL =', M.COL_D_CTRL,
      '| COL_D_ENV =', M.COL_D_ENV, '| COL_D_BASE_DATE =', M.COL_D_BASE_DATE)
print()


class Stub:
    pass


import types

o = Stub()
o.daily_table = M.make_table(len(M.HEADER_DAILY), M.HEADER_DAILY)
o._chk_env = QCheckBox()
o._env_hint = None
o._daily_rows = []
# 把真实方法绑到 stub 上（不跑 __init__），只把 _daily_check_market 换成空操作
o._daily_check_market = lambda *a, **k: None
for _m in ('_daily_visible_rows', '_daily_render_table', '_daily_fetch_and_calc'):
    setattr(o, _m, types.MethodType(getattr(cls, _m), o))
try:
    _rows = o._daily_fetch_and_calc()
    print('_daily_fetch_and_calc 返回: %s 行' % (len(_rows) if _rows else 0))
    o._daily_rows = _rows or []
except Exception as e:
    print('fetch 途中异常（不影响已填好的行数据）: %s %s' % (type(e).__name__, e))

print('_daily_rows =', len(o._daily_rows))
o._daily_render_table()
print('表格实际行数 =', o.daily_table.rowCount())
print()

n = o.daily_table.rowCount()
tipped = []
for i in range(n):
    ctrl_item = o.daily_table.item(i, M.COL_D_CTRL)
    txt = ctrl_item.text() if ctrl_item else '<None>'
    if '·' in txt:
        tipped.append((i, txt, ctrl_item.toolTip() if ctrl_item else ''))
_n_cand = sum(1 for _, t, _t in tipped if '候选' in t)
_n_dist = sum(1 for _, t, _t in tipped if '出货' in t)
_n_wash = sum(1 for _, t, _t in tipped if '洗盘' in t)
print('=== 控盘列带标签的行: %d 条（候选 %d / 出货 %d / 洗盘 %d）==='
      % (len(tipped), _n_cand, _n_dist, _n_wash))
for i, t, tp in tipped:
    nm = o.daily_table.item(i, M.COL_D_NAME)
    cd = o.daily_table.item(i, M.COL_D_CODE)
    print('   %-6s %-6s 控盘=%-8s tooltip=%s' % (
        (nm.text() if nm else '')[:6], (cd.text() if cd else ''),
        t, tp.replace('\n', ' / ')[:70]))
print()

print('=== 前三行完整读回（验证原有列没有错位）===')
for i in range(min(3, n)):
    vals = []
    for c in range(len(M.HEADER_DAILY)):
        it = o.daily_table.item(i, c)
        vals.append('%s=%s' % (M.HEADER_DAILY[c], (it.text() if it else '')[:12]))
    print('   ' + ' | '.join(vals))
print()

# 断言1：控盘列不允许整列为空
_has_ctrl = any((o.daily_table.item(i, M.COL_D_CTRL) or None) and
                o.daily_table.item(i, M.COL_D_CTRL).text() not in ('', '--')
                for i in range(n))
print('断言1 控盘列有值:', 'OK' if _has_ctrl else '失败')

# 断言2：环境分列仍是数字、基准日列仍是日期（没有因插入新列而错位）
_ok_env = all((o.daily_table.item(i, M.COL_D_ENV) is None) or
              (o.daily_table.item(i, M.COL_D_ENV).text().strip() in ('', '--')) or
              o.daily_table.item(i, M.COL_D_ENV).text().strip().replace('.', '').replace('-', '').isdigit()
              for i in range(n))
print('断言2 环境分列仍是数字:', 'OK' if _ok_env else '失败')
_bd = [o.daily_table.item(i, M.COL_D_BASE_DATE).text() for i in range(min(5, n))
       if o.daily_table.item(i, M.COL_D_BASE_DATE)]
print('断言3 基准日列样本:', _bd)

# 断言3：带标签的行数
print('断言4 带标签行数 = 31:', 'OK' if len(tipped) == 31 else '实际 %d' % len(tipped))
print('断言5 候选行数 = 15:', 'OK' if _n_cand == 15 else '实际 %d' % _n_cand)
print('断言6 出货行数 = 16:', 'OK' if _n_dist == 16 else '实际 %d' % _n_dist)
