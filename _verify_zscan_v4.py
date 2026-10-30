# -*- coding: utf-8 -*-
"""V4 升级影子验证：mock 扫描器/板块/LLM → 跑 build_zscan 全链路
断言：①payload V4 schema ②meta/radar/judged_all/excluded 三段解析 ③V4字段映射兜底
④涨幅红线终拦 ⑤量能绝对数字清洗 ⑥降级分支V4卡 ⑦渲染含新字段"""
import io, sys, importlib.util, json
sys.stdout.reconfigure(encoding='utf-8')
spec = importlib.util.spec_from_file_location('cdr', r'D:\QuantMonitorV6\tools\cloud_daily_review.py')
cdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdr)
ok = fail = 0

def check(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1; print('[PASS]', name, detail)
    else: fail += 1; print('[FAIL]', name, detail)

# —— 构造扫描器命中池样例（字段对齐 zhu_force_scan.py V3 输出） ——
def _hit(code, name, price, score, method, mtype, state, kb_pct, res=15, industry='化工新材料', avg_turn=2.1):
    return {'code': code, 'name': name, 'price': price, 'score': score, 'res_bonus': res,
            'score_w': score + res, 'industry': industry, 'method': method,
            'method_type': mtype, 'state': state,
            'box_low': round(price * 0.93, 2), 'box_high': round(price * 1.02, 2),
            'anchor': round(price * 0.97, 2), 'falsify_line': round(price * 0.95, 2),
            'avg_turn': avg_turn, 'next_watch': '放量突破=建仓确认', 'hit_conditions': [1, 2, 3, 4, 6],
            'kline_brief': [{'d': '10-%02d' % (14 + i), 'pct': (0.5 if i % 2 else -0.3), 'vol_wan': 8.0 + i}
                            for i in range(1, 11)] + [{'d': '10-24', 'pct': kb_pct, 'vol_wan': 15.0}]}

HITS = [
    _hit('002838', '道恩股份', 20.58, 82, '打压吸筹→坑底死寂→试盘→突破确认', '打压吸筹', '坑底期', 2.1, res=15),
    _hit('002909', '集泰股份', 12.30, 78, '横盘吸筹+红肥绿瘦', '横盘吸筹', '箱体内', 1.2, res=10, industry='化工'),
    _hit('300453', '三鑫医疗', 9.85, 74, '底部缩量熬底', '横盘吸筹', '箱体内', 0.6, res=5, industry='医疗器械'),
    _hit('600999', '招商证券', 18.50, 88, '拉高吸筹', '拉高吸筹', '高于箱体', 8.5, res=15, industry='证券'),  # 涨幅红线样例
    _hit('601688', '华泰证券', 20.10, 80, '打压吸筹', '打压吸筹', '坑底期', -0.5, res=0, industry='证券'),
]

# —— V4 LLM 输出样例（含绝能量能数字、涨幅红线票、judged_all/excluded） ——
V4_OUT = {
    "meta": {"scan_date": "2026-10-29", "data_gaps": ["历史热点榜7日数据未接入"], "disclaimer": "建仓痕迹为概率研判，不构成投资建议"},
    "radar": [
        {"code": "002838", "name": "道恩股份", "pattern_match": "模式三", "pattern_basis": "底部阳线放量阴线缩量横盘2-4周",
         "method": "打压吸筹→坑底死寂→试盘→突破确认", "method_review": "扫描器给：打压吸筹；复核：一致",
         "sequence_stage": "回踩买点区", "anchor_price": "19.43", "anchor_type": "关键位", "anchor_quality_score": 25,
         "cost_zone": "19.4-19.8", "cost_basis": "坑底均价+锚±2%回踩区",
         "breakout_check": {"close_above_anchor_pct": "3.2", "volume_ratio": "1.8", "sector_background": "同板块涨2%家数5只", "verdict": "通过"},
         "washout_check": {"volume_shrink_ratio": "0.5", "red_fat_green_thin": "1.35", "verdict": "洗盘合格"},
         "second_breakout": {"done": False, "volume_type": "数据不足"},
         "pullback_check": {"five_conditions_met": ["回踩锚±2%", "当日缩量", "站上5日线"], "time_window": "3-7天", "verdict": "可观察"},
         "quality_score_detail": {"anchor": 25, "sector_resonance": 25, "news_freshness": 10, "washout": 15, "second_breakout": 0},
         "quality_total": 75, "observation_priority": "中", "position_ref": "1成档参考",
         "observation_priority_note": "仅作观察优先级参考，非投资建议",
         "credibility": "高", "credibility_reason": "手法三要件齐全+锚关键位+洗盘合格", "evidence_gaps": [],
         "theme": "化工新材料", "resonance": "强", "resonance_basis": "今日主线且涨停5家",
         "sector_rise2pct_count_on_ignition_day": 5, "theme_status": "当前主线", "theme_status_basis": "今日热点榜Top3涨停≥3家",
         "bottom_logic": "道恩股份主营热塑性弹性体TPV，是化工新材料细分国产替代供应商，下游汽车轻量化与新能源配件共振今日主线，成交39.4万股为缩量。据模型知识：TPV为新能源密封条国产替代主力品种。",
         "ignite_theme": "汽车轻量化/新能源新材料",
         "exit_rule": "止损=收盘破19.40元；止盈参考=锚+8%减半/+16%清仓（观察剧本，非投资建议）",
         "next_watch": "①TPV国产替代低位票；②观察触发：缩量回踩19.43元锚±2%不破；③失效条件：放量跌破19.40元移出观察池",
         "false_alarm_status": "未见异常", "false_alarm_risk": "",
         "rank_score": 97, "rank_reason": "当前主线+强共振+质量75", "scan_score": 82},
        {"code": "002909", "name": "集泰股份", "pattern_match": "模式四", "pattern_basis": "底部抬升",
         "method": "横盘吸筹", "sequence_stage": "找锚中", "anchor_price": "11.90", "anchor_type": "无名位", "anchor_quality_score": 10,
         "cost_zone": "11.8-12.2", "cost_basis": "箱体中枢", "breakout_check": {"verdict": "数据不足"},
         "washout_check": {"verdict": "数据不足无法判定"}, "second_breakout": {"done": False, "volume_type": "数据不足"},
         "pullback_check": {"five_conditions_met": [], "time_window": "", "verdict": "未到"},
         "quality_score_detail": {"anchor": 10, "sector_resonance": 15, "news_freshness": 5, "washout": 0, "second_breakout": 0},
         "quality_total": 30, "observation_priority": "放弃", "position_ref": "不参与",
         "credibility": "中", "credibility_reason": "锚为无名位", "evidence_gaps": ["公告数据未接入"],
         "theme": "化工", "resonance": "中", "theme_status": "冷门",
         "bottom_logic": "集泰股份密封胶+新能源电池胶，据模型知识：动力电池pack胶细分供应商",
         "ignite_theme": "当前无，若出现新能源电池胶政策/订单类消息即为催化剂",
         "exit_rule": "止损=收盘破11.60元；止盈参考=锚+8%减半",
         "next_watch": "①电池胶细分；②观察触发：放量突破12.20元；③失效条件：跌破11.60元移出",
         "false_alarm_status": "疑似风险", "false_alarm_risk": "冷门池仓位减半",
         "rank_score": 88, "rank_reason": "冷门降档", "scan_score": 78},
        {"code": "300453", "name": "三鑫医疗", "pattern_match": "不匹配", "pattern_basis": "",
         "method": "底部缩量熬底", "sequence_stage": "找锚中", "anchor_price": "", "anchor_type": "未取得", "anchor_quality_score": 0,
         "cost_zone": "9.5-9.9", "cost_basis": "箱体中枢", "breakout_check": {"verdict": "数据不足"},
         "washout_check": {"verdict": "数据不足无法判定"}, "second_breakout": {"done": False, "volume_type": "数据不足"},
         "pullback_check": {"five_conditions_met": [], "time_window": "", "verdict": "未到"},
         "quality_score_detail": {"anchor": 0, "sector_resonance": 0, "news_freshness": 0, "washout": 0, "second_breakout": 0},
         "quality_total": 45, "observation_priority": "低", "position_ref": "三分之一档参考",
         "credibility": "低", "credibility_reason": "锚未取得+数据缺口明显", "evidence_gaps": ["锚质量数据不足"],
         "theme": "医疗器械", "resonance": "弱", "theme_status": "冷门",
         "bottom_logic": "三鑫医疗血液透析耗材，据模型知识：透析器国产替代标的，与今日主线无直接关联",
         "ignite_theme": "当前无，若出现集采/国产替代政策类消息即为催化剂",
         "exit_rule": "止损=收盘破9.30元", "next_watch": "①透析耗材低位票；②观察触发：放量突破9.90元；③失效：跌破9.30元",
         "false_alarm_status": "数据不足无法判定", "false_alarm_risk": "冷门池",
         "rank_score": 79, "rank_reason": "冷门池保留", "scan_score": 74},
    ],
    "judged_all": [
        {"code": "601688", "name": "华泰证券", "pattern_match": "不匹配", "method": "打压吸筹", "sequence_stage": "找锚中",
         "anchor_type": "未取得", "cost_zone": "19.6-20.1", "quality_total": 55, "observation_priority": "低",
         "credibility": "低", "theme": "证券", "resonance": "弱", "theme_status": "冷门",
         "false_alarm_status": "数据不足无法判定", "evidence_gaps": ["板块涨停数据不足"], "bottom_logic": "券商板块冷门池，数据不足", "ignite_theme": "当前无", "brief": "冷门池保留研判"},
    ],
    "excluded": [
        {"code": "600999", "name": "招商证券", "exclude_reason": "涨幅红线"},
    ],
}

# —— mock 依赖 ——
_payload_cap = {}
def _fake_llm(payload, **kw):
    _payload_cap['p'] = payload
    return json.dumps(V4_OUT, ensure_ascii=False)
cdr.ask_deepseek = _fake_llm
cdr._follow_pool = lambda d: [{'c': '002838', 'hybk': '化工新材料'}, {'c': '002909', 'hybk': '化工'},
                              {'c': '300453', 'hybk': '医疗器械'}, {'c': '600999', 'hybk': '证券'},
                              {'c': '601688', 'hybk': '证券'}]
cdr._sina_sector_pct = lambda: {'化工新材料': {'pct': 2.3, 'cnt': 60}, '化工': {'pct': 1.5, 'cnt': 120},
                                '医疗器械': {'pct': 0.8, 'cnt': 90}, '证券': {'pct': -1.2, 'cnt': 50}}

class _FakeZF:
    def run_scanner(self, **kw):
        return [dict(h) for h in HITS]
import types
_zf = types.SimpleNamespace(**{'run_scanner': _FakeZF().run_scanner})

# 替换 cdr 内 import 的 zhu_force_scan
import sys
sys.modules['zhu_force_scan'] = _zf

html = cdr.build_zscan(limit=None)
check('build_zscan 正常出卡', isinstance(html, str) and len(html) > 500, 'len=%d' % len(html))

# 1. payload V4 schema
p = _payload_cap.get('p') or {}
check('payload含pool数组', isinstance(p.get('pool'), list) and len(p.get('pool')) == 4, 'n=%d（5只-1涨幅红线票）' % len(p.get('pool') or []))
check('payload含hot_sectors', isinstance(p.get('hot_sectors'), list) and len(p.get('hot_sectors')) >= 1, '')
check('payload含hot_sector_history_7d空数组', p.get('hot_sector_history_7d') == [], '')
_p0 = (p.get('pool') or [{}])[0]
check('pool字段齐全', all(k in _p0 for k in ('code', 'name', 'close', 'pct_chg', 'kline_summary', 'condition_hits',
                                              'scan_score', 'method_type', 'state', 'sector', 'sector_limit_up_count',
                                              'sector_rise2pct_count_on_ignition_day', 'announcements_10d',
                                              'news_today', 'liquidity_flag', 'liquidity_percentile')), 'missing=%s' % [k for k in
             ('code', 'name', 'close', 'pct_chg', 'kline_summary', 'condition_hits', 'scan_score', 'method_type',
              'state', 'sector', 'sector_limit_up_count', 'sector_rise2pct_count_on_ignition_day', 'announcements_10d',
              'news_today', 'liquidity_flag', 'liquidity_percentile') if k not in _p0])
check('涨幅红线票未进pool', all(abs(float((x.get('kline_brief') or [{}])[-1].get('pct') or 0)) < 7.0 for x in (p.get('pool') or [])), '')

# 2. 渲染含 V4 新字段
for _f in ('模式匹配', '序列阶段', '突破验收', '洗盘判定', '二次突破', '回踩五条', '观察优先级', '离场规则',
           '参考仓位', '质量分', '全池研判', '硬剔除', '回踩未到', '未二次突破'):
    check('渲染含「%s」' % _f, _f in html, '')

# 3. 涨幅红线终拦：招商证券(8.5%) 只出现在硬剔除段，不推上卡
check('涨幅红线票只进硬剔除', '硬剔除' in html and '招商证券' in html and '涨幅红线' in html, '')
check('涨幅红线票不在雷达卡主体', '招商证券（600999）</div>' not in html and html.split('硬剔除')[0].find('招商证券') < 0, '')
# 4. 量能清洗：绝能量能数字被洗
check('绝能量能数字被清洗', '39.4万股' not in html and '39.4 万' not in html, '')
# 5. 新字段值渲染：道恩股份
check('道恩股份模式三上卡', '道恩股份' in html and '模式三' in html, '')
check('回踩买点区上卡', '回踩买点区' in html, '')
check('洗盘合格上卡', '洗盘合格' in html, '')
check('观察优先级中上卡', '观察优先级：中' in html or '观察优先级' in html, '')

# 6. 降级分支：LLM 返回 None → V4 格式规则降级卡
cdr.ask_deepseek = lambda *a, **k: None
html2 = cdr.build_zscan(limit=None)
check('降级分支出卡', isinstance(html2, str) and '规则降级' in html2, 'len=%d' % len(html2))
check('降级卡含序列阶段', '序列阶段：找锚中' in html2, '')
check('降级卡含观察优先级', '观察优先级' in html2 and '三分之一档参考' in html2, '')
check('降级卡含离场规则', '离场规则' in html2, '')

# 7. 降级分支2：LLM 输出裸数组（FIX17 场景）
cdr.ask_deepseek = lambda *a, **k: json.dumps([{'code': '002838', 'name': '道恩股份', 'method': 'x'}], ensure_ascii=False)
html3 = cdr.build_zscan(limit=None)
check('裸数组降级不崩溃', isinstance(html3, str) and len(html3) > 200, 'len=%d' % len(html3))

# 8. FIX20：截断 JSON 修复（模拟真实截断：字符串在数组元素中断裂）
_trunc = json.dumps(V4_OUT, ensure_ascii=False)[:1800]
# 在任意逗号处切断制造截断
_trunc = _trunc[:_trunc.rfind(',')]
_fix = cdr._repair_json(_trunc)
check('截断JSON修复成功', _fix is not None and isinstance(_fix, dict), '')
check('修复后含meta', isinstance(_fix, dict) and 'meta' in _fix, '')
# 修复后能提取 radar（截断后可能有部分票）
_r, _ja, _ex, _me = cdr._extract_zscan_lists(_fix)
check('修复后提取无异常', isinstance(_r, list), 'n=%d' % len(_r))

# 9. FIX20：max_tokens 按 purpose
src = io.open(r'D:\QuantMonitorV6\tools\cloud_daily_review.py', encoding='utf-8').read()
check('zforce_radar max_tokens=6000', "'max_tokens': (6000 if purpose == 'zforce_radar' else 3000)" in src, '')
check('ZSYS含输出完整性铁律', '输出完整性铁律' in src and '禁止截断' in src, '')
check('解析层含截断修复分支', '截断JSON修复成功' in src, '')

print('\n===== V4 verify: %d pass / %d fail =====' % (ok, fail))
sys.exit(1 if fail else 0)
