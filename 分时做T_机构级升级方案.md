# 分时做T 机构级升级方案（诊断 → 方案 → 代码 → 参数与坑）

时间：2026-10-11　　范围：`ui\battle_widgets\atr_t_widget.py`（2261 行，纯 CRLF，本文件**本轮未改动**）
新增：`strategy\intraday_t_engine.py`（565 行，纯 LF，新文件，零风险）
验证：`tools\_verify_intraday_t_engine.py` → `tools\verify_intraday_t_engine.log`（**45 PASS / 0 FAIL / 0 SKIP**）

---

## 一、问题诊断（对着你的 6 条机构标准，逐条给代码事实）

| 你要求的标准 | 代码里实际是什么 | 位置 | 结论 |
|---|---|---|---|
| ① 持仓成本偏离（最核心） | `cost` 全文件只出现 7 处：L277 注释 / L309 建表 / L338 查询 / L341 读库 / L538 装配 / L549 自选兜底 `None` / **L906 `r['cost'] = item.get('cost')`**。L906 是唯一一次赋值，**赋完之后再没有任何一行读过它**；`_apply_risk_and_signal(self, r, in_open_window)` 的入参里也没有成本 | L552-677 / L679-855 | **零实现** |
| ② 真·分时 VWAP | L586 `vwap = (day_high + day_low + price) / 3.0` —— 这是典型价（HLC/3），**不是成交量加权均价**。而卖点 `vwap+k*ATR`、买点 `vwap-k*ATR`、防飞刀 `price < vwap*0.985` 三处判断全建在它上面 | L586、L699、L708 | **公式错误** |
| ③ 量价结构 | `vol_ratio`（量比）**0 处引用**、`turnover`（换手）**0 处引用**、`amount`（成交额）**0 处引用**。动能列用的是**日线** MACD/TD/背离/支撑压力（bars 取 80 根日K） | L657-663、L949-987 | **零实现**（日内做T却在看日线指标） |
| ④ 时间窗口过滤 | 只有 L864 `in_open_window = (h == 9 and 30 <= m <= 45)`，命中就把信号压成 🟡 暂停、「等9:45后再操作」 | L864、L838-843 | 只有 9:30-9:45 一个"暂停"窗口；你要的 **10:30 前后 / 13:00-13:30 / 14:00-14:40 一个都没有**，午休 11:30-13:00 也没封死 |
| ⑤ 反T 优先于正T | L740-747 按题材强弱写 `dir_note` 文本（`theme_dir=='strong'` → 取消 red_sell，`'weak'` → 取消 red_buy），只是**文案** | L740-747 | **没有基于成本/底仓可用量的优先级机制**，也没有 T+1 可用量概念 |
| ⑥ 可量化强度分 | `signal_level` 只有 `red/orange/yellow/green/gray` 五档；`struct_score` 是 0~3 的整数计数（触支撑压力+1、背离+1、TD9+1） | L657-663 | **零实现**：没有 0-100 分、没有仓位建议、没有成本变化预估 |

### 诊断之外，另查到一个**静默失效（真 bug）**

- `_apply_risk_and_signal` 里 **L785**（买入观察）和 **L802**（卖出观察）两次调用
  `get_wechat_bus().send_t_timing(..., atr=atr, ...)`，
  但函数参数只有 `(self, r, in_open_window)`，函数体内**从未绑定 `atr`**，模块级也没有。
- AST 实证：该函数未绑定的自由名 = `['SIGNAL_FG', 'atr', 'get_wechat_bus']`，
  两处 `atr=` 出现时 `'atr' in local` 均为 `False`。
- 后果：每次调用抛 `NameError`，被外层 `except Exception: pass` 吃掉 →
  **分时做T的微信「买入/卖出观察」推送从来没发出去过**（一直是死的，只是不报错）。
- 修法 1 行：`atr=r.get('atr', 0)`（`_calc_one_stock` 返回的 dict 里本来就有 `atr`）。

### 诊断之外，还查到一个**数据侧空档**

`data\cache\atr_t_tracking.duckdb` 的 `holding` 表现实测 **0 行**（列：code/name/cost/qty/buy_time/exec_buy/exec_sell/anchor_vwap/updated_at）。
→ 就算引擎写好，**没有成本数据，第 ① 条标准在实盘也永远是"无成本、按中性处理"**。
必须先在持仓表录入（或用界面录入），成本维度才会真正参与决策。

---

## 二、升级方案概述

### 架构切法（为什么这么做）

```
行情(amount/volume/vol_ratio/turnover)  持仓(cost/qty/buy_time)  日线结构(支撑压力/MACD/TD)  时刻
                │                              │                        │                    │
                └──────────────► strategy\intraday_t_engine.py ◄─────────┴────────────────────┘
                                    IntradayTEngine.evaluate()
                                              │  plan(dict)
                                    apply_plan_to_row(r, plan)
                                              │
                        现有「信号灯 / 风控 / 操作建议」三列 + 买点卖点两列（无需加列）
```

把"判定"从 UI 里抽出来，做成**纯逻辑引擎**（只 import `dataclasses/datetime/typing`，无 Qt、无网络、无 DB）：

1. **可独立验证**：本轮的 45 条用例全部直接对引擎跑，不依赖界面；
2. **参数集中**：所有阈值在 `TParams`（L40）一处，调参不动判断分支；
3. **替换安全**：与 `_calc_one_stock` / `_apply_risk_and_signal` 解耦，老逻辑一行没动。

### 六条标准的落点

| 标准 | 落点 |
|---|---|
| ① 成本偏离 | `cost_score`：反T 要求 `dev ≥ +1.0%`（`rev_min_dev`），正T 要求 `dev ≤ -1.0%`（`fwd_max_dev`），深套（≤-8%）**直接不给低吸摊薄** |
| ② 真 VWAP | `TQuote.intraday_vwap()`（L141）：`amount/(volume×100)`，带合理性闸门（越界自动退回 HLC/3 并标 `fallback`）；`vwap_score = clamp((price-vwap)/(0.6×ATR))`，不用固定百分比 |
| ③ 量价结构 | `volume_price_state()`（L265）四态：放量上攻不持续→高抛、下跌缩量有承接→低吸、**放量下跌→硬阻断低吸**、缩量上涨→中性 |
| ④ 时间窗口 | `TIME_WINDOWS`（L161）12 段权重：9:35-10:00=1.0、10:15-10:45=1.0、13:00-13:30=1.0、14:00-14:40=1.0、14:40-15:00=0.7、9:30-9:35=0.3、次级时段=0.5~0.6、午休/收盘=0（直接封死） |
| ⑤ 反T 优先 | 主流程先算反向分，`side='reverse'` 且**底仓可用 > 0** 才给反T；T+1（今日买入）自动降级并提示 |
| ⑥ 强度分 | `score = 100×(0.30×cost + 0.25×vwap + 0.20×vol + 0.10×time + 0.15×struct)`，落到 4 档仓位（12%/20%/25%/30%，正T 打 7 折） |

### 多出来的两道护栏（你要的"降成本而非赚价差"）

- **盈亏平衡价差**：价差 ≤ 手续费+滑点（`breakeven_spread`，L223）→ **直接不出信号**，并写明"做T等于白交手续费"；
- **成本预估**：`estimate_cost()`（L238）给出 `做T后成本 / Δ% / 需追加资金`，并显式提示"预估不能降低成本"的情况。

---

## 三、可直接替换的核心代码

### 1）引擎（已落盘，无需你再贴）

文件：`D:\QuantMonitorV6\strategy\intraday_t_engine.py`（565 行，纯 LF）

| 关键位置 | 内容 |
|---|---|
| L40 | `TParams`：全部阈值（成本/VWAP/量价/评分权重/费用/滑点/仓位梯度） |
| L89 / L129 | `THolding`（含 `available_qty()` T+1 推断，L98）/ `TQuote`（含 `intraday_vwap()`，L141） |
| L161 / L182 | `TIME_WINDOWS` 12 段权重表 / `resolve_window(now)` |
| L201-263 | 费用三件套：`trade_fee` / `slippage_cost` / `round_trip_cost` / `breakeven_spread` / `estimate_cost` |
| L265 | `volume_price_state()` 量价四态 |
| L315 | `structure_scores()` 复用你现有日线结论（支撑压力/背离/TD/金叉死叉） |
| L352 | `evaluate()` 主入口：硬闸门 → 双向打分 → 反T优先 → 反T数量/成本预估 → 价差护栏 → 文案 |
| L530 | `apply_plan_to_row(row, plan)` 写回现有行字段 |

### 2）接进现有模块（8 行，放在 `_fetch_and_calc` 里 `r['cost'] = ...` 之后）

```python
# ---- 文件顶部 import ----
from strategy.intraday_t_engine import THolding, TQuote, get_engine, apply_plan_to_row

# ---- 在 L906 之后（r['cost'] = item.get('cost') 的下一行）----
_q = _quotes.get(code, {}) if isinstance(_quotes, dict) else {}
plan = get_engine().evaluate(
    THolding(code=code, name=r.get('name', ''), cost=item.get('cost'),
             qty=item.get('qty'), buy_time=item.get('buy_time')),
    TQuote(price=price, prev_close=_prev_close,
           high=day_high, low=day_low,
           volume_lots=_q.get('volume', 0), amount=_q.get('amount', 0),
           vol_ratio=_q.get('vol_ratio', 0), turnover=_q.get('turnover', 0)),
    now=datetime.now(), atr=r.get('atr'),
    structure=dict(near_support=r.get('near_support'), near_resist=r.get('near_resist'),
                   cross=r.get('cross'), div=r.get('div'),
                   td_low9=(r.get('td') or {}).get('is_low9'),
                   td_high9=(r.get('td') or {}).get('is_high9')),
    market=dict(weak=self._global_warn),
)
apply_plan_to_row(r, plan)      # 信号灯/风控/操作建议 + 买点卖点 直接生效，不需要加列
```

> 变量名按你 `_fetch_and_calc` 里的实际局部名对一下（`price` / `day_high` / `day_low` / 行情 dict 的引用）。
> 关键是：**行情那个 dict 里必须把 `amount` / `volume` / `vol_ratio` 取出来传进去**——
> 现在这三个字段在模块里是 0 引用，不传进来真 VWAP 就没数据源。

### 3）顺手修掉那个静默失效（1 行）

```python
# L785 与 L802 两处，把 atr=atr 改成：
atr=r.get('atr', 0),
```

### 4）UI 不需改列（保持你现有版式）

- 信号灯列：`🔴 反T 92分` / `🟠 正T 71分` / `🟡 观察 63分` / `⛔ 放量下跌`
- 操作建议列：`先卖后买 600股：卖 30.93 → 回落买回 29.84，成本 → 29.569 (-0.100%)`
- 风控列：`VWAP上方 · 放量上攻不持续`；买点/卖点列自动切成 VWAP±k×ATR 的目标价

---

## 四、使用说明、参数建议与坑

### 1）前置：先把持仓录进去（否则第①条永远不生效）

`data\cache\atr_t_tracking.duckdb` → `holding(code, name, cost, qty, buy_time, exec_buy, exec_sell, anchor_vwap, updated_at)`
当前 **0 行**。成本、数量（`qty`）必须录；`buy_time` 录了才能自动判 T+1 可用量。
`qty` 混批（今天买过、昨天也有底仓）时，用 `THolding(qty_avail=...)` 手工指定可用量 —— 其它情况按保守低估处理。

### 2）参数建议（都在 `TParams`）

| 参数 | 默认 | 说明 / 建议 |
|---|---|---|
| `rev_min_dev` / `fwd_max_dev` | +1.0% / -1.0% | 成本偏离门槛。你的票波动大（创业板）可提到 1.5%/2.0% |
| `deep_loss_dev` | -8.0% | 低于此**不给**低吸摊薄信号（防"用做T掩盖该止损"） |
| `k_vwap` | 0.60 | 离 VWAP 0.6×ATR 才满分。小盘股噪声大可提到 0.8~1.0 |
| `vwap_break_pct` | 0.985 | 跌破 VWAP 1.5% 封死买入（原模块也有这条，口径现在变准了） |
| `vol_expand` / `vol_shrink` | 1.5 / 0.7 | 量比口径，直接吃券商字段 |
| `min_score_action` | 65 | 出执行信号的门槛；觉得太密就提到 70~72 |
| 评分权重 | 30/25/20/10/15 | 想更看重成本就加大 `w_cost` |
| 仓位梯度 | 30/25/20/12% | 分数越高比例越大；正T 再打 7 折（要额外资金） |
| 费用 | 佣金万2.5、最低5元；印花税 0.05%（卖）；过户费 0.001%（双）；滑点 1 跳 | **按你真实券商改**，这是决定"值不值得做"的关键 |

### 3）必须知道的坑

1. **小单做T基本不划算**：`qty=100、价 10` 时盈亏平衡价差 = **0.1252 元/股（1.25%）**——因为 5 元最低佣金摊到 100 股就是 0.05 元/股。`qty=2000` 时只要 **0.0302 元/股（0.30%）**。→ 做T数量别太小。
2. **滑点**：默认 1 跳（0.01 元）单边；低价股（3-5 元）1 跳就是 0.2%~0.3%，做T几乎必亏，建议至少 2 跳或直接不做。
3. **T+1**：当日买入不可卖 → 反T 只能卖**昨日及更早**的底仓。引擎已自动判（`buy_time` 是今天就降级并提示），但它只知道聚合持仓，混批要手工 `qty_avail`。
4. **涨跌停**：主板 9.8% / 创业板·科创板 19.5% 以上视为锁仓（跌停同理），直接封死——涨停止盈单卖不掉、跌停买不到，做T会变成被动挨打。
5. **VWAP 的时段偏差**：开盘 5 分钟内 VWAP 样本太少、参考性差（9:30-9:35 权重已压到 0.3）；尾盘（14:40 后）VWAP 反而最稳，是反T 回补的最佳窗口。
6. **单边下跌禁低吸**：这是本引擎最强调的一条。`price < VWAP×0.985` 或"放量下跌"一律不做正T——你要买在启动前，不是接飞刀。
7. **`amount` 口径变化闸门**：VWAP 若算出越界（字段单位被上游改过），会自动退回 HLC/3 并在 `warnings` 里标明"可靠性下降"，不会静默给错数。
8. **本引擎不判断趋势方向**：它是**执行层**（怎么把这一次T做好、别亏手续费），方向还得靠你的日K建仓/控盘/题材那套。两者叠加才是完整闭环。

### 4）验证证据（可重跑：`python tools\_verify_intraday_t_engine.py`）

| 组 | 覆盖 | 结果 |
|---|---|---|
| A | 真实行情 5 只：`amount/(volume×100)` 必须落在当日 low~high | 5/5 通过（600519→1268.33 / 300750→295.98 / 000001→11.685 / 601318→52.913 / 002594→83.837） |
| B | 12 个时刻 → 时间窗映射与权重 | 12/12 命中 |
| C | 量价四态 + 边界 | 5/5 |
| D | 成本预估 vs 手算（反T/正T/做反了） | 6/6（新成本 9.9836、费用 35.72、Δ-0.164% 与手算一致） |
| E | 盈亏平衡价差 vs 手算 | 3/3（0.0302 / 0.1252） |
| F | 反T优先 + T+1 阻断 + 无成本降级 | 5/5（100 分条件齐备给反T；今日买入→不给反T并提示） |
| G | 硬闸门：放量下跌 / 破VWAP / 非交易时段 / 涨停锁仓 / 创业板20cm | 5/5 |
| H | 确定性 + 时间外置（10:20=100 分 vs 11:00=95 分） | 4/4 |
| I | 价差≤盈亏平衡 → 不出信号（且反T分本身够 75） | 2/2 |
| J | 引擎依赖仅标准库（无 Qt/网络/DB） | 3/3 |
| K | **真实 10 只 × 2 时段端到端**：字段齐全 20/20、分数合法 20/20；真实触发样本 300750 反T 80 分，独立复算 Δ 成本 = -4838.00 与引擎逐分一致 | 5/5 |
| L | `apply_plan_to_row` 写回（反T→卖点取当前/目标价、硬闸门不出方向） | 4/4 |

### 5）回退

引擎是**新增文件**，没有改动任何现有业务文件：

```
del D:\QuantMonitorV6\strategy\intraday_t_engine.py
del D:\QuantMonitorV6\tools\_verify_intraday_t_engine.py
```

`atr_t_widget.py` 一行未动（2261 行仍原样），所以现在程序行为与升级前完全一致——
要真正生效，需要你点头让我把上面第 2）步的 8 行集成 + 第 3）步那 1 行 bug 修掉接进 widget。
