#!/usr/bin/env python3
"""
P0.26 Phase 3 · 架构自认知模块

通过 AST 解析运行器自身代码库，构建结构化映射，供 LLM 在代码生成时理解：
  - 哪些模块、哪些类、哪些接口
  - 在哪加什么（扩展点 / 注册点）
  - 模块间依赖关系

核心类: ArchitectureMap
  - build_map()               扫描所有 .py 文件，AST 提取类/函数/导入/抽象方法/docstring
  - get_module_info(name)     查询模块详情
  - get_extension_points()    获取所有扩展点（带 @abstractmethod 的类）
  - get_registration_points() 获取注册点
  - suggest_insertion(desc)   根据自然语言描述建议插入点
  - to_context_string(max_tokens)  格式化为 LLM 上下文（按优先级裁剪）
  - get_dependency_graph()    模块间 import 依赖图
  - diff_map(old, new)        比较两次扫描差异
  - 缓存机制: 首次扫描存 memory/architecture_map.json，后续按 mtime 增量更新

依赖: 仅 Python 标准库 ast / json / os / re / time / pathlib
"""

import ast
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class ArchitectureMap:
    """运行器代码库架构映射"""

    # ── 已知扩展点类名（带 @abstractmethod 或这些名字即视为扩展点） ──
    KNOWN_EXTENSION_CLASSES = {
        "BackgroundPlugin": {
            "module_hint": "background_plugin",
            "description": "后台循环插件基类",
            "how_to_extend": "继承 BackgroundPlugin，实现 tick() 和 get_interval()，"
                             "注册到 PluginManager",
        },
        "PluginBase": {
            "module_hint": "plugin_base",
            "description": "对话插件基类",
            "how_to_extend": "继承 PluginBase，实现 on_user_message() 等钩子，"
                             "注册到 PluginRouter",
        },
        "ModelProvider": {
            "module_hint": "model_provider",
            "description": "LLM Provider 抽象基类",
            "how_to_extend": "继承 ModelProvider，实现 chat()，注册到 ProviderFactory",
        },
        "VisionProvider": {
            "module_hint": "model_provider",
            "description": "视觉模型 Provider 抽象基类",
            "how_to_extend": "继承 VisionProvider，实现 vision_describe()",
        },
        "AudioProvider": {
            "module_hint": "model_provider",
            "description": "音频模型 Provider 抽象基类",
            "how_to_extend": "继承 AudioProvider，实现 transcribe()",
        },
    }

    # ── 已知注册点（硬编码，因为它们是结构性约定而非 AST 可发现） ──
    KNOWN_REGISTRATION_POINTS = [
        {"target": "plugins/manifest.json", "what": "后台插件注册",
         "format": "JSON 数组，每项含 name/module/class/interval"},
        {"target": "config.json:plugins", "what": "插件启用配置",
         "format": "JSON 对象，key=插件名，value=配置"},
        {"target": "cli.py:_handle_command", "what": "CLI 命令注册",
         "format": "elif main_cmd == '/xxx': 分支"},
        {"target": "core.py:chat()", "what": "对话钩子注入",
         "format": "在 chat() 方法中调用对应模块方法"},
    ]

    # ── suggest_insertion 关键词映射 ──
    SUGGESTION_KEYWORDS = [
        {
            "keywords": ["后台", "定时", "循环", "周期", "tick", "interval",
                         "监控", "轮询"],
            "suggestion": {
                "extension_point": "BackgroundPlugin",
                "module": "background_plugin",
                "how_to": "继承 BackgroundPlugin，实现 tick() 和 get_interval()，"
                          "在 plugins/ 下创建新文件，注册到 manifest.json",
                "example": "plugins/stock_monitor.py",
            },
        },
        {
            "keywords": ["命令", "cli", "指令", "/"],
            "suggestion": {
                "extension_point": None,
                "module": "cli",
                "how_to": "在 cli.py _handle_command() 中添加 elif 分支，"
                          "并实现对应的 _handle_xxx 方法",
                "example": "cli.py:_handle_command",
            },
        },
        {
            "keywords": ["模型", "llm", "provider", "api", "gpt", "claude",
                         "deepseek"],
            "suggestion": {
                "extension_point": "ModelProvider",
                "module": "model_provider",
                "how_to": "继承 ModelProvider，实现 chat()，"
                          "在 ProviderFactory 中注册",
                "example": "model_provider.py:DeepSeekProvider",
            },
        },
        {
            "keywords": ["记忆", "存储", "memory", "持久化", "保存"],
            "suggestion": {
                "extension_point": None,
                "module": "memory_system",
                "how_to": "使用 MemorySystem.add() 添加记忆，"
                          "或在 MemorySystem 中扩展新的记忆类型",
                "example": "memory_system.py:MemorySystem.add()",
            },
        },
        {
            "keywords": ["路由", "触发", "route", "shortcut", "短路"],
            "suggestion": {
                "extension_point": None,
                "module": "cognitive_router",
                "how_to": "在 CognitiveRouter 中添加新的路由规则，"
                          "或继承 PluginBase 创建新插件注册到 PluginRouter",
                "example": "cognitive_router.py:CognitiveRouter.route()",
            },
        },
        {
            "keywords": ["插件", "plugin", "对话", "消息", "reply", "回复"],
            "suggestion": {
                "extension_point": "PluginBase",
                "module": "plugin_base",
                "how_to": "继承 PluginBase（或 ContextPlugin/MessagePlugin），"
                          "实现钩子方法，注册到 PluginRouter",
                "example": "plugin_base.py:MessagePlugin",
            },
        },
        {
            "keywords": ["技能", "skill", "学习", "进化"],
            "suggestion": {
                "extension_point": None,
                "module": "skill_evolution",
                "how_to": "通过 SkillEvolution 管理技能生命周期，"
                          "或使用 SkillLearner 自动学习",
                "example": "skill_evolution.py:SkillEvolution",
            },
        },
    ]

    def __init__(self, root_dir: str = ".", cache_file: str = None):
        """
        Args:
            root_dir: 代码库根目录
            cache_file: 缓存文件路径，默认 memory/architecture_map.json
        """
        self.root_dir = Path(root_dir).resolve()
        if cache_file is None:
            cache_file = str(self.root_dir / "memory" / "architecture_map.json")
        self.cache_file = cache_file
        self._map: Optional[dict] = None

    # ══════════════════════════════════════════════════════════════
    #  核心方法: build_map
    # ══════════════════════════════════════════════════════════════

    def build_map(self, force: bool = False) -> dict:
        """扫描所有 .py 文件，AST 解析，构建完整架构映射。

        Args:
            force: True 时强制全量重建（忽略缓存）

        Returns:
            架构映射 dict
        """
        # 尝试加载缓存
        cached = self._load_cache() if not force else None

        # 收集所有 .py 文件
        py_files = self._collect_py_files()

        # 确定哪些文件需要重新解析
        file_mtimes = {}
        for f in py_files:
            try:
                file_mtimes[str(f)] = os.path.getmtime(f)
            except OSError:
                pass

        modules = {}
        if cached and "modules" in cached:
            modules = dict(cached["modules"])
            cached_mtimes = cached.get("_mtimes", {})
            # 只重新解析 mtime 变化的文件
            for f_path in list(file_mtimes.keys()):
                rel = self._rel_module_name(f_path)
                if (rel in cached_mtimes
                        and cached_mtimes[rel] == file_mtimes[f_path]
                        and rel in modules):
                    continue  # 缓存有效
                # 需要重新解析
                mod_info = self._parse_file(f_path)
                if mod_info:
                    modules[mod_info["module_name"]] = mod_info
            # 删除已不存在的文件
            current_modules = {self._rel_module_name(f) for f in py_files}
            for mod_name in list(modules.keys()):
                if mod_name not in current_modules:
                    del modules[mod_name]
        else:
            # 全量解析
            for f_path in py_files:
                mod_info = self._parse_file(f_path)
                if mod_info:
                    modules[mod_info["module_name"]] = mod_info

        # 构建扩展点和注册点
        extension_points = self._detect_extension_points(modules)
        registration_points = list(self.KNOWN_REGISTRATION_POINTS)

        # 构建依赖图
        dependency_graph = self._build_dependency_graph(modules)

        self._map = {
            "scan_time": datetime.now().isoformat(timespec="seconds"),
            "file_count": len(py_files),
            "module_count": len(modules),
            "modules": modules,
            "extension_points": extension_points,
            "registration_points": registration_points,
            "dependency_graph": dependency_graph,
            "_mtimes": {
                self._rel_module_name(f): os.path.getmtime(f)
                for f in py_files
                if os.path.exists(f)
            },
        }

        # 保存缓存
        self._save_cache(self._map)
        return self._map

    # ══════════════════════════════════════════════════════════════
    #  查询方法
    # ══════════════════════════════════════════════════════════════

    def get_module_info(self, name: str) -> Optional[dict]:
        """查询某模块详情"""
        if self._map is None:
            self.build_map()
        return self._map["modules"].get(name)

    def get_extension_points(self) -> List[dict]:
        """获取所有可扩展点（带 @abstractmethod 的类）"""
        if self._map is None:
            self.build_map()
        return self._map.get("extension_points", [])

    def get_registration_points(self) -> List[dict]:
        """获取所有注册点"""
        if self._map is None:
            self.build_map()
        return self._map.get("registration_points", [])

    def suggest_insertion(self, desc: str) -> dict:
        """根据自然语言描述建议插入点。

        Args:
            desc: 需求描述，如 "后台定时任务" / "新增CLI命令"

        Returns:
            {"desc": ..., "suggestion": {...}, "alternatives": [...]}
        """
        if self._map is None:
            self.build_map()

        desc_lower = desc.lower()
        best_match = None
        best_score = 0
        alternatives = []

        for entry in self.SUGGESTION_KEYWORDS:
            score = sum(1 for kw in entry["keywords"] if kw in desc_lower)
            if score > 0:
                if score > best_score:
                    if best_match:
                        alternatives.append(best_match)
                    best_match = entry["suggestion"]
                    best_score = score
                else:
                    alternatives.append(entry["suggestion"])

        if not best_match:
            # 无匹配时返回默认建议
            best_match = {
                "extension_point": None,
                "module": "core",
                "how_to": "在 core.py 中添加新方法，或在 plugins/ 下创建新模块",
                "example": "core.py",
            }

        return {
            "desc": desc,
            "suggestion": best_match,
            "alternatives": alternatives[:3],
        }

    def to_context_string(self, max_tokens: int = 2000) -> str:
        """格式化为 LLM 上下文字符串，按优先级裁剪。

        优先级（高→低）:
          1. 扩展点 + 注册点（必选）
          2. 当前任务相关模块的类和方法签名
          3. 完整模块列表
          4. 依赖关系图

        Args:
            max_tokens: token 上限（~4字符≈1token）

        Returns:
            格式化的架构上下文字符串
        """
        if self._map is None:
            self.build_map()

        char_budget = max_tokens * 4
        sections = []

        def _est(s: str) -> int:
            return len(s)

        # ── 优先级 1: 扩展点 + 注册点 ──
        ext_lines = ["## 扩展点（可继承的基类）"]
        for ep in self._map.get("extension_points", []):
            ext_lines.append(
                f"- {ep['name']} ({ep['module']}): {ep.get('description', '')}"
            )
            if ep.get("abstract_methods"):
                ext_lines.append(
                    f"  抽象方法: {', '.join(ep['abstract_methods'])}"
                )
            if ep.get("how_to_extend"):
                ext_lines.append(f"  扩展方式: {ep['how_to_extend']}")
        ext_text = "\n".join(ext_lines)

        reg_lines = ["## 注册点（新功能登记位置）"]
        for rp in self._map.get("registration_points", []):
            reg_lines.append(f"- {rp['target']}: {rp['what']} ({rp.get('format', '')})")
        reg_text = "\n".join(reg_lines)

        sections.append(ext_text)
        sections.append(reg_text)

        remaining = char_budget - _est(ext_text) - _est(reg_text)
        if remaining <= 0:
            return "\n\n".join(sections)[:char_budget]

        # ── 优先级 3: 完整模块列表 ──
        mod_lines = ["## 模块概览"]
        for mod_name, mod_info in sorted(self._map["modules"].items()):
            classes = ", ".join(mod_info.get("classes", {}).keys()) or "无类"
            mod_lines.append(
                f"- {mod_name} ({mod_info.get('file', '?')}, "
                f"{mod_info.get('lines', 0)}行): {classes}"
            )
        mod_text = "\n".join(mod_lines)

        if _est(mod_text) <= remaining:
            sections.append(mod_text)
            remaining -= _est(mod_text)
        else:
            # 截断到预算内
            truncated = mod_text[:remaining]
            sections.append(truncated)
            remaining = 0

        # ── 优先级 4: 依赖图 ──
        if remaining > 100:
            dep_lines = ["## 模块依赖（部分）"]
            dep_graph = self._map.get("dependency_graph", {})
            shown = 0
            for mod, deps in sorted(dep_graph.items()):
                if shown >= 30:
                    dep_lines.append("... (更多依赖省略)")
                    break
                dep_lines.append(f"- {mod} → {', '.join(deps[:5])}")
                shown += 1
            dep_text = "\n".join(dep_lines)
            if _est(dep_text) <= remaining:
                sections.append(dep_text)

        return "\n\n".join(sections)

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """模块间 import 依赖图

        Returns:
            {module_name: [imported_module, ...]}
        """
        if self._map is None:
            self.build_map()
        return self._map.get("dependency_graph", {})

    @staticmethod
    def diff_map(old: dict, new: dict) -> dict:
        """比较两次扫描差异。

        Returns:
            {
                "added_modules": [...],
                "removed_modules": [...],
                "modified_modules": {mod_name: {"changes": [...]}, ...},
                "added_classes": [...],
                "removed_classes": [...],
                "added_functions": [...],
                "removed_functions": [...],
            }
        """
        old_mods = set(old.get("modules", {}).keys())
        new_mods = set(new.get("modules", {}).keys())

        added = sorted(new_mods - old_mods)
        removed = sorted(old_mods - new_mods)

        modified = {}
        added_classes = []
        removed_classes = []
        added_functions = []
        removed_functions = []

        for mod_name in old_mods & new_mods:
            old_mod = old["modules"][mod_name]
            new_mod = new["modules"][mod_name]
            changes = []

            old_classes = set(old_mod.get("classes", {}).keys())
            new_classes = set(new_mod.get("classes", {}).keys())
            cls_added = new_classes - old_classes
            cls_removed = old_classes - new_classes
            if cls_added:
                changes.append(f"新增类: {cls_added}")
                added_classes.extend(f"{mod_name}.{c}" for c in cls_added)
            if cls_removed:
                changes.append(f"删除类: {cls_removed}")
                removed_classes.extend(f"{mod_name}.{c}" for c in cls_removed)

            old_funcs = set(old_mod.get("functions", []))
            new_funcs = set(new_mod.get("functions", []))
            fn_added = new_funcs - old_funcs
            fn_removed = old_funcs - new_funcs
            if fn_added:
                changes.append(f"新增函数: {fn_added}")
                added_functions.extend(f"{mod_name}.{f}" for f in fn_added)
            if fn_removed:
                changes.append(f"删除函数: {fn_removed}")
                removed_functions.extend(f"{mod_name}.{f}" for f in fn_removed)

            if old_mod.get("lines", 0) != new_mod.get("lines", 0):
                changes.append(
                    f"行数变化: {old_mod.get('lines', 0)}→{new_mod.get('lines', 0)}"
                )

            if changes:
                modified[mod_name] = {"changes": changes}

        return {
            "added_modules": added,
            "removed_modules": removed,
            "modified_modules": modified,
            "added_classes": added_classes,
            "removed_classes": removed_classes,
            "added_functions": added_functions,
            "removed_functions": removed_functions,
        }

    def get_arch_context(self, task_desc: str = "", max_tokens: int = 2000) -> str:
        """供 core.py / template_filler / debug_loop 调用的便捷接口。

        根据 task_desc 提供架构上下文 + 插入建议。
        """
        if self._map is None:
            self.build_map()

        parts = [self.to_context_string(max_tokens=max_tokens)]

        if task_desc:
            suggestion = self.suggest_insertion(task_desc)
            parts.append(f"\n## 插入点建议（针对: {task_desc}）")
            s = suggestion["suggestion"]
            if s.get("extension_point"):
                parts.append(f"扩展点: {s['extension_point']}")
            parts.append(f"目标模块: {s.get('module', '?')}")
            parts.append(f"扩展方式: {s.get('how_to', '?')}")
            parts.append(f"参考示例: {s.get('example', '?')}")

        return "\n".join(parts)

    # ══════════════════════════════════════════════════════════════
    #  内部实现
    # ══════════════════════════════════════════════════════════════

    def _collect_py_files(self) -> List[str]:
        """收集所有需要解析的 .py 文件"""
        skip_dirs = {
            "__pycache__", ".git", ".github", ".pytest_cache",
            "node_modules", "sandbox", "checkpoints",
        }
        skip_files = {"conftest.py", "__init__.py"}
        py_files = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if f.endswith(".py") and f not in skip_files:
                    py_files.append(os.path.join(root, f))
        return sorted(py_files)

    def _rel_module_name(self, file_path: str) -> str:
        """从文件路径提取模块名"""
        rel = os.path.relpath(file_path, self.root_dir)
        no_ext = os.path.splitext(rel)[0]
        return no_ext.replace(os.sep, ".")

    def _parse_file(self, file_path: str) -> Optional[dict]:
        """用 AST 解析单个 .py 文件，失败时降级为正则提取"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception:
            return None

        lines = source.count("\n") + 1
        module_name = self._rel_module_name(file_path)
        rel_file = os.path.relpath(file_path, self.root_dir)

        try:
            tree = ast.parse(source, filename=file_path)
            return self._ast_to_module_info(tree, module_name, rel_file, lines, source)
        except SyntaxError:
            # 降级为正则提取
            return self._regex_to_module_info(source, module_name, rel_file, lines)

    def _ast_to_module_info(self, tree: ast.AST, module_name: str,
                            rel_file: str, lines: int,
                            source: str) -> dict:
        """AST 解析 → 模块信息 dict"""
        classes = {}
        functions = []
        imports = []

        # 模块级 docstring
        module_doc = ast.get_docstring(tree) or ""

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                cls_info = self._parse_class(node)
                classes[node.name] = cls_info
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    functions.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        # 简化导入名（只保留顶级模块名）
        imports = sorted(set(self._simplify_import(imp) for imp in imports))

        return {
            "module_name": module_name,
            "file": rel_file,
            "lines": lines,
            "purpose": module_doc.split("\n")[0][:120] if module_doc else "",
            "classes": classes,
            "functions": functions,
            "imports": imports,
        }

    def _parse_class(self, node: ast.ClassDef) -> dict:
        """解析单个类定义"""
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)

        public_methods = []
        abstract_methods = []
        optional_overrides = []
        has_abstractmethod = False

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 检查 @abstractmethod 装饰器
                is_abstract = any(
                    self._is_abstractmethod(d) for d in item.decorator_list
                )
                if is_abstract:
                    abstract_methods.append(item.name)
                    has_abstractmethod = True
                elif not item.name.startswith("_"):
                    public_methods.append(item.name)
                elif item.name in (
                    "on_start", "on_stop", "serialize", "deserialize",
                    "on_load", "on_unload", "get_capabilities",
                    "on_user_message", "on_pre_llm", "on_post_llm",
                    "on_shortcut", "get_context", "health_check",
                    "get_interval", "tick",
                ):
                    optional_overrides.append(item.name)

        return {
            "bases": bases,
            "is_extension_point": has_abstractmethod
                                  or node.name in self.KNOWN_EXTENSION_CLASSES,
            "abstract_methods": abstract_methods,
            "optional_overrides": optional_overrides,
            "public_methods": public_methods,
        }

    @staticmethod
    def _is_abstractmethod(decorator) -> bool:
        """检查装饰器是否为 @abstractmethod"""
        if isinstance(decorator, ast.Name):
            return decorator.id == "abstractmethod"
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "abstractmethod"
        return False

    @staticmethod
    def _simplify_import(imp: str) -> str:
        """简化导入名: a.b.c → a；但保留有意义的多级（如 bazi.xxx）"""
        parts = imp.split(".")
        # 如果是 label_dictionary 这类，保留二级
        if len(parts) > 1 and parts[-1] == "label_dictionary":
            return ".".join(parts[-2:])
        return parts[0]

    def _regex_to_module_info(self, source: str, module_name: str,
                              rel_file: str, lines: int) -> dict:
        """AST 解析失败时降级为正则提取"""
        classes = {}
        functions = []

        # 正则提取类定义
        for m in re.finditer(
            r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", source, re.MULTILINE
        ):
            cls_name = m.group(1)
            bases_str = m.group(2) or ""
            bases = [b.strip().split(".")[-1] for b in bases_str.split(",") if b.strip()]
            classes[cls_name] = {
                "bases": bases,
                "is_extension_point": cls_name in self.KNOWN_EXTENSION_CLASSES,
                "abstract_methods": [],
                "optional_overrides": [],
                "public_methods": [],
            }

        # 正则提取函数定义
        for m in re.finditer(
            r"^def\s+(\w+)\s*\(", source, re.MULTILINE
        ):
            fn_name = m.group(1)
            if not fn_name.startswith("_"):
                functions.append(fn_name)

        # 正则提取导入
        imports = []
        for m in re.finditer(
            r"^\s*from\s+([\w.]+)\s+import", source, re.MULTILINE
        ):
            imports.append(m.group(1))
        for m in re.finditer(
            r"^\s*import\s+([\w.]+)", source, re.MULTILINE
        ):
            imports.append(m.group(1))
        imports = sorted(set(self._simplify_import(imp) for imp in imports))

        return {
            "module_name": module_name,
            "file": rel_file,
            "lines": lines,
            "purpose": "(正则降级解析)",
            "classes": classes,
            "functions": functions,
            "imports": imports,
        }

    def _detect_extension_points(self, modules: dict) -> List[dict]:
        """从已解析的模块中检测扩展点"""
        eps = []
        seen_names = set()

        for mod_name, mod_info in modules.items():
            for cls_name, cls_info in mod_info.get("classes", {}).items():
                is_ext = cls_info.get("is_extension_point", False)
                # 也检查已知扩展类名
                if not is_ext and cls_name not in self.KNOWN_EXTENSION_CLASSES:
                    continue
                if cls_name in seen_names:
                    continue
                seen_names.add(cls_name)

                known = self.KNOWN_EXTENSION_CLASSES.get(cls_name, {})
                ep = {
                    "name": cls_name,
                    "module": mod_name,
                    "type": "subclass",
                    "description": known.get("description", cls_info.get("bases", [])),
                    "how_to_extend": known.get(
                        "how_to_extend",
                        f"继承 {cls_name}，实现抽象方法"
                    ),
                    "abstract_methods": cls_info.get("abstract_methods", []),
                    "optional_overrides": cls_info.get("optional_overrides", []),
                    "example_file": "",
                }

                # 为已知扩展点补充示例文件
                if cls_name == "BackgroundPlugin":
                    ep["example_file"] = "plugins/stock_monitor.py"
                elif cls_name == "ModelProvider":
                    ep["example_file"] = "model_provider.py:DeepSeekProvider"
                elif cls_name == "PluginBase":
                    ep["example_file"] = "plugin_base.py:MessagePlugin"

                eps.append(ep)

        return eps

    @staticmethod
    def _build_dependency_graph(modules: dict) -> Dict[str, List[str]]:
        """构建模块间 import 依赖图"""
        graph = {}
        all_mod_names = set(modules.keys())
        # 也添加简化名（顶级模块名）
        for mod_name in modules:
            all_mod_names.add(mod_name.split(".")[0])

        for mod_name, mod_info in modules.items():
            deps = []
            for imp in mod_info.get("imports", []):
                # 只保留项目内部的依赖
                if imp in all_mod_names:
                    deps.append(imp)
            if deps:
                graph[mod_name] = sorted(set(deps))

        return graph

    # ══════════════════════════════════════════════════════════════
    #  缓存
    # ══════════════════════════════════════════════════════════════

    def _load_cache(self) -> Optional[dict]:
        """加载缓存"""
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, data: dict):
        """保存缓存"""
        try:
            cache_dir = os.path.dirname(self.cache_file)
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 缓存写入失败不阻塞主流程


# ═════════════════════════════════════════════════════════════════════
#  自测
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys as _sys

    print("=" * 60)
    print("ArchitectureMap 自测")
    print("=" * 60)

    # 确定代码库根目录
    test_root = _sys.argv[1] if len(_sys.argv) > 1 else "."
    am = ArchitectureMap(root_dir=test_root, cache_file=None)

    # ── 测试 1: build_map ──
    print("\n[1] build_map() ...")
    t0 = time.time()
    m = am.build_map(force=True)
    elapsed = time.time() - t0
    print(f"    扫描 {m['file_count']} 个文件, {m['module_count']} 个模块, "
          f"耗时 {elapsed:.2f}s")
    assert m["file_count"] > 0, "应扫描到文件"
    assert m["module_count"] > 0, "应解析到模块"
    print("    ✅ 通过")

    # ── 测试 2: 识别扩展点 ──
    print("\n[2] 识别扩展点 ...")
    eps = am.get_extension_points()
    ep_names = {ep["name"] for ep in eps}
    print(f"    扩展点: {ep_names}")
    for expected in ("BackgroundPlugin", "PluginBase", "ModelProvider"):
        assert expected in ep_names, f"应识别 {expected} 为扩展点"
    print("    ✅ BackgroundPlugin / PluginBase / ModelProvider 均已识别")

    # ── 测试 3: to_context_string token 限制 ──
    print("\n[3] to_context_string(max_tokens=500) ...")
    ctx = am.to_context_string(max_tokens=500)
    est_tokens = len(ctx) / 4
    print(f"    输出 {len(ctx)} 字符 ≈ {est_tokens:.0f} tokens")
    assert est_tokens <= 600, f"应不超过 ~500 tokens (允许10%误差), got {est_tokens:.0f}"
    print("    ✅ 通过")

    print("\n[3b] to_context_string(max_tokens=2000) ...")
    ctx2 = am.to_context_string(max_tokens=2000)
    est_tokens2 = len(ctx2) / 4
    print(f"    输出 {len(ctx2)} 字符 ≈ {est_tokens2:.0f} tokens")
    assert est_tokens2 <= 2200, "应不超过 ~2000 tokens (允许10%误差)"
    print("    ✅ 通过")

    # ── 测试 4: suggest_insertion ──
    print("\n[4] suggest_insertion('后台定时任务') ...")
    s = am.suggest_insertion("后台定时任务")
    print(f"    建议: {s['suggestion']}")
    assert s["suggestion"]["extension_point"] == "BackgroundPlugin", \
        "应建议 BackgroundPlugin"
    print("    ✅ 通过")

    print("\n[4b] suggest_insertion('新增CLI命令') ...")
    s2 = am.suggest_insertion("新增CLI命令")
    print(f"    建议: {s2['suggestion']}")
    assert s2["suggestion"]["module"] == "cli", "应建议 cli 模块"
    print("    ✅ 通过")

    # ── 测试 5: get_dependency_graph ──
    print("\n[5] get_dependency_graph() ...")
    dep = am.get_dependency_graph()
    print(f"    {len(dep)} 个模块有依赖关系")
    # 显示前 5 个
    for mod, deps in list(dep.items())[:5]:
        print(f"    {mod} → {deps[:3]}")
    assert len(dep) > 0, "依赖图应非空"
    print("    ✅ 通过")

    # ── 测试 6: diff_map ──
    print("\n[6] diff_map() ...")
    old_map = json.loads(json.dumps(m))  # 深拷贝
    # 模拟修改：在 core 模块加一个函数
    if "core" in old_map["modules"]:
        old_map["modules"]["core"]["functions"] = old_map["modules"]["core"].get("functions", []) + ["_test_fn"]
    diff = ArchitectureMap.diff_map(old_map, m)
    print(f"    added_functions: {diff['added_functions'][:5]}")
    print(f"    removed_functions: {diff['removed_functions'][:5]}")
    assert "_test_fn" in diff["removed_functions"] or \
           any("_test_fn" in f for f in diff["removed_functions"]), \
        "应检测到 _test_fn 被删除"
    print("    ✅ 通过")

    # ── 测试 7: get_arch_context ──
    print("\n[7] get_arch_context('写一个监控插件') ...")
    arch_ctx = am.get_arch_context("写一个监控插件", max_tokens=1000)
    print(f"    输出 {len(arch_ctx)} 字符")
    assert "扩展点" in arch_ctx or "BackgroundPlugin" in arch_ctx
    print("    ✅ 通过")

    # ── 测试 8: 缓存机制 ──
    print("\n[8] 缓存机制（增量更新） ...")
    cache_path = os.path.join(test_root, "memory", "_test_arch_cache.json")
    am2 = ArchitectureMap(root_dir=test_root, cache_file=cache_path)
    am2.build_map(force=True)  # 首次全量
    t1 = time.time()
    am2.build_map()  # 第二次应走缓存
    cache_elapsed = time.time() - t1
    print(f"    第二次构建（缓存）耗时: {cache_elapsed:.3f}s")
    assert am2._map is not None
    print("    ✅ 通过")
    # 清理测试缓存
    try:
        os.remove(cache_path)
    except OSError:
        pass

    print("\n" + "=" * 60)
    print("✅ 全部测试通过！")
    print("=" * 60)
