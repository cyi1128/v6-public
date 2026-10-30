# -*- coding: utf-8 -*-
"""行级修复 _watch_card 渲染段（L3656-3664）。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
lines = io.open(P, encoding='utf-8').read().split('\n')
# 定位
i0 = None
for i, l in enumerate(lines):
    if l == "    _dsp = (ds_plain or {}).get(sg['n'])":
        i0 = i
        break
if i0 is None:
    print('anchor not found')
    raise SystemExit(1)
# 找到 return f""" 行（i0+5）
ir = i0 + 5
assert lines[ir].startswith('    return f"""'), lines[ir]
assert '🧠 {ai_tag}：{why_txt}' in lines[ir + 3], lines[ir + 3]
new = [
    "    _dsp = (ds_plain or {}).get(sg['n'])",
    "    if isinstance(_dsp, dict):",
    "        _logic = _dsp.get('logic', '')",
    "        _why = _dsp.get('why', '')",
    "        _op_ai = _dsp.get('op', '')",
    "        _logic_html = ('<div style=\"color:' + TEAL + ';font-size:12px;margin-top:4px;\">🧠 个股逻辑：' + _logic + '</div>') if _logic else ''",
    "        _why_html = ('<div style=\"color:#e9ecef;font-size:12px;margin-top:2px;\">👉 大白话：' + _why + ('（' + _op_ai + '）' if _op_ai else '') + '</div>') if _why else ''",
    "        _ai_block = _logic_html + _why_html",
    "    else:",
    "        _why = _dsp if _dsp else sg.get('why', '')",
    "        _ai_block = ('<div style=\"color:#e9ecef;font-size:12px;margin-top:2px;\">👉 大白话：' + _why + '</div>') if _why else ''",
]
lines[i0:i0 + 5] = new
# 替换 🧠 行 为 {_ai_block}
lines[ir + 3] = '{_ai_block}'
io.open(P, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
print('watch_card rows fixed')
