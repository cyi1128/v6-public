# -*- coding: utf-8 -*-
"""
临时诊断脚本：排查各新闻源的原始时间字段
确认 "2025-09-10 00:00" 来自哪个源、哪个字段
"""
import sys
import os
import json
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def diag_juchao():
    print("\n" + "=" * 70)
    print("【巨潮资讯 JuchaoFetcher】原始时间字段诊断")
    print("=" * 70)
    url = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search',
    }
    data = {
        'pageNum': '1', 'pageSize': '5', 'column': 'szse',
        'tabName': 'fulltext', 'plate': '', 'stock': '', 'searchkey': '',
        'secid': '', 'category': '', 'trade': '', 'seDate': '',
        'sortName': '', 'sortType': '', 'isHLtitle': 'true',
    }
    try:
        resp = requests.post(url, data=data, headers=headers, timeout=10)
        print(f"HTTP状态: {resp.status_code}")
        if resp.status_code == 200:
            result = resp.json()
            announcements = result.get('announcements', [])
            print(f"返回公告数: {len(announcements)}")
            for i, ann in enumerate(announcements[:5]):
                print(f"\n--- 公告 #{i+1} ---")
                # 打印所有可能的时间字段
                for key in ['announcementTime', 'announcementDate', 'publishTime',
                            'publishDate', 'createTime', 'updateTime', 'time',
                            'announcementTitle', 'secName', 'secCode']:
                    val = ann.get(key, '<不存在>')
                    print(f"  {key}: {repr(val)} (type={type(val).__name__})")
                # 尝试转换 announcementTime
                at = ann.get('announcementTime', '')
                if at:
                    try:
                        at_int = int(at)
                        print(f"  >> int(announcementTime) = {at_int}")
                        print(f"  >> 作为毫秒: {datetime.fromtimestamp(at_int / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  >> 作为秒:   {datetime.fromtimestamp(at_int).strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"  >> int()转换失败: {e}, 原始值={repr(at)}")
    except Exception as e:
        print(f"请求异常: {e}")


def diag_ths():
    print("\n" + "=" * 70)
    print("【同花顺 THSFetcher】原始时间字段诊断")
    print("=" * 70)
    url = 'https://news.10jqka.com.cn/tapp/news/push/stock/'
    params = {'page': '1', 'tag': '', 'track': 'website', 'pagesize': '5'}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://news.10jqka.com.cn/',
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        print(f"HTTP状态: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', {}).get('list', [])
            print(f"返回新闻数: {len(items)}")
            for i, item in enumerate(items[:5]):
                print(f"\n--- 新闻 #{i+1} ---")
                for key in ['ctime', 'publish_time', 'time', 'create_time',
                            'update_time', 'title', 'id']:
                    val = item.get(key, '<不存在>')
                    print(f"  {key}: {repr(val)} (type={type(val).__name__})")
                ct = item.get('ctime', '')
                if ct:
                    try:
                        ct_int = int(ct)
                        print(f"  >> int(ctime) = {ct_int}")
                        print(f"  >> 作为秒:   {datetime.fromtimestamp(ct_int).strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  >> 作为毫秒: {datetime.fromtimestamp(ct_int / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"  >> int()转换失败: {e}, 原始值={repr(ct)}")
    except Exception as e:
        print(f"请求异常: {e}")


def diag_eastmoney():
    print("\n" + "=" * 70)
    print("【东方财富 EastMoneyFetcher】原始时间字段诊断")
    print("=" * 70)
    url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
    params = {
        'client': 'web', 'biz': 'web_news_col', 'column': '350',
        'order': '1', 'needInteractData': '0',
        'page_index': '1', 'page_size': '5',
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"HTTP状态: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', {}).get('list', [])
            print(f"返回新闻数: {len(items)}")
            for i, item in enumerate(items[:5]):
                print(f"\n--- 新闻 #{i+1} ---")
                for key in ['showtime', 'post_time', 'publish_time', 'time',
                            'create_time', 'update_time', 'title', 'id', 'art_code']:
                    val = item.get(key, '<不存在>')
                    print(f"  {key}: {repr(val)} (type={type(val).__name__})")
    except Exception as e:
        print(f"请求异常: {e}")


def diag_sina():
    print("\n" + "=" * 70)
    print("【新浪财经 SinaFetcher】原始时间字段诊断")
    print("=" * 70)
    url = 'https://feed.mix.sina.com.cn/api/roll/get'
    params = {'pageid': '153', 'lid': '2516', 'k': '', 'num': '5', 'page': 1}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"HTTP状态: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('result', {}).get('data', [])
            print(f"返回新闻数: {len(items)}")
            for i, item in enumerate(items[:5]):
                print(f"\n--- 新闻 #{i+1} ---")
                for key in ['ctime', 'create_time', 'publish_time', 'time',
                            'mtime', 'title', 'oid', 'id']:
                    val = item.get(key, '<不存在>')
                    print(f"  {key}: {repr(val)} (type={type(val).__name__})")
                ct = item.get('ctime', '')
                if ct:
                    try:
                        ct_int = int(ct)
                        print(f"  >> int(ctime) = {ct_int}")
                        print(f"  >> 作为秒:   {datetime.fromtimestamp(ct_int).strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"  >> int()转换失败: {e}, 原始值={repr(ct)}")
    except Exception as e:
        print(f"请求异常: {e}")


def diag_sina7x24():
    print("\n" + "=" * 70)
    print("【新浪7x24 Sina7x24Fetcher】原始时间字段诊断")
    print("=" * 70)
    url = 'https://zhibo.sina.com.cn/api/zhibo/feed'
    params = {
        'page': 1, 'page_size': '5', 'zhibo_id': 152,
        'tag_id': 0, 'dire': 'f', 'dpc': 1,
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        print(f"HTTP状态: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            feed_list = data.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
            print(f"返回新闻数: {len(feed_list)}")
            for i, item in enumerate(feed_list[:5]):
                print(f"\n--- 新闻 #{i+1} ---")
                for key in ['create_time', 'publish_time', 'time', 'ctime',
                            'update_time', 'id', 'rich_text']:
                    val = item.get(key, '<不存在>')
                    if key == 'rich_text' and val != '<不存在>':
                        val = str(val)[:80] + '...'
                    print(f"  {key}: {repr(val)} (type={type(val).__name__})")
                ct = item.get('create_time', '')
                if ct:
                    try:
                        ct_int = int(ct)
                        print(f"  >> int(create_time) = {ct_int}")
                        print(f"  >> 作为秒:   {datetime.fromtimestamp(ct_int).strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"  >> int()转换失败: {e}, 原始值={repr(ct)}")
    except Exception as e:
        print(f"请求异常: {e}")


if __name__ == '__main__':
    print(f"当前系统时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    diag_juchao()
    diag_ths()
    diag_eastmoney()
    diag_sina()
    diag_sina7x24()
    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)
