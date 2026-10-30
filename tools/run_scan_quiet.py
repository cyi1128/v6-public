# -*- coding: utf-8 -*-
"""全市场扫描的静音包装。

为什么要它：
    主程序运行时 kline_cache.duckdb 被独占，引擎取不到本地缓存只能走在线源，
    每只股票都会打 2~3 行降级日志（[K线缓存] get_latest_kline 失败 /
    [KLINE PYTDX] ...无数据），3048 只 → 约 3500 行噪音，把有效信息淹没。

它做什么：
    以子进程方式跑 python -m services.band_pattern_engine，
    实时逐行过滤掉上述噪音行和空行，其余原样透传到 stdout（由 bat 重定向进日志）。
    扫描本身的逻辑、参数、结果一律不动。

用法：
    python tools/run_scan_quiet.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 命中任一关键词即视为噪音
NOISE_KEYS = (
    'get_latest_kline',      # [K线缓存] get_latest_kline(xxx) 失败: IO Error ...
    'already open in',       # IO Error 附带的 “File is already open in ... (PID xxxx)”
)

# 形如 [KLINE PYTDX] / [KLINE EM] / [KLINE SINA] ... 且带失败语义的行也算噪音。
# 注意：不能整类过滤 [KLINE xxx]，因为 “[KLINE HTTP] 000001 从腾讯获取320条(day)”
# 是有用的数据源信息，必须保留。
_RE_KLINE_NOISE = re.compile(
    r'\[KLINE [A-Z]+\].*(失败|无数据|降级|超时|timeout|error)', re.I)

# DuckDB 的 “File is already open in” 是多行错误：
#   File is already open in
#   C:\...\python.exe (PID 24664)      <-- 这一行只有路径 + PID，上面两条规则都抓不到
_RE_PID_PATH = re.compile(r'^[A-Za-z]:\\[^\n]*\(PID \d+\)\s*$')


def is_noise(line):
    """该行是否属于「K线取数降级」噪音。"""
    if any(k in line for k in NOISE_KEYS):
        return True
    if _RE_KLINE_NOISE.search(line):
        return True
    if _RE_PID_PATH.match(line.strip()):
        return True
    return False


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    env = dict(os.environ)
    env.setdefault('PYTHONIOENCODING', 'utf-8')

    proc = subprocess.Popen(
        [sys.executable, '-m', 'services.band_pattern_engine'],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', bufsize=1)

    n_noise = 0
    n_blank = 0
    for line in proc.stdout:
        if is_noise(line):
            n_noise += 1
            continue
        if not line.strip():
            n_blank += 1
            continue
        sys.stdout.write(line if line.endswith('\n') else line + '\n')
        sys.stdout.flush()
    proc.wait()

    if n_noise or n_blank:
        print('[日志降噪] 已过滤 K线缓存降级噪音 %d 行、空行 %d 行'
              % (n_noise, n_blank), flush=True)
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
