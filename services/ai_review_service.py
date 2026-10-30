# -*- coding: utf-8 -*-
"""AI 盘后复盘：接本地 Ollama，把市场看板数据快照喂给模型生成复盘文字。

Ollama endpoint 默认 http://localhost:11434，OpenAI 兼容 /api/chat。
模型可选：qwen2.5:7b（默认，快）/ qwen3:14b / deepseek-r1:7b（推理慢）。
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OLLAMA_BASE = os.environ.get('OLLAMA_BASE', 'http://localhost:11434')
DEFAULT_MODEL = os.environ.get('AI_REVIEW_MODEL', 'qwen2.5:7b')


def list_models():
    try:
        with urllib.request.urlopen(OLLAMA_BASE + '/api/tags', timeout=5) as r:
            data = json.loads(r.read().decode('utf-8'))
        return [m['name'] for m in data.get('models', [])]
    except Exception:
        return []


def _snapshot_text():
    """从市场看板服务拿当日盘面数字，拼成模型能读的文本。"""
    from services.market_dashboard_service import compute_dashboard
    d = compute_dashboard()
    b, lu = d['breadth'], d['limit_up'] or {}
    themes = '、'.join('%s(%d只)' % (t.get('name', ''), t.get('count', 0))
                       for t in d['themes'][:5])
    inds = '、'.join('%s(%d只)' % (t.get('name', ''), t.get('count', 0))
                     for t in d['industries'][:5])
    ladder = '、'.join('%d板%d只' % (k, v) for k, v in
                      sorted(lu.get('ladder', {}).items(), reverse=True))
    g = '、'.join('%s %+0.2f%%' % (nm, p) for _, nm, p in b['gainers'][:5])
    l = '、'.join('%s %+.2f%%' % (nm, p) for _, nm, p in b['losers'][:5])
    return """【日期】{date}
【广度】上涨{up}家 / 平盘{flat}家 / 下跌{down}家；均涨{avg}% / 中位{med}%
【强势弱势】涨超3% {hi3}家，跌超3% {lo3}家
【涨停】{lu}只涨停，炸板{brk}只，封板率{fb}%，最高{maxl}板
【连板梯队】{ladder}
【趋势】站上MA5 {ma5}%、MA20 {ma20}%、MA60 {ma60}%；60日新高{nh}家 / 新低{nl}家
【成交额】{amt}亿元
【情绪分】{sent}/100
【热门概念】{themes}
【热门行业】{inds}
【涨幅前五】{gainers}
【跌幅前五】{losers}""".format(
        date=d.get('data_date', ''), up=b['n_up'], flat=b['n_flat'], down=b['n_dn'],
        avg=b['avg_pct'], med=b['median_pct'], hi3=b['n_hi3'], lo3=b['n_lo3'],
        lu=lu.get('lu_count', 0), brk=lu.get('broken', 0), fb=lu.get('fengban_rate', '--'),
        maxl=lu.get('max_lbc', 0), ladder=ladder or '无',
        ma5=b['ma5_pct'], ma20=b['ma20_pct'], ma60=b['ma60_pct'],
        nh=b['new_high'], nl=b['new_low'], amt=int(b['total_amount_yi']),
        sent=d['sentiment'], themes=themes or '无', inds=inds or '无',
        gainers=g or '无', losers=l or '无')


SYSTEM_PROMPT = """你是资深A股复盘师。根据下面给出的**真实盘面数据**写一段盘后复盘，要求：
1. 先一句话定调（情绪/强弱），再分 3~5 个短段：市场广度与资金、涨停梯队与主线题材、强弱榜透露的结构、明日关注点与风险。
2. 结论必须基于给出的数字，不要编造数据；数字不够就直说。
3. 用短句，适合桌面看板阅读，总长度 300~500 字。不要客套，不要重复数据原文，要给判断。
4. 结尾加一行「风险提示：不构成投资建议」。"""


def generate_review(model=None, extra=''):
    snap = _snapshot_text()
    body = {
        'model': model or DEFAULT_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': '今日盘面数据：\n' + snap +
             ('\n\n补充要求：' + extra if extra else '')},
        ],
        'stream': False,
        'options': {'temperature': 0.6, 'num_predict': 900},
    }
    req = urllib.request.Request(
        OLLAMA_BASE + '/api/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read().decode('utf-8'))
    return out.get('message', {}).get('content', '').strip(), snap


if __name__ == '__main__':
    import time
    t0 = time.time()
    print('models:', list_models())
    txt, snap = generate_review()
    print('---snapshot---')
    print(snap)
    print('---review (%.1fs)---' % (time.time() - t0))
    print(txt)
