# -*- coding: utf-8 -*-
"""
企业微信推送服务 V1.0（V3.0增强）
- 异步发送队列
- 失败重试（指数退避）
- 去重（同股同信号10分钟内不重复）
- 消息分片（按股票卡片分割，不截断单只股票）
- 推送规则：综合评分>=80自动推送
- webhook从.env(WECHAT_WEBHOOK_URL)或data/wechat_config.json读取
"""
import os
import sys
import json
import time
import threading
import queue
from typing import Dict, List, Optional
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class WechatNotifyService:
    """企业微信推送服务（增强版）"""

    MAX_CARD_LENGTH = 2000  # 单条消息安全长度
    DEDUP_WINDOW_SECONDS = 600  # 去重窗口10分钟
    MAX_RETRIES = 3

    def __init__(self):
        self._webhook_url = self._load_webhook()
        self._send_queue = queue.Queue()
        self._dedup_cache = {}  # signal_id -> timestamp
        self._send_history = []
        self._worker_thread = None
        self._running = False
        self._stats = {'sent': 0, 'failed': 0, 'deduped': 0, 'retried': 0}
        # V2.7修复：自动启动后台发送线程，避免push_text等待超时
        self.start()

    def _load_webhook(self) -> str:
        """从.env或配置文件加载webhook"""
        # 1. 环境变量（支持多个变量名）
        for env_key in ['WECHAT_WORK_WEBHOOK', 'WECHAT_WEBHOOK_URL']:
            env_url = os.environ.get(env_key, '')
            if env_url:
                return env_url

        # 2. .env文件
        env_path = os.path.join(PROJECT_ROOT, '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        for key in ['WECHAT_WORK_WEBHOOK=', 'WECHAT_WEBHOOK_URL=']:
                            if line.startswith(key):
                                url = line.split('=', 1)[1].strip().strip('"').strip("'")
                                if url:
                                    return url
            except Exception:
                pass

        # 3. data/wechat_config.json
        config_path = os.path.join(PROJECT_ROOT, 'data', 'wechat_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    url = config.get('webhook_url', '')
                    if url:
                        return url
            except Exception:
                pass

        return ''

    def is_configured(self) -> bool:
        return bool(self._webhook_url)

    def start(self):
        """启动后台发送线程"""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._send_worker, daemon=True)
        self._worker_thread.start()
        print(f"[企业微信] 推送服务已启动 (webhook={'已配置' if self._webhook_url else '未配置'})")

    def stop(self):
        """停止后台发送线程"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _make_signal_id(self, stock_code: str, signal_type: str, grade: str = '') -> str:
        """生成信号去重ID"""
        return f"{stock_code}_{signal_type}_{grade}"

    def _is_duplicate(self, signal_id: str) -> bool:
        """检查是否重复推送"""
        now = time.time()
        if signal_id in self._dedup_cache:
            last_time = self._dedup_cache[signal_id]
            if now - last_time < self.DEDUP_WINDOW_SECONDS:
                return True
        return False

    def _record_dedup(self, signal_id: str):
        self._dedup_cache[signal_id] = time.time()
        # 清理过期缓存
        now = time.time()
        expired = [k for k, v in self._dedup_cache.items() if now - v > self.DEDUP_WINDOW_SECONDS * 2]
        for k in expired:
            del self._dedup_cache[k]

    def build_stock_card(self, stock_data: Dict) -> str:
        """构建单只股票的推送卡片（不截断）"""
        code = stock_data.get('stock_code', '')
        name = stock_data.get('stock_name', '')
        score = stock_data.get('total_score', 0)
        grade = stock_data.get('grade', '')
        price = stock_data.get('today_close', 0)
        pct = stock_data.get('today_pct', 0)

        lines = []
        lines.append(f"📊 {name}({code})")
        lines.append(f"综合评分：{score}/100  等级：{grade}")
        lines.append(f"现价：{price}  涨幅：{pct:+.2f}%")

        # 评分明细
        detail = stock_data.get('score_detail', {})
        if detail:
            parts = []
            for k, v in detail.items():
                if v.get('score', 0) > 0:
                    parts.append(f"{k}:{v['score']:.0f}")
            if parts:
                lines.append(f"评分构成：{' '.join(parts)}")

        # 看好逻辑
        pos = stock_data.get('positive_reasons', [])
        if pos:
            lines.append("【看好逻辑】")
            for i, r in enumerate(pos[:3], 1):
                lines.append(f"  {i}. {r}")

        # 风险提示
        neg = stock_data.get('negative_reasons', [])
        if neg:
            lines.append("【风险提示】")
            for i, r in enumerate(neg[:2], 1):
                lines.append(f"  {i}. {r}")

        # 买卖点
        buy_price = stock_data.get('buy_price', '')
        stop_loss = stock_data.get('stop_loss', '')
        take_profit = stock_data.get('take_profit', '')
        if buy_price or stop_loss:
            lines.append(f"建议买入：{buy_price}  止损：{stop_loss}  止盈：{take_profit}")

        lines.append("-" * 30)
        return "\n".join(lines)

    def push_signal(self, stock_data: Dict, signal_type: str = '综合信号', force: bool = False) -> bool:
        """
        推送单只股票信号（异步）

        Args:
            stock_data: 股票分析结果
            signal_type: 信号类型
            force: 是否强制推送（跳过去重和评分检查）

        Returns:
            是否加入发送队列
        """
        if not self._webhook_url:
            print("[企业微信] 未配置webhook，跳过推送")
            return False

        code = stock_data.get('stock_code', '')
        grade = stock_data.get('grade_level', '')
        score = stock_data.get('total_score', 0)

        # 评分检查（非强制）
        if not force and score < 80:
            return False

        # 去重检查
        signal_id = self._make_signal_id(code, signal_type, grade)
        if not force and self._is_duplicate(signal_id):
            self._stats['deduped'] += 1
            print(f"[企业微信] 去重跳过：{code} {signal_type}")
            return False

        self._record_dedup(signal_id)
        self._send_queue.put({
            'type': 'single',
            'stock_data': stock_data,
            'signal_type': signal_type,
            'signal_id': signal_id,
            'retry': 0,
        })
        return True

    def push_batch(self, stocks_data: List[Dict], title: str = '量化盯盘提醒') -> int:
        """
        批量推送多只股票（自动分片，不截断单只股票）

        Returns:
            加入队列的消息数量
        """
        if not self._webhook_url or not stocks_data:
            return 0

        # 按股票卡片分片
        batches = []
        current_batch = []
        current_length = 0

        for stock in stocks_data:
            card = self.build_stock_card(stock)
            card_length = len(card)
            if current_batch and current_length + card_length > self.MAX_CARD_LENGTH:
                batches.append(current_batch)
                current_batch = []
                current_length = 0
            current_batch.append(stock)
            current_length += card_length

        if current_batch:
            batches.append(current_batch)

        # 加入队列
        count = 0
        for i, batch in enumerate(batches):
            batch_title = f"{title}（{i+1}/{len(batches)}）" if len(batches) > 1 else title
            self._send_queue.put({
                'type': 'batch',
                'stocks_data': batch,
                'title': batch_title,
                'batch_index': i,
                'total_batches': len(batches),
                'retry': 0,
            })
            count += 1

        print(f"[企业微信] 批量推送：{len(stocks_data)}只股票，分为{count}条消息")
        return count

    def push_text(self, text: str, title: str = '量化提醒', wait_for_result: bool = False, timeout: float = 20.0) -> Dict:
        """推送纯文本消息。wait_for_result=True时等待后台线程拿到企业微信真实返回。
        Returns: {'success': bool, 'errcode': int, 'errmsg': str}
        """
        if not self._webhook_url:
            return {'success': False, 'errcode': -1, 'errmsg': 'webhook未配置'}
        event = threading.Event() if wait_for_result else None
        item = {
            'type': 'text', 'text': text, 'title': title, 'retry': 0,
            'wait_event': event, 'result': None,
        }
        self._send_queue.put(item)
        if not wait_for_result:
            return {'success': True, 'errcode': 0, 'errmsg': '已加入发送队列'}
        if event.wait(timeout):
            result = item.get('result')
            if isinstance(result, dict):
                return result
            return {'success': bool(result), 'errcode': 0 if result else -1, 'errmsg': 'ok' if result else '发送失败'}
        return {'success': False, 'errcode': -1, 'errmsg': '发送超时'}

    def _send_worker(self):
        """后台发送线程"""
        while self._running:
            try:
                item = self._send_queue.get(timeout=1)
                self._process_send_item(item)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[企业微信] 发送线程异常: {e}")

    def _process_send_item(self, item: Dict):
        """处理发送项（含重试），保存企业微信真实返回errcode/errmsg"""
        retry = item.get('retry', 0)
        try:
            if item['type'] == 'single':
                content = self.build_stock_card(item['stock_data'])
                title = f"【{item['signal_type']}】"
                resp = self._send_wechat(title + "\n" + content)
            elif item['type'] == 'batch':
                cards = [self.build_stock_card(s) for s in item['stocks_data']]
                content = "\n".join(cards)
                resp = self._send_wechat(f"【{item['title']}】\n{content}")
            elif item['type'] == 'text':
                resp = self._send_wechat(f"【{item['title']}】\n{item['text']}")
            elif item['type'] == 'image':
                resp = self._send_wechat_image(item['media_id'])
            else:
                resp = {'errcode': 0, 'errmsg': 'ok'}

            self._stats['sent'] += 1
            item['result'] = {'success': True, 'errcode': resp.get('errcode', 0), 'errmsg': resp.get('errmsg', 'ok')}
            if item.get('wait_event'):
                item['wait_event'].set()
            self._send_history.append({
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'type': item['type'],
                'status': 'success',
                'errcode': resp.get('errcode', 0),
                'errmsg': resp.get('errmsg', 'ok'),
            })
            print(f"[企业微信] 发送成功 errcode={resp.get('errcode',0)} ({item['type']})")

        except Exception as e:
            if retry < self.MAX_RETRIES:
                item['retry'] = retry + 1
                self._stats['retried'] += 1
                wait_time = 2 ** retry  # 指数退避
                print(f"[企业微信] 发送失败，{wait_time}秒后重试({retry+1}/{self.MAX_RETRIES}): {e}")
                time.sleep(wait_time)
                self._send_queue.put(item)
            else:
                self._stats['failed'] += 1
                item['result'] = {'success': False, 'errcode': -1, 'errmsg': str(e)}
                if item.get('wait_event'):
                    item['wait_event'].set()
                self._send_history.append({
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'type': item['type'],
                    'status': 'failed',
                    'error': str(e),
                })
                print(f"[企业微信] 发送失败，已达最大重试次数: {e}")

    def _send_wechat(self, content: str) -> Dict:
        """实际发送企业微信消息，返回企业微信真实响应{errcode, errmsg}"""
        import urllib.request
        import urllib.error

        payload = {
            "msgtype": "text",
            "text": {"content": content}
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self._webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            errcode = result.get('errcode', -1)
            errmsg = result.get('errmsg', 'unknown')
            if errcode != 0:
                raise Exception(f"企业微信返回错误 errcode={errcode} errmsg={errmsg}")
            return {'errcode': errcode, 'errmsg': errmsg}

    def _send_wechat_image(self, media_id: str) -> Dict:
        """发送图片消息到企业微信"""
        import urllib.request
        payload = {
            "msgtype": "image",
            "image": {"media_id": media_id}
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self._webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            errcode = result.get('errcode', -1)
            errmsg = result.get('errmsg', 'unknown')
            if errcode != 0:
                raise Exception(f"企业微信图片发送错误 errcode={errcode} errmsg={errmsg}")
            return {'errcode': errcode, 'errmsg': errmsg}

    def upload_media(self, image_path: str) -> Optional[str]:
        """上传图片到企业微信，返回media_id
        企业微信webhook上传接口：POST /cgi-bin/webhook/upload_media?key=KEY&type=image
        """
        if not self._webhook_url or not os.path.exists(image_path):
            return None
        try:
            import urllib.request
            # 从webhook_url提取key
            key = ''
            if 'key=' in self._webhook_url:
                key = self._webhook_url.split('key=')[1].split('&')[0]
            upload_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type=image"

            # 使用multipart/form-data上传
            boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
            with open(image_path, 'rb') as f:
                image_data = f.read()
            filename = os.path.basename(image_path)

            body = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
                f'Content-Type: image/png\r\n\r\n'
            ).encode('utf-8') + image_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')

            req = urllib.request.Request(
                upload_url,
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                errcode = result.get('errcode', -1)
                if errcode == 0:
                    media_id = result.get('media_id', '')
                    print(f"[企业微信] 图片上传成功 media_id={media_id}")
                    return media_id
                else:
                    print(f"[企业微信] 图片上传失败 errcode={errcode} errmsg={result.get('errmsg', '')}")
                    return None
        except Exception as e:
            print(f"[企业微信] 图片上传异常: {e}")
            return None

    def push_image(self, image_path: str, wait_for_result: bool = False, timeout: float = 30.0) -> Dict:
        """推送图片消息到企业微信
        流程：上传图片获取media_id → 发送图片消息
        """
        if not self._webhook_url:
            return {'success': False, 'errcode': -1, 'errmsg': 'webhook未配置'}
        if not os.path.exists(image_path):
            return {'success': False, 'errcode': -1, 'errmsg': f'图片不存在: {image_path}'}

        # 上传图片
        media_id = self.upload_media(image_path)
        if not media_id:
            return {'success': False, 'errcode': -1, 'errmsg': '图片上传失败'}

        # 发送图片消息
        event = threading.Event() if wait_for_result else None
        item = {
            'type': 'image', 'media_id': media_id, 'image_path': image_path,
            'retry': 0, 'wait_event': event, 'result': None,
        }
        self._send_queue.put(item)
        if not wait_for_result:
            return {'success': True, 'errcode': 0, 'errmsg': '已加入发送队列', 'media_id': media_id}
        if event.wait(timeout):
            result = item.get('result')
            if isinstance(result, dict):
                return result
            return {'success': bool(result), 'errcode': 0 if result else -1, 'errmsg': 'ok' if result else '发送失败'}
        return {'success': False, 'errcode': -1, 'errmsg': '发送超时', 'media_id': media_id}

    def get_stats(self) -> Dict:
        return self._stats.copy()

    def get_history(self, limit: int = 20) -> List[Dict]:
        return self._send_history[-limit:]

    def get_queue_size(self) -> int:
        return self._send_queue.qsize()


_wechat_service_instance = None

def get_wechat_notify_service() -> WechatNotifyService:
    global _wechat_service_instance
    if _wechat_service_instance is None:
        _wechat_service_instance = WechatNotifyService()
        _wechat_service_instance.start()
    return _wechat_service_instance


if __name__ == '__main__':
    print("企业微信推送服务自测")
    print("=" * 60)

    service = WechatNotifyService()
    print(f"Webhook配置：{'已配置' if service.is_configured() else '未配置'}")
    print(f"去重窗口：{service.DEDUP_WINDOW_SECONDS}秒")
    print(f"单条安全长度：{service.MAX_CARD_LENGTH}字符")
    print(f"最大重试次数：{service.MAX_RETRIES}")

    # 测试股票卡片构建
    test_stock = {
        'stock_code': '000001', 'stock_name': '平安银行',
        'total_score': 85.5, 'grade': '🟢偏强看好', 'grade_level': 'A+',
        'today_close': 11.91, 'today_pct': 2.35,
        'score_detail': {
            'technical': {'score': 18, 'max': 25},
            'reinforcement': {'score': 12, 'max': 15},
            'amplitude': {'score': 10, 'max': 15},
            'volume_price': {'score': 8, 'max': 10},
            'sector': {'score': 9, 'max': 10},
        },
        'positive_reasons': ['MA5>MA10>MA20多头排列', '援军战法A级', '放量阳线', '板块资金流入'],
        'negative_reasons': ['KDJ高位'],
        'buy_price': '11.80-12.00', 'stop_loss': '11.30', 'take_profit': '13.00',
    }

    print("\n测试股票卡片：")
    card = service.build_stock_card(test_stock)
    print(card)
    print(f"卡片长度：{len(card)}字符")

    # 测试去重
    sid = service._make_signal_id('000001', '综合信号', 'A+')
    print(f"\n信号ID：{sid}")
    print(f"首次推送（去重检查）：{'重复' if service._is_duplicate(sid) else '新信号'}")
    service._record_dedup(sid)
    print(f"再次推送（去重检查）：{'重复' if service._is_duplicate(sid) else '新信号'}")

    # 测试批量分片
    print("\n测试批量分片（10只股票）：")
    test_stocks = [test_stock.copy() for _ in range(10)]
    for i, s in enumerate(test_stocks):
        s['stock_code'] = f'00000{i}'
        s['stock_name'] = f'测试股票{i}'
    batch_count = service.push_batch(test_stocks, title='测试批量推送')
    print(f"10只股票分为{batch_count}条消息")
    print(f"队列大小：{service.get_queue_size()}")

    print("\n企业微信推送服务自测完成。")
