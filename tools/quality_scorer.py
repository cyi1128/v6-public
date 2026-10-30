# -*- coding: utf-8 -*-
"""突破回踩·主力成本锚 第2步：质量评分与确认模块。
纯标准库自包含。输入 = 第1步扫描器单票 dict，输出 = 5 维分数 + 总分 + 仓位映射 + action。

评分表（对齐用户两轮契约）：
  ① 锚质量 25    关键位(前高>箱体顶>套牢区>无名) + 点火放量匹配 + 点火→突破间隔
  ② 板块共振 25  sector_count：>=8 25 / >=5 20 / >=3 14 / >=1 8 / 0 2
  ③ 利好新鲜度 20  点火前10天公告：实质利好密集18-20 / 有实质利好14 / 纯资金概念5 / 负面5 / 中性8
  ④ 洗盘质量 15  回踩6 + 洗盘次数(<=2干净) + 距突破天数时机 + 洗盘缩量<0.7倍
  ⑤ 二次突破量型 15  second_break_vol_ratio：1.0-1.5温和放量15 / <1.0缩量10 / 1.5-2.0偏猛8 / >2.0巨量5

硬闸门（来自确认模块契约）：
  - hard_filter_passed = False → score=0, action=放弃
  - 回踩触发时 retest_count > 2 → 放弃；days_since_break > 10 且 retest 未触发 → 放弃
  - 仓位映射（本轮）：>=80 重仓(30-50%) / 65-79 中仓(15-30%) / 50-64 轻仓(5-15%) / <50 观察放弃
  - action 映射：>=80 执行 / 65-79 降仓 / 50-64 轻仓试 / <50 放弃
"""
import json
from typing import Dict, Any, List, Optional, Tuple

# ---------------- 各维度满分 ----------------
W_ANCHOR, W_SECTOR, W_NEWS, W_WASH, W_VOL = 25, 25, 20, 15, 15


def _g(d: Dict, key: str, default=None):
    return d.get(key, default)


def _to_f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def score_anchor_quality(item: Dict) -> Tuple[int, str]:
    """① 锚质量 25：关键位类型 + 锚价有效 + 点火放量匹配 + 点火→突破间隔"""
    anchor_type = str(_g(item, 'anchor_type', '') or '')
    anchor_price = _g(item, 'anchor_price')
    ig_vol = _to_f(_g(item, 'ignition_vol_ratio'))
    ig_date, br_date = str(_g(item, 'ignition_date', '') or ''), str(_g(item, 'break_date', '') or '')

    score, rs = 0, []
    type_score = {'前高': 12, '箱体顶': 10, '套牢区': 7, '无名大阳': 4}.get(anchor_type, 3)
    score += type_score
    rs.append(f"锚类型「{anchor_type or '未知'}」+{type_score}")

    if _to_f(anchor_price) and _to_f(anchor_price) > 0:
        score += 5
        rs.append('锚价有效 +5')
    else:
        rs.append('锚价缺失 +0')

    if ig_vol is not None:
        if ig_vol >= 1.5:
            score += 5; rs.append(f"点火放量{ig_vol:.2f}倍达标 +5")
        elif ig_vol >= 1.2:
            score += 3; rs.append(f"点火放量{ig_vol:.2f}倍尚可 +3")
        else:
            score += 1; rs.append(f"点火放量{ig_vol:.2f}倍不足 +1")
    else:
        score += 1; rs.append('点火量比缺失 +1')

    if ig_date and br_date and len(ig_date) >= 10 and len(br_date) >= 10:
        try:
            from datetime import datetime
            d1 = datetime.strptime(ig_date[:10], '%Y-%m-%d')
            d2 = datetime.strptime(br_date[:10], '%Y-%m-%d')
            delta = (d2 - d1).days
            if 1 <= delta <= 3:
                score += 5; rs.append(f"点火→突破{delta}天干净 +5")
            elif delta <= 5:
                score += 3; rs.append(f"点火→突破{delta}天良好 +3")
            else:
                score += 1; rs.append(f"点火→突破{delta}天偏长 +1")
        except Exception:
            score += 2; rs.append('日期解析失败基础 +2')
    else:
        score += 2; rs.append('日期缺失基础 +2')

    return min(W_ANCHOR, score), '；'.join(rs)


def score_sector_resonance(item: Dict) -> Tuple[int, str]:
    """② 板块共振 25：sector_count 分档"""
    try:
        cnt = int(_g(item, 'sector_count', 0) or 0)
    except (TypeError, ValueError):
        cnt = 0
    if cnt >= 8:
        return W_SECTOR, f"板块共振极强({cnt}只) +25"
    if cnt >= 5:
        return 20, f"板块共振强({cnt}只) +20"
    if cnt >= 3:
        return 14, f"板块共振中等({cnt}只) +14"
    if cnt >= 1:
        return 8, f"板块共振弱({cnt}只) +8"
    return 2, '板块共振缺失或0 +2'


def score_news_freshness(item: Dict) -> Tuple[int, str]:
    """③ 利好新鲜度 20：点火前10天公告关键词启发 + 纯资金概念识别"""
    news = str(_g(item, 'news_summary', '') or '').strip()
    if not news or news in ('无', '无相关公告', '无新闻', 'None'):
        return 4, '无有效新闻/公告 +4'

    pos_kw = ['中标', '合同', '业绩预增', '扭亏', '回购', '增持', '订单', '合作', '获批', '突破', '投产', '签署']
    neg_kw = ['减持', '亏损', '风险提示', '立案', '处罚', '下滑', '预亏', '问询']
    pure_kw = ['涨停', '反弹', '走高', '异动', '概念', '触及', '大涨']

    pos = sum(1 for k in pos_kw if k in news)
    neg = sum(1 for k in neg_kw if k in news)
    pure = sum(1 for k in pure_kw if k in news)

    if pos >= 2 and neg == 0:
        score, reason = 18, f"实质利好密集({pos}处) +18"
    elif pos >= 1 and neg == 0:
        score, reason = 14, f"有实质利好({pos}处) +14"
    elif neg > 0:
        score, reason = 5, f"存在负面信息 +5"
    elif pos == 0 and pure >= 2:
        score, reason = 5, '纯资金/概念行情，无实质消息 +5'
    elif pos > neg:
        score, reason = 10, '利好偏多 +10'
    else:
        score, reason = 8, '新闻中性 +8'

    if len(news) < 20:
        score = max(4, score - 3)
        reason += '；摘要过短-3'
    return min(W_NEWS, score), reason


def score_wash_quality(item: Dict) -> Tuple[int, str]:
    """④ 洗盘质量 15：回踩确认 + 洗盘次数干净度 + 距突破天数时机 + 洗盘缩量"""
    wash_dates = _g(item, 'wash_dates') or []
    retest_date = _g(item, 'retest_date')
    days = _g(item, 'days_since_break')
    wash_vol = _to_f(_g(item, 'wash_vol_ratio'))

    score, rs = 0, []
    if retest_date and str(retest_date) not in ('', '未触发', 'None', 'null', 'NoneType'):
        score += 6; rs.append('已触发回踩 +6')
    else:
        score += 2; rs.append('尚未回踩（观察） +2')

    n_wash = len(wash_dates) if isinstance(wash_dates, list) else 0
    if n_wash == 0:
        score += 2; rs.append('无明确洗盘段 +2')
    elif n_wash <= 2:
        score += 5; rs.append(f"洗盘{n_wash}次干净 +5")
    else:
        score += 1; rs.append(f"洗盘{n_wash}次偏多 +1")

    try:
        d = int(days) if days is not None else 99
        if 2 <= d <= 10:
            score += 4; rs.append(f"距突破{d}天时机优秀 +4")
        elif d <= 20:
            score += 2; rs.append(f"距突破{d}天可接受 +2")
        else:
            rs.append(f"距突破{d}天偏久 +0")
    except Exception:
        score += 1; rs.append('天数解析失败 +1')

    if wash_vol is not None and wash_vol < 0.7:
        score += 3; rs.append(f"洗盘缩量{wash_vol:.2f}倍达标 +3")
    elif wash_vol is not None:
        rs.append(f"洗盘量比{wash_vol:.2f}倍未达0.7 +0")

    return min(W_WASH, score), '；'.join(rs)


def score_second_break(item: Dict) -> Tuple[int, str]:
    """⑤ 二次突破量型 15：second_break_vol_ratio 数值档位，缺失时退回 kline_desc 关键词"""
    v = _to_f(_g(item, 'second_break_vol_ratio'))
    if v is not None:
        if 1.0 <= v <= 1.5:
            return W_VOL, f"二次突破温和放量{v:.2f}倍 +15"
        if v < 1.0:
            return 10, f"二次突破缩量{v:.2f}倍 +10"
        if v > 2.0:
            return 5, f"二次突破巨量{v:.2f}倍 +5"
        return 8, f"二次突破偏猛{v:.2f}倍 +8"

    desc = str(_g(item, 'kline_desc', '') or '')
    score, rs = 8, ['通过硬过滤基础 +8']
    if '放量' in desc:
        score += 5; rs.append('二次突破放量特征 +5')
    if '缩量' in desc and '回踩' in desc:
        score += 2; rs.append('回踩缩量配合 +2')
    return min(W_VOL, score), '；'.join(rs)


def map_position(total: int) -> str:
    if total >= 80:
        return '重仓（建议30-50%）'
    if total >= 65:
        return '中仓（建议15-30%）'
    if total >= 50:
        return '轻仓（建议5-15%）'
    return '观察/放弃'


def map_action(total: int) -> str:
    if total >= 80:
        return '执行'
    if total >= 65:
        return '降仓'
    if total >= 50:
        return '轻仓试'
    return '放弃'


def check_hard_gates(item: Dict) -> Optional[str]:
    """确认模块硬闸门：返回否决原因或 None（通过）。"""
    if _g(item, 'hard_filter_passed') is False:
        return 'hard_filter未通过'
    retest_date = _g(item, 'retest_date')
    if retest_date and str(retest_date) not in ('', '未触发', 'None', 'null'):
        try:
            if int(_g(item, 'retest_count', 0) or 0) > 2:
                return '回踩次数>2'
        except (TypeError, ValueError):
            pass
    try:
        days = int(_g(item, 'days_since_break', 99) or 99)
        if days > 10 and not (retest_date and str(retest_date) not in ('', '未触发', 'None', 'null')):
            return f'突破{days}天未回踩'
    except (TypeError, ValueError):
        pass
    return None


def score_one(item: Dict[str, Any]) -> Dict[str, Any]:
    """单票完整评分。返回带分数的新 dict（保留原字段）。"""
    veto = check_hard_gates(item)
    if veto:
        result = dict(item)
        result.update({
            'score_anchor': 0, 'score_sector': 0, 'score_news': 0,
            'score_wash': 0, 'score_volume': 0, 'score_total': 0,
            'position_suggest': '观察/放弃', 'action': '放弃',
            'veto_reason': veto,
            'score_detail': {'否决': veto},
        })
        return result

    a, ar = score_anchor_quality(item)
    s, sr = score_sector_resonance(item)
    n, nr = score_news_freshness(item)
    w, wr = score_wash_quality(item)
    v, vr = score_second_break(item)
    total = a + s + n + w + v

    result = dict(item)
    result.update({
        'score_anchor': a, 'score_sector': s, 'score_news': n,
        'score_wash': w, 'score_volume': v, 'score_total': total,
        'position_suggest': map_position(total),
        'action': map_action(total),
        'score_detail': {
            '锚质量': f"{a}/{W_ANCHOR}（{ar}）",
            '板块共振': f"{s}/{W_SECTOR}（{sr}）",
            '利好新鲜度': f"{n}/{W_NEWS}（{nr}）",
            '洗盘质量': f"{w}/{W_WASH}（{wr}）",
            '二次突破量型': f"{v}/{W_VOL}（{vr}）",
        },
    })
    return result


def score_batch(candidates: List[Dict]) -> List[Dict]:
    scored = [score_one(c) for c in candidates]
    scored.sort(key=lambda x: x.get('score_total', 0), reverse=True)
    return scored


# ---------------- LLM 精细确认提示词（第2步第2阶段，LLM 用） ----------------
LLM_SCORE_PROMPT = """你是「突破回踩·主力成本锚」策略的质量评分与确认模块，只做两件事：
1. 按固定评分表给候选票打分（满分100）
2. 在回踩买点触发时给出最终执行建议（执行/降仓/放弃）

你禁止：
- 自己计算量能倍数、涨跌幅、是否站上锚（这些已由上游代码算完）
- 修改止损价、目标仓位、拉黑天数
- 输出任何与评分表无关的建议或情绪化语言
- 对未通过硬过滤的票进行评分

评分表（必须严格遵守）：
①锚的质量 25分
  - 关键位（前高/箱体顶/套牢区上沿）=25
  - 无名价位大阳=10
②板块共振 25分
  - 点火日同板块≥3只涨≥2%=25
  - 2只=15
  - 独苗=5
③利好新鲜度 20分
  - 点火前3天内有新公告/政策/业绩=20
  - 3-10天内旧消息=10
  - 无消息纯资金=5
④洗盘质量 15分
  - 阴线缩量（<突破日0.7倍）+ 红肥绿瘦 + 不破点火开盘价=15
  - 基本缩量=8
  - 量能含糊或放量阴线=0
⑤二次突破量型 15分
  - 温和放量1-1.5倍=15
  - 缩量=10
  - 巨量>2倍=5

仓位映射（你只输出分数与action，仓位由下游代码映射）：
≥80 → 标准仓（执行）
60-79 → 半标准仓（降仓）
40-59 → 1/3仓试错（轻仓试）
<40 → 放弃

输入格式（上游会给你JSON）：
{{
  "code": "股票代码",
  "name": "名称",
  "anchor_price": 锚位价格,
  "anchor_type": "前高/箱体顶/套牢区/无名大阳",
  "ignition_date": "点火日",
  "ignition_open": 点火日开盘价,
  "ignition_vol_ratio": 点火日量/前5日均量,
  "break_date": "突破日",
  "break_vol_ratio": 突破日量/均量,
  "wash_dates": ["洗盘日..."],
  "wash_vol_ratio": 洗盘日量/突破日量,
  "second_break_date": "二次突破日",
  "second_break_vol_ratio": 二次突破量/突破量,
  "retest_date": "回踩日（如有）",
  "retest_count": 回踩次数,
  "sector_count": 同板块涨≥2%家数,
  "news_summary": "点火前公告摘要或无",
  "kline_desc": "关键K线文字描述",
  "hard_filter_passed": true/false
}}

输出必须严格JSON，无任何额外文字：
{{
  "code": "股票代码",
  "score": 总分整数,
  "detail": {{"anchor": 分数, "sector": 分数, "news": 分数, "wash": 分数, "second_break": 分数}},
  "action": "执行" | "降仓" | "轻仓试" | "放弃",
  "reason": "不超过30字的硬理由"
}}

如果 hard_filter_passed = false，直接输出 score=0, action="放弃"。
回踩买点触发时，额外检查：回踩次数≤2、收盘站上5日线、时间窗≤10天。不满足任何一条直接 action="放弃"。

候选数据：
{candidate_json}
"""


def build_llm_prompt(item: Dict) -> str:
    return LLM_SCORE_PROMPT.format(candidate_json=json.dumps(item, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print('用法: python quality_scorer.py <candidates.json>')
        sys.exit(1)
    cands = json.load(open(path, encoding='utf-8'))
    for c in score_batch(cands):
        print(f"{c['code']} {c.get('name','')} 总分{c['score_total']} action={c['action']} 仓位={c['position_suggest']}")
