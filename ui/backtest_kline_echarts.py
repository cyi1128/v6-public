# -*- coding: utf-8 -*-
"""
V0.6.3.5 回测K线ECharts组件 - 专业交互式K线

功能：
- K线 + 成交量 + MA5/MA9/MA20
- 买卖点scatter标记（不使用markPoint）
- dataZoom滚轮缩放 + 底部拖动条
- 鼠标十字线
- 点击买卖点显示交易详情tooltip
- 交易区间高亮
- 深色主题
"""
import os
import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, pyqtSignal

# ECharts HTML模板 - 回测专用
BACKTEST_ECHARTS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        html, body {
            margin: 0; padding: 0; width: 100%; height: 100%;
            background: #0d1117; overflow: hidden;
        }
        #chart { width: 100%; height: 100%; }
        .trade-tooltip {
            background: #161b22; border: 1px solid #30363d;
            border-radius: 6px; padding: 10px 14px; color: #c9d1d9;
            font-family: Consolas, monospace; font-size: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        .trade-tooltip .title { font-weight: bold; margin-bottom: 6px; font-size: 13px; }
        .trade-tooltip .buy { color: #22c55e; }
        .trade-tooltip .sell { color: #ef4444; }
        .trade-tooltip .row { display: flex; justify-content: space-between; margin: 2px 0; }
        .trade-tooltip .label { color: #8b949e; }
        .trade-tooltip .value { color: #c9d1d9; }
    </style>
    <script src="echarts.min.js"></script>
</head>
<body>
    <div id="chart"></div>
    <script>
        var chart = echarts.init(document.getElementById('chart'));
        var rawData = [];
        var tradePoints = [];

        // 计算MA
        function calculateMA(dayCount, data) {
            var result = [];
            for (var i = 0; i < data.length; i++) {
                if (i < dayCount - 1) { result.push('-'); continue; }
                var sum = 0;
                for (var j = 0; j < dayCount; j++) sum += data[i - j][1];
                result.push((sum / dayCount).toFixed(2));
            }
            return result;
        }

        function renderChart(klineData, trades, bsStyle) {
            rawData = klineData;
            tradePoints = trades || [];
            // B/S样式配置（默认值）
            var style = bsStyle || {
                buy_color: '#ef4444',
                sell_color: '#22c55e',
                font_size: 18,
                distance: 2,
                buy_offset: -8,
                sell_offset: 8
            };

            var dates = klineData.map(function(d) { return d[0]; });
            var values = klineData.map(function(d) { return [d[1], d[4], d[3], d[2]]; }); // open, close, low, high
            var volumes = klineData.map(function(d, i) {
                return [i, d[5], d[1] <= d[4] ? 1 : -1];
            });

            // 计算价格范围用于偏移
            var allLows = klineData.map(function(d) { return d[3]; });
            var allHighs = klineData.map(function(d) { return d[4]; });
            var priceRange = Math.max.apply(null, allHighs) - Math.min.apply(null, allLows);
            var offset = priceRange * 0.025; // 价格范围的2.5%作为偏移

            // 买卖点数据（买点在最低价下方，卖点在最高价上方）- 使用markPoint
            var buyMarkPoints = [];
            var sellMarkPoints = [];
            trades.forEach(function(t) {
                var idx = dates.indexOf(t.date);
                if (idx >= 0) {
                    var dayLow = klineData[idx][3];
                    var dayClose = klineData[idx][4];
                    if (t.side === 'buy') {
                        buyMarkPoints.push({
                            name: 'B',
                            coord: [t.date, dayLow - offset],
                            value: 'B',
                            symbol: 'circle',
                            symbolSize: 1,
                            itemStyle: { color: 'transparent', borderColor: 'transparent' },
                            label: {
                                show: true,
                                formatter: 'B',
                                color: style.buy_color,
                                fontSize: style.font_size,
                                fontWeight: 'bold',
                                position: 'bottom',
                                distance: style.distance
                            },
                            tradeInfo: t
                        });
                    } else {
                        sellMarkPoints.push({
                            name: 'S',
                            coord: [t.date, dayClose + offset],
                            value: 'S',
                            symbol: 'circle',
                            symbolSize: 1,
                            itemStyle: { color: 'transparent', borderColor: 'transparent' },
                            label: {
                                show: true,
                                formatter: 'S',
                                color: style.sell_color,
                                fontSize: style.font_size,
                                fontWeight: 'bold',
                                position: 'top',
                                distance: style.distance
                            },
                            tradeInfo: t
                        });
                    }
                }
            });

            var option = {
                backgroundColor: '#0d1117',
                animation: false,
                legend: {
                    data: ['K线', 'MA5', 'MA9', 'MA20'],
                    top: 5,
                    textStyle: { color: '#8b949e', fontSize: 11 },
                    itemWidth: 14, itemHeight: 8
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    backgroundColor: '#161b22',
                    borderColor: '#30363d',
                    textStyle: { color: '#c9d1d9', fontSize: 11 },
                    formatter: function(params) {
                        if (!params || !params.length) return '';
                        var idx = params[0].dataIndex;
                        var d = klineData[idx];
                        if (!d) return '';
                        var html = '<div style="font-weight:bold;margin-bottom:4px;">' + d[0] + '</div>';
                        html += '<div>开: ' + d[1] + ' 高: ' + d[2] + ' 低: ' + d[3] + ' 收: ' + d[4] + '</div>';
                        html += '<div>成交量: ' + d[5] + '</div>';
                        // 检查是否有买卖点
                        var tp = trades.find(function(t) { return t.date === d[0]; });
                        if (tp) {
                            var color = tp.side === 'buy' ? '#22c55e' : '#ef4444';
                            var action = tp.side === 'buy' ? '买入' : '卖出';
                            html += '<div style="margin-top:4px;color:' + color + ';font-weight:bold;">'
                                + action + ' @ ' + tp.price;
                            if (tp.pnl) html += ' 盈亏: ' + (tp.pnl > 0 ? '+' : '') + tp.pnl;
                            if (tp.hold_days) html += ' 持仓: ' + tp.hold_days + '天';
                            html += '</div>';
                        }
                        return html;
                    }
                },
                axisPointer: {
                    link: [{ xAxisIndex: 'all' }],
                    label: { backgroundColor: '#30363d' }
                },
                grid: [
                    { left: '8%', right: '3%', top: '12%', height: '55%' },
                    { left: '8%', right: '3%', top: '72%', height: '16%' }
                ],
                xAxis: [
                    {
                        type: 'category', data: dates, scale: true,
                        boundaryGap: false, axisLine: { lineStyle: { color: '#30363d' } },
                        axisLabel: { color: '#8b949e', fontSize: 10 },
                        splitLine: { show: false }, min: 'dataMin', max: 'dataMax'
                    },
                    {
                        type: 'category', gridIndex: 1, data: dates, scale: true,
                        boundaryGap: false, axisLine: { lineStyle: { color: '#30363d' } },
                        axisLabel: { show: false }, splitLine: { show: false }
                    }
                ],
                yAxis: [
                    {
                        scale: true, splitArea: { show: false },
                        axisLine: { lineStyle: { color: '#30363d' } },
                        axisLabel: { color: '#8b949e', fontSize: 10 },
                        splitLine: { lineStyle: { color: '#21262d' } }
                    },
                    {
                        scale: true, gridIndex: 1, splitNumber: 2,
                        axisLabel: { show: false }, axisLine: { show: false },
                        splitLine: { show: false }
                    }
                ],
                dataZoom: [
                    { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
                    {
                        type: 'slider', xAxisIndex: [0, 1], bottom: '2%', height: 18,
                        start: 50, end: 100,
                        textStyle: { color: '#8b949e' },
                        borderColor: '#30363d',
                        fillerColor: 'rgba(31,111,235,0.2)',
                        handleStyle: { color: '#1f6feb' }
                    }
                ],
                series: [
                    {
                        name: 'K线', type: 'candlestick', data: values,
                        itemStyle: {
                            color: '#ef4444', color0: 'transparent',
                            borderColor: '#ef4444', borderColor0: '#22c55e',
                            borderWidth: 1
                        },
                        // trade_mark_layer: 买卖点标记层（纯字母B/S）
                        markPoint: {
                            symbol: 'circle',
                            symbolSize: 1,
                            data: buyMarkPoints.concat(sellMarkPoints),
                            tooltip: {
                                trigger: 'item',
                                formatter: function(p) {
                                    var t = p.data.tradeInfo;
                                    if (!t) return '';
                                    var isBuy = t.side === 'buy';
                                    var color = isBuy ? '#ef4444' : '#22c55e';
                                    var action = isBuy ? '▲ 买入' : '▼ 卖出';
                                    var html = '<div class="trade-tooltip">'
                                        + '<div class="title" style="color:' + color + ';">' + action + '</div>'
                                        + '<div class="row"><span class="label">日期</span><span class="value">' + t.date + '</span></div>'
                                        + '<div class="row"><span class="label">价格</span><span class="value">' + t.price + '</span></div>';
                                    if (t.qty) html += '<div class="row"><span class="label">数量</span><span class="value">' + t.qty + '</span></div>';
                                    if (t.pnl !== undefined && t.pnl !== 0) {
                                        var pnlColor = t.pnl > 0 ? '#ef4444' : '#22c55e';
                                        html += '<div class="row"><span class="label">盈亏</span><span class="value" style="color:' + pnlColor + ';">' + (t.pnl > 0 ? '+' : '') + t.pnl + '</span></div>';
                                    }
                                    if (t.hold_days) html += '<div class="row"><span class="label">持仓</span><span class="value">' + t.hold_days + '天</span></div>';
                                    html += '</div>';
                                    return html;
                                }
                            }
                        }
                    },
                    {
                        name: 'MA5', type: 'line', data: calculateMA(5, values),
                        smooth: true, lineStyle: { width: 1, color: '#ffffff' },
                        showSymbol: false
                    },
                    {
                        name: 'MA9', type: 'line', data: calculateMA(9, values),
                        smooth: true, lineStyle: { width: 1, color: '#fbbf24' },
                        showSymbol: false
                    },
                    {
                        name: 'MA20', type: 'line', data: calculateMA(20, values),
                        smooth: true, lineStyle: { width: 1, color: '#3b82f6' },
                        showSymbol: false
                    },
                    {
                        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
                        data: volumes.map(function(v) {
                            return { value: v[1], itemStyle: { color: v[2] > 0 ? '#ef4444' : '#3b82f6' } };
                        })
                    }
                ]
            };
            chart.setOption(option, true);
        }

        // 暴露给Python调用
        window.pyCallback = {
            setData: function(klineJson, tradesJson, styleJson) {
                try {
                    var kline = JSON.parse(klineJson);
                    var trades = JSON.parse(tradesJson);
                    var bsStyle = styleJson ? JSON.parse(styleJson) : null;
                    renderChart(kline, trades, bsStyle);
                } catch(e) {
                    document.getElementById('chart').innerHTML =
                        '<div style="color:#ef4444;padding:20px;">数据加载失败: ' + e.message + '</div>';
                }
            }
        };

        // 响应式
        window.addEventListener('resize', function() { chart.resize(); });
    </script>
</body>
</html>
"""


class BacktestKlineECharts(QWidget):
    """回测K线ECharts组件 - 专业交互式"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kline_data = None
        self._trade_points = None
        # B/S标记样式配置
        self._bs_style = {
            'buy_color': '#ef4444',      # B点颜色（红）
            'sell_color': '#22c55e',     # S点颜色（绿）
            'font_size': 18,             # 字体大小
            'distance': 2,               # 距离（像素）
            'buy_offset': -8,            # B点Y偏移（负值=下方）
            'sell_offset': 8,            # S点Y偏移（正值=上方）
        }
        self._init_ui()

    def set_bs_style(self, buy_color=None, sell_color=None, font_size=None,
                     distance=None, buy_offset=None, sell_offset=None):
        """设置B/S标记样式

        Args:
            buy_color: B点颜色
            sell_color: S点颜色
            font_size: 字体大小
            distance: 标签距离
            buy_offset: B点Y轴偏移
            sell_offset: S点Y轴偏移
        """
        if buy_color:
            self._bs_style['buy_color'] = buy_color
        if sell_color:
            self._bs_style['sell_color'] = sell_color
        if font_size:
            self._bs_style['font_size'] = font_size
        if distance is not None:
            self._bs_style['distance'] = distance
        if buy_offset is not None:
            self._bs_style['buy_offset'] = buy_offset
        if sell_offset is not None:
            self._bs_style['sell_offset'] = sell_offset
        # 如果已有数据，重新渲染
        if self._kline_data:
            self.set_data(self._kline_data, self._trade_points)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet('background: #0d1117; border: none;')
        layout.addWidget(self.web_view)
        self._load_html()

    def _load_html(self):
        """加载HTML模板"""
        # 保存HTML到临时文件，确保echarts.min.js路径正确
        assets_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets'
        )
        html_path = os.path.join(assets_dir, 'backtest_kline.html')
        os.makedirs(assets_dir, exist_ok=True)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(BACKTEST_ECHARTS_HTML)
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))

    def set_data(self, kline_data, trade_points=None):
        """设置K线数据和买卖点

        Args:
            kline_data: dict, 包含 dates, open, high, low, close, volume
            trade_points: list, [{'date':'2025-01-01','side':'buy','price':20.5,'pnl':0,'qty':1000,'hold_days':0}]
        """
        self._kline_data = kline_data
        self._trade_points = trade_points or []

        if not kline_data:
            return

        # 转换为ECharts格式: [[date, open, high, low, close, volume], ...]
        dates = kline_data.get('dates', [])
        opens = kline_data.get('open', [])
        highs = kline_data.get('high', [])
        lows = kline_data.get('low', [])
        closes = kline_data.get('close', [])
        volumes = kline_data.get('volume', [])

        echarts_data = []
        for i in range(len(dates)):
            d = str(dates[i])[:10]
            echarts_data.append([
                d,
                round(float(opens[i]), 2) if i < len(opens) else 0,
                round(float(highs[i]), 2) if i < len(highs) else 0,
                round(float(lows[i]), 2) if i < len(lows) else 0,
                round(float(closes[i]), 2) if i < len(closes) else 0,
                int(volumes[i]) if i < len(volumes) else 0,
            ])

        # 转换买卖点
        trades = []
        for t in self._trade_points:
            d = str(t.get('date', t.get('filled_date', '')))[:10]
            side = t.get('side', t.get('type', ''))
            side = 'buy' if 'buy' in str(side).lower() or '买' in str(side) else 'sell'
            trades.append({
                'date': d,
                'side': side,
                'price': round(float(t.get('price', t.get('filled_price', 0))), 2),
                'pnl': t.get('pnl', 0),
                'qty': t.get('qty', t.get('filled_quantity', t.get('quantity', 0))),
                'hold_days': t.get('hold_days', 0),
            })

        # 延迟调用JS，确保页面加载完成
        kline_json = json.dumps(echarts_data, ensure_ascii=False)
        trades_json = json.dumps(trades, ensure_ascii=False)
        style_json = json.dumps(self._bs_style, ensure_ascii=False)
        js_code = f"if(window.pyCallback){{window.pyCallback.setData('{kline_json}','{trades_json}','{style_json}');}}"

        # 延迟执行
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, lambda: self.web_view.page().runJavaScript(js_code))
