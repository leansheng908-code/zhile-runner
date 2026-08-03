#!/usr/bin/env python3
"""
知乐回执审计系统 — P0.6（UPSP启发）

UPSP核心哲学："没有回执就不能宣称已经发生。"

两层审计：
  1. 实时审计：每次LLM调用/工具调用/进化操作产生receipt
  2. 事后审计：已有39条测试（P0.3/P0.28），本模块补充实时层

审计记录类型：
  - llm_call: 请求体SHA-256 + 响应摘要 + token消耗
  - tool_call: 工具名 + 参数摘要 + 结果(成功/失败) + 耗时
  - evolution: 改了什么 + 测试结果 + 是否回退
  - memory_op: 记忆操作类型 + 影响的记忆ID
"""

import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class AuditLogger:
    """回执审计系统"""

    MAX_RECORDS = 10000       # 最多保留1万条
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self, config: dict = None):
        config = config or {}
        self.log_file = Path(config.get("log_file", "memory/audit_log.jsonl"))
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: List[dict] = []
        self._buffer_limit = 50  # 缓冲50条后flush

    def log_llm_call(self, system_prompt: str, user_message: str,
                     response: str, tokens_used: int = 0,
                     model: str = "") -> dict:
        """记录LLM调用"""
        record = self._create_record("llm_call", {
            "request_sha256": hashlib.sha256(
                (system_prompt + user_message).encode("utf-8")).hexdigest()[:16],
            "user_message_preview": user_message[:200],
            "response_preview": response[:200],
            "tokens_used": tokens_used,
            "model": model,
        })
        self._add(record)
        return record

    def log_tool_call(self, tool_name: str, params: dict,
                      result: Any, success: bool = True,
                      duration_ms: int = 0) -> dict:
        """记录工具调用"""
        record = self._create_record("tool_call", {
            "tool": tool_name,
            "params_preview": str(params)[:200],
            "result_preview": str(result)[:200],
            "success": success,
            "duration_ms": duration_ms,
        })
        self._add(record)
        return record

    def log_evolution(self, action: str, details: dict,
                      test_passed: bool = False,
                      rolled_back: bool = False) -> dict:
        """记录进化操作"""
        record = self._create_record("evolution", {
            "action": action,
            "details_preview": str(details)[:300],
            "test_passed": test_passed,
            "rolled_back": rolled_back,
        })
        self._add(record)
        return record

    def log_memory_op(self, operation: str, memory_ids: List[str],
                      details: str = "") -> dict:
        """记录记忆操作"""
        record = self._create_record("memory_op", {
            "operation": operation,
            "memory_ids": memory_ids[:10],
            "details_preview": details[:200],
        })
        self._add(record)
        return record

    # ─── 查询 ───────────────────────────────────

    def query(self, record_type: str = None,
              start_time: str = None,
              end_time: str = None,
              limit: int = 50) -> List[dict]:
        """查询审计记录"""
        results = []
        records = self._read_all()

        for r in reversed(records):  # 最新的在前
            if record_type and r.get("type") != record_type:
                continue
            if start_time and r.get("timestamp", "") < start_time:
                continue
            if end_time and r.get("timestamp", "") > end_time:
                continue
            results.append(r)
            if len(results) >= limit:
                break

        return results

    def get_recent(self, limit: int = 10) -> List[dict]:
        """获取最近的审计记录"""
        return self.query(limit=limit)

    def get_stats(self) -> dict:
        """审计统计"""
        records = self._read_all()
        if not records:
            return {"total": 0}

        type_counts = {}
        for r in records:
            t = r.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        # 失败的工具调用
        tool_failures = sum(
            1 for r in records
            if r.get("type") == "tool_call" and not r.get("data", {}).get("success", True)
        )
        # 回退的进化操作
        rollbacks = sum(
            1 for r in records
            if r.get("type") == "evolution" and r.get("data", {}).get("rolled_back", False)
        )

        return {
            "total": len(records),
            "by_type": type_counts,
            "tool_failures": tool_failures,
            "evolution_rollbacks": rollbacks,
            "log_file": str(self.log_file),
            "log_file_size": f"{self.log_file.stat().st_size / 1024:.1f}KB"
                             if self.log_file.exists() else "0KB",
        }

    def verify_record(self, record_id: str) -> Optional[dict]:
        """验证并返回指定记录（"重新打开"功能）"""
        records = self._read_all()
        for r in records:
            if r.get("id") == record_id:
                return r
        return None

    # ─── 内部方法 ───────────────────────────────

    def _create_record(self, record_type: str, data: dict) -> dict:
        return {
            "id": hashlib.sha256(
                f"{record_type}{time.time()}{datetime.now().isoformat()}"
                .encode("utf-8")).hexdigest()[:12],
            "type": record_type,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

    def _add(self, record: dict):
        """添加记录到缓冲区"""
        self._buffer.append(record)
        if len(self._buffer) >= self._buffer_limit:
            self._flush()

    def _flush(self):
        """将缓冲区写入文件"""
        if not self._buffer:
            return

        # 检查文件大小，超限则清理旧记录
        if self.log_file.exists() and self.log_file.stat().st_size > self.MAX_FILE_SIZE:
            self._rotate()

        with open(self.log_file, "a", encoding="utf-8") as f:
            for record in self._buffer:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self._buffer.clear()

    def _rotate(self):
        """清理旧记录（保留最近MAX_RECORDS条）"""
        records = self._read_all()
        if len(records) > self.MAX_RECORDS:
            records = records[-self.MAX_RECORDS:]
            with open(self.log_file, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _read_all(self) -> List[dict]:
        """读取所有记录"""
        # 先flush缓冲区
        if self._buffer:
            self._flush()

        if not self.log_file.exists():
            return []

        records = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

        return records

    def flush(self):
        """手动flush（在/exit时调用）"""
        self._flush()
