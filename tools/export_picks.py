# -*- coding: utf-8 -*-
"""从本地控盘快照导出前50只候选股，供云端DeepSeek研判。只读，不改原快照。"""
import json
import os
import sys
from datetime import datetime

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'cache', 'control_screen.json')
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_picks.json')
VERSION = '1.0'
TOP_N = 50


def export():
    if not os.path.exists(SRC):
        print(f'[export] 源文件不存在: {SRC}')
        return False
    try:
        with open(SRC, encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        print(f'[export] 快照损坏: {e}')
        return False
    rows = d.get('rows') or []
    if not rows:
        print('[export] 快照为空')
        return False
    # 按 score 降序（控盘分越高越靠前），score 缺失排最后
    rows.sort(key=lambda x: x.get('score') or -1, reverse=True)
    picks = []
    for r in rows[:TOP_N]:
        picks.append({
            'code': r.get('code'),
            'name': r.get('name'),
            'price': r.get('price'),
            'pct': r.get('pct'),
            'score': r.get('score'),
            'stage': r.get('stage'),
            'pos': r.get('pos'),
            'theme': r.get('theme'),
            'label': r.get('label'),
            'note': r.get('note'),
            'observe': r.get('observe'),
        })
    out = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_saved_at': d.get('saved_at'),
        'source_data_date': d.get('data_date'),
        'version': VERSION,
        'count': len(picks),
        'picks': picks,
    }
    # 先写临时文件再替换，避免中断损坏
    tmp = DST + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DST)
    print(f'[export] OK {len(picks)}只 -> {DST}')
    print(f'[export] 源数据日: {d.get("data_date")}  快照保存: {d.get("saved_at")}')
    return True


if __name__ == '__main__':
    sys.exit(0 if export() else 1)
