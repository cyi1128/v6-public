# -*- coding: utf-8 -*-
"""
30分钟AI新闻简报自动推送服务
- 独立后台线程，每30分钟汇总本时段重要新闻
- 调用DeepSeek网页版深度分析
- 重要性≥4星才推企业微信
- 复用现有DeepSeek缓存、去重、企业微信推送通道
- 不阻塞主界面和行情刷新
"""
import os
import sys
import time
import json
import threading
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.deepseek_web_interpreter import DeepSeekWebInterpreter
from services.wechat_push import get_wechat_push_service


class News30MinDigest:
    """30分钟新闻简报服务"""

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
        self.running = False
        self.thread = None
        self._news_buffer = []  # 本时段新闻缓存
        self._pushed_hashes = set()  # 已推送新闻hash
        self._interval = 1800  # 30分钟
        self._load_push_history()
        print("[30分钟简报] 服务初始化完成", flush=True)

    def _load_push_history(self):
        """加载历史推送记录，防止重启重复推"""
        try:
            import sqlite3
            db = os.path.join(PROJECT_ROOT, 'data', 'news_push_records.db')
            if os.path.exists(db):
                conn = sqlite3.connect(db)
                c = conn.cursor()
                c.execute("SELECT news_hash FROM push_records WHERE pushed_at > datetime('now', '-7 days')")
                for row in c.fetchall():
                    self._pushed_hashes.add(row[0])
                conn.close()
                print(f"[30分钟简报] 加载历史推送记录{len(self._pushed_hashes)}条", flush=True)
        except Exception as e:
            print(f"[30分钟简报] 历史记录加载失败: {e}", flush=True)

    def add_news(self, news_list):
        """实时新闻刷新时调用，把新闻放进本时段缓存"""
        for n in news_list:
            # 去重：按标题hash
            title = n.get('title', '')
            if not title:
                continue
            import hashlib
            h = hashlib.md5(title.encode()).hexdigest()
            if h in self._pushed_hashes:
                continue
            # 过滤太短/无意义新闻
            if len(title) < 8:
                continue
            self._news_buffer.append({
                'title': title,
                'content': n.get('content', ''),
                'time': n.get('time', ''),
                'source': n.get('source', ''),
                'hash': h,
            })
            # 最多缓存500条防止内存爆
            if len(self._news_buffer) > 500:
                self._news_buffer = self._news_buffer[-500:]

    def start(self):
        """启动后台定时线程"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("[30分钟简报] 定时线程已启动，每30分钟生成一次", flush=True)

    def stop(self):
        self.running = False

    def _run_loop(self):
        """主循环：交易时间30分钟一次，非交易时间60分钟一次"""
        # 启动后先等30秒就测试跑第一次
        time.sleep(30)
        while self.running:
            try:
                self._generate_and_push()
            except Exception as e:
                print(f"[30分钟简报] 本轮执行失败: {e}", flush=True)
            # 判断当前交易时段决定等待多久
            now = datetime.now()
            h, m = now.hour, now.minute
            weekday = now.weekday()
            # 盘中：9:30-15:00 → 30分钟
            in_session = (weekday < 5) and (
                (h == 9 and m >= 30) or
                (10 <= h <= 11) or
                (h == 13) or
                (h == 14) or
                (h == 15 and m == 0)
            )
            if in_session:
                wait_sec = 1800  # 盘中30分钟
            else:
                wait_sec = 3600  # 开盘前/休市后60分钟
            # 分段等待，方便快速停止
            for _ in range(wait_sec // 10):
                if not self.running:
                    return
                time.sleep(10)

    def _generate_and_push(self):
        """生成简报并推送到企业微信"""
        now = datetime.now()
        # 非交易时段不推（9:00-15:30之外不推）
        h, m = now.hour, now.minute
        weekday = now.weekday()
        if weekday >= 5:
            print("[30分钟简报] 周末不推送", flush=True)
            return
        # 交易日全天都推，不限制具体时段
        h, m = now.hour, now.minute
        if h < 7 or h > 21:
            print(f"[30分钟简报] 深夜时段({h}:{m})，跳过", flush=True)
            return

        if len(self._news_buffer) < 2:
            print(f"[30分钟简报] 本时段仅{len(self._news_buffer)}条新闻，不够重要新闻阈值，跳过", flush=True)
            self._news_buffer = []
            return

        print(f"[30分钟简报] 开始汇总本时段{len(self._news_buffer)}条新闻...", flush=True)

        # 组装新闻列表给DeepSeek
        news_list_text = ""
        for i, n in enumerate(self._news_buffer[-50:], 1):  # 最多取最近50条
            news_list_text += f"{i}. {n['title']}\n"
            if n['content']:
                news_list_text += f"   摘要: {n['content'][:100]}\n"

        # 组装Prompt
        prompt = f"""你是A股产业链新闻分析专家。现在请对过去30分钟的以下新闻做筛选和深度分析，只保留重要（4星以上）的事件，按指定格式输出：

【重要股票池规则】
- 可以显示创业板/科创板龙头，但必须**同时给同产业链主板平替标的**
- 主板股票优先级最高：600/601/603/605/000/001/002开头
- 创业板(300/301)、科创板(688/689)龙头如果是新闻直接提到的，可以列，但后面必须跟着主板平替
- 例如新闻说800G光模块订单增，不能只列中际旭创(300)，必须同时列主板铭普光磁(002902)
- 每条利好必须至少包含一只主板标的

要求：
1. 从下面新闻里挑出真正影响A股相关公司/产业链的重要事件，普通资讯/重复新闻/没有投资价值的直接删掉
2. 每个重要事件按格式分析：白话解释、事件类型、事件阶段、影响等级、为什么重要
3. 找出直接利好的A股主板上市公司，必须给股票代码和具体利好逻辑，找不到就写"暂未发现明确标的"，严禁编造
4. 指出哪些是容易误判的纯概念股
5. 总结本时段题材变化
6. 最后给2只最值得关注的主板股票

输出格式严格按以下Markdown：
【AI股票30分钟新闻简报】
时间：{now.strftime('%H:%M')}
🔥【一、本时段重要事件】
① 事件标题
【白话解释】...
【事件类型】订单/合作/技术突破/政策...
【事件阶段】正式订单/量产/技术验证...
【影响等级】★★★★★
【为什么重要】...

🎯【二、对应利好主板股票】
① 股票名(000XXX/600XXX)
★★★★ 直接/间接受益
利好逻辑：...

⚠️【三、容易误判的股票】
...

📊【四、本时段题材变化】
...

🎯【五、最终关注】
第一关注：...

---
本时段新闻列表：
{news_list_text}
"""

        # 调用DeepSeek网页版
        try:
            interpreter = DeepSeekWebInterpreter()
            result = interpreter.interpret_news(f"30分钟简报{now.strftime('%H%M')}", news_list_text)
        except Exception as e:
            print(f"[30分钟简报] DeepSeek调用失败: {e}", flush=True)
            self._news_buffer = []
            return

        if not result or len(result) < 100 or "自动解读失败" in result:
            print(f"[30分钟简报] DeepSeek返回内容太短或失败，跳过推送", flush=True)
            self._news_buffer = []
            return

        # 不再硬检测股票代码，只要有内容就推
        print(f"[30分钟简报] DeepSeek返回{len(result)}字，直接渲染图片推送", flush=True)

        # 推送到企业微信：先渲染成长图再发
        try:
            from services.markdown_to_image import markdown_to_image
            img_path = markdown_to_image(result)
            # base64发图片
            import base64, hashlib, requests
            with open('data/wechat_config.json', 'r', encoding='utf-8') as f:
                import json
                webhook = json.load(f)['webhook_url']
            with open(img_path, 'rb') as f:
                img_data = f.read()
            b64 = base64.b64encode(img_data).decode()
            md5 = hashlib.md5(img_data).hexdigest()
            resp = requests.post(webhook, json={
                "msgtype": "image",
                "image": {"base64": b64, "md5": md5}
            }, timeout=15)
            push_ok = resp.json().get('errcode') == 0
            if push_ok:
                print(f"[30分钟简报] ✅ 图片简报已推送到企业微信，图片大小{len(img_data)}字节", flush=True)
                for n in self._news_buffer:
                    self._pushed_hashes.add(n['hash'])
                self._save_push_record(result)
            else:
                print(f"[30分钟简报] 图片推送失败: {resp.json()}", flush=True)
        except Exception as e:
            print(f"[30分钟简报] 企业微信推送失败: {e}", flush=True)

        # 清空缓存
        self._news_buffer = []

    def _save_push_record(self, content):
        """保存推送记录到数据库"""
        try:
            import sqlite3
            db = os.path.join(PROJECT_ROOT, 'data', 'news_push_records.db')
            conn = sqlite3.connect(db)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS push_records
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          news_hash TEXT, title TEXT, pushed_at TEXT, status TEXT)''')
            import hashlib
            h = hashlib.md5(content.encode()).hexdigest()
            c.execute("INSERT INTO push_records(news_hash, title, pushed_at, status) VALUES(?,?,?,?)",
                      (h, content[:100], datetime.now().isoformat(), 'success'))
            conn.commit()
            conn.close()
        except Exception:
            pass


# 全局单例
_digest_service = None
def get_news_digest_service():
    global _digest_service
    if _digest_service is None:
        _digest_service = News30MinDigest()
    return _digest_service
