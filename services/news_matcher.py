# -*- coding: utf-8 -*-
"""
盘中新闻利好匹配推送器
- 7×24实时新闻流每条新闻自动扫描关键词库
- 命中时判断利好/利空（结合新闻标题情感），匹配度打分
- 匹配度>=阈值时，企业微信推送
- 去重：同一只股票同一新闻只推一次，5分钟内同一股票最多推1次
"""
import os
import sys
import json
import time
import threading
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.keyword_manager import get_keyword_manager
from services.stock_profile_generator import get_profile_generator

# 推送历史路径
PUSH_HISTORY_PATH = os.path.join(PROJECT_ROOT, 'data', 'cache', 'news_push_history.json')

# 匹配阈值：命中2个普通关键词 或 1个核心关键词
MATCH_THRESHOLD_NORMAL = 2
MATCH_THRESHOLD_CORE = 1

# 去重窗口：5分钟内同一股票最多推1次
DEDUP_WINDOW_SECONDS = 300

# 利空关键词（标题包含则不推送或标记利空）
BEARISH_KEYWORDS = [
    '下跌', '跌停', '亏损', '减持', '处罚', '立案', '调查', '退市',
    '风险', '警示', '下滑', '暴跌', '崩盘', '违约', '债务', '诉讼',
    '造假', '欺诈', '违规', '停牌', '利空', '暴雷', '踩雷', '计提',
    '商誉减值', '业绩变脸', '预亏', '扭盈为亏', '下修', '下调评级',
]

# 利好关键词（标题包含则增强利好判断）
BULLISH_KEYWORDS = [
    '上涨', '涨停', '盈利', '增持', '回购', '中标', '签约', '订单',
    '突破', '量产', '投产', '涨价', '扩产', '业绩预增', '扭亏',
    '利好', '超预期', '新高', '增长', '获批', '通过', '合作',
]


def _log(msg: str, level: str = 'INFO'):
    """日志输出"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] [NewsMatcher] [{level}] {msg}", flush=True)


class NewsMatcher:
    """盘中新闻利好匹配推送器"""

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
        self._keyword_mgr = get_keyword_manager()
        self._profile_gen = get_profile_generator()
        self._push_history: Dict[str, List[Dict]] = {}  # {code: [{news_id, time, ...}]}
        self._pushed_news_ids: Set[str] = set()  # 已推送的新闻ID（股票+新闻组合）
        self._history_lock = threading.Lock()
        self._load_push_history()
        _log(f"新闻匹配器初始化完成，关键词库{self._keyword_mgr.get_stats()}")

    def _load_push_history(self):
        """加载推送历史"""
        try:
            if os.path.exists(PUSH_HISTORY_PATH):
                with open(PUSH_HISTORY_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._push_history = data.get('stock_history', {})
                self._pushed_news_ids = set(data.get('news_ids', []))
                _log(f"推送历史加载成功: {len(self._push_history)}只股票, {len(self._pushed_news_ids)}条记录")
        except Exception as e:
            _log(f"加载推送历史失败: {e}", 'WARN')
            self._push_history = {}
            self._pushed_news_ids = set()

    def _save_push_history(self):
        """保存推送历史"""
        try:
            os.makedirs(os.path.dirname(PUSH_HISTORY_PATH), exist_ok=True)
            # 只保留最近的记录（每只股票最多20条）
            trimmed = {}
            for code, records in self._push_history.items():
                trimmed[code] = records[-20:]
            # news_ids只保留最近500个
            news_ids_list = list(self._pushed_news_ids)[-500:]
            data = {
                'stock_history': trimmed,
                'news_ids': news_ids_list,
                'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            with open(PUSH_HISTORY_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log(f"保存推送历史失败: {e}", 'WARN')

    def _calc_score(self, news_text: str, stock_keywords: Dict) -> Dict:
        """
        计算匹配度
        Returns:
            {'score': int, 'matched': [...], 'matched_core': [...], 'should_push': bool}
        """
        if not news_text or not stock_keywords:
            return {'score': 0, 'matched': [], 'matched_core': [], 'should_push': False}

        text_lower = news_text.lower()
        all_keywords = stock_keywords.get('keywords', [])
        core_keywords = set(stock_keywords.get('core_keywords', []))

        matched = []
        matched_core = []

        for kw in all_keywords:
            if not kw:
                continue
            if kw.lower() in text_lower:
                matched.append(kw)
                if kw in core_keywords:
                    matched_core.append(kw)

        # 评分：核心关键词权重2，普通权重1
        score = len(matched_core) * 2 + (len(matched) - len(matched_core)) * 1

        # 判断是否达到推送阈值
        should_push = (len(matched) >= MATCH_THRESHOLD_NORMAL or
                       len(matched_core) >= MATCH_THRESHOLD_CORE)

        return {
            'score': score,
            'matched': matched,
            'matched_core': matched_core,
            'should_push': should_push,
        }

    def _judge_sentiment(self, title: str) -> str:
        """
        判断新闻标题情感
        Returns: 'bullish' / 'bearish' / 'neutral'
        """
        if not title:
            return 'neutral'

        title_lower = title.lower()

        # 检查利空关键词
        for kw in BEARISH_KEYWORDS:
            if kw in title_lower:
                return 'bearish'

        # 检查利好关键词
        for kw in BULLISH_KEYWORDS:
            if kw in title_lower:
                return 'bullish'

        return 'neutral'

    def _should_push(self, stock_code: str, news_id: str) -> Dict:
        """
        去重判断
        Returns: {'should': bool, 'reason': str}
        """
        # 1. 同一股票同一新闻只推一次
        combo_id = f"{stock_code}_{news_id}"
        if combo_id in self._pushed_news_ids:
            return {'should': False, 'reason': '该股票该新闻已推送过'}

        # 2. 5分钟内同一股票最多推1次
        now = datetime.now()
        with self._history_lock:
            records = self._push_history.get(stock_code, [])
            if records:
                last_record = records[-1]
                try:
                    last_time = datetime.strptime(last_record.get('time', ''), '%Y-%m-%d %H:%M:%S')
                    if (now - last_time).total_seconds() < DEDUP_WINDOW_SECONDS:
                        remaining = DEDUP_WINDOW_SECONDS - (now - last_time).total_seconds()
                        return {'should': False, 'reason': f'5分钟去重窗口内，剩余{remaining:.0f}秒'}
                except Exception:
                    pass

        return {'should': True, 'reason': ''}

    def _record_push(self, stock_code: str, news_id: str, news_title: str):
        """记录推送历史"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self._history_lock:
            if stock_code not in self._push_history:
                self._push_history[stock_code] = []
            self._push_history[stock_code].append({
                'news_id': news_id,
                'title': news_title,
                'time': now_str,
            })
            self._pushed_news_ids.add(f"{stock_code}_{news_id}")
        # 异步保存（避免阻塞）
        threading.Thread(target=self._save_push_history, daemon=True).start()

    def _get_realtime_quote(self, code: str) -> Dict:
        """获取股票实时行情（价格、涨跌幅）"""
        try:
            import requests
            if code.startswith('6'):
                qt_code = f'sh{code}'
            else:
                qt_code = f'sz{code}'
            url = f'https://qt.gtimg.cn/q={qt_code}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=3)
            resp.encoding = 'gbk'
            if '=' in resp.text:
                data = resp.text.split('"')[1].split('~')
                if len(data) > 45:
                    price = float(data[3]) if data[3] else 0
                    pct_chg = float(data[32]) if data[32] else 0
                    name = data[1] if len(data) > 1 else ''
                    return {'price': price, 'pct_chg': pct_chg, 'name': name}
        except Exception as e:
            _log(f"获取实时行情失败 {code}: {e}", 'WARN')
        return {}

    def _build_push_message(self, news: Dict, match_result: Dict, stock_code: str,
                            stock_name: str) -> str:
        """构建推送消息"""
        title = news.get('title', '无标题')
        publish_time = news.get('publish_time', news.get('time', ''))
        matched_keywords = match_result.get('matched', [])
        matched_core = match_result.get('matched_core', [])

        # 获取实时行情
        quote = self._get_realtime_quote(stock_code)
        price = quote.get('price', 0)
        pct_chg = quote.get('pct_chg', 0)
        if quote.get('name'):
            stock_name = quote['name']

        # 从画像提取利好逻辑
        bullish_logic = ''
        try:
            profile = self._profile_gen.get_profile(stock_code)
            if profile:
                main_products = profile.get('main_products', '')
                industry_chain = profile.get('industry_chain', '')
                if main_products or industry_chain:
                    parts = []
                    if main_products:
                        parts.append(f"主营: {main_products[:60]}")
                    if industry_chain:
                        parts.append(f"产业链: {industry_chain[:40]}")
                    bullish_logic = ' | '.join(parts)
        except Exception:
            pass

        # 构建消息
        pct_sign = '+' if pct_chg >= 0 else ''
        kw_display = '、'.join(matched_keywords[:6])
        core_display = '、'.join(matched_core) if matched_core else '无'

        content = f"📰 **利好新闻匹配**\n\n"
        content += f"**股票：{stock_name}({stock_code})** "
        if price > 0:
            content += f"{price:.2f} ({pct_sign}{pct_chg:.2f}%)\n"
        else:
            content += "\n"
        content += f"**新闻：**{title}\n"
        if publish_time:
            content += f"**时间：**{publish_time}\n"
        content += f"**命中关键词：**{kw_display}\n"
        content += f"**核心关键词：**{core_display}\n"
        if bullish_logic:
            content += f"**利好逻辑：**{bullish_logic}\n"
        content += f"\n*匹配度: {match_result.get('score', 0)}分 | 新闻匹配推送*"

        return content

    def _send_wechat(self, content: str) -> bool:
        """发送企业微信消息（复用现有推送服务）"""
        try:
            from services.wechat_push import get_wechat_push_service
            service = get_wechat_push_service()
            if not service.is_configured():
                _log("企业微信webhook未配置，记录推送内容但不实际发送", 'WARN')
                _log(f"推送内容预览:\n{content[:500]}")
                return False
            # V3.0 推送链路验收：新闻匹配推送统一走 wechat_bus
            from services.wechat_bus import get_wechat_bus
            return get_wechat_bus()._post("📰【事件驱动】", content)
        except Exception as e:
            _log(f"企业微信推送异常: {e}\n{traceback.format_exc()}", 'ERROR')
            return False

    def match_news(self, news: Dict) -> List[Dict]:
        """
        匹配单条新闻，返回匹配结果列表
        Args:
            news: 新闻dict，需包含 title, content/summary, publish_time, id/news_id
        Returns:
            匹配结果列表，每项包含股票代码、名称、匹配详情、是否推送等
        """
        if not news:
            return []

        news_id = news.get('id', news.get('news_id', ''))
        if not news_id:
            # 无ID时用标题哈希
            import hashlib
            news_id = hashlib.md5(news.get('title', '').encode('utf-8')).hexdigest()[:12]

        title = news.get('title', '')
        content = news.get('content', news.get('summary', ''))
        full_text = f"{title} {content}"

        if not full_text.strip():
            return []

        # 情感判断
        sentiment = self._judge_sentiment(title)

        # 中性新闻过滤：机构调研/媒体关注类，默认不推
        neutral_words = ['机构调研', '机构关注', '176家机构', '盯上', '接待', '投资者关系', '调研', '交流', '走访', '调研活动', '评级', '研报']
        if sentiment != 'bearish' and any(w in title for w in neutral_words):
            _log(f"中性新闻(机构/媒体关注)，不推: {title[:50]}")
            return []

        if sentiment == 'bearish':
            _log(f"新闻标记为利空，继续推送: {title[:50]}")
            # 利空也推（不再跳过）

        # 关键词匹配
        all_matches = self._keyword_mgr.match_news(full_text)
        if not all_matches:
            return []

        results = []
        for match in all_matches:
            code = match['code']
            name = match['name']
            stock_kw = self._keyword_mgr.get_stock_keywords(code)

            # 计算匹配度和推送阈值
            score_result = self._calc_score(full_text, stock_kw or {})
            if not score_result['should_push']:
                continue

            # 去重判断
            dedup = self._should_push(code, news_id)
            pushed = False
            push_reason = dedup['reason']

            if dedup['should']:
                # AI判断：只推强利好/强利空，中性新闻不推
                ai_ok = False
                try:
                    from services.news_ai_interpreter import interpret_news
                    analysis = interpret_news(news)
                    if analysis and analysis.get('mode') == 'ai':
                        quant = analysis.get('quant') or {}
                        s_score = float(quant.get('sentiment_score', 0) or 0)
                        # 强利好>0.3 或 强利空<-0.3 才推
                        if s_score > 0.3 or s_score < -0.3:
                            ai_ok = True
                            _log(f"AI判定推送: {name}({code}) sentiment={s_score}")
                        else:
                            _log(f"AI判定中性不推: {name}({code}) sentiment={s_score}")
                except Exception as _ae:
                    _log(f"AI判断失败，默认推: {_ae}")
                    ai_ok = True  # AI失败时默认推

                if ai_ok:
                    # 构建并发送推送
                    try:
                        push_content = self._build_push_message(news, score_result, code, name)
                        pushed = self._send_wechat(push_content)
                        if pushed:
                            self._record_push(code, news_id, title)
                            _log(f"推送成功: {name}({code}) 匹配{score_result['matched']}")
                        else:
                            push_reason = '推送发送失败或webhook未配置'
                    except Exception as e:
                        push_reason = f'推送异常: {e}'
                        _log(f"推送异常 {name}({code}): {e}", 'ERROR')
                else:
                    push_reason = 'AI判定中性不推'

            results.append({
                'code': code,
                'name': name,
                'matched_keywords': score_result['matched'],
                'matched_core': score_result['matched_core'],
                'score': score_result['score'],
                'sentiment': sentiment,
                'pushed': pushed,
                'push_reason': push_reason,
            })

        return results

    def match_news_batch(self, news_list: List[Dict]) -> List[Dict]:
        """批量匹配新闻"""
        all_results = []
        if not news_list:
            return all_results
        for news in news_list:
            try:
                results = self.match_news(news)
                all_results.extend(results)
            except Exception as e:
                _log(f"批量匹配单条异常: {e}", 'ERROR')
        return all_results

    def get_push_history(self, code: str = None, limit: int = 20) -> List[Dict]:
        """获取推送历史"""
        with self._history_lock:
            if code:
                return self._push_history.get(code, [])[-limit:]
            all_records = []
            for c, records in self._push_history.items():
                for r in records:
                    r['code'] = c
                    all_records.append(r)
            all_records.sort(key=lambda x: x.get('time', ''), reverse=True)
            return all_records[:limit]

    def get_stats(self) -> Dict:
        """获取匹配器统计"""
        with self._history_lock:
            total_pushes = sum(len(v) for v in self._push_history.values())
            return {
                'total_stocks_tracked': len(self._push_history),
                'total_pushes': total_pushes,
                'total_news_combinations': len(self._pushed_news_ids),
                'keyword_stats': self._keyword_mgr.get_stats(),
            }


# 全局单例
_news_matcher: Optional[NewsMatcher] = None


def get_news_matcher() -> NewsMatcher:
    """获取新闻匹配器单例"""
    global _news_matcher
    if _news_matcher is None:
        _news_matcher = NewsMatcher()
    return _news_matcher


if __name__ == '__main__':
    print("=" * 60)
    print("测试新闻匹配推送器")
    print("=" * 60)

    # 先准备关键词
    kw_mgr = get_keyword_manager()
    kw_mgr.add_keywords('002579', ['PCB', 'HDI'], name='中京电子', is_core=True)
    kw_mgr.add_keywords('002579', ['汽车电子', '5G', '覆铜板', 'AI服务器', 'IC载板'], name='中京电子')

    matcher = get_news_matcher()

    # 测试1：利好新闻
    test_news_1 = {
        'id': 'test_001',
        'title': 'PCB行业景气度持续回升，HDI板需求旺盛，AI服务器产业链受益',
        'content': '据行业调研，PCB厂商订单饱满，HDI板产能利用率提升，汽车电子和AI服务器需求拉动明显。中京电子等国内厂商有望受益。',
        'publish_time': '2026-09-11 10:30:00',
    }
    print("\n--- 测试1：利好新闻匹配 ---")
    results = matcher.match_news(test_news_1)
    for r in results:
        print(f"  {r['name']}({r['code']}): 匹配{r['matched_keywords']} 核心{r['matched_core']} "
              f"评分{r['score']} 情感{r['sentiment']} 推送{'成功' if r['pushed'] else '失败:' + r['push_reason']}")

    # 测试2：利空新闻（应跳过）
    test_news_2 = {
        'id': 'test_002',
        'title': '某PCB厂商业绩亏损，股价下跌',
        'content': '...',
        'publish_time': '2026-09-11 10:35:00',
    }
    print("\n--- 测试2：利空新闻（应跳过） ---")
    results2 = matcher.match_news(test_news_2)
    print(f"  匹配结果数: {len(results2)}（应为0）")

    # 测试3：去重（同一股票5分钟内不应重复推送）
    print("\n--- 测试3：去重测试 ---")
    results3 = matcher.match_news(test_news_1)
    for r in results3:
        print(f"  {r['name']}({r['code']}): 推送{'成功' if r['pushed'] else '失败:' + r['push_reason']}")

    print(f"\n统计: {matcher.get_stats()}")
