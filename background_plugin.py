#!/usr/bin/env python3
"""
P0.35 Phase 1 — 后台插件基类与插件管理器

提供可扩展的后台插件框架：
  - BackgroundPlugin(ABC): 抽象基类，子类实现tick()和get_interval()
  - PluginManager: 注册/注销/启动/停止插件，从config.json读取启用列表

设计原则：
  - 每个插件运行在独立的daemon线程中，互不影响
  - 插件崩溃不会影响其他插件或主进程
  - 知乐可以自己写新插件继承BackgroundPlugin，无需修改框架代码
  - 从config.json的plugins段读取启用列表

用法:
    manager = PluginManager()

    class MyMonitor(BackgroundPlugin):
        NAME = "my_monitor"
        def get_interval(self):
            return 60  # 每60秒执行一次
        def tick(self):
            print("检查中...")

    manager.register(MyMonitor())
    manager.start_all()

参考: plugins/stock_monitor.py（独立脚本，非BackgroundPlugin子类）
      background_manager.py（通道无关后台任务管理器）
      plugin_base.py（插件基类体系）
"""

import os
import json
import time
import threading
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Callable


class BackgroundPlugin(ABC):
    """
    后台插件抽象基类

    子类必须实现:
        - tick(): 每次循环执行的逻辑
        - get_interval(): 返回循环间隔秒数

    子类可选覆盖:
        - on_load(): 加载时初始化（兼容PluginManager调用）
        - on_start(): 启动时初始化
        - on_stop(): 停止时清理
        - NAME: 插件名称（类属性）
        - DESCRIPTION: 插件描述（类属性）

    示例:
        class StockAlertPlugin(BackgroundPlugin):
            NAME = "stock_alert"
            DESCRIPTION = "股票价格告警"

            def get_interval(self):
                return 1800  # 30分钟

            def tick(self):
                # 检查股价并发送告警
                pass
    """

    NAME: str = ""
    DESCRIPTION: str = ""
    VERSION: str = "1.0"

    def __init__(self, config: Optional[dict] = None, core=None):
        """
        初始化后台插件

        Args:
            config: 插件配置字典
            core: 核心引擎引用（可选，供插件访问运行器能力）
        """
        self.config = config or {}
        self.core = core
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._error_count = 0  # 连续错误计数（成功时重置）
        self._max_errors = 10  # 连续出错上限（向后兼容）
        self._crash_count = 0  # 总崩溃次数（不重置，用于熔断器）
        self._circuit_disabled = False  # 熔断器是否已触发禁用
        self._tick_timeout = self.config.get("tick_timeout", 30)  # tick()超时秒数
        self._last_tick_time: Optional[datetime] = None
        self._tick_count = 0
        self._output_callback: Optional[Callable[[str], None]] = None
        # 熔断器退避时间表：第1次→立即重试，第2次→30s，第3次→60s，第4+次→300s
        self._BACKOFF_TIMES = [0, 0, 30, 60, 300]
        self._CRASH_DISABLE_THRESHOLD = 5  # 连续崩溃5次后禁用
        self.enabled = True  # 兼容 PluginManager 访问 .enabled

    def set_output_callback(self, callback: Callable[[str], None]):
        """设置输出通道回调，插件可通过 send_output() 发送消息"""
        self._output_callback = callback

    def send_output(self, message: str) -> bool:
        """通过输出通道发送消息，返回是否成功"""
        if self._output_callback:
            try:
                self._output_callback(message)
                return True
            except Exception as e:
                print(f"  ⚠ 插件 {self.name} 输出失败: {e}")
        return False

    @property
    def name(self) -> str:
        """插件名称"""
        return self.NAME or self.__class__.__name__

    @abstractmethod
    def tick(self):
        """
        每次循环执行的逻辑（子类必须实现）

        在独立线程中被周期性调用，异常会被捕获不会导致线程退出。
        """
        ...

    @abstractmethod
    def get_interval(self) -> float:
        """
        返回循环间隔秒数（子类必须实现）

        Returns:
            float: 两次tick()之间的间隔秒数
        """
        ...

    def on_load(self):
        """插件加载时调用（兼容PluginManager），可覆盖做初始化"""
        pass

    def on_start(self):
        """插件启动时调用，可覆盖做初始化"""
        pass

    def on_stop(self):
        """插件停止时调用，可覆盖做清理"""
        pass

    # ─── 状态序列化（热重载时保留状态） ──────────

    def serialize(self) -> dict:
        """返回可序列化的状态数据，子类可覆盖以支持热重载状态保持。

        示例:
            def serialize(self):
                return {"alerted_today": self._alerted_today}
        """
        return {}

    def deserialize(self, state: dict):
        """从序列化数据恢复状态，子类可覆盖。

        Args:
            state: serialize()返回的字典
        """
        pass

    def start(self):
        """启动后台循环（daemon线程）"""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._error_count = 0

        # 调用子类初始化
        try:
            self.on_start()
        except Exception as e:
            print(f"  ⚠ 插件 {self.name} on_start 异常: {e}")

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"bg-plugin-{self.name}",
        )
        self._thread.start()
        print(f"  ▶ 后台插件 '{self.name}' 已启动 (间隔 {self.get_interval()}s)")

    def stop(self):
        """停止后台循环（协作式停机 + 强杀兜底）"""
        if not self.is_running:
            return
        self.is_running = False
        self._stop_event.set()

        # 调用子类清理
        try:
            self.on_stop()
        except Exception as e:
            print(f"  ⚠ 插件 {self.name} on_stop 异常: {e}")

        # 协作式停机：等待线程退出
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            # 如果5秒后仍未退出，强制终止
            if self._thread.is_alive():
                self._force_kill_thread()

        print(f"  ⏹ 后台插件 '{self.name}' 已停止")

    def _force_kill_thread(self):
        """强制终止线程（最后手段，使用ctypes注入异常）"""
        if not self._thread or not self._thread.is_alive():
            return
        try:
            import ctypes
            tid = ctypes.c_long(self._thread.ident)
            exc = ctypes.py_object(SystemExit)
            # 连续注入2次提高成功率
            for _ in range(2):
                ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, exc)
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                print(f"  ⚠ 插件 {self.name} 强杀后线程仍存活（daemon线程，随进程退出）")
            else:
                print(f"  ⚡ 插件 {self.name} 已强制终止")
        except Exception as e:
            print(f"  ⚠ 插件 {self.name} 强杀失败: {e}（daemon线程，随进程退出）")

    def _run_loop(self):
        """后台线程主循环（熔断器 + tick超时保护）"""
        while not self._stop_event.is_set():
            # 熔断器检查
            if self._circuit_disabled:
                break

            interval = self.get_interval()

            # 等待间隔或停止信号（Event.wait替代sleep，秒级响应停止）
            if self._stop_event.wait(interval):
                break

            if not self.is_running:
                break

            # 执行tick（带超时保护）
            self._tick_with_timeout()

    def _tick_with_timeout(self):
        """执行tick()，带超时保护和熔断器"""
        tick_done = threading.Event()
        tick_error = [None]

        def _safe_tick():
            try:
                self.tick()
            except Exception as e:
                tick_error[0] = e
            finally:
                tick_done.set()

        t = threading.Thread(target=_safe_tick, daemon=True, name=f"tick-{self.name}")
        t.start()

        # 轮询等待tick完成或超时，同时响应停止信号
        deadline = time.monotonic() + self._tick_timeout
        while not tick_done.is_set():
            if self._stop_event.is_set():
                return  # 收到停止信号，放弃等待
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # tick超时
                self._handle_crash(f"tick超时({self._tick_timeout}s)")
                return
            tick_done.wait(timeout=min(0.5, remaining))

        if tick_error[0] is not None:
            self._handle_crash(str(tick_error[0]))
        else:
            # 成功
            self._tick_count += 1
            self._last_tick_time = datetime.now()
            self._error_count = 0  # 重置连续错误

    def _handle_crash(self, reason: str):
        """处理插件崩溃（熔断器逻辑）"""
        self._error_count += 1
        self._crash_count += 1
        print(f"  ⚠ 插件 {self.name} 崩溃 #{self._crash_count} ({reason})")

        # 达到禁用阈值
        if self._crash_count >= self._CRASH_DISABLE_THRESHOLD:
            print(f"  ✖ 插件 {self.name} 连续崩溃{self._crash_count}次，熔断器触发，自动禁用")
            self._circuit_disabled = True
            self.is_running = False
            # 通知用户
            if self._output_callback:
                try:
                    self._output_callback(
                        f"⚠ 后台插件 '{self.name}' 连续崩溃{self._crash_count}次已自动禁用，"
                        f"最近原因: {reason}。可用 /bgplugin reload {self.name} 重试"
                    )
                except Exception:
                    pass
            return

        # 退避等待
        idx = min(self._crash_count - 1, len(self._BACKOFF_TIMES) - 1)
        wait = self._BACKOFF_TIMES[idx]
        if wait > 0:
            print(f"  ⏳ 插件 {self.name} 退避 {wait}s 后重试...")
            self._stop_event.wait(wait)

    def get_status(self) -> dict:
        """返回插件状态"""
        return {
            "name": self.name,
            "description": self.DESCRIPTION,
            "version": self.VERSION,
            "is_running": self.is_running,
            "interval": self.get_interval() if self.is_running else None,
            "tick_count": self._tick_count,
            "last_tick": self._last_tick_time.isoformat() if self._last_tick_time else None,
            "error_count": self._error_count,
            "crash_count": self._crash_count,
            "circuit_disabled": self._circuit_disabled,
        }

    # ─── P0.56: 能力暴露 ──────────────────────────

    def get_capabilities(self) -> Optional[dict]:
        """返回能力描述符，供Skills系统注册为T3技能。

        子类覆盖此方法，返回格式:
            {
                "name": "stock_query",          # 能力名称
                "description": "实时股价查询",    # 人类可读描述
                "triggers": ["股价", "股票"],     # 触发关键词列表
                "plugin": "stock_monitor",       # 插件名（即self.name）
                "method": "query_report",        # 可调用的方法名
                "category": "finance",           # 类别（可选）
            }

        返回None表示此插件不暴露对话能力。
        """
        return None


class PluginManager:
    """
    后台插件管理器

    职责:
      1. 注册/注销后台插件
      2. 批量启动/停止所有插件
      3. 从config.json的plugins段读取启用列表
      4. 提供插件状态查询
      5. 插件隔离：单个插件崩溃不影响其他

    用法:
        manager = PluginManager()
        manager.register(MyPlugin())
        manager.start_all()
        # ... 运行中 ...
        manager.stop_all()
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化插件管理器

        Args:
            config: 配置字典，可包含:
                - plugins.enabled: 是否启用插件系统
                - plugins.dir: 插件目录
                - plugins.active: 启用的插件名列表
        """
        self.config = config or {}
        self._plugins: Dict[str, BackgroundPlugin] = {}
        self._lock = threading.Lock()
        self._output_callback: Optional[Callable[[str], None]] = None

        # 配置直接从 config 字典读取
        self._plugins_enabled = self.config.get("enabled", True)
        self._plugins_dir = self.config.get("dir", "plugins")
        self._active_list = self.config.get("active", [])

    def set_output_callback(self, callback: Callable[[str], None]):
        """设置全局输出回调，会同步到所有已注册和后续注册的插件"""
        self._output_callback = callback
        with self._lock:
            for plugin in self._plugins.values():
                plugin.set_output_callback(callback)

    # ─── 注册/注销 ───────────────────────────────

    def register(self, plugin: BackgroundPlugin) -> bool:
        """
        注册一个后台插件

        Args:
            plugin: BackgroundPlugin实例

        Returns:
            bool: 是否注册成功
        """
        if not isinstance(plugin, BackgroundPlugin):
            print(f"  ⚠ 注册失败: {plugin} 不是BackgroundPlugin子类")
            return False

        name = plugin.name
        with self._lock:
            if name in self._plugins:
                print(f"  ⚠ 插件 '{name}' 已注册，跳过重复注册")
                return False
            # 同步输出回调到新插件
            if self._output_callback:
                plugin.set_output_callback(self._output_callback)
            self._plugins[name] = plugin

        print(f"  📌 插件 '{name}' 已注册")
        return True

    def unregister(self, plugin_name: str) -> bool:
        """
        注销一个后台插件（会先停止该插件）

        Args:
            plugin_name: 插件名称

        Returns:
            bool: 是否注销成功
        """
        with self._lock:
            plugin = self._plugins.get(plugin_name)
            if plugin is None:
                print(f"  ⚠ 插件 '{plugin_name}' 未找到")
                return False

            # 先停止
            if plugin.is_running:
                plugin.stop()

            del self._plugins[plugin_name]

        print(f"  🗑 插件 '{plugin_name}' 已注销")
        return True

    # ─── 批量操作 ────────────────────────────────

    def start_all(self):
        """启动所有已注册插件"""
        if not self._plugins_enabled:
            print("  ℹ 插件系统未启用 (config.plugins.enabled=false)")
            return

        with self._lock:
            plugins = list(self._plugins.values())

        started = 0
        for plugin in plugins:
            # 如果配置了active列表，只启动列表中的插件
            if self._active_list and plugin.name not in self._active_list:
                print(f"  ℹ 插件 '{plugin.name}' 不在active列表中，跳过")
                continue

            if not plugin.is_running:
                try:
                    plugin.start()
                    started += 1
                except Exception as e:
                    print(f"  ⚠ 插件 '{plugin.name}' 启动失败: {e}")
                    traceback.print_exc()

        print(f"  ✅ 已启动 {started}/{len(plugins)} 个后台插件")

    def stop_all(self):
        """停止所有运行中的插件"""
        with self._lock:
            plugins = list(self._plugins.values())

        stopped = 0
        for plugin in plugins:
            if plugin.is_running:
                try:
                    plugin.stop()
                    stopped += 1
                except Exception as e:
                    print(f"  ⚠ 插件 '{plugin.name}' 停止失败: {e}")

        print(f"  ✅ 已停止 {stopped} 个后台插件")

    # ─── 查询 ───────────────────────────────────

    def get_status(self) -> dict:
        """
        返回所有插件状态

        Returns:
            dict: {
                "plugins_enabled": bool,
                "total": int,
                "running": int,
                "plugins": [plugin_status, ...]
            }
        """
        with self._lock:
            plugins = list(self._plugins.values())

        statuses = []
        running_count = 0
        for plugin in plugins:
            status = plugin.get_status()
            statuses.append(status)
            if status["is_running"]:
                running_count += 1

        return {
            "plugins_enabled": self._plugins_enabled,
            "total": len(plugins),
            "running": running_count,
            "stopped": len(plugins) - running_count,
            "plugins": statuses,
        }

    def get_plugin(self, name: str) -> Optional[BackgroundPlugin]:
        """获取指定名称的插件实例"""
        with self._lock:
            return self._plugins.get(name)

    def list_plugin_names(self) -> List[str]:
        """列出所有已注册插件名称"""
        with self._lock:
            return list(self._plugins.keys())

    # ─── P0.56: 能力桥接 ──────────────────────────

    def get_all_capabilities(self) -> List[dict]:
        """聚合所有已注册插件的能力描述符。

        Returns:
            list[dict]: 能力描述符列表（跳过返回None的插件）
        """
        with self._lock:
            plugins = list(self._plugins.values())
        caps = []
        for plugin in plugins:
            try:
                cap = plugin.get_capabilities()
                if cap:
                    # 自动补全 plugin 字段
                    cap.setdefault("plugin", plugin.name)
                    caps.append(cap)
            except Exception as e:
                print(f"  ⚠ 插件 '{plugin.name}' get_capabilities 异常: {e}")
        return caps

    def call_capability(self, plugin_name: str, method_name: str, *args, **kwargs):
        """调用指定插件的指定方法。

        Args:
            plugin_name: 插件名称
            method_name: 方法名

        Returns:
            方法返回值，或None（插件不存在/方法不存在/调用异常）
        """
        plugin = self.get_plugin(plugin_name)
        if plugin is None:
            return None
        method = getattr(plugin, method_name, None)
        if method is None or not callable(method):
            return None
        try:
            return method(*args, **kwargs)
        except Exception as e:
            print(f"  ⚠ 插件 '{plugin_name}' 方法 '{method_name}' 调用异常: {e}")
            return None

    # ─── 从config.json加载 ──────────────────────

    def load_from_config(self, config_path: str = "config.json") -> int:
        """
        从config.json的background_plugins段读取启用列表，并尝试加载插件

        Args:
            config_path: config.json路径

        Returns:
            int: 成功加载的插件数量
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
            print(f"  ⚠ 无法读取配置文件 {config_path}: {e}")
            return 0

        # 读取 background_plugins 段
        bgp_cfg = cfg.get("background_plugins", {})
        if not bgp_cfg.get("enabled", True):
            print("  ℹ 配置中后台插件系统未启用")
            return 0

        # 更新配置
        self._plugins_enabled = True
        self._plugins_dir = bgp_cfg.get("dir", "plugins")
        self._active_list = bgp_cfg.get("active", [])

        # 如果配置中有manifest，尝试从plugins目录加载
        loaded = 0
        if self._active_list:
            loaded = self._load_active_plugins()

        return loaded

    def _load_active_plugins(self) -> int:
        """从plugins目录加载active列表中的插件"""
        import importlib
        import sys

        loaded = 0

        # 确保plugins目录在path中
        if self._plugins_dir not in sys.path:
            sys.path.insert(0, self._plugins_dir)

        # 尝试加载manifest.json
        manifest_path = os.path.join(self._plugins_dir, "manifest.json")
        manifest = {}
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            pass

        # 构建模块→类映射
        manifest_entries = {
            entry.get("name", entry.get("module", "")): entry
            for entry in manifest.get("plugins", [])
        }

        for plugin_name in self._active_list:
            entry = manifest_entries.get(plugin_name)
            if not entry:
                print(f"  ℹ 插件 '{plugin_name}' 不在manifest中，跳过自动加载")
                continue

            try:
                module_name = entry["module"]
                class_name = entry.get("class", "Plugin")
                plugin_config = entry.get("config", {})

                mod = importlib.import_module(module_name)
                cls = getattr(mod, class_name)

                # 只加载BackgroundPlugin子类
                if not issubclass(cls, BackgroundPlugin):
                    print(f"  ℹ 插件 '{plugin_name}' 不是BackgroundPlugin子类，跳过")
                    continue

                plugin = cls(config=plugin_config)
                if self.register(plugin):
                    loaded += 1
            except Exception as e:
                print(f"  ⚠ 加载插件 '{plugin_name}' 失败: {e}")

        return loaded

    # ─── 上下文管理 ──────────────────────────────

    def __enter__(self):
        self.start_all()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all()
        return False


# ─── 示例插件 ─────────────────────────────────────

class HeartbeatPlugin(BackgroundPlugin):
    """心跳插件示例 — 每隔固定时间打印一次心跳"""

    NAME = "heartbeat"
    DESCRIPTION = "心跳检测插件（示例）"

    def get_interval(self) -> float:
        return self.config.get("interval", 60)

    def tick(self):
        print(f"  💓 心跳 @ {datetime.now().strftime('%H:%M:%S')}")


# ─── 独立运行入口 ─────────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print("  后台插件系统 · 独立测试")
    print("=" * 52)

    manager = PluginManager()

    # 注册示例插件
    heartbeat = HeartbeatPlugin(config={"interval": 2})
    manager.register(heartbeat)

    # 查看状态
    print(f"\n📊 注册后状态: {manager.get_status()}")

    # 启动所有
    print("\n▶ 启动所有插件...")
    manager.start_all()

    # 运行5秒
    print("\n⏳ 运行5秒...")
    time.sleep(5)

    # 查看运行状态
    print(f"\n📊 运行中状态: {manager.get_status()}")

    # 停止所有
    print("\n⏹ 停止所有插件...")
    manager.stop_all()

    # 最终状态
    print(f"\n📊 最终状态: {manager.get_status()}")

    # 注销插件
    manager.unregister("heartbeat")
    print(f"\n📊 注销后状态: {manager.get_status()}")

    print(f"\n{'=' * 52}")
    print("  测试完成")
    print(f"{'=' * 52}")
