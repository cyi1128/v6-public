import io
P = r"D:\QuantMonitorV6\tools\_verify_ctrl_cached.py"
s = io.open(P, encoding="utf-8").read()
s = s.replace("rank=1, momentum=1.0, base_price=9.5, atr=0.3, support=9.5,",
              "rank=1, momentum=[], base_price=9.5, atr=0.3, support=9.5,")
s = s.replace("resistance=10.5, vol_ratio=1.2, ma5=9.8, ma20=9.5)",
              "resistance=10.5, vol_ratio=1.2, ma5=9.8, ma20=9.5,\n"
              "                cur_price=10.0, last_price=10.0, close=10.0, volume=1e6)")
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("补字段完成")
