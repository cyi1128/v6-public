# -*- coding: utf-8 -*-
"""
作战中控台模块共享辅助
- 题材：使用"选股雷达"同源数据 services/concept_matcher（match_stock_concept）
- 行业补全：东财 ulist 批量取 f100（供自选模块无行业时补全）
- 添加自选按钮：每行一个 "+" / "已添加"
所有数据均为真实接口数据，不造假。
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from .base import BC

# 题材缓存：(code, industry) -> 题材名（盘中基本不变，避免重复计算）
_THEME_CACHE = {}


def _secid(code):
    code = str(code)
    return ('1.' if code.startswith(('6', '9')) else '0.') + code


def get_industry_map(codes):
    """批量获取 代码->行业(f100)。失败返回空dict。"""
    out = {}
    codes = [str(c) for c in codes if c]
    if not codes:
        return out
    try:
        from utils.http_market_data import eastmoney_request
        # 分批，每批最多 60 个 secid
        for i in range(0, len(codes), 60):
            chunk = codes[i:i + 60]
            secids = ','.join(_secid(c) for c in chunk)
            data = eastmoney_request(
                '/api/qt/ulist.np/get',
                {'fltt': '2', 'invt': '2', 'fields': 'f12,f100', 'secids': secids},
                timeout=10,
            )
            diff = data.get('data', {}).get('diff', []) if isinstance(data, dict) else []
            for d in diff:
                if not isinstance(d, dict):
                    continue
                c = d.get('f12', '')
                ind = d.get('f100', '') or ''
                if c:
                    out[c] = ind
    except Exception as e:
        print(f'[题材] 批量获取行业失败: {e}', flush=True)
    return out


def get_radar_theme(code, name='', industry=''):
    """使用选股雷达同源概念匹配函数，返回题材名。失败回退行业/--。"""
    code = str(code)
    key = (code, industry or '')
    if key in _THEME_CACHE:
        return _THEME_CACHE[key]
    theme = industry or '--'
    try:
        from services.concept_matcher import match_stock_concept
        r = match_stock_concept(code, name or '', industry or '')
        theme = r.get('concept') or industry or '--'
    except Exception as e:
        print(f'[题材] {code} {name} 概念匹配失败: {e}', flush=True)
        theme = industry or '--'
    _THEME_CACHE[key] = theme
    return theme


def make_add_button(code, name, on_added=None):
    """构造'添加/已添加'按钮。已在自选则禁用灰色，否则蓝色可点。"""
    from core.watchlist import get_watchlist_manager
    mgr = get_watchlist_manager()
    already = mgr.is_watchlist(str(code))

    btn = QPushButton('已添加' if already else '+')
    btn.setFixedWidth(50)
    btn.setFixedHeight(22)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if already:
        btn.setEnabled(False)
        btn.setStyleSheet(
            f'QPushButton{{background:{BC.BG_HEADER};color:{BC.TEXT3};'
            f'border:1px solid {BC.BORDER};border-radius:4px;font-size:11px;}}'
        )
    else:
        btn.setStyleSheet(
            f'QPushButton{{background:{BC.BLUE};color:white;border:none;'
            f'border-radius:4px;font-size:12px;font-weight:bold;padding:0 6px;}}'
            f'QPushButton:hover{{background:#1a5ce6;}}'
        )

        def _do_add():
            try:
                mgr.add_stock(str(code), name or str(code))
            except Exception as e:
                print(f'[自选] 添加 {code} 失败: {e}', flush=True)
            btn.setText('已添加')
            btn.setEnabled(False)
            btn.setStyleSheet(
                f'QPushButton{{background:{BC.BG_HEADER};color:{BC.TEXT3};'
                f'border:1px solid {BC.BORDER};border-radius:4px;font-size:11px;}}'
            )
            if on_added:
                try:
                    on_added()
                except Exception:
                    pass

        btn.clicked.connect(_do_add)
    return btn
