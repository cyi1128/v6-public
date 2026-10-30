# -*- coding: utf-8 -*-
"""试盘位置门槛收紧 0.75 -> 0.35（一次性补丁，执行成功后勿重跑）

依据 tools\\probe_dist_calib.txt（17516 条滚动观测）：
  pos<0.35        n=462  +2.02%  胜率 55.0%  t=+3.41
  0.35~0.55       n=140  -0.70%  胜率 40.7%
  0.55~0.75       n=55   -5.87%  胜率 29.1%
故只保留低位有效子集。只改这一处参数与相关注释/docstring，不动其他逻辑。
"""
import io
import shutil
import py_compile

P = r'D:\QuantMonitorV6\strategy\base.py'


def main():
    shutil.copy2(P, P + '.bak_before_probe_pos35')
    s = io.open(P, 'r', encoding='utf-8', newline='').read()

    pairs = []

    # 1) 常量 + 注释
    pairs.append((
        'PROBE_POS_MAX = 0.75     # 位置上限：高位长上影归「出货形态」，不按试盘计\r\n',
        'PROBE_POS_MAX = 0.35     # 位置上限：只保留低位有效子集（滚动观测里 pos>=0.35 的试盘为负期望）\r\n'
        '                         # 标定 tools\\probe_dist_calib.txt：pos<0.35 +2.02%/55.0%/t=+3.41；pos∈[0.55,0.75) -5.87%\r\n'
        '                         # 高位长上影归「出货形态」，不按试盘计\r\n'
    ))

    # 2) 函数 docstring 的前置条件
    pairs.append((
        '        前置：位置 pos120 <= PROBE_POS_MAX(0.75)。',
        '        前置：位置 pos120 <= PROBE_POS_MAX(0.35)（2026-10-11 由 0.75 收紧，'
        'pos>=0.35 的试盘为负期望）。\r\n'
        '        高位长上影不按试盘计，由 detect_distribution_pattern() 承接。'
    ))

    for old, new in pairs:
        n = s.count(old)
        assert n == 1, '锚点命中 %d 次: %r' % (n, old[:48])
        s = s.replace(old, new)

    io.open(P, 'w', encoding='utf-8', newline='').write(s)
    py_compile.compile(P, doraise=True)
    b = open(P, 'rb').read()
    print('OK  CRLF=%d 裸LF=%d 总行数=%d' % (
        b.count(b'\r\n'), b.count(b'\n') - b.count(b'\r\n'), s.count('\n') + 1))


if __name__ == '__main__':
    main()
