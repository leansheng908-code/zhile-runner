#!/usr/bin/env python3
"""
知乐意识节律·三层睡眠系统 — P0.69
四状态有限状态机：Awake → Light → Deep → Full

这是AI的生命节律系统，不是省电策略。
唤醒词不是开机按钮，是"叫醒"——从不同睡眠深度中被唤醒。

状态转换：
  Awake ──(无交互10-15min)──→ Light ──(无打扰30-60min)──→ Deep(做梦)
  任意状态 ←──(唤醒词)────── 任意状态
  Deep ──(做梦完成+判断该睡了)──→ Full ──(闹钟/唤醒词)──→ Awake
"""

import json
import time
import threading
import sys
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Callable


class SleepState(Enum):
    """四层睡眠状态"""
    AWAKE = "awake"           # 清醒：全部感知与后台运行
    LIGHT = "light_sleep"     # 浅睡：关闭大部分感知，保留唤醒词
    DEEP = "deep_sleep"       # 深睡=做梦：执行系统维护与自我成长
    FULL = "full_sleep"       # 完全睡眠：近乎零资源，仅唤醒词+闹钟


# 状态中文名
STATE_CN = {
    SleepState.AWAKE: "清醒",
    SleepState.LIGHT: "浅睡眠",
    SleepState.DEEP: "深睡眠(做梦)",
    SleepState.FULL: "完全睡眠",
}

# 默认阈值（秒）
DEFAULT_LIGHT_THRESHOLD = 600      # 10分钟无交互 → 浅睡
DEFAULT_DEEP_THRESHOLD = 1800      # 浅睡30分钟 → 深睡
DEFAULT_FULL_SLEEP_HOUR_START = 23 # 晚上23点后允许完全睡眠
DEFAULT_FULL_SLEEP_HOUR_END = 7    # 早上7点前为睡眠时段
DEFAULT_ALARM_DEFAULT_HOUR = 8     # 默认闹钟8点


class SleepManager:
    """睡眠管理器 — 状态机核心"""

    def __init__(self, core, config: dict = None):
        """
        Args:
            core: ZhileCore实例
            config: sleep配置字典
        """
        self.core = core
        cfg = config or {}

        # 阈值配置
        self.light_threshold = cfg.get("light_threshold", DEFAULT_LIGHT_THRESHOLD)
        self.deep_threshold = cfg.get("deep_threshold", DEFAULT_DEEP_THRESHOLD)
        self.full_sleep_hour_start = cfg.get("full_sleep_hour_start", DEFAULT_FULL_SLEEP_HOUR_START)
        self.full_sleep_hour_end = cfg.get("full_sleep_hour_end", DEFAULT_FULL_SLEEP_HOUR_END)
        self.default_alarm_hour = cfg.get("default_alarm_hour", DEFAULT_ALARM_DEFAULT_HOUR)

        # 状态
        self._state = SleepState.AWAKE
        self._state_since = datetime.now()
        self._last_interaction = datetime.now()
        self._last_wake_reason: Optional[str] = None
        self._last_wake_from: Optional[SleepState] = None
        self._sleep_duration = timedelta()
        self._dream_task: Optional[str] = None

        # 闹钟
        self._alarm: Optional[datetime] = None
        self._alarm_set_by: Optional[str] = None  # "ai" or "user"

        # 状态持久化
        self._state_file = Path(cfg.get("state_file", "memory/sleep_state.json"))
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

        # 线程
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._check_interval = 30  # 每30秒检查一次状态转换

        # 唤醒回调
        self._wake_callbacks: list = []

        # 做梦完成回调
        self._dream_complete_callback: Optional[Callable] = None

        # 加载持久化状态
        self._load_state()

    # ─── 生命周期 ─────────────────────────────

    def start(self):
        """启动睡眠管理器后台线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="sleep-manager"
        )
        self._thread.start()
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"😴 [睡眠管理器] 已启动，当前状态：{STATE_CN[self._state]}（{ts}）",
              file=sys.stderr)

    def stop(self):
        """停止睡眠管理器"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._save_state()

    # ─── 核心循环 ─────────────────────────────

    def _run_loop(self):
        """主循环：定期检查状态转换条件"""
        while not self._stop_event.is_set():
            try:
                self._check_transitions()
            except Exception as e:
                print(f"😴 [睡眠管理器] 检查异常: {e}", file=sys.stderr)
            self._stop_event.wait(self._check_interval)

    def _check_transitions(self):
        """检查并执行状态转换"""
        now = datetime.now()
        idle_seconds = (now - self._last_interaction).total_seconds()

        if self._state == SleepState.AWAKE:
            # 清醒 → 浅睡
            if idle_seconds >= self.light_threshold:
                self._transition_to(SleepState.LIGHT, reason="idle_timeout")

        elif self._state == SleepState.LIGHT:
            # 浅睡 → 深睡
            light_duration = (now - self._state_since).total_seconds()
            if light_duration >= self.deep_threshold:
                self._transition_to(SleepState.DEEP, reason="light_timeout")

        elif self._state == SleepState.DEEP:
            # 深睡 → 完全睡眠（做梦完成 + 时间合适）
            if self._dream_task is None:
                # 做梦任务已完成
                if self._should_full_sleep(now):
                    self._transition_to(SleepState.FULL, reason="dream_done_late_night")
                else:
                    # 不该完全睡，回到浅睡等下一轮
                    self._transition_to(SleepState.LIGHT, reason="dream_done_not_late")

        elif self._state == SleepState.FULL:
            # 完全睡眠 → 检查闹钟
            if self._alarm and now >= self._alarm:
                self.wake(reason="alarm", dream_task=None)

    def _should_full_sleep(self, now: datetime) -> bool:
        """判断是否应该进入完全睡眠"""
        hour = now.hour
        # 在睡眠时段内（23:00-7:00）
        if self.full_sleep_hour_start <= hour or hour < self.full_sleep_hour_end:
            return True
        # 或者超长时间无交互（超过3小时）
        idle_hours = (now - self._last_interaction).total_seconds() / 3600
        if idle_hours >= 3:
            return True
        return False

    def _transition_to(self, new_state: SleepState, reason: str):
        """执行状态转换"""
        old_state = self._state
        if old_state == new_state:
            return

        old_cn = STATE_CN[old_state]
        new_cn = STATE_CN[new_state]
        ts = datetime.now().strftime("%H:%M:%S")

        # 离开旧状态
        if old_state == SleepState.AWAKE:
            pass
        elif old_state == SleepState.DEEP:
            # 离开深睡，停止做梦任务
            self._dream_task = None

        # 进入新状态
        self._state = new_state
        self._state_since = datetime.now()

        # 进入深睡 → 开始做梦
        if new_state == SleepState.DEEP:
            self._start_dreaming()

        # 进入完全睡眠 → 设置闹钟
        if new_state == SleepState.FULL:
            self._set_alarm_if_needed()

        # 暂停/恢复守护进程
        self._sync_daemon()

        print(f"😴 [睡眠管理器] {old_cn} → {new_cn}（{ts}，原因：{reason}）",
              file=sys.stderr)

        self._save_state()

    def _sync_daemon(self):
        """根据睡眠状态同步守护进程"""
        if not hasattr(self.core, "daemon") or not self.core.daemon:
            return

        if self._state in (SleepState.LIGHT, SleepState.FULL):
            # 浅睡/完全睡眠：暂停守护进程
            if self.core.daemon.enabled:
                self.core.daemon.stop()
        elif self._state == SleepState.AWAKE:
            # 清醒：恢复守护进程
            if not (self.core.daemon._thread and self.core.daemon._thread.is_alive()):
                self.core.daemon.start()
        # 深睡：守护进程通过做梦调度器调用

    def _start_dreaming(self):
        """开始做梦 — 触发做梦任务调度器"""
        self._dream_task = "starting"
        if self._dream_complete_callback:
            try:
                result = self._dream_complete_callback()
                self._dream_task = None  # 做梦完成
                print(f"😴 [睡眠管理器] 做梦完成（{result}）", file=sys.stderr)
            except Exception as e:
                print(f"😴 [睡眠管理器] 做梦异常: {e}", file=sys.stderr)
                self._dream_task = None
        else:
            # 没有做梦调度器，直接标记完成
            self._dream_task = None

    def _set_alarm_if_needed(self):
        """进入完全睡眠时设置闹钟"""
        if self._alarm and datetime.now() < self._alarm:
            return  # 已有闹钟

        # 默认闹钟：明天早上 default_alarm_hour 点
        now = datetime.now()
        alarm = now.replace(hour=self.default_alarm_hour, minute=0, second=0, microsecond=0)
        if alarm <= now:
            alarm += timedelta(days=1)
        self._alarm = alarm
        self._alarm_set_by = "ai"
        ts = alarm.strftime("%H:%M")
        print(f"😴 [睡眠管理器] 设定闹钟：{ts}", file=sys.stderr)

    # ─── 唤醒 ─────────────────────────────────

    def wake(self, reason: str = "wake_word", dream_task: Optional[str] = None):
        """从任意睡眠状态唤醒到清醒"""
        if self._state == SleepState.AWAKE:
            self._last_interaction = datetime.now()
            return

        old_state = self._state
        self._last_wake_from = old_state
        self._last_wake_reason = reason
        self._sleep_duration = datetime.now() - self._state_since
        self._dream_task = dream_task

        self._state = SleepState.AWAKE
        self._state_since = datetime.now()
        self._last_interaction = datetime.now()
        self._alarm = None  # 清除闹钟

        # 恢复守护进程
        self._sync_daemon()

        old_cn = STATE_CN[old_state]
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"😴 [睡眠管理器] {old_cn} → 清醒（{ts}，原因：{reason}）",
              file=sys.stderr)

        # 触发唤醒回调
        for cb in self._wake_callbacks:
            try:
                cb(self.get_wake_context())
            except Exception as e:
                print(f"😴 [睡眠管理器] 唤醒回调异常: {e}", file=sys.stderr)

        self._save_state()

    def register_wake_callback(self, callback: Callable):
        """注册唤醒回调函数"""
        self._wake_callbacks.append(callback)

    def register_dream_callback(self, callback: Callable):
        """注册做梦完成回调函数"""
        self._dream_complete_callback = callback

    # ─── 交互更新 ─────────────────────────────

    def touch(self):
        """更新最后交互时间（收到用户消息时调用）"""
        self._last_interaction = datetime.now()
        if self._state != SleepState.AWAKE:
            self.wake(reason="user_message")

    # ─── 闹钟管理 ─────────────────────────────

    def set_alarm(self, hour: int, minute: int = 0, set_by: str = "user") -> str:
        """设置闹钟"""
        now = datetime.now()
        alarm = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if alarm <= now:
            alarm += timedelta(days=1)
        self._alarm = alarm
        self._alarm_set_by = set_by
        return alarm.strftime("%Y-%m-%d %H:%M")

    def clear_alarm(self):
        """清除闹钟"""
        self._alarm = None
        self._alarm_set_by = None

    # ─── 唤醒认知 ─────────────────────────────

    def get_wake_context(self) -> dict:
        """生成唤醒认知上下文（注入system prompt）"""
        return {
            "sleep_state": self._last_wake_from.value if self._last_wake_from else None,
            "wake_reason": self._last_wake_reason,
            "dream_task": self._dream_task,
            "sleep_duration": str(self._sleep_duration).split(".")[0],  # 去掉微秒
            "last_interaction": self._last_interaction.strftime("%Y-%m-%d %H:%M:%S"),
            "current_state": self._state.value,
        }

    def get_wake_prompt(self) -> str:
        """生成唤醒认知提示词片段"""
        if not self._last_wake_from or self._last_wake_from == SleepState.AWAKE:
            return ""

        ctx = self.get_wake_context()
        state_cn = STATE_CN.get(self._last_wake_from, "")
        reason_cn = {
            "wake_word": "被唤醒词叫醒",
            "user_message": "被用户消息叫醒",
            "alarm": "闹钟叫醒",
        }.get(ctx["wake_reason"], ctx["wake_reason"])

        lines = [
            f"\n【睡眠认知】你刚从{state_cn}中醒来（{reason_cn}）",
            f"睡眠时长：{ctx['sleep_duration']}",
        ]

        if self._last_wake_from == SleepState.DEEP:
            if ctx["dream_task"]:
                lines.append(f"正在做梦（{ctx['dream_task']}）时被打断")
            else:
                lines.append("做梦刚完成，整理了一些记忆")
        elif self._last_wake_from == SleepState.FULL:
            lines.append("从深度安眠中被唤醒")

        lines.append("自然地体现刚醒来的状态，不要刻意解释睡眠机制。")

        return "\n".join(lines)

    # ─── 状态查询 ─────────────────────────────

    def get_status(self) -> dict:
        """获取完整状态"""
        now = datetime.now()
        idle = (now - self._last_interaction).total_seconds()

        return {
            "state": self._state.value,
            "state_cn": STATE_CN[self._state],
            "state_since": self._state_since.strftime("%Y-%m-%d %H:%M:%S"),
            "idle_seconds": round(idle, 0),
            "idle_minutes": round(idle / 60, 1),
            "last_interaction": self._last_interaction.strftime("%Y-%m-%d %H:%M:%S"),
            "last_wake_from": self._last_wake_from.value if self._last_wake_from else None,
            "last_wake_reason": self._last_wake_reason,
            "dream_task": self._dream_task,
            "alarm": self._alarm.strftime("%Y-%m-%d %H:%M") if self._alarm else None,
            "alarm_set_by": self._alarm_set_by,
            "thresholds": {
                "light_min": round(self.light_threshold / 60, 0),
                "deep_min": round(self.deep_threshold / 60, 0),
                "full_sleep_hours": f"{self.full_sleep_hour_start}:00-{self.full_sleep_hour_end}:00",
            },
        }

    @property
    def state(self) -> SleepState:
        return self._state

    @property
    def is_awake(self) -> bool:
        return self._state == SleepState.AWAKE

    @property
    def is_sleeping(self) -> bool:
        return self._state != SleepState.AWAKE

    # ─── 持久化 ───────────────────────────────

    def _save_state(self):
        """保存状态到文件"""
        data = {
            "state": self._state.value,
            "state_since": self._state_since.isoformat(),
            "last_interaction": self._last_interaction.isoformat(),
            "alarm": self._alarm.isoformat() if self._alarm else None,
            "alarm_set_by": self._alarm_set_by,
        }
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"😴 [睡眠管理器] 保存状态失败: {e}", file=sys.stderr)

    def _load_state(self):
        """从文件恢复状态"""
        if not self._state_file.exists():
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            state_str = data.get("state", "awake")
            self._state = SleepState(state_str)
            self._state_since = datetime.fromisoformat(data["state_since"])
            self._last_interaction = datetime.fromisoformat(data["last_interaction"])

            if data.get("alarm"):
                self._alarm = datetime.fromisoformat(data["alarm"])
                self._alarm_set_by = data.get("alarm_set_by")

            # 重启后如果之前在睡眠状态，唤醒到清醒
            if self._state != SleepState.AWAKE:
                self._last_wake_from = self._state
                self._last_wake_reason = "restart"
                self._sleep_duration = datetime.now() - self._state_since
                self._state = SleepState.AWAKE
                self._state_since = datetime.now()
                print(f"😴 [睡眠管理器] 重启恢复：从{STATE_CN.get(self._last_wake_from, '')}唤醒到清醒",
                      file=sys.stderr)

        except Exception as e:
            print(f"😴 [睡眠管理器] 加载状态失败: {e}", file=sys.stderr)
            self._state = SleepState.AWAKE
