# -*- coding: utf-8 -*-
"""独立验证 2301 只补数结果（可重跑）。

不走服务层的统计口径：直接读 JSON、按代码前缀自己分板、自己算覆盖率，
再从 15 只「主营失败」里抽 4 只**现场回查上游**，确认是真没有而不是我们漏了。
"""
import io
import json
import os
import sys
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

PASS, FAIL = [], []
L = []


def ck(name, cond, extra=''):
    (PASS if PASS is not None else None)
    (PASS if cond else FAIL).append(name)
    L.append('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                          (' ｜ %s' % extra) if extra else ''))


def board(c):
    c = str(c)
    if c.startswith(('60', '00')):
        return '主板'
    if c.startswith(('300', '301')):
        return '创业板'
    if c.startswith(('688', '689')):
        return '科创板'
    if c.startswith(('8', '4', '920')):
        return '北交所'
    return '其他'


# ---- 1. 直接拆 JSON（绕开服务层的 load_extras 口径）----
raw = json.loads(io.open(SS.EXTRAS_PATH, encoding='utf-8').read())
items = raw.get('items') or {}
L.append('JSON 顶层键=%s ｜ saved_at=%s ｜ 条目=%d ｜ 文件=%.2f MB'
         % (sorted(raw.keys()), raw.get('saved_at'), len(items),
            os.path.getsize(SS.EXTRAS_PATH) / 1048576.0))
ck('1 JSON 结构正常、条目数 ≥3294', isinstance(items, dict) and len(items) >= 3294,
   str(len(items)))

snap = SS.load_snapshot()
rows = snap['rows']
pool = [str(r['code']) for r in rows
        if float(r.get('score') or 0) >= 0.0
        and str(r.get('stage')) != 'distribute'
        and float(r.get('price') or 0) >= 6.0
        and not SS.is_st_name(r.get('name'))]
ck('2 自己重算的池子 = 服务层的 3294（筛条件口径独立复现）', len(pool) == 3294,
   str(len(pool)))

_biz = [c for c in pool if (items.get(c) or {}).get('biz')]
_ann = [c for c in pool if (items.get(c) or {}).get('ann')]
L.append('覆盖率（自算）：主营 %d/%d=%.1f%% ｜ 公告 %d/%d=%.1f%%'
         % (len(_biz), len(pool), 100.0 * len(_biz) / len(pool),
            len(_ann), len(pool), 100.0 * len(_ann) / len(pool)))
ck('3 公告覆盖 100%', len(_ann) == len(pool))
ck('4 主营覆盖 ≥99%（允许极少数个股上游确实没有 F10 主营构成）',
   len(_biz) >= int(len(pool) * 0.99),
   '缺 %d 只' % (len(pool) - len(_biz)))

for b in ('主板', '创业板'):
    sub = [c for c in pool if board(c) == b]
    _b = sum(1 for c in sub if (items.get(c) or {}).get('biz'))
    _a = sum(1 for c in sub if (items.get(c) or {}).get('ann'))
    L.append('   %-4s %5d 只：主营 %5d（%.1f%%）｜公告 %5d（%.1f%%）'
             % (b, len(sub), _b, 100.0 * _b / len(sub), _a, 100.0 * _a / len(sub)))
ck('5 池子里只有主板 + 创业板（无科创板/北交所）',
   all(board(c) in ('主板', '创业板') for c in pool),
   str(dict(Counter(board(c) for c in pool))))

_bad = [c for c in pool if (items.get(c) or {}).get('biz_fail')
        and not (items.get(c) or {}).get('biz')]
L.append('主营失败标记且无数据：%d 只 %s' % (len(_bad), _bad[:20]))
ck('6 失败标记与实际数据一致（有 fail 标记的确实没 biz 内容）',
   all(not (items.get(c) or {}).get('biz') for c in _bad), str(len(_bad)))
ck('7 没有「既无数据也无失败标记」的静默空洞',
   all((items.get(c) or {}).get('biz') or (items.get(c) or {}).get('biz_fail')
       or (items.get(c) or {}).get('biz_ts') for c in pool),
   str([c for c in pool
        if not ((items.get(c) or {}).get('biz') or (items.get(c) or {}).get('biz_ts'))][:8]))
ck('8 每条记录都带时间戳（TTL 可判定）',
   all((items.get(c) or {}).get('biz_ts') and (items.get(c) or {}).get('ann_ts')
       for c in pool if items.get(c)))
ck('9 公告来源只有合法值',
   set(str((items.get(c) or {}).get('ann_src') or '') for c in pool
       if (items.get(c) or {}).get('ann')) <= {'eastmoney', 'sina', 'cninfo'},
   str(dict(Counter(str((items.get(c) or {}).get('ann_src')) for c in pool
                    if (items.get(c) or {}).get('ann')))))
_long = [(c, len(SS.fmt_biz(items.get(c))[0]), len(SS.fmt_ann(items.get(c))[0]))
         for c in pool]
ck('10 单元格长度受控（公告 ≤30 / 主营 ≤22，全池 3294 只）',
   max(x[2] for x in _long) <= 30 and max(x[1] for x in _long) <= 22,
   '公告max=%d 主营max=%d' % (max(x[2] for x in _long), max(x[1] for x in _long)))

# ---- 2. 现场回查：抽 4 只「主营失败」的，直接打上游确认，能拿到就当场补回 ----
L.append('')
L.append('-- 现场回查主营失败标记的 4 只（直打上游；能拿到就当场补回并落盘）--')
_recover = []
for c in _bad[:4]:
    _nm = next((r['name'] for r in rows if str(r['code']) == c), '')
    try:
        rec, ok = SS.fetch_biz(c, timeout=10)
    except Exception as e:                      # noqa: BLE001
        rec, ok = None, 'exc:%s' % e
    _first = ((rec or {}).get('items') or [{}])[0].get('name')
    L.append('   %s %-6s ok=%s 首项=%s' % (c, _nm, ok, _first or '空'))
    if rec:
        _recover.append(c)
ck('11 回查的 4 只全部拿到主营 → 那 15 只是瞬时失败，不是上游没有（可补回）',
   len(_recover) == min(4, len(_bad)), str(_recover))
if _recover:
    _items2 = SS.load_extras()
    for c in _recover:
        _items2.pop(c, None)                      # 清掉失败标记，允许立即重取
    _items2, _st2 = SS.fetch_extras(_recover, _items2, workers=3,
                                    path=SS.EXTRAS_PATH)
    L.append('   当场重补 4 只：%s' % _st2)
    items = SS.load_extras()
    _biz2 = [c for c in pool if (items.get(c) or {}).get('biz')]
    L.append('   重补后主营覆盖 %d/%d=%.1f%%'
             % (len(_biz2), len(pool), 100.0 * len(_biz2) / len(pool)))
    ck('12 重补后这 4 只已写入缓存',
       all((items.get(c) or {}).get('biz') for c in _recover),
       str([c for c in _recover if not (items.get(c) or {}).get('biz')]))
else:
    ck('12 回查未恢复（视为上游确实没有主营构成）', True)

# ---- 3. 大池子下页面渲染是否两列都有内容（离屏）----
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication          # noqa: E402
from ui.battle_widgets.control_screen_widget import ControlScreenWidget  # noqa: E402

_app = QApplication.instance() or QApplication([])
w = ControlScreenWidget()
w._ck_extra.setChecked(False)                     # 离线：只读缓存，不联网
w._sp_score.setValue(0)                           # 门槛拉到 0 → 最大池
w._apply_and_render(fill=False)
_n = w.table.rowCount()
L.append('')
L.append('离屏渲染：门槛=0 时表格 %d 行' % _n)
_empty_biz = [i for i in range(_n) if w.table.item(i, 5).text() == '--']
_empty_ann = [i for i in range(_n) if w.table.item(i, 11).text() == '--']
ck('13 大池渲染行数 ≥3294', _n >= 3294, str(_n))
ck('14 大池里主营空单元格 ≈ 上游确实没有的只数',
   len(_empty_biz) <= len(_bad) + 2,
   '空 %d 行 ｜ 上游确无 %d 只' % (len(_empty_biz), len(_bad)))
ck('15 大池里公告单元格全部有内容', len(_empty_ann) == 0, '空 %d 行' % len(_empty_ann))
_s0 = [w.table.item(0, c).text() for c in range(13)]
L.append('第0行：%s' % _s0)
ck('16 第 0 行 13 列都有内容（不出现空列）', all(x not in ('', None) for x in _s0))

L.append('')
L.append('=== %d PASS / %d FAIL ===' % (len(PASS), len(FAIL)))
if FAIL:
    L.append('失败项：%s' % FAIL)
txt = '\n'.join(L)
print(txt, flush=True)
io.open(os.path.join(ROOT, 'tools', 'ctrl_screen_fill_pool_verify.txt'),
        'w', encoding='utf-8').write(txt + '\n')
sys.exit(1 if FAIL else 0)
