# -*- coding: utf-8 -*-
"""共振因子·规则层引擎（resonance_engine）
定位：不选票，只回答「现在这个市场/这个板块，敢下多大注」。
输出三档：A·真共振(≥70) 允许轻仓试探话术/1成；B·假共振(45-69) 统一口风「看不动手」；C·无共振(<45) 强制「空仓等」。
五重计分（纯规则，不依赖大模型）：
  R1 资金重(25)：板块成交额放大≥1.3倍 且 放大幅度>涨幅
  R2 龙头重(25)：龙头非一字封板+封单稳定+位置相对低位
  R3 结构重(20)：涨停家数↑且炸板率↓且低位票有承接
  R4 情绪重(15)：情绪周期处于冰点修复或升温（非拥挤非退潮）
  R5 时间重(15)：题材发酵≤3天（第4天起每天-3，第8天=0）
一票否决项（命中直接 C）：①量价背离(价升量缩) ②龙头封板松动 ③跟风批量掉队(板块涨停数↓>50%) ④题材已传第8天以上。
账本：data/resonance_ledger.json —— 每天记录判定 + 次日对账（验证昨日判定，共振衰减预警）。
纯标准库。"""
import io
import json
import os

LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'resonance_ledger.json')

# ---------- 规则层计分 ----------

def _safe(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def compute_resonance(idx=None, d=None, ctx=None):
    """五重共振计分。ctx 提供：sector(最强板块名)/stocks(板块个股)/lu/zb/mscore/mlabel/memory/today/seen_count。
    返回 dict：{'grade','score','factors':{R1..R5:{'s':分数,'tag':标签}},'veto':[命中的一票否决],'sector','date','detail'}。
    任何输入缺失按中性处理，不抛异常。"""
    ctx = ctx or {}
    d = d or {}
    factors = {}
    veto = []
    score = 0

    # ---- R1 资金重(25)：板块成交额放大且资金领先价 ----
    stocks = ctx.get('stocks') or []
    lbs = [_safe(s.get('lb')) for s in stocks if _safe(s.get('lb')) > 0]
    pcts = [_safe(s.get('pct')) for s in stocks]
    avg_lb = sum(lbs) / len(lbs) if lbs else 0.0
    avg_pct = sum(pcts) / len(pcts) if pcts else 0.0
    r1 = 0
    if avg_lb >= 1.3:
        # 资金领先近似：量比放大幅度 明显高于 涨幅（量在价先）
        lead = avg_lb - max(0.0, avg_pct) * 0.3
        if lead >= 1.0:
            r1 = 25
        elif lead >= 0.5:
            r1 = 16
        else:
            r1 = 8
    else:
        r1 = 4 if avg_lb >= 0.9 else 0
    factors['R1'] = {'s': r1, 'tag': '资金' + ('强' if r1 >= 16 else ('中' if r1 >= 8 else '弱'))}

    # ---- R2 龙头重(25)：龙头非一字封板+封单稳定+位置低位 ----
    r2 = 0
    if stocks:
        leader = max(stocks, key=lambda s: _safe(s.get('pct')))
        lpct = _safe(leader.get('pct'))
        llb = _safe(leader.get('lb'))
        # 非一字封板：未封死（涨幅未到板）或涨停但量比不极端（有分歧承接）
        non_yizi = lpct < 18.0 if any(str(s.get('code', '')).startswith(('30', '68')) for s in stocks) else lpct < 8.8
        # 位置低位：龙头涨幅不高于板块均值过多（刚启动）且量比健康
        low_pos = lpct <= avg_pct * 1.8 + 3.0
        if non_yizi and llb >= 1.3 and low_pos:
            r2 = 25
        elif non_yizi and llb >= 1.0:
            r2 = 16
        elif non_yizi:
            r2 = 8
        else:
            r2 = 3  # 一字/接近一字：追高区，封板但位置高
    factors['R2'] = {'s': r2, 'tag': '龙头' + ('稳' if r2 >= 16 else ('分' if r2 >= 8 else '松'))}

    # ---- R3 结构重(20)：涨停↑ 且 炸板↓ 且 低位承接 ----
    r3 = 0
    lu = int(ctx.get('lu') or d.get('lu') or 0)
    zb = int(ctx.get('zb') or d.get('zb') or 0)
    memory = ctx.get('memory') or {}
    days = sorted(memory.keys(), reverse=True)
    prev = memory.get(days[1]) if len(days) > 1 else {}
    prev_lu = int(prev.get('lu') or 0)
    prev_zb = int(prev.get('zb') or 0)
    if lu > prev_lu:
        r3 += 10
    elif lu == prev_lu:
        r3 += 5
    # 炸板率下降
    zbr = zb / (lu + zb) if (lu + zb) else 0.5
    prev_zbr = prev_zb / (prev_lu + prev_zb) if (prev_lu + prev_zb) else 0.5
    if zbr < prev_zbr:
        r3 += 7
    elif zbr <= 0.25:
        r3 += 4
    # 低位承接：板块内涨停之外有放量跟风（stocks 数≥2 且非全涨停）
    n_lu_stocks = sum(1 for s in stocks if _safe(s.get('pct')) >= 9.0)
    if stocks and n_lu_stocks < len(stocks):
        r3 += 3
    factors['R3'] = {'s': r3, 'tag': '结构' + ('健' if r3 >= 13 else ('平' if r3 >= 7 else '弱'))}

    # ---- R4 情绪重(15)：冰点修复/升温 ----
    r4 = 0
    mscore = _safe(ctx.get('mscore') or 50, 50)
    if mscore >= 55:
        r4 = 15
    elif mscore >= 45:
        r4 = 8
    else:
        r4 = 0
    factors['R4'] = {'s': r4, 'tag': '情绪' + ('暖' if r4 >= 15 else ('平' if r4 >= 8 else '冷'))}

    # ---- R5 时间重(15)：题材发酵≤3天 ----
    r5 = 0
    seen = int(ctx.get('seen_count') or 0)
    if seen <= 0:
        seen = 1
    if seen <= 3:
        r5 = 15
    else:
        r5 = max(0, 15 - (seen - 3) * 3)  # 第4天12分，第8天=0
    factors['R5'] = {'s': r5, 'tag': '时' + str(seen) + '天' + ('新' if r5 >= 12 else '老')}

    # ---- 一票否决（命中直接 C）----
    # ① 量价背离：板块价升（均涨>1.5%）但量缩（均量比<1.0）
    if avg_pct >= 1.5 and avg_lb < 1.0:
        veto.append('量价背离(价升量缩)')
    # ② 龙头封板松动：龙头涨停但量比过高(≥5，天量) 或 板块炸板占比高
    if stocks:
        leader = max(stocks, key=lambda s: _safe(s.get('pct')))
        if _safe(leader.get('pct')) >= 9.0 and _safe(leader.get('lb')) >= 5.0:
            veto.append('龙头封板松动(天量)')
    if zb > 0 and (lu + zb) > 0 and zb / (lu + zb) >= 0.45:
        veto.append('炸板率过高(>45%)')
    # ③ 跟风批量掉队：涨停数较昨日降>50%
    if prev_lu > 0 and lu > 0 and (prev_lu - lu) / prev_lu > 0.5:
        veto.append('跟风批量掉队(涨停数降>50%)')
    # ④ 题材已传第8天以上
    if seen >= 8:
        veto.append('题材已传8天以上')

    if veto:
        score = 0
        grade = 'C'
    else:
        score = r1 + r2 + r3 + r4 + r5
        grade = 'A' if score >= 70 else ('B' if score >= 45 else 'C')

    return {
        'grade': grade, 'score': score,
        'factors': factors, 'veto': veto,
        'sector': ctx.get('sector') or '', 'date': ctx.get('today') or '',
        'detail': {
            'avg_lb': round(avg_lb, 2), 'avg_pct': round(avg_pct, 2),
            'lu': lu, 'zb': zb, 'prev_lu': prev_lu, 'prev_zb': prev_zb,
            'mscore': mscore, 'seen_count': seen,
        },
    }


def grade_of(score, veto=None):
    """档位判定：≥70 A；45-69 B；<45 C。veto 命中直接 C。"""
    if veto:
        return 'C'
    return 'A' if score >= 70 else ('B' if score >= 45 else 'C')


def resonance_banner(res):
    """卡片头部行：🎚共振档位:B(58分)·资金强/结构弱（挑最强/最弱因子标签）。"""
    if not res:
        return ''
    grade = res.get('grade', 'C')
    score = res.get('score', 0)
    f = res.get('factors') or {}
    tags = []
    for k in ('R1', 'R2', 'R3', 'R4', 'R5'):
        _t = (f.get(k) or {}).get('tag', '')
        if _t:
            tags.append(_t)
    tags_str = '·'.join(tags) if tags else ''
    color = {'A': '#51cf66', 'B': '#ffd43b', 'C': '#ff6b6b'}.get(grade, '#9aa4b8')
    veto_txt = (' <b style="color:#ff6b6b;">[一票否决:' + '/'.join(res.get('veto') or []) + ']</b>') if res.get('veto') else ''
    return (f'<div style="margin-bottom:8px;padding:7px 10px;background:#1a2029;border-left:4px solid {color};'
            f'border-radius:6px;color:#e9ecef;font-size:12px;">🎚 共振档位:<b style="color:{color};">{grade}</b>'
            f'({score}分)·{tags_str}{veto_txt}</div>')


# ---------- 共振账本 ----------

def load_ledger():
    """读账本；空/损坏返回 {'records': {}}。"""
    try:
        with io.open(LEDGER_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError):
        return {'records': {}}


def save_ledger(ledger):
    """写账本。"""
    try:
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        with io.open(LEDGER_PATH, 'w', encoding='utf-8') as f:
            json.dump(ledger, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def record_today(res, verdict=None):
    """记录今日判定入账本（模型层 verdict 可空）。返回 True/False。"""
    if not res:
        return False
    ledger = load_ledger()
    rec = dict(res)
    if verdict:
        rec['verdict'] = verdict
    rec['reconciled'] = False
    date = rec.get('date') or ''
    if not date:
        return False
    ledger.setdefault('records', {})[date] = rec
    return save_ledger(ledger)


def reconcile_today(ledger=None, today=None, cur=None):
    """对账：验证昨日判定——昨日 X 档今日资金重掉档 → 衰减预警。
    返回 (account_txt, alert_txt)。"""
    ledger = ledger or load_ledger()
    records = ledger.get('records') or {}
    days = sorted(records.keys())
    if len(days) < 2:
        return '', ''
    y = days[-2]          # 昨日
    prev = records[y]
    acc = (f'昨日判{prev.get("grade", "?")}·{prev.get("score", 0)}分 '
           f'({prev.get("sector") or "无板块"})')
    if cur:
        cur_grade = cur.get('grade', '?')
        cur_score = cur.get('score', 0)
        acc += f' → 今日{cur_grade}·{cur_score}分'
        if cur_grade == 'C' and prev.get('grade') in ('A', 'B'):
            acc += ' ⚠️ 共振衰减预警：昨日' + prev.get('grade', '') + '档今日降C，先减仓'
            records[y]['reconciled'] = True
            records[days[-1]] = records.get(days[-1]) or {}
            save_ledger(ledger)
            return acc, '⚠️ 共振衰减预警：昨日' + prev.get('grade', '') + '档今日降C，先减仓'
        else:
            acc += ' → 判定延续，无衰减信号'
    return acc, ''
