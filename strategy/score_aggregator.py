# -*- coding: utf-8 -*-
"""统一评分仲裁层（工单1）

职责：把各评分引擎对同一只票的分数合成**唯一** final_score，并保留各子分。
红线：
  1. 某引擎缺分时，其权重按比例摊给其余引擎，**绝不硬算 50 分**。
  2. 权重总和恒为 1.0；文件里的权重不合法/和不为 1 时归一化，并记录。
  3. 一个有效分都没有时返回 final_score=None（报"无可用引擎"），不猜数。
  4. 每次变动/合成可落 data/aggregator_log.jsonl，便于工单2/4 追溯。

权重文件：config/aggregator_weights.json
  不存在时用 DEFAULT_WEIGHTS（工单1 指定）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

WEIGHT_FILE = 'config/aggregator_weights.json'
LOG_FILE = 'data/aggregator_log.jsonl'

# 工单1 指定的初始权重（5 组），总和 1.00
DEFAULT_WEIGHTS = {
    'ai_composite': 0.30,
    'auction_v3': 0.25,
    'factor_engine': 0.25,
    'nine_score': 0.10,
    'main_force': 0.10,
}

# 工单里点名、但初始权重表未覆盖的引擎：默认 0 权重，可后续在配置里抬起来
OPTIONAL_ENGINES = ('ai_520', 'factor_score', 'multi_factor')

_ENGINE_CN = {
    'ai_composite': 'AI综合',
    'auction_v3': '竞价v3',
    'factor_engine': '因子引擎',
    'nine_score': '九重',
    'main_force': '主力行为',
    'ai_520': 'AI520买点',
    'factor_score': '因子评分',
    'multi_factor': '多因子',
}


def _bj_now():
    return datetime.now(timezone(timedelta(hours=8)))


def engine_cn(name):
    return _ENGINE_CN.get(name, name)


def _valid_score(v):
    """只接受 0-100 的有限数字；None/字符串/bool/越界一律视为缺分。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f < 0 or f > 100:
        return None
    return round(f, 2)


def load_weights(path=WEIGHT_FILE, base_dir='.'):
    """读权重文件；缺文件/坏文件回退默认。返回 (weights, note)。"""
    full = path if os.path.isabs(path) else os.path.join(base_dir, path)
    if not os.path.exists(full):
        return dict(DEFAULT_WEIGHTS), 'default(no file)'
    try:
        with open(full, encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        return dict(DEFAULT_WEIGHTS), 'default(bad file: %s)' % str(e)[:40]
    if isinstance(raw, dict) and isinstance(raw.get('weights'), dict):
        raw = raw['weights']
    if not isinstance(raw, dict) or not raw:
        return dict(DEFAULT_WEIGHTS), 'default(empty)'
    w = {}
    for k, v in raw.items():
        s = _valid_score(v if not isinstance(v, float) else v * ((v <= 1.0) and 100 or 1))
        # 允许 0-1 小数或 0-100 百分数两种写法
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f < 0:
            continue
        w[k] = round(f / 100.0 if f > 1.0 else f, 6)
    total = sum(w.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS), 'default(non-positive)'
    norm = {k: round(v / total, 6) for k, v in w.items()}
    return norm, ('normalized from %.4f' % total if abs(total - 1.0) > 1e-6 else 'ok')


def aggregate(scores, weights=None, base_dir='.'):
    """合成唯一 final_score。

    scores: {'engine': 0-100 或 None}
    返回：{'final_score','ok','engines':[{name,name_cn,score,weight,status}],
            'missing':[...],'weights':{...},'note':str}
    """
    if weights is None:
        weights, note = load_weights(base_dir=base_dir)
    else:
        total = sum(weights.values())
        weights = {k: round(v / total, 6) for k, v in weights.items()} if total > 0 else {}
        note = 'explicit'
    scores = scores or {}
    present, missing = {}, []
    for name in set(list(weights.keys()) + list(scores.keys())):
        w = weights.get(name, 0.0)
        s = _valid_score(scores.get(name))
        if s is None:
            if w > 0:
                missing.append(name)
            continue
        present[name] = (s, w)
    if not present:
        return {'final_score': None, 'ok': False, 'engines': [],
                'missing': missing, 'weights': weights,
                'note': 'no valid engine score', 'reason': note}

    # 缺分引擎的权重按比例摊给其余引擎（按各自权重占比）
    wsum = sum(w for _, w in present.values())
    if wsum <= 0:  # 存在的引擎全被配成 0 权重：等权兜底，仍不编分
        share = {k: 1.0 / len(present) for k in present}
        note2 = 'equal(weight-zero)'
    else:
        share = {k: w / wsum for k, (_, w) in present.items()}
        note2 = note

    final = sum(s * share[k] for k, (s, _) in present.items())
    engines = []
    for name, (s, w) in sorted(present.items(), key=lambda kv: -share[kv[0]]):
        engines.append({'name': name, 'name_cn': engine_cn(name), 'score': s,
                        'weight': round(share[name], 4), 'status': 'ok'})
    for name in missing:
        engines.append({'name': name, 'name_cn': engine_cn(name), 'score': None,
                        'weight': 0.0, 'status': 'missing'})
    return {'final_score': round(final, 1), 'ok': True, 'engines': engines,
            'missing': missing, 'weights': weights, 'note': note2}


def fmt_final(result, top=3):
    """推送卡用的一行：唯一最终分 + 括号子分。缺分引擎不出现（不占位、不编值）。"""
    if not result or not result.get('ok'):
        return ''
    ok = [e for e in result['engines'] if e['status'] == 'ok' and e['weight'] > 0]
    subs = '|'.join('%s%.0f' % (e['name_cn'], e['score']) for e in ok[:top])
    return '综合分%.1f（%s）' % (result['final_score'], subs)


def log_append(result, code='', name='', slot='', base_dir='.'):
    full = os.path.join(base_dir, LOG_FILE)
    try:
        os.makedirs(os.path.dirname(full) or '.', exist_ok=True)
        with open(full, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                'ts': _bj_now().strftime('%Y-%m-%d %H:%M:%S'),
                'date': _bj_now().strftime('%Y-%m-%d'), 'slot': slot,
                'code': code, 'name': name,
                'final_score': result.get('final_score'),
                'engines': {e['name']: e['score'] for e in result.get('engines', [])},
                'missing': result.get('missing', []),
            }, ensure_ascii=False) + '\n')
        return True
    except Exception:
        return False
