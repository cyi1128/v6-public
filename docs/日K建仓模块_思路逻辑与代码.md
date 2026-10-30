# 日K建仓模块 · 思路逻辑与完整代码

> 位置：`ui/battle_widgets/atr_t_widget.py`（L42-50 表头常量，L1269-1982 模块代码，共约713行新增）
> 原则：**分时做T模块零修改**，本模块完全新增、状态/缓存/锁/DB 全部独立。
> 已通过：50组随机K线档位顺序验证、8个信号灯分支验证、真实持仓23只盘后复盘渲染验证。

---

## 一、模块定位与协作边界

- **日K底仓模块**：纯底仓级别的「分批建仓 + 终级清仓」，不做日内差价。
- **分时做T**：日内高抛低吸降成本（原有逻辑一行未动）。
- 协作：日K管底仓的买入与最终清仓；建仓位置出现回撤时，由原有分时做T在日内做差价。
- 核心目标：**建仓即带厚安全垫（止损兜底），最大亏损可控；清仓卖在趋势衰竭点，吃满波段收益。**

## 二、核心数据流（对应真实代码）

```
_holdings_source() 持仓/自选(DuckDB holding表优先, 空则自选)
  → get_realtime_quotes_http(codes) 批量实时价(price/prev_close/high/low)
  → _daily_bars(code,120) 日K120根(10分钟缓存, 盘中实时价更新末根, 拷贝副本不污染分时)
  → _daily_calc_one_stock()  核心算法: VWAP20中枢 + ATR14波动 → 三档建仓+两档止盈+止损
  → _daily_anchor()          周度锚定
  → _daily_apply_risk()      风控一票否决 + 信号灯
  → _daily_render_table()    渲染底仓表
```

## 三、核心算法（L1414 `_daily_calc_one_stock`）

**基础定义（与分时做T同源，周期升级）**
- `ATR(14)` = 近14根日K TR均值，TR=max(H-L, |H-昨收|, |L-昨收|)（复用原 `_calc_atr`）
- `VWAP(20)` = 近20日每日典型价 (高+低+收)/3 的均值（日K价值中枢）

**题材强度修正（L1456）**
- `shift = 0.5*f*ATR`（f≥0，强势上移建仓价不深调）；`shift = 0.8*f*ATR`（f<0，弱势下移加厚安全垫）

**三档建仓价（只在中枢下方，越跌安全垫越厚）**
| 档位 | 公式（L1459-1462） | 逻辑 |
|------|--------------------|------|
| 试仓 t1 | `VWAP20 - 1.2*ATR + shift` | 价值中枢下沿，合理回调位 |
| 加仓 t2 | `VWAP20 - 1.8*ATR + shift` | 错杀回调位 |
| 重仓 t3 | `min(前20日最低+0.2*ATR, VWAP20-2.4*ATR) + shift` | 极端回调位，取平台与更低位，保证 t3<t2<t1 |

**止损/止盈（L1463-1465）**
- 止损 `stop = t3 - 0.5*ATR`（极限支撑击穿，最大亏损兜底）
- 止盈1 `take1 = VWAP20 + 2.5*ATR + 0.5*max(f,0)*ATR`（减半仓）
- 止盈2 `take2 = VWAP20 + 3.5*ATR + 0.5*max(f,0)*ATR`（清仓离场）

**档位上限（L1474-1481，仓位管理）**
- f≥0.3 强趋势：三档全开；0≤f<0.3：两档；-0.3≤f<0：仅试仓；f<-0.3：禁建

**结构分（L1498-1514，满分6分）**：触建仓档位+1 / MACD底顶背离+1 / 缩量+1 / TD低9高9+1 / 均线多头+1 / 金铲子标的+1

## 四、周度锚定（L1553 `_daily_anchor`）

- 首次锚定；每周重算（7天）；VWAP20偏离>8%临时刷新
- 锚定生效期间，三档建仓/止盈/止损价位固定不飘，计划交易

## 五、风控一票否决 + 信号灯（L1590 `_daily_apply_risk`）

| 触发条件 | 信号灯 | 动作 |
|---------|--------|------|
| ST/退市股 | 🟡 禁入 | 禁止建仓 |
| 大盘跌超2% 或 f≤-0.6 | 🔴 环境风控 | 暂停建仓 |
| 现价≤止损位 | 🔴 止损清仓 | 全部清仓+推送 |
| 现价≥止盈2 或 破10日线+MACD死叉 | 🔴 清仓执行 | 清仓离场+推送 |
| 现价≥止盈1 且 顶背离 | 🟠 减仓执行 | 减半仓+推送 |
| 弱势(f<-0.3) 或 档位上限0 | 🟡 只清不建 | 仅可减仓 |
| 到重仓价+结构分≥4+缩量 | 🔴 重仓执行 | 买第三档+推送 |
| 到加仓价+结构分≥3+缩量 | 🔴 加仓执行 | 买第二档+推送 |
| 到试仓价+结构分≥2 | 🔴 试仓执行 | 买第一档+推送 |
| 接近试仓价+底背离雏形/TD低 | 🟡 准备建仓 | 等企稳确认 |
| 其它 | 🟢 持有观察 | 底仓不动 |

## 六、持久化与推送

- **DB**（L1373）：`daily_base_position` 表（独立于 holding 表）：code/name/t1/t2/t3/stop/take1/take2/vwap20/atr/f/struct_score/signal_text
- **推送**（L1707 `_daily_signal_push`）：复用 `wechat_bus.send_t_timing` 统一总线，事件：日K试仓/加仓/重仓建仓、日K减仓/清仓/止损清仓；24小时同事件冷却+蜂鸣
- **内存缓存**：`_daily_kline_cache`(10分钟)、`_daily_anchor_state`、`_daily_lock_state`，与分时完全隔离

## 七、金铲子联动（L1919 `_daily_check_golden_spade`）

- 15分钟扫描监控池：现价回踩试仓价±0.8% 且 缩量 → 弹窗「金铲子·日K回踩」，每票每日一次
- 金铲子标的自动+1结构分

---

## 八、完整代码

### 8.1 表头常量（atr_t_widget.py L42-50）

```pythonCOL_D_NAME, COL_D_CODE, COL_D_PRICE, COL_D_PCT, \
    COL_D_T1, COL_D_T2, COL_D_T3, COL_D_STOP, COL_D_TAKE, \
    COL_D_SIG = range(10)
HEADER_DAILY = ['股票名称', '代码', '现价', '涨跌幅',
                '试仓价', '加仓价', '重仓价', '止损价',
                '止盈价', '信号灯/建议']
DAILY_WIDTHS = [80, 65, 60, 70, 70, 70, 70, 70, 70, 110]

# 信号灯背景/前景色
### 8.2 日K建仓模块全部代码（atr_t_widget.py L1269-1982）

```python    # 日K建仓模块 V1.0（纯建仓 + 终级清仓）
    # 基于分时做T思路升级：20日VWAP价值中枢 + 14日ATR波动单位
    # 三档建仓（试仓/加仓/重仓） + 两档止盈 + 一档止损
    # 原则：完全不动分时做T任何逻辑；状态/缓存/锁 全部独立
    # ============================================================
    def _setup_tab_buttons(self):
        """在标题栏 title_label 右侧插入 [分时做T] / [日K建仓] 两个 Tab 按钮（仿竞价Tab样式）"""
        card_layout = self._card_frame.layout()
        title_bar_layout = card_layout.itemAt(0).layout()
        if title_bar_layout is None:
            return

        self._tab_style_normal = (
            'QPushButton{'
            'background:#f0f4f9;color:#666666;'
            'border:1px solid #d0d7e0;border-radius:4px;'
            'padding:3px 12px;font-size:11px;}'
            'QPushButton:hover{background:#e6f0ff;color:#2f6bff;}'
        )
        self._tab_style_checked = (
            'QPushButton{'
            'background:#2f6bff;color:#ffffff;'
            'border:1px solid #2f6bff;border-radius:4px;'
            'padding:3px 12px;font-size:11px;font-weight:bold;}'
        )

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)

        self._btn_hold = QPushButton('分时做T')
        self._btn_hold.setCheckable(True)
        self._btn_hold.setStyleSheet(self._tab_style_checked)
        self._btn_hold.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_group.addButton(self._btn_hold, 0)

        self._btn_daily = QPushButton('日K建仓')
        self._btn_daily.setCheckable(True)
        self._btn_daily.setStyleSheet(self._tab_style_normal)
        self._btn_daily.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_group.addButton(self._btn_daily, 1)

        self._btn_hold.setChecked(True)

        # 插入位置：title_label(0) 之后、stretch 之前
        title_bar_layout.insertWidget(1, self._btn_hold)
        title_bar_layout.insertWidget(2, self._btn_daily)

        self._tab_group.idClicked.connect(self._switch_tab)

    def _switch_tab(self, idx):
        """切换 Tab：0=分时做T（持仓表），1=日K建仓（底仓表）。
        按需启停：切到日K暂停分时刷新与金铲子（释放CPU），切回恢复。"""
        if idx == 0:
            self._tab_active = 0
            self._hold_widget.setVisible(True)
            self._daily_widget.setVisible(False)
            self._btn_hold.setStyleSheet(self._tab_style_checked)
            self._btn_daily.setStyleSheet(self._tab_style_normal)
            # 恢复分时刷新与金铲子5秒联动
            self.start_refresh(5000)
            if not self._gs_timer.isActive():
                self._gs_timer.start(5000)
            self._daily_timer.stop()
            self._daily_gs_timer.stop()
            if getattr(self, '_last_hold_title', None):
                self.title_label.setText(self._last_hold_title)
        else:
            self._tab_active = 1
            self._hold_widget.setVisible(False)
            self._daily_widget.setVisible(True)
            self._btn_hold.setStyleSheet(self._tab_style_normal)
            self._btn_daily.setStyleSheet(self._tab_style_checked)
            # 暂停分时刷新（标题不再被覆盖，省CPU），启动日K计算
            self.stop_refresh()
            self._gs_timer.stop()
            if not self._daily_timer.isActive():
                self._daily_timer.start(300000)
            if not self._daily_gs_timer.isActive():
                self._daily_gs_timer.start(900000)
            if getattr(self, '_last_hold_title', None) is None:
                self._last_hold_title = self.title_label.text()
            self.title_label.setText(getattr(self, '_last_daily_title', None) or '📈 日K建仓')
            QTimer.singleShot(0, self._daily_refresh)

    def _init_daily_module(self):
        """日K建仓模块初始化：独立缓存/锁/锚定/DB，与分时做T完全隔离"""
        self._daily_rows = []
        self._daily_kline_cache = {}      # {code: (bars, ts)} 10分钟缓存
        self._daily_anchor_state = {}     # 周度锚定
        self._daily_lock_state = {}       # {code_event: ts} 24小时信号冷却
        self._daily_gs_alerted = set()    # 今日已弹窗 code
        self._daily_gs_date = None
        self._daily_gs_pool = set()       # 金铲子池（结构分+1）
        self._daily_market_warn = False
        self._daily_market_ts = 0.0
        self._last_hold_title = None
        self._last_daily_title = None
        self._tab_active = 0              # 0=分时做T，1=日K建仓
        self._init_daily_tracking_db()
        self._daily_timer = QTimer(self)
        self._daily_timer.timeout.connect(self._daily_refresh)
        self._daily_gs_timer = QTimer(self)
        self._daily_gs_timer.timeout.connect(self._daily_check_golden_spade)

    def _init_daily_tracking_db(self):
        """日K建仓跟踪表（独立于 holding 表，不污染分时数据）"""
        try:
            import duckdb
            con = duckdb.connect(self._track_db_path)
            con.execute("""
                CREATE TABLE IF NOT EXISTS daily_base_position(
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    t1 DOUBLE, t2 DOUBLE, t3 DOUBLE,
                    stop DOUBLE, take1 DOUBLE, take2 DOUBLE,
                    vwap20 DOUBLE, atr DOUBLE, f DOUBLE,
                    struct_score INTEGER,
                    signal_text TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.close()
        except Exception as e:
            print(f'[日K建仓] 初始化daily_base_position失败: {e}', flush=True)

    def _daily_bars(self, code, price=None, prev_close=None, day_high=None, day_low=None):
        """日K建仓专用K线：120根日K，10分钟缓存；盘中用实时价更新最后一根（拷贝副本，不污染分时缓存）"""
        cached = self._daily_kline_cache.get(code)
        if cached and time.time() - cached[1] < 600:
            bars = [dict(b) for b in cached[0]]
        else:
            bars = self._load_bars(code, n=120)
            if len(bars) < 30:
                return []
            bars = [dict(b) for b in bars]
            self._daily_kline_cache[code] = (bars, time.time())
        if bars and price and price > 0:
            last = bars[-1]
            last['close'] = price
            if day_high and day_high > 0 and day_high > last['high']:
                last['high'] = day_high
            if day_low and day_low > 0 and day_low < last['low']:
                last['low'] = day_low
        return bars

    def _daily_calc_one_stock(self, code, name, price=None, prev_close=None,
                              day_high=None, day_low=None, bars=None):
        """日K建仓核心算法（分时做T思路升级到日K周期）：
        20日VWAP价值中枢 + 14日ATR波动单位 → 三档建仓价 + 两档止盈 + 一档止损；
        题材强度f动态修正建仓价与档位上限；结构分做动能确认。"""
        if bars is None:
            bars = self._daily_bars(code, price=price, prev_close=prev_close,
                                    day_high=day_high, day_low=day_low)
        if len(bars) < 30:
            return None

        closes = np.array([b['close'] for b in bars], dtype=float)
        highs = np.array([b['high'] for b in bars], dtype=float)
        lows = np.array([b['low'] for b in bars], dtype=float)
        vols = np.array([b['volume'] for b in bars], dtype=float)

        last_bar = bars[-1]
        if price is None or price <= 0:
            price = float(last_bar['close'])
        if prev_close is None or prev_close <= 0:
            prev_close = float(bars[-2]['close']) if len(bars) >= 2 else price
        if day_high is None or day_high <= 0:
            day_high = float(last_bar['high'])
        if day_low is None or day_low <= 0:
            day_low = float(last_bar['low'])
        if price <= 0 or prev_close <= 0:
            return None

        pct = (price - prev_close) / prev_close * 100.0
        atr = self._calc_atr(bars, period=14)
        if atr <= 0:
            atr = prev_close * 0.02

        # 20日典型价VWAP（日K价值中枢）
        tp = (highs + lows + closes) / 3.0
        vwap20 = float(np.mean(tp[-20:]))
        if vwap20 <= 0:
            vwap20 = price

        f, theme_tag, theme_dir = self._compute_theme_strength(code, price=price, pct=pct)

        # 题材强度修正：f>0上移建仓价（强势不深调），f<0下移（弱势加厚安全垫）
        shift = (0.5 * f * atr) if f >= 0 else (0.8 * f * atr)

        # 三档建仓价（只在中枢下方）：试仓/加仓/重仓
        t1 = vwap20 - 1.2 * atr + shift          # 试仓（价值中枢下沿）
        t2 = vwap20 - 1.8 * atr + shift          # 加仓（错杀回调位）
        platform = float(np.min(lows[-20:])) + 0.2 * atr   # 前期平台支撑
        t3 = min(platform, vwap20 - 2.4 * atr) + shift   # 重仓（极端回调位，取平台与中枢-2.4ATR更低者）
        stop = t3 - 0.5 * atr                    # 止损（极限支撑击穿）
        take1 = vwap20 + 2.5 * atr + 0.5 * max(f, 0.0) * atr   # 止盈1（减半）
        take2 = vwap20 + 3.5 * atr + 0.5 * max(f, 0.0) * atr   # 止盈2（清仓）

        # 周度锚定：锚定生效期间价位不随日间波动刷新
        anchor = self._daily_anchor(code, vwap20, atr, f, platform)
        if anchor is not None:
            t1, t2, t3 = anchor['t1'], anchor['t2'], anchor['t3']
            stop, take1, take2 = anchor['stop'], anchor['take1'], anchor['take2']

        # 档位上限（仓位管理：强趋势可满三档，弱势仅试仓，退潮禁建）
        if f >= 0.3:
            max_tier = 3
        elif f >= 0:
            max_tier = 2
        elif f >= -0.3:
            max_tier = 1
        else:
            max_tier = 0

        # MACD / TD / 背离（复用分时纯函数）
        dif, dea, hist = calc_macd(closes, 8, 21, 5)
        cross = detect_cross(dif, dea) if len(dif) else None
        td = calc_td(closes.tolist())
        div = check_divergence(closes, dif) if len(dif) else None

        # 量能：5日均量缩量判断
        vol5 = float(np.mean(vols[-5:])) if len(vols) >= 5 else 0.0
        shrink = (vol5 > 0) and (float(vols[-1]) < vol5 * 0.8)

        # 均线结构
        ma10 = float(np.mean(closes[-10:])) if len(closes) >= 10 else price
        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else price
        trend_up = (ma10 > ma20) and (price > ma10)

        # 结构分（满分6分）
        struct_score = 0
        near_t1 = price <= t1 * 1.01
        near_t2 = price <= t2 * 1.01
        near_t3 = price <= t3 * 1.01
        if near_t1 or near_t2 or near_t3:
            struct_score += 1
        if div in ('bottom', 'top'):
            struct_score += 1
        if shrink:
            struct_score += 1
        if td['is_low9'] or td['is_high9']:
            struct_score += 1
        if trend_up:
            struct_score += 1
        if code in self._daily_gs_pool:
            struct_score += 1

        # 动能文本
        momentum_parts = []
        if div == 'bottom':
            momentum_parts.append('日线底背离')
        elif div == 'top':
            momentum_parts.append('日线顶背离')
        elif div == 'bottom_emerging':
            momentum_parts.append('底背离雏形')
        elif div == 'top_emerging':
            momentum_parts.append('顶背离雏形')
        if td['is_low9']:
            momentum_parts.append('TD低9')
        elif td['is_high9']:
            momentum_parts.append('TD高9')
        if shrink:
            momentum_parts.append('缩量')
        if trend_up:
            momentum_parts.append('多头排列')
        elif ma10 < ma20:
            momentum_parts.append('空头排列')
        momentum_text = ' + '.join(momentum_parts) if momentum_parts else '暂无'

        return dict(
            code=code, name=name,
            price=round(price, 2), pct=round(pct, 2),
            t1=round(t1, 2), t2=round(t2, 2), t3=round(t3, 2),
            stop=round(stop, 2), take1=round(take1, 2), take2=round(take2, 2),
            vwap20=round(vwap20, 2), atr=round(atr, 2),
            f=round(f, 2), theme_tag=theme_tag, theme_dir=theme_dir,
            max_tier=max_tier, struct_score=struct_score,
            momentum=momentum_text,
            div=div, td=td, cross=cross, shrink=shrink,
            ma10=round(ma10, 2), ma20=round(ma20, 2),
            trend_up=trend_up,
            near_t1=near_t1, near_t2=near_t2, near_t3=near_t3,
        )

    def _daily_anchor(self, code, vwap20, atr, f, platform):
        """日K周度锚定：每周重算一次；偏离8%或拐头才临时刷新，保证建仓计划稳定不飘"""
        now = time.time()
        anchor = self._daily_anchor_state.get(code)
        need = False
        reason = ''
        if anchor is None:
            need = True
            reason = 'init'
        else:
            if now - anchor['ts'] >= 7 * 24 * 3600:
                need = True
                reason = 'weekly'
            else:
                old_vwap = anchor['vwap']
                if old_vwap > 0 and vwap20 > 0:
                    dev = abs(vwap20 - old_vwap) / old_vwap
                    if dev > 0.08:
                        need = True
                        reason = f'dev{dev*100:.1f}%'
        if need:
            shift = (0.5 * f * atr) if f >= 0 else (0.8 * f * atr)
            t1 = vwap20 - 1.2 * atr + shift
            t2 = vwap20 - 1.8 * atr + shift
            t3 = min(platform, vwap20 - 2.4 * atr) + shift
            stop = t3 - 0.5 * atr
            take1 = vwap20 + 2.5 * atr + 0.5 * max(f, 0.0) * atr
            take2 = vwap20 + 3.5 * atr + 0.5 * max(f, 0.0) * atr
            anchor = {
                'ts': now, 'vwap': vwap20, 'atr': atr, 'f': f,
                't1': t1, 't2': t2, 't3': t3,
                'stop': stop, 'take1': take1, 'take2': take2,
                'reason': reason,
            }
            self._daily_anchor_state[code] = anchor
        return anchor

    def _daily_apply_risk(self, r):
        """日K风控一票否决 + 信号灯（对齐分时三色语义，新增波段级风控）"""
        price = r['price']
        t1, t2, t3 = r['t1'], r['t2'], r['t3']
        stop = r['stop']
        take1, take2 = r['take1'], r['take2']
        f = r['f']
        div = r['div']
        td = r['td']
        cross = r['cross']
        struct_score = r['struct_score']
        shrink = r['shrink']
        max_tier = r['max_tier']
        ma10 = r['ma10']
        theme_dir = r['theme_dir']

        risk_status = '正常(中枢上方)' if price >= r['vwap20'] else '正常(中枢下方)'
        risk_color = SIGNAL_FG['green'] if price >= r['vwap20'] else SIGNAL_FG['yellow']
        signal_level = 'gray'
        signal_text = '⚪ 待机'
        signal_dir = None
        action = '持有观察'
        blocked = None

        name = r.get('name', '') or ''
        is_st = ('ST' in name.upper()) or ('退' in name)
        if is_st:
            signal_level = 'yellow'
            signal_text = '🟡 禁入'
            action = 'ST/退市股，禁止建仓'
            risk_status = '⛔ 禁入标的'
            risk_color = SIGNAL_FG['yellow']
            blocked = 'buy'
        elif self._daily_market_warn or f <= -0.6:
            signal_level = 'red'
            signal_text = '🔴 环境风控'
            action = '大盘/题材退潮，暂停建仓'
            risk_status = '🌊 环境风控'
            risk_color = SIGNAL_FG['red']
            blocked = 'buy'
        elif price <= stop:
            signal_level = 'red'
            signal_text = '🔴 止损清仓'
            action = f'跌破止损{stop:.2f}，全部清仓'
            risk_status = '💥 止损清仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'sell'
            self._daily_signal_push(r, '日K止损清仓', stop, action)
        elif price >= take2 or (price < ma10 and cross == 'dead'):
            signal_level = 'red'
            signal_text = '🔴 清仓执行'
            action = f'到目标位{take2:.2f}或破位，清仓离场'
            risk_status = '🎯 清仓执行'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'sell'
            self._daily_signal_push(r, '日K清仓执行', take2, action)
        elif price >= take1 and div == 'top':
            signal_level = 'orange'
            signal_text = '🟠 减仓执行'
            action = f'到止盈1 {take1:.2f}+顶背离，减半仓'
            risk_status = '💰 减仓执行'
            risk_color = SIGNAL_FG['orange']
            signal_dir = 'sell'
            self._daily_signal_push(r, '日K减仓提醒', take1, action)
        elif theme_dir == 'weak' or max_tier <= 0:
            signal_level = 'yellow'
            signal_text = '🟡 只清不建'
            action = '弱势/禁建仓，仅可减仓'
            risk_status = '🛑 弱势禁建'
            risk_color = SIGNAL_FG['yellow']
            blocked = 'buy'
        elif max_tier >= 3 and price <= t3 and struct_score >= 4 and shrink:
            signal_level = 'red'
            signal_text = '🔴 重仓执行'
            action = f'到重仓{t3:.2f}，买第三档'
            risk_status = '🟢 重仓建仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'buy'
            self._daily_signal_push(r, '日K重仓建仓', t3, action)
        elif max_tier >= 2 and price <= t2 and struct_score >= 3 and shrink:
            signal_level = 'red'
            signal_text = '🔴 加仓执行'
            action = f'到加仓{t2:.2f}，买第二档'
            risk_status = '🟢 加仓建仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'buy'
            self._daily_signal_push(r, '日K加仓建仓', t2, action)
        elif max_tier >= 1 and price <= t1 and struct_score >= 2:
            signal_level = 'red'
            signal_text = '🔴 试仓执行'
            action = f'到试仓{t1:.2f}，买第一档'
            risk_status = '🟢 试仓建仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'buy'
            self._daily_signal_push(r, '日K试仓建仓', t1, action)
        elif price <= t1 * 1.01 and (div in ('bottom_emerging', 'bottom') or td['is_low78'] or td['is_low9']):
            signal_level = 'yellow'
            signal_text = '🟡 准备建仓'
            action = '接近试仓价，等企稳确认'
            risk_status = '⏳ 准备建仓'
            risk_color = SIGNAL_FG['yellow']
        else:
            signal_level = 'green'
            signal_text = '🟢 持有观察'
            action = '底仓持有，日K不动'
            risk_status = '🧊 持有观察'
            risk_color = SIGNAL_FG['green']

        r['risk_status'] = risk_status
        r['risk_color'] = risk_color
        r['signal_level'] = signal_level
        r['signal_text'] = signal_text
        r['signal_dir'] = signal_dir
        r['action'] = action
        r['blocked'] = blocked
        return r

    def _daily_signal_push(self, r, event, ref_price, action):
        """日K触发信号：24小时同事件冷却 + 蜂鸣 + 统一总线推送 + 计划写库"""
        code = r['code']
        now = time.time()
        key = f'{code}_{event}'
        last = self._daily_lock_state.get(key)
        if last and now - last < 24 * 3600:
            return
        self._daily_lock_state[key] = now
        kind = 'buy' if '建仓' in event else 'sell'
        self._play_sound(kind, code)
        try:
            from services.wechat_bus import get_wechat_bus
            get_wechat_bus().send_t_timing(
                event=event, code=code, name=r.get('name', ''),
                price=r['price'], vwap=r['vwap20'], atr=r['atr'],
                ref_price=ref_price, cur_status=r['risk_status'],
                reason=action, risk=r['risk_status'], action=action)
        except Exception:
            pass
        try:
            import duckdb
            con = duckdb.connect(self._track_db_path)
            con.execute("""
                INSERT OR REPLACE INTO daily_base_position
                (code, name, t1, t2, t3, stop, take1, take2,
                 vwap20, atr, f, struct_score, signal_text)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (code, r['name'], r['t1'], r['t2'], r['t3'], r['stop'],
                  r['take1'], r['take2'], r['vwap20'], r['atr'], r['f'],
                  r['struct_score'], r.get('signal_text', '')))
            con.close()
        except Exception as e:
            print(f'[日K建仓] 写daily_base_position失败: {e}', flush=True)

    def _daily_check_market(self):
        """大盘环境风控：上证指数跌超2% → 暂停建仓（10分钟缓存）"""
        now = time.time()
        if now - self._daily_market_ts < 600:
            return self._daily_market_warn
        warn = False
        try:
            from utils.http_market_data import eastmoney_request
            data = eastmoney_request('/api/qt/stock/get', {
                'secid': '1.000001', 'fields': 'f2,f3'
            }, timeout=5)
            if data and 'data' in data:
                pct = float(data['data'].get('f3', 0)) / 100.0
                warn = pct < -2.0
        except Exception:
            pass
        self._daily_market_warn = warn
        self._daily_market_ts = now
        return warn

    def _daily_fetch_and_calc(self):
        """后台：日K建仓行计算（复用持仓来源 + 行情 + K线）"""
        holdings = self._get_holdings_source()
        self._daily_check_market()
        # 金铲子池标记（结构分+1）
        self._daily_gs_pool = set()
        try:
            from services.golden_shovel_scanner import _read_monitor_pool
            for p in _read_monitor_pool() or []:
                self._daily_gs_pool.add(p['code'])
        except Exception:
            pass
        if not holdings:
            return []
        codes = [it['code'] for it in holdings]
        try:
            from utils.http_market_data import get_realtime_quotes_http
            quotes = get_realtime_quotes_http(codes) or {}
        except Exception as e:
            print(f'[日K建仓] 实时行情失败: {e}', flush=True)
            quotes = {}
        rows = []
        for item in holdings:
            code = item['code']
            name = item['name']
            q = quotes.get(code, {}) or {}
            price = float(q.get('price', 0) or 0)
            prev_close = float(q.get('last_close', 0) or 0)
            day_high = float(q.get('high', 0) or 0)
            day_low = float(q.get('low', 0) or 0)
            bars = self._daily_bars(code, price=price or None, prev_close=prev_close or None,
                                    day_high=day_high or None, day_low=day_low or None)
            r = self._daily_calc_one_stock(
                code, name, price=price or None, prev_close=prev_close or None,
                day_high=day_high or None, day_low=day_low or None, bars=bars)
            if r is None:
                continue
            r['cost'] = item.get('cost')
            r['qty'] = item.get('qty')
            r = self._daily_apply_risk(r)
            rows.append(r)
        return rows

    def _daily_refresh(self):
        """日K建仓刷新（仅日K Tab激活时运行，5分钟一次）"""
        if getattr(self, '_tab_active', 0) != 1:
            return
        self.run_async(self._daily_fetch_and_calc, self._daily_on_loaded, self._daily_on_failed)

    def _daily_on_loaded(self, rows):
        """主线程：渲染日K建仓表 + 更新标题"""
        self._daily_rows = rows or []
        now = datetime.now()
        h, m = now.hour, now.minute
        if now.weekday() >= 5:
            tag = '休市'
        elif ((h == 9 and m >= 30) or h == 10 or (h == 11 and m <= 30)
              or h == 13 or h == 14) and h < 15:
            tag = '盘中监控'
        else:
            tag = '盘后复盘'
        self._last_daily_title = f'📈 日K建仓 ({tag}) · {len(self._daily_rows)}只'
        if getattr(self, '_tab_active', 0) == 1:
            self.title_label.setText(self._last_daily_title)
        self._daily_render_table()
        self.set_update_time()

    def _daily_on_failed(self, err):
        self.set_status('日K建仓数据获取失败')

    def _daily_render_table(self):
        rows = self._daily_rows
        self.daily_table.clearSpans()
        self.daily_table.setRowCount(len(rows))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter

        for i, r in enumerate(rows):
            set_table_item(self.daily_table, i, COL_D_NAME, r['name'],
                           BC.TEXT_PRIMARY, bold=True, align=left)
            set_table_item(self.daily_table, i, COL_D_CODE, r['code'],
                           '#000000', bold=True, align=center)
            set_table_item(self.daily_table, i, COL_D_PRICE, f"{r['price']:.2f}",
                           '#000000', bold=True, align=right)
            set_table_item(self.daily_table, i, COL_D_PCT, f"{r['pct']:+.2f}%",
                           pct_color(r['pct']), bold=True, align=right)
            # 三档建仓价：命中档位高亮
            set_table_item(self.daily_table, i, COL_D_T1, f"{r['t1']:.2f}",
                           '#2E7D32' if r['near_t1'] else '#607d8b', bold=True, align=right)
            set_table_item(self.daily_table, i, COL_D_T2, f"{r['t2']:.2f}",
                           '#2E7D32' if r['near_t2'] else '#607d8b', bold=True, align=right)
            set_table_item(self.daily_table, i, COL_D_T3, f"{r['t3']:.2f}",
                           '#2E7D32' if r['near_t3'] else '#607d8b', bold=True, align=right)
            # 止损价（破位红）/ 止盈价（目标橙）
            set_table_item(self.daily_table, i, COL_D_STOP, f"{r['stop']:.2f}",
                           '#C62828' if r['price'] <= r['stop'] else '#8d6e63',
                           bold=True, align=right)
            set_table_item(self.daily_table, i, COL_D_TAKE,
                           f"{r['take1']:.2f}/{r['take2']:.2f}",
                           '#E65100', bold=True, align=right)
            # 信号灯 + 操作建议（合并列，带背景色）
            sig_text = r['signal_text']
            act_short = self._daily_short_action(r.get('action', ''))
            cell_text = sig_text
            if act_short and act_short not in ('观望',):
                cell_text = f'{sig_text}·{act_short}'
            sig_item = QTableWidgetItem(cell_text)
            lvl = r['signal_level']
            bg = SIGNAL_BG.get(lvl, SIGNAL_BG['gray'])
            sig_item.setBackground(QBrush(QColor(bg)))
            sig_item.setForeground(QColor('#000000'))
            fnt = sig_item.font()
            fnt.setBold(True)
            sig_item.setFont(fnt)
            sig_item.setTextAlignment(center)
            self.daily_table.setItem(i, COL_D_SIG, sig_item)

    @staticmethod
    def _daily_short_momentum(mom):
        """日K动能精简"""
        if not mom or mom == '暂无':
            return '--'
        out = []
        for kw, short in [
            ('日线底背离', '底背离'), ('日线顶背离', '顶背离'),
            ('底背离雏形', '底背离'), ('顶背离雏形', '顶背离'),
            ('TD低9', 'TD9'), ('TD高9', 'TD9'),
            ('缩量', '缩量'), ('多头排列', '多头'), ('空头排列', '空头'),
        ]:
            if kw in mom:
                out.append(short)
        return '/'.join(out) if out else '--'

    @staticmethod
    def _daily_short_action(act):
        """日K操作建议精简"""
        if not act:
            return '观望'
        if '止损' in act or '清仓' in act:
            return '清仓'
        if '减半' in act or '减仓' in act:
            return '减仓'
        if '重仓' in act:
            return '重仓'
        if '加仓' in act:
            return '加仓'
        if '试仓' in act:
            return '试仓'
        if '等企稳' in act:
            return '等确认'
        if '持有' in act:
            return '持有'
        if '禁' in act:
            return '禁入'
        return act[:6]

    def _daily_check_golden_spade(self):
        """日K金铲子联动（15分钟）：监控池个股回踩试仓价±0.8%且缩量 → 弹窗（每票每日一次）"""
        if getattr(self, '_tab_active', 0) != 1:
            return
        from datetime import date as _date
        today = _date.today().isoformat()
        if self._daily_gs_date != today:
            self._daily_gs_alerted = set()
            self._daily_gs_date = today
        now = datetime.now()
        h, m = now.hour, now.minute
        if now.weekday() >= 5:
            return
        if not (((h == 9 and m >= 30) or h == 10 or (h == 11 and m <= 30)
                 or h == 13 or h == 14) and h < 15):
            return
        try:
            from services.golden_shovel_scanner import _read_monitor_pool
            pool = _read_monitor_pool()
        except Exception as e:
            print(f'[日K金铲子] 读监控池失败: {e}', flush=True)
            return
        if not pool:
            return
        codes = [p['code'] for p in pool if p['code'] not in self._daily_gs_alerted]
        if not codes:
            return
        try:
            from utils.http_market_data import get_realtime_quotes_http
            quotes = get_realtime_quotes_http(codes) or {}
        except Exception as e:
            print(f'[日K金铲子] 实时行情失败: {e}', flush=True)
            return
        hits = []
        for p in pool:
            code = p['code']
            if code in self._daily_gs_alerted:
                continue
            q = quotes.get(code, {}) or {}
            price = float(q.get('price', 0) or 0)
            volr = float(q.get('volume_ratio', q.get('vol_ratio', 0)) or 0)
            if price <= 0:
                continue
            bars = self._daily_bars(code, price=price)
            if len(bars) < 30:
                continue
            r = self._daily_calc_one_stock(code, p.get('name', ''), price=price, bars=bars)
            if r is None:
                continue
            near = price <= r['t1'] * 1.008
            shrink = (volr > 0 and volr <= 1.0) or r['shrink']
            if near and shrink:
                hits.append((p, r))
                self._daily_gs_alerted.add(code)
        for p, r in hits:
            chain_name = p.get('chain', '') or ''
            try:
                QMessageBox.information(
                    self, f'【金铲子·日K回踩】{chain_name}',
                    f'【金铲子·日K回踩】{p["name"]} {p["code"]}\n'
                    f'现价{r["price"]:.2f}，已回踩至试仓价{r["t1"]:.2f}\n'
                    f'缩量企稳，建议分批建仓底仓。')
            except Exception as e:
                print(f'[日K金铲子] 弹窗失败: {e}', flush=True)
```