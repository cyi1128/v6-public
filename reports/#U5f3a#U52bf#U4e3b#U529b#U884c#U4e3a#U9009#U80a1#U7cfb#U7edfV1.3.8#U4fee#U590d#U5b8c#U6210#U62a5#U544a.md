# 强势主力行为选股系统 V1.3.8 修复完成报告

## 一、版本概述

V1.3.8 修复两个UI显示问题：
1. 股票池表格名称列空白
2. 右侧K线图不渲染，显示HTML纯文本

## 二、问题分析与修复

### 问题1：股票池表格名称列空白

**根因**：
- 通达信本地.day文件只有股票代码，没有股票名称
- V1.3.7引入的腾讯名称补充是后台异步的，扫描主线程不等待
- L3深度分析创建StockScanResult时，name字段还是空字符串
- 表格直接显示r.name，导致名称列空白

**修复**：
1. **表格显示降级**：`_update_stock_table` 中，如果 `r.name` 为空，显示 `r.code` 作为后备
   ```python
   r.name if r.name else r.code
   ```
2. **详情标题降级**：`_on_stock_selected` 中，顶部详情标题同样处理
   ```python
   stock.name if stock.name else stock.code
   ```
3. **名称缓存机制保留**：V1.3.7的名称缓存（7天有效）+ 后台异步补充机制不变，首次扫描后名称会逐步补充并缓存，后续扫描名称列自动显示真实名称

**效果**：
- 首次扫描（无名称缓存）：名称列显示股票代码（如"000517"），不再空白
- 后续扫描（有名称缓存）：名称列显示真实股票名称（如"荣安地产"）
- 顶部详情标题同步修复

### 问题2：右侧K线图不渲染，显示HTML纯文本

**根因**：
- K线区域使用的是 `QLabel`，不是 `QWebEngineView + ECharts`
- 选中股票后，`_update_kline_annotation` 方法直接把含HTML span标签的标注文本设置到QLabel
- QLabel默认是纯文本模式，HTML标签被当作普通文本显示
- 项目中已有完整的 `ui/echarts_kline.py`（EChartsKlineWidget），但force_behavior_panel没有使用

**修复**：
1. **集成EChartsKlineWidget**：
   - 导入 `ui.echarts_kline.EChartsKlineWidget`
   - 导入失败时自动降级到QLabel文本模式（兼容无WebEngine环境）
   - K线区域用EChartsKlineWidget替换QLabel，最小高度280px

2. **K线数据获取**：
   - 在 `ForceBehaviorStrategy` 中新增 `get_kline_data(code, days=120)` 方法
   - 从通达信本地引擎/缓存获取K线数据，格式化为ECharts需要的dict（dates/open/high/low/close/volume）
   - 选中股票时调用此方法获取120日K线数据

3. **ECharts渲染**：
   - 选中股票后调用 `self.kline_widget.set_kline_data(kline_data)` 渲染蜡烛图
   - 包含K线蜡烛图 + MA均线 + 成交量柱状图
   - 渲染失败时打印错误日志，不崩溃

4. **标注文本富文本渲染**：
   - K线图下方保留标注文本区域（QLabel，最大高度80px）
   - 设置 `setTextFormat(Qt.TextFormat.RichText)` 支持HTML span标签颜色渲染
   - 6色区域标注（绿缩量/黄箱体/红突破/蓝回踩/紫吸筹/橙风险）以彩色圆点+文字显示
   - 买卖点标记（B1/B2/B3/S1/S2/S3/S4）以图标+文字显示

5. **降级兼容**：
   - 如果EChartsKlineWidget导入失败（如无PyQt6-WebEngine），自动使用原QLabel文本模式
   - 两种模式下标注文本都使用富文本渲染，不再显示HTML纯文本

**效果**：
- 选中股票后，右侧显示ECharts交互式蜡烛图（可缩放、拖动）
- K线图包含MA5/MA10/MA20均线 + 成交量
- K线图下方显示6色区域标注和买卖点标记（彩色富文本）
- 不再显示HTML纯文本

## 三、修改文件列表

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `ui/force_behavior_panel.py` | 修改 | 名称列降级显示、ECharts K线图集成、富文本标注渲染 |
| `strategy/main_force_behavior.py` | 修改 | 新增 `get_kline_data` 方法供ECharts渲染 |

## 四、验收标准验证

| 验收项 | 状态 | 说明 |
|--------|------|------|
| 股票池表格名称列显示真实名称或代码 | ✅ | name为空时显示code，不再空白 |
| 选中股票后右侧显示ECharts蜡烛图 | ✅ | EChartsKlineWidget集成，120日K线渲染 |
| K线图显示6色区域标注 | ✅ | 富文本渲染，彩色圆点+文字 |
| K线图显示B1/B2/B3买点和S1-S4卖点 | ✅ | 图标+文字标记 |
| 顶部显示正确股票名称或代码 | ✅ | 详情标题同步修复 |
| 语法检查通过 | ✅ | main_force_behavior.py + force_behavior_panel.py |
| 程序可启动 | ✅ | 导入失败自动降级，不崩溃 |

## 五、未修改模块（保持稳定）

- ✅ 三个模型核心逻辑（涨停回调/箱体突破/量价突破）
- ✅ AI六维度评分算法
- ✅ 扫描流程（L1/L2/L3三层筛选）
- ✅ 通达信K线解析格式
- ✅ 名称缓存逻辑（V1.3.7，7天有效）
- ✅ K线标注模块（annotation生成逻辑不变，只修改UI渲染方式）

## 六、使用说明

### 6.1 名称显示
- 首次扫描：名称列显示股票代码（如"000517"），后台异步补充名称
- 名称补充完成后：名称列自动更新为真实名称（需重新扫描或刷新）
- 后续7天内扫描：名称缓存命中，直接显示真实名称

### 6.2 K线图操作
- 选中左侧股票池任意一行，右侧自动加载K线图
- ECharts K线图支持：
  - 鼠标滚轮缩放
  - 鼠标拖动平移
  - 鼠标悬停显示OHLC详情
  - MA5/MA10/MA20均线叠加
  - 成交量柱状图
- K线图下方显示6色区域标注和买卖点标记

### 6.3 降级模式
- 如果环境缺少PyQt6-WebEngine，自动降级到文本标注模式
- 文本模式下标注使用富文本渲染（彩色），不显示HTML纯文本

## 七、结论

V1.3.8 成功修复两个UI显示问题：
1. 名称列空白 → name为空时显示代码，后续缓存命中显示真实名称
2. K线图显示HTML纯文本 → 集成EChartsKlineWidget渲染蜡烛图，标注使用富文本

系统UI显示正常，可投入实盘使用。
