"""
P0.26 Phase 2: 代码执行沙箱

在隔离的子进程中安全执行Python代码：
- subprocess子进程隔离（崩了不影响主程序）
- 超时限制（防止死循环）
- 内存限制 ulimit（防止吃光RAM，Unix only）
- 临时目录隔离（跑完即删）
- 危险导入拦截（import hook阻止os/subprocess/socket等）
- 静态危险模式检查（exec/eval/__import__等）
"""

import subprocess
import tempfile
import os
import sys
import re
import time
import shutil
import platform
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import platform_compat
from platform_compat import (
    IS_WINDOWS, IS_UNIX, get_sandbox_env, get_kill_exit_code,
    can_set_resource_limits, set_resource_limits, get_blocked_modules
)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool = False
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    execution_time: float = 0.0
    error_type: str = ""        # SyntaxError/RuntimeError/Timeout/SecurityBlock/None
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout[:2000],
            "stderr": self.stderr[:2000],
            "exit_code": self.exit_code,
            "execution_time": round(self.execution_time, 3),
            "error_type": self.error_type,
            "error_message": self.error_message[:500],
        }


# ─── 危险模式 ─────────────────────────────────

_DANGEROUS_PATTERNS = [
    (r'\bos\.system\s*\(',      "os.system()"),
    (r'\bos\.popen\s*\(',       "os.popen()"),
    (r'\bos\.exec\w*\s*\(',     "os.exec()"),
    (r'\bos\.spawn\w*\s*\(',    "os.spawn()"),
    (r'\bsubprocess\.\w+\s*\(', "subprocess调用"),
    (r'\b__import__\s*\(',      "__import__()"),
    (r'\beval\s*\(',            "eval()"),
    (r'\bexec\s*\(',            "exec()"),
    (r'\bcompile\s*\(',         "compile()"),
    (r'\bctypes\.\w+\s*\(',     "ctypes调用"),
]


class CodeExecutor:
    """代码执行沙箱"""

    def __init__(self, config: dict = None):
        config = config or {}
        self.timeout = config.get("timeout", 10)          # 秒
        self.memory_limit_mb = config.get("memory_limit_mb", 256)
        self.max_output = config.get("max_output", 10000)  # 字符
        # P0.61: 输出截断阈值（字节），默认 16KB
        self.max_output_bytes = config.get("max_output_bytes", 16384)
        self._exec_count = 0
        # P0.61: 可选的 narration emitter，用于发送 output_truncated 事件
        self._narration = None

    # ─── 公开接口 ──────────────────────────────

    def execute(self, code: str, timeout: int = None,
                input_data: str = None) -> ExecutionResult:
        """执行Python代码字符串

        Args:
            code: Python代码
            timeout: 超时秒数（覆盖默认）
            input_data: stdin输入

        Returns:
            ExecutionResult
        """
        timeout = timeout or self.timeout

        # 1. 静态危险检查
        danger = self._static_check(code)
        if danger:
            return ExecutionResult(
                success=False,
                error_type="SecurityBlock",
                error_message=f"危险操作被拦截: {danger}",
            )

        # 2. 创建临时工作目录
        self._exec_count += 1
        work_dir = tempfile.mkdtemp(prefix=f"zhile_sb_{self._exec_count}_")

        # 3. 写入安全包装后的代码
        code_file = os.path.join(work_dir, "_sandbox.py")
        safe_code = self._wrap_with_safety(code)
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(safe_code)

        # 4. 构建执行命令
        cmd = [sys.executable, "-B", code_file]
        env = self._create_sandbox_env(work_dir)

        # 5. 执行
        result = ExecutionResult()
        t0 = time.time()

        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.PIPE if input_data else subprocess.DEVNULL,
            "cwd": work_dir,
            "env": env,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if IS_UNIX:
            popen_kwargs["preexec_fn"] = self._set_limits

        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)

            try:
                stdout, stderr = proc.communicate(
                    input=input_data, timeout=timeout
                )
                # P0.61: 独立截断 stdout/stderr
                result.stdout = self._truncate_output(
                    stdout[:self.max_output], "stdout"
                )
                result.stderr = self._truncate_output(
                    stderr[:self.max_output], "stderr"
                )
                result.exit_code = proc.returncode
                result.success = (proc.returncode == 0)

                if not result.success and stderr:
                    result.error_type, result.error_message = \
                        self._parse_error(stderr)

            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                result.error_type = "Timeout"
                result.error_message = f"执行超时（{timeout}秒）"
                result.exit_code = get_kill_exit_code()

        except Exception as e:
            result.error_type = "SandboxError"
            result.error_message = str(e)

        finally:
            result.execution_time = round(time.time() - t0, 3)
            # 清理临时目录
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

        return result

    def execute_function(self, func_code: str, func_name: str,
                         args: list = None, kwargs: dict = None,
                         timeout: int = None) -> ExecutionResult:
        """执行指定函数并捕获返回值

        Args:
            func_code: 包含函数定义的代码
            func_name: 要调用的函数名
            args: 位置参数
            kwargs: 关键字参数
            timeout: 超时秒数

        Returns:
            ExecutionResult（stdout为函数返回值的JSON表示）
        """
        import json as _json
        args_json = _json.dumps(args or [], ensure_ascii=False)
        kwargs_json = _json.dumps(kwargs or {}, ensure_ascii=False)

        wrapper = f"""
{func_code}

import json as _json, sys as _sys
try:
    _args = _json.loads(_sys.argv[1])
    _kwargs = _json.loads(_sys.argv[2])
    _result = {func_name}(*_args, **_kwargs)
    print("__SANDBOX_RESULT__")
    print(_json.dumps({{"result": _result}}, default=str, ensure_ascii=False))
except Exception as e:
    print("__SANDBOX_ERROR__")
    print(_json.dumps({{"error": str(e), "type": type(e).__name__}}, ensure_ascii=False))
"""
        result = self.execute(wrapper, timeout=timeout)

        # 解析特殊输出标记
        if "__SANDBOX_RESULT__" in result.stdout:
            lines = result.stdout.split("\n")
            idx = lines.index("__SANDBOX_RESULT__")
            if idx + 1 < len(lines):
                try:
                    data = _json.loads(lines[idx + 1])
                    result.stdout = str(data.get("result", ""))
                    result.success = True
                    result.error_type = ""
                    result.error_message = ""
                except _json.JSONDecodeError:
                    pass
        elif "__SANDBOX_ERROR__" in result.stdout:
            lines = result.stdout.split("\n")
            idx = lines.index("__SANDBOX_ERROR__")
            if idx + 1 < len(lines):
                try:
                    data = _json.loads(lines[idx + 1])
                    result.error_type = data.get("type", "RuntimeError")
                    result.error_message = data.get("error", "")
                    result.success = False
                except _json.JSONDecodeError:
                    pass

        return result

    def get_stats(self) -> dict:
        return {
            "enabled": True,
            "timeout": self.timeout,
            "memory_limit_mb": self.memory_limit_mb,
            "total_executions": self._exec_count,
            "platform": platform_compat.PLATFORM_NAME,
        }

    # ─── 内部方法 ──────────────────────────────

    def _truncate_output(self, text: str, stream: str) -> str:
        """P0.61: 截断输出到 max_output_bytes 字节

        对 stdout 和 stderr 各自独立截断。截断后在末尾追加提示信息。
        如果未超过阈值，原样返回。

        Args:
            text: 原始输出文本
            stream: 输出流名称 (stdout/stderr)

        Returns:
            截断后的文本（可能包含截断提示）
        """
        original_bytes = len(text.encode("utf-8"))
        if original_bytes <= self.max_output_bytes:
            return text

        # 截断到 max_output_bytes 字节
        truncated_text = text.encode("utf-8")[:self.max_output_bytes].decode("utf-8", errors="ignore")
        truncated_bytes = original_bytes - self.max_output_bytes

        # 追加截断提示
        notice = (
            f"\n[输出被截断，原始长度: {original_bytes} 字节，"
            f"已截断 {truncated_bytes} 字节]"
        )
        result = truncated_text + notice

        # 发送 output_truncated narration event
        if self._narration:
            try:
                self._narration.emit_output_truncated(
                    stream=stream,
                    original_bytes=original_bytes,
                    truncated_bytes=truncated_bytes,
                )
            except Exception:
                pass

        return result

    def _static_check(self, code: str) -> str:
        """静态检查危险模式，返回危险描述或空字符串"""
        for pattern, name in _DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                return name
        return ""

    def _wrap_with_safety(self, code: str) -> str:
        """在用户代码前注入安全限制（import hook）"""
        blocked_repr = repr(get_blocked_modules())
        wrapper = f'''#!/usr/bin/env python3
# ─── 沙箱安全层 ───
import sys as _sys

class _SandboxImporter:
    """拦截危险模块导入"""
    BLOCKED = {blocked_repr}

    def find_module(self, name, path=None):
        top = name.split(".")[0]
        if top in self.BLOCKED:
            return self
        return None

    def load_module(self, name):
        raise ImportError(f"沙箱禁止导入模块: {name}")

_sys.meta_path.insert(0, _SandboxImporter())

# 替换内置 __import__
_builtins = _sys.modules['builtins']
_real_import = _builtins.__import__

def _safe_import(name, *args, **kwargs):
    top = name.split(".")[0]
    if top in _SandboxImporter.BLOCKED:
        raise ImportError(f"沙箱禁止导入模块: {name}")
    return _real_import(name, *args, **kwargs)

_builtins.__import__ = _safe_import

# ─── 用户代码开始 ───
'''
        return wrapper + "\n" + code

    def _create_sandbox_env(self, work_dir: str) -> dict:
        """创建沙箱环境变量（委托给平台兼容层）"""
        return get_sandbox_env(work_dir)

    def _set_limits(self):
        """在子进程中设置资源限制（委托给平台兼容层，Unix only）"""
        set_resource_limits(self.memory_limit_mb, self.timeout + 2)

    def _parse_error(self, stderr: str) -> tuple:
        """从stderr解析错误类型和消息"""
        lines = stderr.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if "Error" in line or "Exception" in line:
                if ":" in line:
                    parts = line.split(":", 1)
                    error_type = parts[0].strip()
                    # 去掉模块前缀
                    if "." in error_type:
                        error_type = error_type.split(".")[-1]
                    error_message = parts[1].strip()
                    return error_type, error_message
                return line, ""
        return "RuntimeError", stderr[-200:] if stderr else ""
