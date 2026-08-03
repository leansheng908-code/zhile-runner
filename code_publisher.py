#!/usr/bin/env python3
"""
知乐代码发布与监护人核验 — P0.27

运行器自主生成的代码不直接合入主分支，而是：
  1. 推到 auto/{timestamp} 分支
  2. L1自动扫描（正则检测硬编码密钥/危险命令/AI代码特征）
  3. 生成核验请求，等待监护人（主Agent）审查
  4. 通过→合入主分支；驳回→附修改建议

安全约束：
  - 推送权限仅限创建分支+推送文件，不含删除/合并
  - 核验通过前代码不被运行器自动加载
  - 主Agent核验是强制环节，不可跳过
  - 所有提交记录永久保留在分支历史中
"""

import json
import re
import base64
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class CodePublisher:
    """代码发布与核验系统"""

    def __init__(self, config: dict = None):
        config = config or {}
        self.token = config.get("github_token", "")
        self.owner = config.get("github_owner", "your-github-username")
        self.repo = config.get("github_repo", "zhile-dna")
        self.base_branch = config.get("base_branch", "main")
        self.api_base = f"https://api.github.com/repos/{self.owner}/{self.repo}"

        # 核验队列
        self.queue_file = Path(config.get("queue_file", "memory/code_review_queue.json"))
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.queue: List[dict] = self._load_queue()

    # ─── 发布 ───────────────────────────────────

    def publish(self, files: List[Dict[str, str]],
                description: str = "",
                author: str = "zhile-runner") -> dict:
        """
        将文件推送到新分支，创建核验请求。
        
        Args:
            files: [{"path": "runner/xxx.py", "content": "..."}]
            description: 本次提交描述
            author: 提交者标识
            
        Returns:
            {success, branch, request_id, audit_result}
        """
        if not self.token:
            return {"success": False, "error": "未配置GitHub Token"}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        branch_name = f"auto/{timestamp}"

        # Step 1: 获取主分支最新SHA
        try:
            resp = requests.get(
                f"{self.api_base}/git/refs/heads/{self.base_branch}",
                headers=self._headers(), timeout=15)
            if resp.status_code != 200:
                return {"success": False, "error": f"获取主分支失败: {resp.status_code}"}
            base_sha = resp.json()["object"]["sha"]
        except Exception as e:
            return {"success": False, "error": f"获取主分支SHA失败: {e}"}

        # Step 2: 创建新分支
        try:
            resp = requests.post(
                f"{self.api_base}/git/refs",
                headers=self._headers(), timeout=15,
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha})
            if resp.status_code not in (200, 201):
                return {"success": False, "error": f"创建分支失败: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"创建分支失败: {e}"}

        # Step 3: 推送文件
        pushed = []
        for f in files:
            fpath = f["path"]
            fcontent = f["content"]
            try:
                content_b64 = base64.b64encode(fcontent.encode("utf-8")).decode("ascii")
                resp = requests.put(
                    f"{self.api_base}/contents/{fpath}",
                    headers=self._headers(), timeout=30,
                    json={
                        "message": f"auto: {description} [{author}]",
                        "content": content_b64,
                        "branch": branch_name,
                    })
                if resp.status_code in (200, 201):
                    pushed.append(fpath)
                else:
                    pushed.append(f"{fpath} (FAILED: {resp.status_code})")
            except Exception as e:
                pushed.append(f"{fpath} (ERROR: {e})")

        # Step 4: L1自动审计
        audit = self.l1_audit(files)

        # Step 5: 创建核验请求
        request_id = f"rev_{timestamp}"
        review_request = {
            "id": request_id,
            "branch": branch_name,
            "files": [f["path"] for f in files],
            "description": description,
            "author": author,
            "timestamp": datetime.now().isoformat(),
            "status": "pending",  # pending → approved → merged | rejected
            "l1_audit": audit,
            "review_notes": "",
        }
        self.queue.append(review_request)
        self._save_queue()

        return {
            "success": True,
            "branch": branch_name,
            "request_id": request_id,
            "pushed_files": pushed,
            "l1_audit": audit,
        }

    # ─── L1 自动审计 ───────────────────────────

    def l1_audit(self, files: List[Dict[str, str]]) -> dict:
        """
        L1自动扫描：正则检测常见AI代码漏洞
        参考 DeepSec Shield L1 + VibeCoding研究6类漏洞
        """
        issues = []

        # 检测规则
        rules = [
            # 1. 硬编码密钥
            (r'(?:api_key|secret|token|password|passwd)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{20,}',
             "CRITICAL", "疑似硬编码密钥"),
            (r'(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,})',
             "CRITICAL", "疑似API Key明文"),

            # 2. 危险文件操作
            (r'os\.system\s*\(\s*["\'].*rm\s+-rf', "CRITICAL", "危险rm -rf命令"),
            (r'shutil\.rmtree\s*\(', "WARNING", "递归删除目录"),
            (r'os\.remove\s*\(\s*["\']/', "WARNING", "删除根路径文件"),

            # 3. 危险网络操作
            (r'subprocess\.(?:call|run|Popen)\s*\(.*shell\s*=\s*True',
             "WARNING", "shell=True可能命令注入"),
            (r'eval\s*\(\s*.*input', "CRITICAL", "eval用户输入"),

            # 4. AI代码特征（幻觉包名）
            (r'import\s+(?:ai_magic|smart_utils|auto_helper|intelligent_core)',
             "WARNING", "疑似幻觉包名"),
            (r'from\s+(?:magical_utils|super_ai|brain_core)\s+import',
             "WARNING", "疑似幻觉包名"),

            # 5. 不安全配置
            (r'verify\s*=\s*False', "INFO", "SSL验证被禁用"),
            (r'allow_unsafe\s*=\s*True', "WARNING", "不安全标志被启用"),

            # 6. 干细胞保护检查
            (r'(?:system_prompt|dna_loader)\.py',
             "CRITICAL", "触碰干细胞文件"),
        ]

        for f in files:
            fpath = f["path"]
            fcontent = f.get("content", "")

            # 跳过非Python文件的部分检查
            is_py = fpath.endswith(".py")

            for pattern, severity, desc in rules:
                matches = re.finditer(pattern, fcontent, re.IGNORECASE)
                for m in matches:
                    line_num = fcontent[:m.start()].count("\n") + 1
                    context = fcontent.split("\n")[line_num - 1].strip()[:100] if line_num <= len(fcontent.split("\n")) else ""
                    issues.append({
                        "file": fpath,
                        "line": line_num,
                        "severity": severity,
                        "description": desc,
                        "context": context,
                    })

        # 统计
        critical = sum(1 for i in issues if i["severity"] == "CRITICAL")
        warnings = sum(1 for i in issues if i["severity"] == "WARNING")
        info = sum(1 for i in issues if i["severity"] == "INFO")

        return {
            "total_issues": len(issues),
            "critical": critical,
            "warnings": warnings,
            "info": info,
            "auto_block": critical > 0,  # 有CRITICAL级别问题自动拦截
            "issues": issues,
        }

    # ─── 核验管理 ───────────────────────────────

    def get_pending(self) -> List[dict]:
        """获取待核验请求"""
        return [q for q in self.queue if q["status"] == "pending"]

    def approve(self, request_id: str, notes: str = "") -> dict:
        """监护人批准核验请求，自动合并到主分支"""
        req = self._find_request(request_id)
        if not req:
            return {"success": False, "error": "核验请求不存在"}
        if req["status"] != "pending":
            return {"success": False, "error": f"请求状态非pending: {req['status']}"}

        # 检查L1审计是否有CRITICAL未解决
        if req.get("l1_audit", {}).get("auto_block"):
            return {"success": False, "error": "存在CRITICAL级别问题，无法批准"}

        # 合并到主分支
        try:
            resp = requests.post(
                f"{self.api_base}/merges",
                headers=self._headers(), timeout=30,
                json={
                    "base": self.base_branch,
                    "head": req["branch"],
                    "commit_message": f"guardian: approve {request_id} - {req.get('description', '')}",
                })
            if resp.status_code not in (200, 201):
                return {"success": False, "error": f"合并失败: {resp.status_code} {resp.text[:200]}"}
        except Exception as e:
            return {"success": False, "error": f"合并失败: {e}"}

        req["status"] = "approved"
        req["review_notes"] = notes
        req["merged_at"] = datetime.now().isoformat()
        self._save_queue()

        return {"success": True, "merged": True, "request_id": request_id}

    def reject(self, request_id: str, reason: str = "") -> dict:
        """监护人驳回核验请求"""
        req = self._find_request(request_id)
        if not req:
            return {"success": False, "error": "核验请求不存在"}
        if req["status"] != "pending":
            return {"success": False, "error": f"请求状态非pending: {req['status']}"}

        req["status"] = "rejected"
        req["review_notes"] = reason
        req["rejected_at"] = datetime.now().isoformat()
        self._save_queue()

        return {"success": True, "rejected": True, "reason": reason}

    # ─── 状态报告 ───────────────────────────────

    def get_status(self) -> dict:
        pending = self.get_pending()
        return {
            "total_requests": len(self.queue),
            "pending": len(pending),
            "approved": sum(1 for q in self.queue if q["status"] == "approved"),
            "rejected": sum(1 for q in self.queue if q["status"] == "rejected"),
            "last_request": self.queue[-1].get("id", "") if self.queue else "",
        }

    def get_review_detail(self, request_id: str = None) -> dict:
        """获取核验详情"""
        if request_id:
            req = self._find_request(request_id)
            return req if req else {"error": "不存在"}
        # 返回最近的pending
        pending = self.get_pending()
        return pending[0] if pending else {"message": "无待核验请求"}

    # ─── 内部方法 ───────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _find_request(self, request_id: str) -> Optional[dict]:
        for q in self.queue:
            if q["id"] == request_id:
                return q
        return None

    def _load_queue(self) -> list:
        if not self.queue_file.exists():
            return []
        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []

    def _save_queue(self):
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(self.queue, f, ensure_ascii=False, indent=2)
