"""core/watchlist.py - 自选股管理兼容层
V2.8：为旧UI模块提供兼容接口，实际调用现有服务
"""
import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_FILE = os.path.join(PROJECT_ROOT, 'data', 'watchlist.json')


class WatchlistManager:
    """自选股管理器（兼容层）"""

    def __init__(self):
        self.stocks = []
        self._change_callbacks = []  # V2.8：自选股变化回调列表
        self.load()

    def load(self):
        """从JSON加载自选股"""
        try:
            if os.path.exists(WATCHLIST_FILE):
                with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                    self.stocks = json.load(f)
        except Exception as e:
            print(f"[Watchlist] 加载失败: {e}", flush=True)
            self.stocks = []

    def save(self):
        """保存自选股到JSON"""
        try:
            os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.stocks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Watchlist] 保存失败: {e}", flush=True)

    def get_stocks(self):
        """获取自选股列表"""
        return self.stocks

    def get_codes(self):
        """获取自选股代码列表"""
        return [s.get('code', '') for s in self.stocks if s.get('code')]

    def add_stock(self, code, name=''):
        """添加自选股"""
        if not code:
            return False
        # 检查是否已存在
        for s in self.stocks:
            if s.get('code') == code:
                return False
        self.stocks.append({'code': code, 'name': name or code})
        self.save()
        self._notify_change()  # V2.8：通知自选股变化
        return True

    def remove_stock(self, code):
        """移除自选股"""
        original_len = len(self.stocks)
        self.stocks = [s for s in self.stocks if s.get('code') != code]
        if len(self.stocks) < original_len:
            self.save()
            self._notify_change()  # V2.8：通知自选股变化
            return True
        return False

    def is_watchlist(self, code):
        """判断是否在自选股中"""
        return any(s.get('code') == code for s in self.stocks)

    # ===== V2.7.1：补齐WatchlistWidget所需方法 =====

    def add_change_callback(self, callback):
        """注册自选股变化回调（WatchlistWidget所需）"""
        if callback and callback not in self._change_callbacks:
            self._change_callbacks.append(callback)
            print(f"[Watchlist] 注册变化回调: {callback.__name__ if hasattr(callback, '__name__') else str(callback)}", flush=True)

    def remove_change_callback(self, callback):
        """V2.9.4 移除自选股变化回调（面板销毁时调用，防止管理器持有已销毁面板的引用）"""
        if callback and callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
            print(f"[Watchlist] 移除变化回调: {callback.__name__ if hasattr(callback, '__name__') else str(callback)}", flush=True)

    def _notify_change(self):
        """通知所有回调：自选股已变化"""
        for cb in self._change_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[Watchlist] 回调执行失败: {e}", flush=True)

    def get_all(self):
        """获取所有自选股（WatchlistWidget所需，别名get_stocks）"""
        return self.get_stocks()

    def remove(self, code):
        """移除自选股（WatchlistWidget所需，别名remove_stock）"""
        return self.remove_stock(code)


_watchlist_manager = None


def get_watchlist_manager():
    """获取自选股管理器单例"""
    global _watchlist_manager
    if _watchlist_manager is None:
        _watchlist_manager = WatchlistManager()
    return _watchlist_manager
