# -*- coding: utf-8 -*-
"""隔离验证：不碰 Qt/WebEngine，用假 self 直接调 EChartsKlineWidget.set_kline_data，
抓取它生成的 JS 文本，核对 window.__limitPct 与 self.current_code。

覆盖：① 显式传 code ② code 塞在数据字典 ③ 都不给（向后兼容）
"""
import sys
import re

sys.path.insert(0, r'D:\QuantMonitorV6')
from ui.echarts_kline import EChartsKlineWidget as W      # noqa: E402

N = 60
DATA = {'dates': ['2026-01-%02d' % (i + 1) for i in range(N)],
        'open': [10.0 + i * 0.01 for i in range(N)],
        'high': [10.5 + i * 0.01 for i in range(N)],
        'low': [9.5 + i * 0.01 for i in range(N)],
        'close': [10.2 + i * 0.01 for i in range(N)],
        'volume': [10000 + i for i in range(N)]}


class Page:
    def __init__(self):
        self.js = None

    def runJavaScript(self, js, cb=None):
        self.js = js


class View:
    def __init__(self, page):
        self._p = page

    def page(self):
        return self._p


class Fake:
    def __init__(self):
        self.current_code = ''
        self._price_min = 0
        self._price_max = 0
        self.page = Page()
        self.web_view = View(self.page)
        self._on_js_result = lambda r: None


def run(data, code=''):
    f = Fake()
    if code:
        W.set_kline_data(f, data, code)
    else:
        W.set_kline_data(f, data)
    js = f.page.js or ''
    m = re.search(r'window\.__limitPct\s*=\s*([0-9.]+)', js)
    return {'luPct': float(m.group(1)) if m else None,
            'current_code': f.current_code,
            'js_has_render': 'updateKline(' in js,
            'js_len': len(js)}


CASES = [
    ('① 显式传 code=300750（创业板）', dict(DATA), '300750', 19.8, '300750'),
    ('② 显式传 code=600519（主板）', dict(DATA), '600519', 9.8, '600519'),
    ('③ 显式传 code=688981（科创板）', dict(DATA), '688981', 19.8, '688981'),
    ('④ code 只在数据字典 301001', dict(DATA, code='301001'), '', 19.8, '301001'),
    ('⑤ 都不给（向后兼容，默认 9.8）', dict(DATA), '', 9.8, ''),
]

print('%-34s %-9s %-9s %-9s %-9s %s' % ('用例', 'luPct', '期望', 'code回填', '期望', '判定'))
fails = 0
for name, data, code, exp_lu, exp_code in CASES:
    r = run(data, code)
    ok = (r['luPct'] == exp_lu and r['current_code'] == exp_code and r['js_has_render'])
    fails += 0 if ok else 1
    print('%-34s %-9s %-9s %-9r %-9r %s' % (name, r['luPct'], exp_lu, r['current_code'],
                                             exp_code, 'PASS' if ok else 'FAIL'))

print('\nFAIL 数：%d' % fails)
sys.exit(1 if fails else 0)
