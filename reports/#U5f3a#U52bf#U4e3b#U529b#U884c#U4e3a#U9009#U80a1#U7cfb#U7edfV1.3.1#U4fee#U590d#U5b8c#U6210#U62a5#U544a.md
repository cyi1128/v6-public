# 强势主力行为选股系统 V1.3.1 修复完成报告

## 通达信检测到股票但扫描全市场=0修复

---

## 一、问题现象

用户实测截图显示：
```
数据源: ✅通达信本地 | K线缓存: 26只/76474根 | 数据日期: 20260819
全市场:0 主板:0 L1基础:0 L2预筛:0 L3深度:0 ... 最终池:0 耗时:0.3s
```

**核心矛盾**：通达信检测到26只股票、76474根K线，但扫描全市场=0，耗时仅0.3秒（扫描根本没处理任何股票）。

---

## 二、根因分析

通过代码审查发现**三个潜在问题**：

### 问题1：文件名大小写敏感（核心根因）

`get_all_main_board_codes()` 中使用 `f.endswith('.day')` 过滤文件，这是**大小写敏感**的。

如果用户通达信目录中存在大写扩展名的文件（如 `SH600001.DAY`），会被直接跳过，导致股票列表不完整。

**修复**：改为 `f.lower().endswith('.day')`，大小写不敏感。

### 问题2：_filter_board 不支持001开头深市主板

`_filter_board()` 只保留 `60` 开头和 `000` 开头的股票，**001开头的深市主板被错误过滤**。

通达信 `get_all_main_board_codes()` 中定义的深市主板前缀包括 `('000', '001')`，但 `_filter_board` 没有同步更新。

**修复**：增加 `001` 开头支持。

### 问题3：缺少调试日志，无法定位问题

步骤2中通达信路径缺少详细的调试输出，无法判断：
- `get_all_main_board_codes()` 返回了多少只
- 预加载是否成功
- `stock_list` 构建了多少只
- 是否有异常被静默吞掉

**修复**：增加完整的调试日志和异常堆栈打印。

---

## 三、修复内容

### 1. `data/tdx_data_engine.py`

#### get_all_main_board_codes() 重构
- 文件名过滤改为大小写不敏感：`f.lower().endswith('.day')`
- 增加健壮的文件名解析：新增 `_extract_code_from_filename()` 静态方法，用正则提取6位数字代码
  - 支持 `sh600000.day`、`SH600001.DAY`、`sz000001.day`、`600002.day` 等多种格式
- 增加详细调试日志：
  ```
  [TDX ENGINE] get_all_main_board_codes: 沪市3个.day文件, 深市3个.day文件, 识别主板5只
  [TDX ENGINE] 前5只: ['000001', '001001', '600000', '600001', '600002']
  ```
- 目录不存在时打印警告
- 扫描异常时打印错误信息
- 返回前去重：`sorted(set(codes))`

#### 新增 _extract_code_from_filename() 静态方法
```python
@staticmethod
def _extract_code_from_filename(filename: str) -> Optional[str]:
    """从.day文件名中提取6位股票代码
    支持格式：sh600000.day, sz000001.day, 600000.day, SH600001.DAY等
    """
    import re
    name = filename.replace('.day', '').replace('.DAY', '')
    match = re.search(r'(\d{6})', name)
    if match:
        return match.group(1)
    return None
```

### 2. `strategy/main_force_behavior.py`

#### 步骤2 通达信路径增加详细调试日志
```python
print(f"[SCAN DEBUG] 步骤2 通达信get_all_main_board_codes返回: {len(tdx_codes)}只")
...
print(f"[SCAN DEBUG] 通达信股票列表构建: K线成功{kline_ok}只, 失败{kline_fail}只, 最终stock_list={len(stock_list)}只")
```

#### 异常处理增加堆栈打印
```python
except Exception as e:
    import traceback
    print(f"[SCAN ERROR] 通达信本地扫描异常: {e}")
    traceback.print_exc()
    print(f"[SCAN] 降级到网络API")
    stock_list = []
```

#### 新增：通达信数据不足100只时自动用网络API补充
```python
if len(stock_list) < 100:
    print(f"[SCAN WARN] 通达信本地只有{len(stock_list)}只股票数据，"
          f"建议在通达信软件中执行「盘后数据下载」下载全部主板数据")
    print(f"[SCAN] 尝试用网络API补充完整主板股票列表...")
    # 调用东方财富获取完整主板列表，合并通达信本地行情数据
    net_stocks = get_cached_main_board_stocks()
    if net_stocks:
        tdx_code_map = {s['code']: s for s in stock_list}
        merged = []
        for ns in net_stocks:
            code = ns.get('code', ns.get('ts_code', ''))
            if code in tdx_code_map:
                merged.append(tdx_code_map[code])  # 用通达信本地行情
            else:
                merged.append(ns)  # 网络补充的股票
        stock_list = merged
        print(f"[SCAN] 网络补充完成: 合并后{len(stock_list)}只主板股票")
```

#### _filter_board() 增加001开头支持
```python
# 主板判断：60开头(沪市主板) 或 000/001开头(深市主板)
if code_clean.startswith('60') or code_clean.startswith('000') or code_clean.startswith('001'):
    main_board.append(stock)
```

---

## 四、修复后扫描流程

```
扫描开始
  ↓
步骤1：数据提供者检查
  ↓
步骤2：获取股票列表
  ├─ 通达信本地可用？
  │   ├─ get_all_main_board_codes() → 扫描.day文件目录（大小写不敏感）
  │   ├─ preload_to_memory() → 8线程预加载K线到内存
  │   ├─ 构建stock_list（从内存K线取最新行情）
  │   ├─ 打印调试日志：K线成功XX只，失败XX只
  │   ├─ stock_list < 100只？→ 自动用东方财富网络API补充完整主板列表
  │   └─ stock_list >= 100只？→ 直接使用通达信本地数据
  ├─ 通达信不可用或失败 → 降级东方财富
  ├─ 东方财富失败 → 降级通达信网络接口
  └─ 都失败 → 打印错误并终止（不再用虚拟列表）
  ↓
步骤3：主板过滤（支持60/000/001开头）
  ↓
L1基础筛选（从行情数据过滤，零网络请求）
  ↓
L2行为预筛（从内存K线读取30日）
  ↓
L3深度分析（从内存K线读取120日+三模型+AI评分）
  ↓
输出股票池
```

---

## 五、验收测试结果

**36项全部通过**

| 测试组 | 项数 | 结果 |
|--------|------|------|
| get_all_main_board_codes健壮文件名解析 | 8 | ✅ 全部通过 |
| _extract_code_from_filename静态方法 | 5 | ✅ 全部通过 |
| _filter_board支持001开头 | 7 | ✅ 全部通过 |
| 步骤2调试日志和异常处理 | 6 | ✅ 全部通过 |
| 少量通达信数据扫描验证（5只） | 7 | ✅ 全部通过 |
| _get_kline_with_fallback通达信优先 | 3 | ✅ 全部通过 |

**关键验证**：
- 大写 `SH600001.DAY` 文件现在能正确识别
- 无前缀 `600002.day` 文件能正确识别
- 001开头深市主板通过 `_filter_board`
- 模拟5只少量数据：主板过滤5只 → L1通过5只（零网络请求）
- 通达信数据不足100只时触发网络API补充逻辑
- 异常时打印完整堆栈，不再静默失败

**用户环境验证**：测试中检测到用户通达信安装在 `C:\new_tdx`，本地数据引擎已启用。

---

## 六、修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `data/tdx_data_engine.py` | **修改** | get_all_main_board_codes大小写不敏感+健壮文件名解析+调试日志 |
| `strategy/main_force_behavior.py` | **修改** | 步骤2调试日志+异常堆栈+通达信数据不足自动网络补充+_filter_board支持001 |
| `test_v1_3_1_fix.py` | **新增** | V1.3.1验收测试脚本（36项） |

---

## 七、未修改的模块（遵守约束）

- ✅ 三个模型逻辑（涨停回调/箱体突破/量价突破）— 未修改
- ✅ AI 六维度评分 — 未修改
- ✅ K 线标注模块 — 未修改
- ✅ 回测模块 — 未修改
- ✅ V1.2.3 缓存系统 — 未修改
- ✅ V1.2.4 DuckDB缓存/腾讯批量行情/启动预加载 — 未修改
- ✅ V1.3 通达信数据引擎核心架构 — 在其基础上修复

---

## 八、用户操作建议

1. **查看控制台日志**：重新扫描时，控制台会打印详细的调试信息：
   ```
   [SCAN DEBUG] 步骤2 通达信get_all_main_board_codes返回: XX只
   [TDX ENGINE] get_all_main_board_codes: 沪市XX个.day文件, 深市XX个.day文件, 识别主板XX只
   [SCAN DEBUG] 通达信股票列表构建: K线成功XX只, 失败XX只, 最终stock_list=XX只
   ```

2. **如果通达信只有少量股票**：程序会自动用东方财富网络API补充完整主板列表，控制台会显示：
   ```
   [SCAN WARN] 通达信本地只有XX只股票数据，建议在通达信软件中执行「盘后数据下载」
   [SCAN] 尝试用网络API补充完整主板股票列表...
   [SCAN] 网络补充完成: 合并后XX只主板股票
   ```

3. **建议下载完整盘后数据**：在通达信软件中执行「系统 → 盘后数据下载」，下载全部沪深主板股票数据，这样可以实现完全零网络扫描。

4. **数据日期检查**：UI显示数据日期，如果不是今日，请在通达信中下载最新数据。
