# -*- coding: utf-8 -*-
"""C6 观察规则补丁（低位 + 适中振幅）。执行一次即失效，不要重跑。

改 2 个文件：
  strategy\\base.py                  (纯 CRLF) —— C6 常量 + is_c6_candidate()
  services\\band_pattern_engine.py   (纯 LF)  —— 字段/写入/扫描/UI 文案/漏斗
"""
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\QuantMonitorV6\strategy\base.py'
ENG = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = '.bak_before_c6_20261010_2228'


def load(p):
    with open(p, 'rb') as f:
        raw = f.read()
    crlf = raw.count(b'\r\n')
    lf = raw.count(b'\n') - crlf
    s = raw.decode('utf-8')
    return s, s.replace('\r\n', '\n'), crlf, lf


def save(p, s, crlf):
    out = s.replace('\n', '\r\n') if crlf else s
    with open(p, 'wb') as f:
        f.write(out.encode('utf-8'))


def rep(s, old, new, tag, n=1):
    c = s.count(old)
    assert c == n, '锚点命中 %d 次（期望 %d）: %s' % (c, n, tag)
    return s.replace(old, new)


# ============================================================ base.py
s, t, crlf, lf = load(BASE)
print('base.py: CRLF=%d 裸LF=%d' % (crlf, lf))
shutil.copy2(BASE, BASE + BAK)

C6_CONST = '''# ---- C6 观察规则阈值（2026-10-10）----
# 「低位 + 适中振幅」两条 AND —— 就是 C4 去掉量价结构那两条之后的子集。
# 实测（tools\\buildfactor_wide.csv：17570 条滚动观测 / 4401 只；复现脚本 tools\\_c6_calib.py）：
#   全样本基准        n=17570  r20=-0.80%  胜率 45.2%
#   仅低位 pos<0.25   n=10598  r20=+0.43%  胜率 49.5%  t=+3.73
#   仅适中振幅        n=10982  r20=+0.28%  胜率 49.2%  t=+2.63
#   ★ C6 两条叠加    n= 7749  r20=+0.66%  胜率 52.0%  t=+5.24  中位=+0.62%
#   （叠加后 > 两个分量的单独表现，说明两条不是重复计同一件事）
#   12 个「位置×振幅」阈值档位全部同向为正（+0.49% ~ +0.83%，t 4.1~6.0），
#   不是靠单一阈值凑出来的 —— 这一点比 C4 结实（C4 只有 219 条样本、t=+1.98）。
# 【重要】但逐锚点增量检验同样【未通过】：k20 -0.41 ｜ k40 -0.07 ｜ k60 +6.43 ｜ k80 -1.33
#   —— 4 个锚点里 3 个约为 0 或为负，正贡献几乎全部来自 k60（等权后增量 +1.15pp）。
#   所以 C6 和 C4 一样只能当【观察】用，禁止参与 signal_level / 建仓价 / 排序 / 等级。
# 反向证据（用来判断方向是否可信，不是巧合）：
#   低位 + 过低振幅(<2%)   n=254  r20=-0.76%  胜率 33.5%   <- 「死票」明显负
#   低位 + 过高振幅(>7%)   n=554  r20=+0.80%  胜率 44.8%   <- 靠少数暴涨拉起来，中位 -1.25%
#   低位区内振幅分档呈帐篷形：[3.5%,4.5%) 最好(+1.12%/54.6%)，两侧递减。
C6_POS_MAX = 0.25       # 近120根收盘位置上限（与 C4 同口径，勿单独改）
C6_AMP_LO = 0.025       # 20日均振幅下限 (high-low)/close
C6_AMP_HI = 0.055       # 20日均振幅上限
C6_MIN_BARS = 120       # 位置/振幅窗口要求的最少K线根数（不足直接判不可用）
'''
t = rep(t, 'C4_MIN_BARS = 120       # 位置/振幅/量比窗口要求的最少K线根数（不足直接判不可用）\n',
        'C4_MIN_BARS = 120       # 位置/振幅/量比窗口要求的最少K线根数（不足直接判不可用）\n\n'
        + C6_CONST, 'base C6 常量')

C6_FUNC = '''    @staticmethod
    def is_c6_candidate(df):
        """C6 观察规则：低位 + 适中振幅（= C4 去掉「上涨放量+下跌缩量」后的子集）。

        这是【观察】规则，不是建仓触发：只用来看这批形态后续怎么走。
        历史标定见 C6_* 常量注释 —— 样本量是 C4 的 35 倍、t 值高 2.6 倍、
        12 个阈值档位同向为正，但逐锚点增量 3/4 为负，所以仍然禁止当买入信号。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low，且不少于 C6_MIN_BARS(120) 根。
            （不需要 volume —— 本规则不含量价条件。）

        返回
        ----
        dict : {'ok': bool, 'n_ok': int, 'score': float, 'hits': list[bool],
                'pos120': float|None, 'amp': float|None, 'reason': str}
            ok     —— 位置与振幅两条是否都满足
            n_ok   —— 满足条数 0~2
            score  —— n_ok * 50（0/50/100 的纯计数强度分，不带权重）
            hits   —— [位置, 振幅] 逐个 bool
            reason —— 数据不足/异常时给出原因，正常为空字符串

        判据（与 tools\\\\_c6_calib.py 的口径逐位一致）
        ------------------------------------------
        1. pos120 < C6_POS_MAX(0.25)         近120根收盘位置 (close-min)/(max-min)
        2. C6_AMP_LO <= amp <= C6_AMP_HI     近20根 (high-low)/close 均值 ∈ [2.5%, 5.5%]
        """
        _bad = {'ok': False, 'n_ok': 0, 'score': 0.0, 'hits': [False, False],
                'pos120': None, 'amp': None, 'reason': ''}
        try:
            if df is None or len(df) < C6_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % C6_MIN_BARS
                return r
            for _c in ('close', 'high', 'low'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            closes = np.asarray(df['close'].values, dtype=float)
            highs = np.asarray(df['high'].values, dtype=float)
            lows = np.asarray(df['low'].values, dtype=float)
            # 1) 位置：近 120 根收盘
            c120 = closes[-120:]
            _lo, _hi = float(np.min(c120)), float(np.max(c120))
            pos = (float(closes[-1]) - _lo) / (_hi - _lo + 1e-8)
            # 2) 振幅：近 20 根 (high-low)/close 均值
            amp = float(np.mean((highs[-20:] - lows[-20:]) / (closes[-20:] + 1e-8)))
            hits = [bool(pos < C6_POS_MAX),
                    bool(C6_AMP_LO <= amp <= C6_AMP_HI)]
            n_ok = int(sum(1 for x in hits if x))
            return {'ok': bool(n_ok == 2), 'n_ok': n_ok,
                    'score': float(n_ok * 50.0), 'hits': hits,
                    'pos120': float(pos), 'amp': float(amp), 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r


'''
t = rep(t, "            r['reason'] = type(_e).__name__\n            return r\n\n\n\n"
           "# ============================================================\n"
           "# K线数据解析",
        "            r['reason'] = type(_e).__name__\n            return r\n\n\n" + C6_FUNC
        + "# ============================================================\n# K线数据解析",
        'base C6 方法')
save(BASE, t, crlf)
py_compile.compile(BASE, doraise=True)
print('base.py OK  (%d 行)' % (t.count('\n') + 1))

# ============================================================ engine
s, t, crlf, lf = load(ENG)
print('engine: CRLF=%d 裸LF=%d' % (crlf, lf))
shutil.copy2(ENG, ENG + BAK)

C6_ENG_CONST = '''
# ---- C6 观察规则（2026-10-10）低位 + 适中振幅 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.is_c6_candidate()。
# 标定复现见 tools\\_c6_calib.py（17570 条观测 / 4401 只 / 4 锚点，无未来数据）：
#   ★ C6 两条叠加 n=7749  r20=+0.66%  胜率 52.0%  t=+5.24（全样本基准 -0.80% / 45.2%）
#   12 个「位置×振幅」档位同向为正（+0.49%~+0.83%）；低位区内振幅呈帐篷形
#   （[3.5%,4.5%) 最好 +1.12%/54.6%，<2% 的死票 -0.76%/33.5%）。
#   **但逐锚点增量 3/4 为负**（k20 -0.41 ｜ k40 -0.07 ｜ k60 +6.43 ｜ k80 -1.33），
#   正贡献几乎全在 k60 —— 与 C4 同一个毛病。所以：
#     - 只做「观察」：不参与 signal_level / 建仓价 / 排序 / 等级；
#     - 文案固定为「C6观察：…」，禁止出现买入/启动/建仓类字样；
#     - 是否显示由 _C6_NOTE_MODE 控制（'off' 则只写字段不提示）。
_C6_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_C6_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'amp': 0, 'c6': 0, 'note': 0}
'''
t = rep(t, "_C4_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'vol': 0, 'amp': 0, 'ctrl': 0,\n"
           "              'c4': 0, 'note': 0}\n",
        "_C4_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'vol': 0, 'amp': 0, 'ctrl': 0,\n"
        "              'c4': 0, 'note': 0}\n" + C6_ENG_CONST, 'engine C6 常量')

t = rep(t, 'def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None):',
        'def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None):',
        'engine _ctrl_note 签名')

t = rep(t, '    同样由模块级 _C4_NOTE_MODE 控制（默认 \'watch\'，依据见该常量注释）。\n    """\n    out = []',
        '    同样由模块级 _C4_NOTE_MODE 控制（默认 \'watch\'，依据见该常量注释）。\n'
        '\n'
        '    c6\n'
        '    --\n'
        '    C6 观察规则的满足条数（0~2，来自 TechnicalIndicators.is_c6_candidate 的 n_ok），\n'
        '    默认 None。只有显式传入且 ==2 时才追加「C6观察：低位适中振幅」；\n'
        '    同样由模块级 _C6_NOTE_MODE 控制（默认 \'watch\'，依据见该常量注释）。\n'
        '    与 C4 / 建仓因子互相独立，任一条不通过都不影响其他文案。\n'
        '    """\n    out = []',
        'engine _ctrl_note docstring')

t = rep(t, "        # C4 观察文案（默认 'watch' 会追加；未通过逐锚点检验，只能观察，依据见常量注释）\n"
           "        if _C4_NOTE_MODE != 'off' and c4 is not None and int(c4) >= 5:\n"
           "            out.append('C4观察：低位量价结构')\n",
        "        # C4 观察文案（默认 'watch' 会追加；未通过逐锚点检验，只能观察，依据见常量注释）\n"
        "        if _C4_NOTE_MODE != 'off' and c4 is not None and int(c4) >= 5:\n"
        "            out.append('C4观察：低位量价结构')\n"
        "        # C6 观察文案（默认 'watch'；C4 去掉量价结构后的更稳子集，依据见常量注释）\n"
        "        if _C6_NOTE_MODE != 'off' and c6 is not None and int(c6) >= 2:\n"
        "            out.append('C6观察：低位适中振幅')\n",
        'engine C6 文案')

t = rep(t, "    ('c4_ok', 'INTEGER'), ('c4_score', 'REAL'),\n",
        "    ('c4_ok', 'INTEGER'), ('c4_score', 'REAL'),\n"
        "    ('c6_ok', 'INTEGER'), ('c6_score', 'REAL'),\n", 'engine _ALL_COLS')

t = rep(t, "             c4_ok, c4_score,\n",
        "             c4_ok, c4_score,\n             c6_ok, c6_score,\n", 'engine INSERT 列清单')

t = rep(t, "            rec.get('c4_ok',0), rec.get('c4_score',0),\n",
        "            rec.get('c4_ok',0), rec.get('c4_score',0),\n"
        "            rec.get('c6_ok',0), rec.get('c6_score',0),\n", 'engine INSERT 取值')

_old_ph = 'VALUES (' + ','.join(['?'] * 48) + ')'
_new_ph = 'VALUES (' + ','.join(['?'] * 50) + ')'
t = rep(t, _old_ph, _new_ph, 'engine 占位符 48->50')
print('INSERT 占位符：48 -> 50')

t = rep(t, '        _c4_n, _c4_ok, _c4_sc = 0, False, 0.0\n',
        '        _c4_n, _c4_ok, _c4_sc = 0, False, 0.0\n'
        '        _c6_n, _c6_ok, _c6_sc = 0, False, 0.0\n', 'engine scan_stock 局部变量')

t = rep(t, "                    if _c4_n >= 5:\n                        _C4_FUNNEL['c4'] += 1\n",
        "                    if _c4_n >= 5:\n                        _C4_FUNNEL['c4'] += 1\n"
        "                # C6 观察规则（复用同一个 df，不额外取数；不含量价条件）\n"
        "                _c6r = _ti.is_c6_candidate(_df)\n"
        "                _c6_n = int(_c6r.get('n_ok') or 0)\n"
        "                _c6_ok = bool(_c6r.get('ok'))\n"
        "                _c6_sc = float(_c6r.get('score') or 0.0)\n"
        "                _c6h = _c6r.get('hits') or [False, False]\n"
        "                if _c6r.get('reason'):\n"
        "                    _C6_FUNNEL['insuf'] += 1\n"
        "                else:\n"
        "                    _C6_FUNNEL['ok'] += 1\n"
        "                    if _c6h[0]:\n"
        "                        _C6_FUNNEL['pos'] += 1\n"
        "                    if _c6h[1]:\n"
        "                        _C6_FUNNEL['amp'] += 1\n"
        "                    if _c6_n >= 2:\n"
        "                        _C6_FUNNEL['c6'] += 1\n", 'engine C6 计算块')

t = rep(t, '        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n)\n',
        '        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n, _c6_n)\n',
        'engine _ctrl_note 调用')

t = rep(t, "        if _c4_ok and _C4_NOTE_MODE != 'off':\n            _C4_FUNNEL['note'] += 1\n",
        "        if _c4_ok and _C4_NOTE_MODE != 'off':\n            _C4_FUNNEL['note'] += 1\n"
        "        if _c6_ok and _C6_NOTE_MODE != 'off':\n            _C6_FUNNEL['note'] += 1\n",
        'engine C6 文案计数')

t = rep(t, "                'c4_ok': 1 if _c4_ok else 0, 'c4_score': _c4_sc,\n",
        "                'c4_ok': 1 if _c4_ok else 0, 'c4_score': _c4_sc,\n"
        "                'c6_ok': 1 if _c6_ok else 0, 'c6_score': _c6_sc,\n", 'engine rec 字段')

t = rep(t, '        for _k in _C4_FUNNEL:\n            _C4_FUNNEL[_k] = 0\n',
        '        for _k in _C4_FUNNEL:\n            _C4_FUNNEL[_k] = 0\n'
        '        for _k in _C6_FUNNEL:\n            _C6_FUNNEL[_k] = 0\n', 'engine C6 清零')

t = rep(t, "            print('[C4观察] K线不足%d根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'\n"
           "                  % (120, _c4f['insuf'], _c4f['note']), flush=True)\n",
        "            print('[C4观察] K线不足%d根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'\n"
        "                  % (120, _c4f['insuf'], _c4f['note']), flush=True)\n"
        "            _c6f = _C6_FUNNEL\n"
        "            print('[C6观察] 可算 %d 只 ｜ 位置达标 %d ｜ 振幅达标 %d ｜ 两条全中 %d ｜ 文案开关 _C6_NOTE_MODE=%s'\n"
        "                  % (_c6f['ok'], _c6f['pos'], _c6f['amp'], _c6f['c6'],\n"
        "                     _C6_NOTE_MODE), flush=True)\n"
        "            print('[C6观察] K线不足120根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'\n"
        "                  % (_c6f['insuf'], _c6f['note']), flush=True)\n",
        'engine C6 汇总打印')

save(ENG, t, crlf)
py_compile.compile(ENG, doraise=True)
print('engine OK  (%d 行)' % (t.count('\n') + 1))
print('备份：%s%s / %s%s' % (BASE, BAK, ENG, BAK))
print('补丁完成')
