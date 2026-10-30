# -*- coding: utf-8 -*-
"""竞价筛选漏斗：逐层统计每层砍掉多少只"""
import sys, json, datetime
sys.path.insert(0, r'D:\QuantMonitorV6')
from utils.http_market_data import http_get_with_retry
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget as W
from ui.battle_widgets.auction_filter_widget import _is_main_a_share, _is_st

print('=== 时间', datetime.datetime.now().strftime('%H:%M:%S'), '===')
print()

# ---- 第0层：原始拉取 ----
all_items = []
page_stats = []
for pn in range(1, 16):
    url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
           'Market_Center.getHQNodeData?page=%d&num=80&sort=changepercent&asc=0'
           '&node=hs_a&symbol=&_s_r_a=auto' % pn)
    try:
        text = http_get_with_retry(url, encoding='gbk',
                                   referer='https://finance.sina.com.cn', timeout=10)
        arr = json.loads(text) if text else []
    except Exception as e:
        page_stats.append((pn, 'ERR', str(e)[:40]))
        break
    if not arr:
        page_stats.append((pn, 0, 'break:空'))
        break
    all_items.extend(arr)
    lastcp = float(arr[-1].get('changepercent', 0) or 0)
    page_stats.append((pn, len(arr), '末条涨幅=%.2f' % lastcp))
    if lastcp < 1.5:
        break

print('【第0层】新浪分页拉取')
for s in page_stats:
    print('   第%s页: %s' % (s[0], s[1:]))
print('   累计原始条数: %d' % len(all_items))
nz = sum(1 for it in all_items if float(it.get('changepercent') or 0) != 0)
print('   其中涨幅非0条数: %d  <-- 若为0说明新浪此刻没有竞价数据' % nz)
print()

# ---- 第1层：主板 + 非ST ----
main_rows = []
for it in all_items:
    code = str(it.get('code', '') or '').strip()
    name = str(it.get('name', '') or '').strip()
    if not _is_main_a_share(code):
        continue
    if _is_st(name):
        continue
    main_rows.append(it)
print('【第1层】主板+非ST: %d 只（砍掉 %d）' % (len(main_rows), len(all_items) - len(main_rows)))

# ---- 第2层：open/昨收 有效 ----
valid_px = []
for it in main_rows:
    try:
        lc = float(it.get('settlement') or 0)
        op = float(it.get('open') or 0)
    except Exception:
        continue
    if lc <= 0 or op <= 0:
        continue
    valid_px.append(it)
print('【第2层】今开/昨收有效: %d 只（砍掉 %d）  <-- 9:25前 open=0，这层会全砍光'
      % (len(valid_px), len(main_rows) - len(valid_px)))

# ---- 第3层：缺口 2%~7% ----
gap_ok = []
for it in valid_px:
    lc = float(it.get('settlement') or 0)
    op = float(it.get('open') or 0)
    gap = (op - lc) / lc * 100.0
    if gap > 7.0 or gap < 2.0:
        continue
    gap_ok.append(it)
print('【第3层】缺口 2%%~7%%: %d 只（砍掉 %d）' % (len(gap_ok), len(valid_px) - len(gap_ok)))

# ---- 第4层：换手 0.5%~15% ----
to_ok = []
for it in gap_ok:
    try:
        to = float(it.get('turnoverratio') or 0)
    except Exception:
        continue
    if to < 0.5 or to > 15:
        continue
    to_ok.append(it)
print('【第4层】换手 0.5%%~15%%: %d 只（砍掉 %d）' % (len(to_ok), len(gap_ok) - len(to_ok)))

# ---- 第5层：全流程（含 kline/题材/MA20） ----
res = W._fetch_auction()
rows = res.get('rows') or []
print('【第5层】完整流程最终: %d 只   note=%s' % (len(rows), res.get('note')))
print()

# ---- 被MA20/次新/高位砍掉多少 ----
raw = []
for it in to_ok:
    code = str(it.get('code', '') or '').strip()
    name = str(it.get('name', '') or '').strip()
    lc = float(it.get('settlement') or 0)
    op = float(it.get('open') or 0)
    price = float(it.get('trade') or op)
    raw.append({'code': code, 'name': name, 'price': price, 'open': op,
                'last_close': lc, 'gap': (op - lc) / lc * 100.0,
                'cur_pct': float(it.get('changepercent') or 0),
                'jj_turnover': float(it.get('turnoverratio') or 0),
                'jj_vol_shares': float(it.get('volume') or 0),
                'cur_amount': float(it.get('amount') or 0) / 1e8,
                'em_vol_ratio': 0.0, 'circ_mv_yi': float(it.get('nmc') or 0),
                'industry': '', 'concepts_raw': ''})
W._enrich_with_kline(raw)
newstock = [r for r in raw if r.get('is_new_stock')]
highpos = [r for r in raw if r.get('high_pos')]
ma20_less = [r for r in raw if not r.get('is_new_stock') and not r.get('high_pos')
             and (r.get('ma20') or 0) > 0 and (r.get('price') or 0) < (r.get('ma20') or 0)]
survive = [r for r in raw if not r.get('is_new_stock') and not r.get('high_pos')
           and not ((r.get('ma20') or 0) > 0 and (r.get('price') or 0) < (r.get('ma20') or 0))]
print('【第5层细分】进入打分池 %d 只：' % len(raw))
print('   次新股剔除: %d' % len(newstock))
print('   高位股(距60日低>100%%)剔除: %d' % len(highpos))
print('   现价<MA20 硬过滤剔除: %d' % len(ma20_less))
print('   存活: %d' % len(survive))
for r in survive:
    print('      %s %s gap=%.2f%% price=%.2f ma20=%.2f' % (
        r['code'], r['name'], r['gap'], r['price'], r.get('ma20') or 0))
