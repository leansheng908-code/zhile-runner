#!/usr/bin/env python3
"""
示例插件 — 天气查询（演示插件系统用法）

这是P0.4插件系统的示例，展示如何创建一个标准插件：
1. 继承 PluginBase 或其子类
2. 设置 NAME / DESCRIPTION
3. 实现需要的钩子方法
4. 插件管理器自动加载并调用
"""

from plugin_base import ToolPlugin


class WeatherPlugin(ToolPlugin):
    """天气查询示例插件"""
    NAME = "weather"
    DESCRIPTION = "天气查询示例 — 演示插件系统用法"

    def on_load(self):
        print(f"[WeatherPlugin] 天气插件已加载")

    def on_unload(self):
        print(f"[WeatherPlugin] 天气插件已卸载")

    def get_context(self) -> str:
        return ""  # 不注入上下文

    def health_check(self) -> bool:
        return True
