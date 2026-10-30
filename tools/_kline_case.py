# -*- coding: utf-8 -*-
"""单用例 K 线渲染验证（环境变量 KL_CODE / KL_PERIOD 指定）。

刻意照抄 tools\\_kline_step.py 的稳定流程：直接调 set_kline_data，不经过 load_kline 的
多源抓取线程，避免真实窗口 QWebEngine 的非确定性崩溃。
"""
import io
import os
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtCore import QTimer, Qt                                # noqa: E402
from PyQt6.QtWidgets import QApplication                            # noqa: E402
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ui.echarts_kline import EChartsKlineWidget                     # noqa: E402

CODE = os.environ.get('KL_CODE', '600519')
PERIOD = os.environ.get('KL_PERIOD', 'day')
OUT = os.environ.get('KL_OUT', r'D:\QuantMonitorV6\tools\_kline_case.txt')

app = QApplication(sys.argv)
LOG = io.open(OUT, 'w', encoding='utf-8')


def log(s):
    print(s, flush=True)
    LOG.write(str(s) + '\n')
    LOG.flush()


w = EChartsKlineWidget()
w.resize(1280, 760)
w.show()

from utils.kline_provider import get_kline_by_period                 # noqa: E402

JS = ("(function(){try{if(typeof chart==='undefined'||!chart)return 'NO_CHART';"
      "var o=chart.getOption();var s=o.series||[],c=-1;"
      "for(var i=0;i<s.length;i++){if(s[i].type==='candlestick')c=(s[i].data||[]).length;}"
      "var xd=(o.xAxis&&o.xAxis[0]&&o.xAxis[0].data)?o.xAxis[0].data:[];"
      "return JSON.stringify({candles:c,xaxis:xd.length,last:(xd.length?xd[xd.length-1]:''),"
      "luPct:window.__limitPct});}catch(e){return 'err:'+e.message;}})()")


def step():
    d = get_kline_by_period(CODE, 500, PERIOD)
    n = len(d['close']) if d else -1
    log('case=%s/%s provider_ok=%s bars=%d' % (CODE, PERIOD, bool(d), n))

    def after():
        w.web_view.page().runJavaScript(JS, lambda r: (log('JS → %s' % r),
                                                       QTimer.singleShot(1200, app.quit)))

    try:
        w.set_kline_data(d)
        log('set_kline_data 返回（无异常）')
    except Exception as e:
        log('set_kline_data 抛异常: %r' % (e,))
    QTimer.singleShot(5000, after)


QTimer.singleShot(2000, step)
QTimer.singleShot(25000, app.quit)
app.exec()
log('END')
LOG.close()
