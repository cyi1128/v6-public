# -*- coding: utf-8 -*-
"""实跑竞价模块：1) 新浪接口连通性 2) 全流程 _fetch_auction 3) 快照"""
import sys, json, datetime
sys.path.insert(0, r'D:\QuantMonitorV6')

print('=== 当前时间 ===', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print()

# 1) 新浪接口连通性
from utils.http_market_data import http_get_with_retry
url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
       'Market_Center.getHQNodeData?page=1&num=5&sort=changepercent&asc=0'
       '&node=hs_a&symbol=&_s_r_a=auto')
try:
    text = http_get_with_retry(url, encoding='gbk',
                               referer='https://finance.sina.com.cn', timeout=10)
    print('=== 新浪接口原始返回（前5条） ===')
    if text:
        arr = json.loads(text)
        print('  条数:', len(arr))
        for it in arr[:5]:
            print('  %s %s changepercent=%s open=%s settlement=%s trade=%s turnoverratio=%s volume=%s amount=%s' % (
                it.get('code'), it.get('name'), it.get('changepercent'), it.get('open'),
                it.get('settlement'), it.get('trade'), it.get('turnoverratio'),
                it.get('volume'), it.get('amount')))
    else:
        print('  返回空！')
except Exception as e:
    print('  新浪接口失败:', type(e).__name__, e)
print()

# 2) 全流程
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget
print('=== _fetch_auction 全流程 ===')
res = AuctionFilterWidget._fetch_auction()
rows = res.get('rows') or []
print('  note:', res.get('note'))
print('  最终行数:', len(rows))
for r in rows[:10]:
    print('  %s %-6s gap=%.2f%% 现价=%.2f 量比=%s MA20=%s 分=%.1f 题材=%s' % (
        r.get('code'), (r.get('name') or '')[:6], r.get('gap', 0), r.get('price', 0),
        r.get('vol_ratio'), r.get('ma20'), r.get('score', 0),
        (r.get('theme') or r.get('industry') or '')[:20]))
print()

# 3) 快照
print('=== 竞价快照 ===')
try:
    from services import intraday_snapshot as snap
    import os
    p = r'D:\QuantMonitorV6\data\cache\auction_snapshot.duckdb'
    print('  快照库存在:', os.path.exists(p), '大小:', os.path.getsize(p) if os.path.exists(p) else 0)
    for d in ['2026-09-24', '2026-09-23', '2026-09-22']:
        try:
            data = snap.load_section(d, 'auction') or {}
            print('  %s -> rows=%d saved_at=%s' % (d, len(data.get('rows') or []), data.get('saved_at')))
        except Exception as e:
            print('  %s -> 读取失败 %s' % (d, e))
except Exception as e:
    print('  intraday_snapshot 导入失败:', e)
