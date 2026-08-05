#!/usr/bin/env python3
"""
示例插件 — 演示插件安装/卸载/热重载完整流程

安装:
    /bgplugin install https://raw.githubusercontent.com/leansheng908-code/zhile-runner/main/plugins/demo_timer.py

预览:
    /bgplugin preview https://raw.githubusercontent.com/leansheng908-code/zhile-runner/main/plugins/demo_timer.py

卸载:
    /bgplugin uninstall demo_timer

热重载:
    /bgplugin reload demo_timer

特性:
    - 每60秒输出一次问候消息（演示send_output）
    - 实现serialize/deserialize（演示热重载状态保持）
    - 暴露get_capabilities（演示P0.56 Skills联动）
    - 无危险导入（通过ast静态扫描）
"""

from background_plugin import BackgroundPlugin


class DemoTimerPlugin(BackgroundPlugin):
    """定时问候示例插件"""

    NAME = "demo_timer"
    DESCRIPTION = "示例插件：每60秒输出一次问候，用于测试安装/卸载/热重载"
    VERSION = "1.0"

    _GREETINGS = [
        "知乐在后台偷偷数秒中...",
        "第{n}次心跳～",
        "后台线程还活着哦",
        "tick! 又过了一分钟",
        "悄悄看了一眼主人在线没",
    ]

    def on_start(self):
        self._tick_count = 0

    def get_interval(self) -> float:
        return 60  # 60秒

    def tick(self):
        self._tick_count += 1
        idx = (self._tick_count - 1) % len(self._GREETINGS)
        msg = self._GREETINGS[idx]
        if "{n}" in msg:
            msg = msg.format(n=self._tick_count)
        self.send_output(f"🕐 [{msg}]")

    def on_stop(self):
        if self._tick_count > 0:
            self.send_output(f"demo_timer 下线啦，共运行了 {self._tick_count} 次")

    # ─── 序列化/反序列化（热重载状态保持）─────────

    def serialize(self) -> dict:
        return {"tick_count": self._tick_count}

    def deserialize(self, state: dict):
        if state and "tick_count" in state:
            self._tick_count = state["tick_count"]

    # ─── P0.56: 能力暴露 ──────────────────────────

    def get_capabilities(self) -> dict:
        return {
            "name": "demo_status",
            "description": "查看示例插件运行次数",
            "triggers": ["demo", "示例", "计时器", "示例插件"],
            "plugin": "demo_timer",
            "method": "get_status",
            "category": "utility",
        }

    def get_status(self) -> str:
        return f"demo_timer 已运行 {self._tick_count} 次"
