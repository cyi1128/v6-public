# -*- coding: utf-8 -*-
import py_compile, shutil, sys
P = r"D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py"
sys.stdout.reconfigure(encoding="utf-8")
shutil.copy2(P, P + ".bak_before_ctrl_tip")
raw = open(P, "rb").read()
assert raw.count(b"\r\n") > 0
s = raw.decode("utf-8").replace("\r\n", "\n")

def rep(old, new, tag):
    global s
    assert s.count(old) == 1, "%s 命中 %d 次" % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print("  OK", tag)

# 1) tooltip 只放「控盘」段，且把控盘信息放最前面
rep("            _c_item.setToolTip('\u63a7\u76d8\u5206 %.1f\uff08%s\uff09%s' % (\n"
    "                _cs, r.get('stage_guess') or '--', ('\\n' + _nt if _has_tip else '')))\n",
    "            _c_item.setToolTip(('\u63a7\u76d8\u5206 %.1f\uff08%s\uff09' % (\n"
    "                _cs, r.get('stage_guess') or '--'))\n"
    "                + (('\\n[\u63a7\u76d8] ' + _tt) if _has_tip else ''))\n",
    'G1 tooltip 顺序')

# 2) docstring 列数
rep("        \"\"\"[V5.0] \u6e32\u67d3\u65e5K\u5efa\u4ed3\u8868\uff0811\u5217\uff0c\u542b\u73af\u5883\u5206\u9600\u95e8\u8fc7\u6ee4\uff09\"\"\"\n",
    "        \"\"\"[V5.0] \u6e32\u67d3\u65e5K\u5efa\u4ed3\u8868\uff0812\u5217\uff0c\u542b\u73af\u5883\u5206\u9600\u95e8\u8fc7\u6ee4\uff09\"\"\"\n",
    'G2 docstring 列数')

open(P, "wb").write(s.replace("\n", "\r\n").encode("utf-8"))
py_compile.compile(P, doraise=True)
print("OK tooltip 已修正")
