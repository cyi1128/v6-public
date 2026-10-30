# -*- coding: utf-8 -*-
"""腾讯兜底源验证：真实调用 + 模拟 9:25 前新浪无数据"""
import sys, os, json, datetime
sys.path.insert(0, r'D:\QuantMonitorV6')
import py_compile

print('=== 0) 编译 ===')
try:
    py_compile.compile(r'D:\QuantMonitorV6\ui\battle_widgets\auction_filter_widget.py', doraise=True)
    print('  通过')
except Exception as e:
    print('  失败:', e); sys.exit(1)

from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget as W
print('  _fetch_tencent_rank 存在:', hasattr(W, '_fetch_tencent_rank'))
print()

print('=== 1) 直接调腾讯兜底源 _fetch_tencent_rank ===')
print('  时间:', datetime.datetime.now().strftime('%H:%M:%S'))
fun = {'raw': 0, 'main': 0, 'px': 0, 'gap': 0, 'turn': 0, 'final': 0, 'source': 'sina'}
tw = W._fetch_tencent_rank(fun)
print('  返回条数:', len(tw))
print('  funnel  :', fun)
for r in tw[:10]:
    print('     %s %-6s 竞价价=%.2f 昨收=%.2f gap=%.2f%% 换手=%.2f%% 量比=%.2f 量=%.0f手' % (
        r['code'], r['name'][:6], r['price'], r['last_close'], r['gap'],
        r['jj_turnover'], r['em_vol_ratio'], r['jj_vol_lots']))
print()

print('=== 2) 正常路径仍应走新浪（当前 9:4x 新浪有数据） ===')
r2 = W._fetch_auction()
print('  source:', (r2.get('funnel') or {}).get('source'), ' funnel:', r2.get('funnel'))
print('  rows  :', len(r2.get('rows') or []))
print()

print('=== 3) 模拟 9:25 前：新浪返回空字符串 ===')
import utils.http_market_data as H
_real = H.http_get_with_retry
def fake_empty(url, **kw):
    if 'sina.com.cn' in url:
        return ''                      # 新浪无数据
    return _real(url, **kw)
H.http_get_with_retry = fake_empty
r3 = W._fetch_auction()
f3 = r3.get('funnel') or {}
print('  source:', f3.get('source'), ' funnel:', f3)
print('  note  :', r3.get('note'))
rows3 = r3.get('rows') or []
print('  rows  :', len(rows3))
for x in rows3[:10]:
    print('     %s %-6s gap=%.2f%% 现价=%.2f MA20=%.2f 量比=%s 分=%.1f' % (
        x['code'], x['name'][:6], x['gap'], x['price'], x.get('ma20') or 0,
        x.get('vol_ratio'), x.get('score', 0)))
print()

print('=== 4) 模拟 9:25 前：新浪返回整页全 0（真实观测到的形态） ===')
_zero_page = json.dumps([{'code': '920000', 'name': '安徽凤凰', 'changepercent': 0,
                          'open': 0, 'settlement': 14.29, 'trade': 0, 'volume': 0,
                          'amount': 0, 'turnoverratio': 0, 'nmc': 0}] * 80)
def fake_zero(url, **kw):
    if 'sina.com.cn' in url:
        return _zero_page
    return _real(url, **kw)
H.http_get_with_retry = fake_zero
r4 = W._fetch_auction()
f4 = r4.get('funnel') or {}
print('  source:', f4.get('source'), ' funnel:', f4)
print('  note  :', r4.get('note'))
print('  rows  :', len(r4.get('rows') or []))
print()

print('=== 5) 模拟两个源都无数据 ===')
def fake_all_dead(url, **kw):
    return ''
H.http_get_with_retry = fake_all_dead
r5 = W._fetch_auction()
print('  source:', (r5.get('funnel') or {}).get('source'))
print('  note  :', r5.get('note'))
print('  rows  :', len(r5.get('rows') or []))

H.http_get_with_retry = _real
print()
print('=== 6) 恢复真实函数，再跑一次确认新浪优先 ===')
r6 = W._fetch_auction()
print('  source:', (r6.get('funnel') or {}).get('source'), ' rows:', len(r6.get('rows') or []))
