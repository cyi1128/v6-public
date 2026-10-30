# -*- coding: utf-8 -*-
"""今日市场决策页 数据服务（四重共振）。

数据全部复用现有模块，不新增底层引擎：
  - 市场节奏（题材/状态/龙头/连板/轮动）  → market_rhythm_engine.get_rhythm()
  - 广度/情绪分/封板率/趋势               → market_dashboard_service.compute_dashboard()
  - 持仓                                  → data/cache/atr_t_tracking.duckdb 的 holding 表
  - 持仓弱化信号                          → control_screen_service.compute_stock（含全部因子）

另把识别出的「今日主线」写 data/cache/today_main_themes.json，
供控盘选股页「仅看今日主线」开关读取。
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HOLDING_DB = os.path.join(ROOT, 'data', 'cache', 'atr_t_tracking.duckdb')
THEMES_PATH = os.path.join(ROOT, 'data', 'cache', 'today_main_themes.json')
_LU_DB = os.path.join(ROOT, 'data', 'limit_up_reason.db')


# ----------------------------------------------------------------------
# 当日 / 昨日 涨停家数、最高板（与节奏引擎口径一致：主板+创业板，按 code 去重）
# ----------------------------------------------------------------------
def _day_lu_counts(dates):
    """dates = 两个日期 ['20261009','20261008'] → [(lu_count, max_lbc, broken)]"""
    from services.market_rhythm_engine import is_main_board
    out = {}
    c = sqlite3.connect(_LU_DB)
    for d in dates:
        if not d:
            continue
        rows = c.execute(
            'SELECT DISTINCT code, lbc, zbc FROM limit_up_reasons WHERE date=?',
            (d,)).fetchall()
        rows = [r for r in rows if is_main_board(r[0])]
        out[d] = (len(rows),
                  max((r[1] or 1) for r in rows) if rows else 0,
                  sum(1 for r in rows if r[2] and r[2] > 0))
    c.close()
    return out


def _lead_zbc(code, date):
    """龙头当日是否炸过（zbc>0）。"""
    c = sqlite3.connect(_LU_DB)
    r = c.execute(
        'SELECT MAX(zbc) FROM limit_up_reasons WHERE code=? AND date=?',
        (code, date)).fetchone()
    c.close()
    return (r[0] or 0) > 0


# ----------------------------------------------------------------------
# 四大指数（真实行情：腾讯 qt.gtimg.cn，与 utils.http_market_data 同源）
# ----------------------------------------------------------------------
def _index_snapshot():
    """上证/深证/创业板/科创50 实时点位+涨跌幅。失败返回空列表，UI 显示占位。"""
    try:
        from utils.http_market_data import http_get_with_retry
        url = ('https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688')
        text = http_get_with_retry(url, encoding='gbk', timeout=8)
        names = {'sh000001': '上证指数', 'sz399001': '深证成指',
                 'sz399006': '创业板指', 'sh000688': '科创50'}
        out = []
        for line in text.split(';'):
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, val = line.split('=', 1)
            if not key.startswith('v_'):
                continue
            parts = val.strip('"').split('~')
            if len(parts) < 40:
                continue
            sym = key.split('_')[-1]
            try:
                price = float(parts[3] or 0)
                last = float(parts[4] or 0)
                pct = (price - last) / last * 100 if last else 0.0
                out.append({'code': sym, 'name': names.get(sym, sym),
                            'price': round(price, 2), 'pct': round(pct, 2)})
            except ValueError:
                continue
        return out
    except Exception:
        return []


# ----------------------------------------------------------------------
# 四重共振打分
# ----------------------------------------------------------------------
def _grade(score):
    return '强' if score >= 75 else ('中' if score >= 50 else '弱')


def _score_sector(top, breadth):
    """板块卡（满分100）。"""
    s = 0
    reasons = []
    if top['count'] > top['prev_count']:
        s += 30; reasons.append('涨停家数较昨日+%d' % (top['count'] - top['prev_count']))
    if top['state'] in ('⚡持续', '🆕首日启动', '🔥发酵中'):
        s += 25; reasons.append('状态%s' % top['state'])
    if top['avg_pct'] > breadth['avg_pct']:
        s += 25; reasons.append('板块均涨%.1f%%跑赢大盘' % top['avg_pct'])
    # 板块成交额无逐题材数据 → 20 分跳过（口径里写明「有数据则加」）
    if s >= 75:
        concl = '%s%s，涨停家数增加，主线明确' % (top['theme'], top['state'])
    elif s >= 50:
        concl = '有主线但持续性一般'
    else:
        concl = '无持续主线，轮动较快'
    return {'score': s, 'grade': _grade(s), 'concl': concl, 'reasons': reasons}


def _score_dragon(top, date):
    """龙头卡（满分100）。"""
    s = 0
    lead = top['lead']
    lead_lbc = top['lead_lbc'] or 1
    lead_time = top['lead_time'] or '99:99:99'
    # 率先涨停（09:45 前封板）或连板（明显强于板块）
    if lead_time <= '09:45:00' or lead_lbc >= 2:
        s += 40
    if lead_lbc >= 2:
        s += 30
    if not _lead_zbc(top['lead_code'], date):
        s += 30
    s = min(s, 100)
    if s >= 75:
        concl = '龙头%s率先封板（%d板），带动明显' % (lead, lead_lbc)
    elif s >= 50:
        concl = '龙头在位但带动一般'
    else:
        concl = '龙头高位滞涨，带动减弱'
    return {'score': s, 'grade': _grade(s), 'concl': concl,
            'lead': lead, 'lead_code': top['lead_code']}


def _score_capital(top, today_cnt, prev_cnt):
    """资金卡（满分100）。"""
    s = 0
    lu_t, lbc_t, _brk_t = today_cnt
    lu_p, lbc_p, _brk_p = prev_cnt if prev_cnt else (0, 0, 0)
    if lu_t > lu_p:
        s += 30
    # 跟风：最强题材成员（梯队）≥3 家，不是只有龙头独舞
    if len(top['ladder']) >= 3:
        s += 35
    if lbc_t >= lbc_p:
        s += 35
    if s >= 75:
        concl = '资金从龙头向跟风扩散中'
    elif s >= 50:
        concl = '资金扩散一般'
    else:
        concl = '资金集中在龙头，扩散不足'
    return {'score': s, 'grade': _grade(s), 'concl': concl}


def _score_sentiment(sentiment, lu_stat):
    """情绪卡：基础分=现有情绪分，再按封板率/炸板/连板高度调整。"""
    s = sentiment
    if lu_stat.get('fengban_rate', 0) >= 70 and lu_stat.get('broken', 0) <= 20:
        s += 10
    if lu_stat.get('broken', 0) >= 30:
        s -= 15
    s = max(0, min(100, s))
    if s >= 75:
        concl = '情绪稳定，封板率尚可'
    elif s >= 50:
        concl = '情绪中性，分歧存在'
    else:
        concl = '情绪退潮，炸板增多'
    return {'score': s, 'grade': _grade(s), 'concl': concl}


# ----------------------------------------------------------------------
# 市场状态（顶部状态条，四级）
# ----------------------------------------------------------------------
def _market_state(sentiment, today_cnt, prev_cnt):
    lu_t, lbc_t, _b = today_cnt
    lu_p, lbc_p, _bp = prev_cnt if prev_cnt else (0, 0, 0)
    lu_up = lu_t > lu_p
    lbc_up = lbc_t > lbc_p
    if sentiment >= 75 and lu_up and lbc_up:
        return '主升浪', '重仓'
    if 55 <= sentiment <= 74:
        return '震荡上行', '中等'
    if 35 <= sentiment <= 54:
        return '震荡分化', '轻仓'
    return '退潮期', '空仓/极轻仓'


# ----------------------------------------------------------------------
# 持仓
# ----------------------------------------------------------------------
def load_holdings():
    try:
        import duckdb
        con = duckdb.connect(HOLDING_DB, read_only=True)
        rows = con.execute(
            'SELECT code, name, cost, qty, buy_time FROM holding ORDER BY code'
        ).fetchall()
        con.close()
        return [{'code': r[0], 'name': r[1], 'cost': r[2],
                 'qty': r[3], 'buy_time': str(r[4] or '')} for r in rows]
    except Exception:
        return []


def _holding_warnings(holdings, bars_map, names):
    """沿用现有弱化规则，按优先级给动作。
    持仓预警只看「真有成本」的持仓；cost=None 的是分时做T自选池，不在这里预警。"""
    holdings = [h for h in holdings if h.get('cost')]
    from services.control_screen_service import compute_stock
    import services.band_pattern_engine as engine
    from strategy.base import TechnicalIndicators
    ti = TechnicalIndicators()
    out = []
    for h in holdings:
        code = h['code']
        bars = bars_map.get(code)
        rec = compute_stock(code, bars, name=h.get('name') or names.get(code, ''),
                            ti=ti, engine=engine) if bars else None
        item = dict(h)
        item['price'] = rec['price'] if rec else 0
        item['stage'] = rec['stage'] if rec else ''
        item['pos'] = rec['pos'] if rec else 0
        item['pct'] = rec['pct'] if rec else 0
        # 优先级：出货(分+位置) > 破位未收 > 天量 > 高位放量滞涨
        if rec and rec['stage'] == 'distribute' and rec['pos'] >= 0.65:
            item['action'] = '主动减仓'; item['risk'] = '出货风险'
        elif rec and rec['brk_type'] == '破位未收':
            item['action'] = '减仓观察'; item['risk'] = '放量破位未收回'
        elif rec and '天量' in rec['vreg_tags']:
            item['action'] = '减仓观察'; item['risk'] = '天量'
        elif rec and '高位放量滞涨' in rec['dist_type']:
            item['action'] = '减仓观察'; item['risk'] = '高位放量滞涨'
        else:
            item['action'] = '继续持有'; item['risk'] = ''
        out.append(item)
    return out


# ----------------------------------------------------------------------
# 今日主线（top 1~2 题材，含同簇题材名）
# ----------------------------------------------------------------------
def _main_themes(boards):
    real = [b for b in boards if not b['is_attribute']]
    out = []
    for b in real[:2]:
        out.append({'theme': b['theme'], 'mainline': b.get('mainline') or '',
                    'cluster': b.get('cluster', [])[:3]})
    return out


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------
def compute_decision():
    from services.market_rhythm_engine import get_rhythm
    from services.market_dashboard_service import compute_dashboard
    rhythm = get_rhythm()
    dash = compute_dashboard()
    breadth = dash['breadth']
    lu_stat = dash['limit_up'] or {}
    sentiment = dash['sentiment']
    boards = rhythm.get('boards', [])

    # 今日 vs 昨日
    today_d = rhythm['date']
    prev_d = rhythm.get('prev_date')
    counts = _day_lu_counts([d for d in (today_d, prev_d) if d])
    today_cnt = counts.get(today_d, (0, 0, 0))
    prev_cnt = counts.get(prev_d) if prev_d else None

    top = boards[0] if boards else None
    themes = _main_themes(boards)
    cards = None
    total = 0
    if top:
        c1 = _score_sector(top, breadth)
        c2 = _score_dragon(top, today_d)
        c3 = _score_capital(top, today_cnt, prev_cnt)
        c4 = _score_sentiment(sentiment, lu_stat)
        cards = {'sector': c1, 'dragon': c2, 'capital': c3, 'sentiment': c4}
        total = round((c1['score'] + c2['score'] + c3['score'] + c4['score']) / 4, 1)

    resonance = '强' if total >= 75 else ('中' if total >= 55 else '弱')
    state, max_pos = _market_state(sentiment, today_cnt, prev_cnt)

    # 情绪一票否决：情绪分<=35 或退潮期，共振等级最高只能是「中」，不可进攻
    veto = (sentiment <= 35 or state == '退潮期')
    if veto and resonance == '强':
        resonance = '中'

    # 方向结论（退潮期安全优先：即使主线题材卡强，也不新开仓）
    main_names = [t['theme'] for t in themes]
    allow_open = (not veto and resonance == '强' and bool(main_names))
    if veto:
        concl = '市场退潮、情绪分仅%d，即使%s走强也不新开仓，建议观望或仅做T' % (
            sentiment, ('、'.join(main_names) or '题材'))
    elif total >= 75 and main_names:
        concl = '今日主线明确，建议重点关注：%s，可结合控盘选股做增强' % '、'.join(main_names)
    elif total >= 55:
        concl = '有主线但共振不足，建议轻仓参与最强方向，严格止盈'
    else:
        concl = '今日无明确主线或共振较弱，建议观望或仅做T，不新开仓'

    # 持仓预警
    from services.control_screen_service import load_all_bars, code_name_map
    bars_map = load_all_bars()
    holdings = _holding_warnings(load_holdings(), bars_map, code_name_map())

    result = {
        'state': state, 'max_pos': max_pos, 'sentiment': sentiment,
        'cards': cards, 'total': total, 'resonance': resonance,
        'veto': veto, 'allow_open': allow_open,
        'concl': concl, 'themes': themes,
        'rotation': rhythm.get('rotation', {}).get('summary', ''),
        'holdings': holdings,
        'data_date': dash.get('data_date', ''),
        'lu_today': today_cnt[0], 'lu_prev': prev_cnt[0] if prev_cnt else 0,
        'lbc_today': today_cnt[1], 'lbc_prev': prev_cnt[1] if prev_cnt else 0,
        # 真实广度/涨停/概念/指数（全部来自 compute_dashboard 与腾讯实时行情）
        'breadth': breadth,
        'lu_stat': lu_stat,
        'hot_themes': dash.get('themes', []),
        'indices': _index_snapshot(),
    }
    _save_themes(themes)
    return result


def _save_themes(themes):
    try:
        os.makedirs(os.path.dirname(THEMES_PATH), exist_ok=True)
        with open(THEMES_PATH, 'w', encoding='utf-8') as f:
            json.dump(themes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('[decision] 主线保存失败: %s' % e)


def load_main_themes():
    """控盘选股页「仅看今日主线」读取。"""
    try:
        with open(THEMES_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _theme_keys(themes):
    """主线匹配关键词：主线名 + 同簇题材（含归并主线名）。"""
    keys = set()
    for t in themes:
        keys.add(t['theme'])
        if t.get('mainline') and len(t['mainline']) >= 2:
            keys.add(t['mainline'])
        keys.update(t.get('cluster', []))
    return [k for k in keys if k and len(k) >= 2 and k not in ('北京国资',)]


def filter_rows_by_themes(rows, themes=None):
    """控盘选股「仅看今日主线」：用行内 theme（最近一次涨停原因，形如
    「创新药+抗生素+减肥药」）判断是否属于主线；命中主线名/同簇题材即保留。"""
    themes = themes if themes is not None else load_main_themes()
    keys = _theme_keys(themes)
    out = []
    for r in rows:
        th = str(r.get('theme') or '')
        if any(k in th for k in keys):
            out.append(r)
    return out


def filter_codes_by_themes(codes, themes=None):
    """兼容入口：按代码查 limit_up_reasons 最新原因后判断是否主线。"""
    themes = themes if themes is not None else load_main_themes()
    keys = _theme_keys(themes)
    from data.limit_up_reason_db import get_last_limit_up_reason
    out = []
    for code in codes:
        r = get_last_limit_up_reason(str(code))
        th = str(r[0] or '') if r else ''
        if any(k in th for k in keys):
            out.append(code)
    return out


if __name__ == '__main__':
    r = compute_decision()
    print('状态:%s 建议仓位:%s 情绪分:%d' % (r['state'], r['max_pos'], r['sentiment']))
    print('涨停 今/昨:', r['lu_today'], r['lu_prev'], '｜连板 今/昨:', r['lbc_today'], r['lbc_prev'])
    if r['cards']:
        for k, v in r['cards'].items():
            print('  [%s] %d分(%s) %s' % (k, v['score'], v['grade'], v['concl']))
    print('共振总分:', r['total'], r['resonance'])
    print('主线:', [t['theme'] for t in r['themes']])
    print('结论:', r['concl'])
    print('轮动:', r['rotation'])
    for h in r['holdings']:
        print('持仓 %s %s 价%s 成本%s 阶段%s → %s %s' % (
            h['code'], h['name'], h['price'], h['cost'], h['stage'], h['action'], h['risk']))
