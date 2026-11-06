# -*- coding: utf-8 -*-
"""策略锦标赛 strategy_tournament（工单2）

口径（用户 2026-11-06 指令）：
  - 主指标 win（T+5 涨>1% 为胜，账本列名 win），辅以 ret5 均值；
  - 每个因子维度（jq/lj/zj/tc/dl）两个维度打分：
      ① 子分与实际收益的相关性（Pearson，ret5 与子分）
      ② 高分票（子分≥70）的实际胜率 / ret5 均值
  - 样本 <30：只出报告，**不产生任何权重变动**（代码分支，不靠人盯）；
  - 调权步长 0.03，单维权重上下限 [0.10, 0.45]，调整后其余维度按比例摊回，总和恒 1.0；
  - 每次变动写入 data/tournament_log.json，且必须带 "week_samples"。

纯标准库，云端可直接跑。默认 --report 只读不改；--apply 才写盘。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, 'data', 'signal_log.csv')
FW_PATH = os.path.join(ROOT, 'data', 'factor_weights.json')
TLOG_PATH = os.path.join(ROOT, 'data', 'tournament_log.json')

DIMS = [
    ('jq', '情绪'),
    ('lj', '量价'),
    ('zj', '资金'),
    ('tc', '题材'),
    ('dl', '动量'),
]
# factor_engine 的默认维度权重（data/factor_weights.json 不存在时用它）
DEFAULT_FW = {'jq': 30.0, 'lj': 30.0, 'zj': 20.0, 'tc': 10.0, 'dl': 10.0}
MIN_SAMPLES = 30
STEP = 0.03
LO, HI = 0.10, 0.45
HIGH_SCORE = 70.0


def _num(v):
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except Exception:
        return None


def load_rows(path=CSV_PATH):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read().rstrip('\n')
    except Exception:
        return [], []
    lines = raw.split('\n') if raw else []
    if len(lines) < 2:
        return [], []
    hdr = lines[0].split(',')
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        parts = ln.split(',')
        if len(parts) < len(hdr):
            parts += [''] * (len(hdr) - len(parts))
        rows.append({h: parts[i] for i, h in enumerate(hdr)})
    return rows, hdr


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return sxy / ((sxx ** 0.5) * (syy ** 0.5))


def dim_stats(rows, dim):
    """单维度统计。只用同时有子分与 ret5 的行（win 缺失时用 ret5>1 推）。"""
    pairs, highs = [], []
    for r in rows:
        s = _num(r.get(dim))
        ret = _num(r.get('ret5'))
        if s is None or ret is None:
            continue
        win = r.get('win')
        won = (str(win).strip() in ('1', 'True', 'true')) if str(win).strip() else (ret > 1.0)
        pairs.append((s, ret, won))
        if s >= HIGH_SCORE:
            highs.append((ret, won))
    n = len(pairs)
    out = {'dim': dim, 'n': n, 'corr': None, 'win_rate': None,
           'high_n': len(highs), 'high_win': None, 'high_ret': None, 'status': '数据不足'}
    if n:
        out['win_rate'] = round(100.0 * sum(1 for _, _, w in pairs if w) / n, 1)
        out['corr'] = None if n < 3 else round(_pearson([p[0] for p in pairs], [p[1] for p in pairs]) or 0.0, 3)
    if highs:
        out['high_win'] = round(100.0 * sum(1 for _, w in highs if w) / len(highs), 1)
        out['high_ret'] = round(sum(r for r, _ in highs) / len(highs), 2)
    if n >= 3:
        out['status'] = 'ok'
    return out


def load_observation(path=None):
    """从权重文件读各引擎观察期 {dim: 'YYYY-MM-DD'}（新生因子只统计不调权）。"""
    p = path or os.path.join(ROOT, 'config', 'aggregator_weights.json')
    try:
        with open(p, encoding='utf-8') as f:
            raw = json.load(f) or {}
    except Exception:
        return {}
    obs = raw.get('observation_until') or {}
    eng = raw.get('engines') or {}
    for k, v in eng.items():
        if isinstance(v, dict) and v.get('observation_until'):
            obs.setdefault(k, v['observation_until'])
    return {k: str(v) for k, v in obs.items() if v}


def _in_observation(dim, observation, today):
    """观察期内 → True（只统计、不参与末位降权）。"""
    until = (observation or {}).get(dim)
    if not until:
        return False
    t = today or time.strftime('%Y-%m-%d')
    return t <= until


def weekly_report(rows, min_samples=MIN_SAMPLES, observation=None, today=None):
    st = [dim_stats(rows, d) for d, _ in DIMS]
    total = max((x['n'] for x in st), default=0)
    for x in st:
        x['observation'] = _in_observation(x['dim'], observation, today)
    ranked = sorted([x for x in st], key=lambda x: (x['win_rate'] if x['win_rate'] is not None else -1,
                                                    x['high_ret'] if x['high_ret'] is not None else -9), reverse=True)
    enough = total >= min_samples
    lines = []
    for i, x in enumerate(ranked, 1):
        name = dict(DIMS)[x['dim']]
        tail = ' | 观察期' if x.get('observation') else ''
        if (not enough) or x['win_rate'] is None:
            lines.append('%s | 样本不足，本季观察%s' % (name, tail))
            continue
        lines.append('%s | 本周%d笔 | 胜率%.1f%% | 高分票均值%s | 排名%d%s'
                     % (name, x['n'], x['win_rate'],
                        ('%.2f%%' % x['high_ret']) if x['high_ret'] is not None else '—', i, tail))
    return {'rows': len(rows), 'samples': total, 'enough': enough,
            'dims': st, 'ranked': ranked, 'lines': lines,
            'conclusion': _conclusion(ranked, enough, total)}


def _conclusion(ranked, enough, total):
    if not enough:
        return '本周有效样本%d笔，不足%d笔，只做观察不出结论、不调权；先把账本攒厚。' % (total, MIN_SAMPLES)
    best, worst = ranked[0], ranked[-1]
    return '%s最在状态（高分票均值%s），%s最该警惕，权重按规则小幅动，不一次调狠。' % (
        dict(DIMS)[best['dim']],
        ('%.2f%%' % best['high_ret']) if best['high_ret'] is not None else '—',
        dict(DIMS)[worst['dim']])


def load_fw(path=FW_PATH):
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f) or {}
    except Exception:
        return dict(DEFAULT_FW)
    out = {}
    for k, _ in DIMS:
        v = _num(raw.get(k))
        out[k] = v if v is not None else DEFAULT_FW[k]
    return out


def _normalize(w):
    s = sum(w.values())
    if s <= 0:
        return {k: DEFAULT_FW[k] for k, _ in DIMS}
    return {k: round(v / s * 100.0, 2) for k, v in w.items()}


def _rebalance(w):
    """按小数权重收口：先夹到 [LO,HI]，再把差额按可动空间摊给未触边界的维度，保证和=1.0。"""
    w = {k: max(LO, min(HI, v)) for k, v in w.items()}
    for _ in range(8):
        diff = 1.0 - sum(w.values())
        if abs(diff) < 1e-9:
            break
        if diff > 0:
            free = [k for k in w if w[k] < HI - 1e-9]
            tot = sum(w[k] - LO for k in free)
            for k in free:
                w[k] += diff * ((w[k] - LO) / tot if tot > 0 else 1.0 / len(free))
        else:
            free = [k for k in w if w[k] > LO + 1e-9]
            tot = sum(w[k] - LO for k in free)
            for k in free:
                w[k] += diff * ((w[k] - LO) / tot if tot > 0 else 1.0 / len(free))
        w = {k: max(LO, min(HI, v)) for k, v in w.items()}
    out = {k: round(v * 100.0, 2) for k, v in w.items()}
    # 收口：四舍五入残差补到最大维度，保证总和严格 100.00（红线：总和恒为 1.0）
    res = round(100.0 - sum(out.values()), 2)
    if abs(res) >= 0.01:
        k = max(out, key=lambda x: out[x])
        out[k] = round(out[k] + res, 2)
    return out


def plan_adjust(fw, ranked, samples, observation=None, today=None):
    """返回 (new_fw, changes)。样本不足时 changes 恒为空；观察期引擎不参与末位降权。"""
    if samples < MIN_SAMPLES:
        return dict(fw), []
    worst = None
    for x in ranked[::-1]:
        if x['win_rate'] is None:
            continue
        if _in_observation(x['dim'], observation, today):
            continue                      # 观察期：只统计不调权（代码分支，不靠人盯）
        worst = x
        break
    if worst is None:
        return dict(fw), []
    dim = worst['dim']
    old = fw[dim] / 100.0
    new = max(LO, min(HI, round(old - STEP, 4)))
    if abs(new - old) < 1e-9:
        return dict(fw), []
    delta = new - old
    # 其余维度按比例摊回，保持总和 1.0
    others = {k: v for k, v in fw.items() if k != dim}
    os_sum = sum(others.values())
    new_fw = {k: v / 100.0 for k, v in fw.items()}
    for k in others:
        share = (others[k] / os_sum) if os_sum > 0 else 1.0 / len(others)
        new_fw[k] = new_fw[k] - delta * share
    return _rebalance(new_fw), [
        {'dim': dim, 'old': round(old, 4), 'new': round(new, 4),
         'week_samples': samples, 'reason': '连续末位降权（机械调权）'}]


def apply_changes(new_fw, changes, samples, path_fw=FW_PATH, path_tlog=TLOG_PATH):
    if not changes:
        return False
    with open(path_fw, 'w', encoding='utf-8') as f:
        json.dump({'updated': _today(), 'weights': new_fw,
                   'note': '锦标赛机械调权写入（维度权重）'}, f, ensure_ascii=False, indent=2)
    try:
        with open(path_tlog, encoding='utf-8') as f:
            log = json.load(f) or {}
    except Exception:
        log = {'version': 1, 'entries': [], 'upgrade_hooks': []}
    entries = log.setdefault('entries', [])
    for c in changes:
        entries.append({'date': _today(), 'engine': c['dim'], 'old': c['old'],
                        'new': c['new'], 'week_samples': c['week_samples'],
                        'reason': c['reason'], 'by': '工单2-锦标赛'})
    log['updated'] = _today()
    with open(path_tlog, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return True


def _today():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d')


def _selftest():
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 样本不足：<30 笔 → 不产生任何变动
    few = []
    for i in range(12):
        few.append({'jq': '80', 'lj': '50', 'zj': '60', 'tc': '40', 'dl': '30',
                    'ret5': '-2.0' if i % 2 else '3.0', 'win': '0'})
    rep = weekly_report(few)
    print('few samples=', rep['samples'], 'enough=', rep['enough'])
    ck('12笔→样本不足', rep['enough'] is False, rep['samples'])
    ck('不足时排行榜写观察', any('样本不足，本季观察' in x for x in rep['lines']), rep['lines'][0])
    ck('不足时不出结论', '不足' in rep['conclusion'], rep['conclusion'])
    fw0 = dict(DEFAULT_FW)
    new0, ch0 = plan_adjust(fw0, rep['ranked'], rep['samples'])
    ck('不足时权重零变动', ch0 == [] and new0 == fw0, (ch0, new0))

    # 样本充足：>=30 笔 → 末位降 0.03，且落日志带 week_samples
    many = []
    for i in range(40):
        many.append({'jq': str(50 + i % 40), 'lj': str(50 + i % 30), 'zj': '60',
                     'tc': '40', 'dl': str(20 + i % 10),
                     'ret5': ('%.2f' % ((i % 7) - 2)), 'win': '1' if i % 3 == 0 else '0'})
    rep2 = weekly_report(many)
    print('many samples=', rep2['samples'], 'enough=', rep2['enough'])
    ck('40笔→样本充足', rep2['enough'] is True, rep2['samples'])
    fw = {'jq': 20.0, 'lj': 20.0, 'zj': 20.0, 'tc': 20.0, 'dl': 20.0}
    new, ch = plan_adjust(fw, rep2['ranked'], rep2['samples'])
    print('changes=', ch, 'new=', new)
    ck('充足时产生变动', len(ch) == 1, ch)
    ck('步长=0.03', ch and abs((ch[0]['old'] - ch[0]['new']) - STEP) < 1e-6, ch)
    ck('日志带 week_samples', ch and ch[0]['week_samples'] == rep2['samples'], ch)
    ck('新权重和=100', abs(sum(new.values()) - 100.0) < 0.5, sum(new.values()))
    ck('权重仍在[10,45]', all(LO * 100 <= v <= HI * 100 + 0.01 for v in new.values()), new)

    # 观察期：末位引擎在观察期内 → 不降它，若次末位也观察则不降任何；排名行标「观察期」
    worst_dim = rep2['ranked'][-1]['dim']
    new_obs, ch_obs = plan_adjust(fw, rep2['ranked'], rep2['samples'],
                                  observation={worst_dim: '2999-12-31'}, today='2026-11-07')
    print('obs worst=', worst_dim, 'changes=', ch_obs)
    ck('观察期内末位不降权', bool(ch_obs) and ch_obs[0]['dim'] != worst_dim, ch_obs)
    obs_all = {x['dim']: '2999-12-31' for x in rep2['ranked']}
    new_all, ch_all = plan_adjust(fw, rep2['ranked'], rep2['samples'],
                                  observation=obs_all, today='2026-11-07')
    ck('全部观察期→零变动', ch_all == [] and new_all == fw, (ch_all, new_all))
    rep_obs = weekly_report(many, observation={worst_dim: '2999-12-31'}, today='2026-11-07')
    ck('排行榜标观察期', any('观察期' in x for x in rep_obs['lines']), [x for x in rep_obs['lines'] if '观察期' in x])
    exp_new, ch_exp = plan_adjust(fw, rep2['ranked'], rep2['samples'],
                                  observation={worst_dim: '2020-01-01'}, today='2026-11-07')
    ck('观察期已过期→照常降权', bool(ch_exp) and ch_exp[0]['dim'] == worst_dim, ch_exp)

    # 下限保护：末位已在 10% 时不再降，且总和仍为 100
    low = {'jq': 10.0, 'lj': 30.0, 'zj': 30.0, 'tc': 15.0, 'dl': 15.0}
    new_l, ch_l = plan_adjust(low, rep2['ranked'], rep2['samples'])
    print('low case ch=', ch_l, 'new=', new_l)
    ck('下限10%不再降', all(v >= 10.0 - 0.01 for v in new_l.values()), new_l)
    ck('下限场景总和仍100', abs(sum(new_l.values()) - 100.0) < 0.5, sum(new_l.values()))
    print('[selftest] strategy_tournament RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 3


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    rows, _ = load_rows()
    obs = load_observation()
    rep = weekly_report(rows, observation=obs)
    print('样本=%d 记录=%d 观察期=%s 结论=%s' % (rep['samples'], rep['rows'], obs or '无', rep['conclusion']))
    for line in rep['lines']:
        print('  ' + line)
    if '--apply' in sys.argv:
        fw = load_fw()
        new, ch = plan_adjust(fw, rep['ranked'], rep['samples'], observation=obs)
        if apply_changes(new, ch, rep['samples']):
            print('已写入权重并记账: %s' % ch)
        else:
            print('无变动（样本不足或已到边界）')
