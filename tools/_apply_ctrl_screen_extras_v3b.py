# -*- coding: utf-8 -*-
"""一次性补丁（v3b）：补数只拉「真正过期的那一项」+ 页面补数状态文案带上失败数。

为什么：重试 478 只「公告为空」时，如果每只都连主营一起拉，会白撞 478 次东财 F10
（正是刚才把 IP 撞进风控的原因之一）。所以按字段判定 need_biz / need_ann。
执行一次即失效，勿重跑。
"""
import io
import os
import shutil
import tempfile

ROOT = r'D:\QuantMonitorV6'
SVC = os.path.join(ROOT, 'services', 'control_screen_service.py')
WDG = os.path.join(ROOT, 'ui', 'battle_widgets', 'control_screen_widget.py')

# ---------------- 服务层：按字段精确补 ----------------
s = io.open(SVC, 'r', encoding='utf-8').read()
assert '_need_biz' not in s, 'v3b 已打过'
A = """    def _work(c):
        if abort_ev.is_set():
            return None
        if cancel_cb is not None:
            try:
                if cancel_cb():
                    return None
            except Exception:
                pass
        try:
            rec = fetch_extras_one(c, timeout=timeout, old=items.get(c))
            return c, rec
        except Exception:
            return c, None"""
N = """    def _work(c):
        if abort_ev.is_set():
            return None
        if cancel_cb is not None:
            try:
                if cancel_cb():
                    return None
            except Exception:
                pass
        try:
            _old = items.get(c)
            # 按字段判：只拉真正过期的那一项（重试公告时不再白撞主营接口）
            _need_biz = extras_stale(_old, need_biz=True, need_ann=False)
            _need_ann = extras_stale(_old, need_biz=False, need_ann=True)
            if not (_need_biz or _need_ann):
                return c, _old
            rec = fetch_extras_one(c, need_biz=_need_biz, need_ann=_need_ann,
                                   timeout=timeout, old=_old)
            return c, rec
        except Exception:
            return c, None"""
assert s.count(A) == 1
s = s.replace(A, N, 1)
if not os.path.isfile(SVC + '.bak_before_extras3b'):
    shutil.copy2(SVC, SVC + '.bak_before_extras3b')
io.open(SVC, 'w', encoding='utf-8', newline='').write(s)
import py_compile   # noqa: E402
py_compile.compile(SVC, cfile=os.path.join(tempfile.gettempdir(), 'cs3b.pyc'), doraise=True)
_b = io.open(SVC, 'rb').read()
print('服务层: 行=%d CRLF=%d 字节=%d' % (_b.count(b'\n'), _b.count(b'\r\n'), len(_b)))
assert _b.count(b'\r\n') == 0

# ---------------- 页面：线程数 3 + 状态文案 ----------------
w = io.open(WDG, 'r', encoding='utf-8').read()
assert '_need_biz' not in w
A2 = """            def _job():
                return SS.fetch_extras(
                    miss, self._extras, workers=6,
                    progress_cb=lambda d, t, m: self._fill_progress.emit(d, t, m),
                    cancel_cb=lambda: self._cancel_fill)"""
N2 = """            def _job():
                # workers 只影响本地排队，真正防限流的是服务层「按主机限速」
                # （公告 0.3s/次、主营 0.2s/次 + 失败退避 15 分钟 + 连续失败熔断）
                return SS.fetch_extras(
                    miss, self._extras, workers=3,
                    progress_cb=lambda d, t, m: self._fill_progress.emit(d, t, m),
                    cancel_cb=lambda: self._cancel_fill)"""
assert w.count(A2) == 1
w = w.replace(A2, N2, 1)

A3 = """        self.set_status('主营/公告补数完成：%d 只 / %.1fs（异常 %d）｜来源 东财，公告巨潮兜底'
                        % (int(stats.get('ok') or 0), float(stats.get('elapsed') or 0),
                           int(stats.get('err') or 0)))"""
N3 = """        _ab = str(stats.get('aborted') or '')
        _tail = ('｜被上游限流，本轮已停手（%d 分钟后自动重试）' % int(SS.ANN_FAIL_COOLDOWN / 60)
                 if _ab else '｜来源 东财，公告新浪/巨潮兜底')
        self.set_status('主营/公告补数完成：主营 %d ｜ 公告 %d ｜ 失败 %d（异常 %d）/ %.1fs %s'
                        % (int(stats.get('biz_ok') or 0), int(stats.get('ann_ok') or 0),
                           int(stats.get('ann_fail') or 0), int(stats.get('err') or 0),
                           float(stats.get('elapsed') or 0), _tail))"""
assert w.count(A3) == 1
w = w.replace(A3, N3, 1)
if not os.path.isfile(WDG + '.bak_before_extras3b'):
    shutil.copy2(WDG, WDG + '.bak_before_extras3b')
io.open(WDG, 'w', encoding='utf-8', newline='').write(w)
py_compile.compile(WDG, cfile=os.path.join(tempfile.gettempdir(), 'wdg3b.pyc'), doraise=True)
_w = io.open(WDG, 'rb').read()
print('页面: 行=%d CRLF=%d 字节=%d' % (_w.count(b'\n'), _w.count(b'\r\n'), len(_w)))
assert _w.count(b'\r\n') == 0
print('v3b 落盘 + 语法校验通过')
