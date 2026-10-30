# -*- coding: utf-8 -*-
import py_compile, shutil, sys
P = r"D:\QuantMonitorV6\ui\battle_widgets\base.py"
sys.stdout.reconfigure(encoding="utf-8")
raw = open(P, "rb").read()
crlf = raw.count(b"\r\n"); lf = raw.count(b"\n") - crlf
print("行尾检测: CRLF=%d 裸LF=%d -> %s" % (crlf, lf, "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "混合")))
shutil.copy2(P, P + ".bak_before_ctrl")
s = raw.decode("utf-8")
if crlf and not lf:
    s = s.replace("\r\n", "\n")

helper = '''CTRL_COL_TITLE = '\u63a7\u76d8'


def fetch_ctrl_for(rows, code_key='code', info_key='ctrl'):
    """\u7ed9\u884c\u6570\u636e\u6302\u4e0a\u63a7\u76d8\u5ea6\uff08\u63a7\u76d8\u5206 + \u6d17\u76d8/\u51fa\u8d27 + \u6587\u6848\uff09\u3002

    \u5fc5\u987b\u5728 run_async \u7684\u540e\u53f0\u51fd\u6570\u91cc\u8c03\uff08\u5185\u90e8\u8bfb\u672c\u5730 kline_cache\uff0c
    \u9996\u6b21\u7ea6 28ms/\u53ea\uff0c\u540c\u4e00\u4ea4\u6613\u65e5\u7b2c\u4e8c\u6b21\u547d\u4e2d\u7f13\u5b58\u51e0\u4e4e\u4e0d\u82b1\u65f6\u95f4\uff09\uff0c
    \u4e0d\u8981\u5728 UI \u7ebf\u7a0b\u76f4\u63a5\u8c03\u3002\u4efb\u4f55\u5f02\u5e38\u90fd\u4e0d\u4f1a\u628a\u5217\u8868\u5237\u65b0\u6253\u65ad\u3002
    """
    try:
        from services.control_profile import get_ctrl_map
        codes = [str(r.get(code_key)) for r in rows if r.get(code_key)]
        m = get_ctrl_map(codes)
        for r in rows:
            r[info_key] = m.get(str(r.get(code_key)))
    except Exception:
        for r in rows:
            r.setdefault(info_key, None)
    return rows


def attach_ctrl(table, rows, info_key='ctrl', col=None):
    """\u628a\u63a7\u76d8\u5ea6\u586b\u5230\u8868\u683c\u6700\u540e\u4e00\u5217\u3002

    \u6709\u63d0\u793a: '98\u00b7\u5019\u9009'(\u7eff) / '80\u00b7\u51fa\u8d27'(\u7ea2) / '97\u00b7\u6d17\u76d8'(\u6a59)
    \u65e0\u63d0\u793a: '71'(\u7070)    \u6ca1\u6570\u636e: '--'(\u7070)
    \u65b0\u5217\u52a0\u5728\u672b\u5c3e\uff0c\u4e0d\u4f1a\u52a8\u539f\u6709\u5217\u53f7\u3002
    """
    try:
        from services.control_profile import ctrl_cell, ctrl_tooltip
    except Exception:
        return
    n = table.columnCount()
    if col is None:
        col = n - 1
    if col < 0:
        return
    for i, r in enumerate(rows):
        if i >= table.rowCount():
            break
        info = r.get(info_key)
        txt, color = ctrl_cell(info)
        it = QTableWidgetItem(txt)
        it.setForeground(QColor(color))
        it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
        it.setToolTip(ctrl_tooltip(info))
        table.setItem(i, col, it)


'''

anchor = "def pct_color(pct):\n"
assert s.count(anchor) == 1, "锚点命中 %d 次" % s.count(anchor)
s = s.replace(anchor, helper + anchor, 1)
out = s.replace("\n", "\r\n") if (crlf and not lf) else s
open(P, "wb").write(out.encode("utf-8"))
py_compile.compile(P, doraise=True)
print("OK base.py 已加 fetch_ctrl_for / attach_ctrl")
print("  备份:", P + ".bak_before_ctrl")
