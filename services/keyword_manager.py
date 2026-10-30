# -*- coding: utf-8 -*-
"""
利好因素关键词管理器
- 从个股深度画像中提取利好触发关键词
- 关键词库本地JSON存储，支持手动补充
- 新闻文本匹配，返回命中的股票和关键词
"""
import os
import sys
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 关键词库路径
KEYWORDS_PATH = os.path.join(PROJECT_ROOT, 'data', 'stock_keywords.json')

# 核心关键词判定：出现在concept_tags前2位或bullish_keywords前3位的视为核心
CORE_KEYWORD_RANK = 3


def _log(msg: str, level: str = 'INFO'):
    """日志输出"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] [KeywordMgr] [{level}] {msg}", flush=True)


class KeywordManager:
    """利好因素关键词管理器"""

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
        self._keywords: Dict[str, Dict] = {}
        self._file_lock = threading.Lock()
        self.load_keywords()
        _log(f"关键词管理器初始化完成，共{len(self._keywords)}只股票")

    def load_keywords(self) -> Dict[str, Dict]:
        """加载关键词库"""
        with self._file_lock:
            try:
                if os.path.exists(KEYWORDS_PATH):
                    with open(KEYWORDS_PATH, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._keywords = data
                        _log(f"关键词库加载成功，共{len(data)}只股票")
                    else:
                        _log("关键词库格式错误，重置为空", 'WARN')
                        self._keywords = {}
                else:
                    _log("关键词库文件不存在，初始化为空")
                    self._keywords = {}
            except Exception as e:
                _log(f"加载关键词库失败: {e}", 'ERROR')
                self._keywords = {}
        return self._keywords

    def save_keywords(self, data: Dict = None):
        """保存关键词库"""
        if data is not None:
            self._keywords = data
        with self._file_lock:
            try:
                os.makedirs(os.path.dirname(KEYWORDS_PATH), exist_ok=True)
                with open(KEYWORDS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self._keywords, f, ensure_ascii=False, indent=2)
                _log(f"关键词库已保存，共{len(self._keywords)}只股票")
            except Exception as e:
                _log(f"保存关键词库失败: {e}", 'ERROR')

    def get_stock_keywords(self, code: str) -> Optional[Dict]:
        """获取指定股票的关键词配置"""
        return self._keywords.get(code)

    def get_all_keywords(self) -> Dict[str, Dict]:
        """获取全部关键词库"""
        return dict(self._keywords)

    def extract_from_profile(self, profile: Dict, code: str = '', name: str = '') -> Dict:
        """
        从画像中提取关键词
        Args:
            profile: 画像dict（来自StockProfileGenerator）
            code: 股票代码
            name: 股票名称
        Returns:
            关键词配置dict {'name':..., 'keywords':[...], 'core_keywords':[...]}
        """
        if not profile:
            return {}

        # 从meta中获取code/name
        meta = profile.get('_meta', {})
        if not code:
            code = meta.get('code', '')
        if not name:
            name = meta.get('name', '')

        # 收集关键词
        keywords: Set[str] = set()
        core_keywords: Set[str] = set()

        # 1. concept_tags（受益概念标签）
        concept_tags = profile.get('concept_tags', [])
        if isinstance(concept_tags, list):
            for i, tag in enumerate(concept_tags):
                tag_clean = str(tag).strip()
                if tag_clean and len(tag_clean) <= 20:
                    keywords.add(tag_clean)
                    if i < 2:  # 前2个概念标签视为核心
                        core_keywords.add(tag_clean)

        # 2. bullish_keywords（利好触发关键词）
        bullish = profile.get('bullish_keywords', [])
        if isinstance(bullish, list):
            for i, kw in enumerate(bullish):
                kw_clean = str(kw).strip()
                if kw_clean and len(kw_clean) <= 30:
                    keywords.add(kw_clean)
                    if i < CORE_KEYWORD_RANK:  # 前3个利好关键词视为核心
                        core_keywords.add(kw_clean)

        # 3. 从主营产品和产业链中提取简短关键词
        main_products = str(profile.get('main_products', ''))
        industry_chain = str(profile.get('industry_chain', ''))
        # 简单提取：按逗号、顿号、分号、括号分割，提取产品名
        import re as _re
        for part in _re.split(r'[，,、；;（）()]', main_products):
            part = part.strip()
            # 过滤：长度2-12，不以"等/。/领域"结尾，不包含"公司/主要/从事/生产/销售/覆盖/下游"等通用词
            if (2 <= len(part) <= 12
                    and not part.endswith(('等', '。', '领域', '方面'))
                    and not any(w in part for w in ['公司', '主要', '从事', '生产', '销售', '覆盖', '下游', '客户', '提供'])):
                keywords.add(part)

        # 确保核心关键词是普通关键词的子集
        core_keywords = core_keywords.intersection(keywords)

        result = {
            'name': name,
            'keywords': sorted(list(keywords)),
            'core_keywords': sorted(list(core_keywords)),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        if code:
            self._keywords[code] = result
            self.save_keywords()
            _log(f"从画像提取关键词: {name}({code}) 普通{len(result['keywords'])}个 核心{len(result['core_keywords'])}个")

        return result

    def add_keywords(self, code: str, keywords: List[str], name: str = '',
                     is_core: bool = False):
        """
        手动补充关键词
        Args:
            code: 股票代码
            keywords: 关键词列表
            name: 股票名称（首次添加时需要）
            is_core: 是否作为核心关键词
        """
        if not code or not keywords:
            return

        if code not in self._keywords:
            self._keywords[code] = {
                'name': name,
                'keywords': [],
                'core_keywords': [],
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

        existing = set(self._keywords[code].get('keywords', []))
        for kw in keywords:
            kw_clean = str(kw).strip()
            if kw_clean:
                existing.add(kw_clean)

        self._keywords[code]['keywords'] = sorted(list(existing))

        if is_core:
            existing_core = set(self._keywords[code].get('core_keywords', []))
            for kw in keywords:
                kw_clean = str(kw).strip()
                if kw_clean:
                    existing_core.add(kw_clean)
            self._keywords[code]['core_keywords'] = sorted(list(existing_core))

        if name:
            self._keywords[code]['name'] = name
        self._keywords[code]['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.save_keywords()
        _log(f"手动补充关键词: {code} +{len(keywords)}个 (core={is_core})")

    def remove_keywords(self, code: str, keywords: List[str]):
        """移除关键词"""
        if code not in self._keywords:
            return
        remove_set = set(str(k).strip() for k in keywords)
        self._keywords[code]['keywords'] = [
            k for k in self._keywords[code].get('keywords', []) if k not in remove_set
        ]
        self._keywords[code]['core_keywords'] = [
            k for k in self._keywords[code].get('core_keywords', []) if k not in remove_set
        ]
        self.save_keywords()

    def match_news(self, news_text: str) -> List[Dict]:
        """
        匹配新闻文本，返回命中的股票和关键词
        Args:
            news_text: 新闻标题+正文文本
        Returns:
            [{'code':..., 'name':..., 'matched_keywords':[...], 'matched_core':[...], 'score':...}, ...]
        """
        if not news_text or not self._keywords:
            return []

        text_lower = news_text.lower()
        results = []

        for code, kw_data in self._keywords.items():
            name = kw_data.get('name', '')
            all_keywords = kw_data.get('keywords', [])
            core_keywords = set(kw_data.get('core_keywords', []))

            matched = []
            matched_core = []

            for kw in all_keywords:
                if not kw:
                    continue
                # 中文关键词<4字跳过（"机器人/太阳能/农产品"等行业泛词误命中）；英文缩写(HDU/PCB)保留
                has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in kw)
                if has_cjk and len(kw) < 4:
                    continue
                # 关键词匹配：小写不敏感
                if kw.lower() in text_lower:
                    matched.append(kw)
                    if kw in core_keywords:
                        matched_core.append(kw)

            if matched:
                # 匹配度评分：核心关键词权重2，普通关键词权重1
                score = len(matched_core) * 2 + (len(matched) - len(matched_core)) * 1
                results.append({
                    'code': code,
                    'name': name,
                    'matched_keywords': matched,
                    'matched_core': matched_core,
                    'score': score,
                })

        # 按匹配度降序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    def get_stats(self) -> Dict:
        """获取关键词库统计"""
        total_stocks = len(self._keywords)
        total_keywords = sum(len(v.get('keywords', [])) for v in self._keywords.values())
        total_core = sum(len(v.get('core_keywords', [])) for v in self._keywords.values())
        return {
            'total_stocks': total_stocks,
            'total_keywords': total_keywords,
            'total_core_keywords': total_core,
        }


# 全局单例
_keyword_manager: Optional[KeywordManager] = None


def get_keyword_manager() -> KeywordManager:
    """获取关键词管理器单例"""
    global _keyword_manager
    if _keyword_manager is None:
        _keyword_manager = KeywordManager()
    return _keyword_manager


if __name__ == '__main__':
    print("=" * 60)
    print("测试关键词管理器")
    print("=" * 60)
    mgr = get_keyword_manager()

    # 测试：手动添加关键词
    mgr.add_keywords('002579', ['PCB', 'HDI', '汽车电子'], name='中京电子', is_core=True)
    mgr.add_keywords('002579', ['5G', '覆铜板', 'AI服务器', 'IC载板'], name='中京电子')

    # 测试新闻匹配
    test_news = "PCB行业景气度回升，HDI板需求旺盛，中京电子受益汽车电子和AI服务器产业链"
    matches = mgr.match_news(test_news)
    print(f"\n新闻匹配结果: {len(matches)}只股票命中")
    for m in matches:
        print(f"  {m['name']}({m['code']}): 匹配{m['matched_keywords']} 核心{m['matched_core']} 评分{m['score']}")

    print(f"\n统计: {mgr.get_stats()}")
