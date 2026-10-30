# -*- coding: utf-8 -*-
"""验证分时做T风控阈值按板性分流。
条件直接取自引擎真实函数 _pct_thresholds()，分支顺序与源码 L676-696 一致。
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")

try:
    from PyQt6.QtCore import Qt, QCoreApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    import ui.battle_widgets.atr_t_widget as m
except Exception as e:
    print("!! 导入失败: %s" % e)
    raise SystemExit(1)

print("=== 1. 阈值表（取自引擎 _pct_thresholds）===")
for code in ('600000', '000001', '002594', '300001', '301001'):
    lock, mainup, weak = m._pct_thresholds(code)
    print("   %s  创业板=%-5s  锁仓线=%5.1f  主升浪线=%5.1f  弱势线=%6.1f"
          % (code, m._is_cyb(code), lock, mainup, weak))


def branch(code, pct, sell_radar=True):
    """复刻源码 if/elif 顺序：先 VWAP 破位，再锁仓，再主升浪，否则正常。"""
    lock, mainup, _ = m._pct_thresholds(code)
    price, vwap = 10.0, 10.0           # 价格站上 VWAP，排除第一支
    if price < vwap * 0.985:
        return '防飞刀'
    if pct >= lock:
        return '锁仓(不做T)'
    if pct >= mainup and sell_radar:
        return '主升浪(谨慎卖)'
    return '正常'


print()
print("=== 2. 分支判定 ===")
print("   %-8s %-6s %-18s %-18s" % ("代码", "涨幅", "改后", "改之前(两板都用8/5)"))
for code in ('600000', '300001'):
    for pct in (4.0, 6.0, 9.0, 12.0, 17.0):
        old = '锁仓(不做T)' if pct >= 8.0 else ('主升浪(谨慎卖)' if pct >= 5.0 else '正常')
        print("   %-8s %5.1f%% %-18s %-18s" % (code, pct, branch(code, pct), old))

print()
print("=== 3. 关键对照（+9% 的创业板股票）===")
print("   600000 主板   +9%% → %s（离 10%% 涨停只差 1%%，该锁仓）" % branch('600000', 9.0))
print("   300001 创业板 +9%% → %s（离 20%% 涨停还有 11%%，不该锁仓）" % branch('300001', 9.0))

print()
print("=== 4. 源码断言：分支确实用了板性变量 ===")
src = open(r"D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py",
           encoding="utf-8-sig").read()
checks = [
    ("涨停锁仓用变量", "elif pct >= _lock_pct:"),
    ("主升浪用变量", "elif pct >= _mainup_pct and in_sell_radar:"),
    ("弱势降分用变量", "if pct <= _pct_thresholds(code)[2]:"),
    ("阈值定义", "_pct_thresholds(r.get('code'))"),
]
for name, pat in checks:
    print("   %-16s %s" % (name, "OK" if pat in src else "!! 缺失"))
print("   已无硬编码 elif pct >= 8.0：",
      "是" if "elif pct >= 8.0:" not in src else "!! 还在")
print("   已无硬编码 elif pct >= 5.0：",
      "是" if "elif pct >= 5.0" not in src else "!! 还在")
