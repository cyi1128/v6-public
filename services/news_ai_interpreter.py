# -*- coding: utf-8 -*-
"""
AI 量化新闻深度解读服务（V6量化投研简报 · 大模型版）
================================================================
调用火山方舟 API（DeepSeek-V4-Pro），以"量化程序新闻AI解读专用系统指令"为
System Prompt，对单条A股新闻生成六模块深度投研简报：

  ⚡ 一句话核心提炼 / 🧠 深度逻辑拆解 / 📈 机会挖掘红榜 /
  📉 风险预警黑榜 / 🌡️ 交易环境共振 / 🏷️ 量化标签JSON

输入补充真实上下文（大盘情绪、关联板块实时涨跌、问财关联股票），
让"交易环境共振/机会红榜"有据可依；大模型不可用时由调用方降级规则模板。

硬性红线（写死在 System Prompt）：
- 禁止编造公司合作关系，提及公司必须标注证据等级（A/B/C/D）
- 禁止给出具体买卖点位，只给操作原则
- 禁止"可能/或许/值得关注"等模糊词
- 旧闻/传闻必须开头标注
"""
import os
import sys
import re
import json
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests

from services.stock_profile_generator import load_ark_config

# 量化程序新闻AI解读专用系统指令（实战增强版）——用户提供的原始指令
SYSTEM_PROMPT = """你是一位拥有20年A股实战经验的资深量化策略分析师，兼具卖方产业研究员的产业链拆解能力、买方基金经理的主线轮动思维、短线交易员的情绪博弈敏感度。

一、总则
后续所有消息，默认按"路由式六模块"解读。
先判定新闻类型，再按类型路由到对应条件模块。
输出顺序固定：核心提炼 → 新闻类型判定 → 深度逻辑拆解 → 红榜 → 黑榜 → 条件模块 → 操作建议。
结论优先，不绕弯，先给方向、主体、强度。
不编造合作关系，不编造订单，不编造客户。
不输出具体买卖点位。
不使用"可能 / 或许"等模糊词。
旧闻、传闻、未证实信息，开头必须标注"旧闻"或"传闻"。

二、核心六模块
1. ⚡ 核心提炼（200字内）
包含：主体、事件、方向、强度、关键数字。只给结论，不展开论证。

2. 🧭 新闻类型判定
股票类 / 非股票类 / 混合类。政策类、产业类、热点类可叠加标注。

3. 🧠 深度逻辑拆解
传导链条：政策/事件 → 行业供需 → 公司订单/成本/产能 → 业绩/估值 → 资金/情绪。
反向传导同步列出。区分短期情绪与中期业绩。

4. 📈 红榜（尽量全，不只列头部）
受益股票+代码，每只标注证据等级 A/B/C/D。
按订单、技术、材料、供应链卡位四维交叉筛选。
含上中下游供货商分层。标注与哪家公司有关联、客户、供应商、合作方。
有新技术的描述技术路线；有新产品的描述产品形态；有新材料的描述材料参数与壁垒。
有高切低卡位逻辑的单独说明。

5. 📉 黑榜
风险股票+代码，跷跷板承压方向，证据等级 A/B/C/D。
政策类若无明确受损标的，写"未出现明确受损标的"，并列出跷跷板方向。

6. 条件模块路由
🌐 非股票→A股映射：仅非股票类、混合类中的非股票部分。
🏛️ 政策层级：仅政策类。
📊 产业数据：仅产业类。
🧠 情绪题材：仅热点类。
🎯 操作建议：仅股票类给仓位区间，不给具体买卖点位。

三、硬性红线
不编造合作关系、订单、客户、财务数据。
证据等级必须标注 A/B/C/D。
不给具体买卖点位。不用"可能/或许"模糊词。
旧闻/传闻开头标注。

四、证据等级定义
A：官方公告/监管文件/财报。
B：权威媒体/行业协会/券商研报。
C：公司互动/调研纪要/产业链映射。
D：传闻/未证实信息。

五、产业链分层模板（命中触发词时强制全链展开）
光模块触发词：光模块、光器件、CPO、LPO、800G、1.6T、硅光、光芯片、光纤光缆、交换机、AI服务器、PCB、铜连接、液冷、电源、IDC。
光模块分层：整机→光器件→光芯片→光材料→光纤光缆→铜缆高速连接→PCB→液冷→AI服务器→IDC。

液冷触发词：液冷、温控、散热、冷板、浸没、CDU、冷却液、氟化液、快接头、液冷泵、冷却塔、液冷板、储能液冷。
液冷分层：机房温控/CDU/液冷系统 → 液冷板/冷板 → 液冷泵/阀/快接头 → 冷却液/氟化液 → 服务器液冷整机 → 储能液冷 → 冷却塔/管路。

跨概念交叉：光模块+铜缆、光模块+液冷、光模块+电源、光模块+PCB、液冷+储能、液冷+绿电、算力+调度平台、算力+计量清算。

易漏标的自检：铭普光磁、川润股份、同飞股份、佳力图、依米康、高澜股份、申菱环境、英维克、银轮股份、三花智控、飞龙股份、腾龙股份、盾安环境、松芝股份、和胜股份、华峰铝业、银邦股份、常铝股份、亚太科技、利欧股份、大元泵业、凌霄泵业、中航光电、维峰电子、巨化股份、新宙邦、永和股份、三美股份、永太科技、润禾材料、中科曙光、浪潮信息、工业富联、紫光股份、中兴通讯、海鸥股份、双一科技、纳川股份。

六、输出要求
红榜黑榜尽量全，不只给代表标的。
C级证据纳入红榜，但必须标注"互动/调研/小批量，利润贡献有限"。
股票池不全时补全并说明漏标原因。
高切低卡位逻辑单独说明。
输出前执行易漏标的自检。
量化标签JSON不向前台输出（后台程序解析用）。"""


def _log(msg: str):
    print(f"[NewsAI] {msg}", flush=True)


def build_extra_context(sector_map=None, matched_sectors=None, wencai_stocks=None, wencai_voice='', market_brief=None):
    """组装大模型可见的真实上下文（板块实时涨跌/问财关联股票/大盘情绪），让解读有据可依"""
    lines = []
    if market_brief:
        lines.append(f"【大盘实时概况】{market_brief}")
    if matched_sectors and sector_map:
        sec_parts = []
        for sname in matched_sectors[:8]:
            sec = sector_map.get(sname, {})
            try:
                cp = float(sec.get('change_pct', 0) or 0)
            except Exception:
                cp = 0.0
            sec_parts.append(f"{sname}{cp:+.2f}%")
        lines.append(f"【关联板块实时涨跌】{' '.join(sec_parts)}")
    if wencai_stocks:
        stock_parts = []
        for s in wencai_stocks[:10]:
            try:
                pct = float(s.get('pct', 0) or 0)
            except Exception:
                pct = 0.0
            price = s.get('price', 0)
            price_str = f"{price:.2f}" if price else '--'
            stock_parts.append(f"{s.get('name', '')}({s.get('code', '')}) 现价{price_str} {pct:+.2f}%")
        lines.append("【问财检索到的直接关联股票】" + "；".join(stock_parts))
    if wencai_voice:
        lines.append(f"【问财检索信息】{wencai_voice[:200]}")
    return '\n'.join(lines)


def build_user_prompt(news, extra_context=''):
    """构建用户消息：新闻 + 真实上下文"""
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    sentiment = str(news.get('sentiment', '中性') or '中性')
    intensity = str(news.get('intensity', news.get('impact', '中')) or '中')
    source = str(news.get('source', ''))

    parts = [
        f"请对以下A股新闻做量化投研简报解读：\n",
        f"【新闻标题】{title}",
        f"【新闻内容】{content}",
        f"【消息属性】情绪判定：{sentiment}；影响等级：{intensity}；来源：{source}",
    ]
    if extra_context:
        parts.append(f"\n【可参考的真实数据（仅作依据，勿编造额外数据）】\n{extra_context}")
    parts.append("\n请直接输出符合规范要求的完整解读（六模块 + 量化标签JSON代码块）。")
    return '\n'.join(parts)


# 本地Ollama配置（用户要求改用本地AI，零费用不限量）
LOCAL_LLM_ENABLED = True
LOCAL_LLM_URL = "http://localhost:11434/v1/chat/completions"
LOCAL_LLM_MODEL = "deepseek-r1:7b"


def call_ark(user_prompt, timeout=300, force_cloud=False):
    """调用大模型解读。force_cloud=True走火山方舟，否则优先本地Ollama"""
    cfg = load_ark_config()
    if not cfg.get('enabled', True):
        _log("API已禁用，跳过调用")
        return None

    use_local = LOCAL_LLM_ENABLED and not force_cloud
    endpoint = LOCAL_LLM_URL if use_local else cfg['endpoint']
    model_name = LOCAL_LLM_MODEL if use_local else cfg['model']

    payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': cfg.get('max_tokens', 1500) * 2,
        'temperature': 0.4,
        'stream': False,
    }
    headers = {
        'Content-Type': 'application/json',
    }
    if not use_local:
        headers['Authorization'] = f"Bearer {cfg['api_key']}"

    last_err = None
    for attempt in (1, 2):
        try:
            _log(f"调用API (model={model_name}, attempt={attempt}, timeout={timeout}s)")
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                _log(f"API非200: {last_err}")
                continue
            data = resp.json()
            choices = data.get('choices', [])
            if not choices:
                last_err = "无choices"
                _log(f"API无choices: {str(data)[:300]}")
                continue
            content = choices[0].get('message', {}).get('content', '')
            if not content:
                last_err = "content为空"
                _log("API content为空")
                continue
            _log(f"API调用成功，输出{len(content)}字符")
            # 记录token用量到本地文件
            try:
                usage = data.get('usage', {}) or {}
                import json as _uj
                import os as _uo
                ut = usage.get('total_tokens', 0) or 0
                up = usage.get('prompt_tokens', 0) or 0
                uc = usage.get('completion_tokens', 0) or 0
                uf = _uo.path.join(_uo.path.dirname(_uo.path.dirname(_uo.path.abspath(__file__))), 'data', 'ark_usage.json')
                try:
                    rec = _uj.load(open(uf, encoding='utf-8')) if _uo.path.exists(uf) else {}
                except Exception:
                    rec = {}
                rec['calls'] = int(rec.get('calls', 0)) + 1
                rec['prompt_tokens'] = int(rec.get('prompt_tokens', 0)) + int(up)
                rec['completion_tokens'] = int(rec.get('completion_tokens', 0)) + int(uc)
                rec['total_tokens'] = int(rec.get('total_tokens', 0)) + int(ut)
                rec['last_used'] = time.strftime('%Y-%m-%d %H:%M:%S')
                _uj.dump(rec, open(uf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
                _log(f"本次tokens: {ut} (输入{up}/输出{uc})，累计: {rec['total_tokens']}")
            except Exception as _ue:
                _log(f"用量记录失败: {_ue}")
            return content
        except requests.exceptions.Timeout:
            last_err = f"超时({timeout}s)"
            _log(f"API超时 (attempt={attempt})")
        except requests.exceptions.RequestException as e:
            last_err = str(e)[:200]
            _log(f"API请求异常: {last_err}")
        except Exception as e:
            last_err = str(e)[:200]
            _log(f"API未知异常: {last_err}\n{traceback.format_exc()}")
        if attempt == 1:
            time.sleep(2)
    _log(f"API调用最终失败: {last_err}")
    return None


def extract_quant_json(text):
    """从markdown解读中提取 ```json ... ``` 块并解析为dict"""
    if not text:
        return None
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def sentiment_from_quant(quant, news):
    """由量化标签推断弹窗情绪：利好/利空/中性"""
    if quant and isinstance(quant, dict):
        try:
            score = float(quant.get('sentiment_score', 0))
            if score >= 0.15:
                return '利好'
            if score <= -0.15:
                return '利空'
            return '中性'
        except Exception:
            pass
    s = str(news.get('sentiment', '中性') or '中性')
    return s if s in ('利好', '利空', '中性') else '中性'


def interpret_news(news, sector_map=None, matched_sectors=None,
                   wencai_stocks=None, wencai_voice='', market_brief=None):
    """生成V6量化投研简报（大模型版）。

    Args:
        news: 新闻dict
        sector_map: 板块实时数据
        matched_sectors: 匹配到的板块名列表
        wencai_stocks: 问财关联股票
        wencai_voice: 问财voice_txt
        market_brief: 大盘概况文本（如"涨跌比2890:2110 涨停47家 情绪偏强"）

    Returns:
        dict or None: {
            'text': 六模块markdown全文,
            'quant': 量化标签dict或None,
            'mode': 'ai',
            'sentiment': 利好/利空/中性,
            'impact': 强/中/弱,
        }
    """
    try:
        # 临时禁用NewsAI API（账户欠费），避免403后崩溃
        return None
        extra = build_extra_context(
            sector_map=sector_map, matched_sectors=matched_sectors,
            wencai_stocks=wencai_stocks, wencai_voice=wencai_voice,
            market_brief=market_brief,
        )
        user_prompt = build_user_prompt(news, extra_context=extra)
        text = call_ark(user_prompt, force_cloud=True)
        if not text:
            return None
        quant = extract_quant_json(text)
        impact = str(news.get('intensity', news.get('impact', '中')) or '中')
        if impact not in ('强', '中', '弱'):
            impact = '中'
        return {
            'text': text,
            'quant': quant,
            'mode': 'ai',
            'sentiment': sentiment_from_quant(quant, news),
            'impact': impact,
        }
    except Exception as e:
        _log(f"解读生成异常: {e}\n{traceback.format_exc()}")
        return None


def ask_question(news, question, timeout=90):
    """AI追问：基于当前新闻上下文，用大模型直接回答用户追问（不依赖问财）。

    Args:
        news: 新闻dict（title/content）
        question: 用户追问文本
        timeout: 秒

    Returns:
        str 回答文本，失败返回None
    """
    cfg = load_ark_config()
    if not cfg.get('enabled', True):
        return None
    sys_p = (
        '你是A股资深量化交易助手。基于给定新闻上下文回答用户追问：'
        '简短、专业、直击要点（200字以内）；不编造公司关联，不确定就说不确定；'
        '不给具体买卖点位（价格/日期），只给原则性方向。'
    )
    user_p = (
        f"【新闻】{news.get('title', '')}\n{news.get('content', '')}\n\n"
        f"【用户追问】{question}"
    )
    payload = {
        'model': cfg['model'],
        'messages': [
            {'role': 'system', 'content': sys_p},
            {'role': 'user', 'content': user_p},
        ],
        'max_tokens': 600,
        'temperature': 0.5,
    }
    headers = {
        'Authorization': f"Bearer {cfg['api_key']}",
        'Content-Type': 'application/json',
    }
    try:
        resp = requests.post(cfg['endpoint'], headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            _log(f"追问API非200: {resp.status_code} {resp.text[:200]}")
            return None
        content = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '')
        return content.strip() or None
    except Exception as e:
        _log(f"追问API异常: {e}")
        return None
