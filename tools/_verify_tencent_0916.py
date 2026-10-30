# -*- coding: utf-8 -*-
"""模拟 9:16（9:25 前）验证腾讯兜底真正启动"""
import sys, os, json
sys.path.insert(0, r'D:\QuantMonitorV6')
from datetime import datetime as _dt

import ui.battle_widgets.auction_filter_widget as M
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget as W
import utils.http_market_data as H

_real = H.http_get_with_retry


class FakeDT(_dt):
    """把 now() 固定成 9:16，模拟竞价不可撤单阶段"""
    @classmethod
    def now(cls, tz=None):
        return _dt(2026, 9, 24, 9, 16, 30)


print('=== 场景 A：模拟时间 9:16 + 新浪整页全 0（真实观测形态） ===')
M.datetime = FakeDT
_zero = json.dumps([{'code': '920000', 'name': '安徽凤凰', 'changepercent': 0, 'open': 0,
                     'settlement': 14.29, 'trade': 0, 'volume': 0, 'amount': 0,
                     'turnoverratio': 0, 'nmc': 0}] * 80)


def fake_zero(url, **kw):
    return _zero if 'sina.com.cn' in url else _real(url, **kw)


H.http_get_with_retry = fake_zero
print('  _auction_stage():', W._auction_stage())
r = W._fetch_auction()
f = r.get('funnel') or {}
print('  source :', f.get('source'))
print('  funnel :', f)
print('  note   :', r.get('note'))
rows = r.get('rows') or []
print('  rows   :', len(rows))
for x in rows[:10]:
    print('     %s %-6s gap=%.2f%% 现价=%.2f 昨收=%.2f MA20=%.2f 量比=%s 分=%.1f' % (
        x['code'], x['name'][:6], x['gap'], x['price'], x['last_close'],
        x.get('ma20') or 0, x.get('vol_ratio'), x.get('score', 0)))
print()

print('=== 场景 B：模拟时间 9:16 + 两个源都没数据 ===')


def fake_dead(url, **kw):
    return ''


H.http_get_with_retry = fake_dead
r2 = W._fetch_auction()
print('  note:', r2.get('note'))
print('  rows:', len(r2.get('rows') or []))
print()

print('=== 场景 C：模拟时间 9:16 + 新浪正常有数据（新浪必须优先） ===')
H.http_get_with_retry = _real
r3 = W._fetch_auction()
print('  source:', (r3.get('funnel') or {}).get('source'), ' rows:', len(r3.get('rows') or []))
print()

print('=== 场景 D：模拟时间 10:30（9:25 后）+ 新浪无数据 -> 不兜底 ===')
class FakeDT2(_dt):
    @classmethod
    def now(cls, tz=None):
        return _dt(2026, 9, 24, 10, 30, 0)
M.datetime = FakeDT2
H.http_get_with_retry = fake_zero
r4 = W._fetch_auction()
print('  note:', r4.get('note'))
print('  rows:', len(r4.get('rows') or []))

H.http_get_with_retry = _real
