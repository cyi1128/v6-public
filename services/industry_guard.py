# -*- coding: utf-8 -*-
"""
V2.7.2 行业推送前强制拦截机制
在AI520实时监控推送前，对信号中的行业字段进行三层强校验
拦截不通过的股票不推送，自动重取正确行业后重试
"""
import os
import json
from datetime import datetime
from typing import Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')


class IndustryGuard:
    """行业推送前拦截器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._daily_error_count = 0
        self._daily_errors = []
        self._last_reset_date = None
        self._industry_service = None

    def _get_industry_service(self):
        """获取行业过滤服务（懒加载）"""
        if self._industry_service is None:
            from services.industry_filter_service import get_industry_filter_service
            self._industry_service = get_industry_filter_service()
        return self._industry_service

    def _reset_daily_if_needed(self):
        """每日重置错误计数"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self._last_reset_date != today:
            self._last_reset_date = today
            self._daily_error_count = 0
            self._daily_errors = []

    def check_push_content(self, signal: Dict) -> Dict:
        """
        检查推送信号中的行业字段
        Args:
            signal: 推送信号字典，需包含 code, name, industry
        Returns:
            {'blocked': bool, 'reason': str, 'corrected_industry': str}
        """
        self._reset_daily_if_needed()

        code = signal.get('code', '')
        name = signal.get('name', '')
        industry = signal.get('industry', '')

        if not code:
            return {'blocked': True, 'reason': '股票代码为空', 'corrected_industry': ''}

        # 如果信号中没有行业，尝试从行业服务获取
        if not industry:
            try:
                svc = self._get_industry_service()
                industry, status = svc.get_industry(code, name)
                if industry and status == 'OK':
                    signal['industry'] = industry
                    return {'blocked': False, 'reason': '', 'corrected_industry': industry}
                else:
                    return {'blocked': True, 'reason': f'行业获取失败({status})', 'corrected_industry': ''}
            except Exception as e:
                return {'blocked': True, 'reason': f'行业服务异常: {e}', 'corrected_industry': ''}

        # 调用三层校验
        try:
            svc = self._get_industry_service()
            is_valid, reason, corrected = svc.validate_industry(code, name, industry)

            if not is_valid:
                # 校验不通过，记录错误
                self.log_industry_error(code, name, industry, corrected)

                # 尝试重新获取正确行业
                if corrected:
                    # 校验方法已给出修正值
                    signal['industry'] = corrected
                    return {
                        'blocked': True,
                        'reason': reason,
                        'corrected_industry': corrected,
                    }

                # 尝试从full_map重新获取
                try:
                    new_industry, status = svc.get_industry(code, name)
                    if new_industry and status == 'OK':
                        signal['industry'] = new_industry
                        return {
                            'blocked': True,
                            'reason': f'{reason}，已重取为{new_industry}',
                            'corrected_industry': new_industry,
                        }
                except Exception:
                    pass

                return {
                    'blocked': True,
                    'reason': reason,
                    'corrected_industry': '',
                }

            return {'blocked': False, 'reason': '', 'corrected_industry': industry}

        except Exception as e:
            return {'blocked': True, 'reason': f'校验异常: {e}', 'corrected_industry': ''}

    def log_industry_error(self, code: str, name: str, wrong_industry: str, correct_industry: str):
        """
        写入错误告警日志到 logs/industry_error_YYYYMMDD.log
        单日行业错误≥3次时，自动生成汇总告警日志
        """
        self._reset_daily_if_needed()
        self._daily_error_count += 1
        self._daily_errors.append({
            'code': code,
            'name': name,
            'wrong': wrong_industry,
            'correct': correct_industry,
            'time': datetime.now().strftime('%H:%M:%S'),
        })

        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            today = datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(LOG_DIR, f'industry_error_{today}.log')

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            line = (f'[{timestamp}] 行业错误: {code} {name} '
                    f'错误行业="{wrong_industry}" 正确行业="{correct_industry}"\n')

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line)

            # 单日错误≥3次时生成汇总告警
            if self._daily_error_count >= 3 and self._daily_error_count % 3 == 0:
                self._generate_summary_alert(today)

        except Exception as e:
            print(f"[IndustryGuard] 写日志失败: {e}", flush=True)

    def _generate_summary_alert(self, today: str):
        """生成汇总告警日志"""
        try:
            summary_file = os.path.join(LOG_DIR, f'industry_error_summary_{today}.log')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            lines = [
                f'{"="*60}',
                f'行业错误汇总告警 - {timestamp}',
                f'今日累计错误: {self._daily_error_count}次',
                f'{"="*60}',
            ]
            for err in self._daily_errors:
                lines.append(
                    f'  [{err["time"]}] {err["code"]} {err["name"]}: '
                    f'{err["wrong"]} → {err["correct"]}'
                )
            lines.append(f'{"="*60}\n')

            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            print(f"[IndustryGuard] 汇总告警已生成: {summary_file} "
                  f"(今日{self._daily_error_count}次错误)", flush=True)

        except Exception as e:
            print(f"[IndustryGuard] 生成汇总告警失败: {e}", flush=True)

    def get_daily_stats(self) -> Dict:
        """获取今日错误统计"""
        self._reset_daily_if_needed()
        return {
            'daily_error_count': self._daily_error_count,
            'daily_errors': self._daily_errors,
        }


# 单例
def get_industry_guard() -> IndustryGuard:
    return IndustryGuard()
