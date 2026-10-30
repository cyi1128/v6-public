# -*- coding: utf-8 -*-
"""
利好股票新闻 → AI解读 → 企业微信自动推送
==========================================
新闻刷新引擎拉到新新闻后调用：
- 后台线程调 news_ai_interpreter.interpret_news 生成完整六模块解读
- 仅当 情绪分>0.1 且 相关度>=50（股票类利好）才推送
- 推送内容 = AI解读markdown全文（与弹窗一致）
- 去重：同一新闻ID不重复推送
"""
import time
import hashlib
import threading
from typing import Dict, Set

_pushed_ids: Set[str] = set()
_lock = threading.Lock()


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] [AI推送] {msg}", flush=True)


def push_ai_analysis_if_bullish(news: Dict) -> None:
    """对单条新闻：AI解读 → 利好股票类 → 推企业微信。后台线程调用。"""
    try:
        # 大模型模式不自动推送（省算力），仅本地AI模式推送
        from services.news_ai_interpreter import LOCAL_LLM_ENABLED
        if not LOCAL_LLM_ENABLED:
            return
        title = str(news.get('title', '') or '').strip()
        if not title:
            return
        news_id = news.get('id') or news.get('news_id') or hashlib.md5(title.encode('utf-8')).hexdigest()[:12]
        with _lock:
            if news_id in _pushed_ids:
                return
            _pushed_ids.add(news_id)

        from services.news_ai_interpreter import interpret_news
        analysis = interpret_news(news)
        if not analysis or analysis.get('mode') != 'ai':
            return

        quant = analysis.get('quant') or {}
        try:
            score = float(quant.get('sentiment_score', 0) or 0)
        except Exception:
            score = 0.0
        try:
            rel = float(quant.get('relevance_score', 0) or 0)
        except Exception:
            rel = 0.0

        # 利好股票类判定：情绪分>0.1 且 相关度>=50
        if score <= 0.1 or rel < 50:
            _log(f"非利好股票类，不推送(score={score},rel={rel}): {title[:40]}")
            return

        text = analysis.get('text', '') or ''
        if not text.strip():
            return

        # 质量过滤1：汇总/盘点类新闻不推（一周牛股、月度回顾等无个股指向）
        summary_words = ['一周', '牛股', '盘点', '总结', '回顾', '本周', '月度', '今日股市', '收评', '午评', '早知道']
        if any(w in title for w in summary_words):
            _log(f"汇总类新闻，不推: {title[:40]}")
            return

        # 质量过滤2：解读太水（红榜无实质标的）不推
        no_signal = ['无明显直接受益', '无直接受益', '无相关', '无明确避险', '无直接传导', '无明显纯概念', '无明显连带']
        no_count = sum(1 for w in no_signal if w in text)
        if no_count >= 3:
            _log(f"解读太水(空泛{no_count}处)，不推: {title[:40]}")
            return

        src = str(news.get('source', '') or '')
        ptime = str(news.get('publish_time', '') or '')[:19]

        # 剥离量化标签JSON代码块（用户要求推送里不显示）
        import re as _re
        text = _re.sub(r'```json\s*[\s\S]*?```', '', text).strip()
        text = _re.sub(r'🏷️\s*量化标签.*$', '', text, flags=_re.MULTILINE).strip()

        content = (
            f"# 📈 AI投研简报 · 利好\n\n"
            f"**新闻：**{title}\n"
            f"**来源：**{src}　**时间：**{ptime}\n\n"
            f"{text}\n\n"
            f"---\n*自动推送 · AI量化投研简报 · 仅供参考*"
        )

        from services.wechat_push import get_wechat_push_service
        service = get_wechat_push_service()
        if not service.is_configured():
            _log("企业微信webhook未配置，跳过推送")
            return
        # V3.0 推送链路验收：AI利好新闻推送统一走 wechat_bus
        from services.wechat_bus import get_wechat_bus
        ok = get_wechat_bus()._post("📰【事件驱动】", content)
        if ok:
            _log(f"利好新闻已推送企业微信: {title[:40]}")
        else:
            _log(f"推送发送失败: {title[:40]}")
    except Exception as e:
        _log(f"异常: {e}")


def push_async(news: Dict) -> None:
    """异步触发（daemon线程，不阻塞新闻刷新）"""
    threading.Thread(
        target=push_ai_analysis_if_bullish, args=(news,), daemon=True
    ).start()
