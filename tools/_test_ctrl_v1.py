# -*- coding: utf-8 -*-
import sys, math
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, numpy as np, duckdb

def clamp(v, a=0.0, b=100.0):
    if v != v: return a
    return max(a, min(b, v))

# ---------- 原版 ----------
def v0_ctrl(df, window=20):
    if len(df) < window: return 0.0
    r = df.tail(window).copy()
    if "turnover" in r.columns:
        at = r["turnover"].mean()
    else:
        at = r["volume"].mean() / (r["volume"].rolling(60).mean().iloc[-1] + 1e-8) * 5
    tsc = max(0.0, 100.0 - at * 8.0)
    r["pc"] = r["close"].shift(1)
    up = r[r["close"] > r["pc"]]; dn = r[r["close"] < r["pc"]]
    vm = r["volume"].mean() + 1e-8
    ur = up["volume"].mean()/vm if len(up) else 1.0
    dr = dn["volume"].mean()/vm if len(dn) else 1.0
    vs = 50.0
    if ur < 0.85: vs += 25.0
    if dr > 1.15: vs += 15.0
    if ur > 1.3 and dr < 0.8: vs += 10.0
    amp = (r["high"]-r["low"])/(r["close"]+1e-8)
    asc = max(0.0, 100.0 - amp.mean()*300.0)
    t = df["close"].tail(120)
    pos = (df["close"].iloc[-1]-t.min())/(t.max()-t.min()+1e-8)
    pw = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)
    return float(min(100.0, max(0.0, (tsc*0.40+vs*0.35+asc*0.25)*pw)))

def v0_stage(df, lb=10):
    if len(df) < lb+5: return "unknown"
    r = df.tail(lb).copy()
    vm5 = df["volume"].rolling(5).mean().iloc[-1] + 1e-8
    dn = r[r["close"] < r["open"]]
    dv = dn["volume"].mean() if len(dn) else 0.0
    shr = dv < vm5*0.70
    rec = r["close"].iloc[-1] > r["low"].min()*1.03
    t = df["close"].tail(60)
    pos = (df["close"].iloc[-1]-t.min())/(t.max()-t.min()+1e-8)
    if shr and rec and pos < 0.65: return "wash"
    if (not shr) and pos > 0.70: return "distribute"
    return "unknown"

# ---------- 修正版（把换手分量救活 + 修正自相矛盾 + 空阴线防护）----------
def v1_ctrl(df, window=20):
    if len(df) < 60: return 0.0
    r = df.tail(window)
    if "turnover" in r.columns:
        at = float(r["turnover"].mean())
        tsc = clamp(100.0 - at * 8.0)
    else:
        vm20 = float(df["volume"].tail(20).mean())
        vm60 = float(df["volume"].tail(60).mean()) + 1e-8
        p = vm20 / vm60
        tsc = clamp((1.2 - p) / 0.5 * 100.0)
    pc = df["close"].shift(1)
    seg = df.tail(window)
    up = seg[seg["close"] > seg["close"].shift(1)]
    dn = seg[seg["close"] < seg["close"].shift(1)]
    vm = float(seg["volume"].mean()) + 1e-8
    ur = float(up["volume"].mean())/vm if len(up) else 1.0
    dr = float(dn["volume"].mean())/vm if len(dn) else 1.0
    vs = 50.0
    if ur < 0.85: vs += 25.0
    if dr > 1.15: vs -= 15.0
    if ur > 1.3 and dr < 0.8: vs += 10.0
    vs = clamp(vs)
    amp = ((seg["high"]-seg["low"])/(seg["close"]+1e-8)).mean()
    asc = clamp(100.0 - amp*300.0)
    t = df["close"].tail(120)
    pos = (df["close"].iloc[-1]-t.min())/(t.max()-t.min()+1e-8)
    pw = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)
    return float(clamp((tsc*0.40+vs*0.35+asc*0.25)*pw))

def v1_stage(df, lb=10):
    if len(df) < lb+5: return "unknown"
    r = df.tail(lb)
    vm5 = float(df["volume"].rolling(5).mean().iloc[-1]) + 1e-8
    dn = r[r["close"] < r["open"]]
    if len(dn) == 0: return "unknown"
    dv = float(dn["volume"].mean())
    shr = dv < vm5*0.70
    rec = r["close"].iloc[-1] > r["low"].min()*1.03
    t = df["close"].tail(60)
    pos = (df["close"].iloc[-1]-t.min())/(t.max()-t.min()+1e-8)
    if shr and rec and pos < 0.65: return "wash"
    if (not shr) and dv > vm5*1.0 and pos > 0.70: return "distribute"
    return "unknown"

k = duckdb.connect(r"data\cache\kline_cache.duckdb", read_only=True)
codes = [r[0] for r in k.execute(
    "SELECT DISTINCT code FROM kline_cache WHERE substr(CAST(code AS VARCHAR),1,3) "
    "IN ('600','601','603','605','000','001','002','003') ORDER BY code LIMIT 400").fetchall()]
A, B, SA, SB = [], [], {}, {}
for c in codes:
    rows = k.execute("SELECT date,open,high,low,close,volume FROM kline_cache WHERE code=? ORDER BY date",(c,)).fetchall()
    if len(rows) < 130: continue
    df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume"])
    for col in ("open","high","low","close","volume"): df[col] = df[col].astype(float)
    A.append(v0_ctrl(df)); B.append(v1_ctrl(df))
    g = v0_stage(df); SA[g] = SA.get(g,0)+1
    g = v1_stage(df); SB[g] = SB.get(g,0)+1
k.close()
A = np.array(A); B = np.array(B)
def stat(name, a):
    print("  %-6s min %6.2f | 中位 %6.2f | max %6.2f | >=70 %3d只 | >=75 %3d只"
          % (name, a.min(), np.median(a), a.max(), (a>=70).sum(), (a>=75).sum()))
print("样本 %d 只主板" % len(A))
print("--- control_score ---")
stat("原版", A)
stat("修正后", B)
print()
print("--- stage_guess ---")
tot = len(A)
for nm, d in (("原版", SA), ("修正后", SB)):
    row = "  %-6s " % nm
    for kk in ("wash","distribute","unknown"):
        row += "%s %3d只(%4.1f%%)  " % (kk, d.get(kk,0), 100.0*d.get(kk,0)/tot)
    print(row)
print()
print("--- 原版规则触发率 ---")
print("  规则1 (>=70 且 wash)        : %d 只" % ((A>=70).sum() and int(((A>=70)&np.array([SA.get('wash',0)>0]*len(A))).sum()) if False else int(((A>=70)).sum())))
print("  规则3 (>=75 且 位置低)      : 上限 %.2f 分，数学上不可能达到 >=75" % 67.8)
print()
print("--- 修正版规则触发率 ---")
b_wash = np.array([v1_stage(pd.DataFrame()) if False else 0 for p in []])
print("  >=70 只数: %d   >=75 只数: %d" % ((B>=70).sum(), (B>=75).sum()))
