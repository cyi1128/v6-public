# -*- coding: utf-8 -*-
"""
涨停数据采集器（补回断掉的采集链路）

背景：
    data/limit_up_reason.db 是板块节奏 / 题材记忆 / 盘中机会 / 金铲子 / 日K建仓
    / 竞价 / 今日涨停 等模块共用的题材数据源。
    但写入函数 data/limit_up_reason_db.save_limit_up_data() 全项目无调用方，
    采集链路实际是断的 —— 库停在 2026-09-30，题材口径全部过期。

数据源（实测可用，且支持按日期回溯）：
    同花顺涨停池 —— 直接返回涨停原因（reason_type），形如
        "数据中心+AI营销+体育营销"
    东财涨停池   —— 只返回行业板块（hybk），作为兜底

写入：
    limit_up_reasons(code, name, date, time, pct_chg, lbc, reason, industry,
                     source, fund, amount, hs, zbc, ltsz)
    source='ths' 与库内 17067 条历史真题材记录保持一致。

    后 5 个数值字段是龙头排序（连板身位 > 首封时间 > 封单额 > 涨幅）用的：
        fund   封单额     东财 fund
        amount 成交额     东财 amount
        hs     换手率     东财 hs   / 同花顺 turnover_rate
        zbc    炸板次数   东财 zbc  / 同花顺 open_num
        ltsz   流通市值   东财 ltsz / 同花顺 currency_value
    注意 INSERT OR REPLACE 会把未列出的列清空，所以这几列必须一起写。

CLI:
    python services/limit_up_collector.py --probe           # 只打印，不写库
    python services/limit_up_collector.py --date 20261009   # 采指定交易日
    python services/limit_up_collector.py --backfill 15     # 补最近 15 个交易日
    python services/limit_up_collector.py                   # 采今天
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')

THS_URL = ('https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool?'
           'page=1&limit=200&field=199112,10,9001,330323,330324,330325,9002,330329,'
           '133971,133970,1968584,3475914,9003,9004&filter=HS,GEM2STAR&'
           'order_field=330324&order_type=0&date={date}')
EM_URL = ('http://push2ex.eastmoney.com/getTopicZTPool?'
          'ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&'
          'pagesize=300&sort=fbt:asc&date={date}')


# ----------------------------------------------------------------------
# 底层抓取
# ----------------------------------------------------------------------
def _get_json(url, referer):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': referer, 'Accept': '*/*'})
    raw = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
    return json.loads(raw)


def _norm_time(v):
    """首封时间归一成 'HH:MM:SS'

    三种来源格式都要吃下：
      东财  91500            -> '09:25:00'
      东财  '09:25:00'       -> 原样
      同花顺 '1791527221'    -> Unix 时间戳，转本地时间（本机为北京时间）
    """
    if v in (None, '', 0):
        return ''
    s = str(v).strip()
    if ':' in s:
        return s
    if s.isdigit():
        # 10 位及以上 = Unix 时间戳
        if len(s) >= 10:
            try:
                return datetime.fromtimestamp(int(s)).strftime('%H:%M:%S')
            except Exception:
                return ''
        s = s.zfill(6)
        if len(s) >= 6:
            return '%s:%s:%s' % (s[:2], s[2:4], s[4:6])
    return s


def _norm_lbc(rec):
    """连板数：high_days_value 是 {连续天数: 板数} 结构"""
    hv = rec.get('high_days_value')
    if isinstance(hv, dict) and hv:
        try:
            vals = [int(x) for x in hv.values() if str(x).isdigit()]
            if vals:
                return max(vals)
        except Exception:
            pass
    hd = rec.get('high_days')
    if isinstance(hd, str) and '板' in hd:
        import re
        m = re.search(r'(\d+)\s*板', hd)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)', hd)
        if m:
            return int(m.group(1))
    elif isinstance(hd, (int, float)):
        return int(hd)
    return 1


def fetch_ths_pool(date_str):
    """同花顺涨停池 —— 带真题材 reason_type

    date_str: '20261009'
    return: [{'code','name','time','pct_chg','lbc','reason','industry'}, ...]
    """
    j = _get_json(THS_URL.format(date=date_str),
                  'https://data.10jqka.com.cn/market/longhu/')
    items = (j.get('data') or {}).get('info') or []
    out = []
    for r in items:
        code = str(r.get('code') or '').strip()
        if not code:
            continue
        reason = (r.get('reason_type') or '').strip()
        out.append({
            'code': code,
            'name': (r.get('name') or '').strip(),
            'time': _norm_time(r.get('first_limit_up_time')),
            'pct_chg': float(r.get('change_rate') or 0),
            'lbc': _norm_lbc(r),
            'reason': reason,
            # 同花顺不给行业；industry 先留空，由东财那一层补
            'industry': '',
            # 龙头排序用的数值字段。同花顺能给的先填上，东财有值会覆盖。
            #   up_high_order_amount 实测现在返回 None（拿不到封单额）
            'fund': float(r.get('up_high_order_amount') or 0),
            'amount': 0.0,
            'hs': float(r.get('turnover_rate') or 0),      # 换手率
            'zbc': int(r.get('open_num') or 0),            # 开板次数=炸板次数
            'ltsz': float(r.get('currency_value') or 0),   # 流通市值
        })
    return out


def fetch_em_pool(date_str):
    """东财涨停池 —— 只有行业板块，用于补 industry + 兜底"""
    j = _get_json(EM_URL.format(date=date_str), 'http://quote.eastmoney.com/')
    pool = (j.get('data') or {}).get('pool') or []
    out = {}
    for r in pool:
        code = str(r.get('c') or '').strip()
        if not code:
            continue
        out[code] = {
            'code': code,
            'name': (r.get('n') or '').strip(),
            'time': _norm_time(r.get('fbt')),
            'pct_chg': float(r.get('zdp') or 0),
            'lbc': int(r.get('lbc') or 1),
            'reason': (r.get('hybk') or '').strip(),
            'industry': (r.get('hybk') or '').strip(),
            # 龙头排序用的数值字段（实测东财 69/69 全都有）
            'fund': float(r.get('fund') or 0),      # 封单额
            'amount': float(r.get('amount') or 0),  # 成交额
            'hs': float(r.get('hs') or 0),          # 换手率
            'zbc': int(r.get('zbc') or 0),          # 炸板次数
            'ltsz': float(r.get('ltsz') or 0),      # 流通市值
        }
    return out


def build_day(date_str, prefer='ths'):
    """合并两个源，产出可直接写库的记录"""
    ths, em = [], {}
    try:
        ths = fetch_ths_pool(date_str)
    except Exception as e:
        print('  [采集] 同花顺失败: %s' % str(e)[:80])
    try:
        em = fetch_em_pool(date_str)
    except Exception as e:
        print('  [采集] 东财失败: %s' % str(e)[:80])

    NUM_FIELDS = ('fund', 'amount', 'hs', 'zbc', 'ltsz')
    rows, source = [], 'ths'
    if ths:
        for r in ths:
            e = em.get(r['code'])
            r['industry'] = (e or {}).get('industry', '') or ''
            if not r['time'] and e:
                r['time'] = e['time']
            if not r['pct_chg'] and e:
                r['pct_chg'] = e['pct_chg']
            # 数值字段以东方财富为准（同花顺的封单额字段现已返回 None），
            # 东财缺值时保留同花顺自己填的那份，保证键永远存在
            for _k in NUM_FIELDS:
                _v = (e or {}).get(_k)
                if _v:
                    r[_k] = _v
            for _k in NUM_FIELDS:
                r.setdefault(_k, 0)
            rows.append(r)
        # 东财有、同花顺没有的补进来（避免漏掉）
        have = set(r['code'] for r in rows)
        for code, e in em.items():
            if code not in have:
                rows.append(e)
    elif em:
        rows = list(em.values())
        source = 'eastmoney_zt_pool'
    return rows, source


# ----------------------------------------------------------------------
# 写库
# ----------------------------------------------------------------------
def collect(date_str=None, probe=False):
    """采集并写入某一天。date_str: '20261009'；None=今天"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    rows, source = build_day(date_str)
    print('  [采集] %s 取到 %d 只（源=%s）' % (date_str, len(rows), source))
    if probe:
        for r in rows[:8]:
            print('    %s %-8s 连板%-2s 首封%-8s 封单%.4f亿 炸板%d 换手%.2f%% 原因=%s'
                  % (r['code'], r['name'], r['lbc'], r['time'],
                     (r.get('fund') or 0) / 1e8, r.get('zbc') or 0,
                     r.get('hs') or 0, r['reason'][:50]))
        return len(rows)
    if not rows:
        return 0

    # 直接调用现有写入函数（它就是为这个格式写的）
    from data.limit_up_reason_db import save_limit_up_data, init_db
    try:
        init_db()
    except Exception:
        pass
    # save_limit_up_data 内部写死 source='eastmoney_zt_pool'，
    # 这里自己写一份以便保留 source='ths'（get_last_limit_up_reason 优先读 wencai/ths）
    import sqlite3
    db = os.path.join(_ROOT, 'data', 'limit_up_reason.db')
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS limit_up_reasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL, name TEXT, date TEXT NOT NULL,
            time TEXT, pct_chg REAL, lbc INTEGER, reason TEXT,
            industry TEXT, source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            fund REAL, amount REAL, hs REAL, zbc INTEGER, ltsz REAL,
            UNIQUE(code, date))
    ''')
    # 老库没有这 5 列的补上（已存在时 ALTER 抛错，静默跳过）
    for _c, _t in (('fund', 'REAL'), ('amount', 'REAL'), ('hs', 'REAL'),
                   ('zbc', 'INTEGER'), ('ltsz', 'REAL')):
        try:
            cur.execute('ALTER TABLE limit_up_reasons ADD COLUMN %s %s'
                        % (_c, _t))
        except Exception:
            pass
    n = 0
    for r in rows:
        try:
            cur.execute('''
                INSERT OR REPLACE INTO limit_up_reasons
                (code, name, date, time, pct_chg, lbc, reason, industry, source,
                 fund, amount, hs, zbc, ltsz)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (r['code'], r['name'], date_str, r.get('time', ''),
                  r.get('pct_chg', 0), r.get('lbc', 1), r.get('reason', ''),
                  r.get('industry', ''), source,
                  float(r.get('fund') or 0), float(r.get('amount') or 0),
                  float(r.get('hs') or 0), int(r.get('zbc') or 0),
                  float(r.get('ltsz') or 0)))
            n += 1
        except Exception as e:
            print('    写库失败 %s: %s' % (r.get('code'), e))
    conn.commit()
    conn.close()
    print('  [采集] 已写入 %s：%d 只' % (date_str, n))
    return n


def backfill(days=15, skip_existing=True):
    """补最近 N 个交易日。已有数据的日期默认跳过（skip_existing）。"""
    import sqlite3
    try:
        from utils.trade_calendar import get_latest_trading_date
        base = get_latest_trading_date()
        base_s = base.strftime('%Y%m%d') if hasattr(base, 'strftime') else str(base).replace('-', '')
    except Exception:
        base_s = datetime.now().strftime('%Y%m%d')

    db = os.path.join(_ROOT, 'data', 'limit_up_reason.db')
    have = set()
    if skip_existing and os.path.exists(db):
        c = sqlite3.connect(db)
        have = set(r[0] for r in c.execute(
            "SELECT DISTINCT date FROM limit_up_reasons WHERE source='ths'"))
        c.close()

    # 用日历倒推交易日
    dates = []
    try:
        from utils.trade_calendar import is_trading_day
        from datetime import timedelta
        d = datetime.strptime(base_s, '%Y%m%d')
        cnt = 0
        while len(dates) < days and cnt < days * 3 + 40:
            if is_trading_day(d.date()):
                dates.append(d.strftime('%Y%m%d'))
            d = d - timedelta(days=1)
            cnt += 1
    except Exception as e:
        print('  [回溯] 交易日历不可用(%s)，改用自然日回退' % str(e)[:50])
        from datetime import timedelta
        d = datetime.strptime(base_s, '%Y%m%d')
        for i in range(days):
            dates.append((d - timedelta(days=i)).strftime('%Y%m%d'))

    dates = [x for x in dates if x <= base_s]
    print('  [回溯] 目标 %d 个交易日：%s' % (len(dates), ' '.join(dates)))
    result = {}
    for ds in dates:
        if ds in have:
            print('  [回溯] %s 已有 ths 数据，跳过' % ds)
            result[ds] = 'skip'
            continue
        n = collect(ds)
        result[ds] = n
        time.sleep(0.6)
    ok = sum(1 for v in result.values() if isinstance(v, int) and v > 0)
    print('  [回溯] 完成：%d/%d 个交易日写入成功' % (ok, len(dates)))
    return result


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--probe' in args:
        ds = None
        if '--date' in args:
            ds = args[args.index('--date') + 1]
        print('PROBE %s' % (ds or 'today'))
        collect(ds, probe=True)
    elif '--backfill' in args:
        n = int(args[args.index('--backfill') + 1])
        backfill(n)
    elif '--date' in args:
        collect(args[args.index('--date') + 1])
    else:
        collect()
