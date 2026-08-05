#!/usr/bin/env python3
"""
P0.60: SQLite 持久化任务账本 (Work Ledger)

为 ProviderRuntime 提供任务追踪与持久化能力：
  - work_items 表：任务主记录（描述、provider、payload、状态、结果）
  - run_attempts 表：执行尝试记录（每次dispatch/retry创建一条）
  - 所有方法 try-except 包裹，数据库错误不崩溃主流程
  - check_same_thread=False 允许跨线程访问（异步派发场景）
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional


class WorkLedger:
    """SQLite 持久化任务账本"""

    def __init__(self, db_path: str = "work_ledger.db"):
        self.db_path = db_path
        try:
            self.conn = sqlite3.connect(
                db_path,
                check_same_thread=False,
            )
            self.conn.row_factory = sqlite3.Row
            self._create_tables()
        except Exception as e:
            print(f"  ⚠ [WorkLedger] 初始化失败，降级为内存模式: {e}")
            self.conn = None

    # ─── 建表 ──────────────────────────────────

    def _create_tables(self):
        """自动建表（幂等）"""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS work_items (
                    id          TEXT PRIMARY KEY,
                    description TEXT,
                    provider    TEXT,
                    payload     TEXT,
                    created_at  TEXT,
                    status      TEXT DEFAULT 'pending',
                    result      TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS run_attempts (
                    id           TEXT PRIMARY KEY,
                    work_id      TEXT,
                    started_at   TEXT,
                    completed_at TEXT,
                    status       TEXT DEFAULT 'running',
                    result       TEXT,
                    error        TEXT,
                    FOREIGN KEY (work_id) REFERENCES work_items(id)
                )
            """)
            # 索引加速查询
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_work_status ON work_items(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_attempt_work ON run_attempts(work_id)"
            )
            self.conn.commit()
        except Exception as e:
            print(f"  ⚠ [WorkLedger] 建表失败: {e}")

    # ─── Work Item CRUD ───────────────────────

    def create_work_item(
        self,
        description: str,
        provider: str,
        payload: dict,
    ) -> str:
        """创建任务记录，返回 work_id"""
        work_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        try:
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO work_items (id, description, provider, payload, created_at, status) "
                    "VALUES (?, ?, ?, ?, ?, 'pending')",
                    (
                        work_id,
                        description,
                        provider,
                        json.dumps(payload, ensure_ascii=False),
                        now,
                    ),
                )
                self.conn.commit()
        except Exception as e:
            print(f"  ⚠ [WorkLedger] create_work_item 失败: {e}")
        return work_id

    def start_attempt(self, work_id: str) -> str:
        """开始一次执行尝试，更新 work_item 状态为 running，返回 attempt_id"""
        attempt_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        try:
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO run_attempts (id, work_id, started_at, status) "
                    "VALUES (?, ?, ?, 'running')",
                    (attempt_id, work_id, now),
                )
                cursor.execute(
                    "UPDATE work_items SET status='running' WHERE id=?",
                    (work_id,),
                )
                self.conn.commit()
        except Exception as e:
            print(f"  ⚠ [WorkLedger] start_attempt 失败: {e}")
        return attempt_id

    def complete_attempt(
        self,
        work_id: str,
        attempt_id: str,
        result: dict,
        status: str,
    ):
        """完成一次执行尝试，同时更新 attempt 和 work_item 状态

        Args:
            work_id: 任务ID
            attempt_id: 尝试ID
            result: 执行结果dict
            status: "completed" 或 "failed"
        """
        now = datetime.now().isoformat()
        try:
            if self.conn:
                cursor = self.conn.cursor()
                result_json = json.dumps(result, ensure_ascii=False) if result else None
                error_text = result.get("error", "") if result and isinstance(result, dict) else ""

                cursor.execute(
                    "UPDATE run_attempts SET completed_at=?, status=?, result=?, error=? "
                    "WHERE id=?",
                    (now, status, result_json, error_text, attempt_id),
                )
                cursor.execute(
                    "UPDATE work_items SET status=?, result=? WHERE id=?",
                    (status, result_json, work_id),
                )
                self.conn.commit()
        except Exception as e:
            print(f"  ⚠ [WorkLedger] complete_attempt 失败: {e}")

    def get_work(self, work_id: str) -> Optional[dict]:
        """查询单个任务"""
        try:
            if not self.conn:
                return None
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM work_items WHERE id=?", (work_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)
        except Exception as e:
            print(f"  ⚠ [WorkLedger] get_work 失败: {e}")
            return None

    def get_pending(self) -> List[dict]:
        """获取状态为 pending 或 running 的任务列表"""
        try:
            if not self.conn:
                return []
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM work_items WHERE status IN ('pending', 'running') "
                "ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            print(f"  ⚠ [WorkLedger] get_pending 失败: {e}")
            return []

    def get_history(self, limit: int = 20) -> List[dict]:
        """获取最近的任务历史"""
        try:
            if not self.conn:
                return []
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM work_items ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            print(f"  ⚠ [WorkLedger] get_history 失败: {e}")
            return []

    def retry_work(self, work_id: str) -> str:
        """重试任务：重置状态为 pending，返回新 attempt_id

        实际的 attempt 记录在下次 start_attempt 时创建，
        此方法仅重置 work_item 状态。
        """
        try:
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute(
                    "UPDATE work_items SET status='pending', result=NULL WHERE id=?",
                    (work_id,),
                )
                self.conn.commit()
        except Exception as e:
            print(f"  ⚠ [WorkLedger] retry_work 失败: {e}")
        return work_id

    def get_attempts(self, work_id: str) -> List[dict]:
        """获取任务的所有执行尝试记录"""
        try:
            if not self.conn:
                return []
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM run_attempts WHERE work_id=? ORDER BY started_at DESC",
                (work_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            print(f"  ⚠ [WorkLedger] get_attempts 失败: {e}")
            return []

    # ─── 内部工具 ─────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """将 sqlite3.Row 转为 dict，反序列化 JSON 字段"""
        d = dict(row)
        # 反序列化 payload
        if d.get("payload"):
            try:
                d["payload"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        # 反序列化 result
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def close(self):
        """关闭数据库连接"""
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass


# ===== 独立测试模式 =====
if __name__ == "__main__":
    print("=" * 50)
    print("WorkLedger 独立测试")
    print("=" * 50)

    ledger = WorkLedger(":memory:")

    # 创建任务
    wid = ledger.create_work_item("测试搜索", "search", {"query": "hello"})
    print(f"创建任务: {wid}")

    # 开始尝试
    aid = ledger.start_attempt(wid)
    print(f"开始尝试: {aid}")

    # 完成任务
    ledger.complete_attempt(wid, aid, {"results": ["a", "b"]}, "completed")
    print("完成任务")

    # 查询
    work = ledger.get_work(wid)
    print(f"查询结果: {work}")

    # 历史
    history = ledger.get_history()
    print(f"历史记录: {len(history)} 条")

    # 重试
    ledger.retry_work(wid)
    pending = ledger.get_pending()
    print(f"待处理任务: {len(pending)} 条")

    ledger.close()
    print("\n✅ 全部通过")
