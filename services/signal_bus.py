# -*- coding: utf-8 -*-
"""
全局信号总线（Signal Bus）
================================================================
目的：解耦 UI 模块，避免 widget 之间直接 import / 直接持有引用。
- 生产者（emit）：底部"机会发现"等模块
- 消费者（connect）：右侧"ATR做T助手"等模块

用法：
    from services.signal_bus import get_signal_bus

    bus = get_signal_bus()
    bus.add_to_atr_obs.connect(self._on_add)      # 消费方
    bus.add_to_atr_obs.emit({...})                # 生产方

注意：必须在 QApplication 创建之后再调用 get_signal_bus()（QObject 依赖 Qt 事件循环）。
该单例在首次调用时创建，之后所有模块拿到的是同一个对象。
"""
from PyQt6.QtCore import QObject, pyqtSignal


class _SignalBus(QObject):
    """跨模块全局信号总线（单例）。"""

    # 底部"机会发现" -> ATR做T助手「机会发现」Tab
    # payload: dict(code, name, price, pct, volr, theme, found_time)
    add_to_atr_obs = pyqtSignal(dict)

    # 预留：做T助手 -> 其他模块（例如弹窗提醒跳持仓）
    atr_holding_added = pyqtSignal(dict)


_bus = None


def get_signal_bus():
    """获取全局信号总线单例。"""
    global _bus
    if _bus is None:
        _bus = _SignalBus()
    return _bus
