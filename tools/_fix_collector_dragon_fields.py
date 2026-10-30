# -*- coding: utf-8 -*-
"""
修复 services/limit_up_collector.py：让封单额/炸板/换手/流通市值/成交额
真正写进 limit_up_reasons 表。

问题：新采集器的 INSERT 只写 9 列，且 INSERT OR REPLACE 会把未列出的列清空。
      → 20261008 / 20261009 的 fund/amount/hs/zbc/ltsz 全是 NULL，
        而 20260918~20260924 的老数据这些字段有值（78/103/63/51/52 行）。

改四处：
  1. fetch_ths_pool()  —— 补 open_num→zbc / turnover_rate→hs /
                          currency_value→ltsz
  2. fetch_em_pool()   —— 补 fund/amount/hs/zbc/ltsz（东财全都有）
  3. build_day()       —— 数值字段优先用东财，东财空则保留同花顺的
  4. collect()         —— CREATE TABLE / ALTER 补列，INSERT 写全 14 列
"""
import io
import os
import shutil
import sys
import py_compile

sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\services\limit_up_collector.py'
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '本文件应为纯 LF'
s = raw.decode('utf-8')
print('原行数 %d / %d bytes' % (len(s.splitlines()), len(raw)))


def rep(old, new, desc):
    global s
    n = s.count(old)
    assert n == 1, '[%s] 锚点命中 %d 次，期望 1 次' % (desc, n)
    s = s.replace(old, new)
    print('  ✓ %s' % desc)


# ---------- 0. 文件头说明 ----------
rep(
"""写入：
    limit_up_reasons(code, name, date, time, pct_chg, lbc, reason, industry, source)
    source='ths' 与库内 17067 条历史真题材记录保持一致。""",
"""写入：
    limit_up_reasons(code, name, date, time, pct_chg, lbc, reason, industry,
                     source, fund, amount, hs, zbc, ltsz)
    source='ths' 与库内 17067 条历史真题材记录保持一致。

    后 5 个数值字段是龙头排序（连板身位 > 首封时间 > 封单额 > 涨幅）用的：
        fund   封单额     东财 fund
        amount 成交额     东财 amount
        hs     换手率     东财 hs   / 同花顺 turnover_rate
        zbc    炸板次数   东财 zbc  / 同花顺 open_num
        ltsz   流通市值   东财 ltsz / 同花顺 currency_value
    注意 INSERT OR REPLACE 会把未列出的列清空，所以这几列必须一起写。""",
    '文件头写入说明')

# ---------- 1. 同花顺补齐 ----------
rep(
"""            'reason': reason,
            # 同花顺不给行业；industry 先留空，由东财那一层补
            'industry': '',
            '_order_amount': r.get('order_amount') or 0,
        })
    return out""",
"""            'reason': reason,
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
    return out""",
    'fetch_ths_pool 补 5 个数值字段')

# ---------- 2. 东财补齐 ----------
rep(
"""            'reason': (r.get('hybk') or '').strip(),
            'industry': (r.get('hybk') or '').strip(),
        }
    return out""",
"""            'reason': (r.get('hybk') or '').strip(),
            'industry': (r.get('hybk') or '').strip(),
            # 龙头排序用的数值字段（实测东财 69/69 全都有）
            'fund': float(r.get('fund') or 0),      # 封单额
            'amount': float(r.get('amount') or 0),  # 成交额
            'hs': float(r.get('hs') or 0),          # 换手率
            'zbc': int(r.get('zbc') or 0),          # 炸板次数
            'ltsz': float(r.get('ltsz') or 0),      # 流通市值
        }
    return out""",
    'fetch_em_pool 补 5 个数值字段')

# ---------- 3. build_day 合并 ----------
rep(
"""    rows, source = [], 'ths'
    if ths:
        for r in ths:
            e = em.get(r['code'])
            r['industry'] = (e or {}).get('industry', '') or ''
            if not r['time'] and e:
                r['time'] = e['time']
            if not r['pct_chg'] and e:
                r['pct_chg'] = e['pct_chg']
            rows.append(r)""",
"""    NUM_FIELDS = ('fund', 'amount', 'hs', 'zbc', 'ltsz')
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
            rows.append(r)""",
    'build_day 合并数值字段')

# ---------- 4. collect：建表 / 补列 / 写全列 ----------
rep(
"""    cur.execute('''
        CREATE TABLE IF NOT EXISTS limit_up_reasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL, name TEXT, date TEXT NOT NULL,
            time TEXT, pct_chg REAL, lbc INTEGER, reason TEXT,
            industry TEXT, source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, date))
    ''')""",
"""    cur.execute('''
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
            pass""",
    'collect 建表补 5 列 + ALTER 兼容老库')

rep(
"""            cur.execute('''
                INSERT OR REPLACE INTO limit_up_reasons
                (code, name, date, time, pct_chg, lbc, reason, industry, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (r['code'], r['name'], date_str, r.get('time', ''),
                  r.get('pct_chg', 0), r.get('lbc', 1), r.get('reason', ''),
                  r.get('industry', ''), source))""",
"""            cur.execute('''
                INSERT OR REPLACE INTO limit_up_reasons
                (code, name, date, time, pct_chg, lbc, reason, industry, source,
                 fund, amount, hs, zbc, ltsz)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (r['code'], r['name'], date_str, r.get('time', ''),
                  r.get('pct_chg', 0), r.get('lbc', 1), r.get('reason', ''),
                  r.get('industry', ''), source,
                  float(r.get('fund') or 0), float(r.get('amount') or 0),
                  float(r.get('hs') or 0), int(r.get('zbc') or 0),
                  float(r.get('ltsz') or 0)))""",
    'collect INSERT 写全 14 列')

rep(
"""        for r in rows[:8]:
            print('    %s %-8s 连板%-2s 首封%-8s 原因=%s' % (
                r['code'], r['name'], r['lbc'], r['time'], r['reason'][:60]))""",
"""        for r in rows[:8]:
            print('    %s %-8s 连板%-2s 首封%-8s 封单%.4f亿 炸板%d 换手%.2f%% 原因=%s'
                  % (r['code'], r['name'], r['lbc'], r['time'],
                     (r.get('fund') or 0) / 1e8, r.get('zbc') or 0,
                     r.get('hs') or 0, r['reason'][:50]))""",
    'probe 打印带上新字段')

shutil.copy2(P, P + '.bak_before_dragon_fields')
open(P, 'wb').write(s.encode('utf-8'))
print()
print('已写入 %s (%d bytes, %d 行)' % (P, os.path.getsize(P),
                                      len(s.splitlines())))
py_compile.compile(P, doraise=True)
print('py_compile OK')
