# -*- coding: utf-8 -*-
"""FIX19c：zscan 渲染层量能红线终拦——LLM 仍输出绝对量能数字(万手/万股/万元)时渲染前清洗为相对表述"""
import io, sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\tools\cloud_daily_review.py'
src = io.open(P, encoding='utf-8').read()
orig = src

def rep(old, new, tag):
    global src
    assert old in src, 'NOT FOUND: ' + tag
    assert src.count(old) == 1, 'AMBIG: ' + tag + ' count=%d' % src.count(old)
    src = src.replace(old, new, 1)
    print('[OK]', tag)

# 1. 渲染循环前加清洗函数 + 字段清洗（放在 for r in radar[:5]: 之前）
rep("""    for r in radar[:5]:
        c = r.get('code') or r.get('stock_code') or ''""",
    """    def _strip_abs_vol(t):
        \"\"\"量能红线渲染终拦：剔除 LLM 输出的绝对量能数字（万手/万股/万元/亿），保留相对表述与价格锚。\"\"\"
        if not t:
            return t
        t = str(t)
        t = re.sub(r'成交金额超?\\s*\\d+(?:\\.\\d+)?\\s*万元', '大单放量确认', t)
        t = re.sub(r'成交量\\s*\\d+(?:\\.\\d+)?\\s*万股?', '成交量放量', t)
        t = re.sub(r'\\d+(?:\\.\\d+)?\\s*(?:万手|万股|万元|亿元|亿股|手)', '', t)
        t = re.sub(r'\\s{2,}', ' ', t).strip(' ，。、；')
        return t

    for r in radar[:5]:
        for _k in ('method', 'cost_zone', 'bottom_logic', 'ignite_theme', 'next_watch', 'false_alarm_risk',
                   'theme', 'reason', 'condition', 'risk', 'observation_logic', 'trigger_condition',
                   'data_trace', 'logic', 'why'):
            if r.get(_k):
                r[_k] = _strip_abs_vol(r[_k])
        c = r.get('code') or r.get('stock_code') or ''""",
    'zscan_vol_strip')

io.open(P, 'w', encoding='utf-8', newline='').write(src)
print('patched, delta=%d' % (len(src) - len(orig)))
