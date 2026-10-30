# -*- coding: utf-8 -*-
"""一次性补丁【勿重跑】：我的自选表
1) 收紧数字列（按真实文字宽度重新给量），把省下的宽度让给「题材」列
2) 题材、股票名称 单元格挂 tooltip —— 超长题材悬停看全文（列再宽也放不下 30 字的题材）
"""
import os

P = r'D:\QuantMonitorV6\ui\battle_widgets\watchlist_widget.py'
BAK = P + '.bak_before_colfit'
src0 = open(P, newline='', encoding='utf-8').read()
if not os.path.exists(BAK):
    open(BAK, 'w', newline='', encoding='utf-8').write(src0)
    print('已备份 ->', BAK)
s = src0.replace('\r\n', '\n')

old = """        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 65)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 110)
        self.table.setColumnWidth(COL_CTRL, 78)"""
new = """        # 列宽按「表头 + 典型内容」的真实像素给量（不再写死偏宽的数字列），
        # 省下来的宽度全部给「题材」列（COL_THEME 是 Stretch），让它多显示几个字。
        self.table.setColumnWidth(0, 78)     # 股票名称（4~5 字）
        self.table.setColumnWidth(1, 62)     # 股票代码（6 位）
        self.table.setColumnWidth(2, 56)     # 现价
        self.table.setColumnWidth(3, 68)     # 涨幅（+10.03%）
        self.table.setColumnWidth(4, 68)     # 振幅（+10.03%）
        self.table.setColumnWidth(5, 62)     # 市值（338亿）
        self.table.setColumnWidth(6, 96)     # 题材（还会被 Stretch 拉宽）
        self.table.setColumnWidth(COL_CTRL, 66)   # 控盘（99候选）"""
assert s.count(old) == 1
s = s.replace(old, new)

old_cell = """                theme = (self._themes or {}).get(code, '--') or '--'
                set_table_item(self.table, view_row, COL_THEME, theme, BC.RED, bold=True)"""
new_cell = """                theme = (self._themes or {}).get(code, '--') or '--'
                _tit = set_table_item(self.table, view_row, COL_THEME, theme, BC.RED, bold=True)
                _tit.setToolTip(theme)   # 题材常超过 20 字，列再宽也放不下 → 悬停看全文"""
assert s.count(old_cell) == 1
s = s.replace(old_cell, new_cell)

out = s.replace('\n', '\r\n')
compile(out, P, 'exec')
assert out.count('\n') - out.count('\r\n') == 0
open(P, 'w', newline='', encoding='utf-8').write(out)
chk = open(P, newline='', encoding='utf-8').read()
print('补丁后 行数 %d | CRLF %d | 裸LF %d | 编译 OK' % (
    chk.count('\r\n') + 1, chk.count('\r\n'), chk.count('\n') - chk.count('\r\n')))
print('固定列合计 =', 78 + 62 + 56 + 68 + 68 + 62 + 96 + 66, '（原 608）')
