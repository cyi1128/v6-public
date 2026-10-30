# -*- coding: utf-8 -*-
"""
菜单功能路由中心 V1.0
统一管理菜单点击事件，连接已有功能模块
禁止修改核心策略、评分模型、K线模块
"""
import os
import sys
import traceback
from datetime import datetime

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def log_error(module, error):
    """记录错误日志"""
    try:
        log_file = os.path.join(LOG_DIR, 'menu_error.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] [{module}] {error}\n')
            f.write(traceback.format_exc() + '\n')
    except Exception:
        pass


class MenuRouter:
    """菜单功能路由中心"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 主窗口引用（由主窗口设置）
        self.main_window = None

        # 缓存数据
        self._stock_pool_cache = None  # 选股池结果缓存
        self._stock_pool_time = None  # 选股池结果时间

        print("[MenuRouter] 菜单路由中心初始化完成")

    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window

    # ============================================================
    # 🎯 选股复盘 - AI选股池
    # ============================================================
    def open_ai_stock_pool(self):
        """打开AI选股池页面"""
        try:
            if not self.main_window:
                log_error('stock_pool', '主窗口引用为空')
                return

            # 跳转到选股池Tab
            self.main_window.tabs.setCurrentIndex(1)

            # 如果有缓存结果，直接显示（不重复扫描）
            if self._stock_pool_cache and self._stock_pool_time:
                print(f"[MenuRouter] 使用缓存的选股池结果（{self._stock_pool_time}）")
                # TODO: 把缓存结果填充到页面
                pass

            print("[MenuRouter] 打开AI选股池页面")

        except Exception as e:
            log_error('stock_pool', str(e))
            print(f"[MenuRouter] 打开AI选股池失败: {e}")

    def set_stock_pool_cache(self, data):
        """设置选股池结果缓存"""
        self._stock_pool_cache = data
        self._stock_pool_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[MenuRouter] 选股池结果已缓存（{self._stock_pool_time}）")

    def get_stock_pool_cache(self):
        """获取选股池结果缓存"""
        return self._stock_pool_cache, self._stock_pool_time

    # ============================================================
    # 📊 市场情绪 - 市场情绪仪表盘
    # ============================================================
    def open_market_dashboard(self):
        """打开市场情绪仪表盘"""
        try:
            if not self.main_window:
                log_error('market_dashboard', '主窗口引用为空')
                return

            # 跳转到市场情绪Tab
            self.main_window.tabs.setCurrentIndex(4)

            print("[MenuRouter] 打开市场情绪仪表盘")

        except Exception as e:
            log_error('market_dashboard', str(e))
            print(f"[MenuRouter] 打开市场情绪仪表盘失败: {e}")

    # ============================================================
    # 📈 决策中心 - 交易决策仪表盘
    # ============================================================
    def open_dashboard(self):
        """打开交易决策仪表盘"""
        try:
            if not self.main_window:
                log_error('dashboard', '主窗口引用为空')
                return

            # 跳转到决策中心Tab
            self.main_window.tabs.setCurrentIndex(5)

            print("[MenuRouter] 打开交易决策仪表盘")

        except Exception as e:
            log_error('dashboard', str(e))
            print(f"[MenuRouter] 打开决策仪表盘失败: {e}")

    # ============================================================
    # 🔔 监控预警 - 预警中心
    # ============================================================
    def open_warning_center(self):
        """打开预警中心"""
        try:
            if not self.main_window:
                log_error('warning_center', '主窗口引用为空')
                return

            # 跳转到预警中心Tab
            self.main_window.tabs.setCurrentIndex(6)

            print("[MenuRouter] 打开预警中心")

        except Exception as e:
            log_error('warning_center', str(e))
            print(f"[MenuRouter] 打开预警中心失败: {e}")

    # ============================================================
    # 💹 交易辅助 - 交易辅助工具
    # ============================================================
    def open_trade_helper(self):
        """打开交易辅助中心"""
        try:
            if not self.main_window:
                log_error('trade_helper', '主窗口引用为空')
                return

            # 跳转到交易辅助Tab
            self.main_window.tabs.setCurrentIndex(5)

            print("[MenuRouter] 打开交易辅助中心")

        except Exception as e:
            log_error('trade_helper', str(e))
            print(f"[MenuRouter] 打开交易辅助中心失败: {e}")


# 全局单例
def get_menu_router():
    """获取菜单路由单例"""
    return MenuRouter()
