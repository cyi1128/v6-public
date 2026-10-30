# -*- coding: utf-8 -*-
"""今日板块 / 行业 / 题材异动引擎

【数据源】
  1) data/limit_up_reason.db  表 limit_up_reasons —— 今日涨停股 + 涨停原因(题材) + 行业
  2) data/cache/kline_cache.duckdb              —— 最新交易日涨跌幅 + 全市场 MA20
  3) data/cache/industry_full_map.json          —— 全市场 5211 只 code -> 申万一级行业(粗)

【可介入标的 picks（V3.1 新增）】
  原版 members 只有当日涨停股，「成分股」列全是已封板票，用户只能干看。
  现在每条板块记录额外给 picks —— 该板块里「还没涨停、但已经在动」的
  标的，用于选择可以介入的股票：
    · 非当日涨停
    · 涨幅 1.0% ~ 9.0%（还没封板，但已有资金）
    · 量比 >= 1.2（有量能；腾讯源取不到量比时不做该过滤）
    · 现价 >= MA20（跌破20日均线不碰）
    · 股价 >= 6 元、非 ST（用户既定过滤）
  成分池自建，见 _load_pools()：为什么不用 industry_full_map.json。
  实时行情走腾讯源（utils.http_market_data.get_realtime_quotes_http），
  实测 3499 只主板 1.8 秒返回 3495 只，60 秒缓存。

【为什么不用东财概念板块接口】
  strategy.theme_analyzer.get_concept_market() 走
  https://push2delay.eastmoney.com/api/qt/clist/get
  实测重试 3 次全部 RemoteDisconnected，返回 0 条。板块行情改为本地聚合。

【输出】
  {
    'ok': bool,
    'date': '2026-09-24',
    'themes':     [条目...],   # 题材异动（涨停原因拆词聚合）
    'industries': [条目...],   # 行业异动（涨停股行业聚合 + 全市场行业均涨幅）
    'error': '',
  }
  条目:
  {
    'name': '海峡两岸', 'kind': '题材',
    'count': 10,            # 今日涨停家数
    'avg_pct': 10.92,       # 成员当日均涨幅
    'max_pct': 19.98,
    'lead_code': '000592', 'lead_name': '平潭发展',
    'members': [['000592', '平潭发展', 10.02], ...],   # 按涨幅降序
    'all_avg_pct': None,    # 仅行业: 全市场该行业均涨幅
    'all_count': None,      # 仅行业: 全市场该行业样本数
    'picks': [[code, name, pct, vol_ratio, price], ...],  # 可介入标的(未涨停)
  }
"""
import io
import json
import os
import re
import sqlite3
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_LU_DB = os.path.join(ROOT, 'data', 'limit_up_reason.db')
_KLINE_DB = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
_IND_MAP = os.path.join(ROOT, 'data', 'cache', 'industry_full_map.json')

_TTL = 90.0             # 结果缓存 90 秒。原为 300 秒，但 picks 是「现在
                        # 还能不能上车」，5 分钟就过时了；改为 90 秒后
                        # UI 每 30 秒刷新里每 3 次真算一次（后台线程，约 2 秒）
_MIN_STOCK = 2          # 同题材/同行业至少 2 家才算异动
_KW_MIN, _KW_MAX = 2, 12

# ---- 可介入标的（picks）----
_RT_TTL = 60.0          # 腾讯实时行情缓存 60 秒（实测全市场 1.8 秒）
_POOL_TTL = 600.0       # 成分池缓存 10 分钟（涨停库是历史积累，变化慢）
_PICK_MIN_PCT = 1.0     # 候选涨幅下限：要有资金进
_PICK_MAX_PCT = 5.0     # 候选涨幅上限：还没封板才买得进
                              # 9.0 -> 5.0（2026-10-10，实测驱动）：5603 条历史样本里
                              # 上限 9/8/7/6/5% 对应 5日胜率 41.6/41.7/41.8/42.3/43.1%，
                              # 30日 43.9/44.3/44.7/45.4/45.7%，累计 35.2/35.4/35.9/36.6/38.0%，
                              # 单调上升；样本仍保留 69%。依据 tools\_sweep_pick_thresholds.py。
                              # 量比/价格下限不能提：量比越高胜率越低（反直觉但单调）。
_PICK_MIN_VR = 1.2      # 候选量比下限：要有量能
_PICK_MIN_PRICE = 6.0   # 候选股价下限：6 元以下剔除（用户既定要求）
_PICK_MIN_AMOUNT = 2.0e8     # 机构门槛：当日成交额 ≥ 2 亿
_PICK_MIN_CMV = 20.0         # 机构门槛：流通市值 ≥ 20 亿（游资盘不碰）
_VWAP_DEV_MAX = 0.5          # 量化痕迹：|最新价 − VWAP| ≤ 0.5%
_VWAP_VR_MIN = 1.5           # 量化痕迹：量比 ≥ 1.5
_SEAL_ROTTEN = 0.10          # 封成比 < 0.10 且 ≥2 板 = 烂板
_PICK_TOP = 5           # 每行最多展示几个候选

_cache = {'t': 0.0, 'd': None}
_lock = threading.Lock()
_rt = {'t': 0.0, 'q': {}}                     # 实时行情缓存
_pool = {'t': 0.0, 'ind': {}, 'th': {}, 'lu': set()}   # 成分池缓存
_ma20 = {'t': 0.0, 'm': {}}                   # MA20 缓存


# --------------------------------------------------------------------------
# 基础取数
# --------------------------------------------------------------------------
def _today():
    """最近一个真实交易日 'YYYY-MM-DD'"""
    try:
        from utils import trade_calendar as tc
        return tc.get_latest_trading_date()
    except Exception:
        return time.strftime('%Y-%m-%d')


def _load_pct():
    """最新交易日涨幅 {code: pct}，返回 (date, dict)"""
    if not os.path.exists(_KLINE_DB):
        return '', {}
    import duckdb
    con = duckdb.connect(_KLINE_DB, read_only=True)
    try:
        d = con.execute('SELECT MAX(date) FROM kline_cache').fetchone()[0]
        if not d:
            return '', {}
        q = ('SELECT a.code, (a.close - b.close) / b.close * 100 AS chg '
             'FROM kline_cache a JOIN kline_cache b ON a.code = b.code '
             'AND b.date = (SELECT MAX(date) FROM kline_cache WHERE date < a.date) '
             'WHERE a.date = ?')
        out = {}
        for code, g in con.execute(q, [d]).fetchall():
            if g is not None:
                out[str(code)] = float(g)
        return str(d), out
    finally:
        con.close()


def _load_limit_up():
    """最新一期涨停原因，返回 (date, [rec...])；date 原样 'YYYYMMDD'"""
    if not os.path.exists(_LU_DB):
        return '', []
    c = sqlite3.connect(_LU_DB)
    try:
        d = c.execute('SELECT MAX(date) FROM limit_up_reasons').fetchone()[0]
        if not d:
            return '', []
        # 龙头排序需要的字段（time/lbc/fund/amount/hs/zbc/ltsz）。
        # ltsz 用于算封单强度 = 封单额 / 流通市值，绝对封单额不可比。
        # 老库若没有这些列，降级为只读基础字段，不让整块挂掉。
        try:
            rows = c.execute(
                'SELECT code,name,industry,reason,time,lbc,fund,amount,hs,zbc,'
                'ltsz,pct_chg '
                'FROM limit_up_reasons WHERE date=?', (d,)).fetchall()
        except Exception:
            rows = [(r[0], r[1], r[2], r[3], '', 0, 0.0, 0.0, 0.0, 0, 0.0, None)
                    for r in c.execute('SELECT code,name,industry,reason '
                                       'FROM limit_up_reasons WHERE date=?', (d,))]
        recs = [{'code': str(r[0]), 'name': r[1] or '', 'industry': r[2] or '',
                 'reason': r[3] or '', 'time': (r[4] or '').strip(),
                 'lbc': int(r[5] or 0), 'fund': float(r[6] or 0.0),
                 'amount': float(r[7] or 0.0), 'hs': float(r[8] or 0.0),
                 'zbc': int(r[9] or 0), 'ltsz': float(r[10] or 0.0),
                 'pct': r[11]}
                for r in rows]
        return str(d), recs
    finally:
        c.close()


def _load_ind_map():
    if not os.path.exists(_IND_MAP):
        return {}
    try:
        return json.load(io.open(_IND_MAP, 'r', encoding='utf-8'))
    except Exception:
        return {}


def _load_realtime():
    """腾讯源全市场主板实时行情（60 秒缓存）。

    实测 3499 只主板 1.8 秒返回 3495 只，稳定不限流（东财 clist 实测
    连续 10 次只成功 1 次）。失败时沿用上一份缓存，绝不让主流程挂掉。
    返回 {code: {name, price, pct_chg, vol_ratio, ...}}
    """
    now = time.time()
    if _rt['q'] and (now - _rt['t']) < _RT_TTL:
        return _rt['q']
    try:
        from utils.http_market_data import (get_realtime_quotes_http,
                                            _load_stock_codes)
        sl = _load_stock_codes() or []
        codes = [str(st.get('code') or '') for st in sl]
        # 2026-10-10：放行 30（创业板）
        codes = [c for c in codes if c.startswith(('60', '00', '30'))]
        if not codes:
            return _rt['q']
        q = get_realtime_quotes_http(codes) or {}
        if q:
            _rt['q'] = q
            _rt['t'] = now
    except Exception as e:
        print('[板块异动] 实时行情失败(沿用上一份): %s' % e, flush=True)
    return _rt['q']


def _load_pools():
    """从涨停原因库自建「细分行业池 / 题材池 / 最新涨停名单」（10 分钟缓存）。

    为什么不用 data/cache/industry_full_map.json：
      那份是申万一级 30 个粗行业（机械设备/电子/化工…），而涨停库的
      industry 是东财细分行业（电池/汽车零部/化学制品…），两边名字对不上，
      用它查「电池」永远是 0 只成分，候选恒为空。故直接拿涨停库自身建池。
    池子含义：历史上至少涨停过一次的股票 —— 即板块内的活跃标的，
      正好是「可介入」要看的对象（二线跟风 / 补涨）。
    """
    now = time.time()
    if _pool['t'] and (now - _pool['t']) < _POOL_TTL:
        return _pool
    ind, th, lu = {}, {}, set()
    if not os.path.exists(_LU_DB):
        return _pool
    try:
        c = sqlite3.connect(_LU_DB)
        cur = c.cursor()
        d = cur.execute('SELECT MAX(date) FROM limit_up_reasons').fetchone()[0]
        if d:
            lu = {str(r[0]) for r in cur.execute(
                'SELECT code FROM limit_up_reasons WHERE date=?', (d,))}
        for code, industry, reason in cur.execute(
                'SELECT code,industry,reason FROM limit_up_reasons'):
            code = str(code or '')
            if not code.startswith(('60', '00', '30')):
                continue
            industry = (industry or '').strip()
            if industry:
                ind.setdefault(industry, set()).add(code)
            if reason:
                for t in re.split(r'[+＋·、/]', reason):
                    t = t.strip()
                    for ch in ('\u201c', '\u201d', '\u2018', '\u2019',
                               '\u300c', '\u300d'):
                        t = t.replace(ch, '')
                    t = t.strip()
                    if _KW_MIN <= len(t) <= _KW_MAX:
                        th.setdefault(t, set()).add(code)
        c.close()
    except Exception as e:
        print('[板块异动] 成分池构建失败: %s' % e, flush=True)
        return _pool
    if ind or th:
        _pool['t'] = now
        _pool['ind'] = ind
        _pool['th'] = th
        _pool['lu'] = lu
    return _pool


def _load_ma20():
    """全市场 MA20（最近 20 个完整交易日收盘均值，600 秒缓存）。

    一条窗口函数 SQL 聚合，实测 3000+ 只 0.04 秒。取不到返回 {}，
    调用方不做 MA20 过滤（既不误杀，也不会让主流程失败）。
    """
    now = time.time()
    if _ma20['m'] and (now - _ma20['t']) < _POOL_TTL:
        return _ma20['m']
    m = {}
    try:
        import duckdb
        if not os.path.exists(_KLINE_DB):
            return _ma20['m']
        con = duckdb.connect(_KLINE_DB, read_only=True)
        try:
            rows = con.execute(
                'WITH ranked AS ('
                '  SELECT code, close,'
                '         ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn'
                '  FROM kline_cache'
                ') '
                'SELECT code, AVG(close) AS ma20, COUNT(*) AS n'
                ' FROM ranked WHERE rn <= 20 GROUP BY code').fetchall()
        finally:
            con.close()
        for r in rows:
            try:
                code, v, n = str(r[0]), float(r[1]), int(r[2])
                if code and v > 0 and n >= 20:
                    m[code] = v
            except (TypeError, ValueError, IndexError):
                continue
    except Exception as e:
        print('[板块异动] MA20 聚合失败(本轮不做该过滤): %s' % e, flush=True)
        return _ma20['m']
    if m:
        _ma20['m'] = m
        _ma20['t'] = now
    return _ma20['m']


def _pick_candidates(members, quotes, lu, ma20):
    """从板块成分池里挑「可介入」标的：未涨停、还在涨、有量、在 MA20 上。

    members 是该板块的成分股集合（可能很大，如「国企改革」250+ 只），
    quotes 是全市场实时快照，用查表而非网络请求，所以整体开销极小。
    """
    if not members or not quotes:
        return []
    out = []
    for code in members:
        if code in lu:                      # 已涨停 -> 是龙头，不是介入标的
            continue
        q = quotes.get(code)
        if not q:
            continue
        try:
            pct = float(q.get('pct_chg') or 0)
            px = float(q.get('price') or 0)
            vr = float(q.get('vol_ratio') or 0)
        except (TypeError, ValueError):
            continue
        if px <= 0 or pct < _PICK_MIN_PCT or pct >= _PICK_MAX_PCT:
            continue
        if px < _PICK_MIN_PRICE:            # 6 元以下剔除（用户既定要求）
            continue
        _nm = (q.get('name') or '').upper().replace(' ', '')
        if 'ST' in _nm:                     # ST / *ST 剔除
            continue
        if vr and vr < _PICK_MIN_VR:        # 量比取不到时不拦
            continue
        # ---- 机构/量化执行标准 ----
        # 1) 流动性门槛：算法单按参与率拆单，成交额太小的票冲击成本吃不住
        # 2) 容量门槛：流通市值过小的游资盘/庄股，机构不进
        # 3) 量化痕迹：|最新价 − VWAP| 小且量比高 —— 算法单执行完的典型
        #    结果是价格贴着当日均价走，而不是脉冲式拉升
        amt = float(q.get('amount') or 0.0)
        cmv = float(q.get('circ_mv') or 0.0)
        hs = float(q.get('turnover') or 0.0)
        vol = float(q.get('volume') or 0.0)
        if amt and amt < _PICK_MIN_AMOUNT:
            continue
        if cmv and cmv < _PICK_MIN_CMV:
            continue
        vwap = (amt / (vol * 100.0)) if (amt > 0 and vol > 0) else 0.0
        dev = ((px - vwap) / vwap * 100.0) if vwap > 0 else None
        inst = 1 if (dev is not None and abs(dev) <= _VWAP_DEV_MAX
                     and vr >= _VWAP_VR_MIN) else 0
        # ---- 用户硬门槛：现价必须 >= MA20（等于或大于）----
        # ma20 整表加载成功（非空）时按硬门槛执行：
        #   · 在均线上（等于也算过）        -> 通过，并记录距 MA20 涨幅
        #   · 跌破均线                     -> 剔除
        #   · 表里没有它（K线不足 20 根）   -> 无法确认站上均线，剔除
        # 整表为空（kline_cache 被占用/加载失败）时不做过滤，
        # 避免把候选一次性全清空（_load_ma20 的既定兜底）。
        gap = None
        m20 = ma20.get(code) if ma20 else None
        if ma20:
            if (not m20) or px < m20:
                continue
            gap = round((px - m20) / m20 * 100.0, 2)   # 距MA20 涨幅%
        out.append([code, q.get('name') or '', round(pct, 2),
                    round(vr, 2), round(px, 2), gap,
                    round(amt / 1e8, 2), round(cmv, 1), round(hs, 2),
                    (round(dev, 2) if dev is not None else None), inst])
    # 排序即机构标准：量化痕迹优先 → 成交额大优先 → 涨幅优先
    out.sort(key=lambda x: (-x[10], -x[6], -x[2]))
    return out[:_PICK_TOP]


def _split_reason(reason):
    """'海峡两岸+工程机械+盾构机' -> ['海峡两岸','工程机械','盾构机']"""
    if not reason:
        return []
    parts = re.split(r'[+＋·、/]', reason)
    out = []
    seen = set()
    for p in parts:
        p = p.strip().strip('* ')
        # 去掉中文引号（'“华”字辈' -> '华字辈'），只去引号不删其他字符
        for ch in ('“', '”', '‘', '’', '「', '」'):
            p = p.replace(ch, '')
        p = p.strip()
        if _KW_MIN <= len(p) <= _KW_MAX and p not in seen:
            seen.add(p)
            out.append(p)
    return out


# 封板时段分档（③ 首封时间不再精确到秒比较 / ⑤ 识别尾盘偷袭板）。
# 秒级首封时间几乎永不并列，会把后面的封单强度、炸板等键全部架空 ——
# 实测 2026-10-09 共 69 只涨停股，没有任何一对首封时间相同，
# 所以旧版第 4 键（封单额）和第 5 键（涨幅）一次都没被触发过。
# 改成先归「时段档」，同档内再用封单强度区分，后面的键才能真正起作用。
_SEAL_SLOTS = (
    ('09:25:00', 0, '竞价秒板'),    # 集合竞价直接成交，一字板/秒板，最强
    ('09:35:00', 1, '开盘封板'),
    ('10:00:00', 2, '早盘封板'),
    ('11:30:00', 3, '午前封板'),
    ('14:00:00', 4, '午后封板'),
    ('14:30:00', 5, '尾盘前封板'),
    ('15:00:00', 6, '尾盘偷袭'),    # 14:30 后拉板，次日溢价通常最差
)
_SEAL_SLOT_NONE = 7                 # 无首封时间（老数据）沉底


def _seal_slot(t):
    """首封时间 -> 封板时段档位（0 最强）。返回 (档位, 档名)"""
    t = (t or '').strip()
    if not t:
        return _SEAL_SLOT_NONE, '--'
    for hi, idx, label in _SEAL_SLOTS:
        if t <= hi:
            return idx, label
    return len(_SEAL_SLOTS), '收盘封板'


def _seal_strength(rec):
    """封单强度 = 封单额 / 流通市值（②）。

    绝对封单额不可比：同一天里 3.36 亿封在 14.6 亿流通盘上是 23.02%，
    1.12 亿封在 319.7 亿流通盘上只有 0.35%，相差 65 倍。
    拿绝对额排龙头，等于在比谁的盘子大。
    """
    ltsz = rec.get('ltsz') or 0.0
    if ltsz <= 0:
        return 0.0
    return (rec.get('fund') or 0.0) / ltsz


def _seal_ratio(rec):
    """封成比 = 封单额 / 当日成交额。

    业内判涨停板强度的主口径，衡量「封单还能接住今天多少卖盘」。
    实测 2026-10-09 的 69 只涨停股：
      时代万恒 5板 0.69 亿成交 封成比 3.33 ｜ 新华传媒 9板 6.26 亿 2.27
      澳弘电子 9板 10.67 亿成交 封成比 0.03 ｜ 九阳股份 5板 20.63 亿 0.04
      三人行   1板（炸板 6 次）    封成比 0.01
    也就是说：高位板不等于强板，封单相对成交额薄如纸的，是烂板。
    """
    amt = rec.get('amount') or 0.0
    if amt <= 0:
        return 0.0
    return (rec.get('fund') or 0.0) / amt


def _is_rotten(rec):
    """烂板：2 板及以上，且封成比 < 0.10（封单远小于当日成交额）。"""
    return ((rec.get('lbc') or 0) >= 2) and _seal_ratio(rec) < _SEAL_ROTTEN


def _dragon_key(rec, pct):
    """① 情绪龙头排序键（升序）：
    连板身位 > 烂板(沉底) > 封板时段 > 封成比 > 封单强度 > 秒级时间。

    身位（连板高度）代表题材情绪高度，权重最高，用来判断题材能走多高；
    同身位内先把烂板沉到最后（封成比 < 0.10 的高位板是假板）；
    好板之间比封板时段（越早越强，尾盘偷袭最弱），
    再比封成比、封单强度，最后秒级时间兜底。
    它回答的是「这个题材谁最强」，不是「明天买谁」。
    """
    t = (rec.get('time') or '').strip()
    return (0 if t else 1,
            -(rec.get('lbc') or 0),
            1 if _is_rotten(rec) else 0,
            _seal_slot(t)[0],
            -_seal_ratio(rec),
            -_seal_strength(rec),
            t or '99:99')


# ① 次日接力参考：身位越低、封板越早、封单强度越大越好。
# 4 板以上不再作为接力标的（高位接力赔率差，那是情绪榜要看的）；
# 14:30 后的尾盘偷袭板也排除。
_ENTRY_MAX_LBC = 3
_ENTRY_MAX_SLOT = 5


def _entry_key(rec):
    """次日接力排序键（升序）：身位低 > 封板早 > 封成比大 > 封单强度大

    1 板和 2 板归同一档：首板是「发动」、二板是「确认」，各有各的道理，
    不能让身位把封板时段和封成比架空 —— 否则就退回到「板数大者胜」，
    而板数恰恰是被封成比证伪的那个判据。
    """
    lbc = rec.get('lbc') or 1
    pos = 0 if lbc <= 2 else (1 if lbc == 3 else 2)
    return (pos, _seal_slot(rec.get('time'))[0],
            -_seal_ratio(rec), -_seal_strength(rec))


def _entry_of(mem, pct):
    """从涨停股里挑 1 只次日接力参考，没有合格的返回 None"""
    cand = [m for m in mem
            if (m.get('lbc') or 1) <= _ENTRY_MAX_LBC
            and _seal_slot(m.get('time'))[0] <= _ENTRY_MAX_SLOT
            and not _is_rotten(m)]          # 烂板不做接力标的
    if not cand:
        return None
    m = sorted(cand, key=_entry_key)[0]
    slot = _seal_slot(m.get('time'))
    return {'code': m['code'], 'name': m['name'],
            'pct': pct.get(m['code'], 0.0),
            'time': (m.get('time') or ''), 'slot_name': slot[1],
            'lbc': m.get('lbc') or 0, 'fund': m.get('fund') or 0.0,
            'amount': m.get('amount') or 0.0,
            'ratio': _seal_ratio(m),
            'strength': _seal_strength(m), 'zbc': m.get('zbc') or 0}


def _member_pct(rec, kline_pct):
    """成员涨幅：优先用涨停池自带的当天涨幅（与涨停名单同源），kline 兜底。

    盘中时 kline_cache 最新还停在上一交易日，若直接用 kline 会与
    今天的涨停名单错位一天（日期对不上、涨幅张冠李戴），故以池内值为准。
    """
    v = rec.get('pct')
    if v is None or v == 0:
        v = kline_pct.get(rec['code'])
    return v if v is not None else -999.0


def _dragons_of(mem, pct, n=3):
    """取排序后的前 n 名作为龙一/龙二/龙三，带上判断依据"""
    out = []
    for m in mem[:n]:
        slot = _seal_slot(m.get('time'))
        out.append({'code': m['code'], 'name': m['name'],
                    'pct': pct.get(m['code'], 0.0),
                    'time': (m.get('time') or ''),
                    'slot': slot[0], 'slot_name': slot[1],
                    'lbc': m.get('lbc') or 0,
                    'fund': m.get('fund') or 0.0,
                    'ratio': _seal_ratio(m),
                    'rotten': _is_rotten(m),
                    'strength': _seal_strength(m),
                    'zbc': m.get('zbc') or 0})
    return out


def _is_st(name):
    n = (name or '').upper().replace(' ', '')
    return 'ST' in n or '*ST' in n


# --------------------------------------------------------------------------
# 主构建
# --------------------------------------------------------------------------
def _build():
    t0 = time.time()
    kdate, pct = _load_pct()
    ludate, recs = _load_limit_up()
    imap = _load_ind_map()
    # 可介入标的所需：实时行情 + 成分池 + MA20（任何一个失败都不影响原有输出）
    quotes = _load_realtime()
    pools = _load_pools()
    lu_codes = pools.get('lu') or set()
    ma20 = _load_ma20()

    if not recs:
        return {'ok': False, 'date': kdate or _today(), 'themes': [],
                'industries': [], 'error': '涨停原因库无数据'}

    # ---------- 题材异动：涨停原因拆词聚合 ----------
    grp = {}
    for r in recs:
        for kw in _split_reason(r['reason']):
            grp.setdefault(kw, []).append(r)
    # 成员涨幅按「涨停池当天涨幅优先」取值，避免盘中与 kline 错位一天
    mpct = {r['code']: _member_pct(r, pct) for r in recs}
    themes = []
    for kw, mem in grp.items():
        if len(mem) < _MIN_STOCK:
            continue
        mem2 = sorted(mem, key=lambda x: _dragon_key(x, pct))
        gs = [mpct[m['code']] for m in mem2 if m['code'] in mpct]
        if not gs:
            continue
        lead = mem2[0]
        themes.append({
            'name': kw, 'kind': '题材', 'count': len(mem),
            'avg_pct': sum(gs) / len(gs), 'max_pct': max(gs),
            'lead_code': lead['code'], 'lead_name': lead['name'],
            'lead_pct': mpct.get(lead['code'], 0.0),
            'dragons': _dragons_of(mem2, mpct),
            'entry': _entry_of(mem2, mpct),
            'members': [[m['code'], m['name'], mpct.get(m['code'], 0.0)]
                        for m in mem2],
            'all_avg_pct': None, 'all_count': None,
            'picks': _pick_candidates(pools['th'].get(kw) or set(),
                                      quotes, lu_codes, ma20),
        })

    # ---------- 行业异动：涨停股行业聚合 + 全市场该行业均涨幅 ----------
    ind_grp = {}
    for r in recs:
        if r['industry']:
            ind_grp.setdefault(r['industry'].strip(), []).append(r)
    all_ind = {}
    for code, ind in imap.items():
        g = pct.get(str(code))
        if g is not None:
            all_ind.setdefault(ind, []).append(g)

    industries = []
    for ind, mem in ind_grp.items():
        if len(mem) < _MIN_STOCK:
            continue
        mem2 = sorted(mem, key=lambda x: _dragon_key(x, pct))
        gs = [mpct[m['code']] for m in mem2 if m['code'] in mpct]
        if not gs:
            continue
        ag = all_ind.get(ind) or []
        lead = mem2[0]
        industries.append({
            'name': ind, 'kind': '行业', 'count': len(mem),
            'avg_pct': sum(gs) / len(gs), 'max_pct': max(gs),
            'lead_code': lead['code'], 'lead_name': lead['name'],
            'lead_pct': mpct.get(lead['code'], 0.0),
            'dragons': _dragons_of(mem2, mpct),
            'entry': _entry_of(mem2, mpct),
            'members': [[m['code'], m['name'], mpct.get(m['code'], 0.0)]
                        for m in mem2],
            'all_avg_pct': (sum(ag) / len(ag)) if ag else None,
            'all_count': len(ag) or None,
            'picks': _pick_candidates(pools['ind'].get(ind) or set(),
                                      quotes, lu_codes, ma20),
        })

    # 排序：家数降序 -> 均涨幅降序
    themes.sort(key=lambda x: (-x['count'], -x['avg_pct']))
    industries.sort(key=lambda x: (-x['count'], -x['avg_pct']))

    return {
        'ok': True,
        'date': kdate or ludate,
        'ludate': ludate,
        'themes': themes,
        'industries': industries,
        'pct_sample': len(pct),
        'lu_count': len(recs),
        'rt_count': len(quotes),
        'pick_rows': sum(1 for x in (themes + industries) if x.get('picks')),
        'cost': round(time.time() - t0, 2),
        'error': '',
    }


def get_board_anomaly(force=False):
    """取今日板块/行业/题材异动（5 分钟缓存）。任何异常都不抛出，返回 ok=False。"""
    with _lock:
        if (not force and _cache['d'] and
                time.time() - _cache['t'] < _TTL):
            return _cache['d']
        try:
            d = _build()
        except Exception as e:
            d = {'ok': False, 'date': _today(), 'themes': [], 'industries': [],
                 'error': '%s: %s' % (type(e).__name__, e)}
        _cache['t'] = time.time()
        _cache['d'] = d
        return d


def get_flat_rows(data=None, limit=None):
    """拍平成 UI 表格行：题材 + 行业混排（家数降序）"""
    d = data if data is not None else get_board_anomaly()
    rows = list(d.get('themes') or []) + list(d.get('industries') or [])
    rows.sort(key=lambda x: (-x['count'], -x['avg_pct']))
    return rows[:limit] if limit else rows


def is_trading_now():
    """是否在连续竞价时段（9:30~11:30 / 13:00~15:00），用于推送节流"""
    try:
        from utils import trade_calendar as tc
        if hasattr(tc, 'is_trade_day') and not tc.is_trade_day():
            return False
    except Exception:
        pass
    hm = time.strftime('%H%M')
    return ('0930' <= hm <= '1130') or ('1300' <= hm <= '1500')
