# -*- coding: utf-8 -*-
"""一次性补丁【勿重跑】：修 K 线源顺序 —— 让盘中能取到当天的日K。

根因（2026-10-12 13:44 盘中实测）：
  fetch_kline_pytdx       -> 空（服务器可连但无数据）
  fetch_kline_sina        -> 末根 2026-10-09（新浪日线不含当天未收盘bar）
  fetch_kline_tencent     -> 末根 2026-10-12 ← 有当天
  fetch_kline_eastmoney   -> 连接被断
旧顺序 pytdx → 新浪 → 腾讯 → 东财，且「够根数就 return」，
于是新浪的 10-09 结果把腾讯的当天 bar 挡掉 → K线缓存 data 日永远停在上一交易日
→ 控盘选股/日K建仓 显示的数据日一直是 10-09。

新逻辑：先把「末根=今天」的结果找出来，退而求其次才用「末根<今天」的。
非交易日或开盘前不做这种追求（保持旧的一次命中就返回，不额外多发请求）。
"""
import os
import shutil

P = r'D:\QuantMonitorV6\utils\kline_fetcher.py'
BAK = P + '.bak_before_fresh'
src = open(P, newline='', encoding='utf-8').read()
crlf = src.count('\r\n') > src.count('\n') - src.count('\r\n')
s = src.replace('\r\n', '\n')
if not os.path.exists(BAK):
    shutil.copy2(P, BAK)
    print('已备份 ->', BAK)

# 1) 补 import（该文件原本只有 requests/time/threading/typing）
old_imp = """import requests
import time
import threading
from typing import List, Dict, Optional"""
new_imp = """import json
import os
import requests
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional"""
assert s.count(old_imp) == 1
s = s.replace(old_imp, new_imp)

# 2) 新增两个助手函数 + 重写 fetch_kline
old_entry = '''def fetch_kline(code: str, days: int = 300) -> Optional[List[Dict]]:
    """
    统一K线获取入口：pytdx在线（主）→ 腾讯财经（备）→ 新浪财经（第三备）
    不使用通达信本地数据文件，全部使用在线接口。

    Args:
        code: 股票代码
        days: 获取最近N根K线

    Returns:
        List[Dict]，失败返回None
    """
    # 1. pytdx在线（首选，速度最快0.02s/只，数据最新到当天）
    kline = fetch_kline_pytdx(code, days=days)
    if kline and len(kline) >= min(days, 20):
        return kline

    # 2. 新浪财经（2026-09-18实测稳定，腾讯fqkline被WAF 501拦截时走这里）
    kline = fetch_kline_sina(code, days=days)
    if kline and len(kline) >= min(days, 20):
        return kline

    # 3. 腾讯财经（备用，前复权数据；WAF拦截时快速失败不拖时间）
    kline = fetch_kline_tencent(code, days=days)
    if kline and len(kline) >= min(days, 20):
        return kline

    # 4. 东方财富（第四备用，当前网络不稳定）
    kline = fetch_kline_eastmoney(code, days=days)
    if kline and len(kline) >= min(days, 20):
        return kline

    return None'''

new_entry = '''_TODAY_EXPECT = {'key': None, 'val': True}


def _kline_last_date(kline) -> str:
    """取最后一根K线的日期，统一成 YYYY-MM-DD；取不到返回空串"""
    if not kline:
        return ''
    d = str(kline[-1].get('date', '')).strip()
    if len(d) == 8 and d.isdigit():
        d = '%s-%s-%s' % (d[:4], d[4:6], d[6:8])
    return d


def _today_bar_expected() -> bool:
    """今天是否「本该」已有当日K线：工作日 + 不在休市表里 + 已过 09:30。
    结果按分钟缓存，避免批量拉取时反复读文件。"""
    now = datetime.now()
    key = now.strftime('%Y-%m-%d %H:%M')
    if _TODAY_EXPECT.get('key') == key:
        return _TODAY_EXPECT['val']
    val = True
    if now.weekday() >= 5:
        val = False
    elif (now.hour, now.minute) < (9, 30):
        val = False
    else:
        try:
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'data', 'market_holidays.json')
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    js = json.load(f)
                hols = set(js.get('holidays') or []) if isinstance(js, dict) else set(js or [])
                if now.strftime('%Y-%m-%d') in hols:
                    val = False
        except Exception:
            pass
    _TODAY_EXPECT['key'] = key
    _TODAY_EXPECT['val'] = val
    return val


def fetch_kline(code: str, days: int = 300) -> Optional[List[Dict]]:
    """
    统一K线获取入口：pytdx在线 → 腾讯财经 → 新浪财经 → 东方财富
    不使用通达信本地数据文件，全部使用在线接口。

    V2.9.7（2026-10-12）：改为「新鲜度优先」。
    实测盘中（2026-10-12 13:44）：pytdx 服务器可连但无数据；新浪日线末根只到
    2026-10-09（不含当天未收盘bar）；腾讯 fqkline 末根已是 2026-10-12。
    旧顺序把新浪排在腾讯前面且「够根数就返回」，导致盘中永远拿不到当天的 bar ——
    K线缓存与控盘选股的数据日因此一直停在上一交易日。
    现在：优先返回「末根=今天」的那一份；都不够新时才退回「末根<今天」的那一份。
    非交易日 / 开盘前不做这种追求，保持一次命中即返回，不额外多发请求。

    Args:
        code: 股票代码
        days: 获取最近N根K线

    Returns:
        List[Dict]，失败返回None
    """
    need = min(days, 20)
    today = datetime.now().strftime('%Y-%m-%d')
    expect_today = _today_bar_expected()
    fallback = None

    for fetcher in (fetch_kline_pytdx, fetch_kline_tencent,
                    fetch_kline_sina, fetch_kline_eastmoney):
        try:
            kline = fetcher(code, days=days)
        except Exception:
            kline = None
        if not kline or len(kline) < need:
            continue
        if not expect_today or _kline_last_date(kline) >= today:
            return kline            # 已含今天（或今天本来就不该有）→ 直接用
        if fallback is None:
            fallback = kline        # 记下第一份「能用但不够新」的

    return fallback'''

assert s.count(old_entry) == 1
s = s.replace(old_entry, new_entry)

out = s.replace('\n', '\r\n') if crlf else s
# 该文件带 UTF-8 BOM（原样保留），compile() 需要去掉 BOM 再校验
compile(out.lstrip('\ufeff'), P, 'exec')
open(P, 'w', newline='', encoding='utf-8').write(out)
chk = open(P, newline='', encoding='utf-8').read()
print('原 %d 行 -> 现 %d 行 | CRLF %d | 裸LF %d | 编译 OK' % (
    src.count('\r\n') + 1, chk.count('\r\n') + 1, chk.count('\r\n'),
    chk.count('\n') - chk.count('\r\n')))
print('新函数就位:',
      all(k in chk for k in ('def _kline_last_date', 'def _today_bar_expected',
                             'expect_today', 'fetch_kline_tencent,')))
