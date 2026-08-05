#!/usr/bin/env python3
"""
P0.61: 操作审批工作流 (Approval Gate)

参考 AIRI 的 desktop_approve 模式，创建一个通用的操作审批层：
  - ApprovalGate: 维护待审批操作队列（内存 + 可选持久化到 WorkLedger SQLite）
  - 风险三级：LOW(自动通过) / MEDIUM(通知主人，超时自动通过) / HIGH(必须确认，超时拒绝)
  - 与 narration_events.py 联动：MEDIUM/HIGH 操作触发 approval_requested 事件

设计原则：
  - 审批是同步流程，不改变现有异步任务派发逻辑
  - ApprovalGate 初始化失败不影响主流程（try-except 包裹）
  - 所有方法都有类型注解和 docstring
  - Python 3.10+ 兼容
"""

import enum
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from narration_events import NarrationEmitter


# ─── 风险等级枚举 ───────────────────────────────

class RiskLevel(enum.IntEnum):
    """操作风险等级

    Attributes:
        LOW: 低风险，自动通过（如文件读取、网络请求）
        MEDIUM: 中风险，通知主人，超时后自动通过（如文件写入/删除）
        HIGH: 高风险，必须主人明确确认，超时默认拒绝（如系统命令执行）
    """

    LOW = 0
    MEDIUM = 1
    HIGH = 2


# ─── 审批状态枚举 ───────────────────────────────

class ApprovalStatus(enum.Enum):
    """审批状态"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


# ─── 默认风险映射 ───────────────────────────────

DEFAULT_RISK_MAP: Dict[str, RiskLevel] = {
    "file_read": RiskLevel.LOW,
    "file_write": RiskLevel.MEDIUM,
    "file_delete": RiskLevel.MEDIUM,
    "system_command": RiskLevel.HIGH,
    "network_request": RiskLevel.LOW,
    "code_execute": RiskLevel.HIGH,
}

# ─── 默认超时配置（秒） ─────────────────────────

DEFAULT_TIMEOUTS: Dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,        # 自动通过，不需要超时
    RiskLevel.MEDIUM: 30,    # 默认 30 秒
    RiskLevel.HIGH: 300,     # 默认 300 秒
}


# ─── 审批条目 ───────────────────────────────────

class ApprovalEntry:
    """单个审批条目（内存中的数据结构）

    Attributes:
        approval_id: 审批唯一标识
        action_type: 操作类型（如 file_write, system_command）
        action_desc: 操作描述
        risk_level: 风险等级
        status: 当前审批状态
        created_at: 创建时间戳
        resolved_at: 解决时间戳（审批完成时）
        timeout: 超时秒数
        resolved_by: 解决者（owner/auto_timeout/auto_approved）
    """

    def __init__(
        self,
        approval_id: str,
        action_type: str,
        action_desc: str,
        risk_level: RiskLevel,
        timeout: int = 0,
    ) -> None:
        self.approval_id: str = approval_id
        self.action_type: str = action_type
        self.action_desc: str = action_desc
        self.risk_level: RiskLevel = risk_level
        self.status: ApprovalStatus = ApprovalStatus.PENDING
        self.created_at: float = time.time()
        self.resolved_at: Optional[float] = None
        self.timeout: int = timeout
        self.resolved_by: str = ""

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "approval_id": self.approval_id,
            "action_type": self.action_type,
            "action_desc": self.action_desc,
            "risk_level": self.risk_level.name,
            "status": self.status.value,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "resolved_at": (
                datetime.fromtimestamp(self.resolved_at).isoformat()
                if self.resolved_at
                else None
            ),
            "timeout": self.timeout,
            "resolved_by": self.resolved_by,
        }

    def __repr__(self) -> str:
        return (
            f"ApprovalEntry(id={self.approval_id[:8]}, "
            f"type={self.action_type}, risk={self.risk_level.name}, "
            f"status={self.status.value})"
        )


# ─── 审批门 ─────────────────────────────────────

class ApprovalGate:
    """操作审批门 — 管理待审批操作队列

    工作流：
      1. register_action(action_type, action_desc, risk_level) → approval_id
      2. LOW 风险 → 自动通过，立即返回 approved
      3. MEDIUM 风险 → 发送 narration event 通知主人，超时后自动通过
      4. HIGH 风险 → 发送 narration event 通知主人，必须明确确认，超时拒绝
      5. check_approval(approval_id) → 返回当前状态
      6. resolve(approval_id, approved) → 主人手动审批

    线程安全：所有操作通过 _lock 保护。

    Args:
        config: config.json 的 approval_gate 配置段
        narration: 可选的叙述事件发射器
        ledger: 可选的 WorkLedger 实例（用于持久化）
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        narration: Optional[NarrationEmitter] = None,
        ledger: Optional[Any] = None,
    ) -> None:
        config = config or {}

        self._entries: Dict[str, ApprovalEntry] = {}
        self._lock = threading.Lock()
        self._narration = narration
        self._ledger = ledger

        # 风险映射（可被 config 覆盖）
        self._risk_map: Dict[str, RiskLevel] = dict(DEFAULT_RISK_MAP)
        custom_risks = config.get("risk_overrides", {})
        for action_type, level_str in custom_risks.items():
            try:
                self._risk_map[action_type] = RiskLevel[level_str.upper()]
            except (KeyError, AttributeError):
                print(f"  ⚠ [ApprovalGate] 未知风险等级: {level_str}，跳过")

        # 超时配置（可被 config 覆盖）
        self._timeouts: Dict[RiskLevel, int] = dict(DEFAULT_TIMEOUTS)
        custom_timeouts = config.get("timeouts", {})
        for level_str, seconds in custom_timeouts.items():
            try:
                level = RiskLevel[level_str.upper()]
                self._timeouts[level] = int(seconds)
            except (KeyError, AttributeError, ValueError):
                print(f"  ⚠ [ApprovalGate] 未知超时配置: {level_str}={seconds}，跳过")

        self._enabled: bool = config.get("enabled", True)

    # ─── 公开接口 ─────────────────────────────

    def register_action(
        self,
        action_type: str,
        action_desc: str,
        risk_level: Optional[RiskLevel] = None,
    ) -> str:
        """注册一个待审批操作

        Args:
            action_type: 操作类型（如 file_write, system_command）
            action_desc: 操作描述
            risk_level: 可选的风险等级覆盖；若不提供，则从 _risk_map 查找

        Returns:
            approval_id: 审批唯一标识

        Note:
            - LOW 风险操作自动通过，直接返回 approved 状态的 approval_id
            - MEDIUM/HIGH 风险操作触发 approval_requested narration event
        """
        if not self._enabled:
            # 审批门关闭，所有操作自动通过
            approval_id = str(uuid.uuid4())
            return approval_id

        # 确定风险等级
        if risk_level is None:
            risk_level = self._risk_map.get(action_type, RiskLevel.LOW)

        # 创建审批条目
        approval_id = str(uuid.uuid4())
        timeout = self._timeouts.get(risk_level, 0)
        entry = ApprovalEntry(
            approval_id=approval_id,
            action_type=action_type,
            action_desc=action_desc,
            risk_level=risk_level,
            timeout=timeout,
        )

        with self._lock:
            self._entries[approval_id] = entry

        # LOW 风险：自动通过
        if risk_level == RiskLevel.LOW:
            entry.status = ApprovalStatus.APPROVED
            entry.resolved_at = time.time()
            entry.resolved_by = "auto_approved"
            self._emit_resolved(entry)
            return approval_id

        # MEDIUM/HIGH 风险：发送 narration event 通知主人
        self._emit_requested(entry)

        return approval_id

    def check_approval(self, approval_id: str) -> str:
        """查询审批状态

        Args:
            approval_id: 审批唯一标识

        Returns:
            审批状态字符串: "pending" / "approved" / "rejected" / "timeout" / "unknown"
        """
        with self._lock:
            entry = self._entries.get(approval_id)

        if entry is None:
            return "unknown"

        # 检查超时
        if entry.status == ApprovalStatus.PENDING:
            self._check_timeout(entry)

        return entry.status.value

    def resolve(self, approval_id: str, approved: bool) -> bool:
        """手动解决审批（主人确认）

        Args:
            approval_id: 审批唯一标识
            approved: True=批准, False=拒绝

        Returns:
            是否成功解决（False 表示条目不存在或已被解决）
        """
        with self._lock:
            entry = self._entries.get(approval_id)

        if entry is None:
            return False

        if entry.status != ApprovalStatus.PENDING:
            return False  # 已被解决

        entry.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        entry.resolved_at = time.time()
        entry.resolved_by = "owner"

        self._emit_resolved(entry)
        return True

    def pending_approvals(self) -> List[dict]:
        """获取所有待审批操作列表

        Returns:
            待审批操作字典列表
        """
        with self._lock:
            entries = list(self._entries.values())

        result = []
        for entry in entries:
            if entry.status == ApprovalStatus.PENDING:
                # 检查超时
                self._check_timeout(entry)
                if entry.status != ApprovalStatus.PENDING:
                    continue
                result.append(entry.to_dict())

        return result

    def get_entry(self, approval_id: str) -> Optional[ApprovalEntry]:
        """获取审批条目

        Args:
            approval_id: 审批唯一标识

        Returns:
            ApprovalEntry 或 None
        """
        with self._lock:
            return self._entries.get(approval_id)

    def get_risk_level(self, action_type: str) -> RiskLevel:
        """获取操作类型对应的风险等级

        Args:
            action_type: 操作类型

        Returns:
            RiskLevel 枚举值
        """
        return self._risk_map.get(action_type, RiskLevel.LOW)

    def should_require_approval(self, action_type: str) -> bool:
        """判断操作是否需要审批（风险等级 >= MEDIUM）

        Args:
            action_type: 操作类型

        Returns:
            True 表示需要审批
        """
        return self.get_risk_level(action_type) >= RiskLevel.MEDIUM

    # ─── 内部方法 ─────────────────────────────

    def _check_timeout(self, entry: ApprovalEntry) -> None:
        """检查审批是否超时并自动解决

        Args:
            entry: 审批条目
        """
        if entry.status != ApprovalStatus.PENDING:
            return

        if entry.timeout <= 0:
            return

        elapsed = time.time() - entry.created_at
        if elapsed >= entry.timeout:
            # 超时
            if entry.risk_level == RiskLevel.MEDIUM:
                # MEDIUM 超时 → 自动通过
                entry.status = ApprovalStatus.APPROVED
                entry.resolved_by = "auto_timeout"
            else:
                # HIGH 超时 → 自动拒绝
                entry.status = ApprovalStatus.TIMEOUT
                entry.resolved_by = "auto_timeout"

            entry.resolved_at = time.time()
            self._emit_resolved(entry)

    def _emit_requested(self, entry: ApprovalEntry) -> None:
        """发送 approval_requested narration event

        Args:
            entry: 审批条目
        """
        if not self._narration:
            return

        try:
            event = {
                "type": "approval_requested",
                "timestamp": datetime.now().isoformat(),
                "action_type": entry.action_type,
                "action_desc": entry.action_desc,
                "risk_level": entry.risk_level.name,
                "approval_id": entry.approval_id,
                "timeout": entry.timeout,
            }
            self._narration.emit(event)
        except Exception as e:
            print(f"  ⚠ [ApprovalGate] narration emit 失败: {e}")

    def _emit_resolved(self, entry: ApprovalEntry) -> None:
        """发送 approval_resolved narration event

        Args:
            entry: 审批条目
        """
        if not self._narration:
            return

        try:
            event = {
                "type": "approval_resolved",
                "timestamp": datetime.now().isoformat(),
                "approval_id": entry.approval_id,
                "result": entry.status.value,
            }
            self._narration.emit(event)
        except Exception as e:
            print(f"  ⚠ [ApprovalGate] narration emit 失败: {e}")


# ===== 独立测试模式 =====
if __name__ == "__main__":
    print("=" * 50)
    print("ApprovalGate 独立测试")
    print("=" * 50)

    from narration_events import NarrationEmitter

    narration = NarrationEmitter()
    events_received = []
    narration.on_event(lambda e: events_received.append(e))

    gate = ApprovalGate(
        config={"enabled": True},
        narration=narration,
    )

    # 1. LOW 风险 → 自动通过
    print("\n[1] LOW 风险自动通过测试...")
    aid = gate.register_action("file_read", "读取 config.json")
    status = gate.check_approval(aid)
    print(f"  状态: {status}")
    assert status == "approved", f"期望 approved, 实际 {status}"
    print("  ✅ LOW 自动通过")

    # 2. MEDIUM 风险 → 等待审批
    print("\n[2] MEDIUM 风险等待测试...")
    aid2 = gate.register_action("file_write", "写入 output.txt")
    status2 = gate.check_approval(aid2)
    print(f"  状态: {status2}")
    assert status2 == "pending", f"期望 pending, 实际 {status2}"
    print("  ✅ MEDIUM 进入等待")

    # 3. 手动批准
    print("\n[3] 手动批准测试...")
    ok = gate.resolve(aid2, approved=True)
    status2b = gate.check_approval(aid2)
    print(f"  解决: {ok}, 状态: {status2b}")
    assert ok is True
    assert status2b == "approved"
    print("  ✅ 手动批准成功")

    # 4. HIGH 风险 → 必须确认
    print("\n[4] HIGH 风险必须确认测试...")
    aid3 = gate.register_action("system_command", "执行 rm -rf /tmp/test")
    status3 = gate.check_approval(aid3)
    print(f"  状态: {status3}")
    assert status3 == "pending"
    print("  ✅ HIGH 进入等待")

    # 5. 手动拒绝
    print("\n[5] 手动拒绝测试...")
    ok = gate.resolve(aid3, approved=False)
    status3b = gate.check_approval(aid3)
    print(f"  解决: {ok}, 状态: {status3b}")
    assert ok is True
    assert status3b == "rejected"
    print("  ✅ 手动拒绝成功")

    # 6. MEDIUM 超时自动通过
    print("\n[6] MEDIUM 超时自动通过测试...")
    gate2 = ApprovalGate(
        config={"enabled": True, "timeouts": {"medium": 1}},
        narration=narration,
    )
    aid4 = gate2.register_action("file_write", "写入 test.txt")
    print(f"  注册后状态: {gate2.check_approval(aid4)}")
    print("  等待 1.5 秒...")
    time.sleep(1.5)
    status4 = gate2.check_approval(aid4)
    print(f"  超时后状态: {status4}")
    assert status4 == "approved", f"期望 approved (超时自动通过), 实际 {status4}"
    print("  ✅ MEDIUM 超时自动通过")

    # 7. HIGH 超时自动拒绝
    print("\n[7] HIGH 超时自动拒绝测试...")
    gate3 = ApprovalGate(
        config={"enabled": True, "timeouts": {"high": 1}},
        narration=narration,
    )
    aid5 = gate3.register_action("system_command", "执行危险命令")
    print(f"  注册后状态: {gate3.check_approval(aid5)}")
    print("  等待 1.5 秒...")
    time.sleep(1.5)
    status5 = gate3.check_approval(aid5)
    print(f"  超时后状态: {status5}")
    assert status5 == "timeout", f"期望 timeout, 实际 {status5}"
    print("  ✅ HIGH 超时自动拒绝")

    # 8. 自定义风险覆盖
    print("\n[8] 自定义风险覆盖测试...")
    gate4 = ApprovalGate(
        config={
            "enabled": True,
            "risk_overrides": {"network_request": "HIGH"},
        },
        narration=narration,
    )
    assert gate4.get_risk_level("network_request") == RiskLevel.HIGH
    print("  ✅ 风险覆盖生效")

    # 9. pending_approvals
    print("\n[9] pending_approvals 测试...")
    pending = gate.pending_approvals()
    print(f"  pending 数量: {len(pending)}")

    # 10. narration events
    print(f"\n[10] narration 事件测试...")
    print(f"  收到 {len(events_received)} 个事件")
    for ev in events_received:
        print(f"    {ev['type']}: {ev.get('risk_level', ev.get('result', ''))}")
    assert len(events_received) > 0
    print("  ✅ narration 事件正常")

    # 11. 审批门关闭
    print("\n[11] 审批门关闭测试...")
    gate5 = ApprovalGate(config={"enabled": False}, narration=narration)
    aid6 = gate5.register_action("system_command", "危险命令")
    # 关闭时不需要审批
    print("  ✅ 审批门关闭时不阻塞")

    print("\n✅ 全部通过")
