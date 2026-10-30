# -*- coding: utf-8 -*-
"""把用户指令里的两个函数【原样】跑真实主板数据，量化缺陷。"""
import sys, math
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, numpy as np, duckdb

# ============ 用户原版 verbatim ============
def estimate_control_score(df, window=20):
    if len(df) < window:
        return 0.0
    recent = df.tail(window).copy()
    if "turnover" in recent.columns:
        avg_turnover = recent["turnover"].mean()
    else:
        avg_turnover = recent["volume"].mean() / (recent["volume"].rolling(60).mean().iloc[-1] + 1e-8) * 5
    turnover_score = max(0.0, 100.0 - avg_turnover * 8.0)
    recent["prev_close"] = recent["close"].shift(1)
    up_days = recent[recent["close"] > recent["prev_close"]]
    down_days = recent[recent["close"] < recent["prev_close"]]
    vol_mean = recent["volume"].mean() + 1e-8
    up_vol_ratio = up_days["volume"].mean() / vol_mean if len(up_days) > 0 else 1.0
    down_vol_ratio = down_days["volume"].mean() / vol_mean if len(down_days) > 0 else 1.0
    vol_score = 50.0
    if up_vol_ratio < 0.85: vol_score += 25.0
    if down_vol_ratio > 1.15: vol_score += 15.0
    if up_vol_ratio > 1.3 and down_vol_ratio < 0.8: vol_score += 10.0
    amp = (recent["high"] - recent["low"]) / (recent["close"] + 1e-8)
    amp_score = max(0.0, 100.0 - amp.mean() * 300.0)
    tail120 = df["close"].tail(120)
    pos = (df["close"].iloc[-1] - tail120.min()) / (tail120.max() - tail120.min() + 1e-8)
    pos_weight = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)
    score = (turnover_score*0.40 + vol_score*0.35 + amp_score*0.25) * pos_weight
    return float(min(100.0, max(0.0, score)))

def judge_wash_or_distribute(df, lookback=10):
    if len(df) < lookback + 5:
        return "unknown"
    recent = df.tail(lookback).copy()
    vol_ma5 = df["volume"].rolling(5).mean().iloc[-1] + 1e-8
    down = recent[recent["close"] < recent["open"]]
    down_vol = down["volume"].mean() if len(down) > 0 else 0.0
    is_shrinking = down_vol < vol_ma5 * 0.70
    has_recovery = recent["close"].iloc[-1] > recent["low"].min() * 1.03
    tail60 = df["close"].tail(60)
    pos = (df["close"].iloc[-1] - tail60.min()) / (tail60.max() - tail60.min() + 1e-8)
    if is_shrinking and has_recovery and pos < 0.65: return "wash"
    if (not is_shrinking) and pos > 0.70: return "distribute"
    return "unknown"

# ============ 真实主板数据 ============
k = duckdb.connect(r"data\cache\kline_cache.duckdb", read_only=True)
codes = [r[0] for r in k.execute(
    "SELECT DISTINCT code FROM kline_cache WHERE substr(CAST(code AS VARCHAR),1,3) "
    "IN ('600','601','603','605','000','001','002','003') ORDER BY code LIMIT 400").fetchall()]
scores, stages, raw_turn = [], {}, []
nan_cnt = 0
for c in codes:
    rows = k.execute("SELECT date,open,high,low,close,volume FROM kline_cache "
                     "WHERE code=? ORDER BY date", (c,)).fetchall()
    if len(rows) < 130: continue
    df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume"]).astype(
        {"open":float,"high":float,"low":float,"close":float,"volume":float})
    s = estimate_control_score(df)
    g = judge_wash_or_distribute(df)
    if math.isnan(s): nan_cnt += 1
    scores.append(s); stages[g] = stages.get(g, 0) + 1
    tw = df["volume"].tail(20).mean() / (df["volume"].tail(20).rolling(60).mean().iloc[-1] + 1e-8) * 5
    raw_turn.append(tw)
k.close()

s = np.array([x for x in scores if not math.isnan(x)])
print("样本：%d 只主板股票（kline_cache，各 130+ 交易日）" % len(scores))
print()
print("--- estimate_control_score 结果 ---")
print("  NaN 结果数量        : %d  (%.1f%%)" % (nan_cnt, 100.0*nan_cnt/len(scores)))
print("  min/中位/max       : %.2f / %.2f / %.2f" % (s.min(), np.median(s), s.max()))
print("  >=70 的只数        : %d  (%.1f%%)" % ((s>=70).sum(), 100.0*(s>=70).sum()/len(s)))
print("  >=75 的只数        : %d  (%.1f%%)" % ((s>=75).sum(), 100.0*(s>=75).sum()/len(s)))
print("  ==0.0 的只数       : %d  (%.1f%%)" % ((s==0).sum(), 100.0*(s==0).sum()/len(s)))
print()
print("--- 无 turnover 时的回退值 avg_turnover（前5个）---")
print("  ", ["%.2f" % x for x in raw_turn[:5]])
print("  全部为 NaN: %s  -> turnover_score 恒=0，占总权重 40% 恒丢" % all(math.isnan(x) for x in raw_turn))
print()
print("--- judge_wash_or_distribute 分布 ---")
tot = sum(stages.values())
for kk, vv in sorted(stages.items(), key=lambda x: -x[1]):
    print("  %-11s %4d  (%.1f%%)" % (kk, vv, 100.0*vv/tot))
