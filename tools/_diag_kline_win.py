# -*- coding: utf-8 -*-
"""日K线图真窗口诊断（用真实 Qt 窗口而非 offscreen，WebEngine 才能跑）。

输出：tools\\_kline_win.txt（结论）+ tools\\_kline_win_day.png（抓图）
窗口 6 秒后自动关闭，不碰 QuantMonitorV6 任何业务文件。
"""
import io
import os
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtCore import QTimer, Qt                               # noqa: E402
from PyQt6.QtWidgets import QApplication                           # noqa: E402

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from ui.echarts_kline import EChartsKlineWidget                    # noqa: E402

ROOT = r'D:\QuantMonitorV6'
LOG = io.open(os.path.join(ROOT, 'tools', '_kline_win.txt'), 'w', encoding='utf-8')


def log(s):
    print(s)
    LOG.write(str(s) + '\n')
    LOG.flush()


CODE = os.environ.get('KL_CODE', '600519')
PERIOD = os.environ.get('KL_PERIOD', 'day')

w = EChartsKlineWidget()
w.resize(1280, 760)
w.show()
w.raise_()

log('code=%s period=%s' % (CODE, PERIOD))

JS = """
(function(){
  try{
    if (typeof chart === 'undefined') return 'NO_CHART_VAR';
    if (!chart) return 'CHART_NULL';
    var o = chart.getOption();
    if (!o) return 'NO_OPTION';
    var s = o.series || [];
    var candles = -1, vols = -1, types = [];
    for (var i=0;i<s.length;i++){
      types.push(s[i].type);
      if (s[i].type === 'candlestick') candles = (s[i].data||[]).length;
      if (s[i].type === 'bar') vols = (s[i].data||[]).length;
    }
    var xd = (o.xAxis && o.xAxis[0] && o.xAxis[0].data) ? o.xAxis[0].data.length : -1;
    var first = (o.xAxis && o.xAxis[0] && o.xAxis[0].data) ? o.xAxis[0].data[0] : '';
    var last = (o.xAxis && o.xAxis[0] && o.xAxis[0].data) ? o.xAxis[0].data[o.xAxis[0].data.length-1] : '';
    var dom = document.getElementById('chart');
    return JSON.stringify({seriesCount:s.length, types:types.join(','),
      candles:candles, volbars:vols, xaxis:xd, firstDate:first, lastDate:last,
      domW: dom?dom.clientWidth:-1, domH: dom?dom.clientHeight:-1,
      chartW: chart.getWidth(), chartH: chart.getHeight()});
  }catch(e){ return 'JSERR:'+(e&&e.message); }
})()
"""


def probe():
    w.web_view.page().runJavaScript(JS, on_js)


def on_js(r):
    log('JS → %s' % r)
    try:
        pm = w.web_view.grab()
        p = os.path.join(ROOT, 'tools', '_kline_win_%s.png' % PERIOD)
        log('grab → %s %sx%s saved=%s' % (p, pm.width(), pm.height(), pm.save(p)))
    except Exception as e:
        log('grab 失败: %s' % e)
    QTimer.singleShot(500, app.quit)


QTimer.singleShot(1500, lambda: w.load_kline(CODE, PERIOD))
QTimer.singleShot(7000, probe)
QTimer.singleShot(20000, app.quit)          # 兜底，别挂住
app.exec()
log('结束')
LOG.close()
