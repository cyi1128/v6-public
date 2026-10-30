# -*- coding: utf-8 -*-
"""
把 picks_tracking_service.backfill_history 的取数 SQL 放开创业板。

背景：当日引擎路径 L438 `code.startswith(('60','00','30'))` 已含创业板，
但回填路径 L505 `WHERE code LIKE '60%' OR code LIKE '00%'` 不含 ->
回填永远产不出创业板候选，「可介入」Tab 的历史样本缺一整块。

只改这一行：'60%' / '00%' -> 再加 '30%'。688/689/8xx/920 仍排除（与全项目一致）。
纯 LF 文件。
"""
import io
import os
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
REL = r"services\picks_tracking_service.py"
P = os.path.join(ROOT, REL)
BAK = P + ".bak_before_cyb_backfill"

OLD = "                WHERE code LIKE '60%' OR code LIKE '00%'"
NEW = "                WHERE code LIKE '60%' OR code LIKE '00%' OR code LIKE '30%'"

raw = open(P, "rb").read()
crlf = raw.count(b"\r\n")
lf = raw.count(b"\n") - crlf
assert crlf == 0, "本文件应是纯 LF，实测 CRLF=%d" % crlf
print("行尾核对：纯 LF（LF=%d）√" % lf)

s = raw.decode("utf-8-sig")

if NEW in s:
    print("已改过（幂等跳过）")
    sys.exit(0)

n = s.count(OLD)
assert n == 1, "锚点命中 %d 次（应为 1）" % n
print("锚点唯一 √ -> L505")

if not os.path.exists(BAK):
    shutil.copy2(P, BAK)
    print("已备份 -> %s" % os.path.basename(BAK))
else:
    print("备份已存在，保留原备份（不覆盖）")

s2 = s.replace(OLD, NEW)
assert s2.count(NEW) == 1
open(P, "wb").write(s2.encode("utf-8"))
print("已写入")

py_compile.compile(P, doraise=True)
print("py_compile 通过 √")

# 回读验证
s3 = io.open(P, encoding="utf-8-sig").read()
assert NEW in s3 and "OR code LIKE '30%'" in s3
print("回读验证：L505 现为 -> %s" % NEW.strip())

raw2 = open(P, "rb").read()
c2 = raw2.count(b"\r\n")
assert c2 == 0, "写回后行尾被改了！"
print("写回后行尾仍是纯 LF √")
