# -*- coding: utf-8 -*-
"""补 part2 失败的两处（缩进修正）。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:70].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

rep("""        dsp = ds.get('per', {}).get(name) if ds else None
        if dsp:
            why, op, buy, stop = dsp['why'], dsp['op'], dsp['buy'], dsp['stop']""",
    """        dsp = ds.get('per', {}).get(name) if ds else None
        _logic = (dsp.get('logic') or '') if isinstance(dsp, dict) else ''
        if dsp:
            why, op, buy, stop = (dsp.get('why') or ''), (dsp.get('op') or ''), (dsp.get('buy') or ''), (dsp.get('stop') or '')
            if not (why or op or buy or stop):
                dsp = None""")

rep("""            + '<div style=\"color:' + GREY + ';font-size:12px;\">👉 ' + ('AI 大白话' if dsp else '大白话') + '：' + why + '。</div>'
            + '<div style=\"color:#ced4da;font-size:12px;\">操作：<b style=\"color:' + op_col + ';\">' + op + '</b> ｜ 买点：' + buy + ' ｜ 止损：' + stop + '</div></div>')""",
    """            + (('<div style=\"color:' + TEAL + ';font-size:12px;margin-top:2px;\">🧠 个股逻辑：' + _logic + '</div>') if _logic else '')
            + '<div style=\"color:' + GREY + ';font-size:12px;\">👉 ' + ('AI 大白话' if dsp else '大白话') + '：' + why + '。</div>'
            + '<div style=\"color:#ced4da;font-size:12px;\">操作：<b style=\"color:' + op_col + ';\">' + op + '</b> ｜ 买点：' + buy + ' ｜ 止损：' + stop + '</div></div>')""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
