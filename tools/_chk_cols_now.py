# -*- coding: utf-8 -*-
"""列名与因子填充核查（一次性诊断）。"""
import sqlite3

c = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
cols = [r[1] for r in c.execute('PRAGMA table_info(pattern_record)')]
print('列数', len(cols))
print(', '.join(cols))
print('--- 各因子非空/命中数 ---')
for f in ('control_score', 'stage_guess', 'ctrl_tag', 'probe_ok', 'dist_pattern_ok',
          'dist_pattern_type', 'markup_ok', 'markup_type', 'brk_ok', 'brk_type',
          'vreg_tags', 'vreg_pct', 'stack_score', 'redfat_ratio', 'stack_vol_score',
          'red_fat_score', 'c4_ok', 'c6_ok', 'note'):
    if f in cols:
        n = c.execute('SELECT COUNT(*) FROM pattern_record WHERE [%s] IS NOT NULL AND [%s] != ""'
                      % (f, f)).fetchone()[0]
        print('  %-20s 非空 %d' % (f, n))
    else:
        print('  %-20s （不在表里）' % f)
