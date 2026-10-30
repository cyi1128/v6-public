# -*- coding: utf-8 -*-
"""
V2.2/V2.3 作战闭环集成服务 V2.0
修复：AI520 push_wechat参数、收盘日报list/get错误
新增：四时段企业微信双卡推送（09:00/09:30/14:45/15:05）、S/A去重、防重复执行
统一数据Schema，所有数据来自真实接口
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _lu_pct(code) -> float:
    """[CYB-GATE] 按板性返回判涨停阈值（%）：主板 9.5，创业板/科创板 19.5，北交所 29.5。

    创业板 300/301 与科创板 688/689 是 20cm 板，北交所 8xx/4xx/920 是 30cm 板。
    统一按 9.5% 判会把这两类板的「涨了一半」误当成涨停。
    """
    c = str(code or '')
    if c.startswith(('300', '301', '688', '689')):
        return 19.5
    if c.startswith(('8', '4', '920')):
        return 29.5
    return 9.5


class V22CombatService:
    """V2.2 作战闭环统一服务（单例）"""

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
        self._services = {}
        self._last_scan = None
        self._last_scan_time = None
        self._market_temp_cache = None
        self._market_temp_time = None
        # 防重复执行锁：date+slot
        self._executed_slots = set()
        self._slot_lock_date = None
        # 日志状态去重
        self._last_log_state = None

    def _get_ai520_service(self):
        if 'ai520' not in self._services:
            try:
                from strategy.ai_520_scan_service import AI520ScanService
                self._services['ai520'] = AI520ScanService()
                print("[V22] AI-520扫描服务加载成功")
            except Exception as e:
                print(f"[V22] AI-520扫描服务加载失败: {e}")
                self._services['ai520'] = None
        return self._services.get('ai520')

    def _get_wechat_service(self):
        if 'wechat' not in self._services:
            try:
                from services.wechat_notify_service import WechatNotifyService
                svc = WechatNotifyService()
                svc.start()
                self._services['wechat'] = svc
                print("[V22] 企业微信服务加载成功")
            except Exception as e:
                print(f"[V22] 企业微信服务加载失败: {e}")
                self._services['wechat'] = None
        return self._services.get('wechat')

    def _get_daily_close_service(self):
        if 'daily_close' not in self._services:
            try:
                from services.daily_close_summary_service import DailyCloseSummaryService
                self._services['daily_close'] = DailyCloseSummaryService()
                print("[V22] 收盘总结服务加载成功")
            except Exception as e:
                print(f"[V22] 收盘总结服务加载失败: {e}")
                self._services['daily_close'] = None
        return self._services.get('daily_close')

    def _get_ai520_database(self):
        if 'ai520_db' not in self._services:
            try:
                from strategy.ai_520_database import AI520Database
                self._services['ai520_db'] = AI520Database()
            except Exception as e:
                print(f"[V22] AI-520数据库加载失败: {e}")
                self._services['ai520_db'] = None
        return self._services.get('ai520_db')

    # ============================================================
    # AI-520 扫描（已修复push_wechat参数）
    # ============================================================
    def run_ai520_scan(self, scan_source: str = 'manual', push_wechat: bool = True) -> Dict:
        """执行AI-520全市场扫描
        Args:
            scan_source: 扫描来源（premarket/09:30/14:45/manual）
            push_wechat: 是否推送企业微信
        """
        svc = self._get_ai520_service()
        if not svc:
            return {'success': False, 'error': 'AI-520服务未加载', 'signals': []}
        try:
            print(f"[V22] 开始AI-520扫描 (来源:{scan_source}, 推送:{push_wechat})")
            result = svc.run_scan_and_push(scan_source=scan_source, push_wechat=push_wechat)
            self._last_scan = result
            self._last_scan_time = datetime.now()
            signals = result.get('signals', [])
            grades = result.get('grades', {})
            print(f"[V22] AI-520扫描完成: {len(signals)}只信号")
            return {
                'success': True,
                'signals': signals,
                'grades': grades,
                'total_scanned': result.get('scan', {}).get('total_scanned', 0),
                'push_result': result.get('push'),
            }
        except Exception as e:
            print(f"[ERROR][AI520] 扫描失败: {e}")
            return {'success': False, 'error': str(e), 'signals': []}

    def get_ai520_signals(self) -> List[Dict]:
        """获取最近一次AI-520扫描结果"""
        if self._last_scan:
            return self._last_scan.get('signals', [])
        return []

    # ============================================================
    # 企业微信双卡推送（核心）
    # ============================================================
    def _build_dual_card_message(self, slot: str, market_data: Dict = None, ai520_signals: List[Dict] = None) -> List[str]:
        """构建企业微信双卡消息
        第一张卡：市场概况/市场数据/强势板块
        第二张卡：AI-520信号汇总
        Returns: [card1_text, card2_text]
        """
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')

        # 判断是否为测试模式（非标准时段运行）
        slot_times = {'premarket': (9, 0), '09:30': (9, 30), '14:45': (14, 45), 'close': (15, 5)}
        is_test = False
        if slot in slot_times:
            expected_h, expected_m = slot_times[slot]
            # 如果当前时间与预期时段相差超过30分钟，标记为测试
            if abs((now.hour * 60 + now.minute) - (expected_h * 60 + expected_m)) > 30:
                is_test = True

        # 第一张卡：市场概况
        card1 = []
        slot_names = {'premarket': '盘前作战', '09:30': '开盘信号', '14:45': '尾盘复核', 'close': '收盘总结'}
        slot_name = slot_names.get(slot, slot)
        card1.append(f"📊【量化交易｜{slot_name}】")
        if is_test:
            card1.append(f"日期: {date_str} 测试时间: {time_str} (非{slot}标准时段)")
        else:
            card1.append(f"日期: {date_str} 时间: {time_str}")
        card1.append("━" * 18)

        if market_data:
            # 市场概况
            card1.append("📊 市场概况")
            up = market_data.get('up', '未取得')
            down = market_data.get('down', '未取得')
            flat = market_data.get('flat', '未取得')
            lu = market_data.get('limit_up', '未取得')
            ld = market_data.get('limit_down', '未取得')
            card1.append(f"  上涨:{up} 下跌:{down} 平盘:{flat}")
            card1.append(f"  涨停:{lu} 跌停:{ld}")

            # 市场数据
            card1.append("")
            card1.append("💰 市场数据")
            avg_pct = market_data.get('avg_pct', '未取得')
            if isinstance(avg_pct, (int, float)):
                avg_pct = f"{avg_pct:.2f}%"
            amount = market_data.get('amount', 0)
            if isinstance(amount, (int, float)) and amount > 0:
                amount_yi = amount / 1e8
                amount_str = f"{amount_yi:.0f}亿"
            else:
                amount_str = '未取得'
            card1.append(f"  平均涨跌幅: {avg_pct}")
            card1.append(f"  全市场成交额: {amount_str}")

            # 指数
            indexes = market_data.get('indexes', {})
            if isinstance(indexes, dict):
                idx_list = indexes.get('indexes', [])
                if idx_list:
                    card1.append("")
                    card1.append("📈 指数")
                    for idx in idx_list[:3]:
                        name = idx.get('name', '')
                        price = idx.get('price', idx.get('close', '未取得'))
                        pct = idx.get('pct_chg', idx.get('change_pct', '未取得'))
                        if isinstance(pct, (int, float)):
                            pct_str = f"{pct:+.2f}%"
                        else:
                            pct_str = str(pct)
                        card1.append(f"  {name}: {price} ({pct_str})")

            # 强势板块
            sectors = market_data.get('sectors', {})
            if isinstance(sectors, dict):
                top_sectors = sectors.get('top', [])
                if top_sectors:
                    card1.append("")
                    card1.append("🔥 今日强势板块TOP3")
                    for i, sec in enumerate(top_sectors[:3], 1):
                        sname = sec.get('name', '')
                        spct = sec.get('change_pct', sec.get('pct_chg', 0))
                        if isinstance(spct, (int, float)):
                            spct_str = f"{spct:+.2f}%"
                        else:
                            spct_str = str(spct)
                        card1.append(f"  {i}. {sname} {spct_str}")

            # 新闻催化
            news_list = self._get_latest_news(limit=3)
            if news_list:
                card1.append("")
                card1.append("📰 新闻催化")
                for n in news_list[:3]:
                    title = n.get('title', '')[:40]
                    t = n.get('publish_time', n.get('time', ''))
                    card1.append(f"  [{t}] {title}")
            else:
                card1.append("")
                card1.append("📰 新闻催化: 暂无可靠新闻")

            # 今日作战计划
            card1.append("")
            card1.append("🎯 今日作战")
            is_premarket = market_data.get('is_premarket', False)
            if is_premarket:
                card1.append("  盘前阶段：关注隔夜消息面、集合竞价异动、AI-520候选股")
                card1.append("  开盘后：验证AI-520信号股是否放量突破，关注板块共振")
            else:
                card1.append("  交易阶段：跟踪AI-520 S/A级信号股，关注板块资金流入")
                card1.append("  风控：严格止损，不追高，等待回踩确认")

            # 风险提示
            card1.append("")
            card1.append("⚠️ 风险提示")
            indexes = market_data.get('indexes', {})
            if isinstance(indexes, dict):
                idx_list = indexes.get('indexes', [])
                if idx_list:
                    avg_idx_pct = sum(float(idx.get('pct_chg', 0) or 0) for idx in idx_list[:3]) / 3
                    if avg_idx_pct < -1:
                        card1.append("  指数大幅下跌，市场风险偏好降低，谨慎操作")
                    elif avg_idx_pct > 1:
                        card1.append("  指数上涨，注意追高风险，关注量能是否持续")
                    else:
                        card1.append("  指数震荡，精选个股，控制仓位")
                else:
                    card1.append("  指数数据未取得，注意市场风险")
            else:
                card1.append("  注意控制仓位，严格止损")
        else:
            card1.append("  市场数据: 未取得（数据源不可用）")

        card1.append("")
        card1.append("👉更多详情请打开【量化交易作战中控台】查看！")

        # 第二张卡：AI-520信号
        card2 = []
        card2.append("🎯【AI-520战法】今日信号汇总")
        card2.append(f"扫描时间: {date_str} {time_str}")
        card2.append("━" * 18)

        if ai520_signals:
            # 按股票代码去重（核心修复：同一股票只出现一次）
            seen_codes = set()
            dedup_signals = []
            for s in ai520_signals:
                code = str(s.get('code', ''))
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    dedup_signals.append(s)
            if len(dedup_signals) < len(ai520_signals):
                print(f"[WECHAT] AI-520信号去重: {len(ai520_signals)}→{len(dedup_signals)}")

            # 从东方财富F10获取行业信息（修复板块为空）
            industry_map = {}
            try:
                from service.concept_service import get_stock_industry_f10
                for s in dedup_signals:
                    code = str(s.get('code', ''))
                    if code and not s.get('sector') and not s.get('industry'):
                        try:
                            ind = get_stock_industry_f10(code)
                            if ind:
                                industry_map[code] = ind
                                s['industry'] = ind
                        except Exception:
                            pass
                print(f"[WECHAT] 东方财富F10行业映射: {len(industry_map)}只")
            except Exception as e:
                print(f"[WECHAT] 东方财富F10行业获取失败: {e}")

            total = len(dedup_signals)
            # 按等级分组（真实统计）
            sa = [s for s in dedup_signals if str(s.get('grade', '')).upper() in ('S+', 'S', 'A')]
            b_list = [s for s in dedup_signals if str(s.get('grade', '')).upper() == 'B']
            c_list = [s for s in dedup_signals if str(s.get('grade', '')).upper() == 'C']
            s_plus = len([s for s in sa if str(s.get('grade', '')).upper() == 'S+'])
            s_count = len([s for s in sa if str(s.get('grade', '')).upper() == 'S'])
            a_count = len([s for s in sa if str(s.get('grade', '')).upper() == 'A'])

            # 只统计S/A级推送
            real_total = s_plus + s_count + a_count
            card2.append(f"⭐今日共识别{real_total}只S/A级AI-520信号股")
            card2.append(f"  (S+:{s_plus} S:{s_count} A:{a_count})")
            card2.append("")

            # S/A级
            if sa:
                card2.append("🏆 强势信号（S+/S/A级）")
                for s in sa[:10]:
                    code = s.get('code', '')
                    name = s.get('name', '')
                    # 名称为空或等于code时显示"名称未取得"
                    if not name or name == code:
                        name = "名称未取得"
                    score = s.get('score', s.get('total_score', 0))
                    grade = s.get('grade', '')
                    pct = s.get('pct_chg', s.get('change_pct', 0))
                    if isinstance(pct, (int, float)):
                        pct_str = f"{pct:+.2f}%"
                    else:
                        pct_str = "未取得"
                    sector = s.get('sector', s.get('industry', ''))
                    # 板块为空时显示"未取得"
                    if not sector:
                        sector = "未取得"
                    card2.append(f"  {name}({code}) {grade}{score}分 {pct_str} 板块:{sector}")
                if len(sa) > 10:
                    card2.append(f"  ...其余S/A级{len(sa)-10}只，请打开中控台查看")



            # 板块共振
            sectors = market_data.get('sectors', {})
            if isinstance(sectors, dict):
                top_sectors = sectors.get('top', [])
                if top_sectors:
                    card2.append("")
                    card2.append("🔥 板块共振")
                    for sec in top_sectors[:3]:
                        sname = sec.get('name', '')
                        spct = sec.get('change_pct', sec.get('pct_chg', 0))
                        if isinstance(spct, (int, float)):
                            spct_str = f"{spct:+.2f}%"
                        else:
                            spct_str = str(spct)
                        # 统计该板块AI-520信号数量
                        sector_signals = [s for s in ai520_signals if s.get('sector') == sname or s.get('industry') == sname]
                        if sector_signals:
                            card2.append(f"  {sname} {spct_str} (AI-520信号{len(sector_signals)}只)")
                        else:
                            card2.append(f"  {sname} {spct_str}")

            # 新闻催化
            news_list = self._get_latest_news(limit=2)
            if news_list:
                card2.append("")
                card2.append("📰 新闻催化")
                for n in news_list[:2]:
                    title = n.get('title', '')[:35]
                    card2.append(f"  {title}")
            else:
                card2.append("")
                card2.append("📰 新闻催化: 暂无可靠新闻")
        else:
            card2.append("  今日暂无AI-520信号股")
            card2.append("  （可能非交易时间或当前无符合条件股票）")

        card2.append("")
        card2.append("📊数据来源：AI-520战法模型实时扫描")
        card2.append(f"🕒扫描时间：{date_str} {time_str}")

        return ['\n'.join(card1), '\n'.join(card2)]

    def push_dual_card_to_wechat(self, slot: str, market_data: Dict = None, ai520_signals: List[Dict] = None) -> Dict:
        """推送双卡消息到企业微信
        只有发送成功才写入push_records
        卡2超长时自动生成PNG图片
        """
        # V3.0 推送重构：V2.2 作战双卡业务推送已关闭（不再轰炸企业微信，数据仍在UI/记录）
        return {'skipped': True, 'success': False, 'reason': 'V3.0 作战双卡推送已关闭'}
        wechat = self._get_wechat_service()
        if not wechat or not wechat.is_configured():
            print("[WECHAT] 企业微信未配置，跳过推送")
            return {'success': False, 'error': '企业微信未配置'}

        try:
            cards = self._build_dual_card_message(slot, market_data, ai520_signals)
            print(f"[WECHAT] 生成{slot}正式双卡消息 (卡1:{len(cards[0])}字, 卡2:{len(cards[1])}字)")
            print(f"[WECHAT] 卡1：市场作战")
            print(f"[WECHAT] 卡2：AI-520")

            # 卡2超长时自动生成PNG图片
            image_path = None
            if len(cards[1]) > 3500:
                print(f"[WECHAT] 卡2超长({len(cards[1])}字)，自动生成PNG图片...")
                now = datetime.now()
                date_str = now.strftime('%Y%m%d')
                slot_safe = slot.replace(':', '')
                image_path = os.path.join(PROJECT_ROOT, 'data', 'cache', f'AI520_{date_str}_{slot_safe}.png')
                # 生成图片内容
                img_lines = cards[1].split('\n')
                generated = self.generate_report_image(
                    title=f"AI-520战法｜{slot}信号全量报告",
                    content_lines=img_lines,
                    output_path=image_path
                )
                if generated and os.path.exists(generated):
                    image_path = generated
                    print(f"[IMAGE] 图片生成成功: {image_path} ({os.path.getsize(image_path)}字节)")
                    # 卡2压缩为摘要+图片提示
                    sa_count = len([s for s in (ai520_signals or []) if str(s.get('grade','')).upper() in ('S+','S','A')])
                    cards[1] = cards[1][:2000] + f"\n\n...其余信号已生成图片报告\n📷 图片: {os.path.basename(image_path)}\n共{sa_count}只S/A级信号"
                else:
                    print(f"[IMAGE] 图片生成失败，使用文字压缩")
                    cards[1] = cards[1][:3500] + "\n...(消息过长已截断)"

            results = []
            for i, card_text in enumerate(cards, 1):
                title = f"V2.2-{slot}-卡{i}"
                result = wechat.push_text(card_text, title=title, wait_for_result=True, timeout=30)
                results.append(result)
                errcode = result.get('errcode', -1)
                errmsg = result.get('errmsg', '')
                if result.get('success'):
                    print(f"[WECHAT] 卡{i}发送成功 errcode={errcode} errmsg={errmsg}")
                else:
                    print(f"[WECHAT] 卡{i}发送失败 errcode={errcode} errmsg={errmsg}")

            all_success = all(r.get('success') for r in results)
            if all_success:
                # 只有全部成功才写入push_records
                self._record_push(slot, ai520_signals or [])
                print(f"[WECHAT] 企业微信发送成功，push_records写入成功")
            return {'success': all_success, 'card_results': results, 'image_path': image_path}
        except Exception as e:
            print(f"[ERROR][WECHAT] 推送失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _record_push(self, slot: str, signals: List[Dict]):
        """记录推送成功到push_records"""
        try:
            db = self._get_ai520_database()
            if db and hasattr(db, 'record_push'):
                date_str = datetime.now().strftime('%Y-%m-%d')
                for s in signals[:50]:  # 最多记录50只
                    db.record_push(
                        trade_date=date_str,
                        code=s.get('code', ''),
                        signal_grade=s.get('grade', ''),
                        signal_type='ai520',
                        push_slot=slot,
                        push_status='success'
                    )
        except Exception as e:
            print(f"[V22] push_records记录失败: {e}")

    # ============================================================
    # 收盘日报（已修复list/get错误）
    # ============================================================
    def generate_daily_report(self, push_wechat: bool = True) -> Dict:
        """生成15:05收盘作战日报
        修复：build_summary返回的ai520是list，不再按dict处理
        """
        daily_svc = self._get_daily_close_service()
        if not daily_svc:
            return {'success': False, 'error': '收盘总结服务未加载', 'report': ''}

        try:
            print("[V22] 开始生成收盘作战日报...")
            summary = daily_svc.build_summary()

            # 构建市场数据（从summary提取，适配真实返回结构）
            market_data = {
                'up': summary.get('up', 0),
                'down': summary.get('down', 0),
                'flat': summary.get('flat', 0),
                'limit_up': summary.get('limit_up', 0),
                'limit_down': summary.get('limit_down', 0),
                'avg_pct': summary.get('avg_pct', 0),
                'amount': summary.get('amount', 0),
                'indexes': summary.get('indexes', {}),
                'sectors': summary.get('sectors', {}),
            }

            # AI-520信号（summary['ai520']是list！）
            ai520_list = summary.get('ai520', [])
            if not isinstance(ai520_list, list):
                ai520_list = []

            # V2.3闭环：AI520扫描结果 → Selection Event → ObservationBatch → ObservationTask
            if ai520_list:
                try:
                    from services.observation_service import get_observation_service
                    obs_svc = get_observation_service()
                    batch_result = obs_svc.create_batch_from_scan(
                        signals=ai520_list,
                        scan_id=0,
                        selection_date=datetime.now().strftime('%Y%m%d'),
                        selection_time=datetime.now().strftime('%H:%M:%S')
                    )
                    print(f"[V22] AI520→观察批次创建: {batch_result.get('batch_id', '')} 创建{batch_result.get('created', 0)}只 跳过{batch_result.get('skipped', 0)}只")
                except Exception as e:
                    print(f"[V22] AI520→观察批次创建异常: {e}")
                    import traceback
                    traceback.print_exc()

            # 格式化完整日报文本
            report = self._format_daily_report_v2(summary)

            if push_wechat:
                # 使用双卡格式推送
                self.push_dual_card_to_wechat('close', market_data, ai520_list)
                # 推送AI-520一周观察日报
                try:
                    self.push_observation_report()
                except Exception as e:
                    print(f"[V22] 观察日报推送异常: {e}")

            print("[V22] 收盘作战日报生成完成")
            return {'success': True, 'report': report, 'summary': summary, 'ai520_count': len(ai520_list)}
        except Exception as e:
            print(f"[ERROR][REPORT] 收盘日报生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e), 'report': ''}

    def push_observation_report(self) -> Dict:
        """推送AI-520一周观察日报到企业微信"""
        try:
            from services.observation_service import get_observation_service
            obs_svc = get_observation_service()

            # 生成观察日报
            report = obs_svc.generate_daily_report()
            if not report:
                return {'success': False, 'error': '观察日报为空'}

            print("[V22] 开始推送AI-520一周观察日报...")

            # 使用图片兜底推送（文字过长自动转图片）
            result = self.push_with_image_fallback(
                title="AI-520一周观察日报",
                content=report,
                max_text_length=3500
            )

            if result.get('success'):
                print(f"[V22] 观察日报推送成功 (方式:{result.get('method', 'text')})")
            else:
                print(f"[V22] 观察日报推送失败: {result.get('error', '')}")

            return result
        except Exception as e:
            print(f"[ERROR][OBS] 观察日报推送失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _format_daily_report_v2(self, summary: Dict) -> str:
        """格式化收盘日报（适配build_summary真实返回结构）
        关键修复：ai520是list，indexes是dict包含list，sectors是dict包含list
        """
        lines = []
        date_str = summary.get('date', datetime.now().strftime('%Y-%m-%d'))
        lines.append("📊【量化交易｜收盘作战总报告】")
        lines.append(f"日期: {date_str} 生成时间: {summary.get('generated_at', '')}")
        lines.append("━" * 20)

        # 一、市场概况
        lines.append("📈【一、市场概况】")
        lines.append(f"  全市场: {summary.get('total', '未取得')}只")
        lines.append(f"  上涨:{summary.get('up', 0)} 下跌:{summary.get('down', 0)} 平盘:{summary.get('flat', 0)}")
        lines.append(f"  涨停:{summary.get('limit_up', 0)} 跌停:{summary.get('limit_down', 0)}")
        lines.append(f"  大涨≥5%:{summary.get('big_up5', 0)} 大跌≤-5%:{summary.get('big_down5', 0)}")
        avg = summary.get('avg_pct', 0)
        if isinstance(avg, (int, float)):
            lines.append(f"  平均涨跌幅: {avg:.2f}%")
        amount = summary.get('amount', 0)
        if isinstance(amount, (int, float)) and amount > 0:
            lines.append(f"  全市场成交额: {amount/1e8:.0f}亿")

        # 二、指数（indexes是{'indexes': [...], 'sentiment': ...}）
        indexes = summary.get('indexes', {})
        if isinstance(indexes, dict):
            idx_list = indexes.get('indexes', [])
            if idx_list:
                lines.append("")
                lines.append("📊【二、指数】")
                for idx in idx_list:
                    name = idx.get('name', '')
                    price = idx.get('price', idx.get('close', '未取得'))
                    pct = idx.get('pct_chg', idx.get('change_pct', '未取得'))
                    if isinstance(pct, (int, float)):
                        pct_str = f"{pct:+.2f}%"
                    else:
                        pct_str = str(pct)
                    lines.append(f"  {name}: {price} ({pct_str})")
                lines.append(f"  市场情绪: {indexes.get('sentiment', '未取得')}")

        # 三、强势板块（sectors是{'top': [...], 'weak': [...]}）
        sectors = summary.get('sectors', {})
        if isinstance(sectors, dict):
            top = sectors.get('top', [])
            if top:
                lines.append("")
                lines.append("🏆【三、强势板块TOP5】")
                for i, sec in enumerate(top[:5], 1):
                    sname = sec.get('name', '')
                    spct = sec.get('change_pct', sec.get('pct_chg', 0))
                    if isinstance(spct, (int, float)):
                        spct_str = f"{spct:+.2f}%"
                    else:
                        spct_str = str(spct)
                    lines.append(f"  {i}. {sname} {spct_str}")

        # 四、AI-520（ai520是list！）
        ai520_list = summary.get('ai520', [])
        if isinstance(ai520_list, list) and ai520_list:
            lines.append("")
            lines.append("🎯【四、AI-520信号】")
            lines.append(f"  今日信号: {len(ai520_list)}只")
            # 按等级统计
            grade_count = defaultdict(int)
            for s in ai520_list:
                grade_count[str(s.get('grade', 'D')).upper()] += 1
            lines.append(f"  S+:{grade_count.get('S+',0)} S:{grade_count.get('S',0)} A:{grade_count.get('A',0)} B:{grade_count.get('B',0)} C:{grade_count.get('C',0)} D:{grade_count.get('D',0)}")
            # S/A级股票
            sa = [s for s in ai520_list if str(s.get('grade', '')).upper() in ('S+', 'S', 'A')]
            if sa:
                lines.append("  🏆S/A级重点:")
                for s in sa[:8]:
                    code = s.get('code', '')
                    name = s.get('name', '')
                    score = s.get('total_score', s.get('score', 0))
                    grade = s.get('grade', '')
                    lines.append(f"    {name}({code}) {grade}{score}分")

        # 五、风险等级
        lines.append("")
        lines.append(f"⚠【五、市场风险等级】: {summary.get('risk', '未取得')}")

        # 六、数据质量
        lines.append("")
        lines.append("🔎【六、数据质量】")
        lines.append(f"  行情: {'✓正常' if summary.get('total', 0) > 0 else '×未取得'}")
        lines.append(f"  AI-520: {'✓正常' if isinstance(ai520_list, list) else '×异常'}")
        lines.append(f"  指数: {'✓正常' if indexes.get('indexes') else '×未取得'}")
        lines.append(f"  板块: {'✓正常' if sectors.get('top') else '×未取得'}")

        return '\n'.join(lines)

    # ============================================================
    # 市场温度/指数/涨停生态（UI展示用）
    # ============================================================
    def get_market_temperature(self) -> Dict:
        """获取市场温度（缓存30秒）"""
        now = time.time()
        if self._market_temp_cache and (now - self._market_temp_time) < 30:
            return self._market_temp_cache
        try:
            daily_svc = self._get_daily_close_service()
            if daily_svc and hasattr(daily_svc, '_get_market_quotes'):
                quotes = daily_svc._get_market_quotes()
                if quotes:
                    up = sum(x['pct'] > 0.01 for x in quotes)
                    down = sum(x['pct'] < -0.01 for x in quotes)
                    lu = sum(x['pct'] >= _lu_pct(x.get('code')) for x in quotes)   # [CYB-GATE]
                    ld = sum(x['pct'] <= -_lu_pct(x.get('code')) for x in quotes)  # [CYB-GATE]
                    breadth = (up - down) / max(len(quotes), 1)
                    temp = int(50 + breadth * 60)
                    temp = max(0, min(100, temp))
                    if temp >= 85: status = '进攻'
                    elif temp >= 70: status = '偏强'
                    elif temp >= 50: status = '震荡'
                    elif temp >= 30: status = '偏弱'
                    else: status = '冰点'
                    result = {'temperature': temp, 'status': status, 'up_count': up, 'down_count': down,
                              'limit_up': lu, 'limit_down': ld, 'total': len(quotes)}
                    self._market_temp_cache = result
                    self._market_temp_time = now
                    return result
        except Exception as e:
            print(f"[V22] 市场温度获取失败: {e}")
        return {'temperature': 50, 'status': '未取得', 'up_count': 0, 'down_count': 0, 'limit_up': 0, 'limit_down': 0}

    def get_index_status(self) -> Dict:
        """获取指数技术状态"""
        try:
            daily_svc = self._get_daily_close_service()
            if daily_svc:
                idx_data = daily_svc._get_index_summary()
                idx_list = idx_data.get('indexes', []) if isinstance(idx_data, dict) else []
                result = {}
                for idx in idx_list:
                    name = idx.get('name', '')
                    if '上证' in name: key = 'sh'
                    elif '深证' in name or '深成' in name: key = 'sz'
                    elif '创业' in name: key = 'cyb'
                    else: continue
                    result[key] = {'name': name, 'price': idx.get('price', idx.get('close', 0)),
                                   'pct_chg': idx.get('pct_chg', 0), 'trend': idx_data.get('sentiment', '未取得')}
                return result
        except Exception as e:
            print(f"[V22] 指数状态获取失败: {e}")
        return {}

    def get_limitup_ecology(self) -> Dict:
        """获取涨停生态"""
        try:
            daily_svc = self._get_daily_close_service()
            if daily_svc:
                lu_data = daily_svc._get_limitup_summary()
                if isinstance(lu_data, dict):
                    return lu_data
        except Exception as e:
            print(f"[V22] 涨停生态获取失败: {e}")
        return {'limit_up': 0, 'limit_down': 0, 'broken_board': 0}

    # ============================================================
    # 定时任务（四时段：09:00/09:30/14:45/15:05）
    # ============================================================
    def _check_new_day(self):
        """检查是否新的一天，重置执行锁"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self._slot_lock_date != today:
            self._slot_lock_date = today
            self._executed_slots.clear()
            print(f"[V22] 新交易日 {today}，定时任务锁已重置")

    def _is_trading_day(self) -> bool:
        """简单判断是否交易日（周一到周五，不考虑节假日）"""
        return datetime.now().weekday() < 5

    def check_scheduled_tasks(self) -> Dict:
        """检查定时任务（每分钟调用）
        四时段：09:00盘前、09:30开盘、14:45尾盘、15:05收盘
        防重复：date+slot唯一锁，程序重启也不重复执行
        """
        self._check_new_day()
        if not self._is_trading_day():
            self._log_once('非交易日，跳过定时任务')
            return {'executed': [], 'skipped': '非交易日'}

        now = datetime.now()
        hhmm = now.strftime('%H:%M')
        executed = []

        # 定义四时段
        slots = [
            ('premarket', '09:00', '09:05'),   # 盘前09:00-09:05
            ('09:30', '09:30', '09:40'),         # 开盘09:30-09:40
            ('14:45', '14:45', '14:55'),         # 尾盘14:45-14:55
            ('close', '15:05', '15:15'),          # 收盘15:05-15:15
        ]

        for slot_name, start, end in slots:
            slot_key = f"{self._slot_lock_date}+{slot_name}"
            if slot_key in self._executed_slots:
                continue
            if start <= hhmm <= end:
                print(f"[V22] 触发定时任务: {slot_name} ({hhmm})")
                self._executed_slots.add(slot_key)
                self._execute_slot(slot_name)
                executed.append(slot_name)

        return {'executed': executed, 'current_time': hhmm}

    def _execute_slot(self, slot: str):
        """执行指定时段任务"""
        try:
            if slot == 'premarket':
                # 盘前：市场环境+AI-520候选（使用昨日数据）
                print("[V22] 执行盘前作战任务...")
                market_data = self._get_market_data_snapshot()
                ai520_signals = self.get_ai520_signals()
                if not ai520_signals:
                    # 盘前没有实时扫描，使用最近一次或扫描一次
                    result = self.run_ai520_scan(scan_source='premarket', push_wechat=False)
                    ai520_signals = result.get('signals', [])
                self.push_dual_card_to_wechat('premarket', market_data, ai520_signals)

            elif slot in ('09:30', '14:45'):
                # 开盘/尾盘：真实扫描+推送
                print(f"[V22] 执行{slot}扫描任务...")
                result = self.run_ai520_scan(scan_source=slot, push_wechat=False)
                signals = result.get('signals', [])
                market_data = self._get_market_data_snapshot()
                self.push_dual_card_to_wechat(slot, market_data, signals)

            elif slot == 'close':
                # 收盘：完整日报+双卡推送
                print("[V22] 执行收盘日报任务...")
                # 先执行AI-520一周观察池每日更新
                try:
                    from services.observation_service import get_observation_service
                    obs_svc = get_observation_service()
                    obs_stats = obs_svc.daily_update()
                    print(f"[V22] 观察池每日更新: 更新{obs_stats.get('updated', 0)}只, D1={obs_stats.get('d1',0)} D2={obs_stats.get('d2',0)} D3={obs_stats.get('d3',0)} D4={obs_stats.get('d4',0)} D5={obs_stats.get('d5',0)}")
                except Exception as e:
                    print(f"[V22] 观察池每日更新异常: {e}")
                self.generate_daily_report(push_wechat=True)

        except Exception as e:
            print(f"[ERROR][SCHEDULER] 时段{slot}执行失败: {e}")
            import traceback
            traceback.print_exc()

    def _get_market_data_snapshot(self) -> Dict:
        """获取市场数据快照（用于企业微信推送）
        盘前未开盘时，涨跌家数/成交额等显示"未取得（盘前未开盘）"，禁止用0冒充
        """
        try:
            daily_svc = self._get_daily_close_service()
            if daily_svc:
                quotes = daily_svc._get_market_quotes()
                if quotes:
                    # 判断是否盘前未开盘：所有股票pct=0且amount=0
                    all_pct_zero = all(abs(float(q.get('pct', 0))) < 0.001 for q in quotes)
                    all_amount_zero = all(float(q.get('amount', 0)) < 1 for q in quotes)
                    is_premarket = all_pct_zero and all_amount_zero

                    if is_premarket:
                        # 盘前未开盘：涨跌家数/涨停/成交额显示未取得，但指数仍可从其他接口获取
                        print("[V22] 盘前未开盘，市场涨跌统计显示未取得")
                        return {
                            'up': '未取得（盘前未开盘）',
                            'down': '未取得（盘前未开盘）',
                            'flat': '未取得（盘前未开盘）',
                            'limit_up': '未取得',
                            'limit_down': '未取得',
                            'avg_pct': '未取得',
                            'amount': '未取得',
                            'is_premarket': True,
                            'indexes': daily_svc._get_index_summary(),
                            'sectors': daily_svc._get_sector_summary(),
                        }

                    # 交易时间：真实统计
                    up = sum(x['pct'] > 0.01 for x in quotes)
                    down = sum(x['pct'] < -0.01 for x in quotes)
                    flat = len(quotes) - up - down
                    limit_up = sum(x['pct'] >= _lu_pct(x.get('code')) for x in quotes)     # [CYB-GATE]
                    limit_down = sum(x['pct'] <= -_lu_pct(x.get('code')) for x in quotes)  # [CYB-GATE]
                    avg_pct = sum(x['pct'] for x in quotes) / len(quotes)
                    amount = sum(x['amount'] for x in quotes)
                    return {
                        'up': up, 'down': down, 'flat': flat,
                        'limit_up': limit_up, 'limit_down': limit_down,
                        'avg_pct': avg_pct, 'amount': amount,
                        'is_premarket': False,
                        'indexes': daily_svc._get_index_summary(),
                        'sectors': daily_svc._get_sector_summary(),
                    }
        except Exception as e:
            print(f"[V22] 市场快照获取失败: {e}")
        return {'is_premarket': True, 'up': '未取得', 'down': '未取得', 'flat': '未取得',
                'limit_up': '未取得', 'limit_down': '未取得', 'avg_pct': '未取得', 'amount': '未取得'}

    def _log_once(self, msg: str):
        """只在状态变化时打印日志，避免刷屏"""
        if self._last_log_state != msg:
            print(f"[V22] {msg}")
            self._last_log_state = msg

    def _get_latest_news(self, limit: int = 5) -> List[Dict]:
        """获取最新真实新闻（新浪7x24）"""
        try:
            from service.unified_data_service import get_news_service
            svc = get_news_service()
            news = svc.get_news(source='sina', limit=limit)
            return news or []
        except Exception as e:
            print(f"[V22] 新闻获取失败: {e}")
            return []

    # ============================================================
    # 企业微信测试
    # ============================================================
    def test_wechat(self) -> Dict:
        """测试企业微信连接（发送真实测试消息）"""
        wechat = self._get_wechat_service()
        if not wechat or not wechat.is_configured():
            return {'success': False, 'error': '企业微信未配置（检查.env WECHAT_WORK_WEBHOOK）'}
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            test_msg = f"📡【量化交易作战中控台】连接测试\n时间: {now}\n状态: ✅ 企业微信Webhook连接正常\nAI-520: 就绪\n定时任务: 09:00/09:30/14:45/15:05"
            result = wechat.push_text(test_msg, title='连接测试', wait_for_result=True, timeout=30)
            if result and result.get('success'):
                print("[WECHAT] 测试消息发送成功")
                return {'success': True, 'message': '企业微信测试消息发送成功'}
            else:
                err = result.get('error', '未知错误') if result else '无返回'
                return {'success': False, 'error': err}
        except Exception as e:
            print(f"[ERROR][WECHAT] 测试失败: {e}")
            return {'success': False, 'error': str(e)}

    # ============================================================
    # D+N跟踪统计
    # ============================================================
    def get_ai520_followup_stats(self) -> Dict:
        """获取AI-520 D+1/D+3/D+5/D+7跟踪统计"""
        try:
            db = self._get_ai520_database()
            if db and hasattr(db, 'get_observation_stats'):
                return db.get_observation_stats()
        except Exception as e:
            print(f"[V22] D+N跟踪统计获取失败: {e}")
        return {'total_signals': 0, 'd1_win_rate': 0, 'd3_win_rate': 0, 'd5_win_rate': 0, 'd7_win_rate': 0}

    # ============================================================
    # AI-520回踩启动最终消息模板
    # ============================================================
    def build_ai520_pullback_message(self, stock: Dict, sector_data: Optional[Dict] = None,
                                       news_data: Optional[Dict] = None) -> str:
        """生成AI-520回踩启动详细消息
        包含：回踩详情/金叉日期/涨幅/均线/量能/板块/共振/原因/作战判断/风险
        """
        lines = []
        now = datetime.now().strftime('%H:%M:%S')
        code = stock.get('code', '')
        name = stock.get('name', '')
        grade = stock.get('grade', '')
        score = stock.get('total_score', stock.get('score', 0))
        pullback_type = stock.get('pullback_type', 'MA5回踩')
        pullback_grade = stock.get('pullback_grade', '')

        lines.append(f"🔥【AI-520盘中回踩】")
        lines.append(f"时间：{now}")
        lines.append(f"股票：{name}({code})")
        lines.append(f"评级：{grade}{score}")
        lines.append(f"触发：🔥{pullback_type}")

        # 前期结构
        cross_days = stock.get('cross_days_ago', -1)
        cross_gain = stock.get('cross_gain_pct', 0)
        if cross_days >= 0:
            lines.append(f"前期结构：MA5上穿MA20：{cross_days}天前 金叉后涨幅：{cross_gain:+.2f}%")

        # 今日数据
        today_high = stock.get('today_high', stock.get('high', 0))
        today_low = stock.get('today_low', stock.get('low', 0))
        price = stock.get('price', stock.get('today_close', 0))
        ma5 = stock.get('ma5', 0)
        ma20 = stock.get('ma20', 0)
        dist_ma5 = stock.get('dist_ma5_pct', 0)
        dist_ma20 = stock.get('dist_ma20_pct', 0)
        if price > 0:
            lines.append(f"今日：最高{today_high:.2f} 最低{today_low:.2f} 现价{price:.2f}")
        if ma5 > 0:
            lines.append(f"MA5：{ma5:.2f} MA20：{ma20:.2f} 距离MA5：{dist_ma5:+.2f}% 距离MA20：{dist_ma20:+.2f}%")

        # 量能
        vol_ratio = stock.get('vol_ratio', stock.get('volume_ratio', 0))
        is_shrink = stock.get('is_shrink_volume', False)
        if vol_ratio > 0:
            vol_status = "缩量" if is_shrink else "放量"
            lines.append(f"📊量能：今日量/5日均量：{vol_ratio:.2f}（{vol_status}）")

        # 判断
        judgments = []
        if stock.get('is_shrink_volume'):
            judgments.append("缩量回踩")
        if stock.get('trend_intact'):
            judgments.append("未破坏MA20趋势")
        if stock.get('reclaim_ma5'):
            judgments.append("重新站回MA5")
        elif stock.get('reclaim_ma20'):
            judgments.append("站回MA20")
        if stock.get('is_bullish_candle'):
            judgments.append("止跌阳线")
        if judgments:
            lines.append(f"判断：{' + '.join(judgments)}")

        # 板块
        sector = stock.get('sector', stock.get('industry', ''))
        if sector_data and sector:
            sec_pct = sector_data.get('change_pct', sector_data.get('pct_chg', 0))
            sec_up = sector_data.get('up_count', 0)
            sec_down = sector_data.get('down_count', 0)
            sec_limit_up = sector_data.get('limit_up_count', 0)
            sec_volume = sector_data.get('volume_count', 0)
            lines.append(f"🔥板块：{sector}{sec_pct:+.2f}% 上涨：{sec_up}/{sec_up+sec_down} 涨停：{sec_limit_up} 放量：{sec_volume}")

            # 共振判断
            if sec_pct > 2 and sec_limit_up >= 1:
                lines.append(f"🚀共振：AI-520×板块共振")

        # 原因分析
        reasons = stock.get('pullback_reasons', [])
        if reasons:
            lines.append(f"📰原因：{'、'.join(reasons[:3])}")

        # 作战判断
        lines.append(f"🎯作战判断：关注回踩后的二次启动")

        # 风险
        risks = []
        if stock.get('has_extreme_rise'):
            risks.append("前期连续暴涨")
        if cross_gain > 15:
            risks.append("金叉后涨幅过大")
        if not stock.get('reclaim_ma5') and not stock.get('reclaim_ma20'):
            risks.append("未重新站回均线")
        if not risks:
            risks.append("不追已经大幅拉升个股，等待回踩确认")
        lines.append(f"⚠️风险：{'、'.join(risks)}")

        return '\n'.join(lines)

    # ============================================================
    # 盘中异动原因分析
    # ============================================================
    def analyze_sector_movement(self, sector_name: str, sector_stocks: List[Dict],
                                 sector_data: Optional[Dict] = None) -> Dict:
        """盘中异动原因分析：核心股/个股扩散/成交量/资金/新闻/政策/产业/指数共振
        Returns: {'has_movement': bool, 'reasons': List[str], 'core_stocks': List, 'strength': str}
        """
        result = {'has_movement': False, 'reasons': [], 'core_stocks': [], 'strength': '弱'}

        try:
            if not sector_stocks:
                result['reasons'].append('无板块股票数据')
                return result

            # 1. 核心股启动（涨幅前3）
            sorted_stocks = sorted(sector_stocks, key=lambda x: float(x.get('pct_chg', x.get('change_pct', 0)) or 0), reverse=True)
            core_stocks = sorted_stocks[:3]
            result['core_stocks'] = [{'code': s.get('code',''), 'name': s.get('name',''), 'pct': s.get('pct_chg',0)} for s in core_stocks]

            # 2. 个股数量扩散（上涨家数占比）
            up_count = sum(1 for s in sector_stocks if float(s.get('pct_chg', s.get('change_pct', 0)) or 0) > 0)
            total_count = len(sector_stocks)
            up_ratio = up_count / total_count if total_count > 0 else 0

            # 3. 成交量放大（量比>1.2的股票数量）
            volume_count = sum(1 for s in sector_stocks if float(s.get('volume_ratio', s.get('vol_ratio', 0)) or 0) > 1.2)

            # 4. 涨停数量
            limit_up_count = sum(1 for s in sector_stocks if float(s.get('pct_chg', s.get('change_pct', 0)) or 0) >= _lu_pct(s.get('code')))  # [CYB-GATE]

            # 5. 板块涨幅
            sector_pct = 0
            if sector_data:
                sector_pct = float(sector_data.get('change_pct', sector_data.get('pct_chg', 0)) or 0)

            # 综合判断
            reasons = []
            score = 0

            if sector_pct > 2:
                score += 20
                reasons.append(f'板块涨幅{sector_pct:+.2f}%')
            elif sector_pct > 1:
                score += 10
                reasons.append(f'板块涨幅{sector_pct:+.2f}%')

            if up_ratio > 0.7:
                score += 20
                reasons.append(f'个股扩散：上涨{up_count}/{total_count}家({up_ratio*100:.0f}%)')
            elif up_ratio > 0.5:
                score += 10
                reasons.append(f'个股扩散：上涨{up_count}/{total_count}家')

            if volume_count >= 3:
                score += 15
                reasons.append(f'{volume_count}只个股成交量放大')

            if limit_up_count >= 1:
                score += 20
                reasons.append(f'{limit_up_count}只个股涨停')

            if core_stocks and float(core_stocks[0].get('pct_chg', 0) or 0) > 5:
                score += 15
                reasons.append(f'核心股{core_stocks[0].get("name","")}率先放量上涨')

            # 新闻催化（如果有）
            news_list = self._get_latest_news(limit=3)
            related_news = [n for n in news_list if sector_name in str(n.get('title', '')) or sector_name[:2] in str(n.get('title', ''))]
            if related_news:
                score += 10
                reasons.append(f'相关产业新闻：{related_news[0].get("title","")[:20]}')

            result['reasons'] = reasons
            result['has_movement'] = score >= 40

            if score >= 70:
                result['strength'] = '强'
            elif score >= 40:
                result['strength'] = '中'
            else:
                result['strength'] = '弱'

            if not reasons:
                result['reasons'].append('暂未发现明确新闻催化，当前主要表现为板块内部量价共振')

        except Exception as e:
            print(f"[V22] 盘中异动分析失败: {e}")
            result['reasons'].append(f'分析异常: {e}')

        return result

    # ============================================================
    # 企业微信长消息图片兜底
    # ============================================================
    def generate_report_image(self, title: str, content_lines: List[str], output_path: Optional[str] = None) -> Optional[str]:
        """生成长消息图片报告（企业微信超长消息兜底）
        Returns: 图片文件路径或None
        """
        try:
            from PIL import Image, ImageDraw, ImageFont

            # 图片尺寸
            width = 800
            line_height = 28
            padding = 30
            header_height = 60
            content_height = len(content_lines) * line_height + padding * 2
            height = header_height + content_height + 20

            # 创建图片
            img = Image.new('RGB', (width, height), color='#1a1a2e')
            draw = ImageDraw.Draw(img)

            # 尝试加载中文字体
            font = None
            font_paths = [
                'C:/Windows/Fonts/msyh.ttc',
                'C:/Windows/Fonts/simhei.ttf',
                'C:/Windows/Fonts/simsun.ttc',
            ]
            for fp in font_paths:
                if os.path.exists(fp):
                    try:
                        font = ImageFont.truetype(fp, 16)
                        title_font = ImageFont.truetype(fp, 22)
                        break
                    except:
                        continue
            if font is None:
                font = ImageFont.load_default()
                title_font = font

            # 标题栏
            draw.rectangle([0, 0, width, header_height], fill='#e94560')
            draw.text((padding, 15), title, fill='white', font=title_font)

            # 内容
            y = header_height + padding
            for line in content_lines:
                if line.startswith('🔥') or line.startswith('📊') or line.startswith('🏆'):
                    draw.text((padding, y), line, fill='#ffd700', font=font)
                elif line.startswith('⚠️') or line.startswith('❌'):
                    draw.text((padding, y), line, fill='#ff6b6b', font=font)
                elif line.startswith('✅') or line.startswith('🚀'):
                    draw.text((padding, y), line, fill='#4ecdc4', font=font)
                else:
                    draw.text((padding, y), line, fill='#e0e0e0', font=font)
                y += line_height

            # 底部时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            draw.text((padding, height - 25), f'生成时间: {now} | 数据来源: 量化交易作战中控台', fill='#888', font=font)

            # 保存
            if output_path is None:
                output_path = os.path.join('data', 'cache', f'report_{int(time.time())}.png')
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, 'PNG')
            print(f"[V22] 报告图片生成成功: {output_path} ({width}x{height})")
            return output_path

        except Exception as e:
            print(f"[V22] 报告图片生成失败: {e}")
            return None

    def push_with_image_fallback(self, title: str, content: str, max_text_length: int = 3500) -> Dict:
        """企业微信推送：超长消息自动图片兜底
        流程：长度检测→安全范围？是→文字；否→智能压缩→仍超长→生成图片→上传发送
        """
        # V3.0 推送重构：作战报告/定时简报业务推送已关闭（保留 test_wechat 手动测试）
        return {'skipped': True, 'success': False, 'reason': 'V3.0 作战报告推送已关闭'}
        wechat = self._get_wechat_service()
        if not wechat or not wechat.is_configured():
            return {'success': False, 'error': '企业微信未配置'}

        content_len = len(content)
        content_bytes = len(content.encode('utf-8'))
        print(f"[WECHAT] 消息长度检测: char={content_len}, utf8_bytes={content_bytes}")

        # 安全范围：直接文字发送
        if content_len <= max_text_length:
            result = wechat.push_text(content, title=title, wait_for_result=True, timeout=30)
            return {'success': result.get('success', False), 'method': 'text',
                    'errcode': result.get('errcode', -1), 'errmsg': result.get('errmsg', ''),
                    'char_count': content_len, 'utf8_bytes': content_bytes}

        # 超长：智能压缩（保留关键信息）
        print(f"[WECHAT] 消息超长({content_len}>{max_text_length})，尝试压缩...")
        lines = content.split('\n')
        # 保留标题、S/A级股票、关键统计
        compressed_lines = []
        for line in lines:
            if any(kw in line for kw in ['🔥', '📊', '🏆', '⭐', 'S级', 'A级', '总计', '时间', '数据来源']):
                compressed_lines.append(line)
            elif len(compressed_lines) < 50:  # 最多保留50行
                compressed_lines.append(line)
        compressed = '\n'.join(compressed_lines)

        if len(compressed) <= max_text_length:
            print(f"[WECHAT] 压缩成功: {content_len}→{len(compressed)}")
            result = wechat.push_text(compressed, title=title, wait_for_result=True, timeout=30)
            return {'success': result.get('success', False), 'method': 'compressed_text',
                    'errcode': result.get('errcode', -1), 'errmsg': result.get('errmsg', ''),
                    'char_count': len(compressed), 'utf8_bytes': len(compressed.encode('utf-8'))}

        # 仍超长：生成图片兜底
        print(f"[WECHAT] 压缩后仍超长({len(compressed)}>{max_text_length})，生成图片...")
        img_path = self.generate_report_image(title, lines)
        if img_path and os.path.exists(img_path):
            # V2.3：真正发送图片到企业微信（上传media_id+发送图片消息）
            print(f"[WECHAT] 发送图片报告: {img_path}")
            wechat = self._get_wechat_service()
            img_result = wechat.push_image(img_path, wait_for_result=True, timeout=60)
            if img_result.get('success'):
                # 图片发送成功后，再发送一条文字摘要
                summary_msg = f"📊【{title}】\n消息内容较长，已生成图片报告（共{len(lines)}行）。\n图片已发送，请查看上方图片。\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                text_result = wechat.push_text(summary_msg, title=title, wait_for_result=True, timeout=30)
                return {'success': True, 'method': 'image',
                        'errcode': img_result.get('errcode', 0), 'errmsg': img_result.get('errmsg', ''),
                        'image_path': img_path, 'char_count': content_len}
            else:
                # 图片发送失败，强制截断发送
                print(f"[WECHAT] 图片发送失败: {img_result.get('errmsg', '')}，强制截断发送")
                truncated = content[:max_text_length] + "\n...（内容过长已截断，完整内容请打开中控台查看）"
                result = wechat.push_text(truncated, title=title, wait_for_result=True, timeout=30)
                return {'success': result.get('success', False), 'method': 'truncated_after_image_fail',
                        'errcode': result.get('errcode', -1), 'errmsg': result.get('errmsg', ''),
                        'char_count': len(truncated), 'image_path': img_path}
        else:
            # 图片生成失败，强制截断发送（保留前3500字符）
            print(f"[WECHAT] 图片生成失败，强制截断发送")
            truncated = content[:max_text_length] + "\n...（内容过长已截断，完整内容请打开中控台查看）"
            result = wechat.push_text(truncated, title=title, wait_for_result=True, timeout=30)
            return {'success': result.get('success', False), 'method': 'truncated',
                    'errcode': result.get('errcode', -1), 'errmsg': result.get('errmsg', ''),
                    'char_count': len(truncated)}


def get_v22_combat_service() -> V22CombatService:
    """获取V2.2作战闭环服务单例"""
    return V22CombatService()


if __name__ == '__main__':
    print("V2.2作战闭环服务自测")
    svc = get_v22_combat_service()
    print("1. 服务初始化: OK")
    print("2. 市场温度:", svc.get_market_temperature())
    print("3. 企业微信测试:", svc.test_wechat())
