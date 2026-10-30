# -*- coding: utf-8 -*-
"""FIX22 时段映射验证：模拟 workflow case 分支（顺序敏感），遍历关键时间点"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

def slot_of(H, M):
    # 与 daily-review2.yml FIX22 版本完全一致（顺序敏感）
    hm = '%02d:%02d' % (H, M)
    if hm[:3] == '00:' and '20' <= hm[3:5] <= '24': return 'warn'
    if hm[:3] == '00:' and '30' <= hm[3:5] <= '34': return 'pre'
    if hm[:3] == '01:' and '20' <= hm[3:5] <= '29': return 'auction'
    if hm[:3] == '04:' and '00' <= hm[3:5] <= '04': return 'news2h'
    if hm[:3] == '06:' and '01' <= hm[3:5] <= '04': return 'news2h'
    if hm[:3] == '08:' and '00' <= hm[3:5] <= '04': return 'news2h'
    if (hm[:3] in ('02:', '03:', '05:', '06:') and '00' <= hm[3:5] <= '04'): return 'hourly'
    if hm[:3] == '03:' and '40' <= hm[3:5] <= '44': return 'news'
    if hm[:3] == '06:' and '05' <= hm[3:5] <= '07': return 'follow'
    if hm[:3] == '07:' and '05' <= hm[3:5] <= '08': return 'follow'
    if hm[:3] == '07:' and '20' <= hm[3:5] <= '23': return 'anchor'
    if hm[:3] == '07:' and '30' <= hm[3:5] <= '34': return 'review'
    if hm[:3] == '12:' and '00' <= hm[3:5] <= '02': return 'evaluate'
    if hm[:3] == '07:' and '10' <= hm[3:5] <= '14': return 'news'
    if hm[:3] == '07:' and '35' <= hm[3:5] <= '39': return 'news'
    if hm[:3] in ('13:', '14:') and '36' <= hm[3:5] <= '39': return 'ext'
    if hm[:3] == '14:' and '50' <= hm[3:5] <= '59': return 'evening'
    if hm[:3] == '03:' and '30' <= hm[3:5] <= '35': return 'noon'
    if hm[:3] == '07:': return 'eod'
    return 'watch'

cases = [
    # (H, M, 期望)
    (0, 20, 'warn'), (0, 24, 'warn'), (0, 25, 'watch'),
    (0, 30, 'pre'), (0, 34, 'pre'), (0, 35, 'watch'),
    (1, 20, 'auction'), (1, 25, 'auction'), (1, 29, 'auction'), (1, 30, 'watch'),
    # FIX22 核心：news2h 档
    (4, 0, 'news2h'), (4, 1, 'news2h'), (4, 4, 'news2h'), (4, 5, 'watch'),   # 12:00-04
    (6, 0, 'hourly'), (6, 1, 'news2h'), (6, 4, 'news2h'), (6, 5, 'follow'),   # 14:00 hourly / 14:01-04 news2h / 14:05 follow
    (8, 0, 'news2h'), (8, 1, 'news2h'), (8, 4, 'news2h'), (8, 5, 'watch'),    # 16:00-04
    (2, 0, 'hourly'), (2, 4, 'hourly'), (3, 0, 'hourly'), (5, 0, 'hourly'),
    (3, 30, 'noon'), (3, 35, 'noon'), (3, 36, 'watch'),
    (3, 40, 'news'), (3, 44, 'news'), (3, 45, 'watch'),
    (7, 0, 'eod'), (7, 10, 'news'), (7, 14, 'news'), (7, 20, 'anchor'), (7, 30, 'review'),
    (7, 35, 'news'), (7, 39, 'news'), (7, 40, 'eod'), (7, 59, 'eod'),
    (13, 36, 'ext'), (14, 36, 'ext'), (14, 50, 'evening'), (14, 59, 'evening'),
    (12, 0, 'evaluate'), (12, 2, 'evaluate'),
    (0, 0, 'watch'), (1, 0, 'watch'), (9, 30, 'watch'), (10, 30, 'watch'),
]
ok = fail = 0
for H, M, exp in cases:
    got = slot_of(H, M)
    if got == exp:
        ok += 1
    else:
        fail += 1
        print('[FAIL] %02d:%02d expect=%s got=%s' % (H, M, exp, got))
print('===== FIX22 时段映射: %d pass / %d fail =====' % (ok, fail))
sys.exit(1 if fail else 0)
