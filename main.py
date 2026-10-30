"""
量化盯盘 V6.0 主升龙头全自动系统
主程序入口
"""
# ============================================================
# [崩溃捕获] 最早期启用 faulthandler 写 crash_verbose.log
# 必须在任何业务 import 之前完成，以便捕获 PyQt/原生扩展的段错误
# ============================================================
import faulthandler as _faulthandler
import os as _os

_PROJECT_ROOT_PRE = _os.path.dirname(_os.path.abspath(__file__))
_CRASH_VERBOSE_LOG = _os.path.join(_PROJECT_ROOT_PRE, 'crash_verbose.log')
try:
    _crash_fp = open(_CRASH_VERBOSE_LOG, 'w', encoding='utf-8', buffering=1)
    _faulthandler.enable(file=_crash_fp, all_threads=True)
    print('[faulthandler] 已启用，崩溃堆栈将写入: ' + _CRASH_VERBOSE_LOG, flush=True)
except Exception as _e:
    try:
        _faulthandler.enable(all_threads=True)
        print('[faulthandler] 文件日志失败，降级到stderr: ' + str(_e), flush=True)
    except Exception:
        pass

import sys
import os
import traceback
import time

# 将项目根目录加入路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 启动性能诊断（只测量不修改业务逻辑）
try:
    from tools.startup_profiler import get_profiler, step_start, step_end
    profiler = get_profiler()
    PROFILER_ENABLED = True
except Exception as e:
    PROFILER_ENABLED = False
    print(f"[Profiler] 启动诊断加载失败: {e}")

def p_start(name):
    if PROFILER_ENABLED:
        step_start(name)

def p_end(name, extra=''):
    if PROFILER_ENABLED:
        step_end(name, extra)

# crash日志文件
CRASH_LOG = os.path.join(PROJECT_ROOT, 'crash.log')


def save_crash_log(e):
    """保存崩溃日志到文件"""
    try:
        with open(CRASH_LOG, 'w', encoding='utf-8') as f:
            f.write(f"崩溃时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"错误类型: {type(e).__name__}\n")
            f.write(f"错误信息: {e}\n")
            f.write("\n详细堆栈:\n")
            traceback.print_exc(file=f)
        print(f"\n崩溃日志已保存到: {CRASH_LOG}")
    except Exception as ex:
        print(f"保存崩溃日志失败: {ex}")


def main():
    """主函数"""
    # V2.3 企业微信四时段推送测试入口（不启动GUI，直接测试推送）
    if '--test-push' in sys.argv:
        idx = sys.argv.index('--test-push')
        slot = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'premarket'
        slot_map = {'premarket': 'premarket', '0930': '09:30', '1445': '14:45', 'close': 'close'}
        slot_name = slot_map.get(slot, slot)
        print(f"[测试推送] 开始测试 {slot_name} 时段企业微信双卡推送...")
        print(f"[测试推送] 注意：使用真实数据，不模拟行情")

        from services.v22_combat_service import get_v22_combat_service
        svc = get_v22_combat_service()

        # 获取市场数据
        print("[测试推送] 获取市场数据...")
        market_data = svc._get_market_data_snapshot()
        print(f"[测试推送] 市场数据获取完成 (盘前:{market_data.get('is_premarket', False)})")

        # AI-520扫描（不推送，只获取信号）
        print("[测试推送] 执行AI-520真实扫描...")
        scan_result = svc.run_ai520_scan(scan_source=slot_name, push_wechat=False)
        ai520_signals = scan_result.get('signals', [])
        grades = scan_result.get('grades', {})
        print(f"[AI520] 全市场扫描: {scan_result.get('total_scanned', 0)}")
        print(f"[AI520] 有效候选: {len(ai520_signals)}")
        print(f"[AI520] S+:{grades.get('S+',0)} S:{grades.get('S',0)} A:{grades.get('A',0)} B:{grades.get('B',0)} C:{grades.get('C',0)}")

        # 推送双卡消息
        print(f"[WECHAT] 生成{slot_name}正式双卡消息...")
        push_result = svc.push_dual_card_to_wechat(slot_name, market_data, ai520_signals)

        if push_result.get('success'):
            print(f"\n[测试推送] ✅ {slot_name} 时段双卡推送成功！")
            card_results = push_result.get('card_results', [])
            for i, r in enumerate(card_results, 1):
                print(f"  卡{i}: errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
        else:
            print(f"\n[测试推送] ❌ {slot_name} 时段推送失败: {push_result.get('error', '未知错误')}")
            card_results = push_result.get('card_results', [])
            for i, r in enumerate(card_results, 1):
                print(f"  卡{i}: success={r.get('success')} errcode={r.get('errcode')} errmsg={r.get('errmsg')}")

        print("\n[测试推送] 测试完成，程序退出")
        return

    print("[启动日志 1/10] 程序启动...")

    # V2.7.1：运行身份自证
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    print("\n" + "=" * 50)
    print("  量化交易作战中控台 V2.8")
    print("=" * 50)
    print(f"  VERSION: V2.8")
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  MAIN_FILE: {os.path.join(PROJECT_ROOT, 'main.py')}")
    print(f"  PYTHON: {sys.executable}")
    print(f"  AI520_ENGINE: {os.path.join(PROJECT_ROOT, 'strategy', 'ai_520_engine.py')}")
    print(f"  AI520_SCAN: {os.path.join(PROJECT_ROOT, 'strategy', 'ai_520_scan_service.py')}")
    print(f"  AI520_BUY_SCORE: {os.path.join(PROJECT_ROOT, 'strategy', 'ai_520_buy_score.py')}")
    print(f"  INDUSTRY_FILTER: {os.path.join(PROJECT_ROOT, 'services', 'industry_filter_service.py')}")
    print(f"  WATCHLIST: {os.path.join(PROJECT_ROOT, 'core', 'watchlist.py')}")
    print("=" * 50 + "\n")

    # 【2026-09-24 清理 v28 死引用】原来在这里加载 v28.config 并打印各模块开关状态，
    # v28 包已不存在，这段此前每次都打印一条 "配置加载失败" 的噪音。
    # 现整段移除。如日后找回 v28 包，按原实现恢复即可。

    try:
        p_start("PyQt6导入")
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFont
        p_end("PyQt6导入")
    except ImportError:
        print("错误: 未安装 PyQt6")
        print("请运行: pip install PyQt6 pandas numpy")
        input("按回车键退出...")
        return

    try:
        print("[启动日志 2/10] 创建QApplication...")
        p_start("QApplication创建")
        from PyQt6.QtCore import Qt
        # 必须在创建QApplication之前设置，否则QWebEngine会报错
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv)
        p_end("QApplication创建")
        print("[启动日志 3/10] QApplication创建成功")

        # 设置字体
        font = QFont('Microsoft YaHei', 10)
        app.setFont(font)

        # 设置应用样式
        app.setStyle('Fusion')

        # 应用量化终端主题（皮肤管理器，支持多套主题切换）
        # P3任务3：若存在浅色QSS则跳过SkinManager默认深色主题，避免两套主题叠加
        try:
            p_start("主题应用")
            from ui.theme.skin_manager import SkinManager
            sm = SkinManager()  # 保留实例化，其他地方可能用到
            _light_qss = os.path.join(PROJECT_ROOT, 'ui', 'styles_light.qss')
            if os.path.exists(_light_qss):
                print("[启动日志 3.1/10] 检测到浅色QSS，跳过SkinManager深色主题（避免叠加）")
            else:
                if sm.apply_theme(app):
                    print(f"[启动日志 3.1/10] 主题已应用: {sm.get_current_skin_name()}")
                else:
                    print("[启动日志 3.1/10] 主题应用失败")
            p_end("主题应用")
        except Exception as e:
            print(f"[启动日志 3.1/10] 主题应用失败: {e}")

        print("[启动日志 4/10] 导入主窗口模块...")
        # V2.7.1 浅色玻璃拟态UI
        try:
            qss_path = os.path.join(PROJECT_ROOT, 'ui', 'styles_light.qss')
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    app.setStyleSheet(f.read())
                print("[启动日志 3.2/10] 浅色玻璃拟态QSS已加载")
        except Exception as e:
            print(f"[启动日志 3.2/10] 浅色QSS加载失败: {e}")

        # V0.6.1 开启动态权重（AI学习反馈接入）
        try:
            p_start("AI动态权重初始化")
            from strategy.ai_buy_signal import AIBuySignalEngine
            AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = True
            print("[启动日志 4.1/10] AI动态权重已开启（V0.6.1）")
            p_end("AI动态权重初始化")
        except Exception as e:
            print(f"[启动日志 4.1/10] 动态权重开启失败: {e}")

        p_start("主窗口模块导入")
        from ui.battle_console_v2 import BattleConsoleWindowV2
        p_end("主窗口模块导入")
        print("[启动日志 5/10] 作战中控台V2主窗口模块导入成功")

        # 创建主窗口（量化交易作战中控台 V2 - 真实数据版）
        print("[启动日志 6/10] 创建作战中控台V2主窗口...")
        p_start("BattleConsoleWindowV2创建")
        window = BattleConsoleWindowV2()
        p_end("BattleConsoleWindowV2创建")
        print("[启动日志 7/10] 作战中控台V2主窗口创建成功")

        p_start("主窗口show")
        window.show()
        p_end("主窗口show")
        print("[启动日志 8/10] 主窗口显示成功")

        # 【2026-09-24】30分钟新闻简报服务已按用户要求停用（不再需要）
        # 服务文件未删除：services/news_30min_digest.py（要恢复就取消下面注释）
        # # 兜底：强制启动30分钟新闻简报服务，防止主窗口改动导致服务没启动
        # try:
        #     from services.news_30min_digest import News30MinDigest
        #     if not hasattr(window, '_digest_service') or window._digest_service is None:
        #         window._digest_service = News30MinDigest()
        #         window._digest_service.start()
        #         print("[启动日志 8.1/10] 30分钟新闻简报服务已兜底启动", flush=True)
        # except Exception as e:
        #     print(f"[启动日志 8.1/10] 简报服务兜底启动失败: {e}", flush=True)

        # 后台线程：K线增量更新(不阻塞UI)
        # V2.8 A3：盘前全量校准 - 9:20-9:25启动时执行全市场日K线校准
        def _is_premarket_calibration_window():
            """判断是否在盘前校准窗口（9:20-9:25，周一至周五）"""
            try:
                from datetime import datetime, time as dt_time
                now = datetime.now()
                if now.weekday() >= 5:
                    return False
                t = now.time()
                return dt_time(9, 20) <= t <= dt_time(9, 25)
            except Exception:
                return False

        def _background_kline_incremental_update():
            try:
                import time
                # V2.8 A3：盘前校准窗口缩短等待时间，尽快开始更新
                premarket = _is_premarket_calibration_window()
                if premarket:
                    print("[K线校准] 盘前校准窗口(9:20-9:25)，立即启动全市场K线校准", flush=True)
                    time.sleep(1)  # 盘前窗口只等1秒
                else:
                    time.sleep(3)  # 等待UI完全加载
                from services.kline_cache_service import incremental_update_kline, get_all_cached_codes, get_last_date
                codes = get_all_cached_codes()
                # V2.8：日期校验 - 先检查是否需要更新
                try:
                    from datetime import datetime, timedelta
                    sample_codes = ['000001', '600000', '000002']
                    kline_dates = []
                    for code in sample_codes:
                        last_date = get_last_date(code)
                        if last_date:
                            kline_dates.append(last_date)
                    if kline_dates:
                        latest_kline_date = max(kline_dates)
                        today_str = datetime.now().strftime('%Y-%m-%d')
                        weekday = datetime.now().weekday()
                        if weekday >= 5:
                            expected_date = (datetime.now() - timedelta(days=weekday-4)).strftime('%Y-%m-%d')
                        else:
                            expected_date = today_str
                        
                        if latest_kline_date >= expected_date:
                            print(f"[K线增量更新] K线已是最新({latest_kline_date})，跳过更新", flush=True)
                            return
                        else:
                            print(f"[K线增量更新] K线陈旧({latest_kline_date} < {expected_date})，开始更新 {len(codes)} 只股票...", flush=True)
                    else:
                        print(f"[K线增量更新] 无法获取K线日期，开始更新 {len(codes)} 只股票...", flush=True)
                except Exception as e:
                    print(f"[K线增量更新] 日期校验失败，直接更新: {e}", flush=True)
                # V2.8：互斥机制 - AI520扫描运行时等待，避免pytdx多线程竞争
                import time
                wait_count = 0
                while hasattr(window, '_ai520_scanning') and window._ai520_scanning:
                    wait_count += 1
                    if wait_count > 60:
                        print("[K线增量更新] 等待AI520扫描超时，跳过本次更新", flush=True)
                        break
                    time.sleep(5)
                    if wait_count % 6 == 0:
                        print(f"[K线增量更新] 等待AI520扫描完成... ({wait_count*5}s)", flush=True)
                else:
                    if wait_count > 0:
                        print(f"[K线增量更新] AI520扫描已完成，继续更新（等待{wait_count*5}s）", flush=True)
                # V2.8 A3：盘前校准窗口使用verbose=True输出详细进度
                result = incremental_update_kline(codes, verbose=premarket)
                mode = "盘前全量校准" if premarket else "增量更新"
                print(f"[K线{mode}] 完成: 更新={result['updated']} "
                      f"无新数据={result['no_new_data']} 失败={result['failed']} "
                      f"新增K线={result['new_kline_total']}")
            except Exception as e:
                print(f"[K线增量更新] 后台更新异常(不影响主程序): {e}")

        import threading
        _kline_update_thread = threading.Thread(target=_background_kline_incremental_update, daemon=True)
        _kline_update_thread.start()
        # V2.8 A3：根据启动时间显示校准模式
        try:
            from datetime import datetime, time as dt_time
            now = datetime.now()
            weekday = now.weekday()
            t = now.time()
            if weekday < 5 and dt_time(9, 20) <= t <= dt_time(9, 25):
                print("[启动日志 8.5/10] K线盘前全量校准线程已启动（9:20-9:25窗口）", flush=True)
            elif weekday < 5 and t > dt_time(9, 25):
                print("[启动日志 8.5/10] K线增量更新后台线程已启动（9:25后跳过全量校准）", flush=True)
            else:
                print("[启动日志 8.5/10] K线增量更新后台线程已启动", flush=True)
        except Exception:
            print("[启动日志 8.5/10] K线增量更新后台线程已启动", flush=True)

        # 后台线程：AI520盘中实时监控推送（交易时段每5分钟扫描，不阻塞UI）
        def _background_ai520_realtime_monitor():
            try:
                import time
                time.sleep(5)  # 等待UI和K线更新稳定
                from strategy.ai520_realtime_monitor import get_realtime_monitor
                monitor = get_realtime_monitor()
                monitor.start()
                print("[AI520实时监控] 已在后台启动，交易时段每5分钟扫描推送", flush=True)
            except Exception as e:
                print(f"[AI520实时监控] 启动异常(不影响主程序): {e}", flush=True)

        _realtime_monitor_thread = threading.Thread(target=_background_ai520_realtime_monitor, daemon=True)
        _realtime_monitor_thread.start()
        print("[启动日志 8.6/10] AI520实时监控后台线程已启动")

        # 后台线程：异动检测（只喂数据，不显示任何界面）
        # anchor_tracker 的今日异动池靠它填充；盘后「基准阳跟踪 / 日K建仓」依赖它。
        # 三模块合并后旧「盘中机会」UI 不再加载，必须在这里补上，否则日K建仓会逐日退化。
        def _background_anomaly_detect():
            try:
                import time as _t
                _t.sleep(8)                      # 等 UI 与 K 线更新稳定
                from services.intraday_opportunity_engine import get_engine
                _eng = get_engine()
                print("[异动检测] 后台线程已启动（仅喂 anchor_tracker，无界面）", flush=True)
                while True:
                    try:
                        _eng.scan()              # 内部自带 25 秒节流 + 锁
                    except Exception as _e:
                        print(f"[异动检测] 单次扫描异常(忽略): {_e}", flush=True)
                    _t.sleep(25)
            except Exception as e:
                print(f"[异动检测] 启动异常(不影响主程序): {e}", flush=True)

        _anomaly_thread = threading.Thread(target=_background_anomaly_detect, daemon=True)
        _anomaly_thread.start()
        print("[启动日志 8.7/10] 异动检测后台线程已启动")

        print("[启动日志 9/10] 程序启动完成，进入事件循环...")

        # 打印启动性能报告
        if PROFILER_ENABLED:
            profiler.print_report()

        # 运行
        exit_code = app.exec()
        print(f"[启动日志 10/10] 程序正常退出，退出码: {exit_code}")
        sys.exit(exit_code)

    except Exception as e:
        print("\n" + "=" * 60)
        print("程序崩溃！")
        print("=" * 60)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print("\n详细错误堆栈:")
        traceback.print_exc()
        print("=" * 60)

        # 保存崩溃日志
        save_crash_log(e)

        print("\n请将crash.log文件内容发给开发者排查问题")
        input("\n按回车键退出...")


if __name__ == '__main__':
    main()
