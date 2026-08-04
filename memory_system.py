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
                 label_snapshot: dict = None):
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

    # ─── 记忆管理 ─────────────────────────────

    def add_memory(self, content: str, category: str = "general",
                   importance: int = 5, dimension: str = "recent",
                   entity_ids: List[str] = None,
                   hexagram_binary: str = None,
                   hu_binary: str = None,
                   label_snapshot: dict = None) -> bool:
        """添加一条记忆，已存在则更新触发"""
        content = content.strip()
        if not content:
            return False

        for m in self.memories:
            if m.content == content:
                m.last_triggered = datetime.now().isoformat()
                m.trigger_count += 1
                m.importance = max(m.importance, importance)
                if entity_ids:
                    for eid in entity_ids:
                        if eid not in m.entity_ids:
                            m.entity_ids.append(eid)
                self._save_memories()
                return False  # 已存在

        mem = Memory(content, category, importance, dimension=dimension,
                     entity_ids=entity_ids,
                     hexagram_binary=hexagram_binary,
                     hu_binary=hu_binary,
                     label_snapshot=label_snapshot)
        self.memories.append(mem)
        self._save_memories()

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

以JSON格式返回：
{{"memories": [{{"content": "...", "category": "fact|preference|event|promise|emotion|insight|growth|general", "importance": 1-10, "dimension": "fact|recent|reflection|persona"}}]}}

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
