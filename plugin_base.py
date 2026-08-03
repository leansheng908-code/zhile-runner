#!/usr/bin/env python3
"""
P0.4 插件基类 — 所有插件的统一接口

设计原则：
  - 核心尽量小，一切皆插件
  - 插件隔离：崩了不影响核心和其他插件
  - 接口稳定，实现自由（USB口原理）
  - 生命周期完整：load → message hooks → unload

插件类型：
  ContextPlugin  — 注入上下文到system prompt（记忆、PSI、卦象等）
  MessagePlugin  — 处理消息流（路由、边界拦截、翻译等）
  ToolPlugin     — 提供工具能力（搜索、文件操作等）
  BackgroundPlugin — 后台定时任务（守护进程、成长扫描等）
"""

from typing import List, Dict, Optional


class PluginBase:
    """所有插件的基类"""
    PLUGIN_TYPE = "base"
    VERSION = "1.0"
    NAME = ""
    DESCRIPTION = ""

    def __init__(self, config=None, core=None):
        self.config = config or {}
        self.core = core
        self.enabled = True
        self._healthy = True
        self._error_count = 0
        self._max_errors = 5  # 连续出错超过此值自动禁用

    @property
    def name(self):
        return self.NAME or self.__class__.__name__

    # ─── 生命周期 ─────────────────────────────

    def on_load(self):
        """插件加载时调用，可做初始化"""
        pass

    def on_unload(self):
        """插件卸载时调用，可做清理"""
        pass

    # ─── 消息钩子 ─────────────────────────────

    def on_user_message(self, message: str) -> str:
        """用户消息预处理，可修改消息内容"""
        return message

    def on_pre_llm(self, context: dict) -> dict:
        """LLM调用前，可修改上下文（messages、记忆等）
        context keys: messages, memory_context, psi_context, etc.
        """
        return context

    def on_post_llm(self, response: str) -> str:
        """LLM回复后，可修改回复内容"""
        return response

    def on_shortcut(self, response: str, route_label: str) -> str:
        """路由短路时调用（非LLM回复）"""
        return response

    # ─── 上下文注入 ───────────────────────────

    def get_context(self) -> str:
        """返回需要注入system prompt的上下文文本"""
        return ""

    # ─── 健康 ─────────────────────────────────

    def health_check(self) -> bool:
        """健康检查"""
        return self._healthy

    def _record_error(self):
        """记录一次错误，超过阈值自动禁用"""
        self._error_count += 1
        if self._error_count >= self._max_errors:
            self.enabled = False
            self._healthy = False

    def _record_success(self):
        """记录一次成功，重置错误计数"""
        self._error_count = 0


class ContextPlugin(PluginBase):
    """上下文插件 — 注入上下文到system prompt"""
    PLUGIN_TYPE = "context"


class MessagePlugin(PluginBase):
    """消息插件 — 处理消息流"""
    PLUGIN_TYPE = "message"


class ToolPlugin(PluginBase):
    """工具插件 — 提供工具能力"""
    PLUGIN_TYPE = "tool"

    def get_tools(self) -> List[Dict]:
        """返回工具定义列表（供LLM function calling）"""
        return []

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用工具"""
        return ""


class BackgroundPlugin(PluginBase):
    """后台插件 — 定时任务"""
    PLUGIN_TYPE = "background"

    def tick(self):
        """定时调用（由daemon触发）"""
        pass
