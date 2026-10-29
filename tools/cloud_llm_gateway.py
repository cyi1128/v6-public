#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 DeepSeek 付费网关 + 预算账本（云端流水线唯一付费入口）。

铁律：
1. 远端账本里没有确认存在的 attempt_start 预留事件，绝不发起付费请求；
2. 超时/中断/解析失败 = attempt_unknown，预留保留，绝不自动记 0；
3. 每次真实 HTTP 尝试（attempt）独立记账，重试不合并；
4. 账本损坏 / 价格配置无效 / 远端推送失败 = fail-closed，拒绝付费调用。
"""
import os
import json
import uuid
import datetime
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(HERE, 'cloud_llm_prices.json')
LEDGER_PATH = os.path.join(HERE, 'cloud_llm_ledger.jsonl')
UNSETTLED_DIR = os.path.join(HERE, 'unsettled')

TERMINAL_TYPES = ('attempt_done', 'attempt_failed_zero', 'attempt_unknown',
                  'attempt_released', 'attempt_reconciled')


class GatewayError(Exception):
    pass


class BudgetBlocked(GatewayError):
    pass


class LedgerCorrupt(GatewayError):
    pass


class LedgerUnavailable(GatewayError):
    pass


def beijing_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=8)


def is_peak(dt):
    """高峰=工作日 9:00-12:00、14:00-18:00（北京时间，近似不含节假日）。"""
    if dt.weekday() >= 5:
        return False
    return (9 <= dt.hour < 12) or (14 <= dt.hour < 18)


def load_prices(path=PRICES_PATH):
    try:
        p = json.load(open(path, encoding='utf-8'))
        assert p['model'] and p['per_m_tokens']['peak'] and p['per_m_tokens']['offpeak']
        assert p['reservation_per_attempt'] > 0 and p['block_yuan'] > p['warn_yuan']
        return p
    except Exception as e:
        raise LedgerUnavailable(f'价格配置无效: {e}')


def replay(ledger_path=LEDGER_PATH):
    """重放账本。任何一行无法解析即视为账本损坏（绝不跳行）。"""
    events = []
    if not os.path.exists(ledger_path):
        return events
    seen = set()
    for ln, line in enumerate(open(ledger_path, encoding='utf-8'), 1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            raise LedgerCorrupt(f'账本第{ln}行无法解析')
        eid = ev.get('evt_id')
        if not eid:
            raise LedgerCorrupt(f'账本第{ln}行缺 evt_id')
        if eid in seen:
            continue
        seen.add(eid)
        events.append(ev)
    return events


def summarize(events, month=None):
    """重放得到：本月已结算费用、在途预留数、未决 unknown 预留数。"""
    month = month or beijing_now().strftime('%Y-%m')
    done_cost = 0.0
    terminal = {}
    starts = set()
    unknown_open = set()
    for ev in events:
        t = ev.get('type')
        key = (ev.get('request_id'), ev.get('attempt_id'))
        if t == 'attempt_start':
            starts.add(key)
        elif t == 'attempt_done':
            terminal[key] = t
            if (ev.get('ts') or '')[:7] == month:
                done_cost += float(ev.get('cost') or 0.0)
        elif t in TERMINAL_TYPES:
            terminal[key] = t
        if t == 'attempt_unknown':
            unknown_open.add(key)
        elif t in ('attempt_released', 'attempt_reconciled'):
            unknown_open.discard(key)
    inflight = sum(1 for k in starts if k not in terminal)
    return {'done_cost': done_cost, 'inflight': inflight,
            'unknown_open': len(unknown_open), 'month': month}


def _git(args, cwd=HERE):
    """执行 git，返回 (rc, stdout)。"""
    import subprocess
    r = subprocess.run(['git'] + args, cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True)
    return r.returncode, (r.stdout or '')


def _remote_confirmed(g):
    """push 后核对：本地 HEAD 是否真的在远端。返回 (ok, reason)。"""
    rc, out = g(['rev-parse', 'HEAD'])
    if rc != 0:
        return False, 'no_local_sha'
    local = (out.strip().split() or [''])[0]
    if not local:
        return False, 'empty_local_sha'
    rc2, out2 = g(['ls-remote', 'origin', 'HEAD'])
    if rc2 == 0 and local in out2:
        return True, 'confirmed'
    return False, f'remote_mismatch local={local[:8]}'


def commit_push_ledger(paths, msg='llm ledger', git_run=None):
    """账本/待补推文件提交并推到远端，且用 ls-remote 核对远端真的收到。

    paths: 单个路径或路径列表。返回 (ok, reason)。
    """
    g = git_run or _git
    if isinstance(paths, str):
        paths = [paths]
    if g(['add'] + paths)[0] != 0:
        return False, 'git_add_failed'
    g(['-c', 'user.name=bot', '-c', 'user.email=bot@local',
       'commit', '-m', msg])  # 无变更时 rc=1，可接受
    rc, _ = g(['push', 'origin', 'HEAD'])
    if rc == 0:
        return _remote_confirmed(g)
    # push 未确认成功：远端可能已收（响应丢失），用 ls-remote 自证
    ok, why = _remote_confirmed(g)
    if ok:
        return True, 'pushed_lost_ack'
    return False, f'push_rc={rc}:{why}'


def recover_unsettled(ledger_path, git_run=None, unsettled_dir=UNSETTLED_DIR):
    """恢复：把上一轮结算 push 失败时持久化到仓库 unsettled/ 的事件补登。

    只有确认远端账本已有该事件后才删除本地待补推记录；补登成功才算数。
    """
    if not os.path.isdir(unsettled_dir):
        return 0
    have = set(e.get('evt_id') for e in replay(ledger_path))
    n = 0
    for fn in sorted(os.listdir(unsettled_dir)):
        if not fn.endswith('.json'):
            continue
        fp = os.path.join(unsettled_dir, fn)
        try:
            ev = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue  # 坏文件：不跳过账本、不丢事件，留待人工处理
        if ev.get('evt_id') in have:
            os.remove(fp)
            continue
        _append(ev, ledger_path)
        ok, _ = commit_push_ledger([ledger_path], 'llm recover settle', git_run)
        if not ok:
            continue  # 远端不通：保留文件，下次再试
        os.remove(fp)
        commit_push_ledger([ledger_path, unsettled_dir], 'llm clean unsettled', git_run)
        n += 1
    return n


def _default_http_post(url, headers, body, timeout=40):
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
        return 200, r, ''
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode())
        except Exception:
            data = None
        return e.code, data, f'http_{e.code}'
    except Exception as e:
        return 0, None, str(e)[:200]


def _append(ev, ledger_path):
    with open(ledger_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')


def cost_of(usage, peak, prices):
    p = prices['per_m_tokens']['peak' if peak else 'offpeak']
    hit = int(usage.get('prompt_cache_hit_tokens') or 0)
    miss = int(usage.get('prompt_cache_miss_tokens') or 0)
    if not miss:
        miss = int(usage.get('prompt_tokens') or 0) - hit
    out = int(usage.get('completion_tokens') or 0)
    return hit / 1e6 * p['in_hit'] + miss / 1e6 * p['in_miss'] + out / 1e6 * p['out']


def _gate(ledger_path, prices, month):
    """重放最新账本并算闸门。账本损坏时上抛 LedgerCorrupt（fail-closed）。"""
    events = replay(ledger_path)
    st = summarize(events, month)
    each = float(prices['reservation_per_attempt'])
    need = st['done_cost'] + (st['inflight'] + st['unknown_open'] + 1) * each
    return st, need


def chat(purpose, user_text, system_text='', max_tokens=None,
         http_post=None, git_run=None, clock=None,
         prices_path=PRICES_PATH, ledger_path=LEDGER_PATH,
         unsettled_dir=UNSETTLED_DIR):
    """统一付费调用入口。失败一律返回 {'ok':False,'reason':...}，绝不抛给业务。"""
    prices = load_prices(prices_path)
    # 先恢复上一轮结算 push 失败的待补推事件（远端持久化的 unsettled/）
    try:
        recover_unsettled(ledger_path, git_run, unsettled_dir)
    except Exception:
        pass
    now = clock() if clock else beijing_now()
    month = now.strftime('%Y-%m')
    each = float(prices['reservation_per_attempt'])
    warn = float(prices['warn_yuan'])
    block = float(prices['block_yuan'])
    try:
        st, need = _gate(ledger_path, prices, month)
    except LedgerCorrupt as e:
        return {'ok': False, 'reason': f'ledger_corrupt:{e}', 'done_cost': -1}
    warn_now = st['done_cost'] >= warn

    if need >= block:
        return {'ok': False, 'reason': f'budget_blocked_need_{need:.3f}',
                'done_cost': st['done_cost'], 'warn': warn_now}

    est_in = (len(system_text or '') + len(user_text or '')) // 4
    if est_in > int(prices['max_input_tokens_estimate']):
        return {'ok': False, 'reason': f'input_too_large_{est_in}',
                'done_cost': st['done_cost'], 'warn': warn_now}

    http_post = http_post or _default_http_post
    rid = uuid.uuid4().hex[:16]
    peak = is_peak(now)
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return {'ok': False, 'reason': 'no_api_key', 'done_cost': st['done_cost']}

    # 1) 先写 attempt_start，确认远端分支真的包含它；
    #    每次 push/pull 与远端状态同步后都必须重放最新账本、重算闸门，
    #    绝不沿用入口处的旧闸门结果（并发 Runner 安全的核心）。
    base_ev = {'ts': now.isoformat(), 'request_id': rid, 'model': prices['model'],
               'purpose': purpose, 'peak': peak, 'prices_version': prices.get('version')}
    pushed = False
    last_reason = ''
    for attempt in range(1, 4):
        ev = dict(base_ev)
        ev['evt_id'] = uuid.uuid4().hex[:16]
        ev['type'] = 'attempt_start'
        ev['attempt_id'] = attempt
        ev['reserved'] = each
        _append(ev, ledger_path)
        ok, last_reason = commit_push_ledger([ledger_path], f'llm start {purpose} a{attempt}', git_run)
        # 无论 push 成功/失败，都先与远端同步，再基于最新账本重算闸门
        if git_run:
            git_run(['pull', '--rebase', 'origin', 'HEAD'])
        try:
            st2 = summarize(replay(ledger_path), month)
        except LedgerCorrupt as e:
            return {'ok': False, 'reason': f'ledger_corrupt_after_sync:{e}',
                    'done_cost': -1, 'reservation_kept': True}
        # 本笔 start 已在 inflight 中，不再额外 +1（避免双计自身预留）
        need2 = st2['done_cost'] + (st2['inflight'] + st2['unknown_open']) * each
        if need2 >= block:
            # 并发同步后触发熔断：本笔预留保留在远端，保守不发请求、不释放
            return {'ok': False, 'reason': f'budget_blocked_after_sync_{need2:.3f}',
                    'done_cost': st2['done_cost'], 'warn': st2['done_cost'] >= warn,
                    'reservation_kept': True}
        if ok:
            pushed = True
            break
    if not pushed:
        # 请求未发出：保留一条 unknown 占位，下次运行人工对账
        ev = {'evt_id': uuid.uuid4().hex[:16], 'type': 'attempt_unknown',
              'reason': 'remote_push_failed_no_request_sent', **base_ev, 'attempt_id': 1}
        _append(ev, ledger_path)
        commit_push_ledger([ledger_path], 'llm unknown push-fail', git_run)
        return {'ok': False, 'reason': f'remote_unverified:{last_reason}',
                'done_cost': st['done_cost'], 'warn': warn_now}

    # 2) 远端确认后才发付费请求
    body = json.dumps({
        'model': prices['model'],
        'messages': ([{'role': 'system', 'content': system_text}] if system_text else []) +
                    [{'role': 'user', 'content': user_text}],
        'temperature': 0.6,
        'max_tokens': int(max_tokens or prices['max_output_tokens']),
        'thinking': {'type': 'disabled'},
    }).encode()
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    status, data, err = http_post(prices['base_url'] + '/chat/completions', headers, body)

    if 200 <= status < 300 and data:
        usage = data.get('usage') or {}
        cost = cost_of(usage, peak, prices)
        done_ev = {'evt_id': uuid.uuid4().hex[:16], 'type': 'attempt_done',
                   'prompt_tokens': usage.get('prompt_tokens'),
                   'completion_tokens': usage.get('completion_tokens'),
                   'cost': round(cost, 6), **base_ev, 'attempt_id': attempt,
                   'reservation_used': each}
        _append(done_ev, ledger_path)
        ok2 = False
        for _try in range(3):  # 结算也重试：push 失败/非快进
            ok2, _ = commit_push_ledger([ledger_path], f'llm done {purpose}', git_run)
            if ok2:
                break
            if git_run:
                git_run(['pull', '--rebase', 'origin', 'HEAD'])
        if not ok2:
            # 计费已发生但远端账本没落结算：把事件文件持久化到仓库 unsettled/
            # （随 git push 进入远端，Runner 销毁后下次运行 recover_unsettled 补登）
            try:
                os.makedirs(unsettled_dir, exist_ok=True)
                with open(os.path.join(unsettled_dir, rid + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(done_ev, f, ensure_ascii=False)
                commit_push_ledger([ledger_path, unsettled_dir],
                                   'llm persist unsettled', git_run)
            except Exception:
                pass
        text = (data.get('choices') or [{}])[0].get('message', {}).get('content', '')
        return {'ok': True, 'text': text, 'cost': cost, 'done_cost': st['done_cost'] + cost,
                'warn': (st['done_cost'] + cost) >= warn, 'settled_pushed': ok2}

    if 400 <= status < 500:
        ev = {'evt_id': uuid.uuid4().hex[:16], 'type': 'attempt_failed_zero',
              'http_status': status, 'err': err, **base_ev, 'attempt_id': attempt}
        _append(ev, ledger_path)
        commit_push_ledger([ledger_path], f'llm fail0 {purpose}', git_run)
        return {'ok': False, 'reason': f'http_{status}', 'done_cost': st['done_cost'],
                'warn': warn_now}

    # 超时/中断/5xx/解析失败：未知费用，预留保留
    ev = {'evt_id': uuid.uuid4().hex[:16], 'type': 'attempt_unknown',
          'err': err or f'status_{status}', **base_ev, 'attempt_id': attempt}
    _append(ev, ledger_path)
    commit_push_ledger([ledger_path], f'llm unknown {purpose}', git_run)
    return {'ok': False, 'reason': f'unknown:{err or status}', 'done_cost': st['done_cost'],
            'warn': warn_now, 'reserved_open': True}
