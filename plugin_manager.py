#!/usr/bin/env python3
"""
P0.4 插件管理器 — 加载/卸载/管理插件

职责：
  1. 从 plugins/ 目录动态加载插件
  2. 管理插件生命周期（load → hooks → unload）
  3. 插件隔离：单个插件崩溃不影响其他
  4. 健康检查与自动禁用
  5. 提供统计信息

插件发现方式：
  - plugins/manifest.json 中注册的插件（显式注册）
  - plugins/ 目录下符合命名规范的 .py 文件（自动发现）
"""

import os
import sys
import json
import importlib
import traceback
from typing import Dict, List, Optional


class PluginManager:
    """插件管理器"""

    def __init__(self, config=None, core=None):
        self.config = config or {}
        self.core = core
        self.plugins: Dict[str, PluginBase] = {}
        self._plugins_dir = self.config.get("dir", "plugins")
        self._manifest_path = os.path.join(self._plugins_dir, "manifest.json")
        self._manifest = self._load_manifest()

    # ─── 初始化 ───────────────────────────────

    def load_all(self):
        """加载所有已注册插件"""
        for entry in self._manifest.get("plugins", []):
            if not entry.get("enabled", True):
                continue
            try:
                self._load_from_entry(entry)
            except Exception as e:
                print(f"[PluginManager] 加载失败 {entry.get('name', '?')}: {e}")

    def _load_from_entry(self, entry: dict):
        """从manifest条目加载插件"""
        module_name = entry["module"]
        class_name = entry.get("class", "Plugin")
        plugin_config = entry.get("config", {})

        # 确保plugins目录在path中
        if self._plugins_dir not in sys.path:
            sys.path.insert(0, self._plugins_dir)

        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)

        plugin = cls(config=plugin_config, core=self.core)
        plugin.on_load()

        name = plugin.name
        self.plugins[name] = plugin
        return plugin

    def load_plugin(self, module_name: str, class_name: str = "Plugin",
                    config: dict = None, register: bool = True):
        """手动加载一个插件"""
        entry = {
            "module": module_name,
            "class": class_name,
            "config": config or {},
            "enabled": True,
            "name": module_name,
        }
        plugin = self._load_from_entry(entry)
        if register:
            self._manifest.setdefault("plugins", []).append(entry)
            self._save_manifest()
        return plugin

    def unload(self, name: str):
        """卸载插件"""
        if name in self.plugins:
            try:
                self.plugins[name].on_unload()
            except Exception:
                pass
            del self.plugins[name]
            # 更新manifest
            for entry in self._manifest.get("plugins", []):
                if entry.get("name") == name or entry.get("module") == name:
                    entry["enabled"] = False
            self._save_manifest()

    def enable(self, name: str) -> bool:
        """启用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = False
            return True
        return False

    # ─── 消息钩子（带隔离） ──────────────────

    def on_user_message(self, message: str) -> str:
        """用户消息预处理"""
        for plugin in self._enabled_plugins():
            try:
                message = plugin.on_user_message(message)
                plugin._record_success()
            except Exception as e:
                plugin._record_error()
                if not plugin.enabled:
                    print(f"[PluginManager] 插件 {plugin.name} 因连续错误被禁用: {e}")
        return message

    def on_pre_llm(self, context: dict) -> dict:
        """LLM调用前钩子"""
        for plugin in self._enabled_plugins():
            try:
                context = plugin.on_pre_llm(context)
                plugin._record_success()
            except Exception:
                plugin._record_error()
        return context

    def on_post_llm(self, response: str) -> str:
        """LLM回复后钩子"""
        for plugin in self._enabled_plugins():
            try:
                response = plugin.on_post_llm(response)
                plugin._record_success()
            except Exception:
                plugin._record_error()
        return response

    def on_shortcut(self, response: str, route_label: str) -> str:
        """路由短路时钩子"""
        for plugin in self._enabled_plugins():
            try:
                response = plugin.on_shortcut(response, route_label)
                plugin._record_success()
            except Exception:
                plugin._record_error()
        return response

    def get_all_context(self) -> str:
        """收集所有context插件的上下文"""
        parts = []
        for plugin in self._enabled_plugins():
            try:
                ctx = plugin.get_context()
                if ctx:
                    parts.append(ctx)
                    plugin._record_success()
            except Exception:
                plugin._record_error()
        return "\n\n".join(parts) if parts else ""

    def tick_background(self):
        """触发所有后台插件的tick"""
        from plugin_base import BackgroundPlugin
        for plugin in self._enabled_plugins():
            if isinstance(plugin, BackgroundPlugin):
                try:
                    plugin.tick()
                    plugin._record_success()
                except Exception:
                    plugin._record_error()

    # ─── 查询 ────────────────────────────────

    def _enabled_plugins(self) -> List:
        return [p for p in self.plugins.values() if p.enabled]

    def get_plugin(self, name: str):
        return self.plugins.get(name)

    def get_stats(self) -> dict:
        enabled = self._enabled_plugins()
        return {
            "total": len(self.plugins),
            "enabled": len(enabled),
            "disabled": len(self.plugins) - len(enabled),
            "plugins": [
                {
                    "name": p.name,
                    "type": p.PLUGIN_TYPE,
                    "version": p.VERSION,
                    "enabled": p.enabled,
                    "healthy": p.health_check(),
                    "errors": p._error_count,
                    "description": p.DESCRIPTION,
                }
                for p in self.plugins.values()
            ]
        }

    # ─── 持久化 ──────────────────────────────

    def _load_manifest(self) -> dict:
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"plugins": []}

    def _save_manifest(self):
        try:
            os.makedirs(self._plugins_dir, exist_ok=True)
            with open(self._manifest_path, "w", encoding="utf-8") as f:
                json.dump(self._manifest, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass
