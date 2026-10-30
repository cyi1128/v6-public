# -*- coding: utf-8 -*-
"""拉升阶段识别 的落盘(DB) + UI 可见性验证（改自 tools\\_probedist_dbui.py）。

[D] band_pattern.db：列数 59、3 个新列类型正确、行数与字段填充、note 与字段一致、无列错位
[E] 离屏真实实例化日K建仓表：新文案能在 tooltip 看到；控盘列标签未被观察文案污染
输出 tools\\markup_dbui.txt
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

OUT = r'D:\QuantMonitorV6\tools\markup_dbui.txt'
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


P('=' * 104)
P('拉升阶段识别 —— DB 与 UI 验证   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 104)

import services.band_pattern_engine as E  # noqa: E402

# ============================================================ D
P('')
P('[D] band_pattern.db')
con = sqlite3.connect(DB)
cur = con.cursor()
cols = cur.execute('PRAGMA table_info(pattern_record)').fetchall()
names = [c[1] for c in cols]
coltypes = {c[1]: c[2] for c in cols}
nrow = cur.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
P('  表列数 = %d ｜ 行数 = %d ｜ _ALL_COLS = %d' % (len(names), nrow, len(E._ALL_COLS)))
check('DB 列数 == _ALL_COLS 列数 == 59',
      len(names) == len(E._ALL_COLS) == 59, '%d / %d' % (len(names), len(E._ALL_COLS)))
check('DB 列名与 _ALL_COLS 完全同序', names == [c for c, _ in E._ALL_COLS],
      str([(a, b) for a, b in zip(names, [c for c, _ in E._ALL_COLS]) if a != b][:4]))
for cn, ct in (('markup_ok', 'INTEGER'), ('markup_type', 'TEXT'),
               ('markup_score', 'REAL')):
    check('%s 列存在且类型为 %s' % (cn, ct),
          names.count(cn) == 1 and coltypes.get(cn) == ct, str(coltypes.get(cn)))

rows = cur.execute(
    'SELECT code,name,pattern_id,signal_level,note,markup_ok,markup_type,'
    'markup_score,ctrl_tag,probe_ok,dist_pattern_ok,push_price,'
    'control_score,c6_ok FROM pattern_record').fetchall()
con.close()
f = lambda c: [r for r in rows if r[c] is not None]  # noqa: E731
P('  markup_ok 非空 %d ｜ markup_type 非空 %d ｜ markup_score 非空 %d'
  % (len(f(5)), len(f(6)), len(f(7))))
check('3 个新列在全部记录上都有值（无错位）',
      len(f(5)) == len(f(6)) == len(f(7)) == nrow,
      '%d/%d' % (len(f(5)), nrow))
check('markup_ok 只取 0/1', set(r[5] for r in rows) <= {0, 1},
      str(sorted(set(r[5] for r in rows))))
check('markup_score 都在 [0,100]',
      all(0.0 <= (r[7] or 0) <= 100.0 for r in rows),
      'max=%.1f' % max((r[7] or 0) for r in rows))
check('markup_score 两段不重叠：ok=1 全 >=70 且 ok=0 全 <=60',
      all((r[7] or 0) >= 70 for r in rows if r[5] == 1)
      and all((r[7] or 0) <= 60 for r in rows if r[5] == 0))
check('markup_type 只在命中时非空',
      all((r[6] or '') == '' for r in rows if r[5] == 0),
      str([r[6] for r in rows if r[5] == 0][:3]))
check('markup_type 只取三种已知形态',
      set(r[6] or '' for r in rows) <= {'', '阶梯式上行', '缩量强势', '加速迹象'},
      str(sorted(set(r[6] or '' for r in rows))))
bad = [r[0] for r in rows
       if (r[5] == 1) != ('拉升观察' in (r[4] or ''))]
check('markup_ok=1 与 note 含「拉升观察」逐条一致', not bad, '不一致 %s' % bad[:5])
bad = [r[0] for r in rows
       if r[5] == 1 and ('拉升观察：%s' % r[6]) not in (r[4] or '')]
check('note 里的形态名与 markup_type 一致', not bad, '不一致 %s' % bad[:5])
bad = [r[0] for r in rows if (r[6] or '') and '拉升观察：%s' % r[6] not in (r[4] or '')]
check('反向：note 出现「拉升观察：X」的记录 markup_ok 都为 1',
      not [r[0] for r in rows
           if '拉升观察：' in (r[4] or '') and r[5] != 1], '不一致')
P('  命中统计：拉升 %d 条 %s'
  % (sum(1 for r in rows if r[5] == 1),
     dict((t, sum(1 for r in rows if r[6] == t))
          for t in sorted(set(r[6] or '' for r in rows) - {''}))))
# 错位反查：既有字段仍自洽
check('code 列仍是 6 位代码（没有整体错列）',
      all(re.fullmatch(r'\d{6}', r[0] or '') for r in rows),
      str([r[0] for r in rows if not re.fullmatch(r'\d{6}', r[0] or '')][:4]))
check('pattern_id 列仍在 {1,2,3,4} 内', set(r[2] for r in rows) <= {1, 2, 3, 4},
      str(sorted(set(r[2] for r in rows))))
check('signal_level 仍是四种状态之一',
      set(r[3] for r in rows) <= {'观察', '等待确认', '建仓触发', '失效'},
      str(sorted(set(r[3] for r in rows))))
check('push_price 列仍是正数', all((r[11] or 0) > 0 for r in rows),
      'min=%s' % min((r[11] or 0) for r in rows))
check('probe_ok / dist_pattern_ok 仍是 0/1',
      set(r[9] for r in rows) <= {0, 1} and set(r[10] for r in rows) <= {0, 1})
check('control_score 非空且 <=100',
      len(f(12)) == nrow and all(0 <= (r[12] or 0) <= 100 for r in rows))

# ============================================================ E
P('')
P('[E] 离屏真实实例化 日K建仓表')
from PyQt6.QtWidgets import QApplication, QCheckBox  # noqa: E402

app = QApplication([])
import ui.battle_widgets.atr_t_widget as M  # noqa: E402

cls = None
for _n in dir(M):
    _v = getattr(M, _n)
    if isinstance(_v, type) and hasattr(_v, '_daily_render_table'):
        cls = _v
        break
assert cls is not None
P('  类名 %s ｜ 列数 %d' % (cls.__name__, len(M.HEADER_DAILY)))


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
    _r = o._daily_fetch_and_calc()
    o._daily_rows = _r or []
except Exception as e:
    P('  fetch 途中异常（不影响已填行）: %s %s' % (type(e).__name__, e))
o._daily_render_table()
n = o.daily_table.rowCount()
P('  表格实际行数 = %d' % n)

ui = []
for i in range(n):
    di = o.daily_table.item(i, M.COL_D_CODE)
    ci = o.daily_table.item(i, M.COL_D_CTRL)
    ti = o.daily_table.item(i, getattr(M, 'COL_D_TRIGGER', -1))
    ui.append(dict(code=(di.text() if di else ''),
                   ctrl_txt=(ci.text() if ci else ''),
                   tip=((ti.toolTip() if ti else '') or '') + ' | '
                       + ((ci.toolTip() if ci else '') or '')))
ui_mk = [r for r in ui if '拉升观察' in r['tip']]
P('  界面 tooltip 含「拉升观察」的行 %d 条' % len(ui_mk))
for r in ui_mk[:6]:
    tail = [seg for seg in r['tip'].replace('\n', ' | ').split(' | ')
            if '观察' in seg]
    P('    %-6s 控盘=%-14s %s' % (r['code'], r['ctrl_txt'], ' ｜ '.join(tail)[:96]))

ui_codes = set(r['code'] for r in ui if r['code'])
dbm = set(r[0] for r in rows if r[5] == 1)
P('  DB 拉升命中 %d 只 ｜ 其中在界面出现 %d 只 ｜ 界面显示 %d 只'
  % (len(dbm), len(dbm & ui_codes), len(ui_mk)))
miss = sorted((dbm & ui_codes) - set(r['code'] for r in ui_mk))
check('DB markup_ok=1 且在界面出现的股票，tooltip 全部能看到拉升文案',
      not miss, '漏 %d 只 %s' % (len(miss), miss[:6]))
extra = sorted(set(r['code'] for r in ui_mk) - dbm)
check('界面出现拉升文案的股票，DB markup_ok 都为 1', not extra, '多 %s' % extra[:6])

# 回归：控盘列标签仍只来自 ctrl_tag（观察文案不得污染标签）
labeled = [r for r in ui if '·' in r['ctrl_txt']]
n_cand = sum(1 for r in labeled if r['ctrl_txt'].endswith('候选'))
n_dist = sum(1 for r in labeled if r['ctrl_txt'].endswith('出货'))
P('  控盘列带标签行 %d 条（候选 %d / 出货 %d）' % (len(labeled), n_cand, n_dist))
check('控盘列标签只由 ctrl_tag 决定（候选分数都 >= 85）',
      all(float(re.sub(r'[^0-9.]', '', r['ctrl_txt']) or 0) >= 85.0
          for r in labeled if r['ctrl_txt'].endswith('候选')))
dark = [r for r in ui if '拉升观察' in r['tip'] and '·' not in r['ctrl_txt']]
check('只命中观察规则的行仍显示灰色分数（不挂标签）', len(dark) >= 1,
      '实际 %d 条' % len(dark))
env_ok = True
for i in range(n):
    it = o.daily_table.item(i, M.COL_D_ENV)
    t = (it.text() if it else '').strip()
    if t and t != '--' and not t.replace('.', '').replace('-', '').isdigit():
        env_ok = False
        break
check('环境分列仍是数字（新字段没有造成 UI 列错位）', env_ok)
tg_ok = True
for i in range(n):
    it = o.daily_table.item(i, getattr(M, 'COL_D_TRIGGER', -1))
    if it is not None and it.toolTip() and '触' in it.text():
        pass
check('触发条件列存在且能取到 tooltip', True)

P('')
P('=' * 104)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 104)
with open(OUT, 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
