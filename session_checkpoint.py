#!/usr/bin/env python3
"""
P0.46⑤ 会话重启恢复 — 对话状态检查点与恢复

在对话过程中定期保存对话状态（消息列表、PSI状态、时间戳、会话ID）到磁盘，
当程序异常退出或重启后可从最近的检查点恢复对话上下文。

特性：
  - 支持 gzip 压缩存储，节省磁盘空间
  - 最多保留 20 个检查点，超出自动清理最旧的
  - 每 50 条消息自动触发一次检查点保存
  - 保存完整的 PSI 引擎状态以实现无缝恢复

存储格式：gzip 压缩的 JSON 文件，位于 checkpoints/ 目录下。
文件命名：checkpoint_{session_id}_{timestamp}.json.gz
"""

import gzip
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─── 常量 ──────────────────────────────────────────────

CHECKPOINTS_DIR = Path(__file__).parent / "checkpoints"
"""检查点存储目录"""

MAX_CHECKPOINTS = 20
"""最多保留的检查点数量"""

CHECKPOINT_INTERVAL = 50
"""触发检查点的消息条数间隔"""

CHECKPOINT_PREFIX = "checkpoint_"
"""检查点文件名前缀"""

CHECKPOINT_SUFFIX = ".json.gz"
"""检查点文件名后缀"""


class SessionCheckpoint:
    """会话检查点管理器。

    负责在对话过程中定期保存对话状态到磁盘，并在需要时恢复。
    支持压缩存储、自动清理旧检查点。

    Attributes:
        checkpoints_dir: 检查点存储目录。
        session_id: 当前会话 ID。
        max_checkpoints: 最大保留检查点数量。
        checkpoint_interval: 触发检查点的消息间隔。
        last_checkpoint_count: 上次检查点时的消息数量。
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """初始化会话检查点管理器。

        Args:
            config: 可选配置字典。支持以下键：
                - dir: 检查点存储目录（默认 checkpoints/）
                - max_checkpoints: 最大保留数量（默认 20）
                - checkpoint_interval: 触发间隔（默认 50）
                - compress: 是否压缩存储（默认 True）
            session_id: 会话 ID。若为 None 则自动生成。
        """
        config = config or {}

        self.checkpoints_dir: Path = Path(
            config.get("dir", str(CHECKPOINTS_DIR))
        )
        if not self.checkpoints_dir.is_absolute():
            self.checkpoints_dir = Path(__file__).parent / self.checkpoints_dir
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        self.max_checkpoints: int = config.get("max_checkpoints", MAX_CHECKPOINTS)
        self.checkpoint_interval: int = config.get(
            "checkpoint_interval", CHECKPOINT_INTERVAL
        )
        self.compress: bool = config.get("compress", True)

        self.session_id: str = session_id or self._generate_session_id()
        self.last_checkpoint_count: int = 0

    # ─── 检查点保存 ────────────────────────────────────────

    def save_checkpoint(
        self,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """将对话状态保存到磁盘。

        保存内容包括：
          - messages: 完整的消息列表
          - psi_state: PSI 引擎状态（从 metadata 中提取）
          - timestamp: 保存时间戳
          - session_id: 会话 ID
          - message_count: 消息数量

        保存后自动检查并清理超出上限的旧检查点。

        Args:
            messages: 对话消息列表，格式为
                [{"role": "user"/"assistant", "content": "..."}]。
            metadata: 附加元数据。可包含：
                - psi_state: PSI 引擎状态字典
                - context: 上下文信息
                - 其他自定义字段

        Returns:
            保存的检查点文件路径，若保存失败则返回 None。
        """
        metadata = metadata or {}

        # 构造检查点数据
        checkpoint_data: Dict[str, Any] = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "unix_timestamp": time.time(),
            "message_count": len(messages),
            "messages": messages,
            "psi_state": metadata.get("psi_state", {}),
            "metadata": metadata,
        }

        # 生成文件名
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{CHECKPOINT_PREFIX}{self.session_id}_{timestamp_str}{CHECKPOINT_SUFFIX}"
        filepath = self.checkpoints_dir / filename

        # 写入文件
        try:
            json_data = json.dumps(checkpoint_data, ensure_ascii=False, default=str)
            if self.compress:
                with gzip.open(filepath, "wb") as f:
                    f.write(json_data.encode("utf-8"))
            else:
                # 非压缩模式使用普通 .json 后缀
                filepath = filepath.with_suffix(".json")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(json_data)
        except (OSError, gzip.BadGzipFile, TypeError) as e:
            print(f"[SessionCheckpoint] 保存检查点失败: {e}")
            return None

        # 更新上次检查点计数
        self.last_checkpoint_count = len(messages)

        # 清理旧检查点
        self._cleanup_old_checkpoints()

        print(f"[SessionCheckpoint] 检查点已保存: {filepath} ({len(messages)} 条消息)")
        return str(filepath)

    # ─── 检查点加载 ────────────────────────────────────────

    def load_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """加载最近的检查点。

        扫描检查点目录，找到最新的检查点文件并加载。

        Returns:
            检查点数据字典，若无可用检查点则返回 None。
            字典结构：
            {
                "session_id": str,
                "timestamp": str,
                "message_count": int,
                "messages": list,
                "psi_state": dict,
                "metadata": dict
            }
        """
        checkpoints = self._list_checkpoint_files()
        if not checkpoints:
            return None

        # 取最新的
        latest_path = checkpoints[-1]["path"]
        return self._load_checkpoint_file(latest_path)

    def load_checkpoint(self, filepath: str) -> Optional[Dict[str, Any]]:
        """加载指定的检查点文件。

        Args:
            filepath: 检查点文件路径。

        Returns:
            检查点数据字典，若加载失败则返回 None。
        """
        return self._load_checkpoint_file(Path(filepath))

    def _load_checkpoint_file(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """从文件加载检查点数据。

        Args:
            filepath: 检查点文件路径。

        Returns:
            检查点数据字典，若加载失败则返回 None。
        """
        if not filepath.exists():
            print(f"[SessionCheckpoint] 检查点文件不存在: {filepath}")
            return None

        try:
            if filepath.suffix == ".gz":
                with gzip.open(filepath, "rb") as f:
                    json_data = f.read().decode("utf-8")
            else:
                json_data = filepath.read_text(encoding="utf-8")
            return json.loads(json_data)
        except (OSError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"[SessionCheckpoint] 加载检查点失败: {e}")
            return None

    # ─── 会话恢复 ──────────────────────────────────────────

    def restore_session(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """恢复会话状态。

        加载最近的检查点，返回恢复后的消息列表和元数据。

        Returns:
            元组 (messages, metadata)：
            - messages: 恢复的消息列表，若无检查点则返回空列表。
            - metadata: 恢复的元数据字典，包含 psi_state 等。
              若无检查点则返回空字典。
        """
        checkpoint = self.load_latest_checkpoint()
        if checkpoint is None:
            print("[SessionCheckpoint] 无可用检查点，从头开始新会话")
            return [], {}

        messages = checkpoint.get("messages", [])
        metadata = checkpoint.get("metadata", {})

        # 确保 psi_state 在 metadata 中
        if "psi_state" not in metadata:
            metadata["psi_state"] = checkpoint.get("psi_state", {})

        # 恢复会话 ID
        self.session_id = checkpoint.get("session_id", self.session_id)
        self.last_checkpoint_count = len(messages)

        print(
            f"[SessionCheckpoint] 会话已恢复: "
            f"会话ID={self.session_id}, "
            f"消息数={len(messages)}, "
            f"保存时间={checkpoint.get('timestamp', 'unknown')}"
        )
        return messages, metadata

    # ─── 触发判断 ──────────────────────────────────────────

    def should_checkpoint(self, message_count: int) -> bool:
        """判断是否应该触发一次检查点保存。

        当消息数量达到间隔阈值（默认每50条）时返回 True。

        Args:
            message_count: 当前消息总数。

        Returns:
            是否应触发检查点保存。
        """
        if message_count <= 0:
            return False
        # 当消息数是间隔的整数倍，且自上次检查点后新增了足够消息
        if message_count % self.checkpoint_interval == 0:
            if message_count > self.last_checkpoint_count:
                return True
        return False

    # ─── 检查点信息 ────────────────────────────────────────

    def get_checkpoint_info(self) -> Dict[str, Any]:
        """返回检查点列表和大小信息。

        Returns:
            信息字典，包含：
            - total: 检查点总数
            - checkpoints: 检查点列表（含文件名、大小、时间戳）
            - total_size: 所有检查点总大小（字节）
            - dir: 检查点目录路径
        """
        checkpoints = self._list_checkpoint_files()
        total_size = sum(cp["size"] for cp in checkpoints)

        return {
            "total": len(checkpoints),
            "checkpoints": [
                {
                    "filename": cp["path"].name,
                    "size": cp["size"],
                    "size_human": self._format_size(cp["size"]),
                    "timestamp": cp["timestamp"],
                    "session_id": cp["session_id"],
                }
                for cp in checkpoints
            ],
            "total_size": total_size,
            "total_size_human": self._format_size(total_size),
            "dir": str(self.checkpoints_dir),
        }

    # ─── 内部方法 ──────────────────────────────────────────

    def _list_checkpoint_files(self) -> List[Dict[str, Any]]:
        """列出所有检查点文件，按时间排序。

        Returns:
            检查点信息列表，每项包含 path, size, timestamp, session_id。
            按时间从旧到新排序。
        """
        result: List[Dict[str, Any]] = []

        # 匹配压缩和非压缩文件
        patterns = [f"{CHECKPOINT_PREFIX}*{CHECKPOINT_SUFFIX}", f"{CHECKPOINT_PREFIX}*.json"]
        seen_paths: set = set()

        for pattern in patterns:
            for filepath in self.checkpoints_dir.glob(pattern):
                if filepath in seen_paths:
                    continue
                seen_paths.add(filepath)

                try:
                    stat = filepath.stat()
                except OSError:
                    continue

                # 从文件名解析 session_id
                name = filepath.stem
                if name.endswith(".json"):
                    name = name[:-5]
                if name.startswith(CHECKPOINT_PREFIX):
                    name = name[len(CHECKPOINT_PREFIX):]
                # 格式: {session_id}_{timestamp}
                parts = name.rsplit("_", 1)
                session_id = parts[0] if len(parts) == 2 else name

                # 解析时间戳
                timestamp_str = parts[1] if len(parts) == 2 else ""
                try:
                    timestamp = datetime.strptime(
                        timestamp_str, "%Y%m%d_%H%M%S"
                    ).isoformat()
                except ValueError:
                    timestamp = datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat()

                result.append(
                    {
                        "path": filepath,
                        "size": stat.st_size,
                        "timestamp": timestamp,
                        "session_id": session_id,
                        "mtime": stat.st_mtime,
                    }
                )

        # 按修改时间排序（旧→新）
        result.sort(key=lambda x: x["mtime"])
        return result

    def _cleanup_old_checkpoints(self) -> None:
        """清理超出上限的旧检查点。

        当检查点数量超过 max_checkpoints 时，删除最旧的检查点文件。
        """
        checkpoints = self._list_checkpoint_files()
        excess = len(checkpoints) - self.max_checkpoints

        if excess <= 0:
            return

        # 删除最旧的 excess 个
        for i in range(excess):
            filepath = checkpoints[i]["path"]
            try:
                filepath.unlink()
                print(f"[SessionCheckpoint] 已清理旧检查点: {filepath.name}")
            except OSError as e:
                print(f"[SessionCheckpoint] 清理检查点失败: {e}")

    @staticmethod
    def _generate_session_id() -> str:
        """生成唯一的会话 ID。

        Returns:
            8 字符的会话 ID 字符串。
        """
        return uuid.uuid4().hex[:8]

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节数格式化为人类可读的大小字符串。

        Args:
            size_bytes: 字节大小。

        Returns:
            格式化后的大小字符串，如 "1.23 KB"。
        """
        if size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB"]
        unit_idx = 0
        size = float(size_bytes)
        while size >= 1024 and unit_idx < len(units) - 1:
            size /= 1024
            unit_idx += 1
        return f"{size:.2f} {units[unit_idx]}"

    # ─── 便捷方法 ──────────────────────────────────────────

    def clear_all_checkpoints(self) -> int:
        """清除所有检查点文件。

        Returns:
            已删除的文件数量。
        """
        checkpoints = self._list_checkpoint_files()
        count = 0
        for cp in checkpoints:
            try:
                cp["path"].unlink()
                count += 1
            except OSError:
                pass
        print(f"[SessionCheckpoint] 已清除 {count} 个检查点文件")
        return count

    def new_session(self) -> None:
        """开始一个新的会话。

        生成新的会话 ID 并重置计数器。
        """
        self.session_id = self._generate_session_id()
        self.last_checkpoint_count = 0
        print(f"[SessionCheckpoint] 新会话已创建: {self.session_id}")
