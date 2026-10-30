# -*- coding: utf-8 -*-
"""补验：扫描线程里「补当日K线」的状态提示是否真的发到界面（可重跑，秒级）。

做法：把 services.kline_cache_service.seed_today_bar 临时替换成假函数（不联网、不写库），
接住 widget 的 _scan_progress 信号，看是否收到预期文案；收到后立刻置 _cancel 停掉扫描。
覆盖 ok=True / ok=False（非交易时段）两条文案路径 + 异常路径。
"""
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

P, F = [], []


def ck(name, cond, extra=''):
    (P if cond else F).append(name)
    print('%s %s %s' % ('PASS' if cond else 'FAIL', name, extra), flush=True)


from PyQt6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])

import services.kline_cache_service as KCS  # noqa: E402
from ui.battle_widgets.control_screen_widget import ControlScreenWidget  # noqa: E402

_orig = KCS.seed_today_bar


def run_case(fake):
    """跑一次扫描，返回收集到的状态文案列表；收到补数文案后立即取消扫描。"""
    KCS.seed_today_bar = fake
    w = ControlScreenWidget()
    try:
        w._ck_auto.setChecked(False)
        w._ck_extra.setChecked(False)
    except Exception:
        pass
    msgs = []
    w._scan_progress.connect(lambda d, t, m: msgs.append(m))
    w.show()
    for _ in range(6):
        app.processEvents()
    w._ck_seed.setChecked(True)
    w._start_scan()
    t0 = time.time()
    while time.time() - t0 < 30:
        app.processEvents()
        if any('当日K线' in m for m in msgs):
            w._cancel = True          # 拿到补数文案就停扫描，省时间
        if not w._scanning:
            break
        time.sleep(0.1)
    for _ in range(5):
        app.processEvents()
    w.close()
    KCS.seed_today_bar = _orig
    return msgs


try:
    m1 = run_case(lambda codes=None, progress_cb=None: {
        'ok': True, 'written': 1234, 'before': 0, 'after': 1234, 'reason': ''})
    hit1 = [m for m in m1 if '当日K线' in m]
    ck('成功路径状态文案', bool(hit1) and '已补 1234 只' in hit1[0], str(hit1[:1]))

    m2 = run_case(lambda codes=None, progress_cb=None: {
        'ok': False, 'written': 0, 'reason': '非交易时段，跳过补当日K线'})
    hit2 = [m for m in m2 if '当日K线' in m]
    ck('跳过路径状态文案', bool(hit2) and '非交易时段' in hit2[0], str(hit2[:1]))

    def _boom(codes=None, progress_cb=None):
        raise RuntimeError('模拟行情接口炸了')
    m3 = run_case(_boom)
    hit3 = [m for m in m3 if '当日K线' in m]
    ck('异常路径不打断扫描', bool(hit3) and '异常' in hit3[0], str(hit3[:1]))
finally:
    KCS.seed_today_bar = _orig
    ck('假函数已还原', KCS.seed_today_bar is _orig)

print('=' * 60)
print('结果：%d PASS / %d FAIL' % (len(P), len(F)))
if F:
    print('失败项:', F)
print('=' * 60)
sys.exit(1 if F else 0)
