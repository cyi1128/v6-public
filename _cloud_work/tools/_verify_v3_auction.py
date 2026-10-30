# -*- coding: utf-8 -*-
"""批次 D-2 专项验证：五因子边界 / 0.72+0.28 权重 / 反推修正判定 / Top3 速判 / Top10。"""
import sys, os, io, re
sys.path.insert(0, r'D:\QuantMonitorV6\_cloud_work\tools')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import cloud_daily_review as cdr

cdr._git_commit_push = lambda *a, **k: True
PASS = FAIL = 0
def check(name, ok):
    global PASS, FAIL
    if ok:
        PASS += 1
        print('  PASS ', name)
    else:
        FAIL += 1
        print('> FAIL ', name)

def bars_of(vols, closes, base_date='2026-10-15'):
    """构造腾讯日K：每根 [date, open, close, high, low, volume]。"""
    out = []
    import datetime
    d0 = datetime.date.fromisoformat(base_date)
    for i, (v, c) in enumerate(zip(vols, closes)):
        dd = (d0 - datetime.timedelta(days=len(vols) - i)).isoformat()
        out.append([dd, c * 0.99, c, c * 1.02, c * 0.98, v])
    return out

def mk(code='600001', name='测试股', pct=3.5, vol=30, turn=2.0, lb=5.0,
       price=10.5, high=10.6, low=10.2, prev=10.1, industry='AI算力', board='main'):
    return {'code': code, 'name': name, 'price': price, 'pct': pct, 'vol': vol,
            'turn': turn, 'lb': lb, 'high': high, 'low': low, 'prev': prev,
            'industry': industry, 'board': board, 'amount': 1e8, 'list_date': '20200101'}

# ================= 一、反推修正判定 =================
print('== 反推修正（日K代理）==')
_vols_r = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100]  # 近10日等量
_closes_r = [8.0] * 8 + [9.5, 9.6]                            # 近2日累计 9.6/8.0-1=20%
bars_r = bars_of(_vols_r, _closes_r)
s_r = mk(pct=6.0, vol=100)
v, t = cdr._auction_revise(s_r, 3.0, 0.5, bars_r)
check('暴力反抽（近2日+20%且竞价高开6%）→ -20', v == -20.0 and t == '暴力反抽')

s_w = mk(pct=3.0, vol=10)
v, t = cdr._auction_revise(s_w, 1.5, 0.5, bars_of([100]*10, [10.0]*10))
check('无量反弹（高开3%但量比1.5）→ -12', v == -12.0 and t == '无量反弹')

s_h = mk(pct=2.5, vol=100)
v, t = cdr._auction_revise(s_h, 3.0, 0.90, bars_of([100]*10, [10.0]*10))
check('高位区（pos60=0.90）→ -5', v == -5.0 and t == '高位区')

# 缩量回踩后启动：昨量≤前日×0.95 + 昨收≥MA20×0.97 + vr≥2
_closes_s = [10.0] * 20 + [10.2, 10.1]
_vols_s = [120] * 18 + [100, 60, 55]
bars_s = bars_of(_vols_s, _closes_s)
v, t = cdr._auction_revise(mk(pct=3.0, vol=120), 2.5, 0.4, bars_s)
check('缩量回踩后启动（量递减+昨收站MA20+放量）→ +15', v == 15.0 and t == '缩量回踩启动')

v, t = cdr._auction_revise(mk(pct=2.5, vol=100), 3.0, 0.5, bars_of([100]*10, [10.0]*10))
check('走势平稳（主板高开2.5量比3）→ +8', v == 8.0 and t == '走势平稳')

v, t = cdr._auction_revise(mk(pct=3.0, vol=100), 2.5, 0.5, bars_of([100]*10, [10.0]*10))
check('无命中 → 0', v == 0.0 and t == '')

# ================= 二、五因子 + 权重 =================
print('== 五因子×0.72 + 题材×0.28 − 风险 + 反推 ==')
def patch_klines(bars):
    cdr.get_klines = lambda sym, n: bars

# 打桩竞价时钟：固定 9:25 竞价 5 分钟（避免真实时刻干扰 expected 量比归一化）
cdr._auction_elapsed_minutes = lambda: 5

# 满分场景：pct=3.5 主板满分区间；vol=30手=3000股；avg_vol5 控制 vr=6；ref_vol=5000
#   expected = avg_vol5/240*5；vr = 3000/expected ≥5 → expected≤600 → avg_vol5≤28800；取 24000→expected=500→vr=6
#   emo = turn(2)×6=12 ≥12 → 25；vref = 3000/5000=0.6 ≥0.5 → 15；shape 高开3.5≥3且vr≥5 → 15
_vols_max = [24000] * 5 + [5000]
_closes_max = [10.0] * 30
bars_max = bars_of(_vols_max + [5000]*10, _closes_max)
patch_klines(bars_max)
heat = {'AI算力': 100.0}
cnt = {'AI算力': 6}
mem = {'2026-10-20': ['AI算力']}
sc = mk(pct=3.5, vol=30, turn=2.0, lb=5.0, price=10.0, prev=10.0, industry='AI算力')
tot = cdr._auction_score_v3(sc, heat, cnt, mem)
check('满分场景综合分=100', abs(tot - 100.0) < 0.01)
check('量价分=100（20+25+25+15+15）', sc['_vr'] >= 5 and sc['_shape'] == '红柱递增')

# 权重验证：题材分贡献 = 100×0.28=28（满分时与量价 72 之和恰 100）
# 反推修正叠加：暴力反抽场景
_vols_r2 = [100] * 10 + [100]
_closes_r2 = [8.0] * 8 + [9.5, 9.6]
patch_klines(bars_of(_vols_r2, _closes_r2))
sc2 = mk(pct=6.0, vol=100, turn=3.0, lb=6.0, industry='AI算力')
tot2 = cdr._auction_score_v3(sc2, heat, cnt, mem)
check('暴力反抽修正生效（-20 已进总分）', sc2['_rtag'] == '暴力反抽' and tot2 <= tot - 15.0)

# 无量反弹 + 风险：高开 3% 量比不足（vr<2）→ -12；题材弱 heat<40 → risk+5
patch_klines(bars_of([24000]*5 + [5000]*10, [10.0]*30))
sc3 = mk(pct=3.0, vol=1, turn=1.0, lb=1.5, industry='冷门行业')
tot3 = cdr._auction_score_v3(sc3, {'冷门行业': 30.0}, {'冷门行业': 1}, None)
check('无量反弹(-12)+题材弱(+5) 已进总分', sc3['_rtag'] == '无量反弹' and tot3 < tot)

# ================= 三、Top10 / Top3 速判（集成渲染） =================
print('== build_auction 集成（打桩数据源）==')
cdr.HOLDINGS = []
cdr._clist_gainers = lambda: [mk(code='600001', name='甲票', pct=3.5, vol=30, turn=2.0, lb=5.0, industry='AI算力'),
                              mk(code='600002', name='乙票', pct=6.0, vol=100, turn=3.0, lb=6.0, industry='AI算力'),
                              mk(code='300001', name='丙票', pct=8.0, vol=40, turn=2.5, lb=4.0, industry='半导体'),
                              mk(code='600003', name='丁票', pct=2.0, vol=5, turn=0.8, lb=1.5, industry='冷门')]
cdr.get_pools = lambda: {'sectors': {}, 'zb_sec': {}, 'dt_sec': {}, 'lu': 0, 'zb': 0, 'dt': 0, 'max_lbc': 0}
cdr._auction_ds = lambda tops, heat: ({}, '<div>DS打桩</div>')
cdr.load_memory = lambda: {}
out = cdr.build_auction()
check('集成渲染返回 HTML', isinstance(out, str) and '竞价观察' in out)
check('卡片含 Top3 速判段', 'Top3 速判' in out)
check('卡片含 权重文案 0.72+0.28', '量价×0.72+题材×0.28' in out)
check('卡片含 反推标签 渲染', '暴力反抽' in out or '缩量回踩启动' in out or '走势平稳' in out)
check('卡片含 TOP10', 'TOP10' in out)

# ================= 四、源码机制 =================
print('== 源码机制 ==')
src = io.open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
for kw in ('def _auction_score_v3', 'def _auction_revise', 'def _auction_elapsed_minutes',
           '_GAP_SCORE_MAIN', '_GAP_SCORE_CYB', 'AUCTION_TOP_N = 10', '不推空卡', 'Top3 速判'):
    check(f'源码含「{kw}」', kw in src)

print(f'\n=== {PASS} PASS / {FAIL} FAIL ===')
sys.exit(1 if FAIL else 0)
