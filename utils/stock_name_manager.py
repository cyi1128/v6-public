# -*- coding: utf-8 -*-
"""
全市场股票名称管理
从通达信获取A股股票列表，构建名称->代码映射，用于新闻高亮
缓存到本地文件，每天更新一次
"""
import os
import json
import time
from datetime import datetime


# 缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CACHE_FILE = os.path.join(CACHE_DIR, 'stock_names_cache.json')

# 缓存有效期（秒）- 1天
CACHE_EXPIRE = 86400


def _ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def load_cached_stock_names():
    """
    从缓存文件加载股票名称字典

    Returns:
        dict: {name: code} 或 None（缓存不存在或过期）
    """
    try:
        if not os.path.exists(CACHE_FILE):
            return None

        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 检查是否过期
        cache_time = data.get('timestamp', 0)
        if time.time() - cache_time > CACHE_EXPIRE:
            return None

        return data.get('stock_names', {})
    except Exception:
        return None


def save_stock_names_cache(stock_names):
    """
    保存股票名称字典到缓存文件

    Args:
        stock_names: dict {name: code}
    """
    try:
        _ensure_cache_dir()
        data = {
            'timestamp': time.time(),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'count': len(stock_names),
            'stock_names': stock_names
        }
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_all_stock_names():
    """
    从通达信获取全市场A股股票名称

    Returns:
        dict: {name: code}
    """
    try:
        from pytdx.hq import TdxHq_API

        api = TdxHq_API()
        if not api.connect('180.153.18.170', 7709, time_out=10):
            return {}

        stock_names = {}

        try:
            # A股代码前缀
            a_share_prefixes = ('000', '001', '002', '003', '300', '301',
                                '600', '601', '603', '605', '688')

            # 遍历深圳市场
            count_sz = api.get_security_count(0)
            for i in range(0, count_sz, 1000):
                data = api.get_security_list(0, i)
                if not data:
                    continue
                for item in data:
                    code = item.get('code', '')
                    name = item.get('name', '')
                    if not code or not name:
                        continue
                    if not code.startswith(a_share_prefixes):
                        continue
                    # 清理名称中的空格和特殊字符
                    clean_name = name.replace(' ', '').replace('　', '')
                    # 全角A转半角A
                    clean_name = clean_name.replace('Ａ', 'A').replace('Ｂ', 'B')
                    if len(clean_name) < 2:
                        continue
                    stock_names[clean_name] = code

                    # 处理带A/B的股票，也保存去掉后缀的版本
                    if len(clean_name) > 2 and clean_name[-1] in ('A', 'B'):
                        short_name = clean_name[:-1]
                        if len(short_name) >= 2 and short_name not in stock_names:
                            stock_names[short_name] = code

                    # 处理ST股票，也保存去掉ST的名称
                    if clean_name.startswith('*ST') or clean_name.startswith('ST'):
                        clean_st = clean_name.replace('*ST', '').replace('ST', '').strip()
                        if len(clean_st) >= 2 and clean_st not in stock_names:
                            stock_names[clean_st] = code

            # 遍历上海市场
            count_sh = api.get_security_count(1)
            for i in range(0, count_sh, 1000):
                data = api.get_security_list(1, i)
                if not data:
                    continue
                for item in data:
                    code = item.get('code', '')
                    name = item.get('name', '')
                    if not code or not name:
                        continue
                    if not code.startswith(a_share_prefixes):
                        continue
                    clean_name = name.replace(' ', '').replace('　', '')
                    clean_name = clean_name.replace('Ａ', 'A').replace('Ｂ', 'B')
                    if len(clean_name) < 2:
                        continue
                    stock_names[clean_name] = code

                    if len(clean_name) > 2 and clean_name[-1] in ('A', 'B'):
                        short_name = clean_name[:-1]
                        if len(short_name) >= 2 and short_name not in stock_names:
                            stock_names[short_name] = code

                    if clean_name.startswith('*ST') or clean_name.startswith('ST'):
                        clean_st = clean_name.replace('*ST', '').replace('ST', '').strip()
                        if len(clean_st) >= 2 and clean_st not in stock_names:
                            stock_names[clean_st] = code

        finally:
            api.disconnect()

        return stock_names
    except Exception as e:
        print(f"获取全市场股票名称失败: {e}")
        return {}


def get_all_stock_names(force_refresh=False):
    """
    获取全市场股票名称字典（优先缓存）

    Args:
        force_refresh: 是否强制刷新（忽略缓存）

    Returns:
        dict: {name: code}
    """
    # 尝试加载缓存
    if not force_refresh:
        cached = load_cached_stock_names()
        if cached:
            return cached

    # 从通达信获取
    stock_names = fetch_all_stock_names()

    # 保存到缓存
    if stock_names:
        save_stock_names_cache(stock_names)

    return stock_names


# 内置的常见股票名称（作为兜底，即使通达信获取失败也能高亮常见股票）
BUILTIN_STOCKS = {
    '贵州茅台': '600519', '宁德时代': '300750', '比亚迪': '002594',
    '中国平安': '601318', '招商银行': '600036', '五粮液': '000858',
    '美的集团': '000333', '格力电器': '000651', '海尔智家': '600690',
    '恒瑞医药': '600276', '药明康德': '603259', '迈瑞医疗': '300760',
    '隆基绿能': '601012', '通威股份': '600438', '阳光电源': '300274',
    '中芯国际': '688981', '北方华创': '002371', '韦尔股份': '603501',
    '海康威视': '002415', '大华股份': '002236', '科大讯飞': '002230',
    '东方财富': '300059', '中信证券': '600030', '华泰证券': '601688',
    '中国中免': '601888', '顺丰控股': '002352',
    '平安银行': '000001', '万科A': '000002', '万科': '000002',
    '浦发银行': '600000', '民生银行': '600016',
    '中国石化': '600028', '三一重工': '600031',
    '保利发展': '600048', '中国联通': '600050',
    '上汽集团': '600104', '山东黄金': '600547',
    '三安光电': '600703', '海通证券': '600837', '伊利股份': '600887',
    '京东方A': '000725', '京东方': '000725',
    '广发证券': '000776', '洋河股份': '002304',
    '立讯精密': '002475', '歌尔股份': '002241', '蓝思科技': '300433',
    '工业富联': '601138', '兆易创新': '603986', '闻泰科技': '600745',
    '长电科技': '600584', '通富微电': '002156',
    '中国电信': '601728', '中国移动': '600941',
    '中国石油': '601857', '中国神华': '601088', '紫金矿业': '601899',
    '宝钢股份': '600019', '天齐锂业': '002466', '赣锋锂业': '002460',
    '盐湖股份': '000792', '天赐材料': '002709',
    '国轩高科': '002074', '亿纬锂能': '300014', '欣旺达': '300207',
    '长安汽车': '000625', '长城汽车': '601633', '广汽集团': '601238',
    '赛力斯': '601127', '江淮汽车': '600418',
    '腾讯': '00700', '阿里巴巴': 'BABA', '京东': 'JD',
    '美团': '03690', '小米': '01810', '百度': 'BIDU', '网易': 'NTES',
    '特斯拉': 'TSLA', '蔚来': 'NIO', '小鹏': 'XPEV', '理想': 'LI',
}


def get_stock_names_with_fallback():
    """
    获取股票名称字典（带兜底）
    优先使用全市场缓存，失败则使用内置常见股票

    Returns:
        dict: {name: code}
    """
    # 尝试获取全市场
    all_names = get_all_stock_names()
    if all_names and len(all_names) > 100:
        return all_names

    # 兜底使用内置
    return BUILTIN_STOCKS


if __name__ == '__main__':
    # 测试
    print("正在获取全市场股票名称...")
    start = time.time()
    names = get_all_stock_names(force_refresh=True)
    elapsed = time.time() - start
    print(f"获取到 {len(names)} 只股票名称，耗时 {elapsed:.1f}秒")

    # 显示前20个
    print("\n前20只:")
    for i, (name, code) in enumerate(list(names.items())[:20]):
        print(f"  {i+1}. {name} -> {code}")
