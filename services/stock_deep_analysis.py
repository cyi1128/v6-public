# -*- coding: utf-8 -*-
"""
个股深度分析生成器
使用本地Ollama qwen2.5:7b模型（8GB显存可跑），按固定5章节模板生成企业微信深度个股推送。
调用 /api/chat 接口。
"""
import os
import sys
import json
import time
import hashlib
import requests
from datetime import datetime
from typing import Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 缓存目录
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache', 'deep_analysis')
os.makedirs(CACHE_DIR, exist_ok=True)

# Ollama配置
OLLAMA_BASE_URL = 'http://localhost:11434'
DEFAULT_MODEL = 'qwen2.5:7b'
TIMEOUT = 180  # 7b模型推理，给180秒超时

# 固定风险提示（一字不变）
FIXED_RISK_WARNING = (
    '> 【重要风险提示】本文仅为上市公司基本面信息梳理与逻辑拆解，'
    '不构成任何投资建议。股市波动大，存在多重不确定性风险，投资需谨慎。'
)


def _get_cache_path(code: str) -> str:
    """获取当日缓存文件路径"""
    date_str = datetime.now().strftime('%Y%m%d')
    return os.path.join(CACHE_DIR, f'{code}_{date_str}.txt')


def _load_cache(code: str) -> Optional[str]:
    """加载当日缓存"""
    path = _get_cache_path(code)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass
    return None


def _save_cache(code: str, content: str):
    """保存当日缓存"""
    path = _get_cache_path(code)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass


def _detect_model() -> str:
    """检测可用模型，优先7b（适配8GB显存）"""
    try:
        resp = requests.get(f'{OLLAMA_BASE_URL}/api/tags', timeout=3)
        if resp.status_code == 200:
            tags = (resp.json() or {}).get('models', [])
            if tags:
                # 优先qwen2.5:7b（8GB显存可跑）
                for t in tags:
                    if 'qwen2.5:7b' in t.get('name', ''):
                        return t['name']
                # 其次任意7b模型
                for t in tags:
                    if ':7b' in t.get('name', ''):
                        return t['name']
                # 其次qwen3系列
                for t in tags:
                    if 'qwen3' in t.get('name', ''):
                        return t['name']
                # 最后任意模型
                return tags[0].get('name', DEFAULT_MODEL)
    except Exception:
        pass
    return DEFAULT_MODEL


def _build_prompt(stock_info: Dict) -> str:
    """构建深度分析提示词"""
    code = stock_info.get('code', '')
    name = stock_info.get('name', '')
    industry = stock_info.get('industry', '')
    price = stock_info.get('price', 0)
    pct = stock_info.get('pct_chg', 0)
    score = stock_info.get('total_score', stock_info.get('ai520_score', 0))
    grade = stock_info.get('grade', '')
    market_cap = stock_info.get('market_cap', 0)

    # 一句话定位（基于行业和评分）
    positioning = f'{industry}行业{grade}级标的，AI520评分{score}分'

    prompt = f"""你是一位资深A股投研分析师。请对以下股票生成一份完整的企业微信深度推送文稿。

【股票信息】
- 股票名称：{name}
- 股票代码：{code}
- 所属行业：{industry}
- 当前价格：{price:.2f}元（{pct:+.2f}%）
- 总市值：{market_cap:.1f}亿元（如有）
- AI520评分：{score}分（{grade}级）
- 一句话定位：{positioning}

【输出要求】
严格按照以下固定格式输出，使用markdown，章节顺序不能调换，禁止输出精简版：

# 【个股深度｜{name} {code}】企业微信推送完整版
> 推送场景：投研企业微信群｜适合盘中盘后深度研读，保留完整逻辑、业务拆分、产业链、业绩驱动、潜在预期与风险，无过度压缩
> 标的：{name}（{code}）｜{positioning}

## 一、标的基础画像
简述公司主营、核心赛道、行业地位、核心业务属性，区分主业/题材业务。

## 二、最新财报核心业绩拆解
1、财报核心指标：营收、同比；归母净利润、同比；扣非净利润、同比；经营活动现金流；研发投入及同比。数据缺失时标注【暂无最新公开数据】，不编造数据。
2、业务板块拆分：分业务介绍营收、增速、毛利率、下游客户、业务属性（基本盘/增长引擎）。

## 三、核心投资逻辑分层拆解
### 1. 短期逻辑（1年内，业绩兑现主线）
业绩核心驱动，当前最核心基本面变化、产能、并购、订单、原料端变化。
### 2. 中期逻辑（1–3年）
产能扩张、国产替代、下游行业渗透率提升、供应链导入等中期成长逻辑。
### 3. 长期远期期权（3年以上，产业化存在不确定性）
新业务、新材料、新赛道题材；必须注明：短期基本无营收贡献，仅为估值期权，存在落地不确定性。

## 四、核心风险清单
逐条罗列，至少5条，覆盖：下游需求周期、原材料价格、产能/并购整合、新品认证风险、行业竞争、业务结构短板等。

## 五、逻辑总结
分短期、中期、长期三层总结；区分业绩真实兑现部分和题材期权，点明标的本质，区分基本面驱动 vs 题材炒作。

{FIXED_RISK_WARNING}

【强制规则】
1. 财报优先使用最新一期正式财报数据；数据缺失时标注【暂无最新公开数据】，不编造数据。
2. 题材业务必须明确区分远期期权，严禁把远期题材当成当前业绩主线。
3. 企业微信推送排版适配，使用markdown，标题层级清晰，不使用复杂表格。
4. 每次只输出个股推送正文，不要额外对话、不要询问是否需要调整，直接输出完整推送文稿。
5. 所有分析必须基于该股票的真实行业属性和公开信息，禁止脱离股票编造。

现在开始输出完整推送文稿："""
    return prompt


def generate_deep_analysis(stock_info: Dict, use_cache: bool = True) -> Optional[str]:
    """
    生成个股深度分析

    Args:
        stock_info: 股票信息字典，需包含code, name, industry等
        use_cache: 是否使用当日缓存

    Returns:
        str: 深度分析markdown文本，失败返回None
    """
    code = stock_info.get('code', '')
    name = stock_info.get('name', '')
    if not code:
        return None

    # 检查缓存
    if use_cache:
        cached = _load_cache(code)
        if cached:
            print(f'[深度分析] {name}({code}) 使用当日缓存', flush=True)
            return cached

    # 检测Ollama是否可用
    try:
        resp = requests.get(f'{OLLAMA_BASE_URL}/api/tags', timeout=3)
        if resp.status_code != 200:
            print(f'[深度分析] Ollama服务不可用: HTTP {resp.status_code}', flush=True)
            return None
    except Exception as e:
        print(f'[深度分析] Ollama服务连接失败: {e}', flush=True)
        return None

    model = _detect_model()
    prompt = _build_prompt(stock_info)

    print(f'[深度分析] 开始生成 {name}({code})，模型={model}，超时={TIMEOUT}s', flush=True)
    start_time = time.time()

    try:
        resp = requests.post(
            f'{OLLAMA_BASE_URL}/api/chat',
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'stream': False,
                'options': {
                    'temperature': 0.3,
                    'num_predict': 4096,
                }
            },
            timeout=TIMEOUT,
        )

        if resp.status_code != 200:
            print(f'[深度分析] API请求失败: HTTP {resp.status_code}', flush=True)
            return None

        data = resp.json() or {}
        text = ((data.get('message') or {}).get('content') or '').strip()

        if not text:
            print(f'[深度分析] 模型返回空内容', flush=True)
            return None

        elapsed = time.time() - start_time
        print(f'[深度分析] {name}({code}) 生成完成，耗时{elapsed:.1f}s，{len(text)}字', flush=True)

        # 确保末尾有固定风险提示
        if FIXED_RISK_WARNING not in text:
            text = text.rstrip() + '\n\n' + FIXED_RISK_WARNING

        # 保存缓存
        _save_cache(code, text)

        return text

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f'[深度分析] {name}({code}) 生成超时({elapsed:.0f}s)，使用精简推送', flush=True)
        return None
    except Exception as e:
        print(f'[深度分析] {name}({code}) 生成失败: {e}', flush=True)
        return None


def is_ollama_available() -> bool:
    """检测Ollama服务是否可用"""
    try:
        resp = requests.get(f'{OLLAMA_BASE_URL}/api/tags', timeout=3)
        return resp.status_code == 200
    except Exception:
        return False
