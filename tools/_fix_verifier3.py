import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_cached.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace("cur_price=10.0, last_price=10.0, close=10.0, volume=1e6)",
              "cur_price=10.0, last_price=10.0, close=10.0, volume=1e6,\n"
              "                signal_text='', kind='', sub_kind='', tag='', note='',\n"
              "                trigger='', level='', state='', action='', type='')")
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
