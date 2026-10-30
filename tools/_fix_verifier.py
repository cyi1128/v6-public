import io, re
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_cached.py"
s = io.open(P, encoding="utf-8").read()
# 1) wsp 必须先把 QtWebEngineWidgets 导入（项目已知环境限制），并在 QApplication 前设 AA_ShareOpenGLContexts
s = s.replace("    from PyQt6.QtWidgets import QApplication\n    app = QApplication([])\n",
              "    from PyQt6.QtCore import Qt as _Qt\n    from PyQt6.QtWidgets import QApplication\n"
              "    if mod == 'wsp':\n"
              "        _Qt.ApplicationAttribute.AA_ShareOpenGLContexts\n"
              "        QApplication.setAttribute(_Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)\n"
              "        import PyQt6.QtWebEngineWidgets  # noqa: F401  必须在 QApplication 之前\n"
              "    app = QApplication([])\n")
# 2) 补齐各模块渲染需要的额外字段
s = s.replace("                is_tail=False)",
              "                is_tail=False, buy_point=9.5, sell_point=10.5, trade_date='2026-10-10',\n"
              "                pnl=1.0, pnl_pct=1.0, cum=1.0, rt_price=10.0, rt_pct=1.0,\n"
              "                reason=u'\u6d4b\u8bd5', board=u'\u6d4b\u8bd5', rank=1)")
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("测试脚本已补字段")
