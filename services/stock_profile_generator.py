# -*- coding: utf-8 -*-
"""
个股深度画像生成器
- 调用火山方舟API（DeepSeek-V4-Pro）生成个股深度画像
- 画像内容：主营产品、核心技术、关键材料、产业链位置、受益概念标签、利好触发关键词
- 本地JSON缓存，当日不重复生成
- 批量生成，每只间隔2秒避免限流
- 后台线程运行，不阻塞UI
"""
import os
import sys
import json
import time
import threading
import traceback
from datetime import datetime
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests

# 配置路径
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'ark_api_config.json')
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache', 'stock_profiles')

# 确保缓存目录存在
os.makedirs(CACHE_DIR, exist_ok=True)


def _log(msg: str, level: str = 'INFO'):
    """日志输出"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] [StockProfile] [{level}] {msg}", flush=True)


def load_ark_config() -> Dict:
    """加载火山方舟API配置"""
    default_config = {
        'enabled': True,
        'api_key': os.environ.get('ARK_API_KEY', ''),
        'model': 'deepseek-v4-pro-ga-260813',
        'endpoint': 'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
        'timeout': 60,
        'max_tokens': 1500,
    }
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            default_config.update(cfg)
    except Exception as e:
        _log(f"加载API配置失败，使用默认值: {e}", 'WARN')
    return default_config


class StockProfileGenerator:
    """个股深度画像生成器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._config = load_ark_config()
        self._generating = set()  # 正在生成中的股票代码，防止重复
        self._gen_lock = threading.Lock()
        _log(f"画像生成器初始化完成 (model={self._config.get('model')}, enabled={self._config.get('enabled')})")

    def _get_cache_path(self, code: str, date_str: str = None) -> str:
        """获取缓存文件路径"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')
        return os.path.join(CACHE_DIR, f"{code}_{date_str}.json")

    def get_profile(self, code: str) -> Optional[Dict]:
        """从缓存读取画像，不存在返回None"""
        if not code:
            return None
        cache_path = self._get_cache_path(code)
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            _log(f"读取画像缓存失败 {code}: {e}", 'WARN')
        return None

    def _save_profile(self, code: str, name: str, profile: Dict):
        """保存画像到缓存"""
        cache_path = self._get_cache_path(code)
        try:
            profile['_meta'] = {
                'code': code,
                'name': name,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'model': self._config.get('model', ''),
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
            _log(f"画像缓存已保存: {cache_path}")
        except Exception as e:
            _log(f"保存画像缓存失败 {code}: {e}", 'ERROR')

    def _build_prompt(self, code: str, name: str) -> str:
        """构建画像生成Prompt"""
        prompt = f"""请为A股股票 {name}({code}) 生成深度行业画像。

要求：
1. 返回严格的JSON格式，不要包含任何解释性文字或markdown标记
2. JSON包含以下字段：
   - main_products: 主营产品（字符串，简述公司主要产品和业务）
   - core_tech: 核心技术（字符串，公司掌握的核心技术或工艺）
   - key_materials: 关键材料（字符串，生产所需的关键原材料或上游材料）
   - industry_chain: 产业链位置（字符串，说明公司在产业链中处于上游/中游/下游，以及具体环节）
   - concept_tags: 受益概念标签（数组，列出5-10个相关概念板块名称，如["PCB", "汽车电子", "AI服务器"]）
   - bullish_keywords: 利好触发关键词（数组，列出8-15个可能触发股价上涨的新闻关键词，如["PCB涨价", "HDI产能扩张", "汽车电子订单"]）

请基于公开的行业知识和公司基本面信息生成，确保内容准确、专业。
"""
        return prompt

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """解析API返回的JSON内容，处理可能的markdown包裹"""
        if not text:
            return None
        text = text.strip()
        # 去除可能的markdown代码块标记
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()
        # 找到第一个{和最后一个}
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            _log(f"JSON解析失败，原始内容前200字: {text[:200]}", 'WARN')
            return None

    def _call_api(self, prompt: str) -> Optional[str]:
        """调用火山方舟API，超时30秒，异常捕获"""
        if not self._config.get('enabled', True):
            _log("API已禁用，跳过调用", 'WARN')
            return None

        try:
            headers = {
                'Authorization': f"Bearer {self._config['api_key']}",
                'Content-Type': 'application/json',
            }
            payload = {
                'model': self._config['model'],
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': self._config.get('max_tokens', 2000),
            }
            _log(f"调用API: model={self._config['model']}, timeout={self._config.get('timeout', 30)}s")
            resp = requests.post(
                self._config['endpoint'],
                headers=headers,
                json=payload,
                timeout=self._config.get('timeout', 30),
            )
            if resp.status_code != 200:
                _log(f"API返回非200: status={resp.status_code}, body={resp.text[:300]}", 'ERROR')
                return None
            data = resp.json()
            choices = data.get('choices', [])
            if not choices:
                _log(f"API返回无choices: {str(data)[:300]}", 'ERROR')
                return None
            content = choices[0].get('message', {}).get('content', '')
            if not content:
                _log("API返回content为空", 'ERROR')
                return None
            return content
        except requests.exceptions.Timeout:
            _log(f"API调用超时（{self._config.get('timeout', 30)}秒）", 'ERROR')
            return None
        except requests.exceptions.RequestException as e:
            _log(f"API请求异常: {e}", 'ERROR')
            return None
        except Exception as e:
            _log(f"API调用未知异常: {e}\n{traceback.format_exc()}", 'ERROR')
            return None

    def generate_profile(self, code: str, name: str = '', force: bool = False) -> Optional[Dict]:
        """
        生成单只股票画像
        Args:
            code: 股票代码
            name: 股票名称
            force: 是否强制重新生成（忽略缓存）
        Returns:
            画像dict，失败返回None
        """
        if not code:
            return None

        # 检查缓存
        if not force:
            cached = self.get_profile(code)
            if cached:
                _log(f"使用缓存画像: {name}({code})")
                return cached

        # 防止重复生成
        with self._gen_lock:
            if code in self._generating:
                _log(f"画像正在生成中，跳过: {name}({code})")
                return None
            self._generating.add(code)

        try:
            _log(f"开始生成画像: {name}({code})")
            prompt = self._build_prompt(code, name)
            raw_content = self._call_api(prompt)
            if not raw_content:
                return None

            profile = self._parse_json_response(raw_content)
            if not profile:
                _log(f"画像解析失败: {name}({code})", 'ERROR')
                return None

            # 确保必要字段存在
            required_fields = ['main_products', 'core_tech', 'key_materials',
                               'industry_chain', 'concept_tags', 'bullish_keywords']
            for field in required_fields:
                if field not in profile:
                    profile[field] = '' if field in ('main_products', 'core_tech',
                                                       'key_materials', 'industry_chain') else []

            self._save_profile(code, name, profile)
            _log(f"画像生成成功: {name}({code})")
            return profile
        except Exception as e:
            _log(f"生成画像异常 {name}({code}): {e}\n{traceback.format_exc()}", 'ERROR')
            return None
        finally:
            with self._gen_lock:
                self._generating.discard(code)

    def generate_batch(self, stocks: List[Dict], interval: float = 2.0) -> Dict[str, Dict]:
        """
        批量生成画像
        Args:
            stocks: 股票列表，每项为 {'code': 'xxx', 'name': 'xxx'} 或包含code/name字段的dict
            interval: 每只股票间隔秒数
        Returns:
            {code: profile_dict} 成功生成的画像
        """
        results = {}
        if not stocks:
            return results

        _log(f"开始批量生成画像，共{len(stocks)}只，间隔{interval}秒")
        for i, stock in enumerate(stocks):
            code = stock.get('code', '') if isinstance(stock, dict) else str(stock)
            name = stock.get('name', '') if isinstance(stock, dict) else ''
            if not code:
                continue
            try:
                profile = self.generate_profile(code, name)
                if profile:
                    results[code] = profile
            except Exception as e:
                _log(f"批量生成异常 {code}: {e}", 'ERROR')
            # 间隔
            if i < len(stocks) - 1:
                time.sleep(interval)

        _log(f"批量生成完成，成功{len(results)}/{len(stocks)}只")
        return results

    def generate_batch_async(self, stocks: List[Dict], interval: float = 2.0,
                              callback=None) -> threading.Thread:
        """
        异步批量生成画像（后台线程）
        Args:
            stocks: 股票列表
            interval: 间隔秒数
            callback: 完成回调 callback(results_dict)
        Returns:
            后台线程对象
        """
        def _worker():
            try:
                results = self.generate_batch(stocks, interval)
                if callback:
                    try:
                        callback(results)
                    except Exception:
                        pass
            except Exception as e:
                _log(f"异步批量生成异常: {e}", 'ERROR')

        thread = threading.Thread(target=_worker, daemon=True, name='StockProfileBatch')
        thread.start()
        _log(f"异步批量生成线程已启动，{len(stocks)}只股票")
        return thread


# 全局单例
_generator: Optional[StockProfileGenerator] = None


def get_profile_generator() -> StockProfileGenerator:
    """获取画像生成器单例"""
    global _generator
    if _generator is None:
        _generator = StockProfileGenerator()
    return _generator


if __name__ == '__main__':
    # 测试：生成中京电子画像
    print("=" * 60)
    print("测试个股深度画像生成")
    print("=" * 60)
    gen = get_profile_generator()
    profile = gen.generate_profile('002579', '中京电子')
    if profile:
        print("\n画像生成成功！")
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    else:
        print("\n画像生成失败！")
