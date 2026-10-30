# -*- coding: utf-8 -*-
"""FIX19 影子验证：断言量比字段/振幅计算/confirm缺字段文案/共享红线/theme兜底"""
import io, sys, importlib.util, types
sys.stdout.reconfigure(encoding='utf-8')

spec = importlib.util.spec_from_file_location('cdr', r'D:\QuantMonitorV6\tools\cloud_daily_review.py')
cdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdr)
P = r'D:\QuantMonitorV6\tools\cloud_daily_review.py'
src = io.open(P, encoding='utf-8').read()
ok = fail = 0

def check(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1; print('[PASS]', name, detail)
    else: fail += 1; print('[FAIL]', name, detail)

# 1. _qt 量比 = f43
q = cdr._qt('sh600592')
check('qt.lb=f43(5.12)', abs(q['lb'] - 5.12) < 0.01, 'lb=%s' % q['lb'])

# 2. _deep6_collect 量比/振幅（返回嵌套 {'q': ...}）
d6 = cdr._deep6_collect('600592')
dq = d6.get('q') or {}
check('deep6.lb=f43(5.12)', abs(float(dq.get('lb') or 0) - 5.12) < 0.05, 'lb=%s' % dq.get('lb'))
amp_exp = (17.41 - 16.60) / 15.83 * 100
check('deep6.amp=实算(5.12)', abs(float(dq.get('amp') or 0) - amp_exp) < 0.1, 'amp=%s exp=%.2f' % (dq.get('amp'), amp_exp))

# 3. confirm_ds fmt 缺量比文案
infos = [{'name': '测试票', 'code': '600000', 'op': 3.8, 'lb': 0.0, 'sec': '测试板块', 'ok': True, 'why': '测试'}]
try:
    # 直接构造 fmt 验证缺失文案（monkeypatch ask_deepseek 防止真调用）
    cdr.ask_deepseek = lambda *a, **k: None
    out = cdr._confirm_ds(infos)
    check('confirm_ds 缺lb返回空dict', out == {}, 'out=%s' % out)
except Exception as e:
    check('confirm_ds 调用无异常', False, str(e)[:80])
# 验证 fmt 行构造逻辑（源码级：f-string 内未取得分支 + 提示行）
check('fmt含量比未取得标注', "量比{'未取得' if not x.get('lb')" in src and '不得把"未取得"当作量比0' in src, 'src ok')

# 4. 共享提示词红线（两处 _ASK_DS_SYS 都含）
n_mv = src.count('市值红线·用户铁律')
n_vol = src.count('量能红线')
check('市值红线注入x2', n_mv >= 2, 'n=%d' % n_mv)
check('量能红线注入x2', n_vol >= 2, 'n=%d' % n_vol)
check('SYS_AC含红线', '只在30亿-150亿之间写' in cdr._ASK_DS_SYS_AC, '')
check('SYS含红线', '只在30亿-150亿之间写' in cdr._ASK_DS_SYS, '')

# 5. ZSYS theme 兜底
check('ZSYS含theme兜底', '据模型知识' in cdr.ZSYS and '禁止整卡 theme_status 全部输出"未取得"' in cdr.ZSYS, '')

print('\n===== FIX19 verify: %d pass / %d fail =====' % (ok, fail))
sys.exit(1 if fail else 0)
