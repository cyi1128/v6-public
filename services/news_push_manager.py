# -*- coding: utf-8 -*-
"""
题材新闻精准推送管理器
严格按照用户需求实现：
新闻→题材识别→题材股票映射→相关性评分→行情确认→去重→企业微信推送
"""
import os
import sys
import json
import time
import sqlite3
import hashlib
import threading
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.wechat_push import WechatPusher

# 路径
THEME_DB = os.path.join(PROJECT_ROOT, 'data', 'limit_up_reason.db')
PUSH_RECORD_DB = os.path.join(PROJECT_ROOT, 'data', 'news_push_records.db')

# 配置
MIN_SCORE = 80          # 最低相关分
MAX_STOCKS_PER_NEWS = 5 # 单新闻最多推5只
DEDUP_HOURS = 24        # 24小时去重

# 利好/利空关键词
BULLISH_KW = ['利好', '上涨', '涨停', '突破', '中标', '订单', '量产', '投产', '涨价', '业绩预增', '超预期', '新高', '获批', '合作', '拿下', '通过', '增长']
BEARISH_KW = ['利空', '下跌', '跌停', '减持', '处罚', '立案', '亏损', '暴雷', '风险', '下滑', '下跌', '处罚', '违规']


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[NEWS-PUSH] [{ts}] {msg}", flush=True)


class NewsPushManager:
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
        self.wechat = WechatPusher()
        self._init_record_db()
        self._theme_cache = None
        log("题材新闻推送管理器初始化完成")

    def _init_record_db(self):
        """初始化推送记录数据库"""
        conn = sqlite3.connect(PUSH_RECORD_DB)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS push_records (
                news_id TEXT PRIMARY KEY,
                news_title TEXT,
                news_time TEXT,
                matched_themes TEXT,
                matched_stocks TEXT,
                push_time TEXT,
                push_status TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def _is_pushed(self, news_id):
        """检查是否已推送"""
        conn = sqlite3.connect(PUSH_RECORD_DB)
        c = conn.cursor()
        c.execute('SELECT 1 FROM push_records WHERE news_id=?', (news_id,))
        result = c.fetchone() is not None
        conn.close()
        return result

    def _save_push_record(self, news_id, title, time, themes, stocks, status):
        """保存推送记录"""
        conn = sqlite3.connect(PUSH_RECORD_DB)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO push_records
            (news_id, news_title, news_time, matched_themes, matched_stocks, push_time, push_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (news_id, title, time, json.dumps(themes, ensure_ascii=False),
              json.dumps(stocks, ensure_ascii=False), datetime.now().isoformat(), status))
        conn.commit()
        conn.close()

    def _build_theme_index(self):
        """构建题材→股票映射索引（从涨停数据库）"""
        if self._theme_cache:
            return self._theme_cache
        conn = sqlite3.connect(THEME_DB)
        c = conn.cursor()
        # 读取所有有reason的记录
        c.execute('''
            SELECT code, name, reason FROM limit_up_reasons
            WHERE reason LIKE '%+%'
        ''')
        theme_to_stocks = {}
        stock_themes = {}  # code -> {themes: set, name: str}
        for code, name, reason in c.fetchall():
            themes = [t.strip() for t in reason.split('+') if t.strip()]
            if code not in stock_themes:
                stock_themes[code] = {'name': name, 'themes': set()}
            stock_themes[code]['themes'].update(themes)
            for t in themes:
                if t not in theme_to_stocks:
                    theme_to_stocks[t] = set()
                theme_to_stocks[t].add(code)
        conn.close()
        self._theme_cache = {
            'theme_to_stocks': theme_to_stocks,
            'stock_themes': stock_themes
        }
        log(f"题材索引构建完成: {len(theme_to_stocks)}个题材, {len(stock_themes)}只股票")
        return self._theme_cache

    def extract_themes_from_news(self, title, content=''):
        """从新闻里提取题材，归一化到已有题材库"""
        text = title + ' ' + content
        cache = self._build_theme_index()
        all_themes = list(cache['theme_to_stocks'].keys())
        
        matched = []
        for theme in all_themes:
            if theme in text and len(theme) >= 2:
                matched.append(theme)
        
        # 去重，按长度排序（长的优先）
        matched = sorted(list(set(matched)), key=lambda x: len(x), reverse=True)
        return matched[:10]  # 最多10个题材

    def judge_direction(self, title, content=''):
        """判断利好/利空/中性"""
        text = title + content
        bullish = sum(1 for k in BULLISH_KW if k in text)
        bearish = sum(1 for k in BEARISH_KW if k in text)
        if bullish > bearish:
            return '利好'
        elif bearish > bullish:
            return '利空'
        else:
            return '中性'

    def score_stock_relevance(self, stock_code, themes):
        """给股票和新闻的相关度打分"""
        cache = self._build_theme_index()
        if stock_code not in cache['stock_themes']:
            return 0
        stock_themes = cache['stock_themes'][stock_code]['themes']
        
        score = 0
        matched_count = 0
        for t in themes:
            if t in stock_themes:
                score += 30  # 每个直接匹配的题材30分
                matched_count += 1
        
        # 直接点名股票的话100分
        if matched_count >= 2:
            score = min(100, score + 20)
        
        return score, matched_count

    def get_realtime_quote(self, code):
        """获取实时行情，失败返回None"""
        try:
            # 用akshare获取实时行情
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            row = df[df['代码'] == code]
            if len(row) > 0:
                return {
                    'price': float(row.iloc[0]['最新价']),
                    'pct': float(row.iloc[0]['涨跌幅']),
                }
        except:
            pass
        return None

    def process_news(self, title, content='', news_id=None, news_time=None):
        """
        处理一条新闻：完整流程
        """
        log(f"[NEWS] 新闻: {title}")
        
        # 1. 生成news_id（去重用）
        if not news_id:
            news_id = hashlib.md5(f"{title}{news_time}".encode()).hexdigest()
        
        # 2. 去重
        if self._is_pushed(news_id):
            log(f"  已推送过，跳过")
            return
        
        # 3. 判断方向
        direction = self.judge_direction(title, content)
        log(f"  方向: {direction}")
        if direction != '利好':
            log(f"  非利好，不推送")
            return
        
        # 4. 识别题材
        themes = self.extract_themes_from_news(title, content)
        log(f"  识别题材: {themes}")
        if not themes:
            log(f"  未识别到题材，不推送")
            return
        
        # 5. 题材→股票映射
        cache = self._build_theme_index()
        candidate_stocks = set()
        for t in themes:
            if t in cache['theme_to_stocks']:
                candidate_stocks.update(cache['theme_to_stocks'][t])
        log(f"  候选股票: {len(candidate_stocks)}只")
        
        # 6. 评分排序
        scored = []
        for code in candidate_stocks:
            score, matched_cnt = self.score_stock_relevance(code, themes)
            if score >= MIN_SCORE:
                name = cache['stock_themes'][code]['name']
                scored.append({
                    'code': code,
                    'name': name,
                    'score': score,
                    'matched_themes': [t for t in themes if t in cache['stock_themes'][code]['themes']]
                })
        
        scored = sorted(scored, key=lambda x: x['score'], reverse=True)
        scored = scored[:MAX_STOCKS_PER_NEWS]  # 最多5只
        log(f"  评分后入选: {len(scored)}只")
        
        if not scored:
            log(f"  无符合评分的股票，不推送")
            return
        
        # 7. 实时行情
        for s in scored:
            quote = self.get_realtime_quote(s['code'])
            if quote:
                s['pct'] = quote['pct']
                s['price'] = quote['price']
            else:
                s['pct'] = None
                s['price'] = None
        
        # 8. 格式化推送
        msg = self._format_message(title, themes, scored)
        log(f"  准备推送:\n{msg}")
        
        # 9. 企业微信推送
        if not self.wechat.is_configured():
            log(f"  企业微信未配置，跳过")
            self._save_push_record(news_id, title, news_time, themes, scored, 'skipped_no_wechat')
            return
        
        # V3.0 推送链路验收：新闻事件推送统一走 wechat_bus（保留原格式内容）
        try:
            from services.wechat_bus import get_wechat_bus
            success = get_wechat_bus()._post("📰【事件驱动】", msg)
        except Exception:
            success = False
        if success:
            log(f"  ✅ 推送成功")
            self._save_push_record(news_id, title, news_time, themes, scored, 'success')
        else:
            log(f"  ❌ 推送失败: {result}")
            self._save_push_record(news_id, title, news_time, themes, scored, 'failed')

    def _format_message(self, title, themes, stocks):
        """格式化企业微信消息"""
        now = datetime.now().strftime('%H:%M:%S')
        msg = f"📰【实时题材新闻催化】\n"
        msg += f"⏱ {now}\n"
        msg += f"新闻：{title}\n"
        msg += f"🔥 命中题材：{'｜'.join(themes)}\n"
        msg += f"🎯 精准匹配股票：\n"
        for i, s in enumerate(stocks, 1):
            pct_str = f"{s['pct']:+.2f}%" if s.get('pct') is not None else "未取得"
            matched = '+'.join(s['matched_themes'][:2])
            msg += f"{i}. {s['name']}（{s['code']}）\n"
            msg += f"   涨跌幅：{pct_str}\n"
            msg += f"   相关度：{s['score']}\n"
            msg += f"   匹配：{matched}\n"
        msg += f"📌 新闻催化≠买入信号\n"
        return msg


# 单例
_manager = None
def get_news_push_manager():
    global _manager
    if _manager is None:
        _manager = NewsPushManager()
    return _manager


if __name__ == '__main__':
    # 测试
    mgr = get_news_push_manager()
    # 测试1：题材新闻
    mgr.process_news("800G光模块订单排到明年，空芯光纤完成技术验证")
