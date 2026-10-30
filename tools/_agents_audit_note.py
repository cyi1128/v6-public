# -*- coding: utf-8 -*-
"""AGENTS.md 记录本次全模块反推排查的结论（只记会影响后续改代码的硬事实）。"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\AGENTS.md"
raw = open(P, "rb").read()
assert raw.count(b"\r\n") == 0, "AGENTS.md 应为纯 LF"
shutil.copy2(P, P + ".bak_before_audit")
s = raw.decode("utf-8").replace("\r\n", "\n")

anchor = "- **三轴状态闸门**："
add = """- **涨停阈值口径：唯一来源 `band_pattern_engine._lu_threshold(code)`（2026-10-10 全项目反推排查后新增）**：主板 9.5% / 创业板·科创板 19.5% / 北交所 29.5%。日K建仓的「行业涨停家数 / 大盘涨停家数」改为按板判定（原来全市场统一 `x >= 9.5`）。实测 2026-10-09：旧口径 87 家 → 新口径 69 家，差的 18 家全是创业板 +10%~19.4% 的非涨停股（300340 +15.89%、300111 +14.81% 等）。这两个数喂给环境分与题材因子，会直接改等级与排序，所以这处属于**影响选股结果**的改动。
  > 反推排查时发现：**全项目「判涨停」的容差不统一**（日K建仓 9.5 / 今日涨停 9.8 / 自选与图表 9.8~19.8）。差 0.3%，影响极小；要统一就全部改成引用 `_lu_threshold()`。用户尚未表态。
  > `band_pattern_engine._is_limit_up()`（约 L155）是**死代码，全项目无任何调用**——模式一/二的基准日实际用「实体 >=3% 且涨幅 >=3%」判定，不要以为涨停条件在这里生效。
- **同期按板性改掉的展示类阈值（2026-10-10）**：`ui\\watchlist_panel.py` 近20日涨停次数（约 L1365，主板9.8/创业板19.8）、`ui\\trading_dashboard_panel.py` 仪表盘涨停·跌停家数（约 L519/L523）、`services\\intraday_opportunity_engine.py` L553 过期注释。备份后缀统一 `.bak_before_cyb_lu`。
- **仍写死 10cm 口径、未改（用户未拍板）**：`ui\\watchlist_panel.py` L192-193（自选K线小图涨停配色）、`ui\\echarts_kline.py` L263-264（JS 里 K 线涨停标记色；注意同文件 L1111 的统计口径**已有** 19.8 双档，是写对的）、`ui\\market_sentiment_panel.py` L424（炸板判定 `7 <= pct < 9.8`，按板应为 14~19.8）、`intraday_opportunity_engine.py` L1471/L1473（追高提示文案）。全是展示/文案，不影响筛选结果。
- **`strategy\\ai520_*` / `ai_520_engine.py` / `ai_520_scan_service.py` 里写死的 9.8% 不要去修**——AI520（选股雷达）早已下线，改它们没有意义。
"""
assert s.count(anchor) == 1, "锚点命中 %d 次" % s.count(anchor)
s = s.replace(anchor, add + anchor, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
r2 = open(P, "rb").read()
print("OK AGENTS.md ｜%d 行 ｜CRLF=%d" % (r2.decode("utf-8").count("\n") + 1,
                                          r2.count(b"\r\n")))

print()
print("=== 核对：备份与产物是否都在 ===")
import os
for rel in [r"services\band_pattern_engine.py", r"services\band_pattern_engine.py.bak_before_cyb_lu",
            r"services\band_pattern_engine.py.bak_before_lu_sh",
            r"ui\watchlist_panel.py.bak_before_cyb_lu",
            r"ui\trading_dashboard_panel.py.bak_before_cyb_lu",
            r"services\intraday_opportunity_engine.py.bak_before_cyb_lu",
            r"ui\battle_widgets\atr_t_widget.py.bak_before_cyb_risk",
            r"services\market_rhythm_engine.py.bak_before_cyb_text",
            r"docs\全模块反推排查明细_20261010.md"]:
    p = os.path.join(r"D:\QuantMonitorV6", rel)
    print("   %-58s %s" % (rel, "存在 %d 字节" % os.path.getsize(p) if os.path.exists(p) else "!! 缺失"))
