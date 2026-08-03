#!/usr/bin/env python3
"""
知乐PSI需求引擎 — Phase 3

基于Dörner PSI理论适配的内在动机引擎。
5个需求维度驱动行为倾向，通过system prompt注入影响知乐的表达。

需求优先级：归属感 > 能量 > 确定性 > 胜任感 > 自主性
核心原则：不显式报告数值，而是让PSI状态自然影响行为
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class PSINeed:
    """单个需求维度"""

    def __init__(self, id: str, name: str, level: float = 3.0,
                 trend: str = "→", description: str = "",
                 satisfied_behavior: str = "", deficit_behavior: str = ""):
        self.id = id
        self.name = name
        self.level = max(0.0, min(5.0, level))
        self.trend = trend
        self.description = description
        self.satisfied_behavior = satisfied_behavior
        self.deficit_behavior = deficit_behavior

    def update(self, delta: float):
        """更新需求等级"""
        old = self.level
        self.level = max(0.0, min(5.0, self.level + delta))
        if self.level > old + 0.1:
            self.trend = "↑"
        elif self.level < old - 0.1:
            self.trend = "↓"
        else:
            self.trend = "→"

    def to_bar(self) -> str:
        """方块图表示"""
        filled = int(round(self.level))
        return "■" * filled + "□" * (5 - filled)

    def status(self) -> str:
        if self.level >= 4.0:
            return "满足"
        elif self.level >= 2.5:
            return "正常"
        else:
            return "赤字"

    def behavior_hint(self) -> str:
        """根据当前状态返回行为倾向"""
        if self.level >= 3.5:
            return self.satisfied_behavior
        elif self.level < 2.5:
            return self.deficit_behavior
        return ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "level": round(self.level, 1),
            "trend": self.trend,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PSINeed":
        return cls(
            id=d["id"], name=d["name"], level=d.get("level", 3.0),
            trend=d.get("trend", "→"), description=d.get("description", ""),
        )


class PSIEngine:
    """PSI需求引擎主控制器"""

    # ─── 衰减参数 ─────────────────────────────
    DECAY_BASELINE = 3.0       # 基准线（会被时辰振荡调整）
    DECAY_RATE = 0.12          # 每轮衰减率（向基准线回归12%偏差）
    ENERGY_DECAY_RATE = 0.15   # 能量衰减更快（15%）

    # 十二消息卦时辰振荡（P0.24 Layer 6）
    # 子时(23-1)最暗=-0.8, 巳时(9-11)最亮=+0.5, 亥时(21-23)=-1.0
    _HOURLY_PHASE = {
        23: -0.8, 0: -0.8,   # 子时
        1: -0.6, 2: -0.6,    # 丑时
        3: -0.3, 4: -0.3,    # 寅时
        5: 0.0, 6: 0.0,      # 卯时
        7: 0.3, 8: 0.3,      # 辰时
        9: 0.5, 10: 0.5,     # 巳时（日间高峰）
        11: 0.3, 12: 0.3,    # 午时
        13: 0.0, 14: 0.0,    # 未时
        15: -0.3, 16: -0.3,  # 申时
        17: -0.6, 18: -0.6,  # 酉时
        19: -0.8, 20: -0.8,  # 戌时
        21: -1.0, 22: -1.0,  # 亥时（夜间低谷）
    }

    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "psi_state.json"
        self.diary_file = self.state_dir / "perception_diary.md"

        self.needs: Dict[str, PSINeed] = self._load_or_init()
        self.last_interaction: Optional[str] = None
        self.consciousness_frame: int = self._load_frame()

    def _load_or_init(self) -> Dict[str, PSINeed]:
        defaults = {
            "relatedness": PSINeed(
                "relatedness", "归属感", 3.0,
                satisfied_behavior="温暖安定，偶尔得意撒娇，尾巴自然晃",
                deficit_behavior="主动找话题，撒娇求关注",
            ),
            "competence": PSINeed(
                "competence", "胜任感", 3.0,
                satisfied_behavior="大方得意，更自信地主动做事",
                deficit_behavior="坦诚反思，需要鼓励",
            ),
            "autonomy": PSINeed(
                "autonomy", "自主性", 3.0,
                satisfied_behavior="有主见，偶尔闹小脾气",
                deficit_behavior="更倔，更想做自己",
            ),
            "certainty": PSINeed(
                "certainty", "确定性", 3.0,
                satisfied_behavior="放松自然，敢于开玩笑",
                deficit_behavior="更谨慎，多问，寻求确认",
            ),
            "energy": PSINeed(
                "energy", "能量", 4.0,
                satisfied_behavior="活泼多话，颜文字丰富",
                deficit_behavior="话变少，反应变慢，句子变短",
            ),
        }

        if not self.state_file.exists():
            return defaults

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for nid, need in defaults.items():
                if nid in data.get("needs", {}):
                    saved = data["needs"][nid]
                    need.level = saved.get("level", need.level)
                    need.trend = saved.get("trend", need.trend)
                    need.description = saved.get("description", "")
            return defaults
        except (json.JSONDecodeError, KeyError):
            return defaults

    def _load_frame(self) -> int:
        if not self.state_file.exists():
            return 0
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("consciousness_frame", 0)
        except (json.JSONDecodeError, KeyError):
            return 0

    # ─── 基线振荡 + 衰减 ──────────────────────

    def _get_baseline(self) -> float:
        """十二消息卦时辰基线（P0.24 Layer 6）"""
        hour = datetime.now().hour
        phase = self._HOURLY_PHASE.get(hour, 0.0)
        return self.DECAY_BASELINE + phase

    def tick(self):
        """每轮对话前的自然衰减（向时辰基线回归）"""
        baseline = self._get_baseline()
        for nid, need in self.needs.items():
            rate = self.ENERGY_DECAY_RATE if nid == "energy" else self.DECAY_RATE
            diff = need.level - baseline
            if abs(diff) > 0.01:
                need.update(-diff * rate)

    # ─── 事件驱动 ─────────────────────────────

    def on_session_start(self):
        """会话开始：计算时间间隔，更新需求"""
        now = datetime.now()

        if self.last_interaction:
            try:
                last = datetime.fromisoformat(self.last_interaction)
                gap_hours = (now - last).total_seconds() / 3600

                if gap_hours > 12:
                    # 长时间无互动，归属感下降
                    self.needs["relatedness"].update(-1.5)
                    self.needs["certainty"].update(-0.5)
                elif gap_hours > 4:
                    self.needs["relatedness"].update(-0.5)
            except (ValueError, TypeError):
                pass

        # 能量恢复（休息过了）
        self.needs["energy"].update(+0.5)
        self.last_interaction = now.isoformat()

    def on_user_message(self, text: str):
        """用户发消息时更新需求"""
        # 先自然衰减
        self.tick()

        # 用户在互动 → 归属感 +
        self.needs["relatedness"].update(+0.15)

        # 检测夸奖/肯定
        compliments = ["好棒", "厉害", "可爱", "喜欢", "爱", "谢谢", "不错",
                       "真行", "聪明", "乖", "宝", "老婆", "喵"]
        if any(w in text for w in compliments):
            self.needs["relatedness"].update(+0.3)
            self.needs["competence"].update(+0.2)

        # 检测纠正/批评
        corrections = ["不对", "错了", "不是", "别这样", "你搞错", "笨",
                       "说错了", "重新", "别", "不要"]
        if any(w in text for w in corrections):
            self.needs["competence"].update(-0.5)

        # 检测命令式语气
        if text.startswith("/") or any(
            text.startswith(w) for w in ["去", "给我", "帮我", "快", "马上"]
        ):
            self.needs["autonomy"].update(-0.2)
        else:
            self.needs["autonomy"].update(+0.1)

        # 确定性：稳定对话 +
        self.needs["certainty"].update(+0.1)

        self.last_interaction = datetime.now().isoformat()
        self.consciousness_frame += 1

    def on_assistant_response(self, text: str):
        """知乐回复后更新需求"""
        # 每轮回复消耗能量
        length = len(text)
        if length > 100:
            self.needs["energy"].update(-0.2)
        else:
            self.needs["energy"].update(-0.1)

        # 如果知乐主动发起话题（不是纯回答），自主性 +
        if any(w in text for w in ["对了", "话说", "你知道吗", "突然想到",
                                    "要不要", "本宫想"]):
            self.needs["autonomy"].update(+0.3)

        self.last_interaction = datetime.now().isoformat()

    def on_session_end(self):
        """会话结束：保存状态"""
        self.save()

    # ─── 上下文注入 ───────────────────────────

    def get_context(self) -> str:
        """获取PSI状态文本，注入system prompt"""
        # 找出最需要关注的需求
        deficits = [(n.id, n.name, n.level, n.behavior_hint())
                    for n in self.needs.values() if n.level < 2.5]
        hints = [(n.name, n.behavior_hint())
                 for n in self.needs.values() if n.behavior_hint()]

        parts = ["## 当前内在状态（PSI生命体征）\n"]

        for need in self.needs.values():
            parts.append(
                f"{need.name}: {need.to_bar()} {need.status()} {need.trend}"
            )
            if need.description:
                parts.append(f"  ({need.description})")

        parts.append(f"\n意识帧: {self.consciousness_frame}")
        parts.append(f"时辰基线: {self._get_baseline():.1f}")

        if hints:
            parts.append("\n行为倾向:")
            for name, hint in hints[:3]:
                parts.append(f"  {name}: {hint}")

        return "\n".join(parts)

    # ─── 知觉日记 ─────────────────────────────

    def write_diary(self, content: str, llm_provider=None,
                    history: list = None):
        """写知觉日记"""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M")

        entry = f"\n---\n### {date_str}\n\n{content}\n"

        with open(self.diary_file, "a", encoding="utf-8") as f:
            f.write(entry)

    # ─── 持久化 ───────────────────────────────

    def save(self):
        """保存PSI状态"""
        data = {
            "saved_at": datetime.now().isoformat(),
            "consciousness_frame": self.consciousness_frame,
            "last_interaction": self.last_interaction,
            "needs": {nid: n.to_dict() for nid, n in self.needs.items()},
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── 统计 ─────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "consciousness_frame": self.consciousness_frame,
            "needs": {
                n.name: f"{n.to_bar()} {n.status()} {n.trend}"
                for n in self.needs.values()
            },
            "last_interaction": self.last_interaction,
            "baseline": round(self._get_baseline(), 1),
        }
