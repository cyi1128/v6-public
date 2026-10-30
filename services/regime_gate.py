# -*- coding: utf-8 -*-
"""三轴状态闸门（V18）

把「市场现在是什么状态」做成三个可解释、标签稳定、不需要重训的轴，
再用它给各模块上一道闸门。**不做无监督聚类，不做全样本拟合。**

轴1 温度  = 主板涨停家数 20 日 z-score         源 data/limit_up_reason.db
轴2 趋势  = 全市场等权指数距 MA20 的偏离 %      源 data/cache/kline_cache.duckdb
轴3 集中度 = 最大题材家数 / 主板涨停家数         源 services.market_rhythm_engine

输出状态（四选一，判定顺序：冰点 -> 退潮 -> 过热 -> 常温）：

    状态            条件                         建仓触发  止盈系数  板块推送
    🧊 冰点          z<=-1 且 trend<0              不放行    1.03      不发
    📉 退潮下行      trend<=-1.0                   放行      1.03      发(注记)
    🚀 过热抱团      z>=+1 且 集中度>=35%          放行      1.02      发(注记)
    ⚡ 常温轮动      其余                          放行      1.03      发

**失败一律放行（fail-open）**：任一轴取不到数，状态回落到「常温轮动」，
绝不因为数据问题静默卡死选股或推送。

CLI：python services/regime_gate.py   —— 打印当天三轴读数与状态
"""
import os
import sqlite3
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)          # 直接跑本文件时也能 import services.*
_LU_DB = os.path.join(_ROOT, 'data', 'limit_up_reason.db')
_KL_DB = os.path.join(_ROOT, 'data', 'cache', 'kline_cache.duckdb')

# ---------------- 阈值（要调就调这里）----------------
Z_COLD = -1.0        # 温度冰点：低于这个 z 视为市场冰点
Z_HOT = 1.0          # 温度过热
TREND_DOWN = -1.0    # 趋势下行：等权指数距 MA20 偏离 <= 这个值
CONC_HIGH = 0.12     # 集中度抱团：最大题材占涨停家数 >= 12%
                     # 按近 40 个交易日实测分布标定：最小 3.8% / 25分位 5.9%
                     # / 中位 8.0% / 75分位 11.4% / 90分位 15.5% / 最大 22.4%
TP_NORMAL = 1.03     # 常规止盈系数（建仓价 +3%）
TP_HOT = 1.02        # 过热期提前止盈

# ---------------- 状态名 ----------------
ST_ICE = '🧊 冰点'
ST_FADE = '📉 退潮下行'
ST_HOT = '🚀 过热抱团'
ST_NORMAL = '⚡ 常温轮动'

_CACHE = {'ts': 0.0, 'data': None}
_LOCK = threading.Lock()
TTL = 300.0          # 5 分钟


def _lu_counts(n=21):
    """最近 n 个交易日的主板涨停家数（按日期升序）"""
    con = sqlite3.connect(_LU_DB)
    try:
        rows = con.execute(
            "SELECT date, COUNT(*) c FROM limit_up_reasons "
            "WHERE substr(code,1,3) IN "
            "('600','601','603','605','000','001','002','003') "
            "GROUP BY date ORDER BY date DESC LIMIT ?", (n,)).fetchall()
    finally:
        con.close()
    return [(r[0], r[1]) for r in reversed(rows)]


def _temp_axis():
    """轴1：主板涨停家数 20 日 z-score。返回 dict 或 None"""
    cs = _lu_counts(21)
    if len(cs) < 12:
        return None
    today = cs[-1][1]
    win = [c for _, c in cs[:-1]][-20:]
    if len(win) < 8:
        return None
    mu = sum(win) / float(len(win))
    var = sum((x - mu) ** 2 for x in win) / float(len(win))
    sd = var ** 0.5
    z = (today - mu) / sd if sd > 0 else 0.0
    return {'today': today, 'mean': mu, 'sd': sd, 'z': z,
            'date': cs[-1][0], 'win5': [c for _, c in cs[-5:]]}


def _trend_axis():
    """轴2：全市场等权指数距 MA20 的偏离 %。返回 dict 或 None"""
    if not os.path.exists(_KL_DB):
        return None
    import duckdb
    con = duckdb.connect(_KL_DB, read_only=True)
    try:
        row = con.execute("""
            WITH s AS (
              SELECT CAST(code AS VARCHAR) code, date, close,
                     LAG(close) OVER (PARTITION BY code ORDER BY date) pc
              FROM kline_cache
              WHERE substr(CAST(code AS VARCHAR),1,3) IN
                    ('600','601','603','605','000','001','002','003')
            ), r AS (
              SELECT date, avg(close/pc - 1.0) ret
              FROM s WHERE pc IS NOT NULL AND pc > 0 GROUP BY date
            ), e AS (
              SELECT date, ret,
                     exp(sum(ln(1+ret)) OVER (ORDER BY date)) * 100.0 idx
              FROM r WHERE ret > -0.5
            )
            SELECT date, idx,
                   avg(idx) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING
                                  AND CURRENT ROW) ma20
            FROM e ORDER BY date DESC LIMIT 1
        """).fetchone()
    finally:
        con.close()
    if not row or not row[2]:
        return None
    idx, ma20 = float(row[1]), float(row[2])
    return {'date': row[0], 'idx': idx, 'ma20': ma20,
            'dev': (idx / ma20 - 1.0) * 100.0}


def _conc_axis():
    """轴3：最大题材家数 / 主板涨停家数。返回 dict 或 None"""
    try:
        from services.market_rhythm_engine import get_rhythm
    except Exception:
        return None
    d = get_rhythm()
    if not d or not d.get('ok'):
        return None
    boards = [b for b in (d.get('boards') or []) if not b.get('is_attribute')]
    if not boards:
        return None
    n_lu = d.get('lu_count') or 0
    if n_lu <= 0:
        return None
    # 注意：boards 是按「状态」排序的，[0] 不是家数最多的那个，必须取 max(count)
    top = max(boards, key=lambda b: b.get('count') or 0)
    conc = float(top['count']) / float(n_lu)
    return {'top': top['theme'], 'top_n': top['count'], 'n_lu': n_lu,
            'conc': conc, 'n_board': len(boards)}


def compute(force=False):
    """返回当天状态闸门。任何异常都不抛，失败即放行。"""
    global _CACHE
    now = time.time()
    with _LOCK:
        if (not force and _CACHE['data']
                and now - _CACHE['ts'] < TTL):
            return _CACHE['data']
        out = _compute_inner()
        _CACHE = {'ts': now, 'data': out}
        return out


def _compute_inner():
    t = tr = c = None
    try:
        t = _temp_axis()
    except Exception as e:
        print('[状态闸门] 温度轴取数失败: %s' % e, flush=True)
    try:
        tr = _trend_axis()
    except Exception as e:
        print('[状态闸门] 趋势轴取数失败: %s' % e, flush=True)
    try:
        c = _conc_axis()
    except Exception as e:
        print('[状态闸门] 集中度轴取数失败: %s' % e, flush=True)

    z = t['z'] if t else 0.0
    dev = tr['dev'] if tr else 0.0
    conc = c['conc'] if c else 0.0

    if t and tr and z <= Z_COLD and dev < 0:
        state, allow, tp, push = ST_ICE, False, TP_NORMAL, False
    elif tr and dev <= TREND_DOWN:
        state, allow, tp, push = ST_FADE, True, TP_NORMAL, True
    elif t and c and z >= Z_HOT and conc >= CONC_HIGH:
        state, allow, tp, push = ST_HOT, True, TP_HOT, True
    else:
        state, allow, tp, push = ST_NORMAL, True, TP_NORMAL, True

    parts = []
    if t:
        parts.append('涨停%d家(20日均%.0f,z=%+.2f)' % (t['today'], t['mean'], z))
    else:
        parts.append('涨停--')
    if tr:
        parts.append('等权距MA20 %+.2f%%' % dev)
    else:
        parts.append('趋势--')
    if c:
        parts.append('集中度%.0f%%(%s%d家)' % (conc * 100, c['top'], c['top_n']))
    else:
        parts.append('集中度--')
    note = ' ｜ '.join(parts)

    return {
        'ok': True,
        'state': state, 'grade': state,
        'allow_trigger': allow, 'tp_factor': tp, 'push': push,
        'note': note,
        'temp': t, 'trend': tr, 'conc': c,
        'ts': time.time(),
    }


def brief():
    """给界面用的一行摘要"""
    d = compute()
    return '%s ｜ %s' % (d['state'], d['note'])


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    d = compute(force=True)
    print('=' * 68)
    print('三轴状态闸门')
    print('=' * 68)
    print('状态      :', d['state'])
    print('建仓触发  :', '放行' if d['allow_trigger'] else '不放行（降为观察）')
    print('止盈系数  :', d['tp_factor'])
    print('板块推送  :', '发' if d['push'] else '不发')
    print('读数      :', d['note'])
    print()
    t = d.get('temp')
    if t:
        print('轴1 温度   : 今日主板涨停 %d 家 ｜ 20日均 %.1f ｜ sd %.1f ｜ z %+.2f ｜ %s'
              % (t['today'], t['mean'], t['sd'], t['z'], t['date']))
        print('             近5日 %s' % t['win5'])
    tr = d.get('trend')
    if tr:
        print('轴2 趋势   : 等权指数 %.2f ｜ MA20 %.2f ｜ 偏离 %+.2f%% ｜ %s'
              % (tr['idx'], tr['ma20'], tr['dev'], tr['date']))
    c = d.get('conc')
    if c:
        print('轴3 集中度 : 最大题材「%s」%d 家 / 涨停 %d 家 = %.1f%% ｜ 板块 %d 个'
              % (c['top'], c['top_n'], c['n_lu'], c['conc'] * 100, c['n_board']))
    print()
    print('阈值       : z<%.1f 且 趋势<0 -> 冰点 ；趋势<=%.1f -> 退潮 ；'
          'z>=%+.1f 且 集中度>=%.0f%% -> 过热'
          % (Z_COLD, TREND_DOWN, Z_HOT, CONC_HIGH * 100))
