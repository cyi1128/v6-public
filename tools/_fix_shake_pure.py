# -*- coding: utf-8 -*-
"""V16 提纯：横盘周K 的「建仓触发」必须震仓四项全过，否则降为「观察」。

依据：8 只用户圈定正样本 8/8 全部 4 项全过；
      现有 137 条横盘周K候选里只有 40 条能全过（砍 71%）。
界面 atr_t_widget.py L1824 只显示「建仓触发 + 等待确认」，所以降级即隐藏。
"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = P + '.bak_before_shake_pure'

sys.stdout.reconfigure(encoding='utf-8')
shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '该文件应为纯 LF'
s = raw.decode('utf-8')

# ---------- 1) 常量 ----------
A1 = "_ENTRY_GAP_CAP = 2.5\n"
N1 = ("_ENTRY_GAP_CAP = 2.5\n"
      "\n"
      "# V16 提纯门槛（2026-10-09）：横盘周K 的「建仓触发」要求启动前震仓 4 项全过。\n"
      "#   4 -> 现有 137 条里剩 40 条（砍 71%），8 只正样本全过。\n"
      "#   改成 3 则为温和档：137 条里剩 122 条（砍 11%）。\n"
      "#   3 项及以下一律降为「观察」，而 UI 只显示「建仓触发 + 等待确认」，等于不进表。\n"
      "_SHAKE_MIN_OK = 4\n")
assert s.count(A1) == 1, 'A1 命中 %d 次' % s.count(A1)
s = s.replace(A1, N1, 1)

# ---------- 2) 等级判定 ----------
A2 = ("    _sk = _shake_factors(bars, si, hi, lo, si - seg_n)\n"
      "    return {\n"
      "        'pattern_id': PATTERN_BOTTOM,")
N2 = ("    _sk = _shake_factors(bars, si, hi, lo, si - seg_n)\n"
      "    # V16 提纯：震仓四项全过才给「建仓触发」，否则降为「观察」\n"
      "    _lvl = (LVL_TRIGGER if _sk['shake_ok'] >= _SHAKE_MIN_OK else LVL_WATCH)\n"
      "    return {\n"
      "        'pattern_id': PATTERN_BOTTOM,")
assert s.count(A2) == 1, 'A2 命中 %d 次' % s.count(A2)
s = s.replace(A2, N2, 1)

# ---------- 3) signal_level 用判定结果 ----------
A3 = ("        'volume_ratio': round(w_mult, 2),\n"
      "        'signal_level': LVL_TRIGGER,\n"
      "        'trigger_type': '横盘周K·建仓',")
N3 = ("        'volume_ratio': round(w_mult, 2),\n"
      "        'signal_level': _lvl,\n"
      "        'trigger_type': '横盘周K·建仓',")
assert s.count(A3) == 1, 'A3 命中 %d 次' % s.count(A3)
s = s.replace(A3, N3, 1)

# ---------- 4) note 标注提纯结果 ----------
A4 = ("                '\\n震仓确认%d/4｜启动前回撤到箱体%.0f%%·最大下影%.0f%%·'\n"
      "                '探针MA20%+.1f%%·振幅收敛%.2f' % (")
N4 = ("                '\\n震仓确认%d/4%s｜启动前回撤到箱体%.0f%%·最大下影%.0f%%·'\n"
      "                '探针MA20%+.1f%%·振幅收敛%.2f' % (")
assert s.count(A4) == 1, 'A4 命中 %d 次' % s.count(A4)
s = s.replace(A4, N4, 1)

A5 = ("                    _sk['shake_ok'], _sk['shake_dip'], _sk['shake_shadow'],\n"
      "                    _sk['shake_probe'], _sk['shake_amp']),")
N5 = ("                    _sk['shake_ok'],\n"
      "                    ('·提纯通过' if _sk['shake_ok'] >= _SHAKE_MIN_OK\n"
      "                     else '·震仓不足/%d项，降为观察' % _SHAKE_MIN_OK),\n"
      "                    _sk['shake_dip'], _sk['shake_shadow'],\n"
      "                    _sk['shake_probe'], _sk['shake_amp']),")
assert s.count(A5) == 1, 'A5 命中 %d 次' % s.count(A5)
s = s.replace(A5, N5, 1)

# ---------- 5) docstring ----------
A6 = """      阈值按 8 只正样本标定，只做展示与后续排序参考，不做硬门槛。"""
N6 = """      阈值按 8 只正样本标定。V16 提纯：4 项全过才给「建仓触发」（_SHAKE_MIN_OK=4），
      否则降为「观察」——界面只显示触发+等待，等于不进表。"""
assert s.count(A6) == 1, 'A6 命中 %d 次' % s.count(A6)
s = s.replace(A6, N6, 1)

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  提纯补丁完成')
print('  常量 _SHAKE_MIN_OK = 4')
print('  shake_ok>=4 -> 建仓触发 ；<=3 -> 观察（不进表）')
print('  note 标注「·提纯通过 / ·震仓不足」')
print('  备份:', BAK)
