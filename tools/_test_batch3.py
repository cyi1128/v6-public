# -*- coding: utf-8 -*-
import ast, importlib.util
ast.parse(open('tools/cloud_daily_review.py',encoding='utf-8').read()); print('语法OK')
s = importlib.util.spec_from_file_location('m','tools/cloud_daily_review.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.push=lambda *a,**k:(True,'mock')
print('signals load:', m.load_signals())
print('backfill:', m.backfill_signals())
print('review:', m.signals_review_html())
print('build_eod len', len(m.build_eod()))
print('build_auction len', len(m.build_auction()))
print('DONE')
