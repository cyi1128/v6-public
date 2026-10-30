# 策略冻结基线 FROZEN_STRATEGY_BASELINE

> 冻结时间：2026-08-18 | 基线：V6.0-AI-HANDOVER-BASELINE
> 本文件记录当前项目实际生效的策略参数，禁止擅自修改。

---

## 一、技术指标参数（全项目一致）

| 指标 | 参数 | 来源文件 |
|------|------|----------|
| KDJ | N=13, M1=3, M2=3 | strategy/ai_signal_engine.py L38-40, strategy/factor_score.py, strategy/factor_config.py, strategy/chanlun_core.py |
| MACD | FAST=8, SLOW=21, SIGNAL=5 | strategy/ai_signal_engine.py L48-50, strategy/factor_score.py, strategy/factor_config.py, strategy/chanlun_core.py L442, strategy/ai_trade_analyzer.py L61 |
| MA | MA5, MA10, MA20, MA60, MA120 | 全项目 |

## 二、KDJ 信号阈值

| 条件 | 阈值 | 说明 |
|------|------|------|
| J值超跌 | J ≤ -30 | 超跌关注 |
| J值低位 | J < 8 | 低位关注 |
| K值超卖 | K ≤ 15 | 超卖区域 |
| 金叉区域 | K,D ∈ [40, 60] | 金叉信号 |

## 三、MACD 信号阈值

| 条件 | 阈值 | 说明 |
|------|------|------|
| 轴下金叉 | MACD ≤ -0.020 | 绿柱缩短后金叉 |
| 轴上金叉 | MACD ≥ 0.400 | 红柱缩短后再次金叉 |

## 四、因子评分权重

| 维度 | 权重 | 子因子 |
|------|------|--------|
| 技术面 | 40% | CCI + KDJ + MACD + 趋势(MA5/10/20/60) |

## 五、买卖信号清单

### 实际生效（ai_signal_engine.py）
1. 底部吸筹 BUILDUP — 10日内放量下跌跌破MA5，随后在MA5附近横盘≥3天
2. 观察 WATCH — MA20>MA5，MA5向上拐头
3. 买点一成仓 — 前两日跌破MA5，今日收盘价贴合MA5上方0.1-1元
4. 量价观察 — 大阳线突破MA5/MA10/MA20
5. MA5上穿MA20后回踩
6. 主升回踩完整形态
7. KDJ超跌关注
8. KDJ超卖区域
9. KDJ金叉（40-60区域）
10. MACD轴下金叉
11. MACD轴上金叉

### 备用/实验
- 缠论一买/二买/三买
- 五买
- 三倍量
- 横盘筑底
- 锐角
- 一阳穿5/10

## 六、AI 评分体系

- AI买入信号：strategy/ai_buy_signal.py（动态权重已开启，main.py L74）
- 因子评分：strategy/factor_score.py（8因子）
- 决策融合：ai/decision_fusion.py（买卖评分+历史胜率+市场环境）
- 卖出信号：risk/sell_signal_engine.py（23种风险信号）

## 七、数据源

| 源 | 状态 | 用途 |
|----|------|------|
| 东方财富 | 主要 | 行情、涨停、新闻、概念、财务 |
| 通达信 | 生效 | K线、股票列表、实时行情 |
| DuckDB | 生效 | 历史日线（~4GB，外部路径） |
| SQLite | 生效 | 本地缓存（133MB） |
| Tushare/腾讯/AKShare | 备用 | 降级方案 |

---

*禁止修改本文件记录的参数，如需调整必须经用户明确授权并单独提交版本。*
