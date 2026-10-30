# -*- coding: utf-8 -*-
"""C1 + C2 精确落盘。

C1  services/band_pattern_engine.py（纯 LF）：
    出货警示条件  distribute & ctrl>=_CTRL_DIST(60)
              ->  distribute & pos120>=_CTRL_DIST_POS(0.65)
C2  strategy/base.py（纯 CRLF）：
    删除 estimate_control_score 里「上涨放量+下跌缩量 -> +10 分」两行

做法遵循项目约定：shutil.copy2 备份 -> assert count==1 -> 替换 -> 写回 -> py_compile。
"""
import io, os, shutil, sys, py_compile, datetime

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


def read_raw(p):
    with open(p, 'rb') as f:
        b = f.read()
    crlf = b.count(b'\r\n')
    lf = b.count(b'\n') - crlf
    return b.decode('utf-8'), crlf, lf


def write_raw(p, s, is_crlf):
    if is_crlf:
        s = s.replace('\r\n', '\n').replace('\n', '\r\n')
    else:
        s = s.replace('\r\n', '\n')
    with open(p, 'wb') as f:
        f.write(s.encode('utf-8'))


def patch(rel, edits, is_crlf):
    p = os.path.join(ROOT, rel)
    s, crlf, lf = read_raw(p)
    bak = p + '.bak_before_c1c2_' + STAMP
    shutil.copy2(p, bak)
    print('[备份] %s  (CRLF=%d 裸LF=%d)' % (os.path.basename(bak), crlf, lf))
    s = s.replace('\r\n', '\n')                      # 统一成 LF 再匹配
    for i, (old, new, tag) in enumerate(edits, 1):
        old = old.replace('\r\n', '\n')
        new = new.replace('\r\n', '\n')
        n = s.count(old)
        assert n == 1, '[%s] 锚点命中 %d 次（应为 1）\n---\n%s\n---' % (tag, n, old)
        s = s.replace(old, new)
        print('  [OK] %s  锚点唯一' % tag)
    write_raw(p, s, is_crlf)
    _s2, c2, l2 = read_raw(p)
    print('  [写回] %s  CRLF=%d 裸LF=%d  %s' %
          (rel, c2, l2, '行尾保持正确' if ((is_crlf and l2 == 0) or ((not is_crlf) and c2 == 0)) else '!! 行尾异常'))
    py_compile.compile(p, doraise=True)
    print('  [编译] py_compile OK\n')


print('=' * 96)
print('C1  services/band_pattern_engine.py')
print('=' * 96)
E = os.path.join(ROOT, 'services', 'band_pattern_engine.py')

old_cmt = '#   出货警示另有 _CTRL_DIST 门槛（见下），与这两条独立。\n'
new_cmt = ('#   出货警示原为「控盘分门槛 _CTRL_DIST=60」，2026-10-10 改为「位置门槛\n'
           '#   _CTRL_DIST_POS=0.65」—— 旧口径方向是反的，依据见 _CTRL_DIST_POS 注释。\n')

old_th = ('_CTRL_DIST = 60.0        # 出货风险警示的控盘分门槛：低于此分不出货警示\n'
          '                         # （2026-10-10 加。不加时全市场 161 只出货、列表里 33 条，占全部提示的七成）\n')
new_th = ('_CTRL_DIST = 60.0        # 【已停用 2026-10-10】原为「出货警示的控盘分门槛」。\n'
          '                         #   保留常量仅为兼容 tools\\_test_ctrl_dist.py 等旧脚本的 import；\n'
          '                         #   _ctrl_note 已不再引用它，不要再用它做出货判断。\n'
          '_CTRL_DIST_POS = 0.65    # 出货风险警示的位置门槛：近120日位置 >= 0.65 才警示。\n'
          '                         #   2026-10-10 由「ctrl>=_CTRL_DIST」改为按位置。依据（17570 条滚动观测，\n'
          '                         #   n 已按 4 锚点重叠折半，t 为保守值）：\n'
          '                         #     distribute & pos>=0.7 -> 20日 -4.62% 胜率35.9% 回撤-19.09%\n'
          '                         #     distribute & pos<0.4  -> 20日 +1.03% 胜率53.2% 回撤 -7.13%\n'
          '                         #   旧口径(ctrl>=60)命中集合回撤仅 -8.30%，比全样本(-10.76%)还好，\n'
          '                         #   等于把最危险的那批（pos高但ctrl低）挡在警示之外，方向是反的。\n')

old_rule = "        if stage == 'distribute' and ctrl >= _CTRL_DIST:\n"
new_rule = "        if stage == 'distribute' and pos is not None and pos >= _CTRL_DIST_POS:\n"

patch('services\\band_pattern_engine.py',
      [(old_cmt, new_cmt, '阈值注释'),
       (old_th, new_th, '_CTRL_DIST_POS 新增 + _CTRL_DIST 标停用'),
       (old_rule, new_rule, '出货警示条件改为位置')],
      is_crlf=False)

print('=' * 96)
print('C2  strategy/base.py')
print('=' * 96)
old_c2 = ('            if up_vol_ratio > 1.3 and down_vol_ratio < 0.8:\n'
          '                vol_score += 10.0      # 上涨放量 + 下跌缩量：资金介入\n')
patch('strategy\\base.py', [(old_c2, '', '删除 +10 分加分项')], is_crlf=True)

print('=' * 96)
print('落盘完成 ' + STAMP)
print('=' * 96)
