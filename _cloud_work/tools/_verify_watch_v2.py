# -*- coding: utf-8 -*-
"""异动提醒 v2 模块验证（watch 重写后）：时间窗口 / 触发条件 / 卡片要素 / 冷却机制。
全部打桩，不打网络。运行：python _verify_watch_v2.py"""
import sys, datetime, io
sys.path.insert(0, r'D:\QuantMonitorV6\_cloud_work\tools')
import cloud_daily_review as cdr

PASS = FAIL = 0
def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS  {name}')
    else:
        FAIL += 1
        print(f'  FAIL  {name}')

def t(h, m):
    return datetime.datetime(2026, 10, 20, h, m)

# ---- 1 时间窗口（09:30-11:30 / 13:00-14:50）----
print('== 1 时间窗口 ==')
check('_in_session 09:30 在窗口', cdr._in_session(t(9, 30)))
check('_in_session 11:30 在窗口', cdr._in_session(t(11, 30)))
check('_in_session 13:00 在窗口', cdr._in_session(t(13, 0)))
check('_in_session 14:50 在窗口(临界)', cdr._in_session(t(14, 50)))
check('_in_session 09:29 不在窗口', not cdr._in_session(t(9, 29)))
check('_in_session 11:31 午休不推', not cdr._in_session(t(11, 31)))
check('_in_session 14:51 硬停', not cdr._in_session(t(14, 51)))
check('_in_session 15:00 收盘不推', not cdr._in_session(t(15, 0)))

# ---- 2 _early_watch 触发（打桩 _clist_gainers）----
print('== 2 触发条件 ==')
def mk(code, name, pct, lb, turn, price, prev, industry='半导体'):
    return {'code': code, 'name': name, 'pct': pct, 'lb': lb, 'turn': turn,
            'price': price, 'prev': prev, 'industry': industry, 'high': price, 'low': prev}

rows_ambush = [
    mk('000001', '甲股', 4.5, 2.3, 4.0, 10.5, 10.0),
    mk('000002', '乙股', 3.0, 1.6, 3.0, 9.5, 9.2),
]
cdr._clist_gainers = lambda: rows_ambush
a, n = cdr._early_watch('震荡')
check('启动埋伏: 量比2.3+站上昨收+同题材2只 → 命中', any(x['name'] == '甲股' for x in a))
check('埋伏不误入逼近(<7%)', not any(x['name'] == '甲股' for x in n))

rows_near = [mk('000003', '丙股', 8.2, 2.0, 6.0, 20.0, 18.5)]
cdr._clist_gainers = lambda: rows_near
a, n = cdr._early_watch('震荡')
check('逼近涨停: 8.2%+量比2.0 → 命中', any(x['name'] == '丙股' for x in n))

rows_none = [mk('000004', '丁股', 4.5, 1.5, 3.0, 10.5, 10.0)]
cdr._clist_gainers = lambda: rows_none
a, n = cdr._early_watch('震荡')
check('量比1.5(<2.0) 不触发埋伏', not any(x['name'] == '丁股' for x in a))

rows_bear = [mk('000005', '戊股', 4.2, 2.3, 3.0, 10.5, 10.0)]
cdr._clist_gainers = lambda: rows_bear
a, n = cdr._early_watch('偏空')
check('偏空: 4.2%(<4.5) 涨幅门槛上调不触发', not any(x['name'] == '戊股' for x in a))

rows_bear_weak = [mk('000006', '己股', 4.6, 2.5, 3.0, 10.5, 10.0),
                  mk('000007', '庚股', 3.0, 1.4, 2.0, 9.5, 9.2)]  # 庚股量比1.4不算跟风
cdr._clist_gainers = lambda: rows_bear_weak
a, n = cdr._early_watch('偏空')
check('偏空: 4.6%+量比2.5 但跟风仅1只 → 不触发', not any(x['name'] == '己股' for x in a))

rows_bear_ok = [mk('000006', '己股', 4.6, 2.5, 3.0, 10.5, 10.0),
                mk('000007', '庚股', 3.0, 1.4, 2.0, 9.5, 9.2),
                mk('000008', '辛股', 2.5, 1.5, 1.5, 9.0, 8.8)]
cdr._clist_gainers = lambda: rows_bear_ok
a, n = cdr._early_watch('偏空')
check('偏空: 4.6%+量比2.5+跟风2只 → 命中', any(x['name'] == '己股' for x in a))

# ---- 3 _watch_card 卡片要素（小白友好）----
print('== 3 卡片要素 ==')
sg = {'n': '万润科技', 'code': '002654', 'type': '启动埋伏', 'sec': '存储芯片', 'score': 7.2,
      'cur': '12.35', 'buy_low': '12.29', 'buy_high': '12.47',
      'stop': '11.92（买入价-3%优先执行）', 'pos': '1-2成', 'act': '提前埋伏',
      'why': '存储芯片3只同步放量，量比2.6，分时站上昨收。'}
html = cdr._watch_card(sg, 62)
for kw in ('大白话', '建议买入区间', '止损', '做T思路', '风险', '仓位建议',
           '12.29 ~ 12.47', '冲高+3%~+5%', '强，等回踩再上', '若直接冲涨停'):
    check(f'_watch_card 含「{kw}」', kw in html)

# ---- 3.5 DS 有脑版 + 题材清洗（D-3b）----
print('== 3.5 DS 有脑版 + 题材清洗 ==')
check('_sec_clean 纯数字"-0.68"→空', cdr._sec_clean('-0.68') == '')
check('_sec_clean 数字+板块"13.96板块"→空', cdr._sec_clean('13.96板块') == '')
check('_sec_clean 黑名单"概念"→空', cdr._sec_clean('概念') == '')
check('_sec_clean 正常词"存储芯片"保留', cdr._sec_clean('存储芯片') == '存储芯片')
check('_sec_clean 噪声词"半导体行业"→"半导体"', cdr._sec_clean('半导体行业') == '半导体')
check('_sec_clean 空值→空', cdr._sec_clean('') == '')

spot_txt = """甲股（000001）| 半导体板块集体放量，它是跟得最紧的那个，资金真金白银进来了 | 可轻仓
丙股（000003）| 独立拉起来的妖股，纯情绪没业绩支撑 | 别追"""
cdr.ask_deepseek = lambda payload, purpose='x', system_text=None: spot_txt
parsed = cdr._spot_ds([{'n': '甲股', 'code': '000001', 'type': '逼近涨停', 'pct': 8.2, 'lb': 2.0,
                        'turn': 6.0, 'sec': '半导体', 'score': 7.0, 'act': '可跟进'}])
check('_spot_ds 解析两行', parsed.get('甲股') and parsed.get('丙股'))
check('_spot_ds 大白话为 DS 文本非模板', '跟得最紧' in parsed['甲股'].get('why', ''))

cdr.ask_deepseek = lambda payload, purpose='x', system_text=None: ''
sg2 = {'n': '万润科技', 'code': '002654', 'type': '启动埋伏', 'sec': '存储芯片', 'score': 7.2,
       'cur': '12.35', 'buy_low': '12.29', 'buy_high': '12.47',
       'stop': '11.92（买入价-3%优先执行）', 'pos': '1-2成', 'act': '提前埋伏',
       'why': '存储芯片3只同步放量，量比2.6，分时站上昨收。'}
h_ok = cdr._watch_card(sg2, 62, {'万润科技': '存储芯片今天3只一起放量，资金合力，等回踩分时均线再上'})
check('DS 命中 → 卡内为大白话', '👉 大白话' in h_ok and '资金合力' in h_ok)
h_fb = cdr._watch_card(sg2, 62)
check('DS 缺失 → 回退模板大白话', '大白话' in h_fb and '存储芯片3只同步放量' in h_fb)

rows_dirty = [mk('000001', '甲股', 4.5, 2.3, 4.0, 10.5, 10.0, industry='-0.68'),
              mk('000002', '乙股', 3.0, 1.6, 3.0, 9.5, 9.2, industry='-0.68')]
cdr._clist_gainers = lambda: rows_dirty
a, n = cdr._early_watch('震荡')
if a:
    s0 = a[0]
    check('脏题材清洗: sg 的 sec 不是数字', s0.get('sec_clean') == '其他' and '0.68' not in str(s0.get('sec_clean')))
else:
    check('脏题材清洗: 命中且 sec 不是数字', False)

# ---- 3.6 DS 深度挖掘（D-3c：K线近况+板块历史）----
print('== 3.6 DS 深度挖掘 ==')
import datetime as _dt
_px = 8.0
fake_k = []
_base = _dt.date(2026, 8, 1)
for _i in range(60):
    _d = (_base + _dt.timedelta(days=_i)).strftime('%Y-%m-%d')
    _o = _px; _c = _px + 0.04; _v = 1e6 * (1.1 ** _i)
    fake_k.append((_d, _o, _c, _c, _o, _v))
    _px = _c
cdr.get_klines = lambda sym, n: fake_k
kc = cdr._kline_ctx('000001', 10.4)
check('_kline_ctx 5日涨幅≈+1.6%', kc.get('g5') is not None and abs(kc['g5'] - 1.6) < 0.2)
check('_kline_ctx 量能放大', kc.get('vol_r') and kc['vol_r'] >= 1.2)
check('_kline_ctx 连阳5天', kc.get('up_days') == 5)
check('_kline_ctx 创60日新高', kc.get('new_high') is True)

mem_fake = {'2026-10-20': {'存储芯片': {'leaders': ['万润科技', '香农芯创']}},
            '2026-10-17': {'存储芯片': {'leaders': ['万润科技']}}}
bh = cdr._board_hist('存储芯片', mem_fake, sorted(mem_fake, reverse=True))
check('_board_hist 近2天+龙头', '2天' in bh and '万润科技' in bh and '香农芯创' in bh)
bh0 = cdr._board_hist('其他', mem_fake, sorted(mem_fake, reverse=True))
check('_board_hist 无记录→首日启动', '首日启动' in bh0)

captured = {}
def _fake_ds_capture(payload, purpose='x', system_text=None):
    captured.update(payload)
    return spot_txt
cdr.ask_deepseek = _fake_ds_capture
parsed = cdr._spot_ds([{'n': '万润科技', 'code': '000001', 'type': '启动埋伏', 'pct': 4.5, 'lb': 2.3,
                        'turn': 4.0, 'sec': '存储芯片', 'score': 7.2, 'act': '提前埋伏', 'price': 10.4}],
                       mem_fake, sorted(mem_fake, reverse=True))
check('DS 收到 kline 深度字段', 'kline' in captured['stocks'][0] and '5日累涨' in captured['stocks'][0]['kline'])
check('DS 收到 board_hist 字段', 'board_hist' in captured['stocks'][0] and '龙头' in captured['stocks'][0]['board_hist'])
check('深度版解析仍正常', '跟得最紧' in parsed.get('甲股', {}).get('why', ''))

# ---- 4 源码静态断言（build_watch 关键机制）----
print('== 4 源码机制 ==')
src = open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
bw = src[src.index('def build_watch'):src.index('def build_watch') + 16000]
for kw in ('09:30-11:30/13:00-14:50', '构建超时(>30s)', 'link_ts', '|埋伏',
           '同题材≥3只', '量比≥1.5', '回踩分时均线/开盘价企稳介入'):
    check(f'build_watch 源码含「{kw}」', kw in bw)

print(f'\n=== {PASS} PASS / {FAIL} FAIL ===')
sys.exit(1 if FAIL else 0)
