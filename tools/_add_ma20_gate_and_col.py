# -*- coding: utf-8 -*-
"""
1) 堵住 MA20 门槛唯一能绕过的洞（当日可介入路径）
   改前：m20 = ma20.get(code); if m20: ...   -> 取不到 MA20 直接放行（次新股会漏进来）
   改后：MA20 整表加载成功时按硬门槛执行；该票没有 MA20（K线不足20根）也剔除
        整表为空（kline_cache 被占用/加载失败）时仍不过滤，避免把候选全清空

2) fetch_tracking 带出 ma20，供追踪表显示「距MA20%」

3) 追踪表新增「距MA20%」列（插在「当前价」后面）

三个文件的行尾：board_anomaly_engine.py / picks_tracking_service.py 纯 LF，
picks_track_widget.py 纯 CRLF（写回必须还原 CRLF）。
幂等：已打过会跳过。
"""
import io
import os
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
TAG = "bak_before_ma20gate"


def read_text(rel):
    p = os.path.join(ROOT, rel)
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "\r\n" if (crlf and not lf) else "\n"
    return p, raw, raw.decode("utf-8-sig"), eol


def write_text(p, text, eol, orig_raw):
    bom = orig_raw[:3] == b"\xef\xbb\xbf"
    data = text.replace("\r\n", "\n").replace("\n", eol).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    with open(p, "wb") as f:
        f.write(data)


def backup(p):
    b = p + "." + TAG
    if not os.path.exists(b):
        shutil.copy2(p, b)
        print("   备份 -> %s" % os.path.basename(b))
    return b


def verify(p, eol):
    py_compile.compile(p, doraise=True)
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    got = "\r\n" if (crlf and not lf) else ("LF" if lf and not crlf else "MIXED")
    want = "CRLF" if eol == "\r\n" else "LF"
    assert got == want, "行尾被改坏：%s（期望 %s，实际 %s）" % (p, want, got)
    print("   py_compile OK ｜ 行尾仍是纯 %s" % got)


# ===================================================================
# 1) board_anomaly_engine.py —— 堵 MA20 的洞
# ===================================================================
print("=" * 90)
print("1) services\\board_anomaly_engine.py")
p, raw, s, eol = read_text(r"services\board_anomaly_engine.py")

NEW1 = """        # ---- 用户硬门槛：现价必须 >= MA20（等于或大于）----
        # ma20 整表加载成功（非空）时按硬门槛执行：
        #   · 在均线上（等于也算过）        -> 通过，并记录距 MA20 涨幅
        #   · 跌破均线                     -> 剔除
        #   · 表里没有它（K线不足 20 根）   -> 无法确认站上均线，剔除
        # 整表为空（kline_cache 被占用/加载失败）时不做过滤，
        # 避免把候选一次性全清空（_load_ma20 的既定兜底）。
        gap = None
        m20 = ma20.get(code) if ma20 else None
        if ma20:
            if (not m20) or px < m20:
                continue
            gap = round((px - m20) / m20 * 100.0, 2)   # 距MA20 涨幅%"""

lines = s.split("\n")
hits = [i for i, l in enumerate(lines) if l.strip() == "gap = None"]
if any("m20 = ma20.get(code) if ma20 else None" in l for l in lines):
    print("   已改过（幂等跳过）")
else:
    assert len(hits) == 1, "gap = None 出现 %d 次，不敢动" % len(hits)
    i = hits[0]
    blk = [l.strip() for l in lines[i:i + 6]]
    assert blk[1] == "m20 = ma20.get(code)", blk
    assert blk[2] == "if m20:", blk
    assert blk[3].startswith("if px < m20:"), blk
    assert blk[4] == "continue", blk
    assert blk[5].startswith("gap = round((px - m20)"), blk
    backup(p)
    lines[i:i + 6] = NEW1.split("\n")
    write_text(p, "\n".join(lines), eol, raw)
    verify(p, eol)

# ===================================================================
# 2) picks_tracking_service.py —— fetch_tracking 带出 ma20
# ===================================================================
print()
print("=" * 90)
print("2) services\\picks_tracking_service.py")
p2, raw2, s2, eol2 = read_text(r"services\picks_tracking_service.py")

if "'ma20': ma20," in s2:
    print("   已改过（幂等跳过）")
else:
    a_old = """        out.append({
            'trade_date': td,"""
    a_new = """        # 距 MA20：本地 K 线最近 20 个收盘均值（不足 20 根给 None，界面显示 --）
        ma20 = None
        _cl = [b[1] for b in bars[-20:] if b[1] and b[1] > 0]
        if len(_cl) >= 20:
            ma20 = sum(_cl) / 20.0

        out.append({
            'trade_date': td,"""
    b_old = "            'cur_price': cur,\n"
    b_new = "            'cur_price': cur,\n            'ma20': ma20,\n"
    assert s2.count(a_old) == 1, "锚点A命中 %d 次" % s2.count(a_old)
    assert s2.count(b_old) == 1, "锚点B命中 %d 次" % s2.count(b_old)
    backup(p2)
    s2 = s2.replace(a_old, a_new, 1).replace(b_old, b_new, 1)
    write_text(p2, s2, eol2, raw2)
    verify(p2, eol2)

# ===================================================================
# 3) picks_track_widget.py —— 新增「距MA20%」列（CRLF）
# ===================================================================
print()
print("=" * 90)
print("3) ui\\battle_widgets\\picks_track_widget.py")
p3, raw3, s3, eol3 = read_text(r"ui\battle_widgets\picks_track_widget.py")
print("   原行尾：%s" % ("CRLF" if eol3 == "\r\n" else "LF"))
s3n = s3.replace("\r\n", "\n")          # 多行锚点先归一化

if "T_M20" in s3n:
    print("   已改过（幂等跳过）")
else:
    pairs = []

    pairs.append((
        """TRACK_HEADERS = ['筛选日期', '股票名称', '股票代码', '板块', '入选价',
                 '当前价', '5日盈亏%', '30日盈亏%', '累计盈亏%',
                 CTRL_COL_TITLE]
TRACK_COL_N = 10
(T_DATE, T_NAME, T_CODE, T_BOARD, T_P0,
 T_NOW, T_R5, T_R30, T_CUM, T_CTRL) = range(TRACK_COL_N)
TRACK_WIDTHS = [92, 84, 74, 116, 74, 74, 82, 84, 84, 78]""",
        """TRACK_HEADERS = ['筛选日期', '股票名称', '股票代码', '板块', '入选价',
                 '当前价', '距MA20%', '5日盈亏%', '30日盈亏%', '累计盈亏%',
                 CTRL_COL_TITLE]
TRACK_COL_N = 11
(T_DATE, T_NAME, T_CODE, T_BOARD, T_P0,
 T_NOW, T_M20, T_R5, T_R30, T_CUM, T_CTRL) = range(TRACK_COL_N)
TRACK_WIDTHS = [92, 84, 74, 116, 74, 74, 76, 82, 84, 84, 78]"""))

    pairs.append((
        """                  T_P0: lambda r: r['base_price'],
""",
        """                  T_P0: lambda r: r['base_price'],
                  T_M20: lambda r: (((r['cur_price'] - r['ma20']) / r['ma20'] * 100.0)
                                    if (r.get('ma20') and r.get('cur_price')) else -1e9),
"""))

    pairs.append((
        """            _cur = r['cur_price']
            set_table_item(self.table, row, T_NOW,
                           f'{_cur:.2f}' if _cur > 0 else '--',
                           BC.TEXT, align=right)
""",
        """            _cur = r['cur_price']
            set_table_item(self.table, row, T_NOW,
                           f'{_cur:.2f}' if _cur > 0 else '--',
                           BC.TEXT, align=right)
            # 距 MA20%：入选时它就是硬门槛，这里做成可见列便于验收
            _m20 = r.get('ma20')
            if _m20 and _cur > 0:
                _g20 = (_cur - _m20) / _m20 * 100.0
                set_table_item(self.table, row, T_M20, f'{_g20:+.2f}%',
                               _UP if _g20 >= 0 else _DN, align=right)
            else:
                set_table_item(self.table, row, T_M20, '--',
                               BC.TEXT3, align=right)
"""))

    pairs.append((
        """                    f"口径：非涨停 ｜ 涨幅1~9% ｜ 量比≥1.2 ｜ 价≥6元 ｜ "
""",
        """                    f"距MA20：{r['ma20'] and ('%.2f' % r['ma20']) or '--'}"
                    f"（现价{'在' if (r.get('ma20') and r['cur_price'] >= r['ma20']) else '不在'}"
                    f"均线上）\\n"
                    f"口径：非涨停 ｜ 涨幅1~9% ｜ 量比≥1.2 ｜ 价≥6元 ｜ "
"""))

    pairs.append((
        """            it = self.table.item(row, T_NOW)
            if it is not None:
                it.setText(f'{px:.2f}')
""",
        """            it = self.table.item(row, T_NOW)
            if it is not None:
                it.setText(f'{px:.2f}')
            # 距 MA20% 跟着实时价一起刷新（MA20 当日不变）
            ig = self.table.item(row, T_M20)
            if ig is not None:
                _m20r = r.get('ma20')
                if _m20r and _m20r > 0:
                    _g20r = (px - _m20r) / _m20r * 100.0
                    ig.setText(f'{_g20r:+.2f}%')
                    ig.setForeground(QColor(_UP if _g20r >= 0 else _DN))
                else:
                    ig.setText('--')
"""))

    for k, (o, n) in enumerate(pairs, 1):
        c = s3n.count(o)
        assert c == 1, "第 %d 个锚点命中 %d 次" % (k, c)
    backup(p3)
    for o, n in pairs:
        s3n = s3n.replace(o, n, 1)
    write_text(p3, s3n, eol3, raw3)
    verify(p3, eol3)

print()
print("=" * 90)
print("全部完成。回退：")
print('  copy /Y "<file>.%s" "<file>"' % TAG)
