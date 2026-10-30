# -*- coding: utf-8 -*-
"""执行前探现状：主程序是否在跑 / 备份目录 / picks_tracking.duckdb 现状。"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"

print("=" * 78)
print("一、主程序是否在运行（会影响能否写 picks_tracking.duckdb）")
print("=" * 78)
try:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                       capture_output=True, timeout=30)
    out = r.stdout.decode("gbk", "ignore").strip()
    lines = [x for x in out.split("\n") if x.strip() and "python" in x.lower()]
    if lines:
        print("  发现 python.exe 进程 %d 个：" % len(lines))
        for x in lines:
            print("    %s" % x.strip()[:120])
    else:
        print("  没有 python.exe 在跑（可以安全写库）")
except Exception as e:
    print("  tasklist 调用失败：%s" % e)

print()
print("=" * 78)
print("二、现有还原点（backups\\backup_*）")
print("=" * 78)
bdir = os.path.join(ROOT, "backups")
if os.path.isdir(bdir):
    subs = sorted([d for d in os.listdir(bdir)
                   if d.startswith("backup_") and os.path.isdir(os.path.join(bdir, d))])
    for d in subs:
        p = os.path.join(bdir, d)
        n = sum(len(f) for _, _, f in os.walk(p))
        sz = 0
        for r_, _, fs in os.walk(p):
            for f in fs:
                try:
                    sz += os.path.getsize(os.path.join(r_, f))
                except OSError:
                    pass
        print("  %-32s %5d 文件 / %6.1f MB" % (d, n, sz / 1024 / 1024))
    print("  共 %d 份（backup.py 只保留最近 10 份）" % len(subs))
else:
    print("  backups 目录不存在")
for d in sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []:
    if "removed" in d:
        print("  [隔离区] %s" % d)

print()
print("=" * 78)
print("三、picks_tracking.duckdb 现状")
print("=" * 78)
db = os.path.join(ROOT, "data", "cache", "picks_tracking.duckdb")
if os.path.exists(db):
    print("  路径 %s" % db)
    print("  大小 %.2f MB  修改时间 %s" % (
        os.path.getsize(db) / 1024 / 1024,
        __import__("datetime").datetime.fromtimestamp(os.path.getmtime(db)).strftime("%Y-%m-%d %H:%M:%S")))
    try:
        import duckdb
        con = duckdb.connect(db, read_only=True)
        tabs = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        print("  表：%s" % tabs)
        for t in tabs:
            cnt = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            print("    %-22s %6d 行" % (t, cnt))
        con.close()
    except Exception as e:
        print("  读取失败（可能被占用）：%s: %s" % (type(e).__name__, str(e)[:120]))
else:
    print("  不存在（还没回填过）")

print()
print("=" * 78)
print("四、--backfill 入口确认")
print("=" * 78)
s = io.open(os.path.join(ROOT, r"services\picks_tracking_service.py"), encoding="utf-8-sig").read()
for i, t in enumerate(s.split("\n"), 1):
    if "backfill" in t.lower() and ("def " in t or "--backfill" in t or "BACKFILL_DAYS" in t):
        print("  L%-5d %s" % (i, t.strip()[:110]))
