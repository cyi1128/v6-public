# -*- coding: utf-8 -*-
"""[一次性补丁·第三批] 修掉 set_kline_data 内把入参 code 覆盖掉的写法。

问题：方法内部循环里 `code = kline_data.get('code', '')` 覆盖了入参 code，
      而 get_kline_by_period() 返回的 dict 根本没有 code 键 → 覆盖后恒为空串 →
      ① 逐根「涨停K线标紫」的板性判定永远走主板分支（创业板 20cm 被误判）；
      ② 末尾 `window.__limitPct` 永远 9.8；
      ③ current_code 也回填不了，组件内周期切换按钮点了没反应。

做法：在循环前算一次 `_kline_code`（入参 → 数据字典 → current_code），
      循环内与末尾的 JS 都用它；覆盖入参的那句删掉。
"""
import os
import re
import subprocess
import sys

p = os.path.join(r'D:\QuantMonitorV6', 'ui', 'echarts_kline.py')
src = open(p, newline='', encoding='utf-8').read()
crlf, lf = src.count('\r\n'), src.count('\n') - src.count('\r\n')
assert crlf > 0 and lf == 0, '不是纯 CRLF'
t = src.replace('\r\n', '\n')

EDITS = [
    ('循环前定义 _kline_code',
     r'(            limit_up_count = 0\n)([ \t]*\n)(            for i in range\(data_len\):\n)',
     "\\1\\2"
     "            # [CYB-GATE] 板性代码：入参 code 优先 → 数据字典 code → 当前已加载代码。\n"
     "            # （get_kline_by_period() 返回的 dict 不含 code，所以入参才是主要来源。）\n"
     "            _kline_code = str(code or kline_data.get('code')\n"
     "                              or getattr(self, 'current_code', '') or '')\n"
     "\\2\\3", 1),

    ('逐根涨停判定改用 _kline_code（并删掉覆盖入参的那句）',
     r"                        # 主板：>=9\.8%，创业板/科创板：>=19\.8%\n"
     r"                        code = kline_data\.get\('code', ''\)\n"
     r"                        if code\.startswith\(\('300', '301', '688'\)\):\n",
     "                        # 主板：>=9.8%，创业板/科创板：>=19.8%\n"
     "                        if _kline_code.startswith(('300', '301', '688', '689')):\n", 1),

    ('末尾 luPct 改用 _kline_code 并回填 current_code',
     r"            # 代码来源优先级：显式传入 code → 数据字典里的 code → 当前已加载代码。\n"
     r"            # （get_kline_by_period 返回的 dict 不含 code，所以必须靠前两者。）\n"
     r"            _lu_code = str\(code or kline_data\.get\('code'\)\n"
     r"                           or getattr\(self, 'current_code', ''\) or ''\)\n"
     r"            if code:\n"
     r"                self\.current_code = code      # 供周期切换按钮复用\n"
     r"            _lu_pct = 19\.8 if _lu_code\.startswith\(\('300', '301', '688', '689'\)\) else 9\.8\n",
     "            # [CYB-GATE] 涨停阈值按板性（与上面逐根涨停判定共用 _kline_code）\n"
     "            if _kline_code:\n"
     "                self.current_code = _kline_code   # 供周期切换按钮复用\n"
     "            _lu_pct = 19.8 if _kline_code.startswith(('300', '301', '688', '689')) else 9.8\n", 1),
]

for desc, pat, repl, cnt in EDITS:
    t, n = re.subn(pat, repl, t)
    print('  [%s] %s（%d 处）' % ('OK' if n == cnt else '!!', desc, n))
    assert n == cnt, '%s：命中 %d 次（期望 %d）' % (desc, n, cnt)

out = t.replace('\n', '\r\n')
open(p, 'w', newline='', encoding='utf-8').write(out)
chk = open(p, newline='', encoding='utf-8').read()
c2, l2 = chk.count('\r\n'), chk.count('\n') - chk.count('\r\n')
r = subprocess.run([sys.executable, '-m', 'py_compile', p], capture_output=True, text=True)
print('\n改后：CRLF=%d 裸LF=%d 行数=%d py_compile=%s' % (
    c2, l2, chk.count('\n'), 'OK' if r.returncode == 0 else (r.stderr or '')[:300]))
print('残留的覆盖写法 code = kline_data.get(...) ：%d 处' % chk.count("code = kline_data.get('code'"))
print('_kline_code 出现次数：%d' % chk.count('_kline_code'))
