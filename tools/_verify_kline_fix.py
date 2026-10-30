# -*- coding: utf-8 -*-
"""日K线图修复验证：真实渲染 + JS 回读图表数据，独立于修复代码本身。

覆盖：主板/创业板 × 日/周/5分 周期；核对蜡烛数 = 数据根数、__limitPct 板性阈值。
"""
import io
import os
import sys

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QTimer, Qt                                  # noqa: E402
from PyQt6.QtWidgets import QApplication                             # noqa: E402
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from ui.echarts_kline import EChartsKlineWidget                      # noqa: E402
from utils.kline_provider import get_kline_by_period                 # noqa: E402

app = QApplication(sys.argv)
LOG = io.open(os.path.join(ROOT, 'tools', '_kline_fix_verify.txt'), 'w', encoding='utf-8')
RES = []


def log(s):
    print(s, flush=True)
    LOG.write(str(s) + '\n')
    LOG.flush()


CASES = [('600519', 'day', 9.8), ('600519', 'week', 9.8),
         ('300750', 'day', 19.8), ('600519', '5', 9.8)]

JS = """
(function(){
  try{
    if (typeof chart === 'undefined' || !chart) return 'NO_CHART';
    var o = chart.getOption();
    var s = o.series || [], candles = -1;
    for (var i=0;i<s.length;i++){ if (s[i].type === 'candlestick') candles = (s[i].data||[]).length; }
    var xd = (o.xAxis && o.xAxis[0] && o.xAxis[0].data) ? o.xAxis[0].data.length : -1;
    var last = (o.xAxis && o.xAxis[0] && o.xAxis[0].data) ? o.xAxis[0].data[o.xAxis[0].data.length-1] : '';
    return JSON.stringify({candles:candles, xaxis:xd, lastDate:last,
                           luPct: window.__limitPct});
  }catch(e){ return 'JSERR:'+(e&&e.message); }
})()
"""

w = EChartsKlineWidget()
w.resize(1280, 760)
w.show()

idx = [0]


def next_case():
    if idx[0] >= len(CASES):
        finish()
        return
    code, period, exp_lu = CASES[idx[0]]
    n = len(get_kline_by_period(code, 500, period)['close'])
    log('[%s/%s] 数据源根数=%d，期望 __limitPct=%s' % (code, period, n, exp_lu))
    w.load_kline(code, period)

    def probe():
        def on_js(r):
            log('   JS → %s' % r)
            ok = False
            try:
                import json
                d = json.loads(r)
                ok = (d['candles'] == n and d['xaxis'] == n and abs(float(d['luPct']) - exp_lu) < 1e-9)
                detail = 'candles=%s xaxis=%s luPct=%s 末日=%s' % (
                    d['candles'], d['xaxis'], d['luPct'], d['lastDate'])
            except Exception as e:
                detail = '解析失败 %s' % e
            RES.append((code, period, ok, detail))
            idx[0] += 1
            QTimer.singleShot(300, next_case)

        w.web_view.page().runJavaScript(JS, on_js)

    QTimer.singleShot(3500, probe)


def finish():
    log('\n===== 结论 =====')
    bad = 0
    for code, period, ok, detail in RES:
        log('%s %s/%s  %s' % ('PASS' if ok else 'FAIL', code, period, detail))
        bad += 0 if ok else 1
    log('PASS=%d FAIL=%d' % (len(RES) - bad, bad))
    LOG.close()
    app.quit()


QTimer.singleShot(2000, next_case)
QTimer.singleShot(90000, finish)
app.exec()
