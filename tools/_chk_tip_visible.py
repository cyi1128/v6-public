import sys
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.band_pattern_engine import query_signals

sigs = query_signals() or []
print("query_signals() 返回 %d 条" % len(sigs))
tips = [s for s in sigs if (s.get('note') or '').find('[控盘]') >= 0]
print("其中带 [控盘] 提示的 %d 条" % len(tips))
print()
# 复刻 UI 的过滤规则（atr_t_widget.py L1824）
VIS = ('建仓触发', '等待确认')
vis = [s for s in tips if s.get('signal_level', '') in VIS]
hid = [s for s in tips if s.get('signal_level', '') not in VIS]
print("=== 会出现在日K建仓表里的（%d 条）===" % len(vis))
for s in sorted(vis, key=lambda x: -(x.get('control_score') or 0)):
    t = (s['note']).split('[控盘]')[-1].strip().replace('\n', ' ')
    print("   %s %-6s %-5s 控盘%5.1f %-11s %s" % (
        s['code'], (s.get('name') or '')[:6], s.get('signal_level') or '',
        s.get('control_score') or 0, s.get('stage_guess') or '', t))
print()
print("=== 被表格过滤规则挡掉、看不到的（%d 条）===" % len(hid))
for s in sorted(hid, key=lambda x: -(x.get('control_score') or 0)):
    t = (s['note']).split('[控盘]')[-1].strip().replace('\n', ' ')
    print("   %s %-6s %-5s 控盘%5.1f %-11s %s" % (
        s['code'], (s.get('name') or '')[:6], s.get('signal_level') or '',
        s.get('control_score') or 0, s.get('stage_guess') or '', t))
print()
print("表格总行数（复刻 L1824 过滤后）:", len([s for s in sigs if s.get('signal_level','') in VIS]))
