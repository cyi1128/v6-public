# -*- coding: utf-8 -*-
"""校验还原点：文件数 / 体积 / 四批修复是否真的进了快照。

用法：
    python tools\\_verify_snapshot.py                # 校验 backups\\ 里最新的 backup_*
    python tools\\_verify_snapshot.py <快照目录或名字>  # 校验指定快照
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
BK = os.path.join(ROOT, "backups")


def newest_snap():
    cands = []
    for d in os.listdir(BK):
        p = os.path.join(BK, d)
        if d.startswith("backup_") and os.path.isdir(p):
            cands.append(d)
    if not cands:
        return None
    return os.path.join(BK, sorted(cands)[-1])


arg = sys.argv[1] if len(sys.argv) > 1 else None
if arg:
    SNAP = arg if os.path.isabs(arg) else os.path.join(BK, arg)
else:
    SNAP = newest_snap()

assert SNAP and os.path.isdir(SNAP), "找不到快照目录：%s" % SNAP

n = 0
sz = 0
for r_, _, fs in os.walk(SNAP):
    for f in fs:
        n += 1
        try:
            sz += os.path.getsize(os.path.join(r_, f))
        except OSError:
            pass
print("快照 %s" % os.path.basename(SNAP))
print("  %d 文件 / %.1f MB" % (n, sz / 1024 / 1024))
print()

print("各批修复文件是否在快照内、且是改后版本：")
CHECKS = [
    # ---- 第 1~4 批：判涨停按板性 ----
    (r"ui\battle_console_v2.py", "pct >= _lu_pct(code)", "第三批 主界面"),
    (r"services\v22_combat_service.py", "_lu_pct(x.get('code'))", "第三批 v22"),
    (r"services\daily_close_summary_service.py", "_lu_pct(x.get('code'))", "第三批 收盘总结"),
    (r"utils\indicators.py", "_lu_pct(code)", "第三批 indicators"),
    (r"services\picks_tracking_service.py", "pct >= _lu_pct(code)", "第二批 可介入"),
    (r"services\picks_tracking_service.py", "OR code LIKE '30%'", "第四批 回填放开创业板"),
    (r"ui\market_sentiment_panel.py", "def limit_pct(code)", "第二批 市场情绪"),
    (r"ui\echarts_kline.py", "window.__limitPct", "第二批 K线图"),
    (r"ui\watchlist_panel.py", "def set_kline_data(self, kline_data, code='')", "第二批 自选小K线"),
    (r"services\intraday_opportunity_engine.py", "_chase_hi", "第二批 追高文案"),
    (r"services\band_pattern_engine.py", "def _lu_threshold(code)", "第 1 批 日K建仓截面"),
    # ---- 第 5 批：可介入门槛收紧 ----
    (r"services\picks_tracking_service.py", "PICK_MAX_PCT = 5.0", "第 5 批 门槛收紧(追踪路)"),
    (r"services\board_anomaly_engine.py", "_PICK_MAX_PCT = 5.0", "第 5 批 门槛收紧(当日引擎)"),
    # ---- 第 6 批：MA20 硬门槛 + 追踪表新列 ----
    (r"services\board_anomaly_engine.py", "m20 = ma20.get(code) if ma20 else None",
     "第 6 批 MA20 硬门槛(堵洞)"),
    (r"services\picks_tracking_service.py", "'ma20': ma20,", "第 6 批 追踪带出 MA20"),
    (r"ui\battle_widgets\picks_track_widget.py", "T_M20", "第 6 批 追踪表距MA20%列"),
    # ---- 更早的结构性能力（确认没被回退掉）----
    (r"services\control_profile.py", "def ctrl_cell", "控盘数据源"),
    (r"strategy\base.py", "def estimate_control_score", "控盘/洗盘评分"),
    (r"services\regime_gate.py", "", "三轴状态闸门(文件存在)"),
    (r"ui\battle_widgets\auction_filter_widget.py", "CYB_PREFIXES", "竞价创业板门槛"),
    (r"ui\battle_widgets\atr_t_widget.py", "PCT_LOCK_", "分时做T 板性风控"),
]
ok = bad = 0
for rel, needle, label in CHECKS:
    p = os.path.join(SNAP, rel)
    if not os.path.exists(p):
        print("  X %-34s 快照内不存在该文件" % label)
        bad += 1
        continue
    s = io.open(p, encoding="utf-8-sig").read()
    if needle in s:
        print("  √ %-34s 已是改后版本" % label)
        ok += 1
    else:
        print("  X %-34s 快照里还是旧版本！" % label)
        bad += 1

print()
print("结果：改后版本 %d 项 / 异常 %d 项" % (ok, bad))
print()

print("backups\\ 下所有还原点（按名字倒序 = restore.py 编号）：")
allb = sorted([d for d in os.listdir(BK)
               if d.startswith("backup_") and os.path.isdir(os.path.join(BK, d))], reverse=True)
for i, d in enumerate(allb, 1):
    p = os.path.join(BK, d)
    c = sum(len(f) for _, _, f in os.walk(p))
    s2 = 0
    for r_, _, fs in os.walk(p):
        for f in fs:
            try:
                s2 += os.path.getsize(os.path.join(r_, f))
            except OSError:
                pass
    mark = "  <- 当前默认回滚目标" if i == 1 else ""
    print("  %d  %-26s %4d 文件 / %5.1f MB%s" % (i, d, c, s2 / 1024 / 1024, mark))
