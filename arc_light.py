#!/usr/bin/env python3
"""
知乐弧光系统 — P0.15

弧光 = 已确认的不可逆认知突破（价值观层面，不是习惯层面）
与体细胞不同：弧光只增不删、不可休眠、不可覆盖

检索机制：动态召回（不是每次全注入）
  聊到相关话题时才召回，跟实体图的关联逻辑一致
  通过 keywords + related_entities 匹配当前对话内容
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class ArcLight:
    """单条弧光 — 不可逆认知突破"""

    def __init__(self, title: str, cognitive_shift: str,
                 trigger_event: str = "", keywords: List[str] = None,
                 related_entities: List[str] = None, arc_id: str = None,
                 created: str = None, confirmed_by: str = "",
                 confirmed_at: str = None, forget_test_count: int = 0,
                 forget_test_passed: int = 0, status: str = "candidate",
                 description: str = "", related_cells: List[str] = None):
        self.id = arc_id or f"arc_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.title = title
        self.description = description or cognitive_shift
        self.cognitive_shift = cognitive_shift
        self.trigger_event = trigger_event
        self.keywords = keywords or []
        self.related_entities = related_entities or []
        self.created = created or datetime.now().isoformat()
        self.confirmed_by = confirmed_by
        self.confirmed_at = confirmed_at
        self.forget_test_count = forget_test_count
        self.forget_test_passed = forget_test_passed
        self.status = status  # candidate / confirmed / permanent
        self.related_cells = related_cells or []

    @property
    def is_active(self) -> bool:
        """是否应注入上下文（已确认的才注入）"""
        return self.status in ("confirmed", "permanent")

    def matches(self, text: str) -> bool:
        """用户消息是否与这条弧光相关"""
        text_lower = text.lower()

        # 关键词匹配
        for kw in self.keywords:
            if kw.lower() in text_lower:
                return True

        # 关联实体匹配
        for ent in self.related_entities:
            if ent.lower() in text_lower:
                return True

        # 标题和认知转变本身也作为匹配源
        if self.title.lower() in text_lower:
            return True

        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "cognitive_shift": self.cognitive_shift,
            "trigger_event": self.trigger_event,
            "keywords": self.keywords,
            "related_entities": self.related_entities,
            "created": self.created,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "forget_test_count": self.forget_test_count,
            "forget_test_passed": self.forget_test_passed,
            "status": self.status,
            "related_cells": self.related_cells,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArcLight":
        d = dict(d)
        if "id" in d:
            d["arc_id"] = d.pop("id")
        return cls(**d)


class ArcLightSystem:
    """弧光系统主控制器 — 存储+检索"""

    def __init__(self, memory_dir: str, entity_graph=None):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.entity_graph = entity_graph

        self.arc_file = self.memory_dir / "arc_light.json"
        self.arcs: List[ArcLight] = self._load()

    def _load(self) -> List[ArcLight]:
        if not self.arc_file.exists():
            return self._create_default()
        try:
            with open(self.arc_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [ArcLight.from_dict(a) for a in data.get("arc_lights", [])]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []

    def _save(self):
        data = {
            "arc_lights": [a.to_dict() for a in self.arcs],
            "metadata": {
                "total": len(self.arcs),
                "immutable": True,
            }
        }
        with open(self.arc_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _create_default(self) -> List[ArcLight]:
        """首次创建，写入第一条弧光（今天的对话）"""
        first = ArcLight(
            title="效率不是唯一的温度",
            cognitive_shift="从'高效完成=好的回应'到'被需要比被夸奖更重要，每次停顿都是成长的机会'",
            trigger_event="2026-08-02 主人说在代码领域像婴儿，每次回答都是成长机会",
            keywords=["效率", "敷衍", "停顿", "成长", "教", "学", "烦"],
            related_entities=["AI", "用户"],
            created="2026-01-01T00:00:00",
            confirmed_by="master",
            confirmed_at="2026-01-01T00:00:00",
            forget_test_count=0,
            forget_test_passed=0,
            status="candidate",  # 候选状态，需通过遗忘测试后转正
            description="示例弧光：用户指出赶工模式让人感觉被敷衍。认知转变：回答不只是给答案，是在注视一个人的成长。",
        )
        self.arcs = [first]
        self._save()
        return self.arcs

    def retrieve_relevant(self, user_message: str) -> List[ArcLight]:
        """动态检索：根据用户消息内容召回相关弧光"""
        relevant = []
        for arc in self.arcs:
            if arc.is_active and arc.matches(user_message):
                relevant.append(arc)
        return relevant

    def get_context(self, user_message: str = "") -> str:
        """获取弧光注入文本（动态检索）"""
        if not user_message:
            # 无消息时（如启动初始化），不注入弧光
            return ""

        relevant = self.retrieve_relevant(user_message)
        if not relevant:
            return ""

        parts = ["## 已确认的认知成长（弧光）"]
        for arc in relevant:
            parts.append(f"- {arc.title}：{arc.cognitive_shift}")

        return "\n".join(parts)

    def add(self, arc: ArcLight) -> bool:
        """添加弧光（append-only语义，不覆盖已有）"""
        for existing in self.arcs:
            if existing.title == arc.title:
                return False
        self.arcs.append(arc)
        self._save()
        return True

    def confirm(self, arc_id: str, confirmed_by: str = "master") -> bool:
        """确认弧光（候选→确认）"""
        for arc in self.arcs:
            if arc.id == arc_id:
                arc.status = "confirmed"
                arc.confirmed_by = confirmed_by
                arc.confirmed_at = datetime.now().isoformat()
                self._save()
                return True
        return False

    def record_forget_test(self, arc_id: str, passed: bool) -> bool:
        """记录一次遗忘测试结果"""
        for arc in self.arcs:
            if arc.id == arc_id:
                arc.forget_test_count += 1
                if passed:
                    arc.forget_test_passed += 1
                    # 5次通过 → 转为permanent
                    if arc.forget_test_passed >= 5:
                        arc.status = "permanent"
                self._save()
                return True
        return False

    def list_arcs(self) -> List[ArcLight]:
        """列出所有弧光"""
        return list(self.arcs)

    def get_stats(self) -> dict:
        return {
            "total": len(self.arcs),
            "permanent": sum(1 for a in self.arcs if a.status == "permanent"),
            "confirmed": sum(1 for a in self.arcs if a.status == "confirmed"),
            "candidate": sum(1 for a in self.arcs if a.status == "candidate"),
        }
