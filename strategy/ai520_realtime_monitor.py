# -*- coding: utf-8 -*-
"""
AI520盘中实时监控推送服务
- 交易时段(9:30-11:30, 13:00-15:00)每5分钟扫描全市场
- 发现新的AI520 S/A级（>=80分）股票立即推送企业微信
- 同一只股票当天只推送一次（去重）
- 不限制推送时间，交易时段内随时发现随时推送
- 后台线程运行，不阻塞UI
"""
import os
import sys
import time
import threading
from services.realtime_quote_refresh import refresh_signal_quotes
from services.industry_guard import get_industry_guard
from services.stock_deep_analysis import generate_deep_analysis, is_ollama_available
from services.stock_profile_generator import get_profile_generator
from services.keyword_manager import get_keyword_manager
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Set

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 交易时段
MORNING_START = dt_time(9, 30)
MORNING_END = dt_time(11, 30)
AFTERNOON_START = dt_time(13, 0)
AFTERNOON_END = dt_time(15, 0)

# 扫描间隔（秒）
SCAN_INTERVAL = 300  # 5分钟

# AI520推送阈值（只推S/A级，>=80分）
AI520_PUSH_THRESHOLD = 80


def is_trading_hours() -> bool:
    """判断当前是否为交易时段"""
    now = datetime.now().time()
    # 周一到周五
    if datetime.now().weekday() >= 5:
        return False
    morning = MORNING_START <= now <= MORNING_END
    afternoon = AFTERNOON_START <= now <= AFTERNOON_END
    return morning or afternoon


class AI520RealtimeMonitor:
    """AI520盘中实时监控推送器"""

    def __init__(self, scan_service=None):
        """
        Args:
            scan_service: AI520ScanService实例，None时自动创建
        """
        self._scan_service = scan_service
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._pushed_today: Set[str] = set()  # 今日已推送股票代码
        self._last_scan_time: Optional[datetime] = None
        self._scan_count = 0
        self._push_count = 0
        self._lock = threading.Lock()

    def _get_scan_service(self):
        """获取或创建AI520扫描服务"""
        if self._scan_service is None:
            from strategy.ai_520_scan_service import AI520ScanService
            self._scan_service = AI520ScanService()
        return self._scan_service

    def _reset_daily_dedup(self):
        """每日重置去重集合"""
        today = datetime.now().strftime('%Y-%m-%d')
        # 简单实现：如果日期变了就重置
        if not hasattr(self, '_dedup_date') or self._dedup_date != today:
            self._dedup_date = today
            with self._lock:
                self._pushed_today.clear()
            print(f"[AI520实时监控] {today} 去重集合已重置", flush=True)

    def _is_pushed(self, code: str) -> bool:
        """检查股票今日是否已推送"""
        with self._lock:
            return code in self._pushed_today

    def _mark_pushed(self, code: str):
        """标记股票今日已推送"""
        with self._lock:
            self._pushed_today.add(code)

    def _scan_and_push(self):
        """执行一次扫描并推送新符合条件的股票"""
        try:
            self._reset_daily_dedup()

            scan_service = self._get_scan_service()

            # 执行扫描（不推送，只获取结果）
            print(f"[AI520实时监控] 开始第{self._scan_count + 1}次扫描...", flush=True)
            result = scan_service.run_scan_and_push(
                scan_source='realtime',
                push_wechat=False,  # 不自动推送，由我们控制
            )

            signals = result.get('signals', [])
            if not signals:
                print(f"[AI520实时监控] 扫描完成，无符合条件股票", flush=True)
                return

            # 筛选AI520 S/A级（>=80分）且今日未推送的
            new_signals = []
            for sig in signals:
                code = sig.get('code', '')
                score = sig.get('total_score', sig.get('ai520_score', 0))
                grade = sig.get('grade', '')
                if score >= AI520_PUSH_THRESHOLD and grade in ('S', 'A') and not self._is_pushed(code):
                    new_signals.append(sig)

            if not new_signals:
                print(f"[AI520实时监控] 扫描完成，{len(signals)}只符合条件但均已推送过", flush=True)
                return

            print(f"[AI520实时监控] 发现{len(new_signals)}只新符合条件股票，准备推送", flush=True)

            # V2.9 新增：后台线程触发生成S/A级股票深度画像（不阻塞UI，不恢复深度分析推送）
            try:
                sa_stocks = [{"code": s.get("code",""), "name": s.get("name","")} for s in new_signals if s.get("code")]
                if sa_stocks:
                    def _gen_profiles_async(stocks):
                        try:
                            gen = get_profile_generator()
                            kw_mgr = get_keyword_manager()
                            results = gen.generate_batch(stocks, interval=2)
                            for code, profile in results.items():
                                try:
                                    name = next((s["name"] for s in stocks if s["code"] == code), "")
                                    kw_mgr.extract_from_profile(profile, code, name)
                                except Exception as _e:
                                    print(f"[AI520实时监控] 关键词提取异常 {code}: {_e}", flush=True)
                            print(f"[AI520实时监控] 深度画像批量生成完成，成功{len(results)}/{len(stocks)}只", flush=True)
                        except Exception as _e:
                            print(f"[AI520实时监控] 深度画像生成异常: {_e}", flush=True)
                    _profile_thread = threading.Thread(target=_gen_profiles_async, args=(sa_stocks,), daemon=True)
                    _profile_thread.start()
                    print(f"[AI520实时监控] 已启动后台线程生成{len(sa_stocks)}只股票深度画像", flush=True)
            except Exception as _e:
                print(f"[AI520实时监控] 启动画像生成线程异常: {_e}", flush=True)

            # 逐个推送（每只单独一条消息，确保即时性）
            for sig in new_signals:
                code = sig.get('code', '')
                name = sig.get('name', '')
                score = sig.get('total_score', 0)
                try:
                    # V2.7.2 推送前行业强制拦截：三层校验，不通过则重取行业后重试
                    guard = get_industry_guard()
                    guard_result = guard.check_push_content(sig)
                    if guard_result.get('blocked'):
                        corrected = guard_result.get('corrected_industry', '')
                        reason = guard_result.get('reason', '')
                        print(f"[AI520实时监控] 行业拦截: {name}({code}) {reason}", flush=True)
                        if corrected:
                            sig['industry'] = corrected
                            print(f"[AI520实时监控] 行业已修正为: {corrected}，继续推送", flush=True)
                        else:
                            print(f"[AI520实时监控] 行业无法修正，跳过推送: {name}({code})", flush=True)
                            continue

                    # V2.7.1全量修复：扫描服务已用pytdx批量刷新所有信号行情（价格/涨跌幅）
                    # 此处仅获取腾讯行情补充市值等附加字段，禁止覆盖价格/涨跌幅以确保UI与推送同源一致
                    realtime_quote = self._get_realtime_quote_from_tencent(code)
                    if realtime_quote:
                        if realtime_quote.get('market_cap', 0) > 0:
                            sig['market_cap'] = realtime_quote['market_cap']
                        if sig.get('price', 0) > 0:
                            print(f"[AI520实时监控] 行情已刷新(pytdx): {name}({code}) 价格={sig['price']:.2f} 涨跌幅={sig['pct_chg']:+.2f}% 市值={sig.get('market_cap',0):.1f}亿", flush=True)

                    # 构建单只股票推送消息（即时提醒）
                    content = self._build_single_push_message(sig)
                    success, msg = scan_service.send_wechat_message(content)
                    if success:
                        self._mark_pushed(code)
                        self._push_count += 1
                        print(f"[AI520实时监控] 推送成功: {name}({code}) {score}分", flush=True)

                        # 生成深度分析并作为跟进消息发送
                        try:
                            if is_ollama_available():
                                print(f"[AI520实时监控] 开始生成深度分析: {name}({code})", flush=True)
                                deep_content = generate_deep_analysis(sig, use_cache=True)
                                if deep_content:
                                    deep_success, deep_msg = scan_service.send_wechat_message(deep_content)
                                    if deep_success:
                                        print(f"[AI520实时监控] 深度分析推送成功: {name}({code})", flush=True)
                                    else:
                                        print(f"[AI520实时监控] 深度分析推送失败: {name}({code}) - {deep_msg}", flush=True)
                                else:
                                    print(f"[AI520实时监控] 深度分析生成失败或超时: {name}({code})", flush=True)
                            else:
                                print(f"[AI520实时监控] Ollama不可用，跳过深度分析: {name}({code})", flush=True)
                        except Exception as deep_e:
                            print(f"[AI520实时监控] 深度分析异常: {name}({code}) - {deep_e}", flush=True)
                    else:
                        print(f"[AI520实时监控] 推送失败: {name}({code}) - {msg}", flush=True)
                except Exception as e:
                    print(f"[AI520实时监控] 推送异常: {name}({code}) - {e}", flush=True)

                # 推送间隔，避免频率限制
                time.sleep(1)

        except Exception as e:
            print(f"[AI520实时监控] 扫描异常: {e}", flush=True)

    def _get_realtime_quote_from_tencent(self, code: str) -> Dict:
        """从腾讯行情接口获取实时行情（价格、涨跌幅、市值）"""
        try:
            import requests
            if code.startswith('6'):
                qt_code = f'sh{code}'
            else:
                qt_code = f'sz{code}'
            url = f'https://qt.gtimg.cn/q={qt_code}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=3)
            resp.encoding = 'gbk'
            if '=' in resp.text:
                data = resp.text.split('"')[1].split('~')
                if len(data) > 45:
                    price = float(data[3]) if data[3] else 0
                    pct_chg = float(data[32]) if data[32] else 0
                    # 总市值（亿元）- 腾讯接口直接返回亿元
                    market_cap = float(data[45]) if data[45] else 0
                    return {
                        'price': price,
                        'pct_chg': pct_chg,
                        'market_cap': market_cap,
                        'name': data[1] if len(data) > 1 else '',
                    }
        except Exception as e:
            print(f"[AI520实时监控] 获取实时行情失败 {code}: {e}", flush=True)
        return {}

    def _get_market_cap_from_tencent(self, code: str) -> float:
        """从腾讯行情接口获取实时市值（亿元）"""
        quote = self._get_realtime_quote_from_tencent(code)
        return quote.get('market_cap', 0)

    def _calc_buy_sell_points(self, sig: Dict) -> Dict:
        """根据MA5/MA20/价格计算买卖点"""
        price = sig.get('price', 0)
        ma5 = sig.get('ma5', 0)
        ma20 = sig.get('ma20', 0)
        pullback_type = sig.get('pullback_type', '')

        if price <= 0 or ma5 <= 0:
            return {}

        # 买点：MA5附近
        buy_low = min(ma5, price) * 0.98
        buy_high = max(ma5, price) * 1.02

        # 止损：MA20支撑位下方3%
        stop_loss = ma20 * 0.97 if ma20 > 0 else price * 0.95

        # 目标：15%上涨空间
        target_low = price * 1.10
        target_high = price * 1.20

        # 买点逻辑
        if pullback_type == 'MA5':
            buy_logic = 'MA5缩量回踩，量能恢复可介入'
        elif pullback_type == 'MA20':
            buy_logic = 'MA20强支撑回踩，企稳可介入'
        else:
            buy_logic = '均线多头排列，回踩MA5可介入'

        # 卖点逻辑
        sell_logic = '跌破MA20支撑位，趋势走弱止损'

        return {
            'best_buy_range': [round(buy_low, 2), round(buy_high, 2)],
            'stop_loss': round(stop_loss, 2),
            'target_range': [round(target_low, 2), round(target_high, 2)],
            'buy_logic': buy_logic,
            'sell_logic': sell_logic,
        }

    def _get_auction_volume_info(self, code: str, sig: Dict) -> Dict:
        """获取竞价量能对比信息（量比、放量/缩量判断）"""
        try:
            # 从腾讯行情接口获取量比（字段[49]）
            quote = self._get_realtime_quote_from_tencent(code)
            if not quote:
                return {}
            
            # 尝试从腾讯接口原始数据获取量比
            import requests
            if code.startswith('6'):
                qt_code = f'sh{code}'
            else:
                qt_code = f'sz{code}'
            url = f'https://qt.gtimg.cn/q={qt_code}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=3)
            resp.encoding = 'gbk'
            if '=' in resp.text:
                data = resp.text.split('"')[1].split('~')
                # [49] 量比
                volume_ratio = float(data[49]) if len(data) > 49 and data[49] else 0
                # [38] 换手率
                turnover = float(data[38]) if len(data) > 38 and data[38] else 0
                
                if volume_ratio > 0:
                    # 判断放量/缩量
                    if volume_ratio >= 1.5:
                        volume_status = '放量'
                    elif volume_ratio <= 0.8:
                        volume_status = '缩量'
                    else:
                        volume_status = '平量'
                    
                    # 估算较昨日同期增减幅（基于量比）
                    change_pct = (volume_ratio - 1) * 100
                    
                    return {
                        'volume_ratio': round(volume_ratio, 2),
                        'volume_status': volume_status,
                        'change_pct': round(change_pct, 1),
                        'turnover': turnover,
                    }
        except Exception as e:
            print(f"[AI520实时监控] 获取竞价量能失败 {code}: {e}", flush=True)
        return {}

    def _get_earnings_announcement(self, code: str) -> Dict:
        """获取近7日业绩公告（年报/半年报/三季报/一季报/业绩预告/业绩快报），无则返回空字典"""
        try:
            import requests
            from datetime import datetime, timedelta

            secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
            # 东方财富F10主要财务指标接口
            url = f'https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={secid}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            if not data.get('data'):
                return {}

            latest = data['data'][0]
            report_date_str = latest.get('REPORT_DATE', '')[:10] if latest.get('REPORT_DATE') else ''
            if not report_date_str:
                return {}

            # 判断公告类型
            if '12-31' in report_date_str:
                report_type = '年报'
            elif '06-30' in report_date_str:
                report_type = '半年报'
            elif '09-30' in report_date_str:
                report_type = '三季报'
            elif '03-31' in report_date_str:
                report_type = '一季报'
            else:
                report_type = '定期报告'

            # 尝试获取业绩预告/快报类型（从公告日期字段推断）
            notice_date_str = latest.get('NOTICE_DATE', '')[:10] if latest.get('NOTICE_DATE') else ''
            # 如果有公告日期且与报告日期差异较大，可能是预告/快报
            if notice_date_str:
                try:
                    notice_dt = datetime.strptime(notice_date_str, '%Y-%m-%d')
                    report_dt = datetime.strptime(report_date_str, '%Y-%m-%d')
                    days_diff = (report_dt - notice_dt).days
                    if days_diff > 30:
                        # 提前一个月以上披露，大概率是业绩预告或快报
                        report_type = '业绩预告'
                except Exception:
                    pass

            # 近7日披露时间判断
            today = datetime.now().date()
            seven_days_ago = today - timedelta(days=7)
            disclosure_date = None
            # 优先用公告日期，没有则用报告日期近似
            for date_field in [notice_date_str, report_date_str]:
                if date_field:
                    try:
                        disclosure_date = datetime.strptime(date_field, '%Y-%m-%d').date()
                        break
                    except Exception:
                        continue
            if disclosure_date is None or disclosure_date < seven_days_ago or disclosure_date > today:
                return {}

            # 核心数据摘要
            summary_parts = []
            # 净利润同比增长率
            net_profit_yoy = latest.get('PARENT_NETPROFIT_YOY', None)
            if net_profit_yoy is not None and net_profit_yoy != '-':
                try:
                    np_yoy = float(net_profit_yoy)
                    summary_parts.append(f"净利润同比{np_yoy:+.1f}%")
                except (ValueError, TypeError):
                    pass
            # 营收同比增长率
            revenue_yoy = latest.get('TOTAL_OPERATE_INCOME_YOY', None)
            if revenue_yoy is not None and revenue_yoy != '-':
                try:
                    rev_yoy = float(revenue_yoy)
                    summary_parts.append(f"营收同比{rev_yoy:+.1f}%")
                except (ValueError, TypeError):
                    pass

            summary = '，'.join(summary_parts)

            return {
                'report_type': report_type,
                'report_date': report_date_str,
                'summary': summary,
            }
        except Exception as e:
            print(f"[AI520实时监控] 获取业绩公告失败 {code}: {e}", flush=True)
        return {}

    def _get_sector_announcement(self, industry: str, code: str) -> str:
        """获取板块当日最新公告/重要政策事件，无则返回空字符串"""
        if not industry:
            return ''
        try:
            import requests
            from datetime import datetime

            today_str = datetime.now().strftime('%Y-%m-%d')
            headers = {'User-Agent': 'Mozilla/5.0'}

            # 东方财富行业板块新闻接口
            # 先通过行业名称获取板块代码
            industry_encoded = industry
            # 尝试东方财富资讯搜索接口
            search_url = (
                f'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
                f'?client=web&biz=web_news_col&column=350&order=1&needInteractData=0'
                f'&page_index=1&page_size=20&types=1&keyword={industry_encoded}'
            )
            try:
                resp = requests.get(search_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    news_list = data.get('data', {}).get('list', [])
                    if not news_list:
                        news_list = data.get('data', [])
                    # 筛选当日重要新闻
                    important_keywords = [
                        '政策', '发布', '上调', '下调', '涨价', '降价',
                        '规划', '通知', '意见', '方案', '数据', '增速',
                        '补贴', '监管', '审批', '项目', '投资', '产能',
                        '价格', '供需', '出口', '进口', '关税',
                    ]
                    for news in news_list:
                        title = news.get('title', '') or news.get('Art_title', '')
                        news_date = (news.get('showtime', '') or news.get('Art_ShowTime', ''))[:10]
                        if not title or not news_date:
                            continue
                        if news_date != today_str:
                            continue
                        # 筛选重要政策/事件
                        if any(kw in title for kw in important_keywords):
                            summary = title.strip()
                            if len(summary) > 50:
                                summary = summary[:47] + '...'
                            return summary
            except Exception:
                pass

            # 备用：东方财富个股所属行业资讯接口
            try:
                secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
                ind_url = (
                    f'https://emweb.securities.eastmoney.com/PC_HSF10/IndustryAnalysis/PageAjax'
                    f'?code={secid}'
                )
                resp2 = requests.get(ind_url, headers=headers, timeout=5)
                if resp2.status_code == 200:
                    ind_data = resp2.json()
                    # 尝试提取行业新闻
                    for key in ['news', 'industryNews', 'zxbg']:
                        items = ind_data.get(key, [])
                        if isinstance(items, list):
                            for item in items:
                                title = item.get('title', '') or item.get('INFO_TITLE', '')
                                n_date = (item.get('date', '') or item.get('NOTICE_DATE', ''))[:10]
                                if title and n_date == today_str:
                                    summary = title.strip()
                                    if len(summary) > 50:
                                        summary = summary[:47] + '...'
                                    return summary
            except Exception:
                pass

            return ''
        except Exception as e:
            print(f"[AI520实时监控] 获取板块公告失败 {industry}: {e}", flush=True)
        return ''

    def _build_single_push_message(self, sig: Dict) -> str:
        """构建单只股票实时推送消息（V2.8.0字段调整版）"""
        code = sig.get('code', '')
        name = sig.get('name', '')
        price = sig.get('price', 0)
        pct = sig.get('pct_chg', 0)
        score = sig.get('total_score', 0)
        grade = sig.get('grade', '')
        industry = sig.get('industry', '')
        now_str = datetime.now().strftime('%H:%M:%S')

        grade_icon = '🔥' if grade == 'S' else '🟢' if grade == 'A' else '🟡'

        # ===== 1. 标题区 =====
        content = f"### 【AI-520 盘中实时推送】\n"
        content += f"**{now_str} 发现新符合条件股票**\n\n"
        content += f"**{grade_icon} {name}({code}) {score}分 {grade}级**\n"

        # ===== 2. 核心价格区 =====
        content += f"> 现价: **{price:.2f} ({pct:+.2f}%)** | 行业: {industry}\n"

        # ===== 3. 市值 + 今年涨停 =====
        market_cap = sig.get('market_cap', 0)
        if market_cap <= 0:
            market_cap = self._get_market_cap_from_tencent(code)

        limit_1y = sig.get('limit_count_1y', 0)
        if not limit_1y:
            limit_1y = sig.get('limit_up_1y', 0)

        info_parts = []
        if market_cap > 0:
            info_parts.append(f"市值: {market_cap:.1f}亿")
        if limit_1y > 0:
            info_parts.append(f"今年涨停: {limit_1y}次")
        if info_parts:
            content += f"> {' | '.join(info_parts)}\n"

        # ===== 4. 空行 =====
        content += "\n"

        # ===== 5-7. 可选字段区（有数据显示，无则隐藏，避免双空行）=====
        has_optional_content = False

        # ===== 5. ⏰ 竞价量能 =====
        auction_info = self._get_auction_volume_info(code, sig)
        if auction_info:
            vol_ratio = auction_info.get('volume_ratio', 0)
            vol_status = auction_info.get('volume_status', '')
            change_pct = auction_info.get('change_pct', 0)
            if vol_ratio > 0:
                content += f"⏰ 竞价量能：较昨日同期{change_pct:+.1f}%，量比{vol_ratio:.2f}，{vol_status}开盘\n"
                has_optional_content = True

        # ===== 6. 📰 业绩公告 =====
        earnings_info = self._get_earnings_announcement(code)
        if earnings_info:
            report_type = earnings_info.get('report_type', '')
            summary = earnings_info.get('summary', '')
            if report_type:
                earnings_text = f"📰 业绩公告：{report_type}"
                if summary:
                    earnings_text += f"，{summary}"
                content += f"{earnings_text}\n"
                has_optional_content = True

        # ===== 7. 📑 板块公告 =====
        sector_ann = self._get_sector_announcement(industry, code)
        if sector_ann:
            content += f"📑 板块公告：{sector_ann}\n"
            has_optional_content = True

        # ===== 8. 空行（仅当有可选内容时添加，避免双空行）=====
        if has_optional_content:
            content += "\n"

        # ===== 9-11. 买卖点区 =====
        buy_point = sig.get('buy_point', {})
        if not buy_point:
            buy_point = self._calc_buy_sell_points(sig)

        if buy_point:
            best_buy = buy_point.get('best_buy_range', [0, 0])
            stop_loss = buy_point.get('stop_loss', 0)
            target = buy_point.get('target_range', [0, 0])
            buy_logic = buy_point.get('buy_logic', '')
            sell_logic = buy_point.get('sell_logic', '')
            # 🎯 买点
            if best_buy and best_buy[0] > 0:
                content += f"🎯 买点: {best_buy[0]:.2f}~{best_buy[1]:.2f}元"
                if buy_logic:
                    content += f"（{buy_logic}）"
                content += "\n"
            # 🛑 止损
            if stop_loss > 0:
                content += f"🛑 止损: {stop_loss:.2f}元"
                if sell_logic:
                    content += f"（{sell_logic}）"
                content += "\n"
            # 🎯 目标
            if target and target[1] > 0:
                content += f"🎯 目标: {target[0]:.2f}~{target[1]:.2f}元\n"

        # 长度校验（控制在3000字节以内）
        content_bytes = content.encode('utf-8')
        if len(content_bytes) > 3000:
            content = content.replace('（均线多头排列，回踩MA5可介入）', '')
            content = content.replace('（跌破MA20支撑位，趋势走弱止损）', '')
            print(f"[AI520实时监控] 消息超长({len(content_bytes)}字节)，已精简", flush=True)

        return content

    def _monitor_loop(self):
        """监控主循环"""
        print(f"[AI520实时监控] 监控线程已启动，扫描间隔{SCAN_INTERVAL}秒", flush=True)

        while self._running:
            try:
                if is_trading_hours():
                    self._scan_count += 1
                    self._last_scan_time = datetime.now()
                    self._scan_and_push()
                else:
                    # 非交易时段，每分钟检查一次
                    pass

                # 等待到下一次扫描
                for _ in range(SCAN_INTERVAL):
                    if not self._running:
                        break
                    time.sleep(1)

            except Exception as e:
                print(f"[AI520实时监控] 主循环异常: {e}", flush=True)
                time.sleep(10)

        print(f"[AI520实时监控] 监控线程已停止", flush=True)

    def start(self):
        """启动监控（后台线程）"""
        if self._running:
            print("[AI520实时监控] 已在运行中", flush=True)
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name='AI520RealtimeMonitor')
        self._thread.start()
        print("[AI520实时监控] 已启动后台监控线程", flush=True)

    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[AI520实时监控] 已停止", flush=True)

    def get_status(self) -> Dict:
        """获取监控状态"""
        return {
            'running': self._running,
            'scan_count': self._scan_count,
            'push_count': self._push_count,
            'last_scan_time': self._last_scan_time.strftime('%H:%M:%S') if self._last_scan_time else None,
            'pushed_today': len(self._pushed_today),
            'is_trading_hours': is_trading_hours(),
        }

    def trigger_scan_now(self):
        """立即触发一次扫描（手动触发）"""
        print("[AI520实时监控] 手动触发立即扫描", flush=True)
        self._scan_and_push()


# 全局单例
_realtime_monitor: Optional[AI520RealtimeMonitor] = None


def get_realtime_monitor(scan_service=None) -> AI520RealtimeMonitor:
    """获取全局实时监控器单例"""
    global _realtime_monitor
    if _realtime_monitor is None:
        _realtime_monitor = AI520RealtimeMonitor(scan_service=scan_service)
    return _realtime_monitor


if __name__ == '__main__':
    # 测试：立即触发一次扫描
    monitor = get_realtime_monitor()
    print("测试AI520实时监控...")
    print(f"当前交易时段: {is_trading_hours()}")
    monitor.trigger_scan_now()
    print(f"状态: {monitor.get_status()}")
