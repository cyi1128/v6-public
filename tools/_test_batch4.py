# -*- coding: utf-8 -*-
import ast, importlib.util
ast.parse(open('tools/cloud_daily_review.py',encoding='utf-8').read()); print('语法OK')
s=importlib.util.spec_from_file_location('m','tools/cloud_daily_review.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(m.breadth_sample())
print('div:', m.leader_divergence({}))
m.push=lambda *a,**k:(True,'mock')
print('noon len', len(m.build_noon()))
print('DONE')
