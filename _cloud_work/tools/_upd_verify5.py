# -*- coding: utf-8 -*-
import io
# newsbrief 断言 → 五元组
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_newsbrief.py'
s = io.open(P, encoding='utf-8').read()
s = s.replace("== [('A', '', '解读A', ''), ('B', '', '解读B', '')]", "== [('A', '', '', '解读A', ''), ('B', '', '', '解读B', '')]")
s = s.replace("== [('X', '', 'Y', '')]", "== [('X', '', '', 'Y', '')]")
s = s.replace("== [('T1', '', 'N1', '')]", "== [('T1', '', '', 'N1', '')]")
s = s.replace("== [('A', '影响A', '白话A', '操作A')]", "== [('A', '影响A', '个股A', '白话A', '操作A')]")
s = s.replace('{"t":"A","i":"影响A","w":"白话A","a":"操作A"}', '{"t":"A","i":"影响A","s":"个股A","w":"白话A","a":"操作A"}')
s = s.replace("ok('禁止关键词缩写' in src, '禁止缩写/偷懒')",
              "ok('禁止关键词缩写' in src, '禁止缩写/偷懒')\nok('\"s\":\"代表个股深挖：点名1-2只能代表这条消息的股票代码+名称' in src, '代表个股深挖要素')\nok('🏆 代表个股' in src, '🏆 代表个股渲染行')")
io.open(P, 'w', encoding='utf-8', newline='').write(s)
# news2h 断言 → 五元组
P2 = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_news2h.py'
s2 = io.open(P2, encoding='utf-8').read()
s2 = s2.replace('ok("pairs[k] = (brief[k][\'t\'], it[1], it[2], it[3])" in src, \'标题以原始新闻为准\')',
                'ok("pairs[k] = (brief[k][\'t\'], it[1], it[2], it[3], it[4])" in src, \'标题以原始新闻为准\')')
s2 = s2.replace('ok("len(it[1]) < 12 or len(it[2]) < 12 or len(it[3]) < 10" in src, \'逐字段长度校验防偷懒\')',
                'ok("len(it[1]) < 12 or (len(it) >= 5 and len(it[2]) < 20)" in src, \'代表个股字段长度校验(≥20字)\')')
io.open(P2, 'w', encoding='utf-8', newline='').write(s2)
print('verify scripts updated')
