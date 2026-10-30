# -*- coding: utf-8 -*-
import io, shutil, sys
sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\AGENTS.md"
raw = open(P, "rb").read()
c, l = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
assert c == 0 and l > 0, "AGENTS.md 不是纯 LF：CRLF=%d LF=%d" % (c, l)
shutil.copy2(P, P + ".bak_before_cached")
s = raw.decode("utf-8")

old = """  - \u57fa\u7c7b\u5de5\u5177\uff1a`ui\\battle_widgets\\base.py` \u7684 `fetch_ctrl_for(rows)`\uff08\u540e\u53f0\u6279\u91cf\u7b97\uff09\u3001`attach_ctrl(table, rows)`\uff08\u586b\u672b\u5217\uff09\u3001`BattleModuleBase.ctrl_async_fill(rows, on_done)`\uff08\u5f02\u6b65\u8865\u6570\uff09\u3002\u65b0\u5217\u4e00\u5f8b\u52a0\u5728**\u672b\u5c3e**\uff0c\u6240\u4ee5\u8981\u628a\u539f\u672b\u5217\u7684 `stretchLastSection` \u6539\u6210\u663e\u5f0f Stretch \u67d0\u4e00\u5217\uff0c\u5426\u5219\u63a7\u76d8\u5217\u4f1a\u88ab\u6491\u5f00\u3002"""
new = """  - \u57fa\u7c7b\u5de5\u5177\uff1a`ui\\battle_widgets\\base.py` \u7684 `fetch_ctrl_for(rows)`\uff08\u540e\u53f0\u6279\u91cf\u7b97\uff09\u3001`fetch_ctrl_cached(rows)`\uff08**\u53ea\u8bfb\u5df2\u6709\u7f13\u5b58\u3001\u96f6\u8ba1\u7b97**\uff0c\u53ef\u5728 UI \u7ebf\u7a0b\u76f4\u63a5\u8c03\uff09\u3001`attach_ctrl(table, rows)`\uff08\u586b\u672b\u5217\uff09\u3001`BattleModuleBase.ctrl_async_fill(rows, on_done)`\uff08\u5f02\u6b65\u8865\u6570\uff09\u3001`BattleModuleBase.ctrl_fill_and_async(rows, on_done)`\uff08\u7f13\u5b58\u5373\u65f6\u586b + \u540e\u53f0\u8865\u7b97 + \u56de\u8c03\u91cd\u7ed8\uff09\u3002\u65b0\u5217\u4e00\u5f8b\u52a0\u5728**\u672b\u5c3e**\uff0c\u6240\u4ee5\u8981\u628a\u539f\u672b\u5217\u7684 `stretchLastSection` \u6539\u6210\u663e\u5f0f Stretch \u67d0\u4e00\u5217\uff0c\u5426\u5219\u63a7\u76d8\u5217\u4f1a\u88ab\u6491\u5f00\u3002
  - **\u53cd\u590d\u8e29\u8fc7\u7684\u5751\uff08\u63a7\u76d8\u5217\u6574\u7247\u53d8 `--`\uff0c\u5df2\u4fee\uff09**\uff1a\u884c\u5bf9\u8c61\u5e38\u5728**\u6e32\u67d3\u524d\u88ab\u91cd\u65b0\u88c5\u914d**\uff08\u5feb\u7167\u6062\u590d\u3001\u6301\u4e45\u5316\u5408\u5e76\u3001\u521d\u59cb\u6062\u590d\uff09\uff0c\u53d6\u6570\u65f6\u6302\u4e0a\u7684 `ctrl` \u4f1a\u4e22\u6389\u3002\u56e0\u6b64\u5df2\u5728**\u6bcf\u4e2a\u6e32\u67d3\u51fd\u6570\u6700\u9876\u90e8**\u52a0 `fetch_ctrl_cached(...)`\uff08\u552f\u4e00\u80fd\u8986\u76d6\u5168\u90e8\u88c5\u914d\u8def\u5f84\u7684\u4f4d\u7f6e\uff09\uff1a`limit_up_widget._render_rows` / `auction_filter_widget._render_rows` / `atr_t_widget._render_hold_table` / `picks_track_widget._render` / `watchlist_panel._update_table`\u3002\u65b0\u589e\u6e32\u67d3\u5165\u53e3\u65f6\u5fc5\u987b\u540c\u6b65\u8865\u8fd9\u4e00\u884c\u3002\u5feb\u7167\u8def\u5f84\uff08\u4f11\u5e02\u590d\u76d8\uff09\u8fd8\u8981\u8ddf\u4e00\u53e5 `ctrl_fill_and_async`\uff0c\u5426\u5219\u6ca1\u4eba\u53bb\u7b97\u7f3a\u7684\u3002
  - `services\\control_profile.py` \u7684 `get_ctrl_map(codes, cached_only=True)` \u53ea\u8fd4\u56de\u5df2\u7f13\u5b58\u6761\u76ee\u3001**\u7edd\u4e0d\u8ba1\u7b97**\uff0c\u5c31\u662f\u7ed9 UI \u7ebf\u7a0b\u7528\u7684\u3002"""
assert s.count(old) == 1, "锚点 %d" % s.count(old)
io.open(P, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
r2 = open(P, "rb").read()
print("OK AGENTS.md 行尾 CRLF=%d LF=%d 行数=%d" % (r2.count(b"\r\n"), r2.count(b"\n")-r2.count(b"\r\n"), r2.decode("utf-8").count("\n")+1))
