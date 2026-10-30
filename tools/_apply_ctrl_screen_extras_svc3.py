# -*- coding: utf-8 -*-
"""一次性补丁（服务层 v3）：公告多源 + 按主机限速 + 失败标记 + 退避重试 + 熔断。

背景（实测，不是猜的）：
  · 东财公告接口在本次「978 只 / 61 秒 / 约 16 req/s」的批量后对 IP 返回 **HTTP 567**
    （HTML 挑战页），并且 2 分钟后仍未恢复 → 前 500 只成功、后 478 只全空。
  · 巨潮 hisAnnouncement/query 随后对 IP 返回 **HTTP 403**（连今天早些时候能出的
    000779 也 403），且它依赖 orgId（项目只对 6 开头硬拼 gssh0+code，创业板拿不到）。
  · 新浪公告页 vCB_AllBulletin（GBK HTML）**未受影响**：600338/301201/000779 全部 200
    且能解析出「日期 + 标题 + 详情链接」，作为次源补位（全板性）。
做法：
  1) 公告三源：东财 → 新浪 → 巨潮；返回三元组 (list, src, ok)，ok=False 才算「上游没响应」
     （与「上游确认无公告」严格区分，后者不会污染缓存、也不会被误判成失败）。
  2) 按「主机桶」限速：公告桶 0.30s/次、主营桶 0.20s/次，多线程共享一个节拍。
  3) 失败只记标记 + 打时间戳：EXTRA_FAIL_COOLDOWN=15 分钟内不重试，之后自动重试。
  4) 熔断：连续 12 只「主营+公告都失败」= 已被整体风控，本轮直接停手（stats['aborted']）。

执行一次即失效，勿重跑。
"""
import io
import os
import shutil
import tempfile

ROOT = r'D:\QuantMonitorV6'
SVC = os.path.join(ROOT, 'services', 'control_screen_service.py')
s = io.open(SVC, 'r', encoding='utf-8').read()
assert 'fetch_ann_sina' not in s, '疑似已打过补丁（v3）'
assert '_throttle' not in s, '疑似已打过补丁（v3）'
orig = s

# ---------------- 1) imports ----------------
A = """import io
import json
import os
import sys
import time
from datetime import datetime
"""
N = """import io
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 2) 常量块 ----------------
A = """ANN_URL = ('http://np-anotice-stock.eastmoney.com/api/security/ann'
           '?sr=-1&page_size=%d&page_index=1&ann_type=A&client_source=web&stock_list=%s')
ANN_HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
ANN_DETAIL = 'https://data.eastmoney.com/notices/detail/%s/%s.html'
"""
N = """ANN_URL = ('http://np-anotice-stock.eastmoney.com/api/security/ann'
           '?sr=-1&page_size=%d&page_index=1&ann_type=A&client_source=web&stock_list=%s')
ANN_HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
ANN_DETAIL = 'https://data.eastmoney.com/notices/detail/%s/%s.html'

# 次源：新浪财经「公司公告」页（GBK HTML）。为什么要有它：2026-10-11 实测，
# 东财公告接口在批量 ~500 次后对 IP 返 567、巨潮 hisAnnouncement 返 403，
# 而新浪这条通道同批代码仍是 200 且能解析（600338 / 301201 / 000779 全中）。
ANN_SINA_URL = ('https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin'
                '/stockid/%s.phtml?Page=1')
ANN_SINA_BASE = 'https://vip.stock.finance.sina.com.cn'
ANN_SINA_HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://vip.stock.finance.sina.com.cn/'}
_SINA_ANN_RE = re.compile(
    r"(\\d{4}-\\d{2}-\\d{2})&nbsp;<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>")

# 上游风控后的「退避窗口」：失败只记标记，15 分钟内不再重撞，之后自动重试
BIZ_FAIL_COOLDOWN = 15 * 60
ANN_FAIL_COOLDOWN = 15 * 60

# 按「主机桶」限速（多线程共享一个节拍，避免把 IP 撞进风控）
_BM_LOCK = threading.Lock()
_BM_LAST = {}
ANN_MIN_INTERVAL = 0.30      # 公告桶（东财/新浪/巨潮共用）
BIZ_MIN_INTERVAL = 0.20      # 主营桶（东财 F10）


def _throttle(bucket, interval):
    \"\"\"按桶限速：同一桶内全局串行，最小间隔 interval 秒。\"\"\"
    with _BM_LOCK:
        now = time.time()
        wait = (_BM_LAST.get(bucket) or 0.0) + float(interval) - now
        if wait > 0:
            time.sleep(wait)
        _BM_LAST[bucket] = time.time()
"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 3) extras_stale：失败退避 ----------------
A = """    if need_biz:
        ts = float(rec.get('biz_ts') or 0)
        ttl = BIZ_TTL if rec.get('biz') else BIZ_EMPTY_TTL
        if ts <= 0 or now - ts >= ttl:
            return True
    if need_ann:
        ts = float(rec.get('ann_ts') or 0)
        ttl = ANN_TTL if rec.get('ann') else ANN_EMPTY_TTL
        if ts <= 0 or now - ts >= ttl:
            return True
    return False"""
N = """    if need_biz:
        ts = float(rec.get('biz_ts') or 0)
        if rec.get('biz_fail'):
            # 上游没响应（限流/网络）：只等退避窗口，不套 30 天 TTL、也不覆盖旧值
            if ts <= 0 or now - ts >= BIZ_FAIL_COOLDOWN:
                return True
        else:
            ttl = BIZ_TTL if rec.get('biz') else BIZ_EMPTY_TTL
            if ts <= 0 or now - ts >= ttl:
                return True
    if need_ann:
        ts = float(rec.get('ann_ts') or 0)
        if rec.get('ann_fail'):
            if ts <= 0 or now - ts >= ANN_FAIL_COOLDOWN:
                return True
        else:
            ttl = ANN_TTL if rec.get('ann') else ANN_EMPTY_TTL
            if ts <= 0 or now - ts >= ttl:
                return True
    return False"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 4) fetch_biz：返回 (dict, ok) + 限速 ----------------
A = """def fetch_biz(code, timeout=8):
    \"\"\"取主营构成（东财 F10），返回 {biz, biz_income, biz_ratio, biz_date, biz_items}。\"\"\"
    out = {'biz': '', 'biz_income': '', 'biz_ratio': '', 'biz_date': '', 'biz_items': []}
    try:
        from utils.main_business_service import fetch_main_business_composition
        r = fetch_main_business_composition(code, timeout=timeout) or {}"""
N = """def fetch_biz(code, timeout=8):
    \"\"\"取主营构成（东财 F10），返回 (dict, ok)。

    dict: {biz, biz_income, biz_ratio, biz_date, biz_items}
    ok=False = 上游没给出有效响应（限流/网络）→ 调用方只记失败标记、保留旧值。
    \"\"\"
    out = {'biz': '', 'biz_income': '', 'biz_ratio': '', 'biz_date': '', 'biz_items': []}
    try:
        from utils.main_business_service import fetch_main_business_composition
        _throttle('biz', BIZ_MIN_INTERVAL)
        r = fetch_main_business_composition(code, timeout=timeout) or {}"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

A = """    except Exception as e:
        print('[控盘选股] 主营取数失败(%s): %s' % (code, e), flush=True)
    return out"""
N = """    except Exception as e:
        print('[控盘选股] 主营取数失败(%s): %s' % (code, e), flush=True)
        return out, False
    return out, bool(out.get('biz_items') or out.get('biz_date'))"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 5) fetch_ann_em：显式判 HTTP 状态 ----------------
A = """    try:
        import requests
        r = requests.get(ANN_URL % (int(count), str(code)), headers=ANN_HDR, timeout=timeout)
        j = r.json() or {}"""
N = """    try:
        import requests
        _throttle('ann', ANN_MIN_INTERVAL)
        r = requests.get(ANN_URL % (int(count), str(code)), headers=ANN_HDR, timeout=timeout)
        if r.status_code != 200:
            return None            # 567 等风控页：不是「没有公告」，是没拿到响应
        j = r.json() or {}"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 6) 新增 fetch_ann_sina ----------------
A = """def fetch_ann(code, count=5, timeout=6):
    \"\"\"取最新公告，返回 ([[date, title, url, type], ...], 源名)。

    主源：东财公告接口（不需 orgId，实测并发 0.023s/只、40 只全中）
    兜底：巨潮资讯网 data.announcement_provider（需要 orgId；实测并发下 25/40）
    \"\"\"
    got = fetch_ann_em(code, count=count, timeout=timeout)
    if got:
        return got, 'eastmoney'
    try:
        from data.announcement_provider import get_announcement_provider
        lst = get_announcement_provider().get_announcements(str(code), count=count) or []
        if lst:
            return [[str(a.get('date') or ''), str(a.get('title') or ''),
                     str(a.get('url') or ''), str(a.get('type') or '')]
                    for a in lst[:count]], 'cninfo'
    except Exception as e:
        print('[控盘选股] 公告兜底源失败(%s): %s' % (code, e), flush=True)
    return [], ('eastmoney' if got == [] else '')"""
N = """def fetch_ann_sina(code, count=5, timeout=8):
    \"\"\"次源：新浪财经「公司公告」页解析。返回 [[date, title, url, type], ...]
    或 None（没拿到响应）。成功但无公告返回 []。\"\"\"
    try:
        import requests
        _throttle('ann', ANN_MIN_INTERVAL)
        r = requests.get(ANN_SINA_URL % str(code), headers=ANN_SINA_HDR, timeout=timeout)
        if r.status_code != 200:
            return None
        r.encoding = 'gbk'
        out = []
        for _d, _href, _ti in _SINA_ANN_RE.findall(r.text or ''):
            _u = _href if str(_href).startswith('http') else (ANN_SINA_BASE + str(_href))
            out.append([str(_d), str(_ti).strip(), _u, ''])
            if len(out) >= int(count):
                break
        return out
    except Exception:
        return None


def fetch_ann(code, count=5, timeout=6):
    \"\"\"取最新公告，返回 ([[date, title, url, type], ...], 源名, ok)。

    三源依次尝试，**只要有一个源给出有效响应就算成功**（哪怕结果是空列表）：
      主源  东财公告接口（字段最全、不需 orgId）
      次源  新浪财经公告页（东财被限流时顶上来，全板性）
      兜底  巨潮资讯网 data.announcement_provider（要 orgId，部分代码解析不出）
    ok=False = 三个源都没拿到有效响应（限流/断网）→ 只记失败标记，15 分钟后重试。
    \"\"\"
    got = fetch_ann_em(code, count=count, timeout=timeout)     # None=没拿到, []=真没有
    if got is not None:
        return got, ('eastmoney' if got else ''), True
    got = fetch_ann_sina(code, count=count, timeout=timeout)
    if got is not None:
        return got, ('sina' if got else ''), True
    try:
        from data.announcement_provider import get_announcement_provider
        from data.stock_identity_provider import get_org_id
        if get_org_id(str(code)):      # 没 orgId 时 provider 必然返回 []，不算「成功」
            lst = get_announcement_provider().get_announcements(str(code), count=count) or []
            if lst:
                return [[str(a.get('date') or ''), str(a.get('title') or ''),
                         str(a.get('url') or ''), str(a.get('type') or '')]
                        for a in lst[:count]], 'cninfo', True
    except Exception as e:
        print('[控盘选股] 公告兜底源失败(%s): %s' % (code, e), flush=True)
    return [], '', False"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 7) fetch_extras_one：失败只记标记 ----------------
A = """    rec = dict(old) if isinstance(old, dict) else {}
    now = time.time()
    if need_biz:
        b = fetch_biz(code, timeout=timeout)
        rec.update(b)
        rec['biz_ts'] = now
    if need_ann:
        _ann, _src = fetch_ann(code)
        rec['ann'] = _ann
        rec['ann_src'] = _src
        rec['ann_ts'] = now
    rec['code'] = str(code)
    return rec"""
N = """    rec = dict(old) if isinstance(old, dict) else {}
    now = time.time()
    if need_biz:
        b, _ok = fetch_biz(code, timeout=timeout)
        rec['biz_ts'] = now
        if _ok:
            rec.update(b)
            rec.pop('biz_fail', None)
        else:
            rec['biz_fail'] = 1            # 上游没响应：保留旧值，等退避窗口后再试
            rec.setdefault('biz', '')
            rec.setdefault('biz_items', [])
    if need_ann:
        _ann, _src, _ok = fetch_ann(code)
        rec['ann_ts'] = now
        if _ok:
            rec['ann'] = _ann
            rec['ann_src'] = _src
            rec.pop('ann_fail', None)
        else:
            rec['ann_fail'] = 1
            rec.setdefault('ann', [])
            rec.setdefault('ann_src', '')
    rec['code'] = str(code)
    return rec"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 8) fetch_extras：默认 3 线程 + 统计 + 熔断 ----------------
A = """def fetch_extras(codes, items, workers=6, progress_cb=None, cancel_cb=None,
                 save_every=100, path=None, timeout=8):
    \"\"\"并发补一批股票的「主营收入 + 最新公告」，原地更新 items 并定期落盘。

    codes        要补的代码（一般来自 extras_missing）
    items        已有缓存 dict（会被**原地更新**，便于界面直接用）
    workers      并发线程数（对上游限流友好，默认 6）
    返回 (items, stats)  stats: {'total','done','ok','err','elapsed'}
    \"\"\"
    import concurrent.futures as cf
    t0 = time.perf_counter()
    codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    stats = {'total': len(codes), 'done': 0, 'ok': 0, 'err': 0, 'elapsed': 0.0}
    if not codes:
        return items, stats
    items = items if isinstance(items, dict) else {}
    lock = __import__('threading').Lock()
    done = [0]

    def _work(c):
        if cancel_cb is not None:
            try:
                if cancel_cb():
                    return None
            except Exception:
                pass
        try:
            rec = fetch_extras_one(c, timeout=timeout, old=items.get(c))
            return c, rec
        except Exception:
            return c, None

    try:
        with cf.ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            for c, rec in ex.map(_work, codes):
                with lock:
                    done[0] += 1
                    if rec is None:
                        stats['err'] += 1
                    else:
                        items[c] = rec
                        stats['ok'] += 1
                    stats['done'] = done[0]"""
N = """def fetch_extras(codes, items, workers=3, progress_cb=None, cancel_cb=None,
                 save_every=100, path=None, timeout=8, fail_circuit=12):
    \"\"\"并发补一批股票的「主营收入 + 最新公告」，原地更新 items 并定期落盘。

    codes        要补的代码（一般来自 extras_missing）
    items        已有缓存 dict（会被**原地更新**，便于界面直接用）
    workers      并发线程数（提速交给「按主机限速」，所以默认 3 就够）
    fail_circuit 连续多少只「主营+公告都失败」就判定被整体风控、本轮停手（0=关闭）
    返回 (items, stats)  stats: {'total','done','ok','err','elapsed',
                                 'biz_ok','ann_ok','biz_fail','ann_fail','aborted'}
    \"\"\"
    import concurrent.futures as cf
    t0 = time.perf_counter()
    codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    stats = {'total': len(codes), 'done': 0, 'ok': 0, 'err': 0, 'elapsed': 0.0,
             'biz_ok': 0, 'ann_ok': 0, 'biz_fail': 0, 'ann_fail': 0, 'aborted': ''}
    if not codes:
        return items, stats
    items = items if isinstance(items, dict) else {}
    lock = threading.Lock()
    done = [0]
    abort_ev = threading.Event()
    streak = [0]

    def _work(c):
        if abort_ev.is_set():
            return None
        if cancel_cb is not None:
            try:
                if cancel_cb():
                    return None
            except Exception:
                pass
        try:
            rec = fetch_extras_one(c, timeout=timeout, old=items.get(c))
            return c, rec
        except Exception:
            return c, None

    try:
        with cf.ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            for c, rec in ex.map(_work, codes):
                with lock:
                    done[0] += 1
                    if rec is None:
                        stats['err'] += 1
                    else:
                        items[c] = rec
                        stats['ok'] += 1
                        if rec.get('biz'):
                            stats['biz_ok'] += 1
                        if rec.get('ann'):
                            stats['ann_ok'] += 1
                        if rec.get('biz_fail'):
                            stats['biz_fail'] += 1
                        if rec.get('ann_fail'):
                            stats['ann_fail'] += 1
                        # 熔断：连续「主营+公告都失败」= 上游整体风控，别再撞了
                        streak[0] = (streak[0] + 1) if (rec.get('ann_fail')
                                                        and rec.get('biz_fail')) else 0
                        if fail_circuit and streak[0] >= int(fail_circuit):
                            stats['aborted'] = 'rate_limited'
                            abort_ev.set()
                    stats['done'] = done[0]"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# 熔断跳出 for 循环（原循环体末尾的落盘/进度段之后插入 break）
A = """                    if save_every and done[0] % int(save_every) == 0:
                        save_extras(items, path)
    except Exception as e:"""
N = """                    if save_every and done[0] % int(save_every) == 0:
                        save_extras(items, path)
                if abort_ev.is_set():
                    break
    except Exception as e:"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 9) fmt_ann：加新浪来源名 ----------------
A = """    _src = {'eastmoney': '东方财富', 'cninfo': '巨潮资讯'}.get(str(rec.get('ann_src') or ''), '')"""
N = """    _src = {'eastmoney': '东方财富', 'sina': '新浪财经',
            'cninfo': '巨潮资讯'}.get(str(rec.get('ann_src') or ''), '')"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

# ---------------- 10) 头部注释同步 ----------------
A = """#   最新公告  data.announcement_provider.get_announcement_provider
#             （巨潮资讯网，自带 6 小时内存缓存）"""
N = """#   最新公告  东财公告接口（主源）→ 新浪财经公告页（次源，东财被限流时顶上来）
#             → data.announcement_provider（巨潮兜底）
# 三源 + 按主机限速（公告 0.3s/次、主营 0.2s/次）+ 失败退避 15 分钟 + 连续失败熔断，
# 是因为 2026-10-11 实测「978 只 × 2 源 / 61 秒」把东财撞成 567、巨潮撞成 403。"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

assert s != orig
if not os.path.isfile(SVC + '.bak_before_extras3'):
    shutil.copy2(SVC, SVC + '.bak_before_extras3')
    print('备份: %s.bak_before_extras3' % SVC)
io.open(SVC, 'w', encoding='utf-8', newline='').write(s)

import py_compile   # noqa: E402
b = io.open(SVC, 'rb').read()
print('control_screen_service.py: 行=%d CRLF=%d 字节=%d' % (b.count(b'\n'), b.count(b'\r\n'), len(b)))
assert b.count(b'\r\n') == 0
py_compile.compile(SVC, cfile=os.path.join(tempfile.gettempdir(), 'cs_svc3.pyc'), doraise=True)
print('语法校验通过')
