# -*- coding: utf-8 -*-
"""一次性补丁 4：列宽量字改用 Qt 原生 sizeHintForColumn。执行一次即失效，勿重跑。

Python 逐格量字（3294 行 × 12 列 = 4 万次跨语言调用）实测 662ms，切换筛选/排序会拖慢。
`QTableView.sizeHintForColumn()` 在 C++ 侧做同一件事，代价小一个量级；
默认只采样 1000 行，所以先把 resizeContentsPrecision 设为 -1（量全部行）。
Python 侧只保留：表头宽下限、各列下限、三个长文本列的上限、放不下时的让位顺序。
"""
import io
import os
import shutil

ROOT = r'D:\QuantMonitorV6'
os.chdir(ROOT)
P = os.path.join('ui', 'battle_widgets', 'control_screen_widget.py')
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == 0, '本文件应为纯 LF，停止'

old = """            step = 1 if n <= _FIT_MAX_ROWS else max(1, n // _FIT_SAMPLE)
            fm_h = QFontMetrics(self.table.horizontalHeader().font())
            _fms = {}

            def _fm(f):
                k = f.toString()
                fm = _fms.get(k)
                if fm is None:
                    fm = QFontMetrics(f)
                    _fms[k] = fm
                return fm

            need = {}
            for c in _FIT_COLS:
                _hit = self.table.horizontalHeaderItem(c)
                w = fm_h.horizontalAdvance(_hit.text() if _hit else '') + 10
                for i in range(0, n, step):
                    it = self.table.item(i, c)
                    if it is None:
                        continue
                    t = it.text()
                    if t:
                        w = max(w, _fm(it.font()).horizontalAdvance(t))
                _n = max(w + _WIDTH_PAD, PAGE_WIDTHS_MIN[c])
                _cap = PAGE_WIDTHS_MAX.get(c)
                need[c] = min(_n, _cap) if _cap else _n
"""
new = """            # 量字交给 Qt 自己做（C++ 侧），Python 只做夹取与让位。
            # 默认只采样 1000 行，改成 -1 = 全部行都量，保证不漏最长格。
            try:
                if n > _FIT_MAX_ROWS:
                    self.table.setResizeContentsPrecision(_FIT_SAMPLE)
                else:
                    self.table.setResizeContentsPrecision(-1)
            except Exception:
                pass
            fm_h = QFontMetrics(self.table.horizontalHeader().font())
            need = {}
            for c in _FIT_COLS:
                _hit = self.table.horizontalHeaderItem(c)
                w = fm_h.horizontalAdvance(_hit.text() if _hit else '') + 10
                w = max(w, self.table.sizeHintForColumn(c))
                _n = max(w, PAGE_WIDTHS_MIN[c]) + _HEAD_MIN_PAD
                _cap = PAGE_WIDTHS_MAX.get(c)
                need[c] = min(_n, _cap) if _cap else _n
"""
assert s.count(old) == 1, '量字段锚点不唯一'
s = s.replace(old, new)

old = "_WIDTH_PAD = 22         # 单元格左右 padding 8+8 + 一点呼吸空间\n"
new = ("_HEAD_MIN_PAD = 6       # 量字结果外再留一点呼吸空间（Qt 的 hint 已含 padding）\n")
assert s.count(old) == 1, '_WIDTH_PAD 锚点不唯一'
s = s.replace(old, new)

old = "        · 行数 ≤ _FIT_MAX_ROWS 时**全量量字**（采样会漏掉没抽到的最长格，实测差 1~3px）；\n"
new = ("        · 量字用 Qt 原生 sizeHintForColumn（C++ 侧，precision=-1 = 全部行都量）；\n"
       "          这一条是有来历的：自己用 Python 逐格量 4 万次要 662ms，还会因采样漏掉最长格；\n")
assert s.count(old) == 1, 'docstring 锚点不唯一'
s = s.replace(old, new)

old = ("from ui.battle_widgets.control_screen_widget import" if False else None)
shutil.copy2(P, P + '.bak_before_colfit4')
io.open(P, 'w', encoding='utf-8', newline='').write(s)
chk = io.open(P, encoding='utf-8', newline='').read()
print('新 %d 行 ｜ CRLF=%d ｜ 替换 ok=%s ｜ 残留 _WIDTH_PAD=%d'
      % (chk.count('\n'), chk.count('\r\n'),
         all(k in chk for k in ['sizeHintForColumn', 'setResizeContentsPrecision',
                                '_HEAD_MIN_PAD']),
         chk.count('_WIDTH_PAD')))
