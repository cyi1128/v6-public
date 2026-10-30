# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_watch_v2.py'
s = io.open(P, encoding='utf-8').read()
s = s.replace("check('_spot_ds 大白话为 DS 文本非模板', '跟得最紧' in parsed['甲股'])",
              "check('_spot_ds 大白话为 DS 文本非模板', '跟得最紧' in parsed['甲股'].get('why', ''))")
s = s.replace("h_ok = cdr._watch_card(sg2, 62, {'万润科技': '存储芯片今天3只一起放量，资金合力，等回踩分时均线再上'})\ncheck('DS 命中 → 卡内为 AI 大白话', 'AI 大白话' in h_ok and '资金合力' in h_ok)",
              "h_ok = cdr._watch_card(sg2, 62, {'万润科技': '存储芯片今天3只一起放量，资金合力，等回踩分时均线再上'})\ncheck('DS 命中 → 卡内为大白话', '👉 大白话' in h_ok and '资金合力' in h_ok)")
s = s.replace("check('深度版解析仍正常', '跟得最紧' in parsed.get('甲股', ''))",
              "check('深度版解析仍正常', '跟得最紧' in parsed.get('甲股', {}).get('why', ''))")
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('watch_v2 asserts updated')
