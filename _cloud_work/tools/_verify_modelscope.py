# -*- coding: utf-8 -*-
"""ModelScope 接入专项验证：源码断言 + 真实降级路径（假token→401→降级DeepSeek）。"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_daily_review as C

PASS, FAIL = 0, 0
def ok(cond, name):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(('  ✓ ' if cond else '  ✗ ') + name)

print('== A. 源码结构 ==')
src = io.open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
ok("MODELSCOPE_KEY = os.environ.get('MODELSCOPE_API_KEY', '')" in src, 'MODELSCOPE_KEY 从环境读取（不硬编码）')
ok("MODELSCOPE_URL = 'https://api-inference.modelscope.cn/v1/chat/completions'" in src, 'Base URL 正确')
ok("'Qwen/Qwen3.5-122B-A10B'" in src and "'Qwen/Qwen3.8-27B'" in src and "'Qwen/Qwen3.5-35B-A3B'" in src and "'Qwen/Qwen3.8-Flash-Next'" in src,
   '四个实测可用模型齐全（429自动轮换）')
ok('def _modelscope_chat(payload, purpose, system_text):' in src, '_modelscope_chat 存在')
ok("if not MODELSCOPE_KEY:" in src and '_modelscope_chat(payload, purpose, system_text or _ASK_DS_SYS)' in src,
   'ask_deepseek 纯 ModelScope 通道')
ok("if _ms:" in src and 'return _ms' in src, 'ModelScope 成功直接返回')
ok('for _try in range(2):' in src, 'ModelScope 失败重试2次')
ok("DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '') or 'ms-only'" in src, 'DeepSeek 已停用（恒非空占位兼容旧判断）')
ok("if code in (401, 403):" in src and 'return None' in src, '401/403 认证失败→规则兜底')
ok("if code in (429, 404):" in src and 'continue' in src, '429/404→换备选模型')
ok("MODELSCOPE_MODEL" in src, '支持 MODELSCOPE_MODEL 覆盖首模型')
# body 构造（max_tokens/temperature 与教程一致）
ok("'temperature': 0.5" in src and "'max_tokens': 3000" in src, '请求参数 0.5/3000 与教程一致')
ok("'Authorization': 'Bearer ' + MODELSCOPE_KEY" in src, 'Bearer 鉴权头')

print('== B. 真实降级路径（假 token → 401 → 重试后规则兜底） ==')
os.environ['MODELSCOPE_API_KEY'] = 'ms-test-invalid-token'
os.environ.pop('DEEPSEEK_API_KEY', None)
import importlib
importlib.reload(C)
ms = C._modelscope_chat({'task': 'probe', 'x': 1}, 'probe', 'sys')
ok(ms is None, f'_modelscope_chat 假token返回None（实测: {ms}）')
out = C.ask_deepseek({'task': 'probe', 'x': 1}, purpose='probe')
ok(out == '', f'ask_deepseek 假token最终返回空（规则兜底）（实测: {out!r}）')

print('== C. workflow env 注入 ==')
yml = io.open(r'D:\QuantMonitorV6\.github\workflows\daily-review2.yml', encoding='utf-8').read()
ok('MODELSCOPE_API_KEY: ${{ secrets.MODELSCOPE_API_KEY }}' in yml, 'workflow 注入 MODELSCOPE_API_KEY')
ok('【大白话运作逻辑·强制五步】' in src, '系统提示词含大白话五步逻辑')
ok('DEEPSEEK_API_KEY' not in yml, 'workflow 已移除 DeepSeek env')

print(f'\n===== 结果: {PASS} PASS / {FAIL} FAIL =====')
sys.exit(0 if FAIL == 0 else 1)
