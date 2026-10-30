# -*- coding: utf-8 -*-
"""控盘度/洗盘 审计 · 第1步：数据库实际状态（只读）

跑法： & $py -X utf8 "tools\_audit_ctrl_db.py"
"""
import io, os, sqlite3, sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, 'data', 'cache', 'band_pattern.db')

print('=' * 96)
print('控盘度审计 · 第1步：band_pattern.db 实际状态')
print('=' * 96)
print('库文件:', DB, '| 存在:', os.path.exists(DB))
if os.path.exists(DB):
    print('大小: %.2f MB | 修改时间: %s' % (
        os.path.getsize(DB) / 1048576.0,
        __import__('datetime').datetime.fromtimestamp(os.path.getmtime(DB))))

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

# ---------- 1. 有哪些表 ----------
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print('\n[1] 表清单:', tables)

MAIN = 'pattern_record'
if MAIN not in tables:
    print('!! 主表不存在，退出'); sys.exit(1)

# ---------- 2. 表结构 ----------
info = list(cur.execute('PRAGMA table_info(%s)' % MAIN))
print('\n[2] %s 列数 = %d' % (MAIN, len(info)))
targets = ('control_score', 'stage_guess', 'note', 'signal_level',
           'pattern_id', 'struct_pos', 'env_score')
for r in info:
    if r[1] in targets:
        print('    %-16s %-14s notnull=%d default=%r' % (r[1], r[2], r[3], r[4]))

# 全部列名（核对与 _ALL_COLS 是否一致）
cols = [r[1] for r in info]
print('\n[3] 全部列名（%d）:' % len(cols))
print('   ', ' | '.join(cols))

# ---------- 4. 总行数 / 分模式 ----------
n = cur.execute('SELECT COUNT(*) FROM %s' % MAIN).fetchone()[0]
print('\n[4] 总行数 =', n)
print('    分模式:')
for r in cur.execute('SELECT pattern_id, COUNT(*) c FROM %s GROUP BY pattern_id ORDER BY pattern_id' % MAIN):
    print('       pattern_id=%s  %d 条' % (r[0], r[1]))

# ---------- 5. 两列填充情况 ----------
print('\n[5] 两列填充情况:')
row = cur.execute("""SELECT
    SUM(CASE WHEN control_score IS NULL THEN 1 ELSE 0 END),
    SUM(CASE WHEN control_score = 0 THEN 1 ELSE 0 END),
    SUM(CASE WHEN control_score > 0 THEN 1 ELSE 0 END),
    SUM(CASE WHEN stage_guess IS NULL OR stage_guess = '' THEN 1 ELSE 0 END),
    SUM(CASE WHEN control_score IS NOT NULL AND stage_guess IS NOT NULL THEN 1 ELSE 0 END)
    FROM %s""" % MAIN).fetchone()
print('    control_score IS NULL      : %s' % row[0])
print('    control_score = 0          : %s' % row[1])
print('    control_score > 0          : %s' % row[2])
print('    stage_guess 空/NULL        : %s' % row[3])
print('    两列都非 NULL              : %s' % row[4])

print('\n    stage_guess 取值分布:')
for r in cur.execute('SELECT stage_guess, COUNT(*) c FROM %s GROUP BY stage_guess ORDER BY c DESC' % MAIN):
    print('       %-14r %d' % (r[0], r[1]))

# ---------- 6. 错位检测 ----------
print('\n[6] 错位检测（若错位会出现：分数是文本 / 阶段是数字）')
bad1 = cur.execute("SELECT COUNT(*) FROM %s WHERE typeof(control_score) NOT IN ('real','integer','null')" % MAIN).fetchone()[0]
bad2 = cur.execute("SELECT COUNT(*) FROM %s WHERE control_score IS NOT NULL AND (control_score < 0 OR control_score > 100)" % MAIN).fetchone()[0]
bad3 = cur.execute("SELECT COUNT(*) FROM %s WHERE stage_guess IS NOT NULL AND stage_guess NOT IN ('wash','distribute','unknown','')" % MAIN).fetchone()[0]
print('    control_score 非数值类型: %d   （应为 0）' % bad1)
print('    control_score 越界 0~100 : %d   （应为 0）' % bad2)
print('    stage_guess 非三种取值   : %d   （应为 0）' % bad3)

# 抽样看真值
print('\n[7] 抽样 8 条（看两列是否落在合理业务值上）:')
for r in cur.execute("""SELECT code, name, pattern_id, control_score, stage_guess,
                        struct_pos, signal_level, substr(note,1,60) nt, env_note
                        FROM %s WHERE control_score > 0 ORDER BY control_score DESC LIMIT 8""" % MAIN):
    print('    %s %-8s pid=%s ctrl=%7.2f %-11s pos=%s lvl=%s | note=%r'
          % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]))

# ---------- 8. 分数分布 ----------
print('\n[8] control_score 分布（全库非零）:')
vals = [r[0] for r in cur.execute('SELECT control_score FROM %s WHERE control_score > 0 ORDER BY control_score' % MAIN)]
if vals:
    def pct(p):
        return vals[min(len(vals) - 1, int(len(vals) * p))]
    print('    样本 %d 只 | min=%.2f  25%%=%.2f  50%%=%.2f  75%%=%.2f  90%%=%.2f  max=%.2f'
          % (len(vals), vals[0], pct(0.25), pct(0.50), pct(0.75), pct(0.90), vals[-1]))
    for th in (60, 70, 80, 85, 90, 95):
        c = sum(1 for v in vals if v >= th)
        print('      >=%-3d : %4d 只 (%.1f%%)' % (th, c, 100.0 * c / len(vals)))

# ---------- 9. 提示文案命中 ----------
print('\n[9] note 里的控盘提示:')
c_high = cur.execute("SELECT COUNT(*) FROM %s WHERE note LIKE '%%高度控盘 + 疑似洗盘%%'" % MAIN).fetchone()[0]
c_dist = cur.execute("SELECT COUNT(*) FROM %s WHERE note LIKE '%%出货风险警示%%'" % MAIN).fetchone()[0]
c_cand = cur.execute("SELECT COUNT(*) FROM %s WHERE note LIKE '%%高度控盘候选%%'" % MAIN).fetchone()[0]
c_any = cur.execute("SELECT COUNT(*) FROM %s WHERE note LIKE '%%[控盘]%%'" % MAIN).fetchone()[0]
print('    高度控盘+疑似洗盘 : %d' % c_high)
print('    出货风险警示      : %d' % c_dist)
print('    高度控盘候选      : %d' % c_cand)
print('    含 [控盘] 提示合计 : %d  / 总 %d = %.1f%%' % (c_any, n, 100.0 * c_any / max(1, n)))

print('\n    signal_level × 是否带提示:')
for r in cur.execute("""SELECT signal_level,
        SUM(CASE WHEN note LIKE '%%[控盘]%%' THEN 1 ELSE 0 END) tip,
        COUNT(*) tot FROM %s GROUP BY signal_level ORDER BY tot DESC""" % MAIN):
    print('       %-14s 带提示 %3d / %3d' % (r[0], r[1], r[2]))

# ---------- 10. 复核：两列是否来自同一次扫描（时间戳一致） ----------
print('\n[10] created_at / updated_at 分布（判断是否同一批扫描）:')
for r in cur.execute('SELECT substr(created_at,1,10) d, COUNT(*) c FROM %s GROUP BY d ORDER BY c DESC LIMIT 6' % MAIN):
    print('    %s : %d' % (r[0], r[1]))

con.close()
print('\n' + '=' * 96)
print('第1步完成')
