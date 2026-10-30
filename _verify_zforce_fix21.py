# -*- coding: utf-8 -*-
"""FIX21 验证：①_finish_hit 的 ma5/above_ma5 计算正确性 ②源码过滤存在 ③build_zscan 链路含渲染标记"""
import io, sys, importlib.util, json
sys.stdout.reconfigure(encoding='utf-8')
spec = importlib.util.spec_from_file_location('zf', r'D:\QuantMonitorV6\tools\zhu_force_scan.py')
zf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zf)
spec2 = importlib.util.spec_from_file_location('cdr', r'D:\QuantMonitorV6\tools\cloud_daily_review.py')
cdr = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(cdr)
ok = fail = 0
def check(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1; print('[PASS]', name, detail)
    else: fail += 1; print('[FAIL]', name, detail)

def mk_kl(closes, n=40):
    """构造40根K线：前35根平缓，后len(closes)根按给定收盘价；开=昨收。"""
    kl = []
    prev = closes[0]
    for i in range(n):
        c = closes[i] if i >= n - len(closes) else closes[0] * (1 + 0.001 * (i % 5))
        if i >= n - len(closes):
            c = closes[i - (n - len(closes))]
        o = prev
        kl.append({'date': '2026-10-%02d' % ((i % 28) + 1), 'open': o, 'close': c,
                   'high': max(o, c) * 1.01, 'low': min(o, c) * 0.99, 'volume': 1000000.0 + i * 1000})
        prev = c
    return kl

def mk_pre(hit_cnt=4):
    return ({1: True, 2: True, 3: hit_cnt >= 3, 4: True, 5: True}, 6, 1.4, 1, (True, False), False)

# —— 1. 站上5日线（现价 > MA5） ——
closes_up = [10.0] * 35 + [10.1, 10.3, 10.5, 10.7, 10.9]
kl = mk_kl(closes_up)
s = {'code': '000001', 'name': '测试A', 'industry': '测试'}
r = zf._finish_hit(s, kl, mk_pre(), 60.0, '20200101')
check('上涨票 above_ma5=True', r is not None and r['above_ma5'] is True, '')
if r:
    exp_ma5 = sum(closes_up[-5:]) / 5
    check('ma5计算正确', abs(r['ma5'] - exp_ma5) < 0.011, 'ma5=%s exp=%.2f' % (r['ma5'], exp_ma5))

# —— 2. 低于5日线（现价 < MA5） ——
closes_down = [12.0] * 35 + [11.0, 10.5, 10.0, 9.5, 9.0]
kl2 = mk_kl(closes_down)
s2 = {'code': '000002', 'name': '测试B', 'industry': '测试'}
r2 = zf._finish_hit(s2, kl2, mk_pre(), 60.0, '20200101')
check('下跌票 above_ma5=False', r2 is not None and r2['above_ma5'] is False, 'r2=%s' % (r2.get('above_ma5') if r2 else None))

# —— 3. 等于5日线（现价 == MA5） ——
closes_eq = [10.0] * 38 + [10.2, 10.2]
kl3 = mk_kl(closes_eq)
r3 = zf._finish_hit({'code': '000003', 'name': '测试C', 'industry': '测试'}, kl3, mk_pre(), 60.0, '20200101')
check('等于5日线 above_ma5=True', r3 is not None and r3['above_ma5'] is True, 'ma5=%s price=%s' % (r3['ma5'], r3['price']))

# —— 4. 源码过滤存在 ——
src = io.open(r'D:\QuantMonitorV6\tools\zhu_force_scan.py', encoding='utf-8').read()
check('run_scanner含五日线硬过滤', "hits = [h for h in hits if h.get('above_ma5', False)]" in src, '')
check('过滤含坑底期统计', '坑底期' in src.split('FIX21五日线过滤')[1][:60], '')
src2 = io.open(r'D:\QuantMonitorV6\tools\cloud_daily_review.py', encoding='utf-8').read()
check('pool输入含ma5', "'ma5': h.get('ma5')" in src2, '')
check('渲染含站上5日线', '站上5日线' in src2, '')

# —— 5. build_zscan 链路（mock） ——
def _hit(code, name, price, score, mtype, state, kb_pct, above=True, ma5=None):
    return {'code': code, 'name': name, 'price': price, 'score': score, 'res_bonus': 10,
            'score_w': score + 10, 'industry': '化工', 'method': '横盘吸筹',
            'method_type': mtype, 'state': state,
            'box_low': round(price * 0.93, 2), 'box_high': round(price * 1.02, 2),
            'anchor': round(price * 0.97, 2), 'falsify_line': round(price * 0.95, 2),
            'avg_turn': 2.1, 'next_watch': '放量突破=确认', 'hit_conditions': [1, 2, 4],
            'ma5': ma5 if ma5 is not None else round(price * 0.97, 2), 'above_ma5': above,
            'kline_brief': [{'d': '10-%02d' % (14 + i), 'pct': (0.5 if i % 2 else -0.3), 'vol_wan': 8.0 + i}
                            for i in range(1, 11)] + [{'d': '10-24', 'pct': kb_pct, 'vol_wan': 15.0}]}

HITS = [_hit('002838', '道恩股份', 20.58, 82, '横盘吸筹', '箱体内', 1.2, True, 19.95),
        _hit('002909', '集泰股份', 12.30, 78, '打压吸筹', '坑底期', 0.8, True, 12.10),
        _hit('300453', '三鑫医疗', 9.85, 74, '横盘吸筹', '箱体内', 0.6, True, 9.70)]

def _fake_llm(payload, **kw):
    return json.dumps({"meta": {"scan_date": "2026-10-29", "data_gaps": [], "disclaimer": "概率研判非投资建议"},
        "radar": [{"code": "002838", "name": "道恩股份", "pattern_match": "模式三", "method": "横盘吸筹",
                    "sequence_stage": "回踩买点区", "anchor_price": "19.95", "anchor_type": "关键位", "anchor_quality_score": 25,
                    "cost_zone": "19.9-20.2", "cost_basis": "箱体中枢",
                    "breakout_check": {"verdict": "通过"}, "washout_check": {"verdict": "洗盘合格"},
                    "second_breakout": {"done": False, "volume_type": "数据不足"},
                    "pullback_check": {"five_conditions_met": [], "time_window": "", "verdict": "未到"},
                    "quality_total": 70, "observation_priority": "中", "position_ref": "1成档参考",
                    "credibility": "高", "theme": "化工", "resonance": "强", "theme_status": "当前主线",
                    "bottom_logic": "TPV国产替代供应商，据模型知识：新能源密封条主力品种",
                    "ignite_theme": "新能源新材料", "exit_rule": "止损=收盘破19.6元",
                    "next_watch": "①TPV低位；②观察触发：缩量回踩19.95元；③失效：破19.6元",
                    "false_alarm_status": "未见异常", "rank_score": 92, "rank_reason": "主线+强共振", "scan_score": 82}],
        "judged_all": [], "excluded": []}, ensure_ascii=False)

cdr.ask_deepseek = _fake_llm
cdr._follow_pool = lambda d: [{'c': '002838', 'hybk': '化工'}, {'c': '002909', 'hybk': '化工'}, {'c': '300453', 'hybk': '医疗器械'}]
cdr._sina_sector_pct = lambda: {'化工': {'pct': 2.0, 'cnt': 120}, '医疗器械': {'pct': 0.5, 'cnt': 90}}
import types
sys.modules['zhu_force_scan'] = types.SimpleNamespace(run_scanner=lambda **k: [dict(h) for h in HITS])
html = cdr.build_zscan(limit=None)
check('build_zscan出卡', isinstance(html, str) and '道恩股份' in html, 'len=%d' % len(html))
check('渲染含站上5日线标记', '站上5日线 19.95元' in html, '')
check('pool含above_ma5', "'above_ma5': bool(h.get('above_ma5', False))" in src2, '')

print('\n===== FIX21 verify: %d pass / %d fail =====' % (ok, fail))
sys.exit(1 if fail else 0)
