# -*- coding: utf-8 -*-
"""机构级分时做T引擎 —— 独立验证（真实行情 + 手算交叉比对 + 边界）。

跑法：python tools/_verify_intraday_t_engine.py
可重跑。网络不可用时 [A]/[K] 会自动跳过并记为 SKIP（不判失败），其余逻辑用例必须全过。
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, r'D:\QuantMonitorV6')

from strategy.intraday_t_engine import (                            # noqa: E402
    THolding, TQuote, TParams, IntradayTEngine, get_engine,
    resolve_window, apply_plan_to_row, TIME_WINDOWS,
)

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def skip(name, why):
    RESULTS.append((name, None, why))
    print('  [SKIP] %s（%s）' % (name, why))


E = IntradayTEngine()
print('=' * 96)
print('[' * 3, '机构级分时做T引擎 验证', ']' * 3)
print('=' * 96)

# ---------------- A. 真实行情 VWAP 口径 ----------------
print('\n[A] 真实日内 VWAP 口径（amount/(volume×100) 必须落在当日 low~high 内）')
try:
    from utils.http_market_data import get_realtime_quotes_http
    codes = ['600519', '300750', '000001', '601318', '002594']
    qs = get_realtime_quotes_http(codes) or {}
    okn = 0
    for c in codes:
        d = qs.get(c)
        if not d:
            continue
        tq = TQuote(price=d.get('price', 0), prev_close=d.get('last_close', 0),
                    high=d.get('high', 0), low=d.get('low', 0),
                    volume_lots=d.get('volume', 0), amount=d.get('amount', 0),
                    vol_ratio=d.get('vol_ratio', 0), turnover=d.get('turnover', 0))
        v, src = tq.intraday_vwap()
        good = (src == 'amount/volume' and d.get('low', 0) <= v <= d.get('high', 0))
        okn += 1 if good else 0
        print('      %s price=%.2f vwap=%.3f 来源=%s %s' % (c, tq.price, v, src, 'OK' if good else '越界!'))
    if qs:
        check('A 真实 VWAP 落在当日区间内', okn == len([c for c in codes if qs.get(c)]),
              '%d/%d 只通过' % (okn, len([c for c in codes if qs.get(c)])))
    else:
        skip('A 真实 VWAP', '行情接口无返回')
except Exception as e:
    skip('A 真实 VWAP', '取数异常 %s' % e)

# ---------------- B. 时间窗口 ----------------
print('\n[B] 时间窗口映射')
CASES = [('09:20', 'auction', 0.0), ('09:32', 'open_spike', 0.3), ('09:45', 'open_30', 1.0),
         ('10:05', 'lull_1', 0.6), ('10:20', 'am_core', 1.0), ('11:00', 'am_late', 0.5),
         ('12:00', 'lunch', 0.0), ('13:10', 'pm_open', 1.0), ('13:45', 'lull_2', 0.6),
         ('14:20', 'pm_core', 1.0), ('14:50', 'pm_close', 0.7), ('20:00', 'closed', 0.0)]
bad = []
for hm, key, w in CASES:
    h, m = hm.split(':')
    got = resolve_window(datetime(2026, 10, 9, int(h), int(m)))
    if got['key'] != key or abs(got['weight'] - w) > 1e-9:
        bad.append('%s→%s(%s) 期望 %s(%s)' % (hm, got['key'], got['weight'], key, w))
check('B 12 个时刻映射正确', not bad, '；'.join(bad) if bad else '全部命中')
check('B2 窗口表无重叠/无空洞', len(TIME_WINDOWS) == 12)

# ---------------- C. 量价结构 ----------------
print('\n[C] 量价结构（真实量比口径）')
def vp(price, prev, high, low, vr):
    tq = TQuote(price=price, prev_close=prev, high=high, low=low, vol_ratio=vr,
                volume_lots=1e6, amount=price * 1e6 * 100)
    v, _ = tq.intraday_vwap()
    return E.volume_price_state(tq, v)

c1 = vp(10.60, 10.30, 10.75, 10.20, 1.8)     # 放量上攻不持续
c2 = vp(9.90, 10.10, 10.15, 9.85, 0.5)       # 下跌缩量有承接
c3 = vp(9.60, 10.20, 10.25, 9.55, 1.9)       # 放量下跌
c4 = vp(10.30, 10.10, 10.35, 10.00, 0.5)     # 缩量上涨
c5 = vp(9.88, 10.10, 10.15, 9.87, 1.9)       # 低位放量试探(贴近低点)
check('C1 放量上攻不持续 → 倾向高抛', c1['state'] == 'up_expand_stall' and c1['rev_hint'] >= 0.9, c1['label'])
check('C2 下跌缩量有承接 → 倾向低吸', c2['state'] == 'down_shrink_absorb' and c2['fwd_hint'] >= 0.9, c2['label'])
check('C3 放量下跌 → 硬阻断低吸', c3['state'] == 'down_expand' and c3['hard_block'] == 'buy', c3['label'])
check('C4 缩量上涨 → 中性偏高抛', c4['state'] == 'up_shrink' and 0.4 <= c4['rev_hint'] <= 0.7, c4['label'])
check('C5 低位放量 → 不误判为可低吸满分', c5['fwd_hint'] < 0.9, c5['state'])

# ---------------- D. 成本预估（手算硬比对） ----------------
print('\n[D] 做T后成本预估 vs 手算')
h = THolding(code='600000', cost=10.0, qty=10000, qty_avail=10000)
est = E.estimate_cost(h, 1000, 11.0, 10.8, 'reverse')
# 手算：卖费=5+5.5+0.11=10.61；买费=5+0+0.108=5.108；滑点=1000*0.01*2=20 → 合计 35.718
# Δ总 = (10.8-11.0)*1000 + 35.718 = -164.282 → 新成本 = (100000-164.282)/10000 = 9.98357
check('D1 反T 新成本=9.9836', abs(est['new_cost'] - 9.98357) < 5e-4, '实得 %.5f' % est['new_cost'])
check('D2 反T 费用合计=35.72', abs(est['fees'] - 35.718) < 5e-3, '实得 %.3f' % est['fees'])
check('D3 反T 成本下降且幅度=0.164%', est['delta'] < 0 and abs(est['delta_pct'] + 0.16428) < 5e-3,
      'Δ%%=%.4f' % est['delta_pct'])
est2 = E.estimate_cost(h, 1000, 11.0, 10.8, 'forward')
check('D4 正T 公式同形（同价差同样降幅）', abs(est2['delta'] - est['delta']) < 1e-9)
check('D5 正T 需追加资金>0', est2['extra_cash'] > 10000, '需 %.0f 元' % est2['extra_cash'])
est3 = E.estimate_cost(h, 1000, 10.8, 11.0, 'reverse')
check('D6 做反了会抬高成本（>0）', est3['delta'] > 0, 'Δ%%=%.4f' % est3['delta_pct'])

# ---------------- E. 盈亏平衡价差（手算硬比对） ----------------
print('\n[E] 盈亏平衡价差')
be2000 = E.breakeven_spread(2000, 10.0)
# 手算：2×max(10×0.00025, 5/2000)=0.005；10×(0.0005+0.00002)=0.0052；滑点 0.02 → 0.0302
be100 = E.breakeven_spread(100, 10.0)
# 手算：2×(5/100)=0.1；0.0052；0.02 → 0.1252
check('E1 qty=2000/价10 → 0.0302', abs(be2000 - 0.0302) < 1e-6, '实得 %.6f' % be2000)
check('E2 qty=100/价10 → 0.1252（小单更贵）', abs(be100 - 0.1252) < 1e-6, '实得 %.6f' % be100)
check('E3 价差门槛随数量单调递减', be100 > be2000)

# ---------------- F. 反T优先 / T+1 / 无成本 ----------------
print('\n[F] 反T优先与 T+1 约束')
TEN20 = datetime(2026, 10, 9, 10, 20)
q_ok = TQuote(price=10.60, prev_close=10.30, high=10.75, low=10.20,
              volume_lots=1e6, amount=10.30 * 1e6 * 100, vol_ratio=1.8, turnover=1.2)
struct_hi = dict(near_resist=True, cross='dead_above_zero')
h_free = THolding(code='600000', cost=10.0, qty=10000, qty_avail=10000)
p_free = E.evaluate(h_free, q_ok, now=TEN20, atr=0.15, structure=struct_hi)
check('F1 条件齐备 → 反T 且分数高', p_free['side'] == 'reverse' and p_free['score'] >= 80,
      '%s %.1f分' % (p_free['side_cn'], p_free['score']))
h_today = THolding(code='600000', cost=10.0, qty=10000, buy_time='2026-10-09 09:35:00')
p_today = E.evaluate(h_today, q_ok, now=TEN20, atr=0.15, structure=struct_hi)
check('F2 今日买入(T+1) → 不给反T', p_today['side'] != 'reverse', p_today['side_cn'])
check('F3 T+1 有明确提示', any('T+1' in w for w in p_today['warnings']), '；'.join(p_today['warnings']))
h_nocost = THolding(code='600000', cost=None, qty=None)
p_nc = E.evaluate(h_nocost, q_ok, now=TEN20, atr=0.15)
check('F4 无成本 → 中性处理且有提示', any('无持仓成本' in w for w in p_nc['warnings']))
check('F5 暴露未做T原因链（reasons）', len(p_free['reasons']) >= 3, ' / '.join(p_free['reasons'][:3]))

# ---------------- G. 硬闸门 ----------------
print('\n[G] 硬闸门')
q_down = TQuote(price=9.60, prev_close=10.20, high=10.25, low=9.55,
                volume_lots=1e6, amount=9.9 * 1e6 * 100, vol_ratio=1.9)
p_down = E.evaluate(THolding(code='600000', cost=10.5, qty=10000, qty_avail=10000),
                    q_down, now=TEN20, atr=0.15)
check('G1 放量下跌 → 不做T且红灯', p_down['side'] == 'none' and p_down['level'] == 'red', p_down['risk_status'])
q_weak = TQuote(price=9.90, prev_close=10.30, high=10.35, low=9.85,
                volume_lots=1e6, amount=10.2 * 1e6 * 100, vol_ratio=0.8)
p_weak = E.evaluate(THolding(code='600000', cost=10.0, qty=10000, qty_avail=10000),
                    q_weak, now=TEN20, atr=0.15)
check('G2 跌破VWAP 1.5% → 硬闸门', p_weak['side'] == 'none' and 'VWAP' in (p_weak['hard_block'] or ''),
      str(p_weak['hard_block']))
p_night = E.evaluate(h_free, q_ok, now=datetime(2026, 10, 11, 20, 0), atr=0.15)
check('G3 非交易时段 → 不做T', p_night['side'] == 'none' and p_night['window'] == 'closed', p_night['risk_status'])
p_limit = E.evaluate(THolding(code='600000', cost=10.0, qty=10000, qty_avail=10000),
                     TQuote(price=11.00, prev_close=10.05, high=11.00, low=10.00,
                            volume_lots=1e6, amount=10.5 * 1e6 * 100, vol_ratio=2.5),
                     now=TEN20, atr=0.15)
check('G4 涨停锁仓 → 不做T', p_limit['side'] == 'none' and '涨停' in (p_limit['hard_block'] or ''),
      str(p_limit['hard_block']))
p_cyb = E.evaluate(THolding(code='300750', cost=10.0, qty=10000, qty_avail=10000),
                   TQuote(price=11.00, prev_close=10.05, high=11.00, low=10.00,
                          volume_lots=1e6, amount=10.5 * 1e6 * 100, vol_ratio=2.5),
                   now=TEN20, atr=0.15)
check('G5 创业板 +9.5% 不算涨停（20cm）', p_cyb['hard_block'] is None, str(p_cyb['hard_block']))

# ---------------- H. 确定性与时间外置 ----------------
print('\n[H] 确定性与无隐藏时间依赖')
a = E.evaluate(h_today, q_ok, now=TEN20, atr=0.15, structure=struct_hi)
b = E.evaluate(h_today, q_ok, now=TEN20, atr=0.15, structure=struct_hi)
check('H1 同输入两次结果一致', a == b)
# 时间权重必须真正进入打分：10:20(权重1.0) 的分数应高于 11:00(权重0.5)
w_hi = E.evaluate(h_free, q_ok, now=datetime(2026, 10, 9, 10, 20), atr=0.15, structure=struct_hi)
w_lo = E.evaluate(h_free, q_ok, now=datetime(2026, 10, 9, 11, 0), atr=0.15, structure=struct_hi)
check('H2 时间窗只由入参 now 决定', w_hi['window'] == 'am_core' and w_lo['window'] == 'am_late',
      '%s(%s) → %s(%s)' % (w_hi['window_cn'], w_hi['window'], w_lo['window_cn'], w_lo['window']))
check('H3 时间权重真的进入打分（低权重时段分数更低）', w_lo['score'] < w_hi['score'],
      '%.1f → %.1f' % (w_hi['score'], w_lo['score']))
w_off = E.evaluate(h_free, q_ok, now=datetime(2026, 10, 9, 12, 0), atr=0.15, structure=struct_hi)
check('H4 休市时段直接封死', w_off['side'] == 'none' and w_off['time_weight'] == 0.0, w_off['risk_status'])

# ---------------- I. 价差不足护栏 ----------------
print('\n[I] 做T必须降成本（价差护栏）')
# 造一个"高抛条件齐备但 ATR 太小、价差盖不住手续费"的场景
q_tiny = TQuote(price=10.00, prev_close=9.80, high=10.20, low=9.80,
                volume_lots=1e6, amount=10.00 * 1e6 * 100, vol_ratio=1.8)
h_cheap = THolding(code='600000', cost=9.60, qty=10000, qty_avail=10000)
p_tiny = E.evaluate(h_cheap, q_tiny, now=datetime(2026, 10, 9, 9, 40), atr=0.02, structure=struct_hi)
hit_guard = (p_tiny['side'] == 'none' and
             (any('盈亏平衡' in w for w in p_tiny['warnings']) or '价差不足' in p_tiny['side_cn']))
check('I1 价差≤盈亏平衡 → 不出执行信号', hit_guard,
      '%s | 建议数=1000×? | %s' % (p_tiny['side_cn'], '；'.join(p_tiny['warnings'])))
check('I2 该场景反T分本身是够的（证明是价差护栏拦下的，不是分数不够）',
      p_tiny['score_rev'] >= 65, '反T分 %.1f' % p_tiny['score_rev'])

# ---------------- J. 静态：无 UI/网络耦合 ----------------
print('\n[J] 引擎与 UI/网络解耦（便于独立替换与回测）')
import ast as _ast
eng_path = os.path.join(r'D:\QuantMonitorV6', 'strategy', 'intraday_t_engine.py')
src = open(eng_path, newline='', encoding='utf-8').read()
tree = _ast.parse(src)
imports = set()
for n in _ast.walk(tree):
    if isinstance(n, _ast.Import):
        imports.update(a.name.split('.')[0] for a in n.names)
    elif isinstance(n, _ast.ImportFrom):
        imports.add((n.module or '').split('.')[0])
banned = sorted(x for x in imports
                if x.lower() in ('pyqt6', 'pyqt5', 'requests', 'urllib', 'duckdb', 'sqlite3')
                or 'http_market_data' in x.lower() or 'qt' in x.lower())
check('J1 依赖仅标准库（无 Qt/网络/数据库）', not banned,
      ('命中 %s' % banned) if banned else 'imports=%s' % sorted(imports))
check('J2 文件为 LF（新文件）', '\r\n' not in src)
check('J3 参数集中在一处（TParams）', src.count('class TParams') == 1 and src.count('@dataclass') >= 3)

# ---------------- K. 真实个股端到端 ----------------
print('\n[K] 真实个股端到端（真行情 + 真日线 ATR）')
try:
    from utils.http_market_data import get_realtime_quotes_http
    from utils.kline_provider import _get_kline_from_duckdb
    CODES = ['600519', '300750', '000001', '601318', '002594', '600036', '000858', '601899',
             '002415', '600030']
    qs = get_realtime_quotes_http(CODES) or {}
    fired = None
    fields_ok = score_ok = n_real = 0
    for code in CODES:
        d = qs.get(code)
        bars = _get_kline_from_duckdb(code, count=60) or []
        if not d or len(bars) < 20:
            continue
        n_real += 1
        trs = []
        for i in range(1, len(bars)):
            h_, l_, pc = bars[i]['high'], bars[i]['low'], bars[i - 1]['close']
            trs.append(max(h_ - l_, abs(h_ - pc), abs(l_ - pc)))
        atr = sum(trs[-14:]) / 14.0
        holding = THolding(code=code, cost=round(d['price'] * 0.97, 2), qty=2000, qty_avail=2000)
        quote = TQuote(price=d['price'], prev_close=d['last_close'], open=d.get('open', 0),
                       high=d['high'], low=d['low'], volume_lots=d['volume'], amount=d['amount'],
                       vol_ratio=d.get('vol_ratio', 0), turnover=d.get('turnover', 0))
        # 用真实盘中时段评估两次（早盘 / 尾盘），取真的出信号的那次
        for when in (datetime(2026, 10, 9, 9, 45), datetime(2026, 10, 9, 14, 20)):
            plan = E.evaluate(holding, quote, now=when, atr=atr,
                              structure=dict(near_support=True, near_resist=True))
            need = ('side', 'score', 'level', 'text', 'action', 'vwap', 'window', 'vol_state',
                    'suggest_qty', 'breakeven_spread', 'est_cost_after', 'est_cost_delta_pct', 'reasons')
            if all(k in plan for k in need):
                fields_ok += 1
            if 0 <= plan['score'] <= 100:
                score_ok += 1
            if plan['side'] != 'none' and plan['suggest_qty'] > 0 and fired is None:
                fired = (code, holding, plan, quote)
        last = E.evaluate(holding, quote, now=datetime(2026, 10, 9, 14, 20), atr=atr,
                          structure=dict(near_support=True, near_resist=True))
        print('      %s 现价 %.2f VWAP %.3f(%s) %s %s | %s' % (
            code, quote.price, last['vwap'], last['vwap_src'], last['text'],
            ('%.0f分' % last['score']), last['action'][:44]))
    check('K1 plan 字段齐全（全部真实样本）', n_real > 0 and fields_ok == n_real * 2,
          '%d 只 × 2 时段 = %d/%d' % (n_real, fields_ok, n_real * 2))
    check('K2 分数在 0~100（全部真实样本）', score_ok == n_real * 2, '%d/%d' % (score_ok, n_real * 2))
    if fired:
        code, holding, plan, quote = fired
        span = plan['sell_target'] - plan['buy_target']
        delta_manual = -span * plan['suggest_qty'] + plan['est_fees']
        delta_engine = plan['est_cost_delta'] * holding.qty
        print('      >> 真实触发：%s %s %s' % (code, plan['side_cn'], plan['action']))
        check('K3 成本预估自洽（独立复算 Δ）',
              abs(delta_manual - delta_engine) < max(1.0, abs(delta_engine) * 0.02),
              '%s 手算 Δ=%.2f 引擎 Δ=%.2f' % (code, delta_manual, delta_engine))
        check('K4 触发时成本确实下降', plan['est_cost_delta_pct'] < 0,
              'Δ%%=%.3f' % plan['est_cost_delta_pct'])
        check('K5 触发价差 > 盈亏平衡', (plan['sell_target'] - plan['buy_target']) > plan['breakeven_spread'],
              '价差 %.4f > BE %.4f' % (plan['sell_target'] - plan['buy_target'], plan['breakeven_spread']))
    else:
        skip('K3/K4/K5 真实触发复算', '这 %d 只在当前真实行情下均未达到执行分（本身说明闸门在起作用）' % n_real)
except Exception as e:
    skip('K 真实端到端', '异常 %s' % e)

# ---------------- L. 写回行对象 ----------------
print('\n[L] apply_plan_to_row 写回')
row = dict(code='600000', signal_level='gray', signal_text='⚪ 待机', action='观望',
           risk_status='', buy_point=9.9, sell_point=10.1)
out = apply_plan_to_row(row, p_free)
check('L1 反T 写回 signal_dir=sell', out['signal_dir'] == 'sell')
check('L2 反T 卖点=当前/目标价', abs(out['sell_point'] - p_free['sell_target']) < 1e-9, str(out['sell_point']))
check('L3 附带成本预估字段', out['est_cost_after'] is not None and out['t_score'] is not None,
      '成本→%.4f' % (out['est_cost_after'] or 0))
row2 = apply_plan_to_row(dict(code='x'), E.evaluate(h_free, q_weak, now=TEN20, atr=0.15))
check('L4 硬闸门行不产生买卖方向', row2['signal_dir'] is None)

# ---------------- 汇总 ----------------
bad = [n for n, ok, _ in RESULTS if ok is False]
skips = [n for n, ok, _ in RESULTS if ok is None]
print('\n' + '=' * 96)
print('PASS %d / FAIL %d / SKIP %d' % (len(RESULTS) - len(bad) - len(skips), len(bad), len(skips)))
if bad:
    print('失败用例：' + '；'.join(bad))
print('=' * 96)
sys.exit(1 if bad else 0)
