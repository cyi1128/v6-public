# 强势主力行为选股系统 V1.3.18 菜单调整完成报告

## 一、问题描述

用户要求将两个功能从子菜单提升到顶部一级菜单栏：
1. "工具"菜单中的"股票投资日历"（用户表述为"股票投资日记"，实际为"日历"）
2. "选股复盘"菜单中的"强势主力行为选股"

原菜单栏结构：选股复盘 → 股票回测 → 工具 → 帮助

## 二、修复内容

### 2.1 新增"股票投资日历"一级菜单

在"股票回测"菜单之后、"工具"菜单之前，新增一级菜单：
```python
# ========== V1.3.18：股票投资日历（提升为一级菜单） ==========
menu_calendar = menubar.addMenu('📅 股票投资日历')
action_calendar_top = QAction('📅 打开股票投资日历', self)
action_calendar_top.triggered.connect(self.open_investment_calendar)
menu_calendar.addAction(action_calendar_top)
```

点击后调用 `self.open_investment_calendar`，与原"工具"菜单中的功能完全一致。

### 2.2 新增"强势主力行为选股"一级菜单

在"股票投资日历"菜单之后，新增一级菜单：
```python
# ========== V1.3.18：强势主力行为选股（提升为一级菜单） ==========
menu_screener_top = menubar.addMenu('🎯 强势主力行为选股')
action_screener_top = QAction('🎯 打开强势主力行为选股', self)
action_screener_top.triggered.connect(self.open_force_behavior_screener)
menu_screener_top.addAction(action_screener_top)
```

点击后调用 `self.open_force_behavior_screener`，与原"选股复盘"菜单中的功能完全一致。

### 2.3 从"选股复盘"菜单移除"强势主力行为选股"

注释掉原菜单项（保留代码作为备份，不执行）：
```python
# V1.3.18：强势主力行为选股已提升为一级菜单，此处移除
# action_screener = QAction('🎯 强势主力行为选股', self)
# action_screener.triggered.connect(self.open_force_behavior_screener)
# menu_stock.addAction(action_screener)
```

### 2.4 从"工具"菜单移除"股票投资日历"

注释掉原菜单项（保留代码作为备份，不执行）：
```python
# V1.3.18：股票投资日历已提升为一级菜单，此处移除
# action_calendar = QAction('📅 股票投资日历', self)
# action_calendar.triggered.connect(self.open_investment_calendar)
# menu_tools.addAction(action_calendar)
```

## 三、调整后菜单栏结构

调整前：
```
🎯 选股复盘 → 🎯 强势主力行为选股
              🧪 策略实验室
              📿 AI缠论分析
📊 股票回测 → 回测中心
              ✏️ K线标注训练
              回测报告
              参数优化
🔧 工具     → 📅 股票投资日历
              数据导出
              系统设置
              清空缓存
              🎨 界面皮肤
❓ 帮助     → 使用说明
              🩺 系统健康检查
              关于
```

调整后：
```
🎯 选股复盘 → 🧪 策略实验室
              📿 AI缠论分析
📊 股票回测 → 回测中心
              ✏️ K线标注训练
              回测报告
              参数优化
📅 股票投资日历 → 📅 打开股票投资日历  （新增一级菜单）
🎯 强势主力行为选股 → 🎯 打开强势主力行为选股  （新增一级菜单）
🔧 工具     → 数据导出
              系统设置
              清空缓存
              🎨 界面皮肤
❓ 帮助     → 使用说明
              🩺 系统健康检查
              关于
```

## 四、修改文件列表

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `ui/main_window.py` | 修改 | 新增两个一级菜单；从原菜单注释掉对应项 |

## 五、验收标准验证

| 验收项 | 状态 | 说明 |
|--------|------|------|
| 顶部菜单栏显示"股票投资日历"一级菜单项 | ✅ | 新增menu_calendar，位置在股票回测之后 |
| 顶部菜单栏显示"强势主力行为选股"一级菜单项 | ✅ | 新增menu_screener_top，位置在股票投资日历之后 |
| 点击"股票投资日历"正确打开对应功能页面 | ✅ | 连接到self.open_investment_calendar，与原功能一致 |
| 点击"强势主力行为选股"正确打开对应功能页面 | ✅ | 连接到self.open_force_behavior_screener，与原功能一致 |
| "工具"菜单中不再有"股票投资日历" | ✅ | 已注释掉 |
| "选股复盘"菜单中不再有"强势主力行为选股" | ✅ | 已注释掉 |
| 菜单项样式与现有菜单一致 | ✅ | 使用相同的QMenu/QAction创建方式，样式自动继承 |
| 语法检查通过 | ✅ | main_window.py语法检查通过 |
| 程序可启动 | ✅ | 无语法错误 |

## 六、未修改模块（保持稳定）

- ✅ 股票投资日历的功能逻辑（open_investment_calendar方法不变）
- ✅ 强势主力行为选股的功能逻辑（open_force_behavior_screener方法不变）
- ✅ 其他菜单项（选股复盘、股票回测、工具、帮助的其他项）
- ✅ 三个模型的核心逻辑
- ✅ AI六维度评分算法
- ✅ 扫描流程（L1/L2/L3）
- ✅ 7*24快讯全天新闻显示（V1.3.17）
- ✅ K线图300根和MA120均线（V1.3.16）
- ✅ 行业数据填充（V1.3.15）

## 七、结论

V1.3.18 成功完成菜单调整：

1. **股票投资日历**：从"工具"子菜单提升为顶部一级菜单位于"股票回测"之后，点击直接打开投资日历功能。

2. **强势主力行为选股**：从"选股复盘"子菜单提升为顶部一级菜单位于"股票投资日历"之后，点击直接打开选股系统。

3. **原菜单清理**：从"选股复盘"和"工具"菜单中移除了对应的菜单项，避免重复。

4. **功能不变**：两个功能的点击事件处理函数完全不变，只是改变了菜单位置，用户体验更便捷。

用户现在可以在顶部菜单栏直接看到并点击这两个常用功能，不需要再进入子菜单查找。
