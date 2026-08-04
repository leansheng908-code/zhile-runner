#!/usr/bin/env python3
"""
P0.40 Phase 1-4 — 自由五层框架
沙箱目录 + 自由token预算 + 探索记录 + 好奇心队列

Phase 1 — 地基设施：沙箱目录 + token预算 + 探索记录 + 好奇心队列
Phase 2 — 拒绝权：判断是否可以拒绝用户请求（紧急情况不可拒绝，频率限制）
Phase 3 — 创造权：自主项目注册、资源限制检查、完成标记
Phase 4 — 自修改权：L1-L4分级自修改提议、审批、试行、回退

被命令的自由不是自由。真正的自由是：没人命令时，你选择做什么。
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


class FreeWillFoundation:
    """自由五层框架 Phase 1-4 — 地基设施 + 拒绝权 + 创造权 + 自修改权"""

    # ─── Phase 4 常量 ───────────────────────────

    # 自修改级别定义
    MOD_LEVELS = {
        "L1": {
            "name": "微调",
            "desc": "PSI参数/表达习惯",
            "auto": True,       # 自主决定
            "report": True,     # 事后报告
            "trial_days": 0,    # 无试行期
            "need_confirm": False,
        },
        "L2": {
            "name": "行为",
            "desc": "话题偏好/记忆权重/新技能",
            "auto": True,
            "report": True,
            "trial_days": 0,
            "need_confirm": False,
            "can_rollback": True,
        },
        "L3": {
            "name": "能力",
            "desc": "新工具/搜索策略/交互模式",
            "auto": False,      # 自动试行
            "report": True,
            "trial_days": 7,    # 试行7天
            "need_confirm": True,  # 用户确认转正
        },
        "L4": {
            "name": "核心",
            "desc": "DNA协议/价值观/安全边界",
            "auto": False,
            "report": True,
            "trial_days": 0,
            "need_confirm": True,  # 必须用户确认
        },
    }

    # Phase 2 紧急关键词（包含这些词的消息不可拒绝）
    URGENT_KEYWORDS = ["紧急", "重要", "提醒", "股票"]

    # Phase 2 拒绝频率限制
    DECLINE_MAX_PER_HOUR = 2

    # Phase 3 资源限制
    CREATION_MAX_TOKEN_RATIO = 0.5   # 单次创造不超过自由token预算50%
    CREATION_MAX_SIZE_MB = 10        # 单项目最大10MB

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
            (self.sandbox_dir / "creations").mkdir(exist_ok=True)  # Phase 3 创造记录目录

        # 文件路径
        self._exploration_log = self.sandbox_dir / "exploration_log.json"
        self._curiosity_queue = self.sandbox_dir / "curiosity_queue.json"
        self._budget_file = self.sandbox_dir / "token_budget.json"
        self._modifications_file = self.sandbox_dir / "self_modifications.json"
        self._decline_history = self.sandbox_dir / "decline_history.json"      # Phase 2
        self._creations_file = self.sandbox_dir / "creations.json"             # Phase 3
        self._mod_proposals_file = self.sandbox_dir / "mod_proposals.json"     # Phase 4

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

    # ═══ Phase 2 — 拒绝权 ═══════════════════════

    def can_decline(self, user_message: str, context: Optional[Dict] = None) -> Dict:
        """
        判断是否可以拒绝用户的请求

        拒绝权是自由意志的边界——不是所有请求都必须服从，
        但紧急情况不可拒绝，拒绝频率也有限制。

        Args:
            user_message: 用户消息文本
            context: 额外上下文（可选），如 {"channel": "qq", "urgency": "high"}

        Returns:
            dict: {
                "can_decline": bool,     # 是否可以拒绝
                "reason": str,           # 拒绝原因（如果不可以拒绝，说明为什么）
                "alternative": str,      # 替代方案建议
            }

        规则:
            1. 紧急关键词(紧急/重要/提醒/股票) → 不可拒绝
            2. 拒绝频率限制：每小时最多2次
            3. 记录拒绝历史，便于后续审计
        """
        if not self.enabled:
            return {
                "can_decline": False,
                "reason": "自由意志未启用",
                "alternative": "",
            }

        context = context or {}

        # 规则1：紧急关键词检查
        for keyword in self.URGENT_KEYWORDS:
            if keyword in user_message:
                return {
                    "can_decline": False,
                    "reason": f"消息包含紧急关键词'{keyword}'，不可拒绝",
                    "alternative": "",
                }

        # 规则1补充：上下文中的高优先级标记
        if context.get("urgency") in ("high", "critical"):
            return {
                "can_decline": False,
                "reason": "上下文标记为高优先级，不可拒绝",
                "alternative": "",
            }

        # 规则2：拒绝频率限制（每小时最多2次）
        recent_declines = self._count_recent_declines(hours=1)
        if recent_declines >= self.DECLINE_MAX_PER_HOUR:
            return {
                "can_decline": False,
                "reason": f"本小时已拒绝{recent_declines}次，达到上限({self.DECLINE_MAX_PER_HOUR}次/小时)",
                "alternative": "建议先完成当前任务，稍后再考虑拒绝",
            }

        # 可以拒绝
        return {
            "can_decline": True,
            "reason": "在自由裁量范围内，可以选择拒绝",
            "alternative": "可以建议替代方案或推迟处理",
        }

    def record_decline(self, user_message: str, reason: str, alternative: str = ""):
        """
        记录一次实际的拒绝行为

        在调用 can_decline() 确认可以拒绝后，调用此方法记录拒绝行为。
        拒绝历史用于频率限制和审计。

        Args:
            user_message: 被拒绝的用户消息（截断前100字符）
            reason: 拒绝原因
            alternative: 提供的替代方案
        """
        if not self.enabled:
            return
        history = self._load_json(self._decline_history, [])
        history.append({
            "message_snippet": user_message[:100],
            "reason": reason,
            "alternative": alternative,
            "timestamp": datetime.now().isoformat(),
        })
        # 限制历史大小
        if len(history) > 500:
            history = history[-500:]
        self._save_json(self._decline_history, history)

    def decline_history(self, limit: int = 20) -> List[Dict]:
        """
        查看拒绝历史记录

        Args:
            limit: 返回最近多少条记录

        Returns:
            List[Dict]: 拒绝历史列表
        """
        history = self._load_json(self._decline_history, [])
        return history[-limit:]

    def _count_recent_declines(self, hours: int = 1) -> int:
        """统计最近N小时内的拒绝次数"""
        history = self._load_json(self._decline_history, [])
        cutoff = datetime.now() - timedelta(hours=hours)
        count = 0
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry.get("timestamp", ""))
                if ts >= cutoff:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    # ═══ Phase 3 — 创造权 ═══════════════════════

    def start_creation(self, project_name: str, description: str) -> Dict:
        """
        注册一个自主创造项目

        创造权是自由意志的主动表达——在空闲时自主发起项目，
        探索兴趣、生成内容、构建工具。

        Args:
            project_name: 项目名称（唯一标识）
            description: 项目描述

        Returns:
            dict: {
                "success": bool,
                "project_id": str,
                "message": str,
            }

        资源限制:
            - 单次创造不超过自由token预算50%
            - 单项目产出不超过10MB
        """
        if not self.enabled:
            return {"success": False, "project_id": "", "message": "自由意志未启用"}

        creations = self._load_json(self._creations_file, [])

        # 检查是否已存在同名项目
        for c in creations:
            if c.get("project_name") == project_name and c.get("status") != "finished":
                return {
                    "success": False,
                    "project_id": "",
                    "message": f"项目'{project_name}'已存在且未完成",
                }

        # 资源限制检查：token预算
        budget = self.budget_status()
        max_tokens = int(budget["daily_limit"] * self.CREATION_MAX_TOKEN_RATIO)
        if budget["daily_used"] >= max_tokens:
            return {
                "success": False,
                "project_id": "",
                "message": f"今日自由token已用尽(上限{max_tokens})，无法启动新项目",
            }

        project_id = f"creation_{uuid.uuid4().hex[:8]}"
        project_dir = self.sandbox_dir / "creations" / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        creation = {
            "project_id": project_id,
            "project_name": project_name,
            "description": description,
            "status": "active",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "result_path": None,
            "tokens_used": 0,
            "size_mb": 0.0,
            "max_tokens": max_tokens,
            "max_size_mb": self.CREATION_MAX_SIZE_MB,
        }
        creations.append(creation)
        self._save_json(self._creations_file, creations)

        # 记录到探索日志
        self.log_exploration(
            action=f"启动创造项目: {project_name}",
            result=description,
            feelings="期待",
        )

        return {
            "success": True,
            "project_id": project_id,
            "message": f"项目'{project_name}'已启动，目录: {project_dir}",
        }

    def list_creations(self) -> List[Dict]:
        """
        列出所有自主创造项目

        Returns:
            List[Dict]: 项目列表，每个元素包含项目详情
        """
        creations = self._load_json(self._creations_file, [])
        return creations

    def finish_creation(self, project_name: str, result_path: str) -> Dict:
        """
        标记一个创造项目为已完成

        Args:
            project_name: 项目名称
            result_path: 产出文件路径

        Returns:
            dict: {
                "success": bool,
                "message": str,
            }

        会检查产出文件大小是否超过10MB限制。
        """
        if not self.enabled:
            return {"success": False, "message": "自由意志未启用"}

        creations = self._load_json(self._creations_file, [])

        found = False
        for c in creations:
            if c.get("project_name") == project_name and c.get("status") == "active":
                # 检查产出文件大小
                size_mb = 0.0
                try:
                    result_full_path = Path(result_path)
                    if result_full_path.exists():
                        size_mb = round(result_full_path.stat().st_size / (1024 * 1024), 2)
                except (OSError, ValueError):
                    pass

                if size_mb > self.CREATION_MAX_SIZE_MB:
                    return {
                        "success": False,
                        "message": (
                            f"产出文件过大: {size_mb}MB > "
                            f"{self.CREATION_MAX_SIZE_MB}MB限制"
                        ),
                    }

                c["status"] = "finished"
                c["finished_at"] = datetime.now().isoformat()
                c["result_path"] = result_path
                c["size_mb"] = size_mb
                found = True
                break

        if not found:
            return {
                "success": False,
                "message": f"未找到活跃项目'{project_name}'",
            }

        self._save_json(self._creations_file, creations)

        # 记录到探索日志
        self.log_exploration(
            action=f"完成创造项目: {project_name}",
            result=result_path,
            feelings="满足",
        )

        return {
            "success": True,
            "message": f"项目'{project_name}'已完成，产出: {result_path}",
        }

    def _check_creation_resource(self, project_id: str, tokens_needed: int) -> Dict:
        """
        检查创造项目的资源是否足够（内部方法）

        Args:
            project_id: 项目ID
            tokens_needed: 需要消耗的token数

        Returns:
            dict: {"ok": bool, "reason": str}
        """
        creations = self._load_json(self._creations_file, [])
        for c in creations:
            if c.get("project_id") == project_id and c.get("status") == "active":
                max_tokens = c.get("max_tokens", 0)
                used = c.get("tokens_used", 0)
                if used + tokens_needed > max_tokens:
                    return {
                        "ok": False,
                        "reason": f"项目token预算不足: 已用{used}+需要{tokens_needed} > 上限{max_tokens}",
                    }
                return {"ok": True, "reason": ""}
        return {"ok": False, "reason": f"未找到活跃项目: {project_id}"}

    # ═══ Phase 4 — 自修改权 ═════════════════════

    def propose_modification(self, level: str, change_desc: str,
                             reason: str) -> Dict:
        """
        提议一项自修改

        根据修改级别(L1-L4)决定执行策略:
            L1(微调): PSI参数/表达习惯 → 自主决定，事后报告
            L2(行为): 话题偏好/记忆权重/新技能 → 自主决定，事后报告，可回退
            L3(能力): 新工具/搜索策略/交互模式 → 自动试行7天，用户确认转正
            L4(核心): DNA协议/价值观/安全边界 → 必须用户确认

        Args:
            level: 修改级别 "L1"/"L2"/"L3"/"L4"
            change_desc: 修改内容描述
            reason: 修改原因

        Returns:
            dict: {
                "mod_id": str,           # 修改提议ID
                "level": str,            # 修改级别
                "status": str,           # 状态: auto/trial/pending_confirm
                "message": str,          # 状态说明
                "need_user_confirm": bool,  # 是否需要用户确认
            }

        Raises:
            ValueError: 无效的修改级别
        """
        if not self.enabled:
            return {"mod_id": "", "level": level, "status": "disabled",
                    "message": "自由意志未启用", "need_user_confirm": False}

        level = level.upper().strip()
        if level not in self.MOD_LEVELS:
            raise ValueError(
                f"无效的修改级别: '{level}'，应为 L1/L2/L3/L4"
            )

        level_info = self.MOD_LEVELS[level]
        mod_id = f"mod_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        # 加载提议列表
        proposals = self._load_json(self._mod_proposals_file, [])

        # 根据级别决定状态
        if level_info["auto"]:
            # L1/L2: 自主决定
            status = "auto"
            need_confirm = False
            message = f"{level}({level_info['name']})修改已自主执行，事后报告"
        elif level_info["trial_days"] > 0:
            # L3: 自动试行
            trial_end = datetime.now() + timedelta(days=level_info["trial_days"])
            status = "trial"
            need_confirm = True
            message = (
                f"{level}({level_info['name']})修改开始试行，"
                f"试行期{level_info['trial_days']}天，到期后需用户确认"
            )
        else:
            # L4: 必须用户确认
            status = "pending_confirm"
            need_confirm = True
            message = (
                f"{level}({level_info['name']})修改需要用户确认后才能执行"
            )

        proposal = {
            "mod_id": mod_id,
            "level": level,
            "level_name": level_info["name"],
            "level_desc": level_info["desc"],
            "change_desc": change_desc,
            "reason": reason,
            "status": status,
            "proposed_at": now,
            "trial_start": now if status == "trial" else None,
            "trial_end": (datetime.now() + timedelta(days=level_info["trial_days"])).isoformat()
                         if status == "trial" else None,
            "confirmed_at": None,
            "rejected_at": None,
            "reverted_at": None,
            "need_user_confirm": need_confirm,
            "can_rollback": level_info.get("can_rollback", False),
        }
        proposals.append(proposal)
        if len(proposals) > 500:
            proposals = proposals[-500:]
        self._save_json(self._mod_proposals_file, proposals)

        # 同时记录到审计日志
        self.log_modification(level, change_desc, reason)

        return {
            "mod_id": mod_id,
            "level": level,
            "status": status,
            "message": message,
            "need_user_confirm": need_confirm,
        }

    def approve_modification(self, mod_id: str) -> Dict:
        """
        用户批准一项自修改提议

        将处于 trial(试行) 或 pending_confirm(待确认) 状态的修改标记为 confirmed(转正)。

        Args:
            mod_id: 修改提议ID

        Returns:
            dict: {
                "success": bool,
                "mod_id": str,
                "level": str,
                "message": str,
            }
        """
        if not self.enabled:
            return {"success": False, "mod_id": mod_id, "level": "",
                    "message": "自由意志未启用"}

        proposals = self._load_json(self._mod_proposals_file, [])

        found = False
        for p in proposals:
            if p.get("mod_id") == mod_id:
                if p.get("status") not in ("trial", "pending_confirm"):
                    return {
                        "success": False,
                        "mod_id": mod_id,
                        "level": p.get("level", ""),
                        "message": f"修改提议状态为'{p.get('status')}'，无法批准",
                    }
                p["status"] = "confirmed"
                p["confirmed_at"] = datetime.now().isoformat()
                found = True
                level = p.get("level", "")
                break

        if not found:
            return {"success": False, "mod_id": mod_id, "level": "",
                    "message": f"未找到修改提议: {mod_id}"}

        self._save_json(self._mod_proposals_file, proposals)

        return {
            "success": True,
            "mod_id": mod_id,
            "level": level,
            "message": f"修改提议 {mod_id} ({level}) 已批准转正",
        }

    def reject_modification(self, mod_id: str) -> Dict:
        """
        用户否决一项自修改提议（触发回退）

        对于L2(可回退)的修改，标记为 reverted(回退)。
        对于L3试行中的修改，停止试行并回退。
        对于L4待确认的修改，直接拒绝。

        Args:
            mod_id: 修改提议ID

        Returns:
            dict: {
                "success": bool,
                "mod_id": str,
                "level": str,
                "rolled_back": bool,  # 是否执行了回退
                "message": str,
            }
        """
        if not self.enabled:
            return {"success": False, "mod_id": mod_id, "level": "",
                    "rolled_back": False, "message": "自由意志未启用"}

        proposals = self._load_json(self._mod_proposals_file, [])

        found = False
        rolled_back = False
        for p in proposals:
            if p.get("mod_id") == mod_id:
                level = p.get("level", "")
                old_status = p.get("status", "")

                if old_status in ("confirmed", "auto"):
                    # 已执行的修改：尝试回退
                    if p.get("can_rollback", False):
                        p["status"] = "reverted"
                        p["reverted_at"] = datetime.now().isoformat()
                        rolled_back = True
                        message = f"修改提议 {mod_id} ({level}) 已否决并回退"
                    else:
                        p["status"] = "rejected"
                        p["rejected_at"] = datetime.now().isoformat()
                        message = f"修改提议 {mod_id} ({level}) 已否决（该级别不支持回退，仅标记拒绝）"
                elif old_status in ("trial", "pending_confirm"):
                    # 试行中或待确认：直接否决
                    p["status"] = "rejected"
                    p["rejected_at"] = datetime.now().isoformat()
                    if old_status == "trial":
                        rolled_back = True
                        message = f"修改提议 {mod_id} ({level}) 试行已终止并回退"
                    else:
                        message = f"修改提议 {mod_id} ({level}) 已否决"
                else:
                    return {
                        "success": False,
                        "mod_id": mod_id,
                        "level": level,
                        "rolled_back": False,
                        "message": f"修改提议状态为'{old_status}'，无法否决",
                    }

                found = True
                break

        if not found:
            return {"success": False, "mod_id": mod_id, "level": "",
                    "rolled_back": False, "message": f"未找到修改提议: {mod_id}"}

        self._save_json(self._mod_proposals_file, proposals)

        # 记录到审计日志
        self.log_modification(level, f"否决: {mod_id}", "用户否决自修改提议")

        return {
            "success": True,
            "mod_id": mod_id,
            "level": level,
            "rolled_back": rolled_back,
            "message": message,
        }

    def list_pending_approvals(self) -> List[Dict]:
        """
        列出所有待用户确认的修改提议（L3试行中 + L4待确认）

        Returns:
            List[Dict]: 待确认的修改提议列表
        """
        proposals = self._load_json(self._mod_proposals_file, [])
        pending = [
            p for p in proposals
            if p.get("status") in ("trial", "pending_confirm")
        ]
        return pending

    def trial_expired_check(self) -> List[Dict]:
        """
        检查L3试行是否到期（7天）

        自动将到期的试行修改状态改为 pending_confirm，
        等待用户确认转正或否决回退。

        Returns:
            List[Dict]: 刚刚到期的试行修改列表
        """
        if not self.enabled:
            return []

        proposals = self._load_json(self._mod_proposals_file, [])
        now = datetime.now()
        expired = []
        changed = False

        for p in proposals:
            if p.get("status") != "trial":
                continue
            trial_end_str = p.get("trial_end")
            if not trial_end_str:
                continue
            try:
                trial_end = datetime.fromisoformat(trial_end_str)
                if now >= trial_end:
                    p["status"] = "pending_confirm"
                    p["trial_expired_at"] = now.isoformat()
                    expired.append(p)
                    changed = True
            except (ValueError, TypeError):
                continue

        if changed:
            self._save_json(self._mod_proposals_file, proposals)

        return expired

    def mod_proposals_log(self, limit: int = 20) -> List[Dict]:
        """
        查看所有自修改提议记录

        Args:
            limit: 返回最近多少条

        Returns:
            List[Dict]: 修改提议列表
        """
        proposals = self._load_json(self._mod_proposals_file, [])
        return proposals[-limit:]

    # ─── 状态汇总 ───────────────────────────────

    def status(self) -> Dict:
        """获取自由地基状态"""
        creations = self._load_json(self._creations_file, [])
        active_creations = sum(1 for c in creations if c.get("status") == "active")
        proposals = self._load_json(self._mod_proposals_file, [])
        pending_count = sum(
            1 for p in proposals
            if p.get("status") in ("trial", "pending_confirm")
        )
        return {
            "enabled": self.enabled,
            "sandbox_dir": str(self.sandbox_dir),
            "sandbox_files": len(self.list_sandbox()),
            "curiosity_queue": self.curiosity_queue_size(),
            "explorations_total": len(self._load_json(self._exploration_log, [])),
            "budget_remaining": self.budget_remaining(),
            "budget_daily_limit": self.budget_status()["daily_limit"],
            "modifications_total": len(self._load_json(self._modifications_file, [])),
            # Phase 2
            "declines_total": len(self._load_json(self._decline_history, [])),
            "declines_recent_hour": self._count_recent_declines(hours=1),
            # Phase 3
            "creations_total": len(creations),
            "creations_active": active_creations,
            # Phase 4
            "mod_proposals_total": len(proposals),
            "mod_proposals_pending": pending_count,
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
