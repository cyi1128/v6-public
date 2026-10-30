# -*- coding: utf-8 -*-
"""C6 落盘核查：字段是否真进 pattern_record、有没有列错位、文案是否真写进 note。

输出 tools\\c6_db.txt
"""
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
DB = r'D:\QuantMonitorV6\data\cache\band_pattern.db'
OUT = r'D:\QuantMonitorV6\tools\c6_db.txt'
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

P('=' * 96)
P('C6 落盘核查   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 96)
con = sqlite3.connect(DB)
cur = con.cursor()
info = cur.execute('PRAGMA table_info(pattern_record)').fetchall()
cols = [r[1] for r in info]
types = {r[1]: r[2] for r in info}
P('表 pattern_record 列数：%d（_ALL_COLS %d）' % (len(cols), len(_ALL_COLS)))
check('c6_ok 列存在（INTEGER）', 'c6_ok' in cols and types['c6_ok'] == 'INTEGER',
      'type=%s' % types.get('c6_ok'))
check('c6_score 列存在（REAL）', 'c6_score' in cols and types['c6_score'] == 'REAL',
      'type=%s' % types.get('c6_score'))
check('c4 两列仍在（没被覆盖）', 'c4_ok' in cols and 'c4_score' in cols)
check('_ALL_COLS 与建表列名一一对应', all(c in cols for c, _ in _ALL_COLS),
      '缺 %s' % [c for c, _ in _ALL_COLS if c not in cols])
check('列数 == len(_ALL_COLS)', len(cols) == len(_ALL_COLS),
      '%d vs %d' % (len(cols), len(_ALL_COLS)))

n = cur.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
P('')
P('记录总数：%d' % n)
check('总记录 > 0', n > 0)

for tag in ('c4_ok', 'c6_ok'):
    P('')
    P('%s 分布：' % tag)
    tot = 0
    for ok, c, av in cur.execute(
            'SELECT %s, COUNT(*), ROUND(AVG(%s_score),1) FROM pattern_record'
            ' GROUP BY %s ORDER BY %s DESC' % (tag, tag[:2], tag, tag)).fetchall():
        P('   %s=%s  %4d 条  平均分=%s' % (tag, ok, c, av))
        tot += c
    check('%s 分组合计 == 总数' % tag, tot == n, '%d vs %d' % (tot, n))

P('')
P('c6_score 分布（应为 0/50/100 三档，纯计数分）：')
for sc, c in cur.execute('SELECT c6_score, COUNT(*) FROM pattern_record'
                         ' GROUP BY c6_score ORDER BY c6_score').fetchall():
    P('   c6_score=%6s  %4d 条' % (sc, c))
check('c6_score 只出现 0/50/100',
      set(r[0] for r in cur.execute('SELECT DISTINCT c6_score FROM pattern_record')) <=
      {0.0, 50.0, 100.0})

P('')
P('（控盘标签列 ctrl_tag 核查 —— 只存「控盘提示」，UI 短标签读它）')
check('ctrl_tag 列存在（TEXT）', 'ctrl_tag' in cols and types['ctrl_tag'] == 'TEXT',
      'type=%s' % types.get('ctrl_tag'))
_tg = [x[0] for x in cur.execute('SELECT DISTINCT ctrl_tag FROM pattern_record ORDER BY 1').fetchall()]
P('   ctrl_tag 取值集合：%s' % _tg)
from services.control_profile import _CTRL_TAGS as _WHITE  # noqa: E402
_bad_seg = []
for _v in _tg:
    for _s in _v.split(' ｜ '):
        _s = _s.strip()
        if _s and _s not in _WHITE:
            _bad_seg.append((_v, _s))
check('ctrl_tag 的每一段都是「控盘提示」白名单成员（1~2 段，洗盘+候选可同时命中）',
      not _bad_seg, '越界 %s' % _bad_seg[:5])
check('ctrl_tag 里绝不出现 C4/C6 等观察文案',
      cur.execute("SELECT COUNT(*) FROM pattern_record WHERE ctrl_tag LIKE '%观察%'")
      .fetchone()[0] == 0)
# 语义不变量：有「候选」标签 => control_score >= 85（引擎 _CTRL_HIGH）
bad_c = cur.execute("SELECT COUNT(*) FROM pattern_record"
                    " WHERE ctrl_tag LIKE '%候选%' AND (control_score IS NULL"
                    " OR control_score < 85)").fetchone()[0]
check('带「候选」标签的记录控盘分 >= 85（规则③硬条件）', bad_c == 0, '越界 %d 条' % bad_c)
bad_d = cur.execute("SELECT COUNT(*) FROM pattern_record"
                    " WHERE ctrl_tag LIKE '%出货%' AND (stage_guess IS NULL"
                    " OR stage_guess <> 'distribute')").fetchone()[0]
check('带「出货」标签的记录 stage_guess 都是 distribute', bad_d == 0, '越界 %d 条' % bad_d)
n_tag = cur.execute("SELECT COUNT(*) FROM pattern_record WHERE ctrl_tag <> ''").fetchone()[0]
n_note = cur.execute("SELECT COUNT(*) FROM pattern_record WHERE note <> ''").fetchone()[0]
P('   带控盘标签：%d 条 ｜ 不带标签：%d 条 ｜ note 非空：%d 条'
  % (n_tag, n - n_tag, n_note))
check('带控盘标签条数 <= note 非空条数（观察类文案可以单独存在）',
      0 < n_tag <= n_note, '%d / %d' % (n_tag, n_note))
# 交叉验证：把 note 里的控盘提示段抠出来，必须与 ctrl_tag 完全一致
_mm = 0
for code, ct, nt in cur.execute('SELECT code, ctrl_tag, note FROM pattern_record').fetchall():
    _seg = (nt or '').split('[控盘]')[-1].strip().replace('\n', ' ')
    _only = [s.strip() for s in _seg.split(' ｜ ')
             if s.strip() in ('高度控盘候选', '出货风险警示', '高度控盘 + 疑似洗盘，关注启动')]
    if ' ｜ '.join(_only) != (ct or ''):
        _mm += 1
check('note 抠出的控盘提示与 ctrl_tag 逐条一致（216 条全比）', _mm == 0, '不一致 %d 条' % _mm)

P('')
hit6 = cur.execute('SELECT COUNT(*) FROM pattern_record WHERE c6_ok = 1').fetchone()[0]
note6 = cur.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%C6观察%'")
note6 = note6.fetchone()[0]
hit4 = cur.execute('SELECT COUNT(*) FROM pattern_record WHERE c4_ok = 1').fetchone()[0]
note4 = cur.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%C4观察%'")
note4 = note4.fetchone()[0]
P('C6 两条全中（c6_ok=1）：%d 条 ｜ note 带 C6 文案：%d 条' % (hit6, note6))
P('C4 五条全中（c4_ok=1）：%d 条 ｜ note 带 C4 文案：%d 条' % (hit4, note4))
check('c6_ok=1 条数 == note 带 C6 文案条数', hit6 == note6, '%d vs %d' % (hit6, note6))
check('c4_ok=1 条数 == note 带 C4 文案条数（C4 未被破坏）', hit4 == note4,
      '%d vs %d' % (hit4, note4))
check('c6_ok=1 -> c6_score 必须 100',
      cur.execute('SELECT COUNT(*) FROM pattern_record WHERE c6_ok=1 AND c6_score<>100')
      .fetchone()[0] == 0)
check('c6_ok=0 -> c6_score 必须 <100',
      cur.execute('SELECT COUNT(*) FROM pattern_record WHERE c6_ok=0 AND c6_score>=100')
      .fetchone()[0] == 0)
# 逻辑关系：C6 是 C4 去掉量价结构后的子集口径 —— c4 命中应当包含在 c6 或 c4 命中里？
# C4 ⊂ C6 成立（C4 多两条 AND），所以 c4_ok=1 而 c6_ok=0 的记录理论上不该出现
bad_sub = cur.execute(
    'SELECT COUNT(*) FROM pattern_record WHERE c4_ok=1 AND c6_ok=0').fetchone()[0]
P('C4 命中但 C6 未命中（理论上应为 0，因 C4 ⊃ C6 条件）：%d 条' % bad_sub)
check('C4⊂C6 关系成立（c4_ok=1 的记录 c6_ok 必须为 1）', bad_sub == 0, '%d 条' % bad_sub)

P('')
P('样本（c6_ok=1，最多 10 条）：')
for r in cur.execute(
        "SELECT code, name, pattern_id, signal_level, c6_score, c4_ok,"
        " control_score, substr(note, instr(note,'C6观察')-8, 30)"
        " FROM pattern_record WHERE c6_ok=1 ORDER BY code LIMIT 10").fetchall():
    P('   %s %-7s 模式%s 状态=%-5s c6=%s c4=%s 控盘=%.1f'
      % (r[0], r[1] or '', r[2], r[3] or '', r[4], r[5], r[6] or 0))
    P('        note 片段: %s' % (r[7] or '').replace('\n', ' / '))
P('')
P('反向抽查（c6_score=50，即只满足一条的）：')
for r in cur.execute('SELECT code, name, pattern_id, c6_score'
                     ' FROM pattern_record WHERE c6_score=50 ORDER BY code LIMIT 6'):
    P('   %s %-7s 模式%s c6=%s' % (r[0], r[1] or '', r[2], r[3]))

P('')
P('全列空值计数（查有没有整列落空 / 错位）：')
sel = ','.join("SUM(CASE WHEN %s IS NULL OR %s = '' THEN 1 ELSE 0 END)" % (c, c)
               if types[c] == 'TEXT' else 'SUM(CASE WHEN %s IS NULL THEN 1 ELSE 0 END)' % c
               for c in cols)
vals = cur.execute('SELECT %s FROM pattern_record' % sel).fetchone()
EXPECT_EMPTY = ('invalid_reason', 'ctrl_tag')   # 只在「失效」/「有控盘提示」时才写，全空属正常
empty = [(cols[i], vals[i]) for i in range(len(cols)) if vals[i]]
P('   非空但全空的列：%s' % (empty if empty else '无'))
check('除 invalid_reason / ctrl_tag 外没有整列落空（无字段错位）',
      all(c in EXPECT_EMPTY for c, _ in empty), str(empty))
check('c6_ok 无空值', vals[cols.index('c6_ok')] == 0)
check('c6_score 无空值', vals[cols.index('c6_score')] == 0)

con.close()
P('')
P('=' * 96)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 96)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
