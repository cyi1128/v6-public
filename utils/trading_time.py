"""
交易时间判断工具
判断当前是否是A股交易时间
"""
from datetime import datetime, time


# 测试模式设置
TEST_MODE = False
TEST_DATETIME = None  # 测试用的模拟时间


def set_test_mode(enabled: bool, test_datetime: datetime = None):
    """设置测试模式
    
    Args:
        enabled: 是否启用测试模式
        test_datetime: 测试用的模拟时间
    """
    global TEST_MODE, TEST_DATETIME
    TEST_MODE = enabled
    TEST_DATETIME = test_datetime
    if enabled:
        print(f"[交易时间] 测试模式已启用，模拟时间: {test_datetime}")
    else:
        print("[交易时间] 测试模式已关闭，使用真实时间")


def _get_now():
    """获取当前时间（测试模式下返回模拟时间）"""
    if TEST_MODE and TEST_DATETIME:
        return TEST_DATETIME
    return datetime.now()


def is_trading_day():
    """判断是否是交易日（周一至周五）
    
    注意：暂未处理节假日，后续可接入节假日接口
    
    Returns:
        bool: 是否是交易日
    """
    now = _get_now()
    # 周一=0, 周二=1, ..., 周五=4, 周六=5, 周日=6
    weekday = now.weekday()
    return weekday < 5  # 周一至周五


def is_trading_time():
    """判断当前是否在交易时间内
    
    交易时间：
    - 上午：9:30 - 11:30
    - 下午：13:00 - 15:00
    
    Returns:
        bool: 是否在交易时间
    """
    # 先判断是否是交易日
    if not is_trading_day():
        return False
    
    now = _get_now()
    current_time = now.time()
    
    # 上午交易时间：9:30 - 11:30
    morning_start = time(9, 30)
    morning_end = time(11, 30)
    
    # 下午交易时间：13:00 - 15:00
    afternoon_start = time(13, 0)
    afternoon_end = time(15, 0)
    
    # 判断是否在交易时间段
    in_morning = morning_start <= current_time <= morning_end
    in_afternoon = afternoon_start <= current_time <= afternoon_end
    
    return in_morning or in_afternoon


def get_trading_status():
    """获取交易状态
    
    Returns:
        str: 交易状态（交易中/休市/非交易日）
    """
    if not is_trading_day():
        return "非交易日"
    
    now = _get_now()
    current_time = now.time()
    
    morning_start = time(9, 30)
    morning_end = time(11, 30)
    afternoon_start = time(13, 0)
    afternoon_end = time(15, 0)
    
    if morning_start <= current_time <= morning_end:
        return "上午交易中"
    elif afternoon_start <= current_time <= afternoon_end:
        return "下午交易中"
    elif current_time < morning_start:
        return "盘前"
    elif morning_end < current_time < afternoon_start:
        return "午间休市"
    elif current_time > afternoon_end:
        return "已收盘"
    else:
        return "未知"


def get_next_trading_time():
    """获取下一个交易时间（用于显示倒计时）
    
    Returns:
        str: 下一个交易时间描述
    """
    if is_trading_time():
        return "交易中"
    
    now = _get_now()
    current_time = now.time()
    
    morning_start = time(9, 30)
    morning_end = time(11, 30)
    afternoon_start = time(13, 0)
    
    if not is_trading_day():
        # 非交易日，找下一个周一
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        return f"下周一 09:30 开盘"
    
    # 交易日
    if current_time < morning_start:
        return "今天 09:30 开盘"
    elif morning_end < current_time < afternoon_start:
        return "今天 13:00 开盘"
    elif current_time > time(15, 0):
        # 已收盘，看明天
        if now.weekday() == 4:  # 周五
            return "下周一 09:30 开盘"
        else:
            return "明天 09:30 开盘"
    else:
        return "交易中"
