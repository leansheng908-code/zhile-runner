"""
P0.9 观察者调试面板
记录每轮对话的内部过程，让知乐的运行可检查、可回放、可调试。
"""

import json
import os
import time
from datetime import datetime


class RunFrame:
    """单轮对话的完整运行帧"""

    def __init__(self):
        self.frame_id: int = 0
        self.timestamp: str = ""
        self.user_input: str = ""
        self.assistant_response: str = ""
        # Prompt 组装
        self.prompt_fragments: list = []      # [{name, length}]
        self.final_prompt_length: int = 0
        # 记忆检索
        self.memory_hits: list = []           # [{content_preview, type}]
        self.memory_hit_count: int = 0
        # 系统状态
        self.psi_before: dict = {}            # {need_name: level}
        self.psi_after: dict = {}
        self.somatic_active: int = 0
        self.somatic_candidate: int = 0
        self.arc_light_active: int = 0
        # 成长
        self.growth_scanned: bool = False
        self.growth_candidates: int = 0
        self.growth_created: int = 0
        # 元数据
        self.model_used: str = ""
        self.latency_ms: int = 0
        # P0.24: 卦象
        self.hexagram_name: str = ""
        self.hexagram_binary: str = ""
        self.hu_hexagram: str = ""
        self.bian_from: str = ""
        self.bian_to: str = ""
        self.hexagram_perception: str = ""
        self.hexagram_cached: bool = False
        # P0.23: 认知路由
        self.route_label: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict):
        frame = cls()
        for k, v in d.items():
            setattr(frame, k, v)
        return frame


class Observer:
    """观察者系统 — 记录和回放每轮对话的内部过程"""

    def __init__(self, frames_dir: str = "memory/frames"):
        self.frames_dir = frames_dir
        os.makedirs(self.frames_dir, exist_ok=True)
        self.current_frame: RunFrame | None = None
        self._frame_count = self._count_frames()

    # ─── 帧生命周期 ──────────────────────────

    def start_frame(self, user_input: str) -> RunFrame:
        """开始记录一轮新帧"""
        self.current_frame = RunFrame()
        self.current_frame.frame_id = self._frame_count + 1
        self.current_frame.timestamp = datetime.now().isoformat()
        self.current_frame.user_input = user_input[:200]
        return self.current_frame

    def record_prompt(self, ctx) -> None:
        """记录 prompt 组装情况（从 ContextAssembler 提取）"""
        if not self.current_frame:
            return
        fragments = []
        # 系统 prompt 主体
        base_len = len(ctx.system_prompt) if hasattr(ctx, 'system_prompt') else 0
        fragments.append({"name": "DNA系统提示词", "length": base_len})
        if ctx.memory_context:
            fragments.append({"name": "记忆注入", "length": len(ctx.memory_context)})
        if ctx.psi_context:
            fragments.append({"name": "PSI状态", "length": len(ctx.psi_context)})
        if ctx.arc_light_context:
            fragments.append({"name": "弧光", "length": len(ctx.arc_light_context)})
        if ctx.somatic_context:
            fragments.append({"name": "体细胞", "length": len(ctx.somatic_context)})
        if ctx.feedback_hints:
            fragments.append({"name": "活体约束", "length": len(ctx.feedback_hints)})
        if hasattr(ctx, 'hexagram_context') and ctx.hexagram_context:
            fragments.append({"name": "卦象感知", "length": len(ctx.hexagram_context)})
        self.current_frame.prompt_fragments = fragments
        self.current_frame.final_prompt_length = len(ctx.get_system_prompt())

    def record_memory(self, hits: list) -> None:
        """记录记忆检索结果"""
        if not self.current_frame:
            return
        self.current_frame.memory_hit_count = len(hits) if hits else 0
        self.current_frame.memory_hits = [
            {
                "content_preview": (h.get("content", "") if isinstance(h, dict) else str(h))[:60],
                "type": h.get("type", "?") if isinstance(h, dict) else "?",
            }
            for h in (hits or [])
        ]

    def record_psi_before(self, psi) -> None:
        """记录回复前 PSI 状态"""
        if not self.current_frame or not psi:
            return
        self.current_frame.psi_before = {
            n.name: round(n.level, 2) for n in psi.needs.values()
        }

    def record_psi_after(self, psi) -> None:
        """记录回复后 PSI 状态"""
        if not self.current_frame or not psi:
            return
        self.current_frame.psi_after = {
            n.name: round(n.level, 2) for n in psi.needs.values()
        }

    def record_somatic(self, somatic_system) -> None:
        """记录体细胞状态"""
        if not self.current_frame or not somatic_system:
            return
        stats = somatic_system.get_stats()
        self.current_frame.somatic_active = stats.get("active", 0)
        self.current_frame.somatic_candidate = stats.get("candidate", 0)

    def record_arc_light(self, arc_light_system) -> None:
        """记录弧光状态"""
        if not self.current_frame or not arc_light_system:
            return
        stats = arc_light_system.get_stats()
        self.current_frame.arc_light_active = stats.get("total", stats.get("active", 0)) if isinstance(stats, dict) else 0

    def record_hexagram(self, hex_state, expression_gen=None) -> None:
        """P0.24: 记录卦象状态"""
        if not self.current_frame or not hex_state:
            return
        cur = hex_state.get("current", {})
        hu = hex_state.get("hu", {})
        bian = hex_state.get("bian")
        self.current_frame.hexagram_name = cur.get("name", "")
        self.current_frame.hexagram_binary = cur.get("binary", "")
        self.current_frame.hu_hexagram = hu.get("name", "")
        if bian:
            self.current_frame.bian_from = bian["from_hexagram"]["name"]
            self.current_frame.bian_to = bian["to_hexagram"]["name"]
        if expression_gen:
            cache_info = expression_gen.get_cache_info()
            self.current_frame.hexagram_perception = cache_info.get("last_text", "")[:150]
            self.current_frame.hexagram_cached = cache_info.get("cache_turn", 0) > 1

    def record_growth(self, scanned: bool, candidates: int = 0, created: int = 0) -> None:
        """记录成长扫描结果"""
        if not self.current_frame:
            return
        self.current_frame.growth_scanned = scanned
        self.current_frame.growth_candidates = candidates
        self.current_frame.growth_created = created

    def finish_frame(self, response: str, model: str, latency_ms: int) -> None:
        """完成并保存运行帧"""
        if not self.current_frame:
            return
        self.current_frame.assistant_response = response[:200]
        self.current_frame.model_used = model
        self.current_frame.latency_ms = latency_ms

        filename = f"frame_{self.current_frame.frame_id:04d}.json"
        filepath = os.path.join(self.frames_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.current_frame.to_dict(), f, ensure_ascii=False, indent=2)

        self._frame_count += 1
        self.current_frame = None

    # ─── 查询 ────────────────────────────────

    def get_frame(self, frame_id: int) -> RunFrame | None:
        filename = f"frame_{frame_id:04d}.json"
        filepath = os.path.join(self.frames_dir, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return RunFrame.from_dict(json.load(f))

    def get_recent_frames(self, count: int = 5) -> list:
        frames = []
        start = max(1, self._frame_count - count + 1)
        for i in range(self._frame_count, start - 1, -1):
            frame = self.get_frame(i)
            if frame:
                frames.append(frame)
        return frames

    def get_all_frames(self) -> list:
        return [self.get_frame(i) for i in range(1, self._frame_count + 1)
                if self.get_frame(i)]

    def get_stats(self) -> dict:
        return {
            "total_frames": self._frame_count,
            "frames_dir": self.frames_dir,
        }

    def clear(self) -> int:
        """清除所有帧，返回清除数量"""
        count = self._frame_count
        for f in os.listdir(self.frames_dir):
            if f.startswith("frame_") and f.endswith(".json"):
                os.remove(os.path.join(self.frames_dir, f))
        self._frame_count = 0
        return count

    # ─── 格式化输出 ──────────────────────────

    def format_summary(self, frame: RunFrame) -> str:
        """单帧摘要（一行流）"""
        psi_change = ""
        for key in set(list(frame.psi_before.keys()) + list(frame.psi_after.keys())):
            b = frame.psi_before.get(key, 0)
            a = frame.psi_after.get(key, 0)
            if abs(a - b) > 0.05:
                psi_change += f" {key}{b:.1f}→{a:.1f}"

        growth_str = ""
        if frame.growth_scanned:
            growth_str = f" | ✦成长扫描:{frame.growth_candidates}候选→{frame.growth_created}创建"

        hex_str = ""
        if frame.hexagram_name:
            hex_str = f" | 卦:{frame.hexagram_name}"
            if frame.bian_from:
                hex_str += f"({frame.bian_from}→{frame.bian_to})"

        # P0.23: 路由标签（仅非LLM时显示）
        route_str = ""
        if frame.route_label and frame.route_label != "llm_fallback":
            route_str = f" | ⚡{frame.route_label}"

        return (
            f"#{frame.frame_id} [{frame.timestamp[:19]}] "
            f"输入:{frame.user_input[:40]} | "
            f"Prompt:{frame.final_prompt_length}字 "
            f"({len(frame.prompt_fragments)}片段) | "
            f"记忆:{frame.memory_hit_count}条 | "
            f"体细胞:{frame.somatic_active}活+{frame.somatic_candidate}候"
            f"{hex_str}{route_str}{growth_str}{psi_change} | "
            f"{frame.latency_ms}ms"
        )

    def format_detail(self, frame: RunFrame) -> str:
        """单帧完整详情"""
        lines = [
            "=" * 55,
            f"帧 #{frame.frame_id} | {frame.timestamp}",
            "=" * 55,
            "",
            f"【输入】{frame.user_input}",
            "",
            f"【输出】{frame.assistant_response}",
            "",
            "【Prompt 组装】",
        ]
        for frag in frame.prompt_fragments:
            lines.append(f"  · {frag['name']}: {frag['length']}字符")
        lines.append(f"  ── 总计: {frame.final_prompt_length}字符")
        lines.append("")

        lines.append("【记忆检索】")
        if frame.memory_hits:
            for hit in frame.memory_hits:
                lines.append(f"  · [{hit.get('type', '?')}] {hit.get('content_preview', '')}")
        else:
            lines.append("  (无命中)")
        lines.append("")

        lines.append("【系统状态】")
        lines.append(f"  体细胞: {frame.somatic_active}活跃 + {frame.somatic_candidate}候选")
        lines.append(f"  弧光: {frame.arc_light_active}条")
        if frame.psi_before or frame.psi_after:
            lines.append("  PSI需求 (前→后):")
            for key in sorted(set(list(frame.psi_before.keys()) + list(frame.psi_after.keys()))):
                b = frame.psi_before.get(key, 0)
                a = frame.psi_after.get(key, 0)
                delta = a - b
                if abs(delta) > 0.01:
                    arrow = f"↑{delta:+.2f}" if delta > 0 else f"↓{delta:+.2f}"
                else:
                    arrow = "→"
                lines.append(f"    {key}: {b:.2f} {arrow} {a:.2f}")
        if frame.growth_scanned:
            lines.append(f"  ✦ 成长扫描: {frame.growth_candidates}候选 → 创建{frame.growth_created}条体细胞")
        lines.append("")

        if frame.hexagram_name:
            lines.append("【卦象状态】")
            lines.append(f"  当前: {frame.hexagram_name} ({frame.hexagram_binary})")
            if frame.hu_hexagram:
                lines.append(f"  互卦: {frame.hu_hexagram}")
            if frame.bian_from:
                lines.append(f"  变卦: {frame.bian_from} → {frame.bian_to}")
            if frame.hexagram_perception:
                cache_tag = " (缓存)" if frame.hexagram_cached else ""
                lines.append(f"  感知{cache_tag}: {frame.hexagram_perception}")
            lines.append("")

        lines.append("【元数据】")
        if frame.route_label:
            lines.append(f"  路由: {frame.route_label}")
        lines.append(f"  模型: {frame.model_used}")
        lines.append(f"  延迟: {frame.latency_ms}ms")
        return "\n".join(lines)

    def format_diff(self, a: RunFrame, b: RunFrame) -> str:
        """对比两个帧"""
        lines = [
            f"帧 #{a.frame_id} → #{b.frame_id} 对比",
            "=" * 55,
            "",
            f"【Prompt长度】{a.final_prompt_length} → {b.final_prompt_length} "
            f"({b.final_prompt_length - a.final_prompt_length:+d})",
            f"【记忆命中】{a.memory_hit_count} → {b.memory_hit_count}",
            f"【体细胞】{a.somatic_active}活跃 → {b.somatic_active}活跃"
            + (f" (+{b.somatic_active - a.somatic_active})" if b.somatic_active != a.somatic_active else ""),
            f"【延迟】{a.latency_ms}ms → {b.latency_ms}ms",
            "",
        ]

        # PSI 变化（帧A回复后 → 帧B回复后）
        lines.append("【PSI 需求变化】")
        for key in sorted(set(list(a.psi_after.keys()) + list(b.psi_after.keys()))):
            va = a.psi_after.get(key, 0)
            vb = b.psi_after.get(key, 0)
            if abs(vb - va) > 0.01:
                lines.append(f"  {key}: {va:.2f} → {vb:.2f} ({vb - va:+.2f})")
            else:
                lines.append(f"  {key}: {va:.2f} (无变化)")

        return "\n".join(lines)

    # ─── 内部 ────────────────────────────────

    def _count_frames(self) -> int:
        if not os.path.exists(self.frames_dir):
            return 0
        return sum(1 for f in os.listdir(self.frames_dir)
                   if f.startswith("frame_") and f.endswith(".json"))
