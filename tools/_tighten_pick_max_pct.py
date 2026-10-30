# -*- coding: utf-8 -*-
"""
收紧「可介入」候选门槛：涨幅上限 9.0 -> 5.0（两个文件同步改）。

依据（tools\\_sweep_pick_thresholds.py，5603 条真实历史样本，
口径 = 程序自身 fetch_tracking + win=收益>0）：

    涨幅上限     样本     5日胜率   30日胜率   累计胜率
    <= 9.0%     5603     41.6%     43.9%     35.2%
    <= 8.0%     5419     41.7%     44.3%     35.4%
    <= 7.0%     5080     41.8%     44.7%     35.9%
    <= 6.0%     4543     42.3%     45.4%     36.6%
    <= 5.0%     3843     43.1%     45.7%     38.0%   <- 选它

单调上升，且样本仍保留 69%（不是缩到个位数）。
反例：量比越高胜率越低（1.2->41.6%，3.0->35.9%），所以量比下限不能提，
      价格下限也不能提（6元->41.6%，15元->40.4%/累计28.2%）。

两个文件必须同改（注释里写明「与引擎保持一致」，只改一处会路由分叉）：
  services\\picks_tracking_service.py   L49  PICK_MAX_PCT
  services\\board_anomaly_engine.py      L72  _PICK_MAX_PCT
两个文件都是纯 LF。
"""
import os
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"

JOBS = [
    (r"services\picks_tracking_service.py",
     "PICK_MAX_PCT = 9.0",
     "PICK_MAX_PCT = 5.0",
     ".bak_before_tighten"),
    (r"services\board_anomaly_engine.py",
     "_PICK_MAX_PCT = 9.0     # 候选涨幅上限：还没封板才买得进",
     "_PICK_MAX_PCT = 5.0     # 候选涨幅上限：还没封板才买得进\n"
     "                              # 9.0 -> 5.0（2026-10-10，实测驱动）：5603 条历史样本里\n"
     "                              # 上限 9/8/7/6/5% 对应 5日胜率 41.6/41.7/41.8/42.3/43.1%，\n"
     "                              # 30日 43.9/44.3/44.7/45.4/45.7%，累计 35.2/35.4/35.9/36.6/38.0%，\n"
     "                              # 单调上升；样本仍保留 69%。依据 tools\\_sweep_pick_thresholds.py。\n"
     "                              # 量比/价格下限不能提：量比越高胜率越低（反直觉但单调）。",
     ".bak_before_tighten"),
]

for rel, old, new, suffix in JOBS:
    P = os.path.join(ROOT, rel)
    BAK = P + suffix
    raw = open(P, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    assert crlf == 0, "%s 应是纯 LF，实测 CRLF=%d" % (rel, crlf)
    s = raw.decode("utf-8-sig")

    print("=" * 100)
    print("%s  （纯 LF，LF=%d）" % (rel, lf))

    if new.split("\n")[0] in s and old not in s:
        print("  已改过（幂等跳过）")
        continue

    n = s.count(old)
    assert n == 1, "锚点命中 %d 次（应为 1）：%r" % (n, old[:60])
    print("  锚点唯一 √  %s" % old.strip()[:80])

    if not os.path.exists(BAK):
        shutil.copy2(P, BAK)
        print("  已备份 -> %s" % os.path.basename(BAK))
    else:
        print("  备份已存在，不覆盖")

    s2 = s.replace(old, new)
    open(P, "wb").write(s2.encode("utf-8"))
    py_compile.compile(P, doraise=True)
    print("  已写入 + py_compile 通过 √")

    raw2 = open(P, "rb").read()
    assert raw2.count(b"\r\n") == 0, "写回后行尾被改了！"
    print("  回读：行尾仍纯 LF √")
    for i, t in enumerate(open(P, encoding="utf-8-sig").read().split("\n"), 1):
        if "PICK_MAX_PCT = " in t:
            print("  L%-5d %s" % (i, t.strip()[:100]))
            break

print()
print("=" * 100)
print("两处新值一致性核对：")
import io  # noqa: E402
a = io.open(os.path.join(ROOT, r"services\picks_tracking_service.py"), encoding="utf-8-sig").read()
b = io.open(os.path.join(ROOT, r"services\board_anomaly_engine.py"), encoding="utf-8-sig").read()
ok_a = "PICK_MAX_PCT = 5.0" in a
ok_b = "_PICK_MAX_PCT = 5.0" in b
print("  picks_tracking_service PICK_MAX_PCT = 5.0  ->  %s" % ("√" if ok_a else "X"))
print("  board_anomaly_engine    _PICK_MAX_PCT = 5.0 ->  %s" % ("√" if ok_b else "X"))
print("  结果：%s" % ("两条路已一致 √" if (ok_a and ok_b) else "仍不一致 X"))
