# -*- coding: utf-8 -*-
"""V18：市场节奏接三轴状态闸门 —— 冰点期只记录不推送；界面显示当前状态。
闸门放在后台 worker 线程里算（含 duckdb 查询），不阻塞 UI。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\market_rhythm_widget.py'
BAK = P + '.bak_before_regime'

sys.stdout.reconfigure(encoding='utf-8')
shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
crlf = raw.count(b'\r\n')
lf = raw.count(b'\n') - crlf
assert crlf == 0, '本文件应为纯 LF（实测 CRLF=%d LF=%d）' % (crlf, lf)
s = raw.decode('utf-8')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# ---- 1) __init__ 初始占位 ----
rep("        self._rows = []          # Tab1 行\n",
    "        self._rows = []          # Tab1 行\n"
    "        self._regime = {}        # V18 三轴状态闸门读数\n",
    'B1 __init__ 占位')

# ---- 2) 后台线程里算闸门 ----
rep("            except Exception as e:\n"
    "                out['rhythm_err'] = str(e)[:200]\n"
    "            try:\n"
    "                from services.board_anomaly_engine import (get_board_anomaly,\n",
    "            except Exception as e:\n"
    "                out['rhythm_err'] = str(e)[:200]\n"
    "            try:\n"
    "                from services.regime_gate import compute as _rg\n"
    "                out['regime'] = _rg()\n"
    "            except Exception as e:\n"
    "                out['regime_err'] = str(e)[:200]\n"
    "            try:\n"
    "                from services.board_anomaly_engine import (get_board_anomaly,\n",
    'B2 worker 算闸门')

# ---- 3) _apply 先存闸门（渲染会用到）----
rep("    def _apply(self, d):\n"
    "        # ---- Tab1 ----\n"
    "        rh = d.get('rhythm') or {}\n",
    "    def _apply(self, d):\n"
    "        self._regime = d.get('regime') or {}\n"
    "        # ---- Tab1 ----\n"
    "        rh = d.get('rhythm') or {}\n",
    'B3 _apply 存闸门')

# ---- 4) Tab1 显示状态 ----
rep("                d.get('date', '--'), d.get('lu_count', 0),\n"
    "                d.get('max_lbc', 0), d.get('theme_count', 0), span))\n",
    "                d.get('date', '--'), d.get('lu_count', 0),\n"
    "                d.get('max_lbc', 0), d.get('theme_count', 0), span))\n"
    "        _rg = getattr(self, '_regime', None) or {}\n"
    "        if _rg.get('state'):\n"
    "            self.market_label.setText(\n"
    "                self.market_label.text()\n"
    "                + '  ｜ 状态闸门：%s（%s）' % (_rg.get('state', ''),\n"
    "                                          _rg.get('note', '')))\n",
    'B4 Tab1 显示状态')

# ---- 5) 可介入 显示状态 ----
rep("            ' ｜ 机构门槛：成交额≥2亿·流通市值≥20亿 ｜ ✅=算法单痕迹'\n"
    "            % (dt, meta.get('lu_count', '--'), _n_pick, _n_row))\n",
    "            ' ｜ 机构门槛：成交额≥2亿·流通市值≥20亿 ｜ ✅=算法单痕迹'\n"
    "            % (dt, meta.get('lu_count', '--'), _n_pick, _n_row))\n"
    "        _rg = getattr(self, '_regime', None) or {}\n"
    "        if _rg.get('state'):\n"
    "            self.pick_label.setText(\n"
    "                self.pick_label.text() + '  ｜ 闸门：%s' % _rg.get('state', ''))\n",
    'B5 可介入显示状态')

# ---- 6) 推送过滤 ----
rep("    def _push_boards(self, rows):\n"
    "        if not rows:\n"
    "            return\n"
    "        from services.board_anomaly_engine import is_trading_now\n"
    "        if not is_trading_now():\n"
    "            return\n",
    "    def _push_boards(self, rows):\n"
    "        if not rows:\n"
    "            return\n"
    "        from services.board_anomaly_engine import is_trading_now\n"
    "        if not is_trading_now():\n"
    "            return\n"
    "        # V18 三轴状态闸门：冰点期只记录不推送\n"
    "        try:\n"
    "            from services.regime_gate import compute as _rg\n"
    "            _r = _rg()\n"
    "            if not _r.get('push', True):\n"
    "                print('[市场节奏] 状态闸门 %s：本轮只记录不推送'\n"
    "                      % _r.get('state', ''), flush=True)\n"
    "                return\n"
    "        except Exception as _e:\n"
    "            print('[市场节奏] 状态闸门不可用，按放行处理: %s' % _e, flush=True)\n",
    'B6 推送过滤')

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  市场节奏已接三轴状态闸门')
print('  备份:', BAK)
