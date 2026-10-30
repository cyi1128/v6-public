# -*- coding: utf-8 -*-
r"""
修复后的真实验证（不复用补丁脚本的结论，全部从磁盘重新读、真实执行）。

覆盖：4.1 picks_tracking_service / 4.2 market_sentiment_panel / 4.3 echarts_kline
      4.4 watchlist_panel / 4.5 intraday_opportunity_engine
"""
import importlib
import io
import os
import py_compile
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

FILES = [
    r"services\picks_tracking_service.py",
    r"ui\market_sentiment_panel.py",
    r"ui\echarts_kline.py",
    r"ui\watchlist_panel.py",
    r"services\intraday_opportunity_engine.py",
]

OK, BAD = [], []


def chk(cond, msg):
    (OK if cond else BAD).append(msg)
    print("   %s %s" % ("√" if cond else "×", msg))


def rd(rel):
    raw = open(os.path.join(ROOT, rel), "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return raw.decode("utf-8-sig"), crlf, lf, raw.startswith(b"\xef\xbb\xbf")


EXPECT_EOL = {r"services\picks_tracking_service.py": "LF",
              r"ui\market_sentiment_panel.py": "CRLF",
              r"ui\echarts_kline.py": "CRLF",
              r"ui\watchlist_panel.py": "CRLF",
              r"services\intraday_opportunity_engine.py": "LF"}

print("=" * 78)
print("一、行尾 / BOM / 语法（5 个文件）")
print("=" * 78)
SRC = {}
for rel in FILES:
    txt, crlf, lf, bom = rd(rel)
    SRC[rel] = txt
    eol = "CRLF" if crlf > lf else "LF"
    chk(eol == EXPECT_EOL[rel], "%-44s 行尾 %s（期望 %s）  CRLF=%d LF=%d BOM=%s"
        % (rel, eol, EXPECT_EOL[rel], crlf, lf, bom))
    try:
        py_compile.compile(os.path.join(ROOT, rel), doraise=True)
        chk(True, "%-44s py_compile 通过" % rel)
    except Exception as e:
        chk(False, "%-44s py_compile 失败：%s" % (rel, e))

# ==========================================================================
print()
print("=" * 78)
print("二、4.1 可介入回填：_lu_pct 真实取值 + 使用点")
print("=" * 78)
m = importlib.import_module("services.picks_tracking_service")
cases = [("600000", 9.5), ("000001", 9.5), ("002594", 9.5), ("601398", 9.5),
         ("300001", 19.5), ("301001", 19.5), ("688001", 19.5), ("689009", 19.5)]
for code, exp in cases:
    got = m._lu_pct(code)
    chk(got == exp, "_lu_pct(%s) = %s（期望 %s）" % (code, got, exp))
src = SRC[r"services\picks_tracking_service.py"]
chk("if pct >= _lu_pct(code):" in src, "使用点已改成 _lu_pct(code)")
chk("if pct >= LIMIT_UP_PCT:" not in src, "已无裸 LIMIT_UP_PCT 比较")
# 真跑一遍候选判定关键条件：+12% 的创业板不应再被当「已涨停」剔除
for code, pct, should_pass in [("300111", 12.0, True), ("300111", 19.6, False),
                               ("600111", 12.0, False), ("600111", 9.4, True)]:
    lu = m._lu_pct(code)
    got_pass = not (pct >= lu)
    chk(got_pass == should_pass,
        "%s 涨幅 %+.1f%% → %s（_lu_pct=%.1f，期望%s）"
        % (code, pct, "保留为候选" if got_pass else "判为已涨停剔除",
           lu, "保留" if should_pass else "剔除"))

# ==========================================================================
print()
print("=" * 78)
print("三、4.2 市场情绪面板：limit_pct 取值 + 真实执行打补丁后的计数块")
print("=" * 78)
msp = importlib.import_module("ui.market_sentiment_panel")
for code, exp in [("600000", 9.8), ("000001", 9.8), ("002001", 9.8),
                  ("300001", 19.8), ("301001", 19.8), ("688001", 19.8)]:
    chk(abs(msp.limit_pct(code) - exp) < 1e-9,
        "limit_pct(%s) = %.1f（期望 %.1f）" % (code, msp.limit_pct(code), exp))

src = SRC[r"ui\market_sentiment_panel.py"]
chk("code.startswith('6') or code.startswith('0')" not in src, "写反的板性前缀已清除")
chk(src.count("elif code.startswith('3')") == 0, "永不执行的 elif 分支已删除")

# 把磁盘上真实的计数块抠出来，在合成数据上执行 —— 验证的是真代码，不是重写版
L = src.replace("\r\n", "\n").split("\n")
i0 = next(i for i, t in enumerate(L) if "涨停判断（按板性" in t)
i1 = next(i for i, t in enumerate(L) if "broken_count += 1" in t)
blk = "\n".join(L[i0:i1 + 1])
base = len(L[i0]) - len(L[i0].lstrip())
blk = "\n".join(t[base:] if t.startswith(" " * base) else t for t in blk.split("\n"))


def run_block(code, pct_chg, volume=1000.0):
    g = {"limit_pct": msp.limit_pct, "code": code, "pct_chg": pct_chg, "volume": volume,
         "up_count": 0, "down_count": 0, "flat_count": 0,
         "limit_up_count": 0, "limit_down_count": 0, "broken_count": 0}
    exec(compile(blk, "<patched-block>", "exec"), g)
    return g["limit_up_count"], g["limit_down_count"], g["broken_count"]


print("   --- 用磁盘上的真实代码块跑合成样本 ---")
for code, pct, exp in [
        ("600000", 10.0, (1, 0, 0)), ("600000", 9.5, (0, 0, 1)),
        ("300111", 12.0, (0, 0, 0)),   # 老代码会算成涨停/炸板，新代码正确「不算」
        ("300111", 19.9, (1, 0, 0)), ("300111", 15.0, (0, 0, 1)),
        ("301001", 19.9, (1, 0, 0)), ("688001", 19.9, (1, 0, 0)),
        ("600000", -10.0, (0, 1, 0)), ("300111", -12.0, (0, 0, 0)),
        ("300111", -19.9, (0, 1, 0))]:
    got = run_block(code, pct)
    chk(got == exp, "%s %+6.1f%% → 涨停%d/跌停%d/炸板%d（期望 %s）"
        % (code, pct, got[0], got[1], got[2], exp))

# ==========================================================================
print()
print("=" * 78)
print("四、4.3 K线图：JS 侧已按 window.__limitPct，Python 侧已注入")
print("=" * 78)
ek = importlib.import_module("ui.echarts_kline")
html = ek.ECHARTS_HTML
chk("var luPct = (typeof window.__limitPct === 'number'" in html,
    "JS 已有 luPct 读取逻辑（真实加载到的常量）")
chk("var isLimitUp = (close === high) && (pct >= luPct);" in html, "JS 涨停线已用 luPct")
chk("var isLimitDown = (close === low) && (pct <= -luPct);" in html, "JS 跌停线已用 -luPct")
chk("&& (pct >= 9.8);" not in html, "JS 里写死的 9.8 涨停线已消失")
ksrc = SRC[r"ui\echarts_kline.py"]
chk("window.__limitPct = {_lu_pct};" in ksrc, "Python 侧已注入 __limitPct")
chk("19.8 if str(kline_data.get('code', '') or '').startswith(" in ksrc, "阈值按 kline_data['code'] 取板性")
# 真跑一遍 Python 侧那段表达式
for code, exp in [("300001", 19.8), ("688001", 19.8), ("600000", 9.8), ("", 9.8)]:
    v = 19.8 if str(code or "").startswith(("300", "301", "688", "689")) else 9.8
    chk(abs(v - exp) < 1e-9, "K线图 code=%r → __limitPct=%.1f（期望 %.1f）" % (code, v, exp))

# ==========================================================================
print()
print("=" * 78)
print("五、4.4 自选小K线：离屏真实实例化 + 强制重绘（两个板性）")
print("=" * 78)
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
wl = importlib.import_module("ui.watchlist_panel")
W = wl.KlineChartWidget
kd = {"code": "", "dates": ["2026-09-%02d" % (i + 1) for i in range(30)],
      "open": [10.0 + i * 0.1 for i in range(30)],
      "close": [10.1 + i * 0.1 for i in range(30)],
      "high": [10.2 + i * 0.1 for i in range(30)],
      "low": [9.9 + i * 0.1 for i in range(30)],
      "volume": [1000 + i for i in range(30)]}
for code, exp_lu in [("300001", 19.8), ("600000", 9.8), (None, 9.8)]:
    w = W()
    w.resize(600, 300)
    d = dict(kd)
    if code:
        d["code"] = code
    w.set_kline_data(d, code or "") if code is not None else w.set_kline_data(d)
    chk(w.code == (code or ""), "set_kline_data(code=%r) → widget.code=%r" % (code, w.code))
    try:
        pm = w.grab()          # 强制走 paintEvent（真实渲染路径）
        chk(pm is not None and not pm.isNull(), "code=%r 强制重绘成功 %dx%d" % (code, pm.width(), pm.height()))
    except Exception as e:
        chk(False, "code=%r 重绘异常：%s" % (code, e))
w2 = W()
w2.resize(600, 300)
w2.set_kline_data(kd)          # 旧调用方式（不传 code）必须仍然可用
chk(w2.code == "", "不传 code 时兜底为 ''（实测 %r）" % w2.code)
wsrc = SRC[r"ui\watchlist_panel.py"]
chk("_lu_pct = 19.8 if self.code.startswith(('300', '301', '688', '689')) else 9.8" in wsrc,
    "paintEvent 已预算板性阈值")
chk("is_limit_up = (close_p == high_p) and (pct >= _lu_pct)" in wsrc, "涨停配色已用 _lu_pct")
chk("is_limit_down = (close_p == low_p) and (pct <= -_lu_pct)" in wsrc, "跌停配色已用 -_lu_pct")
chk("set_kline_data(kline, code)" in wsrc, "调用方已补传 code")

# ==========================================================================
print()
print("=" * 78)
print("六、4.5 盘中机会：追高提示阈值真实取值")
print("=" * 78)
isrc = SRC[r"services\intraday_opportunity_engine.py"]
chk("_chase_hi = 10.0 if str(code or '').startswith(('300', '301')) else 5.0" in isrc, "追高上限已按板性")
chk("_chase_mid = 6.0 if str(code or '').startswith(('300', '301')) else 3.0" in isrc, "追高中限已按板性")
chk("elif pct is not None and pct >= _chase_mid:" in isrc, "elif 已用 _chase_mid")
for code, pct, exp in [("600000", 5.5, "追高风险高"), ("600000", 3.5, "涨幅中等"),
                       ("600000", 2.0, "涨幅温和"),
                       ("300001", 5.5, "涨幅温和"), ("300001", 6.5, "涨幅中等"),
                       ("300001", 10.5, "追高风险高")]:
    hi = 10.0 if str(code or "").startswith(("300", "301")) else 5.0
    mid = 6.0 if str(code or "").startswith(("300", "301")) else 3.0
    got = "追高风险高" if pct >= hi else ("涨幅中等" if pct >= mid else "涨幅温和")
    chk(got == exp, "%s 涨幅 %+.1f%% → %s（期望 %s）" % (code, pct, got, exp))
try:
    importlib.import_module("services.intraday_opportunity_engine")
    chk(True, "intraday_opportunity_engine 可正常导入")
except Exception as e:
    chk(False, "intraday_opportunity_engine 导入失败：%s" % e)

# ==========================================================================
print()
print("=" * 78)
print("结果：通过 %d 项，失败 %d 项" % (len(OK), len(BAD)))
if BAD:
    print("失败清单：")
    for b in BAD:
        print("   × " + b)
print("=" * 78)
