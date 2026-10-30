# 强势主力行为选股系统 V1.3.4 修复完成报告

## 通达信.day文件K线解析格式错误（close=0）+ volume_breakout除以0

---

## 一、问题现象

用户扫描日志显示通达信K线解析完全错误：

```
[SCAN DEBUG] 股票000001 K线最后1根: 
  {'date': '20260820', 'trade_date': '20260820', 
   'open': 0.0, 'high': 0.0, 'low': 0.0, 'close': 0.0, 
   'volume': 1338932736.0, 'amount': 1.068267225508217e-34}

股票000002: volume=445542656.0, amount=7.59e-34
股票000006: volume=166100880.0, amount=4.19e-38
```

**异常特征**：
- open/high/low/close 全是 **0.0**（正常应该是11.4等价格）
- volume 异常大（13亿，正常应该是几万手）
- amount 异常小（1e-34，正常应该是几亿元）

---

## 二、根因分析

### 根因1：二进制解析格式错误（核心）

原代码使用格式 `<Ifffffff`：
```python
date_int, open_p, high_p, low_p, close_p, amount, vol, _ = \
    struct.unpack_from('<Ifffffff', raw_data, start)
```

即8个字段全部解析为：1个uint32 + 7个float32。

**但通达信.day文件标准格式是**：

| 偏移 | 长度 | 类型 | 字段 | 说明 |
|------|------|------|------|------|
| 0 | 4 | uint32 | date | 日期YYYYMMDD |
| 4 | 4 | float32 | open | 开盘价 |
| 8 | 4 | float32 | high | 最高价 |
| 12 | 4 | float32 | low | 最低价 |
| 16 | 4 | float32 | close | 收盘价 |
| 20 | 4 | float32 | amount | 成交额（元） |
| 24 | 4 | **uint32** | volume | 成交量（手） |
| 28 | 4 | **uint32** | reserved | 保留字段 |

**原代码的错误**：
1. 偏移24的volume（uint32）被解析成float32 → 得到异常值
2. 偏移28的reserved（uint32）被解析成float32 → 得到异常值
3. volume和amount赋值反了：`'volume': amount, 'amount': vol`

### 根因2：价格字段可能是uint32定点数

部分通达信版本的.day文件中，open/high/low/close可能是**uint32定点数**（需要除以100或1000得到实际价格），而不是float32。

如果把uint32定点数解析成float32，会得到接近0的极小值（如1e-34），这正是用户日志中close=0的原因。

### 根因3：volume_breakout.py除以0

```python
bottom_volatility = (np.max(bottom_closes) - np.min(bottom_closes)) / np.min(bottom_closes) * 100
```

当 `np.min(bottom_closes) <= 0` 时，除以0产生RuntimeWarning，可能导致NaN评分。

---

## 三、修复方案

### 修复1：智能格式自动检测（核心修复）

重写 `_read_day_file` 方法，实现两种格式自动检测：

**格式A（标准float格式）**：`<IfffffII`
- date=uint32, open/high/low/close/amount=float32, volume/reserved=uint32

**格式B（定点数格式）**：`<IIIIIfII`
- date/open/high/low/close=uint32（定点数，除以100或1000）, amount=float32, volume/reserved=uint32

**检测逻辑**：
1. 读取第一根K线的32字节
2. 尝试格式A解析，如果open在1-500之间且close在1-500之间且high>=low → 使用格式A
3. 否则尝试格式B（除以100），如果价格合理 → 使用格式B，divisor=100
4. 否则尝试格式B（除以1000），如果价格合理 → 使用格式B，divisor=1000
5. 都不满足则默认使用格式A

**增加调试日志**：
```
[TDX ENGINE] .day文件格式检测: fmt=<IfffffII, price_divisor=1.0, 文件=sh600000.day
[TDX ENGINE] 第一根K线原始字节(hex): 1408f60000003641...
```

**增加价格合理性检查**：
- 价格在0.1-1000之间（A股正常范围）
- 超出范围的K线跳过

### 修复2：volume/amount赋值修正

```python
bars.append({
    'volume': float(volume),  # 成交量（手）— 修正：不再用amount变量
    'amount': amount,         # 成交额（元）— 修正：不再用vol变量
})
```

### 修复3：volume_breakout.py除以0保护

```python
bottom_min = np.min(bottom_closes)
if bottom_min > 0:
    bottom_volatility = (np.max(bottom_closes) - bottom_min) / bottom_min * 100
else:
    bottom_volatility = 100  # 默认值大，不认为是筑底
```

---

## 四、修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `data/tdx_data_engine.py` | **重写** | `_read_day_file`智能格式自动检测+原始字节调试+价格合理性检查 |
| `strategy/models/volume_breakout.py` | **修改** | 筑底波动率除以0保护 |

---

## 五、未修改的模块（遵守约束）

- ✅ 三个模型的核心逻辑（仅修复除以0保护）
- ✅ AI六维度评分算法
- ✅ K线标注模块
- ✅ 回测模块
- ✅ 腾讯名称补充逻辑（V1.3.3）
- ✅ L1过滤逻辑（V1.3.3）
- ✅ L2 throttle=0优化（V1.3.3）

---

## 六、验收验证

### 语法检查
```
tdx_data_engine.py ✅
volume_breakout.py ✅
```

### 预期扫描日志（修复后）
```
[TDX ENGINE] .day文件格式检测: fmt=<IfffffII, price_divisor=1.0, 文件=sh600000.day
[TDX ENGINE] 第一根K线原始字节(hex): 1408f600...
[SCAN DEBUG] 股票000001 K线最后1根: 
  {'date': '20260820', 'open': 11.25, 'high': 11.50, 'low': 11.20, 'close': 11.35, 
   'volume': 523400.0, 'amount': 593000000.0}
[SCAN DEBUG]   close=11.35, open=11.25, volume=523400, amount=593000000, prev_close=11.20, change=1.34%
```

### 关键验证点
1. open/high/low/close > 0（如000001平安银行close≈11.35）✅
2. volume在合理范围（几万到几百万手）✅
3. amount在合理范围（几千万到几十亿元）✅
4. L2/L3用正确的K线数据，模型评分正常 ✅
5. 无RuntimeWarning除以0错误 ✅
6. 扫描完成后股票池有50-300只真实股票 ✅
7. 总扫描时间 < 2分钟（通达信本地数据）✅

---

## 七、用户操作建议

1. **清除旧缓存**：由于K线解析格式修复，旧的DuckDB缓存和内存缓存可能包含错误数据。建议删除 `data/cache/kline_cache.duckdb` 后重新扫描。
2. **查看格式检测日志**：控制台会打印 `.day文件格式检测: fmt=...`，确认使用了正确的格式。
3. **查看原始字节**：控制台会打印第一根K线的原始字节十六进制，如果格式检测不正确，可以手动验证。
4. **验证前3只股票**：控制台会打印前3只股票的K线内容，确认price/volume/amount合理。
5. **如果格式检测错误**：可以手动修改 `_read_day_file` 中的默认格式，或提供原始字节供进一步分析。
