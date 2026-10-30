# -*- coding: utf-8 -*-
"""扫描后核对主表：MA20 过滤是否真的写进去了。"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
import services.band_pattern_engine as E   # noqa: E402

MARK = 'MA20下方·筑底观察'
con = sqlite3.connect(E.DB_PATH)
try:
    print('=' * 74)
    print('① 主表总览')
    print('=' * 74)
    print('  总记录 %d 条' % con.execute(
        'SELECT COUNT(*) FROM pattern_record').fetchone()[0])
    for lv, c in con.execute('SELECT signal_level, COUNT(*) FROM pattern_record'
                             ' GROUP BY signal_level ORDER BY 2 DESC').fetchall():
        print('    %-10s %d' % (lv, c))
    print()
    for pn, c in con.execute('SELECT pattern_name, COUNT(*) FROM pattern_record'
                             ' GROUP BY pattern_name').fetchall():
        print('    模式 %-8s %d' % (pn, c))

    print()
    print('=' * 74)
    print('② 被 MA20 降级的记录（程序里会显示在「观察」）')
    print('=' * 74)
    rows = con.execute(
        'SELECT code, name, push_price, ma20, signal_level, trigger_type,'
        ' pattern_name FROM pattern_record WHERE trigger_type = ?', (MARK,)
    ).fetchall()
    if not rows:
        print('  无')
    for c, n, px, m20, lv, tt, pn in rows:
        print('  %s %-8s 现价 %7.2f  MA20 %7.2f  差 %+6.2f%%  [%s] %s'
              % (c, n, px or 0, m20 or 0,
                 ((px or 0) - (m20 or 0)) / (m20 or 1) * 100, lv, pn))

    print()
    print('=' * 74)
    print('③ 违规检查：建仓触发里还有没有 现价 < MA20 的')
    print('=' * 74)
    bad = con.execute(
        "SELECT code, name, push_price, ma20 FROM pattern_record "
        "WHERE signal_level = ? AND ma20 > 0 AND push_price < ma20",
        (E.LVL_TRIGGER,)).fetchall()
    print('  违规 %d 条 %s' % (len(bad), '✓' if not bad else '✗'))
    for c, n, px, m20 in bad:
        print('    %s %s 现价%.2f < MA20 %.2f' % (c, n, px, m20))

    print()
    print('=' * 74)
    print('④ 违规检查：观察级里有没有现价 >= MA20 的（误降级）')
    print('=' * 74)
    bad2 = con.execute(
        "SELECT code, name, push_price, ma20, trigger_type FROM pattern_record "
        "WHERE signal_level = ? AND ma20 > 0 AND push_price >= ma20",
        (E.LVL_WATCH,)).fetchall()
    print('  误降级 %d 条 %s' % (len(bad2), '✓' if not bad2 else '✗'))
    for c, n, px, m20, tt in bad2:
        print('    %s %s 现价%.2f >= MA20 %.2f  tt=%s' % (c, n, px, m20, tt))

    print()
    print('=' * 74)
    print('⑤ 建仓触发里距 MA20 最近的 5 只（看过滤边界效果）')
    print('=' * 74)
    for c, n, px, m20, tt in con.execute(
            "SELECT code, name, push_price, ma20, trigger_type FROM pattern_record "
            "WHERE signal_level = ? AND ma20 > 0 ORDER BY (push_price-ma20)/ma20 ASC "
            "LIMIT 5", (E.LVL_TRIGGER,)).fetchall():
        print('  %s %-8s 现价 %7.2f  MA20 %7.2f  差 %+6.2f%%  %s'
              % (c, n, px, m20, (px - m20) / m20 * 100, tt))
finally:
    con.close()

print()
print('结论: %s' % ('MA20 过滤已写入主表，程序打开即可看到 ✓'
                    if not bad and not bad2 else '存在问题 ✗'))
