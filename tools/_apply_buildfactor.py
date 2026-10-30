# -*- coding: utf-8 -*-
"""V20「建仓阶段专门因子」落库到 strategy/base.py（2026-10-10）

1) 模块级阈值常量（常量定义区）
2) TechnicalIndicators 新增两个 @staticmethod：
   - bottom_volume_stack()   底部堆量 -> dict(ok, score, ratio, pos120, cont)
   - red_fat_green_thin()    红肥绿瘦 -> dict(ok, score, ratio, up_days, down_days, ...)

base.py 是纯 CRLF，按项目约定：备份 -> 标准化 -> assert count==1 -> 替换 -> 转回 CRLF -> py_compile
"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SUF = '.bak_before_buildfactor_20261010_2120'
REL = 'strategy/base.py'

CONSTS = '''# ---- V20 建仓阶段专门因子阈值（2026-10-10）----
# 实测标定见 tools\\build_factor_calibration.txt；改「是否满足」门槛前先重跑标定。
BUILD_STACK_RATIO_LO = 1.15     # 底部堆量：近10日均量 / 紧邻前20日均量 的下限
BUILD_STACK_RATIO_HI = 3.50     # 上限（超过视为单日爆量/异动，不算「堆量」）
BUILD_STACK_POS_MAX = 0.45      # 底部堆量：近120日位置必须 < 该值
BUILD_STACK_CONT_MIN = 0.50     # 底部堆量：近10日内量>基准均量的天数占比下限
BUILD_HIT_STACK = 70.0          # 堆量分 >= 该值 -> 报「疑似底部堆量」
BUILD_REDFAT_RATIO = 1.30       # 红肥绿瘦：上涨日均量 / 下跌日均量 的下限
BUILD_HIT_REDFAT = 65.0         # 红肥绿瘦分 >= 该值 -> 报「红肥绿瘦建仓特征」

'''

METHODS = '''
    # ========================================================
    # V20 建仓阶段专门因子（2026-10-10）
    # ========================================================

    @staticmethod
    def bottom_volume_stack(df, recent_win=10, base_win=20):
        """底部堆量：近端量能是否相对更早时期堆高，且股价仍在相对低位。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / high / low / volume。
        recent_win : int
            近端观察窗口（堆量区），默认 10。
        base_win : int
            对比基准窗口（堆量之前的存量区），默认 20。

        返回
        ----
        dict : {'ok': bool, 'score': float, 'ratio': float,
                'pos120': float, 'cont': float}
            df 为空 / 长度不足 / 缺列 / 抛异常 -> ok=False、score=0.0，其余给中性值。

        判据（四段，全部满足才 ok）
        ----
        1. ratio >= BUILD_STACK_RATIO_LO    堆量倍数达标
        2. ratio <= BUILD_STACK_RATIO_HI    不是单日爆量 / 异动
        3. pos120 < BUILD_STACK_POS_MAX     仍在底部
        4. cont >= BUILD_STACK_CONT_MIN     近端窗口内量能持续在基准均量之上

        实现说明
        --------
        1. 基准窗口取「紧邻近端窗口之前」的 base_win 日，与近端窗口**不重叠**。
           若把近端窗口也算进分母，量能会同时进分子分母，把比值压向 1，
           于是「堆量」永远测不出来。
        2. 位置用 120 日 low/high 区间，不用 close 区间 —— 堆量判断关心的是
           「有没有打出过新低/新高」，用高低点不容易被单根影线糊掉。
        3. score 三段加权：量能帐篷 0.45 + 连续性 0.30 + 低位程度 0.25。
        4. 除零 / NaN / 缺列 / 异常全部防护，绝不抛异常。
        """
        _bad = {'ok': False, 'score': 0.0, 'ratio': 0.0, 'pos120': 1.0, 'cont': 0.0}
        try:
            if df is None or len(df) < 60 or len(df) < recent_win + base_win + 1:
                return dict(_bad)
            for _c in ('close', 'high', 'low', 'volume'):
                if _c not in df.columns:
                    return dict(_bad)
            vol = df['volume']
            base_vol = float(vol.iloc[-(recent_win + base_win):-recent_win].mean())
            recent_vol = float(vol.iloc[-recent_win:].mean())
            if base_vol != base_vol or base_vol <= 0 or recent_vol != recent_vol:
                return dict(_bad)
            ratio = recent_vol / (base_vol + 1e-8)
            if ratio != ratio:
                return dict(_bad)
            cont = float((vol.iloc[-recent_win:] > base_vol).sum()) / float(recent_win)
            t120 = df.tail(120)
            _lo = float(t120['low'].min())
            _hi = float(t120['high'].max())
            cur = float(df['close'].iloc[-1])
            if _hi != _hi or _lo != _lo or _hi <= _lo:
                pos120 = 1.0
            else:
                pos120 = (cur - _lo) / (_hi - _lo + 1e-8)
            # 量能帐篷：峰值 1.60 倍（堆量温和放大的位置），下坡 100/倍，上坡 22/倍
            if ratio <= 1.60:
                r_sc = 100.0 - (1.60 - ratio) * 100.0
            else:
                r_sc = 100.0 - (ratio - 1.60) * 22.0
            r_sc = _clamp100(r_sc)
            c_sc = _clamp100(cont * 100.0)
            p_sc = _clamp100((1.0 - pos120) * 100.0)
            score = _clamp100(r_sc * 0.45 + c_sc * 0.30 + p_sc * 0.25)
            ok = (ratio >= BUILD_STACK_RATIO_LO and ratio <= BUILD_STACK_RATIO_HI
                  and pos120 < BUILD_STACK_POS_MAX and cont >= BUILD_STACK_CONT_MIN)
            return {'ok': bool(ok), 'score': float(score), 'ratio': float(ratio),
                    'pos120': float(pos120), 'cont': float(cont)}
        except Exception:
            return dict(_bad)

    @staticmethod
    def red_fat_green_thin(df, window=20):
        """红肥绿瘦：上涨日平均成交量是否明显大于下跌日平均成交量。

        参数
        ----
        df : pandas.DataFrame
            至少含 close / volume。
        window : int
            观察窗口（含末根 K 线），默认 20。

        返回
        ----
        dict : {'ok': bool, 'score': float, 'ratio': float, 'up_days': int,
                'down_days': int, 'up_vol': float, 'down_vol': float}
            数据不足 / 缺列 / 某一侧没有交易日 / 异常 -> ok=False、score=0.0。

        判据
        ----
        ratio = 上涨日平均量 / 下跌日平均量
        ok    = ratio >= BUILD_REDFAT_RATIO 且 上涨日 >= 3 且 下跌日 >= 3

        实现说明
        --------
        1. 涨跌按「收盘 vs 前收」判定，与 estimate_control_score 的量价配合口径一致；
           不用「收盘 vs 开盘」—— 建仓特征看的是承接力度，不是当日实体方向。
        2. 某一侧交易日不足 3 天时返回 ok=False，而不是 ok=True。
           这与 judge_wash_or_distribute「无阴线不判 wash」是同一个教训：
           缺失一侧时比值没有意义，不能默认通过（否则纯上涨段会被误报成红肥绿瘦）。
        3. score 的帐篷峰值放在 ratio=1.50（明显红肥绿瘦），ratio=1.0 给 0 分。
        """
        _bad = {'ok': False, 'score': 0.0, 'ratio': 0.0, 'up_days': 0,
                'down_days': 0, 'up_vol': 0.0, 'down_vol': 0.0}
        try:
            if df is None or len(df) < window + 1 or len(df) < 21:
                return dict(_bad)
            for _c in ('close', 'volume'):
                if _c not in df.columns:
                    return dict(_bad)
            seg = df.tail(window + 1)
            chg = seg['close'].diff().values
            up = seg[(chg > 0)]
            dn = seg[(chg < 0)]
            if len(up) < 3 or len(dn) < 3:
                return dict(_bad)
            up_vol = float(up['volume'].mean())
            down_vol = float(dn['volume'].mean())
            if down_vol != down_vol or down_vol <= 0 or up_vol != up_vol:
                return dict(_bad)
            ratio = up_vol / (down_vol + 1e-8)
            if ratio != ratio:
                return dict(_bad)
            if ratio <= 1.50:
                score = (ratio - 1.0) * 200.0
            else:
                score = 100.0 - (ratio - 1.50) * 40.0
            score = _clamp100(score)
            return {'ok': bool(ratio >= BUILD_REDFAT_RATIO), 'score': float(score),
                    'ratio': float(ratio), 'up_days': int(len(up)),
                    'down_days': int(len(dn)), 'up_vol': up_vol, 'down_vol': down_vol}
        except Exception:
            return dict(_bad)


'''

EDITS = [
    # 1) 常量
    ("# 常量定义\n"
     "# ============================================================\n"
     "\n"
     "MODEL_LIMIT_PULLBACK = \"涨停回调\"\n",

     "# 常量定义\n"
     "# ============================================================\n"
     "\n"
     + CONSTS +
     "MODEL_LIMIT_PULLBACK = \"涨停回调\"\n"),

    # 2) 两个方法（插在 judge_wash_or_distribute 之后、K线数据解析段之前）
    ("            return 'unknown'\n"
     "        except Exception:\n"
     "            return 'unknown'\n"
     "\n"
     "\n"
     "# ============================================================\n"
     "# K线数据解析\n"
     "# ============================================================\n",

     "            return 'unknown'\n"
     "        except Exception:\n"
     "            return 'unknown'\n"
     "\n"
     + METHODS.replace('\n', '\n') +
     "\n"
     "# ============================================================\n"
     "# K线数据解析\n"
     "# ============================================================\n"),
]

p = os.path.join(ROOT, REL)
raw = io.open(p, encoding='utf-8', newline='').read()
n_crlf, n_lf0 = raw.count('\r\n'), raw.count('\n') - raw.count('\r\n')
shutil.copy2(p, p + SUF)
s = raw.replace('\r\n', '\n')
for old, new in EDITS:
    c = s.count(old)
    assert c == 1, '[锚点命中 %d 次] %r' % (c, old[:70])
    s = s.replace(old, new)
out = s.replace('\n', '\r\n')
io.open(p, 'w', encoding='utf-8', newline='').write(out)

back = io.open(p, encoding='utf-8', newline='').read()
b_crlf, b_lf = back.count('\r\n'), back.count('\n') - back.count('\r\n')
assert back.replace('\r\n', '\n') == s, '回读不一致'
assert b_lf == 0 and b_crlf > 0, '行尾被破坏: crlf=%d lf=%d' % (b_crlf, b_lf)
r = subprocess.run([PY, '-X', 'utf8', '-m', 'py_compile', p],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
assert r.returncode == 0, 'py_compile 失败:\n' + r.stderr

print('=' * 96)
print('V20 建仓因子已落库')
print('=' * 96)
print('  %s  行尾=CRLF 编辑%d处  crlf %d->%d / 裸LF %d->%d  py_compile OK'
      % (REL, len(EDITS), n_crlf, b_crlf, n_lf0, b_lf))
print('  备份: %s%s' % (REL, SUF))
