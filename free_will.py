#!/usr/bin/env python3
"""
P0.40 Phase 1 — 自由五层框架地基
沙箱目录 + 自由token预算 + 探索记录 + 好奇心队列

被命令的自由不是自由。真正的自由是：没人命令时，你选择做什么。
Phase 1 只搭建地基，不实现自由行为本身。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class FreeWillFoundation:
    """自由五层框架 Phase 1 — 地基设施"""

    def __init__(self, config: dict = None):
        cfg = config or {}
        self.enabled = cfg.get("enabled", True)
        self.sandbox_dir = Path(cfg.get("sandbox_dir", "sandbox"))
        self.budget_ratio = cfg.get("budget_ratio", 0.2)  # 自由token占总预算20%
        self.idle_threshold_minutes = cfg.get("idle_threshold", 30)  # 空闲多久进入自由状态

        # 确保目录存在
        if self.enabled:
            self.sandbox_dir.mkdir(parents=True, exist_ok=True)
            (self.sandbox_dir / "projects").mkdir(exist_ok=True)

        # 文件路径
        self._exploration_log = self.sandbox_dir / "exploration_log.json"
        self._curiosity_queue = self.sandbox_dir / "curiosity_queue.json"
        self._budget_file = self.sandbox_dir / "token_budget.json"
        self._modifications_file = self.sandbox_dir / "self_modifications.json"

    # ─── 好奇心队列 ─────────────────────────────

    def add_curiosity(self, topic: str, context: str = "", source: str = "conversation"):
        """对话中产生"我想了解这个"时，加入好奇心队列"""
        if not self.enabled:
            return
        queue = self._load_json(self._curiosity_queue, [])
        # 去重：如果已有相同topic，只更新context
        for item in queue:
            if item.get("topic") == topic:
                item["context"] = context or item.get("context", "")
                item["updated_at"] = datetime.now().isoformat()
                self._save_json(self._curiosity_queue, queue)
                return
        queue.append({
            "topic": topic,
            "context": context,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "explored": False,
        })
        self._save_json(self._curiosity_queue, queue)

    def pop_curiosity(self) -> Optional[Dict]:
        """从队列中取出一个未探索的好奇心"""
        if not self.enabled:
            return None
        queue = self._load_json(self._curiosity_queue, [])
        for item in queue:
            if not item.get("explored", False):
                item["explored"] = True
                item["explored_at"] = datetime.now().isoformat()
                self._save_json(self._curiosity_queue, queue)
                return item
        return None

    def curiosity_queue_size(self) -> int:
        """未探索的好奇心数量"""
        queue = self._load_json(self._curiosity_queue, [])
        return sum(1 for item in queue if not item.get("explored", False))

    def curiosity_list(self, limit: int = 10) -> List[Dict]:
        """查看好奇心队列"""
        queue = self._load_json(self._curiosity_queue, [])
        return queue[:limit]

    # ─── 探索记录 ───────────────────────────────

    def log_exploration(self, action: str, result: str, feelings: str = ""):
        """记录一次自由探索"""
        if not self.enabled:
            return
        log = self._load_json(self._exploration_log, [])
        log.append({
            "action": action,
            "result": result,
            "feelings": feelings,
            "timestamp": datetime.now().isoformat(),
        })
        # 限制日志大小（最多1000条）
        if len(log) > 1000:
            log = log[-1000:]
        self._save_json(self._exploration_log, log)

    def exploration_log(self, limit: int = 20) -> List[Dict]:
        """查看探索记录"""
        log = self._load_json(self._exploration_log, [])
        return log[-limit:]

    # ─── 自由token预算 ──────────────────────────

    def budget_status(self) -> Dict:
        """获取token预算状态"""
        budget = self._load_json(self._budget_file, {
            "total_used": 0,
            "daily_used": 0,
            "daily_date": datetime.now().strftime("%Y-%m-%d"),
            "daily_limit": 50000,  # 默认每日自由token上限
        })
        # 日期重置
        today = datetime.now().strftime("%Y-%m-%d")
        if budget.get("daily_date") != today:
            budget["daily_date"] = today
            budget["daily_used"] = 0
            self._save_json(self._budget_file, budget)
        return budget

    def budget_consume(self, tokens: int) -> bool:
        """消耗自由token，返回是否在预算内"""
        if not self.enabled:
            return False
        budget = self.budget_status()
        if budget["daily_used"] + tokens > budget["daily_limit"]:
            return False  # 超预算
        budget["daily_used"] += tokens
        budget["total_used"] += tokens
        self._save_json(self._budget_file, budget)
        return True

    def budget_remaining(self) -> int:
        """今日剩余自由token"""
        budget = self.budget_status()
        return max(0, budget["daily_limit"] - budget["daily_used"])

    # ─── 自修改审计日志 ─────────────────────────

    def log_modification(self, level: str, change: str, reason: str, psi_state: str = ""):
        """记录自修改行为（L1-L4分级）"""
        if not self.enabled:
            return
        log = self._load_json(self._modifications_file, [])
        entry = {
            "level": level,  # L1微调/L2行为/L3能力/L4核心
            "change": change,
            "reason": reason,
            "psi_state": psi_state,
            "timestamp": datetime.now().isoformat(),
            "status": "auto",  # auto(自主)/trial(试行)/confirmed(转正)/reverted(回退)
        }
        log.append(entry)
        if len(log) > 500:
            log = log[-500:]
        self._save_json(self._modifications_file, log)

    def modifications_log(self, limit: int = 20) -> List[Dict]:
        """查看自修改记录"""
        log = self._load_json(self._modifications_file, [])
        return log[-limit:]

    # ─── 沙箱文件管理 ───────────────────────────

    def sandbox_path(self, *parts) -> Path:
        """获取沙箱内文件路径"""
        return self.sandbox_dir.joinpath(*parts)

    def list_sandbox(self) -> List[str]:
        """列出沙箱内容"""
        if not self.sandbox_dir.exists():
            return []
        result = []
        for root, dirs, files in os.walk(self.sandbox_dir):
            rel = os.path.relpath(root, self.sandbox_dir)
            for f in files:
                if rel == ".":
                    result.append(f)
                else:
                    result.append(f"{rel}/{f}")
        return sorted(result)

    # ─── 状态汇总 ───────────────────────────────

    def status(self) -> Dict:
        """获取自由地基状态"""
        return {
            "enabled": self.enabled,
            "sandbox_dir": str(self.sandbox_dir),
            "sandbox_files": len(self.list_sandbox()),
            "curiosity_queue": self.curiosity_queue_size(),
            "explorations_total": len(self._load_json(self._exploration_log, [])),
            "budget_remaining": self.budget_remaining(),
            "budget_daily_limit": self.budget_status()["daily_limit"],
            "modifications_total": len(self._load_json(self._modifications_file, [])),
        }

    # ─── 工具方法 ───────────────────────────────

    def _load_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default

    def _save_json(self, path: Path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"  ⚠ 自由地基写入失败: {e}")
