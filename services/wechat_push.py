# -*- coding: utf-8 -*-
"""
AI-520企业微信推送升级模块 V2.8
三级推送机制：
1. 日常单只信号：Markdown格式推送
2. 每日收盘报告：PNG图片推送
3. 自动兜底保障：长度校验，超限自动转图片或拆分

架构原则：
- 独立模块，封装所有推送逻辑
- 原有调用处仅需修改导入，不改动业务代码
- 保留原有纯文本推送函数兼容
- 所有网络请求、图片生成包裹异常捕获
- 不弹窗、不阻塞主线程，后台线程执行
"""
import os
import sys
import json
import time
import hashlib
import base64
import threading
import traceback
from typing import Dict, List, Optional, Tuple
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 导入配置
try:
    from config.wechat_push_config import (
        PUSH_ENABLED, DEFAULT_PUSH_TYPE,
        SAFE_THRESHOLD, WARN_THRESHOLD, MAX_SPLIT_STOCKS,
        IMAGE_WIDTH, IMAGE_PADDING, IMAGE_HEADER_HEIGHT, IMAGE_ROW_HEIGHT,
        IMAGE_FOOTER_HEIGHT, IMAGE_MAX_SIZE_KB, COLORS, FONT_CONFIG,
        IMAGE_SAVE_DIR, LOG_ENABLED, LOG_DIR, MAX_RETRIES, RETRY_DELAY,
        DAILY_REPORT_ENABLED,
    )
except ImportError:
    # 配置导入失败时使用默认值
    PUSH_ENABLED = True
    DEFAULT_PUSH_TYPE = 'markdown'
    SAFE_THRESHOLD = 18000
    WARN_THRESHOLD = 15000
    MAX_SPLIT_STOCKS = 3
    IMAGE_WIDTH = 1080
    IMAGE_PADDING = 40
    IMAGE_HEADER_HEIGHT = 100
    IMAGE_ROW_HEIGHT = 50
    IMAGE_FOOTER_HEIGHT = 60
    IMAGE_MAX_SIZE_KB = 500
    COLORS = {
        'bg': '#F0F4F9', 'card_bg': '#FFFFFF', 'title': '#1E293B',
        'text': '#475569', 'secondary': '#64748B', 'accent': '#2563EB',
        'up': '#DC2626', 'down': '#16A34A', 'warning': '#EA580C',
        'border': '#E2E8F0', 'grade_s': '#DC2626', 'grade_a': '#EA580C',
        'grade_b': '#2563EB', 'grade_c': '#64748B',
    }
    FONT_CONFIG = {
        'title_size': 28, 'header_size': 20, 'text_size': 16,
        'small_size': 14, 'font_family': 'msyh.ttc',
    }
    IMAGE_SAVE_DIR = os.path.join(PROJECT_ROOT, 'logs', 'push_images')
    os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
    LOG_ENABLED = True
    LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(LOG_DIR, exist_ok=True)
    MAX_RETRIES = 1
    RETRY_DELAY = 2
    DAILY_REPORT_ENABLED = True

import requests


# ============================================================
# 工具函数
# ============================================================

def _log(message: str, level: str = 'INFO'):
    """推送日志"""
    if not LOG_ENABLED:
        return
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [WechatPush] [{level}] {message}"
    print(log_line, flush=True)
    try:
        log_file = os.path.join(LOG_DIR, f'wechat_push_{datetime.now().strftime("%Y%m%d")}.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')
    except Exception:
        pass


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """十六进制颜色转RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


# ============================================================
# 模块1：长度校验函数
# ============================================================

def check_content_length(content: str) -> Dict:
    """
    校验Markdown内容长度
    返回: {'length': int, 'status': 'safe'/'warn'/'overflow', 'action': str}
    """
    byte_length = len(content.encode('utf-8'))
    result = {
        'length': byte_length,
        'status': 'safe',
        'action': 'direct_push',
    }

    if byte_length > SAFE_THRESHOLD:
        result['status'] = 'overflow'
        result['action'] = 'convert_to_image_or_split'
        _log(f"内容超长: {byte_length}字节 > 安全阈值{SAFE_THRESHOLD}字节", 'WARN')
    elif byte_length > WARN_THRESHOLD:
        result['status'] = 'warn'
        result['action'] = 'direct_push_with_log'
        _log(f"内容接近阈值: {byte_length}字节 > 告警阈值{WARN_THRESHOLD}字节", 'WARN')
    else:
        result['status'] = 'safe'

    return result


def split_markdown_by_stocks(content: str, max_stocks: int = MAX_SPLIT_STOCKS) -> List[str]:
    """
    按股票拆分Markdown内容，每条不超过max_stocks只股票
    用于极端兜底：图片生成失败时拆分多条推送
    """
    # 简单按股票卡片分割（以 **数字. 开头）
    lines = content.split('\n')
    chunks = []
    current_chunk = []
    stock_count = 0

    for line in lines:
        # 检测新股票卡片（以 **1. **2. 等开头）
        if line.strip().startswith('**') and any(c.isdigit() for c in line[:10]):
            if stock_count >= max_stocks and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                stock_count = 0
            stock_count += 1
        current_chunk.append(line)

    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    _log(f"内容拆分为 {len(chunks)} 条，每条最多{max_stocks}只股票")
    return chunks


# ============================================================
# 模块2：Markdown格式化函数
# ============================================================

def format_signal_markdown(signal: Dict, market_brief: Optional[Dict] = None) -> str:
    """
    格式化单只信号为Markdown
    signal: 股票信号数据（复用现有计算结果）
    market_brief: 市场简报（可选）
    """
    code = signal.get('code', '')
    name = signal.get('name', '')
    score = signal.get('total_score', signal.get('ai520_score', 0))
    grade = signal.get('grade', '')
    price = signal.get('price', 0)
    pct_chg = signal.get('pct_chg', 0)
    industry = signal.get('industry', '')
    status = signal.get('status', '新入选')

    # 技术指标
    cross_info = signal.get('cross_info', {})
    ma5 = cross_info.get('ma5', 0)
    ma20 = cross_info.get('ma20', 0)
    ma20_trend = cross_info.get('ma20_trend', '')
    cross_days = cross_info.get('cross_days_ago', -1)

    volume_info = signal.get('volume_info', {})
    vol_ratio = volume_info.get('vol_ratio', 0)

    limit_1y = signal.get('limit_count_1y', 0)
    position_info = signal.get('position_info', {})
    dist_high = position_info.get('dist_from_8m_high', 0)

    # 资金面
    fund_flow = signal.get('fund_flow', {})
    main_net = fund_flow.get('main_net', 0)

    # 板块
    hot_sector = signal.get('hot_sector', '')

    # 异动原因
    anomaly_reason = signal.get('anomaly_reason', '')

    # 买卖点
    buy_sell = signal.get('buy_sell_points', {})
    buy_zone = buy_sell.get('buy_zone', '--')
    stop_loss = buy_sell.get('stop_loss', '--')
    target_zone = buy_sell.get('target_zone', '--')
    position_advice = buy_sell.get('position_advice', '轻仓试探')

    # 历史回测（可选）
    backtest = signal.get('backtest', {})
    bt_count = backtest.get('count', '--')
    bt_winrate = backtest.get('winrate', '--')
    bt_avg_return = backtest.get('avg_return', '--')

    # 涨跌颜色标识
    pct_color = 'info' if pct_chg >= 0 else 'warning'
    pct_sign = '+' if pct_chg >= 0 else ''

    # 构建Markdown
    md = f"""### 【AI-520 选股信号】 🟢 **{name}({code}) {score}分 {grade}级** 【{status}】

> **价格：<font color="{pct_color}">{price:.2f} ({pct_sign}{pct_chg:.2f}%)</font>** ｜ 行业：{industry}
> MA5: {ma5:.2f} ｜ MA20: {ma20:.2f}({ma20_trend}) ｜ 金叉: {cross_days}天前
> 量比: {vol_ratio:.2f} ｜ 年涨停: {limit_1y}次 ｜ 距高点: {dist_high:+.1f}%

---

📊 **历史回测**：近2年同类信号 {bt_count} 次，持股5日胜率 {bt_winrate}%，平均收益 {bt_avg_return}%

💰 **资金面**：主力净流入 {main_net:+.0f} 万

📂 **板块**：{hot_sector if hot_sector else '暂无板块异动数据'}

📌 **异动原因**：{anomaly_reason if anomaly_reason else 'AI520相似度匹配'}

---

🎯 **买点**：{buy_zone} 元
🛑 **止损**：{stop_loss} 元
🎯 **目标**：{target_zone} 元
⚖️ **建议仓位**：{position_advice}
"""

    # 市场简报（可选）
    if market_brief:
        md += f"""
---

📰 **今日市场简报**
{market_brief.get('index_summary', '')}
涨跌比 {market_brief.get('up_down_ratio', '')} ｜ 涨停 {market_brief.get('limit_up_count', '')} 家 ｜ 连板高度 {market_brief.get('max_consecutive', '')} 板
主力流入前三：{market_brief.get('top_inflow_sectors', '')}
"""

    md += """
---
*AI-520 动态选股雷达 | 数据来源: pytdx | 仅供参考，不构成投资建议*
"""

    return md


def format_daily_summary_markdown(signals: List[Dict], scan_stats: Dict) -> str:
    """
    格式化每日汇总为Markdown（用于图片生成失败时的降级）
    """
    date = datetime.now().strftime('%Y-%m-%d')
    total = scan_stats.get('scanned', 0)
    sa_count = scan_stats.get('sa_count', 0)
    new_count = scan_stats.get('new_count', 0)

    md = f"""### 【AI-520 每日选股报告】{date}

**今日扫描**：{total}只 ｜ **S/A级**：{sa_count}只 ｜ **新增信号**：{new_count}只

---

"""

    for i, sig in enumerate(signals[:20], 1):
        code = sig.get('code', '')
        name = sig.get('name', '')
        score = sig.get('total_score', sig.get('ai520_score', 0))
        grade = sig.get('grade', '')
        price = sig.get('price', 0)
        pct = sig.get('pct_chg', 0)
        reason = sig.get('anomaly_reason', '')[:30]
        pct_sign = '+' if pct >= 0 else ''
        md += f"**{i}. {name}({code})** {score}分{grade}级 | {price:.2f}({pct_sign}{pct:.2f}%) | {reason}\n"

    if len(signals) > 20:
        md += f"\n... 共{len(signals)}只信号，仅显示前20只\n"

    md += "\n---\n*AI-520 动态选股雷达 | 仅供参考，不构成投资建议*\n"
    return md


# ============================================================
# 模块3：Pillow图片生成函数
# ============================================================

def _get_font(size: int):
    """获取字体"""
    try:
        from PIL import ImageFont
        # 尝试微软雅黑
        font_paths = [
            'C:/Windows/Fonts/msyh.ttc',
            'C:/Windows/Fonts/msyhbd.ttc',
            '/System/Library/Fonts/PingFang.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                return ImageFont.truetype(fp, size)
        #  fallback
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def generate_daily_report_image(signals: List[Dict], scan_stats: Dict) -> Optional[str]:
    """
    生成每日收盘报告PNG图片
    返回图片路径，失败返回None
    """
    try:
        from PIL import Image, ImageDraw

        date = datetime.now().strftime('%Y-%m-%d')
        total = scan_stats.get('scanned', 0)
        sa_count = scan_stats.get('sa_count', 0)
        new_count = scan_stats.get('new_count', 0)
        market_rating = scan_stats.get('market_rating', '中性')

        # 计算图片高度
        num_stocks = min(len(signals), 50)  # 最多显示50只
        content_height = IMAGE_HEADER_HEIGHT + 120 + num_stocks * IMAGE_ROW_HEIGHT + IMAGE_FOOTER_HEIGHT + 100
        img_height = content_height + IMAGE_PADDING * 2

        # 创建图片
        img = Image.new('RGB', (IMAGE_WIDTH, img_height), _hex_to_rgb(COLORS['bg']))
        draw = ImageDraw.Draw(img)

        # 字体
        font_title = _get_font(FONT_CONFIG['title_size'])
        font_header = _get_font(FONT_CONFIG['header_size'])
        font_text = _get_font(FONT_CONFIG['text_size'])
        font_small = _get_font(FONT_CONFIG['small_size'])

        y = IMAGE_PADDING

        # === 标题栏 ===
        draw.rectangle(
            [IMAGE_PADDING, y, IMAGE_WIDTH - IMAGE_PADDING, y + IMAGE_HEADER_HEIGHT],
            fill=_hex_to_rgb(COLORS['card_bg']),
            outline=_hex_to_rgb(COLORS['border']),
            width=1,
        )
        draw.text(
            (IMAGE_PADDING + 30, y + 25),
            f"AI-520 每日选股报告  {date}",
            fill=_hex_to_rgb(COLORS['title']),
            font=font_title,
        )
        draw.text(
            (IMAGE_PADDING + 30, y + 65),
            f"扫描{total}只 | S/A级{sa_count}只 | 新增{new_count}只 | 市场评级：{market_rating}",
            fill=_hex_to_rgb(COLORS['secondary']),
            font=font_text,
        )
        y += IMAGE_HEADER_HEIGHT + 20

        # === 个股信号列表 ===
        # 表头
        draw.rectangle(
            [IMAGE_PADDING, y, IMAGE_WIDTH - IMAGE_PADDING, y + 40],
            fill=_hex_to_rgb(COLORS['accent']),
        )
        headers = ['排名', '代码', '名称', '评分', '等级', '价格', '涨跌幅', '核心逻辑']
        col_x = [IMAGE_PADDING + 20, IMAGE_PADDING + 100, IMAGE_PADDING + 200,
                 IMAGE_PADDING + 350, IMAGE_PADDING + 430, IMAGE_PADDING + 510,
                 IMAGE_PADDING + 620, IMAGE_PADDING + 750]
        for i, h in enumerate(headers):
            draw.text((col_x[i], y + 10), h, fill=(255, 255, 255), font=font_text)
        y += 40

        # 数据行
        for idx, sig in enumerate(signals[:num_stocks]):
            row_y = y + idx * IMAGE_ROW_HEIGHT
            # 交替背景
            if idx % 2 == 0:
                draw.rectangle(
                    [IMAGE_PADDING, row_y, IMAGE_WIDTH - IMAGE_PADDING, row_y + IMAGE_ROW_HEIGHT],
                    fill=_hex_to_rgb(COLORS['card_bg']),
                )

            code = sig.get('code', '')
            name = sig.get('name', '')[:6]
            score = sig.get('total_score', sig.get('ai520_score', 0))
            grade = sig.get('grade', '')
            price = sig.get('price', 0)
            pct = sig.get('pct_chg', 0)
            reason = sig.get('anomaly_reason', '')[:20]

            # 等级颜色
            grade_color = COLORS.get(f'grade_{grade.lower()}', COLORS['text'])

            # 涨跌幅颜色
            pct_color = COLORS['up'] if pct >= 0 else COLORS['down']
            pct_sign = '+' if pct >= 0 else ''

            draw.text((col_x[0], row_y + 15), str(idx + 1), fill=_hex_to_rgb(COLORS['text']), font=font_text)
            draw.text((col_x[1], row_y + 15), code, fill=_hex_to_rgb(COLORS['text']), font=font_text)
            draw.text((col_x[2], row_y + 15), name, fill=_hex_to_rgb(COLORS['title']), font=font_text)
            draw.text((col_x[3], row_y + 15), f"{score}", fill=_hex_to_rgb(COLORS['accent']), font=font_header)
            draw.text((col_x[4], row_y + 15), grade, fill=_hex_to_rgb(grade_color), font=font_text)
            draw.text((col_x[5], row_y + 15), f"{price:.2f}", fill=_hex_to_rgb(COLORS['text']), font=font_text)
            draw.text((col_x[6], row_y + 15), f"{pct_sign}{pct:.2f}%", fill=_hex_to_rgb(pct_color), font=font_text)
            draw.text((col_x[7], row_y + 15), reason, fill=_hex_to_rgb(COLORS['secondary']), font=font_small)

        y += num_stocks * IMAGE_ROW_HEIGHT + 20

        # === 底部免责声明 ===
        draw.rectangle(
            [IMAGE_PADDING, y, IMAGE_WIDTH - IMAGE_PADDING, y + IMAGE_FOOTER_HEIGHT],
            fill=_hex_to_rgb(COLORS['card_bg']),
            outline=_hex_to_rgb(COLORS['border']),
            width=1,
        )
        draw.text(
            (IMAGE_PADDING + 30, y + 20),
            "AI-520 动态选股雷达 | 数据来源: pytdx | 仅供参考，不构成投资建议",
            fill=_hex_to_rgb(COLORS['secondary']),
            font=font_small,
        )

        # 保存图片
        filename = f"daily_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(IMAGE_SAVE_DIR, filename)
        img.save(filepath, 'PNG', optimize=True)

        # 检查文件大小
        file_size_kb = os.path.getsize(filepath) / 1024
        if file_size_kb > IMAGE_MAX_SIZE_KB:
            _log(f"图片大小 {file_size_kb:.1f}KB 超过限制 {IMAGE_MAX_SIZE_KB}KB，尝试压缩", 'WARN')
            # 压缩
            img.save(filepath, 'PNG', optimize=True, compress_level=9)
            file_size_kb = os.path.getsize(filepath) / 1024

        _log(f"每日报告图片生成成功: {filepath} ({file_size_kb:.1f}KB)")
        return filepath

    except Exception as e:
        _log(f"图片生成失败: {e}\n{traceback.format_exc()}", 'ERROR')
        return None


# ============================================================
# 模块4：企业微信推送函数
# ============================================================

class WechatPushService:
    """
    AI-520企业微信推送升级服务
    统一入口：push_signal() / push_daily_report()
    """

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
        self._webhook_url = self._load_webhook()
        self._push_history = []  # 推送历史记录
        _log(f"推送服务初始化完成 (webhook={'已配置' if self._webhook_url else '未配置'})")

    def _load_webhook(self) -> str:
        """加载webhook地址（复用现有配置）"""
        # 1. 环境变量
        for env_key in ['WECHAT_WORK_WEBHOOK', 'WECHAT_WEBHOOK_URL']:
            url = os.environ.get(env_key, '')
            if url:
                return url

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

    # --------------------------------------------------------
    # 基础推送：Markdown
    # --------------------------------------------------------
    def _send_markdown(self, content: str) -> bool:
        """发送Markdown消息，自动按3800字节切分多条发送"""
        if not self._webhook_url:
            _log("webhook未配置，跳过推送", 'WARN')
            return False

        MAX_BYTES = 3800
        content_bytes = content.encode('utf-8')
        if len(content_bytes) <= MAX_BYTES:
            return self._do_send_markdown(content)

        chunks = []
        current = ""
        for line in content.split('\n'):
            if len((current + '\n' + line).encode('utf-8')) > MAX_BYTES:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = current + '\n' + line if current else line
        if current:
            chunks.append(current)

        _log(f"Markdown内容{len(content_bytes)}字节，切分为{len(chunks)}条发送")
        all_ok = True
        for i, chunk in enumerate(chunks, 1):
            prefix = f"📌 (第{i}/{len(chunks)}条)\n" if len(chunks) > 1 else ""
            ok = self._do_send_markdown(prefix + chunk)
            if not ok:
                all_ok = False
            time.sleep(0.5)
        return all_ok

    def _do_send_markdown(self, content: str) -> bool:
        """实际发送单条Markdown"""
        payload = {
            'msgtype': 'markdown',
            'markdown': {'content': content},
        }

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    self._webhook_url,
                    json=payload,
                    timeout=15,
                    headers={'Content-Type': 'application/json'},
                )
                result = resp.json()
                if result.get('errcode') == 0:
                    _log(f"Markdown推送成功 (尝试{attempt + 1}次)")
                    return True
                else:
                    _log(f"Markdown推送失败: errcode={result.get('errcode')}, errmsg={result.get('errmsg')}", 'ERROR')
            except Exception as e:
                _log(f"Markdown推送异常 (尝试{attempt + 1}次): {e}", 'ERROR')

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        return False

    # --------------------------------------------------------
    # 基础推送：文本（兼容旧版）
    # --------------------------------------------------------
    def _send_text(self, content: str) -> bool:
        """发送文本消息（兼容旧版）"""
        if not self._webhook_url:
            return False

        payload = {
            'msgtype': 'text',
            'text': {'content': content},
        }

        try:
            resp = requests.post(self._webhook_url, json=payload, timeout=15)
            result = resp.json()
            return result.get('errcode') == 0
        except Exception as e:
            _log(f"文本推送异常: {e}", 'ERROR')
            return False

    # --------------------------------------------------------
    # 基础推送：图片
    # --------------------------------------------------------
    def _send_image(self, image_path: str) -> bool:
        """发送图片消息（base64 + md5）"""
        if not self._webhook_url or not os.path.exists(image_path):
            _log(f"图片推送失败: webhook未配置或文件不存在 ({image_path})", 'ERROR')
            return False

        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()

            base64_data = base64.b64encode(image_data).decode('utf-8')
            md5_data = hashlib.md5(image_data).hexdigest()

            payload = {
                'msgtype': 'image',
                'image': {
                    'base64': base64_data,
                    'md5': md5_data,
                },
            }

            resp = requests.post(
                self._webhook_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'},
            )
            result = resp.json()
            if result.get('errcode') == 0:
                _log(f"图片推送成功: {os.path.basename(image_path)}")
                return True
            else:
                _log(f"图片推送失败: errcode={result.get('errcode')}, errmsg={result.get('errmsg')}", 'ERROR')
                return False

        except Exception as e:
            _log(f"图片推送异常: {e}", 'ERROR')
            return False

    # --------------------------------------------------------
    # 统一入口1：单只信号推送
    # --------------------------------------------------------
    def push_signal(self, signal: Dict, market_brief: Optional[Dict] = None,
                    push_type: str = DEFAULT_PUSH_TYPE) -> Dict:
        """
        统一入口：推送单只信号
        自动长度校验，超限自动处理
        返回: {'success': bool, 'type': str, 'length': int, 'message': str}
        """
        if not PUSH_ENABLED:
            return {'success': False, 'type': 'skipped', 'length': 0, 'message': '推送已禁用'}

        start_time = time.time()

        # 1. 格式化Markdown
        markdown_content = format_signal_markdown(signal, market_brief)

        # 2. 长度校验
        length_check = check_content_length(markdown_content)

        # 3. 根据长度决定推送方式
        if length_check['status'] == 'overflow':
            _log("单只信号内容超长，尝试拆分推送", 'WARN')
            # 单只信号理论不会超限，若超限则拆分为核心+深度
            chunks = split_markdown_by_stocks(markdown_content, max_stocks=1)
            success_count = 0
            for chunk in chunks:
                if self._send_markdown(chunk):
                    success_count += 1
            success = success_count == len(chunks)
            push_type_used = 'markdown_split'
        else:
            # 正常推送
            if push_type == 'text':
                success = self._send_text(markdown_content)
                push_type_used = 'text'
            else:
                success = self._send_markdown(markdown_content)
                push_type_used = 'markdown'

        elapsed = time.time() - start_time
        result = {
            'success': success,
            'type': push_type_used,
            'length': length_check['length'],
            'elapsed': round(elapsed, 2),
            'message': '推送成功' if success else '推送失败',
        }

        # 记录历史
        self._push_history.append({
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'code': signal.get('code', ''),
            'name': signal.get('name', ''),
            **result,
        })

        # V2.8模块5：推送成功后自动加入信号跟踪池
        # 【2026-09-24 清理 v28 死引用】原 v28.integration.add_signal_to_tracking 已下线，
        # 推送后不再写入跟踪池（此前也一直没写成功）。现保持原有行为不变。

        return result

    # --------------------------------------------------------
    # 统一入口2：每日收盘报告推送
    # --------------------------------------------------------
    def push_daily_report(self, signals: List[Dict], scan_stats: Dict) -> Dict:
        """
        统一入口：推送每日收盘报告
        优先图片推送，失败自动降级为Markdown
        返回: {'success': bool, 'type': str, 'message': str}
        """
        if not PUSH_ENABLED or not DAILY_REPORT_ENABLED:
            return {'success': False, 'type': 'skipped', 'message': '每日报告推送已禁用'}

        if not signals:
            return {'success': False, 'type': 'skipped', 'message': '无信号数据'}

        _log(f"开始生成每日收盘报告 (信号数: {len(signals)})")

        # 1. 先生成Markdown（用于降级）
        markdown_content = format_daily_summary_markdown(signals, scan_stats)

        # 2. 长度校验
        length_check = check_content_length(markdown_content)

        # 3. 尝试图片推送
        image_path = generate_daily_report_image(signals, scan_stats)

        if image_path and os.path.exists(image_path):
            # 图片生成成功，尝试图片推送
            if self._send_image(image_path):
                return {
                    'success': True,
                    'type': 'image',
                    'image_path': image_path,
                    'message': '图片报告推送成功',
                }
            else:
                _log("图片推送失败，降级为Markdown推送", 'WARN')

        # 4. 降级：Markdown推送
        if length_check['status'] == 'overflow':
            # Markdown也超长，拆分推送
            chunks = split_markdown_by_stocks(markdown_content, max_stocks=MAX_SPLIT_STOCKS)
            success_count = 0
            for chunk in chunks:
                if self._send_markdown(chunk):
                    success_count += 1
            success = success_count > 0
            return {
                'success': success,
                'type': 'markdown_split',
                'chunks': len(chunks),
                'success_chunks': success_count,
                'message': f'拆分推送完成 ({success_count}/{len(chunks)}条成功)',
            }
        else:
            success = self._send_markdown(markdown_content)
            return {
                'success': success,
                'type': 'markdown_fallback',
                'length': length_check['length'],
                'message': 'Markdown降级推送成功' if success else 'Markdown降级推送失败',
            }

    # --------------------------------------------------------
    # 异步推送（不阻塞主线程）
    # --------------------------------------------------------
    def push_signal_async(self, signal: Dict, market_brief: Optional[Dict] = None,
                          callback=None):
        """异步推送单只信号（后台线程）"""
        def _do_push():
            result = self.push_signal(signal, market_brief)
            if callback:
                try:
                    callback(result)
                except Exception:
                    pass
            return result

        thread = threading.Thread(target=_do_push, daemon=True)
        thread.start()
        return thread

    def push_daily_report_async(self, signals: List[Dict], scan_stats: Dict, callback=None):
        """异步推送每日报告（后台线程）"""
        def _do_push():
            result = self.push_daily_report(signals, scan_stats)
            if callback:
                try:
                    callback(result)
                except Exception:
                    pass
            return result

        thread = threading.Thread(target=_do_push, daemon=True)
        thread.start()
        return thread

    # --------------------------------------------------------
    # 统计与历史
    # --------------------------------------------------------
    def get_push_history(self, limit: int = 20) -> List[Dict]:
        """获取推送历史"""
        return self._push_history[-limit:]

    def get_stats(self) -> Dict:
        """获取推送统计"""
        total = len(self._push_history)
        success = sum(1 for h in self._push_history if h.get('success'))
        failed = total - success
        return {
            'total': total,
            'success': success,
            'failed': failed,
            'success_rate': f"{success/total*100:.1f}%" if total > 0 else '0%',
        }


# ============================================================
# 全局单例
# ============================================================

_wechat_push_service = None

def get_wechat_push_service() -> WechatPushService:
    """获取推送服务单例"""
    global _wechat_push_service
    if _wechat_push_service is None:
        _wechat_push_service = WechatPushService()
    return _wechat_push_service


# ============================================================
# 兼容旧版接口
# ============================================================

def push_text(content: str, title: str = '', wait_for_result: bool = True, timeout: int = 25) -> bool:
    """
    兼容旧版push_text接口
    原有调用处无需修改
    """
    service = get_wechat_push_service()
    if title:
        content = f"### {title}\n\n{content}"
    return service._send_markdown(content) if DEFAULT_PUSH_TYPE == 'markdown' else service._send_text(content)


# ============================================================
# V2.7.1 推送层扩展（仅新增，不修改原有函数逻辑）
# 所有新增功能通过配置开关控制，默认关闭
# ============================================================

def _log_extension(msg: str, level: str = 'INFO'):
    """扩展模块日志"""
    print(f"[推送扩展] {msg}", flush=True)


def _is_extension_enabled() -> bool:
    """检查推送扩展总开关"""
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        return PUSH_EXTENSION_CONFIG.get('enabled', False)
    except Exception:
        return False


def _embed_auction_strength(signal: Dict) -> str:
    """嵌入竞价强度字段（数据缺失自动隐藏）"""
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('embed_auction_strength', False):
            return ''
        from market_analysis.auction_strength import analyze_auction
        code = signal.get('code', '')
        name = signal.get('name', '')
        result = analyze_auction(code, name)
        if result and result.get('formatted_text'):
            return result['formatted_text'] + '\n'
        return ''
    except Exception as e:
        _log_extension(f"竞价强度嵌入失败(自动降级): {e}", 'WARN')
        return ''


def _embed_sector_strength(signal: Dict) -> str:
    """嵌入板块强度字段（数据缺失自动隐藏）"""
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('embed_sector_strength', False):
            return ''
        from market_analysis.sector_strength import analyze_sector
        industry = signal.get('industry', '')
        code = signal.get('code', '')
        pct = signal.get('pct_chg', 0)
        if not industry:
            return ''
        result = analyze_sector(industry, code, pct)
        if result and result.get('formatted_text'):
            return result['formatted_text'] + '\n'
        return ''
    except Exception as e:
        _log_extension(f"板块强度嵌入失败(自动降级): {e}", 'WARN')
        return ''


def _embed_deep_fund_flow(signal: Dict) -> str:
    """嵌入深度资金面字段（数据缺失自动隐藏）"""
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('embed_deep_fund_flow', False):
            return ''
        from market_analysis.deep_fund_flow import analyze_deep_fund
        code = signal.get('code', '')
        name = signal.get('name', '')
        result = analyze_deep_fund(code, name)
        if result and result.get('formatted_text'):
            return result['formatted_text'] + '\n'
        return ''
    except Exception as e:
        _log_extension(f"深度资金面嵌入失败(自动降级): {e}", 'WARN')
        return ''


def _embed_policy_catalyst(signal: Dict) -> str:
    """嵌入政策催化字段（数据缺失自动隐藏）"""
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('embed_policy_catalyst', False):
            return ''
        from market_analysis.policy_matcher import match_policy_for_stock
        industry = signal.get('industry', '')
        name = signal.get('name', '')
        if not industry:
            return ''
        result = match_policy_for_stock(industry, name)
        if result and result.get('formatted_text'):
            return result['formatted_text'] + '\n'
        return ''
    except Exception as e:
        _log_extension(f"政策催化嵌入失败(自动降级): {e}", 'WARN')
        return ''


def _embed_market_sentiment() -> str:
    """嵌入市场情绪（推送末尾，数据缺失自动隐藏）"""
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('embed_market_sentiment', False):
            return ''
        from market_analysis.market_sentiment import analyze_sentiment
        result = analyze_sentiment()
        if result and result.get('formatted_text'):
            return '\n---\n' + result['formatted_text']
        return ''
    except Exception as e:
        _log_extension(f"市场情绪嵌入失败(自动降级): {e}", 'WARN')
        return ''


def format_enhanced_signal_markdown(signal: Dict, market_brief: Optional[Dict] = None) -> str:
    """
    V2.8 增强版个股推送模板
    在原有format_signal_markdown基础上嵌入新增字段
    字段顺序：竞价→板块→资金→政策→风险
    所有新增字段通过配置开关控制，默认关闭
    任何新增模块异常时自动降级为原有推送逻辑
    新增内容长度自动计入原有长度校验
    """
    start_time = time.time()
    try:
        # 1. 先调用原有函数生成基础推送（不修改原有逻辑）
        base_md = format_signal_markdown(signal, market_brief)

        # 2. 如果扩展未启用，直接返回原有推送
        if not _is_extension_enabled():
            return base_md

        # 3. 嵌入新增字段（按竞价→板块→资金→政策顺序）
        extra_fields = []

        auction = _embed_auction_strength(signal)
        if auction:
            extra_fields.append(auction)

        sector = _embed_sector_strength(signal)
        if sector:
            extra_fields.append(sector)

        fund = _embed_deep_fund_flow(signal)
        if fund:
            extra_fields.append(fund)

        policy = _embed_policy_catalyst(signal)
        if policy:
            extra_fields.append(policy)

        # 4. 在买点/卖点之前插入新增字段
        if extra_fields:
            insert_point = base_md.find('🎯 **买点**')
            if insert_point > 0:
                extra_text = '\n'.join(extra_fields) + '\n'
                base_md = base_md[:insert_point] + extra_text + base_md[insert_point:]
            else:
                base_md += '\n' + '\n'.join(extra_fields)

        # 5. 推送末尾嵌入市场情绪
        sentiment = _embed_market_sentiment()
        if sentiment:
            base_md += sentiment

        elapsed = time.time() - start_time
        _log_extension(f"增强推送生成完成 耗时{elapsed:.2f}s 总长度{len(base_md)}字符")

        return base_md

    except Exception as e:
        # 异常时自动降级为原有推送逻辑
        _log_extension(f"增强推送异常，自动降级为原有推送: {e}", 'ERROR')
        try:
            return format_signal_markdown(signal, market_brief)
        except Exception:
            return f"### 【AI-520 选股信号】{signal.get('name', '')}({signal.get('code', '')})"


def push_sector_anomaly(anomaly_list: List[Dict]) -> bool:
    """
    V2.8 板块异动独立推送入口
    不占用个股信号通道，独立推送
    同一板块30分钟内不重复推送（由sector_anomaly模块控制）
    所有新增内容自动接入原有长度校验
    """
    start_time = time.time()
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG, SECTOR_ANOMALY_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('sector_anomaly_push', False):
            _log_extension("板块异动推送未启用")
            return False
        if not SECTOR_ANOMALY_CONFIG.get('independent_push', True):
            return False

        if not anomaly_list:
            return False

        service = get_wechat_push_service()

        for anomaly in anomaly_list:
            try:
                md = f"### {anomaly.get('formatted_text', '')}\n"
                md += f"> 板块：{anomaly.get('sector_name', '')} ｜ "
                md += f"类型：{'拉升' if anomaly.get('type') == 'surge' else '跳水'} ｜ "
                md += f"幅度：{anomaly.get('pct_change', 0):+.2f}%\n"

                # 长度校验（复用原有机制）
                length_check = check_content_length(md)
                if length_check['status'] == 'overflow':
                    _log_extension(f"板块异动推送超长，截断处理", 'WARN')
                    md = md[:2000]

                result = service._send_markdown(md)
                _log_extension(f"板块异动推送: {anomaly.get('sector_name', '')} {'成功' if result else '失败'}")
                time.sleep(1)  # 避免频率限制

            except Exception as e:
                _log_extension(f"单条板块异动推送失败: {e}", 'ERROR')
                continue

        elapsed = time.time() - start_time
        _log_extension(f"板块异动推送完成 共{len(anomaly_list)}条 耗时{elapsed:.2f}s")
        return True

    except Exception as e:
        _log_extension(f"板块异动推送异常: {e}", 'ERROR')
        return False


def push_timed_report(report_data: Dict) -> bool:
    """
    V2.8 定时简报推送入口
    支持盘前策略简报/盘中动态简报/盘后总结报告
    盘后报告优先生成PNG图片推送，图片失败自动降级Markdown长文
    自动接入原有长度校验与兜底
    """
    start_time = time.time()
    try:
        from config.market_analysis_config import PUSH_EXTENSION_CONFIG
        if not PUSH_EXTENSION_CONFIG.get('timed_report_push', False):
            _log_extension("定时简报推送未启用")
            return False

        if not report_data:
            return False

        service = get_wechat_push_service()
        report_type = report_data.get('type', '')
        markdown = report_data.get('markdown', '')
        image_path = report_data.get('image_path', '')

        # 1. 优先推送图片（盘后报告）
        if image_path and os.path.exists(image_path):
            try:
                result = service._send_image(image_path)
                _log_extension(f"定时简报图片推送: {report_type} {'成功' if result else '失败'}")
                if result:
                    return True
            except Exception as e:
                _log_extension(f"图片推送失败，降级Markdown: {e}", 'WARN')

        # 2. 降级Markdown推送
        if not markdown:
            return False

        # 长度校验（复用原有机制）
        length_check = check_content_length(md=markdown)
        if length_check['status'] == 'overflow':
            _log_extension(f"定时简报超长({length_check['length']}字节)，拆分推送", 'WARN')
            parts = split_markdown_by_stocks(markdown, max_stocks=10)
            for i, part in enumerate(parts):
                service._send_markdown(part)
                time.sleep(1)
            return True

        result = service._send_markdown(markdown)
        elapsed = time.time() - start_time
        _log_extension(f"定时简报推送: {report_type} {'成功' if result else '失败'} 耗时{elapsed:.2f}s")
        return result

    except Exception as e:
        _log_extension(f"定时简报推送异常: {e}", 'ERROR')
        return False
