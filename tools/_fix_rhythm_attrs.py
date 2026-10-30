# -*- coding: utf-8 -*-
"""市场节奏：① 属性词（国资/半年报增长…）不再当题材显示，直接剔除；
              ② 去掉题材条数上限（题材记忆 series 的 [:12]、控制台 [:20]）。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\services\market_rhythm_engine.py'
BAK = P + '.bak_before_attrs'

sys.stdout.reconfigure(encoding='utf-8')
shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '应为纯 LF'
s = raw.decode('utf-8')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# ---- 1) 新增子串关键词表（覆盖 半年增长 / 中报增长 / 国资入主 这类变体）----
rep(
    "    '低价股', '小盘股', '高股息', '破净', '重组预期',\n}\n",
    "    '低价股', '小盘股', '高股息', '破净', '重组预期',\n"
    "}\n"
    "\n"
    "# 子串级属性词：只要题材名里含这些片段，就不是炒作题材。\n"
    "# 用来兜住 ATTRIBUTE_WORDS 覆盖不到的变体（如「半年增长」「上海国资」「中报预增」）。\n"
    "ATTRIBUTE_KW = (\n"
    "    '国资', '央企', '国企', '股份划转',\n"
    "    '业绩', '增长', '预增', '预盈', '扭亏', '净利', '营收',\n"
    "    '年报', '半年报', '半年', '中报', '季报', '报表',\n"
    "    '重组', '并购', '股权转让', '股权激励', '摘帽', '退市风险',\n"
    "    '高送转', '分红', '回购', '增持', '解禁', '员工持股',\n"
    "    '次新', '超跌', '低价股', '小盘股', '高股息', '破净',\n"
    "    '中标', '订单', '专利', '机构调研', '牛散',\n"
    ")\n",
    'A1 ATTRIBUTE_KW')

# ---- 2) _is_attribute 加子串判定 ----
rep(
    "def _is_attribute(word):\n"
    "    if word in ATTRIBUTE_WORDS:\n"
    "        return True\n"
    "    for w in ATTRIBUTE_WORDS:\n"
    "        if w in word and len(word) <= len(w) + 2:\n"
    "            return True\n"
    "    return False\n",
    "def _is_attribute(word):\n"
    "    \"\"\"属性词（财务/股权/交易属性）不是炒作题材。\n"
    "\n"
    "    V17：命中即从板块表里整条剔除，不再只是「降权沉底」——\n"
    "    用户口径：国资 / 半年增长这类不该占题材位。\n"
    "    \"\"\"\n"
    "    w = str(word or '')\n"
    "    if w in ATTRIBUTE_WORDS:\n"
    "        return True\n"
    "    for a in ATTRIBUTE_WORDS:\n"
    "        if a in w and len(w) <= len(a) + 2:\n"
    "            return True\n"
    "    for kw in ATTRIBUTE_KW:\n"
    "        if kw in w:\n"
    "            return True\n"
    "    return False\n",
    'A2 _is_attribute')

# ---- 3) 板块表：属性词不进表 ----
rep(
    "    for theme, members in day_theme[today].items():\n"
    "        n_today = len(members)\n"
    "        if n_today < MIN_STOCK:\n"
    "            continue\n",
    "    for theme, members in day_theme[today].items():\n"
    "        n_today = len(members)\n"
    "        if n_today < MIN_STOCK:\n"
    "            continue\n"
    "        # V17：属性词（国资/半年报增长/股权转让…）不当题材，整条不显示\n"
    "        if _is_attribute(theme):\n"
    "            continue\n",
    'A3 板块表剔除属性词')

# ---- 4) 轮动三张表也剔除属性词 ----
rep("                     if v >= MIN_STOCK and p_all.get(k, 0) < MIN_STOCK],",
    "                     if v >= MIN_STOCK and p_all.get(k, 0) < MIN_STOCK\n"
    "                     and not _is_attribute(k)],",
    'A4 new_in')
rep("                   if v >= MIN_STOCK and t_all.get(k, 0) < MIN_STOCK],",
    "                   if v >= MIN_STOCK and t_all.get(k, 0) < MIN_STOCK\n"
    "                   and not _is_attribute(k)],",
    'A5 fade')
rep("                   if v >= 2 and t_all.get(k, 0) == 0],",
    "                   if v >= 2 and t_all.get(k, 0) == 0\n"
    "                   and not _is_attribute(k)],",
    'A6 dead')

# ---- 5) 去掉条数上限：题材记忆 series ----
rep("    top_themes = [b['theme'] for b in boards if not b['is_attribute']][:12]",
    "    # V17：不再截断，能出多少题材就出多少\n"
    "    top_themes = [b['theme'] for b in boards]",
    'A7 series 上限')

# ---- 6) 控制台打印不再截断 ----
rep("    for i, b in enumerate(d['boards'][:20], 1):",
    "    for i, b in enumerate(d['boards'], 1):",
    'A8 控制台上限')

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  市场节奏：属性词剔除 + 去掉条数上限')
print('  备份:', BAK)
