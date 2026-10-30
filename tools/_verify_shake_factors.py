# -*- coding: utf-8 -*-
"""验证：1) DB 字段是否补齐  2) _shake_factors 能否复现实测值
        3) 现有 137 条真实记录上 factor 分布 / 各档门槛影响"""
import sqlite3
import statistics
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

from datetime import datetime  # noqa: E402
from services.band_pattern_engine import (_init_db, _load_bars,  # noqa: E402
                                         _shake_factors, _save_or_update,
                                         query_signals, DB_PATH)

# ---- 1) 字段 ----
_init_db()
con = sqlite3.connect(DB_PATH)
cols = {r[1] for r in con.execute('PRAGMA table_info(pattern_record)').fetchall()}
need = ['shake_dip', 'shake_shadow', 'shake_probe', 'shake_amp', 'shake_ok']
print('1) DB 字段补齐：', {c: (c in cols) for c in need})

# ---- 2) 写读往返 ----
_save_or_update({'code': '__PROBE__', 'pattern_id': 3, 'base_date': '1999-01-01',
                 'push_date': '', 'shake_ok': 3, 'shake_dip': 61.2},
                table_name='pattern_record')
row = con.execute("SELECT shake_ok, shake_dip FROM pattern_record "
                  "WHERE code='__PROBE__'").fetchone()
print('2) 写读往返 shake_ok/shake_dip =', row)
con.execute("DELETE FROM pattern_record WHERE code='__PROBE__'")
con.commit()

# ---- 3) 复现 8 只正样本 ----
CASES = [('600640', '国脉文化', '2026-09-14'), ('601112', '振石股份', '2026-09-07'),
         ('600088', '中视传媒', '2026-08-31'), ('605577', '龙版传媒', '2026-08-31'),
         ('002005', '德豪润达', '2026-09-21'), ('603230', '内蒙新华', '2026-08-31'),
         ('000910', '大亚圣象', '2026-09-14'), ('600503', '华丽家族', '2026-09-21')]
print()
print('3) _shake_factors 复现正样本（启动周已知，窗口取前 40 日）')
print('%-9s %-11s %6s %8s %8s %8s %8s %5s'
      % ('名称', '启动周', '回撤%', '最大下影%', '探针MA20%', '振幅收敛', 'shake_ok', ''))
for code, name, wd in CASES:
    bars = _load_bars(code)
    si = None
    for i in range(len(bars)):
        if bars[i]['date'][:10] >= wd:
            si = i
            break
    if si is None or si < 45:
        print('%-9s 窗口不足' % name)
        continue
    st = si - 40
    hi = max(b['high'] for b in bars[st:si])
    lo = min(b['low'] for b in bars[st:si])
    f = _shake_factors(bars, si, hi, lo, st)
    print('%-9s %-11s %6.1f %8.1f %8.2f %8.2f %5d %5s'
          % (name, wd, f['shake_dip'], f['shake_shadow'], f['shake_probe'],
             f['shake_amp'], f['shake_ok'],
             '✅' if f['shake_ok'] >= 3 else '⚠'))

# ---- 4) 现有记录上的分布 ----
recs = con.execute("SELECT code, name, base_date, structure_days, signal_level "
                   "FROM pattern_record").fetchall()
print()
print('4) 现有 %d 条记录上重算启动前震仓因子' % len(recs))
vals = []
miss = 0
for code, name, bd, sd, lvl in recs:
    bars = _load_bars(code)
    if not bars or not bd:
        miss += 1
        continue
    bi = None
    for i in range(len(bars)):
        if bars[i]['date'][:10] >= bd[:10]:
            bi = i
            break
    if bi is None:
        miss += 1
        continue
    si = bi + (sd or 0)
    if si >= len(bars) - 1:
        si = len(bars) - 1
    if si < 45:
        miss += 1
        continue
    st = si - (sd or 40)
    hi = max(b['high'] for b in bars[st:si])
    lo = min(b['low'] for b in bars[st:si])
    f = _shake_factors(bars, si, hi, lo, st)
    vals.append((code, name or '', lvl, f))
con.close()

print('  可重算 %d 条，数据不足 %d 条' % (len(vals), miss))
if vals:
    for k, lbl in [('shake_dip', '回撤到箱体%'), ('shake_shadow', '最大下影%'),
                   ('shake_probe', '探针MA20%'), ('shake_amp', '振幅收敛')]:
        v = sorted(x[3][k] for x in vals)
        print('  %-12s 中位 %8.2f  25%% %8.2f  75%% %8.2f  最小 %8.2f  最大 %8.2f'
              % (lbl, statistics.median(v), v[len(v) // 4], v[len(v) * 3 // 4],
                 v[0], v[-1]))
    print()
    print('  shake_ok 分布（0~4 项通过）：')
    for ok in range(5):
        n = sum(1 for x in vals if x[3]['shake_ok'] == ok)
        print('    %d 项: %3d 只 (%.0f%%)' % (ok, n, n * 100.0 / len(vals)))
    print()
    print('  各档门槛影响：')
    for th in (4, 3, 2):
        n = sum(1 for x in vals if x[3]['shake_ok'] >= th)
        print('    要求 >=%d 项: 剩 %3d / %d = %.0f%%'
              % (th, n, len(vals), n * 100.0 / len(vals)))
    print()
    print('  通过 3 项以上的前 15 只：')
    good = sorted([x for x in vals if x[3]['shake_ok'] >= 3],
                  key=lambda x: -x[3]['shake_ok'])
    for code, name, lvl, f in good[:15]:
        print('    %-9s %-8s ok=%d  回撤%.0f%%  下影%.0f%%  探针%+.1f%%  振幅%.2f'
              % (code, name, f['shake_ok'], f['shake_dip'], f['shake_shadow'],
                 f['shake_probe'], f['shake_amp']))
print()
print('完成于', datetime.now().strftime('%H:%M:%S'))
