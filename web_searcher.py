#!/usr/bin/env python3
"""
P0.33: 联网搜索 + 有趣新闻推送 (v3)

策略：DuckDuckGo HTML版（反爬最宽松）→ wttr.in天气API → Bing兜底
DDG HTML版 (html.duckduckgo.com/html/) 是为非JS客户端设计的，不会拦截。
wttr.in 是免费天气服务，直接返回天气信息，不需要搜索。
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
    """联网搜索器 — DDG HTML优先 + 天气API + Bing兜底"""

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

    def _fetch(self, url: str, min_size: int = 200) -> Optional[str]:
        """抓取URL：curl优先 → urllib兜底"""
        if self._curl:
            html = self._fetch_curl(url)
            if html and len(html) > min_size:
                return html
        html = self._fetch_urllib(url)
        if html and len(html) > min_size:
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
            print(f"  ⚠ curl error: {e}")
        return None

    def _fetch_urllib(self, url: str) -> Optional[str]:
        """urllib兜底抓取"""
        headers = {
            "User-Agent": self.BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        req = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self._ssl_ctx))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
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
        req = urllib.request.Request(url, headers={"User-Agent": self.BROWSER_UA})
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self._ssl_ctx))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

    # ===== 天气专用API =====

    def _search_weather(self, query: str) -> List[Dict[str, str]]:
        """wttr.in 天气API — 免费无需Key"""
        # 从查询中提取地名
        location = re.sub(r'(今天|今日|实时|预报|天气|气温|多少度|怎么样|查询|的|了)', '', query).strip()
        if not location:
            location = "Beijing"
        # wttr.in 中文天气
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1&lang=zh"
        data = self._fetch_json(url)
        if not data:
            # 试试纯文本格式
            url2 = f"https://wttr.in/{urllib.parse.quote(location)}?lang=zh"
            text = self._fetch(url2, min_size=50)
            if text:
                # 提取关键天气信息
                lines = [l.strip() for l in text.split('\n') if l.strip() and not l.startswith('┌') and not l.startswith('└') and not l.startswith('│') and not l.startswith(' ─')]
                if lines:
                    return [{"title": f"{location}天气", "snippet": ' '.join(lines[:5])[:200]}]
            return []
        results = []
        try:
            current = data.get("current_condition", [{}])[0]
            weather_desc = current.get("lang_zh", [{}])[0].get("value", current.get("weatherDesc", [{}])[0].get("value", ""))
            temp = current.get("temp_C", "?")
            feels = current.get("FeelsLikeC", "?")
            humidity = current.get("humidity", "?")
            wind = current.get("windspeedKmph", "?")
            results.append({
                "title": f"{location} {weather_desc} {temp}°C",
                "snippet": f"气温{temp}°C 体感{feels}°C 湿度{humidity}% 风速{wind}km/h",
            })
            # 明天预报
            for day_data in data.get("weather", [])[1:3]:
                date = day_data.get("date", "")
                max_t = day_data.get("maxtempC", "?")
                min_t = day_data.get("mintempC", "?")
                desc = day_data.get("hourly", [{}])[4].get("lang_zh", [{}])[0].get("value", "")
                results.append({
                    "title": f"{date} {desc} {min_t}~{max_t}°C",
                    "snippet": f"最高{max_t}°C 最低{min_t}°C {desc}",
                })
        except Exception:
            pass
        return results

    def _is_weather_query(self, query: str) -> bool:
        """判断是否天气查询"""
        weather_keywords = ["天气", "气温", "温度", "多少度", "下雨", "下雪", "预报", "风", "晴", "阴", "冷不冷", "热不热"]
        return any(kw in query for kw in weather_keywords)

    # ===== 搜索引擎 =====

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """搜索：天气→DDG HTML→Bing"""
        # 1. 天气查询走专用API
        if self._is_weather_query(query):
            results = self._search_weather(query)
            if results:
                return results

        # 2. DuckDuckGo HTML版（反爬最宽松）
        results = self._search_ddg_html(query, num_results)
        if results:
            return results

        # 3. Bing兜底
        results = self._search_bing(query, num_results)
        if results:
            return results

        print(f"  ⚠ 所有搜索引擎均失败 [{query}]")
        return []

    def _search_ddg_html(self, query: str, num: int) -> List[Dict[str, str]]:
        """DuckDuckGo HTML版 — 为非JS客户端设计，不拦机器人"""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        html = self._fetch(url)
        if not html:
            print(f"  ⚠ DDG HTML抓取失败 [{query}]")
            return []
        results = self._parse_ddg_html(html, num)
        if not results:
            print(f"  ⚠ DDG HTML解析0条 (HTML {len(html)} bytes)")
        return results

    def _parse_ddg_html(self, html: str, num: int) -> List[Dict[str, str]]:
        """解析DDG HTML搜索结果"""
        results = []
        # DDG HTML版结果结构: <a class="result__a" href="...">TITLE</a>
        # <a class="result__snippet" ...>SNIPPET</a>
        title_pattern = re.compile(r'class="result__a"[^>]*>(.*?)</a>', re.DOTALL)
        snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</(?:a|td)>', re.DOTALL)

        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = self._strip_html(snippets[i]).strip() if i < len(snippets) else ""
            if title and len(title) > 3:
                results.append({"title": title, "snippet": snippet[:200]})

        # 备用解析模式
        if not results:
            blocks = re.findall(r'class="result__body"[^>]*>(.*?)(?=class="result__body"|</div>\s*</div>\s*<div)', html, re.DOTALL)
            for block in blocks[:num]:
                t_match = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL)
                s_match = re.search(r'class="result__snippet"[^>]*>(.*?)</', block, re.DOTALL)
                if t_match:
                    title = self._strip_html(t_match.group(1)).strip()
                    snippet = self._strip_html(s_match.group(1)).strip() if s_match else ""
                    if title and len(title) > 3:
                        results.append({"title": title, "snippet": snippet[:200]})

        return results

    def _search_bing(self, query: str, num: int) -> List[Dict[str, str]]:
        """Bing搜索（兜底）"""
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
    print("WebSearcher v3 测试")
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
