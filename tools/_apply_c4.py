# -*- coding: utf-8 -*-
"""C4 补丁：strategy/base.py（CRLF）+ services/band_pattern_engine.py（LF）

约定：先 shutil.copy2 备份 -> assert s.count(old)==1 -> 替换 -> 按原行尾写回 -> py_compile。
执行一次即失效，不可重跑（锚点会被替换掉）。
"""
import os
import re
import shutil
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'D:\QuantMonitorV6'
STAMP = time.strftime('%Y%m%d_%H%M')
BASE = os.path.join(ROOT, 'strategy', 'base.py')
ENG = os.path.join(ROOT, 'services', 'band_pattern_engine.py')


def load(p):
    """读文件：统一返回 LF 归一化文本（项目约定），并记录原始行尾供写回用。"""
    with open(p, 'rb') as f:
        raw = f.read()
    crlf = raw.count(b'\r\n')
    lf = raw.count(b'\n')
    txt = raw.decode('utf-8')
    n_lf = lf - crlf          # 裸 LF 数量
    if crlf and not n_lf:     # 纯 CRLF -> 归一化为 LF 便于锚点匹配
        txt = txt.replace('\r\n', '\n')
    return txt, crlf, n_lf


def save(p, txt, crlf):
    if crlf:                      # 纯 CRLF 文件：先把裸 LF 补成 CRLF
        txt = txt.replace('\r\n', '\n').replace('\n', '\r\n')
    with open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(txt)


def pyc(p):
    import py_compile
    py_compile.compile(p, doraise=True)
    return 'py_compile OK'


# ==========================================================
# 1) strategy/base.py
# ==========================================================
s, crlf, lf = load(BASE)
print('[base.py] 改前 %d 行 | CRLF=%d 裸LF=%d' % (s.count('\n') + 1, crlf, lf - crlf if crlf else lf))
shutil.copy2(BASE, BASE + '.bak_before_c4_' + STAMP)
print('[base.py] 备份 -> %s' % os.path.basename(BASE + '.bak_before_c4_' + STAMP))

OLD_C = """BUILD_HIT_REDFAT = 65.0         # 红肥绿瘦分 >= 该值 -> 报「红肥绿瘦建仓特征」

MODEL_LIMIT_PULLBACK = "涨停回调\""""
NEW_C = """BUILD_HIT_REDFAT = 65.0         # 红肥绿瘦分 >= 该值 -> 报「红肥绿瘦建仓特征」

# ---- C4 观察规则阈值（2026-10-10）----
# 「低位 + 上涨放量 + 下跌缩量 + 适中振幅 + 控盘分」五条 AND。
# 实测（tools\\buildfactor_wide.csv：17570 条滚动观测 / 4401 只 / 锚点 k=20/40/60/80，
# 每个锚点只喂截断到 T 的 120 根，严格无未来数据）：
#   命中口径 pos<0.25 & up>1.15 & dn<0.95 & amp∈[2.5%,5.5%] & ctrl>=85
#     -> n=219  未来20日 +1.57%  胜率 59.4%  t=+1.98
#   ctrl>=80 的口径同向略强 -> n=300  +1.82%  胜率 61.0%  t=+2.81
#   （门槛取 85 是为了与全项目唯一的「高度控盘线」_CTRL_HIGH 对齐，改 80 只需改这一行。）
# 【重要】该组合【未通过逐锚点检验】：同锚点增量 k20 +0.21 ｜ k40 样本不足 ｜
#   k60 +5.01 ｜ k80 -3.14 —— 汇总为正主要来自样本集中在 k60（锚点构成偏差）。
#   同时「上涨放量+下跌缩量」单独用是 -1.66%（t=-6.31，n=2821），是负向条件。
#   因此 C4 只能当【观察】用，禁止参与 signal_level / 建仓价 / 排序。
#   去掉量价结构、只留 pos<0.25 & amp∈[2.5%,5.5%] 才是统计上更结实的口径
#   （n=7749 r20=+0.66% t=+5.24），但那是另一个组合，改动前先与用户确认。
C4_POS_MAX = 0.25       # 近120根收盘位置上限
C4_UP_MIN = 1.15        # 上涨日量比下限（上涨日均量 / 窗口均量，近20根）
C4_DN_MAX = 0.95        # 下跌日量比上限
C4_AMP_LO = 0.025       # 20日均振幅下限 (high-low)/close
C4_AMP_HI = 0.055       # 20日均振幅上限
C4_CTRL_MIN = 85.0      # 控盘分下限（与 band_pattern_engine._CTRL_HIGH 对齐）
C4_MIN_BARS = 120       # 位置/振幅/量比窗口要求的最少K线根数（不足直接判不可用）

MODEL_LIMIT_PULLBACK = "涨停回调\""""
assert s.count(OLD_C) == 1, 'base 常量锚点命中 %d 次' % s.count(OLD_C)
s = s.replace(OLD_C, NEW_C, 1)
print('[base.py] 已插入 C4_* 常量块（7 个）')

OLD_M = """        except Exception:
            return dict(_bad)



# ============================================================
# K线数据解析
# ============================================================"""
NEW_M = """        except Exception:
            return dict(_bad)


    @staticmethod
    def is_c4_candidate(df, ctrl_score=None):
        \"\"\"C4 观察规则：低位 + 上涨放量 + 下跌缩量 + 适中振幅 + 控盘分过滤。

        这是【观察】规则，不是建仓触发：只用来看这批形态后续怎么走。
        历史标定【未通过逐锚点检验】（见 C4_* 常量注释），禁止当买入信号使用。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low / volume，且不少于 C4_MIN_BARS(120) 根。
        ctrl_score : float | None
            已算好的控盘分，传入可省一次 estimate_control_score；None 则内部计算。

        返回
        ----
        dict : {'ok': bool, 'n_ok': int, 'score': float, 'hits': list[bool],
                'pos120': float|None, 'up_vol_ratio': float|None,
                'down_vol_ratio': float|None, 'amp': float|None,
                'ctrl_score': float|None, 'reason': str}
            ok      —— 5 个子条件是否全部满足
            n_ok    —— 满足的子条件个数 0~5
            score   —— n_ok * 20（0~100 的纯计数强度分，不带任何权重）
            hits    —— [位置, 上涨放量, 下跌缩量, 振幅, 控盘] 逐个 bool
            reason  —— 数据不足/异常时给出原因，正常为空字符串

        判据（全部为近端窗口口径，与标定脚本 tools\\\\_calib_buildfactor_wide.py 逐位一致）
        ------------------------------------------------------------------
        1. pos120 < C4_POS_MAX(0.25)          近120根收盘位置 (close-min)/(max-min)
        2. up_vol_ratio  > C4_UP_MIN(1.15)    近20根上涨日均量 / 该窗口均量
        3. down_vol_ratio < C4_DN_MAX(0.95)   近20根下跌日均量 / 该窗口均量
        4. C4_AMP_LO <= amp <= C4_AMP_HI      近20根 (high-low)/close 均值 ∈ [2.5%, 5.5%]
        5. ctrl_score >= C4_CTRL_MIN(85.0)

        实现说明
        --------
        1. 涨跌按「收盘 vs 前收」判定（不用「收盘 vs 开盘」），且量能切片对齐到
           后 19 根（np.diff 比切片少一根）—— 与 estimate_control_score 的量价配合
           口径完全一致，否则标定数字会与线上对不上。
        2. 某一侧（上涨日/下跌日）一根都没有时，对应子条件判为不满足并返回 None；
           与 red_fat_green_thin「缺一侧不判通过」是同一个教训。
        3. 少于 C4_MIN_BARS 根直接返回 reason='bars<N'，不硬算：位置窗口被截短会
           与标定口径（固定 120 根）不符，宁可判为不可用。
        \"\"\"
        _bad = {'ok': False, 'n_ok': 0, 'score': 0.0, 'hits': [False] * 5,
                'pos120': None, 'up_vol_ratio': None, 'down_vol_ratio': None,
                'amp': None, 'ctrl_score': None, 'reason': ''}
        try:
            if df is None or len(df) < C4_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % C4_MIN_BARS
                return r
            for _c in ('close', 'high', 'low', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            closes = np.asarray(df['close'].values, dtype=float)
            highs = np.asarray(df['high'].values, dtype=float)
            lows = np.asarray(df['low'].values, dtype=float)
            vols = np.asarray(df['volume'].values, dtype=float)
            # 1) 位置：近 120 根收盘
            c120 = closes[-120:]
            _lo, _hi = float(np.min(c120)), float(np.max(c120))
            pos = (float(closes[-1]) - _lo) / (_hi - _lo + 1e-8)
            # 2)3) 量价配合：近 20 根，涨跌按 close vs 前收，量能对齐到后 19 根
            c20, v20 = closes[-20:], vols[-20:]
            dchg = np.diff(c20)
            v19 = v20[1:]
            vm = float(np.mean(v20)) + 1e-8
            up_m, dn_m = dchg > 0, dchg < 0
            up_r = float(np.mean(v19[up_m])) / vm if up_m.sum() > 0 else None
            dn_r = float(np.mean(v19[dn_m])) / vm if dn_m.sum() > 0 else None
            # 4) 振幅：近 20 根 (high-low)/close 均值
            amp = float(np.mean((highs[-20:] - lows[-20:]) / (closes[-20:] + 1e-8)))
            # 5) 控盘分：可外部传入，避免重复计算
            ctrl = (float(ctrl_score) if ctrl_score is not None
                    else float(TechnicalIndicators.estimate_control_score(df)))
            hits = [bool(pos < C4_POS_MAX),
                    bool(up_r is not None and up_r > C4_UP_MIN),
                    bool(dn_r is not None and dn_r < C4_DN_MAX),
                    bool(C4_AMP_LO <= amp <= C4_AMP_HI),
                    bool(ctrl >= C4_CTRL_MIN)]
            n_ok = int(sum(1 for x in hits if x))
            return {'ok': bool(n_ok == 5), 'n_ok': n_ok,
                    'score': float(n_ok * 20.0), 'hits': hits,
                    'pos120': float(pos), 'up_vol_ratio': up_r,
                    'down_vol_ratio': dn_r, 'amp': float(amp),
                    'ctrl_score': float(ctrl), 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r



# ============================================================
# K线数据解析
# ============================================================"""
assert s.count(OLD_M) == 1, 'base 方法锚点命中 %d 次' % s.count(OLD_M)
s = s.replace(OLD_M, NEW_M, 1)
save(BASE, s, crlf)
s2, crlf2, lf2 = load(BASE)
print('[base.py] 改后 %d 行 | CRLF=%d 裸LF=%d | %s'
      % (s2.count('\n') + 1, crlf2, lf2 - crlf2 if crlf2 else lf2, pyc(BASE)))

# ==========================================================
# 2) services/band_pattern_engine.py
# ==========================================================
e, ecrlf, elf = load(ENG)
print('\n[engine] 改前 %d 行 | CRLF=%d 裸LF=%d' % (e.count('\n') + 1, ecrlf, elf - ecrlf if ecrlf else elf))
shutil.copy2(ENG, ENG + '.bak_before_c4_' + STAMP)
print('[engine] 备份 -> %s' % os.path.basename(ENG + '.bak_before_c4_' + STAMP))

# 2.1 常量块
A = """_BUILD_FUNNEL = {'ok': 0, 'stack_ok': 0, 'redfat_ok': 0, 'both_ok': 0, 'tip': 0}
"""
B = """_BUILD_FUNNEL = {'ok': 0, 'stack_ok': 0, 'redfat_ok': 0, 'both_ok': 0, 'tip': 0}


# ---- C4 观察规则（2026-10-10）低位 + 量价结构 + 适中振幅 + 控盘分 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.is_c4_candidate()。
# 标定（tools\\buildfactor_wide.csv：17570 条观测 / 4401 只 / 4 锚点，无未来数据）：
#   命中口径 pos<0.25 & up>1.15 & dn<0.95 & amp∈[2.5%,5.5%] & ctrl>=85
#     -> n=219  未来20日 +1.57%  胜率 59.4%  t=+1.98
#   ctrl>=80 同向略强 -> n=300  +1.82%  胜率 61.0%  t=+2.81
#   **但两个口径都没通过逐锚点检验**（k20 +0.21 ｜ k40 样本不足 ｜ k60 +5.01 ｜ k80 -3.14），
#   汇总为正主要来自样本集中在 k60，是锚点构成偏差；且「上涨放量+下跌缩量」单独用
#   是 -1.66%（t=-6.31），本身是负向条件。所以：
#     - 只做「观察」：不参与 signal_level / 建仓价 / 排序 / 等级；
#     - 文案固定为「C4观察：…」，禁止出现买入/启动/建仓类字样；
#     - 是否显示由 _C4_NOTE_MODE 控制（'off' 则只写字段不提示）。
#   统计上更结实的口径是去掉量价结构的 pos<0.25 & amp∈[2.5%,5.5%]
#   （n=7749 r20=+0.66% t=+5.24），但那不是 C4 定义，要改先与用户确认。
_C4_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_C4_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'vol': 0, 'amp': 0, 'ctrl': 0,
              'c4': 0, 'note': 0}
"""
assert e.count(A) == 1, 'engine 常量锚点 %d 次' % e.count(A)
e = e.replace(A, B, 1)
print('[engine] 已插入 _C4_NOTE_MODE / _C4_FUNNEL')

# 2.2 _ctrl_note 签名与文案
A = """def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None):"""
B = """def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None):"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

A = """    是否真的追加由模块级 _BUILD_NOTE_MODE 控制，默认 'off'（依据见该常量注释）。
    \"\"\""""
B = """    是否真的追加由模块级 _BUILD_NOTE_MODE 控制，默认 'off'（依据见该常量注释）。

    c4
    --
    C4 观察规则的满足子条件个数（0~5，来自 TechnicalIndicators.is_c4_candidate 的 n_ok），
    默认 None。只有显式传入且 ==5 时才追加「C4观察：低位量价结构」；
    同样由模块级 _C4_NOTE_MODE 控制（默认 'watch'，依据见该常量注释）。
    \"\"\""""
assert e.count(A) == 1
e = e.replace(A, B, 1)

A = """            elif _BUILD_NOTE_MODE == 'warn':
                # 按实测方向：这几个条件下同锚点增量 4/4 为负 -> 提示谨慎，而非提示买入
                if _s_hit and _r_hit and _low:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')
    except Exception:
        return ''
    return ' ｜ '.join(out)"""
B = """            elif _BUILD_NOTE_MODE == 'warn':
                # 按实测方向：这几个条件下同锚点增量 4/4 为负 -> 提示谨慎，而非提示买入
                if _s_hit and _r_hit and _low:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')
        # C4 观察文案（默认 'watch' 会追加；未通过逐锚点检验，只能观察，依据见常量注释）
        if _C4_NOTE_MODE != 'off' and c4 is not None and int(c4) >= 5:
            out.append('C4观察：低位量价结构')
    except Exception:
        return ''
    return ' ｜ '.join(out)"""
assert e.count(A) == 1
e = e.replace(A, B, 1)
print('[engine] _ctrl_note 已支持 c4 参数 + 文案')

# 2.3 scan_stock：局部变量初始化
A = """        _stack_ok, _redfat_ok = False, False
"""
B = """        _stack_ok, _redfat_ok = False, False
        _c4_n, _c4_ok, _c4_sc = 0, False, 0.0
"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.4 scan_stock：C4 计算 + 漏斗
A = """                if _stack_ok and _redfat_ok:
                    _BUILD_FUNNEL['both_ok'] += 1
        except Exception as _e:"""
B = """                if _stack_ok and _redfat_ok:
                    _BUILD_FUNNEL['both_ok'] += 1
                # C4 观察规则（复用同一个 df 与已算好的控盘分，不额外取数）
                _c4r = _ti.is_c4_candidate(_df, ctrl_score=_ctrl)
                _c4_n = int(_c4r.get('n_ok') or 0)
                _c4_ok = bool(_c4r.get('ok'))
                _c4_sc = float(_c4r.get('score') or 0.0)
                _c4h = _c4r.get('hits') or [False] * 5
                if _c4r.get('reason'):
                    _C4_FUNNEL['insuf'] += 1
                else:
                    _C4_FUNNEL['ok'] += 1
                    if _c4h[0]:
                        _C4_FUNNEL['pos'] += 1
                    if _c4h[1] and _c4h[2]:
                        _C4_FUNNEL['vol'] += 1
                    if _c4h[3]:
                        _C4_FUNNEL['amp'] += 1
                    if _c4h[4]:
                        _C4_FUNNEL['ctrl'] += 1
                    if _c4_n >= 5:
                        _C4_FUNNEL['c4'] += 1
        except Exception as _e:"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.5 调用处传参 + 计数
A = """        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc)
        if _ctrl_tip and _BUILD_NOTE_MODE != 'off':
            _BUILD_FUNNEL['tip'] += 1"""
B = """        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n)
        if _ctrl_tip and _BUILD_NOTE_MODE != 'off':
            _BUILD_FUNNEL['tip'] += 1
        if _c4_ok and _C4_NOTE_MODE != 'off':
            _C4_FUNNEL['note'] += 1"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.6 rec 字段
A = """                'stack_vol_score': _stack_sc, 'red_fat_score': _redfat_sc,
"""
B = """                'stack_vol_score': _stack_sc, 'red_fat_score': _redfat_sc,
                'c4_ok': 1 if _c4_ok else 0, 'c4_score': _c4_sc,
"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.7 _ALL_COLS
A = """    ('stack_vol_score', 'REAL'), ('red_fat_score', 'REAL'),
    ('note', 'TEXT'), ('created_at', 'TEXT'), ('updated_at', 'TEXT'),"""
B = """    ('stack_vol_score', 'REAL'), ('red_fat_score', 'REAL'),
    ('c4_ok', 'INTEGER'), ('c4_score', 'REAL'),
    ('note', 'TEXT'), ('created_at', 'TEXT'), ('updated_at', 'TEXT'),"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.8 _save_or_update 列清单
A = """             stack_vol_score, red_fat_score,
             created_at, updated_at)"""
B = """             stack_vol_score, red_fat_score,
             c4_ok, c4_score,
             created_at, updated_at)"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.9 占位符 46 -> 48（用正则，避免手数问号出错）
pat = re.compile(r'VALUES \((?:\?,){45}\?\)')
n_hit = len(pat.findall(e))
assert n_hit == 1, '占位符锚点命中 %d 次' % n_hit
e = pat.sub('VALUES (' + ','.join(['?'] * 48) + ')', e, count=1)
print('[engine] 占位符 46 -> 48')

# 2.10 取值
A = """            rec.get('stack_vol_score',0), rec.get('red_fat_score',0),
"""
B = """            rec.get('stack_vol_score',0), rec.get('red_fat_score',0),
            rec.get('c4_ok',0), rec.get('c4_score',0),
"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.11 scan_all 清零
A = """        for _k in _BUILD_FUNNEL:
            _BUILD_FUNNEL[_k] = 0
"""
B = """        for _k in _BUILD_FUNNEL:
            _BUILD_FUNNEL[_k] = 0
        for _k in _C4_FUNNEL:
            _C4_FUNNEL[_k] = 0
"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

# 2.12 扫描汇总打印
A = """            _bf = _BUILD_FUNNEL"""
B = """            _c4f = _C4_FUNNEL
            print('[C4观察] 可算 %d 只 ｜ 位置达标 %d ｜ 量价达标 %d ｜ 振幅达标 %d ｜ 控盘达标 %d ｜ 五条全中 %d ｜ 文案开关 _C4_NOTE_MODE=%s'
                  % (_c4f['ok'], _c4f['pos'], _c4f['vol'], _c4f['amp'],
                     _c4f['ctrl'], _c4f['c4'], _C4_NOTE_MODE), flush=True)
            print('[C4观察] K线不足%d根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (120, _c4f['insuf'], _c4f['note']), flush=True)
            _bf = _BUILD_FUNNEL"""
assert e.count(A) == 1
e = e.replace(A, B, 1)

save(ENG, e, ecrlf)
e2, ecrlf2, elf2 = load(ENG)
print('[engine] 改后 %d 行 | CRLF=%d 裸LF=%d | %s'
      % (e2.count('\n') + 1, ecrlf2, elf2 - ecrlf2 if ecrlf2 else elf2, pyc(ENG)))
print('\nC4 补丁完成')
