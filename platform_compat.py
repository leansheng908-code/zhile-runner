#!/usr/bin/env python3
"""
平台兼容层 — 统一处理 Windows/Linux 差异
所有平台相关逻辑集中在此，其他模块通过 import platform_compat 获取适配。
"""

import os
import sys
import platform

# ─── 平台检测 ──────────────────────────────

IS_WINDOWS = platform.system() == "Windows"
IS_UNIX = not IS_WINDOWS
PLATFORM_NAME = "Windows" if IS_WINDOWS else "Linux"


def get_default_path() -> str:
    """获取当前平台的安全 PATH"""
    if IS_WINDOWS:
        # Windows: 保留系统PATH，补充Python目录
        python_dir = os.path.dirname(sys.executable)
        return os.environ.get("PATH", "") + os.pathsep + python_dir
    else:
        return os.environ.get("PATH", "/usr/bin:/usr/local/bin")


def get_sandbox_env(work_dir: str) -> dict:
    """构建沙箱环境变量（平台适配版）"""
    tmp_dir = os.path.join(work_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    env = {
        "PATH": get_default_path(),
        "HOME": work_dir,
        "TMPDIR": tmp_dir,
        "PYTHONPATH": work_dir,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }

    if IS_WINDOWS:
        # Windows 专属环境变量
        env["TEMP"] = tmp_dir
        env["TMP"] = tmp_dir
        env["USERPROFILE"] = work_dir
        env["APPDATA"] = tmp_dir
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    else:
        # Unix 专属环境变量
        env["LANG"] = "en_US.UTF-8"
        env["LC_ALL"] = "en_US.UTF-8"

    return env


def get_kill_exit_code() -> int:
    """获取进程被kill后的退出码"""
    if IS_UNIX:
        import signal
        return -signal.SIGKILL
    return -1


def can_set_resource_limits() -> bool:
    """当前平台是否支持资源限制（ulimit）"""
    return IS_UNIX


def set_resource_limits(memory_mb: int, cpu_seconds: int):
    """
    在子进程中设置资源限制（仅Unix有效）
    作为 preexec_fn 回调使用
    """
    if not IS_UNIX:
        return
    try:
        import resource
        mem_bytes = memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except (ValueError, OSError):
            pass
    except ImportError:
        pass


def get_temp_prefix() -> str:
    """获取临时文件前缀"""
    return "zhile_sb_"


def get_blocked_modules() -> set:
    """获取沙箱禁止导入的模块列表"""
    blocked = {"os", "subprocess", "shutil", "ctypes", "multiprocessing",
               "socket", "http", "urllib", "requests", "importlib",
               "signal", "glob", "pathlib", "builtins", "sys"}
    if IS_UNIX:
        blocked.update({"resource", "fcntl"})
    return blocked


def supports_qq_mode() -> bool:
    """当前平台是否支持QQ模式（需要NapCat）"""
    # 两个平台都可以支持QQ模式，但需要NapCat单独安装
    # 此函数仅表示平台层面是否可能支持
    return True


def get_recommended_modes() -> list:
    """获取当前平台推荐的模式列表"""
    if IS_WINDOWS:
        return ["cli"]  # Windows默认只推荐CLI，QQ需要额外配置NapCat
    return ["cli", "qq"]


def platform_info() -> dict:
    """返回当前平台信息摘要"""
    return {
        "platform": PLATFORM_NAME,
        "is_windows": IS_WINDOWS,
        "is_unix": IS_UNIX,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "supports_resource_limits": can_set_resource_limits(),
        "recommended_modes": get_recommended_modes(),
    }
