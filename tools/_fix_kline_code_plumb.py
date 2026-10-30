# -*- coding: utf-8 -*-
"""[一次性补丁] 让股票代码流到 K 线组件：板性涨停阈值 + 周期切换按钮可用。

背景：`get_kline_by_period()` 返回的 dict 不含 'code'，而
      `EChartsKlineWidget.set_kline_data()` 只吃这一个 dict →
      `_lu_pct` 恒为 9.8（创业板 20cm 涨停不会标紫），
      且 `current_code` 为空 → 组件内「日/周/月/15/30/60分」按钮点了没反应。

改法：全部为**可选参数新增**（向后兼容），调用方按需补传自己已知的 code。
"""
import os
import subprocess
import sys

ROOT = r'D:\QuantMonitorV6'
FILES = ['ui/echarts_kline.py', 'ui/kline_container.py', 'ui/battle_console_v2.py',
         'ui/stock_detail_v1.py', 'ui/professional_kline_dialog.py', 'ui/pro_stock_pool.py']

STAT = {}


def load(rel):
    p = os.path.join(ROOT, rel)
    src = open(p, newline='', encoding='utf-8').read()
    STAT[rel] = {'nl': '\r\n' if '\r\n' in src else '\n', 'crlf': src.count('\r\n'),
                 'lf': src.count('\n') - src.count('\r\n')}
    return p, src


def rep(rel, old, new, cnt=1):
    """在 rel 文件里把 old 换成 new（old/new 用 \\n 书写，自动适应该文件行尾）。"""
    p = os.path.join(ROOT, rel)
    src = open(p, newline='', encoding='utf-8').read()
    nl = '\r\n' if '\r\n' in src else '\n'
    _o, _n = old.replace('\n', nl), new.replace('\n', nl)
    got = src.count(_o)
    assert got == cnt, '%s: 锚点命中 %d 次（期望 %d）\n%s' % (rel, got, cnt, old[:160])
    src = src.replace(_o, _n)
    open(p, 'w', newline='', encoding='utf-8').write(src)
    print('  [OK] %s  ← %s' % (rel, old.strip().splitlines()[0][:80]))


# ---------- A. ui/echarts_kline.py ----------
def a_echarts():
    # A1 签名 + docstring
    rep('ui/echarts_kline.py',
        '    def set_kline_data(self, kline_data):\n'
        '        """设置K线数据\n'
        '        \n'
        '        Args:\n'
        '            kline_data: dict, 包含 dates, open, high, low, close, volume\n'
        '        """\n',
        '    def set_kline_data(self, kline_data, code=\'\'):\n'
        '        """设置K线数据\n'
        '        \n'
        '        Args:\n'
        '            kline_data: dict, 包含 dates, open, high, low, close, volume\n'
        '            code: 可选，股票代码。按板性判定涨停阈值（创业板/科创板 20cm → 19.8），\n'
        '                  同时回填 current_code，使组件内周期切换按钮可用。\n'
        '        """\n')

    # A2 _lu_pct 解析（含 code 回填）
    rep('ui/echarts_kline.py',
        "            _lu_pct = 19.8 if str(kline_data.get('code', '') or '').startswith(\n"
        "                ('300', '301', '688', '689')) else 9.8\n",
        "            # 代码来源优先级：显式传入 code → 数据字典里的 code → 当前已加载代码。\n"
        "            # （get_kline_by_period 返回的 dict 不含 code，所以必须靠前两者。）\n"
        "            _lu_code = str(code or kline_data.get('code')\n"
        "                           or getattr(self, 'current_code', '') or '')\n"
        "            if code:\n"
        "                self.current_code = code      # 供周期切换按钮复用\n"
        "            _lu_pct = 19.8 if _lu_code.startswith(('300', '301', '688', '689')) else 9.8\n")

    # A3 load_kline 补传 code
    rep('ui/echarts_kline.py',
        '            self.set_kline_data(kline_data)\n',
        '            self.set_kline_data(kline_data, code)\n')


# ---------- B. ui/kline_container.py ----------
def b_container():
    rep('ui/kline_container.py',
        '        self.pending_data = None\n',
        "        self.pending_data = None\n"
        "        self.pending_code = ''            # 与 pending_data 配对：缓存期间的股票代码（板性涨停阈值用）\n")

    rep('ui/kline_container.py',
        '    def set_kline_data(self, kline_data):\n'
        '        """设置K线数据（统一接口）\n'
        '        \n'
        '        Args:\n'
        '            kline_data: dict, 包含 dates, open, high, low, close, volume\n'
        '        """\n',
        '    def set_kline_data(self, kline_data, code=\'\'):\n'
        '        """设置K线数据（统一接口）\n'
        '        \n'
        '        Args:\n'
        '            kline_data: dict, 包含 dates, open, high, low, close, volume\n'
        '            code: 可选，股票代码；透传给内部控件（板性涨停阈值 / 周期切换）\n'
        '        """\n')

    rep('ui/kline_container.py',
        '            self.pending_data = kline_data\n'
        '            return\n',
        '            self.pending_data = kline_data\n'
        '            self.pending_code = code or self.pending_code\n'
        '            return\n')

    rep('ui/kline_container.py',
        '                self.echarts_widget.set_kline_data(kline_data)\n',
        '                self.echarts_widget.set_kline_data(kline_data, code)\n')

    rep('ui/kline_container.py',
        '                    self.qpainter_widget.set_kline_data(kline_data)\n',
        '                    self.qpainter_widget.set_kline_data(kline_data, code)\n')

    # 三处 pending 重放
    rep('ui/kline_container.py',
        '                self.set_kline_data(self.pending_data)\n'
        '                self.pending_data = None\n',
        '                self.set_kline_data(self.pending_data, self.pending_code)\n'
        '                self.pending_data = None\n'
        "                self.pending_code = ''\n", cnt=2)

    rep('ui/kline_container.py',
        '                    self.set_kline_data(self.pending_data)\n'
        '                    self.pending_data = None\n',
        '                    self.set_kline_data(self.pending_data, self.pending_code)\n'
        '                    self.pending_data = None\n'
        "                    self.pending_code = ''\n")


# ---------- C. 调用方补传 code ----------
def c_callers():
    rep('ui/battle_console_v2.py',
        '                self.kline_container_widget.set_kline_data(kline_data)\n',
        '                self.kline_container_widget.set_kline_data(kline_data, code)\n')

    rep('ui/battle_console_v2.py',
        '                self.kline_container_widget.set_kline_data(kline_data)\n',
        '                self.kline_container_widget.set_kline_data(kline_data, code)\n')

    rep('ui/stock_detail_v1.py',
        '            self.kline_chart.set_kline_data(kline)\n',
        '            self.kline_chart.set_kline_data(kline, code)\n')

    rep('ui/professional_kline_dialog.py',
        '                self.kline_container.set_kline_data(kline_data)\n',
        '                self.kline_container.set_kline_data(kline_data, getattr(self, \'code\', \'\'))\n')

    rep('ui/pro_stock_pool.py',
        "            code = self.stock_data.get('code', '')\n"
        '            if not code:\n'
        '                return\n',
        "            code = self.stock_data.get('code', '')\n"
        '            if not code:\n'
        '                return\n'
        '            self._kline_code = code        # 供 _set_kline_data 透传给 K 线控件\n')

    rep('ui/pro_stock_pool.py',
        '                self.kline_widget.set_kline_data(kline_data)\n',
        "                self.kline_widget.set_kline_data(kline_data, getattr(self, '_kline_code', ''))\n")


for f in FILES:
    load(f)
print('改前行尾：')
for f, s in STAT.items():
    print('  %-34s CRLF=%d 裸LF=%d' % (f, s['crlf'], s['lf']))

print('\n--- 开始替换 ---')
a_echarts()
b_container()
c_callers()

print('\n--- 改后核对 ---')
bad = 0
for f in FILES:
    p = os.path.join(ROOT, f)
    src = open(p, newline='', encoding='utf-8').read()
    crlf = src.count('\r\n')
    lf = src.count('\n') - crlf
    ok_nl = (crlf > 0 and lf == 0) if STAT[f]['nl'] == '\r\n' else (crlf == 0)
    r = subprocess.run([sys.executable, '-m', 'py_compile', p], capture_output=True, text=True)
    print('  %-34s CRLF=%d 裸LF=%d 行尾一致=%s py_compile=%s' % (
        f, crlf, lf, ok_nl, 'OK' if r.returncode == 0 else (r.stderr or '')[:200]))
    if not ok_nl or r.returncode != 0:
        bad += 1
print('\n异常文件数：%d' % bad)
