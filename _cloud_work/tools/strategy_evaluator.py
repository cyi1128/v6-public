# -*- coding: utf-8 -*-
"""突破回踩·主力成本锚 策略评估与优化模块（第5步，纯标准库，无第三方依赖）。

能力：
- load_history(days=None, start=None, end=None)   读 data/anchor_history/ 记录（按最近N个交易日或日期区间过滤）
- evaluate(records)                               结构化评估（胜率/收益/触止损率/盈亏比/分数段分层）
- sensitivity_analysis(records, param_grid=None)  min_score 网格扫描 → 推荐阈值
- generate_suggestions(eval_result, sensitivity)  自动输出 3~6 条可执行优化建议
- generate_eval_card(days=20)                     深色 HTML 评估卡（对齐第4步复盘卡风格）
- CLI：--evaluate [--days N] / --sensitivity / --card [--days N]

记录格式复用第4步 anchor_history（candidate 含 performance{day1/3/5_close_pct, hit_stop, ...}）。
空目录/无记录/缺数据一律优雅降级，不抛异常、不写假数据。
"""
import json
import os
import statistics
from datetime import datetime

import anchor_tracker as TR  # 动态取 TR.ANCHOR_HISTORY_DIR（测试可整体替换隔离目录）

# 深色卡配色（与第4步复盘卡同风格）
GOLD = '#e6b455'
GREY = '#9aa4b8'
RED = '#ff6b6b'
GREEN = '#52c41a'

# 默认 min_score 扫描网格
DEFAULT_MIN_SCORE_GRID = [50, 55, 60, 65, 70, 75, 80]
# 分数段分层
SCORE_BANDS = [('>=80', 80, 999), ('70-79', 70, 79), ('60-69', 60, 69), ('50-59', 50, 59)]
# 建议调参的最小样本门槛（3日有数据）
MIN_SAMPLE_FOR_ADJUST = 5


def _cand_perf(c):
    """取 candidate 的 performance dict（无则空 dict）。"""
    return c.get('performance') or {}


def _has_data(c, key='day3_close_pct'):
    """该票在某口径下有可用数据。"""
    return _cand_perf(c).get(key) is not None


def load_history(days=None, start=None, end=None):
    """读 data/anchor_history/ 记录并展平为 candidate 列表。
    - days: 最近 N 个有记录的交易日（按文件名日期倒序）
    - start/end: 'YYYY-MM-DD' 区间过滤（含边界）
    空目录/无有效记录 → 返回 []。"""
    if not os.path.isdir(TR.ANCHOR_HISTORY_DIR):
        return []
    files = [fn for fn in os.listdir(TR.ANCHOR_HISTORY_DIR) if fn.endswith('.json')]
    files.sort(reverse=True)
    # 最近 N 个交易日（days 过滤）
    if days:
        files = files[:days]
    out = []
    for fn in files:
        try:
            with open(os.path.join(TR.ANCHOR_HISTORY_DIR, fn), encoding='utf-8') as f:
                doc = json.load(f)
        except Exception:
            continue
        d = doc.get('trade_date', '')
        if start and d < start:
            continue
        if end and d > end:
            continue
        for c in doc.get('candidates', []):
            c = dict(c)
            c['_file'] = d
            out.append(c)
    return out


def _pct(v):
    """收益率 → 百分点数值（None → None）。"""
    return v if v is not None else None


def _winrate(values):
    """胜率：>0 占比（空样本 → None）。"""
    if not values:
        return None
    return round(sum(1 for v in values if v > 0) / len(values) * 100, 1)


def evaluate(records):
    """结构化评估。records = load_history 输出。
    指标：推送数/各口径样本数/次日·3日·5日胜率/平均·中位收益/触止损率/盈亏比/最差3日/分数段分层/数据未齐数。"""
    n_push = len(records)
    d1s = [_pct(_cand_perf(c).get('day1_close_pct')) for c in records]
    d1s = [v for v in d1s if v is not None]
    d3s = [_pct(_cand_perf(c).get('day3_close_pct')) for c in records]
    d3s = [v for v in d3s if v is not None]
    d5s = [_pct(_cand_perf(c).get('day5_close_pct')) for c in records]
    d5s = [v for v in d5s if v is not None]
    no_data = [c for c in records if not _cand_perf(c) or not _cand_perf(c).get('bars_after')]
    hit = [c for c in records if _cand_perf(c).get('hit_stop') is True]
    hit_rate = round(len(hit) / len(d3s) * 100, 1) if d3s else None  # 触止损率（有3日数据的样本）

    # 盈亏比：盈利票平均3日收益 / |亏损票平均3日收益|
    gains = [v for v in d3s if v > 0]
    losses = [v for v in d3s if v < 0]
    pl_ratio = None
    if gains and losses:
        pl_ratio = round((sum(gains) / len(gains)) / abs(sum(losses) / len(losses)), 2)
    elif gains and not losses:
        pl_ratio = None  # 全盈利 → 不定义

    # 分数段分层（3日口径）
    bands = []
    for label, lo, hi in SCORE_BANDS:
        grp = [c for c in records if lo <= (c.get('score_total') or 0) <= hi]
        g3 = [_pct(_cand_perf(c).get('day3_close_pct')) for c in grp]
        g3 = [v for v in g3 if v is not None]
        bands.append({
            'band': label,
            'n': len(grp),
            'n_with_day3': len(g3),
            'day3_winrate': _winrate(g3),
            'avg_day3': round(sum(g3) / len(g3), 2) if g3 else None,
        })

    return {
        'total_push': n_push,
        'n_day1': len(d1s),
        'n_day3': len(d3s),
        'n_day5': len(d5s),
        'day1_winrate': _winrate(d1s),
        'day3_winrate': _winrate(d3s),
        'day5_winrate': _winrate(d5s),
        'avg_day1': round(sum(d1s) / len(d1s), 2) if d1s else None,
        'median_day1': round(statistics.median(d1s), 2) if d1s else None,
        'avg_day3': round(sum(d3s) / len(d3s), 2) if d3s else None,
        'median_day3': round(statistics.median(d3s), 2) if d3s else None,
        'hit_stop_rate': hit_rate,
        'n_hit_stop': len(hit),
        'profit_loss_ratio': pl_ratio,
        'worst_day3': (round(min(d3s), 2) if d3s else None),
        'best_day3': (round(max(d3s), 2) if d3s else None),
        'bands': bands,
        'n_no_data': len(no_data),
    }


def sensitivity_analysis(records, param_grid=None):
    """对 min_score 做网格扫描：保留 score>=阈值 且有3日数据的票，重算3日胜率/平均收益/样本数。
    推荐：样本数≥3 中优先3日胜率最高，其次平均收益；无合格样本 → recommended=None。"""
    grid = list(param_grid) if param_grid else list(DEFAULT_MIN_SCORE_GRID)
    rows = []
    for thr in grid:
        grp = [c for c in records if (c.get('score_total') or 0) >= thr]
        g3 = [_pct(_cand_perf(c).get('day3_close_pct')) for c in grp]
        g3 = [v for v in g3 if v is not None]
        rows.append({
            'min_score': thr,
            'n': len(grp),
            'n_with_day3': len(g3),
            'day3_winrate': _winrate(g3),
            'avg_day3': round(sum(g3) / len(g3), 2) if g3 else None,
        })
    # 推荐：样本数≥3 中按 3日胜率 降序，次按 avg_day3 降序
    valid = [r for r in rows if r['n_with_day3'] >= 3 and r['day3_winrate'] is not None]
    recommended = None
    if valid:
        recommended = max(valid, key=lambda r: (r['day3_winrate'], r['avg_day3'] or -999))['min_score']
    return {'grid': rows, 'recommended': recommended}


def generate_suggestions(eval_result, sensitivity_result):
    """根据评估结果自动输出 3~6 条可执行优化建议（大白话）。"""
    e = eval_result
    s = sensitivity_result
    out = []
    n3 = e.get('n_day3') or 0
    if e.get('total_push') == 0 or n3 == 0:
        out.append(f'暂无足够样本（推送 {e.get("total_push")} 只、3日数据 {n3} 只），暂不建议调参，继续积累记录')
        return out

    if n3 < MIN_SAMPLE_FOR_ADJUST:
        out.append(f'样本过少（3日数据仅 {n3} 只），以下结论仅供参考，暂不建议正式调参')

    # 阈值建议（来自敏感性扫描）
    rec = s.get('recommended')
    if rec is not None and rec > 50:
        row = next((r for r in s.get('grid', []) if r['min_score'] == rec), None)
        base = next((r for r in s.get('grid', []) if r['min_score'] == 50), None)
        if row and base and base.get('day3_winrate') is not None and row.get('day3_winrate') is not None:
            out.append(f'建议将推送阈值从 50 提升至 {rec}：3日胜率可从 {base["day3_winrate"]:.0f}% 提升至 {row["day3_winrate"]:.0f}%（样本 {row["n_with_day3"]} 只）')
    elif rec == 50:
        out.append('当前 50 分阈值表现最优，暂不建议提高推送门槛（可先加量积累样本）')

    # 分数段结论
    bands = e.get('bands') or []
    hi = next((b for b in bands if b['band'] == '>=80'), None)
    lo = next((b for b in bands if b['band'] in ('50-59', '60-69')), None)
    if hi and hi.get('n_with_day3') and hi.get('day3_winrate') is not None:
        if lo and lo.get('day3_winrate') is not None and hi['day3_winrate'] > (lo['day3_winrate'] or 0) + 10:
            out.append(f'≥80 分段 3日胜率 {hi["day3_winrate"]:.0f}% 显著优于中低分段，可优先推送高分段')
        elif hi.get('day3_winrate') and hi['day3_winrate'] >= 60:
            out.append(f'≥80 分段 3日胜率 {hi["day3_winrate"]:.0f}%，保持高分段优先推送')

    # 触止损率
    hs = e.get('hit_stop_rate')
    if hs is not None and hs >= 30:
        out.append(f'触止损率 {hs:.0f}% 偏高（{e.get("n_hit_stop")} 只），建议收紧止损距离或过滤弱趋势票（板块共振 <3 只的票降权）')
    elif hs is not None and hs < 10:
        out.append(f'触止损率 {hs:.0f}% 很低，止损纪律执行良好')

    # 盈亏比
    pl = e.get('profit_loss_ratio')
    if pl is not None and pl < 1:
        out.append(f'平均盈亏比 {pl} <1，赚的没有亏的多，建议提高入场质量（回踩企稳再介入）或设止盈落袋')
    elif pl is not None and pl >= 1.5:
        out.append(f'平均盈亏比 {pl} 良好，保持「回踩企稳介入 + 破止损离场」的执行纪律')

    # 整体胜率
    w3 = e.get('day3_winrate')
    if w3 is not None and w3 >= 60:
        out.append(f'3日胜率 {w3:.0f}%，策略整体有效，维持当前参数并扩大样本验证')
    elif w3 is not None and w3 < 40 and n3 >= MIN_SAMPLE_FOR_ADJUST:
        out.append(f'3日胜率仅 {w3:.0f}%，策略可能已失效或环境切换，建议暂停推送并回溯选股逻辑')

    if len(out) < 3:
        out.append('当前样本/指标无重大异常，维持现有参数继续观察')
    return out[:6]


def _pct_txt(v, suffix='%'):
    if v is None:
        return '—'
    return f'{v:+.2f}{suffix}'


def _win_txt(v):
    if v is None:
        return '—'
    return f'{v:.0f}%'


def generate_eval_card(days=20):
    """生成「突破回踩·策略评估」深色 HTML 卡（对齐第4步复盘卡风格）。
    空历史/无有效记录 → None；样本不足 → 卡内明确提示。"""
    records = load_history(days=days)
    if not records:
        return None
    e = evaluate(records)
    s = sensitivity_analysis(records)
    sugg = generate_suggestions(e, s)

    lines = [
        f'<div style="font-size:15px;font-weight:800;color:{GOLD};">🎯 突破回踩·策略评估（近{days}个交易日｜推送 {e["total_push"]} 只）</div>',
        f'<div style="margin-top:2px;font-size:12px;color:{GREY};">次日胜率 {_win_txt(e["day1_winrate"])}（{e["n_day1"]}只）｜3日胜率 {_win_txt(e["day3_winrate"])}｜5日胜率 {_win_txt(e["day5_winrate"])}｜平均3日 {_pct_txt(e["avg_day3"])}</div>',
        f'<div style="margin-top:2px;font-size:12px;color:{GREY};">触止损率 {_win_txt(e["hit_stop_rate"])}｜盈亏比 {("—" if e["profit_loss_ratio"] is None else e["profit_loss_ratio"])}｜最差3日 {_pct_txt(e["worst_day3"])}｜数据未齐 {e["n_no_data"]} 只</div>',
    ]
    if (e.get('n_day3') or 0) == 0:
        lines.append(f'<div style="margin-top:8px;font-size:13px;color:{RED};">⚠️ 暂无足够样本（3日数据 0 只），暂不做调参结论</div>')

    # 分数段分层（文本表格 → HTML 行）
    lines.append(f'<div style="margin-top:10px;font-size:13px;color:#fff;font-weight:700;">📊 分数段分层（3日口径）</div>')
    for b in e.get('bands') or []:
        color = GREEN if (b['day3_winrate'] or 0) >= 60 else (RED if (b['day3_winrate'] or 0) < 40 else GREY)
        lines.append(
            f'<div style="margin:2px 0 0 2px;font-size:12px;color:{GREY};">{b["band"]}分｜样本 {b["n"]}（3日 {b["n_with_day3"]}）｜'
            f'3日胜率 <span style="color:{color};">{_win_txt(b["day3_winrate"])}</span>｜平均3日 {_pct_txt(b["avg_day3"])}</div>')

    # 参数敏感性
    lines.append(f'<div style="margin-top:10px;font-size:13px;color:#fff;font-weight:700;">🔧 参数敏感性（min_score）</div>')
    grid = s.get('grid') or []
    if grid:
        lines.append(f'<div style="margin:2px 0 0 2px;font-size:12px;color:{GREY};">' +
                     '｜'.join(f'{r["min_score"]}: {_win_txt(r["day3_winrate"])}/{r["n_with_day3"]}只' for r in grid) + '</div>')
    if s.get('recommended') is not None:
        lines.append(f'<div style="margin:2px 0 0 2px;font-size:12px;color:{GOLD};">🏆 推荐阈值：min_score = {s["recommended"]}</div>')
    else:
        lines.append(f'<div style="margin:2px 0 0 2px;font-size:12px;color:{GREY};">样本不足，暂不推荐阈值</div>')

    # 优化建议
    lines.append(f'<div style="margin-top:10px;font-size:13px;color:#fff;font-weight:700;">💡 优化建议</div>')
    for i, sg in enumerate(sugg, 1):
        icon = '🏆' if i == 1 else ('⚠️' if ('提升' in sg or '收紧' in sg or '暂停' in sg or '失效' in sg or '不足' in sg) else '·')
        lines.append(f'<div style="margin:2px 0 0 2px;font-size:12px;color:#d5dbe6;">{icon} {sg}</div>')

    lines.append('<div style="margin-top:8px;font-size:11px;color:#6b7280;">— 清一盘 · 公开行情，仅供参考，不构成投资建议 —</div>')
    return ('<div style="background:#161b26;padding:12px;border-radius:12px;">' + ''.join(lines) + '</div>')


def main(argv=None):
    """CLI：python tools/strategy_evaluator.py --evaluate [--days N] | --sensitivity | --card [--days N]"""
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('usage: strategy_evaluator.py --evaluate [--days N] | --sensitivity | --card [--days N]')
        return 0
    days = 20
    if '--days' in argv:
        try:
            days = int(argv[argv.index('--days') + 1])
        except Exception:
            pass
    if '--evaluate' in argv:
        e = evaluate(load_history(days=days))
        print(json.dumps(e, ensure_ascii=False, indent=2))
        return 0
    if '--sensitivity' in argv:
        s = sensitivity_analysis(load_history(days=days))
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    if '--card' in argv:
        html = generate_eval_card(days=days)
        print(html if html else 'NO_DATA')
        return 0 if html else 1
    print('unknown cmd')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
