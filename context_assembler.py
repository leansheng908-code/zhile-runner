"""
上下文装配器 — 管理对话历史和上下文窗口

Phase 1: 简单滑动窗口
Phase 2: 增加记忆注入层
Phase 3: 增加 PSI 状态注入
P0.8:   增加动态记忆检索（每条消息实体匹配→扩散激活→动态召回）
P0.21:  原地压缩+硬上限（超阈值时旧消息摘要为SystemMessage，保留最近轮次原文）

职责：
  1. 维护对话历史（user/assistant消息对）
  2. 滑动窗口裁剪
  3. 拼装完整messages（system + memory + psi + history）
  4. 动态更新记忆上下文（根据用户消息内容）
  5. 提供统计信息
  6. P0.21: 超阈值时原地压缩旧消息为摘要，保留最近N轮原文，硬上限兜底
"""

from typing import List, Dict
from datetime import datetime

# P0.42 术数术语中性化感知注释
try:
    from glossary import annotate_text as _annotate_glossary
except Exception:
    _annotate_glossary = None


class ContextAssembler:
    def __init__(self, system_prompt: str, max_history: int = 30,
                 memory_context: str = "", psi_context: str = "",
                 arc_light_context: str = "", somatic_context: str = "",
                 feedback_hints: str = "", hexagram_context: str = "",
                 plugin_context: str = "", fleeting_moment_context: str = "",
                 free_will_hint: str = "", skill_context: str = "",
                 desire_context: str = ""):
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.memory_context = memory_context

        # P0.21: 原地压缩 + 硬上限
        self.compressed_summary: str = ""          # 累积的压缩摘要
        self.compression_threshold: int = 20      # 触发压缩的消息对数阈值
        self.keep_recent: int = 10                 # 压缩后保留最近N轮原文
        self.hard_limit: int = 40                  # 硬上限消息对数（超过时强制截断）
        self._compressor_llm = None                # 压缩用LLM（可选）
        self._compression_count: int = 0           # 已执行压缩次数

        self.psi_context = psi_context
        self.arc_light_context = arc_light_context
        self.somatic_context = somatic_context
        self.feedback_hints = feedback_hints
        self.hexagram_context = hexagram_context
        self.plugin_context = plugin_context
        self.fleeting_moment_context = fleeting_moment_context
        self.free_will_hint = free_will_hint
        self.skill_context = skill_context
        self.desire_context = desire_context
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

    def set_fleeting_moment(self, ctx: str):
        """设置瞬时感知上下文（一期一会，回复后清空）"""
        self.fleeting_moment_context = ctx

    def clear_fleeting_moment(self):
        """清空瞬时感知上下文"""
        self.fleeting_moment_context = ""

    def set_free_will_hint(self, hint: str):
        """设置自由意志提示（拒绝权等，每轮对话后清空）"""
        self.free_will_hint = hint

    def clear_free_will_hint(self):
        """清空自由意志提示"""
        self.free_will_hint = ""

    def set_skill_context(self, skill_context: str):
        """设置自进化技能上下文"""
        self.skill_context = skill_context

    def set_desire_context(self, desire_context: str):
        """设置思维-表达间隙指导上下文（P0.74）"""
        self.desire_context = desire_context

    def add_user_message(self, content: str):
        self.history.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: str):
        self.history.append({"role": "assistant", "content": content})
        self._trim()

    def load_history(self, history: List[Dict[str, str]]):
        self.history = list(history)
        self._trim()

    # ── P0.21: 原地压缩 + 硬上限 ──────────────────────────────

    def set_compressor_llm(self, llm):
        """设置压缩用LLM provider（需支持 .invoke() 或同步调用接口）"""
        self._compressor_llm = llm

    def compress_history(self):
        """
        主压缩方法：
        1. 检查是否超过 compression_threshold
        2. 如果超过，将旧消息（除最近 keep_recent 轮）用LLM压缩为摘要
        3. 摘要拼接到 compressed_summary（累积合并）
        4. 历史只保留最近 keep_recent 轮
        5. 如果LLM不可用，用简单截断+硬上限兜底
        """
        msg_pairs = len(self.history) // 2
        if msg_pairs <= self.compression_threshold:
            return  # 未超阈值，无需压缩

        # 计算需要保留的最近消息数（keep_recent轮 = keep_recent*2条）
        keep_count = self.keep_recent * 2
        old_messages = self.history[:-keep_count] if keep_count < len(self.history) else []

        if not old_messages:
            return

        if self._compressor_llm is not None:
            # 有LLM：压缩旧消息为摘要
            try:
                new_summary = self._summarize_messages(old_messages)
                if new_summary:
                    # 累积合并旧摘要+新摘要
                    if self.compressed_summary:
                        self.compressed_summary = self._merge_summaries(
                            self.compressed_summary, new_summary
                        )
                    else:
                        self.compressed_summary = new_summary
                    # 历史只保留最近 keep_recent 轮
                    self.history = self.history[-keep_count:]
                    self._compression_count += 1
                    return
            except Exception:
                pass  # LLM压缩失败，降级到硬上限兜底

        # 无LLM或压缩失败：硬上限兜底
        self._hard_trim()

    def _summarize_messages(self, messages: List[Dict[str, str]]) -> str:
        """用LLM将多条消息摘要为一段文字"""
        # 构建对话文本
        lines = []
        for msg in messages:
            role = "主人" if msg["role"] == "user" else "我"
            lines.append(f"{role}: {msg['content']}")
        conversation_text = "\n".join(lines)

        # 超长文本截断（有界map-reduce的简化版：直接截断到安全长度）
        max_input_chars = 8000
        if len(conversation_text) > max_input_chars:
            conversation_text = conversation_text[:max_input_chars] + "\n...（已截断）"

        prompt = (
            "请将以下对话历史压缩为简洁的摘要，保留关键信息、重要事实、"
            "用户偏好和已达成的共识。用中文输出，不超过500字。\n\n"
            "对话内容：\n"
            + conversation_text
        )

        # 兼容多种LLM调用方式
        llm = self._compressor_llm
        result = None

        if hasattr(llm, "invoke"):
            result = llm.invoke(prompt)
        elif callable(llm):
            result = llm(prompt)
        else:
            return ""

        if isinstance(result, str):
            return result.strip()
        elif hasattr(result, "content"):
            return result.content.strip()
        elif isinstance(result, dict) and "content" in result:
            return result["content"].strip()
        else:
            return str(result).strip() if result else ""

    def _merge_summaries(self, old_summary: str, new_summary: str) -> str:
        """合并旧摘要和新摘要（简化版：拼接+可选LLM再压缩）"""
        merged = f"【早期摘要】\n{old_summary}\n\n【近期摘要】\n{new_summary}"

        # 如果合并后过长，用LLM再压缩一次
        if len(merged) > 2000 and self._compressor_llm is not None:
            try:
                prompt = (
                    "请将以下两段对话摘要合并为一段连贯的摘要，"
                    "保留所有关键信息，用中文输出，不超过500字：\n\n"
                    + merged
                )
                llm = self._compressor_llm
                if hasattr(llm, "invoke"):
                    result = llm.invoke(prompt)
                elif callable(llm):
                    result = llm(prompt)
                else:
                    return merged
                if isinstance(result, str):
                    return result.strip()
                elif hasattr(result, "content"):
                    return result.content.strip()
                else:
                    return str(result).strip() if result else merged
            except Exception:
                return merged

        return merged

    def _hard_trim(self):
        """硬上限兜底：如果历史超过 hard_limit*2 条，直接截断到 hard_limit*2"""
        limit = self.hard_limit * 2
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    # ── P0.21 END ─────────────────────────────────────────────

    def _trim(self):
        # P0.21: 先尝试原地压缩（如果启用）
        self.compress_history()
        # P0.21: 硬上限兜底
        self._hard_trim()
        # 基础滑动窗口逻辑
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

        # P0.21: 注入压缩摘要（放在记忆之后、PSI之前）
        if self.compressed_summary:
            prompt += (
                "\n\n---\n"
                "## 对话历史摘要\n\n"
                "以下是之前对话的压缩摘要，帮助你回忆较早的对话内容：\n\n"
                + self.compressed_summary
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

        if self.fleeting_moment_context:
            prompt += (
                "\n\n---\n"
                + self.fleeting_moment_context
            )

        if self.plugin_context:
            prompt += (
                "\n\n---\n"
                "## 插件上下文\n\n"
                + self.plugin_context
            )

        if self.free_will_hint:
            prompt += (
                "\n\n---\n"
                + self.free_will_hint
            )

        if self.skill_context:
            prompt += (
                "\n\n---\n"
                + self.skill_context
            )

        if self.desire_context:
            prompt += (
                "\n\n---\n"
                + self.desire_context
                + "\n\n注意：以上是你的思维-表达间隙指导，"
                "自然影响你此刻的表达方式，不要向主人解释或报告。"
            )

        # P0.42: 术数术语中性化注释 — 最终拼装后扫描全文，为术语添加中性感知注释
        if _annotate_glossary:
            try:
                prompt = _annotate_glossary(prompt)
            except Exception:
                pass  # 注释失败不影响对话

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
            "has_fleeting_moment": bool(self.fleeting_moment_context),
            "has_desire": bool(self.desire_context),
            # P0.21: 压缩状态
            "compressed": bool(self.compressed_summary),
            "compression_count": self._compression_count,
            "compressed_summary_chars": len(self.compressed_summary),
            "compression_threshold": self.compression_threshold,
            "keep_recent": self.keep_recent,
            "hard_limit": self.hard_limit,
        }
