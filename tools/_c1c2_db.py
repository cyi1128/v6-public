# -*- coding: utf-8 -*-
"""扫描后：DB 写入完整性 + stage/note 分布实测"""
import io, os, sys, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, 'tools', 'c1c2_db.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); _fh.write(s + '\n')

DB = os.path.join(ROOT, 'data', 'cache', 'band_pattern.db')
con = sqlite3.connect('file:%s?mode=ro' % DB.replace('\\', '/'), uri=True)
con.row_factory = sqlite3.Row

P('=' * 104)
P('DB 实测：data\\cache\\band_pattern.db')
P('=' * 104)
cols = [r[1] for r in con.execute('PRAGMA table_info(pattern_record)')]
P('   列数 = %d' % len(cols))
for c in ('control_score', 'stage_guess'):
    P('   字段 %-14s 存在=%s' % (c, c in cols))
P('')
P('   SELECT COUNT(*) = %d' % con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0])
P('')
P('   signal_level × 记录数：')
for r in con.execute('SELECT signal_level, COUNT(*) n FROM pattern_record GROUP BY signal_level ORDER BY n DESC'):
    P('     %-12s %d' % (r['signal_level'] or '(空)', r['n']))
P('')
P('   stage_guess 分布：')
tot = con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
for r in con.execute('SELECT stage_guess, COUNT(*) n, ROUND(AVG(control_score),1) avg_s '
                     'FROM pattern_record GROUP BY stage_guess ORDER BY n DESC'):
    P('     %-12s %4d 条 (%.1f%%)  平均控盘分=%.1f' % (r['stage_guess'] or '(空)', r['n'], 100.0*r['n']/tot, r['avg_s'] or 0))
P('')
P('   两个新字段的填充率（应 100%，空/错位即 bug）：')
r = con.execute('SELECT SUM(control_score IS NULL) c_null, SUM(stage_guess IS NULL) s_null, '
                'SUM(control_score<0 OR control_score>100) c_out FROM pattern_record').fetchone()
P('     control_score 为空 %d 条 / stage_guess 为空 %d 条 / control_score 越界 %d 条' % (r['c_null'], r['s_null'], r['c_out']))

P('')
P('   note 里的控盘文案命中数（扫描后）：')
for kw in ('出货风险警示', '高度控盘候选', '疑似洗盘'):
    n = con.execute('SELECT COUNT(*) FROM pattern_record WHERE note LIKE ?', ('%' + kw + '%',)).fetchone()[0]
    P('     %-12s %d 条 (%.1f%%)' % (kw, n, 100.0 * n / tot))
n_any = con.execute("SELECT COUNT(*) FROM pattern_record WHERE note LIKE '%控盘%'").fetchone()[0]
P('     %-12s %d 条 (%.1f%%)' % ('任一控盘提示', n_any, 100.0 * n_any / tot))

P('')
P('   逐条重算校验（从库里读回 note，与重新调用 _ctrl_note 的结果比对）：')
import services.band_pattern_engine as E
bad = 0; ok = 0; skip = 0
rows = list(con.execute('SELECT code, control_score, stage_guess, note FROM pattern_record'))
for r in rows:
    code = r['code']
    bars = E._load_bars(code)
    df = E._bars_to_df(bars) if bars else None
    if df is None:
        skip += 1; continue
    t120 = df['close'].tail(120)
    lo, hi = float(t120.min()), float(t120.max())
    pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
    tip = E._ctrl_note(float(r['control_score']), r['stage_guess'], pos)
    if tip and tip in (r['note'] or ''):
        ok += 1
    elif not tip and tip not in ('', None):
        bad += 1
    elif tip:
        bad += 1
    else:
        ok += 1
P('     一致 %d 条 / 不一致 %d 条 / 无K线跳过 %d 条（共 %d）' % (ok, bad, skip, len(rows)))

P('')
P('   出货风险警示明细（新口径，应全部是高位股）：')
rows2 = list(con.execute("SELECT code, name, control_score, stage_guess FROM pattern_record "
                         "WHERE note LIKE '%出货风险警示%'"))
if not rows2:
    P('     （无）')
for r in rows2:
    bars = E._load_bars(r['code'])
    df = E._bars_to_df(bars) if bars else None
    pos = None
    if df is not None:
        t = df['close'].tail(120); lo, hi = float(t.min()), float(t.max())
        pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
    P('     %-7s %-9s 控盘分=%5.1f  pos120=%s' % (r['code'], r['name'] or '', r['control_score'],
                                                  ('%.3f' % pos) if pos is not None else 'n/a'))
con.close()
_fh.close()
