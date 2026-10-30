# -*- coding: utf-8 -*-
"""修复「控盘列全是 --」：
A. control_profile.get_ctrl_map 增加 cached_only（只用已有缓存，绝不计算/阻塞）
B. base.py 增加 fetch_ctrl_cached(rows) + BattleModuleBase.ctrl_fill_and_async(rows, on_done)
C. 把「即时缓存填充」接到所有渲染装配点（快照恢复 / 持久化合并 / 初始恢复等）
"""
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

# ==================== A. services/control_profile.py（纯 LF）====================
PA = r'D:\QuantMonitorV6\services\control_profile.py'
raw = open(PA, 'rb').read()
A_CRLF, A_LF = raw.count(b'\r\n'), raw.count(b'\n') - raw.count(b'\r\n')
shutil.copy2(PA, PA + '.bak_before_cached')
s = raw.decode('utf-8')
if A_CRLF and not A_LF:
    s = s.replace('\r\n', '\n')

old = ("def get_ctrl_map(codes, force=False):\n"
       "    \"\"\"\u6279\u91cf\u53d6\u63a7\u76d8\u4fe1\u606f\uff0c\u8fd4\u56de {code: info_dict \u6216 None}\u3002\n"
       "\n"
       "    codes \u53ef\u4ee5\u662f list / set\uff0c\u5185\u90e8\u53bb\u91cd\uff1b\u987a\u5e8f\u65e0\u5173\u3002\n"
       "    \u5df2\u7f13\u5b58\u4e14 K\u7ebf\u65e5\u671f\u6ca1\u53d8\u65f6\u76f4\u63a5\u590d\u7528\uff0cforce=True \u5f3a\u5236\u91cd\u7b97\u3002\n"
       "    \"\"\"\n"
       "    out = {}\n"
       "    todo = []\n")
new = ("def get_ctrl_map(codes, force=False, cached_only=False):\n"
       "    \"\"\"\u6279\u91cf\u53d6\u63a7\u76d8\u4fe1\u606f\uff0c\u8fd4\u56de {code: info_dict \u6216 None}\u3002\n"
       "\n"
       "    codes \u53ef\u4ee5\u662f list / set\uff0c\u5185\u90e8\u53bb\u91cd\uff1b\u987a\u5e8f\u65e0\u5173\u3002\n"
       "    \u5df2\u7f13\u5b58\u4e14 K\u7ebf\u65e5\u671f\u6ca1\u53d8\u65f6\u76f4\u63a5\u590d\u7528\uff0cforce=True \u5f3a\u5236\u91cd\u7b97\u3002\n"
       "    cached_only=True \u65f6**\u7edd\u4e0d\u8ba1\u7b97**\uff0c\u53ea\u8fd4\u56de\u5df2\u6709\u7f13\u5b58\u7684\u6761\u76ee\uff08\u53ef\u5728 UI \u7ebf\u7a0b\u76f4\u63a5\u8c03\uff09\u3002\n"
       "    \"\"\"\n"
       "    out = {}\n"
       "    todo = []\n")
assert s.count(old) == 1, 'A1 锚点 %d' % s.count(old)
s = s.replace(old, new, 1)

old = ("    for c in todo:\n"
       "        info = compute_one(c)\n")
new = ("    if cached_only:\n"
       "        return out\n"
       "    for c in todo:\n"
       "        info = compute_one(c)\n")
assert s.count(old) == 1, 'A2 锚点 %d' % s.count(old)
s = s.replace(old, new, 1)

# 顺手把 docstring 里过期的取数说明与速度改正
s = s.replace("    K\u7ebf   services.band_pattern_engine._load_bars(code)          -> \u672c\u5730 kline_cache \u4f18\u5148\n",
              "    K\u7ebf   services.kline_cache_service.get_latest_kline(code, 120)  -> **\u53ea\u8bfb\u672c\u5730**\n", 1)
s = s.replace("- \u5355\u53ea\u7ea6 2~4 ms\uff08\u672c\u5730 duckdb + 130 \u6839K\u7ebf\uff09\uff0c50 \u53ea\u7ea6 0.15 s\u3002\n",
              "- \u5355\u53ea\u9996\u6b21\u7ea6 28 ms\uff08\u672c\u5730 duckdb + 120 \u6839K\u7ebf\uff09\uff0c\u540c\u4e00\u4ea4\u6613\u65e5\u5185\u7f13\u5b58\u547d\u4e2d\u51e0\u4e4e 0\u3002\n", 1)
open(PA, 'wb').write((s.replace('\n', '\r\n') if (A_CRLF and not A_LF) else s).encode('utf-8'))
print('OK A control_profile（cached_only + docstring）')

# ==================== B. ui/battle_widgets/base.py（纯 LF）====================
PB = r'D:\QuantMonitorV6\ui\battle_widgets\base.py'
raw = open(PB, 'rb').read()
B_CRLF, B_LF = raw.count(b'\r\n'), raw.count(b'\n') - raw.count(b'\r\n')
shutil.copy2(PB, PB + '.bak_before_cached')
s = raw.decode('utf-8')
if B_CRLF and not B_LF:
    s = s.replace('\r\n', '\n')

H = 4 * ' '
cached_fn = (
    "def fetch_ctrl_cached(rows, code_key='code', info_key='ctrl'):\n"
    '    """\u53ea\u7528**\u5df2\u6709\u7f13\u5b58**\u7ed9\u884c\u6570\u636e\u6302\u63a7\u76d8\u5ea6\uff0c\u7edd\u4e0d\u8ba1\u7b97\u3001\u7edd\u4e0d\u963b\u585e\u3002\n'
    "\n"
    "    \u7528\u4e8e\u6e32\u67d3\u524d\u7684\u201c\u7acb\u5373\u586b\u4e00\u4e0b\u201d\uff1a\u884c\u5bf9\u8c61\u5e38\u5728\u6e32\u67d3\u524d\u88ab\u91cd\u65b0\u88c5\u914d\n"
    "    \uff08\u5feb\u7167\u6062\u590d / \u6301\u4e45\u5316\u5408\u5e76 / \u521d\u59cb\u6062\u590d\uff09\uff0c\u4e0a\u4e00\u6b21\u7b97\u597d\u7684 ctrl \u4e22\u4e86\u5c31\u53d8\u2018--\u2019\u3002\n"
    "    \u8fd9\u91cc\u53ea\u8bfb\u5185\u5b58\u7f13\u5b58\uff0c\u6240\u4ee5\u53ef\u4ee5\u5728 UI \u7ebf\u7a0b\u76f4\u63a5\u8c03\uff0c\u4e0d\u5361\u3002\n"
    '    """\n'
    "    try:\n"
    "        rs = list(rows or [])\n"
    "        codes = []\n"
    "        for r in rs:\n"
    "            if isinstance(r, dict) and r.get(info_key) is None:\n"
    "                c = r.get(code_key)\n"
    "                if c:\n"
    "                    codes.append(str(c))\n"
    "        if not codes:\n"
    "            return rows\n"
    "        from services.control_profile import get_ctrl_map\n"
    "        m = get_ctrl_map(codes, cached_only=True)\n"
    "        for r in rs:\n"
    "            if isinstance(r, dict) and r.get(info_key) is None and r.get(code_key):\n"
    "                v = m.get(str(r[code_key]))\n"
    "                if v is not None:\n"
    "                    r[info_key] = v\n"
    "    except Exception:\n"
    "        pass\n"
    "    return rows\n"
    "\n"
    "\n"
)
anchor = "def attach_ctrl(table, rows, info_key='ctrl', col=None):\n"
assert s.count(anchor) == 1, 'B1 锚点 %d' % s.count(anchor)
s = s.replace(anchor, cached_fn + anchor, 1)

method = (
    H + "def ctrl_fill_and_async(self, rows, on_done=None):\n"
    + H + '    """\u63a7\u76d8\u5ea6\u6807\u51c6\u5165\u53e3\uff1a\u5148\u7528\u7f13\u5b58\u7acb\u5373\u586b\uff08\u4e0d\u5361\uff09\uff0c\u518d\u540e\u53f0\u8865\u7b97\u7f3a\u7684\u3002\n'
    "\n"
    + H + "    \u7528\u5728\u6e32\u67d3\u524d\u7684\u884c\u88c5\u914d\u70b9\uff08\u5feb\u7167\u6062\u590d\u3001\u6301\u4e45\u5316\u5408\u5e76\u3001\u521d\u59cb\u6062\u590d\u7b49\uff09\uff0c\n"
    + H + '    \u907f\u514d\u884c\u5bf9\u8c61\u88ab\u91cd\u5efa\u540e\u63a7\u76d8\u5217\u53d8\u6210\u4e00\u7247 "--"\u3002\n'
    + H + '    """\n'
    + H + "    try:\n"
    + H + "        fetch_ctrl_cached(rows)\n"
    + H + "    except Exception:\n"
    + H + "        pass\n"
    + H + "    self.ctrl_async_fill(rows, on_done)\n"
    "\n"
    "\n"
)
anchor2 = H + "def ctrl_async_fill(self, rows, on_done=None):\n"
assert s.count(anchor2) == 1, 'B2 锚点 %d' % s.count(anchor2)
s = s.replace(anchor2, method + anchor2, 1)
open(PB, 'wb').write((s.replace('\n', '\r\n') if (B_CRLF and not B_LF) else s).encode('utf-8'))
print('OK B base（fetch_ctrl_cached + ctrl_fill_and_async）')
