# -*- coding: utf-8 -*-
"""竞价模块：给创业板做单独门槛。

原理：主板 10cm、创业板 20cm，涨停幅度比 = 2.0。
竞价现在这套门槛是按主板调的，直接套到创业板会有两个后果：
  1) 高开 7% 的天花板把创业板最强的高开信号全砍掉（创业板开盘能到 +20%）；
  2) 打分里「最优高开 3~4%」对创业板偏低，真正强的 6~8% 只给 8 分。
所以按 2 倍等比缩放，两侧口径才可比：
  高开区间      主板 2~7%      → 创业板 4~14%
  换手上限      主板 15%       → 创业板 30%
  高开分满分    主板 3~4%      → 创业板 6~8%
  高开分次优    主板 2~3/4~5%  → 创业板 4~6/8~10%
  形态标签      gap 3/2/2.5    → 创业板 6/4/5
主板口径完全不变。
"""
import io
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\ui\battle_widgets\auction_filter_widget.py"

raw = open(P, "rb").read()
crlf, lf = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
assert crlf and not lf, "该文件应为纯 CRLF，实测 CRLF=%d LF=%d" % (crlf, lf)
shutil.copy2(P, P + ".bak_before_cyb_gate")
s = raw.decode("utf-8").replace("\r\n", "\n")
orig = s

# ---------- 1) 模块级：板性判定 + 三组门槛 ----------
old = """def _is_st(name: str) -> bool:
    nm = (name or '').upper()
    return ('ST' in nm) or ('退' in nm)
"""
new = """def _is_st(name: str) -> bool:
    nm = (name or '').upper()
    return ('ST' in nm) or ('退' in nm)


# [CYB-GATE] 创业板是 20cm 板，主板是 10cm 板，涨停幅度比 = 2.0。
# 竞价的「高开幅度」「换手上限」「最优高开区间」按这个比例等比缩放，两侧口径才可比。
#   高开区间   主板 2~7%     → 创业板 4~14%
#   换手上限   主板 15%      → 创业板 30%（下限 0.5% 不变，那是"有没有人交易"）
#   高开分满分 主板 3~4%     → 创业板 6~8%
CYB_PREFIXES = ('300', '301')
GAP_BAND_MAIN = (2.0, 7.0)
GAP_BAND_CYB = (4.0, 14.0)
TURNOVER_MAX_MAIN = 15.0
TURNOVER_MAX_CYB = 30.0
GAP_SCORE_MAIN = (3.0, 4.0, 2.0, 5.0)    # 满分下限/上限、次优下限/上限
GAP_SCORE_CYB = (6.0, 8.0, 4.0, 10.0)


def _is_cyb(code) -> bool:
    \"\"\"是否创业板（20cm 板）\"\"\"
    return str(code or '').startswith(CYB_PREFIXES)


def _gap_band(code):
    \"\"\"按板性返回允许的高开幅度区间 (下限, 上限)，单位 %\"\"\"
    return GAP_BAND_CYB if _is_cyb(code) else GAP_BAND_MAIN


def _turnover_max(code) -> float:
    \"\"\"按板性返回集合竞价换手率上限，单位 %\"\"\"
    return TURNOVER_MAX_CYB if _is_cyb(code) else TURNOVER_MAX_MAIN


def _gap_score_bands(code):
    \"\"\"按板性返回高开分区间 (满分下限, 满分上限, 次优下限, 次优上限)\"\"\"
    return GAP_SCORE_CYB if _is_cyb(code) else GAP_SCORE_MAIN
"""
assert s.count(old) == 1, "锚点1( _is_st ) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

# ---------- 2) 新浪路径闸门 ----------
old = """            if gap > 7.0 or gap < 2.0:
                continue
            if fun is not None:
                fun['gap'] += 1
            if jj_turnover < 0.5 or jj_turnover > 15:
                continue"""
new = """            _glo, _ghi = _gap_band(code)          # [CYB-GATE] 创业板 4~14%
            if gap > _ghi or gap < _glo:
                continue
            if fun is not None:
                fun['gap'] += 1
            _tmax = _turnover_max(code)            # [CYB-GATE] 创业板 30%
            if jj_turnover < 0.5 or jj_turnover > _tmax:
                continue"""
assert s.count(old) == 1, "锚点2(新浪闸门) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

# ---------- 3) 腾讯兜底路径闸门 ----------
old = """            if gap > 7.0 or gap < 2.0:
                continue
            fun['gap'] += 1
            if jj_turnover < 0.5 or jj_turnover > 15:
                continue
            fun['turn'] += 1"""
new = """            _glo, _ghi = _gap_band(code)          # [CYB-GATE] 创业板 4~14%
            if gap > _ghi or gap < _glo:
                continue
            fun['gap'] += 1
            _tmax = _turnover_max(code)            # [CYB-GATE] 创业板 30%
            if jj_turnover < 0.5 or jj_turnover > _tmax:
                continue
            fun['turn'] += 1"""
assert s.count(old) == 1, "锚点3(腾讯闸门) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

# ---------- 4) 高开幅度分：满分区间按板性 ----------
old = """        gap = r['gap']

        # --- 高开幅度分 (20) ---
        if 3.0 <= gap <= 4.0:
            gap_score = 20
        elif (2.0 <= gap < 3.0) or (4.0 < gap <= 5.0):
            gap_score = 15
        else:  # 5~7%
            gap_score = 8"""
new = """        gap = r['gap']
        # [CYB-GATE] 创业板 20cm：最优高开区间按 2 倍缩放（主板 3~4% → 创业板 6~8%）
        _cyb = _is_cyb(r.get('code'))
        _o1, _o2, _s1, _s2 = _gap_score_bands(r.get('code'))

        # --- 高开幅度分 (20) ---
        if _o1 <= gap <= _o2:
            gap_score = 20
        elif (_s1 <= gap < _o1) or (_o2 < gap <= _s2):
            gap_score = 15
        else:
            gap_score = 8"""
assert s.count(old) == 1, "锚点4(高开分) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

# ---------- 5) 分时形态标签：按板性 ----------
old = """        # --- 分时形态分 (15) + 标签（无逐笔tick时用高开+量比作代理）---
        if gap >= 3 and vol_ratio >= 5:
            shape_score = 15
            shape = '红柱递增'
        elif gap >= 2 and vol_ratio >= 2:
            shape_score = 10
            shape = '价格攀升'
        elif gap < 2.5:
            shape_score = 0
            shape = '绿柱扩大'"""
new = """        # --- 分时形态分 (15) + 标签（无逐笔tick时用高开+量比作代理）---
        # [CYB-GATE] 创业板 20cm：高开阈值按 2 倍缩放（主板 3/2/2.5 → 创业板 6/4/5）
        _sh, _sl, _sf = (6.0, 4.0, 5.0) if _cyb else (3.0, 2.0, 2.5)
        if gap >= _sh and vol_ratio >= 5:
            shape_score = 15
            shape = '红柱递增'
        elif gap >= _sl and vol_ratio >= 2:
            shape_score = 10
            shape = '价格攀升'
        elif gap < _sf:
            shape_score = 0
            shape = '绿柱扩大'"""
assert s.count(old) == 1, "锚点5(形态标签) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

assert s != orig, "没有任何替换生效"
io.open(P, "w", encoding="utf-8", newline="").write(s.replace("\n", "\r\n"))

r2 = open(P, "rb").read()
print("OK 已写入 %s" % P)
print("   行数 %d（原 %d）｜行尾 CRLF=%d 裸LF=%d（应保持纯 CRLF）"
      % (r2.decode("utf-8").count("\n") + 1, raw.decode("utf-8").count("\n") + 1,
         r2.count(b"\r\n"), r2.count(b"\n") - r2.count(b"\r\n")))
