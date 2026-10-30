"""
ECharts专业K线图组件 - 基础稳定版
只保留：K线 + MA均线 + 成交量
确认稳定后再逐步添加功能
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, Qt, pyqtSignal, QObject, pyqtSlot
from PyQt6.QtGui import QColor
import json
import os

# ECharts HTML模板（基础版）
ECHARTS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background: #FFFFFF;
            overflow: hidden;
        }
        #chart {
            width: 100%;
            height: 100%;
            cursor: grab;
            -webkit-user-select: none;
            user-select: none;
        }
        #chart:active {
            cursor: grabbing;
        }
    </style>
    <script src="echarts.min.js"></script>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
    <div id="chart"></div>
    <script>
        var chart = echarts.init(document.getElementById('chart'));
        var currentData = {};
        var pyBridge = null;
        
        // 确保图表容器可以接收鼠标事件
        var chartDom = document.getElementById('chart');
        chartDom.style.pointerEvents = 'auto';
        chartDom.style.touchAction = 'none';
        
        // ========== 自定义鼠标拖动平移（兼容QWebEngineView） ==========
        var isDragging = false;
        var dragStartX = 0;
        var dragStartStart = 0;
        var dragStartEnd = 0;
        var chartWidth = 0;
        
        chartDom.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return; // 只响应左键
            isDragging = true;
            dragStartX = e.clientX;
            chartWidth = chartDom.offsetWidth;
            // 获取当前dataZoom状态
            var option = chart ? chart.getOption() : null;
            if (option && option.dataZoom && option.dataZoom.length > 0) {
                dragStartStart = option.dataZoom[0].start || 0;
                dragStartEnd = option.dataZoom[0].end || 100;
            } else {
                dragStartStart = 0;
                dragStartEnd = 100;
            }
            chartDom.style.cursor = 'grabbing';
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', function(e) {
            if (!isDragging) return;
            var deltaX = e.clientX - dragStartX;
            var deltaPercent = (deltaX / chartWidth) * 100;
            var range = dragStartEnd - dragStartStart;
            var newStart = dragStartStart - deltaPercent;
            var newEnd = dragStartEnd - deltaPercent;
            // 边界检查
            if (newStart < 0) { newStart = 0; newEnd = range; }
            if (newEnd > 100) { newEnd = 100; newStart = 100 - range; }
            if (newStart < 0) newStart = 0;
            // 更新dataZoom
            chart.dispatchAction({
                type: 'dataZoom',
                start: newStart,
                end: newEnd
            });
        });
        
        document.addEventListener('mouseup', function(e) {
            if (isDragging) {
                isDragging = false;
                chartDom.style.cursor = 'grab';
            }
        });
        
        // 鼠标滚轮缩放
        chartDom.addEventListener('wheel', function(e) {
            e.preventDefault();
            var option = chart ? chart.getOption() : null;
            if (!option || !option.dataZoom || option.dataZoom.length === 0) return;
            var start = option.dataZoom[0].start || 0;
            var end = option.dataZoom[0].end || 100;
            var range = end - start;
            var center = (start + end) / 2;
            var delta = e.deltaY > 0 ? 5 : -5; // 向上滚放大，向下滚缩小
            var newRange = Math.max(10, Math.min(100, range + delta));
            var newStart = center - newRange / 2;
            var newEnd = center + newRange / 2;
            if (newStart < 0) { newStart = 0; newEnd = newRange; }
            if (newEnd > 100) { newEnd = 100; newStart = 100 - newRange; }
            chart.dispatchAction({
                type: 'dataZoom',
                start: newStart,
                end: newEnd
            });
        }, { passive: false });
        
        // 初始化QWebChannel，用于与Python通信
        if (typeof QWebChannel !== 'undefined') {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                pyBridge = channel.objects.cursorBridge;
            });
        }
        
        // 缩放/平移：dataZoom事件传给Python（暂时关闭，避免阻塞拖动）
        // var _zoomTimer = null;
        // chart.on('dataZoom', function(params) {
        //     if (!pyBridge || typeof pyBridge.onZoomChanged !== 'function') return;
        //     if (_zoomTimer) clearTimeout(_zoomTimer);
        //     _zoomTimer = setTimeout(function() {
        //         var opt = chart.getOption();
        //         if (opt && opt.dataZoom && opt.dataZoom.length > 0) {
        //             pyBridge.onZoomChanged(opt.dataZoom[0].start || 0, opt.dataZoom[0].end || 100);
        //         }
        //     }, 200);
        // });

        // MA标签跟随光标
        chart.on('updateAxisPointer', function(params) {
            // 传递光标位置给Python（用于MACD/KDJ联动）
            var dataIndex = params.dataIndex;
            if (pyBridge && dataIndex !== undefined && dataIndex >= 0 && typeof pyBridge.onCursorChanged === 'function') {
                pyBridge.onCursorChanged(dataIndex);
            }
            
            if (!currentData.ma5) return;
            
            var dataIndex = params.dataIndex;
            if (dataIndex === undefined || dataIndex < 0) {
                // 鼠标移出，恢复最后一天的值
                updateMALabels(
                    currentData.lastMA5,
                    currentData.lastMA10,
                    currentData.lastMA20,
                    currentData.lastMA120
                );
                return;
            }
            
            // 获取光标所在日期的MA值
            var ma5Val = currentData.ma5[dataIndex];
            var ma10Val = currentData.ma10[dataIndex];
            var ma20Val = currentData.ma20[dataIndex];
            var ma120Val = currentData.ma120[dataIndex];
            
            // 处理null值（MA还没计算出来的位置）
            if (ma5Val === null || ma5Val === undefined) ma5Val = 0;
            if (ma10Val === null || ma10Val === undefined) ma10Val = 0;
            if (ma20Val === null || ma20Val === undefined) ma20Val = 0;
            if (ma120Val === null || ma120Val === undefined) ma120Val = 0;
            
            updateMALabels(ma5Val, ma10Val, ma20Val, ma120Val);
        });
        
        // 更新MA标签
        function updateMALabels(ma5, ma10, ma20, ma120) {
            chart.setOption({
                graphic: [
                    { id: 'ma5-label', style: { text: 'MA5: ' + ma5.toFixed(2) } },
                    { id: 'ma10-label', style: { text: 'MA10: ' + ma10.toFixed(2) } },
                    { id: 'ma20-label', style: { text: 'MA20: ' + ma20.toFixed(2) } },
                    { id: 'ma120-label', style: { text: 'MA120: ' + ma120.toFixed(2) } }
                ]
            });
        }
        
        // 计算MA均线
        function calculateMA(dayCount, data) {
            var result = [];
            for (var i = 0; i < data.length; i++) {
                if (i < dayCount - 1) {
                    result.push(null);
                    continue;
                }
                var sum = 0;
                for (var j = 0; j < dayCount; j++) {
                    var k = data[i - j];
                    // 支持数组格式和对象格式
                    var close = Array.isArray(k) ? k[1] : k.value[1];
                    sum += close;
                }
                result.push(sum / dayCount);
            }
            return result;
        }
        
        // 计算均量线
        function calculateVolMA(dayCount, volumes) {
            var result = [];
            for (var i = 0; i < volumes.length; i++) {
                if (i < dayCount - 1) {
                    result.push(null);
                    continue;
                }
                var sum = 0;
                for (var j = 0; j < dayCount; j++) {
                    sum += volumes[i - j];
                }
                result.push(sum / dayCount);
            }
            return result;
        }
        
        // 基础版更新K线
        function updateKline(dates, klineData, volumes) {
            if (!chart) return 'chart不存在';
            
            chart.clear();
            
            currentData = {
                dates: dates,
                kline: klineData,
                volumes: volumes
            };
            

            // 涨跌停特殊颜色处理：涨停紫色实心，跌停黑色实心
            function applyLimitColors(klineArr) {
                if (!klineArr || klineArr.length === 0) return klineArr;
                var result = [];
                for (var i = 0; i < klineArr.length; i++) {
                    var k = klineArr[i];
                    var open, close, high, low;
                    if (Array.isArray(k)) {
                        open = k[0]; close = k[1]; low = k[2]; high = k[3];
                    } else if (k && k.value) {
                        open = k.value[0]; close = k.value[1]; low = k.value[2]; high = k.value[3];
                    } else {
                        result.push(k);
                        continue;
                    }
                    var pct = open > 0 ? (close - open) / open * 100 : 0;
                    // 涨停阈值按板性：主板 10cm -> 9.8；创业板/科创板 20cm -> 19.8。
                    // set_kline_data 会在调用 updateKline 之前设置 window.__limitPct。
                    var luPct = (typeof window.__limitPct === 'number' && window.__limitPct > 0) ? window.__limitPct : 9.8;
                    var isLimitUp = (close === high) && (pct >= luPct);
                    var isLimitDown = (close === low) && (pct <= -luPct);
                    if (isLimitUp) {
                        result.push({ value: [open, close, low, high], itemStyle: { color: '#AF52DE', borderColor: '#AF52DE' } });
                    } else if (isLimitDown) {
                        result.push({ value: [open, close, low, high], itemStyle: { color: '#000000', borderColor: '#000000' } });
                    } else {
                        result.push(k);
                    }
                }
                return result;
            }
            var klineDataWithLimit = applyLimitColors(klineData);

            // 计算MA
            var ma5 = calculateMA(5, klineData);
            var ma10 = calculateMA(10, klineData);
            var ma20 = calculateMA(20, klineData);
            var ma120 = calculateMA(120, klineData);
            
            // 计算均量线
            var volMA20 = calculateVolMA(20, volumes);
            var volMA120 = calculateVolMA(120, volumes);
            
            // 获取最新的均线值（最后一个有效值）
            function getLastValue(arr) {
                for (var i = arr.length - 1; i >= 0; i--) {
                    if (arr[i] !== null && arr[i] !== undefined) {
                        return arr[i];
                    }
                }
                return 0;
            }
            
            var lastMA5 = getLastValue(ma5);
            var lastMA10 = getLastValue(ma10);
            var lastMA20 = getLastValue(ma20);
            var lastMA120 = getLastValue(ma120);
            
            // 保存MA数据到currentData，供光标跟随使用
            currentData.ma5 = ma5;
            currentData.ma10 = ma10;
            currentData.ma20 = ma20;
            currentData.ma120 = ma120;
            currentData.lastMA5 = lastMA5;
            currentData.lastMA10 = lastMA10;
            currentData.lastMA20 = lastMA20;
            currentData.lastMA120 = lastMA120;
            
            var option = {
                backgroundColor: '#FFFFFF',
                animation: false,
                // 左上角均线价格标签
                graphic: [
                    {
                        id: 'ma5-label',
                        type: 'text',
                        left: 65,
                        top: 15,
                        style: {
                            text: 'MA5: ' + lastMA5.toFixed(2),
                            fill: '#000000',
                            fontSize: 11,
                            fontWeight: 'normal'
                        }
                    },
                    {
                        id: 'ma10-label',
                        type: 'text',
                        left: 135,
                        top: 15,
                        style: {
                            text: 'MA10: ' + lastMA10.toFixed(2),
                            fill: '#FFC107',
                            fontSize: 11,
                            fontWeight: 'normal'
                        }
                    },
                    {
                        id: 'ma20-label',
                        type: 'text',
                        left: 210,
                        top: 15,
                        style: {
                            text: 'MA20: ' + lastMA20.toFixed(2),
                            fill: '#FF3B30',
                            fontSize: 11,
                            fontWeight: 'normal'
                        }
                    },
                    {
                        id: 'ma120-label',
                        type: 'text',
                        left: 285,
                        top: 15,
                        style: {
                            text: 'MA120: ' + lastMA120.toFixed(2),
                            fill: '#64748B',
                            fontSize: 11,
                            fontWeight: 'normal'
                        }
                    }
                ],
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'cross',
                        lineStyle: {
                            color: '#86868B',
                            width: 1,
                            type: 'dashed'
                        },
                        label: {
                            show: true,
                            backgroundColor: '#F0F0F0',
                            color: '#000000',
                            fontSize: 11,
                            fontWeight: 'bold'
                        }
                    },
                    backgroundColor: 'rgba(255,255,255,0.98)',
                    borderColor: '#E5E5EA',
                    borderWidth: 1,
                    textStyle: {
                        color: '#1D1D1F',
                        fontSize: 12
                    },
                    formatter: function(params) {
                        try {
                            if (!params || params.length === 0) return '';
                            
                            // 用dataIndex从currentData取原始数据，确保准确
                            var idx = params[0].dataIndex;
                            if (idx < 0 || idx >= currentData.kline.length) return '';
                            
                            var date = currentData.dates[idx] || '';
                            var k = currentData.kline[idx];
                            
                            // 解析K线数据（支持数组格式和对象格式）
                            var open = 0, close = 0, low = 0, high = 0;
                            if (Array.isArray(k)) {
                                open = k[0];
                                close = k[1];
                                low = k[2];
                                high = k[3];
                            } else if (k && k.value) {
                                open = k.value[0];
                                close = k.value[1];
                                low = k.value[2];
                                high = k.value[3];
                            } else {
                                return '';
                            }
                            
                            var change = 0;
                            if (idx > 0) {
                                var prevK = currentData.kline[idx - 1];
                                var prevClose = Array.isArray(prevK) ? prevK[1] : prevK.value[1];
                                if (prevClose > 0) {
                                    change = ((close - prevClose) / prevClose * 100).toFixed(2);
                                }
                            }
                            var color = close >= open ? '#FF3B30' : '#34C759';
                            
                            // V2.7.2：现价（最新一根K线为实时价格，历史K线为收盘价）
                            var isLatest = (idx === currentData.kline.length - 1);
                            var currentPrice = close;  // K线数据已包含今日实时数据
                            var priceColor = isLatest ? '#007AFF' : color;
                            var priceLabel = isLatest ? '现价' : '现价';

                            var html = '<div style="font-weight: bold; margin-bottom: 5px; color: #1D1D1F;">' + date + (isLatest ? ' <span style="color: #007AFF; font-size: 11px;">(实时)</span>' : '') + '</div>';
                            html += '<div style="color: #86868B;">开盘: <span style="color: #1D1D1F;">' + open.toFixed(2) + '</span></div>';
                            html += '<div style="color: #86868B;">' + priceLabel + ': <span style="color: ' + priceColor + '; font-weight: bold;">' + currentPrice.toFixed(2) + '</span></div>';
                            html += '<div style="color: #86868B;">收盘: <span style="color: ' + color + ';">' + close.toFixed(2) + '</span></div>';
                            html += '<div style="color: #86868B;">最高: <span style="color: #FF3B30;">' + high.toFixed(2) + '</span></div>';
                            html += '<div style="color: #86868B;">最低: <span style="color: #34C759;">' + low.toFixed(2) + '</span></div>';
                            html += '<div style="color: ' + color + '; margin-top: 3px;">涨跌幅: ' + (change >= 0 ? '+' : '') + change + '%</div>';
                            
                            // 成交量
                            var volVal = currentData.volumes[idx] || 0;
                            if (volVal > 0) {
                                var volStr = '';
                                if (volVal >= 100000000) {
                                    volStr = (volVal / 100000000).toFixed(2) + '亿';
                                } else if (volVal >= 10000) {
                                    volStr = (volVal / 10000).toFixed(0) + '万';
                                } else {
                                    volStr = volVal.toFixed(0);
                                }
                                html += '<div style="color: #86868B; margin-top: 3px;">成交量: ' + volStr + '</div>';
                            }
                            
                            return html;
                        } catch(e) {
                            return '';
                        }
                    }
                },
                axisPointer: {
                    link: [{xAxisIndex: 'all'}],
                    label: {
                        backgroundColor: '#F5F5F7'
                    }
                },
                grid: [
                    {
                        left: '60px',
                        right: '20px',
                        top: '10px',
                        height: '65%'
                    },
                    {
                        left: '60px',
                        right: '20px',
                        top: '78%',
                        height: '18%'
                    }
                ],
                xAxis: [
                    {
                        type: 'category',
                        data: dates,
                        gridIndex: 0,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 11, fontWeight: 'bold' },
                        splitLine: { show: false },
                        boundaryGap: false,
                        axisPointer: { z: 100 }
                    },
                    {
                        type: 'category',
                        data: dates,
                        gridIndex: 1,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { show: false },
                        splitLine: { show: false },
                        boundaryGap: false
                    }
                ],
                yAxis: [
                    {
                        scale: true,
                        gridIndex: 0,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 11, fontWeight: 'bold' },
                        splitLine: { lineStyle: { color: '#F0F0F0', type: 'dashed' } }
                    },
                    {
                        scale: true,
                        gridIndex: 1,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 10, show: true },
                        splitLine: { show: false }
                    }
                ],
                dataZoom: [
                    {
                        type: 'inside',
                        xAxisIndex: [0, 1],
                        start: 50,
                        end: 100,
                        zoomOnMouseWheel: true,
                        moveOnMouseMove: true,
                        moveOnMouseWheel: false
                    },
                    {
                        type: 'slider',
                        xAxisIndex: [0, 1],
                        start: 50,
                        end: 100,
                        bottom: '0px',
                        height: '15px',
                        borderColor: '#E5E5EA',
                        backgroundColor: '#F5F5F7',
                        fillerColor: 'rgba(88, 166, 255, 0.2)',
                        handleStyle: { color: '#FF3B30' },
                        textStyle: { color: '#86868B' }
                    }
                ],
                series: [
                    {
                        name: '日K',
                        type: 'candlestick',
                        data: klineDataWithLimit,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        itemStyle: {
                            color: '#FF3B30',
                            color0: 'transparent',
                            borderColor: '#FF3B30',
                            borderColor0: '#34C759'
                        }
                    },
                    {
                        name: 'MA5',
                        type: 'line',
                        data: ma5,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { color: '#000000', width: 1.5 }
                    },
                    {
                        name: 'MA10',
                        type: 'line',
                        data: ma10,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { color: '#FFC107', width: 1.5 }
                    },
                    {
                        name: 'MA20',
                        type: 'line',
                        data: ma20,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { color: '#FF3B30', width: 1.5 }
                    },
                    {
                        name: 'MA120',
                        type: 'line',
                        data: ma120,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { color: '#64748B', width: 1.5 }
                    },
                    {
                        name: '成交量',
                        type: 'bar',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: volumes,
                        itemStyle: {
                            color: function(params) {
                                var idx = params.dataIndex;
                                var k = currentData.kline[idx];
                                if (k) {
                                    // 支持数组格式和对象格式
                                    var open = Array.isArray(k) ? k[0] : k.value[0];
                                    var close = Array.isArray(k) ? k[1] : k.value[1];
                                    return close >= open ? '#FF3B30' : '#2563EB';
                                }
                                return '#86868B';
                            }
                        },
                        label: {
                            show: true,
                            position: 'top',
                            color: '#AF52DE',
                            fontSize: 10,
                            formatter: function(params) {
                                var idx = params.dataIndex;
                                if (idx <= 0) return '';
                                var currVol = currentData.volumes[idx];
                                var prevVol = currentData.volumes[idx - 1];
                                if (prevVol > 0 && currVol > 0) {
                                    var ratio = currVol / prevVol;
                                    if (ratio >= 2) {
                                        return Math.floor(ratio) + '倍';
                                    }
                                }
                                return '';
                            }
                        }
                    },
                    {
                        name: 'VOL20',
                        type: 'line',
                        data: volMA20,
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { color: '#ff9800', width: 1.2 }
                    },
                    {
                        name: 'VOL120',
                        type: 'line',
                        data: volMA120,
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        smooth: true,
                        showSymbol: false,
                        lineStyle: { color: '#ab47bc', width: 1.2 }
                    }
                ]
            };
            
            chart.setOption(option);
            return '基础版K线更新成功: ' + klineData.length + '根';
        }
        
        // 分时图更新
        function updateTimeShare(times, prices, avgPrices, volumes, preClose) {
            if (!chart) return 'chart不存在';
            
            chart.clear();
            
            var option = {
                backgroundColor: '#FFFFFF',
                animation: false,
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'cross',
                        lineStyle: {
                            color: '#86868B',
                            width: 1,
                            type: 'dashed'
                        },
                        label: {
                            show: true,
                            backgroundColor: '#F0F0F0',
                            color: '#000000',
                            fontSize: 11,
                            fontWeight: 'bold'
                        }
                    },
                    backgroundColor: 'rgba(255,255,255,0.98)',
                    borderColor: '#E5E5EA',
                    borderWidth: 1,
                    textStyle: {
                        color: '#1D1D1F',
                        fontSize: 12
                    },
                    formatter: function(params) {
                        try {
                            if (!params || params.length === 0) return '';
                            
                            var idx = params[0].dataIndex;
                            var time = times[idx] || '';
                            var price = prices[idx] || 0;
                            var avg = avgPrices[idx] || 0;
                            var vol = volumes[idx] || 0;
                            
                            var change = preClose > 0 ? ((price - preClose) / preClose * 100) : 0;
                            var color = change >= 0 ? '#FF3B30' : '#34C759';
                            
                            var html = '<div style="font-weight: bold; margin-bottom: 5px; color: #1D1D1F;">' + time + '</div>';
                            html += '<div style="color: #86868B;">价格: <span style="color: ' + color + ';">' + price.toFixed(2) + '</span></div>';
                            html += '<div style="color: #86868B;">均价: <span style="color: #AF52DE;">' + avg.toFixed(2) + '</span></div>';
                            html += '<div style="color: ' + color + '; margin-top: 3px;">涨跌幅: ' + (change >= 0 ? '+' : '') + change.toFixed(2) + '%</div>';
                            
                            if (vol > 0) {
                                var volStr = '';
                                if (vol >= 100000000) {
                                    volStr = (vol / 100000000).toFixed(2) + '亿';
                                } else if (vol >= 10000) {
                                    volStr = (vol / 10000).toFixed(0) + '万';
                                } else {
                                    volStr = vol.toFixed(0);
                                }
                                html += '<div style="color: #86868B; margin-top: 3px;">成交量: ' + volStr + '</div>';
                            }
                            
                            return html;
                        } catch(e) {
                            return '';
                        }
                    }
                },
                axisPointer: {
                    link: [{xAxisIndex: 'all'}],
                    label: {
                        backgroundColor: '#F5F5F7'
                    }
                },
                grid: [
                    {
                        left: '60px',
                        right: '20px',
                        top: '10px',
                        height: '65%'
                    },
                    {
                        left: '60px',
                        right: '20px',
                        top: '78%',
                        height: '18%'
                    }
                ],
                xAxis: [
                    {
                        type: 'category',
                        data: times,
                        gridIndex: 0,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 11, fontWeight: 'bold' },
                        splitLine: { show: false }
                    },
                    {
                        type: 'category',
                        data: times,
                        gridIndex: 1,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 11, fontWeight: 'bold' },
                        splitLine: { show: false }
                    }
                ],
                yAxis: [
                    {
                        scale: true,
                        gridIndex: 0,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 11, fontWeight: 'bold' },
                        splitLine: { lineStyle: { color: '#F0F0F0', type: 'dashed' } }
                    },
                    {
                        scale: true,
                        gridIndex: 1,
                        axisLine: { lineStyle: { color: '#E5E5EA' } },
                        axisLabel: { color: '#000000', fontSize: 10, show: true },
                        splitLine: { show: false }
                    }
                ],
                dataZoom: [
                    {
                        type: 'inside',
                        xAxisIndex: [0, 1],
                        start: 0,
                        end: 100,
                        zoomOnMouseWheel: true,
                        moveOnMouseMove: true,
                        moveOnMouseWheel: false
                    },
                    {
                        type: 'slider',
                        xAxisIndex: [0, 1],
                        start: 0,
                        end: 100,
                        height: 15,
                        bottom: 5,
                        borderColor: '#E5E5EA',
                        backgroundColor: '#F5F5F7',
                        fillerColor: 'rgba(88, 166, 255, 0.2)',
                        handleStyle: { color: '#FF3B30' },
                        textStyle: { color: '#86868B' }
                    }
                ],
                series: [
                    {
                        name: '价格',
                        type: 'line',
                        data: prices,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: false,
                        showSymbol: false,
                        lineStyle: { color: '#64748B', width: 1.5 },
                        markLine: {
                            silent: true,
                            symbol: 'none',
                            lineStyle: {
                                color: '#86868B',
                                width: 1,
                                type: 'dashed'
                            },
                            data: [
                                {
                                    yAxis: preClose,
                                    label: {
                                        show: true,
                                        position: 'end',
                                        formatter: '昨收',
                                        color: '#86868B',
                                        fontSize: 10
                                    }
                                }
                            ]
                        }
                    },
                    {
                        name: '均价',
                        type: 'line',
                        data: avgPrices,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: false,
                        showSymbol: false,
                        lineStyle: { color: '#AF52DE', width: 1.2 }
                    },
                    {
                        name: '成交量',
                        type: 'bar',
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        data: volumes,
                        itemStyle: {
                            color: function(params) {
                                var idx = params.dataIndex;
                                if (idx === 0) return '#007AFF';
                                return prices[idx] >= prices[idx - 1] ? '#007AFF' : '#FF3B30';
                            }
                        }
                    }
                ]
            };
            
            chart.setOption(option);
            return '分时图更新成功: ' + times.length + '分钟';
        }
        
        // 清空图表
        function clearChart() {
            if (chart) {
                chart.clear();
            }
        }
        
        // 窗口大小变化时重绘
        window.addEventListener('resize', function() {
            if (chart) {
                chart.resize();
            }
        });
    </script>
</body>
</html>
"""


class CursorBridge(QObject):
    """JavaScript与Python之间的光标位置桥接"""
    cursor_changed = pyqtSignal(int)  # dataIndex变化信号

    @pyqtSlot(int)
    def onCursorChanged(self, index):
        """JavaScript调用此方法通知光标位置变化"""
        self.cursor_changed.emit(index)


class EChartsKlineWidget(QWidget):
    """ECharts专业K线图组件 - 支持多周期数据"""
    
    cursor_index_changed = pyqtSignal(int)  # 光标位置变化信号（供外部连接）
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.web_view = None
        self.current_code = ''
        self.current_period = 'day'
        self.cursor_bridge = CursorBridge()
        self.cursor_bridge.cursor_changed.connect(self._on_cursor_changed)
        # V1.3.12：价格范围，供标注色带使用
        self._price_min = 0
        self._price_max = 0
        self._init_ui()
        self._init_echarts()
    
    def _on_cursor_changed(self, index):
        """光标位置变化时转发信号"""
        self.cursor_index_changed.emit(index)
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet('background: #FFFFFF; border: none;')
        # 确保鼠标事件正常传递给ECharts
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.web_view.setMouseTracking(True)
        # 设置页面背景色，避免透明背景影响鼠标事件
        self.web_view.page().setBackgroundColor(QColor('#FFFFFF'))
        layout.addWidget(self.web_view)
    
    def _on_period_clicked(self, period):
        """周期按钮点击"""
        if period == self.current_period:
            return
        
        # 更新按钮状态
        for p, btn in self.period_buttons.items():
            btn.setChecked(p == period)
        
        self.current_period = period
        print(f"[ECharts] 切换周期: {period}")
        
        # 发出信号
        self.period_changed.emit(period)
        
        # 如果有当前股票代码，自动重新加载
        if self.current_code:
            self.load_kline(self.current_code, period)
    
    def load_kline(self, code, period='day'):
        """加载指定周期的K线数据"""
        self.current_code = code
        self.current_period = period
        
        # 更新按钮状态
        for p, btn in self.period_buttons.items():
            btn.setChecked(p == period)
        
        # 分时图暂时用日K代替，后面单独实现
        if period == 'time':
            # TODO: 分时图实现
            print("[ECharts] 分时图功能开发中...")
            return
        
        # 获取K线数据
        from utils.kline_provider import get_kline_by_period
        count = 500 if period in ['day', 'week', 'month'] else 300
        kline_data = get_kline_by_period(code, count, period)
        
        if kline_data:
            self.set_kline_data(kline_data, code)
            print(f"[ECharts] 加载{period}K线成功: {code}, 共{len(kline_data['close'])}根")
        else:
            print(f"[ECharts] 加载{period}K线失败: {code}")
    
    def _init_echarts(self):
        """初始化ECharts"""
        # 确保data目录存在
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        # 写入HTML文件
        html_path = os.path.join(data_dir, 'echarts_kline.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(ECHARTS_HTML)
        
        # 复制echarts.min.js到data目录
        js_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'echarts.min.js')
        js_dst = os.path.join(data_dir, 'echarts.min.js')
        if os.path.exists(js_src) and not os.path.exists(js_dst):
            import shutil
            shutil.copy(js_src, js_dst)
        
        # 加载HTML
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))
        
        # 设置QWebChannel，用于JavaScript与Python通信
        self.web_channel = QWebChannel(self.web_view.page())
        self.web_channel.registerObject('cursorBridge', self.cursor_bridge)
        self.web_view.page().setWebChannel(self.web_channel)
        
        # 等待页面加载完成
        self.web_view.loadFinished.connect(self._on_load_finished)
    
    def _on_load_finished(self, ok):
        """页面加载完成回调"""
        print(f"[ECharts] 页面加载完成: {ok}")
    
    def set_kline_data(self, kline_data, code=''):
        """设置K线数据
        
        Args:
            kline_data: dict, 包含 dates, open, high, low, close, volume
            code: 可选，股票代码。按板性判定涨停阈值（创业板/科创板 20cm → 19.8），
                  同时回填 current_code，使组件内周期切换按钮可用。
        """
        print(f"[ECharts] ========== set_kline_data被调用 ==========")
        
        try:
            # ========== 第一步：数据校验 ==========
            if not kline_data:
                print("[ECharts] ❌ 数据为空，跳过")
                return
            
            opens = kline_data.get('open', [])
            highs = kline_data.get('high', [])
            lows = kline_data.get('low', [])
            closes = kline_data.get('close', [])
            volumes = kline_data.get('volume', [])
            dates = kline_data.get('dates', [])
            
            data_len = len(closes)
            print(f"[ECharts] 数据长度: {data_len}根")
            
            # 数据长度校验
            if data_len < 50:
                print(f"[ECharts] ❌ 数据不足50根（{data_len}根），跳过")
                return
            
            # 各数组长度一致性校验
            if len(opens) < data_len or len(highs) < data_len or len(lows) < data_len or len(volumes) < data_len:
                print(f"[ECharts] ❌ 数组长度不一致，跳过")
                print(f"  open={len(opens)}, high={len(highs)}, low={len(lows)}, close={len(closes)}, volume={len(volumes)}")
                return
            
            # 如果dates为空，尝试date字段
            if not dates or len(dates) < data_len:
                dates = kline_data.get('date', [])
            
            # 如果还是为空，生成倒推日期（容错）
            if not dates or len(dates) < data_len:
                print(f"[ECharts] ⚠️  dates字段缺失，生成倒推日期序列")
                import datetime
                dates = []
                today = datetime.date.today()
                for i in range(data_len):
                    d = today - datetime.timedelta(days=i)
                    while d.weekday() >= 5:
                        d -= datetime.timedelta(days=1)
                    dates.append(d.strftime('%Y-%m-%d'))
                dates.reverse()
            
            # ========== 第二步：数据格式化 ==========
            kline_list = []
            vol_list = []
            date_list = []
            limit_up_count = 0
            
            # [CYB-GATE] 板性代码：入参 code 优先 → 数据字典 code → 当前已加载代码。
            # （get_kline_by_period() 返回的 dict 不含 code，所以入参才是主要来源。）
            _kline_code = str(code or kline_data.get('code')
                              or getattr(self, 'current_code', '') or '')
            
            for i in range(data_len):
                # 日期格式化
                if i < len(dates):
                    date_str = str(dates[i])
                    if len(date_str) >= 8 and date_str[:8].isdigit():
                        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    elif ' ' in date_str:
                        date_str = date_str.split(' ')[0]
                    elif len(date_str) > 10 and date_str[4] == '-' and date_str[7] == '-':
                        date_str = date_str[:10]
                    date_list.append(date_str)
                else:
                    date_list.append(str(i))
                
                # K线数据
                try:
                    open_p = float(opens[i])
                    close_p = float(closes[i])
                    low_p = float(lows[i])
                    high_p = float(highs[i])
                    vol_p = float(volumes[i])
                except (ValueError, TypeError) as e:
                    print(f"[ECharts] ⚠️  第{i}根数据转换失败: {e}")
                    open_p = close_p = low_p = high_p = 0
                    vol_p = 0
                
                # 判断是否涨停
                is_limit_up = False
                if i > 0:
                    prev_close = float(closes[i-1])
                    if prev_close > 0:
                        pct = (close_p - prev_close) / prev_close * 100
                        # 主板：>=9.8%，创业板/科创板：>=19.8%
                        if _kline_code.startswith(('300', '301', '688', '689')):
                            if pct >= 19.8:
                                is_limit_up = True
                        else:
                            if pct >= 9.8:
                                is_limit_up = True
                
                if is_limit_up:
                    # 涨停K线：对象格式，带黄色样式
                    limit_up_count += 1
                    kline_list.append({
                        'value': [open_p, close_p, low_p, high_p],
                        'itemStyle': {
                            'color': '#AF52DE',
                            'color0': '#AF52DE',
                            'borderColor': '#AF52DE',
                            'borderColor0': '#AF52DE'
                        }
                    })
                    print(f"[涨停检测] 日期: {date_str}, 涨幅: {pct:.2f}%, 涨停: 是")
                else:
                    # 普通K线：数组格式（保持原样）
                    kline_list.append([open_p, close_p, low_p, high_p])
                
                vol_list.append(vol_p)
            
            print(f"[ECharts] 数据格式化完成，K线:{len(kline_list)}根, 成交量:{len(vol_list)}个, 涨停:{limit_up_count}根")
            print(f"[ECharts] 最后一天: 日期={date_list[-1]}, 开={kline_list[-1]['value'][0] if isinstance(kline_list[-1], dict) else kline_list[-1][0]}, 收={kline_list[-1]['value'][1] if isinstance(kline_list[-1], dict) else kline_list[-1][1]}")
            print(f"[ECharts] 第一天: 日期={date_list[0]}, 开={kline_list[0]['value'][0] if isinstance(kline_list[0], dict) else kline_list[0][0]}, 收={kline_list[0]['value'][1] if isinstance(kline_list[0], dict) else kline_list[0][1]}")

            # V1.3.12：保存价格范围，供标注色带使用
            try:
                self._price_min = float(min(lows))
                self._price_max = float(max(highs))
                print(f"[ECharts] 价格范围: {self._price_min:.2f} ~ {self._price_max:.2f}", flush=True)
            except Exception:
                self._price_min = 0
                self._price_max = 0
            
            # ========== 第三步：更新图表（数据校验通过后才清除旧图） ==========
            # [CYB-GATE] 涨停阈值按板性：创业板/科创板 20cm -> 19.8，其余 9.8
            # 注意：这两行必须在 f-string 之外用 Python 先算好，再作为字面量拼进 JS。
            # （历史事故：曾被误写进 JS 字符串内部 → _lu_pct 未定义 → NameError →
            #   runJavaScript 从不执行 → 日K线图全周期空白。）
            # [CYB-GATE] 涨停阈值按板性（与上面逐根涨停判定共用 _kline_code）
            if _kline_code:
                self.current_code = _kline_code   # 供周期切换按钮复用
            _lu_pct = 19.8 if _kline_code.startswith(('300', '301', '688', '689')) else 9.8
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart) {{
                        return 'chart不存在';
                    }}
                    chart.clear();
                    window.__limitPct = {_lu_pct};
            var result = updateKline(
                        {json.dumps(date_list)},
                        {json.dumps(kline_list)},
                        {json.dumps(vol_list)}
                    );
                    return 'OK: ' + result;
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """
            
            print(f"[KLINE] 开始渲染，数据量: {len(kline_list)}根")
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            print("[KLINE] JS调用已发送")
            
        except Exception as e:
            print(f"[ECharts] ❌ 设置K线数据出错: {e}")
            import traceback
            traceback.print_exc()

    def update_realtime_price(self, price, volume=None):
        """V2.7.2：实时更新最新一根K线的价格和成交量（盘中实时刷新）
        
        Args:
            price: float, 最新价格
            volume: float, 最新成交量（可选，不传则不更新）
        """
        try:
            if not price or price <= 0:
                return
            
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart || !currentData || !currentData.kline || currentData.kline.length === 0) {{
                        return '数据未就绪';
                    }}
                    var idx = currentData.kline.length - 1;
                    var k = currentData.kline[idx];
                    
                    // 更新K线数据（支持数组格式和对象格式）
                    if (Array.isArray(k)) {{
                        k[1] = {price};  // 收盘价=现价
                        if ({price} > k[3]) k[3] = {price};  // 最高
                        if ({price} < k[2]) k[2] = {price};  // 最低
                    }} else if (k && k.value) {{
                        k.value[1] = {price};
                        if ({price} > k.value[3]) k.value[3] = {price};
                        if ({price} < k.value[2]) k.value[2] = {price};
                    }}
                    
                    // 更新成交量
                    if ({volume if volume else 'null'} !== null) {{
                        currentData.volumes[idx] = {volume if volume else 'currentData.volumes[idx]'};
                    }}
                    
                    // 重新设置数据触发刷新
                    chart.setOption({{
                        series: [
                            {{ data: currentData.kline }},
                            {{ data: currentData.volumes }}
                        ]
                    }});
                    
                    return 'OK: 现价更新为 ' + {price};
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """
            
            self.web_view.page().runJavaScript(js_code)
        except Exception as e:
            print(f"[ECharts] 实时价格更新失败: {e}")

    def set_chanlun_data(self, chanlun_data):
        """
        设置缠论结构数据（只显示，不计算）
        Args:
            chanlun_data: dict, 包含 fractals, strokes, zhongshu, signals
        """
        print(f"[ECharts] ========== set_chanlun_data被调用 ==========")

        try:
            if not chanlun_data:
                print("[ECharts] ❌ 缠论数据为空，跳过")
                return

            import json

            # 1. 分型数据 -> scatter series
            fractals = chanlun_data.get('fractals', [])
            top_fractals = []
            bottom_fractals = []
            for f in fractals:
                if f.get('type') == 'top':
                    top_fractals.append([f['date'], f['price']])
                elif f.get('type') == 'bottom':
                    bottom_fractals.append([f['date'], f['price']])

            # 2. 笔数据 -> line series
            strokes = chanlun_data.get('strokes', [])
            stroke_lines = []
            for s in strokes:
                stroke_lines.append([
                    [s['start_date'], s['start_price']],
                    [s['end_date'], s['end_price']],
                ])

            # 3. 中枢数据 -> graphic rectangle
            zhongshu = chanlun_data.get('zhongshu')
            zhongshu_graphics = []
            if zhongshu:
                zhongshu_graphics.append({
                    'type': 'rect',
                    'left': zhongshu['start_date'],
                    'right': zhongshu['end_date'],
                    'top': zhongshu['zg'],
                    'bottom': zhongshu['zd'],
                    'style': {
                        'fill': 'rgba(255, 215, 0, 0.1)',
                        'stroke': 'rgba(255, 215, 0, 0.5)',
                        'lineWidth': 1,
                    },
                    'z': 0,
                })

            # 4. 买卖点数据 -> scatter series
            signals = chanlun_data.get('signals', [])
            buy_signals = []
            sell_signals = []
            for s in signals:
                if s.get('type') == 'buy':
                    # 找对应的日期和价格
                    # 简化：用信号对应的分型位置
                    name = s.get('name', '买点')
                    if '一买' in name:
                        color = '#ff1744'
                    elif '二买' in name:
                        color = '#FF9500'
                    elif '三买' in name:
                        color = '#FF9500'
                    else:
                        color = '#4caf50'
                    # 暂时用最后一个底分型的位置
                    if bottom_fractals:
                        buy_signals.append([bottom_fractals[-1][0], bottom_fractals[-1][1], name, color])
                elif s.get('type') == 'sell':
                    name = s.get('name', '卖点')
                    if '一卖' in name:
                        color = '#00e676'
                    elif '二卖' in name:
                        color = '#00b0ff'
                    elif '三卖' in name:
                        color = '#d500f9'
                    else:
                        color = '#f44336'
                    if top_fractals:
                        sell_signals.append([top_fractals[-1][0], top_fractals[-1][1], name, color])

            # 生成JS代码，增量添加缠论series和graphic
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart) {{
                        return 'chart不存在';
                    }}

                    // 增量添加缠论相关配置
                    var chanlunOption = {{
                        graphic: {json.dumps(zhongshu_graphics)},
                        series: [
                            // 笔方向线
                            {{
                                name: '缠论笔',
                                type: 'line',
                                xAxisIndex: 0,
                                yAxisIndex: 0,
                                data: {json.dumps(stroke_lines)},
                                lineStyle: {{
                                    color: '#ff9800',
                                    width: 1.5,
                                    type: 'dashed',
                                }},
                                symbol: 'none',
                                smooth: false,
                                z: 10,
                            }},
                            // 顶分型
                            {{
                                name: '顶分型',
                                type: 'scatter',
                                xAxisIndex: 0,
                                yAxisIndex: 0,
                                data: {json.dumps(top_fractals)},
                                symbol: 'triangle',
                                symbolSize: 8,
                                symbolRotate: 180,
                                itemStyle: {{
                                    color: '#f44336',
                                }},
                                z: 20,
                            }},
                            // 底分型
                            {{
                                name: '底分型',
                                type: 'scatter',
                                xAxisIndex: 0,
                                yAxisIndex: 0,
                                data: {json.dumps(bottom_fractals)},
                                symbol: 'triangle',
                                symbolSize: 8,
                                itemStyle: {{
                                    color: '#4caf50',
                                }},
                                z: 20,
                            }},
                        ]
                    }};

                    // 合并到现有option（不覆盖原有series）
                    chart.setOption(chanlunOption);

                    return '缠论数据已添加: 分型' + {len(top_fractals) + len(bottom_fractals)} + '个, 笔' + {len(stroke_lines)} + '笔, 中枢' + {len(zhongshu_graphics)} + '个';
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """

            print(f"[ECharts] 缠论数据格式化完成: 分型{len(top_fractals)+len(bottom_fractals)}个, 笔{len(stroke_lines)}笔, 中枢{len(zhongshu_graphics)}个")
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            print("[ECharts] 缠论JS调用已发送")

            self._chanlun_visible = True

        except Exception as e:
            print(f"[ECharts] ❌ 设置缠论数据出错: {e}")
            import traceback
            traceback.print_exc()

    def show_chanlun(self):
        """显示缠论结构"""
        print("[ECharts] 显示缠论结构")
        try:
            js_code = """
            (function() {
                try {
                    if (typeof chart === 'undefined' || !chart) {
                        return 'chart不存在';
                    }
                    // 显示所有缠论相关series
                    var option = chart.getOption();
                    if (option.series) {
                        for (var i = 0; i < option.series.length; i++) {
                            var name = option.series[i].name || '';
                            if (name.indexOf('缠论') >= 0 || name.indexOf('分型') >= 0) {
                                option.series[i].show = true;
                            }
                        }
                    }
                    if (option.graphic) {
                        for (var i = 0; i < option.graphic.length; i++) {
                            option.graphic[i].invisible = false;
                        }
                    }
                    chart.setOption(option);
                    return '缠论已显示';
                } catch(e) {
                    return 'JS错误: ' + e.message;
                }
            })();
            """
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            self._chanlun_visible = True
        except Exception as e:
            print(f"[ECharts] ❌ 显示缠论出错: {e}")

    def hide_chanlun(self):
        """隐藏缠论结构"""
        print("[ECharts] 隐藏缠论结构")
        try:
            js_code = """
            (function() {
                try {
                    if (typeof chart === 'undefined' || !chart) {
                        return 'chart不存在';
                    }
                    // 隐藏所有缠论相关series
                    var option = chart.getOption();
                    if (option.series) {
                        for (var i = 0; i < option.series.length; i++) {
                            var name = option.series[i].name || '';
                            if (name.indexOf('缠论') >= 0 || name.indexOf('分型') >= 0) {
                                option.series[i].show = false;
                            }
                        }
                    }
                    if (option.graphic) {
                        for (var i = 0; i < option.graphic.length; i++) {
                            option.graphic[i].invisible = true;
                        }
                    }
                    chart.setOption(option);
                    return '缠论已隐藏';
                } catch(e) {
                    return 'JS错误: ' + e.message;
                }
            })();
            """
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            self._chanlun_visible = False
        except Exception as e:
            print(f"[ECharts] ❌ 隐藏缠论出错: {e}")

    def is_chanlun_visible(self):
        """缠论是否显示"""
        return getattr(self, '_chanlun_visible', False)

    def set_vision_signals(self, vision_signals):
        """
        设置AI视觉识别信号标记

        Args:
            vision_signals: list, 视觉识别信号列表
                每个信号包含: signal_type, score, date, price, reason, details
        """
        print(f"[ECharts] ========== set_vision_signals被调用 ==========")

        try:
            import json

            if not vision_signals or len(vision_signals) == 0:
                print("[ECharts] 视觉识别信号为空，跳过")
                return

            # 转换为scatter数据
            signal_data = []
            color_map = {
                '五买': '#ff9800',
                '五买失效': '#AEAEB2',
                '底部吸筹': '#4caf50',
                '放量突破': '#2196f3',
                '一阳穿多线': '#9c27b0',
                '缩量回调': '#00bcd4',
                '死叉风险': '#f44336',
            }

            for sig in vision_signals:
                sig_type = sig.get('signal_type', sig.get('type', '信号'))
                color = color_map.get(sig_type, '#ff9800')
                price = sig.get('price', 0)
                date = sig.get('date', '')
                score = sig.get('score', 0)
                reason = sig.get('reason', [])

                # 标记点放在K线下方
                signal_data.append({
                    'name': f'{sig_type}({score}分)',
                    'value': [date, price * 0.98],  # 放在K线下方2%
                    'itemStyle': {'color': color},
                    'label': {
                        'show': True,
                        'formatter': sig_type,
                        'position': 'bottom',
                        'color': color,
                        'fontSize': 10,
                    },
                    'reason': reason,
                })

            # 生成JS代码，添加scatter series
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart) {{
                        return 'chart不存在';
                    }}

                    var visionOption = {{
                        series: [
                            {{
                                name: 'AI视觉信号',
                                type: 'scatter',
                                xAxisIndex: 0,
                                yAxisIndex: 0,
                                data: {json.dumps(signal_data)},
                                symbol: 'pin',
                                symbolSize: 30,
                                label: {{
                                    show: true,
                                    position: 'inside',
                                    formatter: function(params) {{
                                        return params.data.name.split('(')[0];
                                    }},
                                    color: '#fff',
                                    fontSize: 9,
                                }},
                                tooltip: {{
                                    formatter: function(params) {{
                                        var data = params.data;
                                        var reasonText = '';
                                        if (data.reason && data.reason.length > 0) {{
                                            reasonText = '<br/>' + data.reason.join('<br/>');
                                        }}
                                        return data.name + reasonText;
                                    }}
                                }},
                                z: 30,
                            }},
                        ]
                    }};

                    chart.setOption(visionOption);
                    return 'AI视觉信号已添加: {len(signal_data)}个';
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """

            print(f"[ECharts] 视觉识别信号格式化完成: {len(signal_data)}个")
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            print("[ECharts] 视觉识别JS调用已发送")

        except Exception as e:
            print(f"[ECharts] ❌ 设置视觉识别信号出错: {e}")
            import traceback
            traceback.print_exc()

    def set_vision_structure(self, structure_data):
        """
        设置AI结构区域标记（启动K线、洗盘区域、五买位置）

        Args:
            structure_data: dict, 包含:
                - start_kline: 启动K线信息 {date, price, low}
                - pullback_area: 洗盘区域 {start_date, end_date, low, high}
                - buy_point: 五买位置 {date, price}
                - trend_stage: 走势阶段
        """
        print(f"[ECharts] ========== set_vision_structure被调用 ==========")

        try:
            import json

            if not structure_data:
                print("[ECharts] 结构数据为空，跳过")
                return

            graphics = []
            mark_areas = []

            # 1. 启动K线标记（垂直线）
            start_kline = structure_data.get('start_kline')
            if start_kline:
                start_date = start_kline.get('date', '')
                start_price = start_kline.get('price', 0)
                graphics.append({
                    'id': 'start-kline-line',
                    'type': 'line',
                    'shape': {
                        'x1': 0, 'y1': 0,
                        'x2': 0, 'y2': 0,
                    },
                    'style': {
                        'stroke': '#ff9800',
                        'lineWidth': 2,
                        'lineDash': [5, 3],
                    },
                    'z': 15,
                })

            # 2. 洗盘区域（背景矩形）
            pullback_area = structure_data.get('pullback_area')
            if pullback_area:
                start_date = pullback_area.get('start_date', '')
                end_date = pullback_area.get('end_date', '')
                low = pullback_area.get('low', 0)
                high = pullback_area.get('high', 0)
                if start_date and end_date and low > 0 and high > 0:
                    mark_areas.append([
                        {'xAxis': start_date, 'yAxis': low},
                        {'xAxis': end_date, 'yAxis': high},
                    ])

            # 3. 五买位置标记
            buy_point = structure_data.get('buy_point')
            if buy_point:
                buy_date = buy_point.get('date', '')
                buy_price = buy_point.get('price', 0)

            # 4. 走势阶段标签
            trend_stage = structure_data.get('trend_stage', '')
            if trend_stage:
                stage_color = {
                    '调整期': '#4caf50',
                    '启动期': '#ff9800',
                    '主升期': '#f44336',
                    '风险期': '#AEAEB2',
                }.get(trend_stage, '#FF9500')

                graphics.append({
                    'id': 'trend-stage-label',
                    'type': 'text',
                    'right': 10,
                    'top': 40,
                    'style': {
                        'text': f'阶段: {trend_stage}',
                        'fill': stage_color,
                        'fontSize': 12,
                        'fontWeight': 'bold',
                    },
                    'z': 50,
                })

            # 生成JS代码
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart) {{
                        return 'chart不存在';
                    }}

                    var structureOption = {{
                        graphic: {json.dumps(graphics)},
                    }};

                    // 如果有洗盘区域，添加markArea到K线series
                    if ({json.dumps(mark_areas)}.length > 0) {{
                        var option = chart.getOption();
                        if (option.series && option.series.length > 0) {{
                            for (var i = 0; i < option.series.length; i++) {{
                                if (option.series[i].type === 'candlestick') {{
                                    option.series[i].markArea = {{
                                        silent: true,
                                        data: {json.dumps(mark_areas)},
                                        itemStyle: {{
                                            color: 'rgba(255, 152, 0, 0.1)',
                                            borderColor: '#ff9800',
                                            borderWidth: 1,
                                        }},
                                        label: {{
                                            show: true,
                                            formatter: '洗盘区',
                                            position: 'insideTop',
                                            color: '#ff9800',
                                            fontSize: 10,
                                        }},
                                    }};
                                    break;
                                }}
                            }}
                        }}
                        chart.setOption(option);
                    }}

                    chart.setOption(structureOption);
                    return 'AI结构标记已添加';
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """

            print(f"[ECharts] AI结构标记格式化完成")
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            print("[ECharts] AI结构JS调用已发送")

        except Exception as e:
            print(f"[ECharts] ❌ 设置AI结构标记出错: {e}")
            import traceback
            traceback.print_exc()

    def set_annotations(self, annotations: dict, show_regions: bool = False, show_signals: bool = False):
        """V1.3.13：设置K线图标注叠加（默认只显示支撑/压力位线，不显示6色区域和买卖点标记）

        Args:
            annotations: dict, 包含:
                - regions: list, 6色区域
                - markers: list, 买卖点
                - support: float, 支撑位
                - resistance: float, 压力位
            show_regions: bool, 是否显示6色区域色带（默认False，V1.3.13用户要求移除）
            show_signals: bool, 是否显示买卖点标记（默认False，V1.3.13用户要求移除）
        """
        print(f"[ECharts] ========== set_annotations被调用 (show_regions={show_regions}, show_signals={show_signals}) ==========", flush=True)

        try:
            if not annotations:
                print("[ECharts] ❌ 标注数据为空，跳过", flush=True)
                return

            import json

            regions = annotations.get('regions', [])
            markers = annotations.get('markers', [])
            support = annotations.get('support', 0)
            resistance = annotations.get('resistance', 0)

            print(f"[ECharts] 标注数据: 区域{len(regions)}个, 标记{len(markers)}个, "
                  f"支撑={support}, 压力={resistance}", flush=True)

            # ========== 1. markArea: 6色区域（V1.3.13：默认不显示，show_regions=True时才显示） ==========
            mark_areas = []
            if show_regions:
                # 计算顶部色带Y轴范围（占价格范围顶部5%）
                price_min = getattr(self, '_price_min', 0)
                price_max = getattr(self, '_price_max', 0)
                if price_max > price_min and price_max > 0:
                    band_height = (price_max - price_min) * 0.05
                    band_low = price_max - band_height
                    band_high = price_max
                else:
                    band_low = 0
                    band_high = 0
                print(f"[ECharts] 顶部色带范围: {band_low:.2f} ~ {band_high:.2f}", flush=True)

                for region in regions:
                    start_date = region.get('start_date', '')
                    end_date = region.get('end_date', '')
                    color = region.get('color', '#86868B')
                    label = region.get('label', '')
                    if not start_date or not end_date:
                        continue
                    start_fmt = self._format_date(start_date)
                    end_fmt = self._format_date(end_date)
                    rgba_color = self._hex_to_rgba(color, 0.3)
                    if band_high > 0:
                        mark_areas.append([
                            {
                                'xAxis': start_fmt,
                                'yAxis': band_low,
                                'itemStyle': {'color': rgba_color, 'borderColor': color, 'borderWidth': 0.5},
                                'label': {'show': True, 'formatter': label, 'position': 'insideTop',
                                          'color': color, 'fontSize': 9, 'fontWeight': 'bold'}
                            },
                            {
                                'xAxis': end_fmt,
                                'yAxis': band_high
                            }
                        ])
                    else:
                        mark_areas.append([
                            {
                                'xAxis': start_fmt,
                                'itemStyle': {'color': rgba_color, 'borderColor': color, 'borderWidth': 0.5},
                                'label': {'show': True, 'formatter': label, 'position': 'insideTop',
                                          'color': color, 'fontSize': 9, 'fontWeight': 'bold'}
                            },
                            {'xAxis': end_fmt}
                        ])

            # ========== 2. markPoint: 买卖点标记（V1.3.13：默认不显示，show_signals=True时才显示） ==========
            mark_points = []
            if show_signals:
                for marker in markers:
                    mtype = marker.get('type', '')
                    level = marker.get('level', '')
                    date = marker.get('date', '')
                    price = marker.get('price', 0)
                    label_text = marker.get('label', level)
                    if not date or not price:
                        continue
                    date_fmt = self._format_date(date)
                    # 买点绿色，卖点红色
                    if mtype == 'buy':
                        symbol_color = '#22c55e'
                        symbol = 'pin'
                    elif mtype == 'sell':
                        symbol_color = '#ef4444'
                        symbol = 'pin'
                    elif mtype == 'risk':
                        symbol_color = '#f59e0b'
                        symbol = 'diamond'
                    else:
                        symbol_color = '#3b82f6'
                        symbol = 'circle'
                    mark_points.append({
                        'name': label_text,
                        'coord': [date_fmt, float(price)],
                        'value': level or label_text[:4],
                        'symbol': symbol,
                        'symbolSize': 32,
                        'itemStyle': {'color': symbol_color, 'borderColor': '#fff', 'borderWidth': 1},
                        'label': {'show': True, 'formatter': level or label_text[:4],
                                  'color': '#fff', 'fontSize': 9, 'fontWeight': 'bold', 'position': 'inside'}
                    })

            # ========== 3. markLine: 支撑/压力位 ==========
            mark_lines = []
            if support and float(support) > 0:
                mark_lines.append({
                    'name': '支撑',
                    'yAxis': float(support),
                    'lineStyle': {'color': '#22c55e', 'type': 'dashed', 'width': 1.5},
                    'label': {'show': True, 'formatter': f'支撑: {float(support):.2f}',
                              'color': '#22c55e', 'fontSize': 10, 'position': 'insideEndTop'}
                })
            if resistance and float(resistance) > 0:
                mark_lines.append({
                    'name': '压力',
                    'yAxis': float(resistance),
                    'lineStyle': {'color': '#ef4444', 'type': 'dashed', 'width': 1.5},
                    'label': {'show': True, 'formatter': f'压力: {float(resistance):.2f}',
                              'color': '#ef4444', 'fontSize': 10, 'position': 'insideEndTop'}
                })

            print(f"[ECharts] 标注格式化: markArea={len(mark_areas)}, markPoint={len(mark_points)}, markLine={len(mark_lines)}", flush=True)
            if mark_areas:
                print(f"[ECharts] 第一个区域: {mark_areas[0][0].get('xAxis')} ~ {mark_areas[0][1].get('xAxis')}", flush=True)

            # ========== 4. 生成JS代码，直接setOption更新candlestick series ==========
            # V1.3.11：使用部分更新方式，不通过getOption/setOption整个option
            # candlestick series是index=0
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart) {{
                        return 'chart不存在';
                    }}

                    var markAreaData = {json.dumps(mark_areas)};
                    var markPointData = {json.dumps(mark_points)};
                    var markLineData = {json.dumps(mark_lines)};

                    // 直接setOption部分更新series[0]（candlestick）
                    var seriesUpdate = {{}};

                    if (markAreaData.length > 0) {{
                        seriesUpdate.markArea = {{
                            silent: true,
                            z: 1,
                            data: markAreaData
                        }};
                    }} else {{
                        seriesUpdate.markArea = {{ show: false, data: [] }};
                    }}

                    if (markPointData.length > 0) {{
                        seriesUpdate.markPoint = {{
                            symbol: 'pin',
                            symbolSize: 32,
                            data: markPointData,
                            z: 10
                        }};
                    }} else {{
                        seriesUpdate.markPoint = {{ show: false, data: [] }};
                    }}

                    if (markLineData.length > 0) {{
                        seriesUpdate.markLine = {{
                            silent: true,
                            symbol: 'none',
                            z: 5,
                            data: markLineData
                        }};
                    }} else {{
                        seriesUpdate.markLine = {{ show: false, data: [] }};
                    }}

                    chart.setOption({{
                        series: [seriesUpdate]
                    }});

                    return '标注已添加: 区域' + markAreaData.length + ', 标记' + markPointData.length + ', 线' + markLineData.length;
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """

            print(f"[ECharts] 标注JS代码生成完成", flush=True)
            self.web_view.page().runJavaScript(js_code, self._on_annotation_result)
            print("[ECharts] 标注JS调用已发送", flush=True)

        except Exception as e:
            print(f"[ECharts] ❌ 设置标注出错: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _on_annotation_result(self, result):
        """V1.3.11：标注JS执行结果回调"""
        print(f"[ECharts] 标注JS执行结果: {result}", flush=True)
        if result and '错误' in str(result):
            print(f"[ECharts] ⚠️ 标注叠加可能失败: {result}", flush=True)

    def _format_date(self, date_str: str) -> str:
        """V1.3.9：日期格式转换 20260820 -> 2026-08-20"""
        if not date_str:
            return ''
        date_str = str(date_str).strip()
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        if '-' in date_str:
            return date_str
        return date_str

    def _hex_to_rgba(self, hex_color: str, alpha: float = 0.15) -> str:
        """V1.3.9：十六进制颜色转rgba半透明"""
        try:
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 3:
                hex_color = ''.join(c * 2 for c in hex_color)
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f'rgba({r}, {g}, {b}, {alpha})'
        except Exception:
            return f'rgba(136, 136, 136, {alpha})'

    def set_time_share_data(self, time_share_data):
        """设置分时图数据
        
        Args:
            time_share_data: dict, 包含 times, prices, avg_prices, volumes, pre_close
        """
        print(f"[ECharts] ========== set_time_share_data被调用 ==========")
        
        try:
            if not time_share_data:
                print("[ECharts] ❌ 分时数据为空，跳过")
                return
            
            times = time_share_data.get('times', [])
            prices = time_share_data.get('prices', [])
            avg_prices = time_share_data.get('avg_prices', [])
            volumes = time_share_data.get('volumes', [])
            pre_close = time_share_data.get('pre_close', 0)
            
            data_len = len(times)
            print(f"[ECharts] 分时数据长度: {data_len}分钟")
            
            if data_len < 10:
                print(f"[ECharts] ❌ 分时数据不足10分钟，跳过")
                return
            
            # 调用JavaScript更新图表
            print(f"[KLINE] 开始渲染分时图，数据量: {data_len}分钟")
            js_code = f"""
            (function() {{
                try {{
                    if (typeof chart === 'undefined' || !chart) {{
                        return 'chart不存在';
                    }}
                    chart.clear();
                    var result = updateTimeShare(
                        {json.dumps(times)},
                        {json.dumps(prices)},
                        {json.dumps(avg_prices)},
                        {json.dumps(volumes)},
                        {pre_close}
                    );
                    return 'OK: ' + result;
                }} catch(e) {{
                    return 'JS错误: ' + e.message;
                }}
            }})();
            """
            
            self.web_view.page().runJavaScript(js_code, self._on_js_result)
            print("[ECharts] 分时图JS调用已发送")
            
        except Exception as e:
            print(f"[ECharts] ❌ 设置分时数据出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_js_result(self, result):
        """JS执行结果回调"""
        print(f"[KLINE] 渲染完成，结果: {result}")
