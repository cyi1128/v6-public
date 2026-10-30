# -*- coding: utf-8 -*-
"""[一次性补丁·第二批] K线代码透传：容器 + 各调用方（A 部分已在上一脚本完成）。

做法：文件先归一化成 LF 做正则替换，再统一还原成本来的 CRLF（这些文件全是纯 CRLF，
      归一化不会引入裸 LF 混排）。每个替换都断言命中次数，幂等可重跑。
"""
import os
import re
import subprocess
import sys

ROOT = r'D:\QuantMonitorV6'
FILES = ['ui/echarts_kline.py', 'ui/kline_container.py', 'ui/battle_console_v2.py',
         'ui/stock_detail_v1.py', 'ui/professional_kline_dialog.py', 'ui/pro_stock_pool.py']


def patch(rel, edits):
    p = os.path.join(ROOT, rel)
    src = open(p, newline='', encoding='utf-8').read()
    crlf, lf = src.count('\r\n'), src.count('\n') - src.count('\r\n')
    assert crlf > 0 and lf == 0, '%s 不是纯 CRLF（CRLF=%d 裸LF=%d）' % (rel, crlf, lf)
    t = src.replace('\r\n', '\n')
    for desc, pat, repl, cnt in edits:
        t2, n = re.subn(pat, repl, t)
        if n != cnt:
            # 幂等：已经改过就跳过
            t3, n3 = re.subn(pat, repl, t2)
            if n == 0 and t.count(repl.replace('\n', '\n')) > 0:
                print('  [SKIP] %s ← %s（已应用）' % (rel, desc))
                continue
            raise AssertionError('%s ← %s：命中 %d 次（期望 %d）' % (rel, desc, n, cnt))
        t = t2
        print('  [OK] %s ← %s（%d 处）' % (rel, desc, n))
    out = t.replace('\n', '\r\n')
    open(p, 'w', newline='', encoding='utf-8').write(out)


# ---------- B. ui/kline_container.py ----------
print('--- B. KlineContainer 代码透传 ---')
patch('ui/kline_container.py', [
    ('pending_code 字段初始化',
     r'(        self\.pending_data = None\n)(        self\.pending_time_share_data = None)',
     "\\1        self.pending_code = ''            # 与 pending_data 配对：缓存期间的股票代码（板性涨停阈值用）\n\\2", 1),

    ('set_kline_data 签名',
     r'    def set_kline_data\(self, kline_data\):\n'
     r'        """设置K线数据（统一接口）\n',
     '    def set_kline_data(self, kline_data, code=\'\'):\n'
     '        """设置K线数据（统一接口）\n', 1),

    ('docstring 补 code 说明',
     r'(            kline_data: dict, 包含 dates, open, high, low, close, volume\n)'
     r'(        """\n)',
     "\\1            code: 可选，股票代码；透传给内部控件（板性涨停阈值 / 周期切换）\n\\2", 1),

    ('缓存时记下 code',
     r'(            self\.pending_data = kline_data\n)(            return\n)',
     "\\1            self.pending_code = code or self.pending_code\n\\2", 1),

    ('转发给 ECharts 控件',
     r'(\s+)self\.echarts_widget\.set_kline_data\(kline_data\)\n',
     '\\1self.echarts_widget.set_kline_data(kline_data, code)\n', 1),

    ('转发给 QPainter 控件',
     r'(\s+)self\.qpainter_widget\.set_kline_data\(kline_data\)\n',
     '\\1self.qpainter_widget.set_kline_data(kline_data, code)\n', 1),

    ('三处 pending 重放带上 code',
     r'(\s+)self\.set_kline_data\(self\.pending_data\)\n(\s+)self\.pending_data = None\n',
     "\\1self.set_kline_data(self.pending_data, self.pending_code)\n"
     "\\2self.pending_data = None\n"
     "\\2self.pending_code = ''\n", 3),
])

# ---------- C. 调用方补传 code ----------
print('--- C. 调用方补传 code ---')
patch('ui/battle_console_v2.py', [
    ('个股分析页 K线推送（首次 + 渲染重试）',
     r'(\s+)self\.kline_container_widget\.set_kline_data\(kline_data\)\n',
     '\\1self.kline_container_widget.set_kline_data(kline_data, code)\n', 2),
])

patch('ui/stock_detail_v1.py', [
    ('详情页 K线推送',
     r'(\s+)self\.kline_chart\.set_kline_data\(kline\)\n',
     '\\1self.kline_chart.set_kline_data(kline, code)\n', 1),
])

patch('ui/professional_kline_dialog.py', [
    ('专业K线弹窗推送',
     r'(\s+)self\.kline_container\.set_kline_data\(kline_data\)\n',
     "\\1self.kline_container.set_kline_data(kline_data, getattr(self, 'code', ''))\n", 1),
])

patch('ui/pro_stock_pool.py', [
    ('记住当前 K线代码',
     r"(            code = self\.stock_data\.get\('code', ''\)\n)(            if not code:\n)",
     "\\1            self._kline_code = code        # 供 _set_kline_data 透传给 K 线控件\n\\2", 1),

    ('推送时带上 code',
     r'(\s+)self\.kline_widget\.set_kline_data\(kline_data\)\n',
     "\\1self.kline_widget.set_kline_data(kline_data, getattr(self, '_kline_code', ''))\n", 1),
])

print('\n--- 改后核对 ---')
bad = 0
for f in FILES:
    p = os.path.join(ROOT, f)
    src = open(p, newline='', encoding='utf-8').read()
    crlf, lf = src.count('\r\n'), src.count('\n') - src.count('\r\n')
    r = subprocess.run([sys.executable, '-m', 'py_compile', p], capture_output=True, text=True)
    ok = (lf == 0 and crlf > 0 and r.returncode == 0)
    print('  %-34s CRLF=%d 裸LF=%d py_compile=%s' % (f, crlf, lf,
                                                    'OK' if r.returncode == 0 else (r.stderr or '')[:180]))
    bad += 0 if ok else 1
print('\n异常文件数：%d' % bad)
