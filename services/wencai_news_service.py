# -*- coding: utf-8 -*-
"""
同花顺问财新闻解读 HTTP 直连服务 V1.0
- 直接调用 https://www.iwencai.com/customized/chart/get-robot-data
- 不再使用 pywencai，纯 requests 调用
- Cookie 从 config/wencai_cookie.txt 读取，hexin-v 从 Cookie 中提取
- 401 / Cookie 失效时返回 cookie_expired=True
- 网络/JSON/空响应异常统一捕获，返回 success=False
"""
import os
import re
import json
import sys
from typing import Dict, List, Any

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

WENCAI_URL = "https://www.iwencai.com/customized/chart/get-robot-data"
COOKIE_PATH = os.path.join(PROJECT_ROOT, "config", "wencai_cookie.txt")
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT_SECONDS = 15
MAX_STOCKS = 8


class WencaiNewsService:
    """问财新闻解读 HTTP 直连服务（单例）"""

    def __init__(self):
        self._cookie_cache: str = ""
        self._cookie_mtime: float = 0.0

    # ---------- Cookie 读取 ----------
    def _load_cookie(self) -> str:
        """读取 config/wencai_cookie.txt，按 mtime 简单缓存"""
        try:
            if not os.path.exists(COOKIE_PATH):
                return ""
            mtime = os.path.getmtime(COOKIE_PATH)
            if self._cookie_cache and mtime == self._cookie_mtime:
                return self._cookie_cache
            with open(COOKIE_PATH, "r", encoding="utf-8") as f:
                cookie = f.read().strip()
            self._cookie_cache = cookie
            self._cookie_mtime = mtime
            return cookie
        except Exception:
            return self._cookie_cache or ""

    @staticmethod
    def _extract_hexin_v(cookie: str) -> str:
        if not cookie:
            return ""
        m = re.search(r"v=([^;]+)", cookie)
        return m.group(1).strip() if m else ""

    # ---------- 内部请求 ----------
    def _post_question(self, question: str) -> Dict[str, Any]:
        """发起问财 POST 请求，返回标准化 dict（不抛异常）。"""
        cookie = self._load_cookie()
        if not cookie:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "Cookie 文件不存在或为空", "cookie_expired": True}

        hexin_v = self._extract_hexin_v(cookie)
        headers = {
            "Content-Type": "application/json",
            "Cookie": cookie,
            "User-Agent": DEFAULT_UA,
            "Referer": "https://www.iwencai.com/",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.iwencai.com",
        }
        if hexin_v:
            headers["hexin-v"] = hexin_v

        body = {
            "question": question,
            "perpage": MAX_STOCKS,
            "page": 1,
            "source": "Ths_iwencai_Xuangu",
            "version": "2.0",
            "query_area": "",
            "block_list": "",
            "log_info": json.dumps({"input_type": "typewrite"}, ensure_ascii=False),
        }

        try:
            resp = requests.post(WENCAI_URL, headers=headers, json=body,
                                 timeout=TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "问财请求超时（15秒）", "cookie_expired": False}
        except requests.exceptions.ConnectionError as e:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": f"网络连接失败: {str(e)[:80]}", "cookie_expired": False}
        except Exception as e:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": f"请求异常: {str(e)[:80]}", "cookie_expired": False}

        # 401 可能是瞬时风控限流，等待后重试最多2次
        import time as _time
        for _attempt in range(3):
            if resp.status_code != 401:
                break
            try:
                _time.sleep(2.0 * (_attempt + 1))
                resp = requests.post(WENCAI_URL, headers=headers, json=body,
                                     timeout=TIMEOUT_SECONDS)
            except Exception:
                break

        if resp.status_code == 401:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "问财登录已过期，请重新登录后更新Cookie",
                    "cookie_expired": True}
        if resp.status_code != 200:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": f"HTTP {resp.status_code}", "cookie_expired": False}

        try:
            payload = resp.json()
        except Exception as e:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": f"JSON解析失败: {str(e)[:80]}", "cookie_expired": False}

        return self._parse_payload(payload, question)

    @staticmethod
    def _to_float(v: Any) -> float:
        try:
            if v is None or v == "" or str(v).lower() == "nan":
                return 0.0
            s = str(v).replace("%", "").replace(",", "").strip()
            return float(s)
        except Exception:
            return 0.0

    def _parse_payload(self, payload: Dict[str, Any], question: str) -> Dict[str, Any]:
        """从问财响应中提取 voice_txt 和股票列表"""
        if not isinstance(payload, dict):
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "响应结构不是dict", "cookie_expired": False}

        # 顶层 ret 非 0 可能也是登录失效
        ret = payload.get("ret")
        if isinstance(ret, int) and ret == 401:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "问财登录已过期，请重新登录后更新Cookie",
                    "cookie_expired": True}

        data = payload.get("data") or {}
        answers = data.get("answer") or []
        if not answers:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "问财返回空 answer", "cookie_expired": False}

        first_answer = answers[0] or {}
        voice_txt = str(first_answer.get("voice_txt", "") or "")

        stocks: List[Dict[str, Any]] = []
        # txt -> content(dict or list) -> components -> data.datas
        txt_list = first_answer.get("txt") or []
        for txt_block in txt_list:
            if not isinstance(txt_block, dict):
                continue
            contents = txt_block.get("content")
            # content 可能是 dict（直接含 components）或 list
            content_blocks = []
            if isinstance(contents, dict):
                content_blocks = [contents]
            elif isinstance(contents, list):
                content_blocks = contents
            for content_block in content_blocks:
                if not isinstance(content_block, dict):
                    continue
                components = content_block.get("components") or []
                if not isinstance(components, list):
                    continue
                for comp in components:
                    if not isinstance(comp, dict):
                        continue
                    comp_data = comp.get("data") or {}
                    if not isinstance(comp_data, dict):
                        continue
                    datas = comp_data.get("datas") or []
                    if not isinstance(datas, list) or not datas:
                        continue
                    for row in datas:
                        if not isinstance(row, dict):
                            continue
                        code = str(row.get("code") or row.get("股票代码") or "").split(".")[0].zfill(6)
                        name = str(row.get("股票简称") or row.get("股票名称") or row.get("name") or "")
                        if not code or not name or len(code) != 6 or not code.isdigit():
                            continue
                        # 跳过非股票行（comp[3] 这种含 q/encodeQuery 字段）
                        if "最新价" not in row and "最新涨跌幅" not in row:
                            continue
                        price = self._to_float(row.get("最新价") or row.get("price"))
                        pct = self._to_float(row.get("最新涨跌幅") or row.get("涨跌幅"))
                        stocks.append({
                            "code": code,
                            "name": name,
                            "price": price,
                            "pct": pct,
                        })
                        if len(stocks) >= MAX_STOCKS:
                            break
                    if stocks:
                        break
                if stocks:
                    break
            if stocks:
                break

        return {
            "success": True,
            "voice_txt": voice_txt,
            "stocks": stocks,
            "error": "",
            "cookie_expired": False,
        }

    # ---------- 对外方法 ----------
    def query_concept(self, keyword: str) -> Dict[str, Any]:
        """根据核心概念关键词查询概念股。"""
        keyword = (keyword or "").strip()
        if not keyword:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "关键词为空", "cookie_expired": False}
        question = f"{keyword}概念股"
        return self._post_question(question)

    def query_followup(self, question: str) -> Dict[str, Any]:
        """直接用用户追问的自然语言问题查询。"""
        question = (question or "").strip()
        if not question:
            return {"success": False, "voice_txt": "", "stocks": [],
                    "error": "问题为空", "cookie_expired": False}
        return self._post_question(question)


# ---------- 单例 ----------
_singleton: WencaiNewsService = None  # type: ignore


def get_wencai_news_service() -> WencaiNewsService:
    global _singleton
    if _singleton is None:
        _singleton = WencaiNewsService()
    return _singleton


if __name__ == "__main__":
    # 简单自测
    svc = get_wencai_news_service()
    for kw in ["医疗旅游", "半导体设备", "光伏"]:
        print(f"=== {kw} ===")
        r = svc.query_concept(kw)
        print("success=", r["success"], "expired=", r["cookie_expired"],
              "err=", r["error"])
        print("voice=", r["voice_txt"][:120])
        for s in r["stocks"][:5]:
            print("  ", s)
