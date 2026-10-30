# -*- coding: utf-8 -*-
"""整合升级（v2_board）验证：板块启动雷达 / 涨停判定 / 深度逻辑模板 / DS 次数预算 / 可跟区禁已涨停。
全部打桩，不打网络。运行：python _verify_v2_board.py"""
import sys, os, datetime, json
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

# ---- 1 _is_lu 涨停判定边界 ----
print('== 1 涨停判定 ==')
def mk(code, name, pct, lb, price, prev, board='main', industry='半导体'):
    return {'code': code, 'name': name, 'pct': pct, 'lb': lb, 'price': price,
            'prev': prev, 'industry': industry, 'board': board, 'amount': 1e8, 'turn': 3.0}

check('主板 9.4% 未涨停', not cdr._is_lu(mk('000001', '甲', 9.4, 2.0, 10.94, 10.0)))
check('主板 9.5% 涨停', cdr._is_lu(mk('000002', '乙', 9.5, 2.0, 10.95, 10.0)))
check('创业板 19.4% 未涨停', not cdr._is_lu(mk('300001', '丙', 19.4, 2.0, 11.94, 10.0, 'cyb')))
check('创业板 19.5% 涨停', cdr._is_lu(mk('300002', '丁', 19.5, 2.0, 11.95, 10.0, 'cyb')))

# ---- 2 _board_start 板块启动雷达 ----
print('== 2 板块启动雷达 ==')
# 3只共振 → 命中
rows_board = [
    mk('000011', '龙头甲', 7.0, 3.1, 10.7, 10.0, 'main', '存储芯片'),
    mk('000012', '中军乙', 4.0, 2.4, 10.4, 10.0, 'main', '存储芯片'),
    mk('000013', '跟风丙', 2.9, 1.9, 10.3, 10.0, 'main', '存储芯片'),
    mk('000014', '弱票丁', 1.5, 1.0, 10.2, 10.0, 'main', '存储芯片'),   # 不满足门槛
]
b = cdr._board_start(rows_board, '震荡')
check('3只共振 → 命中板块', b is not None and b['sec'] == '存储芯片')
check('共振家数=3', b is not None and b['fzn'] == 3)
roles = {s['name']: s['role'] for s in b['stocks']}
check('龙头甲=龙头(超次高3pp)', roles.get('龙头甲') == '龙头')
check('中军乙=中军', roles.get('中军乙') == '中军')
check('跟风丙=跟风', roles.get('跟风丙') == '跟风')
# 仅2只共振 → 不命中
rows_2 = rows_board[:2]
check('仅2只共振 → 不命中', cdr._board_start(rows_2, '震荡') is None)
# 偏空门槛上调：3只都在涨幅2.5~3.5 且量比1.8 → 震荡命中、偏空不命中
rows_bear = [
    mk('000021', 'a', 3.0, 1.9, 10.3, 10.0, 'main', '军工'),
    mk('000022', 'b', 2.8, 1.9, 10.3, 10.0, 'main', '军工'),
    mk('000023', 'c', 2.6, 1.9, 10.3, 10.0, 'main', '军工'),
]
check('偏空门槛上调(3.5%): 3只2.5~3.5 → 不命中', cdr._board_start(rows_bear, '偏空') is None)
check('震荡口径: 同组 2.5 门槛 → 命中', cdr._board_start(rows_bear, '震荡') is not None)
# 一次只推最强1个：两个题材都≥3 → 返回家数多者
rows_two = rows_board + [
    mk('000031', 'x', 4.0, 2.0, 10.4, 10.0, 'main', '军工'),
    mk('000032', 'y', 3.5, 2.0, 10.4, 10.0, 'main', '军工'),
    mk('000033', 'z', 3.0, 2.0, 10.3, 10.0, 'main', '军工'),
]
b2 = cdr._board_start(rows_two, '震荡')
check('两个题材均≥3 → 取共振家数最多(存储芯片3)且只返回1个', b2 is not None and b2['sec'] == '存储芯片')

# ---- 2.5 _board_start 早期观察参数化 ----
print('== 2.5 早期观察参数化 ==')
b_early = cdr._board_start(rows_2, '震荡', min_cnt=2, min_lb=1.5)
check('min_cnt=2/min_lb=1.5 → 观察命中', b_early is not None and b_early['sec'] == '存储芯片')
b_early2 = cdr._board_start([
    mk('000061', 'x', 2.6, 1.4, 10.3, 10.0, 'main', '光伏'),   # 量比1.4<1.5
    mk('000062', 'y', 2.7, 1.2, 10.3, 10.0, 'main', '光伏'),
], '震荡', min_cnt=2, min_lb=1.5)
check('量比1.4/1.2 → 观察不命中', b_early2 is None)
b_early3 = cdr._board_start(rows_bear, '偏空', min_cnt=2, min_lb=1.5)
check('偏空观察门槛: 涨幅3.0/2.8/2.6 不达3.5 → 不命中', b_early3 is None)
b_early4 = cdr._board_start([
    mk('000063', 'a', 3.8, 2.1, 10.4, 10.0, 'main', '军工'),
    mk('000064', 'b', 3.6, 2.2, 10.4, 10.0, 'main', '军工'),
], '偏空', min_cnt=2, min_lb=1.5)
check('偏空观察: 涨幅≥3.5+量比≥2.0 → 命中', b_early4 is not None and b_early4['sec'] == '军工')

# ---- 3 _deep_logic 六段深度逻辑 ----
print('== 3 六段深度逻辑模板 ==')
s_role = mk('000012', '中军乙', 4.2, 2.4, 10.4, 10.0, 'main', '存储芯片')
s_role['role'] = '中军'
dl = cdr._deep_logic(s_role, '存储芯片', 3)
for kw in ('① 为什么看板块', '② 为什么选这只', '③ 现在能不能买', '④ 买入区间', '⑤ 🎯 目标', '⑥ 🚫 放弃',
           '1-2 成', '-3%', '中军', '10.35', '可以轻仓试'):
    check(f'_deep_logic 含「{kw}」', kw in dl)
# canbuy 判定：fzn<3 → 先观察；价格高于区间上沿 → 先观察
s_obs = mk('000015', '观察票', 1.2, 1.2, 10.1, 10.0, 'main', '军工')
dl2 = cdr._deep_logic(s_obs, '军工', 1)
check('fzn<3 → 先观察', '⏳ 先观察，别急' in dl2)
# eod 口径
dl_eod = cdr._deep_logic(s_role, '存储芯片', None, eod_kind='低吸候选')
for kw in ('③ 明天能不能买', '低开 -1%~-2% 可轻仓低吸', '高开>3% 放弃', '回封或冲高 +3% 做T'):
    check(f'eod六段含「{kw}」', kw in dl_eod)

# ---- 4 _board_card 卡片要素（可跟区禁已涨停 + DS 额度注明 + 今天整体行） ----
print('== 4 板块启动卡 ==')
rows_card = [
    mk('000041', '龙甲', 6.5, 3.0, 10.7, 10.0, 'main', 'AI算力'),
    mk('000042', '中军乙', 4.0, 2.2, 10.4, 10.0, 'main', 'AI算力'),
    mk('000043', '跟风丙', 2.8, 1.9, 10.3, 10.0, 'main', 'AI算力'),
    mk('000044', '涨停丁', 9.5, 3.2, 10.95, 10.0, 'main', 'AI算力'),   # 已涨停：仅热度证据
]
rows_card[0]['role'] = '龙头'; rows_card[1]['role'] = '中军'; rows_card[2]['role'] = '跟风'; rows_card[3]['role'] = '跟风'
cdr._DS_EXHAUSTED = True  # 模拟额度用尽
card = cdr._board_card({'sec': 'AI算力', 'stocks': rows_card, 'fzn': 4}, 62, '震荡')
check('卡片含「今天整体」', '🧭 今天整体' in card)
check('卡片含「为什么现在看这个板块」', '为什么现在看这个板块' in card)
check('共振确认列已涨停仅作热度证据', '已涨停·仅热度证据' in card and '涨停丁' in card)
check('可跟区严格剔除已涨停(涨停丁不在可跟区)', '涨停丁' not in card[card.index('可跟（未涨停'):])
check('卡片含六段深度逻辑(①②③④⑤⑥)', all(k in card for k in ('① 为什么看板块', '② 为什么选这只', '③ 现在能不能买', '④ 买入区间', '⑤ 🎯 目标', '⑥ 🚫 放弃')))
check('DS 额度用尽注明', '今日 DS 额度已用' in card)
cdr._DS_EXHAUSTED = False

# ---- 4.5 _board_watch_card 早期观察卡 ----
print('== 4.5 早期观察卡 ==')
rows_obs = [
    mk('000051', '甲', 3.2, 1.6, 10.3, 10.0, 'main', '氢能源'),
    mk('000052', '乙', 2.8, 1.7, 10.3, 10.0, 'main', '氢能源'),
    mk('000053', '涨停丙', 9.5, 2.5, 10.95, 10.0, 'main', '氢能源'),
]
rows_obs[0]['role'] = '龙头'; rows_obs[1]['role'] = '中军'; rows_obs[2]['role'] = '跟风'
wcard = cdr._board_watch_card({'sec': '氢能源', 'stocks': rows_obs, 'fzn': 3}, 55, '震荡')
for kw in ('🧭 今天整体', '👀 为什么现在关注这个方向', '📌 关注方向', '已经在动的个股', '下一步盯什么', '确认后优先跟谁', '当前仍是观察期，建议先不加仓', '已涨停·仅热度证据'):
    check(f'观察卡含「{kw}」', kw in wcard)
check('观察卡不出现买入区间', '买入区间' not in wcard)

# ---- 5 DS 当日次数预算（≤8 网关） ----
print('== 5 DS 次数预算 ==')
_today = datetime.datetime.now().strftime('%Y-%m-%d')
_bak_path = cdr.DS_DAILY_COUNT_PATH
_bak_data = None
try:
    with open(_bak_path, encoding='utf-8') as f:
        _bak_data = json.load(f)
except Exception:
    pass
# 计数文件指向临时目录避免污染
cdr.DS_DAILY_COUNT_PATH = os.path.join(r'D:\QuantMonitorV6\_cloud_work\tools', 'data', '_ds_count_test.json')
import cloud_llm_gateway  # noqa 确保存在性判断用 try
# 写入 n=8 模拟当日已用尽
os.makedirs(os.path.dirname(cdr.DS_DAILY_COUNT_PATH), exist_ok=True)
with open(cdr.DS_DAILY_COUNT_PATH, 'w', encoding='utf-8') as f:
    json.dump({'date': _today, 'n': 8}, f, ensure_ascii=False)
check('当日已用 8 → used()=8', cdr._ds_daily_used() == 8)
_old_key = cdr.DEEPSEEK_KEY
cdr.DEEPSEEK_KEY = 'test-key'
_old_ask = cdr.ask_deepseek
# 不真调网关：打桩 chat
import importlib
_gw = importlib.import_module('cloud_llm_gateway')
_gw_orig_chat = _gw.chat if hasattr(_gw, 'chat') else None
def _fake_chat(**kw):
    return {'ok': True, 'text': '测试总结', 'done_cost': 0.1}
# 若 gateway 不存在本地，直接 monkeypatch cdr 内的 import 目标不可行 → 用 try 保护
check('DS 预算已停用：无 MODELSCOPE_KEY → ask 返回 '' 且不置 exhausted', (cdr.ask_deepseek({'x': 1}, purpose='board') == '') and not cdr._DS_EXHAUSTED)
# 恢复
cdr.DEEPSEEK_KEY = _old_key
cdr.DS_DAILY_COUNT_PATH = _bak_path
if _bak_data is not None:
    try:
        os.makedirs(os.path.dirname(_bak_path), exist_ok=True)
        with open(_bak_path, 'w', encoding='utf-8') as f:
            json.dump(_bak_data, f, ensure_ascii=False)
    except Exception:
        pass
try:
    os.remove(os.path.join(r'D:\QuantMonitorV6\_cloud_work\tools', 'data', '_ds_count_test.json'))
except Exception:
    pass

# ---- 6 源码静态断言 ----
print('== 6 源码机制 ==')
src = open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
for kw in ('def _is_lu', 'def _board_start', 'def _deep_logic', 'def _board_card', 'def _board_ds',
           'DS_DAILY_LIMIT = 8', '_DS_EXHAUSTED', 'def _ds_daily_used', 'def _ds_daily_inc',
           'min_pct + up_bias', 'min_lb + lb_bias', '已接近涨停：可操作价值低，降权',
           '只跟未涨停、严格止损', '今日 DS 额度已用'):
    check(f'源码含「{kw}」', kw in src)
bw = src[src.index('def build_watch'):src.index('def build_watch') + 6000]
check('build_watch 接入板块启动(最高优先级)', "板块启动雷达（最高优先级" in bw and "_board_card(board, mscore, mlabel" in bw)

print(f'\n=== {PASS} PASS / {FAIL} FAIL ===')
sys.exit(1 if FAIL else 0)
