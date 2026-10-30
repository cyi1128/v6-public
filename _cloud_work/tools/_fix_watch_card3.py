# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
lines = io.open(P, encoding='utf-8').read().split('\n')
i_ai = next(i for i, l in enumerate(lines) if l == '{_ai_block}')
del lines[i_ai]
i_why = next(i for i, l in enumerate(lines) if l.strip().startswith("_why = _dsp if _dsp else"))
lines[i_why:i_why] = ['    else:']
i_ai2 = next(i for i, l in enumerate(lines) if l.strip().startswith('_ai_block = ('))
lines[i_ai2 + 1:i_ai2 + 1] = ['{_ai_block}']
io.open(P, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
print('fixed')
