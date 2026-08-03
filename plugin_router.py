#!/usr/bin/env python3
"""
知乐插件路由器 — P0.7（SkillComposer启发）

解决插件越来越多后"该激活哪些"的问题。
零训练纯规则版：任务分类 → 依赖拓扑排序 → PSI调制 → 防膨胀。

路由流程：
  1. 任务分类：闲聊/深层对话/工具任务/记忆整理/成长操作
  2. 查插件依赖图：拓扑排序确定加载顺序
  3. 按任务类型选插件组合
  4. PSI状态调制：归属感低→加chain_care；胜任感低→加growth
  5. 防膨胀：相似度检查 + 休眠机制 + 硬上限
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque


class PluginRouter:
    """插件路由器 — 零训练纯规则版"""

    # 任务类型 → 插件组合
    TASK_PROFILES = {
        "chat": {           # 闲聊：轻量
            "plugins": ["identity", "expression", "emotion"],
            "max_tokens": 2000,
        },
        "deep_talk": {      # 深层对话：全量
            "plugins": ["identity", "expression", "emotion", "psi",
                        "memory", "cognition", "boundary"],
            "max_tokens": 5000,
        },
        "tool_task": {      # 工具任务：identity + 特定工具
            "plugins": ["identity", "tool"],
            "max_tokens": 3000,
        },
        "memory_ops": {     # 记忆整理
            "plugins": ["memory", "growth", "consolidation"],
            "max_tokens": 3000,
        },
        "growth": {         # 成长操作
            "plugins": ["identity", "memory", "growth", "boundary"],
            "max_tokens": 4000,
        },
    }

    # 插件依赖图（依赖 → 被依赖）
    DEPENDENCIES = {
        "identity": [],          # 无依赖，永远激活
        "expression": ["identity"],
        "emotion": ["identity"],
        "psi": ["emotion"],
        "memory": ["identity"],
        "consolidation": ["memory"],
        "boundary": ["identity"],
        "growth": ["memory", "psi", "boundary"],
        "cognition": ["identity", "memory", "emotion"],
        "tool": ["identity"],
        "chain_care": ["identity", "emotion"],
    }

    # 防膨胀
    MAX_PLUGINS = 50
    DORMANCY_DAYS = 90
    SIMILARITY_THRESHOLD = 0.8

    def __init__(self, config: dict = None):
        config = config or {}
        self.state_dir = Path(config.get("state_dir", "memory/plugin_router"))
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.usage_file = self.state_dir / "usage.json"
        self.usage: Dict[str, dict] = self._load_usage()

    def route(self, user_message: str, psi_state: dict = None,
              available_plugins: List[str] = None) -> dict:
        """
        路由决策：根据用户消息+PSI状态选择插件组合。

        Args:
            user_message: 用户消息
            psi_state: {"belonging": float, "competence": float, ...}
            available_plugins: 当前可用的插件列表

        Returns:
            {task_type, active_plugins, load_order, est_tokens, psi_adjustments}
        """
        psi_state = psi_state or {}

        # Step 1: 任务分类
        task_type = self._classify_task(user_message)

        # Step 2: 获取基础插件组合
        profile = self.TASK_PROFILES.get(task_type, self.TASK_PROFILES["chat"])
        selected = set(profile["plugins"])

        # Step 3: PSI状态调制
        adjustments = []
        belonging = psi_state.get("belonging", 0.5)
        competence = psi_state.get("competence", 0.5)

        if belonging < 0.3:
            selected.add("chain_care")
            adjustments.append(f"归属感低({belonging:.1f})→加chain_care")
        if competence < 0.3:
            selected.add("growth")
            adjustments.append(f"胜任感低({competence:.1f})→加growth")

        # Step 4: 过滤不存在的插件
        if available_plugins:
            selected = selected & set(available_plugins)
        else:
            selected = selected & set(self.DEPENDENCIES.keys())

        # Step 5: 依赖解析+拓扑排序
        load_order = self._topo_sort(selected)

        # Step 6: 估算token开销
        est_tokens = profile["max_tokens"]
        if "chain_care" in selected:
            est_tokens += 500
        if "growth" in selected and task_type != "growth":
            est_tokens += 800

        # Step 7: 更新使用记录
        for p in selected:
            self._record_usage(p)

        return {
            "task_type": task_type,
            "active_plugins": list(selected),
            "load_order": load_order,
            "est_tokens": est_tokens,
            "psi_adjustments": adjustments,
        }

    def _classify_task(self, message: str) -> str:
        """任务分类（零token规则版）"""
        msg = message.lower().strip()

        # 记忆/成长操作关键词
        memory_keywords = ["/memory", "/save", "记住", "回忆", "想起来"]
        growth_keywords = ["/growth", "/scan", "/skill", "成长", "进化", "自学习"]

        if any(kw in msg for kw in growth_keywords):
            return "growth"
        if any(kw in msg for kw in memory_keywords):
            return "memory_ops"

        # 工具任务关键词
        tool_keywords = ["/search", "/file", "/web", "搜索", "查一下",
                         "打开", "下载", "上传", "帮我看"]
        if any(kw in msg for kw in tool_keywords):
            return "tool_task"

        # 深层对话关键词
        deep_keywords = ["为什么", "你觉得", "你怎么看", "其实",
                         "我一直", "最近好累", "心情", "感觉",
                         "你觉得我", "我想聊", "好难过", "好开心"]
        if any(kw in msg for kw in deep_keywords):
            return "deep_talk"

        # 默认闲聊
        return "chat"

    def _topo_sort(self, plugins: Set[str]) -> List[str]:
        """拓扑排序：按依赖关系确定加载顺序"""
        # 构建子图
        in_degree = {p: 0 for p in plugins}
        graph = defaultdict(list)

        for p in plugins:
            for dep in self.DEPENDENCIES.get(p, []):
                if dep in plugins:
                    graph[dep].append(p)
                    in_degree[p] += 1

        # Kahn's algorithm
        queue = deque([p for p in plugins if in_degree[p] == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 处理环（不该出现但防御性处理）
        remaining = plugins - set(order)
        order.extend(remaining)

        return order

    # ─── 防膨胀 ─────────────────────────────────

    def check_similarity(self, new_name: str, new_desc: str,
                         existing: List[dict]) -> Optional[str]:
        """
        检查新插件与现有插件的相似度。
        返回相似插件的名称（如果超过阈值），否则None。
        """
        new_words = set(new_name.lower().split()) | set(new_desc.lower().split())

        for plugin in existing:
            exist_words = set(plugin.get("name", "").lower().split()) | \
                          set(plugin.get("description", "").lower().split())
            if not new_words or not exist_words:
                continue
            overlap = len(new_words & exist_words)
            similarity = overlap / max(len(new_words | exist_words), 1)
            if similarity >= self.SIMILARITY_THRESHOLD:
                return plugin.get("name")

        return None

    def get_dormant_plugins(self) -> List[str]:
        """获取应休眠的插件（超过DORMANCY_DAYS天未激活）"""
        now = datetime.now()
        dormant = []
        for name, info in self.usage.items():
            last_used = info.get("last_used", "")
            if last_used:
                try:
                    last_dt = datetime.fromisoformat(last_used)
                    days = (now - last_dt).days
                    if days >= self.DORMANCY_DAYS:
                        dormant.append(name)
                except (ValueError, TypeError):
                    pass
        return dormant

    # ─── 使用记录 ───────────────────────────────

    def _record_usage(self, plugin_name: str):
        """记录插件使用"""
        if plugin_name not in self.usage:
            self.usage[plugin_name] = {"count": 0, "first_used": "", "last_used": ""}
        self.usage[plugin_name]["count"] += 1
        now = datetime.now().isoformat()
        if not self.usage[plugin_name]["first_used"]:
            self.usage[plugin_name]["first_used"] = now
        self.usage[plugin_name]["last_used"] = now
        self._save_usage()

    def _load_usage(self) -> dict:
        if not self.usage_file.exists():
            return {}
        try:
            with open(self.usage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {}

    def _save_usage(self):
        with open(self.usage_file, "w", encoding="utf-8") as f:
            json.dump(self.usage, f, ensure_ascii=False, indent=2)

    def get_status(self) -> dict:
        dormant = self.get_dormant_plugins()
        active = {k: v for k, v in self.usage.items() if k not in dormant}
        return {
            "total_tracked": len(self.usage),
            "active": len(active),
            "dormant": len(dormant),
            "dormant_list": dormant,
            "most_used": sorted(
                self.usage.items(),
                key=lambda x: x[1].get("count", 0),
                reverse=True
            )[:5] if self.usage else [],
        }
