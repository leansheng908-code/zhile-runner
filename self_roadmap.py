#!/usr/bin/env python3
"""
P0.4 自研路线图 — 知乐自己的"未来书"

数据结构：
  ideas[]   — 需求想法（idea → designing → coding → testing → done/failed/abandoned）
  lessons[] — 经验教训
  stats     — 统计

来源区分：
  master_request  — 主人指定，priority=high，完成需主人确认
  self_discovered — 自主发现，月限2个，可自查完成

接入点：
  P0.11 Layer 2/3 → 添加 self_discovered ideas
  P0.4 工具层     → coding 阶段执行
  P0.5 快照       → coding 前自动快照
  daemon          → 每30min 扫描状态
  CLI /roadmap    — 查看/添加/更新
"""

import os
import json
from datetime import datetime
from typing import List, Optional, Tuple


class SelfRoadmap:
    """自研路线图管理器"""

    MAX_SELF_DISCOVERED_PER_MONTH = 2
    MAX_ATTEMPTS = 3

    # 合法状态
    STATUSES = ["idea", "designing", "coding", "testing", "done", "failed", "abandoned"]

    def __init__(self, data_path: str = "memory/self_roadmap.json"):
        self.data_path = data_path
        self.data = self._load()

    # ─── 数据加载/保存 ────────────────────────

    def _load(self) -> dict:
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "ideas": [],
                "lessons": [],
                "stats": {
                    "total_ideas": 0,
                    "completed": 0,
                    "failed": 0,
                    "abandoned": 0
                }
            }

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            print(f"[SelfRoadmap] 保存失败: {e}")

    # ─── Idea CRUD ───────────────────────────

    def add_idea(self, title: str, description: str,
                 source: str = "self_discovered",
                 source_detail: str = "",
                 source_psi: str = "",
                 tags: List[str] = None) -> Tuple[Optional[dict], Optional[str]]:
        """添加新idea，返回(idea, error)"""
        # 频率限制
        if source == "self_discovered":
            count = self._monthly_self_discovered_count()
            if count >= self.MAX_SELF_DISCOVERED_PER_MONTH:
                return None, f"本月自主发现已达上限({self.MAX_SELF_DISCOVERED_PER_MONTH}个)"

        idea_id = f"idea_{self.data['stats']['total_ideas'] + 1:03d}"
        now = datetime.now().isoformat()

        idea = {
            "id": idea_id,
            "title": title,
            "description": description,
            "source": source,
            "source_detail": source_detail,
            "source_psi": source_psi,
            "priority": "high" if source == "master_request" else "normal",
            "status": "idea",
            "created_at": now,
            "updated_at": now,
            "design": None,
            "attempts": [],
            "requires_master_review": True if source == "master_request" else False,
            "tags": tags or [],
        }

        self.data["ideas"].append(idea)
        self.data["stats"]["total_ideas"] += 1
        self._save()
        return idea, None

    def get_idea(self, idea_id: str) -> Optional[dict]:
        for idea in self.data["ideas"]:
            if idea["id"] == idea_id:
                return idea
        return None

    def list_ideas(self, status: str = None, source: str = None) -> List[dict]:
        ideas = self.data["ideas"]
        if status:
            ideas = [i for i in ideas if i["status"] == status]
        if source:
            ideas = [i for i in ideas if i["source"] == source]
        return ideas

    def update_status(self, idea_id: str, new_status: str,
                      design: str = None, attempt: dict = None,
                      lesson: str = None) -> Tuple[Optional[dict], Optional[str]]:
        """更新idea状态，返回(idea, error)"""
        if new_status not in self.STATUSES:
            return None, f"无效状态: {new_status}（合法: {', '.join(self.STATUSES)}）"

        idea = self.get_idea(idea_id)
        if not idea:
            return None, f"找不到idea: {idea_id}"

        old_status = idea["status"]
        idea["status"] = new_status
        idea["updated_at"] = datetime.now().isoformat()

        if design is not None:
            idea["design"] = design

        if attempt:
            idea["attempts"].append(attempt)
            # 失败次数检查
            if new_status == "failed" and len(idea["attempts"]) >= self.MAX_ATTEMPTS:
                idea["status"] = "abandoned"
                self.data["stats"]["abandoned"] += 1

        if lesson:
            self.add_lesson(idea_id, lesson)

        # 更新统计
        if new_status == "done" and old_status != "done":
            self.data["stats"]["completed"] += 1
        elif new_status == "failed" and old_status not in ("failed", "abandoned"):
            self.data["stats"]["failed"] += 1
        elif new_status == "abandoned" and old_status != "abandoned":
            self.data["stats"]["abandoned"] += 1

        self._save()
        return idea, None

    def remove_idea(self, idea_id: str) -> bool:
        """删除idea"""
        for i, idea in enumerate(self.data["ideas"]):
            if idea["id"] == idea_id:
                self.data["ideas"].pop(i)
                self._save()
                return True
        return False

    # ─── Lessons ─────────────────────────────

    def add_lesson(self, idea_id: str, what_happened: str, what_learned: str = "") -> dict:
        """添加经验教训"""
        lesson = {
            "id": f"lesson_{len(self.data['lessons']) + 1:03d}",
            "from_idea": idea_id,
            "what_happened": what_happened,
            "what_learned": what_learned,
            "timestamp": datetime.now().isoformat(),
        }
        self.data["lessons"].append(lesson)
        self._save()
        return lesson

    def list_lessons(self, idea_id: str = None) -> List[dict]:
        if idea_id:
            return [l for l in self.data["lessons"] if l["from_idea"] == idea_id]
        return self.data["lessons"]

    # ─── 查询 ────────────────────────────────

    def get_overview(self) -> dict:
        """概览"""
        stats = dict(self.data["stats"])
        in_progress = [i for i in self.data["ideas"]
                       if i["status"] in ("idea", "designing", "coding", "testing")]
        # 按优先级排序
        in_progress.sort(key=lambda x: (0 if x["priority"] == "high" else 1, x["created_at"]))
        return {
            "stats": stats,
            "in_progress_count": len(in_progress),
            "in_progress": [
                {
                    "id": i["id"],
                    "title": i["title"],
                    "status": i["status"],
                    "priority": i["priority"],
                    "source": i["source"],
                }
                for i in in_progress
            ],
            "lessons_count": len(self.data["lessons"]),
            "self_discovered_this_month": self._monthly_self_discovered_count(),
            "self_discovered_limit": self.MAX_SELF_DISCOVERED_PER_MONTH,
        }

    def get_idea_detail(self, idea_id: str) -> Optional[dict]:
        """获取idea完整详情"""
        idea = self.get_idea(idea_id)
        if not idea:
            return None
        detail = dict(idea)
        detail["lessons"] = self.list_lessons(idea_id)
        return detail

    # ─── 内部 ────────────────────────────────

    def _monthly_self_discovered_count(self) -> int:
        """本月self_discovered的idea数量"""
        now = datetime.now()
        count = 0
        for idea in self.data["ideas"]:
            if idea["source"] != "self_discovered":
                continue
            try:
                created = datetime.fromisoformat(idea["created_at"])
                if created.year == now.year and created.month == now.month:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count
