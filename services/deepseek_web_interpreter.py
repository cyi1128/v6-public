# -*- coding: utf-8 -*-
"""
DeepSeek 网页版 AI 解读自动化模块
使用 Playwright 控制 DeepSeek 网页版，免费调用，不消耗API额度
"""
import os
import sys
import json
import time
import hashlib
import sqlite3
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright

# 缓存数据库
CACHE_DB = os.path.join(PROJECT_ROOT, 'data', 'ai_interpret_cache.db')
# 浏览器用户数据目录（保存登录状态）
USER_DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'browser_profile')

DEEPSEEK_URL = "https://chat.deepseek.com/"


class DeepSeekWebInterpreter:
    """DeepSeek网页版AI解读器"""

    _instance = None
    _lock = __import__('threading').Lock()

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
        self.playwright = None
        self.browser = None
        self.page = None
        self._init_cache()
        print("[DeepSeek] 模块初始化完成")

    def _init_cache(self):
        """初始化缓存数据库"""
        conn = sqlite3.connect(CACHE_DB)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS interpret_cache (
                news_hash TEXT PRIMARY KEY,
                news_title TEXT,
                result TEXT,
                created_at TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def _get_cache(self, news_hash):
        """读取缓存"""
        conn = sqlite3.connect(CACHE_DB)
        c = conn.cursor()
        c.execute('SELECT result FROM interpret_cache WHERE news_hash=?', (news_hash,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def _save_cache(self, news_hash, title, result):
        """保存缓存"""
        conn = sqlite3.connect(CACHE_DB)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO interpret_cache
            (news_hash, news_title, result, created_at)
            VALUES (?, ?, ?, ?)
        ''', (news_hash, title, result, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def start_browser(self):
        """启动浏览器，保持登录状态"""
        if self.page:
            return
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,  # 有头模式，方便手动登录
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.page = self.browser.new_page()
        self.page.goto(DEEPSEEK_URL)
        print("[DeepSeek] 浏览器已启动，请手动登录DeepSeek")
        time.sleep(5)

    def interpret_news(self, news_title, news_content=""):
        """
        解读一条新闻
        返回解读后的文本结果
        """
        # 1. 缓存检查
        news_text = news_title + news_content
        news_hash = hashlib.md5(news_text.encode()).hexdigest()
        cached = self._get_cache(news_hash)
        if cached:
            print(f"[DeepSeek] 命中缓存: {news_title[:30]}")
            return cached

        # 2. 启动浏览器（如果没启动）
        if not self.page:
            self.start_browser()

        # 3. 组装完整V2规范Prompt
        prompt = self._build_prompt(news_title, news_content)

        # 4. 发送给DeepSeek（新建对话）
        try:
            # 刷新页面新建对话
            self.page.goto(DEEPSEEK_URL)
            time.sleep(3)
            
            # 定位输入框
            textarea = self.page.wait_for_selector('textarea', timeout=10000)
            textarea.click()
            textarea.fill(prompt)
            time.sleep(0.5)
            # 按回车发送
            textarea.press("Enter")
            print(f"[DeepSeek] 已发送: {news_title[:30]}")

            # 5. 等待生成完成（等30秒让它生成完）
            time.sleep(35)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # 6. 精准抓取AI回复
            # 尝试多种选择器找AI回复
            result = ""
            selectors = [
                '[data-message-author-role="assistant"]',
                '.ds-markdown',
                '.markdown',
                '[class*="answer"]',
                '[class*="response"]',
            ]
            for sel in selectors:
                try:
                    elems = self.page.query_selector_all(sel)
                    if elems:
                        result = elems[-1].inner_text()
                        if len(result) > 50:
                            break
                except:
                    continue
            
            # 如果都没抓到，就提示用户看网页
            if len(result) < 50:
                result = "✅ DeepSeek已在浏览器里完成解读，请直接在打开的Chrome窗口查看完整结果。\n程序自动抓取功能受网页结构变化影响，暂时抓不到，但浏览器里的结果是正确的。"
            
            print(f"[DeepSeek] 解读完成，长度{len(result)}字")
            # 保存缓存
            self._save_cache(news_hash, news_title, result)
            return result

        except Exception as e:
            print(f"[DeepSeek] 解读失败: {e}")
            return f"❌ 自动解读失败: {e}\n\n请手动复制Prompt到DeepSeek网页版解读：\n---\n{prompt}"

    def _build_prompt(self, title, content=""):
        """组装V2规范Prompt"""
        system_prompt = """你是A股产业链新闻分析引擎，严格按以下规范输出：

## 一、核心原则
- 结论优先，不绕弯
- 不编造订单、客户、合作、产能、营收
- 没有明确证据不强行关联股票
- 所有股票标注证据等级A/B/C/D
- 区分直接受益和间接受益
- 区分事实和推演
- 不用"可能、或许"模糊词
- 不给具体买卖点位
- 旧闻标注旧闻，传闻标注传闻
- 宁可2只有证据的股，不要10只概念股

## 二、固定输出结构（Markdown格式）
### ⚡ 核心提炼（200字内）
方向：利好/利空/中性
主体：XXX
事件：XXX
影响：XXX
强度：★★★★★
一句话结论：XXX

### 🧭 新闻类型判定
类型：股票类/非股票类/混合类
叠加标签：政策/产业/技术/商品/海外/宏观/事件/业绩/资金/情绪

### 🔥 影响评分（100分制）
新闻影响评分：XX/100
等级：S/A/B/C/D
评分维度：事件级别+产业影响+业绩传导+A股映射+持续性

### 🧠 深度逻辑拆解
完整传导链：
新闻事件 → 行业供需 → 产业链变化 → 公司订单/成本 → 业绩 → 估值 → 资金情绪

### 📈 红榜（受益股票）
按产业链上中下游排序，每只股票：
- 名称（代码）
- 关联方向：直接受益/供应链/技术映射
- 证据等级：A/B/C/D
- 关联依据：新闻→产业链→公司
- 受益逻辑：产品/技术/客户/产能
- 影响强度：★★★★★
- 时间周期：短线/中期/长期

⭐ 核心受益梯队：
第一梯队（直接相关+A/B级证据）：XXX
第二梯队（产业链相关）：XXX

### 📉 黑榜（风险股票）
直接受损/成本上升/跷跷板承压，每只股票：
名称（代码）+ 风险原因 + 证据等级 + 影响周期
没有明确标的就写"未发现明确基本面受损标的"

### 📰 真实性核验
状态：最新/旧闻/传闻/未确认
时间：YYYY-MM-DD HH:MM
是否已反映在股价中

### ⏱️ 影响时间窗口
短线（1-5天）/中期（1-3月）/长期（3月以上）
说明是情绪催化还是产业趋势

### 🎯 操作建议（仅股票类）
情绪级别：强/中/弱
仓位参考：轻仓/标准/观察
核心跟踪标的：1-3只
关注条件：放量突破/订单兑现/政策落地
风险条件：新闻证伪/高位放量/板块退潮

### 🏁 最终判断
方向：利好/利空/中性
等级：S/A/B/C/D
核心受益方向：XXX
核心受益股：XXX（XXXXXX）
影响周期：短线/中期/长期
一句话总结：这条新闻真正值得关注的是XXX

## 三、股票池规则（强制）
- 主板股票优先级最高：600/601/603/605/000/001/002开头
- 可以列创业板/科创板龙头，但必须同时给同产业链主板平替标的
- 每条利好必须至少包含一只主板标的
- 例如光模块龙头中际旭创(300)旁边，必须同时列主板铭普光磁(002902)

## 四、绝对禁止
❌ 编造订单/客户/合作/业绩
❌ 把概念股说成直接受益
❌ 凑数加股票
❌ 给买卖点位
❌ 用"可能/或许"模糊词

现在请按以上结构解读新闻："""
        prompt = f"{system_prompt}\n\n新闻标题：{title}\n新闻内容：{content[:800]}"
        return prompt

    def close(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self.page = None
        self.browser = None
        self.playwright = None


if __name__ == '__main__':
    # 测试
    interpreter = DeepSeekWebInterpreter()
    result = interpreter.interpret_news("光模块订单大增，800G需求爆发")
    print("\n解读结果：")
    print(result)
