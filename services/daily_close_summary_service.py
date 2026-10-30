# -*- coding: utf-8 -*-
"""真实数据收盘总结与企业微信自动推送。
只使用当日实际行情、当日扫描结果和AI-520数据库记录；数据缺失明确标记，不用默认假数据。
"""
import os, json, threading
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(PROJECT_ROOT, 'data', 'daily_close_summary_state.json')

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


class DailyCloseSummaryService:
    def __init__(self):
        self._lock = threading.Lock()

    def _already_pushed(self, date_str: str) -> bool:
        try:
            if not os.path.exists(STATE_PATH): return False
            with open(STATE_PATH, 'r', encoding='utf-8') as f: return json.load(f).get('date') == date_str
        except Exception: return False

    def _mark_pushed(self, date_str: str):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = STATE_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f: json.dump({'date': date_str, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)

    def _get_market_quotes(self) -> List[Dict]:
        from utils.tdx_stock_list import get_stock_list_tdx, get_realtime_quotes_tdx
        stocks = get_stock_list_tdx() or []
        stocks = [s for s in stocks if (s.get('code','').startswith(('600','601','603','605','000','001','002')))]
        stocks = [s for s in stocks if 'ST' not in s.get('name','').upper()]
        codes = [s['code'] for s in stocks]
        quotes = get_realtime_quotes_tdx(codes) or {}
        out=[]
        for s in stocks:
            q=quotes.get(s['code'])
            if not q: continue
            out.append({'code':s['code'],'name':s.get('name',''),'price':float(q.get('price') or 0),'pct':float(q.get('pct_chg') or 0),'amount':float(q.get('amount') or 0)})
        return [x for x in out if x['price'] > 0]

    def _get_ai520(self, date_str: str) -> List[Dict]:
        try:
            from strategy.ai_520_database import AI520Database
            return AI520Database().get_today_signals(date_str)
        except Exception as e:
            print(f'[收盘总结] AI-520读取失败: {e}')
            return []

    def _get_ai520_stats(self) -> Dict:
        """读取AI-520历史观察表现，仅使用本地数据库已有真实记录。"""
        try:
            from strategy.ai_520_database import AI520Database
            return AI520Database().get_observation_stats() or {}
        except Exception as e:
            print(f'[收盘总结] AI-520观察统计读取失败: {e}')
            return {}

    def _get_index_summary(self) -> Dict:
        """读取主要指数与市场情绪；失败时明确返回空，不制造默认行情。"""
        result = {'indexes': [], 'sentiment': '未知', 'source': ''}
        try:
            from strategy.market_sector_analyzer import get_market_analyzer
            analyzer = get_market_analyzer()
            indexes = analyzer.get_index_quotes() or []
            if indexes:
                result['indexes'] = indexes
                result['sentiment'] = analyzer.get_market_sentiment(indexes)
                result['source'] = '腾讯指数行情'
        except Exception as e:
            print(f'[收盘总结] 指数读取失败: {e}')
        return result

    def _get_sector_summary(self) -> Dict:
        """读取真实行业板块排名；失败不使用mock数据。"""
        result = {'top': [], 'weak': [], 'source': ''}
        try:
            from strategy.market_sector_analyzer import get_sector_analyzer
            analyzer = get_sector_analyzer()
            sectors = analyzer.get_sector_ranking() or []
            if sectors:
                result['top'] = analyzer.get_top10_sectors(sectors)[:5]
                result['weak'] = analyzer.get_weak10_sectors(sectors)[:3]
                result['source'] = '东方财富行业板块'
        except Exception as e:
            print(f'[收盘总结] 板块读取失败: {e}')
        return result

    def _get_limitup_summary(self) -> Dict:
        """读取真实涨停池及连板数据。"""
        result = {'stocks': [], 'count': 0, 'max_lbc': 0, 'source': ''}
        try:
            from market.limit_up_center import get_today_limit_up_stocks
            stocks = get_today_limit_up_stocks() or []
            stocks = [x for x in stocks if not str(x.get('name', '')).upper().startswith('ST')]
            result['stocks'] = sorted(stocks, key=lambda x: (int(x.get('lbc') or 0), float(x.get('pct_chg') or 0)), reverse=True)
            result['count'] = len(stocks)
            result['max_lbc'] = max([int(x.get('lbc') or 0) for x in stocks] or [0])
            result['source'] = '东方财富涨停池'
        except Exception as e:
            print(f'[收盘总结] 涨停池读取失败: {e}')
        return result

    def _get_news_summary(self) -> List[Dict]:
        """只取当天真实快讯，最多3条；网络失败则不填充假新闻。"""
        try:
            from market.news_center import NewsProvider
            news = NewsProvider().get_eastmoney_news(page=1, page_size=10) or []
            today = datetime.now().strftime('%Y-%m-%d')
            out = []
            for n in news:
                d = n.to_dict() if hasattr(n, 'to_dict') else dict(n)
                t = str(d.get('time', ''))
                if today in t or not today:
                    title = str(d.get('title', '')).strip()
                    if title:
                        out.append({'title': title, 'time': t, 'source': d.get('source', '')})
                if len(out) >= 3:
                    break
            return out
        except Exception as e:
            print(f'[收盘总结] 新闻读取失败: {e}')
            return []

    def _find_previous_cache_date(self, current_date: str) -> str:
        """寻找最近一个已有真实日行情缓存日期，不把自然日当交易日。"""
        root = os.path.join(PROJECT_ROOT, 'data', 'cache', 'daily')
        try:
            dates = [d for d in os.listdir(root) if len(d) == 10 and d < current_date and os.path.exists(os.path.join(root, d, 'stocks.json'))]
            return max(dates) if dates else ''
        except Exception:
            return ''

    def _load_cached_quotes(self, date_str: str) -> List[Dict]:
        """读取项目保存的历史真实行情，仅用于历史对比。"""
        if not date_str:
            return []
        path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'daily', date_str, 'stocks.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            rows = obj.get('stocks', []) if isinstance(obj, dict) else obj
            return [x for x in rows if x.get('code') and float(x.get('price') or 0) > 0]
        except Exception:
            return []

    def _build_history_comparison(self, today_quotes: List[Dict], today_date: str) -> Dict:
        """计算昨日→今日市场变化、昨日涨停次日表现、成交额变化。"""
        prev_date = self._find_previous_cache_date(today_date)
        prev = self._load_cached_quotes(prev_date)
        if not prev:
            return {'prev_date': '', 'prev_total': 0}
        pm = {x['code']: x for x in prev}
        matched = [x for x in today_quotes if x['code'] in pm]
        prev_amount = sum(float(x.get('amount') or 0) for x in prev)
        today_amount = sum(float(x.get('amount') or 0) for x in today_quotes)
        prev_up = sum(float(x.get('pct_chg') or 0) > 0.01 for x in prev)
        prev_down = sum(float(x.get('pct_chg') or 0) < -0.01 for x in prev)
        yesterday_limit = [x for x in prev if float(x.get('pct_chg') or 0) >= _lu_pct(x.get('code'))]  # [CYB-GATE]
        ymap = {x['code']: x for x in yesterday_limit}
        ymatched = [x for x in matched if x['code'] in ymap]
        yreturns = [float(x.get('pct') or 0) for x in ymatched]
        return {
            'prev_date': prev_date, 'prev_total': len(prev), 'matched': len(matched),
            'prev_up': prev_up, 'prev_down': prev_down, 'prev_amount': prev_amount,
            'amount_change': ((today_amount / prev_amount - 1) * 100) if prev_amount > 0 else None,
            'y_limit_count': len(yesterday_limit), 'y_matched': len(ymatched),
            'y_up': sum(v > 0.01 for v in yreturns), 'y_down': sum(v < -0.01 for v in yreturns),
            'y_avg': sum(yreturns) / len(yreturns) if yreturns else None,
            'y_max': max(yreturns) if yreturns else None, 'y_min': min(yreturns) if yreturns else None,
            'y_profit_rate': (sum(v > 0.01 for v in yreturns) / len(yreturns) * 100) if yreturns else None,
        }

    def _get_ai520_followup(self, today_quotes: List[Dict], today_date: str) -> Dict:
        """上一交易日AI-520信号的D+1真实行情验证。"""
        try:
            prev_date = self._find_previous_cache_date(today_date)
            if not prev_date:
                return {'prev_date': '', 'total': 0}
            from strategy.ai_520_database import AI520Database
            signals = AI520Database().get_today_signals(prev_date) or []
            qmap = {x['code']: x for x in today_quotes}
            rows = []
            for x in signals:
                q = qmap.get(x.get('code'))
                base = float(x.get('price') or 0)
                if not q or base <= 0:
                    continue
                ret = (float(q.get('price') or 0) / base - 1) * 100
                rows.append({'code': x.get('code'), 'name': x.get('name'), 'grade': x.get('grade'), 'score': x.get('total_score'), 'ret': ret})
            if not rows:
                return {'prev_date': prev_date, 'total': 0}
            sa = [r for r in rows if str(r.get('grade') or '').upper() in ('S', 'A')]
            return {
                'prev_date': prev_date, 'total': len(rows), 'sa_total': len(sa),
                'up': sum(r['ret'] > 0.01 for r in rows), 'avg': sum(r['ret'] for r in rows) / len(rows),
                'sa_up_rate': (sum(r['ret'] > 0.01 for r in sa) / len(sa) * 100) if sa else None,
                'sa_avg': (sum(r['ret'] for r in sa) / len(sa)) if sa else None,
                'best': max(rows, key=lambda r: r['ret']), 'worst': min(rows, key=lambda r: r['ret']),
            }
        except Exception as e:
            print(f'[收盘总结] AI-520昨日跟踪失败: {e}')
            return {'prev_date': '', 'total': 0}

    def _market_temperature(self, s: Dict) -> int:
        """0-100市场温度；只由本次真实市场统计计算。"""
        total = max(int(s.get('total') or 0), 1)
        breadth = (int(s.get('up') or 0) - int(s.get('down') or 0)) / total
        avg = float(s.get('avg_pct') or 0)
        lu = int(s.get('limit_up') or 0)
        ld = int(s.get('limit_down') or 0)
        score = 50 + breadth * 45 + avg * 8 + min(lu, 100) * 0.12 - min(ld, 50) * 0.25
        return max(0, min(100, round(score)))

    def build_summary(self, app_window=None) -> Dict:
        date_str = datetime.now().strftime('%Y-%m-%d')
        quotes = self._get_market_quotes()
        if not quotes:
            raise RuntimeError('通达信未返回有效收盘行情，未生成总结，避免推送空壳数据')

        up = sum(x['pct'] > 0.01 for x in quotes)
        down = sum(x['pct'] < -0.01 for x in quotes)
        flat = len(quotes) - up - down
        limit_up = sum(x['pct'] >= _lu_pct(x.get('code')) for x in quotes)     # [CYB-GATE]
        limit_down = sum(x['pct'] <= -_lu_pct(x.get('code')) for x in quotes)  # [CYB-GATE]
        avg = sum(x['pct'] for x in quotes) / len(quotes)
        total_amount = sum(x['amount'] for x in quotes)
        top = sorted(quotes, key=lambda x: x['pct'], reverse=True)[:10]
        bottom = sorted(quotes, key=lambda x: x['pct'])[:5]
        ai = self._get_ai520(date_str)
        ai.sort(key=lambda x: float(x.get('total_score') or 0), reverse=True)
        ai_stats = self._get_ai520_stats()

        indexes = self._get_index_summary()
        sectors = self._get_sector_summary()
        limitups = self._get_limitup_summary()
        news = self._get_news_summary()

        history = self._build_history_comparison(quotes, date_str)
        ai_follow = self._get_ai520_followup(quotes, date_str)
        # 市场风险等级：只基于本次真实统计的涨跌家数、涨跌停与平均涨跌，不假造历史数据。
        breadth = (up - down) / max(len(quotes), 1)
        if breadth >= 0.35 and avg >= 1:
            risk = '进攻'
        elif breadth >= 0.10 and avg >= 0:
            risk = '偏强'
        elif breadth <= -0.35 and avg <= -1:
            risk = '防守'
        elif breadth <= -0.10 and avg < 0:
            risk = '偏弱'
        else:
            risk = '震荡'

        return {
            'date': date_str,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total': len(quotes), 'up': up, 'down': down, 'flat': flat,
            'limit_up': limit_up, 'limit_down': limit_down,
            'avg_pct': avg, 'amount': total_amount, 'top': top, 'bottom': bottom,
            'ai520': ai, 'ai520_stats': ai_stats, 'indexes': indexes, 'sectors': sectors,
            'limitups': limitups, 'news': news, 'risk': risk,
            'history': history, 'ai_follow': ai_follow,
            'big_up5': sum(x['pct'] >= 5 for x in quotes), 'big_down5': sum(x['pct'] <= -5 for x in quotes),
        }

    @staticmethod
    def _fmt_amount(value: float) -> str:
        # 通达信成交额字段为元；异常/缺失不显示成虚假0。
        if value is None or value <= 0:
            return '--'
        return f'{value / 1e8:.2f}亿'

    @staticmethod
    def _fmt_money(value) -> str:
        try:
            v = float(value or 0)
        except Exception:
            return '--'
        if v <= 0:
            return '--'
        if v >= 1e8:
            return f'{v / 1e8:.2f}亿'
        if v >= 1e4:
            return f'{v / 1e4:.2f}万'
        return f'{v:.0f}'

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _bool_mark(value) -> str:
        return '是' if bool(value) else '否'

    def format_text(self, s: Dict) -> str:
        """生成一条完整收盘作战日报。

        设计目标：企业微信群机器人只收到一条消息，但尽可能覆盖
        指数、市场宽度、成交额、涨跌停、连板、板块、AI-520、强弱股、新闻、
        明日盯盘和数据质量。所有数字必须来自本次真实数据，缺失统一显示--。
        """
        lines = []
        date = s.get('date', '--')
        lines += [
            f'📊【量化交易｜收盘作战总报告】{date}',
            f'⏱ 生成时间：{s.get("generated_at", "--")}',
            f'🎯 今日市场状态：{s.get("risk", "未知")}',
            f'🌡 市场温度：{self._market_temperature(s)}/100',
            '',
            '━━━━━━━━━━━━━━',
            '📈【一、指数收盘表现】',
        ]

        indexes = s.get('indexes', {}) or {}
        idx_list = indexes.get('indexes', []) or []
        if idx_list:
            for idx in idx_list[:3]:
                name = idx.get('name', '指数')
                price = self._safe_float(idx.get('price'))
                pct = self._safe_float(idx.get('pct_chg'))
                amount = self._fmt_money(idx.get('amount'))
                extra = f' 成交额{amount}' if amount != '--' else ''
                lines.append(f'• {name}：{price:.2f}  {pct:+.2f}%{extra}')
        else:
            lines.append('• 指数：本次未取得有效数据')
        lines += [
            f'• 主板有效行情：{s.get("total", 0)}只',
            f'• 上涨：{s.get("up", 0)}  下跌：{s.get("down", 0)}  平盘：{s.get("flat", 0)}',
            f'• 涨停约：{s.get("limit_up", 0)}  跌停约：{s.get("limit_down", 0)}  个股平均涨跌：{self._safe_float(s.get("avg_pct")):+.2f}%',
            f'• 主板成交额合计：{self._fmt_amount(s.get("amount"))}',
            f'• 市场情绪：{indexes.get("sentiment", "未知")}',
        ]

        # 市场宽度：让用户一眼看到多空强弱，而不是只看指数。
        total = max(int(s.get('total') or 0), 1)
        breadth = (int(s.get('up') or 0) - int(s.get('down') or 0)) / total * 100
        lines.append(f'• 市场宽度：上涨-下跌占比 {breadth:+.1f}个百分点')

        lines += ['', '🔥【二、涨停/跌停/连板｜短线情绪】']
        lu = s.get('limitups', {}) or {}
        lines.append(f'• 涨停池：{lu.get("count", 0)}只  最高连板：{lu.get("max_lbc", 0)}板')
        lus = lu.get('stocks', []) or []
        if lus:
            no_break = sum(1 for x in lus if int(self._safe_float(x.get('break_count'), 0)) == 0)
            seal_rate = no_break / len(lus) * 100 if lus else 0
            lbc_counts = {}
            for x in lus:
                n = int(self._safe_float(x.get('lbc'), 1))
                lbc_counts[n] = lbc_counts.get(n, 0) + 1
            ladder = ' '.join(f'{k}板:{v}' for k, v in sorted(lbc_counts.items(), reverse=True)[:5])
            lines.append(f'• 封板强度：未炸板{no_break}只｜近似封板率{seal_rate:.1f}%｜连板梯队：{ladder or "--"}')
            for i, x in enumerate(lus[:7], 1):
                name = x.get('name', '--')
                code = x.get('code', '--')
                lbc = int(self._safe_float(x.get('lbc'), 1))
                pct = self._safe_float(x.get('pct_chg'))
                industry = x.get('industry') or '--'
                first_t = x.get('first_limit_time') or '--'
                last_t = x.get('last_limit_time') or '--'
                breaks = int(self._safe_float(x.get('break_count'), 0))
                seal = self._fmt_money(x.get('seal_amount'))
                lines.append(f'• {i}. {name}({code}) {lbc}板 {pct:+.2f}%｜首封{first_t} 末封{last_t} 炸板{breaks}次')
                lines.append(f'  行业/原因：{industry}｜封单：{seal}')
        else:
            lines.append('• 涨停池：本次未取得有效数据')

        lines += ['', '🏆【三、行业板块强弱TOP】']
        sectors = s.get('sectors', {}) or {}
        top_secs = sectors.get('top', []) or []
        weak_secs = sectors.get('weak', []) or []
        if top_secs:
            for i, x in enumerate(top_secs[:5], 1):
                name = x.get('name', '--')
                pct = self._safe_float(x.get('pct_chg'))
                flow = self._fmt_money(x.get('net_inflow'))
                upc = x.get('up_count', '--')
                downc = x.get('down_count', '--')
                leader = x.get('leader') or '--'
                lines.append(f'• 强{i}. {name} {pct:+.2f}%｜资金{flow}｜涨{upc}/跌{downc}｜龙头{leader}')
        else:
            lines.append('• 强势板块：本次未取得有效数据')
        if weak_secs:
            weak_text = []
            for x in weak_secs[:3]:
                weak_text.append(f'{x.get("name", "--")} {self._safe_float(x.get("pct_chg")):+.2f}%')
            lines.append('• 弱势板块：' + '｜'.join(weak_text))

        lines += ['', '🎯【四、AI-520今日全量信号】']
        ai = s.get('ai520', []) or []
        grades = {}
        for x in ai:
            g = str(x.get('grade') or '--').upper()
            grades[g] = grades.get(g, 0) + 1
        lines.append(f'• 信号总数：{len(ai)}｜S：{grades.get("S",0)}｜A：{grades.get("A",0)}｜B：{grades.get("B",0)}｜C：{grades.get("C",0)}')
        ast = s.get('ai520_stats', {}) or {}
        if ast.get('d7_total'):
            lines.append(f'• 历史D+7观察：{ast.get("d7_total",0)}例｜胜率{self._safe_float(ast.get("d7_win_rate")):.1f}%｜平均收益{self._safe_float(ast.get("d7_avg_return")):+.2f}%｜最大{self._safe_float(ast.get("d7_max_return")):+.2f}%｜最差{self._safe_float(ast.get("d7_min_return")):+.2f}%')
        else:
            lines.append('• 历史D+7观察：暂无完成样本，不虚构胜率')
        sa = [x for x in ai if str(x.get('grade', '')).upper() in ('S', 'A')]
        if sa:
            for i, x in enumerate(sa[:4], 1):
                name = x.get('name', '--'); code = x.get('code', '--')
                score = self._safe_float(x.get('total_score'))
                grade = str(x.get('grade') or '--')
                price = self._safe_float(x.get('price'))
                pct = self._safe_float(x.get('pct_chg'))
                sector = x.get('sector_name') or x.get('industry') or '--'
                sec_pct = self._safe_float(x.get('sector_pct'))
                sec_rank = x.get('sector_rank', '--')
                sec_lu = x.get('sector_limit_up', '--')
                flow = self._fmt_money(x.get('sector_fund_flow'))
                vol = self._safe_float(x.get('vol_ratio'))
                d8 = self._safe_float(x.get('dist_from_8m_high'))
                brk = self._bool_mark(x.get('break_10d_high'))
                lc1 = x.get('limit_count_1y', '--')
                lc20 = x.get('limit_count_20d', '--')
                news_status = x.get('news_status') or '--'
                lines.append(f'• {i}. {name}({code})｜{grade} {score:.1f}分｜价{price:.2f} {pct:+.2f}%')
                lines.append(f'  板块：{sector} {sec_pct:+.2f}%｜排名{sec_rank}｜板块涨停{sec_lu}｜资金{flow}')
                lines.append(f'  量能：{vol:.2f}倍｜距8月高：{d8:.1f}%｜破10日高：{brk}｜1年涨停{lc1}次｜20日涨停{lc20}次｜新闻{news_status}')
                reasons = x.get('reasons', [])
                risks = x.get('risks', [])
                if isinstance(reasons, str):
                    try: reasons = json.loads(reasons)
                    except Exception: reasons = [reasons]
                if isinstance(risks, str):
                    try: risks = json.loads(risks)
                    except Exception: risks = [risks]
                if reasons:
                    lines.append('  看好：' + '；'.join(str(r) for r in reasons[:2]))
                if risks:
                    lines.append('  风险：' + '；'.join(str(r) for r in risks[:2]))
        else:
            lines.append('• 今日无S/A级信号；仍保留全部信号数量统计。')

        lines += ['', '📌【五、全市场强弱股】']
        top = s.get('top', []) or []
        bottom = s.get('bottom', []) or []
        if top:
            lines.append('• 今日涨幅TOP：')
            for i, x in enumerate(top[:5], 1):
                lines.append(f'  {i}. {x.get("name", "--")}({x.get("code", "--")}) {self._safe_float(x.get("pct")):+.2f}%')
        if bottom:
            lines.append('• 今日跌幅TOP：')
            for i, x in enumerate(bottom[:5], 1):
                lines.append(f'  {i}. {x.get("name", "--")}({x.get("code", "--")}) {self._safe_float(x.get("pct")):+.2f}%')

        h = s.get('history', {}) or {}
        lines += ['', '📊【六、昨日→今日市场变化】']
        if h.get('prev_date'):
            ac = h.get('amount_change')
            ac_text = f'{ac:+.2f}%' if ac is not None else '--'
            lines.append(f'• 对比：{h.get("prev_date")} → {s.get("date")}｜成交额变化：{ac_text}')
            lines.append(f'• 昨日涨跌：{h.get("prev_up",0)}↑/{h.get("prev_down",0)}↓ → 今日{s.get("up",0)}↑/{s.get("down",0)}↓')
            if h.get('y_limit_count'):
                yr = h.get('y_avg'); yp = h.get('y_profit_rate')
                lines.append(f'• 昨日涨停：{h.get("y_limit_count")}只｜今日匹配{h.get("y_matched")}只｜次日上涨率：{yp:.1f}%｜平均：{yr:+.2f}%')
                lines.append(f'• 昨日涨停今日表现：最高{h.get("y_max"):+.2f}%｜最低{h.get("y_min"):+.2f}%')
        else:
            lines.append('• 历史对比：暂无本地有效历史缓存，不虚构环比数据')

        af = s.get('ai_follow', {}) or {}
        lines += ['', '🔁【七、AI-520昨日信号今日验证】']
        if af.get('total'):
            lines.append(f'• {af.get("prev_date")}信号：{af.get("total")}只｜上涨{af.get("up")}只｜平均{af.get("avg"):+.2f}%')
            if af.get('sa_total'):
                lines.append(f'• S/A：{af.get("sa_total")}只｜上涨率{af.get("sa_up_rate"):.1f}%｜平均{af.get("sa_avg"):+.2f}%')
            best = af.get('best'); worst = af.get('worst')
            if best: lines.append(f'• 最强：{best.get("name")}({best.get("code")}) {best.get("ret"):+.2f}%')
            if worst: lines.append(f'• 最弱：{worst.get("name")}({worst.get("code")}) {worst.get("ret"):+.2f}%')
        else:
            lines.append('• 暂无可匹配的上一交易日AI-520信号，不虚构验证结果')

        temp = self._market_temperature(s)
        temp_state = '强进攻' if temp >= 75 else ('偏进攻' if temp >= 60 else ('震荡' if temp >= 40 else ('偏防守' if temp >= 25 else '强防守')))
        lines += ['', '🌡【八、市场温度/风险雷达】', f'• 温度：{temp}/100｜状态：{temp_state}', f'• 涨停{int(s.get("limit_up") or 0)}｜跌停{int(s.get("limit_down") or 0)}｜大涨≥5%：{s.get("big_up5","--")}｜大跌≤-5%：{s.get("big_down5","--")}', f'• 综合风险：{s.get("risk", "未知")}｜策略：{("优先回调启动/板块共振" if temp>=60 else "降低追高，等待确认" if temp<40 else "控制仓位，等待方向")}']

        lines += ['', '📰【九、实时新闻/公告线索】']
        news = s.get('news', []) or []
        if news:
            for i, n in enumerate(news[:3], 1):
                title = str(n.get('title') or '--').replace('\n', ' ').strip()
                nt = n.get('time') or '--'
                src = n.get('source') or '--'
                lines.append(f'• {i}. [{nt}] {title}｜{src}')
        else:
            lines.append('• 当日未取得有效新闻，不使用模拟内容。')

        lines += [
            '',
            '🎯【十、明日作战重点】',
            '• 第一优先：S/A级 + 强势板块 + 板块资金/涨停联动 + 回调后重新启动。',
            '• 第二优先：站上MA5/MA10、量能确认、接近但未远离20日线的个股。',
            '• 重点观察：20日内涨停记忆、回调后重新站回5日线、突破10日高。',
            '• 回避：连续大涨后高位无板块共振、无新闻支撑、量价背离的追高票。',
            '• AI-520是筛选/盯盘信号，不直接等同买入；T+1交易规则必须遵守。',
            '',
            '📡【十一、数据质量与来源】',
            '• 主板行情：通达信实时行情（600/601/603/605/000/001/002，排除ST）',
            '• 指数：项目指数行情接口｜板块：东方财富行业板块',
            '• 涨停池：东方财富涨停池｜AI-520：本地当日数据库｜新闻：项目实时新闻源',
            '• 任一模块无真实数据时明确标记“未取得”，绝不填充模拟数字。',
            '⚠️ 本报告用于量化盯盘与复盘，不构成投资建议。',
        ]

        text = '\n'.join(lines)
        # 企业微信机器人 text.content 上限约4096字节；保留一条消息，不拆成多条。
        # 优先完整保留前面的市场核心数据，再从明日作战/新闻等长文本开始裁剪。
        raw = text.encode('utf-8')
        if len(raw) > 3900:
            # 分优先级重新构建：核心行情 + 涨停 + 板块 + AI前3 + 强弱 + 新闻前2 + 风控
            keep_sections = []
            current = []
            total_bytes = 0
            # 每行逐步加入，达到预算即停止；预算留给裁剪提示。
            budget = 3820
            for line in lines:
                b = (line + '\n').encode('utf-8')
                if total_bytes + len(b) > budget:
                    break
                keep_sections.append(line)
                total_bytes += len(b)
            keep_sections += ['', '⚠️ 本条消息已按企业微信字节上限安全压缩；完整明细保留在量化交易作战中控台。']
            text = '\n'.join(keep_sections)
        return text

    def generate_and_push(self, app_window=None) -> Dict:
        date_str=datetime.now().strftime('%Y-%m-%d')
        with self._lock:
            if self._already_pushed(date_str): return {'status':'skipped','message':'今日收盘总结已推送'}
            summary=self.build_summary(app_window)
            text=self.format_text(summary)
            # V3.0 推送重构：收盘总结走统一推送总线，标题统一为 📊【收盘总结｜日期】
            from services.wechat_bus import get_wechat_bus
            bus = get_wechat_bus()
            if not (bus._svc and bus._svc.is_configured()):
                return {'status':'pending','message':'企业微信未配置，未标记为已推送'}
            ok = bus._post(f"📊【收盘总结｜{date_str}】", text)
            if not ok:
                return {'status':'failed','message':'企业微信收盘总结发送失败'}
            self._mark_pushed(date_str)
            return {'status':'success','message':f'企业微信已实际返回成功，行情{summary["total"]}只，AI-520信号{len(summary["ai520"])}条'}

_instance=None
def get_daily_close_summary_service():
    global _instance
    if _instance is None: _instance=DailyCloseSummaryService()
    return _instance
