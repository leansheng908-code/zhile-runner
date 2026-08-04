#!/usr/bin/env python3
"""
P0.46④ 写后自检 — 文件写入后自动语法检查

在 core.py 的文件操作之后自动执行语法检查，确保写入的文件格式正确。
支持 Python、JSON、YAML、XML 四种格式的语法验证，并提供批量检查和
回调集成接口。

核心类：
  - PostWriteLinter: 主检查器，提供 lint_file / lint_after_write / batch_lint
  - LintResult: 检查结果数据类

使用方式（集成到 core.py）：
    linter = PostWriteLinter()
    # 方式1：直接在写文件后调用
    result = linter.lint_after_write(filepath, content)
    if not result.success:
        print(result.errors)
    # 方式2：注册回调（在 core.py 的文件写入方法中调用）
    linter.register_callback(my_callback)
"""

import json
import os
import py_compile
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


# ─── 尝试导入 yaml（可选依赖） ──────────────────────────

try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ─── 数据类 ──────────────────────────────────────────────

@dataclass
class LintResult:
    """文件检查结果。

    Attributes:
        success: 检查是否通过（无错误）。
        errors: 错误信息列表。
        warnings: 警告信息列表。
        filepath: 被检查的文件路径。
        file_type: 文件类型（扩展名）。
    """

    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    filepath: str = ""
    file_type: str = ""

    def add_error(self, message: str) -> None:
        """添加一条错误信息并标记为失败。"""
        self.errors.append(message)
        self.success = False

    def add_warning(self, message: str) -> None:
        """添加一条警告信息（不影响 success 状态）。"""
        self.warnings.append(message)

    def __str__(self) -> str:
        """格式化输出检查结果。"""
        status = "✅ PASS" if self.success else "❌ FAIL"
        lines = [f"[{status}] {self.filepath} ({self.file_type})"]
        for err in self.errors:
            lines.append(f"  ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"  WARN:  {warn}")
        return "\n".join(lines)


# ─── 检查器 ──────────────────────────────────────────────

# 支持的文件类型与对应检查器的映射
_LINTERS: Dict[str, str] = {
    ".py": "python",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
}


class PostWriteLinter:
    """写后自检器。

    在文件写入后自动执行语法检查，支持 Python、JSON、YAML、XML 格式。
    可通过回调函数集成到 core.py 的文件操作流程中。

    Attributes:
        callbacks: 注册的回调函数列表。
        linted_files: 已检查过的文件集合（避免重复检查）。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化写后自检器。

        Args:
            config: 可选配置字典。支持以下键：
                - skip_dirs: 跳过的目录名列表（默认 ["__pycache__", ".git"]）
                - max_file_size: 最大检查文件大小（字节，默认 1MB）
                - check_on_write: 是否在写入时自动检查（默认 True）
        """
        config = config or {}
        self.skip_dirs: Set[str] = set(
            config.get("skip_dirs", ["__pycache__", ".git", "node_modules"])
        )
        self.max_file_size: int = config.get("max_file_size", 1024 * 1024)
        self.check_on_write: bool = config.get("check_on_write", True)

        self.callbacks: List[Callable[[LintResult], None]] = []
        self.linted_files: Set[str] = set()

    # ─── 单文件检查 ────────────────────────────────────────

    def lint_file(self, filepath: str) -> LintResult:
        """根据文件扩展名自动检查语法。

        根据文件扩展名选择对应的检查器：
          - .py:   使用 py_compile 检查 Python 语法
          - .json: 使用 json.loads 检查 JSON 格式
          - .yaml/.yml: 使用 yaml.safe_load 检查 YAML 格式
          - .xml:  使用 xml.etree.ElementTree 检查 XML 格式

        对于不支持的扩展名，返回 success=True 且附带一条警告。

        Args:
            filepath: 要检查的文件路径。

        Returns:
            LintResult 检查结果对象。
        """
        path = Path(filepath)
        ext = path.suffix.lower()
        result = LintResult(filepath=str(filepath), file_type=ext)

        # 文件不存在
        if not path.exists():
            result.add_error(f"文件不存在: {filepath}")
            return result

        # 文件过大
        try:
            file_size = path.stat().st_size
            if file_size > self.max_file_size:
                result.add_warning(
                    f"文件过大（{file_size} bytes），跳过检查"
                )
                return result
        except OSError as e:
            result.add_error(f"无法读取文件信息: {e}")
            return result

        # 根据扩展名分派
        linter_type = _LINTERS.get(ext)
        if linter_type is None:
            # 不支持的文件类型，不报错
            result.add_warning(f"不支持的文件类型: {ext}，跳过检查")
            return result

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # 可能是二进制文件
            result.add_warning("文件非文本格式，跳过检查")
            return result
        except OSError as e:
            result.add_error(f"读取文件失败: {e}")
            return result

        # 执行对应检查
        if linter_type == "python":
            self._lint_python(filepath, content, result)
        elif linter_type == "json":
            self._lint_json(content, result)
        elif linter_type == "yaml":
            self._lint_yaml(content, result)
        elif linter_type == "xml":
            self._lint_xml(content, result)

        return result

    def _lint_python(
        self, filepath: str, content: str, result: LintResult
    ) -> None:
        """检查 Python 文件语法。

        使用 py_compile 编译文件以检测语法错误。

        Args:
            filepath: 文件路径。
            content: 文件内容。
            result: 检查结果对象（原地修改）。
        """
        try:
            py_compile.compile(filepath, doraise=True)
        except py_compile.PyCompileError as e:
            result.add_error(f"Python 语法错误: {e}")
        except OSError as e:
            result.add_error(f"文件操作失败: {e}")

    def _lint_json(self, content: str, result: LintResult) -> None:
        """检查 JSON 文件格式。

        Args:
            content: 文件内容。
            result: 检查结果对象（原地修改）。
        """
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            result.add_error(f"JSON 解析错误 (行 {e.lineno}, 列 {e.colno}): {e.msg}")

    def _lint_yaml(self, content: str, result: LintResult) -> None:
        """检查 YAML 文件格式。

        Args:
            content: 文件内容。
            result: 检查结果对象（原地修改）。
        """
        if not _YAML_AVAILABLE:
            result.add_warning("PyYAML 未安装，跳过 YAML 检查")
            return
        try:
            yaml.safe_load(content)  # type: ignore
        except yaml.YAMLError as e:  # type: ignore
            result.add_error(f"YAML 解析错误: {e}")

    def _lint_xml(self, content: str, result: LintResult) -> None:
        """检查 XML 文件格式。

        Args:
            content: 文件内容。
            result: 检查结果对象（原地修改）。
        """
        try:
            ET.fromstring(content)
        except ET.ParseError as e:
            result.add_error(f"XML 解析错误: {e}")

    # ─── 写后检查 ──────────────────────────────────────────

    def lint_after_write(
        self, filepath: str, content: Optional[str] = None
    ) -> LintResult:
        """写入文件后立即检查语法。

        先将内容写入临时文件（如果提供了 content），然后执行语法检查。
        如果未提供 content，则直接检查已存在的文件。

        此方法适合在 core.py 的文件写入操作之后调用。

        Args:
            filepath: 目标文件路径。
            content: 写入的内容。若为 None 则直接检查 filepath 指向的文件。

        Returns:
            LintResult 检查结果对象。
        """
        if content is not None:
            # 将内容写入文件后检查
            try:
                path = Path(filepath)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            except OSError as e:
                result = LintResult(
                    success=False,
                    filepath=str(filepath),
                    file_type=Path(filepath).suffix.lower(),
                )
                result.add_error(f"写入文件失败: {e}")
                self._notify_callbacks(result)
                return result

        result = self.lint_file(filepath)
        self.linted_files.add(str(filepath))
        self._notify_callbacks(result)
        return result

    # ─── 批量检查 ──────────────────────────────────────────

    def batch_lint(
        self, directory: str, recursive: bool = True
    ) -> List[LintResult]:
        """批量检查目录下所有支持的文件。

        遍历目录下所有文件，对支持的文件类型执行语法检查。

        Args:
            directory: 要检查的目录路径。
            recursive: 是否递归检查子目录，默认为 True。

        Returns:
            所有文件的检查结果列表。
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            return [
                LintResult(
                    success=False,
                    filepath=str(directory),
                    file_type="dir",
                    errors=[f"目录不存在: {directory}"],
                )
            ]

        results: List[LintResult] = []

        if recursive:
            walker = dir_path.rglob("*")
        else:
            walker = dir_path.iterdir()

        for item in walker:
            # 跳过目录
            if item.is_dir():
                # 检查是否在跳过列表中
                if item.name in self.skip_dirs:
                    # rglob 不会自动跳过子目录，我们通过检查路径来过滤
                    continue
                continue

            # 跳过不支持的文件类型
            ext = item.suffix.lower()
            if ext not in _LINTERS:
                continue

            # 跳过被排除目录中的文件
            try:
                rel_parts = item.relative_to(dir_path).parts
            except ValueError:
                continue
            if any(part in self.skip_dirs for part in rel_parts[:-1]):
                continue

            result = self.lint_file(str(item))
            results.append(result)

        return results

    # ─── 回调集成 ──────────────────────────────────────────

    def register_callback(
        self, callback: Callable[[LintResult], None]
    ) -> None:
        """注册检查结果回调函数。

        每次 lint_after_write 执行后，会调用所有已注册的回调函数，
        传入 LintResult 对象。适合在 core.py 中注册日志记录或
        错误处理回调。

        Args:
            callback: 回调函数，接收一个 LintResult 参数。
        """
        self.callbacks.append(callback)

    def unregister_callback(
        self, callback: Callable[[LintResult], None]
    ) -> None:
        """取消注册回调函数。

        Args:
            callback: 要移除的回调函数。
        """
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def _notify_callbacks(self, result: LintResult) -> None:
        """通知所有已注册的回调函数。

        Args:
            result: 检查结果。
        """
        for callback in self.callbacks:
            try:
                callback(result)
            except Exception as e:
                # 回调中的异常不应影响主流程
                print(f"[PostWriteLinter] 回调执行失败: {e}")

    # ─── 便捷方法 ──────────────────────────────────────────

    def get_callback(self) -> Callable[[str, Optional[str]], LintResult]:
        """获取一个可直接传入 core.py 的回调函数。

        返回的函数签名为 (filepath, content=None) -> LintResult，
        内部调用 lint_after_write。适合作为 core.py 文件写入后的钩子。

        Returns:
            可作为回调使用的函数。
        """
        def _callback(
            filepath: str, content: Optional[str] = None
        ) -> LintResult:
            return self.lint_after_write(filepath, content)

        return _callback

    @staticmethod
    def summarize_results(results: List[LintResult]) -> Dict[str, Any]:
        """汇总批量检查结果。

        Args:
            results: 检查结果列表。

        Returns:
            汇总信息字典，包含总数、通过数、失败数、警告数。
        """
        total = len(results)
        passed = sum(1 for r in results if r.success and not r.warnings)
        warned = sum(1 for r in results if r.success and r.warnings)
        failed = sum(1 for r in results if not r.success)
        return {
            "total": total,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "errors": [r.errors for r in results if not r.success],
        }
