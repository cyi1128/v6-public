# -*- coding: utf-8 -*-
"""给日K建仓表加一列「控盘」，让控盘提示不用悬停就能看见。
atr_t_widget.py 是纯 CRLF：先转 LF 打补丁，再转回 CRLF 写盘。
5 处必须同步改（少一处这一列就是空的）：
  1) 列常量 range(11) -> range(12) + COL_D_CTRL
  2) HEADER_DAILY 加表头
  3) DAILY_WIDTHS 加宽度
  4) make_table(11, ...) -> make_table(12, ...)
  5) 行映射带上 control_score / stage_guess；渲染函数加单元格
"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
BAK = P + '.bak_before_ctrl_col'
sys.stdout.reconfigure(encoding='utf-8')

shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') > 0, 'atr_t_widget.py 应为 CRLF'
s = raw.decode('utf-8').replace('\r\n', '\n')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# ---- 1) 列常量 + 表头 + 宽度 ----
rep("# 日K建仓表列（11列）\n"
    "# 顺序：股票名称 代码 现价 涨跌幅 建仓价 止盈价 题材 模式 触发条件 环境分 基准日\n"
    "COL_D_NAME, COL_D_CODE, COL_D_PRICE, COL_D_PCT, COL_D_TRIG_PRICE, \\\n"
    "    COL_D_TAKE_PROFIT, COL_D_THEME, COL_D_PATTERN, COL_D_TRIGGER, \\\n"
    "    COL_D_ENV, COL_D_BASE_DATE = range(11)\n"
    "HEADER_DAILY = ['股票名称', '代码', '现价', '涨跌幅', '建仓价', '止盈价',\n"
    "                '题材', '模式', '触发条件', '环境分', '基准日']\n",
    "# 日K建仓表列（12列）\n"
    "# 顺序：股票名称 代码 现价 涨跌幅 建仓价 止盈价 题材 模式 触发条件 控盘 环境分 基准日\n"
    "COL_D_NAME, COL_D_CODE, COL_D_PRICE, COL_D_PCT, COL_D_TRIG_PRICE, \\\n"
    "    COL_D_TAKE_PROFIT, COL_D_THEME, COL_D_PATTERN, COL_D_TRIGGER, \\\n"
    "    COL_D_CTRL, COL_D_ENV, COL_D_BASE_DATE = range(12)\n"
    "HEADER_DAILY = ['股票名称', '代码', '现价', '涨跌幅', '建仓价', '止盈价',\n"
    "                '题材', '模式', '触发条件', '控盘', '环境分', '基准日']\n",
    'F1 列常量+表头')

rep("DAILY_WIDTHS = [80, 70, 58, 72, 58, 58, 0, 92, 86, 52, 92]\n",
    "DAILY_WIDTHS = [80, 70, 58, 72, 58, 58, 0, 92, 86, 74, 52, 92]\n",
    'F2 列宽')

# ---- 2) make_table 列数 ----
rep("self.daily_table = make_table(11, HEADER_DAILY)\n",
    "self.daily_table = make_table(12, HEADER_DAILY)\n",
    'F3 make_table 列数')

# ---- 3) 行映射带上两字段 ----
rep("                'env_note': s.get('env_note', '') or '',\n"
    "                'note': s.get('note', ''),\n",
    "                'env_note': s.get('env_note', '') or '',\n"
    "                'note': s.get('note', ''),\n"
    "                # 控盘：estimate_control_score 的分数 + judge_wash_or_distribute 的阶段\n"
    "                'control_score': s.get('control_score') or 0,\n"
    "                'stage_guess': s.get('stage_guess') or '',\n",
    'F4 行映射')

# ---- 4) 单元格渲染 ----
rep("            self.daily_table.setItem(i, COL_D_ENV, _e_item)\n",
    "            self.daily_table.setItem(i, COL_D_ENV, _e_item)\n"
    "            # 控盘：分数 + 提示短标签（悬停看完整文案）\n"
    "            # 有提示显示成「98·候选 / 80·出货 / 98·洗盘」，颜色分档；无提示只显示分数。\n"
    "            _cs = float(r.get('control_score') or 0)\n"
    "            _nt = r.get('note') or ''\n"
    "            _has_tip = '[控盘]' in _nt\n"
    "            if _has_tip:\n"
    "                _tt = _nt.split('[控盘]')[-1].strip().replace('\\n', ' ')\n"
    "                if '疑似洗盘' in _tt:\n"
    "                    _clabel, _ccol = '洗盘', '#ef6c00'\n"
    "                elif '出货' in _tt:\n"
    "                    _clabel, _ccol = '出货', '#c62828'\n"
    "                else:\n"
    "                    _clabel, _ccol = '候选', '#2e7d32'\n"
    "                _ctxt = '%d·%s' % (int(round(_cs)), _clabel)\n"
    "            else:\n"
    "                _ccol = '#9e9e9e'\n"
    "                _ctxt = str(int(round(_cs))) if _cs else '--'\n"
    "            _c_item = QTableWidgetItem(_ctxt)\n"
    "            _c_item.setForeground(QColor(_ccol))\n"
    "            _c_item.setTextAlignment(center)\n"
    "            _c_item.setToolTip('控盘分 %.1f（%s）%s' % (\n"
    "                _cs, r.get('stage_guess') or '--', ('\\n' + _nt if _has_tip else '')))\n"
    "            self.daily_table.setItem(i, COL_D_CTRL, _c_item)\n",
    'F5 单元格渲染')

open(P, 'wb').write(s.replace('\n', '\r\n').encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  atr_t_widget.py 已加「控盘」列（写回 CRLF）')
print('  备份:', BAK)
