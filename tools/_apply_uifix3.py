# -*- coding: utf-8 -*-
"""一次性补丁【勿重跑】：
项目样式表 QTableWidget::item{padding:4px 8px} —— 每格左右共吃掉 16px。
所以 812px 宽的半屏表里，11 列必须同时满足「文字 + 16px 内边距 + 边框」。此处：
1) 表头去掉冗余前缀（分时做T面板里的「做T买点/卖点」→「买点/卖点」，「股票名称」→「名称」）
   省下约 104px，全部让给「操作建议」；悬停仍能看全称
2) _HOLD_PAD 14 → 20（= 16 内边距 + 2 边框 + 2 加粗余量），保证每格不再被省略号截断
"""
P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
s = open(P, newline='', encoding='utf-8').read().replace('\r\n', '\n')

old_h = """HEADER_HOLD = ['股票名称', '代码', '现价', '涨跌幅',
               '做T买点', '做T卖点', '动能信号', '风控状态',
               '信号灯', '操作建议', CTRL_COL_TITLE]"""
new_h = """# 表头刻意用短名：本表在半屏里只有 ~820px 宽，而样式表每格左右要吃掉 16px 内边距
# （QTableWidget::item{padding:4px 8px}）。6 字表头 × 11 列的宽度会直接挤掉「操作建议」，
# 所以 股票名称→名称、做T买点→买点、做T卖点→卖点（面板本身就叫「分时做T」，前缀冗余）。
# 全称悬停可看（见 AtrTWidget 里给表头挂的 tooltip），不要为了改名去动这一行以外的地方。
HEADER_HOLD = ['名称', '代码', '现价', '涨跌幅',
               '买点', '卖点', '动能信号', '风控状态',
               '信号灯', '操作建议', CTRL_COL_TITLE]"""
assert s.count(old_h) == 1
s = s.replace(old_h, new_h)

old_p = '    _HOLD_PAD = 14          # 单元格左右留白（含加粗字的额外宽度）'
new_p = ('    # 单元格左右留白：样式表 QTableWidget::item{padding:4px 8px} 就要 16px，\n'
         '    # 再加 2px 边框 + 2px 加粗余量。这个值不能再调小，否则文字会被省略号截断。\n'
         '    _HOLD_PAD = 20')
assert s.count(old_p) == 1
s = s.replace(old_p, new_p)

old_mk = '        self.table = make_table(11, HEADER_HOLD)'
new_mk = """        self.table = make_table(11, HEADER_HOLD)
        # 表头用了短名（省宽度），悬停给出全称
        for _hc, _full in ((COL_H_NAME, '股票名称'), (COL_H_BUY, '做T买点'),
                           (COL_H_SELL, '做T卖点')):
            _hi = self.table.horizontalHeaderItem(_hc)
            if _hi is not None:
                _hi.setToolTip(_full)"""
assert s.count(old_mk) == 1
s = s.replace(old_mk, new_mk)

out = s.replace('\n', '\r\n')
compile(out, P, 'exec')
assert out.count('\n') - out.count('\r\n') == 0
open(P, 'w', newline='', encoding='utf-8').write(out)
chk = open(P, newline='', encoding='utf-8').read()
print('行数 %d | CRLF %d | 裸LF %d | 编译 OK' % (
    chk.count('\r\n') + 1, chk.count('\r\n'), chk.count('\n') - chk.count('\r\n')))
print('_HOLD_PAD=20:', '_HOLD_PAD = 20' in chk, '｜ 短表头:', "'名称', '代码', '现价', '涨跌幅'," in chk,
      '｜ 表头 tooltip:', chk.count('setToolTip(_full)'))
