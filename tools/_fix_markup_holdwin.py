# -*- coding: utf-8 -*-
"""小补丁：① 的回调窗口改成「最近 5 根」（发动那根不算回调）+ 回调哲学说明。一次性。"""
import io
import os
import py_compile
import sys

sys.stdout.reconfigure(encoding='utf-8')
TGT = r'D:\QuantMonitorV6\strategy\base.py'

raw = io.open(TGT, 'rb').read()
assert raw.count(b'\n') - raw.count(b'\r\n') == 0, '不是纯 CRLF'
s = raw.decode('utf-8').replace('\r\n', '\n')

REP = [
    # 1) 新增常量 MARKUP_HOLD_WIN
    ("MARKUP_TREND_GAIN = 0.06    # ① 近窗口累计涨幅下限（收盘口径）\n"
     "MARKUP_PULLBACK_TOL = 0.03  # ① 回调容忍度：窗口最低价 >= MA20 x (1 - 该值)\n",
     "MARKUP_TREND_GAIN = 0.06    # ① 近窗口累计涨幅下限（收盘口径）\n"
     "MARKUP_HOLD_WIN = 5         # ① 「回调不破均线」只看最近 5 根（发动那根不算回调）\n"
     "MARKUP_PULLBACK_TOL = 0.03  # ① 回调容忍度：最近 MARKUP_HOLD_WIN 根最低价 >= MA20 x (1-该值)\n"),
    # 2) 判据文档
    ("           A4 近窗口最低价 >= MA20 x (1 - MARKUP_PULLBACK_TOL(3%))（回调不破关键均线）\n",
     "           A4 最近 MARKUP_HOLD_WIN(5) 根的最低价 >= MA20 x (1 - MARKUP_PULLBACK_TOL(3%))\n"
     "              （「回调不破关键均线」只能算发动之后那几根：发动当天的低点本来就在均线附近，\n"
     "                把它算进来会让所有快速发动的票都不通过）\n"),
    # 3) 实现
    ("            trend_hold = bool(float(np.min(lw[-tw:])) >= ma20 * (1.0 - MARKUP_PULLBACK_TOL))\n",
     "            trend_hold = bool(float(np.min(lw[-MARKUP_HOLD_WIN:]))\n"
     "                              >= ma20 * (1.0 - MARKUP_PULLBACK_TOL))\n"),
    # 4) 未通过时的分数项里也换成同一个窗口（保持口径一致）
    ("                    + 0.25 * _c01(1.0 - abs(float(np.min(lw[-tw:]))\n"
     "                                            / (ma20 + 1e-9) - 1.0) / 0.10))\n",
     "                    + 0.25 * _c01(1.0 - abs(float(np.min(lw[-MARKUP_HOLD_WIN:]))\n"
     "                                            / (ma20 + 1e-9) - 1.0) / 0.10))\n"),
]

for i, (old, new) in enumerate(REP, 1):
    cnt = s.count(old)
    assert cnt == 1, '第 %d 处锚点命中 %d 次' % (i, cnt)
    s = s.replace(old, new)

io.open(TGT, 'wb').write(s.replace('\n', '\r\n').encode('utf-8'))
raw2 = io.open(TGT, 'rb').read()
print('行数=%d CRLF=%d 裸LF=%d' % (raw2.count(b'\n'), raw2.count(b'\r\n'),
                                   raw2.count(b'\n') - raw2.count(b'\r\n')))
py_compile.compile(TGT, doraise=True)
print('py_compile OK')
