# -*- coding: utf-8 -*-
"""把 load_kline -> set_kline_data 拆成逐步插桩，定位崩溃发生在哪一步。"""
import io
import os
import sys
import traceback

sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtCore import QTimer, Qt                                # noqa: E402
from PyQt6.QtWidgets import QApplication                            # noqa: E402
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ui.echarts_kline import EChartsKlineWidget                     # noqa: E402

app = QApplication(sys.argv)
LOG = io.open(r'D:\QuantMonitorV6\tools\_kline_step.txt', 'w', encoding='utf-8')


def log(s):
    print(s, flush=True)
    LOG.write(str(s) + '\n')
    LOG.flush()


w = EChartsKlineWidget()
w.resize(1280, 760)
w.show()
log('widget shown')

tick = [0]


def heartbeat():
    tick[0] += 1
    log('heartbeat %d  alive' % tick[0])
    if tick[0] < 14:
        QTimer.singleShot(1000, heartbeat)


QTimer.singleShot(1000, heartbeat)


def step():
    log('step: 取数据（provider）')
    try:
        from utils.kline_provider import get_kline_by_period
        d = get_kline_by_period('600519', 500, 'day')
    except Exception:
        log('provider 异常:\n' + traceback.format_exc())
        app.quit()
        return
    log('step: provider 返回 %s，根数=%s' % (bool(d), len(d['close']) if d else -1))

    log('step: 调 set_kline_data')
    try:
        w.set_kline_data(d)
        log('step: set_kline_data 返回（没崩）')
    except Exception:
        log('set_kline_data 异常:\n' + traceback.format_exc())

    def after():
        log('step: 查 JS 结果')
        w.web_view.page().runJavaScript(
            "(typeof chart==='undefined')?'nochart':(function(){try{var o=chart.getOption();"
            "var s=o.series||[],c=-1;for(var i=0;i<s.length;i++){if(s[i].type==='candlestick')"
            "c=(s[i].data||[]).length;}return 'candles='+c+'|series='+s.length;"
            "}catch(e){return 'err:'+e.message;}})()",
            lambda r: (log('JS → %s' % r), QTimer.singleShot(1500, app.quit)))

    QTimer.singleShot(5000, after)


QTimer.singleShot(1800, step)
QTimer.singleShot(30000, app.quit)
app.exec()
log('结束')
LOG.close()
