# -*- coding: utf-8 -*-
"""
模式四 · G组 43 只叠加"结构位置"阈值验证（只统计，不修改 band_pattern_engine.py）

G组 = 1.1倍满足率≥50% + 最近3个交易日出现≥1.1倍 + 下跌日≤前5日均量×1.0 满足率≥60%

在此基础上叠加结构位置阈值：≥60% / ≥65% / ≥70% / ≥75% / ≥80%

结构位置 = (当前价 - 结构下沿) / (结构上沿 - 结构下沿) * 100
  结构区间 = bars[-40:-1]（不含最新一根K线）
  结构下沿 = 区间内最低价，结构上沿 = 区间内最高价
  当前价   = bars[-1].close

前5日均量口径（严格）：volumes[i-5:i]，不含当根、不含未来K线

输出：
  tools/pattern4_G_position_validation.txt
  tools/pattern4_G_position_validation.csv
"""
import sys, os, csv, statistics as st
sys.path.insert(0, r'D:\QuantMonitorV6')
from services.band_pattern_engine import _load_bars, _ma, _to_weekly, _is_main_a_share, _is_st
from utils.stock_name_manager import get_all_stock_names

OUT_DIR = r'D:\QuantMonitorV6\tools'
TXT = os.path.join(OUT_DIR, 'pattern4_G_position_validation.txt')
CSV = os.path.join(OUT_DIR, 'pattern4_G_position_validation.csv')
os.makedirs(OUT_DIR, exist_ok=True)

LOG = []


def emit(s=''):
    LOG.append(s)
    print(s, flush=True)


def pct(a, b):
    return (a - b) / b * 100 if b else 0.0


# ================= 1. 结构候选 =================
raw = get_all_stock_names()
c2n = {}
for _n, _c in raw.items():
    if _c not in c2n:
        c2n[_c] = _n
items = [(c, n) for c, n in c2n.items() if _is_main_a_share(c)]
emit(f'[扫描] 主板 {len(items)} 只')

cands = []
for code, name in items:
    if _is_st(name):
        continue
    bars = _load_bars(code)
    if len(bars) < 60:
        continue
    closes = [b['close'] for b in bars]
    ma5 = _ma(closes, 5)
    if not ma5 or not _ma(closes, 20):
        continue
    if len(_to_weekly(bars)) < 10:
        continue
    recent = bars[-40:-1]
    if len(recent) < 15:
        continue
    r_high = max(b['high'] for b in recent)
    r_low = min(b['low'] for b in recent)
    if r_low <= 0 or (r_high - r_low) / r_low > 0.25:
        continue
    half = len(recent) // 2
    if half >= 3 and min(b['low'] for b in recent[half:]) <= min(b['low'] for b in recent[:half]):
        continue
    if len(closes) >= 10:
        m5p = _ma(closes[:-5], 5)
        if m5p and ma5 < m5p:
            continue
    cands.append({'code': code, 'name': name, 'bars': bars, 'recent': recent})

emit(f'[结构候选] {len(cands)} 只\n')

# ================= 2. 逐只计算 =================
all_rows = []

for c in cands:
    bars = c['bars']
    recent = c['recent']
    r_high = max(b['high'] for b in recent)
    r_low = min(b['low'] for b in recent)
    vols = [b['volume'] for b in bars]
    closes = [b['close'] for b in bars]
    recent_start = len(bars) - 40
    end_idx = recent_start + len(recent) - 1
    last_i = len(bars) - 1
    cur = closes[-1]

    up, dn = [], []
    for k, b in enumerate(recent):
        i = recent_start + k
        if i < 5:
            continue
        p5 = sum(vols[i-5:i]) / 5.0
        if p5 <= 0:
            continue
        ratio = b['volume'] / p5
        (up if b['close'] > b['open'] else dn).append((b['date'][:10], ratio, i))

    n_up, n_dn = len(up), len(dn)
    if n_up == 0:
        continue

    rate11 = sum(1 for x in up if x[1] >= 1.1) / n_up * 100
    dn_rate = (sum(1 for x in dn if x[1] <= 1.0) / n_dn * 100) if n_dn else 0.0
    cutoff3 = end_idx - 2
    f11_3 = any(x[1] >= 1.1 and x[2] >= cutoff3 for x in up)

    hit = [x for x in up if x[1] >= 1.1]
    last_vol = hit[-1] if hit else None

    l5 = [b['low'] for b in bars[-5:]]
    low_rising = (min(l5) > min(b['low'] for b in bars[-10:-5])) if len(bars) >= 10 else False
    m5_now = _ma(closes, 5)
    m5_ago = _ma(closes[:-5], 5)
    ma5_up = (m5_now > m5_ago) if (m5_now and m5_ago) else False

    if last_vol:
        gi = last_vol[2]
        after = bars[gi+1:]
        base = closes[gi]
        max_pb = pct(base, min(b['low'] for b in after)) if after else 0.0
        gap = last_i - gi
    else:
        max_pb = 0.0
        gap = -1

    span = r_high - r_low
    pos = (cur - r_low) / span * 100 if span > 0 else 0.0
    in_range = (r_low <= cur <= r_high)
    break_top = cur > r_high

    if cur > r_high * 1.10:
        cls = '已明显偏离结构(上)'
    elif cur > r_high:
        cls = '已突破'
    elif cur < r_low * 0.90:
        cls = '已明显偏离结构(下)'
    elif cur < r_low:
        cls = '已破坏结构'
    elif max_pb >= 8:
        cls = '放量后回落'
    else:
        cls = '仍保持结构完整'

    all_rows.append({
        'code': c['code'], 'name': c['name'],
        'start': recent[0]['date'][:10], 'end': recent[-1]['date'][:10],
        'days': len(recent), 'n_up': n_up, 'n_dn': n_dn,
        'rate11': rate11, 'dn_rate': dn_rate, 'f11_3': f11_3,
        'low_rising': low_rising, 'ma5_up': ma5_up,
        'gap': gap, 'vol_date': last_vol[0] if last_vol else '',
        'cur': cur, 'r_low': r_low, 'r_high': r_high,
        'pos': pos, 'in_range': in_range, 'break_top': break_top,
        'up_dist': pct(r_high, cur),          # 当前价距结构上沿（%）
        'cls': cls,
    })

G = [r for r in all_rows if r['rate11'] >= 50 and r['f11_3'] and r['dn_rate'] >= 60]
ALLN = len(all_rows)
GN = len(G)

emit(f'[G组] {GN} 只')
emit(f'[对照·全部结构候选] {ALLN} 只\n')

# ================= 3. CSV =================
THS = [60, 65, 70, 75, 80]
with open(CSV, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['股票代码', '股票名称', '横盘开始', '横盘结束', '结构天数',
                '1.1倍满足率', '下跌缩量满足率', '结构位置%',
                '当前价', '结构下沿', '结构上沿', '当前价距结构上沿%',
                '是否在结构区间内', '是否突破结构上沿', '结构分类',
                '低点抬高', 'MA5走平向上', '最近3日放量',
                '最近放量日', '最近放量距最新K线交易日'] +
               [f'入选位置≥{t}%' for t in THS])
    for r in sorted(G, key=lambda x: -x['pos']):
        w.writerow([r['code'], r['name'], r['start'], r['end'], r['days'],
                    round(r['rate11'], 1), round(r['dn_rate'], 1), round(r['pos'], 1),
                    round(r['cur'], 2), round(r['r_low'], 2), round(r['r_high'], 2),
                    round(r['up_dist'], 2),
                    '是' if r['in_range'] else '否', '是' if r['break_top'] else '否', r['cls'],
                    '是' if r['low_rising'] else '否', '是' if r['ma5_up'] else '否',
                    '是' if r['f11_3'] else '否',
                    r['vol_date'], r['gap'] if r['gap'] >= 0 else '从未'] +
                   ['是' if r['pos'] >= t else '否' for t in THS])

# ================= 4. 报告 =================
emit('=' * 92)
emit('模式四 · G组43只 叠加"结构位置"阈值验证报告')
emit('=' * 92)
emit('G组 = 1.1倍满足率≥50% + 最近3日出现≥1.1倍 + 下跌缩量≥60%')
emit('结构位置 = (当前价 - 结构下沿) / (结构上沿 - 结构下沿) × 100')
emit('结构区间 = bars[-40:-1]（不含最新一根K线）；当前价 = bars[-1].close')
emit()

# --- 一、各档数量与占比 ---
emit('=' * 92)
emit('【一】各档股票数量与占比')
emit('=' * 92)
emit(f'{"阈值":10s}{"股票数":>8s}{"占G组43只":>14s}{"占原517只":>14s}')
for t in THS:
    n = sum(1 for r in G if r['pos'] >= t)
    emit(f'{"≥"+str(t)+"%":10s}{n:>8d}{n/GN*100:>13.1f}%{n/ALLN*100:>13.1f}%')

# --- 二、各档结构质量 ---
emit()
emit('=' * 92)
emit('【二】各档结构质量指标')
emit('=' * 92)
emit(f'{"阈值":8s}{"股票数":>7s}{"结构完整":>10s}{"低点抬高":>10s}{"MA5向上":>10s}'
     f'{"近3日放量":>11s}{"放量距离":>10s}{"距上沿%":>10s}{"已突破":>8s}')
for t in THS:
    sub = [r for r in G if r['pos'] >= t]
    if not sub:
        emit(f'{"≥"+str(t)+"%":8s}{0:>7d}{"—":>10s}')
        continue
    n = len(sub)
    c_full = sum(1 for r in sub if r['cls'] == '仍保持结构完整')
    c_low = sum(1 for r in sub if r['low_rising'])
    c_ma = sum(1 for r in sub if r['ma5_up'])
    c_f3 = sum(1 for r in sub if r['f11_3'])
    gaps = [r['gap'] for r in sub if r['gap'] >= 0]
    gap_med = st.median(gaps) if gaps else -1
    up_med = st.median([r['up_dist'] for r in sub])
    c_break = sum(1 for r in sub if r['break_top'])
    emit(f'{"≥"+str(t)+"%":8s}{n:>7d}'
         f'{c_full/n*100:>9.1f}%{c_low/n*100:>9.1f}%{c_ma/n*100:>9.1f}%'
         f'{c_f3/n*100:>10.1f}%{gap_med:>10.1f}{up_med:>9.2f}%{c_break:>8d}')
emit()
emit('  （"放量距离"= 最近放量日距最新K线的交易日数中位数，越小越新鲜）')
emit('  （"距上沿%"= 当前价距结构上沿的空间中位数，越小越接近突破）')

# --- 三、各档股票清单 ---
emit()
emit('=' * 92)
emit('【三】各档入选股票清单')
emit('=' * 92)
for t in THS:
    sub = sorted([r for r in G if r['pos'] >= t], key=lambda x: -x['pos'])
    emit()
    emit(f'--- 结构位置 ≥ {t}% ：{len(sub)} 只 ---')
    if not sub:
        emit('    （无）')
        continue
    for i, r in enumerate(sub, 1):
        emit(f'  {i:3d}. {r["code"]} {r["name"][:8]:10s} 位置={r["pos"]:5.1f}%  '
             f'距上沿={r["up_dist"]:5.2f}%  涨日={r["n_up"]:2d}  1.1倍={r["rate11"]:5.1f}%  '
             f'跌缩量={r["dn_rate"]:5.1f}%  {r["cls"]}')

# --- 四、重点：≥70% 的四项同时满足 ---
emit()
emit('=' * 92)
emit('【四】重点：结构位置≥70% 的 G 组股票中，同时满足四项条件的数量')
emit('=' * 92)
emit('四项条件 = 低点抬高 AND MA5走平向上 AND 最近3日放量 AND 仍保持结构完整')
emit()
sub70 = [r for r in G if r['pos'] >= 70]
full = [r for r in sub70 if r['low_rising'] and r['ma5_up'] and r['f11_3']
        and r['cls'] == '仍保持结构完整']
emit(f'  结构位置≥70% 的 G 组股票      : {len(sub70):3d} 只')
emit(f'  其中四项条件同时满足          : {len(full):3d} 只')
emit(f'  占≥70%档比例                 : {len(full)/len(sub70)*100 if sub70 else 0:5.1f}%')
emit(f'  占G组43只比例                : {len(full)/GN*100:5.1f}%')
emit(f'  占原517只比例                : {len(full)/ALLN*100:5.1f}%')
emit()
if full:
    emit('  四项同时满足清单：')
    for i, r in enumerate(sorted(full, key=lambda x: -x['pos']), 1):
        emit(f'    {i:2d}. {r["code"]} {r["name"][:8]:10s} 位置={r["pos"]:5.1f}%  '
             f'距上沿={r["up_dist"]:5.2f}%  放量距最新={r["gap"]}日')

# --- 五、逐项条件在 G 组的达标率（作为基线） ---
emit()
emit('=' * 92)
emit('【五】G组43只基线（未加位置阈值）')
emit('=' * 92)
emit(f'  G组总数                      : {GN} 只')
emit(f'  结构仍完整                    : {sum(1 for r in G if r["cls"]=="仍保持结构完整")} 只'
     f'  ({sum(1 for r in G if r["cls"]=="仍保持结构完整")/GN*100:.1f}%)')
emit(f'  低点抬高                     : {sum(1 for r in G if r["low_rising"])} 只'
     f'  ({sum(1 for r in G if r["low_rising"])/GN*100:.1f}%)')
emit(f'  MA5走平向上                   : {sum(1 for r in G if r["ma5_up"])} 只'
     f'  ({sum(1 for r in G if r["ma5_up"])/GN*100:.1f}%)')
emit(f'  最近3日放量                   : {sum(1 for r in G if r["f11_3"])} 只'
     f'  ({sum(1 for r in G if r["f11_3"])/GN*100:.1f}%)')
emit(f'  已突破结构上沿                 : {sum(1 for r in G if r["break_top"])} 只')
gaps = [r['gap'] for r in G if r['gap'] >= 0]
emit(f'  最近放量距最新K线(中位数)        : {st.median(gaps):.1f} 个交易日')
emit(f'  当前价距结构上沿(中位数)         : {st.median([r["up_dist"] for r in G]):.2f}%')
emit(f'  结构位置(中位数)               : {st.median([r["pos"] for r in G]):.1f}%')

emit()
emit('=' * 92)
emit(f'CSV 已写入: {CSV}')
emit(f'报告已写入: {TXT}')

with open(TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(LOG))
print('\n完成')
