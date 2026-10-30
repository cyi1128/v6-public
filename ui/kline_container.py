"""
K线容器组件 - 安全切换机制
ECharts优先，QPainter备用，失败自动降级
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class KlineContainer(QWidget):
    """K线容器 - ECharts优先，QPainter备用
    
    功能：
    - 优先使用ECharts专业K线
    - ECharts加载失败自动降级为QPainter
    - 统一的set_kline_data接口
    - 详细的日志输出
    - 超时保护机制
    - 异步初始化，避免阻塞主线程
    """
    
    cursor_index_changed = pyqtSignal(int)  # 光标位置变化信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.echarts_widget = None
        self.qpainter_widget = None
        self.current_widget = None
        self.use_echarts = False
        self.is_initialized = False
        self.pending_data = None
        self.pending_code = ''            # 与 pending_data 配对：缓存期间的股票代码（板性涨停阈值用）
        self.pending_time_share_data = None  # P4任务3：分时数据独立缓存，避免与K线数据互相覆盖
        self.timeout_timer = None
        
        # 主布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 初始化
        print("[KLINE] ========== KlineContainer初始化 ==========")
        print("[KLINE] 正在初始化专业K线...")
        
        # 超时保护：5秒还没初始化成功，自动切换QPainter
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        self.timeout_timer.start(5000)
        print("[KLINE] 超时保护已启动（5秒）")
        
        # 【K线恢复·V2.9.6】ECharts优先，QPainter备用。
        # 历史：V2.9.5曾因怀疑QWebEngineView导致最大化段错误而禁用ECharts，
        # 但实测真正崩溃根因是 QSettings restoreState 列数不匹配（已修复+清注册表）。
        # main.py 已设置 AA_ShareOpenGLContexts，QtWebEngine 可安全使用。
        # 若 ECharts 仍初始化失败，_try_echarts 内部自动降级 QPainter，不影响使用。
        QTimer.singleShot(500, self._try_echarts)
    
    def _try_echarts(self):
        """尝试初始化ECharts（异步调用）"""
        try:
            from ui.echarts_kline import EChartsKlineWidget
            
            print("[KLINE] 尝试创建ECharts专业K线...")
            self.echarts_widget = EChartsKlineWidget(self)
            
            # 立即处理事件，确保QWebEngineView初始化不阻塞
            QApplication.processEvents()
            
            # 监听ECharts加载状态
            # 由于ECharts是异步加载，我们延迟检查（缩短到1秒，更快响应）
            QTimer.singleShot(1000, self._check_echarts_status)
            
            print("[KLINE] ✅ ECharts组件创建成功，等待初始化...")
            
        except Exception as e:
            print(f"[KLINE] ❌ ECharts创建失败: {e}")
            import traceback
            traceback.print_exc()
            print("[KLINE] 🔄 自动切换为QPainter自绘K线")
            self._fallback_to_qpainter()
    
    def _check_echarts_status(self):
        """检查ECharts状态"""
        if self.echarts_widget and hasattr(self.echarts_widget, 'web_view'):
            # 检查页面是否加载成功
            print("[KLINE] 检查ECharts初始化状态...")
            
            # 显示ECharts组件
            self.layout.addWidget(self.echarts_widget)
            self.current_widget = self.echarts_widget
            self.use_echarts = True
            self.is_initialized = True
            
            # 连接光标位置变化信号
            if hasattr(self.echarts_widget, 'cursor_index_changed'):
                self.echarts_widget.cursor_index_changed.connect(self.cursor_index_changed.emit)
            
            # 停止超时计时器
            self.timeout_timer.stop()
            
            print("[KLINE] ✅ ECharts K线加载成功")
            print("[KLINE] ========== 初始化完成 ==========")
            
            # 如果有待处理的数据，立即设置
            if self.pending_data:
                print("[KLINE] 应用待处理的K线数据...")
                self.set_kline_data(self.pending_data, self.pending_code)
                self.pending_data = None
                self.pending_code = ''
            # P4任务3：应用待处理的分时数据
            if self.pending_time_share_data:
                print("[KLINE] 应用待处理的分时数据...")
                self.set_time_share_data(self.pending_time_share_data)
                self.pending_time_share_data = None
        else:
            print("[KLINE] ⚠️  ECharts状态异常，切换为QPainter")
            self._fallback_to_qpainter()
    
    def _fallback_to_qpainter(self):
        """降级为QPainter自绘K线"""
        print("[KLINE] 🔄 降级为QPainter自绘K线...")
        
        try:
            # KlineChartWidget定义在watchlist_panel中
            from ui.watchlist_panel import KlineChartWidget
            
            self.qpainter_widget = KlineChartWidget(self)
            self.layout.addWidget(self.qpainter_widget)
            self.current_widget = self.qpainter_widget
            self.use_echarts = False
            self.is_initialized = True
            
            # 停止超时计时器
            if self.timeout_timer:
                self.timeout_timer.stop()
            
            print("[KLINE] ✅ QPainter K线加载成功")
            print("[KLINE] ========== 初始化完成 ==========")
            
            # 如果有待处理的数据，立即设置
            if self.pending_data:
                print("[KLINE] 应用待处理的K线数据...")
                self.set_kline_data(self.pending_data, self.pending_code)
                self.pending_data = None
                self.pending_code = ''
            # P4任务3：应用待处理的分时数据
            if self.pending_time_share_data:
                print("[KLINE] 应用待处理的分时数据...")
                self.set_time_share_data(self.pending_time_share_data)
                self.pending_time_share_data = None
                
        except Exception as e:
            print(f"[KLINE] ❌ QPainter也创建失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 显示错误信息
            error_label = QLabel('K线组件初始化失败')
            error_label.setStyleSheet('color: #FF3B30; font-size: 14px;')
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(error_label)
            self.is_initialized = True
            if self.timeout_timer:
                self.timeout_timer.stop()
    
    def _on_timeout(self):
        """超时处理：强制标记初始化完成，避免无限卡滞"""
        print("[KLINE] ⏰ 初始化超时（5秒），强制标记初始化完成")
        
        if not self.is_initialized:
            # 关键修复：超时后强制标记初始化完成，不再等待，避免程序启动卡滞
            self.is_initialized = True
            if self.timeout_timer:
                self.timeout_timer.stop()
            # 如果ECharts组件已创建，直接使用（即使页面还在加载，后续数据设置会自动渲染）
            if self.echarts_widget:
                try:
                    self.layout.addWidget(self.echarts_widget)
                    self.current_widget = self.echarts_widget
                    self.use_echarts = True
                    if hasattr(self.echarts_widget, 'cursor_index_changed'):
                        self.echarts_widget.cursor_index_changed.connect(self.cursor_index_changed.emit)
                    print("[KLINE] ✅ 超时降级：使用ECharts组件（页面后台继续加载）")
                except Exception as e:
                    print(f"[KLINE] 超时后添加ECharts组件失败: {e}")
                    self._fallback_to_qpainter()
            else:
                self._fallback_to_qpainter()
            print("[KLINE] ========== 初始化完成（超时降级） ==========")
            # 应用待处理数据
            if self.pending_data:
                try:
                    self.set_kline_data(self.pending_data, self.pending_code)
                    self.pending_data = None
                    self.pending_code = ''
                except Exception as e:
                    print(f"[KLINE] 超时后应用待处理数据失败: {e}")
            # P4任务3：应用待处理的分时数据
            if self.pending_time_share_data:
                try:
                    self.set_time_share_data(self.pending_time_share_data)
                    self.pending_time_share_data = None
                except Exception as e:
                    print(f"[KLINE] 超时后应用待处理分时数据失败: {e}")
    
    def set_kline_data(self, kline_data, code=''):
        """设置K线数据（统一接口）
        
        Args:
            kline_data: dict, 包含 dates, open, high, low, close, volume
            code: 可选，股票代码；透传给内部控件（板性涨停阈值 / 周期切换）
        """
        if not self.is_initialized:
            # 还没初始化完成，先缓存数据
            print("[KLINE] ⏳ 组件未初始化完成，缓存K线数据")
            self.pending_data = kline_data
            self.pending_code = code or self.pending_code
            return
        
        if not self.current_widget:
            print("[KLINE] ⚠️  当前没有可用的K线组件")
            return
        
        try:
            if self.use_echarts:
                # ECharts版本
                self.echarts_widget.set_kline_data(kline_data, code)
            else:
                # QPainter版本
                # QPainter的set_data接口可能不同，需要适配
                if hasattr(self.qpainter_widget, 'set_data'):
                    self.qpainter_widget.set_data(kline_data)
                elif hasattr(self.qpainter_widget, 'set_kline_data'):
                    self.qpainter_widget.set_kline_data(kline_data, code)
                else:
                    print("[KLINE] ⚠️  QPainter组件没有set_data方法")
                    
        except Exception as e:
            print(f"[KLINE] ❌ 设置K线数据失败: {e}")
            import traceback
            traceback.print_exc()
    
    def set_time_share_data(self, time_share_data):
        """设置分时图数据（统一接口）
        
        Args:
            time_share_data: dict, 包含 times, prices, avg_prices, volumes, pre_close
        """
        if not self.is_initialized:
            print("[KLINE] ⏳ 组件未初始化完成，缓存分时数据")
            self.pending_time_share_data = time_share_data
            return
        
        if not self.current_widget:
            print("[KLINE] ⚠️  当前没有可用的K线组件")
            return
        
        try:
            if self.use_echarts:
                self.echarts_widget.set_time_share_data(time_share_data)
            else:
                print("[KLINE] ⚠️  QPainter版本不支持分时图")
                    
        except Exception as e:
            print(f"[KLINE] ❌ 设置分时数据失败: {e}")
            import traceback
            traceback.print_exc()
    
    def get_kline_type(self):
        """获取当前使用的K线类型"""
        if self.use_echarts:
            return 'echarts'
        else:
            return 'qpainter'
    
    def is_using_echarts(self):
        """是否使用ECharts"""
        return self.use_echarts
