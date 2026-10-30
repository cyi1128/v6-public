# -*- coding: utf-8 -*-
"""第4步 实盘跟踪与复盘验证：record → update_performance → generate_review_card 全链路。
用 2026-10-23 两只实测票（永创智能84/凡拓数创62）mock K线，断言记录/回填/复盘卡关键内容。
可重跑：python tests/test_anchor_tracker.py"""
import importlib.util, io, json, os, shutil, sys, tempfile

PASS = FAIL = 0

def chk(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1; print('PASS', name)
    else:
        FAIL += 1; print('FAIL', name)

TOOLS = r'D:\QuantMonitorV6\tools'
sys.path.insert(0, TOOLS)
import anchor_tracker as T
import quality_scorer as QS

# 隔离记录目录（不污染正式 data/anchor_history）
TMP = tempfile.mkdtemp(prefix='anchor_trk_')
T.ANCHOR_HISTORY_DIR = TMP

# ---------- 准备：从实测扫描缓存评分，得到与推送一致的 final ----------
RAW = json.load(io.open(os.path.join(TOOLS, r'data\_test_anchor_full.json'), encoding='utf-8'))
scored = QS.score_batch(list(RAW))
FINAL = [c for c in scored if c.get('score_total', 0) >= 50]
TRADE_DATE = '2026-10-23'

# ---------- mock K线：推送日后 3 根（10-26/10-27/10-28） ----------
# 永创智能 603901：anchor 9.89 → entry_mid 9.89 / stop 9.59；后续连涨、最低 9.80 不触止损
# 凡拓数创 301313：anchor 32.23 → entry_mid 32.23 / stop 31.26；后续下跌、最低 31.10 触止损
def fake_kline(code, n=120):
    if code == '603901':
        return [
            {'date': '2026-10-23', 'open': 9.90, 'close': 9.95, 'high': 10.00, 'low': 9.80, 'volume': 1e6, 'amount': 1e7},
            {'date': '2026-10-26', 'open': 9.95, 'close': 10.19, 'high': 10.25, 'low': 9.90, 'volume': 1.2e6, 'amount': 1.2e7},
            {'date': '2026-10-27', 'open': 10.19, 'close': 10.42, 'high': 10.50, 'low': 10.10, 'volume': 1.4e6, 'amount': 1.4e7},
            {'date': '2026-10-28', 'open': 10.42, 'close': 10.55, 'high': 10.60, 'low': 10.30, 'volume': 1.3e6, 'amount': 1.3e7},
        ]
    if code == '301313':
        return [
            {'date': '2026-10-23', 'open': 32.30, 'close': 32.28, 'high': 32.50, 'low': 32.10, 'volume': 8e5, 'amount': 2.6e7},
            {'date': '2026-10-26', 'open': 32.00, 'close': 31.62, 'high': 32.05, 'low': 31.40, 'volume': 9e5, 'amount': 2.85e7},
            {'date': '2026-10-27', 'open': 31.60, 'close': 30.94, 'high': 31.70, 'low': 30.80, 'volume': 1e6, 'amount': 3.1e7},
            {'date': '2026-10-28', 'open': 30.90, 'close': 31.05, 'high': 31.20, 'low': 30.70, 'volume': 7e5, 'amount': 2.2e7},
        ]
    if code == '000002':
        # 只有推送日当天K线（停牌/未到后续交易日）→ 无后续bar 降级路径
        return [
            {'date': '2026-10-22', 'open': 5.00, 'close': 5.05, 'high': 5.10, 'low': 4.98, 'volume': 5e5, 'amount': 2.5e6},
        ]
    return None  # 其他 code → 无数据（降级路径）

T.get_kline = fake_kline

# ---------- A 记录落盘 ----------
n = T.record_candidates(FINAL, TRADE_DATE)
chk('A1 记录2只', n == 2)
rec_path = T._hist_path(TRADE_DATE)
chk('A2 记录文件存在', os.path.exists(rec_path))
doc = json.load(io.open(rec_path, encoding='utf-8'))
chk('A3 trade_date正确', doc['trade_date'] == TRADE_DATE)
codes = {c['code'] for c in doc['candidates']}
chk('A4 含两只', codes == {'603901', '301313'})
c1 = next(c for c in doc['candidates'] if c['code'] == '603901')
chk('A5 字段齐全(entry_zone/stop_loss/entry_mid/push_date)', all(c1.get(k) is not None for k in ('entry_zone', 'stop_loss', 'entry_mid', 'push_date', 'score_total', 'name')))
chk('A6 永创进场区间9.69~10.09', c1['entry_zone'] == '9.69~10.09')
chk('A7 永创止损9.59', c1['stop_loss'] == 9.59)
# 同日重复记录去重
n2 = T.record_candidates(FINAL, TRADE_DATE)
doc2 = json.load(io.open(rec_path, encoding='utf-8'))
chk('A8 重复记录不堆叠', len(doc2['candidates']) == 2)

# ---------- B 表现回填 ----------
u = T.update_performance(TRADE_DATE)
chk('B1 回填2只', u == 2)
doc3 = json.load(io.open(rec_path, encoding='utf-8'))
perf = {c['code']: c.get('performance') or {} for c in doc3['candidates']}
p901 = perf['603901']
chk('B2 永创day1+3.03%', abs(p901['day1_close_pct'] - 3.03) < 0.01)
chk('B3 永创day3+6.67%', abs(p901['day3_close_pct'] - 6.67) < 0.01)
chk('B4 永创未触止损', p901['hit_stop'] is False)
p313 = perf['301313']
chk('B5 凡拓day1-1.89%', abs(p313['day1_close_pct'] - (-1.89)) < 0.01)
chk('B6 凡拓day3-3.66%', abs(p313['day3_close_pct'] - (-3.66)) < 0.01)
chk('B7 凡拓触止损', p313['hit_stop'] is True)
chk('B8 永创5日最高10.60', abs(p901['max_high5'] - 10.60) < 0.01)

# ---------- C 复盘卡 ----------
html = T.generate_review_card(days=5)
chk('C1 复盘卡非空', bool(html))
for kw in ('突破回踩·复盘', '推送 2 只', '次日胜率', '永创智能', '凡拓数创', '9.69~10.09', '31.26', '触止损', '表现最好', '表现最差', '平均3日收益'):
    chk(f'C2 含[{kw}]', kw in html)
# 胜率：次日 1盈1亏 → 50%；3日 1盈1亏 → 50%；平均3日 (6.67-4.00)/2 = +1.335
chk('C3 次日胜率50%', '50%' in html)
chk('C4 表现最好=永创', '表现最好：永创智能' in html)
chk('C5 表现最差=凡拓', '表现最差：凡拓数创' in html)

# ---------- D 缺数据优雅降级 ----------
# D1: get_kline 返回 None（拉取失败）→ 不写假表现、不崩
T.record_candidates([{'code': '000001', 'name': '平安银行', 'score_total': 60, 'position_suggest': '轻仓（建议5-15%）',
                      'anchor_price': 10.00, 'retest_date': None, 'sector_count': 1}], '2026-10-22')
u2 = T.update_performance('2026-10-22')
chk('D1 缺数据回填不崩(0)', u2 == 0)
doc22 = json.load(io.open(T._hist_path('2026-10-22'), encoding='utf-8'))
p0 = doc22['candidates'][0].get('performance')
chk('D2 拉取失败不写假表现', p0 is None)
# D3: 有K线但无后续bar（停牌）→ bars_after=0 标记
T.record_candidates([{'code': '000002', 'name': '万科A', 'score_total': 55, 'position_suggest': '1/3仓试错',
                      'anchor_price': 5.00, 'retest_date': None, 'sector_count': 0}], '2026-10-22')
u3 = T.update_performance('2026-10-22')
doc22b = json.load(io.open(T._hist_path('2026-10-22'), encoding='utf-8'))
p00 = {c['code']: c.get('performance') or {} for c in doc22b['candidates']}
chk('D3 无后续bar标记bars_after=0', p00.get('000002', {}).get('bars_after') == 0)
html2 = T.generate_review_card(days=5)
chk('D4 复盘卡含数据未齐', '数据未齐' in html2 or '待回填' in html2)
chk('D5 缺数据票仍在卡内', '平安银行' in html2 and '万科A' in html2)

# ---------- E 无记录防御 ----------
T.ANCHOR_HISTORY_DIR = tempfile.mkdtemp(prefix='anchor_trk_empty_')
chk('E1 空目录复盘返回None', T.generate_review_card(5) is None)

# ---------- F cloud_daily_review.build_review 真实链路（mock tracker K线） ----------
T.ANCHOR_HISTORY_DIR = TMP
import cloud_daily_review as C
rv = C.build_review()
chk('F1 build_review非空', bool(rv))
chk('F2 build_review含复盘标题', bool(rv) and '突破回踩·复盘' in rv)
chk('F3 build_review含永创', bool(rv) and '永创智能' in rv)

print(f'==== {PASS} PASS / {FAIL} FAIL')
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
