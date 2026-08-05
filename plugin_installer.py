#!/usr/bin/env python3
"""
插件安装器 — 下载、静态扫描、注册、热加载/卸载/重载

功能:
  1. install(url): 从HTTPS URL下载插件，ast静态扫描，动态导入，注册到manifest，热启动
  2. uninstall(name): 停止插件，序列化状态(可选)，从manifest移除，删除文件
  3. reload(name): 序列化状态→停止→重新导入→反序列化→启动

安全:
  - 只允许HTTPS URL
  - ast静态扫描危险导入(os/subprocess/ctypes等)和危险调用(eval/exec等)
  - 扫描结果作为警告返回，不自动拦截（由用户/cli决定）
  - 导入前用importlib动态加载，失败不影响主进程

用法:
    installer = PluginInstaller("plugins", "plugins/manifest.json")
    ok, msg, warnings = installer.install("https://example.com/my_plugin.py", manager=mgr)
    ok, msg = installer.uninstall("my_plugin", manager=mgr)
    ok, msg = installer.reload("my_plugin", manager=mgr)
"""

import os
import ast
import json
import urllib.request
import importlib.util
import importlib
import sys
from typing import Optional, Tuple, List

# ─── 危险模式黑名单 ──────────────────────────────

DANGEROUS_IMPORTS = {"os", "subprocess", "shutil", "ctypes", "sys", "socket", "pickle"}
DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__", "globals", "locals"}
DANGEROUS_ATTRS = {"__builtins__", "__subclasses__", "__bases__", "__mro__"}


class PluginInstaller:
    """插件安装/卸载/热重载管理器"""

    def __init__(self, plugins_dir: str = "plugins",
                 manifest_path: str = "plugins/manifest.json"):
        self.plugins_dir = plugins_dir
        self.manifest_path = manifest_path

    # ─── 安装 ───────────────────────────────────

    def install(self, url: str, manager=None) -> Tuple[bool, str, List[str]]:
        """
        从URL安装插件

        Args:
            url: HTTPS URL，指向.py文件
            manager: PluginManager实例（提供则自动注册+启动）

        Returns:
            (success, message, warnings)
        """
        # 1. 下载
        source, filename = self._download(url)
        if not source:
            return False, "下载失败", []

        # 2. 静态扫描
        warnings, has_bg_subclass = self._scan(source)
        if not has_bg_subclass:
            return False, "未找到BackgroundPlugin子类", warnings

        # 3. 保存到plugins目录
        os.makedirs(self.plugins_dir, exist_ok=True)
        filepath = os.path.join(self.plugins_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(source)

        # 4. 动态导入
        module_name = filename[:-3]  # 去掉.py
        mod = self._import_module(filepath, module_name)
        if not mod:
            return False, f"模块导入失败", warnings

        # 5. 查找BackgroundPlugin子类
        plugin_cls = self._find_plugin_class(mod)
        if not plugin_cls:
            return False, "导入后未找到BackgroundPlugin子类", warnings

        # 6. 注册到manifest
        plugin_name = plugin_cls.NAME or module_name
        self._register_manifest(plugin_name, module_name, plugin_cls.__name__)

        # 7. 热加载（如果提供了manager）
        if manager:
            # 先检查是否已注册同名插件
            existing = manager.get_plugin(plugin_name)
            if existing:
                manager.unregister(plugin_name)

            plugin = plugin_cls()
            manager.register(plugin)
            if not plugin.is_running:
                plugin.start()

        msg = f"插件 '{plugin_name}' v{getattr(plugin_cls, 'VERSION', '1.0')} 安装成功"
        if warnings:
            msg += f"（{len(warnings)}条安全警告）"
        return True, msg, warnings

    # ─── 卸载 ───────────────────────────────────

    def uninstall(self, name: str, manager=None) -> Tuple[bool, str]:
        """
        卸载插件：停止→从manager移除→从manifest移除→删除文件

        Args:
            name: 插件名称
            manager: PluginManager实例

        Returns:
            (success, message)
        """
        # 1. 从manager停止并移除
        if manager:
            plugin = manager.get_plugin(name)
            if plugin:
                manager.unregister(name)

        # 2. 从manifest移除并获取模块名
        removed, module_name = self._unregister_manifest(name)
        if not removed:
            return False, f"manifest中未找到插件 '{name}'"

        # 3. 删除文件
        if module_name:
            filepath = os.path.join(self.plugins_dir, module_name + ".py")
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError as e:
                    return True, f"插件 '{name}' 已移除（文件删除失败: {e}）"

        return True, f"插件 '{name}' 已卸载"

    # ─── 热重载 ─────────────────────────────────

    def reload(self, name: str, manager=None) -> Tuple[bool, str]:
        """
        热重载插件：序列化状态→停止→重新导入→反序列化→启动

        Args:
            name: 插件名称
            manager: PluginManager实例

        Returns:
            (success, message)
        """
        if not manager:
            return False, "需要PluginManager实例"

        plugin = manager.get_plugin(name)
        if not plugin:
            return False, f"插件 '{name}' 未找到"

        # 1. 序列化状态
        try:
            state = plugin.serialize()
        except Exception as e:
            state = {}
            print(f"  ⚠ 序列化状态失败: {e}")

        # 2. 停止插件
        plugin.stop()
        manager.unregister(name)

        # 3. 查找模块信息
        manifest = self._read_manifest()
        module_name = None
        class_name = None
        plugin_config = {}
        for entry in manifest.get("plugins", []):
            if entry.get("name") == name:
                module_name = entry.get("module")
                class_name = entry.get("class", "Plugin")
                plugin_config = entry.get("config", {})
                break

        if not module_name:
            return False, f"找不到插件 '{name}' 的模块信息"

        # 4. 重新导入模块
        filepath = os.path.join(self.plugins_dir, module_name + ".py")
        if not os.path.exists(filepath):
            return False, f"插件文件不存在: {filepath}"

        # 使用importlib.reload如果模块已加载
        if module_name in sys.modules:
            try:
                mod = importlib.reload(sys.modules[module_name])
            except Exception as e:
                return False, f"重新导入失败: {e}"
        else:
            mod = self._import_module(filepath, module_name)
            if not mod:
                return False, "模块导入失败"

        # 5. 查找类并创建新实例
        plugin_cls = self._find_plugin_class(mod)
        if not plugin_cls:
            return False, "重新导入后未找到BackgroundPlugin子类"

        # 6. 创建新实例，恢复状态，注册启动
        new_plugin = plugin_cls(config=plugin_config)
        try:
            if state:
                new_plugin.deserialize(state)
        except Exception as e:
            print(f"  ⚠ 反序列化状态失败: {e}")

        manager.register(new_plugin)
        new_plugin.start()

        return True, f"插件 '{name}' 已热重载（状态已恢复）"

    # ─── 内部方法 ───────────────────────────────

    def _download(self, url: str) -> Tuple[Optional[str], str]:
        """从HTTPS URL下载插件源码"""
        if not url.startswith("https://"):
            print(f"  ⚠ 仅支持HTTPS URL")
            return None, ""

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ZhileRunner/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                source = resp.read().decode("utf-8")

            # 从URL提取文件名
            filename = url.rstrip("/").split("/")[-1]
            if not filename.endswith(".py"):
                filename = "plugin_" + filename + ".py"

            # 安全文件名
            filename = "".join(
                c for c in filename if c.isalnum() or c in "._-"
            )
            if not filename:
                filename = "plugin_downloaded.py"

            return source, filename
        except Exception as e:
            print(f"  ⚠ 下载失败: {e}")
            return None, ""

    def _scan(self, source: str) -> Tuple[List[str], bool]:
        """
        静态分析插件源码

        Returns:
            (warnings, has_background_plugin_subclass)
        """
        warnings = []
        has_bg_subclass = False

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return [f"语法错误: {e}"], False

        for node in ast.walk(tree):
            # 检查import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module in DANGEROUS_IMPORTS:
                        warnings.append(f"⚠ 导入危险模块: {alias.name} (行{node.lineno})")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in DANGEROUS_IMPORTS:
                        warnings.append(f"⚠ 从危险模块导入: {node.module} (行{node.lineno})")

            # 检查危险调用
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_CALLS:
                    warnings.append(f"⚠ 危险调用: {node.func.id}() (行{node.lineno})")
                elif isinstance(node.func, ast.Attribute) and node.func.attr in DANGEROUS_ATTRS:
                    warnings.append(f"⚠ 危险属性访问: {node.func.attr} (行{node.lineno})")

            # 检查BackgroundPlugin子类
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "BackgroundPlugin":
                        has_bg_subclass = True
                    elif isinstance(base, ast.Attribute) and base.attr == "BackgroundPlugin":
                        has_bg_subclass = True

        return warnings, has_bg_subclass

    def _import_module(self, filepath: str, module_name: str):
        """动态导入模块"""
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if not spec or not spec.loader:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod
        except Exception as e:
            print(f"  ⚠ 模块执行失败: {e}")
            # 清理失败的模块
            if module_name in sys.modules:
                del sys.modules[module_name]
            return None

    def _find_plugin_class(self, mod):
        """在模块中查找BackgroundPlugin子类"""
        try:
            from background_plugin import BackgroundPlugin
        except ImportError:
            return None

        for attr_name in dir(mod):
            try:
                attr = getattr(mod, attr_name)
                if (isinstance(attr, type) and
                        issubclass(attr, BackgroundPlugin) and
                        attr is not BackgroundPlugin):
                    return attr
            except Exception:
                continue
        return None

    def _read_manifest(self) -> dict:
        """读取manifest.json"""
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            return {"plugins": []}

    def _write_manifest(self, data: dict):
        """写入manifest.json"""
        os.makedirs(os.path.dirname(self.manifest_path) or ".", exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _register_manifest(self, name: str, module: str, class_name: str):
        """注册插件到manifest（同名替换）"""
        data = self._read_manifest()
        data["plugins"] = [
            p for p in data.get("plugins", []) if p.get("name") != name
        ]
        data["plugins"].append({
            "name": name,
            "module": module,
            "class": class_name,
            "config": {}
        })
        self._write_manifest(data)

    def _unregister_manifest(self, name: str) -> Tuple[bool, Optional[str]]:
        """从manifest移除插件，返回(是否移除, 模块名)"""
        data = self._read_manifest()
        module_name = None
        original = data.get("plugins", [])
        filtered = []
        for entry in original:
            if entry.get("name") == name:
                module_name = entry.get("module")
            else:
                filtered.append(entry)

        if len(filtered) < len(original):
            data["plugins"] = filtered
            self._write_manifest(data)
            return True, module_name
        return False, None

    # ─── 工具方法 ───────────────────────────────

    def list_installable(self) -> List[dict]:
        """列出manifest中已注册但可能未加载的插件"""
        data = self._read_manifest()
        return data.get("plugins", [])

    def preview_source(self, url: str, max_lines: int = 30) -> Tuple[bool, str, List[str]]:
        """预览插件源码（不安装）"""
        source, _ = self._download(url)
        if not source:
            return False, "下载失败", []

        warnings, has_bg = self._scan(source)
        lines = source.split("\n")
        preview = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            preview += f"\n... ({len(lines)}行，仅显示前{max_lines}行)"

        return True, preview, warnings


# ─── 独立测试入口 ─────────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print("  插件安装器 · 独立测试")
    print("=" * 52)

    installer = PluginInstaller()

    # 测试静态扫描
    test_code = '''
import os
from background_plugin import BackgroundPlugin

class TestPlugin(BackgroundPlugin):
    NAME = "test"
    def tick(self):
        eval("1+1")
    def get_interval(self):
        return 60
'''
    warnings, has_bg = installer._scan(test_code)
    print(f"\n📋 静态扫描测试:")
    print(f"  BackgroundPlugin子类: {has_bg}")
    print(f"  警告: {warnings}")

    # 测试manifest读写
    print(f"\n📋 manifest读取:")
    entries = installer.list_installable()
    for e in entries:
        print(f"  - {e.get('name')}: {e.get('module')}.{e.get('class')}")

    print(f"\n{'=' * 52}")
    print("  测试完成")
    print(f"{'=' * 52}")
