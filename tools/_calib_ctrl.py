# -*- coding: utf-8 -*-
import sys, math
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, numpy as np, duckdb
def clamp(v, a=0.0, b=100.0):
    if v != v: return a
    return max(a, min(b, v))
def v1_ctrl(df, window=20):
    if len(df) < 60: return 0.0
    r = df.tail(window)
    if "turnover" in r.columns:
        at = float(r["turnover"].mean()); tsc = clamp(100.0 - at*8.0)
    else:
        vm20 = float(df["volume"].tail(20).mean())
        vm60 = float(df["volume"].tail(60).mean()) + 1e-8
        tsc = clamp((1.2 - vm20/vm60) / 0.5 * 100.0)
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
    return float(clamp((tsc*0.40+vs*0.35+asc*0.25)*pw)), float(vm20/vm60) if "turnover" not in r.columns else -1
def v1_stage(df, lb=10):
    if len(df) < lb+5: return "unknown"
    r = df.tail(lb)
    vm5 = float(df["volume"].rolling(5).mean().iloc[-1]) + 1e-8
    dn = r[r["close"] < r["open"]]
    if len(dn) == 0: return "unknown"
    dv = float(dn["volume"].mean()); shr = dv < vm5*0.70
    rec = r["close"].iloc[-1] > r["low"].min()*1.03
    t = df["close"].tail(60)
    pos = (df["close"].iloc[-1]-t.min())/(t.max()-t.min()+1e-8)
    if shr and rec and pos < 0.65: return "wash"
    if (not shr) and dv > vm5*1.0 and pos > 0.70: return "distribute"
    return "unknown"
k = duckdb.connect(r"data\cache\kline_cache.duckdb", read_only=True)
codes=[r[0] for r in k.execute("SELECT DISTINCT code FROM kline_cache WHERE substr(CAST(code AS VARCHAR),1,3) IN ('600','601','603','605','000','001','002','003') ORDER BY code LIMIT 600").fetchall()]
S=[];P=[];ST=[]
for c in codes:
    rows=k.execute("SELECT date,open,high,low,close,volume FROM kline_cache WHERE code=? ORDER BY date",(c,)).fetchall()
    if len(rows)<130: continue
    df=pd.DataFrame(rows,columns=["date","open","high","low","close","volume"])
    for col in ("open","high","low","close","volume"): df[col]=df[col].astype(float)
    sc,p=v1_ctrl(df); S.append(sc); P.append(p); ST.append(v1_stage(df))
k.close()
S=np.array(S); P=np.array([x for x in P if x>0]); n=len(S)
print("样本 %d 只主板" % n)
print()
print("--- 量能中枢比 vm20/vm60（换手回退量的原料）---")
qs=[0,10,25,50,75,90,100]
print("  " + "  ".join("%d%%:%.2f" % (q, np.percentile(P,q)) for q in qs))
print()
print("--- control_score 分位 ---")
print("  " + "  ".join("%d%%:%.1f" % (q, np.percentile(S,q)) for q in qs))
print()
print("--- 各阈值触发只数 / 占比 ---")
for th in (60,65,70,75,80,85,90):
    m=(S>=th).sum(); print("  >=%-3d : %3d 只 (%.1f%%)" % (th, m, 100.0*m/n))
print()
st=np.array(ST)
print("--- 联合分布（control_score × stage_guess）---")
for th in (75,80,85):
    for g in ("wash","distribute","unknown"):
        m=((S>=th)&(st==g)).sum()
        print("  >=%-3d 且 %-10s : %3d 只 (%.1f%%)" % (th,g,m,100.0*m/n))
