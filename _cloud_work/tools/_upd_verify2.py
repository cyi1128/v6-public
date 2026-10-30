# -*- coding: utf-8 -*-
import io
# newsbrief
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_newsbrief.py'
s = io.open(P, encoding='utf-8').read()
s = s.replace('ok(\'"items":[{"t":"消息标题","p":"大白话\' in src, \'DS 要求 JSON 输出（逐条大白话）\')',
              'ok(\'{"items":[{"t":"消息标题","i":"影响\' in src, \'DS 要求 JSON 三要素输出\')')
s = s.replace('ok(\'必须覆盖全部{num}条，不许漏、不许编\' in src, \'禁止漏条/编造\')',
              'ok(\'禁止关键词缩写\' in src, \'禁止缩写/偷懒\')')
s = s.replace("ok(C._parse_ds_json('{\"items\":[{\"t\":\"A\",\"p\":\"解读A\"},{\"t\":\"B\",\"p\":\"解读B\"}]}') == [('A', '解读A'), ('B', '解读B')],",
              "ok(C._parse_ds_json('{\"items\":[{\"t\":\"A\",\"p\":\"解读A\"},{\"t\":\"B\",\"p\":\"解读B\"}]}') == [('A', '', '解读A', ''), ('B', '', '解读B', '')],")
s = s.replace("ok(C._parse_ds_json('```json\\n{\"items\":[{\"t\":\"X\",\"p\":\"Y\"}]}\\n```') == [('X', 'Y')], 'markdown 代码块包裹解析')",
              "ok(C._parse_ds_json('```json\\n{\"items\":[{\"t\":\"X\",\"p\":\"Y\"}]}\\n```') == [('X', '', 'Y', '')], 'markdown 代码块包裹解析')")
s = s.replace("ok(C._parse_ds_json('{\"data\":[{\"title\":\"T1\",\"note\":\"N1\"}]}') == [('T1', 'N1')], 'data/title/note 别名解析')",
              "ok(C._parse_ds_json('{\"data\":[{\"title\":\"T1\",\"note\":\"N1\"}]}') == [('T1', '', 'N1', '')], 'data/title/note 别名解析')")
s = s.replace("ok(C._parse_ds_json('{\"items\":[{\"t\":\"A\",\"i\":\"影响A\",\"w\":\"白话A\",\"a\":\"操作A\"}]}')",
              "ok(C._parse_ds_json('{\"items\":[{\"t\":\"A\",\"i\":\"影响A\",\"w\":\"白话A\",\"a\":\"操作A\"}]}')")
if "('A', '影响A', '白话A', '操作A')" not in s:
    s = s.replace("== [('A', '影响A', '白话A', '操作A')]", "== [('A', '影响A', '白话A', '操作A')]")
io.open(P, 'w', encoding='utf-8', newline='').write(s)
# modelscope
P2 = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_modelscope.py'
s2 = io.open(P2, encoding='utf-8').read()
s2 = s2.replace("0.6/1500", "0.5/3000").replace("'temperature': 0.6, 'max_tokens': 1500", "'temperature': 0.5, 'max_tokens': 3000")
io.open(P2, 'w', encoding='utf-8', newline='').write(s2)
print('done')
