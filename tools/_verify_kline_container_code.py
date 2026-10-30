# -*- coding: utf-8 -*-
"""KlineContainer 的 code 透传单测（不创建 WebEngine，纯 QWidget 逻辑）。

覆盖：① 已初始化直接转发 ② 未初始化时缓存 pending_code ③ 重放语义
      ④ 源码级：三处 pending 重放必须带 pending_code ⑤ 不传 code 的向后兼容
      ⑥ QPainter 降级路径同样透传
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication                        # noqa: E402
app = QApplication([])
from ui.kline_container import KlineContainer                    # noqa: E402

N = 60
DATA = {'dates': ['2026-01-%02d' % (i + 1) for i in range(N)],
        'open': [10.0] * N, 'high': [10.5] * N, 'low': [9.5] * N,
        'close': [10.2] * N, 'volume': [1000] * N}


class Stub:
    def __init__(self):
        self.calls = []

    def set_kline_data(self, data, code=''):
        self.calls.append((len(data.get('close', [])), code))


results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def ready(kc, use_echarts=True):
    kc.timeout_timer.stop()
    st = Stub()
    kc.echarts_widget = st if use_echarts else None
    kc.qpainter_widget = None if use_echarts else st
    kc.current_widget = st
    kc.use_echarts = use_echarts
    kc.is_initialized = True
    return st


# ① 已初始化 → 直接转发 code
kc = KlineContainer()
st = ready(kc)
kc.set_kline_data(DATA, '300750')
check('① 已初始化转发 code', st.calls == [(N, '300750')], str(st.calls))

# ⑤ 不传 code → 仍可用（向后兼容）
kc5 = KlineContainer()
st5 = ready(kc5)
kc5.set_kline_data(DATA)
check('⑤ 不传 code 向后兼容', st5.calls == [(N, '')], str(st5.calls))

# ② 未初始化 → 缓存 pending_code
kc2 = KlineContainer()
kc2.timeout_timer.stop()
kc2.set_kline_data(DATA, '301001')
check('② 未初始化缓存 pending_code', kc2.pending_data is DATA and kc2.pending_code == '301001',
      'pending_code=%r' % kc2.pending_code)

# ③ 重放语义（写法与源码三处一致）
st2 = ready(kc2)
kc2.set_kline_data(kc2.pending_data, kc2.pending_code)
kc2.pending_data = None
kc2.pending_code = ''
check('③ 重放带上 code', st2.calls == [(N, '301001')], str(st2.calls))

# ⑥ QPainter 降级路径
kc6 = KlineContainer()
st6 = ready(kc6, use_echarts=False)
kc6.set_kline_data(DATA, '600519')
check('⑥ QPainter 路径透传', st6.calls == [(N, '600519')], str(st6.calls))

# ④ 源码级断言
src = open(os.path.join(r'D:\QuantMonitorV6', 'ui', 'kline_container.py'),
           newline='', encoding='utf-8').read()
n_replay = src.count('self.set_kline_data(self.pending_data, self.pending_code)')
check('④ 三处 pending 重放都带 pending_code', n_replay == 3, '命中 %d 处' % n_replay)
check('④b 无遗留的无参重放', src.count('self.set_kline_data(self.pending_data)') == 0)
check('④c 转发 ECharts 带 code', 'self.echarts_widget.set_kline_data(kline_data, code)' in src)
check('④d 转发 QPainter 带 code', 'self.qpainter_widget.set_kline_data(kline_data, code)' in src)

bad = sum(1 for _, ok, _ in results if not ok)
print('\nPASS %d / FAIL %d' % (len(results) - bad, bad))
sys.exit(1 if bad else 0)
