# -*- coding: utf-8 -*-
"""龙一/龙二/龙三 判定实测：把排序键的每一项都摊开看。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import services.board_anomaly_engine as B     # noqa: E402
import services.market_rhythm_engine as M     # noqa: E402

d = B.get_board_anomaly(force=True)
if not d.get('ok'):
    print('引擎失败: %s' % d.get('error'))
    sys.exit(1)

print('数据日 %s ｜ 涨停库 %s ｜ 记录 %d 条' % (d.get('date'), d.get('ludate'),
                                              d.get('lu_count', 0)))
print()


def show(title, items, n=4):
    print('=' * 92)
    print(title)
    print('=' * 92)
    for r in items[:n]:
        print('【%s】%s  涨停 %d 家  均涨 %+.2f%%  最高 %+.2f%%'
              % (r['kind'], r['name'], r['count'], r['avg_pct'], r['max_pct']))
        print('  龙头列显示: %s %+.1f%%' % (r['lead_name'], r['lead_pct']))
        print('  成分股前3名标注:')
        for i, g in enumerate(r['dragons']):
            tag = ('龙一', '龙二', '龙三')[i]
            print('    %s  %-8s  连板 %d ｜ 首封 %-5s ｜ 封单 %7.4f 亿 ｜ 涨幅 %+6.2f%%'
                  ' ｜ 炸板 %d'
                  % (tag, g['name'], g['lbc'], g['time'] or '--',
                     g['fund'] / 1e8, g['pct'], g['zbc']))
        print('  排序键（升序，越小越靠前）:')
        for i, g in enumerate(r['dragons']):
            rec = {'time': g['time'], 'lbc': g['lbc'], 'fund': g['fund'],
                   'code': g['code']}
            k = B._dragon_key(rec, {g['code']: g['pct']})
            print('    %s -> %s' % (g['name'], k))
        print()


show('Tab2「可介入」—— 题材榜（龙一/龙二/龙三 就来自这里）', d['themes'], 4)
show('Tab2「可介入」—— 行业榜', d['industries'], 2)

# Tab1 用的是另一套
print('=' * 92)
print('Tab1「市场节奏」的龙头 —— 另一套排序键（只看连板 + 首封时间）')
print('=' * 92)
rh = M.get_rhythm(force=True)
if rh.get('ok'):
    for b in rh['boards'][:6]:
        lad = b['ladder']
        print('【%s】%s  %s  今日 %d 家' % (b['state'], b['theme'],
                                          b['mainline'] or '—', b['count']))
        for i, m in enumerate(lad[:3]):
            print('    %s  %-8s 连板 %d ｜ 首封 %s'
                  % (('龙头' if i == 0 else '  '), m['name'], m['lbc'],
                     m['time'] or '--'))
        print()
else:
    print('  节奏引擎失败: %s' % rh.get('error'))
