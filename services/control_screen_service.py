# -*- coding: utf-8 -*-
"""控盘选股页 数据服务 —— 全市场按「控盘标准」扫描，供「控盘选股」页面使用。

为什么单独一个服务
------------------
现有 services.control_profile.compute_one 是「逐只、按需」查询（约 28ms/只，
按行调用没问题，但 4400 只全市场逐只读 duckdb 要 2 分多钟）。
本服务改为**一次性批量读本地 K 线**（实测 52.9 万行 / 1.15 秒），
再逐只算因子（控盘 3.7ms + 观察因子 1.9ms），全市场约 30 秒。

口径 —— 全部复用现有单一来源，**不另写一套**：
    K线    data/cache/kline_cache.duckdb（只读本地，不做网络兜底）
    控盘分  strategy.base.TechnicalIndicators.estimate_control_score
    阶段    strategy.base.TechnicalIndicators.judge_wash_or_distribute
    位置    近120日位置 (close - min120) / (max120 - min120)  ← 与 control_profile 逐字一致
    文案    services.band_pattern_engine._ctrl_note(...)      ← 阈值/开关只在引擎里定义一处
    观察因子 bottom_volume_stack / red_fat_green_thin / is_c4_candidate /
            is_c6_candidate / detect_probe / detect_distribution_pattern / detect_markup /
            detect_breakdown_recover（破位—收复双向判据）/
            detect_volume_regime（量能分位：地量/天量/缩量上涨）
    短标签  五阶段词表在 services.control_profile（obs_tag_pairs / obs_stages），
            日K建仓表与本页共用一份，本页按「建仓→试盘→洗盘→拉升→出货」出标签，
            并支持按阶段筛选（apply_filters(stage=...)）
    短标签  services.control_profile.ctrl_label（白名单，不会把观察类文案误判成「候选」）
    题材    data.limit_up_reason_db.get_last_limit_up_reason（最近一次涨停原因，
            与「日K建仓」「竞价」同源；空串=库里没有该股的含 '+' 题材）

与 control_profile 的关系：本服务不替换它，页面之外的所有列表仍走 control_profile；
本服务的结果已用「逐只与 control_profile.compute_one 全量比对」验证一致（见 tools 下的验证脚本）。

线程：scan_market 必须在后台线程调用（约 30 秒），progress_cb 从该线程回调。
"""
import io
import json
import os
import re
import sys
import threading
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.control_profile import (STAGE_PICK, obs_tag_pairs as _obs_tag_pairs,
                                      obs_stages as _obs_stages)

KLINE_DB = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
SNAPSHOT_PATH = os.path.join(PROJECT_ROOT, 'data', 'cache', 'control_screen.json')

# 股票池：主板 + 创业板（用户已确认可买创业板）；科创板/北交所仍剔除
UNIVERSE_PREFIXES = ('60', '00', '30')
EXCLUDE_PREFIXES = ('688', '689', '8', '4', '920')
MIN_BARS = 60           # 与 control_profile / 引擎一致：不足 60 根不算
BARS_LIMIT = 120        # 控盘分与位置都用最近 120 根（与 control_profile 一致）

OBS_ALL = '全部'
OBS_ANY = '有任一观察'
OBS_NO_MARKUP = '排除拉升（未启动）'
OBS_PROBE = '仅试盘观察'
OBS_C46 = '仅C4/C6观察'
OBS_OPTIONS = (OBS_ALL, OBS_ANY, OBS_NO_MARKUP, OBS_PROBE, OBS_C46)

# 「阶段」筛选：按操盘手法五阶段归属筛（一只股票可同时属于多阶段）。
# 选项与阶段归属映射都在 services.control_profile 里定义一处，UI 直接引用。
STAGE_OPTIONS = STAGE_PICK


# ============================================================
# 股票池 / 名称
# ============================================================
def is_universe_code(code):
    """是否属于本页扫描范围：主板 + 创业板，剔除科创板 / 北交所 / 非6位代码。"""
    c = str(code or '').strip()
    if len(c) != 6 or not c.isdigit():
        return False
    if c.startswith(EXCLUDE_PREFIXES):
        return False
    return c.startswith(UNIVERSE_PREFIXES)


def code_name_map():
    """{code: 名称}。来源 utils.stock_name_manager（本地缓存，失败返回 {}）。"""
    out = {}
    try:
        from utils.stock_name_manager import get_all_stock_names
        for _n, _c in (get_all_stock_names() or {}).items():
            _c = str(_c or '').strip()
            if _c and _c not in out:
                out[_c] = str(_n or '').strip()
    except Exception:
        pass
    return out


def is_st_name(name):
    """ST / *ST 判定，与 data.stock_list_provider._is_st_stock 同一口径（不吃「退市」）。"""
    up = str(name or '').upper()
    return ('ST' in up) or ('*ST' in up)


# ============================================================
# 涨停题材（最近一次涨停原因）
# ============================================================
def limit_up_theme(code):
    """最近一次涨停原因 -> (reason, date, lbc, industry)。

    与「日K建仓」（atr_t_widget）/「竞价」（auction_filter_widget）**同一来源**：
        data.limit_up_reason_db.get_last_limit_up_reason(code)
      · 先查 source='wencai'，再查任意来源但 reason 必须含 '+'（真题材串；
        纯时间格式的 reason 不算）
      · 库里没有该股 / 无含 '+' 的题材 -> 返回 ('', '', 0, '')
    库里出现过的股票 3529 只（2025-09-15 ~ 至今）；单只查询实测 0.3ms，
    4400 只约 1.2 秒，所以直接在扫描线程里逐只取。
    """
    try:
        from data.limit_up_reason_db import get_last_limit_up_reason
        r = get_last_limit_up_reason(str(code))
        if not r:
            return '', '', 0, ''
        try:
            _lbc = int(r[2] or 0)
        except Exception:
            _lbc = 0
        return str(r[0] or ''), str(r[1] or ''), _lbc, str(r[3] or '')
    except Exception:
        return '', '', 0, ''


# ============================================================
# 批量读 K 线（本服务的关键：一次 SQL 拿全市场）
# ============================================================
def load_all_bars(limit_bars=BARS_LIMIT, codes=None):
    """一次性读全市场最近 limit_bars 根日K，返回 {code: [bar(dict), ...]}（按日期升序）。

    bar 结构与 services.kline_cache_service.get_latest_kline 完全一致：
        {'date','open','high','low','close','volume'}
    只读本地库；异常时退回逐只读取（慢但不会没结果）。
    """
    keep = None
    if codes is not None:
        keep = set(str(c) for c in codes)
    out = {}
    try:
        import duckdb
        con = duckdb.connect(KLINE_DB, read_only=True)
        try:
            rows = con.execute("""
                SELECT code, date, open, high, low, close, volume FROM (
                    SELECT code, date, open, high, low, close, volume,
                           ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                    FROM kline_cache
                ) WHERE rn <= ?
                ORDER BY code, date
            """, [int(limit_bars)]).fetchall()
        finally:
            con.close()
        for r in rows:
            c = str(r[0] or '').strip()
            if not is_universe_code(c):
                continue
            if keep is not None and c not in keep:
                continue
            out.setdefault(c, []).append({
                'date': str(r[1]),
                'open': float(r[2] or 0), 'high': float(r[3] or 0),
                'low': float(r[4] or 0), 'close': float(r[5] or 0),
                'volume': float(r[6] or 0),
            })
        return out
    except Exception as e:
        print(f'[控盘选股] 批量读K线失败，改逐只读取: {e}', flush=True)
    # 兜底：逐只读（慢）
    try:
        from services.kline_cache_service import get_all_cached_codes, get_latest_kline
        for c in get_all_cached_codes():
            c = str(c or '').strip()
            if not is_universe_code(c):
                continue
            if keep is not None and c not in keep:
                continue
            b = get_latest_kline(c, count=limit_bars)
            if b:
                out[c] = b
    except Exception as e:
        print(f'[控盘选股] 逐只读取也失败: {e}', flush=True)
    return out


# ============================================================
# 单只计算
# ============================================================
def compute_stock(code, bars, name='', ti=None, engine=None):
    """算单只的「控盘画像」。数据不足 / 异常返回 None（不抛）。

    返回 dict：
        code / name / price / pct / score / stage / pos / data_date / note /
        label（候选|出货|洗盘|''）/ observe（观察标签 list）/
        probe_ok / probe_stage / dist_type / markup_type / c4_ok / c6_ok /
        stack_score / redfat_ratio
    """
    try:
        if not bars or len(bars) < MIN_BARS:
            return None
        if engine is None:
            import services.band_pattern_engine as engine
        if ti is None:
            from strategy.base import TechnicalIndicators as _TI
            ti = _TI()
        df = engine._bars_to_df(bars)
        if df is None:
            return None

        score = float(ti.estimate_control_score(df))
        stage = ti.judge_wash_or_distribute(df)
        _t = df['close'].tail(120)
        _lo, _hi = float(_t.min()), float(_t.max())
        pos = (float(df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)

        stack = ti.bottom_volume_stack(df) or {}
        redfat = ti.red_fat_green_thin(df) or {}
        c4 = ti.is_c4_candidate(df, ctrl_score=score) or {}
        c6 = ti.is_c6_candidate(df) or {}
        probe = ti.detect_probe(df) or {}
        distp = ti.detect_distribution_pattern(df) or {}
        markup = ti.detect_markup(df) or {}
        # A/B 批次的两个因子（破位—收复双向判据 / 量能分位）。此前只写库、界面看不到，
        # 2026-10-11 起接入本页：既进 note（悬停可见），也进「观察」列与「阶段」筛选。
        brk = ti.detect_breakdown_recover(df) or {}
        vreg = ti.detect_volume_regime(df) or {}

        note = engine._ctrl_note(
            score, stage, pos,
            stack.get('score'), redfat.get('score'),
            c4.get('n_ok'), c6.get('n_ok'),
            probe.get('ok'), distp.get('type'), markup.get('type'),
            brk.get('type'), vreg.get('tags'))

        last = bars[-1]
        prev = bars[-2]['close'] if len(bars) > 1 else last['close']
        price = float(last.get('close') or 0)
        pct = 0.0
        if prev:
            pct = (price - prev) / float(prev) * 100.0

        label, _color = ('', '')
        try:
            from services.control_profile import ctrl_label
            label, _color = ctrl_label('', note)
        except Exception:
            pass

        rec = {
            'code': str(code), 'name': str(name or ''),
            'price': round(price, 2), 'pct': round(pct, 2),
            'score': round(score, 2), 'stage': str(stage or ''),
            'pos': round(float(pos), 4),
            'data_date': str(last.get('date') or '')[:10],
            'note': str(note or ''), 'label': label,
            'probe_ok': bool(probe.get('ok')),
            'probe_stage': str(probe.get('stage') or ''),
            'dist_type': str(distp.get('type') or ''),
            'markup_type': str(markup.get('type') or ''),
            'c4_ok': bool(c4.get('n_ok') == 5), 'c4_n': int(c4.get('n_ok') or 0),
            'c6_ok': bool(c6.get('n_ok') == 2), 'c6_n': int(c6.get('n_ok') or 0),
            'stack_score': round(float(stack.get('score') or 0.0), 1),
            'redfat_ratio': round(float(redfat.get('ratio') or 0.0), 2),
            'stack_ok': bool(stack.get('ok')),
            'redfat_ok': bool(redfat.get('ok')),
            'brk_type': str(brk.get('type') or ''),
            'vreg_tags': str(vreg.get('tags') or ''),
            'vreg_pct': (round(float(vreg.get('pct')), 1)
                         if vreg.get('pct') is not None else None),
            # 涨停题材（最近一次涨停原因）：默认空，由 scan_market 统一填，见 limit_up_theme()
            'theme': '', 'theme_date': '', 'theme_lbc': 0, 'theme_ind': '',
        }
        # 五阶段短标签（词表在 services.control_profile，日K建仓表与本页共用一份）
        _pairs = _obs_tag_pairs(
            stack_ok=rec['stack_ok'], redfat_ok=rec['redfat_ok'],
            probe_ok=rec['probe_ok'], c4_ok=rec['c4_ok'], c6_ok=rec['c6_ok'],
            brk_type=rec['brk_type'], vreg_tags=rec['vreg_tags'],
            dist_type=rec['dist_type'], markup_type=rec['markup_type'])
        rec['obs_pairs'] = [[t, lv] for t, lv in _pairs]   # 快照要落 JSON，用 list
        rec['observe'] = [t for t, lv in _pairs]
        rec['stages'] = _obs_stages(_pairs)
        return rec
    except Exception:
        return None


def observe_tags(rec):
    """五阶段观察/风险短标签，供表格「观察」列显示。

    2026-10-11 起词表移到 services.control_profile.obs_tag_pairs（日K建仓表与本页
    共用一份，避免两处词不一致）；本函数保留为薄封装，旧调用方无需改。
    输出顺序固定：建仓 → 试盘 → 洗盘 → 拉升 → 出货 → 观察规则(C4/C6)。
    """
    try:
        return [t for t, _lv in obs_tag_pairs(rec)]
    except Exception:
        return []


def obs_tag_pairs(rec):
    """按 rec 的因子字段生成 [(短标签, level)]（兼容老快照：字段缺就当没命中）。"""
    try:
        return _obs_tag_pairs(
            stack_ok=bool(rec.get('stack_ok')),
            redfat_ok=bool(rec.get('redfat_ok')),
            probe_ok=bool(rec.get('probe_ok')),
            c4_ok=bool(rec.get('c4_ok')),
            c6_ok=bool(rec.get('c6_ok')),
            brk_type=rec.get('brk_type') or '',
            vreg_tags=rec.get('vreg_tags') or '',
            dist_type=rec.get('dist_type') or '',
            markup_type=rec.get('markup_type') or '')
    except Exception:
        return []


def stages_of(rec):
    """阶段归属（list）：优先用扫描时算好的 stages；老快照缺列时从观察文本回推。"""
    try:
        st = rec.get('stages')
        if st:
            return list(st)
        return _obs_stages(obs_tag_pairs(rec))
    except Exception:
        return []


# ============================================================
# 全市场扫描
# ============================================================
def scan_market(codes=None, bars=None, progress_cb=None, cancel_cb=None,
                progress_every=150):
    """全市场扫描，返回 (rows, stats)。

    codes      None = 用本地缓存里的全部主板+创业板代码
    bars       传了就用它（避免重复读库），否则内部 load_all_bars()
    progress_cb(done, total, msg)  从**调用线程**回调（给 UI 用要自己转信号）
    cancel_cb  () -> bool          返回 True 立刻中止
    只读本地数据；不写库、不改任何文件。
    """
    t0 = time.perf_counter()
    stats = {'universe': 0, 'ok': 0, 'skip_bars': 0, 'fail': 0,
             'elapsed': 0.0, 'data_date': '', 'theme_ok': 0}
    if bars is None:
        bars = load_all_bars()
    if codes is None:
        codes = sorted(bars.keys())
    codes = [str(c) for c in codes if is_universe_code(c)]
    stats['universe'] = len(codes)

    import services.band_pattern_engine as E
    from strategy.base import TechnicalIndicators as TI
    ti = TI()
    names = code_name_map()

    rows = []
    total = len(codes)
    for i, c in enumerate(codes):
        if cancel_cb is not None:
            try:
                if cancel_cb():
                    break
            except Exception:
                pass
        b = bars.get(c)
        if not b or len(b) < MIN_BARS:
            stats['skip_bars'] += 1
        else:
            rec = compute_stock(c, b, names.get(c, ''), ti=ti, engine=E)
            if rec is None:
                stats['fail'] += 1
            else:
                # 涨停题材：最近一次涨停原因（与日K建仓同一来源，空串=库里没查到）
                _th, _thd, _thl, _thi = limit_up_theme(c)
                rec['theme'], rec['theme_date'] = _th, _thd
                rec['theme_lbc'], rec['theme_ind'] = _thl, _thi
                if _th:
                    stats['theme_ok'] += 1
                rows.append(rec)
                stats['ok'] += 1
        if progress_cb is not None and ((i + 1) % progress_every == 0 or i + 1 == total):
            try:
                progress_cb(i + 1, total, '正在计算 %d/%d' % (i + 1, total))
            except Exception:
                pass
    rows.sort(key=lambda r: float(r.get('score') or 0), reverse=True)
    stats['elapsed'] = round(time.perf_counter() - t0, 1)
    _dates = [r.get('data_date') for r in rows if r.get('data_date')]
    stats['data_date'] = max(_dates) if _dates else ''
    return rows, stats


# ============================================================
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
#   最新公告  东财公告接口（主源）→ 新浪财经公告页（次源，东财被限流时顶上来）
#             → data.announcement_provider（巨潮兜底）
# 三源 + 按主机限速（公告 0.3s/次、主营 0.2s/次）+ 失败退避 15 分钟 + 连续失败熔断，
# 是因为 2026-10-11 实测「978 只 × 2 源 / 61 秒」把东财撞成 567、巨潮撞成 403。
# ============================================================
EXTRAS_PATH = os.path.join(PROJECT_ROOT, 'data', 'cache', 'ctrl_screen_extras.json')
BIZ_TTL = 30 * 24 * 3600      # 主营构成命中：30 天（季报/中报才变）
BIZ_EMPTY_TTL = 24 * 3600     # 主营构成空结果：1 天后重试
ANN_TTL = 6 * 3600            # 最新公告命中：6 小时
ANN_EMPTY_TTL = 2 * 3600      # 公告空结果：2 小时后重试
_TIMESTAMP_KEYS = ('biz_ts', 'ann_ts')

# 公告主源：东方财富公告接口（不需要 orgId、全板性覆盖；项目 ui\watchlist_panel.py
# L2485 已用同一接口）。实测单线程 23/23 命中、并发 6 线程 0.023s/只；
# 而巨潮 orgId 有新老两套格式、且并发下只有 25/40，所以降为兜底。
ANN_URL = ('http://np-anotice-stock.eastmoney.com/api/security/ann'
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
    r"(\d{4}-\d{2}-\d{2})&nbsp;<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>")

# 上游风控后的「退避窗口」：失败只记标记，15 分钟内不再重撞，之后自动重试
BIZ_FAIL_COOLDOWN = 15 * 60
ANN_FAIL_COOLDOWN = 15 * 60

# 按「主机桶」限速（多线程共享一个节拍，避免把 IP 撞进风控）
_BM_LOCK = threading.Lock()
_BM_LAST = {}
ANN_MIN_INTERVAL = 0.30      # 公告桶（东财/新浪/巨潮共用）
BIZ_MIN_INTERVAL = 0.20      # 主营桶（东财 F10）


def _throttle(bucket, interval):
    """按桶限速：同一桶内全局串行，最小间隔 interval 秒。"""
    with _BM_LOCK:
        now = time.time()
        wait = (_BM_LAST.get(bucket) or 0.0) + float(interval) - now
        if wait > 0:
            time.sleep(wait)
        _BM_LAST[bucket] = time.time()


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
    """取主营构成（东财 F10），返回 (dict, ok)。

    dict: {biz, biz_income, biz_ratio, biz_date, biz_items}
    ok=False = 上游没给出有效响应（限流/网络）→ 调用方只记失败标记、保留旧值。
    """
    out = {'biz': '', 'biz_income': '', 'biz_ratio': '', 'biz_date': '', 'biz_items': []}
    try:
        from utils.main_business_service import fetch_main_business_composition
        _throttle('biz', BIZ_MIN_INTERVAL)
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
        return out, False
    return out, bool(out.get('biz_items') or out.get('biz_date'))


def fetch_ann_em(code, count=5, timeout=6):
    """东财公告接口（主源）。返回 [[date, title, url, type], ...]；
    请求失败返回 None（以便与「成功但上游就是空」区分开）。"""
    try:
        import requests
        _throttle('ann', ANN_MIN_INTERVAL)
        r = requests.get(ANN_URL % (int(count), str(code)), headers=ANN_HDR, timeout=timeout)
        if r.status_code != 200:
            return None            # 567 等风控页：不是「没有公告」，是没拿到响应
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


def fetch_ann_sina(code, count=5, timeout=8):
    """次源：新浪财经「公司公告」页解析。返回 [[date, title, url, type], ...]
    或 None（没拿到响应）。成功但无公告返回 []。"""
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
    """取最新公告，返回 ([[date, title, url, type], ...], 源名, ok)。

    三源依次尝试，**只要有一个源给出有效响应就算成功**（哪怕结果是空列表）：
      主源  东财公告接口（字段最全、不需 orgId）
      次源  新浪财经公告页（东财被限流时顶上来，全板性）
      兜底  巨潮资讯网 data.announcement_provider（要 orgId，部分代码解析不出）
    ok=False = 三个源都没拿到有效响应（限流/断网）→ 只记失败标记，15 分钟后重试。
    """
    got = fetch_ann_em(code, count=count, timeout=timeout)     # None=没拿到, []=真没有
    if got is not None:
        return got, ('eastmoney' if got else ''), True
    got = fetch_ann_sina(code, count=count, timeout=timeout)
    if got is not None:
        return got, ('sina' if got else ''), True
    try:
        from data.announcement_provider import get_announcement_provider
        from data.stock_identity_provider import get_stock_identity_provider
        # orgId 是方法不是模块函数（原写法 import get_org_id 必抛 ImportError，
        # 导致巨潮这一层其实一直没生效 → 已修正为单例方法调用）
        if get_stock_identity_provider().get_org_id(str(code)):
            lst = get_announcement_provider().get_announcements(str(code), count=count) or []
            if lst:
                return [[str(a.get('date') or ''), str(a.get('title') or ''),
                         str(a.get('url') or ''), str(a.get('type') or '')]
                        for a in lst[:count]], 'cninfo', True
    except Exception as e:
        print('[控盘选股] 公告兜底源失败(%s): %s' % (code, e), flush=True)
    return [], '', False


def fetch_extras_one(code, need_biz=True, need_ann=True, timeout=8, old=None):
    """补单只：把新拿到的字段与旧记录合并（某一项失败时保留旧值）。"""
    rec = dict(old) if isinstance(old, dict) else {}
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
    return rec


def fetch_extras(codes, items, workers=3, progress_cb=None, cancel_cb=None,
                 save_every=100, path=None, timeout=8, fail_circuit=12):
    """并发补一批股票的「主营收入 + 最新公告」，原地更新 items 并定期落盘。

    codes        要补的代码（一般来自 extras_missing）
    items        已有缓存 dict（会被**原地更新**，便于界面直接用）
    workers      并发线程数（提速交给「按主机限速」，所以默认 3 就够）
    fail_circuit 连续多少只「主营+公告都失败」就判定被整体风控、本轮停手（0=关闭）
    返回 (items, stats)  stats: {'total','done','ok','err','elapsed',
                                 'biz_ok','ann_ok','biz_fail','ann_fail','aborted'}
    """
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
            _old = items.get(c)
            # 按字段判：只拉真正过期的那一项（重试公告时不再白撞主营接口）
            _need_biz = extras_stale(_old, need_biz=True, need_ann=False)
            _need_ann = extras_stale(_old, need_biz=False, need_ann=True)
            if not (_need_biz or _need_ann):
                return c, _old
            rec = fetch_extras_one(c, need_biz=_need_biz, need_ann=_need_ann,
                                   timeout=timeout, old=_old)
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
                    stats['done'] = done[0]
                    if progress_cb is not None and (done[0] % 5 == 0 or done[0] == len(codes)):
                        try:
                            progress_cb(done[0], len(codes), '补主营/公告 %d/%d'
                                        % (done[0], len(codes)))
                        except Exception:
                            pass
                    if save_every and done[0] % int(save_every) == 0:
                        save_extras(items, path)
                if abort_ev.is_set():
                    break
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
    text = _clip(('%s %s' % (name, income)).strip(), 22)
    lines = ['主营构成（报告期 %s）' % (rec.get('biz_date') or '-')]
    for it in (rec.get('biz_items') or [])[:6]:
        try:
            _n, _inc, _r, _y = (list(it) + ['', '', '', ''])[:4]
        except Exception:
            continue
        lines.append('  %s ｜ %s ｜ 占比%s ｜ 同比%s' % (_n, _inc or '-', _r or '-', _y or '-'))
    if ratio:
        lines.append('首项占比 %s' % ratio)
    return text, '\n'.join(lines)


def _strip_ann_prefix(title):
    """去掉公告标题里开头的「简称:」（如「甘咨询:甘肃工程咨询集团…」）。

    只影响单元格显示（简称与左边的「股票名称」列重复、白占宽度）；
    tooltip 里给的是上游原始标题，不做任何改写。
    """
    t = str(title or '')
    for i, ch in enumerate(t[:10]):
        if ch in ':：':
            return t[i + 1:].strip() if i >= 1 else t
    return t


def _strip_company_prefix(title):
    """去掉公告标题开头的「公司全称」——只剥真正的全称，剥不动就原样返回。

    东财/新浪的公告标题常把公司全称写在最前面（如「甘肃工程咨询集团股份有限公司
    2026年半年度权益分派实施公告」），而最左边的「股票名称」列已经写了公司，
    全称白占三四十个字符、把真正的公告主题挤到看不见。
    保守规则（三条同时成立才剥）：公司名 ≥6 字、含「股份」或「集团」、且前缀里
    不含「关于/全资/控股/拟」等主题词 —— 避免把「关于全资子公司…提供担保的进展
    公告」这类标题误剥成「为全资子公司…」。
    """
    t = str(title or '')
    _p = t.find('公司')
    if _p < 6 or _p > 40:
        return t
    _head = t[:_p + 2]
    if ('股份' not in _head) and ('集团' not in _head):
        return t
    if any(w in _head for w in ('关于', '全资', '控股', '拟', '的')):
        return t
    _rest = t[_p + 2:].strip()
    return _rest if len(_rest) >= 6 else t


def _clip(txt, n):
    """单元格文本收敛（tooltip 里始终给原文，这里只影响一格显示）。"""
    t = str(txt or '')
    return t if len(t) <= n else (t[:n - 1] + '…')


def fmt_ann(rec):
    """最新公告列 → (显示文本, tooltip)。没数据返回 ('', '')。"""
    if not isinstance(rec, dict):
        return '', ''
    lst = rec.get('ann') or []
    if not lst:
        return '', ''
    _d, _t = str(lst[0][0] or ''), str(lst[0][1] or '')
    _short = _d[5:] if len(_d) >= 10 else _d          # YYYY-MM-DD → MM-DD
    _title = _strip_company_prefix(_strip_ann_prefix(_t))
    text = _clip(('%s %s' % (_short, _title)).strip(), 30)
    _src = {'eastmoney': '东方财富', 'sina': '新浪财经',
            'cninfo': '巨潮资讯'}.get(str(rec.get('ann_src') or ''), '')
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
    return text, '\n'.join(lines)


# ============================================================
# 快照（页面重开不用再等 30 秒）
# ============================================================
def save_snapshot(rows, stats=None, path=None):
    """把扫描结果写成本地 JSON 快照。返回写入路径，失败返回 ''。"""
    p = path or SNAPSHOT_PATH
    try:
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        payload = {
            'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_date': (stats or {}).get('data_date', ''),
            'universe': (stats or {}).get('universe', 0),
            'ok': (stats or {}).get('ok', len(rows or [])),
            'elapsed': (stats or {}).get('elapsed', 0.0),
            'rows': list(rows or []),
        }
        with io.open(p, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        return p
    except Exception as e:
        print(f'[控盘选股] 写快照失败: {e}', flush=True)
        return ''


def load_snapshot(path=None):
    """读快照，返回 {'saved_at','data_date','universe','rows',...} 或 None。"""
    p = path or SNAPSHOT_PATH
    try:
        if not os.path.isfile(p):
            return None
        with io.open(p, 'r', encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict) or not isinstance(d.get('rows'), list):
            return None
        return d
    except Exception:
        return None


# ============================================================
# 筛选 / 导出
# ============================================================
def apply_filters(rows, min_score=85.0, pos_max=None, exclude_dist=True,
                  min_price=6.0, drop_st=True, obs=OBS_ALL, stage=None):
    """按页面上的条件筛一遍。全部条件都是「筛掉」，不改任何分数。

    stage：'建仓'/'试盘'/'洗盘'/'拉升'/'出货' 之一（'全部'/None = 不筛）。
           归属来自五阶段观察标签（services.control_profile.TAG_STAGE），
           一只股票可同时属于多个阶段（例如 拉升+出货形态 都命中）。
    """
    out = []
    for r in rows or []:
        try:
            if float(r.get('score') or 0) < float(min_score):
                continue
            if pos_max is not None and float(r.get('pos') or 0) > float(pos_max):
                continue
            if exclude_dist and str(r.get('stage')) == 'distribute':
                continue
            if min_price and float(r.get('price') or 0) < float(min_price):
                continue
            if drop_st and is_st_name(r.get('name')):
                continue
            if obs != OBS_ALL:
                _tags = r.get('observe') or []
                if obs == OBS_ANY and not _tags:
                    continue
                if obs == OBS_NO_MARKUP and r.get('markup_type'):
                    continue
                if obs == OBS_PROBE and not r.get('probe_ok'):
                    continue
                if obs == OBS_C46 and not (r.get('c4_ok') or r.get('c6_ok')):
                    continue
            if stage and stage != '全部' and stage not in stages_of(r):
                continue
            out.append(r)
        except Exception:
            continue
    out.sort(key=lambda r: float(r.get('score') or 0), reverse=True)
    return out


def export_codes(rows, path):
    """导出 6 位代码（每行一个、无表头，可直接导入同花顺）。返回写入条数。"""
    codes, seen = [], set()
    for r in rows or []:
        c = str(r.get('code') or '').strip()
        if len(c) == 6 and c.isdigit() and c not in seen:
            seen.add(c)
            codes.append(c)
    if not codes:
        return 0
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(codes))
        f.write('\n')
    return len(codes)
