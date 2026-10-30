import sys
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, numpy as np, duckdb
from strategy.base import TechnicalIndicators as TI

k = duckdb.connect(r"data\cache\kline_cache.duckdb", read_only=True)
S=[]; ST={}
codes=[r[0] for r in k.execute("SELECT DISTINCT code FROM kline_cache WHERE substr(CAST(code AS VARCHAR),1,3) IN ('600','601','603','605','000','001','002','003') ORDER BY code LIMIT 600").fetchall()]
first=None
for c in codes:
    rows=k.execute("SELECT date,open,high,low,close,volume FROM kline_cache WHERE code=? ORDER BY date",(c,)).fetchall()
    if len(rows)<130: continue
    df=pd.DataFrame(rows,columns=["date","open","high","low","close","volume"])
    for col in ("open","high","low","close","volume"): df[col]=df[col].astype(float)
    s=TI().estimate_control_score(df)          # 实例调法（用户写法）
    s2=TI.estimate_control_score(df)           # 静态调法
    assert abs(s-s2)<1e-9, "两种调法结果不一致"
    g=TI.judge_wash_or_distribute(df)
    S.append(s); ST[g]=ST.get(g,0)+1
    if first is None: first=(c,s,s2,g)
k.close()
S=np.array(S); n=len(S)
qs=[0,10,25,50,75,90,100]
print("样本 %d 只主板  两种调法一致 OK" % n)
print("control_score 分位: " + "  ".join("%d%%:%.1f" % (q,np.percentile(S,q)) for q in qs))
for th in (70,75,80,85,90,95):
    print("   >=%-3d : %3d 只 (%.1f%%)" % (th,(S>=th).sum(),100.0*(S>=th).sum()/n))
print("stage_guess:", {kk: "%d(%.1f%%)" % (vv,100.0*vv/n) for kk,vv in sorted(ST.items(),key=lambda x:-x[1])})
print()
print("--- 边界与空值防护 ---")
print("  空 DataFrame            :", TI().estimate_control_score(pd.DataFrame()), TI().judge_wash_or_distribute(pd.DataFrame()))
print("  只有 10 行              :", TI().estimate_control_score(pd.DataFrame({'close':[1]*10,'high':[1]*10,'low':[1]*10,'volume':[1]*10})))
print("  缺列                    :", TI().estimate_control_score(pd.DataFrame({'close':[1]*100})), TI().judge_wash_or_distribute(pd.DataFrame({'close':[1]*100})))
print("  全 NaN volume          :", TI().estimate_control_score(pd.DataFrame({'close':[1.0]*100,'high':[1.0]*100,'low':[1.0]*100,'volume':[float('nan')]*100})))
print("  无阴线(纯上涨)          :", TI().judge_wash_or_distribute(pd.DataFrame(
      {'open':list(range(100)),'close':[x+1.0 for x in range(100)],'high':[x+2.0 for x in range(100)],
       'low':list(range(100)),'volume':[1e6]*100})))
print("  含 turnover 列          :", TI().estimate_control_score(pd.DataFrame(
      {'close':[10.0]*100,'high':[10.5]*100,'low':[9.5]*100,'volume':[1e6]*100,'turnover':[2.0]*100})))
