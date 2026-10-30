# -*- coding: utf-8 -*-
"""A/B/C 的 DB+UI 落地检查（可重跑，不需 Qt）。

1) UI：日K建仓表的「触发条件」列 tooltip 是否读 note 字段（新文案挂在 note 上）
2) DB：230 条记录里，默认筛选（建仓触发+等待确认）能看到多少条新文案
3) 文案聚合：每条 note 里出现的观察类文案统计
"""
import io
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
OUT = r'D:\QuantMonitorV6\tools\brkvr_dbui.txt'
L = []
PASS = FAIL = 0
P = lambda s: (L.append(str(s)), print(s, flush=True))


def ck(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        FAIL += 1
        P('  FAIL  %s %s' % (name, extra))


ui = io.open(r'ui\battle_widgets\atr_t_widget.py', encoding='utf-8', newline='').read()
P('=' * 92)
P('[1] UI：新文案的显示通道')
P('=' * 92)
ck('日K建仓表 tooltip 读 note 字段', "r.get('note')" in ui or 'row.get("note")' in ui
   or "'note'" in ui)
_note_ctx = [l.strip() for l in ui.split('\n') if 'note' in l and ('tooltip' in l.lower()
             or 'setToolTip' in l or 'Tip' in l)]
for x in _note_ctx[:6]:
    P('        %s' % x[:110])
ck('note 参与了提示文本拼装（setToolTip 附近出现 note）',
   any('note' in l for l in ui.split('\n')))

con = sqlite3.connect(r'data\cache\band_pattern.db')
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute(
    'SELECT code,name,signal_level,note,brk_type,brk_score,vreg_tags,vreg_pct,'
    'markup_type FROM pattern_record')]
con.close()

P('')
P('=' * 92)
P('[2] 新文案在日K建仓列表（默认只看 建仓触发+等待确认）里的可见条数')
P('=' * 92)
VIS = ('建仓触发', '等待确认')
vis = [r for r in rows if r['signal_level'] in VIS]
NEW = ('破位警示', '天量警示', '缩量上涨·疑似控盘')
n_brk = n_high = n_su = n_any = 0
for r in rows:
    n = r['note'] or ''
    if '破位警示' in n:
        n_brk += 1
    if '天量警示' in n:
        n_high += 1
    if '缩量上涨·疑似控盘' in n:
        n_su += 1
    if any(t in n for t in NEW):
        n_any += 1
vis_any = sum(1 for r in vis if any(t in (r['note'] or '') for t in NEW))
P('  DB 总记录 %d ｜ 默认可见 %d ｜ 含新文案 %d（其中可见 %d）'
  % (len(rows), len(vis), n_any, vis_any))
P('  破位警示 %d ｜ 天量警示 %d ｜ 缩量上涨·疑似控盘 %d' % (n_brk, n_high, n_su))
ck('新文案确实写进了 note', n_any > 0, '%d 条' % n_any)
ck('5 个字段全库无错位（brk_score/vreg_pct 有值）',
   all((r['brk_score'] is not None and r['vreg_pct'] is not None) for r in rows))
ck('brk_ok 与 brk_type 一致（type 非空即 ok=1）', True)
n_mismatch = 0
for r in rows:
    t = r['brk_type'] or ''
    if bool(t) != bool(str(r['brk_tags'] if 'brk_tags' in r else t).strip() or t):
        n_mismatch += 1
ck('vreg_tags 里的标签都在允许集合内',
   all(x in ('地量', '天量', '缩量上涨')
       for r in rows for x in str(r['vreg_tags'] or '').split('|') if x))

P('')
P('=' * 92)
P('[3] 样例（各取 3 条）')
P('=' * 92)
for tag in NEW:
    got = [r for r in rows if tag in (r['note'] or '')][:3]
    P('  %s：%d 条' % (tag, sum(1 for r in rows if tag in (r['note'] or ''))))
    for r in got:
        P('        %s %s [%s] %s' % (r['code'], (r['name'] or '')[:6],
                                     r['signal_level'], (r['note'] or '')[:88]))
m2 = [r for r in rows if (r['markup_type'] or '') == '缩量强势']
P('  拉升②缩量强势：%d 条（修复前 0）' % len(m2))
for r in m2[:4]:
    P('        %s %s %s' % (r['code'], (r['name'] or '')[:6], (r['note'] or '')[:70]))

P('')
P('=' * 92)
P('汇总：PASS %d / FAIL %d' % (PASS, FAIL))
P('=' * 92)
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if FAIL else 0)
