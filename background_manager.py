#!/usr/bin/env python3
"""
P0.37 — 通道无关的后台任务管理器
将主动关心(P0.31)和新闻推送(P0.33)从qq.py下沉到核心层。
CLI/QQ/Web 各模式只需注册输出回调，后台逻辑由本模块统一驱动。
"""

import threading
import time
from datetime import datetime
from typing import Callable, Optional


class BackgroundTaskManager:
    """通道无关的后台任务管理器"""

    def __init__(self, core):
        self.core = core
        self._output_callback: Optional[Callable[[str], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 状态追踪
        self._last_proactive_time: Optional[datetime] = None
        self._last_news_date: dict = {}
        self._last_proactive_check = 0.0
        self._last_news_check = 0.0

    # ─── 输出通道注册 ──────────────────────────

    def register_output(self, callback: Callable[[str], None]):
        """注册输出通道回调。回调接收一个字符串消息。"""
        self._output_callback = callback

    def output(self, message: str) -> bool:
        """通过注册的通道输出消息，返回是否成功。"""
        if self._output_callback:
            try:
                self._output_callback(message)
                return True
            except Exception as e:
                print(f"  ⚠ 后台输出失败: {e}")
        return False

    # ─── 启动/停止 ──────────────────────────────

    def start(self):
        """启动后台任务线程（daemon，随主进程退出）"""
        if self._running:
            return
        proactive_cfg = self.core.config.get("proactive", {})
        news_cfg = self.core.config.get("news_push", {})
        if not (proactive_cfg.get("enabled", False) or news_cfg.get("enabled", False)):
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="bg-tasks")
        self._thread.start()

    def stop(self):
        self._running = False

    def status(self) -> dict:
        return {
            "running": self._running,
            "has_output": self._output_callback is not None,
            "last_proactive": self._last_proactive_time.isoformat() if self._last_proactive_time else None,
            "news_pushed_today": dict(self._last_news_date),
        }

    # ─── 主循环 ─────────────────────────────────

    def _run_loop(self):
        """后台线程主循环，每30秒检查一次各任务是否到期"""
        while self._running:
            time.sleep(30)
            try:
                now = time.time()
                # 主动关心检查
                proactive_cfg = self.core.config.get("proactive", {})
                if proactive_cfg.get("enabled", False):
                    interval = proactive_cfg.get("check_interval", 1800)
                    if now - self._last_proactive_check >= interval:
                        self._last_proactive_check = now
                        self._check_proactive(proactive_cfg)

                # 新闻推送检查
                news_cfg = self.core.config.get("news_push", {})
                if news_cfg.get("enabled", False):
                    interval = news_cfg.get("check_interval", 600)
                    if now - self._last_news_check >= interval:
                        self._last_news_check = now
                        self._check_news(news_cfg)

            except Exception as e:
                print(f"  ⚠ 后台任务异常: {e}")

    # ─── 主动关心 ───────────────────────────────

    def _check_proactive(self, config: dict):
        """检查并发送一条主动消息（从qq.py迁移，通道无关化）"""
        now = datetime.now()
        hour = now.hour

        quiet_start = config.get("quiet_hours_start", 23)
        quiet_end = config.get("quiet_hours_end", 7)
        min_gap = config.get("min_gap_hours", 2)
        belonging_threshold = config.get("belonging_threshold", 2.0)
        min_interaction_gap = config.get("min_interaction_gap_hours", 3)

        # 免打扰时段
        if quiet_start <= quiet_end:
            if quiet_start <= hour < quiet_end:
                return
        else:
            if hour >= quiet_start or hour < quiet_end:
                return

        # 节流
        if self._last_proactive_time:
            gap_h = (now - self._last_proactive_time).total_seconds() / 3600
            if gap_h < min_gap:
                return

        # 优先级0：对话感知关心钩子（P0.32）
        hook = self.core.pop_care_hook()
        if hook:
            message = self.core.generate_hook_message(hook)
            if message:
                if self.output(message):
                    self._last_proactive_time = now
                    print(f"  🪝 关心钩子已发送 [{hook.get('topic')}]: {message[:40]}")
                return

        # 优先级1：投递"想说的话"队列
        msg = self.core.pop_want_to_say()
        if msg:
            if self.output(msg):
                self._last_proactive_time = now
                print(f"  💌 主动消息已发送: {msg[:40]}")
            return

        # 优先级2：PSI归属感赤字 → 生成主动关心
        if self.core.psi:
            belonging = self.core.psi.needs.get("relatedness")
            if belonging and belonging.level < belonging_threshold:
                last_interaction = self.core.psi.last_interaction
                gap_hours = 0
                if last_interaction:
                    try:
                        last = datetime.fromisoformat(last_interaction)
                        gap_hours = (now - last).total_seconds() / 3600
                    except (ValueError, TypeError):
                        pass

                if gap_hours >= min_interaction_gap:
                    message = self.core.generate_proactive_message(
                        belonging.level, gap_hours
                    )
                    if message:
                        if self.output(message):
                            self._last_proactive_time = now
                            print(f"  💌 主动关心已发送: {message[:40]}")

    # ─── 新闻推送 ───────────────────────────────

    def _check_news(self, config: dict):
        """检查并推送新闻（从qq.py迁移，通道无关化）"""
        now = datetime.now()
        hour = now.hour

        quiet_start = config.get("quiet_hours_start", 23)
        quiet_end = config.get("quiet_hours_end", 7)
        push_windows = config.get("push_times", [9, 16])

        # 免打扰时段
        if quiet_start <= quiet_end:
            if quiet_start <= hour < quiet_end:
                return
        else:
            if hour >= quiet_start or hour < quiet_end:
                return

        # 检查是否在推送时间窗口内（±1小时）
        in_window = False
        window_key = None
        for pt in push_windows:
            if abs(hour - pt) <= 1:
                in_window = True
                window_key = f"news_{pt}"
                break

        if not in_window:
            return

        # 检查今天这个时段是否已推送
        today = now.strftime("%Y-%m-%d")
        if self._last_news_date.get(window_key) == today:
            return

        # 搜索并格式化新闻
        print(f"  📰 开始搜索新闻...")
        brief = self.core.search_and_format_news()
        if brief:
            if self.output(brief):
                self._last_news_date[window_key] = today
                print(f"  📰 新闻已推送: {brief[:50]}")
        else:
            print(f"  📰 新闻搜索无结果，跳过")
            self._last_news_date[window_key] = today
