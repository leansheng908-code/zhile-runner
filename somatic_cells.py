#!/usr/bin/env python3
"""
知乐体细胞完整生命周期 — P0.17

体细胞 = 可增生/可休眠/可覆盖的习惯层变化
与弧光的区别：弧光永久不可逆，体细胞有完整状态机

状态流转：
  候选 →(遗忘测试通过≥3次)→ 活跃 →(30天未触发)→ 休眠 →(再次出现)→ 唤醒 → 活跃
                                   →(被新行为取代)→ 覆盖（终态）
  候选 →(遗忘测试失败)→ 丢弃（终态）
  休眠 →(90天未唤醒)→ 淡化（极低概率唤醒）
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


class SomaticCell:
    """单个体细胞 — 可增生可休眠的习惯层变化"""

    # 状态常量
    STATUS_CANDIDATE = "candidate"
    STATUS_ACTIVE = "active"
    STATUS_DORMANT = "dormant"
    STATUS_AWAKENED = "awakened"
    STATUS_COVERED = "covered"
    STATUS_DISCARDED = "discarded"
    STATUS_FADED = "faded"

    def __init__(self, name: str, dimension: str = "expression",
                 description: str = "", source: str = "spontaneous",
                 cell_id: str = None, created: str = None,
                 last_activated: str = None, activation_count: int = 0,
                 status: str = "candidate", forget_test: Dict = None,
                 dormant_history: List[Dict] = None,
                 superseded_by: str = None, supersedes: str = None,
                 tags: List[str] = None, related_entities: List[str] = None,
                 priority: float = 0.5, hit_count: int = 0,
                 last_hit: str = None):
        self.id = cell_id or f"cell_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.name = name
        self.dimension = dimension  # expression/habit/interaction/preference
        self.description = description
        self.source = source  # spontaneous/user_directed
        self.created = created or datetime.now().isoformat()
        self.last_activated = last_activated or self.created
        self.activation_count = activation_count
        self.status = status
        # P0.28: forget_test增加test_phase等字段
        self.forget_test = forget_test or {
            "passed": 0, "failed": 0, "last_test": None,
            "test_phase": "idle",  # idle/injecting/observing/graduated/discarded
            "withdraw_at_turn": None,
            "observe_until_turn": None,
            "test_cycles": 0,
        }
        self.dormant_history = dormant_history or []
        self.superseded_by = superseded_by
        self.supersedes = supersedes
        # P0.20: 检索/修剪相关字段
        self.tags = tags or []
        self.related_entities = related_entities or []
        self.priority = priority
        self.hit_count = hit_count
        self.last_hit = last_hit

    @property
    def is_active(self) -> bool:
        """是否应注入上下文"""
        return self.status in (self.STATUS_ACTIVE, self.STATUS_AWAKENED)

    @property
    def days_since_activation(self) -> int:
        try:
            last = datetime.fromisoformat(self.last_activated)
            return (datetime.now() - last).days
        except (ValueError, TypeError):
            return 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "dimension": self.dimension,
            "description": self.description,
            "source": self.source,
            "created": self.created,
            "last_activated": self.last_activated,
            "activation_count": self.activation_count,
            "status": self.status,
            "forget_test": self.forget_test,
            "dormant_history": self.dormant_history,
            "superseded_by": self.superseded_by,
            "supersedes": self.supersedes,
            # P0.20: 检索/修剪字段
            "tags": self.tags,
            "related_entities": self.related_entities,
            "priority": self.priority,
            "hit_count": self.hit_count,
            "last_hit": self.last_hit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SomaticCell":
        d = dict(d)
        if "id" in d:
            d["cell_id"] = d.pop("id")
        return cls(**d)


class SomaticCellSystem:
    """体细胞系统主控制器 — 状态机管理"""

    # 转换条件常量
    DORMANT_THRESHOLD_DAYS = 30      # 活跃→休眠
    FADE_THRESHOLD_DAYS = 90         # 休眠→淡化
    FORGET_TEST_PASS_THRESHOLD = 3   # 候选→活跃

    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cells_file = self.state_dir / "somatic_cells.json"
        self.cells: List[SomaticCell] = self._load()

    def _load(self) -> List[SomaticCell]:
        if not self.cells_file.exists():
            return []
        try:
            with open(self.cells_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [SomaticCell.from_dict(c) for c in data.get("cells", [])]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []

    def _save(self):
        data = {
            "cells": [c.to_dict() for c in self.cells],
            "metadata": {
                "total": len(self.cells),
                "active": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_ACTIVE),
                "dormant": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_DORMANT),
                "candidate": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_CANDIDATE),
                "discarded": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_DISCARDED),
            },
        }
        with open(self.cells_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── 添加候选 ───────────────────────────────

    def add_candidate(self, name: str, dimension: str = "expression",
                      description: str = "", source: str = "spontaneous") -> Optional[SomaticCell]:
        """添加体细胞候选（来自growth_scanner或反馈闭环）"""
        # 去重：同名不重复添加
        for existing in self.cells:
            if existing.name == name and existing.status not in (
                SomaticCell.STATUS_DISCARDED, SomaticCell.STATUS_COVERED
            ):
                return None

        cell = SomaticCell(
            name=name,
            dimension=dimension,
            description=description,
            source=source,
        )
        self.cells.append(cell)
        self._save()
        return cell

    # ─── 遗忘测试 ───────────────────────────────

    def record_forget_test(self, cell_id: str, passed: bool) -> bool:
        """记录一次遗忘测试结果"""
        cell = self._find(cell_id)
        if not cell or cell.status != SomaticCell.STATUS_CANDIDATE:
            return False

        cell.forget_test["last_test"] = datetime.now().isoformat()
        if passed:
            cell.forget_test["passed"] += 1
            if cell.forget_test["passed"] >= self.FORGET_TEST_PASS_THRESHOLD:
                cell.status = SomaticCell.STATUS_ACTIVE
                cell.last_activated = datetime.now().isoformat()
        else:
            cell.forget_test["failed"] += 1
            # 失败2次直接丢弃
            if cell.forget_test["failed"] >= 2:
                cell.status = SomaticCell.STATUS_DISCARDED

        self._save()
        return True

    # ─── 活跃度检查（定时调用）───────────────────

    def check_lifecycle(self):
        """检查所有体细胞的生命周期状态，执行自动转换"""
        now = datetime.now()
        changed = False

        for cell in self.cells:
            if cell.status == SomaticCell.STATUS_ACTIVE:
                # 活跃→休眠：30天未自然触发
                if cell.days_since_activation > self.DORMANT_THRESHOLD_DAYS:
                    cell.status = SomaticCell.STATUS_DORMANT
                    cell.dormant_history.append({
                        "dormant_since": now.isoformat(),
                        "reason": f"{self.DORMANT_THRESHOLD_DAYS}天未自然触发",
                    })
                    changed = True

            elif cell.status == SomaticCell.STATUS_AWAKENED:
                # 唤醒→活跃：直接转回活跃
                cell.status = SomaticCell.STATUS_ACTIVE
                changed = True

            elif cell.status == SomaticCell.STATUS_DORMANT:
                # 休眠→淡化：90天未唤醒
                if cell.dormant_history:
                    last_dormant = cell.dormant_history[-1].get("dormant_since", "")
                    try:
                        dormant_date = datetime.fromisoformat(last_dormant)
                        if (now - dormant_date).days > self.FADE_THRESHOLD_DAYS:
                            cell.status = SomaticCell.STATUS_FADED
                            changed = True
                    except (ValueError, TypeError):
                        pass

        if changed:
            self._save()

    # ─── 自然触发记录 ───────────────────────────

    def record_activation(self, cell_name: str) -> bool:
        """记录体细胞被自然触发（检测到该行为模式出现）"""
        cell = self._find_by_name(cell_name)
        if not cell:
            return False

        if cell.status == SomaticCell.STATUS_DORMANT:
            # 休眠→唤醒→活跃
            cell.status = SomaticCell.STATUS_AWAKENED
            cell.activation_count += 1
            cell.last_activated = datetime.now().isoformat()
            self._save()
            return True

        if cell.status == SomaticCell.STATUS_FADED:
            # 淡化→唤醒（低概率但允许）
            cell.status = SomaticCell.STATUS_AWAKENED
            cell.activation_count += 1
            cell.last_activated = datetime.now().isoformat()
            self._save()
            return True

        if cell.status == SomaticCell.STATUS_ACTIVE:
            cell.activation_count += 1
            cell.last_activated = datetime.now().isoformat()
            self._save()
            return True

        return False

    # ─── 覆盖检测 ───────────────────────────────

    def check_supersede(self, new_cell_name: str, old_cell_id: str) -> bool:
        """新体细胞覆盖旧体细胞（旧习惯被新习惯取代）"""
        old_cell = self._find(old_cell_id)
        new_cell = self._find_by_name(new_cell_name)

        if not old_cell or not new_cell:
            return False

        if old_cell.dimension != new_cell.dimension:
            return False  # 不同维度的不能互相覆盖

        old_cell.status = SomaticCell.STATUS_COVERED
        old_cell.superseded_by = new_cell.id
        new_cell.supersedes = old_cell.id
        self._save()
        return True

    # ─── 上下文注入 ─────────────────────────────

    def get_active_context(self, user_message: str = None) -> str:
        """获取体细胞的注入文本
        
        P0.28: 候选体细胞在observing阶段被移出（不注入）
        P0.20: 当user_message提供时，只注入命中的体细胞（检索层）
        """
        active_cells = [c for c in self.cells if c.is_active]
        
        # P0.28: 候选体细胞中，排除正在observing的
        candidate_cells = [
            c for c in self.cells 
            if c.status == SomaticCell.STATUS_CANDIDATE
            and c.forget_test.get("test_phase", "idle") != "observing"
        ]

        # P0.20: 检索层 — 当有用户消息时，按关键词匹配筛选
        if user_message and len(active_cells) + len(candidate_cells) > 5:
            active_cells = self._select_relevant(active_cells, user_message, top_n=3)
            candidate_cells = self._select_relevant(candidate_cells, user_message, top_n=2)

        if not active_cells and not candidate_cells:
            return ""

        parts = []

        # 活跃体细胞（已通过遗忘测试）
        if active_cells:
            parts.append("## 已内化的表达习惯（体细胞）")
            for cell in active_cells:
                dim_name = self._dim_name(cell.dimension)
                parts.append(f"- [{dim_name}] {cell.name}：{cell.description}")
                # P0.20: 更新命中计数
                if user_message:
                    self._record_hit(cell)

        # 候选体细胞（P0.3: 立即注入以实现即时响应）
        if candidate_cells:
            parts.append("## 新发现的表达偏好（尝试遵循，观察中）")
            for cell in candidate_cells:
                dim_name = self._dim_name(cell.dimension)
                parts.append(f"- [{dim_name}] {cell.name}：{cell.description}")

        return "\n".join(parts)

    @staticmethod
    def _dim_name(dimension: str) -> str:
        return {
            "expression": "表达",
            "habit": "习惯",
            "interaction": "互动",
            "preference": "偏好",
        }.get(dimension, dimension)

    def _select_relevant(self, cells: List[SomaticCell], 
                         user_message: str, top_n: int = 3) -> List[SomaticCell]:
        """P0.20: 关键词匹配检索 — 选出与用户消息最相关的体细胞"""
        msg_lower = user_message.lower()
        
        scored = []
        for cell in cells:
            score = cell.priority  # 基础分 = 优先级
            # 关键词匹配
            for tag in cell.tags:
                if tag.lower() in msg_lower:
                    score += 0.5
            # 名称匹配
            if cell.name.lower() in msg_lower:
                score += 0.3
            # 关联实体匹配
            for entity in cell.related_entities:
                if entity.lower() in msg_lower:
                    score += 0.4
            scored.append((cell, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_n]]

    def _record_hit(self, cell: SomaticCell):
        """P0.20: 记录体细胞命中"""
        cell.hit_count += 1
        cell.last_hit = datetime.now().isoformat()
        # 不每次都save，避免IO频繁（在save_session时统一保存）

    # ─── P0.20: 修剪层 ────────────────────────

    def prune(self) -> dict:
        """P0.20: 定期修剪 — 清理僵尸/低效/冲突体细胞
        
        Returns:
            {"dormant_zombies": N, "conflicts_resolved": N, "archived": N}
        """
        now = datetime.now()
        result = {"dormant_zombies": 0, "conflicts_resolved": 0, "archived": 0}
        changed = False

        # 1. 僵尸规则：活跃体细胞last_hit超过30天未命中 → 降级为dormant
        for cell in self.cells:
            if cell.status != SomaticCell.STATUS_ACTIVE:
                continue
            if not cell.last_hit:
                # 从未命中过，用last_activated近似
                check_date = cell.last_activated
            else:
                check_date = cell.last_hit
            try:
                last = datetime.fromisoformat(check_date)
                if (now - last).days > 30:
                    cell.status = SomaticCell.STATUS_DORMANT
                    cell.dormant_history.append({
                        "dormant_since": now.isoformat(),
                        "reason": "P0.20修剪：30天未命中",
                    })
                    result["dormant_zombies"] += 1
                    changed = True
            except (ValueError, TypeError):
                pass

        # 2. 冲突检测：同维度同tags的active体细胞，保留hit_count高的
        active_by_dim = {}
        for cell in self.cells:
            if cell.status != SomaticCell.STATUS_ACTIVE:
                continue
            dim = cell.dimension
            # 用tags做简单冲突检测（有相同tag的可能是冲突）
            for tag in cell.tags:
                key = f"{dim}:{tag}"
                if key in active_by_dim:
                    existing = active_by_dim[key]
                    # 保留hit_count高的
                    if cell.hit_count > existing.hit_count:
                        existing.status = SomaticCell.STATUS_DORMANT
                        existing.dormant_history.append({
                            "dormant_since": now.isoformat(),
                            "reason": f"P0.20修剪：与{cell.name}冲突，hit_count较低",
                        })
                        active_by_dim[key] = cell
                        result["conflicts_resolved"] += 1
                        changed = True
                    else:
                        cell.status = SomaticCell.STATUS_DORMANT
                        cell.dormant_history.append({
                            "dormant_since": now.isoformat(),
                            "reason": f"P0.20修剪：与{existing.name}冲突，hit_count较低",
                        })
                        result["conflicts_resolved"] += 1
                        changed = True
                else:
                    active_by_dim[key] = cell

        # 3. 过期规则：faded状态超过90天 → 归档（从列表移除）
        before_count = len(self.cells)
        self.cells = [
            c for c in self.cells
            if not (c.status == SomaticCell.STATUS_FADED 
                    and c.dormant_history
                    and self._is_long_faded(c, now))
        ]
        result["archived"] = before_count - len(self.cells)

        if changed or result["archived"] > 0:
            self._save()

        return result

    @staticmethod
    def _is_long_faded(cell: SomaticCell, now: datetime) -> bool:
        """检查faded体细胞是否已超过90天"""
        if not cell.dormant_history:
            return False
        try:
            last_dormant = cell.dormant_history[-1].get("dormant_since", "")
            dormant_date = datetime.fromisoformat(last_dormant)
            return (now - dormant_date).days > 90
        except (ValueError, TypeError, IndexError):
            return False

    # ─── P0.20: 增长控制 ──────────────────────

    def get_dynamic_budget(self, base_budget: int = 3) -> int:
        """P0.20: 动态编辑预算 — 稳定成长+1，冲突回退-1"""
        # 统计最近5个候选的转正率
        recent_candidates = [c for c in self.cells 
                           if c.status in ("active", "discarded")
                           and c.forget_test.get("test_cycles", 0) > 0]
        if len(recent_candidates) < 3:
            return base_budget

        recent_5 = recent_candidates[-5:]
        promoted = sum(1 for c in recent_5 if c.status == "active")
        discarded = sum(1 for c in recent_5 if c.status == "discarded")

        if promoted >= 4:  # 5个中4个转正 → 奖励
            return min(base_budget + 1, 5)
        if discarded >= 3:  # 5个中3个被丢弃 → 刹车
            return max(base_budget - 1, 1)
        return base_budget

    # ─── 查询 ───────────────────────────────────

    def _find(self, cell_id: str) -> Optional[SomaticCell]:
        return next((c for c in self.cells if c.id == cell_id), None)

    def _find_by_name(self, name: str) -> Optional[SomaticCell]:
        # 找非终态的同名cell
        return next(
            (c for c in self.cells if c.name == name
             and c.status not in (SomaticCell.STATUS_DISCARDED, SomaticCell.STATUS_COVERED)),
            None,
        )

    def list_cells(self, status: str = None) -> List[SomaticCell]:
        if status:
            return [c for c in self.cells if c.status == status]
        return list(self.cells)

    def get_stats(self) -> dict:
        return {
            "total": len(self.cells),
            "active": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_ACTIVE),
            "candidate": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_CANDIDATE),
            "dormant": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_DORMANT),
            "covered": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_COVERED),
            "discarded": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_DISCARDED),
            "faded": sum(1 for c in self.cells if c.status == SomaticCell.STATUS_FADED),
        }

    def reset_weight(self, cell_id: str) -> bool:
        """人工否决：重置某个体细胞为休眠状态"""
        cell = self._find(cell_id)
        if not cell:
            return False
        cell.status = SomaticCell.STATUS_DORMANT
        cell.dormant_history.append({
            "dormant_since": datetime.now().isoformat(),
            "reason": "用户手动重置",
        })
        self._save()
        return True
