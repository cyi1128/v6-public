# -*- coding: utf-8 -*-
"""一次性补丁：把「拉升阶段识别」接进 services/band_pattern_engine.py（2026-10-11）。

7 处同步（少一处字段就会全 0 / 列错位）：
  1) 常量块 _MARKUP_NOTE_MODE + _MARKUP_FUNNEL
  2) _ctrl_note 参数 + docstring + 调用
  3) _observe_tags 参数 + 文案
  4) _ALL_COLS +3 列（markup_ok / markup_type / markup_score）
  5) _save_or_update 列清单 + 占位符 56 -> 59 + 取值
  6) scan_stock 局部量 + 计算块 + tip 调用 + 计数器 + rec
  7) scan_all 漏斗清零 + 打印
"""
import io
import os
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
TGT = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = TGT + '.bak_before_markup'
NEW_COLS = 3

CONSTS = '''
# ---- 拉升阶段识别（2026-10-11）阶梯式上行 / 缩量强势 / 加速迹象 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.detect_markup()。
# ⚠ 方向说明（别用反）：C4 / C6 / 试盘找的是「低位、启动前」；本因子找的是「已经拉起来」。
#   在本项目「买在启动前、不接飞刀」的框架下，它是【追高提示 / 排他标记】，不是买入提示。
# 实盘标定见 tools\\markup_calib.txt（tools\\_calib_markup.py 生成；锚点 k=20/40/60/80，无未来数据）。
# 只做【观察】：不参与 signal_level / 建仓价 / 排序 / 等级。
_MARKUP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_MARKUP_FUNNEL = {'ok': 0, 'insuf': 0, 'trend': 0, 'lock': 0,
                  'acc': 0, 'hit': 0, 'note': 0}
'''

COMPUTE = '''                # 拉升阶段识别（复用同一个 df；只做观察）
                _mr = _ti.detect_markup(_df)
                _markup_ok = bool(_mr.get('ok'))
                _markup_sc = float(_mr.get('score') or 0.0)
                _markup_type = _mr.get('type') or ''
                if _mr.get('reason'):
                    _MARKUP_FUNNEL['insuf'] += 1
                else:
                    _MARKUP_FUNNEL['ok'] += 1
                    if _markup_ok:
                        _MARKUP_FUNNEL['hit'] += 1
                        if _markup_type == '阶梯式上行':
                            _MARKUP_FUNNEL['trend'] += 1
                        elif _markup_type == '缩量强势':
                            _MARKUP_FUNNEL['lock'] += 1
                        elif _markup_type == '加速迹象':
                            _MARKUP_FUNNEL['acc'] += 1
'''

PRINT = '''            _mkf = _MARKUP_FUNNEL
            print('[拉升观察] 可算 %d 只 ｜ 阶梯式上行 %d ｜ 缩量强势 %d ｜ 加速迹象 %d ｜ 命中合计 %d ｜ 文案开关 _MARKUP_NOTE_MODE=%s'
                  % (_mkf['ok'], _mkf['trend'], _mkf['lock'], _mkf['acc'],
                     _mkf['hit'], _MARKUP_NOTE_MODE), flush=True)
            print('[拉升观察] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_mkf['insuf'], _mkf['note']), flush=True)
'''


def main():
    raw = io.open(TGT, 'rb').read()
    lf = raw.count(b'\n') - raw.count(b'\r\n')
    print('改动前：CRLF=%d 裸LF=%d 行数=%d' % (raw.count(b'\r\n'), lf, raw.count(b'\n')))
    assert raw.count(b'\r\n') == 0, '引擎不是纯 LF，先人工确认'

    shutil.copy2(TGT, BAK)
    print('已备份 ->', os.path.basename(BAK))

    s = raw.decode('utf-8')

    REP = [
        # 1) 常量块
        ("_WASH_NOTE_MODE = 'off'   # 'off' 不出洗盘文案（默认，依据见上）；'watch' 恢复旧文案\n",
         "_WASH_NOTE_MODE = 'off'   # 'off' 不出洗盘文案（默认，依据见上）；'watch' 恢复旧文案\n"
         + CONSTS),
        # 2) _ctrl_note 签名
        ("def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None,\n"
         "               probe=None, distpat=None):\n",
         "def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None,\n"
         "               probe=None, distpat=None, markup=None):\n"),
        # 3) _ctrl_note docstring
        ("              两者同样受 _PROBE_NOTE_MODE / _DISTP_NOTE_MODE 控制。\n    \"\"\"\n",
         "              两者同样受 _PROBE_NOTE_MODE / _DISTP_NOTE_MODE 控制。\n"
         "\n"
         "    markup\n"
         "    ------\n"
         "    拉升阶段识别的类型（TechnicalIndicators.detect_markup 的 type），默认 None。\n"
         "    非空时追加「拉升观察：<类型>」。**方向与试盘相反**：这是【追高提示 / 排他标记】，\n"
         "    不是买入提示（依据见 _MARKUP_NOTE_MODE 注释）。\n"
         "    \"\"\"\n"),
        # 4) _ctrl_note 调用
        ("    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)\n"
         "                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl,\n"
         "                                      probe, distpat))\n",
         "    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)\n"
         "                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl,\n"
         "                                      probe, distpat, markup))\n"),
        # 5) _observe_tags 签名
        ("def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False,\n"
         "                  probe=None, distpat=None):\n",
         "def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False,\n"
         "                  probe=None, distpat=None, markup=None):\n"),
        # 6) _observe_tags docstring 首行
        ("    \"\"\"只返回「观察类」文案（建仓因子 + C4 + C6），与控盘提示分开。\n",
         "    \"\"\"只返回「观察类」文案（建仓因子 + C4 + C6 + 试盘 + 出货形态 + 拉升），与控盘提示分开。\n"),
        # 7) _observe_tags 文案
        ("        # 出货形态确认文案（默认 'watch'；与「出货风险警示」并列，不替代）\n"
         "        if _DISTP_NOTE_MODE != 'off' and distpat:\n"
         "            out.append('出货形态观察：%s' % distpat)\n",
         "        # 出货形态确认文案（默认 'watch'；与「出货风险警示」并列，不替代）\n"
         "        if _DISTP_NOTE_MODE != 'off' and distpat:\n"
         "            out.append('出货形态观察：%s' % distpat)\n"
         "        # 拉升阶段识别文案（默认 'watch'；与试盘/出货形态同为观察类，方向见常量注释）\n"
         "        if _MARKUP_NOTE_MODE != 'off' and markup:\n"
         "            out.append('拉升观察：%s' % markup)\n"),
        # 8) _ALL_COLS
        ("    ('dist_pattern_ok', 'INTEGER'), ('dist_pattern_type', 'TEXT'),\n"
         "    ('dist_pattern_score', 'REAL'),\n",
         "    ('dist_pattern_ok', 'INTEGER'), ('dist_pattern_type', 'TEXT'),\n"
         "    ('dist_pattern_score', 'REAL'),\n"
         "    ('markup_ok', 'INTEGER'), ('markup_type', 'TEXT'),\n"
         "    ('markup_score', 'REAL'),\n"),
        # 9) INSERT 列清单
        ("             dist_pattern_ok, dist_pattern_type, dist_pattern_score,\n"
         "             created_at, updated_at)\n",
         "             dist_pattern_ok, dist_pattern_type, dist_pattern_score,\n"
         "             markup_ok, markup_type, markup_score,\n"
         "             created_at, updated_at)\n"),
        # 10) 取值
        ("            rec.get('dist_pattern_ok',0), rec.get('dist_pattern_type',''),\n"
         "            rec.get('dist_pattern_score',0),\n",
         "            rec.get('dist_pattern_ok',0), rec.get('dist_pattern_type',''),\n"
         "            rec.get('dist_pattern_score',0),\n"
         "            rec.get('markup_ok',0), rec.get('markup_type',''),\n"
         "            rec.get('markup_score',0),\n"),
        # 11) scan_stock 局部量
        ("        _distp_ok, _distp_sc, _distp_type = False, 0.0, ''\n",
         "        _distp_ok, _distp_sc, _distp_type = False, 0.0, ''\n"
         "        _markup_ok, _markup_sc, _markup_type = False, 0.0, ''\n"),
        # 12) scan_stock 计算块
        ("                        elif _distp_type == '\\u53cc\\u9876\\u96cf\\u5f62':\n"
         "                            _DISTP_FUNNEL['dtop'] += 1\n",
         "                        elif _distp_type == '\\u53cc\\u9876\\u96cf\\u5f62':\n"
         "                            _DISTP_FUNNEL['dtop'] += 1\n" + COMPUTE),
        # 13) tip 调用
        ("        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n,\n"
         "                               _c6_n, _probe_ok, _distp_type)\n",
         "        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n,\n"
         "                               _c6_n, _probe_ok, _distp_type, _markup_type)\n"),
        # 14) 计数器
        ("        if _distp_ok and _DISTP_NOTE_MODE != 'off':\n"
         "            _DISTP_FUNNEL['note'] += 1\n",
         "        if _distp_ok and _DISTP_NOTE_MODE != 'off':\n"
         "            _DISTP_FUNNEL['note'] += 1\n"
         "        if _markup_ok and _MARKUP_NOTE_MODE != 'off':\n"
         "            _MARKUP_FUNNEL['note'] += 1\n"),
        # 15) rec
        ("                'dist_pattern_ok': 1 if _distp_ok else 0,\n"
         "                'dist_pattern_type': _distp_type,\n"
         "                'dist_pattern_score': _distp_sc,\n",
         "                'dist_pattern_ok': 1 if _distp_ok else 0,\n"
         "                'dist_pattern_type': _distp_type,\n"
         "                'dist_pattern_score': _distp_sc,\n"
         "                'markup_ok': 1 if _markup_ok else 0,\n"
         "                'markup_type': _markup_type,\n"
         "                'markup_score': _markup_sc,\n"),
        # 16) scan_all 漏斗清零
        ("        for _k in _DISTP_FUNNEL:\n"
         "            _DISTP_FUNNEL[_k] = 0\n",
         "        for _k in _DISTP_FUNNEL:\n"
         "            _DISTP_FUNNEL[_k] = 0\n"
         "        for _k in _MARKUP_FUNNEL:\n"
         "            _MARKUP_FUNNEL[_k] = 0\n"),
        # 17) scan_all 打印
        ("            print('[出货形态] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'\n"
         "                  % (_dpf['insuf'], _dpf['note']), flush=True)\n",
         "            print('[出货形态] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'\n"
         "                  % (_dpf['insuf'], _dpf['note']), flush=True)\n" + PRINT),
    ]

    for i, (old, new) in enumerate(REP, 1):
        cnt = s.count(old)
        assert cnt == 1, '第 %d 处锚点命中 %d 次' % (i, cnt)
        s = s.replace(old, new)

    # 占位符 56 -> 59
    lines = s.split('\n')
    hits = [i for i, ln in enumerate(lines) if ln.startswith('            VALUES (?')]
    assert len(hits) == 1, 'VALUES 行数量异常: %d' % len(hits)
    hv = hits[0]
    old_q = lines[hv]
    assert old_q.count('?') == 56, '原占位符不是 56 个: %d' % old_q.count('?')
    lines[hv] = ('            VALUES (' + ','.join(['?'] * (56 + NEW_COLS))
                 + ')""", (')
    s = '\n'.join(lines)
    assert lines[hv].count('?') == 56 + NEW_COLS, '占位符数量不对'

    # 字段顺序自检：INSERT 列清单必须与 rec 取值一一对应
    i_col = s.index('            markup_ok, markup_type, markup_score,\n')
    i_val = s.index("            rec.get('markup_ok',0), rec.get('markup_type',''),\n")
    assert i_col < i_val, '列清单/取值顺序异常'
    assert s.count("rec.get('markup_score',0),") == 1

    io.open(TGT, 'wb').write(s.encode('utf-8'))
    raw2 = io.open(TGT, 'rb').read()
    print('改动后：CRLF=%d 裸LF=%d 行数=%d 占位符=%d'
          % (raw2.count(b'\r\n'), raw2.count(b'\n') - raw2.count(b'\r\n'),
             raw2.count(b'\n'), raw2.decode('utf-8').count('VALUES (')))
    assert raw2.count(b'\r\n') == 0
    py_compile.compile(TGT, doraise=True)
    print('py_compile OK')


if __name__ == '__main__':
    main()
