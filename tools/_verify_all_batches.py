# -*- coding: utf-8 -*-
"""三批改动总验收：真实 import 冒烟 + 残留复查 + AGENTS.md 行尾。"""
import io
import importlib
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

N_OK = N_BAD = 0


def chk(c, m):
    global N_OK, N_BAD
    if c:
        N_OK += 1
        print("  √ %s" % m)
    else:
        N_BAD += 1
        print("  X %s" % m)


print("=" * 78)
print("一、真实 import 冒烟（改了 + 相关的模块能不能 import）")
print("=" * 78)
for mod in ["utils.indicators",
            "services.daily_close_summary_service",
            "services.picks_tracking_service",
            "services.v22_combat_service",
            "services.intraday_opportunity_engine",
            "services.band_pattern_engine",
            "ui.echarts_kline",
            "ui.market_sentiment_panel"]:
    try:
        importlib.import_module(mod)
        chk(True, "import %s 成功" % mod)
    except Exception as e:
        chk(False, "import %s 失败：%s: %s" % (mod, type(e).__name__, str(e)[:110]))

print()
print("=" * 78)
print("二、三批改动点的源码断言（在磁盘上真实成立）")
print("=" * 78)
ASSERT = [
    (r"services\picks_tracking_service.py", "pct >= _lu_pct(code)", "4.1 使用点"),
    (r"ui\market_sentiment_panel.py", "_lp = limit_pct(code)", "4.2 使用点"),
    (r"ui\echarts_kline.py", "window.__limitPct = {_lu_pct}", "4.3 Python 注入"),
    (r"ui\watchlist_panel.py", "def set_kline_data(self, kline_data, code='')", "4.4 签名"),
    (r"services\intraday_opportunity_engine.py", "_chase_hi = ", "4.5 追高阈值"),
    (r"ui\battle_console_v2.py", "pct >= _lu_pct(code)", "10.1 接近涨停"),
    (r"services\v22_combat_service.py", ">= _lu_pct(x.get('code'))", "10.2 v22"),
    (r"services\daily_close_summary_service.py", ">= _lu_pct(x.get('code'))", "10.3 收盘总结"),
    (r"utils\indicators.py", ">= _lu_pct(code)", "10.4 indicators"),
    (r"services\band_pattern_engine.py", "_lu_threshold", "上一批 日K建仓截面"),
]
for rel, needle, label in ASSERT:
    s = io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read()
    chk(needle in s, "%s ｜ %s" % (label, needle))

print()
print("=" * 78)
print("三、全项目残留复查（只看这 9 个文件的写死 10cm）")
print("=" * 78)
CHECK = [r"ui\battle_console_v2.py", r"services\v22_combat_service.py",
         r"services\daily_close_summary_service.py", r"utils\indicators.py",
         r"services\picks_tracking_service.py", r"ui\market_sentiment_panel.py",
         r"services\intraday_opportunity_engine.py"]
for rel in CHECK:
    s = io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read()
    hits = []
    for t in s.split("\n"):
        ts = t.strip()
        if ts.startswith("#") or re.match(r"^LIMIT_UP_PCT\s*=", ts):
            continue                      # 注释行 / 主板基准常量定义不算「使用点」
        if re.search(r">= *9\.5\b|<= *-9\.5\b", ts):
            hits.append(ts[:88])
    chk(not hits, "%s 已无写死的 >= 9.5 / <= -9.5 使用点（残留 %d）" % (rel, len(hits)))
    for h in hits:
        print("      ! %s" % h)

# LIMIT_UP_PCT 现在是 _lu_pct 内部的主板基准，必须是活常量
s = io.open(os.path.join(ROOT, r"services\picks_tracking_service.py"), encoding="utf-8-sig").read()
chk("LIMIT_UP_PCT = 9.5" in s and "return LIMIT_UP_PCT" in s,
    "LIMIT_UP_PCT 仍被 _lu_pct 作主板基准返回（活常量，外部工具 _check_rhythm_doc.py 还在断言它=9.5）")

print()
print("=" * 78)
print("四、AGENTS.md 行尾")
print("=" * 78)
raw = open(os.path.join(ROOT, "AGENTS.md"), "rb").read()
crlf = raw.count(b"\r\n")
lf = raw.count(b"\n") - crlf
chk(crlf == 0, "AGENTS.md 仍是纯 LF（CRLF=%d, LF=%d）" % (crlf, lf))

print()
print("=" * 78)
print("五、第四批：回填 SQL 已放开创业板 + 库里真的有了创业板样本")
print("=" * 78)
s = io.open(os.path.join(ROOT, r"services\picks_tracking_service.py"), encoding="utf-8-sig").read()
chk("OR code LIKE '30%'" in s, "回填取数 SQL 已含 30%（创业板）")
chk("if not code.startswith(('60', '00', '30')):" in s, "当日引擎路径的板性过滤同样是 60/00/30（两条路一致）")
chk("code LIKE '688%'" not in s and "code LIKE '8%'" not in s, "科创板与北交所仍被排除（未误放开）")
try:
    import duckdb
    db = os.path.join(ROOT, "data", "cache", "picks_tracking.duckdb")
    con = duckdb.connect(db, read_only=True)
    tot = con.execute("SELECT COUNT(*) FROM picks_tracking").fetchone()[0]
    cyb = con.execute("SELECT COUNT(*) FROM picks_tracking WHERE code LIKE '30%'").fetchone()[0]
    mb = con.execute(
        "SELECT COUNT(*) FROM picks_tracking WHERE code LIKE '60%' OR code LIKE '00%'").fetchone()[0]
    con.close()
    chk(cyb > 0, "picks_tracking 里有创业板样本 %d 条（改前为 0）" % cyb)
    chk(mb > 0, "主板样本仍在 %d 条" % mb)
    print("      总 %d 行 = 主板 %d + 创业板 %d" % (tot, mb, cyb))
except Exception as e:
    chk(False, "读 picks_tracking.duckdb 失败：%s" % e)

print()
print("=" * 78)
print("结果：通过 %d 项，失败 %d 项" % (N_OK, N_BAD))
print("=" * 78)
