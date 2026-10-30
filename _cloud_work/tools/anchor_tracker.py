# -*- coding: utf-8 -*-
"""突破回踩·主力成本锚 实盘跟踪与复盘模块（第4步，纯标准库，无第三方依赖）。

功能：
- record_candidates(scored_list, trade_date)  把当天 ≥50 分已推送票落盘归档
- update_performance(trade_date)              用最新K线回填后续表现（次日/3日涨跌、5日高低、是否触及止损）
- generate_review_card(days=5)                生成「突破回踩复盘」深色 HTML 微信卡

记录文件：data/anchor_history/YYYYMMDD.json（按推送日归档，同一天按 code 去重合并）。
数据源：复用 anchor_break_retest_scanner.get_kline（腾讯→新浪双源降级）。
所有缺失数据优雅降级为 None/“数据未齐”，不报错中断。
"""
import json
import os
from datetime import datetime

from anchor_break_retest_scanner import get_kline  # 复用双源日线（list[{date,open,high,low,close,volume,amount}]）

# 记录目录（验证脚本可整体替换为临时目录，避免污染正式数据）
ANCHOR_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'anchor_history')

# 深色卡配色（与现有突破回踩推送卡同风格）
GOLD = '#e6b455'
GREY = '#9aa4b8'
TEAL = '#66d9e8'
RED = '#ff6b6b'
GREEN = '#52c41a'


def _hist_path(trade_date):
    """记录文件路径：data/anchor_history/YYYYMMDD.json。"""
    return os.path.join(ANCHOR_HISTORY_DIR, trade_date.replace('-', '') + '.json')


def _entry_plan(anchor_price):
    """由锚位派生进场区间/止损/进场中值（与推送卡同口径：锚±2%进场、锚下3%止损）。"""
    try:
        ap = float(anchor_price)
    except (TypeError, ValueError):
        return None, None, None, None
    lo, hi = round(ap * 0.98, 2), round(ap * 1.02, 2)
    stop = round(ap * 0.97, 2)
    return lo, hi, stop, round(ap, 2)


def record_candidates(scored_list, trade_date):
    """把 ≥50 分已推送票写入当日记录（同日重复推送按 code 去重合并，不堆叠）。
    返回本次写入条数。"""
    os.makedirs(ANCHOR_HISTORY_DIR, exist_ok=True)
    path = _hist_path(trade_date)
    # 读已有记录（同日可能已被 demo/定时 推过一次）
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                existing = {c['code']: c for c in json.load(f).get('candidates', [])}
        except Exception:
            existing = {}
    rows = []
    # 本批出现的 code（本批覆盖同 code 条目）
    batch_codes = {c.get('code') for c in scored_list if c.get('score_total', 0) >= 50}
    # 旧记录里未在本批出现的票保留（同日多次推送不丢票）
    rows.extend(v for k, v in existing.items() if k not in batch_codes)
    for c in scored_list:
        if c.get('score_total', 0) < 50:
            continue  # 只记录达标推送票
        code = c.get('code')
        ap = c.get('anchor_price')
        lo, hi, stop, mid = _entry_plan(ap)
        rows.append({
            'code': code,
            'name': c.get('name'),
            'score_total': c.get('score_total'),
            'position_suggest': c.get('position_suggest'),
            'anchor_price': ap,
            'anchor_type': c.get('anchor_type'),
            'retest_date': c.get('retest_date'),
            'sector_count': c.get('sector_count'),
            'push_date': trade_date,
            'entry_zone': f'{lo}~{hi}' if lo else '',
            'stop_loss': stop,
            'entry_mid': mid,
            # 同日重复推送时保留已有回填表现，不覆盖
            'performance': (existing.get(code) or {}).get('performance') or None,
        })
    doc = {
        'trade_date': trade_date,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'candidates': rows,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return len(rows)


def _as_date(s):
    """date 字段统一为 date 对象（K线 date 为 'YYYY-MM-DD' 字符串）。"""
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def update_performance(trade_date):
    """用最新K线回填某交易日推送票的后续表现。
    字段：day1_close_pct / day3_close_pct（相对进场中值）、max_high5/min_low5/max_high_pct、
    hit_stop（未来5日最低是否触及止损）、bars_after（推送日后K线根数）。
    数据不足（停牌/退市/未到期）→ 对应字段 None，不中断。返回成功回填票数。"""
    path = _hist_path(trade_date)
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    push_d = _as_date(trade_date)
    updated = 0
    for c in doc.get('candidates', []):
        code = c.get('code')
        mid = c.get('entry_mid')
        stop = c.get('stop_loss')
        try:
            rows = get_kline(code, n=120)
        except Exception as e:
            print(f'[tracker] {code} K线拉取失败（跳过）: {e}')
            continue
        if not rows:
            continue
        # 找推送日之后的所有bar
        after = [r for r in rows if _as_date(r['date']) and _as_date(r['date']) > push_d]
        if not after:
            # 无后续数据：保留旧表现或置空标记，不硬造
            c['performance'] = c.get('performance') or {'bars_after': 0, 'note': '推送日后暂无K线（停牌或未到交易日）'}
            continue
        perf = {'bars_after': len(after)}
        if mid:
            if len(after) >= 1:
                perf['day1_close_pct'] = round((after[0]['close'] - mid) / mid * 100, 2)
            if len(after) >= 3:
                perf['day3_close_pct'] = round((after[2]['close'] - mid) / mid * 100, 2)
            if len(after) >= 5:
                perf['day5_close_pct'] = round((after[4]['close'] - mid) / mid * 100, 2)
            seg = after[0:min(5, len(after))]
            if seg:
                perf['max_high5'] = float(max(r['high'] for r in seg))
                perf['min_low5'] = float(min(r['low'] for r in seg))
                perf['max_high_pct'] = round((perf['max_high5'] - mid) / mid * 100, 2)
            if stop:
                perf['hit_stop'] = bool(any(r['low'] <= stop for r in seg))
        c['performance'] = perf
        updated += 1
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return updated


def load_history(days=5):
    """读最近 N 个有记录的交易日（按文件名日期倒序取最近 days 个），返回 doc 列表。"""
    if not os.path.isdir(ANCHOR_HISTORY_DIR):
        return []
    files = [fn for fn in os.listdir(ANCHOR_HISTORY_DIR) if fn.endswith('.json')]
    files.sort(reverse=True)
    docs = []
    for fn in files:
        try:
            with open(os.path.join(ANCHOR_HISTORY_DIR, fn), encoding='utf-8') as f:
                docs.append(json.load(f))
        except Exception:
            continue
        if len(docs) >= days:
            break
    return docs


def _pct_txt(v, suffix='%'):
    """涨跌幅显示：None → “数据未齐”，正负带符号。"""
    if v is None:
        return '数据未齐'
    return f'{v:+.2f}{suffix}'


def generate_review_card(days=5):
    """生成「突破回踩·复盘」深色 HTML 微信卡。
    统计口径：胜率 = 次日/3日收盘价相对进场中值（entry_mid）盈利的占比；
    平均收益 = 3日收盘收益均值；数据不足的票不参与该统计、单独注明。"""
    docs = load_history(days)
    if not docs:
        return None
    pairs = []            # (candidate, performance) 有表现数据的票
    no_data = []          # 数据缺失的票（优雅降级展示）
    for doc in docs:
        for c in doc.get('candidates', []):
            p = c.get('performance') or {}
            if p.get('day1_close_pct') is None and p.get('day3_close_pct') is None and not p.get('bars_after'):
                no_data.append((c, p))
            else:
                pairs.append((c, p))

    total_push = sum(len(d.get('candidates', [])) for d in docs)
    d1s = [p['day1_close_pct'] for _, p in pairs if p.get('day1_close_pct') is not None]
    d3s = [p['day3_close_pct'] for _, p in pairs if p.get('day3_close_pct') is not None]
    win1 = (sum(1 for v in d1s if v > 0) / len(d1s) * 100) if d1s else None
    win3 = (sum(1 for v in d3s if v > 0) / len(d3s) * 100) if d3s else None
    avg3 = (sum(d3s) / len(d3s)) if d3s else None

    # 表现最好/最差：优先3日，缺3日用次日
    def _key(p):
        v = p.get('day3_close_pct')
        if v is None:
            v = p.get('day1_close_pct')
        return v if v is not None else -999
    best = max(pairs, key=lambda t: _key(t[1])) if pairs else None
    worst = min(pairs, key=lambda t: _key(t[1])) if pairs else None

    lines = [
        f'<div style="font-size:15px;font-weight:800;color:{GOLD};">🎯 突破回踩·复盘（近{days}个交易日｜推送 {total_push} 只）</div>',
        f'<div style="margin-top:2px;font-size:12px;color:{GREY};">次日胜率 {("—" if win1 is None else f"{win1:.0f}%（{len(d1s)}只有数据）")}｜3日胜率 {("—" if win3 is None else f"{win3:.0f}%")}｜平均3日收益 {_pct_txt(avg3)}</div>',
    ]
    # 每票一张小卡
    for c, p in pairs:
        code, name = c.get('code'), c.get('name')
        sc = c.get('score_total')
        ez = c.get('entry_zone') or '—'
        st = c.get('stop_loss') if c.get('stop_loss') is not None else '—'
        d1, d3 = p.get('day1_close_pct'), p.get('day3_close_pct')
        hs = p.get('hit_stop')
        d1c = GREEN if (d1 or 0) >= 0 else RED
        d3c = GREEN if (d3 or 0) >= 0 else RED
        stop_txt = f'<span style="color:{RED};font-size:12px;">⚠️ 触止损</span>' if hs else '<span style="color:#52c41a;font-size:12px;">未触止损</span>'
        lines.append(
            f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;">'
            f'<div style="font-size:14px;color:#fff;font-weight:700;">{name}（{code}）{sc}分'
            f'<span style="color:{GREY};font-size:12px;font-weight:400;"> 推送{c.get("push_date","")}</span></div>'
            f'<div style="margin:3px 0 0 2px;font-size:12px;color:{GREY};">进场 {ez}｜止损 {st}｜{stop_txt}</div>'
            f'<div style="margin:2px 0 0 2px;font-size:12px;">次日 <span style="color:{d1c};font-weight:700;">{_pct_txt(d1)}</span>｜3日 <span style="color:{d3c};font-weight:700;">{_pct_txt(d3)}</span>'
            f'<span style="color:{GREY};">｜5日高 {_pct_txt(p.get("max_high_pct"))}（{p.get("max_high5","—")}） 低 {("—" if p.get("min_low5") is None else p.get("min_low5"))}</span></div>'
            '</div>')
    # 数据缺失票
    for c, p in no_data:
        lines.append(
            f'<div style="margin-top:6px;padding:8px 10px;background:#1c2230;border-left:4px solid {GREY};border-radius:8px;">'
            f'<div style="font-size:12px;color:{GREY};">{c.get("name","")}（{c.get("code","")}）{c.get("score_total","")}分：数据未齐（停牌/未到交易日），待回填</div></div>')
    # 最好/最差
    if best:
        b = best[0]; bp = best[1]
        lines.append(f'<div style="margin-top:10px;font-size:12px;color:{GREEN};">🏆 表现最好：{b.get("name")}（{b.get("code")}）{_pct_txt(_key(bp))}</div>')
    if worst:
        w = worst[0]; wp = worst[1]
        lines.append(f'<div style="margin-top:2px;font-size:12px;color:{RED};">💀 表现最差：{w.get("name")}（{w.get("code")}）{_pct_txt(_key(wp))}</div>')
    lines.append('<div style="margin-top:8px;font-size:11px;color:#6b7280;">— 清一盘 · 公开行情，仅供参考，不构成投资建议 —</div>')
    return ('<div style="background:#161b26;padding:12px;border-radius:12px;">'
            + ''.join(lines) + '</div>')


def main(argv=None):
    """CLI：python tools/anchor_tracker.py --record YYYY-MM-DD / --update YYYY-MM-DD / --review [days]"""
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('usage: anchor_tracker.py --record <date> | --update <date> | --review [days]')
        return 0
    if argv[0] == '--record':
        # 从 anchor 扫描缓存重建记录（含评分，模拟 build_anchor 后落盘）
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import quality_scorer as QS
        cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                             f'anchor_candidates_{argv[1].replace("-", "")}.json')
        raw = json.load(open(cache, encoding='utf-8')) if os.path.exists(cache) else []
        scored = QS.score_batch(raw)
        n = record_candidates([c for c in scored if c.get('score_total', 0) >= 50], argv[1])
        print(f'recorded {n}')
        return n
    if argv[0] == '--update':
        n = update_performance(argv[1])
        print(f'updated {n}')
        return n
    if argv[0] == '--review':
        days = int(argv[1]) if len(argv) > 1 else 5
        html = generate_review_card(days)
        print(html if html else 'NO_DATA')
        return 0 if html else 1
    print('unknown cmd')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
