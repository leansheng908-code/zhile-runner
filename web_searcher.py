#!/usr/bin/env python3
"""
P0.33: 联网搜索 + 有趣新闻推送

使用 DuckDuckGo HTML 搜索（无需API Key），配合LLM筛选有趣新闻。
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
    """联网搜索器 — DuckDuckGo HTML"""

    def __init__(self, config: dict):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 12)

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """搜索DuckDuckGo，返回结果列表"""
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
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            return self._parse_results(html, num_results)
        except Exception as e:
            print(f"  ⚠ 搜索失败 [{query}]: {e}")
            return []

    def _parse_results(self, html: str, num: int) -> List[Dict[str, str]]:
        """解析DuckDuckGo HTML结果页"""
        results = []

        # DuckDuckGo HTML 格式：
        # <a class="result__a" href="...">标题</a>
        # <a class="result__snippet">摘要</a>
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
            # 无LLM时简单返回第一条
            if results:
                r = results[0]
                return f"📰 {r['title']}\n{r['snippet'][:60]}"
            return None

        # 构建搜索结果文本
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
            # 降级：返回第一条
            if results:
                r = results[0]
                return f"📰 {r['title']}"
            return None
