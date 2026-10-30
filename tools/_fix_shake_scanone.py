# -*- coding: utf-8 -*-
"""修真正的落库位置：BandPatternEngine._scan_one 会重建 rec dict（L1312-1343），
显式列举字段，之前漏了 5 个 shake 因子 —— 所以 note 对、DB 全 0。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = P + '.bak_before_shake_scanone'

sys.stdout.reconfigure(encoding='utf-8')
shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0
s = raw.decode('utf-8')

A = ("                'struct_pos': r.get('struct_pos',0),\n"
     "                'recent_vol3': r.get('recent_vol3',0),\n"
     "                'take_profit': _tp,")
N = ("                'struct_pos': r.get('struct_pos',0),\n"
     "                'recent_vol3': r.get('recent_vol3',0),\n"
     "                'shake_dip': r.get('shake_dip',0),\n"
     "                'shake_shadow': r.get('shake_shadow',0),\n"
     "                'shake_probe': r.get('shake_probe',0),\n"
     "                'shake_amp': r.get('shake_amp',0),\n"
     "                'shake_ok': r.get('shake_ok',0),\n"
     "                'take_profit': _tp,")
assert s.count(A) == 1, '命中 %d 次' % s.count(A)
s = s.replace(A, N, 1)

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  _scan_one 的 rec 补 5 个 shake 字段')
print('  备份:', BAK)
