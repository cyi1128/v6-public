# -*- coding: utf-8 -*-
"""一次性补丁：ModelScope（魔搭）免费 LLM 通道接入。
- 新增 _modelscope_chat()：OpenAI 兼容端点，urllib 原生实现零依赖；429/404 自动轮换备选模型；
- ask_deepseek 改造：ModelScope 优先（不烧 DS 预算/不记账），失败自动降级 DeepSeek 付费网关；
- 保留全部原有提示词结构，只换底层通道。
勿重跑。备份：.bak_before_modelscope"""
import io, sys

P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:70], n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# ========== 1. 配置区加 ModelScope 常量 ==========
rep("DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')  # 在 GitHub Secrets 配",
    "DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')  # 在 GitHub Secrets 配\n"
    "MODELSCOPE_KEY = os.environ.get('MODELSCOPE_API_KEY', '')  # 魔搭免费通道（GitHub Secrets 配，形如 ms-xxx，勿入库）\n"
    "MODELSCOPE_URL = 'https://api-inference.modelscope.cn/v1/chat/completions'\n"
    "# 首模型可被环境变量 MODELSCOPE_MODEL 覆盖；429/404 时依次轮换备选（单模型日额度用完自动换小模型）\n"
    "_MODELSCOPE_MODELS = ('Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2.5-32B-Instruct', 'ZhipuAI/GLM-4.7-Flash')")

# ========== 2. 新增 _modelscope_chat（放 ask_deepseek 之前） ==========
rep("def ask_deepseek(payload, purpose='eod', system_text=None):",
    "def _modelscope_chat(payload, purpose, system_text):\n"
    "    \"\"\"魔搭免费通道（OpenAI 兼容端点，urllib 原生零依赖）。\n"
    "    成功返回文本；401/403/429/404/网络失败返回 None（调用方降级 DeepSeek 付费网关）。\n"
    "    429/404 自动轮换备选模型（最多试完 _MODELSCOPE_MODELS 全部）。\"\"\"\n"
    "    models = list(_MODELSCOPE_MODELS)\n"
    "    override = os.environ.get('MODELSCOPE_MODEL', '')\n"
    "    if override and override not in models:\n"
    "        models.insert(0, override)\n"
    "    msgs = [{'role': 'system', 'content': system_text or _ASK_DS_SYS},\n"
    "            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]\n"
    "    for m in models:\n"
    "        try:\n"
    "            body = json.dumps({'model': m, 'messages': msgs,\n"
    "                              'temperature': 0.6, 'max_tokens': 1500}).encode('utf-8')\n"
    "            req = urllib.request.Request(MODELSCOPE_URL, data=body, headers={\n"
    "                'Content-Type': 'application/json',\n"
    "                'Authorization': 'Bearer ' + MODELSCOPE_KEY,\n"
    "                'User-Agent': 'quantmonitor/1.0'})\n"
    "            r = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))\n"
    "            txt = ((r.get('choices') or [{}])[0].get('message') or {}).get('content') or ''\n"
    "            if txt.strip():\n"
    "                print(f'[LLM] ModelScope OK model={m} purpose={purpose}')\n"
    "                return txt.strip()\n"
    "            print(f'[LLM] ModelScope 空回复 model={m}，试下一个')\n"
    "        except urllib.error.HTTPError as e:\n"
    "            code = e.code\n"
    "            if code in (401, 403):\n"
    "                print(f'[LLM] ModelScope 认证失败({code})：需绑定阿里云+实名 或 token 无效，降级 DeepSeek')\n"
    "                return None\n"
    "            if code in (429, 404):\n"
    "                print(f'[LLM] ModelScope {code} model={m} 额度/模型不可用，换备选')\n"
    "                continue\n"
    "            print(f'[LLM] ModelScope http_{code} model={m}，降级 DeepSeek')\n"
    "            return None\n"
    "        except Exception as e:\n"
    "            print(f'[LLM] ModelScope 异常: {str(e)[:120]}，降级 DeepSeek')\n"
    "            return None\n"
    "    print('[LLM] ModelScope 全部模型不可用，降级 DeepSeek')\n"
    "    return None\n"
    "\n"
    "\n"
    "def ask_deepseek(payload, purpose='eod', system_text=None):")

# ========== 3. ask_deepseek 改造：ModelScope 优先 ==========
rep("    global _DS_EXHAUSTED\n"
    "    if not DEEPSEEK_KEY:\n"
    "        return ''",
    "    global _DS_EXHAUSTED\n"
    "    # —— ModelScope 免费通道优先（成功即返回，不烧 DS 日预算/不记账）——\n"
    "    if MODELSCOPE_KEY:\n"
    "        _ms = _modelscope_chat(payload, purpose, system_text or _ASK_DS_SYS)\n"
    "        if _ms:\n"
    "            return _ms\n"
    "        print('[LLM] ModelScope 不可用，自动降级 DeepSeek 付费网关')\n"
    "    if not DEEPSEEK_KEY:\n"
    "        return ''")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
sys.exit(0 if not cnt['fail'] else 1)
