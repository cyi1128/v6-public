# -*- coding: utf-8 -*-
"""规则① 洗盘文案降级 —— DB + UI 验证（在重跑全市场扫描之后运行）。

验证：
  [D] 库里再无洗盘文案；stage_guess 仍记录 wash；其他两类标签条数不变
  [E] 离屏真实渲染日K建仓表：控盘列不再出现「洗盘」标签，候选/出货正常
  [F] 用改动前的备份模块逐行重算，证明差异只落在「改前有洗盘文案」的那些行上
"""
import importlib.machinery
import importlib.util
import io
import re
import sqlite3
import sys
import time
import types

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

ROOT = r'D:\QuantMonitorV6'
DB = ROOT + r'\data\cache\band_pattern.db'
BAK = ROOT + r'\services\band_pattern_engine.py.bak_before_washnote'
OUT = r'D:\QuantMonitorV6\tools\washnote_off_dbui.txt'
WASH = '高度控盘 + 疑似洗盘，关注启动'

_lines = []
PASS = [0]
FAIL = [0]


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


def check(name, cond, extra=''):
    if cond:
        PASS[0] += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        FAIL[0] += 1
        P('  FAIL  %s %s' % (name, extra))


P('=' * 104)
P('规则① 洗盘文案降级 —— DB 与 UI 验证   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 104)

sys.path.insert(0, ROOT)
import services.band_pattern_engine as E  # noqa: E402

_ld = importlib.machinery.SourceFileLoader('bpe_old_wash', BAK)
_sp = importlib.util.spec_from_loader('bpe_old_wash', _ld)
Old = importlib.util.module_from_spec(_sp)
_ld.exec_module(Old)

# ============================================================ D
P('')
P('[D] band_pattern.db')
con = sqlite3.connect(DB)
cur = con.cursor()
names = [r[1] for r in cur.execute('PRAGMA table_info(pattern_record)').fetchall()]
rows = cur.execute(
    'SELECT code, name, pattern_id, signal_level, control_score, stage_guess,'
    ' struct_pos, ctrl_tag, note FROM pattern_record').fetchall()
P('  表列数 = %d ｜ 行数 = %d' % (len(names), len(rows)))

n_note_wash = sum(1 for r in rows if '疑似洗盘' in (r[8] or ''))
n_tag_wash = sum(1 for r in rows if '疑似洗盘' in (r[7] or ''))
P('  note 含「疑似洗盘」 = %d 条 ｜ ctrl_tag 含「疑似洗盘」 = %d 条'
  % (n_note_wash, n_tag_wash))
check('note 字段里不再有任何洗盘文案', n_note_wash == 0, '实际 %d' % n_note_wash)
check('ctrl_tag 字段里不再有任何洗盘文案', n_tag_wash == 0, '实际 %d' % n_tag_wash)

stage_dist = {}
for r in rows:
    stage_dist[r[5]] = stage_dist.get(r[5], 0) + 1
P('  stage_guess 分布：%s' % stage_dist)
check("stage_guess 仍正常记录 'wash'（字段没被一起删掉）",
      stage_dist.get('wash', 0) > 0, 'wash=%d' % stage_dist.get('wash', 0))
check('stage_guess 取值仍只有 wash / distribute / unknown',
      set(stage_dist) <= {'wash', 'distribute', 'unknown', ''}, str(set(stage_dist)))

tag_dist = {}
for r in rows:
    t = (r[7] or '').strip()
    if t:
        for x in t.split(' ｜ '):
            tag_dist[x] = tag_dist.get(x, 0) + 1
P('  ctrl_tag 分布：%s' % tag_dist)
check('ctrl_tag 里只剩「候选 / 出货」两类（洗盘已消失）',
      set(tag_dist) <= {'高度控盘候选', '出货风险警示'}, str(set(tag_dist)))
n_cand_db = tag_dist.get('高度控盘候选', 0)
n_dist_db = tag_dist.get('出货风险警示', 0)
P('  库内：候选 %d 条 ｜ 出货 %d 条 ｜ 合计 %d 条'
  % (n_cand_db, n_dist_db, n_cand_db + n_dist_db))

# ============================================================ F（先算，D 要用）
P('')
P('[F] 与改动前的备份模块逐行重算：差异必须只落在「改前有洗盘文案」的行上')
P('  口径说明（上一轮验证脚本在这里踩过坑）：判定函数吃的 pos 是「近120日位置」'
  ' = (末收盘-min(close[-120:]))/(max-min)，')
P('  取值 0~1；库里 struct_pos 是「横盘结构位置」百分比（引擎 L1548），两者不是同一个量，'
  '所以下面独立算 pos120，不用 struct_pos。')

import duckdb  # noqa: E402

_kc = duckdb.connect(ROOT + r'\data\cache\kline_cache.duckdb', read_only=True)


def pos120(code):
    r = _kc.execute(
        'SELECT close FROM kline_cache WHERE code=? ORDER BY date DESC LIMIT 120',
        [code]).fetchall()
    if len(r) < 120:
        return None
    cl = [float(x[0]) for x in r]
    lo, hi = min(cl), max(cl)
    return (cl[0] - lo) / (hi - lo + 1e-8)


pos_map = {}
was_wash, other_diff, now_cand_after = [], [], []
n_pos_missing = 0
for r in rows:
    code, name, pid, lvl, ctrl, stage, pos, tag, note = r
    ctrl = float(ctrl or 0.0)
    pf = pos_map.get(code, '?')
    if pf == '?':
        pf = pos120(code)
        pos_map[code] = pf
    if pf is None:
        n_pos_missing += 1
    new_tags = E._ctrl_note_tags(ctrl, stage, pf)
    old_tags = Old._ctrl_note_tags(ctrl, stage, pf)
    if WASH in old_tags:
        was_wash.append((code, name, pid, ctrl, stage, pf, old_tags, new_tags, tag))
    if [x for x in old_tags if x != WASH] != new_tags:
        other_diff.append((code, old_tags, new_tags))
    if WASH in old_tags and '高度控盘候选' in new_tags:
        now_cand_after.append(code)
P('  K 线不足 120 根、算不出 pos120 的行 = %d 条' % n_pos_missing)
P('  改前会出洗盘文案的行 = %d 条（这就是本批生效的范围）' % len(was_wash))
P('  改前有洗盘、改后仍保留「候选」的行 = %d 条' % len(now_cand_after))
for c, n, pid, ctrl, st, p, o, nw, tag in was_wash[:12]:
    P('    %-6s %-8s 模式%s 控盘=%-5.1f %-10s pos120=%.4f 改前%s -> 改后%s ｜ 落库ctrl_tag=%r'
      % (c, n, pid, ctrl, st, p, o, nw, tag))
if len(was_wash) > 12:
    P('    ...（其余 %d 条略）' % (len(was_wash) - 12))
check('改前确实存在会被关闭的洗盘文案行（说明这不是空改动）', len(was_wash) >= 1,
      '实际 %d 条' % len(was_wash))
check('除洗盘那一条外，其他标签逐行完全一致（没误伤候选/出货）',
      not other_diff, '异常 %s' % other_diff[:3])


def _recalc(r):
    c = float(r[4] or 0.0)
    return ' ｜ '.join(E._ctrl_note_tags(c, r[5], pos_map[r[0]]))


bad_recalc = [r[0] for r in rows if (r[7] or '') != _recalc(r)]
P('  用 pos120 独立重算后对不上的行 = %d 条 %s' % (len(bad_recalc), bad_recalc[:6]))
check('落库的 ctrl_tag 与「关闭洗盘后的规则 + 独立算的 pos120」逐行一致',
      not bad_recalc, '不一致 %d 条 %s' % (len(bad_recalc), bad_recalc[:5]))
# 这些行在库里必须仍是 wash（字段保留），且 ctrl_tag 不含洗盘
bad_field = [w[0] for w in was_wash if w[4] != 'wash' or '疑似洗盘' in (w[8] or '')]
check('这些行的 stage_guess 仍是 wash、ctrl_tag 已无洗盘文案',
      not bad_field, '异常 %s' % bad_field[:5])
miss = [r[0] for r in rows
        if float(r[4] or 0) >= E._CTRL_HIGH and pos_map[r[0]] is not None
        and pos_map[r[0]] < E._CTRL_CAND_POS and '高度控盘候选' not in (r[7] or '')]
check('候选规则（pos120<0.25 且 ctrl>=85）逐行都拿到了标签', not miss, '漏 %s' % miss[:5])

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
P('  类名 %s ｜ 列数 %d ｜ 控盘列下标 %d' % (cls.__name__, len(M.HEADER_DAILY),
                                            M.COL_D_CTRL))


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

lab = [r for r in ui if '·' in r['ctrl_txt']]
n_cand_ui = sum(1 for r in lab if r['ctrl_txt'].endswith('候选'))
n_dist_ui = sum(1 for r in lab if r['ctrl_txt'].endswith('出货'))
n_wash_ui = sum(1 for r in lab if r['ctrl_txt'].endswith('洗盘'))
n_tip_wash = sum(1 for r in ui if '疑似洗盘' in r['tip'])
P('  控盘列带标签 = %d 条（候选 %d / 出货 %d / 洗盘 %d）｜ tooltip 含洗盘文案 = %d 条'
  % (len(lab), n_cand_ui, n_dist_ui, n_wash_ui, n_tip_wash))
check('界面控盘列不再出现「洗盘」标签', n_wash_ui == 0, '实际 %d' % n_wash_ui)
check('界面 tooltip 也不再出现洗盘文案', n_tip_wash == 0, '实际 %d' % n_tip_wash)
check('界面仍有候选 / 出货标签（其他规则正常显示）',
      n_cand_ui + n_dist_ui >= 1, '候选 %d 出货 %d' % (n_cand_ui, n_dist_ui))
for r in lab[:14]:
    P('    %-6s 控盘=%-12s %s' % (r['code'], r['ctrl_txt'],
                                  r['tip'].replace('\n', ' ')[:88]))

# 界面标签与库里 ctrl_tag 的一致性（只看界面出现的股票）
db_tag = {r[0]: (r[7] or '') for r in rows}
bad = []
for r in ui:
    want = db_tag.get(r['code'], '')
    shown = r['ctrl_txt']
    if want and '·' in shown:
        ok = (('高度控盘候选' in want) == shown.endswith('候选')) and \
             (('出货风险警示' in want) == shown.endswith('出货'))
        if not ok:
            bad.append((r['code'], want, shown))
check('界面标签与库内 ctrl_tag 一一对应（没有对不上的）', not bad, '异常 %s' % bad[:5])

P('')
P('=' * 104)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], FAIL[0]))
P('=' * 104)
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(_lines))
sys.exit(1 if FAIL[0] else 0)
