# -*- coding: utf-8 -*-
"""把「写死 9.x% 的涨停统计」按板性分流。

主板 10cm → 9.5 / 9.8 阈值；创业板 20cm → 19.5 / 19.8（等比 2 倍）。
涉及：
  services\\band_pattern_engine.py   涨停家数统计（喂环境分/题材因子）—— 影响选股
  ui\\watchlist_panel.py            近20日涨停次数（自选评分列）
  ui\\trading_dashboard_panel.py    仪表盘涨停/跌停家数
  services\\intraday_opportunity_engine.py  过期注释
"""
import io
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"


def patch(rel, pairs, add_before=None):
    p = os.path.join(ROOT, rel)
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "MIXED")
    shutil.copy2(p, p + ".bak_before_cyb_lu")
    nl = "\r\n" if eol == "CRLF" else "\n"
    s = raw.decode("utf-8-sig").replace("\r\n", "\n")
    n0 = len(s)
    if add_before:
        old, new = add_before
        assert s.count(old) == 1, "%s 插入锚点命中 %d 次" % (rel, s.count(old))
        s = s.replace(old, new, 1)
    for old, new in pairs:
        c = s.count(old)
        assert c == 1, "%s 锚点命中 %d 次：%s" % (rel, c, old.strip()[:60])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace("\n", nl))
    r2 = open(p, "rb").read()
    print("   OK %-46s [%s] %d→%d 行" % (rel, eol, n0, len(s)))


# ============ 1) 日K建仓引擎（影响选股）============
print("=== 1. services\\band_pattern_engine.py ===")
patch(
    r"services\band_pattern_engine.py",
    [
        # 行业涨停家数
        ("""                'limitup': sum(1 for x in ps if x >= 9.5),""",
         """                'limitup': sum(1 for c, x in ps if x >= _lu_threshold(c)),"""),
        # 行业聚合改成带 code 的元组
        ("""        for code, p in pcts.items():
            agg.setdefault(ind_map.get(code, '未知'), []).append(p)""",
         """        for code, p in pcts.items():
            agg.setdefault(ind_map.get(code, '未知'), []).append((code, p))"""),
        ("""                'avg': sum(ps) / len(ps),""",
         """                'avg': sum(x for _c, x in ps) / len(ps),"""),
        ("""                'up_ratio': sum(1 for x in ps if x > 0) / len(ps) * 100,""",
         """                'up_ratio': sum(1 for _c, x in ps if x > 0) / len(ps) * 100,"""),
        # 大盘涨停家数
        ("""        allp = list(pcts.values())
        ctx.update(ready=True, ind_map=ind_map, ind_stat=ind_stat,
                   market={'avg': sum(allp) / len(allp),
                           'up_ratio': sum(1 for x in allp if x > 0) / len(allp) * 100,
                           'limitup': sum(1 for x in allp if x >= 9.5),
                           'date': d_now})""",
         """        allp = list(pcts.items())
        ctx.update(ready=True, ind_map=ind_map, ind_stat=ind_stat,
                   market={'avg': sum(x for _c, x in allp) / len(allp),
                           'up_ratio': sum(1 for _c, x in allp if x > 0) / len(allp) * 100,
                           'limitup': sum(1 for c, x in allp if x >= _lu_threshold(c)),
                           'date': d_now})"""),
        # 死代码的 docstring 更正（该函数全项目无调用）
        ('''def _is_limit_up(b, prev_close, threshold=0.098):
    """涨停：相对前收盘涨幅 >= 9.8%（主板 10%，留 0.2% 容差）"""''',
         '''def _is_limit_up(b, prev_close, threshold=0.098):
    """涨停：相对前收盘涨幅 >= threshold（默认 9.8% = 主板 10% 留 0.2% 容差）。

    注意：**本函数目前全项目无任何调用**（模式一/二的基准日改用
    「实体 >=3% 且涨幅 >=3%」判定）。创业板要按 19.5% 判，传 threshold=0.195。
    """'''),
    ],
    add_before=(
        "def _is_st(name):",
        '''def _lu_threshold(code):
    """涨停判定阈值（%）：主板 9.5，创业板 19.5（均留 0.5% 容差）。

    创业板是 20cm 板，若统一用 9.5% 判，+10%~19.4% 的非涨停创业板股
    会被算成涨停，导致「行业涨停家数 / 大盘涨停家数」虚高，
    进而抬高环境分与题材因子。本函数是全项目唯一的口径来源。
    """
    return 19.5 if str(code).startswith(('300', '301')) else 9.5


def _is_st(name):'''),
)

# ============ 2) 自选面板：近20日涨停次数 ============
print()
print("=== 2. ui\\watchlist_panel.py ===")
patch(
    r"ui\watchlist_panel.py",
    [
        ("""                                pct = (recent_closes[i] - prev_close) / prev_close * 100
                                if pct >= 9.8:
                                    limit_up_count += 1""",
         """                                pct = (recent_closes[i] - prev_close) / prev_close * 100
                                # [CYB] 涨停阈值按板性：主板 9.8% / 创业板 19.8%
                                _lu_th = 19.8 if str(code).startswith(('300', '301')) else 9.8
                                if pct >= _lu_th:
                                    limit_up_count += 1"""),
    ],
)

# ============ 3) 仪表盘：先看上下文，再决定 ============
print()
print("=== 3. ui\\trading_dashboard_panel.py 上下文（尚未修改）===")
p3 = os.path.join(ROOT, r"ui\trading_dashboard_panel.py")
raw3 = open(p3, "rb").read()
print("   EOL: CRLF=%d LF=%d" % (raw3.count(b"\r\n"),
                                raw3.count(b"\n") - raw3.count(b"\r\n")))
lines3 = raw3.decode("utf-8-sig").splitlines()
for k, ln in enumerate(lines3, 1):
    if "'limit_up': sum(1 for s in stocks" in ln or "'limit_down': sum(1 for s in stocks" in ln:
        for j in range(max(0, k - 4), min(len(lines3), k + 2)):
            print("      L%d : %s" % (j + 1, lines3[j].rstrip()[:120]))
        print("      ---")

