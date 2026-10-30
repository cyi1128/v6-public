# -*- coding: utf-8 -*-
"""一次性补丁【勿重跑】：
1) 日K表的 _daily_short_action 兜底也从 6 字放宽到 8 字（同「操作建议」的坑）
2) 建表时的列宽初始化跳过「操作建议」列 —— 否则会给 Stretch 列强塞一个 60px
"""
P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
s = open(P, newline='', encoding='utf-8').read()
s = s.replace('\r\n', '\n')

a = '        return act[:6]'
assert s.count(a) == 1, s.count(a)
s = s.replace(a, '        return act[:8]   # 兜底：放宽到 8 字（原来 6 字，容易把词切断）')

b = '        for _i, _w in enumerate(self._HOLD_MINW.get(i, 60) for i in range(11)):'
assert s.count(b) == 1, s.count(b)
s = s.replace(b, '        for _i, _w in enumerate(self._HOLD_MINW.get(i, 60)\n'
                 '                               for i in range(11) if i != COL_H_ACT):')

out = s.replace('\n', '\r\n')
compile(out, P, 'exec')
assert out.count('\n') - out.count('\r\n') == 0
open(P, 'w', newline='', encoding='utf-8').write(out)
chk = open(P, newline='', encoding='utf-8').read()
print('行数 %d | CRLF %d | 裸LF %d | 编译 OK' % (
    chk.count('\r\n') + 1, chk.count('\r\n'), chk.count('\n') - chk.count('\r\n')))
print('act[:6] 残留 =', chk.count('act[:6]'), '｜ act[:8] =', chk.count('act[:8]'),
      '｜ 跳过 ACT 的初始化 =', chk.count('if i != COL_H_ACT'))
