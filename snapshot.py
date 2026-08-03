#!/usr/bin/env python3
"""
知乐版本回退与安全机制 — P0.5

防止知乐"把自己进化没了"。

核心机制：
  1. 存档点：每次进化前自动创建快照（拷贝所有可进化状态文件）
  2. 回退：进化出问题时读档恢复
  3. 安全阀：回退预算/复杂度预算/一致性检查/干细胞校验
  4. 进化日志：记录每次进化和回退的完整审计链

就像游戏存档——升级前先存盘，升级后变弱了就读档重来。

干细胞保护：
  干细胞文件（身份/性格/边界/硬规则）是知乐的"不可变内核"。
  进化系统物理上不应该写入这些文件。
  本模块通过文件哈希校验检测未授权修改，并在启动时发出警告。
"""

import json
import shutil
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Snapshot:
    """单个存档点"""

    def __init__(self, snapshot_id: str, timestamp: str, reason: str,
                 file_hashes: Dict[str, str], metadata: Dict):
        self.id = snapshot_id
        self.timestamp = timestamp
        self.reason = reason
        self.file_hashes = file_hashes  # {relative_path: md5_hash}
        self.metadata = metadata  # counts, psi values, etc.

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "file_hashes": self.file_hashes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        return cls(
            snapshot_id=d["id"],
            timestamp=d["timestamp"],
            reason=d["reason"],
            file_hashes=d.get("file_hashes", {}),
            metadata=d.get("metadata", {}),
        )


class SnapshotManager:
    """版本回退与安全管理器"""

    # 保留最近多少个快照
    MAX_SNAPSHOTS = 20
    # 每天最多回退几次
    DAILY_ROLLBACK_BUDGET = 3
    # 体细胞数量上限（超过需人工批准）
    MAX_SOMATIC_CELLS = 50
    # 弧光数量上限
    MAX_ARC_LIGHTS = 20

    # 需要快照的可进化文件（相对于memory_dir）
    EVOLVABLE_FILES = [
        "growth/somatic_cells.json",
        "growth/workspace.md",
        "arc_light.json",
        "psi/psi_state.json",
        "memories.json",
        "session.json",
    ]

    # 需要快照的目录（递归拷贝）
    EVOLVABLE_DIRS = [
        "entities",
    ]

    # 干细胞文件（相对于dna_path，进化系统不应写入）
    STEM_CELL_FILES = [
        "system_prompt.md",
        "core/identity.json",
        "core/personality.json",
        "core/boundaries.json",
        "core/hard_rules.json",
        "core/safety_rules.json",
        "data/SOUL.md",
    ]

    def __init__(self, memory_dir: str, dna_path: str = None):
        self.memory_dir = Path(memory_dir)
        self.dna_path = Path(dna_path) if dna_path else None
        self.snapshots_dir = self.memory_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.snapshots_dir / "index.json"
        self.log_file = self.snapshots_dir / "evolution_log.json"
        self._stem_hashes: Dict[str, str] = {}
        self._init_index()
        self._init_log()
        self._record_stem_hashes()

    # ─── 初始化 ───────────────────────────────

    def _init_index(self):
        if not self.index_file.exists():
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _init_log(self):
        if not self.log_file.exists():
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _record_stem_hashes(self):
        """启动时记录干细胞文件哈希，用于后续校验"""
        if not self.dna_path:
            return
        for rel_path in self.STEM_CELL_FILES:
            full_path = self.dna_path / rel_path
            if full_path.exists():
                self._stem_hashes[rel_path] = self._hash_file(full_path)

    # ─── 工具方法 ─────────────────────────────

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()

    def _load_index(self) -> List[dict]:
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return []

    def _save_index(self, entries: List[dict]):
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def _load_log(self) -> List[dict]:
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return []

    def _append_log(self, entry: dict):
        log = self._load_log()
        log.append(entry)
        # 只保留最近100条日志
        if len(log) > 100:
            log = log[-100:]
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    def _collect_metadata(self, somatic_system=None, arc_system=None,
                          psi_engine=None) -> dict:
        """收集当前系统状态的元数据"""
        meta = {"timestamp": datetime.now().isoformat()}
        if somatic_system:
            stats = somatic_system.get_stats()
            meta["somatic"] = stats
        if arc_system:
            meta["arc_lights"] = arc_system.get_stats()
        if psi_engine:
            meta["psi"] = psi_engine.get_stats()
        return meta

    # ─── 核心：创建快照 ───────────────────────

    def create_snapshot(self, reason: str = "manual",
                        somatic_system=None, arc_system=None,
                        psi_engine=None) -> Optional[str]:
        """创建存档点

        Args:
            reason: 快照原因（manual/auto_scan/arc_promote/param_change）
            somatic_system: 体细胞系统实例
            arc_system: 弧光系统实例
            psi_engine: PSI引擎实例

        Returns:
            snapshot_id 或 None（失败时）
        """
        snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snap_dir = self.snapshots_dir / snapshot_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        file_hashes = {}

        # 拷贝可进化文件
        for rel_path in self.EVOLVABLE_FILES:
            src = self.memory_dir / rel_path
            if src.exists():
                dst = snap_dir / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                file_hashes[rel_path] = self._hash_file(src)

        # 拷贝可进化目录
        for rel_dir in self.EVOLVABLE_DIRS:
            src_dir = self.memory_dir / rel_dir
            if src_dir.exists() and src_dir.is_dir():
                dst_dir = snap_dir / rel_dir
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                # 记录目录下所有文件的哈希
                for root, _, files in os.walk(src_dir):
                    for fname in files:
                        fpath = Path(root) / fname
                        rel = fpath.relative_to(self.memory_dir)
                        file_hashes[str(rel)] = self._hash_file(fpath)

        # 收集元数据
        metadata = self._collect_metadata(somatic_system, arc_system, psi_engine)

        # 创建快照对象
        snapshot = Snapshot(snapshot_id, metadata["timestamp"], reason,
                           file_hashes, metadata)

        # 保存快照元信息
        meta_file = snap_dir / "snapshot_meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)

        # 更新索引
        index = self._load_index()
        index_entry = {
            "id": snapshot_id,
            "timestamp": metadata["timestamp"],
            "reason": reason,
            "files": len(file_hashes),
            "somatic_count": metadata.get("somatic", {}).get("active", 0),
            "arc_count": metadata.get("arc_lights", {}).get("total", 0),
        }
        index.append(index_entry)
        # 保留最近MAX_SNAPSHOTS个
        if len(index) > self.MAX_SNAPSHOTS:
            old_entries = index[:-self.MAX_SNAPSHOTS]
            index = index[-self.MAX_SNAPSHOTS:]
            # 删除过期快照目录
            for old in old_entries:
                old_dir = self.snapshots_dir / old["id"]
                if old_dir.exists():
                    shutil.rmtree(old_dir, ignore_errors=True)
        self._save_index(index)

        # 记录日志
        self._append_log({
            "type": "snapshot",
            "id": snapshot_id,
            "timestamp": metadata["timestamp"],
            "reason": reason,
            "files": len(file_hashes),
        })

        return snapshot_id

    # ─── 核心：回退 ───────────────────────────

    def rollback(self, snapshot_id: str,
                 somatic_system=None, arc_system=None,
                 psi_engine=None) -> Tuple[bool, str]:
        """回退到指定存档点

        Returns:
            (success, message)
        """
        # 检查回退预算
        budget_ok, budget_msg = self._check_rollback_budget()
        if not budget_ok:
            return False, budget_msg

        # 查找快照
        snap_dir = self.snapshots_dir / snapshot_id
        if not snap_dir.exists():
            return False, f"快照不存在: {snapshot_id}"

        meta_file = snap_dir / "snapshot_meta.json"
        if not meta_file.exists():
            return False, f"快照元数据缺失: {snapshot_id}"

        with open(meta_file, "r", encoding="utf-8") as f:
            snap_data = json.load(f)
        snapshot = Snapshot.from_dict(snap_data)

        # 恢复文件
        restored = 0
        for rel_path in self.EVOLVABLE_FILES:
            src = snap_dir / rel_path
            if src.exists():
                dst = self.memory_dir / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                restored += 1

        # 恢复目录
        for rel_dir in self.EVOLVABLE_DIRS:
            src_dir = snap_dir / rel_dir
            if src_dir.exists() and src_dir.is_dir():
                dst_dir = self.memory_dir / rel_dir
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)
                restored += 1

        # 重新加载系统状态
        if somatic_system:
            somatic_system.cells = somatic_system._load()
        if arc_system:
            arc_system.arcs = arc_system._load()
        if psi_engine:
            psi_engine.needs = psi_engine._load_or_init()
            psi_engine.consciousness_frame = psi_engine._load_frame()

        # 更新日志
        self._append_log({
            "type": "rollback",
            "id": snapshot_id,
            "timestamp": datetime.now().isoformat(),
            "reason": snapshot.reason,
            "files_restored": restored,
        })

        return True, f"已回退到 {snapshot_id}（恢复{restored}个文件）"

    # ─── 安全阀 ───────────────────────────────

    def _check_rollback_budget(self) -> Tuple[bool, str]:
        """检查今日回退预算"""
        today = datetime.now().strftime("%Y-%m-%d")
        log = self._load_log()
        today_rollbacks = sum(
            1 for e in log
            if e.get("type") == "rollback"
            and e.get("timestamp", "").startswith(today)
        )
        if today_rollbacks >= self.DAILY_ROLLBACK_BUDGET:
            return False, (f"今日已回退{today_rollbacks}次，"
                          f"超过预算({self.DAILY_ROLLBACK_BUDGET})，暂停回退")
        return True, "OK"

    def check_complexity(self, somatic_system=None,
                         arc_system=None) -> Tuple[bool, str]:
        """检查复杂度预算"""
        issues = []
        if somatic_system:
            stats = somatic_system.get_stats()
            total = stats.get("total", 0)
            if total > self.MAX_SOMATIC_CELLS:
                issues.append(f"体细胞{total}个，超过上限{self.MAX_SOMATIC_CELLS}")
        if arc_system:
            stats = arc_system.get_stats()
            total = stats.get("total", 0)
            if total > self.MAX_ARC_LIGHTS:
                issues.append(f"弧光{total}条，超过上限{self.MAX_ARC_LIGHTS}")
        if issues:
            return False, "；".join(issues)
        return True, "OK"

    def verify_stem_cells(self) -> Tuple[bool, List[str]]:
        """校验干细胞文件是否被篡改

        Returns:
            (all_ok, warnings)
        """
        warnings = []
        if not self.dna_path or not self._stem_hashes:
            return True, ["干细胞校验跳过（DNA路径未配置）"]

        for rel_path, expected_hash in self._stem_hashes.items():
            full_path = self.dna_path / rel_path
            if not full_path.exists():
                warnings.append(f"干细胞文件缺失: {rel_path}")
                continue
            current_hash = self._hash_file(full_path)
            if current_hash != expected_hash:
                warnings.append(f"干细胞文件被修改: {rel_path}")

        return len(warnings) == 0, warnings

    def verify_integrity(self, somatic_system=None,
                         arc_system=None) -> dict:
        """全面完整性检查"""
        checks = []

        # 1. 干细胞校验
        stem_ok, stem_warnings = self.verify_stem_cells()
        for w in stem_warnings:
            checks.append({"name": "干细胞校验", "passed": "被修改" not in w and "缺失" not in w, "detail": w})

        # 2. 复杂度预算
        cx_ok, cx_msg = self.check_complexity(somatic_system, arc_system)
        checks.append({"name": "复杂度预算", "passed": cx_ok, "detail": cx_msg})

        # 3. 体细胞冲突检查（同名不同状态）
        if somatic_system:
            names = {}
            for cell in somatic_system.cells:
                if cell.status in ("active", "candidate"):
                    if cell.name in names:
                        checks.append({
                            "name": "体细胞冲突",
                            "passed": False,
                            "detail": f"同名体细胞: {cell.name}"
                        })
                    names[cell.name] = cell.id

        # 4. 快照索引完整性
        index = self._load_index()
        missing_snaps = []
        for entry in index:
            snap_dir = self.snapshots_dir / entry["id"]
            if not snap_dir.exists():
                missing_snaps.append(entry["id"])
        if missing_snaps:
            checks.append({
                "name": "快照完整性",
                "passed": False,
                "detail": f"缺失快照目录: {', '.join(missing_snaps)}"
            })
        else:
            checks.append({"name": "快照完整性", "passed": True, "detail": f"{len(index)}个快照完好"})

        all_passed = all(c["passed"] for c in checks)
        return {"passed": all_passed, "checks": checks}

    # ─── 查询 ─────────────────────────────────

    def list_snapshots(self) -> List[dict]:
        """列出所有快照"""
        return self._load_index()

    def get_latest_snapshot(self) -> Optional[dict]:
        """获取最近的快照"""
        index = self._load_index()
        if index:
            return index[-1]
        return None

    def get_log(self, limit: int = 20) -> List[dict]:
        """获取进化日志"""
        log = self._load_log()
        return log[-limit:] if limit < len(log) else log

    def get_stats(self) -> dict:
        """获取统计信息"""
        index = self._load_index()
        log = self._load_log()
        today = datetime.now().strftime("%Y-%m-%d")
        today_rollbacks = sum(
            1 for e in log
            if e.get("type") == "rollback"
            and e.get("timestamp", "").startswith(today)
        )
        return {
            "total_snapshots": len(index),
            "total_log_entries": len(log),
            "today_rollbacks": today_rollbacks,
            "rollback_budget": self.DAILY_ROLLBACK_BUDGET - today_rollbacks,
            "max_snapshots": self.MAX_SNAPSHOTS,
            "max_somatic": self.MAX_SOMATIC_CELLS,
            "max_arc": self.MAX_ARC_LIGHTS,
        }
