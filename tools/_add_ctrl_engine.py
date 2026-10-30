# -*- coding: utf-8 -*-
"""把控盘度 / 洗盘出货判断接进 services/band_pattern_engine.py。
关键：新增两列必须同时改 _ALL_COLS、_save_or_update 的列清单+占位符、scan_stock 的 rec，
缺一处就会「库里全是 0 / 空」（上次 shake 五个字段就是这么丢的）。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = P + '.bak_before_ctrl'
sys.stdout.reconfigure(encoding='utf-8')

shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, 'band_pattern_engine.py 应为纯 LF'
s = raw.decode('utf-8')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# ---- 1) 辅助函数 + 阈值 + 计数器（紧跟 _load_bars 之后）----
rep("def _to_weekly(bars):\n",
    "# ==================================================================\n"
    "# V19 控盘度 + 洗盘/出货判断（TechnicalIndicators，strategy/base.py）\n"
    "# ==================================================================\n"
    "# 提醒文案的触发阈值。实测 591 只主板（kline_cache）control_score 分位：\n"
    "#   中位 73.7 / 75分位 91.9 / 90分位 96.4 —— 分数偏挤在高位，区分度一般。\n"
    "#   按下面默认值：>=70 命中 54.0%，>=75 命中 48.7%（偏多，几乎人人达标）。\n"
    "#   想更聚焦可改成 85（32.7%）/ 90（27.1%），改这两行即可。\n"
    "_CTRL_HIGH = 70.0        # 高度控盘线\n"
    "_CTRL_CAND = 75.0        # 高度控盘候选线\n"
    "_CTRL_POS_LOW = 0.4      # 「位置较低」= 近120日位置 < 0.4（与评分里的加权阈值一致）\n"
    "_CTRL_FUNNEL = {'ok': 0, 'ctrl': 0, 'wash': 0, 'dist': 0, 'tip': 0}\n"
    "\n"
    "\n"
    "def _bars_to_df(bars):\n"
    "    \"\"\"把引擎内部的 bars(list[dict]) 转成 DataFrame，供控盘度 / 洗盘判断使用。\n"
    "\n"
    "    bars 来自 kline_cache（含 date/open/high/low/close/volume）；若将来行情源\n"
    "    补上 turnover，这里会自动带上，estimate_control_score 会优先用真实换手率。\n"
    "    长度不足 60 或异常时返回 None。\n"
    "    \"\"\"\n"
    "    try:\n"
    "        if not bars or len(bars) < 60:\n"
    "            return None\n"
    "        import pandas as pd\n"
    "        d = {\n"
    "            'open': [float(b.get('open') or 0) for b in bars],\n"
    "            'high': [float(b.get('high') or 0) for b in bars],\n"
    "            'low': [float(b.get('low') or 0) for b in bars],\n"
    "            'close': [float(b.get('close') or 0) for b in bars],\n"
    "            'volume': [float(b.get('volume') or 0) for b in bars],\n"
    "        }\n"
    "        if bars and 'turnover' in bars[-1]:\n"
    "            d['turnover'] = [float(b.get('turnover') or 0) for b in bars]\n"
    "        return pd.DataFrame(d)\n"
    "    except Exception:\n"
    "        return None\n"
    "\n"
    "\n"
    "def _ctrl_note(ctrl, stage, pos):\n"
    "    \"\"\"按控盘分 / 阶段 / 位置生成提醒文案，多条用 ' ｜ ' 连接；无提示返回 ''。\"\"\"\n"
    "    out = []\n"
    "    try:\n"
    "        if ctrl >= _CTRL_HIGH and stage == 'wash':\n"
    "            out.append('高度控盘 + 疑似洗盘，关注启动')\n"
    "        if stage == 'distribute':\n"
    "            out.append('出货风险警示')\n"
    "        if ctrl >= _CTRL_CAND and pos is not None and pos < _CTRL_POS_LOW:\n"
    "            out.append('高度控盘候选')\n"
    "    except Exception:\n"
    "        return ''\n"
    "    return ' ｜ '.join(out)\n"
    "\n"
    "\n"
    "def _to_weekly(bars):\n",
    'D1 辅助函数+阈值+计数器')

# ---- 2) _ALL_COLS 加两列 ----
rep("    ('take_profit', 'REAL'), ('env_score', 'INTEGER'), ('env_note', 'TEXT'),\n"
    "    ('note', 'TEXT'), ('created_at', 'TEXT'), ('updated_at', 'TEXT'),\n",
    "    ('take_profit', 'REAL'), ('env_score', 'INTEGER'), ('env_note', 'TEXT'),\n"
    "    ('control_score', 'REAL'), ('stage_guess', 'TEXT'),\n"
    "    ('note', 'TEXT'), ('created_at', 'TEXT'), ('updated_at', 'TEXT'),\n",
    'D2 _ALL_COLS 加列')

# ---- 3) _save_or_update 列清单 + 占位符 + 取值 ----
rep("             shake_amp, shake_ok, take_profit, env_score, env_note,\n"
    "             created_at, updated_at)\n"
    "            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\"\"\", (",
    "             shake_amp, shake_ok, take_profit, env_score, env_note,\n"
    "             control_score, stage_guess,\n"
    "             created_at, updated_at)\n"
    "            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\"\"\", (",
    'D3 列清单+占位符 42->44')

rep("            rec.get('take_profit',0), rec.get('env_score',0), rec.get('env_note',''),\n"
    "            rec.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),",
    "            rec.get('take_profit',0), rec.get('env_score',0), rec.get('env_note',''),\n"
    "            rec.get('control_score',0), rec.get('stage_guess','unknown'),\n"
    "            rec.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),",
    'D4 取值加两列')

# ---- 4) scan_stock 计算并落 rec ----
rep("        _below_ma20 = today['close'] < ma20\n"
    "        today_str = today['date'][:10]\n",
    "        _below_ma20 = today['close'] < ma20\n"
    "        today_str = today['date'][:10]\n"
    "        # V19 控盘度 + 洗盘/出货判断（每股算一次，两个模式共用结果）\n"
    "        _ctrl, _stage, _pos = 0.0, 'unknown', None\n"
    "        try:\n"
    "            from strategy.base import TechnicalIndicators as _TI\n"
    "            _df = _bars_to_df(bars)\n"
    "            if _df is not None:\n"
    "                _ti = _TI()\n"
    "                _ctrl = float(_ti.estimate_control_score(_df))\n"
    "                _stage = _ti.judge_wash_or_distribute(_df)\n"
    "                _t120 = _df['close'].tail(120)\n"
    "                _lo, _hi = float(_t120.min()), float(_t120.max())\n"
    "                _pos = (float(_df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)\n"
    "                _CTRL_FUNNEL['ok'] += 1\n"
    "                if _ctrl >= _CTRL_HIGH:\n"
    "                    _CTRL_FUNNEL['ctrl'] += 1\n"
    "                if _stage == 'wash':\n"
    "                    _CTRL_FUNNEL['wash'] += 1\n"
    "                elif _stage == 'distribute':\n"
    "                    _CTRL_FUNNEL['dist'] += 1\n"
    "        except Exception as _e:\n"
    "            print(f'[日K建仓] {code} 控盘度计算异常: {type(_e).__name__}: {_e}', flush=True)\n"
    "        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos)\n"
    "        if _ctrl_tip:\n"
    "            _CTRL_FUNNEL['tip'] += 1\n",
    'D5 scan_stock 计算')

rep("                'take_profit': _tp,\n",
    "                'take_profit': _tp,\n"
    "                'control_score': _ctrl, 'stage_guess': _stage,\n",
    'D6 rec 加两字段')

rep("                _REGIME['blocked'] = _REGIME.get('blocked', 0) + 1\n"
    "            _save_or_update(rec)\n",
    "                _REGIME['blocked'] = _REGIME.get('blocked', 0) + 1\n"
    "            # V19 控盘提醒文案（note 就是 UI 里「触发条件」列的 tooltip）\n"
    "            if _ctrl_tip:\n"
    "                rec['note'] = ((rec.get('note') or '') + '\\n[控盘] ' + _ctrl_tip)\n"
    "            _save_or_update(rec)\n",
    'D7 note 追加提醒')

# ---- 5) 扫描汇总打印 ----
rep("            print('  \\u51b0\\u70b9\\u671f\\u964d\\u7ea7\\u4e3a\\u89c2\\u5bdf: %d \\u6761' % _REGIME.get('blocked', 0),\n"
    "                  flush=True)\n",
    "            print('  \\u51b0\\u70b9\\u671f\\u964d\\u7ea7\\u4e3a\\u89c2\\u5bdf: %d \\u6761' % _REGIME.get('blocked', 0),\n"
    "                  flush=True)\n"
    "            _cf = _CTRL_FUNNEL\n"
    "            print('[\\u63a7\\u76d8\\u5ea6] \\u5df2\\u8ba1\\u7b97 %d \\u53ea \\uff5c >=%.0f\\u5206 %d \\u53ea \\uff5c '\n"
    "                  '\\u6d17\\u76d8 %d \\u53ea \\uff5c \\u51fa\\u8d27 %d \\u53ea \\uff5c \\u89e6\\u53d1\\u63d0\\u9192 %d \\u53ea'\n"
    "                  % (_cf['ok'], _CTRL_HIGH, _cf['ctrl'], _cf['wash'],\n"
    "                     _cf['dist'], _cf['tip']), flush=True)\n",
    'D8 汇总打印')

# ---- 6) 扫描开始时清零计数器 ----
rep("        _load_regime(verbose=verbose)\n",
    "        _load_regime(verbose=verbose)\n"
    "        for _k in _CTRL_FUNNEL:\n"
    "            _CTRL_FUNNEL[_k] = 0\n",
    'D9 计数器清零')

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  band_pattern_engine.py 已接控盘度')
print('  备份:', BAK)
