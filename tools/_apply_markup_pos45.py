# -*- coding: utf-8 -*-
"""一次性补丁：拉升识别加位置门槛 pos120 < 0.45（1010m）。

- strategy\\base.py（纯 CRLF）：新增 MARKUP_POS_MAX=0.45 常量 + detect_markup 前置门槛 + docstring
- services\\band_pattern_engine.py（纯 LF）：_MARKUP_FUNNEL 加 'pos' 计数 + 计数分支 + 打印
"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\QuantMonitorV6\strategy\base.py'
ENG = r'D:\QuantMonitorV6\services\band_pattern_engine.py'


def load_crlf(p):
    return io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')


def save(p, s, crlf):
    data = s.replace('\n', '\r\n') if crlf else s
    io.open(p, 'wb').write(data.encode('utf-8'))


# ============================ base.py ============================
shutil.copy2(BASE, BASE + '.bak_before_markup_pos45')
s = load_crlf(BASE)

r1_old = "MARKUP_MIN_BARS = 60        # 最少K线根数\n"
r1_new = """MARKUP_MIN_BARS = 60        # 最少K线根数
MARKUP_POS_MAX = 0.45       # 位置门槛（1010m 新增）：只保留 pos120 < 0.45 的低位子集
                            # 依据 tools\\markup_calib.txt（17516 条滚动观测 / 无未来数据）：
                            #   pos < 0.45      n=1250  +1.10% / 胜率54.3% / t=+3.31  <- 唯一正期望档
                            #   pos 0.45~0.60   n=266   -2.79% / t=-3.90
                            #   pos 0.60~0.75   n=211   -4.25% / t=-4.48
                            #   pos >= 0.75     n=384   -3.32% / t=-3.30
                            #   全部命中的均值相对基准只有 +0.06pp（=噪音），高分档更差（score>=90 为 -4.18%）
                            # 边界口径：0.45 归入负期望档 [0.45,0.60)，所以写 pos >= MARKUP_POS_MAX 即拦。
                            # ⚠ 连带后果：形态②缩量强势自带 pos >= MARKUP_LOCK_POS_MIN(0.55)，
                            #   被本门槛完全覆盖后【不可达】——②在现参数下不会再产生命中。
                            #   常量保留，回退门槛（改 1.01）即可恢复。
"""

r2_old = """        判据
        ----
        ① 阶梯式上行（趋势型拉升）
"""
r2_new = """        前置：位置 pos120 < MARKUP_POS_MAX(0.45)（1010m 新增）。
        依据 tools\\markup_calib.txt：整体命中的均值增量只有 +0.06pp（噪音），
        只有 pos<0.45 那一段是正期望（+1.10% / 胜率 54.3% / t=+3.31），
        pos>=0.45 三档全部显著为负 -> 高位一律不判「拉升」。
        边界：0.45 归入负期望档，故判定写 pos >= MARKUP_POS_MAX 即拦。
        ⚠ 连带后果：形态②缩量强势要求 pos>=0.55，被本门槛完全覆盖后【不可达】。

        判据
        ----
        ① 阶梯式上行（趋势型拉升）
"""

r3_old = """            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            hi60 = float(np.max(h[-60:]))
"""
r3_new = """            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            # 位置门槛（1010m）：只保留低位有效子集，高位一律不判拉升（依据见 MARKUP_POS_MAX 注释）
            r = dict(_bad)
            r['pos120'] = float(pos)
            if pos >= MARKUP_POS_MAX:
                r['reason'] = 'pos>=%.2f' % MARKUP_POS_MAX
                return r
            hi60 = float(np.max(h[-60:]))
"""

for i, (o, n) in enumerate([(r1_old, r1_new), (r2_old, r2_new), (r3_old, r3_new)], 1):
    assert s.count(o) == 1, 'base.py 第 %d 处锚点命中 %d 次' % (i, s.count(o))
    s = s.replace(o, n)
save(BASE, s, True)

# ============================ engine ============================
shutil.copy2(ENG, ENG + '.bak_before_markup_pos45')
e = io.open(ENG, 'rb').read().decode('utf-8').replace('\r\n', '\n')

e1_old = """_MARKUP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_MARKUP_FUNNEL = {'ok': 0, 'insuf': 0, 'trend': 0, 'lock': 0,
                  'acc': 0, 'hit': 0, 'note': 0}
"""
e1_new = """# 1010m：因子层加了位置门槛 MARKUP_POS_MAX=0.45（只保留 pos120<0.45 的低位子集）——
#   依据 tools\\markup_calib.txt：整体命中均值增量仅 +0.06pp（噪音），pos>=0.45 三档全部显著为负，
#   只有 pos<0.45 是正期望（+1.10% / 胜率 54.3% / t=+3.31）。
#   因此 markup_ok=1 只会落在 pos120<0.45 的票上；连带形态②缩量强势（自带 pos>=0.55）不可达。
#   要看高位拉升（追高警示）就把门槛调回 1.01，或直接读 detect_markup 的 pos120。
_MARKUP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_MARKUP_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'trend': 0, 'lock': 0,
                  'acc': 0, 'hit': 0, 'note': 0}
"""

e2_old = """                _markup_type = _mr.get('type') or ''
                if _mr.get('reason'):
                    _MARKUP_FUNNEL['insuf'] += 1
                else:
"""
e2_new = """                _markup_type = _mr.get('type') or ''
                _mrr = _mr.get('reason') or ''
                if _mrr.startswith('pos>'):
                    _MARKUP_FUNNEL['pos'] += 1
                elif _mrr:
                    _MARKUP_FUNNEL['insuf'] += 1
                else:
"""

e3_old = """            _mkf = _MARKUP_FUNNEL
            print('[拉升观察] 可算 %d 只 ｜ 阶梯式上行 %d ｜ 缩量强势 %d ｜ 加速迹象 %d ｜ 命中合计 %d ｜ 文案开关 _MARKUP_NOTE_MODE=%s'
                  % (_mkf['ok'], _mkf['trend'], _mkf['lock'], _mkf['acc'],
                     _mkf['hit'], _MARKUP_NOTE_MODE), flush=True)
            print('[拉升观察] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_mkf['insuf'], _mkf['note']), flush=True)
"""
e3_new = """            _mkf = _MARKUP_FUNNEL
            from strategy.base import MARKUP_POS_MAX as _MPMAX
            print('[拉升观察] 可算（已过位置门槛）%d 只 ｜ 阶梯式上行 %d ｜ 缩量强势 %d ｜ 加速迹象 %d ｜ 命中合计 %d ｜ 文案开关 _MARKUP_NOTE_MODE=%s'
                  % (_mkf['ok'], _mkf['trend'], _mkf['lock'], _mkf['acc'],
                     _mkf['hit'], _MARKUP_NOTE_MODE), flush=True)
            print('[拉升观察] K线不足60根跳过 %d 只 ｜ 位置超限跳过(pos>=%.2f) %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_mkf['insuf'], _MPMAX, _mkf['pos'], _mkf['note']), flush=True)
"""

for i, (o, n) in enumerate([(e1_old, e1_new), (e2_old, e2_new), (e3_old, e3_new)], 1):
    assert e.count(o) == 1, 'engine 第 %d 处锚点命中 %d 次' % (i, e.count(o))
    e = e.replace(o, n)
save(ENG, e, False)

for p, crlf in ((BASE, True), (ENG, False)):
    raw = io.open(p, 'rb').read()
    txt = raw.decode('utf-8')
    print('%s: 行数=%d CRLF=%d 裸LF=%d'
          % (p.split('\\')[-1], txt.count('\n'), raw.count(b'\r\n'),
             raw.count(b'\n') - raw.count(b'\r\n')))
