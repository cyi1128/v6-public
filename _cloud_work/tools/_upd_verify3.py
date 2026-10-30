# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_modelscope.py'
s = io.open(P, encoding='utf-8').read()
s = s.replace("ok('自动降级 DeepSeek 付费网关' in src, '失败降级 DeepSeek 文案')",
              "ok('for _try in range(2):' in src, 'ModelScope 失败重试2次')\nok(\"DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '') or 'ms-only'\" in src, 'DeepSeek 已停用（恒非空占位兼容旧判断）')")
s = s.replace("ok(\"if code in (401, 403):\" in src and 'return None' in src, '401/403 认证失败→降级')",
              "ok(\"if code in (401, 403):\" in src and 'return None' in src, '401/403 认证失败→规则兜底')")
s = s.replace("print('== B. 真实降级路径（假 token → 401 → 降级 DeepSeek） ==')",
              "print('== B. 真实降级路径（假 token → 401 → 重试后规则兜底） ==')")
s = s.replace("ok(out == '', f'ask_deepseek 假token+无DeepSeekKey 最终返回空（实测: {out!r}）')",
              "ok(out == '', f'ask_deepseek 假token最终返回空（规则兜底）（实测: {out!r}）')")
s = s.replace("ok('DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}' in yml, 'DeepSeek env 未破坏')",
              "ok('DEEPSEEK_API_KEY' not in yml, 'workflow 已移除 DeepSeek env')")
s = s.replace("ok('MODELSCOPE_API_KEY: ${{ secrets.MODELSCOPE_API_KEY }}' in yml, 'workflow 注入 MODELSCOPE_API_KEY')",
              "ok('MODELSCOPE_API_KEY: ${{ secrets.MODELSCOPE_API_KEY }}' in yml, 'workflow 注入 MODELSCOPE_API_KEY')\nok('【大白话运作逻辑·强制五步】' in src, '系统提示词含大白话五步逻辑')")
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('verify_modelscope updated')
