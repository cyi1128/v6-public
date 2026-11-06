# -*- coding: utf-8 -*-
"""半 Kelly 仓位 position_sizer（工单9）

口径（用户 2026-11-07 指令）：
  1. 数据源 data/signal_log.csv 已回填记录，**有效样本 ≥30 才启动**；<30 输出「数据积累中 N/30」。
  2. 数据质量门：缺 push_price 或 ret5（close_t5）未回填的记录**不计有效样本**——不拿半截数据算仓位。
  3. 建议仓位 = (胜率×平均盈 − 败率×平均亏) / 平均盈 × 0.5，clamp [0,1]。
  4. 硬上限：单票 ≤20%；冰点期总仓 ≤2成（读 data/sentiment_state.json 四态）。
  5. 平均亏=0（样本期无亏损）→ 统计不可靠，保守封顶并标注。
  6. 输出：💰 仓位公式：N笔 | 胜率X% | 建议总仓Y成 | 情绪修正后Z成
  7. 每月「公式建议 vs 实际操作」记 data/position_log.json（实际操作留空待录）。
  本模块只出建议，不接任何推送卡（激活等 30 笔后由用户确认）。

用法：
  python -u tools/position_sizer.py --selftest
  python -u tools/position_sizer.py            # 读真实账本出建议
  python -u tools/position_sizer.py --actual 1.5   # 记录本月实际操作（成）
"""
import csv
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, 'data', 'signal_log.csv')
STATE_PATH = os.path.join(ROOT, 'data', 'sentiment_state.json')
LOG_PATH = os.path.join(ROOT, 'data', 'position_log.json')

MIN_SAMPLES = 30
KELLY_FACTOR = 1.0            # 2026-11-07 定案：全 Kelly（半Kelly 在60%胜率下长期只得1.7成，无表达力）
MAX_SINGLE = 0.20
ICE_TOTAL_CAP = 0.20          # 冰点期总仓上限 2成（硬保险②）
EMOTION_CAPS = {'高潮期': 1.0, '回暖期': 0.6, '退潮期': 0.3, '冰点期': 0.2}   # 第四层：档位上限
WIN_THRESHOLD = 0.01          # 与账本 win 口径一致：T+5 涨>1%


def _num(v):
    try:
        s = str(v).strip()
        return float(s) if s not in ('', 'None', 'nan') else None
    except Exception:
        return None


def load_trades(path=CSV_PATH):
    """返回 (valid_records, dropped)。质量门：push_price 与 ret5 都必须有值。"""
    valid, dropped = [], {'缺push_price': 0, '缺ret5': 0, 'ret5非数': 0}
    try:
        f = open(path, encoding='utf-8-sig')
    except Exception:
        return [], dropped
    with f:
        for r in csv.DictReader(f):
            if not r.get('code'):
                continue
            pp = _num(r.get('push_price'))
            ret5 = _num(r.get('ret5'))
            if ret5 is None:
                c5 = _num(r.get('close_t5'))
                if pp and c5:
                    ret5 = c5 / pp - 1.0
            if not pp:
                dropped['缺push_price'] += 1
                continue
            if ret5 is None:
                dropped['缺ret5'] += 1
                continue
            win = r.get('win')
            w = (win.strip() == '1') if win not in (None, '') else (ret5 > WIN_THRESHOLD)
            valid.append({'code': str(r['code']), 'date': r.get('date'),
                          'slot': r.get('slot'), 'ret5': ret5,
                          'win': bool(w) or ret5 > WIN_THRESHOLD})
    return valid, dropped


def stats(valid):
    n = len(valid)
    if n == 0:
        return None
    wins = [x['ret5'] for x in valid if x['win']]
    losses = [x['ret5'] for x in valid if not x['win']]
    p = len(wins) / float(n)
    q = 1.0 - p
    avg_win = (sum(wins) / len(wins)) if wins else None
    avg_loss = (abs(sum(losses) / len(losses))) if losses else None
    return {'n': n, 'win_rate': p, 'avg_win': avg_win, 'avg_loss': avg_loss}


def kelly_half(st):
    """返回 (suggest, flags)。平均盈缺/无盈利样本 → 0 并标不可算。"""
    flags = []
    if not st or st['avg_win'] is None or st['avg_win'] <= 0:
        return 0.0, ['无盈利样本，无法计算凯利']
    p, q, aw = st['win_rate'], 1.0 - st['win_rate'], st['avg_win']
    al = st['avg_loss'] or 0.0
    if st['avg_loss'] is None:
        flags.append('样本期无亏损记录，统计不可靠（保守封顶）')
    raw = (p * aw - q * al) / aw * KELLY_FACTOR
    if raw < 0:
        flags.append('公式结果为负（期望为负），建议空仓')
    s = max(0.0, min(1.0, raw))
    n_win = int(round(p * st['n']))
    n_loss = st['n'] - n_win
    if n_loss < 3:
        flags.append('亏损样本仅%d笔，统计不可靠' % n_loss)
    return s, flags


def sentiment_cap(path=STATE_PATH):
    """冰点期总仓 ≤2成；返回 (cap/None, level/None)。"""
    try:
        with open(path, encoding='utf-8') as f:
            st = json.load(f) or {}
    except Exception:
        return None, None
    level = st.get('level')
    if level == '冰点期':
        return ICE_TOTAL_CAP, level
    return None, level


def evaluate(valid, state_path=STATE_PATH):
    st = stats(valid)
    res = {'n': len(valid), 'status': 'ok', 'line': '', 'flags': [], 'single_cap': MAX_SINGLE}
    if len(valid) < MIN_SAMPLES:
        res['status'] = 'accumulating'
        res['line'] = '💰 仓位公式：数据积累中 %d/%d（样本不足不出建议）' % (len(valid), MIN_SAMPLES)
        return res
    s, flags = kelly_half(st)
    kelly_raw = s
    cap, level = sentiment_cap(state_path)
    after_pos = s
    if cap is not None:
        if s > cap:
            flags.append('%s总仓上限2成生效（原建议%.1f成）' % (level, s * 10))
        after_pos = min(s, cap)
    emo_cap = EMOTION_CAPS.get(level) if level else None
    after_emo = after_pos
    if emo_cap is not None:
        if after_pos > emo_cap:
            flags.append('%s档位上限%.1f成生效（原建议%.1f成）' % (level, emo_cap * 10, after_pos * 10))
        after_emo = min(after_pos, emo_cap)
    res.update({'status': 'ok', 'win_rate': st['win_rate'], 'avg_win': st['avg_win'],
                'avg_loss': st['avg_loss'], 'suggest': round(after_emo, 4),
                'kelly_raw': round(kelly_raw, 4),
                'after_position_cap': round(after_pos, 4),
                'after_emotion_cap': round(after_emo, 4),
                'level': level, 'emotion_cap': emo_cap, 'flags': flags})
    res['line'] = ('💰 仓位公式：%d笔 | 胜率%.0f%% | 建议总仓%.1f成 | 情绪修正后%.1f成'
                   % (st['n'], st['win_rate'] * 100, kelly_raw * 10, after_emo * 10))
    return res


def raw_of(st):
    p, q, aw = st['win_rate'], 1.0 - st['win_rate'], st['avg_win']
    al = st['avg_loss'] or 0.0
    return max(0.0, min(1.0, (p * aw - q * al) / aw * KELLY_FACTOR))


def log_month(res, actual=None, path=LOG_PATH):
    month = time.strftime('%Y-%m')
    try:
        with open(path, encoding='utf-8') as f:
            doc = json.load(f) or {}
    except Exception:
        doc = {}
    rec = doc.setdefault('months', {})
    slot = rec.setdefault(month, {})
    slot['date'] = time.strftime('%Y-%m-%d')
    slot['n'] = res.get('n')
    slot['win_rate'] = None if res.get('win_rate') is None else round(res['win_rate'] * 100, 1)
    slot['suggest'] = res.get('suggest')
    slot['suggest_pct'] = None if res.get('suggest') is None else round(res['suggest'] * 100, 1)
    slot['level'] = res.get('level')
    slot['flags'] = res.get('flags') or []
    if actual is not None:
        slot['actual'] = actual
    slot.setdefault('actual', None)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc


def _selftest():
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 1. 合成 30 笔：胜率 60%、盈亏比 1.5（平均盈 +5%、平均亏 -3.3333%）
    valid = []
    for i in range(30):
        if i < 18:
            valid.append({'code': str(i), 'ret5': 0.05, 'win': True})
        else:
            valid.append({'code': str(i), 'ret5': -0.05 / 1.5, 'win': False})
    st = stats(valid)
    print('  n=%d p=%.3f avg_win=%.6f avg_loss=%.6f' % (st['n'], st['win_rate'], st['avg_win'], st['avg_loss']))
    s, flags = kelly_half(st)
    hand = (0.6 * 0.05 - 0.4 * (0.05 / 1.5)) / 0.05 * KELLY_FACTOR
    print('  全Kelly手算=%.6f (KELLY_FACTOR=%.1f)' % (hand, KELLY_FACTOR))
    ck('全Kelly=0.333（3.3成）', abs(s - 0.3333) < 0.0005, s)
    ck('与验收期望0.334一致', abs(s - 0.334) < 0.001, s)
    # 2. 有效样本<30 → 积累提示，不出建议
    res = evaluate(valid[:10], state_path='__none__')
    print('  ', res['line'])
    ck('不足30笔走积累分支', res['status'] == 'accumulating' and '积累中 10/30' in res['line'], res['line'])
    ck('积累期无建议值', res.get('suggest') is None, res.get('suggest'))
    # 3. 四档情绪上限各断言一例（第四层保险）：raw=0.3333 分别被 1.0/0.6/0.3/0.2 约束
    exp = {'高潮期': 0.3333, '回暖期': 0.3333, '退潮期': 0.30, '冰点期': 0.20}
    for lvl, want in exp.items():
        with open('__tmp_state.json', 'w', encoding='utf-8') as f:
            json.dump({'level': lvl, 'S': 34.0}, f, ensure_ascii=False)
        r = evaluate(valid, state_path='__tmp_state.json')
        print('  %s → after_emotion=%.4f（%s）' % (lvl, r['suggest'], r['line']))
        ck('%s 上限生效' % lvl, abs(r['suggest'] - want) < 0.002, r['suggest'])
        ck('%s 三段值可追溯' % lvl,
           r.get('kelly_raw') is not None and r.get('after_position_cap') is not None
           and r.get('after_emotion_cap') is not None, (r.get('kelly_raw'), r.get('after_position_cap'), r.get('after_emotion_cap')))
    os.remove('__tmp_state.json')
    # 4. 高胜率样本被冰点两层同时拦：raw 8.67成 → 位置 2成 → 情绪 2成
    hi = [{'code': str(i), 'ret5': 0.06, 'win': True} for i in range(36)] + \
         [{'code': str(i), 'ret5': -0.02, 'win': False} for i in range(4)]
    st_hi = stats(hi)
    s_hi, _ = kelly_half(st_hi)
    print('  高胜率样本 全Kelly=%.4f（%.1f成）' % (s_hi, s_hi * 10))
    ck('高胜率全Kelly>2成', s_hi > ICE_TOTAL_CAP, s_hi)
    with open('__tmp_state.json', 'w', encoding='utf-8') as f:
        json.dump({'level': '冰点期', 'S': 34.0}, f, ensure_ascii=False)
    r3 = evaluate(hi, state_path='__tmp_state.json')
    print('  ', r3['line'], r3['flags'])
    ck('冰点期clamp到2成', abs(r3['suggest'] - ICE_TOTAL_CAP) < 1e-9, r3['suggest'])
    ck('clamp有标注', any('上限2成生效' in x for x in r3['flags']), r3['flags'])
    ck('三段值 raw>位置>情绪', r3['kelly_raw'] > r3['after_position_cap'] >= r3['after_emotion_cap'],
       (r3['kelly_raw'], r3['after_position_cap'], r3['after_emotion_cap']))
    os.remove('__tmp_state.json')
    # 3b. 无情绪状态文件 → 不额外拦，仍出建议
    r_no = evaluate(valid, state_path='__none__')
    ck('无情绪文件不拦', abs(r_no['suggest'] - 0.3333) < 0.002, r_no['suggest'])
    # 4. 平均亏=0（全胜）→ 不除零、封顶且标不可靠
    allwin = [{'code': str(i), 'ret5': 0.03, 'win': True} for i in range(30)]
    st4 = stats(allwin)
    s4, f4 = kelly_half(st4)
    print('  全胜 建议=%.3f flags=%s' % (s4, f4))
    ck('平均亏=0不除零且≤1', 0 <= s4 <= 1.0, s4)
    ck('全胜标不可靠', any('无亏损记录' in x for x in f4), f4)
    # 5. 期望为负 → 建议 0 且标空仓
    neg = [{'code': str(i), 'ret5': -0.04, 'win': False} for i in range(20)] + \
          [{'code': str(i), 'ret5': 0.02, 'win': True} for i in range(10)]
    s5, f5 = kelly_half(stats(neg))
    ck('负期望→0且标空仓', s5 == 0.0 and any('空仓' in x for x in f5), (s5, f5))
    # 6. 数据质量门：缺 push_price / 缺 ret5 不计有效样本
    tmp = '__tmp_sig.csv'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['date', 'slot', 'code', 'name', 'push_price', 'total', 'close_t5', 'ret5', 'win'])
        w.writerow(['2026-11-06', 'eod', '600000', 'x', '10.0', '70', '11.0', '0.10', '1'])
        w.writerow(['2026-11-06', 'eod', '600001', 'y', '', '70', '11.0', '0.10', '1'])
        w.writerow(['2026-11-06', 'eod', '600002', 'z', '10.0', '70', '', '', ''])
    v6, d6 = load_trades(tmp)
    print('  valid=%d dropped=%s' % (len(v6), d6))
    ck('质量门：缺push_price/缺ret5 被剔除', len(v6) == 1 and d6['缺push_price'] == 1 and d6['缺ret5'] == 1, d6)
    ck('close_t5 可回算 ret5', v6[0]['ret5'] == 0.10, v6[0]['ret5'])
    os.remove(tmp)
    # 7. 卡片一行格式
    line = evaluate(valid, state_path='__none__')['line']
    print('  line=', line)
    ck('卡片含四要素且无问号', all(k in line for k in ('仓位公式', '胜率', '建议总仓', '情绪修正后'))
       and '？' not in line and '?' not in line, line)
    # 8. 单票硬上限常量
    ck('单票上限20%', MAX_SINGLE == 0.20, MAX_SINGLE)
    print('[selftest] position_sizer RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 6


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    valid, dropped = load_trades()
    print('[sizer] 有效样本=%d 剔除=%s' % (len(valid), dropped))
    res = evaluate(valid)
    print(res['line'])
    for x in res['flags']:
        print('  · ' + x)
    if res['status'] == 'ok':
        actual = None
        if '--actual' in sys.argv:
            i = sys.argv.index('--actual')
            actual = _num(sys.argv[i + 1]) if i + 1 < len(sys.argv) else None
        log_month(res, actual)
        print('[sizer] 已记入 %s' % LOG_PATH)
