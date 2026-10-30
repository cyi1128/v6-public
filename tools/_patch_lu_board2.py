# -*- coding: utf-8 -*-
"""补丁：仪表盘涨停家数 + 异动池过期注释。"""
import io
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "MIXED")
    shutil.copy2(p, p + ".bak_before_cyb_lu")
    nl = "\r\n" if eol == "CRLF" else "\n"
    s = raw.decode("utf-8-sig").replace("\r\n", "\n")
    n0 = len(s.splitlines())
    for old, new in pairs:
        c = s.count(old)
        assert c == 1, "%s 锚点命中 %d 次：%s" % (rel, c, old.strip()[:70])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace("\n", nl))
    print("   OK %-44s [%s] %d→%d 行" % (rel, eol, n0, len(s.splitlines())))


print("=== 3. ui\\trading_dashboard_panel.py（仪表盘涨停/跌停家数）===")
patch(
    r"ui\trading_dashboard_panel.py",
    [
        ("""                    'limit_up': sum(1 for s in stocks if s.get('pct_chg', 0) >= 9.8),
                    'limit_down': sum(1 for s in stocks if s.get('pct_chg', 0) <= -9.8),""",
         """                    # [CYB] 涨停/跌停家数按板性：主板 9.8% / 创业板 19.8%
                    'limit_up': sum(1 for s in stocks
                                    if s.get('pct_chg', 0) >= (
                                        19.8 if str(s.get('code', '')).startswith(('300', '301'))
                                        else 9.8)),
                    'limit_down': sum(1 for s in stocks
                                      if s.get('pct_chg', 0) <= -(
                                          19.8 if str(s.get('code', '')).startswith(('300', '301'))
                                          else 9.8)),"""),
    ],
)

print()
print("=== 4. services\\intraday_opportunity_engine.py（过期注释）===")
patch(
    r"services\intraday_opportunity_engine.py",
    [
        ('        """拉全市场行情（只主板；剔除 6 元以下 + ST/退市）。',
         '        """拉全市场行情（主板 + 创业板 300/301；剔除低价 + ST/退市）。\n'
         '        注：科创板 688/689、北交所 8xx/4xx/920 仍剔除；低价门槛见模块常量 MIN_PRICE。'),
    ],
)
