#!/usr/bin/env python3
"""
P0.60: Provider Runtime 执行层

参考 Amadeus 三层分离架构：
  - 叙述层 (NarrationLayer): narration_events.py — 表情/字幕/状态事件
  - 执行层 (ExecutionLayer): 本文件 — Provider 抽象 + 任务派发
  - 控制层 (ControlLayer): core.py / cli.py — 调度与用户交互

核心组件：
  1. Provider (ABC): 执行器基类，定义 can_handle / execute / serialize / deserialize
  2. SearchProvider: 封装 WebSearcher
  3. CodeProvider: 封装 CodeExecutor
  4. ProviderRuntime: 管理器，负责注册/派发/回调/重试/状态查询

设计原则：
  - ProviderRuntime 初始化失败不影响主流程（chat 正常工作）
  - WorkLedger 持久化所有任务记录到 SQLite
  - 异步派发用线程执行，完成后调用回调
"""

import threading
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from work_ledger import WorkLedger
from narration_events import NarrationEmitter


# ─── Provider 基类 ────────────────────────────

class Provider(ABC):
    """执行器基类 — 所有具体 Provider 继承此类"""

    NAME: str = "base"

    @abstractmethod
    def can_handle(self, task_type: str) -> bool:
        """判断是否能处理该任务类型"""
        ...

    @abstractmethod
    def execute(self, task: dict) -> dict:
        """同步执行任务，返回结果dict"""
        ...

    def serialize(self) -> dict:
        """序列化状态（用于持久化）"""
        return {"name": self.NAME}

    def deserialize(self, data: dict):
        """反序列化状态（恢复时调用）"""
        pass


# ─── SearchProvider ───────────────────────────

class SearchProvider(Provider):
    """搜索执行器 — 封装 WebSearcher"""

    NAME = "search"

    def __init__(self, web_searcher=None):
        """
        Args:
            web_searcher: WebSearcher 实例（可选，延迟注入）
        """
        self.web_searcher = web_searcher

    def can_handle(self, task_type: str) -> bool:
        return task_type in ("search", "web_search")

    def execute(self, task: dict) -> dict:
        """执行搜索

        Args:
            task: {"query": "...", "num_results": N}

        Returns:
            {"results": [...], "text": "格式化文本", "success": bool}
        """
        if not self.web_searcher:
            return {"results": [], "text": "", "success": False,
                    "error": "WebSearcher 未初始化"}

        query = task.get("query", "")
        num_results = task.get("num_results", 5)

        if not query:
            return {"results": [], "text": "", "success": False,
                    "error": "query 为空"}

        try:
            results = self.web_searcher.search(query, num_results)
            # 格式化为文本（供 LLM 上下文注入）
            text = "\n".join(
                f"[{i+1}] {r['title']}: {r.get('snippet', '')[:120]}"
                for i, r in enumerate(results)
            ) if results else "未找到相关结果"
            return {
                "results": results,
                "text": text,
                "success": True,
                "count": len(results),
            }
        except Exception as e:
            return {"results": [], "text": "", "success": False,
                    "error": str(e)}


# ─── CodeProvider ─────────────────────────────

class CodeProvider(Provider):
    """代码执行器 — 封装 CodeExecutor"""

    NAME = "code"

    def __init__(self, code_executor=None):
        """
        Args:
            code_executor: CodeExecutor 实例（可选，延迟注入）
        """
        self.code_executor = code_executor

    def can_handle(self, task_type: str) -> bool:
        return task_type in ("code", "execute_code", "python")

    def execute(self, task: dict) -> dict:
        """执行代码

        Args:
            task: {"code": "...", "timeout": N}

        Returns:
            执行结果dict（含 stdout/stderr/exit_code/success）
        """
        if not self.code_executor:
            return {"success": False, "error": "CodeExecutor 未初始化"}

        code = task.get("code", "")
        timeout = task.get("timeout", None)

        if not code:
            return {"success": False, "error": "code 为空"}

        try:
            result = self.code_executor.execute(code, timeout=timeout)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── ProviderRuntime 管理器 ───────────────────

class ProviderRuntime:
    """Provider Runtime 管理器 — 注册/派发/回调/重试/状态查询"""

    def __init__(self, config: dict = None, narration: NarrationEmitter = None):
        """
        Args:
            config: provider_runtime 配置段
            narration: 可选的叙述事件发射器
        """
        config = config or {}
        self._providers: Dict[str, Provider] = {}
        self._callbacks: List[Callable[[str, dict, str], None]] = []
        self._narration = narration

        # 初始化 WorkLedger
        ledger_path = config.get("ledger_path", "work_ledger.db")
        try:
            self.ledger = WorkLedger(db_path=ledger_path)
        except Exception as e:
            print(f"  ⚠ [ProviderRuntime] WorkLedger 初始化失败: {e}")
            self.ledger = None

        self._enabled = config.get("enabled", True)

    # ─── Provider 注册 ────────────────────────

    def register(self, provider: Provider):
        """注册一个 Provider"""
        self._providers[provider.NAME] = provider
        print(f"  [ProviderRuntime] 已注册 Provider: {provider.NAME}")

    def get_provider(self, name: str) -> Optional[Provider]:
        """获取已注册的 Provider"""
        return self._providers.get(name)

    @property
    def provider_names(self) -> List[str]:
        """已注册的 Provider 名称列表"""
        return list(self._providers.keys())

    # ─── 回调管理 ─────────────────────────────

    def on_complete(self, callback: Callable[[str, dict, str], None]):
        """注册完成回调 callback(work_id, result, status)"""
        self._callbacks.append(callback)

    def _notify_complete(self, work_id: str, result: dict, status: str):
        """通知所有回调"""
        for cb in self._callbacks:
            try:
                cb(work_id, result, status)
            except Exception as e:
                print(f"  ⚠ [ProviderRuntime] 回调异常: {e}")

        # 叙述事件
        if self._narration:
            try:
                msg = None
                if status == "completed":
                    msg = "任务完成"
                elif status == "failed":
                    msg = result.get("error", "任务失败") if isinstance(result, dict) else "任务失败"
                self._narration.emit_task_status(work_id, status, msg)
            except Exception:
                pass

    # ─── 同步派发 ─────────────────────────────

    def dispatch_sync(self, provider_name: str, task: dict) -> dict:
        """同步派发任务（阻塞等待结果）

        Args:
            provider_name: Provider 名称
            task: 任务参数dict

        Returns:
            执行结果dict（含 work_id, status, result）
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return {"success": False, "error": f"未注册的 Provider: {provider_name}"}

        # 创建任务记录
        description = task.get("description", f"{provider_name} task")
        work_id = ""
        attempt_id = ""
        if self.ledger:
            try:
                work_id = self.ledger.create_work_item(description, provider_name, task)
                attempt_id = self.ledger.start_attempt(work_id)
            except Exception as e:
                print(f"  ⚠ [ProviderRuntime] ledger 记录失败: {e}")

        # 执行
        try:
            result = provider.execute(task)
            status = "completed" if result.get("success", True) else "failed"
        except Exception as e:
            result = {"success": False, "error": str(e)}
            status = "failed"

        # 记录结果
        if self.ledger and work_id and attempt_id:
            try:
                self.ledger.complete_attempt(work_id, attempt_id, result, status)
            except Exception as e:
                print(f"  ⚠ [ProviderRuntime] ledger 记录完成失败: {e}")

        # 通知回调
        if work_id:
            self._notify_complete(work_id, result, status)

        return {
            "work_id": work_id,
            "status": status,
            "result": result,
        }

    # ─── 异步派发 ─────────────────────────────

    def dispatch_async(self, provider_name: str, task: dict) -> str:
        """异步派发任务（立即返回 work_id，在线程中执行）

        Args:
            provider_name: Provider 名称
            task: 任务参数dict

        Returns:
            work_id（字符串）
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return ""

        # 创建任务记录
        description = task.get("description", f"{provider_name} async task")
        work_id = ""
        if self.ledger:
            try:
                work_id = self.ledger.create_work_item(description, provider_name, task)
            except Exception as e:
                print(f"  ⚠ [ProviderRuntime] ledger 记录失败: {e}")

        if not work_id:
            work_id = f"ephemeral-{provider_name}-{id(task)}"

        # 启动线程执行
        thread = threading.Thread(
            target=self._async_execute,
            args=(work_id, provider, task),
            daemon=True,
            name=f"provider-{provider_name}-{work_id[:8]}",
        )
        thread.start()

        return work_id

    def _async_execute(self, work_id: str, provider: Provider, task: dict):
        """异步执行内部方法（在线程中运行）"""
        attempt_id = ""
        if self.ledger:
            try:
                attempt_id = self.ledger.start_attempt(work_id)
            except Exception as e:
                print(f"  ⚠ [ProviderRuntime] start_attempt 失败: {e}")

        try:
            result = provider.execute(task)
            status = "completed" if result.get("success", True) else "failed"
        except Exception as e:
            result = {"success": False, "error": str(e)}
            status = "failed"

        if self.ledger and attempt_id:
            try:
                self.ledger.complete_attempt(work_id, attempt_id, result, status)
            except Exception as e:
                print(f"  ⚠ [ProviderRuntime] complete_attempt 失败: {e}")

        self._notify_complete(work_id, result, status)

    # ─── 状态查询 ─────────────────────────────

    def get_status(self, work_id: str) -> dict:
        """查询任务状态"""
        if not self.ledger:
            return {"work_id": work_id, "status": "unknown", "error": "ledger 不可用"}
        try:
            work = self.ledger.get_work(work_id)
            if not work:
                return {"work_id": work_id, "status": "not_found"}
            return {
                "work_id": work_id,
                "status": work.get("status", "unknown"),
                "provider": work.get("provider", ""),
                "description": work.get("description", ""),
                "result": work.get("result"),
                "created_at": work.get("created_at", ""),
            }
        except Exception as e:
            return {"work_id": work_id, "status": "error", "error": str(e)}

    def pending_works(self) -> list:
        """获取未完成任务列表"""
        if not self.ledger:
            return []
        try:
            return self.ledger.get_pending()
        except Exception as e:
            print(f"  ⚠ [ProviderRuntime] pending_works 失败: {e}")
            return []

    # ─── 重试 ─────────────────────────────────

    def retry(self, work_id: str) -> str:
        """重试失败任务

        Args:
            work_id: 要重试的任务ID

        Returns:
            work_id（重置后的）
        """
        if not self.ledger:
            return work_id

        # 获取原任务信息
        work = None
        try:
            work = self.ledger.get_work(work_id)
        except Exception:
            pass

        if not work:
            print(f"  ⚠ [ProviderRuntime] retry: 任务不存在 {work_id}")
            return work_id

        # 重置状态
        try:
            self.ledger.retry_work(work_id)
        except Exception as e:
            print(f"  ⚠ [ProviderRuntime] retry_work 失败: {e}")

        # 重新派发（异步）
        provider_name = work.get("provider", "")
        payload = work.get("payload", {})
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        provider = self._providers.get(provider_name)
        if provider:
            thread = threading.Thread(
                target=self._async_execute,
                args=(work_id, provider, payload),
                daemon=True,
                name=f"provider-retry-{work_id[:8]}",
            )
            thread.start()
        else:
            print(f"  ⚠ [ProviderRuntime] retry: Provider {provider_name} 未注册")

        return work_id

    def get_history(self, limit: int = 20) -> list:
        """获取任务历史"""
        if not self.ledger:
            return []
        try:
            return self.ledger.get_history(limit)
        except Exception as e:
            print(f"  ⚠ [ProviderRuntime] get_history 失败: {e}")
            return []


# ===== 独立测试模式 =====
if __name__ == "__main__":
    import time

    print("=" * 50)
    print("ProviderRuntime 独立测试")
    print("=" * 50)

    # 使用内存数据库
    from narration_events import NarrationEmitter

    narration = NarrationEmitter()
    events_received = []
    narration.on_event(lambda e: events_received.append(e))

    runtime = ProviderRuntime(
        config={"enabled": True, "ledger_path": ":memory:"},
        narration=narration,
    )

    # 注册一个 mock provider
    class MockProvider(Provider):
        NAME = "mock"

        def can_handle(self, task_type: str) -> bool:
            return task_type == "mock"

        def execute(self, task: dict) -> dict:
            return {"success": True, "output": f"mock result for {task.get('q', '')}"}

    runtime.register(MockProvider())

    # 1. 同步派发
    print("\n[1] 同步派发测试...")
    result = runtime.dispatch_sync("mock", {"q": "hello", "description": "测试"})
    print(f"  结果: {result}")
    assert result["status"] == "completed"
    assert result["result"]["success"] is True
    print("  ✅ 同步派发成功")

    # 2. 状态查询
    print("\n[2] 状态查询测试...")
    wid = result["work_id"]
    status = runtime.get_status(wid)
    print(f"  状态: {status}")
    assert status["status"] == "completed"
    print("  ✅ 状态查询成功")

    # 3. 异步派发
    print("\n[3] 异步派发测试...")
    received_results = []
    runtime.on_complete(
        lambda work_id, result, status: received_results.append((work_id, result, status))
    )
    async_wid = runtime.dispatch_async("mock", {"q": "async test"})
    print(f"  work_id: {async_wid}")
    time.sleep(1)  # 等待线程完成
    assert len(received_results) > 0, "异步回调未触发"
    print(f"  回调结果: {received_results[0]}")
    print("  ✅ 异步派发成功")

    # 4. 重试
    print("\n[4] 重试测试...")
    retry_wid = runtime.retry(wid)
    time.sleep(1)
    status = runtime.get_status(wid)
    print(f"  重试后状态: {status['status']}")
    print("  ✅ 重试成功")

    # 5. 叙述事件
    print(f"\n[5] 叙述事件测试...")
    print(f"  收到 {len(events_received)} 个叙述事件")
    for ev in events_received:
        print(f"    {ev['type']}: {ev.get('status', '')}")
    assert len(events_received) > 0
    print("  ✅ 叙述事件正常")

    # 6. 历史
    print("\n[6] 历史查询测试...")
    history = runtime.get_history()
    print(f"  历史记录: {len(history)} 条")
    assert len(history) > 0
    print("  ✅ 历史查询成功")

    print("\n✅ 全部通过")
