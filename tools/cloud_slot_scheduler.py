#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端时段调度器 v2 —— 全天候闭环版（2026-11-07 改造）

为什么要 v2
-----------
v1 只在 08:00-11:45 / 13:00-15:48 两段长驻，时段外（12:00·14:01·16:00 两小时汇总、
21:38·22:38 外盘、22:50 晚间）全部裸靠 cron 触发；而 GitHub 对本仓库的 schedule
存在系统性延迟与丢弃（实测 cron 名义时刻与 run 实际启动时刻相差数小时），导致：
  1. push job 的 `case $H:$M` 按"启动时刻"判槽 → 延迟后判错槽或判成 watch；
  2. 上午 08:20/08:30/10:00 与收盘 15:00 常年整段缺失（11-06 实测缺 warn/pre/hourly10/eod）；
  3. 周末 11-07 全天 0 次 schedule，休市日新闻彻底断供。

v2 的三条改造
-------------
1. 判槽不再看"run 启动时刻"，只看"现在北京时间该跑什么 + 今天还欠什么"——
   任何一次 cron 命中（哪怕延迟到 10:00）都能把欠的槽补齐（受补跑宽容窗约束）。
2. 时刻表扩到全天：08:20 … 22:50，含 12:00/14:01/16:00 news2h、21:38/22:38 ext、22:50 evening。
3. 判槽权威唯一：起点用"滚动占段"而非固定三段班次（见下节）。

滚动占段（2026-11-07 二次改造，替代原来的 am/pm/night 三段）
------------------------------------------------------------
原三段班次的毛病：11-06 真实发生的 17:15 与 21:06 两次触发，被 pm 的 16:30 结束
和 night 的 21:15 开始这两条边界挡在门外，收盘复盘与晚间外盘整段丢失。
现在的规则：
  · 启动门槛 = "接下来这个滚动窗口里还有没有待跑槽"，不是"现在在不在班次里"；
  · 有槽就占段，吃满 ROLL_MINUTES=300 分钟，段尾 ROLL_TAIL_MINUTES=45 分钟内
    能接上下一槽就顺延（上限 DAY_END 23:55）；
  · 正常退出清 marker，排队中的同类 run 立刻接手（concurrency 串行 + 不清 marker
    会被 seg_end+600s 宽限白白挡住）；
  · 无槽则秒退且不提交状态，不白占 runner。
副产物：凌晨触发的 run 会一路守到早盘第一个槽，早盘不必再赌一次 cron。

补跑（backfill）
----------------
启动时先扫描"名义时刻已到、且仍在宽容窗内、但 slot_done 里没有"的槽，按时间顺序补跑。
宽容窗按槽分档：auction 只有 2 分钟（竞价数据有时效，宁缺毋滥），warn/pre 60 分钟、
eod 120 分钟、其余 60 分钟。超窗不补——宁可缺口，也不推过时内容。

并发安全
--------
1. 班次 marker（tools/data/sched_active.json）：同一天同一班次已有存活调度时本 run 秒退；
   存活判定按"班次结束时刻 + 10 分钟"计算，不再用固定 3.8 小时（pm 段 4.5 小时会被误判过期）。
2. 重复推送最终由主程序内部 slot_done / eod_status.json 兜住，本脚本不另设内容去重。
3. 每个槽跑完立即 git add tools/data/ + commit + pull --rebase + push，跨 run 状态一致。

自检
----
`python3 cloud_slot_scheduler.py --selftest` 用注入的固定时刻跑判定逻辑，
不联网、不推送，输出每个场景应选槽位与补跑清单，全 PASS 才退出 0。
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
# 本 run 的段名（acquire_segment 成功后写入）；_touch_marker 靠它判断
# 「这份标记还是我的吗」——不是我的就一个字节都不许改。
_CUR_SEG = ''
_CUR_DATE = ''
SLOT_DONE = os.path.join(DATA_DIR, 'slot_done.json')
# 收盘复盘另用一套去重：主程序 eod_push_done() 读的是仓库根 data/eod_status.json
# （结构 {"date": "YYYY-MM-DD", "pushed_at": ...}），不是 tools/data/slot_done.json。
EOD_STATUS = os.path.join(ROOT, 'data', 'eod_status.json')
PY = sys.executable or 'python3'

# ---------------------------------------------------------------- 全天时刻表
# (时, 分, 槽位, 准时窗口分钟, 补跑宽容分钟) —— 全部北京时间
# 准时窗口：该槽在此区间内被选中的"正点"范围
# 补跑宽容：迟到超过该分钟数不再补跑（避免把盘前内容推到盘中）
FIXED_SLOTS = [
    (8, 20, 'warn', 20, 60),       # 板块启动预警（消息面版）
    (8, 30, 'pre', 20, 60),        # 盘前速递
    (9, 25, 'auction', 3, 2),      # 竞价观察：严格 09:25-09:27，超窗绝不补
    (9, 35, 'open', 5, 10),       # 开盘验证·30分钟定调（过点不补：10 分钟后已没意义）
    (10, 0, 'hourly', 20, 60),     # 盘中解读
    (10, 30, 'newsfire', 20, 60),  # 新闻发酵
    (10, 35, 'risk', 20, 60),      # 风险体检（绿档静默）
    (11, 0, 'hourly', 20, 60),
    (11, 30, 'noon', 20, 60),      # 午间作战
    (11, 40, 'news', 20, 60),      # 午间事件简报
    (10, 0, 'news2h', 20, 60),     # 两小时消息汇总（上午首档，v80-A13 补：全天每 2 小时）
    (12, 0, 'news2h', 20, 60),     # 两小时消息汇总（午间，原先裸靠 cron）
    (13, 5, 'pmopen', 5, 15),     # 午后接力·钱往哪去（过点不补，别撞 13:30 newsfire）
    (13, 0, 'hourly', 20, 60),
    (13, 30, 'newsfire', 20, 60),
    (13, 35, 'risk', 20, 60),
    (14, 0, 'hourly', 20, 60),
    (14, 1, 'news2h', 4, 60),      # 两小时消息汇总（午后，窗口窄防抢 hourly）
    (10, 35, 'follow', 20, 40),    # 跟涨三步走·盘中一档（开盘一小时后首批补涨刚启动，埋伏来得及）
    (14, 30, 'preclose', 5, 10),  # 尾盘前决策·过不过夜（过点不补，15:00 后再推是废卡）
    (14, 55, 'tail', 20, 60),      # 尾盘竞价筛选
    (15, 0, 'eod', 45, 120),       # 收盘复盘（窗口长，允许补跑）
    (13, 35, 'follow', 20, 40),    # 跟涨三步走·盘中二档（午后第一波，收盘后不再推：过了买点是废话）
    (15, 10, 'news', 20, 60),      # 尾盘事件简报
    (15, 20, 'cycle', 20, 60),     # 多周期视角研判
    (15, 35, 'news', 20, 60),      # 尾盘事件简报
    (16, 0, 'news2h', 20, 90),     # 16:00 两小时消息汇总（原先裸靠 cron）
    (18, 0, 'news2h', 20, 90),     # 18:00 两小时消息汇总（v80-A13 补）
    (20, 0, 'news2h', 20, 90),     # 20:00 两小时消息汇总（v80-A13 补）
    (22, 0, 'news2h', 20, 90),     # 22:00 两小时消息汇总（v80-A13 补）
    (21, 38, 'ext', 10, 40),       # 外盘窗口（原先裸靠 cron）
    (22, 38, 'ext', 10, 40),
    (22, 50, 'evening', 20, 60),   # 晚间消息汇总（原先裸靠 cron）
]

# 班次：(起, 止, 名称) 分钟制
SESSIONS = [
    (8 * 60 + 0, 11 * 60 + 45, 'am'),
    (12 * 60 + 0, 16 * 60 + 30, 'pm'),
    (21 * 60 + 15, 23 * 60 + 10, 'night'),
]

WATCH_WINDOWS = ((9 * 60 + 15, 11 * 60 + 30), (13 * 60, 15 * 60 + 5))  # 午休不扫
WATCH_STEP = 15             # 每 15 分钟一次异动扫描

SLOT_TIMEOUT = 900          # 全局兜底：单槽 15 分钟（主程序行情请求自带超时）

# 每槽预算（2026-11-09 新增）：(LLM 总预算秒, 单模型超时秒, 子进程硬超时秒)
# 依据：ModelScope 首轮全超时约 45s × 5 个备选 = 225s/次，串 3~4 个 purpose 就是 10~15 分钟。
# 时限卡的槽（auction/pre/tail/eod）必须把 LLM 预算压到「一轮就够」，慢就降级成代码结论。
# 2026-11-09 v11：单模型超时 45s -> 60s。
# 实测 ModelScope 免费队列上，health 这种短请求 27s 能回，但卡面要的长正文（暗线深挖）
# 45s 内生成不完 -> 一律 tag=timeout -> 卡面退回代码数据行，用户判定为「规则化」。
# 2026-11-09 v12：用户指令「不要限制时间」。
# 45~75s 的单模型超时会把长正文生成一刀砍断 -> 全 tag=timeout -> 卡面退回代码行（「规则化」）。
# 除竞价（业务窗口只有 2 分钟）和 watch（15 分钟一扫）外，全部放开到 30~40 分钟。
SLOT_BUDGET = {
    'auction': (150, 40, 240),     # 09:25 起跑，2 分钟内必须出卡，业务硬窗口
    'pre':     (1800, 300, 2400),  # 08:30 起跑
    'warn':    (1800, 300, 2400),  # 08:20 起跑
    'watch':   (600, 120, 750),    # 15 分钟一扫，给 12 分钟封顶
    'open':     (1200, 300, 1500),  # 09:35 起跑，10:00 hourly 之前落地
    'pmopen':   (900, 300, 1200),   # 13:05 起跑，13:30 newsfire 之前落地
    'preclose': (900, 300, 1200),   # 14:30 起跑，14:50 前后必须落地（过夜决策不能拖
    'hourly':  (1800, 300, 2400),
    'tail':    (900, 300, 1200),   # 14:55 起跑，15:05 前落地
    'eod':     (2400, 300, 3000),  # 收盘复盘数据量大，放到 40 分钟
    'noon':    (1800, 300, 2400),
    'news':    (1800, 300, 2400),
    'news2h':  (1800, 300, 2400),
    'newsfire': (1800, 300, 2400),
    'risk':    (1200, 300, 1500),
    'follow':  (1800, 300, 2400),
    'cycle':   (1800, 300, 2400),
    'ext':     (1200, 300, 1500),
    'evening': (1800, 300, 2400),
}
DEFAULT_BUDGET = (1800, 300, 2400)


def slot_budget(slot: str) -> tuple[int, int, int]:
    """取该槽的 (LLM 总预算, 单模型超时, 子进程硬超时)。"""
    return SLOT_BUDGET.get(slot, DEFAULT_BUDGET)
SEG_ALIVE_GRACE = 600
# 2026-11-09：段心跳。调度器每落地一个槽就刷新 hb；hb 超过这个秒数没动就判死段。
# 45 分钟 = 最长槽间隔（16:00 -> 次日 08:20 之外，最长的盘中空档约 30 分钟）的两倍余量。
SEG_HB_STALE = 2700       # 正常退出会清 marker，这里只是兜住"被 timeout 杀掉"的情况
ROLL_MINUTES = 350          # 滚动占段时长：一次触发覆盖未来 5.8 小时（+ 启动开销仍在 380 timeout 内）
ROLL_TAIL_MINUTES = 45      # 段尾 45 分钟内若还能接上下一槽，就把终点延到那槽窗口末端
DAY_END = (23, 55)          # 今日收工时刻（之后不再占段）
EARLY_GUARD = (9, 30)       # 凌晨/深夜命中一律守到早盘竞价（09:25）跑完，不让早盘整段靠下一次运气


LOG_PATH = os.path.join(DATA_DIR, 'sched_log.txt')
LOG_KEEP = 400              # 只保留最近 400 行（约一周的一天内多段运行轨迹），避免仓库状态文件膨胀
LOG_TO_FILE = '--selftest' not in sys.argv   # 自检不落盘，避免污染仓库状态


_LOG_BUF: list[str] = []
_LOG_INITED = False


def log(msg: str) -> None:
    """同时打 stdout 和落盘 tools/data/sched_log.txt。

    落盘目的：云端 job 日志匿名 API 取不到（403/404），把判定过程写进仓库，
    用 git fetch 就能读到云端真实执行轨迹（每次状态持久化会一并提交）。
    实现要点：以内存 _LOG_BUF 为唯一真源，每次整体覆写文件。
    主程序内部的 `git pull --rebase --autostash` 会动工作区，读文件再追加
    会丢行；整体覆写才能保证云端日志不残缺（11-07 实测只落下首行的教训）。
    """
    global _LOG_INITED
    stamp = datetime.datetime.now(BJ).strftime('%m-%d %H:%M:%S')
    print(f'[SCHED] {msg}', flush=True)
    if not LOG_TO_FILE:
        return
    # 2026-11-09 改追加写：原「内存缓冲整体覆写」在多 run 并发时互相抹行，
    # auction / warn 这类关键执行痕迹在仓库里查不到。追加单行不会互删。
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as fh:
            fh.write(f'{stamp} {msg}\n')
        _LOG_INITED = True
        _trim_log()
    except Exception:  # noqa: BLE001  日志落盘失败绝不能影响调度
        pass


def bj_now() -> datetime.datetime:
    return datetime.datetime.now(BJ)


def minutes_of(now: datetime.datetime) -> int:
    return now.hour * 60 + now.minute


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ['git'] + list(args), cwd=ROOT, capture_output=True,
            # v13：原 120s。状态推送失败会重试多轮，120s 一轮能把整个时刻表卡死
            # （实测 13:56:53 接管后零日志 10 分钟，14:00 hourly 整槽消失）。
            text=True, timeout=25,
        )
    except Exception as exc:  # noqa: BLE001
        log(f'git {" ".join(args)} 异常: {exc}')
        return subprocess.CompletedProcess(args, 1, '', str(exc))


def pull_latest() -> None:
    """拉远端最新；失败（rebase 冲突 / autostash pop 失败 / 网络）立刻自愈。

    不自愈的后果：工作区留在 rebase in-progress，之后每次 pull 都 120s 超时，
    _read_json 读到冲突标记后一律返回 {}，心跳再也刷不上，段静默失活。
    """
    r = git('pull', '--rebase', '--autostash')
    if r.returncode == 0:
        return
    out = ((r.stdout or '') + (r.stderr or '')).strip()
    log(f'pull 失败，自愈：{out[:120]}')
    # v14：原序列解不开 "unmerged files"（14:09:49 实测就死在这里，后面所有槽都不跑）。
    # 补 merge --abort 与 reset --hard origin/main 两级；tools/data 的状态丢了下一 tick 会重写。
    for _cmd in (('rebase', '--abort'), ('merge', '--abort'), ('rebase', '--quit'),
                 ('checkout', '--', 'tools/data'),
                 ('reset', '--hard', 'origin/main')):
        try:
            git(*_cmd)
        except Exception:  # noqa: BLE001
            pass


def _trim_log() -> None:
    """日志超长时只保留最近 LOG_KEEP 行；读全量再写回，失败就算了。"""
    try:
        if os.path.getsize(LOG_PATH) <= 160000:
            return
        with open(LOG_PATH, encoding='utf-8') as fh:
            lines = fh.readlines()
        if len(lines) <= LOG_KEEP:
            return
        with open(LOG_PATH, 'w', encoding='utf-8') as fh:
            fh.writelines(lines[-LOG_KEEP:])
    except Exception:  # noqa: BLE001
        pass


def _flush_log() -> None:
    """把缓冲里剩下的行补写进文件（追加模式下缓冲基本为空，仅作兜底）。"""
    try:
        if LOG_TO_FILE and _LOG_BUF:
            with open(LOG_PATH, 'a', encoding='utf-8') as fh:
                fh.writelines(_LOG_BUF)
            _LOG_BUF.clear()
    except Exception:  # noqa: BLE001  日志落盘失败绝不能影响调度
        pass


def _touch_marker() -> None:
    """刷新段标记心跳——只在本段还持有该标记时才改。

    2026-11-09 事故修复：原来不看归属，run 本地读到的是自己启动时留下的旧 seg，
    一路把接管者的 seg 覆盖回自己，两个段互相踩、双双退出，整段时间表空转
    （11:30 noon / 11:40 news 就是这样丢的）。现在先拿远端最新标记，
    只要 seg 不是本段就原样不动。
    """
    try:
        if not _CUR_SEG:
            return
        pull_latest()
        m = _read_json(MARKER)
        if (m.get('seg') or '') != _CUR_SEG or (m.get('date') or '') != _CUR_DATE:
            return
        m['hb'] = bj_now().isoformat(timespec='seconds')
        with open(MARKER, 'w', encoding='utf-8') as fh:
            json.dump(m, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


HEARTBEAT_GAP = 900        # 空转期心跳间隔（秒）；必须小于 SEG_HB_STALE


def heartbeat() -> None:
    """空转期独立刷一次段心跳：只在本段仍持有标记时才写，写后提交推送。

    2026-11-09 事故：心跳原来只跟着 persist_state 走，11:43 跑完 news 到 12:00
    之间没有槽，45 分钟不刷心跳，段被判死、12:00 news2h 整槽消失。
    """
    if not _CUR_SEG:
        return
    try:
        pull_latest()
        m = _read_json(MARKER)
        if (m.get('seg') or '') != _CUR_SEG or (m.get('date') or '') != _CUR_DATE:
            log(f'心跳跳过：段标记已不是本段（{m.get("seg") or "空"}）')
            return
        _hb = bj_now().isoformat(timespec='seconds')
        if (m.get('hb') or '')[:16] == _hb[:16]:
            return
        m['hb'] = _hb
        with open(MARKER, 'w', encoding='utf-8') as fh:
            json.dump(m, fh, ensure_ascii=False)
        git('add', 'tools/data/sched_active.json')
        if git('diff', '--cached', '--quiet').returncode == 0:
            return
        git('config', 'user.email', 'v6-bot@users.noreply.github.com')
        git('config', 'user.name', 'v6-bot')
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if git('commit', '-m', f'chore: 心跳 {stamp}').returncode != 0:
            return
        r = git('push', 'origin', 'HEAD:main')
        out = ((r.stdout or '') + (r.stderr or '')).strip()
        if r.returncode == 0 and 'Everything up-to-date' not in out:
            log(f'心跳已刷新至 {_hb}')
        else:
            log(f'心跳推送失败：{out[:120]}')
    except Exception as _e:  # noqa: BLE001
        log(f'心跳异常：{_e}')


def persist_state(tag: str) -> None:
    """把工具写出的状态文件提交回仓库，保证跨 run 去重一致。

    提交前必须先用内存日志重写文件：主程序的 `git pull --rebase --autostash`
    撞上远端并发的 sched_log 改动时，autostash pop 会失败并把工作区文件退回
    HEAD 版本（改动留在 stash），此时 add + diff 判定为"无改动"直接返回，
    「退出原因」「今日缺口」这类关键判定行就永远进不了仓库。
    """
    _flush_log()
    _touch_marker()
    git('add', 'tools/data/')
    diff = git('diff', '--cached', '--quiet')
    if diff.returncode == 0:
        log(f'持久化({tag})：无可提交改动')
        return
    # CI runner 的 git 身份常常是空的，此时 commit 会直接失败；而 commit 失败后
    # 再 push 只会得到 "Everything up-to-date"（returncode 仍是 0），于是被误判成
    # 推送成功——这是「日志写已推送、远端一个字节没变」的真正原因。三处都要收紧。
    git('config', 'user.email', 'v6-bot@users.noreply.github.com')
    git('config', 'user.name', 'v6-bot')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    c = git('commit', '-m', f'chore: 状态持久化({tag}) {stamp}')
    if c.returncode != 0:
        log(f'持久化({tag})：提交失败 {((c.stderr or c.stdout or "").strip())[:140]}')
        return
    # v15：v13 砍成 1 轮后，撞上「远端已被别人先推」就直接放弃，
    # slot_done 丢键 -> 下一个 run 补跑 -> 重复推送（14:42 实测 ! [rejected] fetch first）。
    # 改成 2 轮：第一轮失败先 pull --rebase 再推。最坏 75 秒，仍不会卡死时刻表。
    for attempt in (1, 2):
        r = git('push', 'origin', 'HEAD:main')
        out = ((r.stdout or '') + (r.stderr or '')).strip()
        if r.returncode == 0 and 'Everything up-to-date' not in out:
            log(f'持久化({tag})：已推送')
            return
        log(f'状态推送失败（第{attempt}次）：{out[:160]}')
        git('pull', '--rebase', '--autostash', 'origin', 'main')


# ---------------------------------------------------------------- 状态判定
def _read_json(path: str) -> dict:
    try:
        with open(path, encoding='utf-8') as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def slot_done_key(hour: int, minute: int, slot: str) -> str | None:
    """与主程序 cloud_daily_review.py 完全一致的窗口键（写错就会重复推或漏推）。"""
    today = bj_now().strftime('%Y-%m-%d')
    if slot == 'hourly':
        return 'hourly|%s|%02d' % (today, hour)
    if slot == 'risk':
        return 'risk|%s|%s' % (today, '1035' if hour == 10 else '1335')
    if slot == 'news':
        tag = {(11, 40): '1140', (15, 10): '1510', (15, 35): '1535'}.get((hour, minute))
        return 'news|%s|%s' % (today, tag) if tag else None
    if slot == 'follow':
        tag = {(10, 35): '1035', (13, 35): '1335'}.get((hour, minute))
        return 'follow|%s|%s' % (today, tag) if tag else None
    if slot == 'ext':
        tag = {(21, 38): '2135', (22, 38): '2235'}.get((hour, minute))
        return 'ext|%s|%s' % (today, tag) if tag else None
    if slot == 'news2h':
        tag = {(12, 0): '1200', (14, 1): '1400', (16, 0): '1600'}.get((hour, minute))
        return 'news2h|%s|%s' % (today, tag) if tag else None
    return '%s|%s' % (slot, today)


def is_done(hour: int, minute: int, slot: str, done: dict | None = None) -> bool:
    """该槽今天是否已完成。eod 用独立 eod_status.json（主程序就是这么判的）。"""
    if slot == 'eod':
        st = _read_json(EOD_STATUS)
        return st.get('date') == bj_now().strftime('%Y-%m-%d')
    key = slot_done_key(hour, minute, slot)
    if key is None:
        return False
    if done is None:
        done = _read_json(SLOT_DONE)
    return bool(done.get(key))


# ---------------------------------------------------------------- 选槽
def pick_slot(now: datetime.datetime, executed: set) -> str | None:
    """此刻该跑哪个"正点"槽；不在任何时刻点返回 None。

    多个窗口重叠时取"离时刻点最近"的，避免宽窗口（如 eod 45 分钟）抢先吞掉后续槽。
    """
    day = now.strftime('%Y-%m-%d')
    minutes = minutes_of(now)

    best: tuple[int, str, str] | None = None
    for hour, minute, slot, window, _late in FIXED_SLOTS:
        start = hour * 60 + minute
        if start <= minutes <= start + window:
            token = f'{day}|{slot}|{hour:02d}{minute:02d}'
            if token in executed:
                continue
            lag = minutes - start
            if best is None or lag < best[0]:
                best = (lag, slot, token)

    # 异动扫描点（:00/:15/:30/:45）与正点槽重叠时的优先级：
    #   1) 恰在正点槽起点（lag==0，如 13:00 hourly / 15:00 eod）→ 先跑正点槽；
    #   2) 否则先跑 watch——否则 hourly 的 20 分钟窗口会把 :15 那次扫描整段吞掉
    #      （这正是 v1 每天漏 10:15/11:15/13:15/14:15 四次扫描的原因）。
    in_watch = any(a <= minutes <= b for a, b in WATCH_WINDOWS)
    watch_due = in_watch and now.minute % WATCH_STEP == 0
    watch_taken = f'{day}|watch|{minutes}' in executed

    if watch_due and not watch_taken and (best is None or best[0] > 0):
        executed.add(f'{day}|watch|{minutes}')
        return 'watch'
    if best is not None:
        executed.add(best[2])
        return best[1]
    return None


def plan_of(slot: str, now: datetime.datetime) -> tuple[int | None, int | None]:
    """按当前时刻反查该槽的「计划时刻」。同一 slot 有多档（news2h 12:00/14:01/16:00、
    hourly 多次）时，取当前落在其窗口内且离起点最近的那条。查不到返回 (None, None)。"""
    minutes = minutes_of(now)
    best = None
    for hour, minute, s, window, _late in FIXED_SLOTS:
        if s != slot:
            continue
        start = hour * 60 + minute
        if start <= minutes <= start + window:
            lag = minutes - start
            if best is None or lag < best[0]:
                best = (lag, hour, minute)
    if best is None:
        return None, None
    return best[1], best[2]


def pending_within(now: datetime.datetime, end: datetime.datetime, executed: set, done: dict | None = None) -> bool:
    """(now, end] 内是否还有待跑的槽位（含补跑宽容窗与异动扫描点）。

    用途：滚动占段不能空转。本段尾部若已没有任何待跑槽（例如 15:40 之后既无
    正点槽、尾盘扫描也收工），就提前把调度权让出来，省一个 runner 的时间，
    也让后一个触发的 run 能立刻接手。
    """
    m0, m1 = minutes_of(now), minutes_of(end)
    day = now.strftime('%Y-%m-%d')
    if done is None:
        done = _read_json(SLOT_DONE)

    for hour, minute, slot, window, late in FIXED_SLOTS:
        start = hour * 60 + minute
        if start > m1:
            continue
        if start + max(window, late) < m0:
            continue
        token = f'{day}|{slot}|{hour:02d}{minute:02d}'
        if token in executed:
            continue
        if is_done(hour, minute, slot, done):
            continue
        return True

    for a, b in WATCH_WINDOWS:
        lo, hi = max(a, m0), min(b, m1)
        if lo > hi:
            continue
        t = ((lo + WATCH_STEP - 1) // WATCH_STEP) * WATCH_STEP
        if t <= lo:
            t += WATCH_STEP
        while t <= hi:
            if f'{day}|watch|{t}' not in executed:
                return True
            t += WATCH_STEP
    return False


def report_new_misses(executed: set, missed: set, done: dict | None = None) -> None:
    """跑的过程中就把「已过宽容窗还没推」的槽记下来。

    旧版只在进程退出时统计一次，上午漏了 hourly 要等到下午收盘退出才看得见；
    用户问「到底按时没按时」，要能在当场留下痕迹。
    """
    now = bj_now()
    m = minutes_of(now)
    day = now.strftime('%Y-%m-%d')
    if done is None:
        done = _read_json(SLOT_DONE)
    for hour, minute, slot, _window, late in FIXED_SLOTS:
        start = hour * 60 + minute
        if start + late >= m:
            continue                      # 仍在宽容窗内，不算漏
        token = f'{day}|{slot}|{hour:02d}{minute:02d}'
        if token in missed or token in executed:
            continue
        missed.add(token)
        if is_done(hour, minute, slot, done):
            continue
        log('漏推留痕：%02d:%02d %s 已过宽容窗 %d 分钟仍未推送' % (hour, minute, slot, late))


def backfill_pending(now: datetime.datetime, executed: set, done: dict | None = None) -> list[tuple[int, int, str]]:
    """启动补跑：名义时刻已到、仍在宽容窗内、但今天还没推的槽，按时间顺序返回。"""
    minutes = minutes_of(now)
    day = now.strftime('%Y-%m-%d')
    todo: list[tuple[int, int, int, str]] = []
    for hour, minute, slot, _window, late in FIXED_SLOTS:
        start = hour * 60 + minute
        if not (start <= minutes <= start + late):
            continue
        token = f'{day}|{slot}|{hour:02d}{minute:02d}'
        if token in executed:
            continue
        if is_done(hour, minute, slot, done):
            continue
        todo.append((start, hour, minute, slot))
    todo.sort()
    out: list[tuple[int, int, str]] = []
    for start, hour, minute, slot in todo:
        executed.add(f'{day}|{slot}|{hour:02d}{minute:02d}')
        out.append((hour, minute, slot))
        log(f'补跑待执行：{hour:02d}:{minute:02d} {slot}（已迟到 {minutes - start} 分钟）')
    return out


# ---------------------------------------------------------------- 执行
def run_slot(slot: str, hour: int | None = None, minute: int | None = None) -> None:
    t0 = time.time()
    log(f'>>> 执行槽位 {slot} @ {bj_now():%H:%M:%S}')
    llm_budget, ms_timeout, proc_cap = slot_budget(slot)
    env = dict(os.environ)
    env['LLM_TOTAL_BUDGET'] = str(llm_budget)
    env['MS_TIMEOUT'] = str(ms_timeout)
    env['V6_SLOT'] = slot
    # v10：把计划槽时刻交给主程序，去重键必须按计划槽写（否则迟到补跑写成实际时刻，
    # 下一段查不到就再补跑一次——12:18 与 12:27 同一 12:00 news2h 推两张卡的根因）
    if hour is not None and minute is not None:
        env['V6_SLOT_AT'] = '%02d%02d' % (hour, minute)
        log(f'>>> 计划槽时刻 {env["V6_SLOT_AT"]}（去重键按此生成，防补跑重复推）')
    log(f'>>> 预算：LLM {llm_budget}s / 单模型 {ms_timeout}s / 子进程上限 {proc_cap}s')
    try:
        proc = subprocess.run(
            [PY, '-u', 'tools/cloud_daily_review.py', '--time', slot],
            cwd=ROOT, capture_output=True, text=True, timeout=proc_cap, env=env,
        )
        tail = (proc.stdout or '').strip().splitlines()[-40:]
        for line in tail:
            print(f'    | {line}', flush=True)
        # 关键行落盘：云端 job 日志取不到，这几行是"到底推没推"的唯一云端证据
        key_hits = [ln.strip() for ln in tail
                    if any(k in ln for k in ('SLOT', 'PUSH', 'Traceback', 'Error', '异常', '跳过', '已推送', 'FAIL'))]
        for ln in key_hits[-6:]:
            log(f'    {slot}| {ln[:170]}')
        if proc.returncode != 0:
            log(f'槽位 {slot} 返回码 {proc.returncode}')
            for line in (proc.stderr or '').strip().splitlines()[-15:]:
                print(f'    ! {line}', flush=True)
    except subprocess.TimeoutExpired:
        log(f'槽位 {slot} 撞到子进程硬上限 {proc_cap}s，跳过（下个槽不会被它拖住）')
    except Exception as exc:  # noqa: BLE001
        log(f'槽位 {slot} 异常: {exc}')
    try:
        persist_state(slot)
    except Exception as exc:  # noqa: BLE001
        log(f'状态落盘失败（{slot}）: {exc}')
    log(f'<<< 完成槽位 {slot}，用时 {time.time() - t0:.1f}s')


# ---------------------------------------------------------------- 并发占段
def acquire_segment(bj: datetime.datetime, seg: str, seg_end: datetime.datetime) -> bool:
    """占用当天该班次的调度权；已有存活调度时返回 False。

    存活判定：now < 该班次记录的 seg_end + 10 分钟。这样 pm 段（4.5 小时）不会被
    固定 3.8 小时阈值误判成"过期"从而被第二个 run 接管造成并发双推。
    """
    day = bj.strftime('%Y-%m-%d')
    pull_latest()

    marker = _read_json(MARKER)
    mday = marker.get('date')
    raw_end = marker.get('seg_end') or ''
    try:
        end_ts = datetime.datetime.fromisoformat(raw_end).timestamp()
    except Exception:  # noqa: BLE001
        end_ts = 0
    # 2026-11-09 修：原来还要求 marker['seg'] == 本次 seg，但段名是按启动时刻起的
    # （roll-0841 / roll-1002），两个 run 永远对不上，等于「谁都能占段」，
    # 结果 08:41 与 10:02 两个调度同时驱动时刻表 → 同槽重复推送。
    # 现在只看「同一天 + 段还没过期」。
    hb_raw = marker.get('hb') or ''
    try:
        hb_ts = datetime.datetime.fromisoformat(hb_raw).timestamp()
    except Exception:  # noqa: BLE001
        hb_ts = 0
    in_window = bool(mday == day and end_ts and time.time() < end_ts + SEG_ALIVE_GRACE)
    dead = bool(in_window and hb_ts and (time.time() - hb_ts) > SEG_HB_STALE)
    if in_window and not dead:
        log(f'{day} 已有调度在运行（{marker.get("seg")} 止于 {raw_end}，心跳 {hb_raw or "无"}），本 run 退出以免并发双推')
        return False
    if dead:
        log(f'{day} 段 {marker.get("seg")} 心跳停在 {hb_raw}（超过 {SEG_HB_STALE // 60} 分钟），判定死段，接管')
    if mday == day and raw_end:
        log(f'发现 {day} 段的过期标记（{marker.get("seg")} 止于 {raw_end}），接管')

    marker = {
        'date': day,
        'seg': seg,
        'started': bj.isoformat(timespec='seconds'),
        'seg_end': seg_end.isoformat(timespec='seconds'),
        'hb': bj.isoformat(timespec='seconds'),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MARKER, 'w', encoding='utf-8') as fh:
        json.dump(marker, fh, ensure_ascii=False)
    global _CUR_SEG, _CUR_DATE
    _CUR_SEG, _CUR_DATE = seg, day
    persist_state('sched-active')
    log(f'已占用 {day} {seg} 段调度权（至 {seg_end:%H:%M}）')
    return True


def rolling_end(bj: datetime.datetime) -> datetime.datetime:
    """滚动段终点：先吃满 ROLL_MINUTES；若段尾紧邻下一个槽（≤ROLL_TAIL_MINUTES），
    把终点延到那个槽的窗口末端。

    为什么需要这个延伸：17:45 触发的 run 死板算 5 小时会正好停在 22:45，
    把 22:50 的晚间消息汇总截在段外——它只能等下一个人恰好触发，等于白等。
    """
    day_end = bj.replace(hour=DAY_END[0], minute=DAY_END[1], second=0, microsecond=0)
    # 凌晨/天没亮就命中：直接守到早盘 09:30（受 ROLL_MINUTES 上限约束）。
    # 这是"平台一天只给 1-7 次命中、且多半落在深夜"下唯一能把早盘 8:20/8:30/9:25 兜住的办法。
    if bj.hour < 8:
        guard = bj.replace(hour=EARLY_GUARD[0], minute=EARLY_GUARD[1], second=0, microsecond=0)
        return min(bj + datetime.timedelta(minutes=ROLL_MINUTES), guard)
    end = min(bj + datetime.timedelta(minutes=ROLL_MINUTES), day_end)
    if end >= day_end:
        return end
    m_end = minutes_of(end)
    best: int | None = None
    for hour, minute, _slot, window, _late in FIXED_SLOTS:
        start = hour * 60 + minute
        if start <= m_end:
            continue
        if start - m_end > ROLL_TAIL_MINUTES:
            break
        cand = start + window
        best = cand if best is None else max(best, cand)
    if best is not None and best <= DAY_END[0] * 60 + DAY_END[1]:
        return bj.replace(hour=best // 60, minute=best % 60, second=0, microsecond=0)
    return end


def release_segment() -> None:
    """正常退出时清空 marker，让下一个触发的 run 立刻可接管。

    不清的话要靠 seg_end + SEG_ALIVE_GRACE 才释放，下一次触发会被白白挡住
    （15:00 那条 eod 就是这么丢的）。清空动作由 finish() 一并提交。
    """
    try:
        with open(MARKER, 'w', encoding='utf-8') as fh:
            json.dump({}, fh)
    except Exception as exc:  # noqa: BLE001
        log(f'释放调度权失败: {exc}')


def current_session(bj: datetime.datetime) -> tuple[str, datetime.datetime] | None:
    """参考用班次划分（am / pm / night）。

    2026-11-07 起 main 不再用它当启动门槛——旧版正是被 pm 的 16:30 与 night 的
    21:15 这两条边界，把 11-06 真实发生的 17:15、21:06 两次触发挡在门外。
    现在启动只认"滚动窗口里还有没有待跑槽"。本函数保留供自检与人工排障对照。
    """
    """当前落在哪个班次；返回 (段名, 段结束时刻)。"""
    m = minutes_of(bj)
    for start, end, name in SESSIONS:
        if start <= m <= end:
            end_dt = bj.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)
            return name, end_dt
    return None


# ---------------------------------------------------------------- 自检
def _selftest() -> int:
    """注入固定时刻验证选槽与补跑，不联网不推送。"""
    fails = 0

    def expect(desc: str, got, want) -> None:
        nonlocal fails
        ok = got == want
        if not ok:
            fails += 1
        print(f'[{"PASS" if ok else "FAIL"}] {desc}: got={got} want={want}')

    def at(hh: int, mm: int, day: int = 9) -> datetime.datetime:
        return datetime.datetime(2026, 11, day, hh, mm, tzinfo=BJ)

    # 正点选槽（executed 为空）
    for hh, mm, want in ((8, 20, 'warn'), (8, 30, 'pre'), (9, 26, 'auction'),
                         (10, 0, 'hourly'), (10, 31, 'newsfire'), (10, 36, 'risk'),
                         (11, 40, 'news'), (12, 0, 'news2h'), (14, 1, 'news2h'),
                         (14, 55, 'tail'), (15, 2, 'eod'), (15, 20, 'cycle'),
                         (16, 0, 'news2h'), (21, 38, 'ext'), (22, 38, 'ext'),
                         (22, 50, 'evening')):
        expect(f'{hh:02d}:{mm:02d} 选槽', pick_slot(at(hh, mm), set()), want)

    # 异动扫描点
    expect('09:15 选槽', pick_slot(at(9, 15), set()), 'watch')
    expect('13:15 选槽', pick_slot(at(13, 15), set()), 'watch')
    expect('14:15 选槽', pick_slot(at(14, 15), set()), 'watch')
    expect('13:00 整点让位 hourly', pick_slot(at(13, 0), set()), 'hourly')
    expect('15:00 整点让位 eod', pick_slot(at(15, 0), set()), 'eod')
    expect('12:21 不选槽（正点窗口空档）', pick_slot(at(12, 21), set()), None)
    expect('12:18 反查 news2h 计划时刻', plan_of('news2h', at(12, 18)), (12, 0))
    expect('14:03 反查 hourly 计划时刻', plan_of('hourly', at(14, 3)), (14, 0))
    expect('14:03 反查 news2h 计划时刻', plan_of('news2h', at(14, 3)), (14, 1))
    expect('15:56 不选槽（news 窗口已过）', pick_slot(at(15, 56), set()), None)

    # 同一 run 内记忆防重
    s = set()
    expect('14:00 首次', pick_slot(at(14, 0), s), 'hourly')
    expect('14:01 已记忆', pick_slot(at(14, 1), s), 'news2h')

    # 补跑宽容窗（warn 8:20+60=09:20 已过窗，故 09:30 只补 pre）
    expect('09:30 补跑清单', [x[2] for x in backfill_pending(at(9, 30), set(), done={})], ['pre'])
    expect('10:05 补跑清单', [x[2] for x in backfill_pending(at(10, 5), set(), done={})], ['hourly', 'news2h'])
    _today = datetime.datetime.now(BJ).strftime('%Y-%m-%d')
    expect('10:05 已完成不补',
           [x[2] for x in backfill_pending(at(10, 5), set(), done={f'hourly|{_today}|10': True})], ['news2h'])
    expect('21:50 补跑清单', [x[2] for x in backfill_pending(at(21, 50), set(), done={})], ['ext'])

    # 班次判定
    expect('08:05 班次', (current_session(at(8, 5)) or ('', None))[0], 'am')
    expect('11:45 班次', (current_session(at(11, 45)) or ('', None))[0], 'am')
    expect('12:00 班次', (current_session(at(12, 0)) or ('', None))[0], 'pm')
    expect('16:30 班次', (current_session(at(16, 30)) or ('', None))[0], 'pm')
    expect('21:15 班次', (current_session(at(21, 15)) or ('', None))[0], 'night')
    expect('19:00 无班次', current_session(at(19, 0)), None)

    # 滚动占段：段尾无槽时提前让位（否则一个 run 白占 5 小时 runner）
    expect('09:59 段内仍有待跑槽', pending_within(at(9, 59), at(14, 59), set(), done={}), True)
    expect('17:20 仍在 news2h 宽容窗内', pending_within(at(17, 20), at(19, 0), set(), done={}), True)
    expect('17:40 段内仍有 18:00 news2h', pending_within(at(17, 40), at(19, 0), set(), done={}), True)
    _seed_day = datetime.datetime.now(BJ).strftime('%Y-%m-%d')   # slot_done_key 取的是"今天"，注入日期不参与
    expect('23:05 evening 与 ext 都已推过则无槽', pending_within(at(23, 5), at(23, 10), set(),
             done={f'evening|{_seed_day}': True, f'ext|{_seed_day}|2235': True}), True)

    # 滚动段终点（300 分钟 + 段尾 45 分钟延伸，杜绝"恰好把下一槽截在段外"）
    expect('10:00 启动终点（350 分钟+段尾延伸到 16:00 news2h）',
           rolling_end(at(10, 0)).strftime('%H:%M'), '16:20')
    expect('13:30 启动终点（350 分钟，段尾延伸到 20:00 news2h）',
           rolling_end(at(13, 30)).strftime('%H:%M'), '20:20')
    expect('17:45 启动终点（350 分钟，已过 22:50 故不延伸）',
           rolling_end(at(17, 45)).strftime('%H:%M'), '23:35')
    # 凌晨命中必须守到早盘，不许秒退（11-06 早盘整段丢失的根因）
    expect('04:47 凌晨命中守到早盘 09:30', rolling_end(at(4, 47)).strftime('%H:%M'), '09:30')
    expect('03:00 凌晨命中受 350 分钟上限 -> 08:50', rolling_end(at(3, 0)).strftime('%H:%M'), '08:50')
    expect('00:27 命中受上限约束 -> 06:17', rolling_end(at(0, 27)).strftime('%H:%M'), '06:17')

    # 窗口键必须与主程序一致（错一个就重复推或漏推）；用当天日期动态断言
    _t = datetime.datetime.now(BJ).strftime('%Y-%m-%d')
    expect('hourly 键', slot_done_key(10, 0, 'hourly'), f'hourly|{_t}|10')
    expect('news 11:40 键', slot_done_key(11, 40, 'news'), f'news|{_t}|1140')
    expect('news 15:35 键', slot_done_key(15, 35, 'news'), f'news|{_t}|1535')
    expect('follow 10:35 键', slot_done_key(10, 35, 'follow'), f'follow|{_t}|1035')
    expect('ext 21:38 键', slot_done_key(21, 38, 'ext'), f'ext|{_t}|2135')
    expect('news2h 14:01 键', slot_done_key(14, 1, 'news2h'), f'news2h|{_t}|1400')

    print(f'\n[SELFTEST] 失败 {fails} 项')
    return 0 if fails == 0 else 1


# ---------------------------------------------------------------- 主流程
def report_gaps() -> None:
    """退出前把"今天名义时刻已过宽容窗、但仍没推"的槽列出来，让缺口可追溯。"""
    try:
        now = bj_now()
        minutes = minutes_of(now)
        done = _read_json(SLOT_DONE)
        if now.weekday() >= 5:
            log('休市日：按各槽 holiday_slot 走，不统计工作日缺口')
            return
        gaps = []
        for hour, minute, slot, _window, late in FIXED_SLOTS:
            start = hour * 60 + minute
            if start + late >= minutes:
                continue          # 还没过窗，不叫缺口
            if is_done(hour, minute, slot, done):
                continue
            gaps.append(f'{hour:02d}:{minute:02d}{slot}')
        if gaps:
            log('今日已过窗未推 %d 个槽：%s' % (len(gaps), '、'.join(gaps)))
        else:
            log('今日应推槽位全部已落地，无缺口')
    except Exception as exc:  # noqa: BLE001
        log(f'缺口统计失败: {exc}')


def finish(tag: str) -> int:
    """退出前把日志与状态写回仓库，保证云端每次都留下可追溯痕迹。

    任何退出都先算一遍"今天哪些槽已过窗却没推"写进日志——用户问的就是"到底按时推没推"，
    这条不留痕就等于没法查。持久化仍只覆盖有意义的退出：weekend-end / roll-end / idle
    （idle 是"接下来窗口里没槽"，一天最多几次，不会把历史刷脏）；weekend-busy 让位不写。
    """
    log(f'退出原因：{tag}')
    report_gaps()
    if tag == 'preempted':
        # 让位者的本地 marker 可能是过期的旧段：再推一次就会把接管者覆盖掉。
        # 让位只写本地日志，不碰仓库状态。
        _flush_log()
        return 0
    if tag in ('weekend-end', 'roll-end', 'idle'):
        try:
            persist_state(tag)
        except Exception as exc:  # noqa: BLE001
            log(f'退出持久化失败: {exc}')
    return 0


def main() -> int:
    if '--selftest' in sys.argv:
        return _selftest()

    bj = bj_now()
    log(f'启动调度器 v6，当前北京时间 {bj:%Y-%m-%d %H:%M:%S} 星期{"一二三四五六日"[bj.weekday()]}')

    # ---- 周末/休市日：快跑一次休市新闻汇总即退出（不占长班次） ----
    if bj.weekday() >= 5:
        win = bj.hour // 2 * 2
        seg = f'weekend-{win:02d}'
        if not acquire_segment(bj, seg, bj + datetime.timedelta(minutes=20)):
            log(f'周末 {seg} 段已有存活调度器，本 run 让位退出')
            return finish('weekend-busy')
        # 周日 09:00 档先出因子体检报告，再出本窗休市新闻（去重都在主程序内）
        if bj.weekday() == 6 and 9 <= bj.hour < 12:
            run_slot('factor_weekly')
        run_slot('watch')   # 休市日闸门会把任意槽位改走 holiday_slot（2 小时窗去重）
        log('周末快跑结束，退出')
        return finish('weekend-end')

    # ---- 工作日：滚动占段 ----
    # 不再绑定"固定三段班次"。GitHub 对本仓库的 schedule 实测延迟 2-15 小时
    # （11-06 八次 run 只有 09:59 那次落在上午班次内，17:15 与 21:06 被旧 pm/night
    # 边界挡在门外，收盘复盘整段丢失），所以改成：
    #   启动门槛 = "接下来这个滚动窗口里还有待跑槽"，而不是"现在正好在班次里"；
    #   一旦启动就吃满随后 300 分钟（段尾 45 分钟内能接上下一槽再顺延）。
    # 副产物：凌晨触发的 run 会一路守到早盘第一个槽（省得早盘再赌一次 cron）。
    executed: set = set()
    missed: set = set()
    end = rolling_end(bj)
    if not pending_within(bj, end, executed):
        log(f'接下来 {(end - bj).total_seconds() / 60:.0f} 分钟内已无待跑槽位，本 run 直接退出')
        return finish('idle')

    seg_name = f'roll-{bj:%H%M}'
    if not acquire_segment(bj, seg_name, end):
        log(f'滚动段 {seg_name} 已被存活调度器占用，本 run 让位退出（防并发双推）')
        return finish('roll-busy')

    # 启动补跑：先把本次触发之前漏掉的槽补上（受宽容窗约束，过窗不补）
    # v15：补跑前再拉一次去重表——上一个 run 的状态推送若刚好被拒（fetch first），
    # 本地 slot_done 是旧表，照着补跑就是重复推送。
    pull_latest()
    for _h, _m, slot in backfill_pending(bj_now(), executed):
        run_slot(slot, _h, _m)

    log(f'滚动段 {seg_name} 调度至 {end:%H:%M}，共可覆盖约 {(end - bj_now()).total_seconds() / 60:.0f} 分钟')
    last_chk = bj_now()
    last_hb = bj_now()
    while bj_now() < end:
        now = bj_now()
        # 2026-11-09：每 4 分钟复查一次段标记。如果段已被别的 run 接管（本段被判死），
        # 立刻让位，绝不能让两个 run 同时按时刻表推同一槽（重复推送）。
        if (now - last_chk).total_seconds() >= 240:
            last_chk = now
            try:
                pull_latest()
                m_now = _read_json(MARKER)
                if (m_now.get('seg') or '') != seg_name:
                    log(f'段标记已切到 {m_now.get("seg") or "空"}，本 run 让位退出')
                    return finish('preempted')
            except Exception as _e:  # noqa: BLE001
                log(f'段标记复查异常（不影响继续）：{_e}')
            # 空转期心跳：段里长时间没有槽要跑时也要证明自己活着（v9）
            if (now - last_hb).total_seconds() >= HEARTBEAT_GAP:
                last_hb = now
                heartbeat()
        slot = pick_slot(now, executed)
        if slot:
            _ph, _pm = plan_of(slot, now)
            run_slot(slot, _ph, _pm)
            continue
        if not pending_within(now, end, executed):
            log('本段剩余时间内已无待跑槽位，提前让位退出')
            break
        report_new_misses(executed, missed)
        time.sleep(15)

    release_segment()
    log(f'滚动段调度结束（{bj_now():%H:%M}），退出')
    return finish('roll-end')


if __name__ == '__main__':
    sys.exit(main())
