#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端时段调度器 —— 单次 Actions run 内按精确时刻表驱动当日推送。

为什么需要它
------------
GitHub 对同一仓库的 schedule 触发存在系统性配额节流（本仓库实测每天约 17 次，
而 18 条 cron 理论应触发约 95 次），且早盘 08:20-09:30 连续多日整段被吞。
结果是"定时器明明配好了，早上就是没有推送"。

本脚本把"任意一次 schedule 命中"变成一个可以在云端连续存活数小时的调度进程：
在本次 run 内按分钟粒度准时驱动各槽位，从而不再依赖高频 cron 是否命中。
全程只需要 GITHUB_TOKEN（仓库自带），不需要任何外部 PAT 或外部定时服务。

安全设计
--------
1. 只在工作日交易时段运行：08:00-11:45（上午段）/ 13:00-15:45（下午段）
2. 是否重复推送由主程序内部 slot_done 去重兜住，本脚本不另设去重逻辑
3. 启动前检查 active marker：同一日同一段已有调度在跑时，本 run 立即退出，
   避免多条 cron 同时命中造成多个长循环并发（GitHub 排队时尤其重要）
4. 每个槽跑完立即落盘并 commit/push 状态，保证跨 run 的去重状态一致
5. 任何单槽异常都不中断循环，只记录日志（避免一处报错拖垮整天）
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time

BJ = datetime.timezone(datetime.timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'tools', 'data')
MARKER = os.path.join(DATA_DIR, 'sched_active.json')
PY = sys.executable or 'python3'

# ---------------------------------------------------------------- 时刻表
# (时, 分, 槽位, 允许延迟窗口分钟) —— 全部北京时间
FIXED_SLOTS = [
    (8, 20, 'warn', 20),       # 板块启动预警
    (8, 30, 'pre', 20),        # 盘前速递
    (9, 25, 'auction', 3),     # 竞价观察（严格 09:25-09:27，窗口只留 3 分钟）
    (10, 0, 'hourly', 20),     # 盘中解读
    (10, 30, 'newsfire', 20),  # 新闻发酵
    (10, 35, 'risk', 20),      # 风险体检
    (11, 0, 'hourly', 20),
    (11, 30, 'noon', 20),      # 午间作战
    (11, 40, 'news', 20),      # 午间事件简报
    (13, 0, 'hourly', 20),
    (13, 30, 'newsfire', 20),
    (13, 35, 'risk', 20),
    (14, 0, 'hourly', 20),
    (14, 5, 'follow', 20),     # 跟涨三步走·盘中
    (14, 55, 'tail', 20),      # 尾盘竞价筛选
    (15, 0, 'eod', 45),       # 收盘复盘（窗口放长，收盘后补跑）
    (15, 5, 'follow', 20),     # 跟涨三步走·收盘
    (15, 10, 'news', 20),      # 尾盘事件简报
    (15, 20, 'cycle', 20),     # 多周期视角研判
    (15, 35, 'news', 20),
]

WATCH_WINDOWS = ((9 * 60 + 15, 11 * 60 + 30), (13 * 60, 15 * 60 + 5))  # 09:15-11:30 / 13:00-15:05，午休不扫
WATCH_STEP = 15             # 每 15 分钟一次异动扫描


def log(msg: str) -> None:
    print(f'[SCHED] {msg}', flush=True)


def bj_now() -> datetime.datetime:
    return datetime.datetime.now(BJ)


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ['git'] + list(args), cwd=ROOT, capture_output=True,
            text=True, timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        log(f'git {" ".join(args)} 异常: {exc}')
        return subprocess.CompletedProcess(args, 1, '', str(exc))


def pull_latest() -> None:
    git('pull', '--rebase', '--autostash')


def persist_state(tag: str) -> None:
    """把工具写出的状态文件提交回仓库，保证跨 run 去重一致。"""
    git('add', 'tools/data/')
    diff = git('diff', '--cached', '--quiet')
    if diff.returncode == 0:
        return
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    git('commit', '-m', f'chore: 状态持久化({tag}) {stamp}')
    git('pull', '--rebase', '--autostash')
    git('push')


def acquire_segment(bj: datetime.datetime) -> bool:
    """占用当天当前段的调度权；已有活跃调度时返回 False。"""
    day = bj.strftime('%Y-%m-%d')
    seg = 'am' if bj.hour < 12 else 'pm'
    pull_latest()

    marker: dict = {}
    try:
        with open(MARKER, encoding='utf-8') as fh:
            marker = json.load(fh)
    except Exception:  # noqa: BLE001
        marker = {}

    if marker.get('date') == day and marker.get('seg') == seg:
        started = marker.get('started')
        try:
            started_ts = datetime.datetime.fromisoformat(started).timestamp()
        except Exception:  # noqa: BLE001
            started_ts = 0
        alive = (time.time() - started_ts) < 3.8 * 3600
        if alive:
            log(f'{day} {seg} 段已有调度在运行（起于 {started}），本 run 退出以免并发')
            return False
        log(f'发现 {day} {seg} 段的过期标记（{started}），接管')

    marker = {'date': day, 'seg': seg, 'started': bj.isoformat(timespec='seconds')}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MARKER, 'w', encoding='utf-8') as fh:
        json.dump(marker, fh, ensure_ascii=False)
    persist_state('sched-active')
    log(f'已占用 {day} {seg} 段调度权')
    return True


def run_slot(slot: str) -> None:
    t0 = time.time()
    log(f'>>> 执行槽位 {slot} @ {bj_now():%H:%M:%S}')
    try:
        proc = subprocess.run(
            [PY, '-u', 'tools/cloud_daily_review.py', '--time', slot],
            cwd=ROOT, capture_output=True, text=True, timeout=1500,
        )
        tail = (proc.stdout or '').strip().splitlines()[-40:]
        for line in tail:
            print(f'    | {line}', flush=True)
        if proc.returncode != 0:
            log(f'槽位 {slot} 返回码 {proc.returncode}')
            for line in (proc.stderr or '').strip().splitlines()[-15:]:
                print(f'    ! {line}', flush=True)
    except subprocess.TimeoutExpired:
        log(f'槽位 {slot} 执行超时（25 分钟），跳过')
    except Exception as exc:  # noqa: BLE001
        log(f'槽位 {slot} 异常: {exc}')
    try:
        persist_state(slot)
    except Exception as exc:  # noqa: BLE001
        log(f'状态落盘失败（{slot}）: {exc}')
    log(f'<<< 完成槽位 {slot}，用时 {time.time() - t0:.1f}s')


def pick_slot(now: datetime.datetime, executed: set) -> str | None:
    """判断此刻应执行哪个槽；不在任何时刻点则返回 None。"""
    day = now.strftime('%Y-%m-%d')
    minutes = now.hour * 60 + now.minute

    # 同一时刻可能落在多个窗口内（如 15:35 既在 eod 的长窗口、也在 news 的点位），
    # 取"离当前时间最近的那个时刻点"，避免宽窗口把后续槽位抢先吞掉。
    best: tuple[int, str, str] | None = None
    for hour, minute, slot, window in FIXED_SLOTS:
        start = hour * 60 + minute
        if start <= minutes <= start + window:
            token = f'{day}|{slot}|{hour:02d}{minute:02d}'
            if token in executed:
                continue
            lag = minutes - start
            if best is None or lag < best[0]:
                best = (lag, slot, token)
    if best is not None:
        executed.add(best[2])
        return best[1]

    in_watch = any(a <= minutes <= b for a, b in WATCH_WINDOWS)
    if in_watch and now.minute % WATCH_STEP == 0:
        token = f'{day}|watch|{minutes}'
        if token in executed:
            return None
        executed.add(token)
        return 'watch'

    return None


def segment_end(bj: datetime.datetime) -> datetime.datetime:
    if bj.hour < 12:
        return bj.replace(hour=11, minute=45, second=0, microsecond=0)
    return bj.replace(hour=15, minute=48, second=0, microsecond=0)


def main() -> int:
    bj = bj_now()
    log(f'启动调度器，当前北京时间 {bj:%Y-%m-%d %H:%M:%S} 星期{"一二三四五六日"[bj.weekday()]}')

    if bj.weekday() >= 5:
        log('周末不调度，退出')
        return 0

    in_am = 8 <= bj.hour < 12
    in_pm = 13 <= bj.hour < 16
    if not (in_am or in_pm):
        log('当前不在调度时段（08:00-11:45 / 13:00-15:45），本 run 直接退出')
        return 0

    if not acquire_segment(bj):
        return 0

    end = segment_end(bj)
    log(f'本段调度至 {end:%H:%M}，共可覆盖约 {(end - bj).total_seconds() / 60:.0f} 分钟')

    executed: set = set()
    while bj_now() < end:
        now = bj_now()
        slot = pick_slot(now, executed)
        if slot:
            run_slot(slot)
            continue
        time.sleep(15)

    log(f'本段调度结束（{bj_now():%H:%M}），退出')
    return 0


if __name__ == '__main__':
    sys.exit(main())
