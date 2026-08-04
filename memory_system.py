#!/usr/bin/env python3
"""
知乐记忆系统 — Phase 2 → P0.8/P0.14 升级

五维记忆架构（P0.14）：
  工作记忆（working）    — 当前对话滑动窗口（ContextAssembler已实现）
  近期记忆（recent）     — 跨对话重要信息，每次对话后LLM提取
  事实记忆（fact）       — 结构化事实（人物/事件/偏好/承诺）
  反思记忆（reflection） — 从对话中提取的洞察和反思
  人格记忆（persona）    — 人格演变轨迹记录

实体图关联（P0.8）：
  记忆不再孤立，通过实体图互相关联
  检索时做实体匹配→扩散激活→动态召回

记忆生命周期：
  产生 → 活跃（注入prompt）→ 衰减（每天-5%优先级）→ 归档（14天未触发）

遗忘曲线：
  priority = importance × max(0.3, 1.0 - days_since_trigger × 0.05)
  重要的事衰减慢，不重要的事很快沉底
"""

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# ─── 五维分类 + 细分类别 ─────────────────────

DIMENSION_NAMES = {
    "recent": "近期记忆",
    "fact": "事实记忆",
    "reflection": "反思记忆",
    "persona": "人格记忆",
}

# 细分类别（兼容旧版）
CATEGORY_NAMES = {
    "fact": "事实",
    "preference": "偏好",
    "event": "事件",
    "promise": "约定",
    "emotion": "情感",
    "insight": "洞察",
    "growth": "成长",
    "general": "其他",
}


class Memory:
    """单条记忆"""

    def __init__(self, content: str, category: str = "general",
                 importance: int = 5, created_at: str = None,
                 last_triggered: str = None, trigger_count: int = 0,
                 dimension: str = "recent", entity_ids: List[str] = None,
                 memory_id: str = None,
                 hexagram_binary: str = None, hu_binary: str = None,
                 label_snapshot: dict = None,
                 cues: List[str] = None, tags: List[str] = None):
        self.content = content
        self.category = category
        self.importance = max(1, min(10, importance))
        self.created_at = created_at or datetime.now().isoformat()
        self.last_triggered = last_triggered or self.created_at
        self.trigger_count = trigger_count
        self.dimension = dimension  # recent/fact/reflection/persona
        self.entity_ids = entity_ids or []
        self.id = memory_id or self._make_id(content, self.created_at)
        # P0.25: 卦象情绪标签
        self.hexagram_binary = hexagram_binary  # 存入时的卦象6位编码
        self.hu_binary = hu_binary  # 存入时的互卦6位编码
        # P0.42: 多策略共振快照（13系统精简标签向量）
        self.label_snapshot = label_snapshot  # {system_name: {key: value}}
        # P0.39: Cue-Tag-Content 三层关联图
        self.cues = cues or []   # 细粒度关键词（3-5个）
        self.tags = tags or []   # 语义标签桥梁（1-2个，≤2词）

    @staticmethod
    def _make_id(content: str, created_at: str) -> str:
        raw = f"{content[:50]}:{created_at}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_triggered": self.last_triggered,
            "trigger_count": self.trigger_count,
            "dimension": self.dimension,
            "entity_ids": self.entity_ids,
            "hexagram_binary": self.hexagram_binary,
            "hu_binary": self.hu_binary,
            "label_snapshot": self.label_snapshot,
            "cues": self.cues,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        return cls(
            content=d["content"], category=d.get("category", "general"),
            importance=d.get("importance", 5), created_at=d.get("created_at"),
            last_triggered=d.get("last_triggered"),
            trigger_count=d.get("trigger_count", 0),
            dimension=d.get("dimension", "recent"),
            entity_ids=d.get("entity_ids", []),
            memory_id=d.get("id"),
            hexagram_binary=d.get("hexagram_binary"),
            hu_binary=d.get("hu_binary"),
            label_snapshot=d.get("label_snapshot"),
            cues=d.get("cues", []),
            tags=d.get("tags", []),
        )

    def should_archive(self) -> bool:
        """超过14天未被触发 → 归档"""
        try:
            last = datetime.fromisoformat(self.last_triggered)
            return (datetime.now() - last).days > 14
        except (ValueError, TypeError):
            return False

    def priority(self) -> float:
        """优先级 = 重要性 × 衰减因子"""
        try:
            last = datetime.fromisoformat(self.last_triggered)
            days = (datetime.now() - last).days
        except (ValueError, TypeError):
            days = 0
        decay = max(0.3, 1.0 - days * 0.05)
        return self.importance * decay

    def boost(self, factor: float = 1.5) -> float:
        """实体激活后的优先级（临时提升）"""
        return self.priority() * factor


class MemoryResult:
    """P0.39 Phase 3: 三层检索统一结果

    将 Episodic 层和 Semantic 层的检索结果统一封装，
    便于综合排序和来源追踪。

    属性:
        memory: 原始 Memory 对象
        score: 综合评分（相关度 × 时间衰减）
        source: 来源层 ``"episodic" | "semantic"``
        topic: 来源主题名称（仅 Semantic 层结果有值）
    """

    def __init__(self, memory: Memory, score: float, source: str,
                 topic: str = None):
        self.memory = memory
        self.score = score
        self.source = source  # "episodic" | "semantic"
        self.topic = topic    # 来源主题（仅 semantic 层）

    def to_dict(self) -> dict:
        """转为字典表示"""
        return {
            "memory": self.memory.to_dict(),
            "score": round(self.score, 4),
            "source": self.source,
            "topic": self.topic,
        }

    def __repr__(self) -> str:
        topic_str = f", topic={self.topic}" if self.topic else ""
        return (f"MemoryResult(source={self.source}, score={self.score:.3f}"
                f"{topic_str})")


class MemorySystem:
    """记忆系统主控制器 — 五维+实体图"""

    def __init__(self, memory_dir: str, llm_provider=None,
                 entity_graph=None):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm_provider
        self.entity_graph = entity_graph

        self.memories_file = self.memory_dir / "memories.json"
        self.session_file = self.memory_dir / "session.json"
        self.archive_file = self.memory_dir / "archive.json"

        self.memories: List[Memory] = self._load_memories()
        self.session_history: List[Dict] = self._load_session()

        # P0.39 Phase 3: Topic 记忆层（可选，可通过 config 关闭）
        self.topic_enabled = True
        self.topic_file = self.memory_dir / "topics.json"
        self.topic_store: Dict[str, dict] = self._load_topics()
        # 为旧记忆自动补充 topic 标签
        if self.topic_enabled:
            self._backfill_topic_tags()

    # ─── 持久化 ───────────────────────────────

    def _load_memories(self) -> List[Memory]:
        if not self.memories_file.exists():
            return []
        try:
            with open(self.memories_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            memories = []
            for m in data:
                # 兼容旧版（无dimension/entity_ids/id字段）
                mem = Memory.from_dict(m)
                memories.append(mem)
            return memories
        except (json.JSONDecodeError, TypeError):
            return []

    def _load_session(self) -> List[Dict]:
        if not self.session_file.exists():
            return []
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("messages", [])[-60:]
        except (json.JSONDecodeError, TypeError):
            return []

    def _load_topics(self) -> Dict[str, dict]:
        """P0.39 Phase 3: 加载主题存储"""
        if not self.topic_file.exists():
            return {}
        try:
            with open(self.topic_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_topics(self):
        """P0.39 Phase 3: 保存主题存储"""
        with open(self.topic_file, "w", encoding="utf-8") as f:
            json.dump(self.topic_store, f, ensure_ascii=False, indent=2)

    def _backfill_topic_tags(self):
        """P0.39 Phase 3: 为旧记忆自动补充 topic 标签（向后兼容）

        遍历所有没有 tags 的记忆，自动提取主题关键词并关联到 topic_store。
        只在首次加载时执行一次，不会重复处理已有 tags 的记忆。
        """
        if not self.topic_enabled:
            return

        updated_memories = False
        updated_topics = False

        for mem in self.memories:
            if not mem.tags:
                topic = self.auto_extract_topic(mem)
                if topic:
                    mem.tags = [topic]
                    updated_memories = True

                    # 同时添加到 topic_store
                    if topic not in self.topic_store:
                        self.topic_store[topic] = {
                            "summary": f"自动提取主题: {topic}",
                            "related_memories": [mem.id],
                            "last_updated": datetime.now().isoformat(),
                        }
                        updated_topics = True
                    elif mem.id not in self.topic_store[topic].get(
                            "related_memories", []):
                        self.topic_store[topic]["related_memories"].append(
                            mem.id)
                        self.topic_store[topic]["last_updated"] = \
                            datetime.now().isoformat()
                        updated_topics = True

        if updated_memories:
            self._save_memories()
        if updated_topics:
            self._save_topics()

    def _save_memories(self):
        data = [m.to_dict() for m in self.memories]
        with open(self.memories_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_session(self, history: List[Dict]):
        """保存当前对话历史"""
        data = {
            "saved_at": datetime.now().isoformat(),
            "messages": history,
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def restore_session(self) -> List[Dict]:
        """恢复上次对话历史"""
        return self.session_history

    # ─── 记忆注入 ─────────────────────────────

    def get_memory_context(self, max_memories: int = 15) -> str:
        """获取静态记忆上下文（启动时用）"""
        return self._format_memories(max_memories)

    def get_relevant_memories(self, user_message: str,
                              max_memories: int = 15) -> str:
        """
        动态检索：根据用户消息做实体匹配→扩散激活→召回相关记忆
        每条用户消息调用一次
        """
        # 如果没有实体图，退化为静态检索
        if not self.entity_graph:
            return self._format_memories(max_memories)

        # 1. 实体匹配
        entity_ids, related_memory_ids = self.entity_graph.process_extraction(
            user_message
        )

        if not entity_ids:
            # 没匹配到实体，用静态检索
            return self._format_memories(max_memories)

        # 2. 分两批：实体关联的 + 补充的
        active = [m for m in self.memories if not m.should_archive()]

        # 实体关联的记忆（优先级提升）
        entity_linked = []
        for m in active:
            if m.id in related_memory_ids or set(m.entity_ids) & set(entity_ids):
                entity_linked.append(m)

        # 补充记忆（按优先级填充）
        remaining = [m for m in active if m not in entity_linked]
        remaining.sort(key=lambda m: m.priority(), reverse=True)

        # 组合：实体关联的优先，不足的用补充记忆填满
        combined = entity_linked + remaining
        top = combined[:max_memories]

        # 触发记录
        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        self._save_memories()

        return self._format_memory_list(top)

    def _format_memories(self, max_memories: int) -> str:
        """静态检索：按优先级排序取top N"""
        active = [m for m in self.memories if not m.should_archive()]
        if not active:
            return ""

        active.sort(key=lambda m: m.priority(), reverse=True)
        top = active[:max_memories]

        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        self._save_memories()

        return self._format_memory_list(top)

    def _format_memory_list(self, memories: List[Memory]) -> str:
        """格式化记忆列表为注入文本"""
        if not memories:
            return ""

        # 按维度分组
        by_dimension = {}
        for m in memories:
            dim = m.dimension
            if dim not in by_dimension:
                by_dimension[dim] = []
            by_dimension[dim].append(m)

        parts = []
        for dim in ["fact", "recent", "reflection", "persona"]:
            if dim not in by_dimension:
                continue
            name = DIMENSION_NAMES.get(dim, dim)
            parts.append(f"【{name}】")
            for m in by_dimension[dim]:
                cat = CATEGORY_NAMES.get(m.category, m.category)
                parts.append(f"  - [{cat}] {m.content}")

        return "\n".join(parts)

    # ─── P0.39: Cue-Tag提取 ──────────────────

    def extract_cues_tags(self, content: str) -> Tuple[List[str], List[str]]:
        """P0.39: 用LLM从记忆内容中提取Cue和Tag

        Cue: 3-5个细粒度关键词，用于精确检索匹配
        Tag: 1-2个语义标签（≤2词），作为Cue→Content的桥梁
        """
        if not self.llm or len(content.strip()) < 5:
            return [], []

        prompt = f"""从以下记忆内容中提取检索关键词和语义标签。

记忆内容：{content[:500]}

提取规则：
1. 提取3-5个细粒度关键词作为Cue，用于精确匹配
   - 应是内容中的具体实体、概念或术语
   - 避免泛化词（如"事情"、"东西"等）
2. 提取1-2个语义标签作为Tag，每个标签不超过2个词
   - 应是概括性的语义类别（如"编程经验"、"项目记录"、"个人偏好"）

以JSON格式返回：
{{"cues": ["关键词1", "关键词2", ...], "tags": ["标签1", "标签2"]}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是记忆标注助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = ""
            for chunk in self.llm.chat(messages, stream=True):
                result += chunk
            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]
            data = json.loads(result)
            return data.get("cues", []), data.get("tags", [])
        except (json.JSONDecodeError, KeyError, TypeError, Exception):
            return [], []

    # ─── P0.39 Phase 3: Topic 记忆层 ──────────

    def add_topic(self, topic_name: str, summary: str,
                  memory_ids: List[str]) -> bool:
        """添加或更新主题

        参数:
            topic_name: 主题名称
            summary: 主题摘要描述
            memory_ids: 相关记忆 ID 列表

        返回:
            ``True`` 表示新建主题，``False`` 表示更新已有主题
        """
        is_new = topic_name not in self.topic_store
        existing_ids = set()
        if not is_new:
            existing_ids = set(
                self.topic_store[topic_name].get("related_memories", []))

        self.topic_store[topic_name] = {
            "summary": summary,
            "related_memories": list(existing_ids | set(memory_ids)),
            "last_updated": datetime.now().isoformat(),
        }
        self._save_topics()
        return is_new

    def get_topic(self, topic_name: str) -> Optional[dict]:
        """获取主题信息

        参数:
            topic_name: 主题名称

        返回:
            ``{summary, related_memories, last_updated}`` 或 ``None``
        """
        return self.topic_store.get(topic_name)

    def search_topics(self, keyword: str) -> List[dict]:
        """搜索相关主题

        在主题名称和摘要中匹配关键词。

        参数:
            keyword: 搜索关键词

        返回:
            匹配的主题列表，每项为
            ``{name, summary, related_memories, last_updated}``
        """
        if not keyword:
            return []
        keyword_lower = keyword.lower()
        results = []
        for name, info in self.topic_store.items():
            if (keyword_lower in name.lower() or
                    keyword_lower in info.get("summary", "").lower()):
                results.append({"name": name, **info})
        return results

    def list_topics(self) -> List[str]:
        """列出所有主题名称

        返回:
            主题名称列表
        """
        return list(self.topic_store.keys())

    def auto_extract_topic(self, memory: Memory) -> Optional[str]:
        """从记忆中自动提取主题关键词

        提取优先级：
        1. 记忆的 ``tags``（如果存在）
        2. ``dimension`` + ``category`` 组合推断

        参数:
            memory: 记忆对象

        返回:
            主题名称字符串，无法提取时返回 ``None``
        """
        # 优先使用 tags
        if memory.tags:
            return memory.tags[0]

        # 退化：从 dimension + category 推断
        dim_map = {
            "fact": "事实", "recent": "近期",
            "reflection": "反思", "persona": "人格",
        }
        cat_map = {
            "fact": "事实", "preference": "偏好", "event": "事件",
            "promise": "约定", "emotion": "情感", "insight": "洞察",
            "growth": "成长", "general": "其他",
        }
        dim_name = dim_map.get(memory.dimension, memory.dimension)
        cat_name = cat_map.get(memory.category, memory.category)

        if dim_name != cat_name:
            return f"{dim_name}-{cat_name}"
        return dim_name

    def retrieve_three_layer(
        self, query: str, max_results: int = 5
    ) -> List["MemoryResult"]:
        """三层记忆检索接口

        P0.39 Phase 3: 统一 Episodic + Semantic 两层检索，
        按相关度和时间衰减综合排序。

        - **Episodic 层**: 基于内容的记忆检索（关键词/Cue/Tag 匹配）
        - **Semantic 层**: 从 ``topic_store`` 检索相关主题下的记忆
        - **综合排序**: 按相关度 × 优先级（含时间衰减）合并

        参数:
            query: 查询文本
            max_results: 最大返回数量

        返回:
            ``MemoryResult`` 列表，按综合评分降序排列
        """
        results: List[MemoryResult] = []
        seen_ids: set = set()

        # 查询分词（处理中英文混排边界）
        query_lower = query.lower()
        # 在 CJK-ASCII 边界插入空格，使 "Python编程" → "python 编程"
        query_lower = re.sub(
            r'([\u4e00-\u9fff])([a-zA-Z0-9])', r'\1 \2', query_lower)
        query_lower = re.sub(
            r'([a-zA-Z0-9])([\u4e00-\u9fff])', r'\1 \2', query_lower)
        query_tokens = set(
            t for t in re.split(r'[，。！？\s,\.!?;:、]+', query_lower)
            if len(t) >= 2
        )

        # ── Layer 1: Episodic — 基于内容的记忆检索 ──
        for mem in self.memories:
            if mem.should_archive() or mem.id in seen_ids:
                continue

            content_lower = mem.content.lower()
            mem_cues = set(c.lower() for c in (mem.cues or []))
            mem_tags = set(t.lower() for t in (mem.tags or []))

            # 计算匹配分
            match_score = 0.0
            # 内容匹配
            content_hits = sum(
                1 for token in query_tokens if token in content_lower)
            match_score += content_hits * 0.3
            # Cue 匹配
            cue_hits = len(query_tokens & mem_cues)
            match_score += cue_hits * 0.5
            # Tag 匹配
            tag_hits = len(query_tokens & mem_tags)
            match_score += tag_hits * 0.4

            if match_score > 0:
                # 综合分 = 匹配分 × 优先级（含时间衰减）
                combined = match_score * mem.priority()
                results.append(MemoryResult(mem, combined, "episodic"))
                seen_ids.add(mem.id)

        # ── Layer 2: Semantic — 从 topic_store 检索 ──
        if self.topic_enabled and self.topic_store:
            for topic_name, topic_info in self.topic_store.items():
                topic_lower = topic_name.lower()
                summary_lower = topic_info.get("summary", "").lower()

                # 主题名/摘要与 query 的匹配度
                topic_match = 0.0
                for token in query_tokens:
                    if token in topic_lower or token in summary_lower:
                        topic_match += 0.5

                if topic_match > 0:
                    related_ids = topic_info.get("related_memories", [])
                    for mem in self.memories:
                        if (mem.id in related_ids and
                                mem.id not in seen_ids and
                                not mem.should_archive()):
                            combined = topic_match * mem.priority() * 0.8
                            results.append(MemoryResult(
                                mem, combined, "semantic", topic_name))
                            seen_ids.add(mem.id)

        # 综合排序
        results.sort(key=lambda r: r.score, reverse=True)

        # 触发记录
        now = datetime.now().isoformat()
        for r in results[:max_results]:
            r.memory.trigger_count += 1
            r.memory.last_triggered = now
        self._save_memories()

        return results[:max_results]

    # ─── 记忆管理 ─────────────────────────────

    def add_memory(self, content: str, category: str = "general",
                   importance: int = 5, dimension: str = "recent",
                   entity_ids: List[str] = None,
                   hexagram_binary: str = None,
                   hu_binary: str = None,
                   label_snapshot: dict = None,
                   cues: List[str] = None,
                   tags: List[str] = None) -> bool:
        """添加一条记忆，已存在则更新触发
        P0.39: 自动提取Cue和Tag（如果未提供且有LLM）
        """
        content = content.strip()
        if not content:
            return False

        # P0.39: 未提供cues/tags时自动提取
        if cues is None and tags is None and self.llm:
            cues, tags = self.extract_cues_tags(content)

        for m in self.memories:
            if m.content == content:
                m.last_triggered = datetime.now().isoformat()
                m.trigger_count += 1
                m.importance = max(m.importance, importance)
                if entity_ids:
                    for eid in entity_ids:
                        if eid not in m.entity_ids:
                            m.entity_ids.append(eid)
                # P0.39: 补充cues/tags如果旧记忆缺失
                if cues and not m.cues:
                    m.cues = cues
                if tags and not m.tags:
                    m.tags = tags
                self._save_memories()
                return False  # 已存在

        mem = Memory(content, category, importance, dimension=dimension,
                     entity_ids=entity_ids,
                     hexagram_binary=hexagram_binary,
                     hu_binary=hu_binary,
                     label_snapshot=label_snapshot,
                     cues=cues, tags=tags)
        self.memories.append(mem)
        self._save_memories()

        # P0.39 Phase 3: 自动提取 topic 并关联到 topic_store
        if self.topic_enabled:
            topic = self.auto_extract_topic(mem)
            if topic:
                if topic not in self.topic_store:
                    self.topic_store[topic] = {
                        "summary": f"自动提取主题: {topic}",
                        "related_memories": [mem.id],
                        "last_updated": datetime.now().isoformat(),
                    }
                elif mem.id not in self.topic_store[topic].get(
                        "related_memories", []):
                    self.topic_store[topic]["related_memories"].append(mem.id)
                    self.topic_store[topic]["last_updated"] = \
                        datetime.now().isoformat()
                self._save_topics()

        # 关联到实体图
        if self.entity_graph and entity_ids:
            for eid in entity_ids:
                self.entity_graph.link_memory(eid, mem.id)

        return True  # 新增

    def remove_memory(self, index: int) -> bool:
        """按索引删除记忆"""
        active = [m for m in self.memories if not m.should_archive()]
        active.sort(key=lambda m: m.priority(), reverse=True)
        if 0 <= index < len(active):
            target = active[index]
            self.memories.remove(target)
            self._save_memories()
            return True
        return False

    def list_memories(self, category: str = None,
                      dimension: str = None) -> List[Memory]:
        """列出记忆（按优先级排序）"""
        result = [m for m in self.memories if not m.should_archive()]
        if category:
            result = [m for m in result if m.category == category]
        if dimension:
            result = [m for m in result if m.dimension == dimension]
        result.sort(key=lambda m: m.priority(), reverse=True)
        return result

    def archive_old(self) -> int:
        """归档过期记忆，返回归档数量"""
        to_archive = [m for m in self.memories if m.should_archive()]
        if not to_archive:
            return 0

        archive_data = []
        if self.archive_file.exists():
            try:
                with open(self.archive_file, "r", encoding="utf-8") as f:
                    archive_data = json.load(f)
            except json.JSONDecodeError:
                pass
        archive_data.extend([m.to_dict() for m in to_archive])
        with open(self.archive_file, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)

        self.memories = [m for m in self.memories if not m.should_archive()]
        self._save_memories()
        return len(to_archive)

    # ─── P0.25 卦象记忆 ──────────────────────

    def boost_on_bian(self, bian_info: dict, max_boost: int = 3,
                      recent_count: int = 5):
        """变卦事件通知：提升最近记忆的优先级
        bian_info: hexagram_tracker.update()返回的result["bian"]
        max_boost: 最大提升值（变卦幅度越大提升越多）
        recent_count: 提升最近几条记忆
        """
        changed_count = bian_info.get("changed_count", 1)
        boost = min(max_boost, changed_count)  # 每变一条爻+1，上限max_boost

        # 给最近N条记忆提升重要性
        recent = sorted(self.memories,
                        key=lambda m: m.created_at, reverse=True)[:recent_count]
        now = datetime.now().isoformat()
        for m in recent:
            m.importance = min(10, m.importance + boost)
            m.last_triggered = now  # 变卦时刻重新激活
        if recent:
            self._save_memories()
        return len(recent)

    @staticmethod
    def _hexagram_similarity(binary_a: str, binary_b: str) -> float:
        """卦象相似度（0.0~1.0）：相同位数越多越相似"""
        if not binary_a or not binary_b:
            return 0.0
        matches = sum(1 for a, b in zip(binary_a, binary_b) if a == b)
        return matches / 6.0

    def get_relevant_memories_with_hexagram(
        self, user_message: str, current_hexagram_binary: str = None,
        current_hu_binary: str = None, max_memories: int = 15,
        hex_weight: float = 0.3, hu_weight: float = 0.2,
        hu_resonance_boost: float = 0.5
    ) -> str:
        """P0.25 Phase 2: 卦象加权的记忆检索
        在现有实体匹配基础上，叠加卦象情绪共振权重 + 互卦深层关联召回

        三层加权：
        1. 实体匹配（内容关联）— 最高优先级
        2. 卦象相似度（情绪共振）— 同卦象的记忆更可能相关
        3. 互卦深层召回（跨话题深层关联）— 互卦完全相同的记忆即使内容
           无关也会被拉入候选，因为深层心理结构相同

        参数：
        - hex_weight: 卦象相似度权重（0~1）
        - hu_weight: 互卦相似度权重（0~1）
        - hu_resonance_boost: 互卦完全匹配时的额外提升（0~1）
        """
        active = [m for m in self.memories if not m.should_archive()]
        if not active:
            return ""

        # 实体匹配（如果有实体图）
        entity_linked = []
        remaining = []
        if self.entity_graph:
            entity_ids, related_memory_ids = self.entity_graph.process_extraction(
                user_message
            )
            for m in active:
                if m.id in related_memory_ids or set(m.entity_ids) & set(entity_ids):
                    entity_linked.append(m)
                else:
                    remaining.append(m)
        else:
            remaining = list(active)

        # P0.25: 卦象加权排序 + 互卦深层召回
        if current_hexagram_binary:
            # 互卦深层召回：互卦完全相同的记忆即使不在实体匹配中也被拉入
            hu_resonance = []
            if current_hu_binary:
                hu_resonance = [
                    m for m in remaining
                    if m.hu_binary and m.hu_binary == current_hu_binary
                ]
                # 从remaining中移除已通过互卦召回的
                remaining = [m for m in remaining if m not in hu_resonance]

            # 对remaining做卦象加权排序
            for m in remaining:
                hex_sim = self._hexagram_similarity(
                    current_hexagram_binary, m.hexagram_binary or "")
                hu_sim = self._hexagram_similarity(
                    current_hu_binary or "", m.hu_binary or "")
                m._hex_boost = m.priority() * (
                    1 + hex_sim * hex_weight + hu_sim * hu_weight)
            remaining.sort(key=lambda m: getattr(m, '_hex_boost', m.priority()),
                           reverse=True)

            # 互卦共振的记忆给予额外提升后排入
            for m in hu_resonance:
                m._hex_boost = m.priority() * (1 + hu_resonance_boost)

            # 组合：实体关联 > 互卦共振 > 卦象加权
            combined = entity_linked + hu_resonance + remaining
        else:
            # 没有卦象信息时退化为纯优先级排序
            remaining.sort(key=lambda m: m.priority(), reverse=True)
            combined = entity_linked + remaining

        top = combined[:max_memories]

        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        self._save_memories()

        return self._format_memory_list(top)

    def get_relevant_memories_with_resonance(
        self, user_message: str, current_snapshot: dict = None,
        max_memories: int = 15
    ) -> str:
        """P0.42: 多策略共振加权记忆检索

        使用13系统多策略共振引擎替代旧版卦象单一加权。
        三层排序：
        1. 实体匹配（内容关联）— 最高优先级
        2. 多策略共振（13系统加权）— 共振分高的记忆更可能相关
        3. 优先级排序（重要性+衰减）— 兜底

        参数：
        - current_snapshot: ResonanceEngine.generate_snapshot() 或
                           ResonanceEngine.extract_compact_snapshot() 的返回值
        """
        active = [m for m in self.memories if not m.should_archive()]
        if not active:
            return ""

        # 实体匹配
        entity_linked = []
        remaining = []
        if self.entity_graph:
            entity_ids, related_memory_ids = self.entity_graph.process_extraction(
                user_message)
            for m in active:
                if m.id in related_memory_ids or set(m.entity_ids) & set(entity_ids):
                    entity_linked.append(m)
                else:
                    remaining.append(m)
        else:
            remaining = list(active)

        # 多策略共振加权
        if current_snapshot:
            try:
                from resonance_engine import ResonanceEngine
                engine = ResonanceEngine()
                for m in remaining:
                    if m.label_snapshot:
                        res_score = engine.calculate(current_snapshot, m.label_snapshot)
                    else:
                        res_score = 1.0  # 无快照的记忆用中性分
                    m._resonance_raw = res_score  # 原始共振分（供瞬时感知层使用）
                    m._resonance_boost = m.priority() * res_score
                remaining.sort(
                    key=lambda m: getattr(m, '_resonance_boost', m.priority()),
                    reverse=True)
            except Exception:
                remaining.sort(key=lambda m: m.priority(), reverse=True)
        else:
            remaining.sort(key=lambda m: m.priority(), reverse=True)

        combined = entity_linked + remaining
        top = combined[:max_memories]

        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        self._last_top_memories = top  # 供瞬时感知层读取共振分
        self._save_memories()

        return self._format_memory_list(top)

    def extract_from_conversation(self, history: List[Dict],
                                   hexagram_binary: str = None,
                                   hu_binary: str = None,
                                   label_snapshot: dict = None) -> int:
        """对话结束后，用LLM提取值得记住的信息+实体
        P0.25: 存入时打卦象情绪标签
        """
        if not self.llm or len(history) < 4:
            return 0

        recent = history[-12:]
        conv_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '知乐'}: {m['content']}"
            for m in recent
        )

        prompt = f"""分析以下对话，提取值得长期记住的信息。

对话内容：
{conv_text}

提取规则：
1. 只提取具体的、可复用的信息（用户偏好、事实、约定、重要事件）
2. 忽略寒暄、情绪表达、一次性闲聊
3. 提取对话中的洞察或反思（如果有）
4. 每条记忆用简洁的一句话描述
5. 如果没有值得记住的信息，返回空列表

记忆维度分类：
- fact: 结构化事实（人物信息、事件、偏好、承诺）
- recent: 近期发生的事
- reflection: 从对话中产生的洞察或反思
- persona: 知乐自己的人格变化或成长

P0.39 Cue-Tag标注：
- cues: 3-5个细粒度关键词，用于检索匹配（具体实体/概念/术语）
- tags: 1-2个语义标签，每个不超过2个词（概括性类别）

以JSON格式返回：
{{"memories": [{{"content": "...", "category": "fact|preference|event|promise|emotion|insight|growth|general", "importance": 1-10, "dimension": "fact|recent|reflection|persona", "cues": ["关键词1", "关键词2"], "tags": ["标签1"]}}]}}

只返回JSON，不要其他文字。"""

        messages = [
            {"role": "system", "content": "你是一个信息提取助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = ""
            for chunk in self.llm.chat(messages, stream=True):
                result += chunk

            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            count = 0
            new_memory_ids = []

            for m in data.get("memories", []):
                # 实体提取
                entity_ids = []
                if self.entity_graph:
                    content = m["content"]
                    matched = self.entity_graph.match_entities(content)
                    entity_ids = [e.id for e in matched]

                if self.add_memory(
                    m["content"],
                    m.get("category", "general"),
                    m.get("importance", 5),
                    dimension=m.get("dimension", "recent"),
                    entity_ids=entity_ids,
                    hexagram_binary=hexagram_binary,
                    hu_binary=hu_binary,
                    label_snapshot=label_snapshot,
                    cues=m.get("cues"),
                    tags=m.get("tags"),
                ):
                    count += 1
                    # 记录新记忆ID用于实体关联
                    for mem in self.memories:
                        if mem.content == m["content"]:
                            new_memory_ids.append((mem.id, entity_ids))
                            break

            # 批量建立共现边
            if self.entity_graph and len(new_memory_ids) > 1:
                all_entity_ids = set()
                for _, eids in new_memory_ids:
                    all_entity_ids.update(eids)
                if len(all_entity_ids) > 1:
                    self.entity_graph.add_co_occurrence_edges(list(all_entity_ids))

            return count
        except (json.JSONDecodeError, KeyError, Exception):
            return 0

    # ─── 统计 ─────────────────────────────────

    def get_stats(self) -> dict:
        active = [m for m in self.memories if not m.should_archive()]
        archived = len(self.memories) - len(active)
        by_category = {}
        by_dimension = {}
        for m in active:
            name = CATEGORY_NAMES.get(m.category, m.category)
            by_category[name] = by_category.get(name, 0) + 1
            dim = DIMENSION_NAMES.get(m.dimension, m.dimension)
            by_dimension[dim] = by_dimension.get(dim, 0) + 1

        stats = {
            "total": len(self.memories),
            "active": len(active),
            "archived": archived,
            "by_category": by_category,
            "by_dimension": by_dimension,
            "has_session": bool(self.session_history),
            "session_messages": len(self.session_history),
            "hexagram_tagged": sum(1 for m in active if m.hexagram_binary),
        }

        if self.entity_graph:
            stats["entity_graph"] = self.entity_graph.get_stats()

        return stats
