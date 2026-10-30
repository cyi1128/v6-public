# -*- coding: utf-8 -*-
import py_compile, sys, io
P = r"D:\QuantMonitorV6\services\control_profile.py"
sys.stdout.reconfigure(encoding="utf-8")
s = io.open(P, encoding="utf-8").read()

old = """def _engine():
    \"\"\"懒加载引擎模块（避免启动期循环 import）。\"\"\"
    import services.band_pattern_engine as E
    return E
"""
new = '''def _engine():
    """懒加载引擎模块（避免启动期循环 import）。"""
    import services.band_pattern_engine as E
    return E


def _load_bars_local(code):
    """只读本地 kline_cache，**不做网络兜底**。

    引擎的 _load_bars 在缓存缺失时会走 pytdx/腾讯在线抓 120 天K线，
    单只可能几百 ms 甚至卡住 —— 列表刷新（自选/涨停/竞价）绝不能这样。
    本地没有就返回 []，界面上显示 '--'，宁可空也不能卡 UI。
    """
    try:
        from services.kline_cache_service import get_latest_kline
        bars = get_latest_kline(code, count=120)
        if bars and len(bars) >= 60:
            return bars
    except Exception:
        pass
    return []
'''
assert s.count(old) == 1, "锚点1 命中 %d" % s.count(old)
s = s.replace(old, new, 1)

old2 = """        E = _engine()
        bars = E._load_bars(code)
        df = E._bars_to_df(bars)"""
new2 = """        E = _engine()
        bars = _load_bars_local(code)
        df = E._bars_to_df(bars)"""
assert s.count(old2) == 1, "锚点2 命中 %d" % s.count(old2)
s = s.replace(old2, new2, 1)
io.open(P, "w", encoding="utf-8").write(s)
py_compile.compile(P, doraise=True)
print("OK 已改为只读本地缓存")
