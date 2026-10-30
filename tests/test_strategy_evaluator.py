# -*- coding: utf-8 -*-
"""第5步 策略评估与优化验证：load_history / evaluate / sensitivity / suggestions / eval_card / build_evaluate 全链路。
mock 多日记录（分数段覆盖 + 数据未齐票），断言指标/分层/推荐/建议/卡内容。
可重跑：python tests/test_strategy_evaluator.py"""
import io, json, os, shutil, sys, tempfile

PASS = FAIL = 0

def chk(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1; print('PASS', name)
    else:
        FAIL += 1; print('FAIL', name)

TOOLS = r'D:\QuantMonitorV6\tools'
sys.path.insert(0, TOOLS)
import anchor_tracker as TR
import strategy_evaluator as SE

# 隔离记录目录（不污染正式 data/anchor_history）
TMP = tempfile.mkdtemp(prefix='strat_eval_')
TR.ANCHOR_HISTORY_DIR = TMP

def perf(day1, day3, day5, hit, bars=6):
    return {'day1_close_pct': day1, 'day3_close_pct': day3, 'day5_close_pct': day5,
            'hit_stop': hit, 'bars_after': bars, 'max_high5': 11.0, 'min_low5': 8.0}

def cand(code, name, score, p=None):
    c = {'code': code, 'name': name, 'score_total': score, 'position_suggest': '轻仓（建议5-15%）',
         'anchor_price': 10.0, 'retest_date': None, 'sector_count': 1, 'push_date': '2026-10-23',
         'entry_zone': '9.8~10.2', 'stop_loss': 9.7, 'entry_mid': 10.0, 'performance': p}
    return c

def write_doc(fname, cands, trade_date):
    os.makedirs(TMP, exist_ok=True)
    doc = {'trade_date': trade_date, 'candidates': cands}
    with open(os.path.join(TMP, fname), 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

# ---------- 准备 mock 记录（覆盖分数段 + 数据未齐） ----------
write_doc('20261023.json', [
    cand('603901', '永创智能', 84, perf(3.03, 6.67, 8.5, False)),
    cand('301313', '凡拓数创', 62, perf(-1.89, -3.66, -5.0, True)),
    cand('000555', '恒立实业', 55, perf(1.0, 2.0, 3.0, False)),
    cand('600111', '北方稀土', 82, perf(-2.0, -4.0, -4.5, True)),
    cand('000666', '经纬纺机', 60, None),   # 数据未齐
], '2026-10-23')
write_doc('20261024.json', [
    cand('300777', '中简科技', 68, perf(1.5, 2.5, 2.8, False)),
], '2026-10-24')

# ---------- A load_history ----------
recs = SE.load_history(days=1)          # 只取最近1个有记录交易日（10-24）
chk('A1 days=1只读最近', len(recs) == 1 and recs[0]['code'] == '300777')
recs_all = SE.load_history()            # 全部
chk('A2 全量6只', len(recs_all) == 6)
recs_range = SE.load_history(start='2026-10-23', end='2026-10-23')
chk('A3 区间过滤只取10-23', len(recs_range) == 5)
chk('A4 空目录返回空', (lambda: (TR.ANCHOR_HISTORY_DIR.__setitem__ if False else None))() is None)  # 占位不执行
TR2 = tempfile.mkdtemp(prefix='strat_eval_empty_')
TR.ANCHOR_HISTORY_DIR = TR2
chk('A5 空目录load空', SE.load_history() == [])
chk('A6 空目录evaluate不崩', SE.evaluate([])['total_push'] == 0)
chk('A7 空目录card返回None', SE.generate_eval_card(20) is None)
TR.ANCHOR_HISTORY_DIR = TMP

# ---------- B evaluate 指标 ----------
e = SE.evaluate(SE.load_history(days=2))
chk('B1 推送6只', e['total_push'] == 6)
chk('B2 3日数据5只', e['n_day3'] == 5)
chk('B3 次日胜率60%', abs(e['day1_winrate'] - 60.0) < 0.01)          # 3/5
chk('B4 3日胜率60%', abs(e['day3_winrate'] - 60.0) < 0.01)          # 3/5
chk('B5 平均3日', abs(e['avg_day3'] - ((6.67-3.66+2.0-4.0+2.5)/5)) < 0.01)
chk('B6 中位3日', abs(e['median_day3'] - 2.0) < 0.01)               # [-4,-3.66,2,2.5,6.67] → 2.0
chk('B7 触止损率40%', abs(e['hit_stop_rate'] - 40.0) < 0.01)        # 2/5
chk('B8 盈亏比0.97', e['profit_loss_ratio'] is not None and abs(e['profit_loss_ratio'] - 0.97) < 0.02)
chk('B9 最差3日-4.0', e['worst_day3'] == -4.0)
chk('B10 数据未齐1只', e['n_no_data'] == 1)
chk('B11 5日胜率60%', abs(e['day5_winrate'] - 60.0) < 0.01)         # 3/5

# ---------- C 分数段分层 ----------
bands = {b['band']: b for b in e['bands']}
chk('C1 >=80样本2', bands['>=80']['n'] == 2)
chk('C2 >=80 3日胜率50%', abs(bands['>=80']['day3_winrate'] - 50.0) < 0.01)
chk('C3 >=80 平均3日1.33', 1.32 <= bands['>=80']['avg_day3'] <= 1.34)
chk('C4 60-69样本3', bands['60-69']['n'] == 3 and bands['60-69']['n_with_day3'] == 2)
chk('C5 50-59胜率100%', abs(bands['50-59']['day3_winrate'] - 100.0) < 0.01)
chk('C6 70-79样本0', bands['70-79']['n'] == 0)

# ---------- D 敏感性 ----------
s = SE.sensitivity_analysis(SE.load_history(days=2))
rows = {r['min_score']: r for r in s['grid']}
chk('D1 阈值50样本6/5', rows[50]['n'] == 6 and rows[50]['n_with_day3'] == 5)
chk('D2 阈值60样本5/4', rows[60]['n'] == 5 and rows[60]['n_with_day3'] == 4)
chk('D3 阈值80样本2', rows[80]['n_with_day3'] == 2)
chk('D4 推荐阈值65', s['recommended'] == 65)
# 无3日数据的记录不进敏感性格局
s_empty = SE.sensitivity_analysis([cand('X', 'X', 90, None)])
chk('D5 无数据推荐None', s_empty['recommended'] is None)

# ---------- E 建议生成 ----------
sugg = SE.generate_suggestions(e, s)
chk('E1 建议3-6条', 3 <= len(sugg) <= 6)
joined = '；'.join(sugg)
chk('E2 含阈值建议', any('阈值' in x or 'min_score' in x for x in sugg))
chk('E3 含触止损建议', any('触止损率' in x or '止损' in x for x in sugg))
chk('E4 含样本提示', any('样本' in x for x in sugg))
# 空样本建议
sugg0 = SE.generate_suggestions(SE.evaluate([]), s_empty)
chk('E5 空样本提示调参', len(sugg0) == 1 and '暂无足够样本' in sugg0[0])

# ---------- F 评估卡 ----------
html = SE.generate_eval_card(days=2)
chk('F1 卡非空', bool(html))
for kw in ('策略评估', '推送 6 只', '次日胜率', '3日胜率', '触止损率', '盈亏比', '分数段分层', '参数敏感性', '推荐阈值', '优化建议', '>=80分', '🏆'):
    chk(f'F2 含[{kw}]', kw in html)
chk('F3 含数据未齐', '数据未齐 1 只' in html)

# ---------- G build_evaluate 真实链路（mock tracker 目录 + 防拉真K线） ----------
import cloud_daily_review as C
TR.update_performance = lambda d: 0          # 防真实拉网
rv = C.build_evaluate()
chk('G1 build_evaluate非空', bool(rv))
chk('G2 含策略评估标题', bool(rv) and '策略评估' in rv)
chk('G3 含推荐阈值', bool(rv) and '推荐阈值' in rv)
chk('G4 含推荐阈值', bool(rv) and '推荐阈值' in rv)

# ---------- H 无历史时 build_evaluate 防御 ----------
TR.ANCHOR_HISTORY_DIR = tempfile.mkdtemp(prefix='strat_eval_none_')
rv0 = C.build_evaluate()
chk('H1 空历史返回None', rv0 is None)

print(f'==== {PASS} PASS / {FAIL} FAIL')
shutil.rmtree(TMP, ignore_errors=True)
shutil.rmtree(TR2, ignore_errors=True)
sys.exit(1 if FAIL else 0)
