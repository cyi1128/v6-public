import sys, types
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")

# ---- 打桩：交易中 / 企微总线 ----
import services.board_anomaly_engine as BA
BA.is_trading_now = lambda: True
SENT = []
class _Bus:
    def send_theme_rotation(self, **kw):
        SENT.append(kw); return {"sent": True}
import services.wechat_bus as WB
WB.get_wechat_bus = lambda: _Bus()
import services.regime_gate as RG

import importlib
MR = importlib.import_module("ui.battle_widgets.market_rhythm_widget")
print("widget 导入 OK")

ROWS = [{"kind": "题材", "name": "AI漫剧", "count": 4, "avg_pct": 9.99,
         "max_pct": 10.0, "members": [("600001", "甲"), ("600002", "乙")],
         "lead_name": "甲", "all_avg_pct": 1.0, "all_count": 100}]

class Stub:
    _PUSH_MIN_STOCK = 3
    _PUSH_COOLDOWN = 1800
    def __init__(self): self._pushed = {}

# 场景A：常温（放行）
RG.compute = lambda force=False: {"push": True, "state": "⚡ 常温轮动"}
SENT.clear(); MR.MarketRhythmWidget._push_boards(Stub(), ROWS)
print("A 常温 -> 实际推送 %d 条" % len(SENT))

# 场景B：冰点（不发）
RG.compute = lambda force=False: {"push": False, "state": "🧊 冰点"}
SENT.clear(); MR.MarketRhythmWidget._push_boards(Stub(), ROWS)
print("B 冰点 -> 实际推送 %d 条" % len(SENT))

# 场景C：闸门异常（应放行，不能卡死）
def _boom(force=False): raise RuntimeError("模拟取数失败")
RG.compute = _boom
SENT.clear(); MR.MarketRhythmWidget._push_boards(Stub(), ROWS)
print("C 闸门异常 -> 实际推送 %d 条（应为 1，fail-open）" % len(SENT))
