# -*- coding: utf-8 -*-
"""
高级按钮组件库 - advanced_buttons.py
专为量化交易终端设计，支持14套皮肤自适应

按钮类型（8种）：
  PrimaryButton    - 主操作按钮（accent色填充+渐变+外发光）
  SuccessButton    - 成功/确认按钮（绿色填充）
  DangerButton     - 危险/止损按钮（红色填充）
  GhostButton      - 幽灵按钮（透明底+边框）
  IconButton       - 纯图标按钮（圆形/方形）
  ToggleButton     - 开关切换按钮（滑块动画）
  PulseButton      - 脉冲动画按钮（下单闪烁）
  StatusButton     - 状态指示按钮（连接/断开指示灯）

辅助：
  ButtonGroup      - 按钮组容器
  generate_button_qss() - 生成按钮专用QSS
  patch_skin_manager()  - 集成到SkinManager
"""

import math
from typing import Optional

from PyQt6.QtWidgets import (
    QPushButton, QWidget, QHBoxLayout, QSizePolicy, QApplication
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtSignal, pyqtProperty, QRectF, QPointF
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QLinearGradient, QPainterPath
)


# ═══════════════════════════════════════════════════
# 颜色工具函数
# ═══════════════════════════════════════════════════

def hex_to_rgb(hex_color: str):
    """HEX → (R, G, B)"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b) -> str:
    """(R, G, B) → HEX"""
    return f'#{int(r):02x}{int(g):02x}{int(b):02x}'


def lighten(hex_color: str, factor: float = 0.2) -> str:
    """提亮颜色，factor=0.2表示提亮20%"""
    r, g, b = hex_to_rgb(hex_color)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return rgb_to_hex(r, g, b)


def darken(hex_color: str, factor: float = 0.2) -> str:
    """加深颜色，factor=0.2表示加深20%"""
    r, g, b = hex_to_rgb(hex_color)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return rgb_to_hex(r, g, b)


def with_alpha(hex_color: str, alpha: int) -> str:
    """添加透明度 → rgba字符串，alpha取值0-255"""
    r, g, b = hex_to_rgb(hex_color)
    return f'rgba({r}, {g}, {b}, {alpha})'


def lerp_color(c1: str, c2: str, t: float) -> str:
    """线性插值两种颜色，t=0→c1, t=1→c2"""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def get_skin_colors() -> dict:
    """获取当前皮肤颜色配置（13个颜色值）"""
    try:
        from ui.theme.skin_manager import SkinManager
        return SkinManager.get_colors()
    except Exception:
        return {
            'bg_darkest': '#080C12',
            'bg_window': '#0D1117',
            'bg_card': '#161B22',
            'bg_card_hover': '#1C2128',
            'border': '#30363D',
            'border_hover': '#484F58',
            'text_primary': '#FFFFFF',
            'text_secondary': '#8B949E',
            'up': '#F85149',
            'down': '#3FB950',
            'accent': '#3B82F6',
            'limit_up': '#FFD700',
            'limit_down': '#58A6FF',
        }


# ═══════════════════════════════════════════════════
# 基础按钮：AnimatedButtonBase
# ═══════════════════════════════════════════════════

class AnimatedButtonBase(QPushButton):
    """
    动画按钮基类
    - 悬停渐变过渡（hover_progress 0→1）
    - 按下缩放效果（press_scale 1.0→0.95）
    - 自定义paintEvent绘制
    - 外发光效果
    """

    def __init__(self, text: str = '', parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._hover_progress = 0.0
        self._press_scale = 1.0
        self._anim_hover = None
        self._anim_press = None
        self._glow_enabled = False
        self._glow_alpha = 0

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )

    # ── 悬停动画 ──
    def enterEvent(self, event):
        super().enterEvent(event)
        self._start_hover_anim(1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._start_hover_anim(0.0)

    def _start_hover_anim(self, target: float):
        if self._anim_hover:
            self._anim_hover.stop()
        self._anim_hover = QPropertyAnimation(self, b"hover_progress")
        self._anim_hover.setDuration(180)
        self._anim_hover.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_hover.setStartValue(self._hover_progress)
        self._anim_hover.setEndValue(target)
        self._anim_hover.start()

    @pyqtProperty(float)
    def hover_progress(self):
        return self._hover_progress

    @hover_progress.setter
    def hover_progress(self, val: float):
        self._hover_progress = val
        self.update()

    # ── 按下动画 ──
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_press_anim(0.95)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_press_anim(1.0)
        super().mouseReleaseEvent(event)

    def _start_press_anim(self, target: float):
        if self._anim_press:
            self._anim_press.stop()
        self._anim_press = QPropertyAnimation(self, b"press_scale")
        self._anim_press.setDuration(100)
        self._anim_press.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_press.setStartValue(self._press_scale)
        self._anim_press.setEndValue(target)
        self._anim_press.start()

    @pyqtProperty(float)
    def press_scale(self):
        return self._press_scale

    @press_scale.setter
    def press_scale(self, val: float):
        self._press_scale = val
        self.update()

    # ── 发光效果 ──
    def set_glow(self, enabled: bool):
        self._glow_enabled = enabled
        if not enabled:
            self._glow_alpha = 0
            self.update()

    def _update_glow(self):
        if self._glow_enabled:
            self._glow_alpha = int(80 * self._hover_progress)

    # ── 绘制入口 ──
    def paintEvent(self, event):
        self._update_glow()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        scale = self._press_scale
        if scale != 1.0:
            painter.translate(w / 2, h / 2)
            painter.scale(scale, scale)
            painter.translate(-w / 2, -h / 2)

        self._paint_button(painter, w, h)
        self._paint_text(painter, w, h)
        painter.end()

    def _paint_button(self, painter: QPainter, w: int, h: int):
        """子类重写：绘制按钮背景"""
        raise NotImplementedError

    def _paint_text(self, painter: QPainter, w: int, h: int):
        """绘制文字"""
        colors = get_skin_colors()
        painter.setPen(QColor(self._get_text_color(colors)))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(0, 0, w, h),
            Qt.AlignmentFlag.AlignCenter,
            self.text()
        )

    def _get_text_color(self, colors: dict) -> str:
        return colors['text_primary']

    # ── 绘制工具方法 ──
    def _draw_rounded_rect(self, painter, w, h, radius,
                           bg_color, border_color=None, border_w=1):
        """绘制圆角矩形，bg_color支持hex或QColor"""
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        if isinstance(bg_color, QColor):
            painter.fillPath(path, bg_color)
        else:
            painter.fillPath(path, QColor(bg_color))
        if border_color:
            if isinstance(border_color, QColor):
                painter.setPen(QPen(border_color, border_w))
            else:
                painter.setPen(QPen(QColor(border_color), border_w))
            painter.drawPath(path)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

    def _draw_gradient_rect(self, painter, w, h, radius, color1, color2):
        """绘制垂直渐变圆角矩形"""
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(color1))
        grad.setColorAt(1.0, QColor(color2))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.fillPath(path, grad)
        painter.setPen(Qt.PenStyle.NoPen)

    def _draw_glow(self, painter, w, h, color, radius):
        """绘制外发光（多层描边模拟）"""
        if self._glow_alpha <= 0:
            return
        for i in range(3, 0, -1):
            c = QColor(color)
            c.setAlpha(int(self._glow_alpha * i / 4))
            pen = QPen(c, i * 2)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.addRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)
            painter.drawPath(path)


# ═══════════════════════════════════════════════════
# PrimaryButton - 主操作按钮
# ═══════════════════════════════════════════════════

class PrimaryButton(AnimatedButtonBase):
    """
    主操作按钮
    accent色填充 + 渐变悬停 + 外发光
    用途：确认下单、启动策略、保存配置
    """

    def __init__(self, text: str = '', parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.set_glow(True)
        self.setMinimumHeight(38)

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        accent = colors['accent']
        t = self._hover_progress
        base = lerp_color(accent, lighten(accent, 0.15), t)
        bottom = lerp_color(darken(accent, 0.15), accent, t)
        self._draw_gradient_rect(painter, w, h, 6, base, bottom)
        self._draw_glow(painter, w, h, accent, 6)

    def _get_text_color(self, colors):
        return '#FFFFFF'


# ═══════════════════════════════════════════════════
# SuccessButton - 成功/确认按钮
# ═══════════════════════════════════════════════════

class SuccessButton(AnimatedButtonBase):
    """
    成功按钮
    绿色（down色）填充，用于买入确认、策略验证通过
    """

    def __init__(self, text: str = '', parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.set_glow(True)
        self.setMinimumHeight(38)

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        down_color = colors['down']
        t = self._hover_progress
        base = lerp_color(down_color, lighten(down_color, 0.2), t)
        bottom = lerp_color(darken(down_color, 0.2), down_color, t)
        self._draw_gradient_rect(painter, w, h, 6, base, bottom)
        self._draw_glow(painter, w, h, down_color, 6)

    def _get_text_color(self, colors):
        return '#FFFFFF'


# ═══════════════════════════════════════════════════
# DangerButton - 危险/止损按钮
# ═══════════════════════════════════════════════════

class DangerButton(AnimatedButtonBase):
    """
    危险按钮
    红色（up色）填充，用于止损、清仓、删除
    """

    def __init__(self, text: str = '', parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.set_glow(True)
        self.setMinimumHeight(38)

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        up_color = colors['up']
        t = self._hover_progress
        base = lerp_color(up_color, lighten(up_color, 0.2), t)
        bottom = lerp_color(darken(up_color, 0.2), up_color, t)
        self._draw_gradient_rect(painter, w, h, 6, base, bottom)
        self._draw_glow(painter, w, h, up_color, 6)

    def _get_text_color(self, colors):
        return '#FFFFFF'


# ═══════════════════════════════════════════════════
# GhostButton - 幽灵按钮
# ═══════════════════════════════════════════════════

class GhostButton(AnimatedButtonBase):
    """
    幽灵按钮
    透明底 + accent边框，悬停时填充淡accent
    color_key可选: 'accent' / 'up' / 'down'
    """

    def __init__(self, text: str = '', color_key: str = 'accent',
                 parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._color_key = color_key
        self.setMinimumHeight(34)

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        base_color = colors.get(self._color_key, colors['accent'])
        t = self._hover_progress

        # 背景：透明 → 半透明accent
        bg = QColor(base_color)
        bg.setAlpha(int(25 * t))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
        painter.fillPath(path, bg)

        # 边框
        bc = QColor(base_color)
        bc.setAlpha(int(120 + 135 * t))
        painter.setPen(QPen(bc, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _get_text_color(self, colors):
        return colors.get(self._color_key, colors['accent'])


# ═══════════════════════════════════════════════════
# IconButton - 图标按钮
# ═══════════════════════════════════════════════════

class IconButton(AnimatedButtonBase):
    """
    图标按钮
    圆形/方形图标按钮，无文字，用字符或emoji作图标
    """

    def __init__(self, icon_char: str = '', parent: Optional[QWidget] = None,
                 circular: bool = True, size: int = 36):
        super().__init__('', parent)
        self._icon_char = icon_char
        self._circular = circular
        self.setFixedSize(size, size)

    def set_icon_char(self, char: str):
        self._icon_char = char
        self.update()

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        t = self._hover_progress
        bg = QColor(colors['bg_card_hover'])
        bg.setAlpha(int(60 + 140 * t))
        if self._circular:
            painter.setBrush(bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(w / 2, h / 2), w / 2 - 1, h / 2 - 1)
        else:
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
            painter.fillPath(path, bg)

    def _paint_text(self, painter, w, h):
        colors = get_skin_colors()
        t = self._hover_progress
        color = lerp_color(colors['text_secondary'], colors['text_primary'], t)
        painter.setPen(QColor(color))
        font = self.font()
        font.setPixelSize(int(min(w, h) * 0.5))
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 0, w, h),
            Qt.AlignmentFlag.AlignCenter,
            self._icon_char
        )


# ═══════════════════════════════════════════════════
# ToggleButton - 开关切换按钮
# ═══════════════════════════════════════════════════

class ToggleButton(AnimatedButtonBase):
    """
    切换按钮
    带滑块动画的开关，用于启停策略、实时数据切换
    """

    toggled = pyqtSignal(bool)

    def __init__(self, text: str = '', parent: Optional[QWidget] = None,
                 checked: bool = False):
        super().__init__(text, parent)
        self._checked = checked
        self._slider_pos = 1.0 if checked else 0.0
        self._anim_slider = None
        self.setFixedHeight(32)
        self.setMinimumWidth(56)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        self._checked = checked
        self._start_slider_anim(1.0 if checked else 0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._start_slider_anim(1.0 if self._checked else 0.0)
            self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def _start_slider_anim(self, target: float):
        if self._anim_slider:
            self._anim_slider.stop()
        self._anim_slider = QPropertyAnimation(self, b"slider_pos")
        self._anim_slider.setDuration(200)
        self._anim_slider.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_slider.setStartValue(self._slider_pos)
        self._anim_slider.setEndValue(target)
        self._anim_slider.start()

    @pyqtProperty(float)
    def slider_pos(self):
        return self._slider_pos

    @slider_pos.setter
    def slider_pos(self, val: float):
        self._slider_pos = val
        self.update()

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        t = self._slider_pos

        # 背景轨道
        track_off = QColor(colors['border'])
        track_on = QColor(colors['accent'])
        track_color = QColor(
            int(track_off.red() + (track_on.red() - track_off.red()) * t),
            int(track_off.green() + (track_on.green() - track_off.green()) * t),
            int(track_off.blue() + (track_on.blue() - track_off.blue()) * t),
            180
        )
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        painter.fillPath(path, track_color)

        # 滑块
        slider_w = h - 6
        slider_x = 3 + t * (w - slider_w - 6)
        slider_rect = QRectF(slider_x, 3, slider_w, slider_w)
        painter.setBrush(QColor(colors['text_primary']))
        painter.drawEllipse(slider_rect)

    def _paint_text(self, painter, w, h):
        pass  # 开关按钮不绘制文字


# ═══════════════════════════════════════════════════
# PulseButton - 脉冲动画按钮
# ═══════════════════════════════════════════════════

class PulseButton(PrimaryButton):
    """
    脉冲按钮
    继承PrimaryButton，增加周期性脉冲发光
    用途：下单按钮、紧急止损、实时提醒
    """

    def __init__(self, text: str = '', parent: Optional[QWidget] = None,
                 pulse_color: Optional[str] = None):
        super().__init__(text, parent)
        self._pulse_color = pulse_color  # None = 使用accent
        self._pulse_phase = 0.0
        self._pulse_active = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

    def start_pulse(self, interval_ms: int = 50):
        """启动脉冲"""
        self._pulse_active = True
        self._pulse_timer.start(interval_ms)

    def stop_pulse(self):
        """停止脉冲"""
        self._pulse_active = False
        self._pulse_timer.stop()
        self._pulse_phase = 0.0
        self.update()

    def _on_pulse_tick(self):
        self._pulse_phase = (self._pulse_phase + 0.05) % 1.0
        self.update()

    def _paint_button(self, painter, w, h):
        super()._paint_button(painter, w, h)
        if self._pulse_active:
            colors = get_skin_colors()
            pc = self._pulse_color or colors['accent']
            alpha = int(40 * abs(math.sin(self._pulse_phase * math.pi)))
            glow = QColor(pc)
            glow.setAlpha(alpha)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
            painter.fillPath(path, glow)


# ═══════════════════════════════════════════════════
# StatusButton - 状态指示按钮
# ═══════════════════════════════════════════════════

class StatusButton(AnimatedButtonBase):
    """
    状态按钮
    左侧带状态指示灯（绿/红/黄/灰），在线时呼吸动画
    用途：连接状态、策略运行状态、数据流状态
    """

    STATUS_ONLINE = 'online'
    STATUS_OFFLINE = 'offline'
    STATUS_WARNING = 'warning'
    STATUS_DISABLED = 'disabled'

    STATUS_COLORS = {
        'online': '#3FB950',
        'offline': '#F85149',
        'warning': '#FFD700',
        'disabled': '#484F58',
    }

    def __init__(self, text: str = '', parent: Optional[QWidget] = None,
                 status: str = 'disabled'):
        super().__init__(text, parent)
        self._status = status
        self._dot_anim_phase = 0.0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._dot_tick)
        self.setMinimumHeight(34)

    def set_status(self, status: str):
        """设置状态"""
        self._status = status
        if status == self.STATUS_ONLINE:
            self._dot_timer.start(60)
        else:
            self._dot_timer.stop()
            self._dot_anim_phase = 0.0
        self.update()

    def get_status(self) -> str:
        return self._status

    def _dot_tick(self):
        self._dot_anim_phase = (self._dot_anim_phase + 0.06) % 1.0
        self.update()

    def _paint_button(self, painter, w, h):
        colors = get_skin_colors()
        t = self._hover_progress

        # 背景
        bg = QColor(colors['bg_card'])
        bg.setAlpha(int(180 + 75 * t))
        border = QColor(
            colors['border_hover'] if t > 0.3 else colors['border']
        )
        self._draw_rounded_rect(painter, w, h, 6, bg, border, 1)

        # 状态指示灯
        dot_color = self.STATUS_COLORS.get(self._status, '#484F58')
        dot_x = 14
        dot_y = h / 2
        dot_r = 4

        if self._status == self.STATUS_ONLINE:
            breath = 0.7 + 0.3 * math.sin(self._dot_anim_phase * math.pi)
            glow = QColor(dot_color)
            glow.setAlpha(int(60 * breath))
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(dot_x, dot_y), dot_r + 3, dot_r + 3)
            painter.setBrush(QColor(dot_color))
            painter.drawEllipse(QPointF(dot_x, dot_y),
                                dot_r * breath, dot_r * breath)
        else:
            painter.setBrush(QColor(dot_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

    def _paint_text(self, painter, w, h):
        colors = get_skin_colors()
        painter.setPen(QColor(colors['text_secondary']))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(26, 0, w - 26, h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text()
        )


# ═══════════════════════════════════════════════════
# ButtonGroup - 按钮组容器
# ═══════════════════════════════════════════════════

class ButtonGroup(QWidget):
    """
    按钮组容器
    自动水平排列按钮，支持紧凑/宽松间距
    """

    def __init__(self, parent: Optional[QWidget] = None,
                 spacing: int = 8, compact: bool = False):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing if not compact else 4)
        self._compact = compact

    def add_button(self, button: QPushButton, stretch: int = 0):
        self._layout.addWidget(button, stretch)
        return button

    def add_stretch(self, stretch: int = 1):
        self._layout.addStretch(stretch)

    def add_spacing(self, size: int = 8):
        self._layout.addSpacing(size)


# ═══════════════════════════════════════════════════
# QSS模板 + 生成函数
# ═══════════════════════════════════════════════════

BUTTON_QSS_TEMPLATE = """
/* ===== 升级版 QPushButton 样式 ===== */
QPushButton {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 6px;
    color: {text_primary};
    padding: 6px 16px;
    font-size: 12px;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: {bg_card_hover};
    border-color: {border_hover};
}}
QPushButton:pressed {{
    background-color: {bg_card};
    padding-top: 7px;
    padding-bottom: 5px;
}}
QPushButton:disabled {{
    background-color: {bg_card};
    color: {border};
    border-color: {border};
}}

/* ── Primary ── */
QPushButton[class="primary"] {{
    background-color: {accent};
    border: 1px solid {accent};
    color: #FFFFFF;
    font-weight: bold;
    min-height: 36px;
}}
QPushButton[class="primary"]:hover {{
    background-color: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton[class="primary"]:pressed {{
    background-color: {accent_pressed};
}}

/* ── Success ── */
QPushButton[class="success"] {{
    background-color: {down};
    border: 1px solid {down};
    color: #FFFFFF;
    font-weight: bold;
    min-height: 36px;
}}
QPushButton[class="success"]:hover {{
    background-color: {down_hover};
    border-color: {down_hover};
}}

/* ── Danger ── */
QPushButton[class="danger"] {{
    background-color: {up};
    border: 1px solid {up};
    color: #FFFFFF;
    font-weight: bold;
    min-height: 36px;
}}
QPushButton[class="danger"]:hover {{
    background-color: {up_hover};
    border-color: {up_hover};
}}

/* ── Ghost ── */
QPushButton[class="ghost"] {{
    background-color: transparent;
    border: 1.5px solid {accent};
    color: {accent};
}}
QPushButton[class="ghost"]:hover {{
    background-color: {accent_faint};
}}

/* ── Icon ── */
QPushButton[class="icon"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 17px;
    padding: 0px;
    min-height: 34px; max-height: 34px;
    min-width: 34px; max-width: 34px;
    color: {text_secondary};
}}
QPushButton[class="icon"]:hover {{
    background-color: {bg_card_hover};
    color: {text_primary};
}}

/* ── Pill 药丸按钮 ── */
QPushButton[class="pill"] {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 14px;
    color: {text_secondary};
    padding: 4px 14px;
    min-height: 28px; max-height: 28px;
    font-size: 11px;
}}
QPushButton[class="pill"]:hover {{
    background-color: {bg_card_hover};
    border-color: {accent};
    color: {accent};
}}
QPushButton[class="pill"][active="true"] {{
    background-color: {accent_faint};
    border-color: {accent};
    color: {accent};
}}

/* ── Segment 分段按钮 ── */
QPushButton[class="segment"] {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 0px;
    color: {text_secondary};
    padding: 5px 12px;
    min-height: 30px;
}}
QPushButton[class="segment"]:hover {{
    background-color: {bg_card_hover};
    color: {text_primary};
}}
QPushButton[class="segment"]:checked,
QPushButton[class="segment"][active="true"] {{
    background-color: {accent_faint};
    border-color: {accent};
    color: {accent};
    font-weight: bold;
}}

/* ── 涨跌停标记按钮 ── */
QPushButton[class="limit_up"] {{
    background-color: {limit_up};
    border: none;
    color: #1A1A1A;
    font-weight: bold;
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 22px; max-height: 22px;
    font-size: 11px;
}}
QPushButton[class="limit_down"] {{
    background-color: {limit_down};
    border: none;
    color: #1A1A1A;
    font-weight: bold;
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 22px; max-height: 22px;
    font-size: 11px;
}}
"""


def generate_button_qss(colors: dict) -> str:
    """
    根据皮肤颜色生成按钮专用QSS
    可直接追加到 SkinManager.generate_qss() 的输出中
    """
    c = colors
    return BUTTON_QSS_TEMPLATE.format(
        bg_card=c['bg_card'],
        bg_card_hover=c['bg_card_hover'],
        border=c['border'],
        border_hover=c['border_hover'],
        text_primary=c['text_primary'],
        text_secondary=c['text_secondary'],
        accent=c['accent'],
        accent_hover=lighten(c['accent'], 0.15),
        accent_pressed=darken(c['accent'], 0.15),
        accent_faint=with_alpha(c['accent'], 25),
        up=c['up'],
        up_hover=lighten(c['up'], 0.15),
        down=c['down'],
        down_hover=lighten(c['down'], 0.15),
        limit_up=c['limit_up'],
        limit_down=c['limit_down'],
    )


def apply_button_class(button: QPushButton, button_class: str):
    """为普通QPushButton应用按钮class（配合QSS使用）"""
    button.setProperty('class', button_class)
    button.style().unpolish(button)
    button.style().polish(button)


# ═══════════════════════════════════════════════════
# 集成到 SkinManager
# ═══════════════════════════════════════════════════

def patch_skin_manager() -> bool:
    """
    将按钮QSS注入到 SkinManager.generate_qss() 中
    在应用启动时调用一次，皮肤切换时按钮样式自动更新
    """
    try:
        from ui.theme.skin_manager import SkinManager

        original_generate = SkinManager.generate_qss

        def patched_generate(cls, skin_key=None):
            qss = original_generate(skin_key)
            colors = cls.get_colors(skin_key)
            qss += '\n' + generate_button_qss(colors)
            return qss

        SkinManager.generate_qss = classmethod(patched_generate)
        SkinManager._qss_cache = {}
        return True
    except Exception as e:
        print(f"[AdvancedButtons] patch_skin_manager failed: {e}")
        return False


def refresh_all_buttons():
    """刷新所有动画按钮（皮肤切换后调用）"""
    app = QApplication.instance()
    if not app:
        return
    for widget in app.allWidgets():
        if isinstance(widget, AnimatedButtonBase):
            widget.update()


# ═══════════════════════════════════════════════════
# Demo 示例
# ═══════════════════════════════════════════════════

def run_demo():
    """运行高级按钮Demo，展示所有8种按钮类型"""
    import sys
    from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QLabel, QGroupBox

    app = QApplication(sys.argv)
    patch_skin_manager()

    window = QMainWindow()
    window.setWindowTitle('Advanced Buttons Demo - 高级按钮系统')
    window.resize(550, 650)

    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setSpacing(16)
    layout.setContentsMargins(24, 24, 24, 24)

    title = QLabel('🎨 高级按钮系统 Demo（8种按钮）')
    title.setStyleSheet('font-size: 18px; font-weight: bold; color: #FFFFFF;')
    layout.addWidget(title)

    # 动画按钮组
    g1 = QGroupBox('动画按钮（自绘+渐变+发光）')
    g1.setStyleSheet(
        'QGroupBox { color: #8B949E; border: 1px solid #30363D; '
        'border-radius: 8px; margin-top: 12px; padding-top: 16px; } '
        'QGroupBox::title { subcontrol-origin: margin; left: 12px; }'
    )
    l1 = QVBoxLayout(g1)
    l1.setSpacing(10)
    l1.addWidget(PrimaryButton('🚀 PrimaryButton 主操作按钮'))
    l1.addWidget(SuccessButton('✅ SuccessButton 成功确认'))
    l1.addWidget(DangerButton('⚠️ DangerButton 危险止损'))
    l1.addWidget(GhostButton('👻 GhostButton 幽灵按钮'))
    l1.addWidget(IconButton('⚙', circular=True, size=36))
    l1.addWidget(ToggleButton(checked=True))
    pulse = PulseButton('💓 PulseButton 脉冲按钮（点击启动脉冲）')
    pulse.clicked.connect(lambda: pulse.start_pulse() if not pulse._pulse_active else pulse.stop_pulse())
    l1.addWidget(pulse)
    l1.addWidget(StatusButton('🔌 StatusButton 行情连接', status=StatusButton.STATUS_ONLINE))
    layout.addWidget(g1)

    # 按钮组
    g2 = QGroupBox('ButtonGroup 按钮组')
    g2.setStyleSheet(g1.styleSheet())
    l2 = QVBoxLayout(g2)
    group = ButtonGroup(compact=True)
    group.add_button(PrimaryButton('买入'))
    group.add_button(DangerButton('卖出'))
    group.add_button(GhostButton('挂单'))
    group.add_stretch()
    group.add_button(IconButton('⚙'))
    l2.addWidget(group)
    layout.addWidget(g2)

    tip = QLabel('💡 鼠标悬停查看颜色过渡动画 | 脉冲按钮点击启动闪烁 | 皮肤切换自动适配')
    tip.setStyleSheet('color: #8B949E; font-size: 11px;')
    layout.addWidget(tip)
    layout.addStretch()

    window.setCentralWidget(central)
    window.show()
    sys.exit(app.exec())


# ═══════════════════════════════════════════════════
# 模块导出
# ═══════════════════════════════════════════════════

__all__ = [
    # 工具函数
    'hex_to_rgb', 'rgb_to_hex', 'lighten', 'darken',
    'with_alpha', 'lerp_color', 'get_skin_colors',
    # 基类
    'AnimatedButtonBase',
    # 8种按钮
    'PrimaryButton', 'SuccessButton', 'DangerButton',
    'GhostButton', 'IconButton', 'ToggleButton',
    'PulseButton', 'StatusButton',
    # 容器
    'ButtonGroup',
    # QSS集成
    'BUTTON_QSS_TEMPLATE', 'generate_button_qss',
    'apply_button_class', 'patch_skin_manager', 'refresh_all_buttons',
    # Demo
    'run_demo',
]


if __name__ == '__main__':
    run_demo()
