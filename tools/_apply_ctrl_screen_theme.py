# -*- coding: utf-8 -*-
"""一次性补丁：控盘选股加「涨停题材」列。

服务 services\\control_screen_service.py（纯 LF）
  1) 新增 limit_up_theme(code)（与日K建仓/竞价同一来源 get_last_limit_up_reason）
  2) compute_stock 的 rec 加 4 个题材字段（默认空）
  3) scan_market 逐只填题材 + stats['theme_ok'] 计数
  4) 模块 docstring 加题材来源一行

页面 ui\\battle_widgets\\control_screen_widget.py（纯 LF）
  1) 11 列：在「涨跌幅」后插入「涨停题材」
  2) 拉伸列由 观察 → 涨停题材
  3) 排序键加题材
  4) _render 填题材单元格（紫色 #6a1b9a，与日K建仓一致；空显示 --；tooltip 给来源日/连板/行业）
  5) 新增 _theme_tip()

执行一次即失效，勿重跑。
"""
import io
import os
import shutil
import sys

ROOT = r'D:\QuantMonitorV6'
SVC = os.path.join(ROOT, 'services', 'control_screen_service.py')
WDG = os.path.join(ROOT, 'ui', 'battle_widgets', 'control_screen_widget.py')

# ---------------------------------------------------------------- 服务层
s = io.open(SVC, 'r', encoding='utf-8').read()
assert 'limit_up_theme' not in s, '服务层疑似已打过补丁'

S1_OLD = """# ============================================================
# 批量读 K 线（本服务的关键：一次 SQL 拿全市场）
# ============================================================"""
S1_NEW = """# ============================================================
# 涨停题材（最近一次涨停原因）
# ============================================================
def limit_up_theme(code):
    \"\"\"最近一次涨停原因 -> (reason, date, lbc, industry)。

    与「日K建仓」（atr_t_widget）/「竞价」（auction_filter_widget）**同一来源**：
        data.limit_up_reason_db.get_last_limit_up_reason(code)
      · 先查 source='wencai'，再查任意来源但 reason 必须含 '+'（真题材串；
        纯时间格式的 reason 不算）
      · 库里没有该股 / 无含 '+' 的题材 -> 返回 ('', '', 0, '')
    库里出现过的股票 3529 只（2025-09-15 ~ 至今）；单只查询实测 0.3ms，
    4400 只约 1.2 秒，所以直接在扫描线程里逐只取。
    \"\"\"
    try:
        from data.limit_up_reason_db import get_last_limit_up_reason
        r = get_last_limit_up_reason(str(code))
        if not r:
            return '', '', 0, ''
        try:
            _lbc = int(r[2] or 0)
        except Exception:
            _lbc = 0
        return str(r[0] or ''), str(r[1] or ''), _lbc, str(r[3] or '')
    except Exception:
        return '', '', 0, ''


# ============================================================
# 批量读 K 线（本服务的关键：一次 SQL 拿全市场）
# ============================================================"""

S2_OLD = """            'redfat_ratio': round(float(redfat.get('ratio') or 0.0), 2),
        }
"""
S2_NEW = """            'redfat_ratio': round(float(redfat.get('ratio') or 0.0), 2),
            # 涨停题材（最近一次涨停原因）：默认空，由 scan_market 统一填，见 limit_up_theme()
            'theme': '', 'theme_date': '', 'theme_lbc': 0, 'theme_ind': '',
        }
"""

S3_OLD = """    stats = {'universe': 0, 'ok': 0, 'skip_bars': 0, 'fail': 0,
             'elapsed': 0.0, 'data_date': ''}
"""
S3_NEW = """    stats = {'universe': 0, 'ok': 0, 'skip_bars': 0, 'fail': 0,
             'elapsed': 0.0, 'data_date': '', 'theme_ok': 0}
"""

S4_OLD = """            rec = compute_stock(c, b, names.get(c, ''), ti=ti, engine=E)
            if rec is None:
                stats['fail'] += 1
            else:
                rows.append(rec)
                stats['ok'] += 1
"""
S4_NEW = """            rec = compute_stock(c, b, names.get(c, ''), ti=ti, engine=E)
            if rec is None:
                stats['fail'] += 1
            else:
                # 涨停题材：最近一次涨停原因（与日K建仓同一来源，空串=库里没查到）
                _th, _thd, _thl, _thi = limit_up_theme(c)
                rec['theme'], rec['theme_date'] = _th, _thd
                rec['theme_lbc'], rec['theme_ind'] = _thl, _thi
                if _th:
                    stats['theme_ok'] += 1
                rows.append(rec)
                stats['ok'] += 1
"""

S5_OLD = """    短标签  services.control_profile.ctrl_label（白名单，不会把观察类文案误判成「候选」）
"""
S5_NEW = """    短标签  services.control_profile.ctrl_label（白名单，不会把观察类文案误判成「候选」）
    题材    data.limit_up_reason_db.get_last_limit_up_reason（最近一次涨停原因，
            与「日K建仓」「竞价」同源；空串=库里没有该股的含 '+' 题材）
"""

for tag, old, new in (('S1', S1_OLD, S1_NEW), ('S2', S2_OLD, S2_NEW),
                      ('S3', S3_OLD, S3_NEW), ('S4', S4_OLD, S4_NEW),
                      ('S5', S5_OLD, S5_NEW)):
    n = s.count(old)
    assert n == 1, '服务层锚点 %s 命中 %d 次' % (tag, n)
    s = s.replace(old, new, 1)

if not os.path.isfile(SVC + '.bak_before_theme'):
    shutil.copy2(SVC, SVC + '.bak_before_theme')
    print('备份: %s.bak_before_theme' % SVC)
io.open(SVC, 'w', encoding='utf-8', newline='').write(s)

# ---------------------------------------------------------------- 页面
w = io.open(WDG, 'r', encoding='utf-8').read()
assert 'C_THEME' not in w, '页面疑似已打过补丁'

W1_OLD = """PAGE_HEADERS = ['股票名称', '代码', '现价', '涨跌幅', '控盘分',
                '阶段', '位置', '控盘提示', '观察', '数据日']
PAGE_COL_N = len(PAGE_HEADERS)
(C_NAME, C_CODE, C_PRICE, C_PCT, C_SCORE,
 C_STAGE, C_POS, C_LABEL, C_OBS, C_DATE) = range(PAGE_COL_N)
PAGE_WIDTHS = [96, 66, 70, 74, 70, 58, 58, 96, 190, 90]
"""
W1_NEW = """PAGE_HEADERS = ['股票名称', '代码', '现价', '涨跌幅', '涨停题材', '控盘分',
                '阶段', '位置', '控盘提示', '观察', '数据日']
PAGE_COL_N = len(PAGE_HEADERS)
(C_NAME, C_CODE, C_PRICE, C_PCT, C_THEME, C_SCORE,
 C_STAGE, C_POS, C_LABEL, C_OBS, C_DATE) = range(PAGE_COL_N)
# 题材串很长（如「参股算力建设（金额较小）+工程咨询+AI应用+甘肃国资」），
# 所以拉伸列给题材、观察列固定宽度（观察标签最多 3 个短词，190 够）。
PAGE_WIDTHS = [96, 66, 70, 74, 230, 70, 58, 58, 96, 190, 90]
_THEME_COLOR = '#6a1b9a'   # 与「日K建仓」题材列同色
"""

W2_OLD = "        hh.setSectionResizeMode(C_OBS, QHeaderView.ResizeMode.Stretch)\n"
W2_NEW = "        hh.setSectionResizeMode(C_THEME, QHeaderView.ResizeMode.Stretch)\n"

W3_OLD = """                  C_LABEL: lambda r: str(r.get('label') or ''),
"""
W3_NEW = """                  C_LABEL: lambda r: str(r.get('label') or ''),
                  C_THEME: lambda r: str(r.get('theme') or ''),
"""

W4_OLD = """            _pct = float(r.get('pct') or 0)
            set_table_item(self.table, i, C_PCT, '%+.2f%%' % _pct, pct_color(_pct),
                           align=Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
"""
W4_NEW = """            _pct = float(r.get('pct') or 0)
            set_table_item(self.table, i, C_PCT, '%+.2f%%' % _pct, pct_color(_pct),
                           align=Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            # 涨停题材：最近一次涨停原因（limit_up_reason_db），空显示 --
            _th = str(r.get('theme') or '')
            _th_item = set_table_item(self.table, i, C_THEME, _th or '--',
                                      _THEME_COLOR if _th else BC.TEXT3)
            _th_item.setToolTip(_theme_tip(r))
"""

W5_OLD = """def _obs_color(tags):"""
W5_NEW = """def _theme_tip(rec):
    \"\"\"涨停题材列 tooltip：题材串 + 最近一次涨停的日期/连板/行业（便于核对）。\"\"\"
    _th = str(rec.get('theme') or '')
    if not _th:
        return '本地涨停原因库（data/limit_up_reason.db）里没有该股的含「+」题材'
    _d = str(rec.get('theme_date') or '')
    _d = '%s-%s-%s' % (_d[0:4], _d[4:6], _d[6:8]) if len(_d) == 8 else (_d or '-')
    return ('涨停题材：%s\\n来源：最近一次涨停 %s ｜ %s连板 ｜ 行业：%s'
            % (_th, _d, int(rec.get('theme_lbc') or 0) or '-',
               rec.get('theme_ind') or '-'))


def _obs_color(tags):"""

W6_OLD = """控盘标准（三层，全部复用项目单一来源，不另写一套）
------------------------------------------------"""
W6_NEW = """列（11 列）：股票名称 / 代码 / 现价 / 涨跌幅 / **涨停题材** / 控盘分 / 阶段 /
位置 / 控盘提示 / 观察 / 数据日。涨停题材与「日K建仓」「竞价」同源：
data.limit_up_reason_db.get_last_limit_up_reason(code)（最近一次涨停原因）。

控盘标准（三层，全部复用项目单一来源，不另写一套）
------------------------------------------------"""

for tag, old, new in (('W1', W1_OLD, W1_NEW), ('W2', W2_OLD, W2_NEW),
                      ('W3', W3_OLD, W3_NEW), ('W4', W4_OLD, W4_NEW),
                      ('W5', W5_OLD, W5_NEW), ('W6', W6_OLD, W6_NEW)):
    n = w.count(old)
    assert n == 1, '页面锚点 %s 命中 %d 次' % (tag, n)
    w = w.replace(old, new, 1)

if not os.path.isfile(WDG + '.bak_before_theme'):
    shutil.copy2(WDG, WDG + '.bak_before_theme')
    print('备份: %s.bak_before_theme' % WDG)
io.open(WDG, 'w', encoding='utf-8', newline='').write(w)

# ---------------------------------------------------------------- 校验
import py_compile     # noqa: E402
import tempfile       # noqa: E402

for p in (SVC, WDG):
    raw = io.open(p, 'rb').read()
    lf = raw.count(b'\n')
    crlf = raw.count(b'\r\n')
    print('%s: 行=%d CRLF=%d 裸LF=%d 字节=%d'
          % (os.path.basename(p), lf, crlf, lf - crlf, len(raw)))
    assert crlf == 0, '%s 被写成 CRLF（本文件应为纯 LF）' % p
    py_compile.compile(p, cfile=os.path.join(tempfile.gettempdir(), 'cs_theme.pyc'),
                       doraise=True)
print('两个文件语法校验通过')
