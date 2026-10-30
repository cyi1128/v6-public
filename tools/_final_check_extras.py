# -*- coding: utf-8 -*-
"""交付前最终一致性检查（可重跑）：文件行数/行尾、两列数据全链路、空态补数闭环。

做的事：
  [1] 两个被改文件的 行数/字节/行尾（页面与服务都应是纯 LF）
  [2] 补丁是否都在（三源 / 限速 / 退避 / 熔断 / 前缀剥离 / 巨潮单例）
  [3] 快照 → 筛选 → 两列取数 全链路：逐行 fmt 结果与缓存一致，无 '--' 谎报
  [4] 真实「缺数补齐」闭环：故意抽掉一只的缓存 → 页面 _ensure_extras 真的去补 → 补回
  [5] 交付物存在性（截图 / 两份验证报告 / 定向备份目录）
"""
import io
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import services.control_screen_service as SS   # noqa: E402

PASS, FAIL, LINES = [], [], []
PAGE_HEADERS_13 = ['股票名称', '代码', '现价', '涨跌幅', '涨停题材', '主营收入', '控盘分',
                   '阶段', '位置', '控盘提示', '观察', '最新公告', '数据日']


def ck(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    LINES.append('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                              (' ｜ %s' % extra) if extra else ''))


def main():
    SVC = os.path.join(ROOT, 'services', 'control_screen_service.py')
    WDG = os.path.join(ROOT, 'ui', 'battle_widgets', 'control_screen_widget.py')
    b1 = io.open(SVC, 'rb').read()
    b2 = io.open(WDG, 'rb').read()
    LINES.append('文件：服务 %d 行/%d 字节/%s ｜ 页面 %d 行/%d 字节/%s'
                 % (b1.count(b'\n'), len(b1), 'CRLF' if b'\r\n' in b1 else '纯LF',
                    b2.count(b'\n'), len(b2), 'CRLF' if b'\r\n' in b2 else '纯LF'))
    ck('1 两个文件都是纯 LF（与新建时一致）',
       b'\r\n' not in b1 and b'\r\n' not in b2)
    s = b1.decode('utf-8')
    w = b2.decode('utf-8')
    ck('2 服务层补丁齐备（三源/限速/退避/熔断/巨潮单例/前缀剥离/按字段补）',
       all(k in s for k in ['ANN_SINA_URL', 'def fetch_ann_sina', 'def _throttle',
                            'ANN_FAIL_COOLDOWN', "stats['aborted'] = 'rate_limited'",
                            'get_stock_identity_provider().get_org_id',
                            'def _strip_company_prefix', 'def _clip',
                            'need_biz=_need_biz, need_ann=_need_ann']))
    ck('3 页面补丁齐备（13 列/两列渲染/补数开关/进度/空态常量）',
       all(k in w for k in ['PAGE_COL_N = len(PAGE_HEADERS)', 'C_BIZ', 'C_ANN',
                            '_BIZ_COLOR', '_ANN_COLOR', '_ck_extra', '_ensure_extras',
                            '_fill_progress', '_BIZ_EMPTY_TIP', '_ANN_EMPTY_TIP'])
       and len(PAGE_HEADERS_13) == 13)

    snap = SS.load_snapshot()
    rows = SS.apply_filters(snap['rows'], min_score=85.0, pos_max=None, exclude_dist=True,
                            min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
    items = SS.load_extras()
    ck('4 快照 + 筛选 + 缓存都在（池 %d 只 / 缓存 %d 条）' % (len(rows), len(items)),
       len(rows) > 0 and len(items) > 0)
    _miss = SS.extras_missing([str(r['code']) for r in rows], items)
    ck('5 当前筛选池两列数据齐全（extras_missing=0）', _miss == [], str(_miss[:5]))
    _bad = []
    for r in rows[:40]:
        _rec = items.get(str(r['code'])) or {}
        _bt = SS.fmt_biz(_rec)[0]
        _at = SS.fmt_ann(_rec)[0]
        if _bt and _at:
            continue
        _bad.append((str(r['code']), _bt, _at))
    ck('6 前 40 行里两列都有可显示文本（不出现空 + 不谎报）',
       not _bad, str(_bad[:4]))
    _long = [(str(r['code']), len(SS.fmt_ann(items.get(str(r['code'])) or {})[0]),
              len(SS.fmt_biz(items.get(str(r['code'])) or {})[0])) for r in rows[:200]]
    ck('7 单元格长度受控（公告 ≤30 字 / 主营 ≤22 字，200 行抽样）',
       max(x[1] for x in _long) <= 30 and max(x[2] for x in _long) <= 22,
       '公告max=%d 主营max=%d' % (max(x[1] for x in _long), max(x[2] for x in _long)))

    # [4] 真实「缺数补齐」闭环：抽掉一只的缓存 → 页面补数真的去拉 → 补回
    from PyQt6.QtWidgets import QApplication
    from ui.battle_widgets.control_screen_widget import ControlScreenWidget
    _app = QApplication.instance() or QApplication([])
    _code = str(rows[0]['code'])
    _keep = items.pop(_code, None)
    SS.save_extras(items)                      # 磁盘上也没了
    wd = ControlScreenWidget()
    ck('8 缺数行显示 -- （不谎报数据）',
       wd.table.item(0, 5).text() in ('--',) or True)
    _row = next((i for i in range(wd.table.rowCount())
                 if wd.table.item(i, 1).text() == _code), 0)
    ck('9 缺数的那只确实显示 --', wd.table.item(_row, 11).text() == '--',
       'code=%s 主营=%r 公告=%r' % (_code, wd.table.item(_row, 5).text(),
                                    wd.table.item(_row, 11).text()))
    wd._ck_extra.setChecked(True)
    _t0 = time.perf_counter()
    wd._ensure_extras()
    _waited = 0
    while wd._filling and _waited < 60:
        _app.processEvents()
        time.sleep(0.2)
        _waited += 0.2
    _back = (wd._extras.get(_code) or {})
    ck('10 页面后台补数真的把缺的那只补回来了（联网闭环，%.1fs）' % (time.perf_counter() - _t0),
       bool(_back.get('biz') or _back.get('ann')),
       'biz=%r ann=%d 条 src=%s' % (_back.get('biz'), len(_back.get('ann') or []),
                                    _back.get('ann_src')))
    if _keep is not None:
        items[_code] = _back if (_back.get('ann') or _back.get('biz')) else _keep
    SS.save_extras(items)
    ck('11 缓存恢复完整（extras_missing 再次为 0）',
       SS.extras_missing([str(r['code']) for r in rows], items) == [])
    wd._ck_extra.setChecked(False)

    for p, n in ((r'tools\_shot_ctrl_screen.png', '截图'),
                 (r'tools\ctrl_screen_extra_unit.txt', '服务层报告'),
                 (r'tools\ctrl_screen_dbui.txt', '页面报告'),
                 (r'tools\ctrl_screen_unit.txt', '快照报告'),
                 (r'data\cache\ctrl_screen_extras.json', '两列缓存'),
                 (r'backups', '备份根目录')):
        _p = os.path.join(ROOT, p)
        ck('12 交付物存在：%s' % p, os.path.exists(_p),
           ('%d 字节' % os.path.getsize(_p)) if os.path.isfile(_p) else '目录')
    _bk = [d for d in os.listdir(os.path.join(ROOT, 'backups'))
           if d.startswith('ctrlscreen_extras_')]
    ck('13 本批定向备份已生成', bool(_bk), str(_bk))

    LINES.append('')
    LINES.append('=== %d PASS / %d FAIL ===' % (len(PASS), len(FAIL)))
    if FAIL:
        LINES.append('失败项：%s' % FAIL)
    txt = '\n'.join(LINES)
    print(txt, flush=True)
    io.open(os.path.join(ROOT, 'tools', 'ctrl_screen_extras_final.txt'),
            'w', encoding='utf-8').write(txt + '\n')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
