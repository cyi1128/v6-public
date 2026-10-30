# -*- coding: utf-8 -*-
"""
第三批（明细文档 9.1）板性修复的独立验证。
不复用补丁脚本的结论：全部从磁盘重读 + 真实 import / exec 真实代码行。
"""
import io
import os
import py_compile
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

N_OK = 0
N_BAD = 0


def chk(cond, msg):
    global N_OK, N_BAD
    if cond:
        N_OK += 1
        print("  √ %s" % msg)
    else:
        N_BAD += 1
        print("  X %s" % msg)
    return bool(cond)


def read_n(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read().replace("\r\n", "\n")


FILES = [r"ui\battle_console_v2.py",
         r"services\v22_combat_service.py",
         r"services\daily_close_summary_service.py",
         r"utils\indicators.py"]

print("=" * 78)
print("一、行尾 / BOM / 编译")
print("=" * 78)
for rel in FILES:
    raw = open(os.path.join(ROOT, rel), "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    chk(crlf > lf, "%s 仍是纯 CRLF（CRLF=%d, LF=%d）" % (rel, crlf, lf))
    chk(not raw.startswith(b"\xef\xbb\xbf"), "%s 无 BOM" % rel)
    try:
        py_compile.compile(os.path.join(ROOT, rel), doraise=True)
        chk(True, "%s py_compile 通过" % rel)
    except Exception as e:
        chk(False, "%s py_compile 失败：%s" % (rel, e))

print()
print("=" * 78)
print("二、_lu_pct 定义存在且只定义一次 + 写死阈值已消失")
print("=" * 78)
for rel in FILES:
    s = read_n(rel)
    chk(s.count("def _lu_pct(") == 1, "%s 中 def _lu_pct( 恰好 1 次" % rel)
for rel in FILES[:3]:
    s = read_n(rel)
    bad = re.findall(r">= 9\.5\b|<= -9\.5\b", s)
    chk(not bad, "%s 已无写死的 9.5 / -9.5 判定（残留 %d 处）" % (rel, len(bad)))
    chk(s.count("_lu_pct(") >= 2, "%s 使用点存在（%d 次）" % (rel, s.count("_lu_pct(")))
s = read_n(FILES[3])
chk(s.count("_lu_pct(code)") == 2, "utils\\indicators.py 两个函数都用了 _lu_pct(code)")
chk("code=None" in s, "utils\\indicators.py 新参数带默认值 code=None（向后兼容）")

print()
print("=" * 78)
print("三、_lu_pct 真实取值（从磁盘抠出源码 exec，不抄结论）")
print("=" * 78)


def grab_helper(rel):
    s = read_n(rel)
    m = re.search(r"(def _lu_pct\(.*?\n(?:.*?\n)*?    return (?:9\.5|base)\n)", s)
    if not m:
        return None
    ns = {}
    exec(compile(m.group(1), rel, "exec"), ns)
    return ns["_lu_pct"]


CASES = [("600000", 9.5), ("000001", 9.5), ("002594", 9.5), ("601398", 9.5),
         ("300001", 19.5), ("301001", 19.5), ("688001", 19.5), ("689009", 19.5),
         ("830799", 29.5), ("920001", 29.5), ("", 9.5), (None, 9.5)]
for rel in FILES[:3]:
    f = grab_helper(rel)
    if not chk(f is not None, "%s 抠取 _lu_pct 源码成功" % rel):
        continue
    allok = True
    for code, exp in CASES:
        got = f(code)
        if abs(got - exp) > 1e-9:
            allok = False
            print("      ! %s 期望 %s 实际 %s" % (code, exp, got))
    chk(allok, "%s 的 _lu_pct 12 组取值全对" % rel)

print()
print("=" * 78)
print("四、utils\\indicators.py 真实 import + 函数行为（向后兼容 = 关键）")
print("=" * 78)
from utils.indicators import calc_limit_up_count, is_yesterday_limit_up   # noqa: E402

PCTS = [12.0, 19.6, 20.0, 8.0]
chk(calc_limit_up_count([10] * 4, PCTS) == 3,
    "不传 code：旧口径 9.8 → 数到 12.0 / 19.6 / 20.0（3 次），行为未变")
chk(calc_limit_up_count([10] * 4, PCTS, code="300111") == 1,
    "传 300111：19.8 口径 → 只数到 20.0（1 次），12.0 与 19.6 都不算")
chk(calc_limit_up_count([10] * 4, PCTS, code="600111") == 3, "传 600111：9.8 口径 → 仍 3 次")
chk(calc_limit_up_count([10] * 4, PCTS, code="830799") == 0,
    "传 830799：29.8 口径 → 0 次（12.0 / 19.6 / 20.0 都不算北交所涨停）")
chk(calc_limit_up_count([10] * 4, PCTS, code=None) == calc_limit_up_count([10] * 4, PCTS),
    "code=None 与不传参结果相同（向后兼容）")
chk(bool(is_yesterday_limit_up([12.0, 1.0])) is True,
    "is_yesterday_limit_up 不传 code：前一日 12.0 算涨停（旧口径）")
chk(bool(is_yesterday_limit_up([12.0, 1.0], code="300111")) is False,
    "传 300111：前一日 12.0 不算涨停")
chk(bool(is_yesterday_limit_up([20.0, 1.0], code="300111")) is True,
    "传 300111：前一日 20.0 算涨停")

print()
print("=" * 78)
print("五、真实代码行在合成样本上执行（把磁盘那一行原样抠出来跑）")
print("=" * 78)


def grab_line(rel, needle):
    for t in read_n(rel).split("\n"):
        if needle in t:
            return t.strip()
    return None


# 5.1 daily_close_summary_service：昨日涨停股筛选用
ln = grab_line(r"services\daily_close_summary_service.py", "yesterday_limit = [x for x in prev")
chk(ln is not None, "抠到 yesterday_limit 那一行")
if ln:
    fn = grab_helper(r"services\daily_close_summary_service.py")
    prev = [{"code": "300111", "pct_chg": 12.0},     # 创业板 +12%：旧口径误判为涨停
            {"code": "300111", "pct_chg": 19.6},     # 创业板真涨停
            {"code": "600111", "pct_chg": 12.0},     # 主板真涨停
            {"code": "600000", "pct_chg": 9.6},      # 主板涨停
            {"code": "300111", "pct_chg": 8.0}]      # 创业板 +8%
    ns = {"prev": prev, "_lu_pct": fn}
    exec(compile(ln, "daily", "exec"), ns)
    got = [x["pct_chg"] for x in ns["yesterday_limit"]]
    old = [x["pct_chg"] for x in prev if x["pct_chg"] >= 9.5]
    chk(got == [19.6, 12.0, 9.6], "按板性结果 = [19.6, 12.0, 9.6]（创业板 +12% 已排除）")
    chk(len(old) == 4, "旧口径会得到 4 只（含误判的创业板 +12pct）→ 口径确实变了：%s" % old)

# 5.2 v22：涨停家数
ln2 = grab_line(r"services\v22_combat_service.py", "limit_up = sum(x['pct'] >= _lu_pct")
chk(ln2 is not None, "抠到 v22 limit_up 那一行")
if ln2:
    fn2 = grab_helper(r"services\v22_combat_service.py")
    quotes = [{"code": "600000", "pct": 10.0}, {"code": "300111", "pct": 12.0},
              {"code": "300111", "pct": 19.6}, {"code": "601398", "pct": 4.0}]
    ns = {"quotes": quotes, "_lu_pct": fn2}
    exec(compile(ln2, "v22", "exec"), ns)
    chk(ns["limit_up"] == 2, "v22 涨停家数按板性 = 2（600000 + 300111@19.6），旧口径会是 3")

# 5.3 v22：板块内涨停数
ln3 = grab_line(r"services\v22_combat_service.py", "limit_up_count = sum(1 for s in sector_stocks")
chk(ln3 is not None, "抠到 v22 板块 limit_up_count 那一行")
if ln3:
    fn3 = grab_helper(r"services\v22_combat_service.py")
    sector_stocks = [{"code": "300001", "pct_chg": 12.0}, {"code": "300001", "pct_chg": 20.0},
                     {"code": "600001", "pct_chg": 12.0}, {"code": "600001", "pct_chg": 3.0}]
    ns = {"sector_stocks": sector_stocks, "_lu_pct": fn3}
    exec(compile(ln3, "v22s", "exec"), ns)
    chk(ns["limit_up_count"] == 2, "板块涨停数按板性 = 2（300001@20.0 与 600001@12.0）")

# 5.4 battle_console_v2：接近涨停提示
ln4 = grab_line(r"ui\battle_console_v2.py", "if pct >= _lu_pct(code)")
chk(ln4 is not None, "抠到主界面「接近涨停」判断那一行")
if ln4:
    fn4 = grab_helper(r"ui\battle_console_v2.py")

    def fire(code, pct):
        ns = {"code": code, "pct": pct, "_lu_pct": fn4}
        exec(compile(ln4, "bc", "exec"), ns)
        return bool(ns.get("_hit"))
    # 用带标记的方式跑：把原行包一层
    def fire2(code, pct):
        ns = {"code": code, "pct": pct, "_lu_pct": fn4, "_hit": False}
        code_src = ln4 + "\n    _hit = True"
        ind = len(ln4) - len(ln4.lstrip())
        body = ln4.replace(ln4.strip(), ln4.strip()) + "\n" + " " * (ind + 4) + "_hit = True"
        exec(compile(body, "bc2", "exec"), ns)
        return bool(ns["_hit"])
    chk(fire2("600000", 9.6) is True, "主板 +9.6% → 提示接近涨停")
    chk(fire2("600000", 8.0) is False, "主板 +8.0% → 不提示")
    chk(fire2("300111", 9.6) is False, "创业板 +9.6% → 不再误报（改前会报）")
    chk(fire2("300111", 19.6) is True, "创业板 +19.6% → 提示接近涨停")

print()
print("=" * 78)
print("六、兼容性红线：code 缺失时必须退回旧行为")
print("=" * 78)
for rel in FILES[:3]:
    f = grab_helper(rel)
    chk(abs(f(None) - 9.5) < 1e-9 and abs(f("") - 9.5) < 1e-9,
        "%s：code 为空 → 返回 9.5（与改前一致，不会因字典缺 code 而变形）" % rel)
chk(calc_limit_up_count([10] * 5, PCTS, code=None) == calc_limit_up_count([10] * 5, PCTS),
    "utils\\indicators.py：code=None 与不传参结果相同")

print()
print("=" * 78)
print("结果：通过 %d 项，失败 %d 项" % (N_OK, N_BAD))
print("=" * 78)
