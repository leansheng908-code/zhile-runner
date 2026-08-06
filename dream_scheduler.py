#!/usr/bin/env python3
"""
知乐做梦任务调度器 — P0.69 Phase 3
深睡眠状态下的任务队列管理

做梦内容映射已有模块：
  - P0.3 自成长循环 → 复盘今天的对话，扫描成长候选
  - P0.21 记忆摄取管线 → 整理今天的新记忆，提取关键信息
  - P0.29 记忆编译层 → 把短期记忆编译成长期记忆
  - P0.5 版本快照 → 给自己存档
  - healthcheck → 自检系统健康
  - P0.25 Phase 2 卦象加权检索 → 重新整理记忆索引
  - session垃圾清理 → 扫描session.json，剔除垃圾交互
"""

import time
import sys
from datetime import datetime
from typing import Optional, Dict, List, Callable
from enum import Enum


class DreamTaskPriority(Enum):
    """做梦任务优先级"""
    CRITICAL = 1    # 记忆整理 — 不做会丢失重要信息
    HIGH = 2        # 自成长 — 当天对话复盘
    MEDIUM = 3      # 版本快照/记忆编译
    LOW = 4         # 健康检查/索引整理


class DreamTask:
    """单个做梦任务"""
    def __init__(self, name: str, priority: DreamTaskPriority,
                 func: Callable, description: str = ""):
        self.name = name
        self.priority = priority
        self.func = func
        self.description = description
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.duration: float = 0

    def execute(self) -> dict:
        """执行任务"""
        start = time.time()
        try:
            self.result = self.func()
            self.duration = time.time() - start
            return self.result or {"status": "done"}
        except Exception as e:
            self.error = str(e)
            self.duration = time.time() - start
            return {"error": str(e)}


class DreamScheduler:
    """做梦调度器 — 深睡眠期间执行系统维护任务"""

    def __init__(self, core):
        """
        Args:
            core: ZhileCore实例
        """
        self.core = core
        self._tasks: List[DreamTask] = []
        self._last_dream: Optional[dict] = None
        self._dream_count = 0

    def _build_task_queue(self) -> List[DreamTask]:
        """构建做梦任务队列（按优先级排序）"""
        tasks = []

        # 1. 记忆整理（CRITICAL）
        if hasattr(self.core, "memory") and self.core.memory:
            tasks.append(DreamTask(
                name="memory_consolidation",
                priority=DreamTaskPriority.CRITICAL,
                func=self._dream_memory_consolidation,
                description="整理今天的新记忆，提取关键信息",
            ))

        # 2. Session垃圾清理（CRITICAL）
        tasks.append(DreamTask(
            name="session_cleanup",
            priority=DreamTaskPriority.CRITICAL,
            func=self._dream_session_cleanup,
            description="清理session中的垃圾对话",
        ))

        # 3. 自成长复盘（HIGH）
        if hasattr(self.core, "somatic_cells") and self.core.somatic_cells:
            tasks.append(DreamTask(
                name="growth_scan",
                priority=DreamTaskPriority.HIGH,
                func=self._dream_growth_scan,
                description="复盘今天的对话，扫描成长候选",
            ))

        # 4. 记忆编译（MEDIUM）
        if hasattr(self.core, "memory_compiler") and self.core.memory_compiler:
            tasks.append(DreamTask(
                name="memory_compile",
                priority=DreamTaskPriority.MEDIUM,
                func=self._dream_memory_compile,
                description="把短期记忆编译成长期记忆",
            ))

        # 5. 版本快照（MEDIUM）
        if hasattr(self.core, "snapshot_manager") and self.core.snapshot_manager:
            tasks.append(DreamTask(
                name="version_snapshot",
                priority=DreamTaskPriority.MEDIUM,
                func=self._dream_version_snapshot,
                description="给自己存档",
            ))

        # 6. 卦象记忆索引整理（LOW）
        if hasattr(self.core, "hexagram_tracker") and self.core.hexagram_tracker:
            tasks.append(DreamTask(
                name="hexagram_index",
                priority=DreamTaskPriority.LOW,
                func=self._dream_hexagram_index,
                description="重新整理卦象加权记忆索引",
            ))

        # 7. 健康检查（LOW）
        tasks.append(DreamTask(
            name="health_check",
            priority=DreamTaskPriority.LOW,
            func=self._dream_health_check,
            description="自检系统健康状态",
        ))

        # 按优先级排序
        tasks.sort(key=lambda t: t.priority.value)
        return tasks

    # ─── 做梦任务实现 ─────────────────────────

    def _dream_memory_consolidation(self) -> dict:
        """做梦：记忆整理"""
        if not self.core.memory:
            return {"skipped": "无记忆系统"}

        stats = self.core.memory.get_stats()
        mems = self.core.memory.memories

        # 找出今天新增的记忆
        today = datetime.now().strftime("%Y-%m-%d")
        today_mems = []
        for m in mems:
            try:
                if hasattr(m, "created_at") and m.created_at.startswith(today):
                    today_mems.append(m)
            except (AttributeError, TypeError):
                continue

        # 触发记忆衰减和索引更新
        if hasattr(self.core, "daemon") and self.core.daemon:
            try:
                self.core.daemon._calculate_memory_decay()
                self.core.daemon._detect_stale_memories()
                self.core.daemon._organize_memory_index()
            except Exception:
                pass

        return {
            "total_memories": stats.get("total", 0),
            "today_new": len(today_mems),
            "consolidated": True,
        }

    def _dream_session_cleanup(self) -> dict:
        """做梦：清理session垃圾"""
        cleaned = 0
        try:
            if hasattr(self.core, "_cleanup_session"):
                cleaned = self.core._cleanup_session()
            elif hasattr(self.core, "memory") and self.core.memory:
                # 尝试调用memory_system的session清理
                if hasattr(self.core.memory, "cleanup_session"):
                    cleaned = self.core.memory.cleanup_session()
        except Exception as e:
            return {"error": str(e)}

        return {"cleaned": cleaned}

    def _dream_growth_scan(self) -> dict:
        """做梦：自成长复盘"""
        if not self.core.somatic_cells:
            return {"skipped": "无体细胞系统"}

        try:
            stats = self.core.somatic_cells.get_stats()
        except Exception:
            stats = {}

        # 扫描成长候选（通过守护进程的功能）
        candidates = 0
        if hasattr(self.core, "daemon") and self.core.daemon:
            try:
                result = self.core.daemon._scan_growth_candidates()
                candidates = result.get("workspace_candidates", 0)
            except Exception:
                pass

        return {
            "somatic_cells": stats.get("total", 0),
            "growth_candidates": candidates,
        }

    def _dream_memory_compile(self) -> dict:
        """做梦：记忆编译"""
        if not self.core.memory_compiler:
            return {"skipped": "无记忆编译器"}

        try:
            if self.core.memory_compiler.should_compile(self.core._turn_count):
                return self.core.memory_compiler.compile(
                    turn_count=self.core._turn_count)
            return {"skipped": "未到编译阈值"}
        except Exception as e:
            return {"error": str(e)}

    def _dream_version_snapshot(self) -> dict:
        """做梦：版本快照"""
        if not self.core.snapshot_manager:
            return {"skipped": "无快照管理器"}

        try:
            return self.core.snapshot_manager.create_snapshot(
                label=f"dream_{datetime.now().strftime('%Y%m%d_%H%M')}"
            )
        except Exception as e:
            return {"error": str(e)}

    def _dream_hexagram_index(self) -> dict:
        """做梦：卦象记忆索引整理"""
        if not self.core.hexagram_tracker:
            return {"skipped": "无卦象追踪器"}

        try:
            return {
                "update_count": self.core.hexagram_tracker.update_count,
                "current_hexagram": self.core._hex_state.get("current", {}).get("name", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def _dream_health_check(self) -> dict:
        """做梦：健康检查"""
        try:
            status = self.core.get_status() if hasattr(self.core, "get_status") else {}
            return {"checked": True, "status_keys": list(status.keys())[:5]}
        except Exception as e:
            return {"error": str(e)}

    # ─── 执行做梦 ─────────────────────────────

    def run_dream(self) -> dict:
        """执行一次完整的做梦周期"""
        self._dream_count += 1
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        print(f"😴 [做梦] 第{self._dream_count}次做梦开始（{ts}）", file=sys.stderr)

        tasks = self._build_task_queue()
        results = {}
        errors = []
        completed = 0

        for task in tasks:
            try:
                result = task.execute()
                results[task.name] = result
                if "error" in result:
                    errors.append(f"{task.name}: {result['error']}")
                else:
                    completed += 1
                print(f"😴 [做梦] {task.name} 完成（{task.duration:.1f}s）", file=sys.stderr)
            except Exception as e:
                errors.append(f"{task.name}: {e}")
                results[task.name] = {"error": str(e)}

        dream_summary = {
            "dream_count": self._dream_count,
            "timestamp": ts,
            "total_tasks": len(tasks),
            "completed": completed,
            "errors": errors if errors else None,
            "results": results,
        }

        self._last_dream = dream_summary

        print(f"😴 [做梦] 第{self._dream_count}次做梦完成：{completed}/{len(tasks)}任务完成",
              file=sys.stderr)

        return dream_summary

    def get_last_dream(self) -> Optional[dict]:
        """获取上次做梦结果"""
        return self._last_dream

    def get_status(self) -> dict:
        """获取做梦调度器状态"""
        return {
            "dream_count": self._dream_count,
            "last_dream_time": self._last_dream.get("timestamp") if self._last_dream else None,
            "last_dream_tasks": self._last_dream.get("total_tasks", 0) if self._last_dream else 0,
            "last_dream_completed": self._last_dream.get("completed", 0) if self._last_dream else 0,
        }
