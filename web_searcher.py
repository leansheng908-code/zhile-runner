#!/usr/bin/env python3
"""
P0.33: 联网搜索 + 有趣新闻推送

双引擎搜索：Bing中国版（直连） → DuckDuckGo（代理兜底），无需API Key。
每天定时推送：上午9点 + 下午4点。

搜索流程：
  1. 按配置主题列表搜索（科技/二次元/奇闻异事/历史）
  2. 汇总搜索结果
  3. LLM筛选最有反差感的一条，生成简短播报

依赖：urllib（标准库，无需额外安装）
"""

import re
import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import List, Dict, Optional


class WebSearcher:
    """联网搜索器 — Bing直连 + DuckDuckGo代理兜底"""

    def __init__(self, config: dict):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 12)
        self.proxy = self.config.get("proxy", "")  # 如 http://127.0.0.1:7890

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """搜索：先试Bing直连，失败走DuckDuckGo+代理"""
        # 引擎1：Bing中国版（国内直连）
        results = self._search_bing(query, num_results)
        if results:
            return results

        # 引擎2：DuckDuckGo（可能需要代理）
        results = self._search_ddg(query, num_results)
        if results:
            return results

        print(f"  ⚠ 所有搜索引擎均失败 [{query}]")
        return []

    def _search_bing(self, query: str, num: int) -> List[Dict[str, str]]:
        """Bing中国版搜索（国内直连，无需代理）"""
        url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&count={num}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            return self._parse_bing(html, num)
        except Exception as e:
            print(f"  ⚠ Bing搜索失败: {e}")
            return []

    def _parse_bing(self, html: str, num: int) -> List[Dict[str, str]]:
        """解析Bing搜索结果"""
        results = []

        # Bing搜索结果格式：
        # <li class="b_algo"><h2><a href="...">标题</a></h2>
        # <p class="b_lineclamp...">摘要</p> 或 <div class="b_caption"><p>摘要</p>

        # 提取标题（在<h2><a>标签内）
        title_pattern = re.compile(
            r'<h2>\s*<a[^>]*>(.*?)</a>', re.DOTALL
        )
        titles = title_pattern.findall(html)

        # 提取摘要（在b_caption的p标签内）
        snippet_pattern = re.compile(
            r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>',
            re.DOTALL | re.IGNORECASE
        )
        snippets = snippet_pattern.findall(html)

        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = ""
            if i < len(snippets):
                snippet = self._strip_html(snippets[i]).strip()
            if title and len(title) > 3:
                results.append({
                    "title": title,
                    "snippet": snippet[:200] if snippet else "",
                })

        return results

    def _search_ddg(self, query: str, num: int) -> List[Dict[str, str]]:
        """DuckDuckGo搜索（可能需要代理）"""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

        # 配置代理（如果设置了）
        if self.proxy:
            proxy_handler = urllib.request.ProxyHandler({
                "http": self.proxy,
                "https": self.proxy,
            })
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()

        try:
            with opener.open(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            return self._parse_ddg(html, num)
        except Exception as e:
            print(f"  ⚠ DuckDuckGo搜索失败: {e}")
            return []

    def _parse_ddg(self, html: str, num: int) -> List[Dict[str, str]]:
        """解析DuckDuckGo HTML结果页"""
        results = []
        title_pattern = re.compile(
            r'class="result__a"[^>]*>(.*?)</a>', re.DOTALL
        )
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|span)>', re.DOTALL
        )
        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = ""
            if i < len(snippets):
                snippet = self._strip_html(snippets[i]).strip()
            if title and len(title) > 5:
                results.append({
                    "title": title,
                    "snippet": snippet[:200] if snippet else "",
                })
        return results

    @staticmethod
    def _strip_html(text: str) -> str:
        """去除HTML标签和实体"""
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<")
        text = text.replace("&gt;", ">").replace("&quot;", '"')
        text = text.replace("&#39;", "'").replace("&nbsp;", " ")
        return text

    def search_news(
        self,
        topics: List[str],
        num_per_topic: int = 3,
    ) -> List[Dict[str, str]]:
        """按主题列表搜索新闻"""
        all_results = []
        today = datetime.now().strftime("%Y年%m月%d日")
        for topic in topics:
            query = f"{today} {topic} 新闻 热点"
            results = self.search(query, num_per_topic)
            for r in results:
                r["topic"] = topic
            all_results.extend(results)
        return all_results

    def format_news_brief(
        self,
        results: List[Dict[str, str]],
        llm,
        user_prefs: str = "",
    ) -> Optional[str]:
        """用LLM筛选并格式化最有趣的新闻"""
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
            {
                "role": "system",
                "content": (
                    "你是一个新闻筛选助手，为用户挑一条最有趣、最有反差感的新闻。\n"
                    f"用户偏好: {user_prefs or '科技、历史、奇异事件、二次元，喜欢反差感'}\n"
                    "要求：\n"
                    "1. 从搜索结果中选1条最有趣的\n"
                    "2. 用一句话概括（不超过40字）\n"
                    "3. 附上简短点评（不超过30字），带点趣味性\n"
                    "4. 如果搜索结果质量都不高，可以说'今天暂无特别有趣的新闻'\n"
                    "格式：\n📰 标题概括\n💬 点评"
                ),
            },
            {
                "role": "user",
                "content": f"今日搜索结果：\n{results_text}",
            },
        ]

        try:
            response = ""
            for chunk in llm.chat(messages, stream=True, max_tokens=200):
                response += chunk
            result = response.strip()
            if result and len(result) > 5:
                return result
            return None
        except Exception as e:
            print(f"  ⚠ 新闻格式化失败: {e}")
            if results:
                r = results[0]
                return f"📰 {r['title']}"
            return None
