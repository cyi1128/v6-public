# -*- coding: utf-8 -*-
"""
基准放量阳跨日跟踪器（anchor_tracker.py）
==================================================
闭环定位：
    题材异动引擎（intraday_opportunity_engine）盘中抓异动股 → 本模块盘后只跟踪
    这些异动股里"放量阳 + MA20上方"的标的，跨日推进状态机：

        基准阳建立 → 次日高开放量 → 洗盘(横盘/回踩MA20下影承接)
                  → 回踩MA5 建仓 → 收盘站上MA5 加仓

    解决"题材是人形机器人但股票不关联"的问题：
    基准阳必须先经过题材异动引擎确认是热点股，才会进入跟踪。

状态机（日K级别，盘后推进一次）：
    ANCHOR_SET        基准阳已建立，等待次日高开
    NEXT_DAY_HIGH     次日高开放量已确认
    WASHING           洗盘中（横盘/回踩MA20）
    BUILD             建仓信号（回踩MA5收回）
    ADD               加仓信号（收盘站稳MA5）
    INVALID           失效（跌破基准阳最低 或 跌破MA20 或 15天无推进）

推送：
    - 建仓/加仓 同时推金铲子表格 + 企业微信
    - 基准阳建立 只推金铲子观察，不发微信（避免刷屏）
"""
import os
import sys
import time
import sqlite3
import threading
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DB_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')
DB_PATH = os.path.join(DB_DIR, 'anchor_tracker.db')

# 参数
VOL_MULT = 2.0           # 基准阳放量倍数
RANGE_TOL = 0.04         # 洗盘横盘 ±4%
MA5_TOUCH = 0.01         # 触及MA5 ±1%
MAX_DAYS = 15            # 15天无推进失效

# 状态
ST_ANCHOR = 'ANCHOR_SET'
ST_NEXTDAY = 'NEXT_DAY_HIGH'
ST_WASH = 'WASHING'
ST_BUILD = 'BUILD'
ST_ADD = 'ADD'
ST_INVALID = 'INVALID'

STATE_CN = {
    ST_ANCHOR: '基准阳',
    ST_NEXTDAY: '次日高开',
    ST_WASH: '洗盘中',
    ST_BUILD: '建仓',
    ST_ADD: '加仓',
    ST_INVALID: '失效',
}


def _ma(values, n):
    if not values or len(values) < n:
        return None
    return sum(values[-n:]) / n


def _init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS anchor_record (
                code TEXT PRIMARY KEY,
                name TEXT,
                anchor_date TEXT,
                anchor_close REAL,
                anchor_low REAL,
                anchor_volume REAL,
                anchor_ma20 REAL,
                state TEXT,
                state_date TEXT,
                wash_days INTEGER DEFAULT 0,
                push_price REAL,
                push_ma5 REAL,
                push_ma20 REAL,
                push_dist_ma20 REAL,
                push_pct REAL,
                note TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS today_anomaly (
                code TEXT,
                name TEXT,
                pct REAL,
                price REAL,
                anomaly_time TEXT,
                anomaly_type TEXT,
                themes TEXT,
                PRIMARY KEY (code, anomaly_time)
            )
        """)
        con.commit()
    finally:
        con.close()


# 当日异动股内存集合（盘中由 intraday_opportunity_engine 调用 mark_anomaly 填充）
_anomaly_today = {}
_anomaly_lock = threading.Lock()


def mark_anomaly(code, name, pct, price, anomaly_type='', themes=''):
    """盘中：题材异动引擎发现新股时调，加入今日异动池（内存+DB双写）。"""
    if not code:
        return
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = {
        'code': code, 'name': name, 'pct': pct, 'price': price,
        'anomaly_time': now, 'anomaly_type': anomaly_type, 'themes': themes,
    }
    with _anomaly_lock:
        _anomaly_today[code] = entry
    # 同时写DB（bat独立进程重启时能恢复）
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            INSERT OR IGNORE INTO today_anomaly
            (code, name, pct, price, anomaly_time, anomaly_type, themes)
            VALUES (?,?,?,?,?,?,?)
        """, (code, name, pct, price, now, anomaly_type, themes))
        con.commit()
        con.close()
    except Exception:
        pass


def _load_bars(code):
    from services.kline_cache_service import get_latest_kline
    bars = get_latest_kline(code, count=80) or []
    if len(bars) < 25:
        try:
            from utils.kline_fetcher import fetch_kline_tencent
            kb = fetch_kline_tencent(code, days=80)
            if kb:
                bars = [{'date': b.get('date', ''),
                         'open': float(b.get('open', 0)), 'high': float(b.get('high', 0)),
                         'low': float(b.get('low', 0)), 'close': float(b.get('close', 0)),
                         'volume': float(b.get('volume', 0))} for b in kb]
        except Exception:
            pass
    return bars


class AnchorTracker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        _init_db()
        # 启动时从DB恢复活跃状态到内存
        self._active = self._load_active()
        # 启动时从 today_anomaly 表恢复今日异动池（bat独立进程启动时用）
        self._load_today_anomaly_from_db()

    def _load_today_anomaly_from_db(self):
        """从 today_anomaly 表读最近1天的异动股，灌回内存。
        盘中程序运行时 mark_anomaly 会实时写库；bat 独立进程启动时从这里恢复。"""
        try:
            con = sqlite3.connect(DB_PATH)
            con.row_factory = sqlite3.Row
            today = datetime.now().strftime('%Y-%m-%d')
            rows = con.execute(
                "SELECT * FROM today_anomaly WHERE substr(anomaly_time,1,10)=?",
                (today,)).fetchall()
            con.close()
            with _anomaly_lock:
                for r in rows:
                    _anomaly_today[r['code']] = {
                        'code': r['code'], 'name': r['name'],
                        'pct': r['pct'], 'price': r['price'],
                        'anomaly_time': r['anomaly_time'],
                        'anomaly_type': r['anomaly_type'],
                        'themes': r['themes'],
                    }
            if rows:
                print(f'[基准阳] 从DB恢复今日异动股 {len(rows)} 只', flush=True)
        except Exception as e:
            print(f'[基准阳] 恢复今日异动池失败: {e}', flush=True)

    def _load_active(self):
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM anchor_record WHERE state != ?", (ST_INVALID,)).fetchall()
            return {r['code']: dict(r) for r in rows}
        finally:
            con.close()

    # ---------- 工具 ----------
    @staticmethod
    def _pct(a, b):
        return (a - b) / b * 100.0 if b else 0.0

    # ---------- 主扫描：盘后调用 ----------
    def scan_daily(self):
        """盘后推进：
        1. 把今日异动池里的股票，判断是否形成基准阳 → 新建跟踪
        2. 对已有跟踪股，推进状态机
        """
        today = datetime.now().strftime('%Y-%m-%d')
        con = sqlite3.connect(DB_PATH)
        try:
            # 把盘中内存异动池落库（去重）
            with _anomaly_lock:
                anomalies = list(_anomaly_today.values())
            for a in anomalies:
                con.execute("""
                    INSERT OR IGNORE INTO today_anomaly
                    (code, name, pct, price, anomaly_time, anomaly_type, themes)
                    VALUES (?,?,?,?,?,?,?)
                """, (a['code'], a['name'], a['pct'], a['price'],
                      a['anomaly_time'], a['anomaly_type'], a['themes']))
            con.commit()

            # 1. 异动池里找新基准阳
            new_anchors = []
            for a in anomalies:
                code = a['code']
                if code in self._active:
                    continue  # 已在跟踪
                bars = _load_bars(code)
                if len(bars) < 25:
                    continue
                last = bars[-1]
                if last['date'][:10] != today:
                    continue  # 今天K线还没更新
                closes = [b['close'] for b in bars]
                vols = [b['volume'] for b in bars]
                ma20 = _ma(closes, 20)
                if not ma20:
                    continue
                # 条件：今日阳线 或 涨停 + 收盘≥MA20 + 量≥前5均量×2
                is_yang = last['close'] > last['open']
                prev5_vol = _ma(vols[-6:-1], 5)
                if not is_yang or not prev5_vol:
                    continue
                if last['close'] < ma20:
                    continue
                if last['volume'] < prev5_vol * VOL_MULT:
                    continue
                # 写入DB
                rec = {
                    'code': code, 'name': a.get('name') or code,
                    'anchor_date': today, 'anchor_close': last['close'],
                    'anchor_low': last['low'], 'anchor_volume': last['volume'],
                    'anchor_ma20': ma20, 'state': ST_ANCHOR, 'state_date': today,
                    'wash_days': 0,
                    'push_price': last['close'], 'push_ma5': _ma(closes, 5),
                    'push_ma20': ma20,
                    'push_dist_ma20': self._pct(last['close'], ma20),
                    'push_pct': self._pct(last['close'], closes[-2]) if len(closes) >= 2 else 0,
                    'note': f'异动{a["pct"]:+.1f}% 放量阳 收站上MA20',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
                self._upsert(con, rec)
                self._active[code] = rec
                new_anchors.append(rec)

            # 2. 推进已有跟踪股状态机
            advanced = []
            for code, rec in list(self._active.items()):
                new_state = self._advance_state(code, rec)
                if new_state:
                    self._upsert(con, new_state)
                    self._active[code] = new_state
                    advanced.append(new_state)
                    # 建仓/加仓 推微信
                    if new_state['state'] in (ST_BUILD, ST_ADD):
                        self._push_wecom(new_state)
            con.commit()
            return {'new_anchors': len(new_anchors), 'advanced': len(advanced),
                    'active': len(self._active)}
        finally:
            con.close()

    def _upsert(self, con, rec):
        con.execute("""
            INSERT OR REPLACE INTO anchor_record
            (code, name, anchor_date, anchor_close, anchor_low, anchor_volume,
             anchor_ma20, state, state_date, wash_days,
             push_price, push_ma5, push_ma20, push_dist_ma20, push_pct, note,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rec['code'], rec['name'], rec['anchor_date'], rec['anchor_close'],
            rec['anchor_low'], rec['anchor_volume'], rec['anchor_ma20'],
            rec['state'], rec['state_date'], rec.get('wash_days', 0),
            rec.get('push_price'), rec.get('push_ma5'), rec.get('push_ma20'),
            rec.get('push_dist_ma20'), rec.get('push_pct'), rec.get('note'),
            rec.get('created_at'), rec['updated_at'],
        ))

    def _advance_state(self, code, rec):
        """推进一只股票的状态机，返回更新后的rec或None。"""
        bars = _load_bars(code)
        if len(bars) < 25:
            return None
        closes = [b['close'] for b in bars]
        vols = [b['volume'] for b in bars]
        today = bars[-1]
        today_str = today['date'][:10]
        if today_str <= rec['state_date']:
            return None  # 今天没新K线
        ma5 = _ma(closes, 5)
        ma20 = _ma(closes, 20)
        if not ma5 or not ma20:
            return None

        # 失效判定
        if today['close'] < rec['anchor_low'] or today['close'] < ma20:
            rec['state'] = ST_INVALID
            rec['state_date'] = today_str
            rec['note'] = f"跌破{'基准阳低' if today['close'] < rec['anchor_low'] else 'MA20'}"
            rec['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return rec
        days_since = (datetime.strptime(today_str, '%Y-%m-%d') -
                      datetime.strptime(rec['anchor_date'], '%Y-%m-%d')).days
        if days_since > MAX_DAYS:
            rec['state'] = ST_INVALID
            rec['state_date'] = today_str
            rec['note'] = f"{MAX_DAYS}天无推进 失效"
            rec['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return rec

        anchor_close = rec['anchor_close']
        state = rec['state']

        # 状态推进
        if state == ST_ANCHOR:
            # 次日高开放量
            if today['open'] > anchor_close and today['close'] >= anchor_close:
                prev5_vol = _ma(vols[-6:-1], 5)
                if prev5_vol and today['volume'] >= prev5_vol * 1.5:
                    rec['state'] = ST_NEXTDAY
                    rec['state_date'] = today_str
                    rec['note'] = '次日高开放量确认'
                else:
                    rec['state'] = ST_WASH
                    rec['state_date'] = today_str
                    rec['wash_days'] = 1
                    rec['note'] = '进入洗盘'
            else:
                rec['state'] = ST_WASH
                rec['state_date'] = today_str
                rec['wash_days'] = 1
                rec['note'] = '进入洗盘'

        elif state == ST_NEXTDAY:
            rec['state'] = ST_WASH
            rec['state_date'] = today_str
            rec['wash_days'] = 1
            rec['note'] = '高开后进入洗盘'

        elif state == ST_WASH:
            rec['wash_days'] = rec.get('wash_days', 0) + 1
            # 洗盘中：横盘在 anchor_close ±4% 内，或回踩MA20有下影
            in_range = anchor_close * (1 - RANGE_TOL) <= today['close'] <= anchor_close * 1.08
            lower_shadow = min(today['close'], today['open']) - today['low']
            has_support = (today['low'] <= ma20 * 1.01 and
                           lower_shadow > abs(today['close'] - today['open']) * 0.5)
            if not in_range and not has_support:
                rec['note'] = '洗盘超出区间'
            else:
                rec['note'] = f"洗盘第{rec['wash_days']}日"

            # 建仓触发：今日碰MA5 ±1% 且 收回MA5
            if today['low'] <= ma5 * (1 + MA5_TOUCH) and today['close'] >= ma5:
                rec['state'] = ST_BUILD
                rec['state_date'] = today_str
                rec['push_price'] = today['close']
                rec['push_ma5'] = ma5
                rec['push_ma20'] = ma20
                rec['push_dist_ma20'] = self._pct(today['close'], ma20)
                rec['push_pct'] = self._pct(today['close'], closes[-2])
                rec['note'] = f"回踩MA5({ma5:.2f}) 收回 → 建仓"

        elif state == ST_BUILD:
            # 收盘完全站上MA5 → 加仓
            if today['close'] > ma5:
                rec['state'] = ST_ADD
                rec['state_date'] = today_str
                rec['push_price'] = today['close']
                rec['push_ma5'] = ma5
                rec['push_ma20'] = ma20
                rec['push_dist_ma20'] = self._pct(today['close'], ma20)
                rec['push_pct'] = self._pct(today['close'], closes[-2])
                rec['note'] = f"站稳MA5({ma5:.2f}) → 加仓"
            else:
                rec['note'] = '建仓后观察MA5'

        rec['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return rec

    # ---------- 微信推送 ----------
    @staticmethod
    def _push_wecom(rec):
        try:
            from services.wechat_bus import get_wechat_bus
            bus = get_wechat_bus()
            st_cn = STATE_CN.get(rec['state'], rec['state'])
            color = '🔴' if rec['state'] == ST_ADD else '🟢'
            title = f"{color}【基准阳跟踪｜{st_cn}】"
            body = (
                f"**{rec['name']}（{rec['code']}）**\n"
                f"> 推送价格：{rec['push_price']:.2f}\n"
                f"> 今日涨幅：{rec['push_pct']:+.2f}%\n"
                f"> 当日MA5：{rec['push_ma5']:.2f} ｜ 当日MA20：{rec['push_ma20']:.2f}\n"
                f"> 距MA20：{rec['push_dist_ma20']:+.2f}%\n\n"
                f"**基准阳（{rec['anchor_date']}）：**\n"
                f"> 收盘：{rec['anchor_close']:.2f} ｜ 最低：{rec['anchor_low']:.2f}\n"
                f"> 基准当日MA20：{rec['anchor_ma20']:.2f}\n\n"
                f"> 当前状态：{st_cn}\n"
                f"> 说明：{rec['note']}\n\n"
                f"---\n*清一盘·基准阳跟踪闭环 ｜ 仅供参考，不构成投资建议*"
            )
            bus._post_async(title, body)
        except Exception as e:
            print(f'[基准阳] 推送失败: {e}', flush=True)

    # ---------- UI 读接口 ----------
    def get_active_signals(self):
        """返回所有非失效的跟踪股，按状态排序。"""
        order = {ST_ADD: 0, ST_BUILD: 1, ST_WASH: 2, ST_NEXTDAY: 3, ST_ANCHOR: 4}
        rows = []
        for code, rec in self._active.items():
            if rec['state'] == ST_INVALID:
                continue
            rows.append(rec)
        rows.sort(key=lambda r: (order.get(r['state'], 9), r['anchor_date']))
        return rows


_engine = None


def get_anchor_tracker():
    global _engine
    if _engine is None:
        _engine = AnchorTracker()
    return _engine


if __name__ == '__main__':
    eng = get_anchor_tracker()
    # 测试：手动塞几只异动股进去
    mark_anomaly('603139', '康惠股份', -4.6, 36.54, 'TEST', '测试')
    summary = eng.scan_daily()
    print('扫描结果:', summary)
    for r in eng.get_active_signals():
        print(f"  {r['code']} {r['name']} {STATE_CN[r['state']]} "
              f"anchor={r['anchor_date']} close={r['anchor_close']} "
              f"note={r['note']}")
