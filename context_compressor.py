#!/usr/bin/env python3
"""
P0.46② — 上下文压缩器
当对话历史超长时，用廉价LLM对中间轮次做结构化摘要，
保护头部（系统提示）和尾部（最近上下文），防止context爆炸。

参考：Hermes Agent的上下文压缩器设计
- Tool Output Pruning: 先裁剪工具输出节省token
- 结构化摘要: Goal/Progress/Decisions/Files/Next Steps
- 双窗口保护: 头部N条+尾部M条不动
"""

import json
from typing import List, Dict, Optional, Tuple


class ContextCompressor:
    """上下文压缩器 — 长对话自动摘要中间部分"""

    def __init__(self, llm_provider=None, config: dict = None):
        self.llm = llm_provider
        cfg = config or {}
        self.enabled = cfg.get("enabled", True)
        # 触发阈值：对话轮次超过此值时启动压缩
        self.threshold = cfg.get("threshold", 40)
        # 保护头部：前N条不压缩
        self.protect_head = cfg.get("protect_head", 6)
        # 保护尾部：最近M条不压缩
        self.protect_tail = cfg.get("protect_tail", 10)
        # 工具输出裁剪：超过此字符数的工具输出截断
        self.tool_output_max = cfg.get("tool_output_max", 500)
        # 压缩后的摘要最大token
        self.summary_max_tokens = cfg.get("summary_max_tokens", 800)
        # 摘要存储
        self._summaries: List[Dict] = []

    def should_compress(self, history: List[Dict]) -> bool:
        """判断是否需要压缩"""
        if not self.enabled or not self.llm:
            return False
        return len(history) > self.threshold

    def _prune_tool_outputs(self, messages: List[Dict]) -> List[Dict]:
        """Tool Output Pruning: 裁剪过长的工具输出"""
        pruned = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > self.tool_output_max:
                # 保留开头和结尾，中间用省略号
                half = self.tool_output_max // 2
                pruned_content = (
                    content[:half]
                    + f"\n...[已裁剪{len(content) - self.tool_output_max}字符]...\n"
                    + content[-half:]
                )
                msg = {**msg, "content": pruned_content}
            pruned.append(msg)
        return pruned

    def _format_for_summary(self, messages: List[Dict]) -> str:
        """将消息列表格式化为LLM可读的文本"""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # 处理多模态消息
                content = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            role_name = {"user": "用户", "assistant": "知乐", "system": "系统"}.get(role, role)
            lines.append(f"[{role_name}] {content}")
        return "\n".join(lines)

    def _build_summary_prompt(self, messages_text: str) -> List[Dict]:
        """构建摘要LLM请求"""
        system = (
            "你是对话摘要助手。请将以下对话历史压缩为结构化摘要，"
            "包含以下部分（如果有的话）：\n"
            "## 目标: 用户当前想完成什么\n"
            "## 进展: 已经做了什么\n"
            "## 决策: 做了哪些重要选择\n"
            "## 文件: 涉及哪些文件或路径\n"
            "## 下一步: 接下来要做什么\n\n"
            "要求：简洁、保留关键信息、不要编造。用中文。"
        )
        user = f"以下是需要压缩的对话历史：\n\n{messages_text}"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def compress(self, history: List[Dict]) -> Tuple[List[Dict], bool]:
        """
        压缩对话历史。
        返回 (压缩后的历史, 是否执行了压缩)
        """
        if not self.should_compress(history):
            return history, False

        head = history[:self.protect_head]
        middle = history[self.protect_head:-self.protect_tail]
        tail = history[-self.protect_tail:]

        if not middle:
            return history, False

        # Step 1: Tool Output Pruning
        middle_pruned = self._prune_tool_outputs(middle)

        # Step 2: 格式化并请求LLM摘要
        messages_text = self._format_for_summary(middle_pruned)
        summary_messages = self._build_summary_prompt(messages_text)

        try:
            # 使用非流式调用获取摘要
            summary = ""
            for chunk in self.llm.chat(summary_messages, stream=True):
                summary += chunk
            summary = summary.strip()
        except Exception as e:
            print(f"  ⚠ 上下文压缩失败，保持原样: {e}")
            return history, False

        if not summary:
            return history, False

        # Step 3: 构建压缩后的历史
        summary_msg = {
            "role": "system",
            "content": f"[对话摘要 — 之前的{len(middle)}轮对话已压缩]\n{summary}",
        }

        # 记录摘要历史
        self._summaries.append({
            "original_count": len(middle),
            "summary_length": len(summary),
            "timestamp": history[-1].get("timestamp", "") if history else "",
        })

        compressed = head + [summary_msg] + tail
        return compressed, True

    def get_stats(self) -> dict:
        """获取压缩统计"""
        return {
            "enabled": self.enabled,
            "threshold": self.threshold,
            "total_compressions": len(self._summaries),
            "last_compression": self._summaries[-1] if self._summaries else None,
        }

    def estimate_token_savings(self, history: List[Dict]) -> dict:
        """估算如果压缩能节省多少token"""
        if not self.should_compress(history):
            return {"would_compress": False}

        middle = history[self.protect_head:-self.protect_tail]
        if not middle:
            return {"would_compress": False}

        original_chars = sum(
            len(msg.get("content", "")) if isinstance(msg.get("content"), str) else 0
            for msg in middle
        )
        estimated_summary_chars = self.summary_max_tokens * 2  # 粗估：1 token ≈ 2字符

        return {
            "would_compress": True,
            "middle_turns": len(middle),
            "original_chars": original_chars,
            "estimated_summary_chars": estimated_summary_chars,
            "estimated_savings": max(0, original_chars - estimated_summary_chars),
        }
