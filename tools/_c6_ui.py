# -*- coding: utf-8 -*-
"""离屏真实实例化验证 C6 文案在日K建仓表里可见，且原有列/标签没有回归。

不依赖 py_compile：直接跑真实 _daily_fetch_and_calc + _daily_render_table，再读回单元格。
输出 tools\\c6_ui.txt
"""
import os
import re
import sqlite3
import sys
import time
import types

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\QuantMonitorV6')
sys.stdout.reconfigure(encoding='utf-8')

OUT = r'D:\QuantMonitorV6\tools\c6_ui.txt'
DB = r'D:\QuantMonitorV6\data\cache\band_pattern.db'
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


PASS = [0, 0]


def check(name, cond, extra=''):
    if cond:
        PASS[0] += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        PASS[1] += 1
        P('  FAIL  %s %s' % (name, extra))


P('=' * 100)
P('C6 UI 验证（离屏真实渲染）   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 100)

from PyQt6.QtWidgets import QApplication, QCheckBox  # noqa: E402

app = QApplication([])
import ui.battle_widgets.atr_t_widget as M  # noqa: E402

cls = None
for _n in dir(M):
    _v = getattr(M, _n)
    if isinstance(_v, type) and hasattr(_v, '_daily_render_table'):
        cls = _v
        break
assert cls is not None, '找不到 AtrTWidget 类'
P('类名: %s ｜ 列数 %d ｜ COL_D_CTRL=%s ｜ COL_D_TRIGGER=%s'
  % (cls.__name__, len(M.HEADER_DAILY), M.COL_D_CTRL, getattr(M, 'COL_D_TRIGGER', '?')))
P('表头: %s' % M.HEADER_DAILY)
P('')


class Stub:
    pass


o = Stub()
o.daily_table = M.make_table(len(M.HEADER_DAILY), M.HEADER_DAILY)
o._chk_env = QCheckBox()
o._env_hint = None
o._daily_rows = []
o._daily_check_market = lambda *a, **k: None
for _m in ('_daily_visible_rows', '_daily_render_table', '_daily_fetch_and_calc'):
    setattr(o, _m, types.MethodType(getattr(cls, _m), o))
try:
    _rows = o._daily_fetch_and_calc()
    P('_daily_fetch_and_calc 返回: %s 行' % (len(_rows) if _rows else 0))
    o._daily_rows = _rows or []
except Exception as e:
    P('fetch 途中异常（不影响已填好的行）: %s %s' % (type(e).__name__, e))
o._daily_render_table()
n = o.daily_table.rowCount()
P('表格实际行数 = %d' % n)
P('')

# 从界面读回：控盘列文本 + 它的 tooltip；触发条件列的 tooltip
rows = []
for i in range(n):
    ci = o.daily_table.item(i, M.COL_D_CTRL)
    ni = o.daily_table.item(i, M.COL_D_NAME)
    di = o.daily_table.item(i, M.COL_D_CODE)
    tri = o.daily_table.item(i, getattr(M, 'COL_D_TRIGGER', -1)) if getattr(
        M, 'COL_D_TRIGGER', -1) >= 0 else None
    rows.append({
        'code': (di.text() if di else ''),
        'name': (ni.text() if ni else ''),
        'ctrl_txt': (ci.text() if ci else ''),
        'ctrl_tip': (ci.toolTip() if ci else ''),
        'trig_tip': (tri.toolTip() if tri else ''),
        'score': float(re.sub(r'[^0-9.]', '', (ci.text() if ci else '') or '0') or 0),
        'stage': ((ci.toolTip() if ci else '') or '').split('（')[1].split('）')[0]
        if '（' in ((ci.toolTip() if ci else '') or '') else '',
    })

ui_c6 = [r for r in rows if 'C6观察' in r['ctrl_tip']]
ui_c4 = [r for r in rows if 'C4观察' in r['ctrl_tip']]
ui_trig6 = [r for r in rows if 'C6观察' in r['trig_tip']]
P('=== 界面读回 ===')
P('控盘列 tooltip 含「C6观察」的行: %d 条' % len(ui_c6))
P('控盘列 tooltip 含「C4观察」的行: %d 条' % len(ui_c4))
P('触发条件列 tooltip 含「C6观察」的行: %d 条' % len(ui_trig6))
for r in ui_c6[:6]:
    P('   %-6s %-7s 控盘=%-14s tip=%s'
      % (r['code'], r['name'][:6], r['ctrl_txt'],
         r['ctrl_tip'].replace('\n', ' / ')[-46:]))
P('')

# 与 DB 对照：界面里出现的代码中，DB 标了 c6_ok=1 的有多少
con = sqlite3.connect(DB)
db6 = {}
for c, k in con.execute('SELECT code, c6_ok FROM pattern_record').fetchall():
    db6[c] = max(db6.get(c, 0), k)
db4 = dict(con.execute('SELECT code, MAX(c4_ok) FROM pattern_record GROUP BY code').fetchall())
con.close()
db6_codes = set(c for c, k in db6.items() if k == 1)
ui_codes = set(r['code'] for r in rows if r['code'])
P('DB 里 c6_ok=1 的股票数: %d ｜ 界面出现的股票数: %d ｜ 交集: %d'
  % (len(db6_codes), len(ui_codes), len(db6_codes & ui_codes)))
miss = sorted((db6_codes & ui_codes) - set(r['code'] for r in ui_c6))
check('DB 中 c6_ok=1 且在界面出现的股票，界面 tooltip 全部带 C6 文案',
      not miss, '漏 %d 只 %s' % (len(miss), miss[:6]))
extra = sorted(set(r['code'] for r in ui_c6) - db6_codes)
check('界面带 C6 文案的股票，DB 里 c6_ok 都为 1', not extra, '多 %s' % extra[:6])

# 回归（改成语义断言，不再用魔法数字）：标签只能来自控盘提示，且候选必须真的够格
labeled = [r for r in rows if '·' in r['ctrl_txt']]
n_cand = sum(1 for r in labeled if r['ctrl_txt'].endswith('候选'))
n_dist = sum(1 for r in labeled if r['ctrl_txt'].endswith('出货'))
n_wash = sum(1 for r in labeled if r['ctrl_txt'].endswith('洗盘'))
P('')
P('控盘列带标签行: %d 条（候选 %d / 出货 %d / 洗盘 %d）｜ 不带标签 %d 条'
  % (len(labeled), n_cand, n_dist, n_wash, len(rows) - len(labeled)))
cand_rows = [r for r in labeled if r['ctrl_txt'].endswith('候选')]
bad_cand = [r for r in cand_rows if r['score'] < 85.0]
check('带「候选」标签的行控盘分全部 >= 85（规则③硬条件）', not bad_cand,
      '越界 %d 条 %s' % (len(bad_cand), [(r['code'], r['score']) for r in bad_cand[:5]]))
bad_dist = [r for r in labeled if r['ctrl_txt'].endswith('出货') and r['stage'] != 'distribute']
check('带「出货」标签的行 stage_guess 都是 distribute', not bad_dist,
      '越界 %s' % [(r['code'], r['stage']) for r in bad_dist[:5]])
check('带标签行数已回到「只有控盘提示」的量级（< 之前被污染的 59）',
      0 < len(labeled) < 59, '实际 %d' % len(labeled))
only_c6 = [r for r in rows if 'C6观察' in r['ctrl_tip'] and '·' not in r['ctrl_txt']]
check('有 C6 文案但没有控盘提示的行：只显示分数、不挂标签', len(only_c6) >= 20,
      '实际 %d 条' % len(only_c6))

# 断言：控盘列仍有值；环境列仍是数字（没有因新字段错位）
has_ctrl = any(r['ctrl_txt'] not in ('', '--') for r in rows)
check('控盘列有值（不是整列 --）', has_ctrl)
env_ok = True
for i in range(n):
    it = o.daily_table.item(i, M.COL_D_ENV)
    t = (it.text() if it else '').strip()
    if t and t != '--' and not t.replace('.', '').replace('-', '').isdigit():
        env_ok = False
        break
check('环境分列仍是数字（新字段没有造成列错位）', env_ok)
bd = [o.daily_table.item(i, M.COL_D_BASE_DATE).text() for i in range(min(3, n))
      if o.daily_table.item(i, M.COL_D_BASE_DATE)]
P('基准日列样本: %s' % bd)

P('')
P('=' * 100)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 100)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
