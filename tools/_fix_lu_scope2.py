# -*- coding: utf-8 -*-
"""
第三批判涨停阈值板性化（明细文档 9.1 的 4 处线上残留）。

改法固定：
  1) 在模块顶层加一个小工具 _lu_pct(code)
       · 9.5 家族（battle_console_v2 / v22_combat_service / daily_close_summary_service）
         主板 9.5 / 创业板·科创板 19.5 / 北交所 29.5
       · 9.8 家族（utils/indicators）用 _lu_pct(code, base=9.8)，code 为空时返回 base，
         保持老调用方行为完全不变（向后兼容）
  2) 把所有写死的 9.5 / -9.5 使用点换成 _lu_pct(...)

安全措施：先 shutil.copy2 备份 → 断言命中数 → 行内替换保留原始缩进 → 按原行尾回写 → py_compile。
幂等：已打过补丁会自动跳过。
"""
import io
import os
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
BAK = "bak_before_cyb_lu3"

OK = []
FAIL = []


def read_file(rel):
    p = os.path.join(ROOT, rel)
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "\r\n" if crlf >= lf else "\n"
    txt = raw.decode("utf-8-sig")
    return {"rel": rel, "path": p, "raw": raw, "eol": eol, "text": txt,
            "text_n": txt.replace("\r\n", "\n")}


def commit(f, new_text_n, note):
    p = f["path"]
    bak = p + "." + BAK
    if not os.path.exists(bak):
        shutil.copy2(p, bak)
    out = new_text_n.replace("\n", f["eol"])
    io.open(p, "w", encoding="utf-8", newline="").write(out)
    try:
        py_compile.compile(p, doraise=True)
    except Exception as e:
        FAIL.append("%s py_compile 失败：%s" % (f["rel"], e))
        print("  X %s 编译失败，已回滚" % f["rel"])
        shutil.copy2(bak, p)
        return False
    OK.append("%s ｜ %s" % (f["rel"], note))
    print("  √ %s ｜ %s" % (f["rel"], note))
    return True


def sub_line(f, old_stripped, new_stripped, expect=1):
    """按「去缩进后完全相等」匹配整行，保留原缩进替换。"""
    lines = f["text_n"].split("\n")
    idx = [i for i, t in enumerate(lines) if t.strip() == old_stripped]
    if len(idx) != expect:
        raise AssertionError("锚点 %r 命中 %d 次（期望 %d）" % (old_stripped, len(idx), expect))
    for i in idx:
        ind = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        lines[i] = ind + new_stripped
    f["text_n"] = "\n".join(lines)
    return len(idx)


def insert_before(f, anchor, block):
    """在 anchor 行之前插入 block（多行，含末尾空行）。"""
    lines = f["text_n"].split("\n")
    idx = [i for i, t in enumerate(lines) if t.startswith(anchor)]
    if len(idx) != 1:
        raise AssertionError("插入锚点 %r 命中 %d 次" % (anchor, len(idx)))
    i = idx[0]
    lines[i:i] = block.split("\n")
    f["text_n"] = "\n".join(lines)


HELPER_95 = '''def _lu_pct(code) -> float:
    """[CYB-GATE] 按板性返回判涨停阈值（%）：主板 9.5，创业板/科创板 19.5，北交所 29.5。

    创业板 300/301 与科创板 688/689 是 20cm 板，北交所 8xx/4xx/920 是 30cm 板。
    统一按 9.5% 判会把这两类板的「涨了一半」误当成涨停。
    """
    c = str(code or '')
    if c.startswith(('300', '301', '688', '689')):
        return 19.5
    if c.startswith(('8', '4', '920')):
        return 29.5
    return 9.5

'''

HELPER_98 = '''def _lu_pct(code, base=9.8) -> float:
    """[CYB-GATE] 按板性返回判涨停阈值（%）。

    base 是本模块的历史口径（默认 9.8）。code 为空时**原样返回 base**，
    因此所有老调用方（不传 code）的行为与改动前完全一致；
    只有显式传入 code 才会按板性 +10 / +20。
    """
    c = str(code or '')
    if not c:
        return base
    if c.startswith(('300', '301', '688', '689')):
        return base + 10.0
    if c.startswith(('8', '4', '920')):
        return base + 20.0
    return base

'''


def skip_if_done(f):
    if "_lu_pct" in f["text_n"]:
        print("  - %s 已有 _lu_pct，跳过" % f["rel"])
        return True
    return False


# ───────────────────────────────── 1. 主界面风险提示
print("=" * 74)
print("1. ui\\battle_console_v2.py（纯 CRLF）")
print("=" * 74)
f = read_file(r"ui\battle_console_v2.py")
if not skip_if_done(f):
    try:
        insert_before(f, "def p_start(name):", HELPER_95)
        n = sub_line(f, "if pct >= 9.5:",
                     "if pct >= _lu_pct(code):      # [CYB-GATE] 按板性：创业板 19.5 / 北交所 29.5")
        commit(f, f["text_n"], "L3779「接近涨停」提示按板性（%d 处）" % n)
    except AssertionError as e:
        FAIL.append("battle_console_v2 锚点失败：%s" % e)
        print("  X %s" % e)

# ───────────────────────────────── 2. v22 作战服务
print()
print("=" * 74)
print("2. services\\v22_combat_service.py（纯 CRLF）")
print("=" * 74)
f = read_file(r"services\v22_combat_service.py")
if not skip_if_done(f):
    try:
        insert_before(f, "class V22CombatService:", HELPER_95)
        n = 0
        n += sub_line(f, "lu = sum(x['pct'] >= 9.5 for x in quotes)",
                      "lu = sum(x['pct'] >= _lu_pct(x.get('code')) for x in quotes)   # [CYB-GATE]")
        n += sub_line(f, "ld = sum(x['pct'] <= -9.5 for x in quotes)",
                      "ld = sum(x['pct'] <= -_lu_pct(x.get('code')) for x in quotes)  # [CYB-GATE]")
        n += sub_line(f, "limit_up = sum(x['pct'] >= 9.5 for x in quotes)",
                      "limit_up = sum(x['pct'] >= _lu_pct(x.get('code')) for x in quotes)     # [CYB-GATE]")
        n += sub_line(f, "limit_down = sum(x['pct'] <= -9.5 for x in quotes)",
                      "limit_down = sum(x['pct'] <= -_lu_pct(x.get('code')) for x in quotes)  # [CYB-GATE]")
        n += sub_line(f,
                      "limit_up_count = sum(1 for s in sector_stocks if float(s.get('pct_chg', s.get('change_pct', 0)) or 0) >= 9.5)",
                      "limit_up_count = sum(1 for s in sector_stocks if float(s.get('pct_chg', s.get('change_pct', 0)) or 0) >= _lu_pct(s.get('code')))  # [CYB-GATE]")
        commit(f, f["text_n"], "涨停/跌停家数按板性（%d 处）" % n)
    except AssertionError as e:
        FAIL.append("v22_combat_service 锚点失败：%s" % e)
        print("  X %s" % e)

# ───────────────────────────────── 3. 收盘总结
print()
print("=" * 74)
print("3. services\\daily_close_summary_service.py（纯 CRLF）")
print("=" * 74)
f = read_file(r"services\daily_close_summary_service.py")
if not skip_if_done(f):
    try:
        insert_before(f, "class DailyCloseSummaryService:", HELPER_95)
        n = 0
        n += sub_line(f, "yesterday_limit = [x for x in prev if float(x.get('pct_chg') or 0) >= 9.5]",
                      "yesterday_limit = [x for x in prev if float(x.get('pct_chg') or 0) >= _lu_pct(x.get('code'))]  # [CYB-GATE]")
        n += sub_line(f, "limit_up = sum(x['pct'] >= 9.5 for x in quotes)",
                      "limit_up = sum(x['pct'] >= _lu_pct(x.get('code')) for x in quotes)     # [CYB-GATE]")
        n += sub_line(f, "limit_down = sum(x['pct'] <= -9.5 for x in quotes)",
                      "limit_down = sum(x['pct'] <= -_lu_pct(x.get('code')) for x in quotes)  # [CYB-GATE]")
        commit(f, f["text_n"], "昨日涨停表现 + 涨跌停家数按板性（%d 处）" % n)
    except AssertionError as e:
        FAIL.append("daily_close_summary_service 锚点失败：%s" % e)
        print("  X %s" % e)

# ───────────────────────────────── 4. utils/indicators
print()
print("=" * 74)
print("4. utils\\indicators.py（纯 CRLF）—— 加可选 code 参数，向后兼容")
print("=" * 74)
f = read_file(r"utils\indicators.py")
if not skip_if_done(f):
    try:
        insert_before(f, "def calc_limit_up_count(close_prices, pct_changes, days=252):", HELPER_98)
        n = 0
        n += sub_line(f, "def calc_limit_up_count(close_prices, pct_changes, days=252):",
                      "def calc_limit_up_count(close_prices, pct_changes, days=252, code=None):")
        n += sub_line(f, "统计N日内涨停次数(涨幅>=9.8%视为涨停)",
                      "统计N日内涨停次数（按板性；code 为空时沿用旧口径 9.8%）")
        n += sub_line(f, "if pct_changes[i] >= 9.8:", "if pct_changes[i] >= _lu_pct(code):")
        n += sub_line(f, "def is_yesterday_limit_up(pct_changes):",
                      "def is_yesterday_limit_up(pct_changes, code=None):")
        n += sub_line(f, "return pct_changes[-2] >= 9.8", "return pct_changes[-2] >= _lu_pct(code)")
        commit(f, f["text_n"], "两个涨停统计函数支持按板性（%d 处）" % n)
    except AssertionError as e:
        FAIL.append("indicators 锚点失败：%s" % e)
        print("  X %s" % e)

print()
print("=" * 74)
print("成功 %d 项 / 失败 %d 项" % (len(OK), len(FAIL)))
for x in OK:
    print("  √ %s" % x)
for x in FAIL:
    print("  X %s" % x)
print("=" * 74)
