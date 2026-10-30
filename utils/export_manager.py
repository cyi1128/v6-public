"""
股票扫描结果导出模块
支持 TXT / CSV / JSON 格式
"""
import json
import csv
from datetime import datetime
import os


class ExportManager:
    """导出管理器"""

    def __init__(self, export_dir='exports'):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    def export(self, stocks_data, format_type='txt', filename=None):
        """
        导出股票数据
        stocks_data: 股票数据列表，每个元素包含：
            - ts_code, name, price, total_score, signals,
              chan_status, tv_status, risk_level, catalysts,
              suggestion, update_time
        format_type: txt/csv/json
        filename: 自定义文件名（不含扩展名）
        """
        if not stocks_data:
            return None, '没有数据可导出'

        if filename is None:
            filename = f'scan_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

        filepath = os.path.join(self.export_dir, f'{filename}.{format_type}')

        try:
            if format_type == 'txt':
                self._export_txt(stocks_data, filepath)
            elif format_type == 'csv':
                self._export_csv(stocks_data, filepath)
            elif format_type == 'json':
                self._export_json(stocks_data, filepath)
            else:
                return None, f'不支持的格式: {format_type}'

            return filepath, f'导出成功: {filepath}'
        except Exception as e:
            return None, f'导出失败: {str(e)}'

    def _export_txt(self, stocks_data, filepath):
        """导出为TXT格式"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('=' * 80 + '\n')
            f.write('量化盯盘系统 V6.0 Pro - 股票扫描结果\n')
            f.write(f'导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'股票数量: {len(stocks_data)}\n')
            f.write('=' * 80 + '\n\n')

            for i, stock in enumerate(stocks_data, 1):
                f.write(f'【{i}】{stock.get("name", "")} ({stock.get("ts_code", "")})\n')
                f.write('-' * 60 + '\n')
                f.write(f'  当前价格: {stock.get("price", 0):.2f} 元\n')
                f.write(f'  综合评分: {stock.get("total_score", 0)} 分\n')
                f.write(f'  趋势状态: {stock.get("trend_status", "-")}\n')
                f.write(f'  缠论状态: {stock.get("chan_status", "-")}\n')
                f.write(f'  三倍量状态: {stock.get("tv_status", "-")}\n')
                f.write(f'  风险等级: {stock.get("risk_level", "-")}\n')

                signals = stock.get('signals', [])
                if signals:
                    sig_names = [s.get('name', '') for s in signals if isinstance(s, dict)]
                    if not sig_names:
                        sig_names = signals
                    f.write(f'  买卖信号: {", ".join(sig_names)}\n')

                catalysts = stock.get('catalysts', [])
                if catalysts:
                    f.write(f'  催化因素: {", ".join(catalysts)}\n')

                f.write(f'  操作建议: {stock.get("suggestion", "-")}\n')
                f.write(f'  更新时间: {stock.get("update_time", "-")}\n')
                f.write('\n')

            f.write('=' * 80 + '\n')
            f.write('免责声明: 本系统仅供参考，不构成投资建议。股市有风险，投资需谨慎。\n')

    def _export_csv(self, stocks_data, filepath):
        """导出为CSV格式"""
        fieldnames = [
            '序号', '股票代码', '股票名称', '当前价格', '综合评分',
            '趋势状态', '缠论状态', '三倍量状态', '风险等级',
            '买卖信号', '催化因素', '操作建议', '更新时间'
        ]

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for i, stock in enumerate(stocks_data, 1):
                signals = stock.get('signals', [])
                if signals and isinstance(signals[0], dict):
                    sig_names = '|'.join([s.get('name', '') for s in signals])
                else:
                    sig_names = '|'.join(signals) if signals else ''

                catalysts = stock.get('catalysts', [])
                catalyst_str = '|'.join(catalysts) if catalysts else ''

                writer.writerow({
                    '序号': i,
                    '股票代码': stock.get('ts_code', ''),
                    '股票名称': stock.get('name', ''),
                    '当前价格': f'{stock.get("price", 0):.2f}',
                    '综合评分': stock.get('total_score', 0),
                    '趋势状态': stock.get('trend_status', ''),
                    '缠论状态': stock.get('chan_status', ''),
                    '三倍量状态': stock.get('tv_status', ''),
                    '风险等级': stock.get('risk_level', ''),
                    '买卖信号': sig_names,
                    '催化因素': catalyst_str,
                    '操作建议': stock.get('suggestion', ''),
                    '更新时间': stock.get('update_time', ''),
                })

    def _export_json(self, stocks_data, filepath):
        """导出为JSON格式"""
        export_data = {
            'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stock_count': len(stocks_data),
            'stocks': []
        }

        for stock in stocks_data:
            signals = stock.get('signals', [])
            # 转换信号为可序列化格式
            serializable_signals = []
            for sig in signals:
                if isinstance(sig, dict):
                    serializable_signals.append({
                        'name': sig.get('name', ''),
                        'type': sig.get('type', ''),
                        'score': sig.get('score', 0),
                        'description': sig.get('description', ''),
                    })
                else:
                    serializable_signals.append(str(sig))

            export_data['stocks'].append({
                'ts_code': stock.get('ts_code', ''),
                'name': stock.get('name', ''),
                'price': stock.get('price', 0),
                'total_score': stock.get('total_score', 0),
                'technical_score': stock.get('technical_score', 0),
                'chan_score': stock.get('chan_score', 0),
                'triple_volume_score': stock.get('triple_volume_score', 0),
                'fundamental_score': stock.get('fundamental_score', 0),
                'trend_status': stock.get('trend_status', ''),
                'chan_status': stock.get('chan_status', ''),
                'tv_status': stock.get('tv_status', ''),
                'risk_level': stock.get('risk_level', ''),
                'signals': serializable_signals,
                'catalysts': stock.get('catalysts', []),
                'suggestion': stock.get('suggestion', ''),
                'buy_price': stock.get('buy_price', 0),
                'stop_loss': stock.get('stop_loss', 0),
                'target_price': stock.get('target_price', 0),
                'update_time': stock.get('update_time', ''),
            })

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def export_signal_log(self, signal_logs, format_type='txt'):
        """导出信号日志"""
        if not signal_logs:
            return None, '没有信号日志可导出'

        filename = f'signal_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        filepath = os.path.join(self.export_dir, f'{filename}.{format_type}')

        try:
            if format_type == 'txt':
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write('=' * 60 + '\n')
                    f.write('信号触发记录\n')
                    f.write(f'导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                    f.write('=' * 60 + '\n\n')

                    for log in signal_logs:
                        f.write(f'[{log.get("time", "")}] ')
                        f.write(f'{log.get("name", "")}({log.get("ts_code", "")}) ')
                        f.write(f'价格:{log.get("price", 0):.2f} ')
                        f.write(f'信号:{log.get("signal", "")}\n')
                        if log.get('reason'):
                            f.write(f'  原因: {log["reason"]}\n')
                        f.write('\n')

            return filepath, f'导出成功: {filepath}'
        except Exception as e:
            return None, f'导出失败: {str(e)}'
