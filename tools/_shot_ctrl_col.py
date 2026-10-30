# -*- coding: utf-8 -*-
"""把日K建仓表「控盘」列的 19 条提示行画成 PNG。
数据不是编的：先跑真实的 _daily_fetch_and_calc + _daily_render_table，
再把单元格文字/颜色读回来，用 PIL 按读回的值画。
"""
import os
import sys
import types

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\QuantMonitorV6')
sys.stdout.reconfigure(encoding='utf-8')

from PyQt6.QtWidgets import QApplication, QCheckBox
from PIL import Image, ImageDraw, ImageFont

app = QApplication([])
import ui.battle_widgets.atr_t_widget as M

cls = None
for _n in dir(M):
    _v = getattr(M, _n)
    if isinstance(_v, type) and hasattr(_v, '_daily_render_table'):
        cls = _v
        break


class Stub:
    pass


o = Stub()
o.daily_table = M.make_table(len(M.HEADER_DAILY), M.HEADER_DAILY)
o._chk_env = QCheckBox()
o._env_hint = None
o._daily_rows = []
o._daily_check_market = lambda *a, **k: None
for _m in ('_daily_visible_rows', '_daily_render_table', '_daily_fetch_and_calc'):
    setattr(o, _m, types.MethodType(getattr(cls, _m), o))
o._daily_rows = o._daily_fetch_and_calc() or []
o._daily_render_table()
src = o.daily_table
print('完整表格行数: %d' % src.rowCount())

tip_idx = [i for i in range(src.rowCount())
           if (src.item(i, M.COL_D_CTRL) and '·' in src.item(i, M.COL_D_CTRL).text())]
flat_idx = [i for i in range(src.rowCount()) if i not in tip_idx][:3]
rows_i = tip_idx + flat_idx
print('带标签 %d 行 + 无标签样例 %d 行' % (len(tip_idx), len(flat_idx)))

COLS = [M.COL_D_NAME, M.COL_D_CODE, M.COL_D_PRICE, M.COL_D_PCT,
        M.COL_D_TRIGGER, M.COL_D_CTRL, M.COL_D_ENV, M.COL_D_BASE_DATE]
HEAD = [M.HEADER_DAILY[c] for c in COLS]
W = [104, 74, 62, 74, 104, 84, 58, 96]

F = 'C:/Windows/Fonts/msyh.ttc'
FB = 'C:/Windows/Fonts/msyhbd.ttc'
f_t = ImageFont.truetype(F, 13)
f_b = ImageFont.truetype(FB, 13)
f_h = ImageFont.truetype(FB, 14)
f_ttl = ImageFont.truetype(FB, 16)

RH, HH, TITLE_H = 27, 30, 52
PW = sum(W) + 2
PH = TITLE_H + HH + RH * len(rows_i) + 12
img = Image.new('RGB', (PW, PH), '#ffffff')
d = ImageDraw.Draw(img)

d.text((10, 9), '日K建仓表 · 新增「控盘」列（19 条提示全部带标签）', font=f_ttl, fill='#1A1B1C')
d.text((10, 30), '数据来自真实渲染读回（query_signals -> _daily_fetch_and_calc -> _daily_render_table）',
       font=f_t, fill='#6B7280')

y = TITLE_H
d.rectangle([0, y, PW - 1, y + HH - 1], fill='#f2f2f2')
x = 1
for i, h in enumerate(HEAD):
    tw = d.textlength(h, font=f_h)
    d.text((x + (W[i] - tw) / 2, y + 7), h, font=f_h, fill='#1A1B1C')
    x += W[i]
d.line([0, y + HH - 1, PW - 1, y + HH - 1], fill='#c8c8c8')
y += HH

for n, si in enumerate(rows_i):
    if n == len(tip_idx):
        d.line([0, y - 1, PW - 1, y - 1], fill='#9e9e9e')
    bg = '#ffffff' if n % 2 == 0 else '#fafafa'
    d.rectangle([0, y, PW - 1, y + RH - 1], fill=bg)
    x = 1
    for ci, sc in enumerate(COLS):
        it = src.item(si, sc)
        txt = it.text() if it else ''
        if ci == M.COL_D_NAME:
            fnt, col = f_b, '#1A1B1C'
        elif ci == M.COL_D_CTRL:
            fnt = f_b
            col = it.foreground().color().name() if it else '#9e9e9e'
        else:
            fnt, col = f_t, '#333333'
        tw = d.textlength(txt, font=fnt)
        d.text((x + (W[ci] - tw) / 2, y + 7), txt, font=fnt, fill=col)
        x += W[ci]
    d.line([0, y + RH - 1, PW - 1, y + RH - 1], fill='#e0e0e0')
    y += RH

for xx in range(1, PW - 1, 1):
    pass
x = 1
for i in range(len(W) - 1):
    x += W[i]
    d.line([x, TITLE_H, x, y - 1], fill='#e0e0e0')

OUT = r'D:\QuantMonitorV6\_shot_ctrl_col.png'
img.save(OUT)
print('已保存:', OUT, os.path.getsize(OUT), 'bytes', img.size)
