# -*- coding: utf-8 -*-
"""UI：龙头 tooltip 加封成比/烂板；可介入列加量化痕迹标记 + 机构字段 tooltip。"""
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

# ---------- 1. 龙头 tooltip 加封成比 ----------
old1 = """                    _tip = ('【情绪龙头】%s %+.2f%%\\n'
                            '判定依据：首封 %s（%s）｜ %d连板 ｜ '
                            '封单 %.2f亿 · 强度 %.2f%%%s\\n'
                            '（排序：连板身位 > 封板时段 > 封单强度）'
                            % (d0['name'], d0['pct'], d0['time'] or '--',
                               d0.get('slot_name') or '--', d0['lbc'],
                               d0['fund'] / 1e8,
                               (d0.get('strength') or 0.0) * 100,
                               (' ｜ 炸板%d次' % d0['zbc']) if d0['zbc'] else ''))"""
new1 = """                    _tip = ('【情绪龙头】%s %+.2f%%\\n'
                            '判定依据：首封 %s（%s）｜ %d连板 ｜ '
                            '封单 %.2f亿\\n'
                            '　　　　　封成比 %.2f · 封单强度 %.2f%%%s%s\\n'
                            '（排序：连板身位 > 烂板沉底 > 封板时段 > '
                            '封成比 > 封单强度）'
                            % (d0['name'], d0['pct'], d0['time'] or '--',
                               d0.get('slot_name') or '--', d0['lbc'],
                               d0['fund'] / 1e8,
                               d0.get('ratio') or 0.0,
                               (d0.get('strength') or 0.0) * 100,
                               (' ｜ 炸板%d次' % d0['zbc']) if d0['zbc'] else '',
                               '  ⚠烂板' if (d0['lbc'] >= 2
                                             and (d0.get('ratio') or 0.0) < 0.10)
                               else ''))"""
assert s.count(old1) == 1, '龙头tip锚点 %d 次' % s.count(old1)
s = s.replace(old1, new1)
print('  ✓ 龙头 tooltip 加封成比/烂板')

# ---------- 2. 接力参考加封成比 ----------
old2 = """                        _tip += ('\\n\\n【次日接力参考】%s %s\\n'
                                 '　　%d板 ｜ 首封 %s（%s）\\n'
                                 '　　封单 %.2f亿 · 强度 %.2f%%%s'
                                 % (_e['name'], _e['code'], _e['lbc'],
                                    _e['time'] or '--',
                                    _e.get('slot_name') or '--',
                                    _e['fund'] / 1e8,
                                    (_e.get('strength') or 0.0) * 100,
                                    (' ｜ 炸板%d次' % _e['zbc'])
                                    if _e.get('zbc') else ''))"""
new2 = """                        _tip += ('\\n\\n【次日接力参考】%s %s\\n'
                                 '　　%d板 ｜ 首封 %s（%s）\\n'
                                 '　　封单 %.2f亿 · 封成比 %.2f · 强度 %.2f%%%s'
                                 % (_e['name'], _e['code'], _e['lbc'],
                                    _e['time'] or '--',
                                    _e.get('slot_name') or '--',
                                    _e['fund'] / 1e8,
                                    _e.get('ratio') or 0.0,
                                    (_e.get('strength') or 0.0) * 100,
                                    (' ｜ 炸板%d次' % _e['zbc'])
                                    if _e.get('zbc') else ''))"""
assert s.count(old2) == 1, '接力tip锚点 %d 次' % s.count(old2)
s = s.replace(old2, new2)
print('  ✓ 接力参考加封成比')

# ---------- 3. 可介入列：量化痕迹标记 + 机构字段 tooltip ----------
old3 = """                set_table_item(self.pick_table, row, P_PICKS,
                               '  '.join('%s %+.1f%%' % (p[1], p[2])
                                         for p in picks[:3]),
                               BC.CYAN, align=left)"""
new3 = """                set_table_item(self.pick_table, row, P_PICKS,
                               '  '.join('%s %+.1f%%%s'
                                         % (p[1], p[2],
                                            '✅' if (len(p) > 10 and p[10]) else '')
                                         for p in picks[:3]),
                               BC.CYAN, align=left)"""
assert s.count(old3) == 1, '可介入列锚点 %d 次' % s.count(old3)
s = s.replace(old3, new3)
print('  ✓ 可介入列加 ✅ 量化痕迹标记')

old4 = """                    _pi.setToolTip(
                        '【可介入】%s 里还没涨停、但已在动的标的：\\n' % r['name']
                        + '\\n'.join(
                            '  %s %s  %+.2f%%  量比%.2f  现价%.2f'
                            % (p[1], p[0], p[2], p[3], p[4])
                            + (('  距MA20 %+.1f%%' % p[5])
                               if len(p) > 5 and p[5] is not None else '')
                            for p in picks)
                        + '\\n\\n口径：非涨停 ｜ 涨幅 1~9% ｜ 量比≥1.2 ｜ 现价≥MA20'
                          '\\n（点此格跳转候选第一名个股分析）')"""
new4 = """                    _lines = []
                    for p in picks:
                        _t = ('  %s %s  %+.2f%%  量比%.2f  现价%.2f'
                              % (p[1], p[0], p[2], p[3], p[4]))
                        if len(p) > 5 and p[5] is not None:
                            _t += '  距MA20 %+.1f%%' % p[5]
                        if len(p) > 9 and p[6] is not None:
                            _t += ('\\n      成交额 %.2f亿 ｜ 流通市值 %.0f亿 ｜ '
                                   '换手 %.2f%%' % (p[6], p[7], p[8]))
                        if len(p) > 9 and p[9] is not None:
                            _t += ' ｜ VWAP偏离 %+.2f%%' % p[9]
                            _t += ('　✅算法单痕迹' if (len(p) > 10 and p[10])
                                   else '')
                        _lines.append(_t)
                    _pi.setToolTip(
                        '【可介入】%s 里还没涨停、但已在动的标的：\\n' % r['name']
                        + '\\n'.join(_lines)
                        + '\\n\\n口径：非涨停 ｜ 涨幅 1~9% ｜ 量比≥1.2 ｜ '
                          '现价≥MA20\\n'
                          '机构门槛：成交额 ≥2 亿 ｜ 流通市值 ≥20 亿\\n'
                          '✅ = |最新价 − VWAP| ≤0.5% 且量比 ≥1.5，'
                          '算法单执行痕迹（价格贴当日均价走）\\n'
                          '（点此格跳转候选第一名个股分析）')"""
assert s.count(old4) == 1, '可介入tip锚点 %d 次' % s.count(old4)
s = s.replace(old4, new4)
print('  ✓ 可介入 tooltip 加机构字段')

old5 = """                    _pi.setToolTip('该板块成分池里暂无符合「未涨停 + 涨幅1~9%'
                                   ' + 量比≥1.2 + 站上MA20」的标的')"""
new5 = """                    _pi.setToolTip('该板块成分池里暂无符合「未涨停 + 涨幅1~9%'
                                   ' + 量比≥1.2 + 站上MA20 + 成交额≥2亿'
                                   ' + 流通市值≥20亿」的标的')"""
assert s.count(old5) == 1, '空态锚点 %d 次' % s.count(old5)
s = s.replace(old5, new5)
print('  ✓ 空态提示同步')

shutil.copy2(P, P + '.bak_before_inst_exec')
open(P, 'wb').write(s.encode('utf-8'))
print()
print('已写入 %s (%d bytes, %d 行)' % (P, os.path.getsize(P),
                                      len(s.splitlines())))
py_compile.compile(P, doraise=True)
print('py_compile OK')
