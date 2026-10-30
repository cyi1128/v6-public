# -*- coding: utf-8 -*-
import io, sys, shutil
sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6\\"

# ---------- 1. 一键灌数据 bat ----------
bat = """@echo off
chcp 65001 >nul
cd /d D:\\QuantMonitorV6
set "PY=C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\python.exe"
echo ==========================================================
echo  灌入创业板(300/301)日K线到本地缓存  kline_cache.duckdb
echo.
echo  作用：让全市场扫描、控盘度、K线读取走本地缓存，
echo        不走在线接口，速度快十几倍。
echo.
echo  ！！运行前请先关闭 QuantMonitorV6 主程序 ！！
echo     （程序开着时数据库被占用，脚本会拒绝运行，
echo       以免把数据写进备用文件）
echo.
echo  首次约 10-30 分钟，之后可重复运行做补漏，很快。
echo ==========================================================
echo.
pause
echo.
"%PY%" -X utf8 tools\\seed_cyb_kline.py --workers 10
echo.
echo ==========================================================
echo  结束。如果显示"成功 xxx 只"，说明创业板数据已就位。
echo  可以重新打开 QuantMonitorV6 了。
echo ==========================================================
pause
"""
bp = ROOT + "灌创业板K线缓存.bat"
io.open(bp, "w", encoding="utf-8", newline="\r\n").write(bat)
print("OK 已生成 %s" % bp)

# ---------- 2. AGENTS.md ----------
P = ROOT + "AGENTS.md"
raw = open(P, "rb").read()
assert raw.count(b"\r\n") == 0, "AGENTS.md 不是纯 LF"
shutil.copy2(P, P + ".bak_before_cyb")
s = raw.decode("utf-8")

anchor = "- **三轴状态闸门**："
add = """- **创业板已放行（2026-10-10）**：用户可买创业板，原先全项目「只保留主板」的过滤已放开 300/301。改的 6 处（科创板 688/689、北交所 8xx/4xx/920 仍剔除）：
  - `services\\band_pattern_engine.py`：`_is_main_a_share()`（日K建仓全市场扫描的**前置**过滤，位置在 `_load_bars` 之前，属性能优化，不要挪到后面）+ `scan_stock` 注释
  - `ui\\battle_widgets\\auction_filter_widget.py`：`MAIN_BOARD_PREFIXES`（竞价筛选，成交额/涨幅两条路径都走它）
  - `services\\intraday_opportunity_engine.py`：`MAIN_PREFIX`（异动池 → anchor_tracker 基准阳跟踪的信号源）
  - `services\\market_rhythm_engine.py`：`is_main_board()`（市场节奏；注意创业板 20cm，混入后「均涨幅」列会从约 10% 偏到约 15%，已在 docstring 标注）
  - `services\\board_anomaly_engine.py`：2 处 `startswith(('60','00'))` → `('60','00','30')`（可介入 Tab）
  - `services\\picks_tracking_service.py`：1 处同上（追踪 Tab）
  > 未改（不在线上链路）：`data\\stock_list_provider.py _is_main_board_code`（只被 `strategy\\main_force_behavior.py`、`strategy\\nine_filter_strategy.py` 用）、`strategy\\*` 下若干老选股模块、`ui\\stock_screener_panel.py`（有「仅主板」复选框，属用户可选开关）。
- **创业板需要先灌 K 线缓存**：本地 `kline_cache.duckdb` 原为增量模式（只更新已在库代码，`INCREMENTAL_FETCH_DAYS=15`），创业板从未入库。不灌也能跑（`_load_bars` 会兜底在线抓取，实测 0.6 秒/只），但全市场扫描会多花十几分钟。灌法：**关掉主程序**后双击根目录 `灌创业板K线缓存.bat`（调 `tools\\seed_cyb_kline.py`）。脚本直连主库写入，主库被占用时**报错退出**、不写备用文件（`KlineCacheDB._get_conn` 被锁时是静默转写备用文件的，这里刻意避开）。无历史数据的新股记进 `tools\\_cyb_nodata.txt`，下次自动跳过。
  > 灌数据期间主库是写锁独占，主程序读本地缓存会失败并降级在线抓取（不崩，只是慢），所以要在程序关闭时跑。
"""
assert s.count(anchor) == 1, "锚点 %d" % s.count(anchor)
s = s.replace(anchor, add + anchor, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
r2 = open(P, "rb").read()
print("OK AGENTS.md CRLF=%d LF=%d 行数=%d" % (r2.count(b"\r\n"), r2.count(b"\n")-r2.count(b"\r\n"),
      r2.decode("utf-8").count("\n")+1))
