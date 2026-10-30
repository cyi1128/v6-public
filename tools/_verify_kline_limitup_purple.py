# -*- coding: utf-8 -*-
"""验证逐根「涨停K线标紫」的板性判定（真凶就是入参 code 被覆盖的那处）。

造数：倒数两根分别 +10% 与 +20%（相对各自前收）。
- 创业板 300750：只有 +20% 那根该标紫（19.8 阈值）→ 期望 1 根
- 主板 600519：两根都该标紫（9.8 阈值）→ 期望 2 根
判据：生成的 JS 里紫色 '#AF52DE' 出现次数（每根涨停 4 次 = color/color0/borderColor/borderColor0）。
"""
import re
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')
from ui.echarts_kline import EChartsKlineWidget as W      # noqa: E402

N = 60
closes = [10.0] * N
closes[-2] = closes[-3] * 1.10          # +10%
closes[-1] = closes[-2] * 1.20          # +20%
DATA = {'dates': ['2026-01-%02d' % (i + 1) for i in range(N)],
        'open': [c * 0.99 for c in closes],
        'high': [c * 1.04 for c in closes],
        'low': [c * 0.97 for c in closes],
        'close': closes,
        'volume': [10000] * N}


class Page:
    def __init__(self):
        self.js = ''

    def runJavaScript(self, js, cb=None):
        self.js = js


class View:
    def __init__(self, p):
        self._p = p

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


def count_purple(code):
    f = Fake()
    W.set_kline_data(f, dict(DATA), code)
    return f.page.js.count('#AF52DE') // 4


res = []
for code, exp in (('300750', 1), ('600519', 2), ('301001', 1)):
    got = count_purple(code)
    ok = got == exp
    res.append(ok)
    print('  [%s] %s 标紫K线=%d（期望 %d）' % ('PASS' if ok else 'FAIL', code, got, exp))

bad = res.count(False)
print('\nPASS %d / FAIL %d' % (len(res) - bad, bad))
sys.exit(1 if bad else 0)
