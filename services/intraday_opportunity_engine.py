# -*- coding: utf-8 -*-
"""
盘中机会引擎 V2.2（intraday_opportunity_engine.py）
================================================================
完整闭环：全市场异动 → 题材/产业链扩散 → 候选发现 → 自身响应
         → 二次确认 → 金铲子 → ATR实时跟踪

V2.2 升级（用户需求）：
1. 交易日统一：is_trading_day / get_latest_trading_date / is_market_open
   来自 utils/trade_calendar.py（真实交易日历优先，本地涨停库+指数日K缓存）
2. 休市逻辑：休市期间不产生新异动、不推进事件状态、不新增联动/机会、
   不运行新ATR跟踪；保留最近一个交易日完整盘中数据；
   界面显示 市场状态：休市 / 数据日期：最近交易日 / 模式：复盘
3. 状态机：UNRESPONDED → PREPARE → FIRST_EVENT → COOLING → SECOND_EVENT
   → CONFIRMED → ATR_TRACKING → INVALID
4. 预备候选 PREPARE：集群扩散中 + 关系真实 + 自身尚未明显启动
   → 提前进入金铲子预备区（只代表值得观察，绝不出买入结论）
5. 扩散检测：cluster_total / active_count / first_event_count /
   second_event_count / last_event_time / first_event_time /
   event_density / actual_path（只能由真实异动时间生成）
6. 候选股票不永久排除：只排除集群首发源；后续自身异动的股票
   可从候选转入 FIRST_EVENT → COOLING → SECOND_EVENT → CONFIRMED
7. processed_codes_this_cycle：同一轮每只股票最多一次状态迁移
8. 关系四级：DIRECT_CHAIN / CHAIN_MEMBER / SAME_THEME / INDUSTRY_RELATED
   （直接产业链优先，禁止普通关键词当产业链）
9. get_gold_shovel_candidates()：金铲子统一接口，只接收有效状态
10. ATR职责严格隔离：只读 atr_t_tracking.duckdb，绝不反向筛选全市场

保留（已验证不重写）：全市场 clist fid=f12 分页行情、腾讯5分钟线
真实异动时间回溯、多值产业链索引、涨停题材映射、ATR字段实测。
"""
import os
import sqlite3
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT_UP_DB = os.path.join(ROOT, 'data', 'limit_up_reason.db')
ATR_TRACK_DB = os.path.join(ROOT, 'data', 'cache', 'atr_t_tracking.duckdb')

# 主板 + 创业板代码前缀（2026-10-10 放行 300/301，用户可买创业板）
MAIN_PREFIX = ('600', '601', '603', '605', '000', '001', '002', '003',
               '300', '301')

# 低价股下限：现价低于该值的股票不进入异动检测 / 联动 / 盘中机会 / 金铲子。
# 口径 = 实时行情里的现价（f2），与日K建仓模块的 MIN_PRICE 保持一致。
MIN_PRICE = 6.0

# 全市场 MA20 缓存（秒）。第1层硬过滤用：现价 < MA20 的股票从行情池剔除。
# MA20 基于日K，盘中不变，不需要每轮重算；600 秒足够覆盖一个交易时段。
MA20_ALL_TTL = 600

# 异动检测阈值（保留V2.1已验证）
ANOMALY_PCT_JUMP = 1.0        # 30秒涨幅跳变>=1.0%
ANOMALY_VOL_RATIO = 2.0       # 量比>=2
ANOMALY_MIN_PCT = 0.5         # 最低涨幅门槛
ANOMALY_FIRSTSCAN_PCT = 1.0   # 首扫（无基准）粗判涨幅门槛
ANOMALY_FIRSTSCAN_VR = 1.5    # 首扫量比门槛
EVENT_COOLDOWN = 60           # 同一股票事件冷却（秒）
COOLING_SECONDS = 120         # 首次异动后冷却观察期（秒）
CLUSTER_WINDOW = 300          # 异动群时间窗口（秒，5分钟）
CLUSTER_MIN = 2               # 异动群最少股票数
STALE_EVENT_SECONDS = 1800    # 事件30分钟无更新视为过期
STALE_CLUSTER_SECONDS = 1800  # 群30分钟无更新清理
INVALID_TIMEOUT = 900         # 机会15分钟无推进失效
SCAN_INTERVAL = 25            # 扫描最小间隔（秒）

# 状态机（V2.2）
ST_UNRESPONDED = '尚未响应'
ST_PREPARE = '预备'
ST_FIRST_EVENT = '初步联动'
ST_COOLING = '冷却观察'
ST_SECOND_EVENT = '二次异动'
ST_CONFIRMED = '联动确认'
ST_ATR_TRACKING = 'ATR跟踪'
ST_INVALID = '失效'
ST_STARTED = '已启动'

# 金铲子接收的有效状态
GS_VALID = {ST_PREPARE, ST_FIRST_EVENT, ST_COOLING, ST_SECOND_EVENT,
            ST_CONFIRMED, ST_ATR_TRACKING}
# 金铲子内部分类
GS_CLASS = {
    ST_PREPARE: '预备',
    ST_FIRST_EVENT: '初步联动',
    ST_COOLING: '初步联动',
    ST_SECOND_EVENT: '联动确认',
    ST_CONFIRMED: '联动确认',
    ST_ATR_TRACKING: 'ATR跟踪',
}

# 扩散状态
DIFF_EXPANDING = '扩散中'
DIFF_WEAKENING = '扩散减弱'
DIFF_STOPPED = '扩散停止'

# 产业链位置（无可靠分层数据）
CHAIN_UNKNOWN = '未取得'

# 关系类型（四级，直接产业链优先）
REL_DIRECT_CHAIN = 'DIRECT_CHAIN'           # 直接产业链
REL_CHAIN_MEMBER = 'CHAIN_MEMBER'           # 产业链成员
REL_SAME_THEME = 'SAME_THEME'               # 同题材
REL_INDUSTRY_RELATED = 'INDUSTRY_RELATED'   # 行业相关
REL_UNKNOWN = 'UNKNOWN'

REL_CN = {
    REL_DIRECT_CHAIN: '产业链',
    REL_CHAIN_MEMBER: '链成员',
    REL_SAME_THEME: '同题材',
    REL_INDUSTRY_RELATED: '行业相关',
    REL_UNKNOWN: '未取得',
}

TIME_UNKNOWN = '历史异动时间未取得'


class IntradayOpportunityEngine:
    """盘中机会引擎V2.2（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self, restore=True):
        self._day = datetime.now().strftime('%Y-%m-%d')
        self._quotes = {}          # 当前全市场快照 {code: quote}
        self._prev = {}            # 上次全市场快照
        self._events = {}          # {code: event_dict}
        self._clusters = {}        # {key: cluster_dict}
        self._opportunities = {}   # {code: opp_dict}
        self._theme_map = {}       # {code: [theme,...]} 来自涨停原因库
        self._theme_industry = {}  # {theme: industry}
        self._chain_map = {}       # {chain: meta} 来自产业链映射
        self._stock_chains = {}    # {code: [chain,...]} 多值索引
        self._atr_ref = {}         # {code: atr_dict}
        self._pushed = set()       # 已推送的(code|status)
        self._backfill_cache = {}  # 5分钟线回溯缓存 {date|code: (time, accel)}
        self._stats = {}           # 统计链
        self._drop_reasons = defaultdict(int)  # 淘汰原因
        self._market_info = {'status': '休市', 'data_date': '', 'mode': '复盘'}
        self._last_scan = 0
        self._last_cal_refresh = 0
        self._scan_lock = threading.Lock()  # [NEW] 防两个模块并发scan()
        self._ma20_cache = {}               # [NEW] MA20内存缓存{code: (ts, result)}
        self._low_price_codes = set()        # [NEW] 本轮被 6 元下限剔除的代码
        self._px_cache = {}                  # [NEW] 兜底价格缓存 {code: (ts, price)}
        self._st_codes = set()               # [NEW] ST/退市股代码（跨轮累积）
        self._code_industry = {}             # [NEW] 股票代码 → 行业（本地库）
        self._ma20_all = {}                  # [NEW] 全市场MA20 {code: ma20}（第1层过滤用）
        self._ma20_all_ts = 0                # [NEW] 全市场MA20 缓存时间戳
        self._ma20_dropped = 0               # [NEW] 本轮第1层因低于MA20剔除的只数
        self._load_themes()
        self._load_code_industry()
        self._load_chain_map()
        self._load_atr()
        self._refresh_calendar_once()
        # ---- V2.3 交易日快照恢复 ----
        # _state_date = 当前状态归属的交易日（快照归属日）
        self._state_date = self._snapshot_trading_date()
        if restore:
            self._restore_snapshot(self._state_date)

    # ------------------------------------------------------------------
    # 交易日快照（V2.3：盘中持续保存 / 重启恢复 / 休市复盘读取）
    # ------------------------------------------------------------------
    @staticmethod
    def _snapshot_trading_date(now=None):
        """当前状态归属的交易日：今天已开盘(>=9:25)→今天；否则→最近交易日。"""
        from utils import trade_calendar as tc
        now = now or datetime.now()
        today = now.strftime('%Y-%m-%d')
        if tc.is_trading_day(today):
            # [FIX] 开盘前（9:25前）归属最近交易日，保留昨天复盘数据
            if now.hour < 9 or (now.hour == 9 and now.minute < 25):
                return tc.get_latest_trading_date(now)
            return today
        return tc.get_latest_trading_date(now)

    def _save_snapshot(self):
        """把当前引擎状态保存到归属交易日快照（JSON 可序列化）。"""
        try:
            from services import intraday_snapshot as snap
            sd = self._snapshot_trading_date()
            data = {
                'day': self._day,
                'state_date': self._state_date,
                'events': self._events,
                'clusters': self._clusters,
                'opportunities': self._opportunities,
                'stats': dict(self._stats or {}),
                'drop_reasons': dict(self._drop_reasons or {}),
                'pushed': sorted(self._pushed or []),
                'market_info': dict(self._market_info or {}),
            }
            return snap.save_section(sd, 'engine', data)
        except Exception:
            return False

    def _restore_snapshot(self, trading_date=None):
        """从指定交易日快照恢复引擎状态。成功返回 True，否则 False。"""
        try:
            from services import intraday_snapshot as snap
            td = trading_date or self._snapshot_trading_date()
            data = snap.load_section(td, 'engine') or {}
            if not data:
                return False
            self._events = data.get('events') or {}
            self._clusters = data.get('clusters') or {}
            self._opportunities = data.get('opportunities') or {}
            self._stats = dict(data.get('stats') or {})
            self._drop_reasons = defaultdict(int, data.get('drop_reasons') or {})
            self._pushed = set(data.get('pushed') or [])
            mi = data.get('market_info')
            if isinstance(mi, dict) and mi:
                self._market_info = mi
            if data.get('day'):
                self._day = data.get('day')
            self._state_date = data.get('state_date') or td
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 交易日历（真实日历优先）
    # ------------------------------------------------------------------
    def _refresh_calendar_once(self):
        """每天最多刷新一次交易日历（指数日K，失败静默保留本地数据）"""
        now = time.time()
        if now - self._last_cal_refresh < 3600:
            return
        self._last_cal_refresh = now
        try:
            from utils import trade_calendar as tc
            tc.refresh_from_market()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _load_themes(self):
        """从涨停原因库加载 股票→题材/行业 映射（只保留主板）"""
        self._theme_map = {}
        self._theme_industry = {}
        if not os.path.exists(LIMIT_UP_DB):
            return
        try:
            conn = sqlite3.connect(LIMIT_UP_DB)
            c = conn.cursor()
            c.execute("SELECT code, name, reason, industry FROM limit_up_reasons ORDER BY date DESC LIMIT 8000")
            for code, name, reason, industry in c.fetchall():
                if not code or not code.startswith(MAIN_PREFIX):
                    continue
                # 结果集按 date DESC 排列 → 同一只股票必须先出现的最新记录胜出。
                # 旧代码缺这一行，循环末尾会把窗口内【最老】一次题材覆盖上去，
                # 导致 _theme_map 长期停留在几个月前的旧题材（实测 600815：
                # 库里 9/24 是"海峡两岸"，引擎却读到 2026-04-27 的旧题材），
                # 板块批量异动因此大面积漏判。
                if code in self._theme_map:
                    continue
                tags = []
                if reason:
                    for t in reason.split('+'):
                        t = t.strip()
                        if not t or t.endswith('板') or len(t) <= 2:
                            continue
                        tags.append(t)
                if tags:
                    self._theme_map[code] = tags
                    if industry:
                        for t in tags:
                            self._theme_industry[t] = industry
            conn.close()
        except Exception as e:
            print(f'[机会引擎V2.2] 题材加载失败: {e}', flush=True)

    def _load_code_industry(self):
        """股票代码 → 行业（本地涨停原因库，零网络）。

        为什么要这一步：行情主源换成腾讯 qt.gtimg.cn 后，东财 clist 的
        f100(行业) 字段就没了，而行业被用于关系判定(INDUSTRY_RELATED)、
        板块涨幅(_get_sector_pct) 和界面展示。
        本地 limit_up_reasons 表实测有 3473 只股票的行业，足够覆盖主板。
        """
        self._code_industry = {}
        if not os.path.exists(LIMIT_UP_DB):
            return
        try:
            conn = sqlite3.connect(LIMIT_UP_DB)
            c = conn.cursor()
            c.execute("SELECT code, industry FROM limit_up_reasons "
                      "WHERE industry IS NOT NULL AND industry <> '' "
                      "ORDER BY date DESC")
            for code, industry in c.fetchall():
                if code and code not in self._code_industry:
                    self._code_industry[code] = industry
            conn.close()
        except Exception as e:
            print(f'[机会引擎] 行业映射加载失败: {e}', flush=True)

    def _load_all_ma20(self, force=False):
        """全市场 MA20（第1层硬过滤用）。

        数据源：本地 data/cache/kline_cache.duckdb，一条窗口函数 SQL 聚合。
        实测 3059 只耗时 0.04 秒，远快于逐只 get_latest_kline（约 26ms/只，
        全市场要 60 秒以上，那种做法在 25 秒扫描周期里不可行）。
        MA20 = 最近 20 个完整交易日收盘均值，要求至少 20 根 K 线。
        结果缓存 MA20_ALL_TTL 秒。
        取不到时返回上一份缓存或空 dict —— 空 dict 时本轮不做 MA20 过滤，
        既不误杀，也不会让主流程失败。
        """
        now = time.time()
        if not force and self._ma20_all and (now - self._ma20_all_ts) < MA20_ALL_TTL:
            return self._ma20_all
        try:
            from services.kline_cache_service import get_db_connection
            con = get_db_connection()
        except Exception as e:
            print(f'[MA20] 本地K线库连接失败(本轮不做MA20过滤): {e}', flush=True)
            return self._ma20_all
        try:
            rows = con.execute(
                'WITH ranked AS ('
                '  SELECT code, close,'
                '         ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn'
                '  FROM kline_cache'
                ') '
                'SELECT code, AVG(close) AS ma20, COUNT(*) AS n'
                ' FROM ranked WHERE rn <= 20 GROUP BY code'
            ).fetchall()
        except Exception as e:
            print(f'[MA20] 全市场均线聚合失败(本轮不做MA20过滤): {e}', flush=True)
            return self._ma20_all
        finally:
            try:
                con.close()
            except Exception:
                pass
        m = {}
        for r in rows:
            try:
                code, v, n = r[0], float(r[1]), int(r[2])
                if code and v > 0 and n >= 20:
                    m[code] = v
            except (TypeError, ValueError, IndexError):
                continue
        if m:
            self._ma20_all = m
            self._ma20_all_ts = now
        return self._ma20_all

    def _apply_ma20_filter(self):
        """第1层：现价 < MA20 的股票直接从行情池剔除。

        位置在第 1 层末尾（行情拉取完成后、异动检测之前）。因此低于 MA20
        的股票不会进入异动检测 / 聚类 / 候选池，从源头收敛，而不是等到
        第 4 层候选阶段才过滤。
        本地库没有该股 MA20 的保留，不误杀。
        """
        ma20 = self._load_all_ma20()
        if not ma20:
            self._ma20_dropped = 0
            return
        below = []
        for code, q in self._quotes.items():
            m = ma20.get(code)
            px = q.get('price') or 0
            if m and px and px < m:
                below.append(code)
        now_px = time.time()
        for code in below:
            # 剔除前把价格存进兜底价缓存：联动表的路径里没存价格，
            # 判断「是否跌破MA20」只能靠价格。若不预先留存，
            # _resolve_prices 会为这些股票发起网络请求，白白浪费一次拉取。
            px = (self._quotes.get(code) or {}).get('price') or 0
            if px:
                self._px_cache[code] = (now_px, px)
            self._quotes.pop(code, None)
        self._ma20_dropped = len(below)
        if below:
            print(f'[MA20] 第1层剔除低于MA20 {len(below)} 只，'
                  f'行情池剩余 {len(self._quotes)} 只', flush=True)

    def _px_of(self, code):
        """取某只股票的当前价：优先行情池，其次兜底价缓存。

        被第1层 MA20 过滤剔除的股票不在 _quotes 里，但价格已由
        _apply_ma20_filter 存进 _px_cache，这里能直接取到，不发起网络请求。
        """
        p = (self._quotes.get(code) or {}).get('price') or 0
        if p:
            return p
        hit = self._px_cache.get(code)
        return hit[1] if hit else 0

    def _is_below_ma20(self, code, price=None):
        """现价是否低于 MA20（第1层过滤之后的兜底判断）。

        为什么还要兜底：_opportunities 和 _clusters 都是跨轮累积的。
        某只股票在 A 轮站上 MA20 进了机会池/异动群，B 轮跌破后如果只靠
        第1层过滤，它会一直留在池子里（第1层只过滤当轮新拉进来的行情）。
        MA20 取不到时返回 False（不误杀）。
        """
        m = self._ma20_all.get(code)
        if not m:
            return False
        if price is None:
            price = self._px_of(code)
        if not price:
            return False
        return price < m

    def _load_chain_map(self):
        """从 data/industry_chain_map 加载产业链映射（DIRECT_CHAIN 数据源）
        建立多值索引 code → [chain, ...]（同一股票可属多条链，禁止dict覆盖）"""
        self._chain_map = {}
        self._stock_chains = {}
        try:
            from data.industry_chain_map import INDUSTRY_CHAIN_MAP
            self._chain_map = INDUSTRY_CHAIN_MAP
            multi = defaultdict(list)
            for chain, meta in INDUSTRY_CHAIN_MAP.items():
                for code, name in meta.get('stocks', []):
                    multi[code].append(chain)
            self._stock_chains = dict(multi)
        except Exception as e:
            print(f'[机会引擎V2.2] 产业链映射加载失败: {e}', flush=True)

    def _load_atr(self):
        """只读ATR持仓表（字段实测：code/name/cost/qty/anchor_vwap）"""
        self._atr_ref = {}
        try:
            import duckdb
            if not os.path.exists(ATR_TRACK_DB):
                return
            con = duckdb.connect(ATR_TRACK_DB, read_only=True)
            rows = con.execute(
                "SELECT code, name, cost, qty, anchor_vwap FROM holding"
            ).fetchall()
            con.close()
            for r in rows:
                self._atr_ref[r[0]] = {
                    'name': r[1], 'cost': r[2], 'qty': r[3],
                    'anchor_vwap': r[4],
                }
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 主扫描入口（休市逻辑）
    # ------------------------------------------------------------------
    def scan(self):
        now = time.time()
        if now - self._last_scan < SCAN_INTERVAL:
            return
        # [NEW] 串行化：两个模块同时调scan时，第二个直接等锁，不并发跑
        if not self._scan_lock.acquire(blocking=False):
            return  # 上一轮还在跑，跳过本次
        try:
            self._last_scan = now
            self._do_scan()
        finally:
            self._scan_lock.release()

    def _do_scan(self):
        from utils import trade_calendar as tc
        now_dt = datetime.now()
        today = now_dt.strftime('%Y-%m-%d')

        # V2.3 状态归属日：进入新交易日盘中 → 重置为当天（若当天已有快照则恢复，
        # 支持盘中重启继续推进）；非交易日 → 保留最近交易日快照状态（复盘）
        if tc.is_trading_day(today):
            # [FIX] 开盘前（9:25前）不切换日期，保留昨天复盘数据
            _before_open = (now_dt.hour < 9) or (now_dt.hour == 9 and now_dt.minute < 25)
            if not _before_open and self._state_date != today:
                self._init(restore=True)
        else:
            if today != self._day:
                self._day = today

        # 市场状态（供UI显示）
        self._market_info = tc.market_status_info(now_dt)
        if not self._market_info.get('data_date'):
            self._market_info['data_date'] = tc.get_latest_trading_date(now_dt)

        # 休市：不产生新异动/不推进事件状态/不新增联动/不新增机会/
        #       不运行新ATR跟踪/不清空上一交易日数据（复盘模式）
        if not tc.is_market_open(now_dt):
            # [NEW] 9:15-9:25 预热MA20缓存，避免开盘时集中查询卡UI
            if now_dt.hour == 9 and 15 <= now_dt.minute < 25:
                self._prewarm_ma20_cache()
            return

        self._refresh_calendar_once()
        self._fetch_quotes()
        self._detect_events()
        self._build_clusters()
        self._update_opportunities()
        self._update_stats()
        # V2.3 盘中持续保存：每轮正常扫描完成后更新当天快照
        # （09:31→...→14:59→15:00 最终状态，程序退出/重启可恢复）
        self._save_snapshot()

    def get_market_info(self):
        """市场状态：{status: 交易中/休市, data_date, mode: 实时/复盘}"""
        return dict(self._market_info)

    # ------------------------------------------------------------------
    # 复盘快照查询（V2.4：无快照明确提示，而非静默显示0）
    # ------------------------------------------------------------------
    def list_review_dates(self):
        """返回已有盘中快照的交易日列表（升序），供UI日期选择器。"""
        try:
            from services import intraday_snapshot as snap
            return snap.list_snapshot_dates()
        except Exception:
            return []

    def review_status(self):
        """复盘状态：{data_date, mode, has_snapshot, available_dates, reason}
        has_snapshot=False 时 reason 给出明确原因（UI据此提示，不静默0）。"""
        mi = dict(self._market_info or {})
        d = mi.get('data_date') or self._snapshot_trading_date()
        avail = self.list_review_dates()
        has = bool(d and d in avail)
        reason = ''
        if not has:
            if avail:
                reason = '交易日 %s 无持久化快照（仅有：%s），无法复盘' % (
                    d, ','.join(avail[-5:]))
            else:
                reason = '尚无任何交易日盘中快照（需交易日盘中运行后生成）'
        return {
            'data_date': d,
            'mode': mi.get('mode', '复盘'),
            'has_snapshot': has,
            'available_dates': avail,
            'reason': reason,
        }

    # ------------------------------------------------------------------
    # 行情扫描（全市场，保留V2.1：fid=f12 按代码分页，非涨幅TOP）
    # ------------------------------------------------------------------
    def _fetch_quotes(self):
        """拉全市场行情（主板 + 创业板 300/301；剔除低价 + ST/退市）。
        注：科创板 688/689、北交所 8xx/4xx/920 仍剔除；低价门槛见模块常量 MIN_PRICE。

        V2.9.6 换源：
          主源 腾讯 qt.gtimg.cn —— 实测 3498 只主板 1.91 秒返回 3494 只，
               稳定不限流；东财 clist 实测连续 10 次只成功 1 次。
          降级 东财 clist 分页 —— 腾讯整体失败时才用。
          行业 腾讯源不提供 f100，改从本地 limit_up_reasons 表补
               （见 _load_code_industry）。
        """
        new_q, low_add, st_add = {}, set(), set()
        try:
            new_q, low_add, st_add = self._fetch_quotes_tencent()
        except Exception as e:
            print(f'[行情] 腾讯源异常: {e}', flush=True)
        if not new_q:
            try:
                new_q, low_add, st_add = self._fetch_quotes_eastmoney()
            except Exception as e:
                print(f'[行情] 东财降级源异常: {e}', flush=True)
        if not new_q:
            return
        self._prev = self._quotes
        self._quotes = new_q
        # 低价 / ST 集合跨轮累积：本轮行情里出现过的股票必然合格，先移除；
        # 没出现的保留标记，避免某一轮接口异常把历史标记清空。
        self._low_price_codes = (set(self._low_price_codes) | low_add) - set(new_q.keys())
        self._st_codes = (set(self._st_codes) | st_add) - set(new_q.keys())
        # [NEW] 第1层 MA20 硬过滤：现价低于20日均价的股票在这里就剔除，
        # 不进入异动检测 / 聚类 / 候选池（原先只在第4层候选阶段过滤）。
        self._apply_ma20_filter()

    def _fetch_quotes_tencent(self):
        """腾讯源拉全市场主板行情。返回 (new_q, low_add, st_add)。"""
        from utils.http_market_data import (get_realtime_quotes_http,
                                            _load_stock_codes)
        stock_list = _load_stock_codes() or []
        codes, names = [], {}
        for st in stock_list:
            c = st.get('code', '')
            if not c or not c.startswith(MAIN_PREFIX):
                continue
            codes.append(c)
            names[c] = st.get('name', '')
        if not codes:
            return {}, set(), set()
        quotes = get_realtime_quotes_http(codes) or {}
        new_q, low_add, st_add = {}, set(), set()
        for code, q in quotes.items():
            try:
                name = q.get('name') or names.get(code, '')
                px = float(q.get('price') or 0)
                if not px:
                    continue
                if self._is_st_name(name):
                    st_add.add(code)
                    continue
                if px < MIN_PRICE:
                    low_add.add(code)
                    continue
                new_q[code] = {
                    'name': name,
                    'price': px,
                    'pct': float(q.get('pct_chg') or 0),
                    'vol': float(q.get('volume') or 0),
                    'amount': float(q.get('amount') or 0),
                    'vol_ratio': float(q.get('vol_ratio') or 0),
                    'turnover': float(q.get('turnover') or 0),
                    'last_close': float(q.get('last_close') or 0),
                    'industry': self._code_industry.get(code, ''),
                }
            except (ValueError, TypeError):
                continue
        return new_q, low_add, st_add

    def _fetch_quotes_eastmoney(self):
        """东财 clist 分页拉全市场（降级源）。返回 (new_q, low_add, st_add)。"""
        from utils.http_market_data import eastmoney_request
        new_q, low_add, st_add = {}, set(), set()

        def fetch_page(pn):
            try:
                return eastmoney_request('/api/qt/clist/get', {
                    'pn': str(pn), 'pz': '200', 'po': '1', 'np': '1',
                    'fltt': '2', 'invt': '2', 'fid': 'f12',
                    'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                    'fields': 'f12,f14,f2,f3,f5,f6,f8,f10,f18,f100',
                }, timeout=8)
            except Exception:
                return None

        first = fetch_page(1)
        if not first or not isinstance(first, dict):
            return {}, set(), set()
        total = 0
        try:
            total = int((first.get('data') or {}).get('total') or 0)
        except (TypeError, ValueError):
            pass
        if total <= 0:
            return {}, set(), set()
        pages = max(1, min(30, -(-total // 200)))

        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(fetch_page, pn): pn for pn in range(1, pages + 1)}
            for f in as_completed(futs):
                data = f.result()
                items = (data or {}).get('data', {}).get('diff', []) if isinstance(data, dict) else []
                if not items:
                    continue
                for it in items:
                    try:
                        code = it.get('f12', '')
                        if not code or not code.startswith(MAIN_PREFIX):
                            continue
                        name = it.get('f14', '') or ''
                        if self._is_st_name(name):
                            st_add.add(code)
                            continue
                        if float(it.get('f2', 0) or 0) < MIN_PRICE:
                            low_add.add(code)
                            continue
                        new_q[code] = {
                            'name': name,
                            'price': float(it.get('f2', 0) or 0),
                            'pct': float(it.get('f3', 0) or 0),
                            'vol': float(it.get('f5', 0) or 0),
                            'amount': float(it.get('f6', 0) or 0),
                            'vol_ratio': float(it.get('f10', 0) or 0),
                            'turnover': float(it.get('f8', 0) or 0),
                            'last_close': float(it.get('f18', 0) or 0),
                            'industry': it.get('f100', '') or self._code_industry.get(code, ''),
                        }
                    except (ValueError, TypeError):
                        continue
        return new_q, low_add, st_add

    def _backfill_anomaly_time(self, code):
        """
        用腾讯5分钟线回溯当天第一根满足异动的bar时间（分钟级精度）。
        返回 (first_time_str 或 None, recent_accel)。
        失败返回 (None, 0.0)，绝不伪造时间。
        """
        today = datetime.now().strftime('%Y-%m-%d')
        key = today + '|' + code
        if key in self._backfill_cache:
            return self._backfill_cache[key]
        result = (None, 0.0)
        try:
            from services.minute_kline import fetch_minute_5m
            df = fetch_minute_5m(code)
            if df is not None and not df.empty:
                df = df[df['datetime'].str.slice(0, 10) == today].sort_values('datetime')
                bars = df.to_dict('records')
                if bars:
                    first_ts = None
                    for i, bar in enumerate(bars):
                        o = bar['open']
                        c = bar['close']
                        v = bar['volume']
                        if o <= 0:
                            continue
                        bar_pct = (c - o) / o * 100.0
                        prev_v = bars[i - 1]['volume'] if i > 0 else 0
                        vol_ratio = (v / prev_v) if prev_v > 0 else 0
                        if bar_pct >= 1.0 or (bar_pct >= 0.8 and vol_ratio >= 2.0):
                            first_ts = bar['datetime']  # 'YYYY-MM-DD HH:MM'
                            break
                    if first_ts:
                        result = (first_ts[11:16] + ':00', 0.0)
                    recent = 0.0
                    for bar in bars[-2:]:
                        if bar['open'] > 0:
                            recent += (bar['close'] - bar['open']) / bar['open'] * 100.0
                    result = (result[0], round(recent, 2))
        except Exception:
            pass
        self._backfill_cache[key] = result
        return result

    @staticmethod
    def _hhmmss_to_ts(s):
        """把当天 HH:MM:SS 转成时间戳；失败返回 None"""
        if not s or s == TIME_UNKNOWN:
            return None
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            return datetime.strptime(today + ' ' + s, '%Y-%m-%d %H:%M:%S').timestamp()
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # 异动事件（保留V2.1检测逻辑）
    # ------------------------------------------------------------------
    def _detect_events(self):
        now_ts = time.time()
        scan_time = datetime.now().strftime('%H:%M:%S')
        first_scan = not self._prev

        for code, q in self._quotes.items():
            prev = self._prev.get(code)
            prev_pct = prev['pct'] if prev else None
            prev_vol = prev['vol'] if prev else None
            pct_jump = (q['pct'] - prev_pct) if prev_pct is not None else None
            vol_jump = (q['vol'] / prev_vol) if (prev_vol and prev_vol > 0) else None

            is_anomaly = False
            event_type = 'OTHER'
            if pct_jump is not None and pct_jump >= ANOMALY_PCT_JUMP and q['pct'] > ANOMALY_MIN_PCT:
                is_anomaly = True
                event_type = 'PRICE_ACCELERATION'
            if q['vol_ratio'] >= ANOMALY_VOL_RATIO and q['pct'] > ANOMALY_MIN_PCT:
                is_anomaly = True
                event_type = 'PRICE_VOLUME'
            if vol_jump is not None and vol_jump >= 2.0 and q['pct'] > ANOMALY_MIN_PCT:
                is_anomaly = True
                event_type = 'VOLUME_EXPANSION'
            if first_scan and pct_jump is None and \
                    q['pct'] >= ANOMALY_FIRSTSCAN_PCT and q['vol_ratio'] >= ANOMALY_FIRSTSCAN_VR:
                is_anomaly = True
                event_type = 'PRICE_VOLUME'

            if not is_anomaly:
                continue

            existing = self._events.get(code)
            if existing and now_ts - existing.get('_ts', 0) < EVENT_COOLDOWN:
                existing['pct'] = q['pct']
                existing['price'] = q['price']
                existing['vol_ratio'] = q['vol_ratio']
                existing['last_ts'] = now_ts
                if q['pct'] >= 5.0:
                    existing['strength'] = 'strong'
                continue

            real_time = scan_time
            time_known = True
            recent_accel = 0.0
            if first_scan:
                bt, recent_accel = self._backfill_anomaly_time(code)
                if bt:
                    real_time = bt
                    time_known = True
                else:
                    real_time = TIME_UNKNOWN
                    time_known = False

            first_ts = self._hhmmss_to_ts(real_time) if time_known else None
            prev_event_count = existing.get('event_count', 0) if existing else 0

            self._events[code] = {
                'code': code,
                'name': q['name'],
                'time': real_time,
                'time_known': time_known,
                'first_ts': first_ts,
                '_ts': now_ts,
                'last_ts': now_ts,
                'event_count': prev_event_count + 1,
                'price': q['price'],
                'pct': q['pct'],
                'prev_pct': prev_pct if prev_pct is not None else 0.0,
                'pct_jump': pct_jump if pct_jump is not None else 0.0,
                'vol_ratio': q['vol_ratio'],
                'vol_jump': vol_jump if vol_jump is not None else 0.0,
                'volume': q['vol'],
                'recent_accel': recent_accel,
                'event_type': event_type,
                'strength': 'strong' if ((pct_jump or 0) >= 2.0 or q['vol_ratio'] >= 3.0) else 'normal',
                'themes': self._theme_map.get(code, []),
                'industry': q.get('industry', ''),
                'chains': self._stock_chains.get(code, []),
                'chain_position': CHAIN_UNKNOWN,
            }
            # [闭环] 通知基准阳跟踪器：这是今日异动股，盘后只跟踪它
            try:
                from services.anchor_tracker import mark_anomaly
                theme_str = ','.join(self._theme_map.get(code, [])[:3])
                mark_anomaly(code, q['name'], q['pct'], q['price'],
                             anomaly_type=event_type, themes=theme_str)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 异动群 + 扩散检测（V2.2 增强字段）
    # ------------------------------------------------------------------
    def _build_clusters(self):
        now_ts = time.time()
        # 低价股过滤：6 元以下的股票不参与异动群。
        # 这一层同时清掉「快照恢复」带进来的历史事件，避免重启后残留。
        if self._low_price_codes:
            for _cd in [c for c in self._events if c in self._low_price_codes]:
                self._events.pop(_cd, None)
        # ST/退市股同样不参与异动群
        if self._st_codes:
            for _cd in [c for c in self._events if c in self._st_codes]:
                self._events.pop(_cd, None)
        stale_ev = [c for c, e in self._events.items()
                    if now_ts - e.get('last_ts', e['_ts']) > STALE_EVENT_SECONDS]
        for c in stale_ev:
            del self._events[c]
        stale_cl = [k for k, g in self._clusters.items()
                    if now_ts - g.get('_last_ts', 0) > STALE_CLUSTER_SECONDS]
        for k in stale_cl:
            del self._clusters[k]

        # 1) 产业链聚合（DIRECT_CHAIN，最高优先级）
        chain_events = defaultdict(list)
        for code, ev in self._events.items():
            for chain in ev['chains']:
                chain_events[chain].append(ev)
        for chain, evs in chain_events.items():
            if len(evs) < CLUSTER_MIN:
                continue
            self._upsert_cluster('chain:' + chain, REL_DIRECT_CHAIN, chain, evs, now_ts)

        # 2) 题材标签聚合（SAME_THEME）
        theme_events = defaultdict(list)
        for code, ev in self._events.items():
            for theme in ev['themes']:
                theme_events[theme].append(ev)
        for theme, evs in theme_events.items():
            if len(evs) < CLUSTER_MIN:
                continue
            self._upsert_cluster('theme:' + theme, REL_SAME_THEME, theme, evs, now_ts)

    def _cluster_total(self, g):
        """集群相关股票总数（链名单∪行业匹配 / 题材映射）"""
        if g['relation_type'] == REL_DIRECT_CHAIN:
            meta = self._chain_map.get(g['label'], {})
            total = set(c for c, _ in meta.get('stocks', []))
            # 用 _code_industry（全量 代码→行业 映射）而不是 _quotes：
            # 第1层 MA20 过滤会缩小行情池，若继续用 _quotes 会让联动密度的
            # 分母偏小、百分比虚高。行业映射与 MA20 无关，口径更稳定。
            for code, ind in self._code_industry.items():
                if ind and any(kw and kw in ind for kw in meta.get('industries', [])):
                    total.add(code)
            return max(len(total), 1)
        return max(sum(1 for codes, themes in self._theme_map.items()
                       if g['label'] in themes), 1)

    def _upsert_cluster(self, key, relation_type, label, evs, now_ts):
        """创建或更新异动群。首次异动时间取真实最早，发现时间首次创建时固定。"""
        evs = sorted(evs, key=lambda x: (x.get('first_ts') is None, x.get('first_ts') or 0, x['_ts']))

        known = [e for e in evs if e.get('time_known')]
        first_time = TIME_UNKNOWN
        if known:
            first_time = known[0]['time']

        is_new = key not in self._clusters
        g = self._clusters.get(key, {
            'key': key,
            'label': label,
            'relation_type': relation_type,
            'first_event_time': first_time,
            'discovery_time': datetime.now().strftime('%H:%M:%S'),
            'first_stock': '',
            'first_code': '',
            'first_pct': 0.0,
        })
        g['events'] = evs
        g['label'] = label
        g['relation_type'] = relation_type
        g['first_event_time'] = first_time
        if is_new:
            g['discovery_time'] = datetime.now().strftime('%H:%M:%S')
        g['first_stock'] = evs[0]['name']
        g['first_code'] = evs[0]['code']
        g['first_pct'] = evs[0]['pct']
        g['stock_count'] = len(evs)
        g['path_names'] = [e['name'] for e in evs]
        g['path_codes'] = [e['code'] for e in evs]
        g['path_times'] = [e['time'] for e in evs]
        g['diffusion_state'] = self._calc_diffusion(evs, now_ts)

        # ---- 扩散检测增强字段 ----
        g['active_count'] = len(evs)
        g['first_event_count'] = sum(1 for e in evs if e.get('event_count', 0) >= 1)
        g['second_event_count'] = sum(1 for e in evs if e.get('event_count', 0) >= 2)
        g['last_event_time'] = evs[-1]['time'] if evs else ''
        g['cluster_total'] = self._cluster_total(g)
        g['event_density'] = round(len(evs) / g['cluster_total'] * 100.0, 1)
        g['actual_path'] = [
            {'name': e['name'], 'code': e['code'], 'time': e['time']}
            for e in evs
        ]
        g['_last_ts'] = now_ts
        self._clusters[key] = g

    @staticmethod
    def _calc_diffusion(evs, now_ts):
        """基于真实事件时间戳判断扩散状态"""
        if not evs:
            return DIFF_STOPPED
        ts_list = [e.get('first_ts') or e['_ts'] for e in evs]
        recent2 = sum(1 for t in ts_list if now_ts - t < 120)
        recent5 = sum(1 for t in ts_list if now_ts - t < 300)
        last = max(ts_list)
        if recent2 >= 2:
            return DIFF_EXPANDING
        if recent5 >= 2 and now_ts - last < 600:
            return DIFF_WEAKENING
        if now_ts - last > 600:
            return DIFF_STOPPED
        return DIFF_WEAKENING

    # ------------------------------------------------------------------
    # 关系判定（四级：DIRECT_CHAIN > CHAIN_MEMBER > SAME_THEME > INDUSTRY_RELATED）
    # ------------------------------------------------------------------
    def _relation_to_cluster(self, code, g):
        """返回 (relation_type, detail)。直接产业链优先，禁止关键词冒充产业链。"""
        q = self._quotes.get(code, {})
        ev_chains = set()
        for e in g['events']:
            ev_chains.update(e.get('chains', []))
        stock_chains = set(self._events.get(code, {}).get('chains', []))
        ev_industries = {e.get('industry', '') for e in g['events'] if e.get('industry')}

        if g['relation_type'] == REL_DIRECT_CHAIN:
            chain = g['label']
            meta = self._chain_map.get(chain)
            if meta:
                chain_codes = {c for c, _ in meta.get('stocks', [])}
                # 1) 目标股票本身就在该链 stocks 名单
                if code in chain_codes:
                    return REL_DIRECT_CHAIN, chain
                # 2) 目标股票的链列表含该链（多值索引）
                if chain in stock_chains:
                    return REL_DIRECT_CHAIN, chain
                # 3) 行业匹配该链 industries（东财f100）
                ind = q.get('industry', '')
                for kw in meta.get('industries', []):
                    if kw and ind and kw in ind:
                        return REL_DIRECT_CHAIN, chain
            # 不在链名单/链列表/行业匹配：但属于其他链 → 链成员
            if stock_chains:
                return REL_CHAIN_MEMBER, chain
            # 与集群事件行业相同 → 行业相关
            if ind := q.get('industry', ''):
                if ind in ev_industries:
                    return REL_INDUSTRY_RELATED, ind
            return REL_SAME_THEME, ''
        else:  # SAME_THEME 集群
            # 候选与集群事件共享任一链 → 升格直接产业链
            shared = stock_chains & ev_chains
            if shared:
                return REL_DIRECT_CHAIN, next(iter(shared))
            # 候选本身是某链名单成员 → 链成员
            for chain, meta in self._chain_map.items():
                if code in {c for c, _ in meta.get('stocks', [])}:
                    return REL_CHAIN_MEMBER, chain
            if stock_chains:
                return REL_CHAIN_MEMBER, next(iter(stock_chains))
            # 与集群事件行业相同 → 行业相关
            ind = q.get('industry', '')
            if ind and ind in ev_industries:
                return REL_INDUSTRY_RELATED, ind
            return REL_SAME_THEME, g['label']

    def _cluster_related(self, g):
        """集群候选池（只排除逻辑在外层处理，这里返回全部相关股票）"""
        if g['relation_type'] == REL_DIRECT_CHAIN:
            meta = self._chain_map.get(g['label'], {})
            related = {c for c, _ in meta.get('stocks', [])}
            for code, q in self._quotes.items():
                ind = q.get('industry', '')
                if ind and any(kw and kw in ind for kw in meta.get('industries', [])):
                    related.add(code)
            return related
        return {code for code, themes in self._theme_map.items()
                if g['label'] in themes}

    # ------------------------------------------------------------------
    # 尚未充分启动判断（保留V2.1：基础过滤 + 加速末端）
    # ------------------------------------------------------------------
    def _is_not_fully_started(self, ev, q):
        if q['pct'] >= 8.0:
            return False
        if q['pct'] < 0.3:
            return False
        if ev.get('prev_pct', 0) >= 5.0:
            return False
        recent_accel = ev.get('recent_accel', 0) or 0
        if q['pct'] >= 6.0 and recent_accel >= 3.0:
            return False
        return True

    def _is_not_fully_started_no_event(self, q):
        """无自身事件时的预备候选门槛（仅用真实行情判断）"""
        if q['pct'] >= 8.0:
            return False
        if q['pct'] < 0.3:
            return False
        return True

    @staticmethod
    def _update_price(opp, q):
        opp['price'] = q['price']
        opp['pct'] = q['pct']
        opp['vol_ratio'] = q['vol_ratio']
        # [PUSH-UPG] 推送补齐：成交额/换手率/行业/昨收 随行情同步更新
        opp['amount'] = q.get('amount', 0)
        opp['turnover'] = q.get('turnover', 0)
        opp['industry'] = q.get('industry', '')
        opp['last_close'] = q.get('last_close', 0)

    # ------------------------------------------------------------------
    # 机会更新（V2.2 状态机 + PREPARE + 防重复推进）
    # ------------------------------------------------------------------
    def _update_opportunities(self):
        now_ts = time.time()
        self._drop_reasons = defaultdict(int)
        processed = set()  # 本轮已发生状态迁移的 code（跨集群防重复推进）

        for key, g in self._clusters.items():
            related = self._cluster_related(g)
            # 只排除集群首发源；其他成员（含后续自身异动的股票）均可成为候选目标
            related.discard(g.get('first_code', ''))
            if g.get('diffusion_state') == DIFF_STOPPED:
                # 扩散停止的集群不再产生新预备候选（已有机会由失效逻辑处理）
                pass

            for code in related:
                q = self._quotes.get(code)
                if not q:
                    continue
                ev = self._events.get(code)
                rel_type, rel_detail = self._relation_to_cluster(code, g)
                if rel_type == REL_UNKNOWN:
                    self._drop_reasons['关系无效'] += 1
                    continue

                opp = self._opportunities.get(code)

                # ---------- 无自身事件 ----------
                if not ev:
                    if opp is None:
                        # 预备候选门槛：扩散未停止 + 集群已有真实异动成员 + 自身未明显启动
                        if g.get('diffusion_state') == DIFF_STOPPED:
                            self._drop_reasons['扩散停止'] += 1
                            continue
                        if g.get('active_count', 0) < CLUSTER_MIN:
                            self._drop_reasons['扩散未形成'] += 1
                            continue
                        if not self._is_not_fully_started_no_event(q):
                            self._drop_reasons['已经启动或加速过快'] += 1
                            continue
                        # [NEW] 硬过滤：现价低于MA20剔除
                        tech = self._tech_levels(code, q.get('price', 0))
                        if tech and tech.get('ma20') and not tech.get('ma20_above'):
                            self._drop_reasons['跌破MA20'] += 1
                            continue
                        if code in processed:
                            continue
                        self._opportunities[code] = {
                            'code': code,
                            'name': q['name'],
                            'theme': g['label'],
                            'relation_type': rel_type,
                            'relation_detail': rel_detail,
                            'chain_position': CHAIN_UNKNOWN,
                            'first_chain_time': g['first_event_time'],
                            'discovery_time': g['discovery_time'],
                            'own_first_time': '',
                            'own_second_time': '',
                            'event_count': 0,
                            'path': ' → '.join(g['path_names'][:6]),
                            'price': q['price'],
                            'pct': q['pct'],
                            'vol_ratio': q['vol_ratio'],
                            'amount': q.get('amount', 0),
                            'turnover': q.get('turnover', 0),
                            'industry': q.get('industry', ''),
                            'last_close': q.get('last_close', 0),
                            'status': ST_PREPARE,
                            'reason': f"扩散中·{g['label']} 已动{g['active_count']}只；自身待响应",
                            'atr_ref': None,
                            'atr_status': '未取得',
                            '_ts': now_ts,
                        }
                        processed.add(code)
                        self._maybe_push(code, ST_PREPARE, q['name'], g['label'])
                    else:
                        # 已有机会但本轮无自身事件（PREPARE/COOLING等待中）：只更新行情
                        if code in processed:
                            continue
                        self._update_price(opp, q)
                        opp['path'] = ' → '.join(g['path_names'][:6])
                    continue

                # ---------- 有自身事件 ----------
                if not self._is_not_fully_started(ev, q):
                    if opp is not None and opp['status'] not in (ST_INVALID, ST_STARTED):
                        if code not in processed:
                            opp['status'] = ST_INVALID
                            opp['reason'] = '已经启动或加速过快'
                            opp['_ts'] = now_ts
                            processed.add(code)
                    else:
                        self._drop_reasons['已经启动或加速过快'] += 1
                    continue

                if opp is None:
                    # 自身真实异动：首次 → 初步联动；
                    # 若事件计数已>=2（如程序重启后机会丢失）→ 直接二次异动+确认
                    if code in processed:
                        continue
                    if ev['event_count'] >= 2:
                        self._opportunities[code] = {
                            'code': code,
                            'name': q['name'],
                            'theme': g['label'],
                            'relation_type': rel_type,
                            'relation_detail': rel_detail,
                            'chain_position': CHAIN_UNKNOWN,
                            'first_chain_time': g['first_event_time'],
                            'discovery_time': g['discovery_time'],
                            'own_first_time': ev['time'],
                            'own_second_time': ev['time'],
                            'event_count': ev['event_count'],
                            'path': ' → '.join(g['path_names'][:6]),
                            'price': q['price'],
                            'pct': q['pct'],
                            'vol_ratio': q['vol_ratio'],
                            'amount': q.get('amount', 0),
                            'turnover': q.get('turnover', 0),
                            'industry': q.get('industry', ''),
                            'last_close': q.get('last_close', 0),
                            'status': ST_SECOND_EVENT,
                            'reason': f"自身二次异动 {ev['time']}",
                            'atr_ref': None,
                            'atr_status': '未取得',
                            '_ts': now_ts,
                        }
                        if g['diffusion_state'] != DIFF_STOPPED:
                            self._opportunities[code]['status'] = ST_CONFIRMED
                            self._opportunities[code]['reason'] = f"二次异动确认 {ev['time']}"
                        processed.add(code)
                        self._maybe_push(code, ST_CONFIRMED, q['name'], g['label'])
                    else:
                        self._opportunities[code] = {
                            'code': code,
                            'name': q['name'],
                            'theme': g['label'],
                            'relation_type': rel_type,
                            'relation_detail': rel_detail,
                            'chain_position': CHAIN_UNKNOWN,
                            'first_chain_time': g['first_event_time'],
                            'discovery_time': g['discovery_time'],
                            'own_first_time': ev['time'],
                            'own_second_time': '',
                            'event_count': ev['event_count'],
                            'path': ' → '.join(g['path_names'][:6]),
                            'price': q['price'],
                            'pct': q['pct'],
                            'vol_ratio': q['vol_ratio'],
                            'amount': q.get('amount', 0),
                            'turnover': q.get('turnover', 0),
                            'industry': q.get('industry', ''),
                            'last_close': q.get('last_close', 0),
                            'status': ST_FIRST_EVENT,
                            'reason': f"首发{g['first_stock']} {g['first_event_time']}；自身首次{ev['time']}",
                            'atr_ref': None,
                            'atr_status': '未取得',
                            '_ts': now_ts,
                        }
                        processed.add(code)
                        self._maybe_push(code, ST_FIRST_EVENT, q['name'], g['label'])
                    continue

                # ---------- 已有机会：状态机推进（每轮最多一次） ----------
                if code in processed:
                    self._update_price(opp, q)
                    opp['path'] = ' → '.join(g['path_names'][:6])
                    continue
                self._update_price(opp, q)
                opp['path'] = ' → '.join(g['path_names'][:6])

                prev = opp['status']
                if prev in (ST_PREPARE, ST_UNRESPONDED):
                    if ev['event_count'] >= 1:
                        opp['status'] = ST_FIRST_EVENT
                        opp['own_first_time'] = ev['time']
                        opp['event_count'] = ev['event_count']
                        opp['reason'] = f"自身首次异动 {ev['time']}"
                        opp['_ts'] = now_ts
                        processed.add(code)
                        self._maybe_push(code, ST_FIRST_EVENT, q['name'], g['label'])
                elif prev == ST_FIRST_EVENT:
                    first_ts = self._hhmmss_to_ts(opp.get('own_first_time', ''))
                    if ev['event_count'] >= 2:
                        opp['status'] = ST_SECOND_EVENT
                        opp['own_second_time'] = ev['time']
                        opp['event_count'] = ev['event_count']
                        opp['reason'] = f"自身二次异动 {ev['time']}"
                        opp['_ts'] = now_ts
                        processed.add(code)
                        self._maybe_push(code, ST_SECOND_EVENT, q['name'], g['label'])
                        # 扩散有效 → 同轮确认（一次推进完成 CONFIRMED）
                        if g['diffusion_state'] != DIFF_STOPPED:
                            opp['status'] = ST_CONFIRMED
                            opp['reason'] = f"二次异动确认 {ev['time']}"
                            self._maybe_push(code, ST_CONFIRMED, q['name'], g['label'])
                    elif first_ts is not None and now_ts - first_ts >= COOLING_SECONDS:
                        opp['status'] = ST_COOLING
                        opp['reason'] = '首次异动后冷却观察，等待二次确认'
                        opp['_ts'] = now_ts
                        processed.add(code)
                elif prev == ST_COOLING:
                    if ev['event_count'] >= 2:
                        opp['status'] = ST_SECOND_EVENT
                        opp['own_second_time'] = ev['time']
                        opp['event_count'] = ev['event_count']
                        opp['reason'] = f"自身二次异动 {ev['time']}"
                        opp['_ts'] = now_ts
                        processed.add(code)
                        self._maybe_push(code, ST_SECOND_EVENT, q['name'], g['label'])
                        if g['diffusion_state'] != DIFF_STOPPED:
                            opp['status'] = ST_CONFIRMED
                            opp['reason'] = f"二次异动确认 {ev['time']}"
                            self._maybe_push(code, ST_CONFIRMED, q['name'], g['label'])
                elif prev == ST_SECOND_EVENT:
                    if g['diffusion_state'] != DIFF_STOPPED:
                        opp['status'] = ST_CONFIRMED
                        opp['reason'] = '二次异动 + 扩散有效，联动确认'
                        opp['_ts'] = now_ts
                        processed.add(code)
                        self._maybe_push(code, ST_CONFIRMED, q['name'], g['label'])
                elif prev == ST_CONFIRMED:
                    # 确认后进入ATR实时跟踪（只读）
                    self._fill_atr(opp)
                    opp['status'] = ST_ATR_TRACKING
                    opp['reason'] = '联动确认完成，进入ATR跟踪'
                    opp['_ts'] = now_ts
                    processed.add(code)
                    self._maybe_push(code, ST_ATR_TRACKING, q['name'], g['label'])
                elif prev == ST_ATR_TRACKING:
                    # 持续跟踪：刷新ATR参考（只读，不反向筛选）
                    self._fill_atr(opp)
                    opp['_ts'] = now_ts

                # ---------- 失效判断 ----------
                if opp['status'] not in (ST_INVALID, ST_STARTED):
                    if q['pct'] >= 8.0:
                        opp['status'] = ST_STARTED
                        opp['reason'] = '已经启动（涨幅≥8%）'
                        self._drop_reasons['已经启动'] += 1
                    elif g['diffusion_state'] == DIFF_STOPPED:
                        opp['status'] = ST_INVALID
                        opp['reason'] = '产业链扩散停止'
                        self._drop_reasons['扩散停止'] += 1
                    elif ev.get('recent_accel', 0) >= 3.0 and q['pct'] >= 6.0:
                        opp['status'] = ST_INVALID
                        opp['reason'] = '加速过快'
                        self._drop_reasons['加速过快'] += 1
                    elif now_ts - opp.get('_ts', now_ts) > INVALID_TIMEOUT:
                        opp['status'] = ST_INVALID
                        opp['reason'] = '长时间无推进'
                        self._drop_reasons['无推进'] += 1

    def _fill_atr(self, opp):
        """只读ATR持仓参考（绝不修改ATR逻辑/库结构）"""
        ref = self._atr_ref.get(opp['code'])
        if ref:
            opp['atr_ref'] = {'vwap': ref.get('anchor_vwap'), 'cost': ref.get('cost')}
            opp['atr_status'] = '有参考'
        else:
            opp['atr_ref'] = None
            opp['atr_status'] = '未持仓'

    # ------------------------------------------------------------------
    # 微信推送（状态变化只推一次）
    # ------------------------------------------------------------------
    def _maybe_push(self, code, status, name, theme):
        # V3.0 推送重构：企业微信只在"联动确认/早期启动确认"时发，
        # 预备/初步联动/冷却/ATR等待 等中间状态只留在 UI，不再轰炸微信。
        key = f"{code}|{status}"
        if key in self._pushed:
            return
        self._pushed.add(key)
        # [PUSH-UPG] 全字段在引擎端构建：涨幅/产业链/触发依据/风险，
        # 取不到输出"数据源缺失：xxx"，禁止"未取得"占位文案。
        try:
            opp = self._opportunities.get(code, {}) or {}
            detail = self._build_push_detail(code, opp, theme)
            from services.wechat_bus import get_wechat_bus
            get_wechat_bus().send_intraday(
                status=status, code=code, name=name,
                price=detail.get('price'), pct=detail.get('pct'),
                theme=theme, chain_path=detail.get('chain_path', ''),
                reasons=detail.get('reasons', []),
                risk=detail.get('risk', ''),
                extra=detail.get('extra'))
        except Exception:
            pass

    # [PUSH-UPG] 盘中机会推送全字段构建：每个字段独立 try/except，
    # 取不到输出"数据源缺失：xxx"（禁止"未取得"占位文案）
    def _build_push_detail(self, code, opp, theme):
        def _src(label):
            return f"数据源缺失：{label}"

        detail = {'price': None, 'pct': None, 'chain_path': '', 'reasons': [], 'risk': '', 'extra': {}}

        # ---------- 1. 涨幅：现价 / 涨跌幅% / 相对板块超额涨幅 ----------
        price = opp.get('price')
        pct = opp.get('pct')
        detail['price'] = price
        detail['pct'] = pct
        try:
            industry = opp.get('industry', '') or ''
            detail['extra']['industry'] = industry or _src('行业(东财f100)')
            if pct is not None and industry:
                sec = self._get_sector_pct(industry)
                if sec and sec.get('pct') is not None:
                    detail['extra']['excess'] = f"{pct - sec['pct']:+.2f}%"
                    detail['extra']['sector_pct'] = f"{sec['pct']:+.2f}%"
                    detail['extra']['sector_cnt'] = f"板块涨{sec.get('up_cnt', 0)}家/跌{sec.get('down_cnt', 0)}家"
                else:
                    detail['extra']['excess'] = _src('板块超额涨幅(板块榜未匹配)')
                    detail['extra']['sector_pct'] = _src('板块指数涨幅')
                    detail['extra']['sector_cnt'] = _src('板块涨跌家数')
            else:
                detail['extra']['excess'] = _src('板块超额涨幅(缺行业或涨幅)')
                detail['extra']['sector_pct'] = _src('板块指数涨幅')
                detail['extra']['sector_cnt'] = _src('板块涨跌家数')
        except Exception:
            detail['extra']['excess'] = _src('板块超额涨幅')
            detail['extra']['sector_pct'] = _src('板块指数涨幅')
            detail['extra']['sector_cnt'] = _src('板块涨跌家数')

        # ---------- 2. 题材与产业链 ----------
        try:
            rel = opp.get('relation_type', '') or ''
            rel_cn = {
                'DIRECT_CHAIN': '直接产业链核心成员',
                'CHAIN_MEMBER': '产业链成员',
                'SAME_THEME': '同题材异动',
                'INDUSTRY_RELATED': '行业相关',
                'UNKNOWN': '关系未知',
            }.get(rel, rel if rel else '')
            rel_det = opp.get('relation_detail', '') or ''
            anchor_txt = ''
            try:
                meta = self._chain_map.get(theme) or {}
                if meta.get('anchor'):
                    anchor_txt = f"·锚点：{meta['anchor'][1]}"
            except Exception:
                anchor_txt = ''
            if rel in ('DIRECT_CHAIN', 'CHAIN_MEMBER') and rel_det:
                detail['extra']['chain_position'] = f"{rel_cn}（{rel_det}）{anchor_txt}·上中下游环节：{_src('产业链环节')}"
            elif rel_cn and rel_det:
                detail['extra']['chain_position'] = f"{rel_cn}（{rel_det}）{anchor_txt}"
            elif rel_cn:
                detail['extra']['chain_position'] = f"{rel_cn}{anchor_txt}"
            else:
                detail['extra']['chain_position'] = _src('产业链位置(无链映射)')
        except Exception:
            detail['extra']['chain_position'] = _src('产业链位置')
        try:
            path = opp.get('path') or ''
            detail['chain_path'] = path or _src('轮动路径')
            detail['extra']['rotation_path'] = detail['chain_path']
        except Exception:
            detail['extra']['rotation_path'] = _src('轮动路径')
        try:
            leaders = self._cluster_leaders(code)
            detail['extra']['leaders'] = leaders or _src('同题材领涨股')
        except Exception:
            detail['extra']['leaders'] = _src('同题材领涨股')

        # ---------- 3. 触发依据：联动标的/板块/量能/资金 ----------
        reasons = []
        try:
            own_first = opp.get('own_first_time') or ''
            own_second = opp.get('own_second_time') or ''
            if own_first:
                reasons.append(f"自身首次异动 {own_first}")
            if own_second:
                reasons.append(f"自身二次异动 {own_second}")
            linked = self._cluster_linked(code)
            detail['extra']['linked'] = linked or _src('联动标的清单')
            g = self._find_cluster(code)
            if g:
                diff = g.get('diffusion_state', '')
                active = g.get('active_count', 0)
                if diff and active:
                    reasons.append(f"集群{diff}·已联动{active}只")
            vr = opp.get('vol_ratio')
            amt = opp.get('amount')
            to = opp.get('turnover')
            detail['extra']['vol_ratio'] = f"{vr:.2f}" if vr is not None else _src('量比')
            detail['extra']['amount'] = self._fmt_amount(amt) if amt is not None else _src('成交额')
            detail['extra']['turnover'] = f"{to:.2f}%" if to is not None else _src('换手率')
            fund = self._fetch_main_net(code)
            if fund:
                net, ratio = fund
                detail['extra']['fund'] = f"主力净流入{net:+.0f}万（净占比{ratio:.1f}%）"
            else:
                detail['extra']['fund'] = _src('主力净流入(资金接口无数据)')
        except Exception:
            detail['extra']['linked'] = detail['extra'].get('linked') or _src('联动标的清单')
            detail['extra']['vol_ratio'] = detail['extra'].get('vol_ratio') or _src('量比')
            detail['extra']['amount'] = detail['extra'].get('amount') or _src('成交额')
            detail['extra']['turnover'] = detail['extra'].get('turnover') or _src('换手率')
            detail['extra']['fund'] = detail['extra'].get('fund') or _src('主力净流入')

        # ---------- 4. 风险提示：止损/压力/追高/时效 ----------
        try:
            tech = self._tech_levels(code, price)
            if tech:
                detail['extra']['tech'] = f"突破：{tech.get('breakout', _src('突破状态'))} ｜ 均线：{tech.get('ma_state', _src('均线状态'))}"
                detail['extra']['stop_ref'] = tech.get('stop_ref') or _src('止损参考位(K线)')
                detail['extra']['pressure'] = tech.get('pressure') or _src('压力位(K线)')
            else:
                detail['extra']['tech'] = _src('技术指标(K线)')
                detail['extra']['stop_ref'] = _src('止损参考位(K线)')
                detail['extra']['pressure'] = _src('压力位(K线)')
            # [CYB-GATE] 追高提示阈值按板性等比放大（涨停幅度比 2.0）：
            # 主板 5% / 3%  ->  创业板 10% / 6%
            _chase_hi = 10.0 if str(code or '').startswith(('300', '301')) else 5.0
            _chase_mid = 6.0 if str(code or '').startswith(('300', '301')) else 3.0
            if pct is not None and pct >= _chase_hi:
                detail['extra']['chase'] = f"涨幅已大（+{pct:.1f}%），谨防冲高回落，追高风险高"
            elif pct is not None and pct >= _chase_mid:
                detail['extra']['chase'] = f"涨幅中等（+{pct:.1f}%），不追高、回踩确认再看"
            elif pct is not None:
                detail['extra']['chase'] = f"涨幅温和（+{pct:.1f}%），可跟踪但需放量确认"
            else:
                detail['extra']['chase'] = _src('涨幅(追高判断)')
            detail['extra']['timeliness'] = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}（多源实时行情+K线）"
        except Exception:
            detail['extra']['tech'] = detail['extra'].get('tech') or _src('技术指标')
            detail['extra']['stop_ref'] = _src('止损参考位')
            detail['extra']['pressure'] = _src('压力位')
            detail['extra']['chase'] = _src('追高风险判断')
            detail['extra']['timeliness'] = _src('数据时效')

        if reasons:
            reasons.append(f"题材/产业链：{theme}")
        detail['reasons'] = reasons or [_src('触发依据')]
        detail['risk'] = (f"止损参考位：{detail['extra'].get('stop_ref', _src('止损参考位'))}；"
                          f"压力位：{detail['extra'].get('pressure', _src('压力位'))}；"
                          f"{detail['extra'].get('chase', _src('追高风险判断'))}")
        return detail

    def _find_cluster(self, code):
        """返回包含该股票的异动群（联动清单/领涨/扩散信息的数据源）"""
        try:
            for g in self._clusters.values():
                for e in g.get('events', []):
                    if e.get('code') == code:
                        return g
        except Exception:
            pass
        return None

    def _cluster_linked(self, code):
        """联动标的清单：'名称(代码)+x.x%'，最多8只"""
        try:
            g = self._find_cluster(code)
            if not g:
                return ''
            evs = sorted(g.get('events', []), key=lambda e: e.get('pct', 0), reverse=True)
            return '、'.join(
                f"{e.get('name', '')}({e.get('code', '')}){e.get('pct', 0):+.1f}%"
                for e in evs[:8])
        except Exception:
            return ''

    def _cluster_leaders(self, code):
        """同题材当日领涨 top3（含自身）"""
        try:
            g = self._find_cluster(code)
            if not g:
                return ''
            evs = sorted(g.get('events', []), key=lambda e: e.get('pct', 0), reverse=True)
            return '、'.join(
                f"{e.get('name', '')}({e.get('code', '')}){e.get('pct', 0):+.1f}%"
                for e in evs[:3])
        except Exception:
            return ''

    def _get_sector_pct(self, industry):
        """板块指数涨幅/涨跌家数：东财行业板块榜（m:90+t:2），全榜缓存30分钟"""
        try:
            if not industry:
                return None
            now = time.time()
            board = getattr(self, '_sector_board', None)
            ts = getattr(self, '_sector_board_ts', 0)
            if board is None or now - ts > 1800:
                from utils.http_market_data import eastmoney_request
                data = eastmoney_request('/api/qt/clist/get', {
                    'pn': 1, 'pz': 100, 'po': 1, 'np': 1,
                    'fltt': 2, 'invt': 2, 'fs': 'm:90+t:2',
                    'fields': 'f12,f14,f3,f104,f105',
                }, timeout=6)
                board = {}
                for it in ((data or {}).get('data') or {}).get('diff', []) or []:
                    nm = (it.get('f14') or '').strip()
                    if nm:
                        board[nm] = {
                            'pct': float(it.get('f3', 0) or 0),
                            'up_cnt': int(it.get('f104', 0) or 0),
                            'down_cnt': int(it.get('f105', 0) or 0),
                        }
                self._sector_board = board
                self._sector_board_ts = now
            for nm, s in board.items():
                if nm in industry or industry in nm:
                    return s
            return None
        except Exception:
            return None

    def _fetch_main_net(self, code):
        """主力净流入(万元)+净占比%：东财 fflow 接口（与深度资金面同款，轻量只取主力两项）"""
        try:
            from utils.http_market_data import eastmoney_request
            secid = f'1.{code}' if str(code).startswith('6') else f'0.{code}'
            data = eastmoney_request('/api/qt/stock/fflow/daykline/get', {
                'secid': secid,
                'fields1': 'f1,f2,f3,f7',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63',
            }, timeout=6)
            if data and data.get('data') and data['data'].get('klines'):
                latest = data['data']['klines'][-1].split(',')
                if len(latest) >= 7:
                    net = float(latest[1]) / 10000      # f52 主力净流入 元→万元
                    ratio = float(latest[6] or 0)       # f57 主力净占比%
                    return (net, ratio)
            return None
        except Exception:
            return None

    def _tech_levels(self, code, price=None):
        """技术位：压力=近20日最高，止损=近10日最低，均线MA5/10/20，突破状态。
        数据源：本地K线缓存（kline_cache_service.get_latest_kline）。"""
        # [FIX] 内存缓存：10分钟内同一只股不重复查K线，防止开盘候选多导致网络堆积
        now_ts = time.time()
        if not hasattr(self, '_ma20_cache'):
            self._ma20_cache = {}
        cached = self._ma20_cache.get(code)
        if cached and now_ts - cached[0] < 600:
            # 缓存命中，只更新 price 相关字段
            r = dict(cached[1])
            if price is not None:
                ma20 = r.get('ma20', 0)
                r['ma20_above'] = (ma20 > 0 and price >= ma20)
            return r
        try:
            bars = None
            try:
                from services.kline_cache_service import get_latest_kline
                bars = get_latest_kline(code, count=60) or []
            except Exception:
                bars = None
            # [PUSH-UPG] 本地缓存缺失/被占用时，在线腾讯日K兜底（已有接口，不新增数据源）
            if not bars or len(bars) < 15:
                try:
                    from utils.kline_fetcher import fetch_kline_tencent
                    kb = fetch_kline_tencent(code, days=60)
                    if kb:
                        bars = [{'date': b.get('date', ''), 'open': b.get('open', 0),
                                 'high': b.get('high', 0), 'low': b.get('low', 0),
                                 'close': b.get('close', 0), 'volume': b.get('volume', 0)}
                                for b in kb if isinstance(b, dict)]
                except Exception:
                    bars = None
            if not bars or len(bars) < 15:
                return None
            closes = [b['close'] for b in bars]
            highs = [b['high'] for b in bars]
            lows = [b['low'] for b in bars]
            pressure = max(highs[-20:])
            stop_ref = min(lows[-10:])
            ma5 = sum(closes[-5:]) / 5
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20
            if ma5 > ma10 > ma20:
                ma_state = '多头排列'
            elif ma5 < ma10 < ma20:
                ma_state = '空头排列'
            else:
                ma_state = '均线纠缠'
            if price is not None:
                if price >= pressure:
                    breakout = f"已突破20日高点{pressure:.2f}"
                elif price >= pressure * 0.97:
                    breakout = f"逼近20日高点{pressure:.2f}"
                else:
                    breakout = f"未突破20日高点{pressure:.2f}"
            else:
                breakout = f"距20日高点{pressure:.2f}"
            return {
                'pressure': f"{pressure:.2f}",
                'stop_ref': f"{stop_ref:.2f}（近10日低点）",
                'ma_state': ma_state,
                'breakout': breakout,
                'ma20': round(ma20, 2),
                'ma20_above': (price is not None and price >= ma20),
            }
            self._ma20_cache[code] = (now_ts, result)
            return result
        except Exception:
            return None

    @staticmethod
    def _fmt_amount(amt):
        try:
            if amt >= 1e8:
                return f"{amt / 1e8:.1f}亿"
            if amt >= 1e4:
                return f"{amt / 1e4:.0f}万"
            return f"{amt:.0f}元"
        except Exception:
            return '数据源缺失：成交额'

    # ------------------------------------------------------------------
    # 统计链 + 淘汰原因
    # ------------------------------------------------------------------
    def _update_stats(self):
        opps = list(self._opportunities.values())
        active = [o for o in opps if o['status'] not in (ST_INVALID, ST_STARTED)]
        self._stats = {
            'anomaly_count': len(self._events),
            'cluster_count': len(self._clusters),
            'direct_chain_count': sum(1 for g in self._clusters.values()
                                      if g['relation_type'] == REL_DIRECT_CHAIN),
            'theme_count': sum(1 for g in self._clusters.values()
                               if g['relation_type'] == REL_SAME_THEME),
            'relation_ok': sum(1 for o in active if o['relation_type'] != REL_UNKNOWN),
            'prepare': sum(1 for o in active if o['status'] == ST_PREPARE),
            'first_event': sum(1 for o in active if o['status'] == ST_FIRST_EVENT),
            'cooling': sum(1 for o in active if o['status'] == ST_COOLING),
            'second_event': sum(1 for o in active if o['status'] == ST_SECOND_EVENT),
            'confirmed': sum(1 for o in active if o['status'] == ST_CONFIRMED),
            'atr_tracking': sum(1 for o in active if o['status'] == ST_ATR_TRACKING),
            'opportunity_count': len(active),
            'drop_reasons': dict(self._drop_reasons),
            # [NEW] 第1层 MA20 过滤统计
            'ma20_quote_dropped': self._ma20_dropped,
            'ma20_quote_left': len(self._quotes),
            'ma20_map_size': len(self._ma20_all),
        }

    # ------------------------------------------------------------------
    # 对外接口（UI）
    # ------------------------------------------------------------------
    def _resolve_prices(self, codes):
        """兜底补价：确保这批股票的价格已知。

        为什么需要：联动表的路径里没有存价格，判断「是否 <6 元」只能靠
        实时行情。而东财 clist 接口会间歇性限流（实测 10 次里只成功 1 次，
        且成功那次只返回 77 只），此时 _quotes 里没有这些股票，
        只靠 _low_price_codes 会漏判，联动表就会残留低价股。
        这里用腾讯源（稳定）补一次，结果缓存 5 分钟。

        正常情况下集群里的股票都在 _quotes 里，need 为空，不会发起网络请求。
        """
        now = time.time()
        need = []
        for c in codes:
            if not c or c in self._low_price_codes or c in self._quotes:
                continue
            hit = self._px_cache.get(c)
            if hit and now - hit[0] < 300:
                continue
            need.append(c)
        if not need:
            return
        try:
            from utils.http_market_data import get_realtime_quotes_http
            q = get_realtime_quotes_http(need) or {}
        except Exception:
            return
        for c, d in (q or {}).items():
            px = (d or {}).get('price') or 0
            if not px:
                continue
            self._px_cache[c] = (now, px)
            if px < MIN_PRICE:
                self._low_price_codes.add(c)

    @staticmethod
    def _is_st_name(name):
        """名称含 ST / 退 视为风险警示股（*ST、ST、退市整理都覆盖）。"""
        n = (name or '').upper().replace(' ', '')
        return ('ST' in n) or ('退' in n)

    def _is_st(self, code):
        """代码是否 ST/退市：先查跨轮 ST 集合，再用当前行情池名称兜底。"""
        if not code:
            return False
        if code in self._st_codes:
            return True
        q = self._quotes.get(code)
        return bool(q) and self._is_st_name(q.get('name'))

    def _is_low_price(self, code):
        """该股是否属于「6 元以下」被剔除对象。

        先查本轮行情过滤时记下的集合（覆盖「已从行情池剔除」的股票），
        再用当前行情价兜底（覆盖休市复盘等场景）。
        """
        if not code:
            return False
        if code in self._low_price_codes:
            return True
        q = self._quotes.get(code)
        return bool(q) and (q.get('price') or 0) < MIN_PRICE

    def get_clusters(self):
        # 先确保集群里出现的股票价格已知（东财限流时用腾讯源兜底）
        _all_codes = set()
        for _g in self._clusters.values():
            _all_codes.update(_g.get('path_codes') or [])
            if _g.get('first_code'):
                _all_codes.add(_g['first_code'])
        if _all_codes:
            self._resolve_prices(sorted(_all_codes))
        result = []
        for g in self._clusters.values():
            # ---- 低价股过滤：把 <6 元的股票从该群的路径/首发里剔除 ----
            _pc = g.get('path_codes') or []
            _pn = g.get('path_names') or []
            _pt = g.get('path_times') or []
            _keep = [i for i in range(len(_pc))
                     if not self._is_low_price(_pc[i])
                     and not self._is_st_name(_pn[i] if i < len(_pn) else '')
                     and not self._is_below_ma20(_pc[i])]
            if len(_keep) < CLUSTER_MIN:
                # 剔除低价股/ST 后已不足「群」的最少股票数，该群不再展示
                continue
            _fs, _fc, _fp = g['first_stock'], g['first_code'], g['first_pct']
            if self._is_low_price(_fc) or self._is_st_name(_fs):
                # 首发股本身是低价股/ST → 用剔除后最早的一只顶上
                _fi = _keep[0]
                _fc = _pc[_fi]
                _fs = _pn[_fi] if _fi < len(_pn) else _fc
                _fp = 0.0
            _total = g.get('cluster_total', 0)
            result.append({
                'key': g['key'],
                'theme': g['label'],
                'relation_type': g['relation_type'],
                'relation_cn': REL_CN.get(g['relation_type'], REL_CN[REL_UNKNOWN]),
                'first_stock': _fs,
                'first_code': _fc,
                'first_pct': _fp,
                'first_time': g['first_event_time'],
                'discovery_time': g['discovery_time'],
                'stock_count': len(_keep),
                'active_count': len(_keep),
                'second_event_count': g.get('second_event_count', 0),
                'cluster_total': _total,
                'event_density': round(len(_keep) / _total * 100.0, 1) if _total else 0.0,
                'last_event_time': g.get('last_event_time', ''),
                'path': [_pn[i] for i in _keep if i < len(_pn)],
                'path_times': [_pt[i] for i in _keep if i < len(_pt)],
                'path_codes': [_pc[i] for i in _keep],
                'actual_path': [ap for ap in (g.get('actual_path') or [])
                                if not self._is_low_price(ap.get('code', ''))],
                'diffusion_state': g['diffusion_state'],
                'chain_position': CHAIN_UNKNOWN,
            })
            # [NEW] 首发股MA20状态
            first_code = g.get('first_code', '')
            first_q = self._quotes.get(first_code, {})
            first_price = first_q.get('price', 0)
            if first_code and first_price:
                tech = self._tech_levels(first_code, first_price)
                if tech:
                    result[-1]['first_ma20_above'] = tech.get('ma20_above')
                    result[-1]['first_ma20'] = tech.get('ma20')
                else:
                    result[-1]['first_ma20_above'] = None
            else:
                result[-1]['first_ma20_above'] = None
        rank = {DIFF_EXPANDING: 0, DIFF_WEAKENING: 1, DIFF_STOPPED: 2}
        result.sort(key=lambda r: (
            r['relation_type'] != REL_DIRECT_CHAIN,
            rank.get(r['diffusion_state'], 9),
            -r['stock_count'],
        ))
        return result[:20]

    def get_opportunities(self):
        result = []
        for code, o in self._opportunities.items():
            if o['status'] in (ST_INVALID, ST_STARTED):
                continue
            # 低价股过滤：6 元以下不进入盘中机会
            if (o.get('price') or 0) < MIN_PRICE:
                continue
            # ST/退市股不进入盘中机会
            if self._is_st_name(o.get('name')) or self._is_st(code):
                continue
            # [NEW] MA20 兜底：跨轮累积的机会池里，跌破 MA20 的剔除
            if self._is_below_ma20(code, o.get('price')):
                continue
            result.append({
                'code': code,
                'name': o['name'],
                'price': o['price'],
                'pct': o['pct'],
                'theme': o['theme'],
                'relation_cn': REL_CN.get(o['relation_type'], REL_CN[REL_UNKNOWN]),
                'chain_position': o['chain_position'],
                'path': o['path'],
                'status': o['status'],
                'state_class': GS_CLASS.get(o['status'], o['status']),
                'own_time': o.get('own_second_time') or o.get('own_first_time', ''),
                'reason': o['reason'],
                'atr_ref': o.get('atr_ref'),
                'atr_status': o.get('atr_status', '未取得'),
                'event_count': o.get('event_count', 0),
            })
        order = {ST_ATR_TRACKING: 0, ST_CONFIRMED: 1, ST_SECOND_EVENT: 2,
                 ST_COOLING: 3, ST_FIRST_EVENT: 4, ST_PREPARE: 5}
        result.sort(key=lambda x: (order.get(x['status'], 9), -x['pct']))
        return result[:50]

    def get_gold_shovel_candidates(self):
        """金铲子统一接口：只接收有效状态（预备/初步联动/联动确认/ATR跟踪）"""
        result = []
        for code, o in self._opportunities.items():
            if o['status'] not in GS_VALID:
                continue
            # 低价股过滤：6 元以下不进入金铲子
            if (o.get('price') or 0) < MIN_PRICE:
                continue
            # ST/退市股不进入金铲子
            if self._is_st_name(o.get('name')) or self._is_st(code):
                continue
            # [NEW] MA20 兜底：跨轮累积的机会池里，跌破 MA20 的剔除
            if self._is_below_ma20(code, o.get('price')):
                continue
            g = None
            expansion_count = 0
            expansion_density = 0.0
            for k, cl in self._clusters.items():
                if cl['label'] == o['theme']:
                    g = cl
                    expansion_count = cl.get('active_count', 0)
                    expansion_density = cl.get('event_density', 0.0)
                    break
            result.append({
                'code': code,
                'name': o['name'],
                'price': o['price'],
                'pct': o['pct'],
                'relation_type': o['relation_type'],
                'relation_cn': REL_CN.get(o['relation_type'], REL_CN[REL_UNKNOWN]),
                'cluster_name': o['theme'],
                'actual_path': o['path'],
                'state': o['status'],
                'state_class': GS_CLASS.get(o['status'], o['status']),
                'event_count': o.get('event_count', 0),
                'first_event_time': o.get('own_first_time', ''),
                'discovery_time': o.get('discovery_time', ''),
                'event_reason': o['reason'],
                'expansion_count': expansion_count,
                'expansion_density': expansion_density,
                'atr_status': o.get('atr_status', '未取得'),
                'atr_ref': o.get('atr_ref'),
            })
        order = {ST_ATR_TRACKING: 0, ST_CONFIRMED: 1, ST_SECOND_EVENT: 2,
                 ST_COOLING: 3, ST_FIRST_EVENT: 4, ST_PREPARE: 5}
        result.sort(key=lambda x: (order.get(x['state'], 9), -x['pct']))

        # [已移除] 原「合并 band_pattern_engine 波段信号」段。
        # 原因：band_pattern_engine 里从来没有 get_band_engine 这个名字，
        # 这段一直抛 ImportError 被 except 吞掉，属于从未生效的僵尸代码；
        # 且它会把「日K建仓(四模式)」的盘后信号混进盘中金铲子，
        # 与金铲子「盘中机会子集」的定位冲突。2026-09-24 按你的要求删除。

        # [基准阳跟踪闭环] 合并 anchor_tracker 的活跃信号（建仓/加仓/洗盘/次日高开/基准阳）
        try:
            from services.anchor_tracker import get_anchor_tracker, STATE_CN
            anchor_rows = []
            for s in get_anchor_tracker().get_active_signals():
                # 只主板 + 低价股过滤：6 元以下不进入金铲子（基准阳跟踪段）
                _c = s.get('code', '')
                if not _c.startswith(MAIN_PREFIX):
                    continue
                if self._is_low_price(_c) \
                        or (s.get('push_price') or s.get('anchor_close') or 0) < MIN_PRICE:
                    continue
                if self._is_st_name(s.get('name')) or self._is_st(_c):
                    continue
                st_cn = STATE_CN.get(s['state'], s['state'])
                anchor_rows.append({
                    'code': s['code'],
                    'name': s.get('name') or s['code'],
                    'price': s.get('push_price') or s.get('anchor_close') or 0,
                    'pct': s.get('push_pct') or 0,
                    'relation_type': 'ANCHOR',
                    'relation_cn': '跟踪',
                    'cluster_name': '基准阳跨日跟踪',
                    'actual_path': (f"【跟踪】基准{s.get('anchor_date','')} 收{s.get('anchor_close',0):.2f}"
                                    f" | {s.get('note','')}"),
                    'state': st_cn,
                    'state_class': 'ANCHOR_' + s['state'],
                    'event_count': 0,
                    'first_event_time': s.get('anchor_date', ''),
                    'discovery_time': s.get('updated_at', ''),
                    'event_reason': s.get('note', ''),
                    'expansion_count': 0,
                    'expansion_density': 0.0,
                    'atr_status': '基准阳跟踪',
                    'atr_ref': None,
                    # 共用波段UI字段
                    'is_band': True,
                    'pattern_name': '基准阳·' + st_cn,
                    'push_ma5': s.get('push_ma5'),
                    'push_ma20': s.get('push_ma20'),
                    'push_dist_ma20': s.get('push_dist_ma20'),
                    'base_date': s.get('anchor_date'),
                    'base_close': s.get('anchor_close'),
                    'base_low': s.get('anchor_low'),
                })
            # 基准阳跟踪的建仓/加仓排在最前，其次4种模式，最后原异动
            result = anchor_rows + result
        except Exception as e:
            print(f'[金铲子] 合并基准阳跟踪失败(忽略): {e}', flush=True)

        return result

    def get_stats(self):
        return self._stats

    def _prewarm_ma20_cache(self):
        """[NEW] 9:15-9:25预热：批量读自选股+持仓股，提前算MA20填缓存。
        避免开盘时候选集中触发腾讯在线查询。"""
        try:
            import json, os
            # 读自选
            wl_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), 'data', 'watchlist.json')
            codes = set()
            if os.path.exists(wl_path):
                with open(wl_path, 'r', encoding='utf-8') as f:
                    for item in json.load(f):
                        c = item.get('code', '')
                        if c:
                            codes.add(c)
            # 读持仓
            try:
                import duckdb
                db = os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), 'data', 'cache', 'atr_t_tracking.duckdb')
                if os.path.exists(db):
                    con = duckdb.connect(db, read_only=True)
                    for row in con.execute("SELECT DISTINCT code FROM holding").fetchall():
                        codes.add(row[0])
                    con.close()
            except Exception:
                pass
            # 批量算MA20
            n = 0
            for code in codes:
                if code in self._ma20_cache:
                    continue
                self._tech_levels(code, None)
                n += 1
            if n:
                print(f'[预热] MA20缓存已预热 {n} 只自选/持仓股', flush=True)
        except Exception as e:
            print(f'[预热] MA20预热失败: {e}', flush=True)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = IntradayOpportunityEngine()
    return _engine
