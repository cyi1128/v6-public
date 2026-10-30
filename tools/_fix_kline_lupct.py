# -*- coding: utf-8 -*-
"""[一次性补丁] 修复 ui\\echarts_kline.py 里被误写进 JS f-string 内部的 _lu_pct 计算。

问题：CYB-GATE 那次改动把
        _lu_pct = 19.8 if ... else 9.8
      这两行 Python 代码插进了 f-string 字符串里面 —— _lu_pct 在 Python 侧从未定义，
      拼字符串时抛 NameError，runJavaScript 根本没被调用 → K线图永远没数据（所有周期）。
修法：把这两行提到 f-string 之前（Python 侧），JS 里只留下字面量 window.__limitPct。
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = r'D:\QuantMonitorV6'
TARGET = os.path.join(ROOT, 'ui', 'echarts_kline.py')
BAK = TARGET + '.bak_before_kline_fix'

src = open(TARGET, newline='', encoding='utf-8').read()
crlf_before = src.count('\r\n')
lf_before = src.count('\n') - crlf_before

if os.path.exists(BAK):
    print('备份已存在，跳过备份: %s' % BAK)
else:
    shutil.copy2(TARGET, BAK)
    print('已备份 → %s' % BAK)

i = src.index('            # ========== 第三步：更新图表')
j = src.index('            js_code = f"""', i)
k = src.index('            var result = updateKline(', j)
old_block = src[j:k]
print('--- 原片段（%d 字符）---' % len(old_block))
print(old_block.replace('\r\n', '\n'))

if '_lu_pct' not in old_block or '# [CYB-GATE]' not in old_block:
    print('!! 锚点内容与预期不符，中止')
    sys.exit(1)

new_block = (
    '            # [CYB-GATE] 涨停阈值按板性：创业板/科创板 20cm -> 19.8，其余 9.8\n'
    '            # 注意：这两行必须在 f-string 之外用 Python 先算好，再作为字面量拼进 JS。\n'
    '            # （历史事故：曾被误写进 JS 字符串内部 → _lu_pct 未定义 → NameError →\n'
    '            #   runJavaScript 从不执行 → 日K线图全周期空白。）\n'
    "            _lu_pct = 19.8 if str(kline_data.get('code', '') or '').startswith(\n"
    "                ('300', '301', '688', '689')) else 9.8\n"
    '            js_code = f"""\n'
    '            (function() {{\n'
    '                try {{\n'
    '                    if (typeof chart === \'undefined\' || !chart) {{\n'
    "                        return 'chart不存在';\n"
    '                    }}\n'
    '                    chart.clear();\n'
    '                    window.__limitPct = {_lu_pct};\n'
).replace('\n', '\r\n')

out = src[:j] + new_block + src[k:]
open(TARGET, 'w', newline='', encoding='utf-8').write(out)

chk = open(TARGET, newline='', encoding='utf-8').read()
crlf_after = chk.count('\r\n')
lf_after = chk.count('\n') - crlf_after
print('\n--- 新片段 ---')
print(chk[chk.index('            # ========== 第三步：更新图表'):
          chk.index('            var result = updateKline(')].replace('\r\n', '\n'))
print('行尾：改前 CRLF=%d/裸LF=%d → 改后 CRLF=%d/裸LF=%d' % (crlf_before, lf_before, crlf_after, lf_after))

# 静态校验：_lu_pct 的定义必须出现在 js_code = f""" 之前
p_def = chk.index('_lu_pct = 19.8 if')
p_js = chk.index("js_code = f\"\"\"", p_def - 2000)
print('_lu_pct 赋值在 f-string 之前: %s' % (p_def < p_js))
print('全文件 _lu_pct 出现次数: %d（应为 3：注释1 + 赋值1 + JS字面量1）' % chk.count('_lu_pct'))

r = subprocess.run([sys.executable, '-m', 'py_compile', TARGET], capture_output=True, text=True)
print('py_compile: rc=%s %s' % (r.returncode, (r.stderr or '').strip()[:400]))
