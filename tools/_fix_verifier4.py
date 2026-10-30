import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_cached.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace("def base_row(c, n):\n    return dict(",
              "class Row(dict):\n"
              "    \"\"\"\u5bbd\u5bb9\u5b57\u5178\uff1a\u7f3a\u952e\u8fd4\u56de\u7a7a\uff0c\u907f\u514d\u6d4b\u8bd5\u6570\u636e\u53cd\u590d\u8865\u952e\u3002\"\"\"\n"
              "    def __missing__(self, k):\n"
              "        return ''\n"
              "\n"
              "\n"
              "def base_row(c, n):\n    return Row(")
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
