# -*- coding: utf-8 -*-
"""market_rhythm_widget.py：龙头 tooltip 显示封板时段 / 封单强度 / 次日接力参考。"""
import os
import shutil
import sys
import py_compile

sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\ui\battle_widgets\market_rhythm_widget.py'
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '本文件应为纯 LF'
s = raw.decode('utf-8')
print('原行数 %d / %d bytes' % (len(s.splitlines()), len(raw)))

old = """                if dragons:
                    d0 = dragons[0]
                    _it.setToolTip(
                        '【龙头】%s %+.2f%%\\n'
                        '判定依据：首封 %s ｜ %d连板 ｜ 封单 %.2f亿%s\\n'
                        '（排序：连板身位 > 首封时间 > 封单额）'
                        % (d0['name'], d0['pct'], d0['time'] or '--',
                           d0['lbc'], d0['fund'] / 1e8,
                           (' ｜ 炸板%d次' % d0['zbc']) if d0['zbc'] else ''))"""

new = """                if dragons:
                    d0 = dragons[0]
                    _tip = ('【情绪龙头】%s %+.2f%%\\n'
                            '判定依据：首封 %s（%s）｜ %d连板 ｜ '
                            '封单 %.2f亿 · 强度 %.2f%%%s\\n'
                            '（排序：连板身位 > 封板时段 > 封单强度）'
                            % (d0['name'], d0['pct'], d0['time'] or '--',
                               d0.get('slot_name') or '--', d0['lbc'],
                               d0['fund'] / 1e8,
                               (d0.get('strength') or 0.0) * 100,
                               (' ｜ 炸板%d次' % d0['zbc']) if d0['zbc'] else ''))
                    _e = r.get('entry')
                    if _e:
                        _tip += ('\\n\\n【次日接力参考】%s %s\\n'
                                 '　　%d板 ｜ 首封 %s（%s）\\n'
                                 '　　封单 %.2f亿 · 强度 %.2f%%%s'
                                 % (_e['name'], _e['code'], _e['lbc'],
                                    _e['time'] or '--',
                                    _e.get('slot_name') or '--',
                                    _e['fund'] / 1e8,
                                    (_e.get('strength') or 0.0) * 100,
                                    (' ｜ 炸板%d次' % _e['zbc'])
                                    if _e.get('zbc') else ''))
                    _tip += ('\\n\\n情绪龙头 = 这个题材谁最强（判断高度）\\n'
                             '接力参考 = 明天能打的（低位 + 早封 + 封单强）')
                    _it.setToolTip(_tip)"""

assert s.count(old) == 1, '锚点命中 %d 次' % s.count(old)
s = s.replace(old, new)
shutil.copy2(P, P + '.bak_before_dragon_key_v2')
open(P, 'wb').write(s.encode('utf-8'))
print('已写入 %s (%d bytes, %d 行)' % (P, os.path.getsize(P),
                                      len(s.splitlines())))
py_compile.compile(P, doraise=True)
print('py_compile OK')
