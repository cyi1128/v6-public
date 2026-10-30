# -*- coding: utf-8 -*-
import ast, importlib.util
src = open('tools/cloud_daily_review.py', encoding='utf-8').read()
ast.parse(src); print('1. 语法OK', len(src.splitlines()))
s = importlib.util.spec_from_file_location('m', 'tools/cloud_daily_review.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print('2. commodities:', m.commodities())
print('3. premium:', m.yesterday_premium())
m.push = lambda *a, **k: (True, 'mock')
print('4. build_pre 长度', len(m.build_pre()))
print('5. build_noon 长度', len(m.build_noon()))
print('DONE')
