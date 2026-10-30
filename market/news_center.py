"""
7×24小时财经快讯模块
类似同花顺7×24快讯，实时更新财经新闻
基于东方财富、新浪财经等免费API
"""
import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class NewsItem:
    """新闻条目"""

    def __init__(self, title: str, content: str, time_str: str, source: str = '',
                 url: str = '', importance: int = 0, tags: List[str] = None):
        self.title = title
        self.content = content
        self.time_str = time_str
        self.source = source
        self.url = url
        self.importance = importance  # 0=普通, 1=重要, 2=重大
        self.tags = tags or []
        self.id = f"{time_str}_{title[:20]}"

    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'content': self.content,
            'time': self.time_str,
            'source': self.source,
            'url': self.url,
            'importance': self.importance,
            'tags': self.tags,
        }


class NewsProvider:
    """新闻数据提供者"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://kuaixun.eastmoney.com/',
        })

    def get_eastmoney_news(self, page: int = 1, page_size: int = 30) -> List[NewsItem]:
        """获取东方财富7×24快讯"""
        news_list = []

        try:
            # 东方财富快讯API（多个备用地址）
            urls = [
                f'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=350&order=1&needInteractData=0&page_index={page}&page_size={page_size}',
                f'https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html',
            ]

            for url in urls:
                try:
                    resp = self.session.get(url, timeout=8)
                    if resp.status_code == 200:
                        text = resp.text
                        # 尝试解析JSON
                        try:
                            data = json.loads(text)
                            items = data.get('data', {}).get('list', []) or data.get('LivesList', [])
                        except:
                            # 可能是JSONP格式
                            if '(' in text and ')' in text:
                                json_str = text[text.index('(')+1:text.rindex(')')]
                                data = json.loads(json_str)
                                items = data.get('data', {}).get('list', []) or data.get('LivesList', [])
                            else:
                                items = []

                        if items:
                            for item in items:
                                title = item.get('title', '') or item.get('Title', '')
                                content = item.get('digest', '') or item.get('content', '') or item.get('Digest', '')
                                show_time = item.get('showtime', '') or item.get('display_time', '') or item.get('ShowTime', '')
                                source = item.get('source', '东方财富') or item.get('Source', '东方财富')
                                news_url = item.get('url_w', '') or item.get('url', '') or item.get('Url', '')
                                importance = item.get('level', 0) or item.get('Level', 0)

                                # 解析时间
                                time_str = self._parse_time(show_time)

                                news = NewsItem(
                                    title=title,
                                    content=content,
                                    time_str=time_str,
                                    source=source,
                                    url=news_url,
                                    importance=importance,
                                )
                                news_list.append(news)

                            if news_list:
                                break  # 成功获取就不再尝试其他地址
                except:
                    continue

        except Exception as e:
            pass

        return news_list

    def _parse_time(self, time_val) -> str:
        """解析时间字符串"""
        if not time_val:
            return datetime.now().strftime('%H:%M:%S')

        try:
            # 处理数字或数字字符串（Unix时间戳）
            if isinstance(time_val, (int, float)):
                return datetime.fromtimestamp(time_val).strftime('%H:%M:%S')

            time_str = str(time_val).strip()

            # 检测是否为纯数字字符串（Unix时间戳）
            if time_str.isdigit():
                ts = int(time_str)
                # 合理的时间戳范围（2000年-2030年）
                if 946656000 <= ts <= 1893456000:
                    return datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                # 毫秒级时间戳
                if ts > 1893456000 and 946656000000 <= ts <= 1893456000000:
                    return datetime.fromtimestamp(ts / 1000).strftime('%H:%M:%S')

            # 提取时间部分
            if ' ' in time_str:
                return time_str.split(' ')[-1][:8]
            if len(time_str) >= 8:
                return time_str[-8:]
            return time_str
        except:
            return str(time_val)

    def get_sina_news(self, page: int = 1, page_size: int = 30) -> List[NewsItem]:
        """获取新浪财经7×24快讯（支持分页）"""
        news_list = []

        try:
            url = f'https://zhibo.sina.com.cn/api/zhibo/feed?page={page}&page_size={page_size}&zhibo_id=152&tag_id=0&dire=f&dpc=1'
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('result', {}).get('data', {}).get('feed', {}).get('list', [])

                for item in items:
                    rich_text = item.get('rich_text', '')
                    create_time = item.get('create_time', '')

                    # 解析时间
                    time_str = self._parse_time(create_time)

                    # 提取标题和内容
                    title = ''
                    content = rich_text
                    if '【' in rich_text and '】' in rich_text:
                        end_idx = rich_text.index('】')
                        title = rich_text[1:end_idx]
                        content = rich_text[end_idx+1:].strip()

                    # 判断重要性
                    importance = 0
                    if any(kw in rich_text for kw in ['重磅', '突发', '紧急', '央行', '证监会', '国务院']):
                        importance = 2
                    elif any(kw in rich_text for kw in ['利好', '利空', '涨停', '大跌', '大涨']):
                        importance = 1

                    news = NewsItem(
                        title=title or content[:30],
                        content=content,
                        time_str=time_str,
                        source='新浪财经',
                        importance=importance,
                    )
                    news_list.append(news)

        except Exception as e:
            pass

        return news_list

    def get_cls_news(self) -> List[NewsItem]:
        """获取财联社7×24快讯"""
        news_list = []

        try:
            url = 'https://www.cls.cn/nodeapi/updateTelegraphList?app=CailianpressWeb&category=&lastTime=&last_time=&os=web&rn=20&sv=7.7.5'
            self.session.headers.update({
                'Referer': 'https://www.cls.cn/telegraph',
            })
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('data', {}).get('roll_data', []) or data.get('data', [])

                for item in items:
                    title = item.get('title', '') or item.get('brief', '')
                    content = item.get('content', '') or item.get('brief', '')
                    ctime = item.get('ctime', '') or item.get('time', '')
                    importance = item.get('level', 0) or item.get('importance', 0)

                    time_str = self._parse_time(ctime)

                    news = NewsItem(
                        title=title or content[:30],
                        content=content,
                        time_str=time_str,
                        source='财联社',
                        importance=importance,
                    )
                    news_list.append(news)

        except Exception as e:
            pass

        return news_list

    def get_10jqka_news(self) -> List[NewsItem]:
        """获取同花顺7×24快讯"""
        news_list = []

        try:
            # 同花顺7×24快讯API（多个备用地址）
            urls = [
                'https://news.10jqka.com.cn/tapp/news/push/stock/?page=1&tag=&track=website&pagesize=30',
                'https://news.10jqka.com.cn/tapp/news/push/stock/?page=1&track=website&pagesize=30',
            ]

            self.session.headers.update({
                'Referer': 'https://news.10jqka.com.cn/realtimenews.html',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            })

            for url in urls:
                try:
                    resp = self.session.get(url, timeout=8)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get('data', {}).get('list', []) or data.get('data', []) or []

                        if not items:
                            continue

                        for item in items:
                            title = item.get('title', '') or item.get('digest', '')
                            content = item.get('content', '') or item.get('digest', '') or title
                            ctime = item.get('ctime', '') or item.get('time', '') or item.get('create_time', '')
                            importance = item.get('level', 0) or item.get('importance', 0)
                            news_url = item.get('url', '') or item.get('share_url', '')

                            # 解析时间
                            time_str = self._parse_time(ctime)

                            # 判断重要性
                            if importance == 0:
                                if any(kw in (title + content) for kw in ['重磅', '突发', '紧急', '央行', '证监会', '国务院', '重大']):
                                    importance = 2
                                elif any(kw in (title + content) for kw in ['利好', '利空', '涨停', '大跌', '大涨', '突破']):
                                    importance = 1

                            news = NewsItem(
                                title=title or content[:30],
                                content=content,
                                time_str=time_str,
                                source='同花顺',
                                url=news_url,
                                importance=importance,
                            )
                            news_list.append(news)

                        if news_list:
                            break  # 成功获取就不再尝试其他地址
                except Exception:
                    continue

        except Exception as e:
            pass

        return news_list

    def get_tencent_news(self) -> List[NewsItem]:
        """获取腾讯财经快讯"""
        news_list = []
        try:
            url = "https://news.qq.com/rain/a/finance"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://news.qq.com/'
            }
            resp = self.session.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                # 腾讯财经的API可能需要调整，这里用备用方式
                pass
        except Exception:
            pass

        # 备用：用腾讯财经的另一个接口
        try:
            url = "https://qt.gtimg.cn/q=sh000001,sz399001"
            # 这个是行情接口，不是新闻，跳过
            pass
        except Exception:
            pass

        return news_list

    def get_wallstreet_news(self) -> List[NewsItem]:
        """获取华尔街见闻快讯"""
        news_list = []
        try:
            # 华尔街见闻API
            url = "https://api-one.wallstreetcn.com/apiv1/content/lives"
            params = {
                'channel': 'global-channel',
                'limit': 20,
                'first_page': 1
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://wallstreetcn.com/'
            }
            resp = self.session.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and data['data'].get('items'):
                    for item in data['data']['items']:
                        try:
                            title = item.get('title', '') or item.get('content_text', '')[:50]
                            content = item.get('content_text', '')
                            time_str = ''
                            if item.get('display_time'):
                                import datetime
                                dt = datetime.datetime.fromtimestamp(item['display_time'])
                                time_str = dt.strftime('%H:%M:%S')

                            importance = 0
                            if item.get('is_important'):
                                importance = 2
                            elif item.get('is_hot'):
                                importance = 1

                            news_url = ''
                            if item.get('uri'):
                                news_url = f"https://wallstreetcn.com/news/{item['uri']}"

                            news = NewsItem(
                                title=title,
                                content=content,
                                time_str=time_str,
                                source='华尔街见闻',
                                url=news_url,
                                importance=importance,
                            )
                            news_list.append(news)
                        except Exception:
                            continue
        except Exception:
            pass

        return news_list

    def get_jin10_news(self) -> List[NewsItem]:
        """获取金十数据快讯"""
        news_list = []
        try:
            # 金十数据API
            url = "https://flash-api.jin10.com/get_flash_list"
            params = {
                'channel': '-8200',
                'vip': 1,
                'max_time': ''
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.jin10.com/',
                'x-app-id': 'bVBF4FyRTn5njq7Q',
                'x-version': '1.0.0'
            }
            resp = self.session.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data'):
                    for item in data['data']:
                        try:
                            content = item.get('data', {}).get('content', '') or item.get('data', {}).get('title', '')
                            title = content[:50] if content else ''

                            time_str = ''
                            if item.get('time'):
                                time_str = item['time'][-8:] if len(item['time']) >= 8 else item['time']

                            importance = 0
                            if item.get('important') == 1:
                                importance = 2
                            elif item.get('important') == 2:
                                importance = 1

                            news = NewsItem(
                                title=title,
                                content=content,
                                time_str=time_str,
                                source='金十数据',
                                url='',
                                importance=importance,
                            )
                            news_list.append(news)
                        except Exception:
                            continue
        except Exception:
            pass

        return news_list

    def _get_sort_hour(self, time_str):
        """
        计算排序用的时间值（小时数）
        智能判断日期：
        - 当前是凌晨（0-5点）时：凌晨的新闻（0点到当前小时）是今天的，加24小时排前面；其他都是昨天的
        - 当前是白天/晚上时：都按当天计算
        """
        try:
            if not time_str or ':' not in time_str:
                return 0

            # 统一提取时间部分（处理各种格式）
            # 格式1: HH:MM:SS
            # 格式2: HH:MM
            # 格式3: 包含日期的完整时间
            time_part = time_str.strip()

            # 如果包含空格，取最后一部分（时间部分）
            if ' ' in time_part:
                time_part = time_part.split(' ')[-1]

            # 如果包含T（ISO格式），取T后面的部分
            if 'T' in time_part:
                time_part = time_part.split('T')[-1]

            parts = time_part.split(':')
            if len(parts) < 2:
                return 0

            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            second = int(parts[2]) if len(parts) > 2 else 0

            # 确保小时在0-23之间
            if hour < 0 or hour > 23:
                return 0

            current_hour = datetime.now().hour
            time_val = hour + minute / 60 + second / 3600

            # 凌晨时段（0-5点），需要区分今天和昨天
            if current_hour < 5:
                # 小时数 <= 当前小时的，是今天凌晨的，加24小时排最前面
                if hour <= current_hour:
                    return time_val + 24
                # 其他时间的新闻都是昨天的，按原时间排序
                return time_val
            else:
                # 白天/晚上，都按当天计算
                return time_val
        except Exception:
            return 0

    def get_all_news(self, max_pages: int = 10, max_news: int = 500) -> List[NewsItem]:
        """V1.3.17：获取全天新闻（分页获取，直到当天00:00或达到最大数量）"""
        all_news = []
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_start_hour = 0  # 当天00:00

        # 东方财富（支持分页，主要数据源）
        for page in range(1, max_pages + 1):
            em_news = self.get_eastmoney_news(page=page, page_size=50)
            if not em_news:
                break
            all_news.extend(em_news)
            print(f"[NEWS] 东方财富第{page}页: 获取{len(em_news)}条，累计{len(all_news)}条")
            # 检查是否已经获取到当天00:00之前的新闻
            if len(em_news) > 0:
                last_news = em_news[-1]
                last_hour = self._get_sort_hour(last_news.time_str)
                if last_hour < today_start_hour + 1:  # 已经到凌晨1点之前，基本覆盖全天
                    print(f"[NEWS] 已获取到当天凌晨新闻，停止分页")
                    break
            if len(all_news) >= max_news:
                break

        # 新浪财经（支持分页，补充数据源）
        if len(all_news) < max_news:
            for page in range(1, max_pages + 1):
                sina_news = self.get_sina_news(page=page, page_size=30)
                if not sina_news:
                    break
                all_news.extend(sina_news)
                print(f"[NEWS] 新浪财经第{page}页: 获取{len(sina_news)}条，累计{len(all_news)}条")
                if len(all_news) >= max_news:
                    break

        # 其他数据源（单页，补充）
        if len(all_news) < max_news:
            # 财联社
            cls_news = self.get_cls_news()
            all_news.extend(cls_news)
            # 同花顺
            jqka_news = self.get_10jqka_news()
            all_news.extend(jqka_news)
            # 腾讯财经
            tencent_news = self.get_tencent_news()
            all_news.extend(tencent_news)
            # 华尔街见闻
            wallstreet_news = self.get_wallstreet_news()
            all_news.extend(wallstreet_news)
            # 金十数据
            jin10_news = self.get_jin10_news()
            all_news.extend(jin10_news)

        # 按时间排序（最新的在前）
        all_news.sort(key=lambda x: self._get_sort_hour(x.time_str), reverse=True)

        # 去重
        seen = set()
        unique_news = []
        for news in all_news:
            key = news.title[:20] if news.title else news.content[:20]
            if key not in seen:
                seen.add(key)
                unique_news.append(news)

        result = unique_news[:max_news]
        print(f"[NEWS] 全天新闻获取完成: 共{len(result)}条（去重后）")
        return result


class NewsCenter(QObject):
    """
    7×24快讯中心
    支持实时更新、信号通知
    """
    news_updated = pyqtSignal(list)  # 新闻更新信号
    new_important_news = pyqtSignal(object)  # 重要新闻信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.provider = NewsProvider()
        self.news_list = []
        self._last_news_ids = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_news)
        self._refresh_interval = 60000  # 60秒刷新一次

    def start(self):
        """启动自动刷新"""
        self._timer.start(self._refresh_interval)
        # 立即刷新一次
        self._refresh_news()

    def stop(self):
        """停止自动刷新"""
        self._timer.stop()

    def set_refresh_interval(self, seconds: int):
        """设置刷新间隔（秒）"""
        self._refresh_interval = seconds * 1000
        if self._timer.isActive():
            self._timer.start(self._refresh_interval)

    def _refresh_news(self):
        """刷新新闻"""
        try:
            new_news = self.provider.get_all_news()

            if not new_news:
                print("新闻获取结果为空")
                return

            # 检测新的重要新闻
            for news in new_news:
                if news.id not in self._last_news_ids:
                    if news.importance >= 1:
                        self.new_important_news.emit(news)

            # 更新新闻列表
            self.news_list = new_news
            self._last_news_ids = {n.id for n in new_news}

            # 通知UI更新
            self.news_updated.emit([n.to_dict() for n in new_news])

        except Exception as e:
            print(f"刷新新闻失败: {e}")
            import traceback
            traceback.print_exc()

    def get_news(self, count: int = 500) -> List[Dict]:
        """V1.3.17：获取新闻列表（默认返回500条，覆盖全天）"""
        return [n.to_dict() for n in self.news_list[:count]]

    def refresh_now(self):
        """手动立即刷新"""
        self._refresh_news()
