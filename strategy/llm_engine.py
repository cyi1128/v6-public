# -*- coding: utf-8 -*-
"""
本地大模型引擎

通过Ollama本地API调用开源大模型，将自然语言策略描述解析为标准JSON条件。
AI只负责理解和输出JSON，不执行选股计算，确保安全可控。

依赖：Ollama (https://ollama.com)
默认模型：qwen3:14b（可配置）
"""
import json
import re
import requests

from strategy.strategy_schema import (
    get_schema_description,
    is_valid_conditions,
    merge_with_default,
    DEFAULT_CONDITIONS,
)


class LLMEngine:
    """本地大模型策略解析引擎"""

    def __init__(self, model="qwen3:14b", base_url="http://localhost:11434", timeout=30):
        """
        初始化LLM引擎

        Args:
            model: Ollama模型名称，如qwen3:14b, qwen3:14b
            base_url: Ollama API地址
            timeout: 请求超时秒数
        """
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._available = None  # 缓存可用性检测结果

    def is_available(self):
        """
        检测Ollama服务是否可用

        Returns:
            bool: True表示可用
        """
        if self._available is not None:
            return self._available
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get('name', '') for m in data.get('models', [])]
                # 检查指定模型是否已下载
                if any(self.model in m for m in models):
                    self._available = True
                    return True
                # 如果有其他模型也可用（自动切换）
                if models:
                    self.model = models[0]
                    self._available = True
                    return True
            self._available = False
            return False
        except Exception:
            self._available = False
            return False

    def parse_strategy(self, user_text):
        """
        使用大模型解析自然语言策略描述

        Args:
            user_text: 用户自然语言描述，如"找价格5到60元，市值30到230亿，一年涨停超过3次的股票"

        Returns:
            dict: 解析后的标准条件字典
        """
        if not self.is_available():
            return None

        prompt = self._build_prompt(user_text)

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # 低温度，确保输出稳定
                        "num_predict": 500,  # 限制输出长度
                    }
                },
                timeout=self.timeout
            )

            if resp.status_code != 200:
                print(f"[LLM] API请求失败: {resp.status_code}")
                return None

            data = resp.json()
            raw_text = data.get('response', '').strip()

            # 提取JSON
            conditions = self._extract_json(raw_text)
            if conditions is None:
                print(f"[LLM] 无法从输出中提取JSON: {raw_text[:200]}")
                return None

            # 验证并合并默认值
            if not is_valid_conditions(conditions):
                print(f"[LLM] 输出条件不符合Schema: {conditions}")
                return None

            result = merge_with_default(conditions)
            print(f"[LLM] 解析成功: {result}")
            return result

        except requests.exceptions.Timeout:
            print("[LLM] 请求超时")
            return None
        except Exception as e:
            print(f"[LLM] 解析失败: {e}")
            return None

    def _build_prompt(self, user_text):
        """构建发送给AI的提示词"""
        schema_desc = get_schema_description()
        prompt = f"""你是一个专业的股票策略解析器。你的任务是将用户用自然语言描述的选股策略，转换为标准JSON格式的条件。

{schema_desc}

重要规则：
1. 只能输出JSON，不要输出任何解释、说明、markdown格式
2. 未提及的条件不要输出
3. 数字要准确，单位要正确（价格元、市值亿、百分比）
4. 如果用户说"涨幅6%"，pct_chg_range应设为[6, 99]
5. 如果用户说"涨幅3%到8%"，pct_chg_range应设为[3, 8]
6. 如果用户说"MACD金叉"，macd_golden_cross应设为true
7. 如果用户说"均线多头"，ma_bullish应设为true
8. 如果用户说"穿九"或"MA5上穿MA9"，ma5_cross_ma9应设为true

用户描述：{user_text}

输出JSON："""
        return prompt

    def _extract_json(self, text):
        """
        从AI输出文本中提取JSON

        Args:
            text: AI原始输出

        Returns:
            dict or None: 解析后的JSON字典
        """
        # 尝试直接解析
        try:
            return json.loads(text)
        except Exception:
            pass

        # 尝试提取 ```json ... ``` 块
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass

        # 尝试提取第一个 { 到最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass

        return None

    def get_model_info(self):
        """获取当前模型信息"""
        if not self.is_available():
            return {"available": False, "model": None}
        return {
            "available": True,
            "model": self.model,
            "base_url": self.base_url,
        }


# 单例
_llm_engine = None


def get_llm_engine(model="qwen2.5:7b"):
    """获取LLM引擎单例"""
    global _llm_engine
    if _llm_engine is None:
        _llm_engine = LLMEngine(model=model)
    return _llm_engine
