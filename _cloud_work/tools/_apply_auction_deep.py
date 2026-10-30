# -*- coding: utf-8 -*-
"""竞价观察深挖(LLM JSON per-stock) + 竞价观察仓(记录/结算盈亏率)。一次性补丁勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:60].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# ========== 1. 新增竞价仓工具函数（插在 _auction_ds 之前） ==========
rep("""def _auction_ds(tops, heat):
    \"\"\"竞价 DeepSeek：按市场行业板块题材优先级给大白话推荐；失败返回 ''（调用方用规则降级）。\"\"\"""",
    """AUCTION_POOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'auction_pool.json')


def _auction_pool_record(tops):
    \"\"\"竞价观察仓：记录今日竞价批次（入选价=竞价价），只留最近10天。\"\"\"
    try:
        today = _bj_now().strftime('%Y-%m-%d')
        data = {}
        if os.path.exists(AUCTION_POOL_PATH):
            try:
                data = json.load(open(AUCTION_POOL_PATH, encoding='utf-8'))
            except Exception:
                data = {}
        data[today] = [{'code': s['code'], 'name': s['name'], 'price': float(s['price']),
                        'score': round(float(s['score']), 1), 'pct': round(float(s['pct']), 2)}
                       for s in tops]
        days = sorted(data)
        for dd in days[:-10]:
            data.pop(dd, None)
        with open(AUCTION_POOL_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print('[auction_pool] record fail:', e)


def _auction_pool_stats(date_str=None):
    \"\"\"竞价观察仓结算：每只 当日收盘/入选价-1 → 赚钱/亏钱百分比。date_str 空=最近一个非今日批次。返回 HTML 或 ''。\"\"\"
    try:
        if not os.path.exists(AUCTION_POOL_PATH):
            return ''
        data = json.load(open(AUCTION_POOL_PATH, encoding='utf-8'))
        if not data:
            return ''
        if date_str is None:
            today = _bj_now().strftime('%Y-%m-%d')
            batch_dates = [d for d in sorted(data) if d != today]
            if not batch_dates:
                return ''
            date_str = batch_dates[-1]
        batch = data.get(date_str)
        if not batch:
            return ''
        rets = []
        for it in batch:
            sym = ('sh' if it['code'].startswith('6') else 'sz') + it['code']
            arr = get_klines(sym, 30)
            close = None
            if arr:
                d8 = date_str.replace('-', '')
                for r in reversed(arr):
                    if r[0] == d8:
                        close = float(r[2])
                        break
            if not close or not it.get('price'):
                continue
            rets.append((close / it['price'] - 1) * 100)
        if not rets:
            return ''
        win = [r for r in rets if r > 0]
        loss = [r for r in rets if r <= 0]
        avg = sum(rets) / len(rets)
        pct_win = len(win) / len(rets) * 100
        pct_loss = len(loss) / len(rets) * 100
        return (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📊 竞价观察仓结算（{date_str} 选股 → 当日收盘）</div>'
                f'<div style="font-size:13px;color:#e9ecef;background:#1c2830;border-left:4px solid {GOLD};border-radius:8px;padding:8px 10px;">'
                f'共 {len(rets)} 只｜🟢 赚钱 {len(win)} 只（<b style="color:{GREEN}">{pct_win:.0f}%</b>）｜🔴 亏钱 {len(loss)} 只（<b style="color:{RED}">{pct_loss:.0f}%</b>）'
                f'｜平均 <b>{avg:+.1f}%</b>｜最好 {max(rets):+.1f}%｜最差 {min(rets):+.1f}%<br>'
                f'<span style="color:{GREY};font-size:12px;">口径：09:25竞价入选价→当日收盘，未含手续费/滑点</span></div>')
    except Exception as e:
        print('[auction_pool] stats fail:', e)
        return ''


def _auction_ds(tops, heat):
    \"\"\"竞价深挖：每只 TOP 票题材+市场关联+主线多因素深挖（JSON）。返回 (per_map, overall)；失败 ({}, '') 渲染回退规则行。\"\"\"""")

# ========== 2. _auction_ds 函数体替换（JSON per-stock） ==========
rep("""    if not tops:
        return ''
    # 持仓诊断纯文本（只读复用 _qt / three_way，供 DS 终审参考）
    hold_txt = []
    for h in HOLDINGS:
        q = _qt(h['code'])
        if not q:
            continue
        op = (q['open'] / q['prev'] - 1) * 100 if q['prev'] else 0
        vq_ratio = None
        try:
            arr = get_klines(h['code'], 2)
            if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                vq_ratio = (q['vol'] * 100) / float(arr[-2][5]) * 100
        except Exception:
            pass
        act, _ = three_way(op, q.get('lb', 0), vq_ratio)
        hold_txt.append(f"{h['name']} 开幅{op:+.1f}% 量比{q.get('lb',0):.1f} {act}")
    payload = {
        'task': 'auction_top20',
        'stocks': [{'name': s['name'], 'code': s['code'], 'score': s['score'],
                    'pct': s['pct'], 'industry': s['industry']} for s in tops],
        'hot_sectors': sorted(heat.items(), key=lambda kv: -kv[1])[:6],
        'holding_diagnosis': '\\n'.join(hold_txt) or '无持仓',
        'format': (_TRADER_RULES + '\\n请对以下竞价数据进行终审分析（三分法+双重打分已完成）：\\n'
                   '持仓诊断：\\n{holding_diagnosis}\\n'
                   '全市场硬过滤后 TOP20（已按量价×题材综合分排序，见 stocks 字段）：\\n{stocks}\\n'
                   '请严格按以下格式输出：\\n'
                   '【大白话总结】一句话概括今天竞价情绪+重点方向\\n'
                   '【推荐】3-5只（只出终审推荐的，观察的不要写）\\n'
                   '每只格式：名称(代码) | 综合分 | 为什么选它（一句话） | 怎么跟（小高开/平开怎么处理 + 止损） | 仓位建议\\n'
                   '【风险提示】一句话\\n'
                   '【最终结论】今日可重点关注方向（若都不值得做，写「今日无强推」并说明原因）'),
    }
    t = ask_deepseek(payload, purpose='auction')
    return md2html(t) if t else ''""",
    """    if not tops:
        return {}, ''
    # 持仓诊断纯文本（供 LLM 终审参考）
    hold_txt = []
    for h in HOLDINGS:
        q = _qt(h['code'])
        if not q:
            continue
        op = (q['open'] / q['prev'] - 1) * 100 if q['prev'] else 0
        vq_ratio = None
        try:
            arr = get_klines(h['code'], 2)
            if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                vq_ratio = (q['vol'] * 100) / float(arr[-2][5]) * 100
        except Exception:
            pass
        act, _ = three_way(op, q.get('lb', 0), vq_ratio)
        hold_txt.append(f"{h['name']} 开幅{op:+.1f}% 量比{q.get('lb',0):.1f} {act}")
    payload = {
        'task': 'auction_top_deep',
        'stocks': [{'name': s['name'], 'code': s['code'], 'score': round(float(s['score']), 1),
                    'pct': s['pct'], 'industry': s['industry'],
                    'vr': round(float(s.get('_vr') or 0), 1), 'revise': round(float(s.get('_revise') or 0), 1),
                    'rtag': s.get('_rtag', '')} for s in tops],
        'hot_sectors': sorted(heat.items(), key=lambda kv: -kv[1])[:6],
        'holding_diagnosis': '\\n'.join(hold_txt) or '无持仓',
        'format': ('你是A股竞价短线交易员。对以下每只竞价强票做「题材+市场关联」多因素深挖（禁止单条件结论）：\\n'
                   '1. 题材归属：属于什么题材？是不是今日主线？题材里什么地位（龙头/中军/跟风/补涨）？\\n'
                   '2. 板块共振：同题材几只一起动？真合力还是一只独涨？\\n'
                   '3. 资金逻辑：量比/竞价量比/反推修正说明谁在抢？抢筹还是出货？\\n'
                   '4. 位置与预期差：60日位置高低？有没有市场还没消化的东西（业绩预期/错杀修复/政策外溢/龙头扩散）？\\n'
                   '5. 为什么值得看或不值得看，多因素交叉说清依据；数据不足以判断就直说。\\n'
                   '6. 禁止编新闻猜消息、禁止万能句（「回踩分时均线可轻仓试」等）及变体、禁止满仓/必涨/稳了。\\n'
                   '7. 只输出 JSON，不要其他文字：\\n'
                   '{"overall":"竞价情绪一句话+今天能不能追+最强方向","per":[{"name":"股票名称","logic":"题材归属+市场关联深挖：题材是不是主线+地位+板块共振几只+资金逻辑+位置+预期差，为什么值得看/不看，多因素，至少40字，禁止单条件","why":"大白话：一句话戳穿真假+该不该追，至少20字，禁止万能句","op":"别追/看/轻仓试/观望","buy":"具体买点条件","stop":"具体止损条件"}]}，'
                   'per 必须覆盖我给的每只股票。'),
    }
    t = ask_deepseek(payload, purpose='auction')
    if not t:
        return {}, ''
    overall = ''
    per = {}
    try:
        j = json.loads(t[t.find('{'):t.rfind('}') + 1])
        if isinstance(j, dict):
            overall = str(j.get('overall', '') or '')
            for it in (j.get('per') or []):
                nm = str(it.get('name', '')).split('（')[0].split('(')[0].strip()
                if nm:
                    per[nm] = {'logic': str(it.get('logic', '') or ''),
                               'why': str(it.get('why', '') or ''),
                               'op': str(it.get('op', '') or ''),
                               'buy': str(it.get('buy', '') or ''),
                               'stop': str(it.get('stop', '') or '')}
    except Exception:
        pass
    return per, overall""")

# ========== 3. build_auction：ds 调用 + 记录仓 ==========
rep("""    ds_html = _auction_ds(tops, heat)
    ds_block = (f\"\"\"<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;">\"\"\"
                f\"\"\"<div style="font-size:15px;font-weight:800;color:{GOLD};">🤖 DeepSeek 行业板块题材推荐（大白话）</div>{ds_html}</div>\"\"\") if ds_html else ''""",
    """    ds_map, ds_overall = _auction_ds(tops, heat)
    try:
        _auction_pool_record(tops)
    except Exception:
        pass
    ds_block = (f\"\"\"<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;">\"\"\"
                f\"\"\"<div style="font-size:15px;font-weight:800;color:{GOLD};">🤖 竞价深挖总结（大白话）</div><div style="color:#e9ecef;font-size:13px;">{ds_overall}</div></div>\"\"\") if ds_overall else ''""")

# ========== 4. build_auction：每只票深挖渲染 ==========
rep("""        rows += f\"\"\"<div style="background:#1f2635;border-left:3px solid {GOLD if s['score'] >= 70 else TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{GOLD};font-weight:800;float:right;">{s['score']:.0f}分</span></div>
<div style="color:{GREY};font-size:12px;">竞价高开 <b style="color:{_c(s['pct'])}">{s['pct']:+.2f}%</b> ｜ 量比 {s['lb']:.1f} ｜ 竞价量比(归一) {s.get('_vr', 0):.2f} ｜ 题材：{s['industry']}{f' ｜ <b style="color:{RED if s.get('_revise',0)<0 else TEAL}">{s.get('_rtag','')}{s.get('_revise',0):+.0f}</b>' if s.get('_rtag') else ''}</div>
<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 大白话：{s['industry']}竞价高开{s['pct']:+.1f}%、量比{s['lb']:.1f}、{brk_txt}，{_qiang}。</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">👉 建议：开盘30分钟站稳不破均线再动手（1成试探），买入区间 {buy_low}~{buy_high}，破 {buy_low} 的 -3% 止损</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🚫 放弃：跌破分时均线且量能萎缩，或低开超过2%先观望</div></div>\"\"\"""",
    """        _deep = (ds_map or {}).get(s['name'])
        if _deep and _deep.get('logic'):
            _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY}.get(_deep.get('op', ''), GOLD)
            _deep_html = (f\"\"\"<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🧠 题材深挖：{_deep.get('logic','')}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_deep.get('why','')}</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 操作：<b style="color:{_opcol};">{_deep.get('op','')}</b> ｜ 买点：{_deep.get('buy','')} ｜ 止损：{_deep.get('stop','')}</div>\"\"\")
        else:
            _deep_html = ''
        rows += f\"\"\"<div style="background:#1f2635;border-left:3px solid {GOLD if s['score'] >= 70 else TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{GOLD};font-weight:800;float:right;">{s['score']:.0f}分</span></div>
<div style="color:{GREY};font-size:12px;">竞价高开 <b style="color:{_c(s['pct'])}">{s['pct']:+.2f}%</b> ｜ 量比 {s['lb']:.1f} ｜ 竞价量比(归一) {s.get('_vr', 0):.2f} ｜ 题材：{s['industry']}{f' ｜ <b style="color:{RED if s.get('_revise',0)<0 else TEAL}">{s.get('_rtag','')}{s.get('_revise',0):+.0f}</b>' if s.get('_rtag') else ''}</div>
{_deep_html or f\"\"\"<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 大白话：{s['industry']}竞价高开{s['pct']:+.1f}%、量比{s['lb']:.1f}、{brk_txt}，{_qiang}。</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">👉 建议：开盘30分钟站稳不破均线再动手（1成试探），买入区间 {buy_low}~{buy_high}，破 {buy_low} 的 -3% 止损</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🚫 放弃：跌破分时均线且量能萎缩，或低开超过2%先观望</div>\"\"\"}</div>\"\"\"""")

# ========== 5. build_auction：pick 段加昨日战绩 ==========
rep("""    pick = f\"\"\"{top3_txt}<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🎯 今日可关注 TOP{AUCTION_TOP_N}（量价×0.72+题材×0.28−风险+反推修正）</div>
{rows or '<div style="color:' + GREY + ';font-size:13px;">今日无符合硬过滤条件的竞价票（涨幅榜未取得或全被过滤）</div>'}{ds_block}\"\"\"""",
    """    try:
        _pool_prev = _auction_pool_stats()
    except Exception:
        _pool_prev = ''
    pick = f\"\"\"{top3_txt}<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🎯 今日可关注 TOP{AUCTION_TOP_N}（量价×0.72+题材×0.28−风险+反推修正）</div>
{rows or '<div style="color:' + GREY + ';font-size:13px;">今日无符合硬过滤条件的竞价票（涨幅榜未取得或全被过滤）</div>'}{ds_block}{_pool_prev}\"\"\"""")

# ========== 6. build_eod：收盘加今日竞价仓结算 ==========
rep("""    inner = (_overall + health_bar(idx, d, fin, fout) + sec1 + sec2 + sec4 + sec45 + sec5 + sec_ds +
             + build_events('eod') + sec6""",
    """    try:
        _pool_today = _auction_pool_stats(_bj_now().strftime('%Y-%m-%d'))
    except Exception:
        _pool_today = ''
    inner = (_overall + health_bar(idx, d, fin, fout) + sec1 + sec2 + sec4 + sec45 + sec5 + sec_ds +
             + build_events('eod') + sec6 + _pool_today""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
