# -*- coding: utf-8 -*-
import io
P = r"D:\QuantMonitorV6\tools\_shot_ctrl_col.py"
s = io.open(P, encoding="utf-8").read()
old = "from PyQt6.QtGui import QColor\nfrom PyQt6.QtCore import Qt\napp = QApplication([])\n"
new = ("from PyQt6.QtGui import QColor, QFont, QFontDatabase\nfrom PyQt6.QtCore import Qt\n"
       "app = QApplication([])\n"
       "_fams = QFontDatabase.families()\n"
       "for _f in ('Microsoft YaHei', 'SimHei', 'SimSun', 'DengXian', 'KaiTi'):\n"
       "    if _f in _fams:\n"
       "        app.setFont(QFont(_f, 9))\n"
       "        print('using font:', _f)\n"
       "        break\n"
       "else:\n"
       "    print('!! 没找到中文字体，可用前20个:', [str(x) for x in _fams[:20]])\n")
assert s.count(old) == 1, "命中 %d" % s.count(old)
s = s.replace(old, new, 1)
s = s.replace('"QTableWidget{background:#ffffff;color:#1A1B1C;font-size:12px;gridline-color:#e0e0e0;}"',
              '"QTableWidget{background:#ffffff;color:#1A1B1C;font-family:\\"Microsoft YaHei\\",\\"SimHei\\",sans-serif;font-size:12px;gridline-color:#e0e0e0;}"')
io.open(P, "w", encoding="utf-8").write(s)
print("OK 已加字体设置")
