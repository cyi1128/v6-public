# -*- coding: utf-8 -*-
"""C4 落盘核查：字段是否真的进了 pattern_record、有没有列错位、文案是否真的写进 note。

输出 tools\\c4_db.txt
"""
import os
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
DB = r'D:\QuantMonitorV6\data\cache\band_pattern.db'
OUT = r'D:\QuantMonitorV6\tools\c4_db.txt'
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


from services.band_pattern_engine import _ALL_COLS  # noqa: E402

P('=' * 78)
P('C4 落盘核查   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 78)
con = sqlite3.connect(DB)
cur = con.cursor()
cols = [r[1] for r in cur.execute('PRAGMA table_info(pattern_record)').fetchall()]
types = {r[1]: r[2] for r in cur.execute('PRAGMA table_info(pattern_record)').fetchall()}
P('表 pattern_record 列数：%d' % len(cols))
check('c4_ok 列存在（INTEGER）', 'c4_ok' in cols and types['c4_ok'] == 'INTEGER',
      'type=%s' % types.get('c4_ok'))
check('c4_score 列存在（REAL）', 'c4_score' in cols and types['c4_score'] == 'REAL',
      'type=%s' % types.get('c4_score'))
check('_ALL_COLS 与建表列名一一对应',
      all(c in cols for c, _ in _ALL_COLS),
      '缺: %s' % [c for c, _ in _ALL_COLS if c not in cols])
check('列数 == len(_ALL_COLS)', len(cols) == len(_ALL_COLS),
      '%d vs %d' % (len(cols), len(_ALL_COLS)))

n = cur.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
P('')
P('记录总数：%d' % n)
check('总记录 > 0', n > 0)
rows = cur.execute("""
    SELECT c4_ok, COUNT(*), ROUND(AVG(c4_score),1)
    FROM pattern_record GROUP BY c4_ok ORDER BY c4_ok DESC""").fetchall()
P('')
P('c4_ok 分布：')
tot = 0
for ok, c, av in rows:
    P('   c4_ok=%s  %4d 条  平均 c4_score=%s' % (ok, c, av))
    tot += c
check('c4_ok 分组合计 == 总数', tot == n, '%d vs %d' % (tot, n))

P('')
P('c4_score 分布（应为 0/20/40/60/80/100 六档，纯计数分）：')
for sc, c in cur.execute("""
        SELECT c4_score, COUNT(*) FROM pattern_record
        GROUP BY c4_score ORDER BY c4_score""").fetchall():
    P('   c4_score=%6s  %4d 条' % (sc, c))

P('')
hit = cur.execute("SELECT COUNT(*) FROM pattern_record WHERE c4_ok = 1").fetchone()[0]
note_n = cur.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%C4观察%'").fetchone()[0]
P('C4 五条全中（c4_ok=1）记录：%d 条' % hit)
P('note 里带「C4观察」文案的记录：%d 条' % note_n)
check('c4_ok=1 的条数 == note 带 C4 文案的条数（只在 C4 时追加文案）',
      hit == note_n, '%d vs %d' % (hit, note_n))
check('c4_ok=1 的记录 c4_score 必须是 100',
      cur.execute('SELECT COUNT(*) FROM pattern_record WHERE c4_ok=1 AND c4_score<>100')
      .fetchone()[0] == 0)
check('c4_ok=0 的记录 c4_score 必须 < 100',
      cur.execute('SELECT COUNT(*) FROM pattern_record WHERE c4_ok=0 AND c4_score>=100')
      .fetchone()[0] == 0)

P('')
P('样本（c4_ok=1，最多 8 条）：')
s = cur.execute("""
    SELECT code, name, pattern_id, pattern_name, signal_level, c4_score,
           control_score, struct_pos, LIKE_ANS
    FROM (SELECT *, (SELECT substr(note, instr(note,'C4观察')-6, 24)) AS LIKE_ANS
          FROM pattern_record WHERE c4_ok=1)
    ORDER BY code LIMIT 8""").fetchall()
if not s:
    P('   （无）')
for r in s:
    P('   %s %-6s 模式%s %-6s 状态=%-6s c4=%s 控盘=%.1f 结构位=%.2f'
      % (r[0], r[1] or '', r[2], r[3] or '', r[4] or '', r[5], r[6] or 0, r[7] or 0))
    P('        note 片段: %s' % (r[8] or '').replace('\n', ' / '))

P('')
P('反向抽查（c4_score>=80 但不是 100，即差一条的）：')
s2 = cur.execute("""
    SELECT code, name, pattern_id, c4_score, control_score, struct_pos
    FROM pattern_record WHERE c4_score = 80 ORDER BY code LIMIT 6""").fetchall()
if not s2:
    P('   （无）')
for r in s2:
    P('   %s %-6s 模式%s c4=%s 控盘=%.1f 结构位=%.2f'
      % (r[0], r[1] or '', r[2], r[3], r[4] or 0, r[5] or 0))

P('')
P('全列非空计数（查有没有整列落空/错位）：')
sel = ','.join('SUM(CASE WHEN %s IS NULL OR %s = \'\' THEN 1 ELSE 0 END)'
               % (c, c) if types[c] == 'TEXT' else
               'SUM(CASE WHEN %s IS NULL THEN 1 ELSE 0 END)' % c for c in cols)
vals = cur.execute('SELECT %s FROM pattern_record' % sel).fetchone()
empty = [(cols[i], vals[i]) for i in range(len(cols)) if vals[i]]
P('   非空但全空的列：%s' % (empty if empty else '无'))
check('c4_ok 无空值', vals[cols.index('c4_ok')] == 0)
check('c4_score 无空值', vals[cols.index('c4_score')] == 0)

con.close()
P('')
P('=' * 78)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 78)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
