# -*- coding: utf-8 -*-
"""一次性：把 A/B/C 这一批写进 AGENTS.md（纯 LF，追加章节）。"""
import io
import os

os.chdir(r'D:\QuantMonitorV6')
P = 'AGENTS.md'
s = io.open(P, encoding='utf-8', newline='').read()
assert '\r\n' not in s
SEC = """
---

## 2026-10-11 A/B/C 三件套：破位—收复 / 量能分位（地量·天量·缩量上涨） / 拉升②位置下限修正

来源：用户贴《机构、庄家、主力操盘控盘的核心逻辑与手法拆解》，逐条对账后只做三个真缺口（A/B/C），
按用户「按照顺序升级」= A → B → C 落地。**照旧先标定、后落地**：两个因子都先用项目自己的滚动观测口径
（17516 条 / 4384 只 / 锚点 k=20/40/60/80 / 只喂 `df[:T+1]` / 无未来数据）标定，再决定出不出文案。

### 标定结论（决定「出不出文案」，不是手感）

| 分组 | n | 未来20日均值 | 胜率 | t | 处置 |
|---|---|---|---|---|---|
| 全样本基准 | 17516 | -0.78% | 45.2% | -7.79 | 基准 |
| A 破位未收 | 180 | **-3.63%** | 33.9% | -3.76 | **出风险文案** |
| A 洗盘收复（全） | 552 | -1.08% | 47.5% | -1.75 | 只写字段 |
| A 洗盘收复 pos<0.45 | 474 | -0.41% | 50.8% | -0.65 | 不显著 → 只写字段 |
| B 天量 | 2849 | **-2.44%** | 37.7% | **-8.36** | **出警示** |
| B 缩量上涨（全） | 702 | +2.64% | 58.5% | +4.84 | 限低位出 |
| B 缩量上涨 pos<0.45 | 518 | **+4.34%** | **66.4%** | **+8.21** | **限 pos<0.45 出文案** |
| B 地量 | 5604 | +0.02% | 47.6% | +0.14 | 噪音 → 只写字段 |
| C ②缩量强势 pos<0.35 | 2458 | +2.36% | 58.1% | +11.66 | 下限改 0.00 |
| C ②缩量强势 pos∈[0.55,0.75) | 147 | -2.83% | — | -2.89 | 原下限就锁在这里 |

量能分位整体单调：pct[0,20) -0.07% → [80,101) -2.44%（**分位越高越差**，故天量=风险而非机会）。

### 代码改动

**`strategy\\base.py`（纯 CRLF，1949 → 1952 行）**
- 新增常量块 `BRK_*`（`BRK_LOOKBACK=12 / BRK_SUPPORT_WIN=20 / BRK_RECOVER_WIN=5 / BRK_SHRINK_MAX=1.00 /
  BRK_EXPAND_MIN=1.50 / BRK_RECOVER_VOL=1.20 / BRK_POS_LOW=0.55 / BRK_SCORE_OK=70.0 / BRK_MIN_BARS=60`）
  与 `VR_*`（`VR_WIN=60 / VR_LOW_PCT=20.0 / VR_HIGH_PCT=80.0 / VR_SU_WIN=5 / VR_SU_VOL_MAX=0.90 /
  VR_SU_GAIN_MIN=0.03 / VR_SU_YANG_MIN=0.60 / VR_SCORE_OK=70.0 / VR_MIN_BARS=60`），紧跟 `MARKUP_POS_MAX` 之后。
- 新增 `TechnicalIndicators.detect_breakdown_recover()` / `volume_percentile(df, win)` / `detect_volume_regime()`，
  插在 `detect_markup` 之后、`# K线数据解析` 段头之前。返回契约沿用项目约定（`ok/type|tags/score` 两段不重叠
  `ok=True` 必 ≥70、未通过 ≤60 / `pos120` / `detail` / `reason`）。
  - 口径坑：破位日必须是「`low[i] < min(low[i-20:i])`」的**最近一次**；收复要「其后 5 根内 `close >= 支撑`」；
    `p5 = sum(volumes[i-5:i]) / 5.0` **绝不含当前K线**（B 与模式四同一条硬约束）。
  - 分数两段不重叠是**给 DB 反查用的**，别改成连续打分。
- **C 项**：`MARKUP_LOCK_POS_MIN` **0.55 → 0.00** + 依据注释；`detect_markup` docstring 里「②不可达」那句
  改成「自 2026-10-11 起位置下限 0.00，在本门槛内可正常命中」。全局 `MARKUP_POS_MAX=0.45` 未动。

**`services\\band_pattern_engine.py`（纯 LF，2074 → 2171 行）**
- 常量：`_BRK_NOTE_MODE='watch'` / `_BRK_FUNNEL={'ok','insuf','pos','nobreak','wash','dist','note'}` /
  `_VREG_NOTE_MODE='watch'` / `_VREG_FUNNEL={'ok','insuf','low','high','shrinkup','note'}`；
  拉升段那段「②不可达」的注释同步更新。
- `_ctrl_note(..., brk=None, vreg=None)` / `_observe_tags(..., brk=None, vreg=None, pos=None)`；
  新文案：`'破位警示：放量破位未收回'`（仅 `brk=='破位未收'`）、`'天量警示'`、
  `'缩量上涨·疑似控盘'`（**且 pos<0.45**）。「洗盘收复」「地量」**只写字段不出文案**。
- `_ALL_COLS` 59 → **64 列**（`brk_ok INTEGER / brk_type TEXT / brk_score REAL / vreg_tags TEXT / vreg_pct REAL`，
  自动 ALTER 已打印 `DB补齐字段(pattern_record): [...5 个]`）；`_save_or_update` 的列清单 / 占位符（59→64）/
  取值三处同步（**取值元组比列清单少 1 项是正常的**：末列 `updated_at` 是 `datetime.now()` 字面量表达式）；
  `scan_stock` 局部量 + 计算块（复用同一个 `_df`，接在 markup 漏斗后）+ `_ctrl_note` 调用 + 计数器 + `rec`；
  `scan_all` 清零 + 两组打印。

### 实测（`tools\\run_scan_quiet.py` → `tools\\_scan_after_brkvr.log`）

- 全市场 **5223 只 / 异常 0 / 模式一 191 / 模式三 39 / 总记录 230**，与上一批**逐项 0 变化**（新因子不参与筛选）。
- `[破位收复] 可算 2347 只 ｜ 洗盘收复 106 ｜ 破位未收 368 ｜ 位置超限(pos>=0.55) 620 ｜ 无破位日 614 ｜ 文案 474`
- `[量能分位] 可算 3581 只 ｜ 地量 298 ｜ 天量 812 ｜ 缩量上涨 54 ｜ 文案 1144 只`
- `[拉升观察] 可算 2675 ｜ 阶梯式上行 76 ｜ **缩量强势 58（修复前恒为 0）** ｜ 加速迹象 1 ｜ 命中合计 135`
- DB 230 条里：**破位警示 7 条 / 天量警示 67 条 / 缩量上涨·疑似控盘 4 条**（9 条 `缩量上涨` 里只有 4 条 pos<0.45）；
  日K建仓默认筛选（建仓触发+等待确认）203 行里 **59 行**能带出新文案。

### 验证

- `tools\\_verify_brkvr.py`（**可重跑**）→ `tools\\brkvr_verify.txt`：**28 PASS / 0 FAIL**。
  ① 源码结构：CRLF/LF 行尾、`BRK_POS_LOW=0.55`、`MARKUP_LOCK_POS_MIN=0.00`、三个 `@staticmethod`、
  docstring 无单反斜杠转义、`_ALL_COLS == INSERT 列 == 占位符 == 64`、取值元组与列清单逐项同序同名；
  ② **229 条 DB 记录用独立重写的实现逐只重算**（不调用被验证函数）：`brk_type/brk_ok/brk_score/vreg_tags/vreg_pct`
  **0 处不一致**；③ 文案与字段零矛盾（`破位未收` 7/7 都出警示、`天量` 67/67 都出警示、洗盘收复不出警示）；
  ④ C 项：`markup_type='缩量强势'` 的记录 **pos120 全部 <0.45**。
- `tools\\_brkvr_dbui.py`（**可重跑**）→ `tools\\brkvr_dbui.txt`：**6 PASS / 0 FAIL**。
  UI 侧 `atr_t_widget.py` L2128-2130 `_note = r.get('note','')` → `_tg_item.setToolTip(_note)`，
  新文案走**触发条件列 tooltip**，全文可见，不需要改 UI。
- 回退：`copy /Y "strategy\\base.py.bak_before_brkvr_engine" "strategy\\base.py"` +
  `copy /Y "services\\band_pattern_engine.py.bak_before_brkvr_engine" "services\\band_pattern_engine.py"` +
  （C 项另需）`copy /Y "strategy\\base.py.bak_before_brkvr" "strategy\\base.py"`，**回退后必须重跑全市场扫描**；
  只想去掉文案 → `_BRK_NOTE_MODE` / `_VREG_NOTE_MODE` 改 `'off'`（字段继续写，无需改代码）。
- 还原点：A/B/C **之前**的 `backups\\backup_20261011_164852` 仍在；**A/B/C 之后尚未打新快照**
  （`scripts\\backup.py` 只留最近 10 份，会挤掉最旧的一份，需要就说一声）。

### 本批踩的坑（别重复）

1. **`@staticmethod` 必补**：同族老函数（`estimate_control_score` / `detect_probe` / `detect_markup`）都带
   `@staticmethod`，引擎是 `_ti = _TI()` 后用**实例**调用 → 漏装饰器就 `TypeError: takes 1 positional argument
   but 2 were given`，异常被 try/except 吞掉、字段永远全 0（**本次真实发生过**）。
2. **docstring 里的 Windows 路径必须双反斜杠**：`tools\\markup2_pos_calib.txt` 写成单反斜杠 → `SyntaxWarning: "\\m"`
   （L1260）。**注释里的单反斜杠无害**，只有 docstring/字符串要改。
3. **打印里 import 常量要核对真名**：我写成 `from strategy.base import BRK_POS_MAX as _BPMAX`，真名是
   `BRK_POS_LOW` → 扫描数据已落库但尾部漏斗日志整体被 ImportError 打断（进程退 1）。
4. `_ALL_COLS` 与 INSERT **列顺序本来就不同**（列名显式给出），别拿两边顺序做相等断言；
   真正要对齐的是**取值元组 vs INSERT 列清单**，且取值元组天然少 1 项（`updated_at` 字面量）。
"""
if not s.endswith('\n'):
    s += '\n'
s += SEC
io.open(P, 'w', encoding='utf-8', newline='').write(s)
c = io.open(P, encoding='utf-8', newline='').read()
print('AGENTS.md %d -> %d 行 ｜ 裸CRLF %d ｜ 字节 %d'
      % (s.count('\n') - SEC.count('\n'), c.count('\n'), c.count('\r\n'), len(c.encode('utf-8'))))
