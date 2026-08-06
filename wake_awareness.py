#!/usr/bin/env python3
"""
知乐唤醒认知注入 — P0.69 Phase 4
唤醒时生成状态JSON，注入system prompt，闹钟管理

唤醒后立刻清醒（不做渐醒过渡），但在system prompt中注入当前状态信息。
AI根据这个信息自然表达：
  - 从浅睡醒来：「嗯？在呢~」
  - 从深睡醒来：「啊……刚在做梦呢，整理记忆来着」
  - 从完全睡眠被叫醒：「唔……几点了？」
  - 自然醒（闹钟）：「早安~ 睡了个好觉」
"""

from datetime import datetime, timedelta
from typing import Optional


class WakeAwareness:
    """唤醒认知管理器"""

    def __init__(self, sleep_manager):
        """
        Args:
            sleep_manager: SleepManager实例
        """
        self.sm = sleep_manager
        self._pending_wake_prompt: Optional[str] = None

    def on_wake(self, wake_context: dict):
        """唤醒回调 — 由SleepManager调用"""
        self._pending_wake_prompt = self.sm.get_wake_prompt()

    def consume_wake_prompt(self) -> Optional[str]:
        """消费并清除待处理的唤醒提示词"""
        prompt = self._pending_wake_prompt
        self._pending_wake_prompt = None
        return prompt

    def has_pending_wake(self) -> bool:
        """是否有待处理的唤醒认知"""
        return self._pending_wake_prompt is not None

    def get_sleep_status_text(self) -> str:
        """获取当前睡眠状态的简洁文本描述（用于观察者面板）"""
        status = self.sm.get_status()
        state_cn = status["state_cn"]
        idle_min = status["idle_minutes"]

        if status["state"] == "awake":
            return f"清醒（空闲{idle_min:.0f}min）"
        elif status["state"] == "light_sleep":
            return f"浅睡眠（已睡{idle_min:.0f}min）"
        elif status["state"] == "deep_sleep":
            dream = status.get("dream_task", "做梦中")
            return f"深睡眠·{dream}"
        elif status["state"] == "full_sleep":
            alarm = status.get("alarm", "未设闹钟")
            return f"完全睡眠（闹钟：{alarm}）"
        return state_cn

    def suggest_alarm_time(self) -> dict:
        """AI自主建议闹钟时间（基于用户作息规律）"""
        now = datetime.now()
        hour = now.hour

        # 深夜（23:00-5:00）→ 明早8点
        if hour >= 23 or hour < 5:
            alarm = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if alarm <= now:
                alarm += timedelta(days=1)
            return {
                "suggested_hour": 8,
                "suggested_minute": 0,
                "reason": "深夜了，明早8点叫你",
                "alarm_time": alarm.strftime("%H:%M"),
            }

        # 上午（5:00-11:00）→ 不设闹钟，白天小憩
        elif 5 <= hour < 11:
            return {
                "suggested_hour": None,
                "suggested_minute": None,
                "reason": "白天不需要闹钟，等你来找我",
                "alarm_time": None,
            }

        # 下午/傍晚（11:00-18:00）→ 30分钟后
        elif 11 <= hour < 18:
            return {
                "suggested_hour": None,
                "suggested_minute": 30,
                "reason": "午后小憩，30分钟后叫你",
                "alarm_time": (now + timedelta(minutes=30)).strftime("%H:%M"),
            }

        # 晚上（18:00-23:00）→ 1小时后
        else:
            return {
                "suggested_hour": None,
                "suggested_minute": 60,
                "reason": "晚上小憩，1小时后叫你",
                "alarm_time": (now + timedelta(minutes=60)).strftime("%H:%M"),
            }
