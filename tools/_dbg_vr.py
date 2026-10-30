# -*- coding: utf-8 -*-
"""临时调试：还原 detect_volume_regime 的真实异常（不含 try/except 包装）。"""
import inspect
import sys
import traceback

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import strategy.base as B  # noqa: E402

TI = B.TechnicalIndicators
src = inspect.getsource(TI.detect_volume_regime)
i = src.find('        try:')
j = src.rfind('        except Exception as _e:')
body = src[i + len('        try:'):j]
body = '\n'.join((l[4:] if l.startswith('    ') else l) for l in body.split('\n'))
g = dict(B.__dict__)
exec(compile('def _f(df):\n' + body, '<dbg>', 'exec'), g, g)

from services.kline_cache_service import get_latest_kline  # noqa: E402
from services.band_pattern_engine import _bars_to_df  # noqa: E402

d = _bars_to_df(get_latest_kline('600519', count=140))
print('列：', list(d.columns), '行数', len(d))
try:
    print(g['_f'](d))
except Exception:
    traceback.print_exc()
