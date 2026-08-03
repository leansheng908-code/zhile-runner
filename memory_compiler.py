#!/usr/bin/env python3
"""
知乐记忆编译层 — P0.29（Karpathy LLM Wiki 启发）

将零散记忆"预编译"成结构化知识页，不靠RAG临时检索拼凑，
而是主动整理成可复用的知识单元，知识持续复利累积。

四种页面类型：
  source_page     — 来源页：一批记忆的结构化摘要
  entity_page     — 实体页：人/物/概念的汇总（基于实体图节点）
  concept_page    — 概念页：被2+来源提到的主题（LLM归纳）
  comparison_page — 对比页：多来源立场不同时记录分歧

Lint健康检查：
  - 矛盾检测：同一实体有冲突信息
  - 孤立记忆：没有实体关联的记忆
  - 缺失链接：被提及但未建立关联的实体
  - 关联建议：可能相关但未连接的页对

运行方式：
  - compile() 由 daemon_thinker 定期调用
  - lint() 由 daemon_thinker 定期调用
  - get_compiled_context() 由 context_assembler 在对话时调用（零token）
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class CompiledPage:
    """编译后的知识页"""

    def __init__(self, page_id: str, page_type: str, title: str,
                 content: str, source_memory_ids: List[str] = None,
                 entity_ids: List[str] = None, tags: List[str] = None,
                 conflicts: List[Dict] = None,
                 created_at: str = None, last_updated: str = None):
        self.id = page_id
        self.type = page_type  # source/entity/concept/comparison
        self.title = title
        self.content = content
        self.source_memory_ids = source_memory_ids or []
        self.entity_ids = entity_ids or []
        self.tags = tags or []
        self.conflicts = conflicts or []
        self.created_at = created_at or datetime.now().isoformat()
        self.last_updated = last_updated or self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "title": self.title,
            "content": self.content,
            "source_memory_ids": self.source_memory_ids,
            "entity_ids": self.entity_ids, "tags": self.tags,
            "conflicts": self.conflicts,
            "created_at": self.created_at, "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompiledPage":
        return cls(
            page_id=d["id"], page_type=d["type"], title=d["title"],
            content=d["content"],
            source_memory_ids=d.get("source_memory_ids", []),
            entity_ids=d.get("entity_ids", []),
            tags=d.get("tags", []),
            conflicts=d.get("conflicts", []),
            created_at=d.get("created_at"),
            last_updated=d.get("last_updated"),
        )


class MemoryCompiler:
    """记忆编译层 — 将零散记忆编译成结构化知识页"""

    COMPILE_INTERVAL_TURNS = 30  # 每30轮编译一次
    LINT_INTERVAL_CYCLES = 8     # 每8个daemon周期lint一次
    MAX_PAGES = 200              # 页数上限
    MIN_MEMORIES_TO_COMPILE = 5  # 最少新记忆数才触发编译

    def __init__(self, memory_system, entity_graph, llm_provider, config: dict):
        self.memory = memory_system
        self.entities = entity_graph
        self.llm = llm_provider

        mem_dir = Path(config.get("memory_dir", "memory"))
        self.compiled_dir = mem_dir / "compiled"
        self.compiled_dir.mkdir(parents=True, exist_ok=True)

        self.pages_file = self.compiled_dir / "pages.json"
        self.index_file = self.compiled_dir / "index.json"
        self.state_file = self.compiled_dir / "state.json"

        self.pages: List[CompiledPage] = self._load_pages()
        self._state = self._load_state()
        self._lint_cycle_count = 0

    # ─── 持久化 ───────────────────────────────

    def _load_pages(self) -> List[CompiledPage]:
        if not self.pages_file.exists():
            return []
        try:
            with open(self.pages_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [CompiledPage.from_dict(p) for p in data]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def _save_pages(self):
        data = [p.to_dict() for p in self.pages]
        with open(self.pages_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._update_index()

    def _load_state(self) -> dict:
        default = {"last_compile_turn": 0, "last_compile_time": None,
                   "last_lint_time": None, "compile_count": 0}
        if not self.state_file.exists():
            return default
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except (json.JSONDecodeError, IOError):
            return default

    def _save_state(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def _update_index(self):
        """更新索引：页标题 + 标签 + 关联实体"""
        index = {
            "pages": [
                {"id": p.id, "type": p.type, "title": p.title,
                 "tags": p.tags, "entity_ids": p.entity_ids,
                 "last_updated": p.last_updated}
                for p in self.pages
            ],
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    # ─── 编译 ─────────────────────────────────

    def should_compile(self, turn_count: int) -> bool:
        """检查是否该编译"""
        last_turn = self._state.get("last_compile_turn", 0)
        return (turn_count - last_turn) >= self.COMPILE_INTERVAL_TURNS

    def compile(self, turn_count: int = 0, force: bool = False) -> dict:
        """编译循环：扫描记忆→分组→LLM编译→存页→更新索引"""
        if not self.memory or not self.memory.memories:
            return {"compiled": 0, "reason": "无记忆"}
        if not self.llm:
            return {"compiled": 0, "reason": "无LLM"}

        # 获取自上次编译以来的新记忆
        last_time = self._state.get("last_compile_time")
        if force or not last_time:
            new_memories = list(self.memory.memories)
        else:
            try:
                last_dt = datetime.fromisoformat(last_time)
                new_memories = [
                    m for m in self.memory.memories
                    if datetime.fromisoformat(m.created_at) > last_dt
                ]
            except (ValueError, TypeError):
                new_memories = list(self.memory.memories)

        if len(new_memories) < self.MIN_MEMORIES_TO_COMPILE and not force:
            return {"compiled": 0, "reason": f"新记忆不足（{len(new_memories)}/{self.MIN_MEMORIES_TO_COMPILE}）"}

        # 按维度分组
        by_dimension = {}
        for m in new_memories:
            dim = m.dimension or "recent"
            by_dimension.setdefault(dim, []).append(m)

        compiled_count = 0
        pages_created = []

        # 1. 来源页：每个维度的摘要
        for dim, mems in by_dimension.items():
            if len(mems) < 2:
                continue
            page = self._compile_source_page(dim, mems)
            if page:
                self.pages.append(page)
                pages_created.append(page)
                compiled_count += 1

        # 2. 概念页：跨维度归纳主题
        for cp in self._compile_concept_pages(new_memories):
            self.pages.append(cp)
            pages_created.append(cp)
            compiled_count += 1

        # 3. 对比页：检测冲突信息
        for cp in self._compile_comparison_pages(new_memories):
            self.pages.append(cp)
            pages_created.append(cp)
            compiled_count += 1

        # 4. 实体页：汇总每个实体信息
        if self.entities:
            for ep in self._compile_entity_pages(new_memories):
                existing = next(
                    (p for p in self.pages
                     if p.type == "entity" and p.entity_ids == ep.entity_ids), None)
                if existing:
                    existing.content = ep.content
                    existing.last_updated = datetime.now().isoformat()
                    for mid in ep.source_memory_ids:
                        if mid not in existing.source_memory_ids:
                            existing.source_memory_ids.append(mid)
                else:
                    self.pages.append(ep)
                    pages_created.append(ep)
                    compiled_count += 1

        # 修剪：保持页数上限
        if len(self.pages) > self.MAX_PAGES:
            self.pages.sort(key=lambda p: p.last_updated, reverse=True)
            self.pages = self.pages[:self.MAX_PAGES]

        self._save_pages()

        now = datetime.now().isoformat()
        self._state["last_compile_time"] = now
        self._state["last_compile_turn"] = turn_count
        self._state["compile_count"] = self._state.get("compile_count", 0) + 1
        self._save_state()

        return {
            "compiled": compiled_count,
            "new_memories": len(new_memories),
            "total_pages": len(self.pages),
            "pages_created": [
                {"type": p.type, "title": p.title} for p in pages_created],
        }

    def _compile_source_page(self, dimension: str, memories: list) -> Optional[CompiledPage]:
        """编译来源页：对一组同维度记忆做摘要"""
        mem_text = "\n".join(f"- {m.content}" for m in memories[:20])
        dim_names = {"recent": "近期记忆", "fact": "事实记忆",
                     "reflection": "反思记忆", "persona": "人格记忆"}
        dim_name = dim_names.get(dimension, dimension)

        prompt = f"""将以下{dim_name}整理成一个结构化摘要页。

记忆条目：
{mem_text}

要求：
1. 提炼核心主题和关键信息
2. 去重、合并相似条目
3. 用简洁的结构化文本输出
4. 标注2-5个关键词标签

格式：
标题：[一句话主题]
内容：[结构化摘要，200字以内]
标签：[关键词1, 关键词2, ...]

只输出上述格式，不要其他文字。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你是一个知识整理助手。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()
            title, content, tags = self._parse_page_result(result)
            if not title or not content:
                return None

            page_id = hashlib.md5(
                f"source:{dimension}:{title}".encode()).hexdigest()[:12]
            return CompiledPage(
                page_id=page_id, page_type="source", title=title,
                content=content, source_memory_ids=[m.id for m in memories],
                tags=tags)
        except Exception:
            return None

    def _compile_concept_pages(self, memories: list) -> List[CompiledPage]:
        """编译概念页：跨维度归纳被多次提到的主题"""
        if len(memories) < 3:
            return []

        mem_text = "\n".join(
            f"- [{m.dimension}] {m.content}" for m in memories[:30])

        prompt = f"""分析以下记忆条目，找出被2条以上记忆共同涉及的主题/概念。

记忆条目：
{mem_text}

对每个被多次涉及的主题，创建一个概念页：
1. 主题名称
2. 汇总不同维度对此主题的信息
3. 标注关键词标签

以JSON格式返回：
{{"concepts": [{{"title": "...", "content": "...", "tags": ["..."], "source_indices": [0, 1, 3]}}]}}

source_indices是上面记忆条目的序号（从0开始）。
如果没有被多次涉及的主题，返回空列表。
只返回JSON。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你是一个知识整理助手，只输出JSON。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            pages = []
            for concept in data.get("concepts", []):
                source_indices = concept.get("source_indices", [])
                source_ids = [memories[i].id for i in source_indices
                              if 0 <= i < len(memories)]
                if len(source_ids) < 2:
                    continue
                page_id = hashlib.md5(
                    f"concept:{concept['title']}".encode()).hexdigest()[:12]
                pages.append(CompiledPage(
                    page_id=page_id, page_type="concept",
                    title=concept["title"], content=concept["content"],
                    source_memory_ids=source_ids,
                    tags=concept.get("tags", [])))
            return pages
        except (json.JSONDecodeError, KeyError, Exception):
            return []

    def _compile_comparison_pages(self, memories: list) -> List[CompiledPage]:
        """编译对比页：检测信息冲突"""
        if len(memories) < 3:
            return []

        mem_text = "\n".join(
            f"- [{m.dimension}|{m.category}] {m.content}" for m in memories[:30])

        prompt = f"""分析以下记忆条目，找出互相矛盾或立场不同的信息对。

记忆条目：
{mem_text}

对每对冲突信息，创建一个对比页：
1. 冲突主题
2. 各方立场及来源
3. 标注关键词

以JSON格式返回：
{{"comparisons": [{{"title": "...", "content": "...", "conflicts": [{{"stance": "...", "source": "...", "memory_index": 0}}], "tags": ["..."]}}]}}

如果没有冲突信息，返回空列表。只返回JSON。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你是一个信息冲突检测助手，只输出JSON。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            pages = []
            for comp in data.get("comparisons", []):
                conflicts = comp.get("conflicts", [])
                source_ids = []
                for c in conflicts:
                    idx = c.get("memory_index", -1)
                    if 0 <= idx < len(memories):
                        source_ids.append(memories[idx].id)
                page_id = hashlib.md5(
                    f"comparison:{comp['title']}".encode()).hexdigest()[:12]
                pages.append(CompiledPage(
                    page_id=page_id, page_type="comparison",
                    title=comp["title"], content=comp["content"],
                    source_memory_ids=source_ids, conflicts=conflicts,
                    tags=comp.get("tags", [])))
            return pages
        except (json.JSONDecodeError, KeyError, Exception):
            return []

    def _compile_entity_pages(self, memories: list) -> List[CompiledPage]:
        """编译实体页：汇总每个实体相关信息"""
        if not self.entities:
            return []

        entity_memories = {}
        for m in memories:
            for eid in (m.entity_ids or []):
                entity_memories.setdefault(eid, []).append(m)

        pages = []
        for eid, mems in entity_memories.items():
            entity = self.entities.entities.get(eid)
            if not entity:
                continue

            entity_name = entity.canonical_name
            mem_text = "\n".join(f"- {m.content}" for m in mems[:15])

            content = f"实体：{entity_name}（类型：{entity.entity_type}）\n"
            content += f"别名：{', '.join(entity.aliases) if entity.aliases else '无'}\n"
            content += f"关联记忆数：{len(mems)}\n\n相关信息：\n{mem_text}"

            page_id = hashlib.md5(f"entity:{eid}".encode()).hexdigest()[:12]
            pages.append(CompiledPage(
                page_id=page_id, page_type="entity",
                title=entity_name, content=content,
                source_memory_ids=[m.id for m in mems],
                entity_ids=[eid],
                tags=[entity_name, entity.entity_type]))
        return pages

    @staticmethod
    def _parse_page_result(result: str) -> tuple:
        """解析LLM输出的页面格式"""
        title, content, tags = "", "", []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("标题：") or line.startswith("标题:"):
                title = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("内容：") or line.startswith("内容:"):
                content = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("标签：") or line.startswith("标签:"):
                tag_str = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                tags = [t.strip() for t in tag_str.replace("，", ",").split(",") if t.strip()]
        return title, content, tags

    # ─── Lint健康检查 ─────────────────────────

    def should_lint(self) -> bool:
        """检查是否该lint"""
        self._lint_cycle_count += 1
        return self._lint_cycle_count >= self.LINT_INTERVAL_CYCLES

    def lint(self) -> dict:
        """健康检查：找矛盾/孤立/缺失链接/建议新关联（零token）"""
        issues = {
            "contradictions": [], "orphan_memories": [],
            "missing_links": [], "suggestions": [],
            "total_memories": 0, "total_pages": len(self.pages),
        }

        if not self.memory or not self.memory.memories:
            return issues

        mems = self.memory.memories
        issues["total_memories"] = len(mems)

        # 1. 孤立记忆：没有实体关联且重要性>=5
        for m in mems:
            if not m.entity_ids and m.importance >= 5:
                issues["orphan_memories"].append({
                    "id": m.id, "content": m.content[:50],
                    "importance": m.importance})

        # 2. 缺失链接：记忆内容提到实体名但未关联
        if self.entities:
            for m in mems:
                matched = self.entities.match_entities(m.content)
                matched_ids = {e.id for e in matched}
                linked_ids = set(m.entity_ids or [])
                missing = matched_ids - linked_ids
                if missing:
                    missing_names = [
                        self.entities.entities[mid].canonical_name
                        for mid in missing
                        if mid in self.entities.entities]
                    if missing_names:
                        issues["missing_links"].append({
                            "memory_id": m.id, "content": m.content[:50],
                            "missing_entities": missing_names})

        # 3. 矛盾检测：检查对比页
        for p in self.pages:
            if p.type == "comparison" and p.conflicts:
                issues["contradictions"].append({
                    "page_id": p.id, "title": p.title,
                    "conflict_count": len(p.conflicts)})

        # 4. 关联建议：同标签但未互相关联的页
        tag_map = {}
        for p in self.pages:
            for tag in p.tags:
                tag_map.setdefault(tag, []).append(p)

        for tag, pages in tag_map.items():
            if len(pages) >= 2:
                for i in range(len(pages)):
                    for j in range(i + 1, len(pages)):
                        if (pages[j].id not in pages[i].source_memory_ids and
                                pages[i].id not in pages[j].source_memory_ids):
                            issues["suggestions"].append({
                                "tag": tag,
                                "page_a": pages[i].title,
                                "page_b": pages[j].title})

        # 截断
        issues["orphan_memories"] = issues["orphan_memories"][:10]
        issues["missing_links"] = issues["missing_links"][:10]
        issues["suggestions"] = issues["suggestions"][:10]

        self._state["last_lint_time"] = datetime.now().isoformat()
        self._save_state()
        self._lint_cycle_count = 0

        return issues

    # ─── 检索（零token）─────────────────────

    def get_compiled_context(self, query: str, max_pages: int = 3) -> str:
        """检索编译页：先读索引→关键词匹配→返回相关页内容"""
        if not self.pages:
            return ""

        query_lower = query.lower()
        scored = []
        for p in self.pages:
            score = 0
            if p.title.lower() in query_lower or query_lower in p.title.lower():
                score += 3
            for tag in p.tags:
                if tag.lower() in query_lower:
                    score += 2
            if any(word in p.content.lower()
                   for word in query_lower.split() if len(word) > 1):
                score += 1
            if score > 0:
                scored.append((p, score))

        if not scored:
            return ""

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:max_pages]

        parts = ["【编译知识】"]
        for p, _ in top:
            parts.append(f"  [{p.type}] {p.title}")
            parts.append(f"  {p.content[:200]}")
        return "\n".join(parts)

    # ─── 状态 ─────────────────────────────────

    def get_status(self) -> dict:
        """获取编译层状态"""
        type_counts = {}
        for p in self.pages:
            type_counts[p.type] = type_counts.get(p.type, 0) + 1
        return {
            "total_pages": len(self.pages),
            "by_type": type_counts,
            "last_compile_time": self._state.get("last_compile_time"),
            "last_lint_time": self._state.get("last_lint_time"),
            "compile_count": self._state.get("compile_count", 0),
        }
