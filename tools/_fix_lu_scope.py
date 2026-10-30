# -*- coding: utf-8 -*-
r"""
修复 4.1~4.5：全项目「判涨停 / 追高」阈值按板性（主板 10cm vs 创业板·科创板 20cm）。

  4.1 services\picks_tracking_service.py      可介入回填 LIMIT_UP_PCT=9.5 误剔创业板
  4.2 ui\market_sentiment_panel.py            板性分支写反，elif 永不执行
  4.3 ui\echarts_kline.py                      K线涨停标记色写死 9.8
  4.4 ui\watchlist_panel.py                    自选小K线涨停配色写死 9.8
  4.5 services\intraday_opportunity_engine.py  追高提示文案写死 5%/3%

约定：读二进制核验行尾/BOM -> 归一化到 \n 匹配 -> 断言锚点唯一 -> 回写原行尾/BOM
      -> py_compile。每个文件先 shutil.copy2 备份。已打过补丁的文件自动跳过，可重复运行。
"""
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"D:\QuantMonitorV6" + "\\"
BAK = ".bak_before_cyb_lu2"


def read_file(rel):
    p = ROOT + rel
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig" if bom else "utf-8")
    return {"path": p, "rel": rel, "raw": raw, "text": text, "crlf": crlf, "lf": lf, "bom": bom,
            "eol": "\r\n" if crlf > lf else "\n"}


def norm(F):
    """归一化到 \n 用于匹配；返回 (匹配用文本, 是否本来就是 LF)"""
    t = F["text"].replace("\r\n", "\n")
    assert "\r" not in t, "文件里有孤立 \\r，需要人工确认"
    return t


def denorm(F, t):
    assert "\r" not in t
    return t if F["eol"] == "\n" else t.replace("\n", "\r\n")


def sub(s, old, new, want=1, tag=""):
    n = s.count(old)
    assert n == want, "[%s] 锚点命中 %d 次（期望 %d）：%r" % (tag, n, want, old[:80])
    return s.replace(old, new, want)


def resub(s, pat, repl_fn, want=1, tag=""):
    ms = list(re.finditer(pat, s, re.M))
    assert len(ms) == want, "[%s] 正则命中 %d 次（期望 %d）：%s" % (tag, len(ms), want, pat[:80])
    return re.sub(pat, repl_fn, s, count=want, flags=re.M)


def commit(F, t, tag):
    full = denorm(F, t)
    assert full != F["text"], "[%s] 内容没有任何变化" % tag
    shutil.copy2(F["path"], F["path"] + BAK)
    open(F["path"], "wb").write((b"\xef\xbb\xbf" if F["bom"] else b"") + full.encode("utf-8"))
    back = read_file(F["rel"])
    c2 = back["raw"].count(b"\r\n")
    l2 = back["raw"].count(b"\n") - c2
    assert (c2 > l2) == (F["crlf"] > F["lf"]), "[%s] 行尾风格变了" % tag
    assert back["bom"] == F["bom"], "[%s] BOM 变了" % tag
    import py_compile
    py_compile.compile(F["path"], doraise=True)
    print("  √ %-44s 行尾 %-4s  语法OK  备份 *%s" % (
        F["rel"], "CRLF" if c2 > l2 else "LF", BAK))


def skip(F, marker):
    if marker in F["text"]:
        print("  · %-44s 已含标记 %r，跳过" % (F["rel"], marker))
        return True
    return False


DONE = []

# ==========================================================================
print("=" * 78)
print("4.2  ui\\market_sentiment_panel.py —— 涨停/跌停/炸板按板性（修 elif 永不执行）")
print("=" * 78)
F = read_file(r"ui\market_sentiment_panel.py")
if not skip(F, "def limit_pct(code):"):
    assert F["lf"] == 0, "期望纯 CRLF，实测 LF=%d" % F["lf"]
    s = norm(F)

    s = sub(s,
            'def log_error(error):\n    """记录错误日志"""',
            "# 板性前缀：主板 10cm；创业板 300/301 与科创板 688/689 是 20cm。\n"
            "# 原先把涨停/跌停/炸板统一按 9.8% 判：前缀 '0' 会把创业板、'6' 会把\n"
            "# 科创板一起吞进主板分支，20cm 那条 elif 永远执行不到 —— 家数全错。\n"
            "PLUS_PREFIXES = ('300', '301', '688', '689')\n"
            "\n"
            "\n"
            "def limit_pct(code):\n"
            "    \"\"\"按板性返回涨停幅度阈值（%）：主板 9.8，创业板/科创板 19.8。\"\"\"\n"
            "    return 19.8 if str(code or '').startswith(PLUS_PREFIXES) else 9.8\n"
            "\n"
            "\n"
            'def log_error(error):\n    """记录错误日志"""',
            tag="4.2-a 新增 limit_pct")

    lines = s.split("\n")
    i0 = next(i for i, t in enumerate(lines) if "涨停判断（主板9.8%以上" in t)
    i1 = next(i for i, t in enumerate(lines) if "broken_count += 1" in t)
    old_block = "\n".join(lines[i0:i1 + 1])
    ind = len(lines[i0]) - len(lines[i0].lstrip())
    assert ind >= 12, "缩进异常 ind=%d" % ind
    assert lines[i0 + 2].strip().startswith("if code.startswith('6')"), \
        "i0+2 不是预期板性分支：%r" % lines[i0 + 2]
    assert old_block.count("is_limit_up") == 3, "is_limit_up 出现 %d 次" % old_block.count("is_limit_up")

    P = " " * ind
    new_block = "\n".join([
        P + "# 涨停判断（按板性：主板 9.8%，创业板/科创板 19.8%）",
        P + "_lp = limit_pct(code)",
        P + "is_limit_up = False",
        P + "if pct_chg >= _lp:",
        P + "    limit_up_count += 1",
        P + "    is_limit_up = True",
        "",
        P + "# 跌停判断（同样按板性）",
        P + "if pct_chg <= -_lp:",
        P + "    limit_down_count += 1",
        "",
        P + "# 炸板判断（简化：涨幅在涨停线的 70%~100% 之间且有量）",
        P + "# 主板 7%~9.8%，创业板/科创板 14%~19.8%",
        P + "_brk_lo = 14.0 if _lp > 10 else 7.0",
        P + "if _brk_lo <= pct_chg < _lp and volume > 0:",
        P + "    broken_count += 1",
    ])
    s = sub(s, old_block, new_block, tag="4.2-b 替换涨停/跌停/炸板")

    assert "code.startswith('6') or code.startswith('0')" not in s, "板性前缀残留"
    assert s.count("_lp = limit_pct(code)") == 1, "调用点异常"
    assert len(re.findall(r"limit_pct\(", s)) == 2, "limit_pct( 出现 %d 次（应=定义1+调用1）" % len(re.findall(r"limit_pct\(", s))
    commit(F, s, "4.2")
    DONE.append("4.2")


# ==========================================================================
print("=" * 78)
print("4.3  ui\\echarts_kline.py —— K线涨停/跌停标记色按板性")
print("=" * 78)
F = read_file(r"ui\echarts_kline.py")
if not skip(F, "window.__limitPct"):
    assert F["lf"] == 0, "期望纯 CRLF，实测 LF=%d" % F["lf"]
    s = norm(F)

    s = sub(s,
            "var isLimitUp = (close === high) && (pct >= 9.8);",
            "// 涨停阈值按板性：主板 10cm -> 9.8；创业板/科创板 20cm -> 19.8。\n"
            "                    // set_kline_data 会在调用 updateKline 之前设置 window.__limitPct。\n"
            "                    var luPct = (typeof window.__limitPct === 'number' && window.__limitPct > 0) ? window.__limitPct : 9.8;\n"
            "                    var isLimitUp = (close === high) && (pct >= luPct);",
            tag="4.3-a JS 涨停线")
    s = sub(s,
            "var isLimitDown = (close === low) && (pct <= -9.8);",
            "var isLimitDown = (close === low) && (pct <= -luPct);",
            tag="4.3-b JS 跌停线")

    lines = s.split("\n")
    i_js = next(i for i, t in enumerate(lines) if 'js_code = f"""' in t and "updateKline" in lines[i + 7])
    ind_js = len(lines[i_js]) - len(lines[i_js].lstrip())
    assert 4 <= ind_js <= 12, "js_code 缩进异常 %d" % ind_js
    P = " " * ind_js
    s = sub(s,
            "                    var result = updateKline(",
            P + "# [CYB-GATE] 涨停阈值按板性：创业板/科创板 20cm -> 19.8，其余 9.8\n"
            + P + "_lu_pct = 19.8 if str(kline_data.get('code', '') or '').startswith(\n"
            + P + "    ('300', '301', '688', '689')) else 9.8\n"
            + P + "window.__limitPct = {_lu_pct};\n"
            + P + "var result = updateKline(",
            tag="4.3-c 注入 __limitPct")
    assert "window.__limitPct = {_lu_pct};" in s
    commit(F, s, "4.3")
    DONE.append("4.3")


# ==========================================================================
print("=" * 78)
print("4.4  ui\\watchlist_panel.py —— 自选小K线涨停/跌停配色按板性")
print("=" * 78)
F = read_file(r"ui\watchlist_panel.py")
if not skip(F, "self.code.startswith"):
    assert F["lf"] == 0, "期望纯 CRLF，实测 LF=%d" % F["lf"]
    s = norm(F)

    s = sub(s,
            "        self.kline_data = None\n        self.ma5 = None",
            "        self.kline_data = None\n"
            "        self.code = ''          # [CYB-GATE] 按板性判涨停色用\n"
            "        self.ma5 = None",
            tag="4.4-a __init__ 加 code")

    s = sub(s,
            "    def set_kline_data(self, kline_data):\n"
            '        """设置K线数据"""',
            "    def set_kline_data(self, kline_data, code=''):\n"
            '        """设置K线数据（code 用于按板性判涨停配色）"""\n'
            "        self.code = str(code or '')\n",
            tag="4.4-b set_kline_data 收 code")

    s = resub(s,
              r"^(\s*)# 绘制K线\n\1for i in range\(count\):$",
              lambda m: (m.group(1) + "# 绘制K线\n"
                         + m.group(1) + "# [CYB-GATE] 涨停阈值按板性：创业板/科创板 20cm -> 19.8\n"
                         + m.group(1) + "_lu_pct = 19.8 if self.code.startswith(('300', '301', '688', '689')) else 9.8\n"
                         + m.group(1) + "for i in range(count):"),
              tag="4.4-c paintEvent 预算阈值")

    s = sub(s,
            "is_limit_up = (close_p == high_p) and (pct >= 9.8)",
            "is_limit_up = (close_p == high_p) and (pct >= _lu_pct)",
            tag="4.4-d 涨停配色")
    s = sub(s,
            "is_limit_down = (close_p == low_p) and (pct <= -9.8)",
            "is_limit_down = (close_p == low_p) and (pct <= -_lu_pct)",
            tag="4.4-e 跌停配色")
    s = sub(s,
            "self.kline_chart.set_kline_data(kline)",
            "self.kline_chart.set_kline_data(kline, code)",
            tag="4.4-f 调用方补 code")
    commit(F, s, "4.4")
    DONE.append("4.4")


# ==========================================================================
print("=" * 78)
print("4.5  services\\intraday_opportunity_engine.py —— 追高提示文案按板性")
print("=" * 78)
F = read_file(r"services\intraday_opportunity_engine.py")
if not skip(F, "_chase_hi"):
    assert F["crlf"] == 0, "期望纯 LF，实测 CRLF=%d" % F["crlf"]
    s = norm(F)

    s = resub(s,
              r"^(\s*)if pct is not None and pct >= 5:$",
              lambda m: (m.group(1) + "# [CYB-GATE] 追高提示阈值按板性等比放大（涨停幅度比 2.0）：\n"
                         + m.group(1) + "# 主板 5% / 3%  ->  创业板 10% / 6%\n"
                         + m.group(1) + "_chase_hi = 10.0 if str(code or '').startswith(('300', '301')) else 5.0\n"
                         + m.group(1) + "_chase_mid = 6.0 if str(code or '').startswith(('300', '301')) else 3.0\n"
                         + m.group(1) + "if pct is not None and pct >= _chase_hi:"),
              tag="4.5-a 追高上限")

    s = resub(s,
              r"^(\s*)elif pct is not None and pct >= 3:$",
              lambda m: m.group(1) + "elif pct is not None and pct >= _chase_mid:",
              tag="4.5-b 追高中限")
    commit(F, s, "4.5")
    DONE.append("4.5")

print()
print("=" * 78)
print("本轮写入完成的文件：%s" % (", ".join(DONE) if DONE else "（无，均已是最新）"))
print("4.1 在上一轮已写入（services\\picks_tracking_service.py）")
print("=" * 78)
