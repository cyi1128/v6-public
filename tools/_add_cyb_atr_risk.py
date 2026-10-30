# -*- coding: utf-8 -*-
"""分时做T：把 3 处「按 10cm 写死的个股涨跌幅阈值」改成按板性。

主板 10cm / 创业板 20cm，涨停幅度比 = 2.0：
  L683 涨停锁仓（涨停的 80%）  主板 8.0%  → 创业板 16.0%
  L690 主升浪  （涨停的 50%）  主板 5.0%  → 创业板 10.0%
  L1147 弱势降分               主板 -5.0% → 创业板 -10.0%
大盘指数那两处（-1% / -2%）与板性无关，不动。
"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py"

raw = open(P, "rb").read()
crlf, lf = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
assert crlf and not lf, "该文件应为纯 CRLF，实测 CRLF=%d LF=%d" % (crlf, lf)
shutil.copy2(P, P + ".bak_before_cyb_risk")
s = raw.decode("utf-8").replace("\r\n", "\n")
orig = s

print("r 里是否带 code 键：", "'code': code" in s or '"code": code' in s)

# ---------- 0) 模块级：板性判定 + 阈值 ----------
old = "SIGNAL_BG = {"
new = """# [CYB-GATE] 创业板是 20cm 板，主板是 10cm 板，涨停幅度比 = 2.0。
# 下面这些「个股当日涨跌幅」阈值原按主板写死，创业板必须等比放大，
# 否则一只 +9% 的创业板股票（离涨停还有 11%）会被误判成「涨停锁仓、不做T」。
CYB_PREFIXES = ('300', '301')
PCT_LOCK_MAIN = 8.0        # 涨停锁仓（涨停的 80%：主板 10% → 8%）
PCT_LOCK_CYB = 16.0        # 涨停锁仓（涨停的 80%：创业板 20% → 16%）
PCT_MAINUP_MAIN = 5.0      # 主升浪（涨停的 50%：主板 10% → 5%）
PCT_MAINUP_CYB = 10.0      # 主升浪（涨停的 50%：创业板 20% → 10%）
PCT_WEAK_MAIN = -5.0       # 弱势降分
PCT_WEAK_CYB = -10.0       # 弱势降分（创业板）


def _is_cyb(code) -> bool:
    \"\"\"是否创业板（20cm 板）\"\"\"
    return str(code or '').startswith(CYB_PREFIXES)


def _pct_thresholds(code):
    \"\"\"按板性返回 (涨停锁仓线, 主升浪线, 弱势降分线)\"\"\"
    if _is_cyb(code):
        return PCT_LOCK_CYB, PCT_MAINUP_CYB, PCT_WEAK_CYB
    return PCT_LOCK_MAIN, PCT_MAINUP_MAIN, PCT_WEAK_MAIN


SIGNAL_BG = {"""
assert s.count(old) == 1, "锚点0(SIGNAL_BG) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

# ---------- 1) 风控：涨停锁仓 + 主升浪 ----------
old = """        risk_status = '正常(VWAP上方)' if price >= vwap else '正常(VWAP下方)'"""
new = """        # [CYB-GATE] 涨停锁仓线/主升浪线按板性：主板 8/5%，创业板 16/10%
        _lock_pct, _mainup_pct, _ = _pct_thresholds(r.get('code'))

        risk_status = '正常(VWAP上方)' if price >= vwap else '正常(VWAP下方)'"""
assert s.count(old) == 1, "锚点1(risk_status) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

old = """        elif pct >= 8.0:
            risk_status = '🚀 强势涨停锁仓，不做T'"""
new = """        elif pct >= _lock_pct:
            risk_status = '🚀 强势涨停锁仓，不做T'"""
assert s.count(old) == 1, "锚点2(锁仓) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

old = """        elif pct >= 5.0 and in_sell_radar:
            risk_status = '🔥 主升浪中，谨慎卖出'"""
new = """        elif pct >= _mainup_pct and in_sell_radar:
            risk_status = '🔥 主升浪中，谨慎卖出'"""
assert s.count(old) == 1, "锚点3(主升浪) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

# ---------- 2) 题材强度：弱势降分 ----------
old = """        if pct <= -5.0:
            f -= 0.10"""
new = """        # [CYB-GATE] 弱势降分线按板性：主板 -5%，创业板 -10%
        if pct <= _pct_thresholds(code)[2]:
            f -= 0.10"""
assert s.count(old) == 1, "锚点4(弱势降分) 命中 %d 次" % s.count(old)
s = s.replace(old, new, 1)

assert s != orig, "没有任何替换生效"
io.open(P, "w", encoding="utf-8", newline="").write(s.replace("\n", "\r\n"))
r2 = open(P, "rb").read()
print("OK %s ｜行数 %d（原 %d）｜CRLF=%d 裸LF=%d"
      % (P, r2.decode("utf-8").count("\n") + 1, raw.decode("utf-8").count("\n") + 1,
         r2.count(b"\r\n"), r2.count(b"\n") - r2.count(b"\r\n")))
