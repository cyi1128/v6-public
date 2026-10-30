# -*- coding: utf-8 -*-
"""Unified design tokens - V2.8 轻量立体卡片式 UI"""

# ---------- Core palette - Light Card Style ----------
BG_WINDOW = "#F0F4F9"
BG_PANEL = "rgba(255,255,255,0.92)"
BG_PANEL_ALT = "#F8FAFC"
BG_CARD = "rgba(255,255,255,0.92)"
BG_CARD_HOVER = "rgba(37,99,235,0.06)"
BG_CARD_ACTIVE = "rgba(37,99,235,0.1)"
BG_CONTAINER = "#FFFFFF"
BG_COMPONENT = "#F1F5F9"
BG_INTERACTIVE = "rgba(255,255,255,0.8)"
BG_SIDEBAR = "rgba(255,255,255,0.9)"
BG_SIDEBAR_ACTIVE = "rgba(37,99,235,0.08)"
BG_STATUS = "#F1F5F9"
BG_NAV = "rgba(255,255,255,0.95)"
SHADOW = "rgba(15, 23, 42, 0.06)"

BORDER = "#E2E8F0"
BORDER_SOFT = "rgba(255,255,255,0.9)"
BORDER_STRONG = "#CBD5E1"

TEXT_PRIMARY = "#1E293B"
TEXT_SECONDARY = "#475569"
TEXT_MUTED = "#64748B"
TEXT_WEAK = "#94A3B8"

# ---------- Market colors (A-share rule: red up, green down) ----------
UP = "#FF3B30"
DOWN = "#34C759"
FLAT = "#64748B"
LIMIT_UP = "#AF52DE"
LIMIT_DOWN = "#000000"

# ---------- AI score colors ----------
AI_SCORE_HIGH = "#FF3B30"
AI_SCORE_MID_HIGH = "#FF9500"
AI_SCORE_MID = "#2563EB"
AI_SCORE_LOW = "#64748B"
AI_SCORE_NEUTRAL = "#64748B"

# ---------- Accent colors ----------
ACCENT_RED = "#FF3B30"
ACCENT_ORANGE = "#FF9500"
ACCENT_GOLD = "#FFC107"
ACCENT_GREEN = "#34C759"
ACCENT_BLUE = "#2563EB"
ACCENT_CYAN = "#0EA5E9"
ACCENT_PURPLE = "#AF52DE"

# ---------- Status colors ----------
STATUS_SUCCESS = "#34C759"
STATUS_WARNING = "#FF9500"
STATUS_ERROR = "#FF3B30"
STATUS_INFO = "#2563EB"
STATUS_RISK_LOW = "#34C759"
STATUS_RISK_MID = "#FF9500"
STATUS_RISK_HIGH = "#FF3B30"

# ---------- Typography ----------
FONT_TITLE = "16px"
FONT_SUBTITLE = "13px"
FONT_BODY = "13px"
FONT_LABEL = "11px"
FONT_VALUE = "28px"
FONT_VALUE_LARGE = "32px"

# ---------- Spacing ----------
CARD_RADIUS = 12
CARD_PADDING = 12
CARD_GAP = 8
BTN_RADIUS = 6


def get_ai_score_color(score: float):
    if score >= 90:
        return AI_SCORE_HIGH
    if score >= 80:
        return AI_SCORE_MID_HIGH
    if score >= 70:
        return AI_SCORE_MID
    return AI_SCORE_LOW


def get_change_color(value: float):
    if value > 0:
        return UP
    if value < 0:
        return DOWN
    return FLAT


def get_risk_color(level):
    level_name = str(level).lower()
    if "低" in level_name or "low" in level_name:
        return STATUS_RISK_LOW
    if "中" in level_name or "mid" in level_name or "medium" in level_name:
        return STATUS_RISK_MID
    return STATUS_RISK_HIGH
