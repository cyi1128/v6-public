# -*- coding: utf-8 -*-
"""最小 WebEngine 对照实验：逐步加载，定位崩溃到底是环境还是代码。

阶段：1) 空页面  2) 真载入 data\\echarts_kline.html  3) 跑 chart 查询 JS
"""
import io
import os
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtCore import QTimer, Qt, QUrl                              # noqa: E402
from PyQt6.QtWidgets import QApplication                               # noqa: E402
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from PyQt6.QtWebEngineWidgets import QWebEngineView                    # noqa: E402

app = QApplication(sys.argv)
LOG = io.open(r'D:\QuantMonitorV6\tools\_webe_ctl.txt', 'w', encoding='utf-8')


def log(s):
    print(s, flush=True)
    LOG.write(str(s) + '\n')
    LOG.flush()


STAGE = os.environ.get('WE_STAGE', '1')
log('stage=%s' % STAGE)

v = QWebEngineView()
v.resize(1100, 700)
v.show()

if STAGE == '1':
    v.setHtml('<html><body><h1 id="t">hello</h1></body></html>')
else:
    v.setUrl(QUrl.fromLocalFile(r'D:\QuantMonitorV6\data\echarts_kline.html'))


def on_load(ok):
    log('loadFinished=%s' % ok)
    if STAGE == '1':
        QTimer.singleShot(500, lambda: v.page().runJavaScript(
            "document.getElementById('t').innerText", lambda r: (log('JS1=%s' % r), app.quit())))
    else:
        QTimer.singleShot(1500, lambda: v.page().runJavaScript(
            "typeof echarts + '|' + (typeof chart) + '|' + (document.getElementById('chart')?'hasDom':'noDom')",
            lambda r: (log('JS2=%s' % r), app.quit())))


v.loadFinished.connect(on_load)
QTimer.singleShot(25000, app.quit)
app.exec()
log('结束')
LOG.close()
