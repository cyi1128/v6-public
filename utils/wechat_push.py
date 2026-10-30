# -*- coding: utf-8 -*-
"""
微信推送模块
支持企业微信群机器人推送
"""
import json
import requests
import os


class WechatPusher:
    """企业微信群机器人推送"""

    def __init__(self, webhook_url=None):
        self.webhook_url = webhook_url
        self.config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'wechat_config.json'
        )
        self._load_config()

    def _load_config(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if not self.webhook_url:
                        self.webhook_url = config.get('webhook_url', '')
            except Exception as e:
                print(f"加载微信配置失败: {e}")

    def save_config(self, webhook_url):
        """保存配置"""
        self.webhook_url = webhook_url
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({'webhook_url': webhook_url}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存微信配置失败: {e}")
            return False

    def is_configured(self):
        """是否已配置"""
        return bool(self.webhook_url and self.webhook_url.strip())

    def send_text(self, content, mentioned_list=None, mentioned_mobile_list=None):
        """
        发送文本消息
        Args:
            content: 文本内容
            mentioned_list: @用户的userid列表，如 ["wangqing","@all"]
            mentioned_mobile_list: @用户的手机号列表，如 ["13800000000","@all"]
        """
        if not self.is_configured():
            return False, "未配置Webhook地址"

        data = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        if mentioned_list:
            data["text"]["mentioned_list"] = mentioned_list
        if mentioned_mobile_list:
            data["text"]["mentioned_mobile_list"] = mentioned_mobile_list

        return self._send(data)

    def send_markdown(self, content):
        """
        发送Markdown消息
        支持的语法：标题、加粗、链接、代码、引用、颜色文字
        """
        if not self.is_configured():
            return False, "未配置Webhook地址"

        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        return self._send(data)

    def send_stock_list(self, title, stocks, max_count=20):
        """
        发送股票列表（Markdown格式）
        Args:
            title: 标题
            stocks: 股票列表，每个元素包含 code, name, price, pct_chg, ai_score, signal_names等
            max_count: 最多显示多少只
        """
        if not stocks:
            return self.send_text(f"【{title}】\n暂无符合条件的股票")

        lines = []
        lines.append(f"## 📊 {title}")
        lines.append(f"> 共 **{len(stocks)}** 只股票")
        lines.append("")

        # 表格头
        lines.append("| 名称 | 现价 | 涨跌幅 | AI评分 |")
        lines.append("|------|------|--------|--------|")

        for i, stock in enumerate(stocks[:max_count]):
            name = stock.get('name', '')
            code = stock.get('code', '')
            price = stock.get('price', 0)
            pct = stock.get('pct_chg', 0)
            ai_score = stock.get('ai_score', 0)

            # 涨跌幅颜色（企业微信markdown支持<font color="info">等）
            if pct >= 0:
                pct_text = f'<font color="warning">+{pct:.2f}%</font>'
            else:
                pct_text = f'<font color="info">{pct:.2f}%</font>'

            # AI评分颜色
            if ai_score >= 80:
                score_text = f'<font color="warning">{ai_score}</font>'
            elif ai_score >= 60:
                score_text = f'<font color="info">{ai_score}</font>'
            else:
                score_text = f'{ai_score}'

            lines.append(f"| {name}({code}) | {price:.2f} | {pct_text} | {score_text} |")

            # 信号标签
            signals = stock.get('signal_names', [])
            if signals:
                sig_text = ' '.join([f"`{s}`" for s in signals[:3]])
                lines.append(f"| 信号: {sig_text} | | | |")

        if len(stocks) > max_count:
            lines.append("")
            lines.append(f"> 仅显示前{max_count}只，完整列表请查看PC端")

        lines.append("")
        lines.append(f"> 📅 {self._get_now_str()}")

        content = '\n'.join(lines)
        return self.send_markdown(content)

    def send_watchlist(self, stocks):
        """发送自选股行情"""
        return self.send_stock_list("自选股行情", stocks, max_count=30)

    def send_limit_up(self, stocks):
        """发送涨停股列表"""
        return self.send_stock_list("今日涨停个股", stocks, max_count=30)

    def _send(self, data):
        """发送请求"""
        try:
            resp = requests.post(self.webhook_url, json=data, timeout=10)
            result = resp.json()
            if result.get('errcode') == 0:
                return True, "发送成功"
            else:
                return False, result.get('errmsg', '发送失败')
        except Exception as e:
            return False, f"发送异常: {e}"

    def _get_now_str(self):
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def test_push(self):
        """测试推送"""
        return self.send_text("✅ 企业微信机器人配置成功！\n\n这是一条测试消息。")


# 单例
_pusher = None


def get_wechat_pusher():
    global _pusher
    if _pusher is None:
        _pusher = WechatPusher()
    return _pusher
