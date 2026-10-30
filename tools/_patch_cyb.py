# -*- coding: utf-8 -*-
import io, sys, shutil, py_compile
sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6\\"

JOBS = [
 # (文件, [(旧, 新), ...])
 (r"services\band_pattern_engine.py", [
  ("""def _is_main_a_share(code):
    return code.startswith(('600','601','603','605','000','001','002','003'))""",
   """def _is_main_a_share(code):
    # 2026-10-10：用户可买创业板，放行 300/301。
    # 科创板(688/689) / 北交所(8xx/4xx/920) 仍剔除。
    return code.startswith(('600','601','603','605','000','001','002','003',
                            '300','301'))"""),
  ("""        # 基础过滤【前置】：只保留主板（600/601/603/605/000/001/002/003），剔除 ST/退市。
        # 这一步不依赖K线，必须在 _load_bars 之前 —— 全市场 5221 只里有 2000+ 只
        # 是创业板/科创板/北交所，原先"先取数再过滤"等于每只都白跑一次在线请求""",
   """        # 基础过滤【前置】：保留主板 + 创业板（600/601/603/605/000/001/002/003/300/301），
        # 剔除 ST/退市/科创板/北交所。
        # 这一步不依赖K线，必须在 _load_bars 之前 —— 全市场 5221 只里有 1000+ 只
        # 是科创板/北交所，原先"先取数再过滤"等于每只都白跑一次在线请求"""),
 ]),
 (r"ui\battle_widgets\auction_filter_widget.py", [
  ("""# 只保留沪深主板：沪市 600/601/603/605，深市 000/001/002/003
# 剔除创业板(300)、科创板(688)、北交所(8/4/9开头)
MAIN_BOARD_PREFIXES = ('600', '601', '603', '605', '000', '001', '002', '003')""",
   """# 主板 + 创业板：沪市 600/601/603/605，深市 000/001/002/003，创业板 300/301
# 剔除科创板(688)、北交所(8/4/9开头)
MAIN_BOARD_PREFIXES = ('600', '601', '603', '605', '000', '001', '002', '003',
                       '300', '301')"""),
  ('''    """只保留沪深A股主板，剔除创业板/科创板/北交所"""''',
   '''    """保留沪深A股主板 + 创业板，剔除科创板/北交所"""'''),
 ]),
 (r"services\intraday_opportunity_engine.py", [
  ("""# 主板代码前缀
MAIN_PREFIX = ('600', '601', '603', '605', '000', '001', '002', '003')""",
   """# 主板 + 创业板代码前缀（2026-10-10 放行 300/301，用户可买创业板）
MAIN_PREFIX = ('600', '601', '603', '605', '000', '001', '002', '003',
               '300', '301')"""),
 ]),
 (r"services\market_rhythm_engine.py", [
  ("""def is_main_board(code):
    \"\"\"只统计主板（沪 600/601/603/605 + 深 000/001/002/003）

    原因：创业板/科创板/北交所是 20cm/30cm，混进来会让板块「均涨幅」
    失真（实测涨停股均涨幅算出 15%）。而且用户口径一直是只看主板。
    \"\"\"
    return str(code or '')[:3] in ('600', '601', '603', '605',
                                   '000', '001', '002', '003')""",
   """def is_main_board(code):
    \"\"\"统计主板 + 创业板（沪 600/601/603/605 + 深 000/001/002/003 + 创 300/301）

    2026-10-10：用户可买创业板，放行 300/301。科创板(688)/北交所(8xx/4xx/920)
    仍剔除 —— 30cm 混进来失真更严重。
    注意：创业板是 20cm，放进来后本模块「均涨幅」列会比纯主板时偏高
    （涨停股口径下纯主板约 10%，混合后约 15%），看该列时按此理解。
    \"\"\"
    return str(code or '')[:3] in ('600', '601', '603', '605',
                                   '000', '001', '002', '003',
                                   '300', '301')"""),
 ]),
]

for rel, pairs in JOBS:
    P = ROOT + rel
    raw = open(P, "rb").read()
    crlf = raw.count(b"\r\n"); lf = raw.count(b"\n") - crlf
    if crlf and not lf:
        eol, name = "\r\n", "CRLF"
    elif lf and not crlf:
        eol, name = "\n", "LF"
    else:
        print("!! %s 行尾混合 CRLF=%d LF=%d，跳过" % (rel, crlf, lf)); continue
    shutil.copy2(P, P + ".bak_before_cyb")
    s = raw.decode("utf-8").replace("\r\n", "\n")
    okall = True
    for old, new in pairs:
        old = old.replace("\r\n", "\n"); new = new.replace("\r\n", "\n")
        n = s.count(old)
        if n != 1:
            print("!! %s 锚点命中 %d 次，跳过该处" % (rel, n)); okall = False; continue
        s = s.replace(old, new, 1)
    if not okall:
        print("!! %s 有锚点未命中，未写回" % rel); continue
    out = s.replace("\n", eol) if eol == "\r\n" else s
    io.open(P, "w", encoding="utf-8", newline="").write(out)
    r2 = open(P, "rb").read()
    c2, l2 = r2.count(b"\r\n"), r2.count(b"\n") - r2.count(b"\r\n")
    try:
        py_compile.compile(P, doraise=True); comp = "OK"
    except Exception as e:
        comp = "FAIL %s" % e
    print("OK %-46s 行尾 %s->CRLF=%d/LF=%d  编译=%s" % (rel, name, c2, l2, comp))
