# -*- coding: utf-8 -*-
"""V20 建仓因子：数据库落盘复核 + 独立重算比对（步骤四）

1. pattern_record 表结构（列数 / 两个新列是否存在 / 类型）
2. 两个新列的填充率与分布、命中数量
3. 逐条【独立重算】：走引擎同一条取数路径 get_latest_kline -> _bars_to_df -> 因子函数，
   与库内值比对，抓字段错位（错位会整列对不上，不会只差几条）
4. C1~C5 回归：control_score / stage_guess / note 是否仍然正常
"""
import io
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DB = os.path.join(ROOT, 'data', 'cache', 'band_pattern.db')
OUT = os.path.join(ROOT, 'tools', 'buildfactor_db.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
OK = [0]
BAD = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


def check(nm, cond, detail=''):
    if cond:
        OK[0] += 1
        P('  [PASS] %s %s' % (nm, detail))
    else:
        BAD.append(nm)
        P('  [FAIL] %s %s' % (nm, detail))


import services.band_pattern_engine as E
from strategy.base import TechnicalIndicators as TI

_ti = TI()
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

P('=' * 100)
P('V20 建仓因子 · 数据库落盘复核')
P('=' * 100)
P('  DB: %s' % DB)

# ---------- 1 表结构 ----------
P('\n[1] pattern_record 表结构')
cols = con.execute('PRAGMA table_info(pattern_record)').fetchall()
names = [c['name'] for c in cols]
types = {c['name']: c['type'] for c in cols}
P('  列数 = %d' % len(cols))
check('列数 >= 46', len(cols) >= 46, '实际 %d' % len(cols))
for nm in ('stack_vol_score', 'red_fat_score'):
    check('存在列 %s' % nm, nm in names, 'type=%s' % types.get(nm))
check('stack_vol_score 类型 REAL', (types.get('stack_vol_score') or '').upper() == 'REAL',
      types.get('stack_vol_score'))
check('red_fat_score 类型 REAL', (types.get('red_fat_score') or '').upper() == 'REAL',
      types.get('red_fat_score'))
check('_ALL_COLS 与建表列名一致',
      all(c in names for c in [k for k, _ in E._ALL_COLS if k not in ('code',)]),
      '缺: %s' % [k for k, _ in E._ALL_COLS if k not in ('code',) and k not in names])

# ---------- 2 填充率与分布 ----------
P('\n[2] 填充率与分布')
tot = con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
P('  记录总数 = %d' % tot)
for nm in ('stack_vol_score', 'red_fat_score', 'control_score', 'stage_guess'):
    nn = con.execute('SELECT COUNT(*) FROM pattern_record WHERE %s IS NOT NULL' % nm).fetchone()[0]
    P('    %-18s 非空 %d / %d  (%.1f%%)' % (nm, nn, tot, 100.0 * nn / max(1, tot)))
    check('%s 100%% 填充' % nm, nn == tot)

P('\n  按模式分组（模式一=1 / 横盘周K=3）:')
for pid, cnt in con.execute('SELECT pattern_id, COUNT(*) FROM pattern_record GROUP BY pattern_id'):
    P('    pattern_id=%s : %d 条' % (pid, cnt))

P('\n  stack_vol_score 分布:')
for lo, hi in ((0, 20), (20, 40), (40, 55), (55, 70), (70, 101)):
    n = con.execute('SELECT COUNT(*) FROM pattern_record WHERE stack_vol_score>=? AND stack_vol_score<?',
                    (lo, hi)).fetchone()[0]
    P('    [%3d,%3d) : %4d 条 (%.1f%%)' % (lo, hi, n, 100.0 * n / max(1, tot)))
P('  red_fat_score 分布:')
for lo, hi in ((0, 20), (20, 40), (40, 60), (60, 70), (70, 101)):
    n = con.execute('SELECT COUNT(*) FROM pattern_record WHERE red_fat_score>=? AND red_fat_score<?',
                    (lo, hi)).fetchone()[0]
    P('    [%3d,%3d) : %4d 条 (%.1f%%)' % (lo, hi, n, 100.0 * n / max(1, tot)))
n_s = con.execute('SELECT COUNT(*) FROM pattern_record WHERE stack_vol_score>=?',
                  (E._BUILD_HIT_STACK,)).fetchone()[0]
n_r = con.execute('SELECT COUNT(*) FROM pattern_record WHERE red_fat_score>=?',
                  (E._BUILD_HIT_REDFAT,)).fetchone()[0]
n_b = con.execute('SELECT COUNT(*) FROM pattern_record WHERE stack_vol_score>=? AND red_fat_score>=?',
                  (E._BUILD_HIT_STACK, E._BUILD_HIT_REDFAT)).fetchone()[0]
P('  命中口径 (stack>=%.0f / redfat>=%.0f): 堆量 %d 条 | 红肥绿瘦 %d 条 | 两者 %d 条'
  % (E._BUILD_HIT_STACK, E._BUILD_HIT_REDFAT, n_s, n_r, n_b))

# ---------- 3 独立重算 ----------
P('\n[3] 逐条独立重算比对（走引擎同一条取数路径 get_latest_kline）')
from services.kline_cache_service import get_latest_kline   # noqa: E402

rows = con.execute(
    'SELECT code, pattern_id, base_date, stack_vol_score, red_fat_score,'
    ' control_score, stage_guess, note FROM pattern_record ORDER BY rowid').fetchall()
P('  待比对 %d 条' % len(rows))
cache = {}
n_ok = n_nodata = n_bad_s = n_bad_r = n_bad_c = n_bad_g = 0
mismatch_samples = []
for r in rows:
    code = r['code']
    if code not in cache:
        try:
            cache[code] = get_latest_kline(code, count=120)
        except Exception:
            cache[code] = []
    bars = cache[code]
    df = E._bars_to_df(bars)
    if df is None:
        n_nodata += 1
        continue
    rs = _ti.bottom_volume_stack(df)
    rr = _ti.red_fat_green_thin(df)
    rc = float(_ti.estimate_control_score(df))
    rg = _ti.judge_wash_or_distribute(df)
    ds = abs(float(rs['score']) - float(r['stack_vol_score'])) > 0.02
    dr = abs(float(rr['score']) - float(r['red_fat_score'])) > 0.02
    dc = abs(rc - float(r['control_score'])) > 0.02
    dg = (rg != r['stage_guess'])
    if ds or dr or dc or dg:
        mismatch_samples.append((code, r['pattern_id'], r['stack_vol_score'], rs['score'],
                                 r['red_fat_score'], rr['score'],
                                 r['control_score'], rc, r['stage_guess'], rg))
    n_bad_s += int(ds)
    n_bad_r += int(dr)
    n_bad_c += int(dc)
    n_bad_g += int(dg)
    if not (ds or dr or dc or dg):
        n_ok += 1

P('  重算成功 %d 条 | 取不到K线(未比对) %d 条' % (n_ok + len(mismatch_samples), n_nodata))
P('  完全一致 %d 条' % n_ok)
P('  不一致: stack %d / redfat %d / control %d / stage %d' % (n_bad_s, n_bad_r, n_bad_c, n_bad_g))
if mismatch_samples:
    P('  前 8 条不一致样本 (code, pid, 库stack, 重算stack, 库redfat, 重算redfat, 库ctrl, 重算ctrl, 库stage, 重算stage):')
    for s in mismatch_samples[:8]:
        P('    %s' % (s,))
check('stack_vol_score 逐条一致（0 条错位）', n_bad_s == 0, '%d 条不一致' % n_bad_s)
check('red_fat_score 逐条一致（0 条错位）', n_bad_r == 0, '%d 条不一致' % n_bad_r)
check('control_score 回归（C1~C5 未受影响）', n_bad_c == 0, '%d 条不一致' % n_bad_c)
check('stage_guess 回归（C1~C5 未受影响）', n_bad_g == 0, '%d 条不一致' % n_bad_g)

# ---------- 4 note 回归 ----------
P('\n[4] note 文案回归（C1/C3 规则 + 建仓开关）')
P('  _BUILD_NOTE_MODE = %s  (off = 不产生建仓文案)' % E._BUILD_NOTE_MODE)
for pat, nm in (('高度控盘候选', '高度控盘候选'),
                ('出货风险警示', '出货风险警示'),
                ('疑似洗盘', '疑似洗盘'),
                ('疑似底部堆量', '疑似底部堆量'),
                ('红肥绿瘦', '红肥绿瘦'),
                ('建仓加强', '建仓加强')):
    n = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE ?", ('%' + pat + '%',)).fetchone()[0]
    P('    note 含「%s」: %d 条' % (nm, n))
n_any = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note IS NOT NULL AND note<>''").fetchone()[0]
P('    note 非空: %d 条' % n_any)
if E._BUILD_NOTE_MODE == 'off':
    n_build = con.execute(
        "SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%疑似底部堆量%'"
        " OR note LIKE '%红肥绿瘦%' OR note LIKE '%建仓加强%'").fetchone()[0]
    check('mode=off 时库内无建仓文案', n_build == 0, '%d 条' % n_build)

con.close()
P('\n' + '=' * 100)
P('结果: %d 项通过 / %d 项失败' % (OK[0], len(BAD)))
for b in BAD:
    P('  FAIL: ' + b)
P('=' * 100)
_fh.close()
print('\n已写:', OUT)
sys.exit(1 if BAD else 0)
