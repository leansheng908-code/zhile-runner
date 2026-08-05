#!/usr/bin/env python3
"""
P0.60: 叙述事件协议 (Narration Events)

为桌宠/TTS/字幕系统铺路的三层分离架构 — 叙述层：
  - NarrationEvent: 纯数据类 + 工厂方法，定义事件协议
  - NarrationEmitter: 事件发射器，管理回调列表，无回调时静默通过

事件类型：
  - expression: 表情/动作（桌宠表情切换）
  - subtitle: 字幕（文字气泡）
  - task_status: 任务状态变更
  - thinking: 思考中（桌宠歪头）
  - speaking: 说话中（桌宠嘴巴动）

设计原则：
  - 事件是纯数据dict，不携带行为
  - Emitter只负责分发，不做任何渲染
  - 无消费者时emit静默通过，不影响主流程
"""

from datetime import datetime
from typing import Callable, Dict, List, Optional


class NarrationEvent:
    """叙述事件工厂 — 生成标准化事件dict"""

    # ─── 工厂方法 ─────────────────────────────

    @staticmethod
    def expression(emotion: str, action: str = None) -> dict:
        """表情/动作事件

        Args:
            emotion: 情绪标签 (happy/sad/curious/thinking/surprised/neutral)
            action: 可选动作描述 (wave/nod/shake_head/tilt_head)
        """
        event = {
            "type": "expression",
            "timestamp": datetime.now().isoformat(),
            "emotion": emotion,
        }
        if action:
            event["action"] = action
        return event

    @staticmethod
    def subtitle(text: str) -> dict:
        """字幕事件"""
        return {
            "type": "subtitle",
            "timestamp": datetime.now().isoformat(),
            "text": text,
        }

    @staticmethod
    def task_status(
        work_id: str,
        status: str,
        message: str = None,
    ) -> dict:
        """任务状态事件

        Args:
            work_id: 任务ID
            status: pending/running/completed/failed
            message: 可选状态消息
        """
        event = {
            "type": "task_status",
            "timestamp": datetime.now().isoformat(),
            "work_id": work_id,
            "status": status,
        }
        if message:
            event["message"] = message
        return event

    @staticmethod
    def thinking() -> dict:
        """思考中事件（桌宠歪头）"""
        return {
            "type": "thinking",
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def speaking() -> dict:
        """说话中事件（桌宠嘴巴动）"""
        return {
            "type": "speaking",
            "timestamp": datetime.now().isoformat(),
        }


class NarrationEmitter:
    """叙述事件发射器 — 管理回调列表，无回调时静默通过"""

    def __init__(self):
        self._callbacks: List[Callable[[dict], None]] = []

    # ─── 回调管理 ─────────────────────────────

    def on_event(self, callback: Callable[[dict], None]):
        """注册事件回调 callback(event_dict)"""
        self._callbacks.append(callback)

    # ─── 事件发射 ─────────────────────────────

    def emit(self, event: dict):
        """发出事件给所有已注册回调（异常不中断）"""
        if not self._callbacks:
            return
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                # 回调异常不影响主流程
                print(f"  ⚠ [Narration] 回调异常: {e}")

    # ─── 便捷方法 ─────────────────────────────

    def emit_expression(self, emotion: str, action: str = None):
        """便捷：发出表情事件"""
        self.emit(NarrationEvent.expression(emotion, action))

    def emit_subtitle(self, text: str):
        """便捷：发出字幕事件"""
        self.emit(NarrationEvent.subtitle(text))

    def emit_task_status(
        self,
        work_id: str,
        status: str,
        message: str = None,
    ):
        """便捷：发出任务状态事件"""
        self.emit(NarrationEvent.task_status(work_id, status, message))

    def emit_thinking(self):
        """便捷：发出思考中事件"""
        self.emit(NarrationEvent.thinking())

    def emit_speaking(self):
        """便捷：发出说话中事件"""
        self.emit(NarrationEvent.speaking())


# ===== 独立测试模式 =====
if __name__ == "__main__":
    print("=" * 50)
    print("NarrationEvents 独立测试")
    print("=" * 50)

    emitter = NarrationEmitter()

    # 1. 无回调时静默通过
    print("\n[1] 无回调 emit 测试...")
    emitter.emit_thinking()
    emitter.emit_speaking()
    emitter.emit_subtitle("测试字幕")
    emitter.emit_expression("happy", "wave")
    emitter.emit_task_status("test-001", "completed", "完成")
    print("  ✅ 无回调时不报错")

    # 2. 注册回调后接收事件
    print("\n[2] 注册回调后 emit 测试...")
    received = []
    emitter.on_event(lambda e: received.append(e))

    emitter.emit_thinking()
    emitter.emit_speaking()
    emitter.emit_subtitle("你好世界")
    emitter.emit_expression("curious", "tilt_head")
    emitter.emit_task_status("work-123", "running", "搜索中...")

    for ev in received:
        print(f"  {ev['type']:12s} | {ev}")

    assert len(received) == 5, f"期望5个事件，实际{len(received)}"
    print(f"\n  ✅ 收到 {len(received)} 个事件")

    # 3. 回调异常不中断
    print("\n[3] 回调异常隔离测试...")
    emitter2 = NarrationEmitter()
    emitter2.on_event(lambda e: (_ for _ in ()).throw(ValueError("故意出错")))
    emitter2.on_event(lambda e: print(f"  第二回调正常执行: {e['type']}"))
    emitter2.emit_thinking()
    print("  ✅ 异常回调不影响其他回调")

    print("\n✅ 全部通过")
