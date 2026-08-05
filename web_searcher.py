#!/usr/bin/env python3
"""
P0.33: 联网搜索 + 有趣新闻推送

搜索引擎：curl抓取Bing → curl抓取Sogou → curl抓取百度 → DuckDuckGo JSON API → urllib兜底
curl优先策略：Windows 10+自带curl.exe，绕过Python SSL/代理兼容性问题。
"""

import re
import json
import subprocess
import urllib.request
import urllib.parse
import ssl
from datetime import datetime
from typing import List, Dict, Optional

# Windows curl.exe 路径候选
_CURL_CANDIDATES = [
    "curl",
    r"C:\Windows\System32\curl.exe",
    r"C:\Windows\SysWOW64\curl.exe",
]


def _find_curl() -> Optional[str]:
    """找到可用的curl可执行文件"""
    import shutil
    for c in _CURL_CANDIDATES:
        path = shutil.which(c) or (c if _test_curl(c) else None)
        if path:
            return path
    return None


def _test_curl(path: str) -> bool:
    """测试curl是否可执行"""
    try:
        r = subprocess.run([path, "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


class WebSearcher:
    """联网搜索器 — curl优先 + 多引擎"""

    BROWSER_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    def __init__(self, config: dict):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 15)
        self.proxy = self.config.get("proxy", "")
        self._curl = _find_curl()
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE
        if self._curl:
            print(f"  [WebSearcher] curl found: {self._curl}")
        else:
            print("  [WebSearcher] ⚠ curl not found, will try urllib only")

    # ===== 抓取层 =====

    def _fetch(self, url: str) -> Optional[str]:
        """抓取URL：curl优先 → urllib兜底"""
        # 方式1: curl（最可靠，绕过Python SSL/代理问题）
        if self._curl:
            html = self._fetch_curl(url)
            if html and len(html) > 200:
                return html
        # 方式2: urllib兜底
        html = self._fetch_urllib(url)
        if html and len(html) > 200:
            return html
        return None

    def _fetch_curl(self, url: str) -> Optional[str]:
        """用curl命令行抓取"""
        cmd = [
            self._curl, "-sL",
            "--max-time", str(self.timeout),
            "-A", self.BROWSER_UA,
            "-H", "Accept-Language: zh-CN,zh;q=0.9",
            "-H", "Accept: text/html,application/xhtml+xml",
        ]
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])
        cmd.append(url)
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout + 5)
            if result.returncode == 0 and result.stdout:
                return result.stdout.decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"  ⚠ curl失败: {e}")
        return None

    def _fetch_urllib(self, url: str) -> Optional[str]:
        """urllib兜底抓取"""
        headers = {
            "User-Agent": self.BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        req = urllib.request.Request(url, headers=headers)
        if self.proxy:
            handler = urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=self._ssl_ctx))
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self._ssl_ctx))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return None

    def _fetch_json(self, url: str) -> Optional[dict]:
        """抓取JSON API（curl优先）"""
        if self._curl:
            cmd = [self._curl, "-sL", "--max-time", str(self.timeout), "-A", self.BROWSER_UA]
            if self.proxy:
                cmd.extend(["--proxy", self.proxy])
            cmd.append(url)
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=self.timeout + 5)
                if result.returncode == 0 and result.stdout:
                    return json.loads(result.stdout.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        # urllib兜底
        req = urllib.request.Request(url, headers={"User-Agent": self.BROWSER_UA})
        if self.proxy:
            handler = urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=self._ssl_ctx))
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self._ssl_ctx))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

    # ===== 搜索引擎 =====

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """搜索：Bing → Sogou → 百度 → DDG API"""
        for engine_name, engine_fn in [
            ("Bing", self._search_bing),
            ("Sogou", self._search_sogou),
            ("百度", self._search_baidu),
            ("DDG-API", self._search_ddg_api),
        ]:
            results = engine_fn(query, num_results)
            if results:
                return results
        print(f"  ⚠ 所有搜索引擎均失败 [{query}]")
        return []

    def _search_bing(self, query: str, num: int) -> List[Dict[str, str]]:
        url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&count={num}"
        html = self._fetch(url)
        if not html:
            print(f"  ⚠ Bing抓取失败 [{query}]")
            return []
        results = self._parse_bing(html, num)
        if not results:
            print(f"  ⚠ Bing解析0条 (HTML {len(html)} bytes)")
        return results

    def _parse_bing(self, html: str, num: int) -> List[Dict[str, str]]:
        results = []
        titles = re.findall(r'<h2[^>]*>\s*<a[^>]*>(.*?)</a>', html, re.DOTALL)
        snippets = []
        for sp in [
            re.compile(r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', re.DOTALL | re.IGNORECASE),
            re.compile(r'class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', re.DOTALL),
        ]:
            snippets = sp.findall(html)
            if snippets:
                break
        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = self._strip_html(snippets[i]).strip() if i < len(snippets) else ""
            if title and len(title) > 3:
                results.append({"title": title, "snippet": snippet[:200]})
        return results

    def _search_sogou(self, query: str, num: int) -> List[Dict[str, str]]:
        url = f"https://www.sogou.com/web?query={urllib.parse.quote(query)}&num={num}"
        html = self._fetch(url)
        if not html:
            print(f"  ⚠ Sogou抓取失败 [{query}]")
            return []
        results = self._parse_sogou(html, num)
        if not results:
            print(f"  ⚠ Sogou解析0条 (HTML {len(html)} bytes)")
        return results

    def _parse_sogou(self, html: str, num: int) -> List[Dict[str, str]]:
        results = []
        titles = []
        for tp in [
            re.compile(r'<h3[^>]*class="[^"]*vr-title[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL),
            re.compile(r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL),
        ]:
            titles = tp.findall(html)
            if titles:
                break
        snippets = []
        for sp in [
            re.compile(r'<p class="str-info[^"]*"[^>]*>(.*?)</p>', re.DOTALL),
            re.compile(r'class="str-text-info"[^>]*>(.*?)</p>', re.DOTALL),
        ]:
            snippets = sp.findall(html)
            if snippets:
                break
        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = self._strip_html(snippets[i]).strip() if i < len(snippets) else ""
            if title and len(title) > 3:
                results.append({"title": title, "snippet": snippet[:200]})
        return results

    def _search_baidu(self, query: str, num: int) -> List[Dict[str, str]]:
        url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}&rn={num}"
        html = self._fetch(url)
        if not html:
            print(f"  ⚠ 百度抓取失败 [{query}]")
            return []
        if len(html) < 3000:
            print(f"  ⚠ 百度疑似反爬 (HTML {len(html)} bytes)")
            return []
        results = self._parse_baidu(html, num)
        if not results:
            print(f"  ⚠ 百度解析0条 (HTML {len(html)} bytes)")
        return results

    def _parse_baidu(self, html: str, num: int) -> List[Dict[str, str]]:
        results = []
        titles = []
        for tp in [
            re.compile(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>', re.DOTALL),
            re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL),
        ]:
            titles = tp.findall(html)
            if titles:
                break
        snippets = []
        for sp in [
            re.compile(r'class="content-right[^"]*"[^>]*>(.*?)</span>', re.DOTALL),
            re.compile(r'class="c-abstract[^"]*"[^>]*>(.*?)</(?:div|span)', re.DOTALL),
        ]:
            snippets = sp.findall(html)
            if snippets:
                break
        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = self._strip_html(snippets[i]).strip() if i < len(snippets) else ""
            if title and len(title) > 2:
                results.append({"title": title, "snippet": snippet[:200]})
        return results

    def _search_ddg_api(self, query: str, num: int) -> List[Dict[str, str]]:
        """DuckDuckGo Instant Answer API（JSON，无需解析HTML）"""
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        data = self._fetch_json(url)
        if not data:
            print(f"  ⚠ DDG API失败 [{query}]")
            return []
        results = []
        # Abstract
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data["AbstractText"][:200],
            })
        # RelatedTopics
        for topic in (data.get("RelatedTopics") or [])[:num * 2]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:60],
                    "snippet": topic.get("Text", "")[:200],
                })
            if len(results) >= num:
                break
        if not results:
            print(f"  ⚠ DDG API返回0条 [{query}]")
        return results

    @staticmethod
    def _strip_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        for old, new in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
            text = text.replace(old, new)
        return text

    def search_news(self, topics: List[str], num_per_topic: int = 3) -> List[Dict[str, str]]:
        all_results = []
        today = datetime.now().strftime("%Y年%m月%d日")
        for topic in topics:
            query = f"{today} {topic} 新闻 热点"
            results = self.search(query, num_per_topic)
            for r in results:
                r["topic"] = topic
            all_results.extend(results)
        return all_results

    def format_news_brief(self, results: List[Dict[str, str]], llm, user_prefs: str = "") -> Optional[str]:
        if not results or not llm:
            if results:
                r = results[0]
                return f"📰 {r['title']}\n{r.get('snippet', '')[:60]}"
            return None
        results_text = "\n".join(
            f"[{i+1}] [{r.get('topic', '')}] {r['title']}: {r.get('snippet', '')[:80]}"
            for i, r in enumerate(results[:15])
        )
        messages = [
            {"role": "system", "content": (
                "你是一个新闻筛选助手，为用户挑一条最有趣、最有反差感的新闻。\n"
                f"用户偏好: {user_prefs or '科技、历史、奇异事件、二次元，喜欢反差感'}\n"
                "要求：\n1. 从搜索结果中选1条最有趣的\n"
                "2. 用一句话概括（不超过40字）\n"
                "3. 附上简短点评（不超过30字），带点趣味性\n"
                "4. 如果搜索结果质量都不高，可以说'今天暂无特别有趣的新闻'\n"
                "格式：\n📰 标题概括\n💬 点评"
            )},
            {"role": "user", "content": f"今日搜索结果：\n{results_text}"},
        ]
        try:
            response = ""
            for chunk in llm.chat(messages, stream=True, max_tokens=200):
                response += chunk
            result = response.strip()
            return result if result and len(result) > 5 else None
        except Exception as e:
            print(f"  ⚠ 新闻格式化失败: {e}")
            if results:
                return f"📰 {results[0]['title']}"
            return None


if __name__ == "__main__":
    import sys
    print("=" * 50)
    print("WebSearcher 测试（curl优先）")
    print("=" * 50)
    searcher = WebSearcher({"timeout": 15, "proxy": ""})
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "今天天气"
    print(f"\n搜索: {query}\n")
    results = searcher.search(query, 5)
    print(f"\n共 {len(results)} 条结果")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['title']}")
        if r['snippet']:
            print(f"      {r['snippet'][:80]}")
