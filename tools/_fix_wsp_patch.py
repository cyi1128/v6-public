import io
P = r"D:\QuantMonitorV6\tools\_add_ctrl_watchlist_panel.py"
s = io.open(P, encoding="utf-8").read()
# 修 W2 锚点（真实列宽是 120 不是 200）
s = s.replace('rep("        self.table.setColumnWidth(8, 200)   # AI\\u64cd\\u4f5c\\u5efa\\u8bae\\n",\n'
              '    "        self.table.setColumnWidth(8, 200)   # AI\\u64cd\\u4f5c\\u5efa\\u8bae\\n"',
              'rep("        self.table.setColumnWidth(8, 120)  # AI\\u64cd\\u4f5c\\u5efa\\u8bae\\n",\n'
              '    "        self.table.setColumnWidth(8, 120)  # AI\\u64cd\\u4f5c\\u5efa\\u8bae\\n"')
# threading 模块级没导入 -> 在 _ctrl_async 里局部导入
s = s.replace('            self._ctrl_busy = True\n',
              '            self._ctrl_busy = True\n'
              '            import threading\n', 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("补丁脚本已修正")
