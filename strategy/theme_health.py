# -*- coding: utf-8 -*-
"""题材梯队健康分 theme_health（工单3）

纯标准库 + 纯入参：涨停池 list 进、分数 dict 出。云端 eod 与桌面端
strategy/limit_up_radar.py 共用同一份算法，两端各自喂数据，不互相依赖。

算法（用户 2026-11-06 指令，禁止改口径）：
  高度 30 = min(最高板/8, 1) × 30；最高板 ≥2 只并列再 +5（封顶 30）
  完整度 30 = 无断层 30 / 断1级 18 / 断2级 8 / 独苗(仅1家) 0
  广度 20 = 涨停≥10家 20 / ≥6家 15 / ≥3家 10 / 其余 5
  晋级率 20 = 昨日该题材首板今日晋级≥50% 满分，按比例给分
  晋级率数据缺失时：不编分，按 30/30/20 折算成 80 分制再映射回 100
  档位：≥70 加速期 / 40–69 分歧期 / <40 崩塌期

入参约定：
  rows      : [{'theme': '光伏', 'lbc': 3, 'code': '600000', 'name': 'XX'}, ...]
              兼容东财涨停池原始字段（'hybk' 当题材、'c' 当代码、'n' 当名称）
  prev_rows : 昨日涨停池同结构；传 None 表示历史未接入 → 晋级率标"数据未接入"
"""

LEVEL_ACCEL = 70
LEVEL_SPLIT = 40


def _int(v, d=0):
    try:
        return int(float(v))
    except Exception:
        return d


def _row_theme(r):
    return str(r.get('theme') or r.get('hybk') or r.get('sec') or '其他').strip() or '其他'


def _row_lbc(r):
    return _int(r.get('lbc', r.get('lianchi', 0)))


def _row_code(r):
    return str(r.get('code') or r.get('c') or '').strip()


def _group(rows):
    g = {}
    for r in rows:
        g.setdefault(_row_theme(r), []).append(r)
    return g


def health_one(theme, rows, prev_first_codes=None):
    """单个题材的健康分。prev_first_codes 为昨日该题材首板代码集合；None=数据未接入。"""
    rows = list(rows or [])
    lbs = [_row_lbc(r) for r in rows]
    max_lb = max(lbs) if lbs else 0
    n = len(rows)

    # 1) 高度 30：min(最高板/8,1)×30，最高板并列≥2只再 +5，封顶 30
    height = min(max_lb / 8.0, 1.0) * 30
    if max_lb >= 2 and lbs.count(max_lb) >= 2:
        height += 5
    height = min(round(height, 1), 30.0)

    # 2) 完整度 30：从最高板到 1 板逐级检查是否缺级
    if n <= 1:
        complete, gaps = 0.0, []
    else:
        present = set(x for x in lbs if x >= 1)
        gaps = [lv for lv in range(1, max_lb + 1) if lv not in present]
        if not gaps:
            complete = 30.0
        elif len(gaps) == 1:
            complete = 18.0
        elif len(gaps) == 2:
            complete = 8.0
        else:
            complete = 0.0

    # 3) 广度 20
    breadth = 20.0 if n >= 10 else 15.0 if n >= 6 else 10.0 if n >= 3 else 5.0

    # 4) 晋级率 20：昨日首板今日晋级 ≥50% 满分，按比例
    if not prev_first_codes:
        promote = None
    else:
        prev = [c for c in prev_first_codes if c]
        if not prev:
            promote = None
        else:
            today_lb2 = {_row_code(r) for r in rows if _row_lbc(r) >= 2}
            rate = len([c for c in prev if c in today_lb2]) / float(len(prev))
            promote = round(min(rate / 0.5, 1.0) * 20, 1)

    if promote is None:
        # 30/30/20 = 80 分制 → 映射回 100，晋级率如实标"数据未接入"
        raw = height + complete + breadth
        score = round(min(raw / 80.0 * 100.0, 100.0), 1)
        promote_note = '晋级率：数据未接入'
    else:
        score = round(min(height + complete + breadth + promote, 100.0), 1)
        promote_note = ''

    # 档位
    level = '加速期' if score >= LEVEL_ACCEL else ('分歧期' if score >= LEVEL_SPLIT else '崩塌期')

    # 梯队：6板×1|4板×1|3板×2|2板×4|1板×11（从高到低）
    counts = {}
    for b in lbs:
        if b >= 1:
            counts[b] = counts.get(b, 0) + 1
    ladder = '|'.join('%d板×%d' % (b, counts[b]) for b in sorted(counts, reverse=True)) or '无'

    note = _talking(theme, level, max_lb, len(gaps or []), n, promote)

    return {'theme': theme, 'score': score, 'level': level, 'ladder': ladder,
            'note': note, 'promote_note': promote_note,
            'parts': {'height': height, 'complete': complete,
                      'breadth': breadth, 'promote': promote},
            'count': n, 'max_lb': max_lb, 'gaps': gaps}


def _talking(theme, level, max_lb, gap_n, n, promote):
    """一句大白话，禁模板句、禁问句。"""
    if level == '加速期':
        return '%s 梯队完整、%d家涨停、最高%d板，资金在往里加仓，明日重点看龙头能否再顶一字' % (theme, n, max_lb)
    if level == '分歧期':
        if gap_n:
            return '%s 高度有%d板但梯队断了%d级，只能算局部强势，追高要等回封确认' % (theme, max_lb, gap_n)
        return '%s %d家涨停、最高%d板，热度还在但没加速，明日看能否补高度' % (theme, n, max_lb)
    if max_lb <= 1:
        return '%s 全是首板没高度，一日游概率大，别当主线做' % theme
    return '%s 只剩%d板独苗、%d家涨停，梯队塌了，明日以退为主' % (theme, max_lb, n)


def theme_health(rows, prev_rows=None, min_count=1, top_n=None):
    """全市场题材健康分，按分数降序返回 list[dict]。

    prev_rows 传昨日涨停池（同结构）；为 None 时晋级率一律"数据未接入"。
    """
    today = _group(rows)
    prev = _group(prev_rows) if prev_rows else {}
    out = []
    for theme, rs in today.items():
        if len(rs) < min_count:
            continue
        prev_codes = None
        if prev_rows is not None:
            prev_codes = [_row_code(x) for x in prev.get(theme, []) if _row_lbc(x) == 1]
        out.append(health_one(theme, rs, prev_codes))
    out.sort(key=lambda x: (-x['score'], -x['count']))
    return out[:top_n] if top_n else out


def _selftest():
    """合成数据自检：覆盖三档边界与晋级率两种情况，不联网。"""
    import sys
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 光伏（无断层，6-5-4-3-2-1 全在）：高度 6/8→22.5，完整度30，广度20
    rows = [{'theme': '光伏', 'lbc': 6, 'code': 'A1', 'name': 'x'}] \
        + [{'theme': '光伏', 'lbc': 5, 'code': 'A1b', 'name': 'x'},
           {'theme': '光伏', 'lbc': 4, 'code': 'A2', 'name': 'x'}] \
        + [{'theme': '光伏', 'lbc': 3, 'code': 'A3', 'name': 'x'},
           {'theme': '光伏', 'lbc': 3, 'code': 'A4', 'name': 'x'}] \
        + [{'theme': '光伏', 'lbc': 2, 'code': 'A5', 'name': 'x'},
           {'theme': '光伏', 'lbc': 2, 'code': 'A6', 'name': 'x'},
           {'theme': '光伏', 'lbc': 2, 'code': 'A7', 'name': 'x'},
           {'theme': '光伏', 'lbc': 2, 'code': 'A8', 'name': 'x'}] \
        + [{'theme': '光伏', 'lbc': 1, 'code': 'A%d' % (9 + i), 'name': 'x'} for i in range(11)]
    h = health_one('光伏', rows)
    print('光伏 parts=', h['parts'], 'score=', h['score'], 'ladder=', h['ladder'])
    ck('光伏 高度 6/8→22.5', h['parts']['height'] == 22.5, h['parts']['height'])
    ck('光伏 完整度30(无断层)', h['parts']['complete'] == 30.0, h['parts']['complete'])
    ck('光伏 广度20(17家)', h['parts']['breadth'] == 20.0, h['parts']['breadth'])
    ck('光伏 晋级率缺省→80分制映射 90.6', h['score'] == 90.6, h['score'])
    ck('光伏 梯队串格式', h['ladder'] == '6板×1|5板×1|4板×1|3板×2|2板×4|1板×11', h['ladder'])
    ck('光伏 档位加速', h['level'] == '加速期', h['level'])
    ck('光伏 并列最高板才加5', h['parts']['height'] == 22.5, h['parts']['height'])

    # 用户样板梯队（6|4|3|2|1，本身缺 5 板）→ 完整度 18，分数 (22.5+18+20)/80*100 = 75.6
    r_gap = [{'theme': '光伏', 'lbc': 6, 'code': 'B1'}] \
        + [{'theme': '光伏', 'lbc': 4, 'code': 'B2'}] \
        + [{'theme': '光伏', 'lbc': 3, 'code': 'B3'}, {'theme': '光伏', 'lbc': 3, 'code': 'B4'}] \
        + [{'theme': '光伏', 'lbc': 2, 'code': 'B%d' % (5 + i)} for i in range(4)] \
        + [{'theme': '光伏', 'lbc': 1, 'code': 'B%d' % (9 + i)} for i in range(11)]
    hg = health_one('光伏', r_gap)
    ck('样板梯队 完整度18(断5板)', hg['parts']['complete'] == 18.0, hg['parts']['complete'])
    ck('样板梯队 梯队串=用户样板', hg['ladder'] == '6板×1|4板×1|3板×2|2板×4|1板×11', hg['ladder'])
    ck('样板梯队 分数75.6→加速期', (hg['score'], hg['level']) == (75.6, '加速期'), (hg['score'], hg['level']))

    # 无断层梯队再抽掉 3 板 → 断 1 级 → 18
    r_one = [r for r in rows if r['lbc'] != 3]
    h2 = health_one('光伏', r_one)
    ck('断1级→18', h2['parts']['complete'] == 18.0, h2['parts']['complete'])

    # 独苗
    h3 = health_one('独苗', [{'theme': '独苗', 'lbc': 2, 'code': 'Z'}])
    ck('独苗→完整度0', h3['parts']['complete'] == 0.0, h3['parts']['complete'])

    # 三档边界：≥70 加速 / 40-69 分歧 / <40 崩塌
    def score_of(n_lb1, max_lb):
        rs = [{'theme': 'T', 'lbc': max_lb}] + [{'theme': 'T', 'lbc': 1} for _ in range(n_lb1 - 1)]
        return health_one('T', rs)
    b1 = score_of(4, 2)     # 高度 7.5 完整度30 广度10 → 47.5/80*100=59.4 分歧
    print('边界样例 b1=', b1['score'], b1['level'])
    ck('59.4 → 分歧期', b1['level'] == '分歧期', b1['level'])
    b2 = health_one('T', [{'theme': 'T', 'lbc': 1}] * 1)
    print('独苗 b2=', b2['score'], b2['level'])
    ck('<40 → 崩塌期', b2['score'] < 40 and b2['level'] == '崩塌期', (b2['score'], b2['level']))

    # 晋级率真分：昨日 4 只首板，今日 2 只晋级 → 50% → 满 20
    prev = [{'theme': '光伏', 'lbc': 1, 'code': c} for c in ('A9', 'A10', 'PX1', 'PX2')]
    rows_p = rows + [{'theme': '光伏', 'lbc': 2, 'code': 'PX1'},
                     {'theme': '光伏', 'lbc': 2, 'code': 'A9'}]
    hp = health_one('光伏', rows_p, prev_first_codes=['A9', 'A10', 'PX1', 'PX2'])
    ck('晋级率50%→20分', hp['parts']['promote'] == 20.0, hp['parts']['promote'])
    ck('晋级率接入后分数含20', hp['score'] > h['score'], (h['score'], hp['score']))
    hp2 = health_one('光伏', rows_p, prev_first_codes=['PX1', 'A9', 'X3', 'X4'])
    ck('晋级率100%→封顶20', hp2['parts']['promote'] == 20.0, hp2['parts']['promote'])
    print('[selftest] theme_health RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 3


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    print('theme_health: 用 --selftest 运行自检')
