# -*- coding: utf-8 -*-
"""一次性补丁（2/2）：控盘选股服务层加「主营收入 + 最新公告」补数层。

新增（插在「快照」小节之前）：
  EXTRAS_PATH / BIZ_TTL / ANN_TTL
  load_extras / save_extras / extras_stale / extras_missing
  fetch_biz / fetch_ann / fetch_extras_one / fetch_extras
  fmt_biz / fmt_ann

数据源（都是项目已有通道，不另写接口）：
  主营收入  utils.main_business_service.fetch_main_business_composition（东财 F10，带当日文件缓存）
  最新公告  data.announcement_provider.get_announcement_provider（巨潮资讯网，6h 内存缓存）

执行一次即失效，勿重跑。
"""
import io
import os
import shutil
import sys
import tempfile

ROOT = r'D:\QuantMonitorV6'
SVC = os.path.join(ROOT, 'services', 'control_screen_service.py')

s = io.open(SVC, 'r', encoding='utf-8').read()
assert 'fetch_extras' not in s, '服务层疑似已打过补丁（2/2）'

ANCHOR = """# ============================================================
# 快照（页面重开不用再等 30 秒）
# ============================================================"""

NEW = '''# ============================================================
# 主营收入 + 最新公告（联网补数，带本地 TTL 缓存）
# ------------------------------------------------------------
# 这两项**都不进全市场扫描**：扫描是本地 25 秒的活儿，而它们要联网
# （公告 0.09~0.17s/只、主营构成 0.18~0.46s/只，实测），4400 只同步拉要 20 分钟以上。
# 所以走「页面渲染完 → 后台并发补当前筛选结果的缺项 → 补完重绘」，
# 结果落 data/cache/ctrl_screen_extras.json，第二次打开直接命中缓存（0 秒）。
#
# 数据源（项目已有通道，不另写接口）：
#   主营收入  utils.main_business_service.fetch_main_business_composition
#             （东方财富 F10 BusinessAnalysis，自带 data/cache/main_business/{code}_{YYYYMMDD}.json）
#   最新公告  data.announcement_provider.get_announcement_provider
#             （巨潮资讯网，自带 6 小时内存缓存）
# ============================================================
EXTRAS_PATH = os.path.join(PROJECT_ROOT, 'data', 'cache', 'ctrl_screen_extras.json')
BIZ_TTL = 30 * 24 * 3600      # 主营构成：30 天（季报/中报才变）
ANN_TTL = 6 * 3600            # 最新公告：6 小时（与 announcement_provider 的 CACHE_EXPIRE 一致）
_TIMESTAMP_KEYS = ('biz_ts', 'ann_ts')


def load_extras(path=None):
    """读本地补数缓存，返回 {code: rec}；不存在/损坏返回 {}。"""
    p = path or EXTRAS_PATH
    try:
        if not os.path.isfile(p):
            return {}
        d = json.load(io.open(p, 'r', encoding='utf-8'))
        items = d.get('items') if isinstance(d, dict) else None
        return items if isinstance(items, dict) else {}
    except Exception:
        return {}


def save_extras(items, path=None):
    """写本地补数缓存。返回写入路径，失败返回 ''。"""
    p = path or EXTRAS_PATH
    try:
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        payload = {'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'items': items or {}}
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        return p
    except Exception as e:
        print('[控盘选股] 写补数缓存失败: %s' % e, flush=True)
        return ''


def extras_stale(rec, now=None, need_biz=True, need_ann=True):
    """缓存是否需要刷新（按 TTL 判）。rec=None 视为过期。"""
    if not isinstance(rec, dict):
        return True
    now = time.time() if now is None else now
    if need_biz and not (rec.get('biz') and now - float(rec.get('biz_ts') or 0) < BIZ_TTL):
        return True
    if need_ann and not (rec.get('ann') and now - float(rec.get('ann_ts') or 0) < ANN_TTL):
        return True
    return False


def extras_missing(codes, items, need_biz=True, need_ann=True):
    """返回缓存里缺/过期、需要联网补的代码列表（保持入参顺序、去重）。"""
    now = time.time()
    out, seen = [], set()
    for c in codes or []:
        c = str(c or '').strip()
        if not c or c in seen:
            continue
        seen.add(c)
        if extras_stale((items or {}).get(c), now, need_biz, need_ann):
            out.append(c)
    return out


def fetch_biz(code, timeout=8):
    """取主营构成（东财 F10），返回 {biz, biz_income, biz_ratio, biz_date, biz_items}。"""
    out = {'biz': '', 'biz_income': '', 'biz_ratio': '', 'biz_date': '', 'biz_items': []}
    try:
        from utils.main_business_service import fetch_main_business_composition
        r = fetch_main_business_composition(code, timeout=timeout) or {}
        items = r.get('items') or []
        out['biz_date'] = str(r.get('report_date') or '')
        out['biz_items'] = [[str(x.get('name') or ''), str(x.get('income_str') or ''),
                             str(x.get('ratio') or ''), str(x.get('yoy') or '')]
                            for x in items[:6]]
        if items:
            top = max(items, key=lambda x: float(x.get('ratio_val') or 0))
            out['biz'] = str(top.get('name') or '')
            out['biz_income'] = str(top.get('income_str') or '')
            out['biz_ratio'] = str(top.get('ratio') or '')
    except Exception as e:
        print('[控盘选股] 主营取数失败(%s): %s' % (code, e), flush=True)
    return out


def fetch_ann(code, count=5):
    """取最新公告，返回 [[date, title, url], ...]（按时间倒序，最多 count 条）。"""
    try:
        from data.announcement_provider import get_announcement_provider
        lst = get_announcement_provider().get_announcements(str(code), count=count) or []
        return [[str(a.get('date') or ''), str(a.get('title') or ''),
                 str(a.get('url') or '')] for a in lst[:count]]
    except Exception as e:
        print('[控盘选股] 公告取数失败(%s): %s' % (code, e), flush=True)
        return []


def fetch_extras_one(code, need_biz=True, need_ann=True, timeout=8, old=None):
    """补单只：把新拿到的字段与旧记录合并（某一项失败时保留旧值）。"""
    rec = dict(old) if isinstance(old, dict) else {}
    now = time.time()
    if need_biz:
        b = fetch_biz(code, timeout=timeout)
        rec.update(b)
        rec['biz_ts'] = now
    if need_ann:
        rec['ann'] = fetch_ann(code)
        rec['ann_ts'] = now
    rec['code'] = str(code)
    return rec


def fetch_extras(codes, items, workers=6, progress_cb=None, cancel_cb=None,
                 save_every=100, path=None, timeout=8):
    """并发补一批股票的「主营收入 + 最新公告」，原地更新 items 并定期落盘。

    codes        要补的代码（一般来自 extras_missing）
    items        已有缓存 dict（会被**原地更新**，便于界面直接用）
    workers      并发线程数（对上游限流友好，默认 6）
    返回 (items, stats)  stats: {'total','done','ok','err','elapsed'}
    """
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
                    stats['done'] = done[0]
                    if progress_cb is not None and (done[0] % 5 == 0 or done[0] == len(codes)):
                        try:
                            progress_cb(done[0], len(codes), '补主营/公告 %d/%d'
                                        % (done[0], len(codes)))
                        except Exception:
                            pass
                    if save_every and done[0] % int(save_every) == 0:
                        save_extras(items, path)
    except Exception as e:
        print('[控盘选股] 补数线程池异常: %s' % e, flush=True)
    if path is not False:
        save_extras(items, path)
    stats['elapsed'] = round(time.perf_counter() - t0, 1)
    return items, stats


def fmt_biz(rec):
    """主营收入列 → (显示文本, tooltip)。没数据返回 ('', '')。"""
    if not isinstance(rec, dict):
        return '', ''
    name = str(rec.get('biz') or '')
    if not name:
        return '', ''
    income = str(rec.get('biz_income') or '')
    ratio = str(rec.get('biz_ratio') or '')
    text = ('%s %s' % (name, income)).strip()
    lines = ['主营构成（报告期 %s）' % (rec.get('biz_date') or '-')]
    for it in (rec.get('biz_items') or [])[:6]:
        try:
            _n, _inc, _r, _y = (list(it) + ['', '', '', ''])[:4]
        except Exception:
            continue
        lines.append('  %s ｜ %s ｜ 占比%s ｜ 同比%s' % (_n, _inc or '-', _r or '-', _y or '-'))
    if ratio:
        lines.append('首项占比 %s' % ratio)
    return text, '\\n'.join(lines)


def fmt_ann(rec):
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
    return text, '\\n'.join(lines)


'''

n = s.count(ANCHOR)
assert n == 1, '锚点命中 %d 次' % n
s = s.replace(ANCHOR, NEW + ANCHOR, 1)

if not os.path.isfile(SVC + '.bak_before_extras'):
    shutil.copy2(SVC, SVC + '.bak_before_extras')
    print('备份: %s.bak_before_extras' % SVC)
io.open(SVC, 'w', encoding='utf-8', newline='').write(s)

import py_compile   # noqa: E402
b = io.open(SVC, 'rb').read()
print('control_screen_service.py: 行=%d CRLF=%d 裸LF=%d 字节=%d'
      % (b.count(b'\n'), b.count(b'\r\n'), b.count(b'\n') - b.count(b'\r\n'), len(b)))
assert b.count(b'\r\n') == 0
py_compile.compile(SVC, cfile=os.path.join(tempfile.gettempdir(), 'cs_extras.pyc'), doraise=True)
print('语法校验通过')
