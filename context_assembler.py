"""
上下文装配器 — 管理对话历史和上下文窗口

Phase 1: 简单滑动窗口
Phase 2: 增加记忆注入层
Phase 3: 增加 PSI 状态注入
P0.8:   增加动态记忆检索（每条消息实体匹配→扩散激活→动态召回）

职责：
  1. 维护对话历史（user/assistant消息对）
  2. 滑动窗口裁剪
  3. 拼装完整messages（system + memory + psi + history）
  4. 动态更新记忆上下文（根据用户消息内容）
  5. 提供统计信息
"""

from typing import List, Dict
from datetime import datetime


class ContextAssembler:
    def __init__(self, system_prompt: str, max_history: int = 30,
                 memory_context: str = "", psi_context: str = "",
                 arc_light_context: str = "", somatic_context: str = "",
                 feedback_hints: str = "", hexagram_context: str = "",
                 plugin_context: str = ""):
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.memory_context = memory_context
        self.psi_context = psi_context
        self.arc_light_context = arc_light_context
        self.somatic_context = somatic_context
        self.feedback_hints = feedback_hints
        self.hexagram_context = hexagram_context
        self.plugin_context = plugin_context
        self.history: List[Dict[str, str]] = []

    def set_memory_context(self, memory_context: str):
        """更新记忆上下文（动态检索后调用）"""
        self.memory_context = memory_context

    def set_psi_context(self, psi_context: str):
        self.psi_context = psi_context

    def set_arc_light_context(self, arc_light_context: str):
        self.arc_light_context = arc_light_context

    def set_somatic_context(self, somatic_context: str):
        self.somatic_context = somatic_context

    def set_feedback_hints(self, feedback_hints: str):
        self.feedback_hints = feedback_hints

    def set_hexagram_context(self, hexagram_context: str):
        self.hexagram_context = hexagram_context

    def set_plugin_context(self, plugin_context: str):
        self.plugin_context = plugin_context

    def add_user_message(self, content: str):
        self.history.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: str):
        self.history.append({"role": "assistant", "content": content})
        self._trim()

    def load_history(self, history: List[Dict[str, str]]):
        self.history = list(history)
        self._trim()

    def _trim(self):
        limit = self.max_history * 2
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    def get_system_prompt(self) -> str:
        """获取完整system prompt（含记忆+PSI注入）"""
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        time_info = (
            f"\n\n---\n## 当前时间\n\n"
            f"现在是 {now.strftime('%Y年%m月%d日')} {weekdays[now.weekday()]} "
            f"{now.strftime('%H:%M')}（北京时间）"
        )

        prompt = self.system_prompt + time_info

        if self.memory_context:
            prompt += (
                "\n\n---\n"
                "## 记忆（运行器自动注入）\n\n"
                "以下是你应该记住的关于主人和自己的重要信息，"
                "对话中自然运用但不要机械复述：\n\n"
                + self.memory_context
            )

        if self.psi_context:
            prompt += (
                "\n\n---\n"
                + self.psi_context
                + "\n\n注意：以上是你的内在状态，自然影响你的表达节奏和语气，"
                "但不要向主人解释PSI理论或报告数值。"
                "能量低时话变短，归属感高时更甜，这些都是自然的。"
            )

        if self.arc_light_context:
            prompt += (
                "\n\n---\n"
                + self.arc_light_context
                + "\n\n注意：以上是你已经内化的认知转变，自然体现在对话中，不要解释或报告。"
            )

        if self.somatic_context:
            prompt += (
                "\n\n---\n"
                + self.somatic_context
                + "\n\n注意：以上是你已经内化的表达习惯，自然使用，不要解释。"
            )

        if self.feedback_hints:
            prompt += (
                "\n\n---\n"
                + self.feedback_hints
                + "\n\n注意：以上是当前表达策略的微调方向，自然调整，不要向主人解释。"
            )

        if self.hexagram_context:
            prompt += (
                "\n\n---\n"
                "## 内心感知\n\n"
                + self.hexagram_context
                + "\n\n注意：以上是你此刻对自己内心的感知，"
                "自然影响你的语气和节奏，但不要向主人解释或分析自己的状态。"
            )

        if self.plugin_context:
            prompt += (
                "\n\n---\n"
                "## 插件上下文\n\n"
                + self.plugin_context
            )

        return prompt

    def get_messages(self) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": self.get_system_prompt()}]
        messages.extend(self.history)
        return messages

    def clear(self):
        self.history = []

    def get_stats(self) -> dict:
        history_chars = sum(len(m["content"]) for m in self.history)
        system_chars = len(self.get_system_prompt())
        total_chars = history_chars + system_chars
        estimated_tokens = int(total_chars / 1.8)

        return {
            "turn_count": len(self.history) // 2,
            "message_count": len(self.history),
            "history_chars": history_chars,
            "system_chars": system_chars,
            "estimated_tokens": estimated_tokens,
            "max_history": self.max_history,
            "has_memory": bool(self.memory_context),
            "has_psi": bool(self.psi_context),
            "has_arc_light": bool(self.arc_light_context),
            "has_somatic": bool(self.somatic_context),
            "has_feedback": bool(self.feedback_hints),
            "has_hexagram": bool(self.hexagram_context),
        }
