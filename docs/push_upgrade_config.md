# V2.7.1 企业微信推送全维度增量升级 — 配置说明文档

## 概述

本次升级采用**只新增不破坏**原则：所有新增功能独立封装，通过配置开关控制（默认全部关闭），100%兼容原有推送入口与业务逻辑。启用任何功能不会影响选股主流程运行。

## 文件结构

```
D:\QuantMonitorV6\
├── config\
│   └── market_analysis_config.py      # 统一配置文件（所有开关/阈值/时间）
├── market_analysis\                    # 市场分析独立包（6个模块）
│   ├── __init__.py
│   ├── auction_strength.py             # 模块1：竞价强度
│   ├── sector_strength.py              # 模块2：板块强度评级
│   ├── deep_fund_flow.py               # 模块3：个股深度资金面
│   ├── market_sentiment.py             # 模块4：实时市场情绪
│   ├── sector_anomaly.py               # 模块5：板块异动监控
│   └── policy_matcher.py               # 任务二：政策与事件驱动匹配
├── timed_report\                        # 定时简报模块
│   └── __init__.py                     # 盘前/盘中/盘后三阶段简报生成器
├── services\
│   └── wechat_push.py                  # 推送层（新增扩展函数，原有函数未修改）
└── docs\
    └── push_upgrade_config.md          # 本文档
```

## 配置开关总览

所有开关位于 `config/market_analysis_config.py`，默认全部关闭。

### 总开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_MARKET_ANALYSIS` | `False` | 市场分析总开关，关闭时所有子模块均不执行 |

### 推送扩展总开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PUSH_EXTENSION_CONFIG.enabled` | `False` | 推送扩展总开关，关闭时个股推送使用原有模板 |

### 个股推送嵌入字段开关

| 配置项 | 默认值 | 说明 | 调整建议 |
|--------|--------|------|----------|
| `embed_auction_strength` | `False` | 嵌入竞价强度 | 早盘9:30-10:00开启效果最佳 |
| `embed_sector_strength` | `False` | 嵌入板块强度评级 | 建议开启，增加板块维度 |
| `embed_deep_fund_flow` | `False` | 嵌入深度资金面（含龙虎榜/北向） | 建议开启，资金面重要 |
| `embed_market_sentiment` | `False` | 推送末尾嵌入市场情绪 | 建议开启，全局视角 |
| `embed_policy_catalyst` | `False` | 嵌入政策催化 | 政策密集期开启 |

### 独立推送开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `sector_anomaly_push` | `False` | 板块异动独立推送（不占用个股通道） |
| `timed_report_push` | `False` | 定时简报推送（盘前/盘中/盘后） |

## 各模块详细配置

### 模块1：竞价强度 `AUCTION_STRENGTH_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 模块开关 |
| `data_source` | `pytdx` | 数据源：pytdx / akshare |
| `auction_volume_ratio_threshold` | `3.0` | 竞价量比≥此值标注"主力抢筹" |
| `virtual_rally_pct` | `2.0` | 高开≥此值但无量标注"无量虚拉" |
| `timeout` | `3` | 接口超时秒数 |
| `retry` | `1` | 失败重试次数 |

**强度评级**：极强（量比≥3+高开>1%+委比≥1.5）/ 强（量比≥2+高开>0）/ 中性（量比0.8-1.5）/ 弱（量比<0.8+下跌）/ 虚拉（高开≥2%+无量）

### 模块2：板块强度 `SECTOR_STRENGTH_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 模块开关 |
| `weights.sector_pct` | `30` | 板块涨跌幅权重（%） |
| `weights.advance_decline` | `20` | 涨跌家数比权重（%） |
| `weights.limit_up_count` | `20` | 涨停家数权重（%） |
| `weights.main_net_inflow` | `20` | 主力净流入权重（%） |
| `weights.ma20_trend` | `10` | MA20趋势权重（%） |
| `grade_thresholds.S` | `90` | S级阈值（≥90分） |
| `grade_thresholds.A` | `80` | A级阈值 |
| `grade_thresholds.B` | `70` | B级阈值 |
| `grade_thresholds.C` | `60` | C级阈值（<60为D） |

### 模块3：深度资金面 `DEEP_FUND_FLOW_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 模块开关 |
| `show_dragon_tiger` | `True` | 龙虎榜数据（未上榜自动隐藏） |
| `show_northbound` | `True` | 北向资金（无数据自动隐藏） |
| `northbound_days` | `3` | 北向资金近N日持仓变化 |

### 模块4：市场情绪 `MARKET_SENTIMENT_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 模块开关 |
| `update_interval` | `3600` | 更新间隔（秒），默认每小时 |
| `sentiment_levels.big_profit.advance_ratio` | `0.7` | 大赚：涨跌比≥70% |
| `sentiment_levels.big_profit.limit_up` | `50` | 大赚：涨停≥50家 |

**情绪定级**：大赚/小赚/平衡/小亏/大亏（对应标签：极强/偏强/中性/偏弱/极弱）

### 模块5：板块异动 `SECTOR_ANOMALY_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 模块开关 |
| `surge_threshold` | `1.5` | 5分钟涨幅≥此值触发拉升异动（%） |
| `drop_threshold` | `1.5` | 5分钟跌幅≥此值触发跳水异动（%） |
| `check_interval` | `300` | 检查间隔（秒），默认5分钟 |
| `dedup_minutes` | `30` | 同一板块N分钟内不重复推送 |
| `independent_push` | `True` | 独立推送不占用个股信号通道 |

### 任务二：政策匹配 `POLICY_MATCHER_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 模块开关 |
| `data_source` | `akshare` | 数据源：akshare / eastmoney / local |
| `match_industries` | `True` | 匹配持仓/信号股所属行业 |
| `cache_hours` | `6` | 政策新闻缓存小时数 |

### 任务三：定时简报 `TIMED_REPORT_CONFIG`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `False` | 定时简报总开关 |
| `premarket.enabled` | `False` | 盘前策略简报开关 |
| `premarket.time` | `08:50` | 盘前简报时间 |
| `intraday.enabled` | `False` | 盘中动态简报开关 |
| `intraday.times` | `['10:30','14:00']` | 盘中简报时间点 |
| `postmarket.enabled` | `False` | 盘后总结报告开关 |
| `postmarket.time` | `15:30` | 盘后报告时间 |
| `postmarket.prefer_image` | `True` | 优先生成PNG图片推送 |
| `postmarket.image_fallback` | `True` | 图片失败自动降级Markdown |

## 完整推送模板（含所有新增字段）

```markdown
### 【AI-520 选股信号】 🟢 **{名称}({代码}) {分数}分 {等级}级** 【{状态}】

> **价格：<font color="info">{现价} ({涨跌幅}%)</font>** ｜ 行业：{行业}
> MA5: {MA5} ｜ MA20: {MA20}({趋势}) ｜ 金叉: {N}天前
> 量比: {量比} ｜ 年涨停: {N}次 ｜ 距高点: {N}%

---

📊 **历史回测**：近2年同类信号 {N} 次，持股5日胜率 {N}%，平均收益 {N}%

💰 **资金面**：主力净流入 {N} 万

📂 **板块**：{板块异动数据}

📌 **异动原因**：{异动原因}

---
<!-- 以下为新增字段（按竞价→板块→资金→政策顺序，开关控制） -->

⏰竞价强度：竞价量比{N} 高开{N}% 放量承接 评级【{强}】

📂板块强度：{板块名}板块评级{B+} 日内排名{N}/{N} 连续{N}日领涨 主力净流入{N}亿

💰资金面：主力净流入{N}万 占成交额{N}% 🏛️龙虎榜：机构净买入{N}万 北向资金增持{N}%

📰政策催化：{政策标题} {行业}板块直接受益 该股为{区域龙头}

---
<!-- 以上为新增字段 -->

🎯 **买点**：{买入区间} 元
🛑 **止损**：{止损价} 元
🎯 **目标**：{目标区间} 元
⚖️ **建议仓位**：{仓位建议}

---
<!-- 推送末尾市场情绪（开关控制） -->

😀市场情绪：涨跌比{N}:{N} 涨停{N}家 连板{N}板 炸板率{N}% 情绪【偏强】 💸量能：半日成交{N}亿 较昨日同期+{N}%
```

## 快速启用指南

### 最小启用（仅个股推送增加板块+资金面）

```python
# config/market_analysis_config.py
ENABLE_MARKET_ANALYSIS = True
PUSH_EXTENSION_CONFIG['enabled'] = True
PUSH_EXTENSION_CONFIG['embed_sector_strength'] = True
PUSH_EXTENSION_CONFIG['embed_deep_fund_flow'] = True
SECTOR_STRENGTH_CONFIG['enabled'] = True
DEEP_FUND_FLOW_CONFIG['enabled'] = True
```

### 全功能启用

```python
ENABLE_MARKET_ANALYSIS = True
PUSH_EXTENSION_CONFIG['enabled'] = True
for key in ['embed_auction_strength', 'embed_sector_strength',
            'embed_deep_fund_flow', 'embed_market_sentiment',
            'embed_policy_catalyst', 'sector_anomaly_push', 'timed_report_push']:
    PUSH_EXTENSION_CONFIG[key] = True
AUCTION_STRENGTH_CONFIG['enabled'] = True
SECTOR_STRENGTH_CONFIG['enabled'] = True
DEEP_FUND_FLOW_CONFIG['enabled'] = True
MARKET_SENTIMENT_CONFIG['enabled'] = True
SECTOR_ANOMALY_CONFIG['enabled'] = True
POLICY_MATCHER_CONFIG['enabled'] = True
TIMED_REPORT_CONFIG['enabled'] = True
TIMED_REPORT_CONFIG['premarket']['enabled'] = True
TIMED_REPORT_CONFIG['intraday']['enabled'] = True
TIMED_REPORT_CONFIG['postmarket']['enabled'] = True
```

## 测试方法

### 1. 模块导入测试

```bash
cd D:\QuantMonitorV6
python -c "from market_analysis.auction_strength import analyze_auction; print('OK')"
python -c "from market_analysis.sector_strength import analyze_sector; print('OK')"
python -c "from market_analysis.deep_fund_flow import analyze_deep_fund; print('OK')"
python -c "from market_analysis.market_sentiment import analyze_sentiment; print('OK')"
python -c "from market_analysis.sector_anomaly import check_sector_anomaly; print('OK')"
python -c "from market_analysis.policy_matcher import match_policy_for_stock; print('OK')"
python -c "from timed_report import get_report_generator; print('OK')"
python -c "from services.wechat_push import format_enhanced_signal_markdown, push_sector_anomaly, push_timed_report; print('OK')"
```

### 2. 增强推送模板测试（不实际发送）

```bash
python tools/test_push_extension.py
```

### 3. 实际推送测试

```bash
# 测试个股增强推送（需配置webhook）
python -c "
from services.wechat_push import format_enhanced_signal_markdown, get_wechat_push_service
signal = {'code':'000001','name':'平安银行','total_score':75,'grade':'B','price':11.5,'pct_chg':1.2,'industry':'银行'}
md = format_enhanced_signal_markdown(signal)
print(md)
get_wechat_push_service()._send_markdown(md)
"

# 测试板块异动推送
python -c "
from services.wechat_push import push_sector_anomaly
anomaly = [{'sector_name':'半导体','type':'surge','pct_change':2.1,'formatted_text':'🚨板块异动：半导体板块5分钟拉升2.1%'}]
push_sector_anomaly(anomaly)
"

# 测试盘后报告推送
python -c "
from timed_report import get_report_generator
from services.wechat_push import push_timed_report
report = get_report_generator().generate_postmarket_report()
if report: push_timed_report(report)
"
```

### 4. 异常兜底测试

```bash
# 模拟模块异常（断开网络），验证自动降级为原有推送
python -c "
from services.wechat_push import format_enhanced_signal_markdown
signal = {'code':'000001','name':'测试','total_score':60}
md = format_enhanced_signal_markdown(signal)
assert 'AI-520' in md  # 降级后仍有基础推送
print('降级测试通过')
"
```

## 设计原则

1. **只新增不破坏**：原有`format_signal_markdown`/`push_text`等函数未修改一行代码
2. **配置开关默认关闭**：所有新功能需显式启用，不影响现有运行
3. **异常自动降级**：任何新增模块异常时，自动回退到原有推送逻辑
4. **数据缺失自动隐藏**：无龙虎榜/北向/政策数据时，对应字段不显示
5. **长度校验复用**：所有新增内容自动计入原有`check_content_length`校验
6. **独立日志**：每个模块独立记录日志、计算耗时、推送状态、异常信息
7. **不弹窗不中断**：所有错误仅记录日志，不影响主程序运行
8. **后台线程**：数据计算在独立后台线程，不阻塞选股主流程
