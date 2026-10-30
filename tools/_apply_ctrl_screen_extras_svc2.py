# -*- coding: utf-8 -*-
"""一次性补丁：控盘选股补数层 v2 —— 公告主源换东财 + 修正 TTL 语义。

1) 常量块：加 ANN_EMPTY_TTL / BIZ_EMPTY_TTL / ANN_URL / ANN_HDR / ANN_DETAIL
2) extras_stale：改为「按尝试时间戳」判定，而不是「有没有数据」
   —— 原版对「确实没有公告」的股票（40 只里 15 只）会永远判过期，每次渲染都重拉
3) fetch_ann：主源换东财公告接口（实测 23/23 命中、并发 0.023s/只；项目 ui\\watchlist_panel.py
   L2485 也是这个接口），巨潮 provider 作兜底；返回 (list, 源名)
4) fetch_extras_one：记录 ann_src
5) fmt_ann：支持 4 元组（含公告类型）、tooltip 注明来源

执行一次即失效，勿重跑。
"""
import io
import os
import shutil
import tempfile

ROOT = r'D:\QuantMonitorV6'
SVC = os.path.join(ROOT, 'services', 'control_screen_service.py')
s = io.open(SVC, 'r', encoding='utf-8').read()
assert 'fetch_ann_em' not in s, '疑似已打过 v2 补丁'

# ---------------- 1) 常量块 ----------------
A1 = """BIZ_TTL = 30 * 24 * 3600      # 主营构成：30 天（季报/中报才变）
ANN_TTL = 6 * 3600            # 最新公告：6 小时（与 announcement_provider 的 CACHE_EXPIRE 一致）
_TIMESTAMP_KEYS = ('biz_ts', 'ann_ts')"""
N1 = """BIZ_TTL = 30 * 24 * 3600      # 主营构成命中：30 天（季报/中报才变）
BIZ_EMPTY_TTL = 24 * 3600     # 主营构成空结果：1 天后重试
ANN_TTL = 6 * 3600            # 最新公告命中：6 小时
ANN_EMPTY_TTL = 2 * 3600      # 公告空结果：2 小时后重试
_TIMESTAMP_KEYS = ('biz_ts', 'ann_ts')

# 公告主源：东方财富公告接口（不需要 orgId、全板性覆盖；项目 ui\\watchlist_panel.py
# L2485 已用同一接口）。实测单线程 23/23 命中、并发 6 线程 0.023s/只；
# 而巨潮 orgId 有新老两套格式、且并发下只有 25/40，所以降为兜底。
ANN_URL = ('http://np-anotice-stock.eastmoney.com/api/security/ann'
           '?sr=-1&page_size=%d&page_index=1&ann_type=A&client_source=web&stock_list=%s')
ANN_HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
ANN_DETAIL = 'https://data.eastmoney.com/notices/detail/%s/%s.html'"""
assert s.count(A1) == 1
s = s.replace(A1, N1, 1)

# ---------------- 2) extras_stale ----------------
A2 = '''def extras_stale(rec, now=None, need_biz=True, need_ann=True):
    """缓存是否需要刷新（按 TTL 判）。rec=None 视为过期。"""
    if not isinstance(rec, dict):
        return True
    now = time.time() if now is None else now
    if need_biz and not (rec.get('biz') and now - float(rec.get('biz_ts') or 0) < BIZ_TTL):
        return True
    if need_ann and not (rec.get('ann') and now - float(rec.get('ann_ts') or 0) < ANN_TTL):
        return True
    return False'''
N2 = '''def extras_stale(rec, now=None, need_biz=True, need_ann=True):
    """缓存是否需要刷新——按「上次尝试的时间戳」判，不是按「有没有数据」。

    这一条很关键：确实没有公告的股票（实测 40 只里有 15 只上游就是空），
    如果按「ann 非空」判新鲜度，它们会被永远判成过期、每次渲染都重拉一遍。
    所以：命中按各自 TTL（主营 30 天 / 公告 6 小时），空结果只等更短的重试期
    （主营 1 天 / 公告 2 小时），且从没尝试过（ts=0）一律算过期。
    """
    if not isinstance(rec, dict) or not rec:
        return True
    now = time.time() if now is None else now
    if need_biz:
        ts = float(rec.get('biz_ts') or 0)
        ttl = BIZ_TTL if rec.get('biz') else BIZ_EMPTY_TTL
        if ts <= 0 or now - ts >= ttl:
            return True
    if need_ann:
        ts = float(rec.get('ann_ts') or 0)
        ttl = ANN_TTL if rec.get('ann') else ANN_EMPTY_TTL
        if ts <= 0 or now - ts >= ttl:
            return True
    return False'''
assert s.count(A2) == 1
s = s.replace(A2, N2, 1)

# ---------------- 3) fetch_ann ----------------
A3 = '''def fetch_ann(code, count=5):
    """取最新公告，返回 [[date, title, url], ...]（按时间倒序，最多 count 条）。"""
    try:
        from data.announcement_provider import get_announcement_provider
        lst = get_announcement_provider().get_announcements(str(code), count=count) or []
        return [[str(a.get('date') or ''), str(a.get('title') or ''),
                 str(a.get('url') or '')] for a in lst[:count]]
    except Exception as e:
        print('[控盘选股] 公告取数失败(%s): %s' % (code, e), flush=True)
        return []'''
N3 = '''def fetch_ann_em(code, count=5, timeout=6):
    """东财公告接口（主源）。返回 [[date, title, url, type], ...]；
    请求失败返回 None（以便与「成功但上游就是空」区分开）。"""
    try:
        import requests
        r = requests.get(ANN_URL % (int(count), str(code)), headers=ANN_HDR, timeout=timeout)
        j = r.json() or {}
        lst = ((j.get('data') or {}).get('list')) or []
        out = []
        for it in lst[:int(count)]:
            _d = str(it.get('notice_date') or '')[:10]
            _cols = it.get('columns') or []
            _type = str((_cols[0] or {}).get('column_name') or '') if _cols else ''
            _art = str(it.get('art_code') or '')
            out.append([_d, str(it.get('title') or ''),
                        (ANN_DETAIL % (str(code), _art)) if _art else '', _type])
        return out
    except Exception:
        return None


def fetch_ann(code, count=5, timeout=6):
    """取最新公告，返回 ([[date, title, url, type], ...], 源名)。

    主源：东财公告接口（不需 orgId，实测并发 0.023s/只、40 只全中）
    兜底：巨潮资讯网 data.announcement_provider（需要 orgId；实测并发下 25/40）
    """
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
    return [], ('eastmoney' if got == [] else '')'''
assert s.count(A3) == 1
s = s.replace(A3, N3, 1)

# ---------------- 4) fetch_extras_one 的公告段 ----------------
A4 = """    if need_ann:
        rec['ann'] = fetch_ann(code)
        rec['ann_ts'] = now"""
N4 = """    if need_ann:
        _ann, _src = fetch_ann(code)
        rec['ann'] = _ann
        rec['ann_src'] = _src
        rec['ann_ts'] = now"""
assert s.count(A4) == 1
s = s.replace(A4, N4, 1)

# ---------------- 5) fmt_ann ----------------
A5 = '''def fmt_ann(rec):
    """最新公告列 → (显示文本, tooltip)。没数据返回 ('', '')。"""
    if not isinstance(rec, dict):
        return '', ''
    lst = rec.get('ann') or []
    if not lst:
        return '', ''
    _d, _t = str(lst[0][0] or ''), str(lst[0][1] or '')
    _short = _d[5:] if len(_d) >= 10 else _d          # YYYY-MM-DD → MM-DD
    text = ('%s %s' % (_short, _t)).strip()
    lines = ['最新公告：']
    for a in lst[:3]:
        try:
            lines.append('  %s  %s' % (str(a[0] or ''), str(a[1] or '')))
        except Exception:
            continue
    _u = str(lst[0][2] or '') if len(lst[0]) > 2 else ''
    if _u:
        lines.append(_u)
    return text, '\\n'.join(lines)'''
N5 = '''def _strip_ann_prefix(title):
    """去掉公告标题里开头的「简称:」（如「甘咨询:甘肃工程咨询集团…」）。

    只影响单元格显示（简称与左边的「股票名称」列重复、白占宽度）；
    tooltip 里给的是上游原始标题，不做任何改写。
    """
    t = str(title or '')
    for i, ch in enumerate(t[:10]):
        if ch in ':：':
            return t[i + 1:].strip() if i >= 1 else t
    return t


def fmt_ann(rec):
    """最新公告列 → (显示文本, tooltip)。没数据返回 ('', '')。"""
    if not isinstance(rec, dict):
        return '', ''
    lst = rec.get('ann') or []
    if not lst:
        return '', ''
    _d, _t = str(lst[0][0] or ''), str(lst[0][1] or '')
    _short = _d[5:] if len(_d) >= 10 else _d          # YYYY-MM-DD → MM-DD
    text = ('%s %s' % (_short, _strip_ann_prefix(_t))).strip()
    _src = {'eastmoney': '东方财富', 'cninfo': '巨潮资讯'}.get(str(rec.get('ann_src') or ''), '')
    lines = ['最新公告%s：' % (('（来源 %s）' % _src) if _src else '')]
    for a in lst[:3]:
        try:
            _ty = (' ［%s］' % str(a[3])) if len(a) > 3 and a[3] else ''
            lines.append('  %s  %s%s' % (str(a[0] or ''), str(a[1] or ''), _ty))
        except Exception:
            continue
    _u = str(lst[0][2] or '') if len(lst[0]) > 2 else ''
    if _u:
        lines.append(_u)
    return text, '\\n'.join(lines)'''
assert s.count(A5) == 1
s = s.replace(A5, N5, 1)

if not os.path.isfile(SVC + '.bak_before_extras2'):
    shutil.copy2(SVC, SVC + '.bak_before_extras2')
    print('备份: %s.bak_before_extras2' % SVC)
io.open(SVC, 'w', encoding='utf-8', newline='').write(s)

import py_compile   # noqa: E402
b = io.open(SVC, 'rb').read()
print('control_screen_service.py: 行=%d CRLF=%d 字节=%d'
      % (b.count(b'\n'), b.count(b'\r\n'), len(b)))
assert b.count(b'\r\n') == 0
py_compile.compile(SVC, cfile=os.path.join(tempfile.gettempdir(), 'cs_extras2.pyc'), doraise=True)
print('语法校验通过')
