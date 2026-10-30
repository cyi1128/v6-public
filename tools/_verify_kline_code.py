# -*- coding: utf-8 -*-
"""验证「股票代码透传」在 ECharts K线控件里真的生效（单用例，环境变量驱动）。

KL_CODE  股票代码      KL_MODE  pass=传 code 参数 / dict=塞进数据字典 / none=都不给
KL_OUT   日志文件
流程照抄稳定版 tools\\_kline_case.py：直接 set_kline_data，不走 load_kline 抓取线程。
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
MODE = os.environ.get('KL_MODE', 'pass')
OUT = os.environ.get('KL_OUT', r'D:\QuantMonitorV6\tools\_kline_code_case.txt')

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

EXPECT = 19.8 if CODE.startswith(('300', '301', '688', '689')) else 9.8


def step():
    d = get_kline_by_period(CODE, 500, 'day')
    n = len(d['close']) if d else -1
    log('case=%s mode=%s provider_ok=%s bars=%d 期望luPct=%s' % (CODE, MODE, bool(d), n, EXPECT))

    def after():
        def got(r):
            log('JS → %s' % r)
            log('widget.current_code=%r' % w.current_code)
            q = w.current_code if w.current_code else ''
            ok_fmt = (q == (CODE if MODE in ('pass', 'dict') else ''))
            log('current_code 回填: %s（mode=%s 期望 %r）' % (ok_fmt, MODE, CODE if MODE in ('pass', 'dict') else ''))
            QTimer.singleShot(800, app.quit)
        w.web_view.page().runJavaScript(JS, got)

    import inspect
    log('实到方法签名: %s ｜ 源文件变更时间=%s' % (
        inspect.signature(w.set_kline_data),
        __import__('os').path.getmtime(__import__('ui.echarts_kline', fromlist=['x']).__file__)))
    try:
        if MODE == 'pass':
            w.set_kline_data(d, CODE)
        elif MODE == 'dict':
            d = dict(d)
            d['code'] = CODE
            w.set_kline_data(d)
        else:
            w.set_kline_data(d)
        log('set_kline_data 返回（无异常）')
    except Exception as e:
        log('set_kline_data 抛异常: %r' % (e,))
    log('调用后立即读: widget.current_code=%r' % w.current_code)
    QTimer.singleShot(5000, after)


QTimer.singleShot(2000, step)
QTimer.singleShot(25000, app.quit)
app.exec()
log('END')
LOG.close()
