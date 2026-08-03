#!/usr/bin/env python3
"""
知乐实体图记忆引擎 — P0.8 + P0.14

把人、地点、物品、事件组织成实体节点，节点间有加权边。
说"小猫"能命中"猫咪"，想起一件事能带出相关的事。

核心机制：
  1. 实体节点（含别名）—— 标准名+别名列表，模糊匹配
  2. 加权边 —— 共现强度，同时出现的实体之间边权重+1
  3. 扩散激活 —— 命中一个实体后，沿边扩散到相邻实体
  4. 预置实体 —— 从USER.md/MEMORY.md预加载已知实体
"""

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple


class Entity:
    """实体节点"""

    def __init__(self, canonical_name: str, entity_type: str = "general",
                 description: str = "", aliases: List[str] = None,
                 entity_id: str = None, linked_memories: List[str] = None,
                 created_at: str = None, last_activated: str = None,
                 activation: float = 0.0):
        self.id = entity_id or self._make_id(canonical_name)
        self.canonical_name = canonical_name
        self.entity_type = entity_type  # person/place/object/event/interest
        self.description = description
        self.aliases = aliases or []
        self.linked_memories = linked_memories or []
        self.created_at = created_at or datetime.now().isoformat()
        self.last_activated = last_activated or self.created_at
        self.activation = activation

    @staticmethod
    def _make_id(name: str) -> str:
        return hashlib.md5(name.encode()).hexdigest()[:12]

    @property
    def all_names(self) -> List[str]:
        """标准名+所有别名，用于匹配"""
        names = [self.canonical_name] + self.aliases
        # 确保唯一且非空
        seen = set()
        result = []
        for n in names:
            n = n.strip()
            if n and n not in seen:
                seen.add(n)
                result.append(n)
        return result

    def matches(self, text: str) -> bool:
        """文本中是否提到了这个实体"""
        text_lower = text.lower()
        for name in self.all_names:
            if name.lower() in text_lower:
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "description": self.description,
            "aliases": self.aliases,
            "linked_memories": self.linked_memories,
            "created_at": self.created_at,
            "last_activated": self.last_activated,
            "activation": self.activation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entity":
        return cls(**d)


class EntityEdge:
    """实体间的加权边（共现强度）"""

    def __init__(self, source_id: str, target_id: str, weight: float = 1.0):
        self.source_id = source_id
        self.target_id = target_id
        self.weight = weight

    @property
    def key(self) -> str:
        """无向边key，排序确保一致性"""
        a, b = sorted([self.source_id, self.target_id])
        return f"{a}::{b}"

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EntityEdge":
        return cls(**d)


class EntityGraph:
    """实体图主控制器"""

    # 预置实体模板（用户可自行修改或删除，运行后会自动从对话中提取新实体）
    PRESET_ENTITIES = [
        # 人物示例（请替换为你的信息）
        {"canonical_name": "主人", "entity_type": "person",
         "aliases": ["用户"],
         "description": "AI的主人，请在USER.md中填写真实信息"},
        {"canonical_name": "AI", "entity_type": "person",
         "aliases": [],
         "description": "人格DNA驱动的AI角色"},

        # 兴趣示例
        {"canonical_name": "Python", "entity_type": "interest",
         "aliases": ["python", "py"],
         "description": "编程语言"},
    ]

    def __init__(self, graph_dir: str, llm_provider=None):
        self.graph_dir = Path(graph_dir)
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm_provider

        self.entities_file = self.graph_dir / "entities.json"
        self.edges_file = self.graph_dir / "edges.json"

        self.entities: Dict[str, Entity] = self._load_entities()
        self.edges: Dict[str, EntityEdge] = self._load_edges()

        # 首次初始化预置实体
        if not self.entities:
            self._init_preset_entities()

    # ─── 持久化 ───────────────────────────────

    def _load_entities(self) -> Dict[str, Entity]:
        if not self.entities_file.exists():
            return {}
        try:
            with open(self.entities_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {e["id"]: Entity.from_dict(e) for e in data}
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            return {}

    def _load_edges(self) -> Dict[str, EntityEdge]:
        if not self.edges_file.exists():
            return {}
        try:
            with open(self.edges_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {e["key"]: EntityEdge.from_dict(e) for e in data}
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            return {}

    def _save_entities(self):
        data = [e.to_dict() for e in self.entities.values()]
        with open(self.entities_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_edges(self):
        data = [{"key": k, **v.to_dict()} for k, v in self.edges.items()]
        with open(self.edges_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _init_preset_entities(self):
        """初始化预置实体"""
        for template in self.PRESET_ENTITIES:
            entity = Entity(**template)
            self.entities[entity.id] = entity
        self._save_entities()

    # ─── 实体管理 ─────────────────────────────

    def add_entity(self, name: str, entity_type: str = "general",
                   description: str = "", aliases: List[str] = None) -> Entity:
        """添加实体，已存在则更新"""
        entity_id = Entity._make_id(name)

        if entity_id in self.entities:
            entity = self.entities[entity_id]
            if description and not entity.description:
                entity.description = description
            if aliases:
                for a in aliases:
                    if a not in entity.aliases:
                        entity.aliases.append(a)
        else:
            entity = Entity(name, entity_type, description, aliases)
            self.entities[entity_id] = entity

        self._save_entities()
        return entity

    def add_alias(self, entity_id: str, alias: str):
        """给实体添加别名"""
        if entity_id in self.entities:
            entity = self.entities[entity_id]
            if alias not in entity.aliases and alias != entity.canonical_name:
                entity.aliases.append(alias)
                self._save_entities()

    def link_memory(self, entity_id: str, memory_id: str):
        """将记忆关联到实体"""
        if entity_id in self.entities:
            entity = self.entities[entity_id]
            if memory_id not in entity.linked_memories:
                entity.linked_memories.append(memory_id)
                self._save_entities()

    # ─── 边管理 ───────────────────────────────

    def add_edge(self, source_id: str, target_id: str, weight: float = 1.0):
        """添加或加强共现边"""
        if source_id == target_id:
            return
        edge = EntityEdge(source_id, target_id, weight)
        if edge.key in self.edges:
            self.edges[edge.key].weight += weight
        else:
            self.edges[edge.key] = edge
        self._save_edges()

    def add_co_occurrence_edges(self, entity_ids: List[str]):
        """多个实体共现时，两两建边"""
        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                self.add_edge(entity_ids[i], entity_ids[j])

    # ─── 匹配与检索 ───────────────────────────

    def match_entities(self, text: str) -> List[Entity]:
        """在文本中匹配提到的实体"""
        matched = []
        for entity in self.entities.values():
            if entity.matches(text):
                matched.append(entity)
        return matched

    def spread_activation(self, entity_ids: List[str],
                          hops: int = 1) -> List[Entity]:
        """从给定实体出发，沿边扩散激活"""
        activated: Set[str] = set(entity_ids)
        frontier = set(entity_ids)

        for _ in range(hops):
            next_frontier = set()
            for eid in frontier:
                for edge in self.edges.values():
                    neighbor = None
                    if edge.source_id == eid:
                        neighbor = edge.target_id
                    elif edge.target_id == eid:
                        neighbor = edge.source_id

                    if neighbor and neighbor not in activated:
                        # 边权越高，扩散概率越大
                        if edge.weight >= 1.0:
                            activated.add(neighbor)
                            next_frontier.add(neighbor)

            frontier = next_frontier
            if not frontier:
                break

        return [self.entities[eid] for eid in activated
                if eid in self.entities]

    def get_related_memories(self, entity_ids: List[str]) -> List[str]:
        """获取与实体关联的记忆ID列表"""
        memory_ids: Set[str] = set()
        for eid in entity_ids:
            if eid in self.entities:
                memory_ids.update(self.entities[eid].linked_memories)
        return list(memory_ids)

    def activate(self, entity_ids: List[str]):
        """标记实体被激活（更新时间）"""
        now = datetime.now().isoformat()
        for eid in entity_ids:
            if eid in self.entities:
                self.entities[eid].last_activated = now
                self.entities[eid].activation += 1.0
        self._save_entities()

    # ─── LLM实体提取 ──────────────────────────

    def extract_entities(self, text: str) -> List[Dict]:
        """用LLM从文本中提取实体"""
        if not self.llm:
            return []

        # 先用规则匹配（快，不花token）
        rule_matched = self.match_entities(text)
        if rule_matched:
            return [{"name": e.canonical_name, "type": e.entity_type,
                     "id": e.id} for e in rule_matched]

        # 规则没匹配到，用LLM提取（慢，花token）
        # 只在有实质内容时才调用
        if len(text.strip()) < 10:
            return []

        prompt = f"""从以下文本中提取实体（人名、地名、物品、事件、兴趣）。

文本：{text[:500]}

以JSON格式返回：
{{"entities": [{{"name": "标准名", "type": "person|place|object|event|interest|general", "aliases": ["别名1"]}}]}}

规则：
1. 只提取明确出现的实体
2. 别名是文本中对同一实体的其他称呼
3. 没有实体则返回空列表
只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是实体提取助手，只输出JSON。"},
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
            return data.get("entities", [])
        except (json.JSONDecodeError, KeyError, Exception):
            return []

    def process_extraction(self, text: str) -> Tuple[List[str], List[str]]:
        """
        处理文本：提取实体→匹配/创建→建边→返回实体ID和记忆ID
        返回: (entity_ids, related_memory_ids)
        """
        # 1. 先用规则匹配
        matched = self.match_entities(text)

        # 2. 规则没匹配到，用LLM提取
        if not matched:
            llm_entities = self.extract_entities(text)
            for e in llm_entities:
                name = e.get("name", "").strip()
                if name:
                    entity = self.add_entity(
                        name,
                        e.get("type", "general"),
                        aliases=e.get("aliases", []),
                    )
                    matched.append(entity)

        if not matched:
            return [], []

        # 3. 激活匹配的实体
        entity_ids = [e.id for e in matched]
        self.activate(entity_ids)

        # 4. 共现建边
        self.add_co_occurrence_edges(entity_ids)

        # 5. 扩散激活，获取相关记忆
        spread = self.spread_activation(entity_ids, hops=1)
        all_entity_ids = list(set(entity_ids + [e.id for e in spread]))
        related_memories = self.get_related_memories(all_entity_ids)

        return entity_ids, related_memories

    # ─── 统计 ─────────────────────────────────

    def get_stats(self) -> dict:
        type_count = {}
        for e in self.entities.values():
            t = e.entity_type
            type_count[t] = type_count.get(t, 0) + 1

        total_edges = len(self.edges)
        avg_weight = 0
        if total_edges > 0:
            avg_weight = sum(e.weight for e in self.edges.values()) / total_edges

        return {
            "total_entities": len(self.entities),
            "total_edges": total_edges,
            "avg_edge_weight": round(avg_weight, 2),
            "by_type": type_count,
        }
