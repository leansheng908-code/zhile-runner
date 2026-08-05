#!/usr/bin/env python3
"""
知乐角色卡Avatar系统 — P0.58 Phase 1

PSI状态 → 表情映射引擎
支持emoji模式（默认）和图片模式（预留）

表情映射逻辑：
  energy < 2.0       → sleepy  😴
  relatedness < 2.0  → lonely  🥺
  autonomy < 2.0     → pout    😤
  relatedness >= 4.0 && energy >= 4.0 → happy 😊
  competence >= 4.0  → proud   😏
  certainty < 2.0    → thinking 🤔
  default            → neutral 🐱
"""

import json
from pathlib import Path
from typing import Optional


# ─── 表情定义 ───────────────────────────────

EXPRESSIONS = {
    "happy":    {"emoji": "😊", "label": "开心",  "desc": "归属感和能量都很足"},
    "lonely":   {"emoji": "🥺", "label": "想你",  "desc": "归属感低，想找主人"},
    "sleepy":   {"emoji": "😴", "label": "困倦",  "desc": "能量不足"},
    "pout":     {"emoji": "😤", "label": "傲娇",  "desc": "自主性受挫"},
    "proud":    {"emoji": "😏", "label": "得意",  "desc": "胜任感满满"},
    "thinking": {"emoji": "🤔", "label": "思考",  "desc": "确定性不足"},
    "neutral":  {"emoji": "🐱", "label": "日常",  "desc": "状态平稳"},
}


class AvatarManager:
    """角色卡表情管理器"""

    def __init__(self, config: dict = None):
        self.enabled = True
        self.name = "知乐"
        self.mode = "emoji"  # "emoji" or "image"
        self.image_dir = "assets/avatar"
        self.image_map = {}
        self._load_config(config or {})

    def _load_config(self, config: dict):
        """从config.json的avatar段加载配置"""
        av = config.get("avatar", {})
        self.enabled = av.get("enabled", True)
        self.name = av.get("name", "知乐")
        self.mode = av.get("mode", "emoji")
        self.image_dir = av.get("image_dir", "assets/avatar")
        self.image_map = av.get("image_expressions", {})

    def get_expression(self, psi_stats: dict) -> dict:
        """根据PSI状态返回当前表情信息"""
        if not self.enabled:
            return EXPRESSIONS["neutral"]

        needs = psi_stats.get("needs", {}) if psi_stats else {}

        # 从PSI needs解析数值
        levels = {}
        for nid, status_str in needs.items():
            # status_str 格式: "■■■□□ 满足 ↑"
            import re
            bar_match = re.search(r'([■□]+)', status_str)
            if bar_match:
                bars = bar_match.group(1)
                levels[nid] = bars.count("■")
            else:
                levels[nid] = 3.0  # 默认中等

        # 表情判定优先级（从高到低）
        energy = levels.get("energy", 4)
        relatedness = levels.get("relatedness", 3)
        autonomy = levels.get("autonomy", 3)
        competence = levels.get("competence", 3)
        certainty = levels.get("certainty", 3)

        if energy <= 1:
            expr_key = "sleepy"
        elif relatedness <= 1:
            expr_key = "lonely"
        elif autonomy <= 1:
            expr_key = "pout"
        elif relatedness >= 4 and energy >= 4:
            expr_key = "happy"
        elif competence >= 4:
            expr_key = "proud"
        elif certainty <= 1:
            expr_key = "thinking"
        else:
            expr_key = "neutral"

        expr = EXPRESSIONS.get(expr_key, EXPRESSIONS["neutral"])
        result = {
            "key": expr_key,
            "emoji": expr["emoji"],
            "label": expr["label"],
            "desc": expr["desc"],
            "name": self.name,
            "mode": self.mode,
        }

        # 图片模式：附带图片路径
        if self.mode == "image":
            img_file = self.image_map.get(expr_key, self.image_map.get("neutral", "default.png"))
            result["image"] = f"{self.image_dir}/{img_file}"

        return result

    def get_avatar_info(self) -> dict:
        """返回Avatar配置信息（不含当前表情）"""
        return {
            "enabled": self.enabled,
            "name": self.name,
            "mode": self.mode,
            "image_dir": self.image_dir,
            "expressions": {k: {"emoji": v["emoji"], "label": v["label"]}
                           for k, v in EXPRESSIONS.items()},
        }
