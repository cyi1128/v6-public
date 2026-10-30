# -*- coding: utf-8 -*-
"""一次性修补：给 A/B 三个新方法补 @staticmethod，并修 docstring 里的 \\m 转义。"""
import io
import os

os.chdir(r'D:\QuantMonitorV6')
P = os.path.join('strategy', 'base.py')
s = io.open(P, encoding='utf-8', newline='').read()
NL = '\r\n'
assert s.count('\n') == s.count(NL)

for sig in ('    def detect_breakdown_recover(df):',
            '    def volume_percentile(df, win=VR_WIN):',
            '    def detect_volume_regime(df):'):
    old = sig + NL
    assert s.count(old) == 1, '签名锚点不唯一: %s' % sig
    s = s.replace(old, '    @staticmethod' + NL + old)

old_d = 'MARKUP_LOCK_POS_MIN=0.00（依据 tools\\markup2_pos_calib.txt）' + NL
assert s.count(old_d) == 1, 'docstring 反斜杠锚点不唯一'
s = s.replace(old_d, 'MARKUP_LOCK_POS_MIN=0.00（依据 tools\\\\markup2_pos_calib.txt）' + NL)

io.open(P, 'w', encoding='utf-8', newline='').write(s)
c = io.open(P, encoding='utf-8', newline='').read()
print('行 %d ｜ CRLF %d ｜ 裸LF %d ｜ @staticmethod 计数 %d'
      % (c.count('\n'), c.count(NL), c.count('\n') - c.count(NL), c.count('@staticmethod')))
