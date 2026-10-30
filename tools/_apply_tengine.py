# -*- coding: utf-8 -*-
"""一次性补丁：机构级分时做T引擎接入 atr_t_widget.py + 修 atr 未绑定的静默 bug。

【勿重跑】改完即失效（锚点会命中 0 次并 assert 报错，属预期）。
补丁内容：
  1) 模块级开关 _T_ENGINE_AUTHORITATIVE（True=引擎结论覆盖原信号；False=只加字段不改原判定）
  2) 在 _fetch_and_calc 的「旧判定之后」接入引擎（不放在 r['cost'] 之后 —— 那里会被 L909 覆盖）
  3) L787 / L804 两处 send_t_timing(atr=atr) → atr=r.get('atr', 0)（原来必然 NameError 被静默吞掉）
"""
import os
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
BAK = P + '.bak_before_tengine'

src = open(P, newline='', encoding='utf-8').read()
if not os.path.exists(BAK):
    open(BAK, 'w', newline='', encoding='utf-8').write(src)
    print('已备份 ->', BAK)
else:
    print('备份已存在，跳过备份（保留最早一份）')
print('补丁前：总行数 %d，CRLF %d，裸LF %d' % (
    src.count('\r\n') + 1, src.count('\r\n'), src.count('\n') - src.count('\r\n')))

# ---------- 1) 模块级开关 ----------
a1 = "               '信号灯', '操作建议', CTRL_COL_TITLE]\r\n"
assert src.count(a1) == 1, '锚点1 命中 %d 次' % src.count(a1)
ins1 = a1 + (
    "\r\n"
    "# 机构级分时做T引擎（2026-10-12 接入，实现在 strategy/intraday_t_engine.py）：\r\n"
    "# True  = 引擎结论覆盖「信号灯 / 操作建议 / 买卖点」（成本偏离+VWAP+量价+时段+反T优先）\r\n"
    "# False = 只写 t_plan / t_score / cost_dev_pct 等字段，保留原判定（一键回退，不改代码）\r\n"
    "_T_ENGINE_AUTHORITATIVE = True\r\n"
)
src = src.replace(a1, ins1, 1)

# ---------- 2) 引擎接入块（放在旧判定之后） ----------
a2 = "            r = self._apply_risk_and_signal(r, in_open_window)\r\n"
assert src.count(a2) == 1, '锚点2 命中 %d 次' % src.count(a2)
BLOCK = (
    "            # ===== 机构级分时做T引擎接入（务必在 _apply_risk_and_signal 之后：否则信号会被旧判定覆盖）=====\r\n"
    "            try:\r\n"
    "                from strategy.intraday_t_engine import (\r\n"
    "                    THolding, TQuote, get_engine, apply_plan_to_row,\r\n"
    "                )\r\n"
    "                _t_plan = get_engine().evaluate(\r\n"
    "                    holding=THolding(\r\n"
    "                        code=code, name=name,\r\n"
    "                        cost=item.get('cost'), qty=item.get('qty'),\r\n"
    "                        buy_time=item.get('buy_time'),\r\n"
    "                    ),\r\n"
    "                    quote=TQuote(\r\n"
    "                        price=price, prev_close=prev_close,\r\n"
    "                        high=day_high, low=day_low,\r\n"
    "                        volume_lots=q.get('volume', 0), amount=q.get('amount', 0),\r\n"
    "                        vol_ratio=q.get('vol_ratio', 0), turnover=q.get('turnover', 0),\r\n"
    "                    ),\r\n"
    "                    now=datetime.now(), atr=r.get('atr'),\r\n"
    "                    structure={\r\n"
    "                        'near_support': r.get('near_support'),\r\n"
    "                        'near_resist': r.get('near_resist'),\r\n"
    "                        'cross': r.get('cross'),\r\n"
    "                        'div': r.get('div'),\r\n"
    "                        'td_low9': (r.get('td') or {}).get('is_low9'),\r\n"
    "                        'td_high9': (r.get('td') or {}).get('is_high9'),\r\n"
    "                    },\r\n"
    "                    market={'weak': bool(getattr(self, '_global_warn', False))},\r\n"
    "                )\r\n"
    "                if _T_ENGINE_AUTHORITATIVE:\r\n"
    "                    apply_plan_to_row(r, _t_plan)\r\n"
    "                else:\r\n"
    "                    _keep = {k: r.get(k) for k in (\r\n"
    "                        'signal_level', 'signal_text', 'signal_dir',\r\n"
    "                        'action', 'risk_status', 'buy_point', 'sell_point')}\r\n"
    "                    apply_plan_to_row(r, _t_plan)\r\n"
    "                    for _k, _v in _keep.items():\r\n"
    "                        if _v is not None:\r\n"
    "                            r[_k] = _v\r\n"
    "                self._tengine_plans = getattr(self, '_tengine_plans', {})\r\n"
    "                self._tengine_plans[code] = _t_plan\r\n"
    "            except Exception as _e:\r\n"
    "                # 刻意不静默：打印类型+原因+堆栈，避免「改了没变化」\r\n"
    "                import traceback\r\n"
    "                print('[intraday_t_engine] %s 评估失败: %s: %s' % (\r\n"
    "                    code, type(_e).__name__, _e), flush=True)\r\n"
    "                traceback.print_exc()\r\n"
    "            # ===== 接入结束 =====\r\n"
)
src = src.replace(a2, a2 + BLOCK, 1)

# ---------- 3) 静默 bug：atr 未绑定 ----------
n_atr = src.count('atr=atr,')
assert n_atr == 2, '预期 2 处 atr=atr,，实际 %d 处' % n_atr
src = src.replace('atr=atr,', "atr=r.get('atr', 0),")

open(P, 'w', newline='', encoding='utf-8').write(src)
after = open(P, newline='', encoding='utf-8').read()
naked = after.count('\n') - after.count('\r\n')
print('补丁后：总行数 %d，CRLF %d，裸LF %d' % (after.count('\r\n') + 1, after.count('\r\n'), naked))
print('atr=atr 残留:', after.count('atr=atr,'), '| atr=r.get 命中:', after.count("atr=r.get('atr', 0),"))
print('引擎块命中:', after.count('机构级分时做T引擎接入'), '| 开关命中:', after.count('_T_ENGINE_AUTHORITATIVE'))
if naked != 0:
    print('!! 行尾被破坏（出现裸 LF），需要回滚')
    sys.exit(1)
print('行尾完好（纯 CRLF）')
