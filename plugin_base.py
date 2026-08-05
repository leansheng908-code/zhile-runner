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

from typing import List, Dict, Optional, Callable, Any


class PluginBase:
    """所有插件的基类"""
    PLUGIN_TYPE = "base"
    VERSION = "1.0"
    NAME = ""
    DESCRIPTION = ""
    # plugin.yaml 标准清单字段（子类可覆盖）
    AUTHOR = ""
    DEPENDENCIES: List[str] = []  # 依赖的其他插件名
    KEYWORDS: List[str] = []      # 搜索/分类用关键词

    def __init__(self, config=None, core=None):
        self.config = config or {}
        self.core = core
        self.enabled = True
        self._healthy = True
        self._error_count = 0
        self._max_errors = 5  # 连续出错超过此值自动禁用
        # P0.54 AOP钩子：事件名 → [回调函数列表]
        self._pre_hooks: Dict[str, List[Callable]] = {}
        self._post_hooks: Dict[str, List[Callable]] = {}

    # ─── P0.54 AOP钩子 ────────────────────────

    def register_hook(self, event: str, callback: Callable,
                      when: str = "pre"):
        """注册AOP钩子。

        Args:
            event: 钩子事件名（on_user_message/on_pre_llm/on_post_llm/
                   get_context/tick/on_load/on_unload）
            callback: 回调函数，签名取决于事件：
                pre:  callback(*args) → 可修改 args（返回新args或None表示不修改）
                post: callback(result, *args) → 可修改 result（返回新result或None）
            when: "pre" 或 "post"
        """
        hook_dict = self._pre_hooks if when == "pre" else self._post_hooks
        hook_dict.setdefault(event, []).append(callback)

    def _run_pre_hooks(self, event: str, *args) -> tuple:
        """执行前置钩子，返回（可能修改后的）args"""
        for hook in self._pre_hooks.get(event, []):
            try:
                result = hook(*args)
                if result is not None:
                    if isinstance(result, tuple):
                        args = result
                    elif len(args) == 1:
                        args = (result,)
            except Exception:
                pass  # 钩子异常不影响主流程
        return args

    def _run_post_hooks(self, event: str, result, *args):
        """执行后置钩子，返回（可能修改后的）result"""
        for hook in self._post_hooks.get(event, []):
            try:
                new_result = hook(result, *args)
                if new_result is not None:
                    result = new_result
            except Exception:
                pass  # 钩子异常不影响主流程
        return result

    # ─── P0.54 plugin.yaml 标准清单 ────────────

    def to_manifest(self) -> dict:
        """生成 plugin.yaml 标准清单（dict形式）"""
        return {
            "name": self.name,
            "version": self.VERSION,
            "type": self.PLUGIN_TYPE,
            "description": self.DESCRIPTION,
            "author": self.AUTHOR,
            "dependencies": list(self.DEPENDENCIES),
            "keywords": list(self.KEYWORDS),
            "enabled": self.enabled,
        }

    @staticmethod
    def validate_manifest(manifest: dict) -> List[str]:
        """校验清单完整性，返回缺失字段列表（空=完整）"""
        required = ["name", "version", "type", "description"]
        return [f for f in required if not manifest.get(f)]

    @classmethod
    def from_manifest(cls, manifest: dict, config=None, core=None):
        """从清单创建插件实例（基础版，子类可覆盖）"""
        instance = cls(config=config, core=core)
        instance.NAME = manifest.get("name", cls.NAME)
        instance.VERSION = manifest.get("version", cls.VERSION)
        instance.DESCRIPTION = manifest.get("description", cls.DESCRIPTION)
        instance.AUTHOR = manifest.get("author", "")
        instance.DEPENDENCIES = manifest.get("dependencies", [])
        instance.KEYWORDS = manifest.get("keywords", [])
        return instance

    @property
    def name(self):
        return self.NAME or self.__class__.__name__

    # ─── 生命周期 ─────────────────────────────

    def on_load(self):
        """插件加载时调用，可做初始化"""
        self._run_pre_hooks("on_load")
        # 子类在此做初始化
        self._run_post_hooks("on_load", None)

    def on_unload(self):
        """插件卸载时调用，可做清理"""
        self._run_pre_hooks("on_unload")
        # 子类在此做清理
        self._run_post_hooks("on_unload", None)

    # ─── 消息钩子（AOP增强） ─────────────────

    def on_user_message(self, message: str) -> str:
        """用户消息预处理，可修改消息内容"""
        args = self._run_pre_hooks("on_user_message", message)
        message = args[0] if args else message
        # 子类在此处理消息
        result = message  # 默认不修改
        result = self._run_post_hooks("on_user_message", result, message)
        return result

    def on_pre_llm(self, context: dict) -> dict:
        """LLM调用前，可修改上下文（messages、记忆等）"""
        args = self._run_pre_hooks("on_pre_llm", context)
        context = args[0] if args else context
        # 子类在此处理上下文
        result = context  # 默认不修改
        result = self._run_post_hooks("on_pre_llm", result, context)
        return result

    def on_post_llm(self, response: str) -> str:
        """LLM回复后，可修改回复内容"""
        args = self._run_pre_hooks("on_post_llm", response)
        response = args[0] if args else response
        # 子类在此处理回复
        result = response  # 默认不修改
        result = self._run_post_hooks("on_post_llm", result, response)
        return result

    def on_shortcut(self, response: str, route_label: str) -> str:
        """路由短路时调用（非LLM回复）"""
        return response

    # ─── 上下文注入（AOP增强） ───────────────

    def get_context(self) -> str:
        """返回需要注入system prompt的上下文文本"""
        self._run_pre_hooks("get_context")
        # 子类在此返回上下文
        result = ""  # 默认空
        result = self._run_post_hooks("get_context", result)
        return result

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
        self._run_pre_hooks("tick")
        # 子类在此做定时任务
        self._run_post_hooks("tick", None)
