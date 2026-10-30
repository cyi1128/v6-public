# -*- coding: utf-8 -*-
"""1) 订正 market_rhythm_engine 里 3 处过期的「只留主板」注释/文案
   2) AGENTS.md 记录分时做T的创业板风控阈值"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

# ---------- 1) market_rhythm_engine.py（纯 LF） ----------
P = ROOT + r"services\market_rhythm_engine.py"
raw = open(P, "rb").read()
crlf, lf = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
assert lf and not crlf, "应为纯 LF，实测 CRLF=%d LF=%d" % (crlf, lf)
shutil.copy2(P, P + ".bak_before_cyb_text")
s = raw.decode("utf-8").replace("\r\n", "\n")

pairs = [
    ("    # 每个交易日的记录 —— 只留主板",
     "    # 每个交易日的记录 —— 主板 + 创业板（300/301 已放开）"),
    ("return {'ok': False, 'error': '近期交易日无主板涨停数据'}",
     "return {'ok': False, 'error': '近期交易日无主板/创业板涨停数据'}"),
    ("        # 均涨幅（已只含主板，所以是 10% 一档，不会出现 15%）",
     "        # 均涨幅（主板 + 创业板混合，20cm 会把这一档从约 10% 抬到约 15%）"),
]
for old, new in pairs:
    assert s.count(old) == 1, "锚点命中 %d 次: %s" % (s.count(old), old[:40])
    s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
r2 = open(P, "rb").read()
print("OK %s ｜CRLF=%d 裸LF=%d" % (P, r2.count(b"\r\n"),
                                   r2.count(b"\n") - r2.count(b"\r\n")))

# ---------- 2) AGENTS.md（纯 LF） ----------
P2 = ROOT + "AGENTS.md"
raw2 = open(P2, "rb").read()
assert raw2.count(b"\r\n") == 0, "AGENTS.md 应为纯 LF"
shutil.copy2(P2, P2 + ".bak_before_cyb_atr")
s2 = raw2.decode("utf-8")

anchor = "- **三轴状态闸门**："
add = """- **分时做T的创业板风控阈值（2026-10-10）**：`ui\\battle_widgets\\atr_t_widget.py`（**纯 CRLF**）。这个模块**没有板性过滤**（股票池 = 持仓 DB → 自选兜底，两条路都不过滤板性），但它有 3 处「个股当日涨跌幅」绝对值阈值是按 10cm 写死的，创业板会被误判：
  | 行 | 逻辑 | 主板 | 创业板 |
  |---|---|---|---|
  | `_apply_risk_and_signal` | 涨停锁仓、禁止卖出做T（涨停的 80%） | 8.0% | **16.0%** |
  | 同上 | 主升浪、谨慎卖出（涨停的 50%） | 5.0% | **10.0%** |
  | `_compute_theme_strength` | 弱势降分 `f -= 0.10` | -5.0% | **-10.0%** |
  改前后果：一只 +9% 的创业板股票（离 20% 涨停还有 11%）会被判「🚀 强势涨停锁仓，不做T」并 `blocked='sell'`，**禁止用户做T卖出**。
  实现：模块级 `CYB_PREFIXES` / `PCT_LOCK_*` / `PCT_MAINUP_*` / `PCT_WEAK_*` + `_is_cyb()` / `_pct_thresholds(code)`；`_apply_risk_and_signal` 里由 `r.get('code')` 取板性。
  > **大盘指数那两处不算**：`_check_market_sentiment` 的 `pct < -1.0` 与 `_check_daily_market_warn` 的 `pct < -2.0` 读的是上证指数（`1.000001`），与板性无关，保持不动。
  > 已验证：+9% 时主板判「锁仓」、创业板判「正常」；主板各档与改动前逐档一致。回退 `.bak_before_cyb_risk`。
- **今日涨停模块的板性判定本来就是对的**（2026-10-10 核查）：`ui\\battle_widgets\\limit_up_widget.py` 的 `_fetch_limit_up` 按 `code.startswith(('300','301','688','689')) → 19.5` / `('8','4','920') → 29.5` / `else → 9.8` 判涨停，不用改。
- **涨停原因库上游无板性过滤**（2026-10-10 核查）：`services\\limit_up_collector.py` 与 `data\\limit_up_reason_db.py` 都不含板性过滤，创业板涨停原因一直在采，「日K建仓」的题材列能查到创业板。所以市场节奏 L243 的 `is_main_board()` 放开后，涨停统计口径自然变成主板 + 创业板（均涨幅那一档从约 10% 抬到约 15%，用户已确认按此口径）。
"""
assert s2.count(anchor) == 1, "AGENTS 锚点命中 %d 次" % s2.count(anchor)
s2 = s2.replace(anchor, add + anchor, 1)
io.open(P2, "w", encoding="utf-8", newline="").write(s2)
r3 = open(P2, "rb").read()
print("OK AGENTS.md ｜行数 %d ｜CRLF=%d" % (r3.decode("utf-8").count("\n") + 1,
                                           r3.count(b"\r\n")))
