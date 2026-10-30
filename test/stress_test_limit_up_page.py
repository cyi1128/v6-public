# -*- coding: utf-8 -*-
"""
V1.3-A-5-DEV Step1：涨停原因页面压力测试脚本

测试目标：
- 模拟100只涨停股票
- 连续点击切换N次
- 后台线程稳定性
- 内存占用监控
- UI刷新耗时统计

两种模式：
- fast: 使用模拟card_data，只测试UI渲染性能（推荐用于CI）
- full: 调用实际analyze_and_format，测试全链路（较慢）

用法：
    python test/stress_test_limit_up_page.py --mode fast --clicks 1000
    python test/stress_test_limit_up_page.py --mode full --clicks 50
"""
import os
import sys
import time
import random
import argparse
import tracemalloc
from datetime import datetime
from collections import defaultdict

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

# 必须在QApplication创建前设置
from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.pages.limit_up_reason_page import LimitUpReasonPage
from test.mock_limit_up_data import generate_mock_limit_up_stocks, generate_mock_card_data


class StressTester:
    """压力测试器"""

    def __init__(self, mode='fast', total_clicks=1000, stock_count=100, seed=42):
        self.mode = mode
        self.total_clicks = total_clicks
        self.stock_count = stock_count
        self.seed = seed

        # 测试结果统计
        self.results = {
            'total_clicks': 0,
            'success_count': 0,
            'fail_count': 0,
            'render_times': [],
            'errors': [],
            'memory_snapshots': [],
            'thread_errors': [],
        }

        # 内存监控
        self._mem_start = 0
        self._mem_peak = 0

        # 页面引用
        self.page = None
        self.stocks = []
        self._current_click = 0
        self._click_start_time = 0
        self._running = False

    def run(self):
        """运行压力测试"""
        print('=' * 70)
        print('V1.3-A-5-DEV Step1：涨停原因页面压力测试')
        print('=' * 70)
        print(f"模式: {self.mode}")
        print(f"股票数量: {self.stock_count}")
        print(f"点击次数: {self.total_clicks}")
        print(f"随机种子: {self.seed}")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print('=' * 70)

        app = QApplication(sys.argv)

        # 启动内存监控
        tracemalloc.start()
        self._mem_start = tracemalloc.get_traced_memory()[0]

        # 创建页面
        print('\n[1/4] 初始化页面...')
        self.page = LimitUpReasonPage()
        # 禁用自动加载（避免网络请求阻塞测试）
        self.page._is_loading = True
        app.processEvents()
        print('  ✅ 页面初始化完成')

        # 加载模拟股票
        print(f'\n[2/4] 加载 {self.stock_count} 只模拟涨停股票...')
        self.stocks = generate_mock_limit_up_stocks(self.stock_count, seed=self.seed)
        self.page._on_stocks_loaded(self.stocks)
        app.processEvents()
        print(f'  ✅ 股票列表加载完成，共 {self.page.stock_list.count()} 只')

        # 连板分布
        from collections import Counter
        lbc_counter = Counter(s['lbc'] for s in self.stocks)
        print('  连板分布:')
        for lbc in sorted(lbc_counter.keys(), reverse=True):
            print(f'    {lbc}连板: {lbc_counter[lbc]}只')

        # 开始压力测试
        print(f'\n[3/4] 开始压力测试（{self.total_clicks}次点击）...')
        self._running = True
        self._current_click = 0

        # 直接循环点击（offscreen模式下QTimer递归不可靠）
        for i in range(self.total_clicks):
            self._current_click = i + 1
            self._click_start_time = time.time()

            # 随机选择一只股票
            stock_idx = random.randint(0, len(self.stocks) - 1)
            stock = self.stocks[stock_idx]
            item = self.page.stock_list.item(stock_idx)

            if not item:
                self.results['fail_count'] += 1
                self.results['errors'].append(f"第{self._current_click}次: 列表项不存在 idx={stock_idx}")
                continue

            if self.mode == 'fast':
                self._fast_render(stock, app)
            else:
                self.page._on_stock_clicked(item)
                self._wait_for_analysis(stock, app)

            app.processEvents()

        self._running = False

        # 停止内存监控
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self._mem_peak = peak

        # 输出报告
        print('\n[4/4] 生成测试报告...')
        self._print_report(current, peak)

        return self._get_exit_code()

    def _schedule_next_click(self, app):
        """调度下一次点击"""
        if self._current_click >= self.total_clicks:
            self._running = False
            return

        self._current_click += 1
        self._click_start_time = time.time()

        # 随机选择一只股票
        stock_idx = random.randint(0, len(self.stocks) - 1)
        stock = self.stocks[stock_idx]
        item = self.page.stock_list.item(stock_idx)

        if not item:
            self.results['fail_count'] += 1
            self.results['errors'].append(f"第{self._current_click}次: 列表项不存在 idx={stock_idx}")
            self._schedule_next_click(app)
            return

        if self.mode == 'fast':
            # 快速模式：直接用模拟数据渲染，不调用实际分析
            self._fast_render(stock, app)
        else:
            # 完整模式：调用实际分析
            self.page._on_stock_clicked(item)
            # 等待后台线程完成
            self._wait_for_analysis(stock, app)

    def _fast_render(self, stock, app):
        """快速渲染模式"""
        try:
            code = stock['code']
            name = stock['name']
            industry = stock['industry']
            lbc = stock['lbc']

            # 生成模拟卡片数据
            card_data = generate_mock_card_data(code, name, industry, lbc)

            # 直接渲染
            self.page._show_card(card_data)
            app.processEvents()

            render_time = (time.time() - self._click_start_time) * 1000  # ms
            self.results['render_times'].append(render_time)
            self.results['success_count'] += 1
            self.results['total_clicks'] += 1

            # 验证渲染结果
            if not self.page._current_card or not self.page._current_card.card_data:
                self.results['fail_count'] += 1
                self.results['errors'].append(f"第{self._current_click}次: 卡片渲染失败 {name}")

        except Exception as e:
            self.results['fail_count'] += 1
            self.results['errors'].append(f"第{self._current_click}次: 渲染异常 {name} - {e}")

        # 进度输出（每100次）
        if self._current_click % 100 == 0:
            avg_time = sum(self.results['render_times'][-100:]) / min(100, len(self.results['render_times']))
            print(f"  进度: {self._current_click}/{self.total_clicks} | "
                  f"成功: {self.results['success_count']} | "
                  f"失败: {self.results['fail_count']} | "
                  f"平均耗时: {avg_time:.1f}ms")

        # 记录内存快照（每200次）
        if self._current_click % 200 == 0:
            current, _ = tracemalloc.get_traced_memory()
            self.results['memory_snapshots'].append({
                'click': self._current_click,
                'memory_mb': current / 1024 / 1024,
            })

    def _wait_for_analysis(self, stock, app, timeout=30):
        """等待后台分析完成（完整模式）"""
        start = time.time()
        while time.time() - start < timeout:
            app.processEvents()
            if self.page._current_card and self.page._current_card.card_data:
                break
            time.sleep(0.05)

        render_time = (time.time() - self._click_start_time) * 1000
        self.results['render_times'].append(render_time)
        self.results['total_clicks'] += 1

        if self.page._current_card and self.page._current_card.card_data:
            self.results['success_count'] += 1
        else:
            self.results['fail_count'] += 1
            self.results['errors'].append(f"第{self._current_click}次: 分析超时 {stock['name']}")

        if self._current_click % 10 == 0:
            avg_time = sum(self.results['render_times'][-10:]) / min(10, len(self.results['render_times']))
            print(f"  进度: {self._current_click}/{self.total_clicks} | "
                  f"成功: {self.results['success_count']} | "
                  f"平均耗时: {avg_time:.0f}ms")

    def _print_report(self, current_mem, peak_mem):
        """打印测试报告"""
        print('\n' + '=' * 70)
        print('压力测试报告')
        print('=' * 70)

        # 基本统计
        total = self.results['total_clicks']
        success = self.results['success_count']
        fail = self.results['fail_count']
        success_rate = (success / total * 100) if total > 0 else 0

        print(f'\n【基本统计】')
        print(f"  总点击次数: {total}")
        print(f"  成功次数: {success}")
        print(f"  失败次数: {fail}")
        print(f"  成功率: {success_rate:.2f}%")

        # 渲染耗时统计
        if self.results['render_times']:
            times = self.results['render_times']
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)

            # 分位数
            sorted_times = sorted(times)
            p50 = sorted_times[int(len(sorted_times) * 0.5)]
            p90 = sorted_times[int(len(sorted_times) * 0.9)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]

            # 卡顿统计（>3000ms）
            lag_count = sum(1 for t in times if t > 3000)
            lag_rate = lag_count / len(times) * 100

            print(f'\n【渲染耗时】')
            print(f"  平均耗时: {avg_time:.1f}ms")
            print(f"  最小耗时: {min_time:.1f}ms")
            print(f"  最大耗时: {max_time:.1f}ms")
            print(f"  P50: {p50:.1f}ms")
            print(f"  P90: {p90:.1f}ms")
            print(f"  P99: {p99:.1f}ms")
            print(f"  卡顿(>3s): {lag_count}次 ({lag_rate:.2f}%)")

        # 内存统计
        print(f'\n【内存占用】')
        print(f"  起始内存: {self._mem_start / 1024 / 1024:.2f} MB")
        print(f"  当前内存: {current_mem / 1024 / 1024:.2f} MB")
        print(f"  峰值内存: {peak_mem / 1024 / 1024:.2f} MB")
        print(f"  内存增长: {(current_mem - self._mem_start) / 1024 / 1024:.2f} MB")

        if self.results['memory_snapshots']:
            print(f"  内存变化趋势:")
            for snap in self.results['memory_snapshots']:
                print(f"    第{snap['click']}次: {snap['memory_mb']:.2f} MB")

        # 错误详情
        if self.results['errors']:
            print(f'\n【错误详情】(前10条)')
            for i, err in enumerate(self.results['errors'][:10]):
                print(f"  {i+1}. {err}")
            if len(self.results['errors']) > 10:
                print(f"  ... 共 {len(self.results['errors'])} 条错误")

        # 验收结论
        print(f'\n【验收结论】')
        passed = True

        if fail > 0:
            print(f"  ❌ 存在失败: {fail}次")
            passed = False
        else:
            print(f"  ✅ 无失败")

        if self.results['render_times']:
            lag_rate = sum(1 for t in self.results['render_times'] if t > 3000) / len(self.results['render_times']) * 100
            if lag_rate > 1:
                print(f"  ❌ 卡顿率超标: {lag_rate:.2f}% > 1%")
                passed = False
            else:
                print(f"  ✅ 卡顿率达标: {lag_rate:.2f}% ≤ 1%")

        # 内存泄漏检测（简单判断：最后10次和前10次内存对比）
        if len(self.results['memory_snapshots']) >= 2:
            first_mem = self.results['memory_snapshots'][0]['memory_mb']
            last_mem = self.results['memory_snapshots'][-1]['memory_mb']
            mem_growth = last_mem - first_mem
            if mem_growth > 50:  # 增长超过50MB视为可能泄漏
                print(f"  ⚠️  内存增长明显: {mem_growth:.2f} MB，建议进一步排查")
            else:
                print(f"  ✅ 内存稳定: 增长 {mem_growth:.2f} MB")

        print(f'\n{"✅ 测试通过" if passed else "❌ 测试未通过"}')
        print('=' * 70)

    def _get_exit_code(self):
        """获取退出码"""
        return 0 if self.results['fail_count'] == 0 else 1


def main():
    parser = argparse.ArgumentParser(description='涨停原因页面压力测试')
    parser.add_argument('--mode', choices=['fast', 'full'], default='fast',
                        help='测试模式: fast=快速UI渲染, full=完整分析链路')
    parser.add_argument('--clicks', type=int, default=1000,
                        help='总点击次数 (默认1000)')
    parser.add_argument('--stocks', type=int, default=100,
                        help='模拟股票数量 (默认100)')
    parser.add_argument('--seed', type=int, default=42,
                        help='随机种子 (默认42)')

    args = parser.parse_args()

    tester = StressTester(
        mode=args.mode,
        total_clicks=args.clicks,
        stock_count=args.stocks,
        seed=args.seed,
    )
    sys.exit(tester.run())


if __name__ == '__main__':
    main()
