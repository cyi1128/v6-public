# -*- coding: utf-8 -*-
"""日K线图离屏真渲染诊断：查 ECharts 实例里是否真的拿到数据 + 截图。"""
import io
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
                      '--disable-gpu --no-sandbox --disable-software-rasterizer '
                      '--in-process-gpu --disable-features=Vulkan')

sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtCore import QTimer, Qt                               # noqa: E402
from PyQt6.QtWidgets import QApplication                           # noqa: E402

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
app = QApplication([])

from ui.echarts_kline import EChartsKlineWidget                     # noqa: E402

w = EChartsKlineWidget()
w.resize(1200, 700)
w.show()

PERIODS = sys.argv[1:] or ['day']
out = io.open(os.path.join(r'D:\QuantMonitorV6\tools', '_kline_diag.txt'),
              'w', encoding='utf-8')


def log(s):
    print(s)
    out.write(s + '\n')
    out.flush()


log('QT_QPA_PLATFORM=%s' % os.environ.get('QT_QPA_PLATFORM'))
log('periods=%s' % PERIODS)


def probe(period, done):
    w.load_kline('600519', period)

    def ask():
        js = """
        (function(){
          try{
            if (typeof chart === 'undefined' || !chart) return 'NO_CHART_VAR';
            var o = chart.getOption();
            if (!o) return 'NO_OPTION';
            var s = o.series || [];
            var candles = 0, vols = 0;
            for (var i=0;i<s.length;i++){
              if (s[i].type === 'candlestick') candles = (s[i].data||[]).length;
              if (s[i].type === 'bar') vols = (s[i].data||[]).length;
            }
            var xd = (o.xAxis && o.xAxis[0] && o.xAxis[0].data) ? o.xAxis[0].data.length : -1;
            var dz = (o.dataZoom && o.dataZoom[0]) ? (o.dataZoom[0].start+'~'+o.dataZoom[0].end) : '-';
            return JSON.stringify({series:s.length, candles:candles, volbars:vols,
                                   xaxis:xd, zoom:dz,
                                   title:(o.title&&o.title[0]&&o.title[0].text)||'',
                                   canvasW:(document.getElementById('chart')||{}).clientWidth,
                                   canvasH:(document.getElementById('chart')||{}).clientHeight});
          }catch(e){ return 'JSERR:'+e.message; }
        })()
        """
        w.web_view.page().runJavaScript(js, lambda r: (log('[%s] JS → %s' % (period, r)), done()))

    QTimer.singleShot(6000, ask)


def grab(tag):
    try:
        pm = w.web_view.grab()
        p = os.path.join(r'D:\QuantMonitorV6\tools', '_kline_diag_%s.png' % tag)
        ok = pm.save(p)
        log('截图 %s → %s (%sx%s)' % (p, ok, pm.width(), pm.height()))
    except Exception as e:
        log('截图失败: %s' % e)


idx = [0]


def step():
    if idx[0] >= len(PERIODS):
        app.quit()
        return
    p = PERIODS[idx[0]]
    idx[0] += 1
    probe(p, lambda: (grab(p), step()))


QTimer.singleShot(4000, step)
app.exec()
log('完成')
out.close()
