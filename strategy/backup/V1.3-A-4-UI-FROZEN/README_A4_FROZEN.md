# V1.3-A-4-UI-FROZEN 冻结版本说明

**冻结日期**: 2026-08-15
**版本**: V1.3-A-4-UI-FROZEN
**状态**: 🔒 已冻结，禁止修改核心逻辑

---

## 版本链

```
V1.3-A-3.1-OPT-FROZEN (核心算法冻结)
        │
        ▼
V1.3-A-4-DEV (UI增强开发)
        │
        ├── 字段读取接口              ✅
        ├── 原因卡片组件              ✅
        ├── 涨停原因Tab接入           ✅
        ├── 股票基础信息展示          ✅
        ├── 概念题材展示              ✅
        ├── 新闻标题/来源展示         ✅
        ├── evidence详细依据展示      ✅
        ├── 缓存机制                 ✅
        ├── 多股票压力测试            ✅
        ├── Bug修复(加载/公告)        ✅
        └── UI增强验收                ✅ 通过
```

---

## 冻结文件清单

| 文件 | 说明 | 大小 |
|------|------|------|
| `limit_up_reason_card_FROZEN.py` | 分析+格式化接口，补充概念标签/股票信息/新闻详情 | 18.7KB |
| `reason_card_widget_FROZEN.py` | 卡片UI组件，5大展示模块 | 22.9KB |
| `limit_up_reason_page_FROZEN.py` | 涨停原因Tab页面，信号机制+超时保护+缓存 | 19.3KB |
| `main_window_A4_FROZEN.py` | 主窗口，集成涨停原因Tab | 30.7KB |

---

## 五大展示模块

### 1. 股票基础信息
- 行业、现价、涨幅、换手率、成交额、连板数
- 数据来源：`market.limit_up_center.get_today_limit_up_stocks()`

### 2. 概念题材
- 彩色标签展示所有概念（过滤D级禁止标签+地域标签）
- 数据来源：`service.concept_service.get_stock_concepts()`（东方财富核心题材）
- 过滤规则：`D_LEVEL_TAGS` + `AREA_TAGS`

### 3. 核心依据
- 主营匹配（S/A/B/C级 + 分数）
- 热点强度（来源 + 关联度）
- 公告催化（等级 + 具体标题）
- 新闻催化（**具体标题 + 来源 + 关键词**，不再只是"存在新闻催化"）

### 4. 详细证据链
- 产业关联、市场表现、个股表现、热点关联、风险因素
- 数据来源：engine原始 `evidence_list`

### 5. 评分拆解
- 基础分、题材分、主营分、热点分、公告分、新闻分、连板分
- 总分自动计算

---

## 技术特性

### 数据链路
```
涨停池数据
    ↓
limit_up_reason_page
    ↓
analyze_and_format()  [补充概念标签+股票信息]
    ↓
format_reason_card()  [新增concepts/stock_info/news_detail/evidence_detail]
    ↓
ReasonCardWidget      [5大模块渲染]
    ↓
UI展示
```

### 跨线程通信
- 使用 `pyqtSignal` 信号机制（替代 `QTimer.singleShot`，更可靠）
- 30秒加载超时保护
- 重复加载保护

### 缓存机制
- 概念标签缓存（`concept_service` 内部缓存）
- 新闻资讯缓存（`news_service` 内部缓存）
- 卡片数据缓存（`reason_card_cache`，按股票代码缓存）

---

## 验收结果

### 抽样验证（6只股票，78项检查）
- 通过率：**100%**
- 问题数：**0**

| 类型 | 股票 | 结果 |
|------|------|------|
| 科技 | 中石科技(300684) | ✅ 13/13 |
| 医药 | 澳洋健康(002172) | ✅ 13/13 |
| 消费 | 康盛股份(002418) | ✅ 13/13 |
| 低位首板 | 华森制药(002907) | ✅ 13/13 |
| 连板龙头 | 蓝盾光电(300862) | ✅ 13/13 |
| 华森专项 | 华森制药(002907) | ✅ 13/13 |

### 性能测试（连续10只股票）
- 成功率：10/10 (100%)
- 平均耗时：0.42秒
- 最快：0.00秒（缓存命中）
- 最慢：0.86秒
- 性能评级：✅ 优秀

---

## 冻结后禁止修改

### 🔒 核心算法层（V1.3-A-3.1-OPT-FROZEN已冻结）
- `strategy/limit_up_reason_engine.py`
- `strategy/market_hot_detector.py`
- score评分规则
- A/B/C评级逻辑
- 主营匹配逻辑
- 公告分级逻辑

### 🔒 本版本UI层（V1.3-A-4-UI-FROZEN）
- 五大展示模块结构
- 数据链路接口
- 缓存机制
- 信号通信机制

### 避免出现
- UI需求导致评分变化
- 展示字段反向影响策略
- 热点算法再次漂移

---

## 下一阶段：V1.3-A-4.1-DEV（展示增强分支）

**不要直接修改冻结版，建立新分支开发**

```
V1.3-A-4-UI-FROZEN
          │
          └── V1.3-A-4.1-DEV
```

### 计划新增（仅展示层，不参与评分）

#### ① 涨停强度模块
- 连板高度、封单金额、首次涨停时间、炸板次数
- 封板质量星级评定

#### ② AI辅助总结卡
- 上涨逻辑★★★★☆ / 持续性★★★☆☆ / 资金认可★★★★☆ / 风险★★★☆☆
- 文字总结（仅解释，不参与评分）

#### ③ 排序能力
- 综合评分、热点强度、连板高度、主营匹配、公告催化排序
- 快速识别龙头/中军/跟风

---

## 版本评价

从架构看，本版本完成一次重要升级：

**以前**：涨停 → 猜概念 → 简单原因

**现在**：
```
涨停事实
    ↓
涨停池资金验证(P0)
    ↓
行业/概念映射
    ↓
主营真实性验证
    ↓
公告/新闻催化
    ↓
证据链展示
    ↓
A/B/C可信度
    ↓
UI解释
```

已从"涨停展示工具"升级为"涨停逻辑分析系统"。

---

## 恢复方法

如需恢复到此版本：
```bash
# 复制回原位置
copy strategy\backup\V1.3-A-4-UI-FROZEN\limit_up_reason_card_FROZEN.py ui\limit_up_reason_card.py
copy strategy\backup\V1.3-A-4-UI-FROZEN\reason_card_widget_FROZEN.py ui\widgets\reason_card_widget.py
copy strategy\backup\V1.3-A-4-UI-FROZEN\limit_up_reason_page_FROZEN.py ui\pages\limit_up_reason_page.py
copy strategy\backup\V1.3-A-4-UI-FROZEN\main_window_A4_FROZEN.py ui\main_window.py
```

---

**冻结标记**: 🔒 V1.3-A-4-UI-FROZEN - 2026-08-15
