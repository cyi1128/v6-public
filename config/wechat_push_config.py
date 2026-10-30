# -*- coding: utf-8 -*-
"""
AI-520企业微信推送升级模块配置
V2.8 三级推送机制配置
"""
import os

# ============================================================
# 基础配置
# ============================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 推送开关
PUSH_ENABLED = True
DEFAULT_PUSH_TYPE = 'markdown'  # markdown / text / image

# ============================================================
# 长度校验配置（字节，UTF-8编码）
# ============================================================
# 企业微信Markdown官方限制：20480字节
SAFE_THRESHOLD = 18000      # 安全阈值，低于此值直接推送
WARN_THRESHOLD = 15000       # 告警阈值，记录日志不处理
MAX_SPLIT_STOCKS = 3         # 拆分推送时每条最多股票数

# ============================================================
# 图片生成配置（Pillow）
# ============================================================
IMAGE_WIDTH = 1080            # 图片宽度
IMAGE_PADDING = 40            # 内边距
IMAGE_HEADER_HEIGHT = 100     # 标题栏高度
IMAGE_ROW_HEIGHT = 50         # 每行高度
IMAGE_FOOTER_HEIGHT = 60      # 底部高度
IMAGE_MAX_SIZE_KB = 500       # 图片最大大小KB

# 配色（浅色商务风格，与UI一致）
COLORS = {
    'bg': '#F0F4F9',           # 主背景
    'card_bg': '#FFFFFF',      # 卡片背景
    'title': '#1E293B',        # 标题文字
    'text': '#475569',         # 正文文字
    'secondary': '#64748B',    # 次要文字
    'accent': '#2563EB',       # 主色调（蓝）
    'up': '#DC2626',           # 上涨（红）
    'down': '#16A34A',         # 下跌（绿）
    'warning': '#EA580C',      # 警告（橙）
    'border': '#E2E8F0',       # 边框
    'grade_s': '#DC2626',      # S级
    'grade_a': '#EA580C',      # A级
    'grade_b': '#2563EB',      # B级
    'grade_c': '#64748B',      # C级
}

# 字体配置（系统默认无衬线）
FONT_CONFIG = {
    'title_size': 28,
    'header_size': 20,
    'text_size': 16,
    'small_size': 14,
    'font_family': 'msyh.ttc',  # 微软雅黑，Windows默认
}

# 图片保存目录
IMAGE_SAVE_DIR = os.path.join(PROJECT_ROOT, 'logs', 'push_images')
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

# ============================================================
# 推送日志配置
# ============================================================
LOG_ENABLED = True
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# ============================================================
# 重试配置
# ============================================================
MAX_RETRIES = 1               # 失败重试次数
RETRY_DELAY = 2               # 重试延迟（秒）

# ============================================================
# 每日收盘报告配置
# ============================================================
DAILY_REPORT_ENABLED = True
DAILY_REPORT_TIME = '15:30'   # 收盘报告触发时间
