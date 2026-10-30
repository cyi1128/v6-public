# -*- coding: utf-8 -*-
"""V18：把三轴状态闸门接到日K建仓的「建仓触发」上。
冰点期不放行 -> 降为观察（UI 只显示触发+等待，等于不进表）；止盈系数按状态取。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = P + '.bak_before_regime'

sys.stdout.reconfigure(encoding='utf-8')
shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '应为纯 LF'
s = raw.decode('utf-8')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# ---- 1) 模块级状态 + 载入函数 ----
rep("_SHAKE_MIN_OK = 4\n",
    "_SHAKE_MIN_OK = 4\n"
    "\n"
    "# V18 三轴状态闸门（实现在 services/regime_gate.py）\n"
    "#   冰点期 allow_trigger=False -> 建仓触发降为观察（不进表）\n"
    "#   止盈系数按状态取：常温/退潮 1.03，过热抱团 1.02（提前止盈）\n"
    "#   取不到数一律放行，绝不因为数据问题卡死选股。\n"
    "_REGIME = {'state': '\\u26a1 \\u5e38\\u6e29\\u8f6e\\u52a8', 'allow_trigger': True,\n"
    "           'tp_factor': 1.03, 'push': True, 'note': '\\u95f8\\u95e8\\u672a\\u52a0\\u8f7d',\n"
    "           'blocked': 0}\n"
    "\n"
    "\n"
    "def _load_regime(verbose=True):\n"
    "    \"\"\"扫描开始时载入一次状态闸门（模块级缓存，不重复算）\"\"\"\n"
    "    global _REGIME\n"
    "    try:\n"
    "        from services.regime_gate import compute as _rc\n"
    "        d = _rc(force=True)\n"
    "        _REGIME = {'state': d.get('state', ''),\n"
    "                   'allow_trigger': bool(d.get('allow_trigger', True)),\n"
    "                   'tp_factor': float(d.get('tp_factor') or 1.03),\n"
    "                   'push': bool(d.get('push', True)),\n"
    "                   'note': d.get('note', ''), 'blocked': 0}\n"
    "    except Exception as e:\n"
    "        _REGIME = {'state': '\\u26a1 \\u5e38\\u6e29\\u8f6e\\u52a8', 'allow_trigger': True,\n"
    "                   'tp_factor': 1.03, 'push': True, 'note': '\\u95f8\\u95e8\\u4e0d\\u53ef\\u7528\\uff0c\\u5df2\\u653e\\u884c',\n"
    "                   'blocked': 0}\n"
    "        print('[\\u72b6\\u6001\\u95f8\\u95e8] \\u4e0d\\u53ef\\u7528\\uff0c\\u5df2\\u653e\\u884c: %s' % e, flush=True)\n"
    "    if verbose:\n"
    "        print('[\\u72b6\\u6001\\u95f8\\u95e8] %s\\uff5c%s' % (_REGIME['state'], _REGIME['note']), flush=True)\n"
    "    return _REGIME\n",
    'A1 状态常量+载入函数')

# ---- 2) scan_all 开头载入 ----
rep("        for k in _M1_FUNNEL:\n"
    "            _M1_FUNNEL[k] = 0\n"
    "        pat_cnt = {1: 0, 3: 0}\n",
    "        for k in _M1_FUNNEL:\n"
    "            _M1_FUNNEL[k] = 0\n"
    "        _load_regime(verbose=verbose)\n"
    "        pat_cnt = {1: 0, 3: 0}\n",
    'A2 scan_all 载入')

# ---- 3) 止盈系数按状态 ----
rep("                _tp = round(r['trigger_price'] * 1.03, 2)",
    "                _tp = round(r['trigger_price']\n"
    "                            * (_REGIME.get('tp_factor') or 1.03), 2)",
    'A3 止盈系数')

# ---- 4) 冰点不放行：建仓触发降为观察 ----
rep("                _fn['ma20_below'] += 1\n"
    "            _save_or_update(rec)\n",
    "                _fn['ma20_below'] += 1\n"
    "            # V18 三轴状态闸门：冰点期不放行建仓触发\n"
    "            if (not _REGIME.get('allow_trigger', True)\n"
    "                    and rec['signal_level'] == LVL_TRIGGER):\n"
    "                rec['signal_level'] = LVL_WATCH\n"
    "                rec['trigger_type'] = '\\u51b0\\u70b9\\u671f\\u00b7\\u4e0d\\u653e\\u884c'\n"
    "                rec['note'] = ((rec.get('note') or '')\n"
    "                               + '\\n[\\u72b6\\u6001\\u95f8\\u95e8] %s\\uff0c\\u51b0\\u70b9\\u671f\\u4e0d\\u653e\\u884c\\u5efa\\u4ed3\\u89e6\\u53d1'\n"
    "                               % _REGIME.get('state', ''))\n"
    "                _REGIME['blocked'] = _REGIME.get('blocked', 0) + 1\n"
    "            _save_or_update(rec)\n",
    'A4 冰点不放行')

# ---- 5) 扫描汇总打印状态 ----
rep("            print(f'异常: {err}', flush=True)\n",
    "            print(f'异常: {err}', flush=True)\n"
    "            print('[状态闸门] %s\\uff5c%s' % (_REGIME.get('state', ''),\n"
    "                                          _REGIME.get('note', '')), flush=True)\n"
    "            print('  \\u51b0\\u70b9\\u671f\\u964d\\u7ea7\\u4e3a\\u89c2\\u5bdf: %d \\u6761' % _REGIME.get('blocked', 0),\n"
    "                  flush=True)\n",
    'A5 汇总打印')

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  日K建仓已接三轴状态闸门')
print('  备份:', BAK)
