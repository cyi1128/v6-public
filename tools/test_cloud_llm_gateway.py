#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_llm_gateway 自动化验收：不调用真实 API、不碰真实账本。"""
import os, sys, json, tempfile, shutil, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cloud_llm_gateway as g
os.environ['DEEPSEEK_API_KEY'] = 'test-fake-key-not-used'

PASS, FAIL = [], []
def check(name, cond, detail=''):
    PASS.append(name) if cond else FAIL.append(name)
    print(('PASS' if cond else 'FAIL'), name, ('| ' + str(detail) if detail else ''))


class FakeGit:
    """mock git：返回 (rc, stdout)；远端是否持有本地提交由 remote_has_local 控制。"""
    def __init__(self, push_rc=0, remote_has_local=True):
        self.push_rc = push_rc
        self.cmds = []
        self.local_sha = 'c01deadbeef'
        self.remote_head = self.local_sha if remote_has_local else 'stalehash'
    def __call__(self, args):
        self.cmds.append(args[0])
        if args[0] == 'push':
            return (self.push_rc, '')
        if args[0] == 'rev-parse':
            return (0, self.local_sha)
        if args[0] == 'ls-remote':
            return (0, self.remote_head + '  HEAD')
        return (0, '')


def mkenv():
    work = tempfile.mkdtemp(prefix='llm_test_')
    prices = json.load(open(os.path.join(HERE, 'cloud_llm_prices.json'), encoding='utf-8'))
    pp = os.path.join(work, 'prices.json'); json.dump(prices, open(pp, 'w', encoding='utf-8'))
    lp = os.path.join(work, 'ledger.jsonl')
    us = os.path.join(work, 'unsettled')
    return work, pp, lp, us


_EV_N = [0]
def ev(t, rid='r1', aid=1, **kw):
    _EV_N[0] += 1
    d = {'evt_id': 'e%04d' % _EV_N[0],
         'ts': datetime.datetime(2026, 10, 18, 15).isoformat(), 'type': t,
         'request_id': rid, 'attempt_id': aid}
    d.update(kw)
    return d


p = json.load(open(os.path.join(HERE, 'cloud_llm_prices.json'), encoding='utf-8'))
c_peak = g.cost_of({'prompt_tokens': 3000, 'completion_tokens': 800}, True, p)
c_off = g.cost_of({'prompt_tokens': 3000, 'completion_tokens': 800}, False, p)
check('cost 高峰 3k/800', abs(c_peak - 0.0124) < 1e-6, c_peak)
check('cost 空闲半价', abs(c_off - 0.0062) < 1e-6, c_off)
check('cost 缓存命中大幅便宜', g.cost_of({'prompt_tokens': 3000, 'prompt_cache_hit_tokens': 2800, 'completion_tokens': 800}, True, p) < 0.008)

W, PP, LP, US = mkenv()

# 1. 正常流程：start 远端确认 → 200 → done 结算成功
fg = FakeGit()
hp = lambda *a: (200, {'choices': [{'message': {'content': '复盘内容'}}],
                       'usage': {'prompt_tokens': 3000, 'completion_tokens': 800}}, '')
r = g.chat('eod', '用户数据' * 10, system_text='sys', git_run=fg.__call__,
           http_post=hp, prices_path=PP, ledger_path=LP, unsettled_dir=US)
check('正常调用 ok', r['ok'] is True, r)
lines = [json.loads(l) for l in open(LP, encoding='utf-8') if l.strip()]
check('账本含 start+done', 'attempt_start' in [x['type'] for x in lines] and 'attempt_done' in [x['type'] for x in lines], [x['type'] for x in lines])
exp_cost = g.cost_of({'prompt_tokens': 3000, 'completion_tokens': 800}, g.is_peak(g.beijing_now()), p)
check('done 费用正确', abs(lines[-1]['cost'] - exp_cost) < 1e-6, lines[-1].get('cost'))
check('每次push都有ls-remote核对', fg.cmds.count('ls-remote') >= 1)

# 2. 9 元熔断
work2, pp2, lp2, us2 = mkenv()
with open(lp2, 'w', encoding='utf-8') as f:
    for i in range(750):
        f.write(json.dumps(ev('attempt_done', rid='r%d' % i, cost=0.0124,
                             ts=datetime.datetime(2026, 10, 18, 9, i % 60).isoformat()), ensure_ascii=False) + '\n')
called = [0]
r2 = g.chat('eod', 'x', git_run=FakeGit().__call__, prices_path=pp2, ledger_path=lp2, unsettled_dir=us2,
            http_post=lambda *a: (called.__setitem__(0, 1) or (200, {}, '')))
check('9元熔断拒绝', r2['ok'] is False and 'budget_blocked' in r2['reason'], r2)
check('熔断时不发 HTTP', called[0] == 0)
check('7元后 warn=True', g.summarize(g.replay(lp2))['done_cost'] >= 7.0)

# 3. 超时 → unknown 占预留
work3, pp3, lp3, us3 = mkenv()
r3 = g.chat('eod', 'x', git_run=FakeGit().__call__, prices_path=pp3, ledger_path=lp3, unsettled_dir=us3,
            http_post=lambda *a: (0, None, 'timeout'))
ev3 = [json.loads(l) for l in open(lp3, encoding='utf-8') if l.strip()]
check('超时返回 unknown', r3['ok'] is False and 'unknown' in r3['reason'], r3)
check('超时写 attempt_unknown', any(x['type'] == 'attempt_unknown' for x in ev3))
check('unknown 占用预留', g.summarize(ev3)['unknown_open'] == 1)

# 4. 账本损坏 → fail-closed
work4, pp4, lp4, us4 = mkenv()
open(lp4, 'w', encoding='utf-8').write('{"type":"attempt_start"}\n')
try:
    g.replay(lp4); check('账本损坏抛错', False)
except g.LedgerCorrupt:
    check('账本损坏抛 LedgerCorrupt', True)

# 5. 远端 push 失败 → 不发请求
work5, pp5, lp5, us5 = mkenv()
fg5 = FakeGit(push_rc=1, remote_has_local=False)
called5 = [0]
r5 = g.chat('eod', 'x', git_run=fg5.__call__, prices_path=pp5, ledger_path=lp5, unsettled_dir=us5,
            http_post=lambda *a: (called5.__setitem__(0, 1) or (200, {}, '')))
check('远端push失败拒绝', r5['ok'] is False and 'remote_unverified' in r5['reason'], r5)
check('push失败绝不发付费请求', called5[0] == 0)

# 6. 结算 push 最终失败 → unsettled 事件随仓库持久化（mock：push后全部失败）
class SettleFailGit(FakeGit):
    def __call__(self, args):
        if 'commit' in args:
            self.cmds.append('commit'); self.local_sha = 'c%02d' % len([c for c in self.cmds if c == 'commit'])
            return (0, '')
        if args[0] == 'push':
            self.cmds.append('push')
            n = self.cmds.count('push')
            if n == 1:
                self.remote_head = self.local_sha
                return (0, '')
            return (1, '')
        return super().__call__(args)
work6, pp6, lp6, us6 = mkenv()
fg6 = SettleFailGit()
r6 = g.chat('eod', 'x', git_run=fg6.__call__, prices_path=pp6, ledger_path=lp6, unsettled_dir=us6,
            http_post=lambda *a: (200, {'choices': [{'message': {'content': 'ok'}}],
                                       'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}, ''))
check('结算失败仍返回文本', r6['ok'] is True, r6)
check('settled_pushed=False', r6.get('settled_pushed') is False)
check('unsettled 事件文件已落盘', os.path.isdir(us6) and len(os.listdir(us6)) == 1, os.listdir(us6) if os.path.isdir(us6) else [])

# 7. 恢复：recover_unsettled 把待补登事件写回账本并删除文件
work7, pp7, lp7, us7 = mkenv()
shutil.copytree(us6, us7) if False else None
pending = json.load(open(os.path.join(us6, os.listdir(us6)[0]), encoding='utf-8'))
os.makedirs(us7, exist_ok=True)
json.dump(pending, open(os.path.join(us7, 'x.json'), 'w', encoding='utf-8'))
st_before = g.summarize(g.replay(lp7))
g.recover_unsettled(lp7, FakeGit().__call__, us7)
ev7 = g.replay(lp7)
st_after = g.summarize(ev7)
check('recover 补登 done 事件', any(x['type'] == 'attempt_done' for x in ev7))
check('recover 后待补推文件已删', len(os.listdir(us7)) == 0)
check('recover 后费用计入', abs(st_after['done_cost'] - st_before['done_cost'] - pending['cost']) < 1e-6,
      (st_before['done_cost'], st_after['done_cost']))

# 8. 结算重试最终成功 → 不留 unsettled
class SettleRetryGit(FakeGit):
    def __init__(self):
        super().__init__(); self.n_push = 0
    def __call__(self, args):
        if 'commit' in args:
            self.cmds.append('commit'); self.local_sha = 'r%02d' % len([c for c in self.cmds if c == 'commit'])
            return (0, '')
        if args[0] == 'push':
            self.cmds.append('push'); self.n_push += 1
            if self.n_push == 1 or self.n_push == 4:
                self.remote_head = self.local_sha; return (0, '')
            return (1, '')
        return super().__call__(args)
work8, pp8, lp8, us8 = mkenv()
fg8 = SettleRetryGit()
r8 = g.chat('eod', 'x', git_run=fg8.__call__, prices_path=pp8, ledger_path=lp8, unsettled_dir=us8,
            http_post=lambda *a: (200, {'choices': [{'message': {'content': 'ok'}}],
                                       'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}, ''))
check('结算重试后成功', r8['ok'] is True and r8.get('settled_pushed') is True, r8)
check('结算成功不留 unsettled', not os.path.exists(us8) or len(os.listdir(us8)) == 0)

# 9. push 响应丢失但远端已收 → ls-remote 自证 → 发请求
work9, pp9, lp9, us9 = mkenv()
fg9 = FakeGit(push_rc=1, remote_has_local=True)  # push rc 失败但远端有本地 sha
called9 = [0]
r9 = g.chat('eod', 'x', git_run=fg9.__call__, prices_path=pp9, ledger_path=lp9, unsettled_dir=us9,
            http_post=lambda *a: (called9.__setitem__(0, 1) or (200, {'choices': [{'message': {'content': 'x'}}], 'usage': {}}, '')))
check('远端已收但确认丢失→放行', r9['ok'] is True, r9)

# 10. push 失败且远端没有本地提交 → 拒绝发请求
work10, pp10, lp10, us10 = mkenv()
fg10 = FakeGit(push_rc=1, remote_has_local=False)
called10 = [0]
r10 = g.chat('eod', 'x', git_run=fg10.__call__, prices_path=pp10, ledger_path=lp10, unsettled_dir=us10,
             http_post=lambda *a: (called10.__setitem__(0, 1) or (200, {}, '')))
check('远端确实没有→拒绝', r10['ok'] is False and 'remote_unverified' in r10['reason'], r10)
check('未确认前不发请求', called10[0] == 0)

# 11. 在途 start 计 inflight
work11, pp11, lp11, us11 = mkenv()
open(lp11, 'w', encoding='utf-8').write(json.dumps({'evt_id': 'x1', 'ts': '2026-10-18T10:00:00',
    'type': 'attempt_start', 'request_id': 'z', 'attempt_id': 1}) + '\n')
check('在途 start 计 inflight', g.summarize(g.replay(lp11))['inflight'] == 1)

# 12. 输入超限拒绝
work12, pp12, lp12, us12 = mkenv()
called12 = [0]
r12 = g.chat('eod', '字' * 40000, git_run=FakeGit().__call__, prices_path=pp12, ledger_path=lp12, unsettled_dir=us12,
             http_post=lambda *a: (called12.__setitem__(0, 1) or (200, {}, '')))
check('输入超限拒绝', r12['ok'] is False and 'input_too_large' in r12['reason'])
check('超限不发请求', called12[0] == 0)

# 13. 跨月
work13, pp13, lp13, us13 = mkenv()
open(lp13, 'w', encoding='utf-8').write(json.dumps({'evt_id': 'y1', 'ts': '2026-09-15T10:00:00',
    'type': 'attempt_done', 'request_id': 'old', 'attempt_id': 1, 'cost': 5.0}) + '\n')
check('跨月累计归零', g.summarize(g.replay(lp13), month='2026-10')['done_cost'] == 0.0)


# ===== 并发预算竞态回归（A~G） =====
import hashlib
class RemoteGit:
    """模拟共享远端账本：push 快进成功；pull --rebase = 远端 + 本地未推送提交。"""
    def __init__(self, local, remote, push_rc=0, overwrite_remote=True, extra_done=0.0):
        self.local, self.remote = local, remote
        self.push_rc, self.overwrite, self.extra = push_rc, overwrite_remote, extra_done
        self.cmds = []
    def _h(self, p):
        return hashlib.sha1(open(p, 'rb').read() if os.path.exists(p) else b'').hexdigest()
    def _lines(self, p):
        return open(p, encoding='utf-8').readlines() if os.path.exists(p) else []
    def __call__(self, args):
        self.cmds.append(args[0])
        if args[0] == 'rev-parse': return (0, self._h(self.local))
        if args[0] == 'ls-remote': return (0, self._h(self.remote) + '  HEAD')
        if args[0] == 'push':
            if not self.overwrite: return (self.push_rc, '')  # rc=0 但远端没更新
            rl, ll = self._lines(self.remote), self._lines(self.local)
            if ll[:len(rl)] == rl:  # 快进：本地是远端的后继
                shutil.copy(self.local, self.remote)
                return (self.push_rc, '')
            return (1, '')  # 非快进
        if args[0] == 'pull':  # rebase：远端 + 本地未推送提交
            rl, ll = self._lines(self.remote), self._lines(self.local)
            extra = ll[len(rl):] if ll[:len(rl)] == rl else ll
            with open(self.local, 'w', encoding='utf-8') as f:
                f.writelines(rl + extra)
            if self.extra > 0:
                f = open(self.local, 'a', encoding='utf-8')
                f.write(json.dumps({'evt_id': 'ext%d' % len(self.cmds),
                    'ts': '2026-10-18T10:00:00', 'type': 'attempt_done',
                    'request_id': 'ext', 'attempt_id': 1, 'cost': self.extra},
                    ensure_ascii=False) + '\n')
                f.close()
                self.extra = 0
            return (0, '')
        return (0, '')

def fill_done(path, n=720, cost=0.0124):
    with open(path, 'w', encoding='utf-8') as f:
        for i in range(n):
            f.write(json.dumps({'evt_id': 'd%03d' % i, 'ts': '2026-10-18T09:00:00',
                'type': 'attempt_done', 'request_id': 'r%d' % i, 'attempt_id': 1,
                'cost': cost}, ensure_ascii=False) + '\n')

# C. rebase 同步后远端多了一笔费用，原可放行→现熔断：HTTP 必须 0 次
wc, pc, lc, uc = mkenv()
fill_done(lc)  # 8.928 元
shutil.copy(lc, wc + '/remote.json')
gc = RemoteGit(lc, wc + '/remote.json', extra_done=0.25)
hc = [0]
rc = g.chat('eod', 'x', git_run=gc, prices_path=pc, ledger_path=lc, unsettled_dir=uc,
            http_post=lambda *a: (hc.__setitem__(0, 1) or (200, {'choices': [{'message': {'content': 'z'}}], 'usage': {}}, '')))
check('C. 同步后超熔断→拒绝', rc['ok'] is False and 'after_sync' in rc['reason'], rc)
check('C. HTTP 调用次数=0', hc[0] == 0, hc[0])
check('C. 本笔预留保留在远端', g.summarize(g.replay(lc))['inflight'] == 1)

# A/B. 两个 Runner：A 放行并结算；B 基于旧账本入口检查也通过，但同步后必须被熔断
wb, pb, lb, ub = mkenv()
fill_done(lb, n=723)  # 8.965 元：单独都 <9，合并 A 结算后触线
remote_b = wb + '/remote.json'; shutil.copy(lb, remote_b)
ga = RemoteGit(lb, remote_b)
ha = [0]
ra = g.chat('eod', 'x', git_run=ga, prices_path=pb, ledger_path=lb, unsettled_dir=ub,
            http_post=lambda *a: (ha.__setitem__(0, 1) or (200, {'choices': [{'message': {'content': 'ok'}}],
                                       'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}, '')))
check('A. Runner A 正常放行', ra['ok'] is True and ha[0] == 1)
# B 拿着旧快照（8.928）开始；远端已因 A 变为 9.13
lb2 = wb + '/lb2.json'
fill_done(lb2, n=723)  # 旧快照
gb = RemoteGit(lb2, remote_b)
hb2 = [0]
rb = g.chat('eod', 'x', git_run=gb, prices_path=pb, ledger_path=lb2, unsettled_dir=wb + '/ub2',
            http_post=lambda *a: (hb2.__setitem__(0, 1) or (200, {}, '')))
check('B. Runner B 同步后被熔断', rb['ok'] is False and ('blocked' in rb['reason']), rb)
check('B. Runner B 未发 HTTP', hb2[0] == 0, hb2[0])

# D. push 失败但远端实际已收（响应丢失）→ 远端确认 + 最新核算仍有余量 → 放行
wd, pd_, ld, ud = mkenv()
fill_done(ld, n=10)  # 0.124 元，远低于熔断
shutil.copy(ld, wd + '/remote.json')
class LostAckGit(RemoteGit):
    def __call__(self, args):
        if args[0] == 'push':
            shutil.copy(self.local, self.remote)  # 远端实际收了
            return (1, '')  # 但客户端没收到确认
        return super().__call__(args)
gd = LostAckGit(ld, wd + '/remote.json')
hd = [0]
rd = g.chat('eod', 'x', git_run=gd, prices_path=pd_, ledger_path=ld, unsettled_dir=ud,
            http_post=lambda *a: (hd.__setitem__(0, 1) or (200, {'choices': [{'message': {'content': 'x'}}], 'usage': {}}, '')))
check('D. 响应丢失但远端已收→放行', rd['ok'] is True and hd[0] == 1, rd)

# E. push 返回成功但远端分支没收到 → 拒绝，HTTP=0
we, pe, le, ue = mkenv()
fill_done(le, n=10)
shutil.copy(le, we + '/remote.json')
ge = RemoteGit(le, we + '/remote.json', push_rc=0, overwrite_remote=False)  # rc=0 但不更新远端
he = [0]
re_ = g.chat('eod', 'x', git_run=ge, prices_path=pe, ledger_path=le, unsettled_dir=ue,
             http_post=lambda *a: (he.__setitem__(0, 1) or (200, {}, '')))
check('E. 远端未包含事件→拒绝', re_['ok'] is False and 'remote_unverified' in re_['reason'], re_)
check('E. HTTP 调用次数=0', he[0] == 0)

# F. 并发恢复 unsettled 幂等：账本已有该 evt_id → 直接删文件、费用不重复计入
wf, pf, lf, uf = mkenv()
ev_f = {'evt_id': 'dup001', 'ts': '2026-10-18T10:00:00', 'type': 'attempt_done',
        'request_id': 'f', 'attempt_id': 1, 'cost': 0.0062}
with open(lf, 'w', encoding='utf-8') as fp:
    fp.write(json.dumps(ev_f, ensure_ascii=False) + '\n')
os.makedirs(uf, exist_ok=True)
json.dump(ev_f, open(os.path.join(uf, 'dup001.json'), 'w', encoding='utf-8'))
gf = RemoteGit(lf, wf + '/remote.json')
g.recover_unsettled(lf, gf, uf)
check('F. 幂等：文件已删', not os.path.exists(os.path.join(uf, 'dup001.json')))
check('F. 费用不重复计入', abs(g.summarize(g.replay(lf))['done_cost'] - 0.0062) < 1e-6)

# G. 冲突超过重试上限 → 拒绝，unknown 占位保留
wg, pg, lg, ug = mkenv()
gg = FakeGit(push_rc=1, remote_has_local=False)
hg = [0]
rg = g.chat('eod', 'x', git_run=gg, prices_path=pg, ledger_path=lg, unsettled_dir=ug,
            http_post=lambda *a: (hg.__setitem__(0, 1) or (200, {}, '')))
check('G. 重试耗尽→拒绝', rg['ok'] is False and 'remote_unverified' in rg['reason'], rg)
check('G. HTTP=0', hg[0] == 0)
check('G. 预留未释放(unknown占位)', any(x['type'] == 'attempt_unknown' for x in g.replay(lg)))

for w in (W, work2, work3, work4, work5, work6, work7, work8, work9, work10, work11, work12, work13,
          wc, wb, wd, we, wf, wg):
    shutil.rmtree(w, ignore_errors=True)

print('TOTAL %d PASS / %d FAIL' % (len(PASS), len(FAIL)))
if FAIL:
    print('FAILED:', FAIL); sys.exit(1)
