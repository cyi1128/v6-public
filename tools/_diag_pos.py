# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\QuantMonitorV6')
from services.band_pattern_engine import _load_bars, _is_main_a_share, _is_st
from utils.stock_name_manager import get_all_stock_names

raw = get_all_stock_names()
c2n = {}
for _n, _c in raw.items():
    if _c not in c2n:
        c2n[_c] = _n

cnt = 0
for code, name in c2n.items():
    if not _is_main_a_share(code):
        continue
    if _is_st(name):
        continue
    bars = _load_bars(code)
    if len(bars) < 60:
        continue
    recent = bars[-40:-1]
    r_low = min(b['low'] for b in recent)
    r_high = max(b['high'] for b in recent)
    cur = bars[-1]['close']
    print(f'{code} {name[:6]:8s} bars[-1]={bars[-1]["date"][:10]} close={cur:.2f} | '
          f'recent {recent[0]["date"][:10]}~{recent[-1]["date"][:10]} | '
          f'r_low={r_low:.2f} r_high={r_high:.2f} | pos={(cur-r_low)/(r_high-r_low)*100:.1f}%')
    cnt += 1
    if cnt >= 12:
        break

print()
print('--- 检查 bars 是否升序 ---')
bars = _load_bars('600050')
if bars:
    print('前3根日期:', [b['date'][:10] for b in bars[:3]])
    print('后3根日期:', [b['date'][:10] for b in bars[-3:]])
    print('总根数:', len(bars))
    print('最后一根完整数据:', bars[-1])
    print('倒数第二根完整数据:', bars[-2])
