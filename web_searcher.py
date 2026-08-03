#!/usr/bin/env python3
"""
P0.33: 联网搜索 + 有趣新闻推送

三引擎搜索：百度（直连） → Bing中国版（直连） → DuckDuckGo（代理兜底），无需API Key。
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
    """联网搜索器 — 百度直连 + Bing直连 + DuckDuckGo代理兜底"""

    def __init__(self, config: dict):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 12)
        self.proxy = self.config.get("proxy", "")  # 如 http://127.0.0.1:7890

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """搜索：百度 → Bing → DuckDuckGo，依次尝试"""
        # 引擎1：百度（国内直连，最稳定）
        results = self._search_baidu(query, num_results)
        if results:
            return results

        # 引擎2：Bing中国版（国内直连）
        results = self._search_bing(query, num_results)
        if results:
            return results

        # 引擎3：DuckDuckGo（可能需要代理）
        results = self._search_ddg(query, num_results)
        if results:
            return results

        print(f"  ⚠ 所有搜索引擎均失败 [{query}]")
        return []

    def _search_baidu(self, query: str, num: int) -> List[Dict[str, str]]:
        """百度搜索（国内直连，无需代理）"""
        url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}&rn={num}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            results = self._parse_baidu(html, num)
            if not results:
                print(f"  ⚠ 百度搜索返回0条结果 (HTML {len(html)} bytes)")
            return results
        except Exception as e:
            print(f"  ⚠ 百度搜索失败: {e}")
            return []

    def _parse_baidu(self, html: str, num: int) -> List[Dict[str, str]]:
        """解析百度搜索结果"""
        results = []

        # 百度搜索结果多种格式，逐个尝试
        # 格式1: <h3 class="t"><a href="...">title</a></h3>
        # 格式2: <h3><a href="...">title</a></h3>
        title_patterns = [
            re.compile(r'<h3[^>]*>\s*<a[^>]*>(.*?)</a>', re.DOTALL),
            re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL),
        ]
        titles = []
        for tp in title_patterns:
            titles = tp.findall(html)
            if titles:
                break

        # 摘要多种格式
        snippet_patterns = [
            re.compile(r'class="content-right[^"]*"[^>]*>(.*?)</span>', re.DOTALL),
            re.compile(r'class="c-abstract[^"]*"[^>]*>(.*?)</(?:div|span)>', re.DOTALL),
            re.compile(r'<span class="c-color-text"[^>]*>(.*?)</span>', re.DOTALL),
        ]
        snippets = []
        for sp in snippet_patterns:
            snippets = sp.findall(html)
            if snippets:
                break

        for i in range(min(num, len(titles))):
            title = self._strip_html(titles[i]).strip()
            snippet = ""
            if i < len(snippets):
                snippet = self._strip_html(snippets[i]).strip()
            if title and len(title) > 2:
                results.append({
                    "title": title,
                    "snippet": snippet[:200] if snippet else "",
                })

        return results

    def _search_bing(self, query: str, num: int) -> List[Dict[str, str]]:
        """Bing中国版搜索（国内直连，无需代理）"""
        url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&count={num}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            results = self._parse_bing(html, num)
            if not results:
                print(f"  ⚠ Bing搜索返回0条结果 (HTML {len(html)} bytes)")
            return results
        except Exception as e:
            print(f"  ⚠ Bing搜索失败: {e}")
            return []

    def _parse_bing(self, html: str, num: int) -> List[Dict[str, str]]:
        """解析Bing搜索结果（多种格式兼容）"""
        results = []

        # Bing HTML结构经常变，多种正则兼容
        # 格式1: <h2><a href="...">title</a></h2>
        # 格式2: <h2 class="..."><a href="...">title</a></h2>
        title_patterns = [
            re.compile(r'<h2[^>]*>\s*<a[^>]*>(.*?)</a>', re.DOTALL),
            re.compile(r'class="b_algo"[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL),
            re.compile(r'<h2[^>]*>(.*?)</h2>', re.DOTALL),
        ]
        titles = []
        for tp in title_patterns:
            titles = tp.findall(html)
            if titles:
                break

        # 摘要多种格式
        snippet_patterns = [
            re.compile(r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', re.DOTALL | re.IGNORECASE),
            re.compile(r'class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', re.DOTALL),
            re.compile(r'class="b_caption"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
        ]
        snippets = []
        for sp in snippet_patterns:
            snippets = sp.findall(html)
            if snippets:
                break

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
        """DuckDuckGo搜索（需要代理）"""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
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
            results = self._parse_ddg(html, num)
            if not results:
                print(f"  ⚠ DDG搜索返回0条结果 (HTML {len(html)} bytes)")
            return results
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


# ===== 独立测试模式 =====
if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("WebSearcher 独立测试")
    print("=" * 50)

    config = {
        "timeout": 15,
        "proxy": "http://127.0.0.1:7890",
    }
    searcher = WebSearcher(config)

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "2026年8月 有趣新闻 科技"
    print(f"\n搜索: {query}\n")

    # 测试百度
    print("--- 百度 ---")
    baidu_results = searcher._search_baidu(query, 5)
    for i, r in enumerate(baidu_results, 1):
        print(f"  [{i}] {r['title']}")
        if r['snippet']:
            print(f"      {r['snippet'][:80]}")

    # 测试Bing
    print("\n--- Bing ---")
    bing_results = searcher._search_bing(query, 5)
    for i, r in enumerate(bing_results, 1):
        print(f"  [{i}] {r['title']}")
        if r['snippet']:
            print(f"      {r['snippet'][:80]}")

    # 测试综合搜索
    print("\n--- 综合搜索 ---")
    all_results = searcher.search(query, 5)
    print(f"共 {len(all_results)} 条结果")
    for i, r in enumerate(all_results, 1):
        print(f"  [{i}] {r['title']}")
        if r['snippet']:
            print(f"      {r['snippet'][:80]}")
