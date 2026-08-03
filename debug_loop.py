"""
P0.26 Phase 2: 迭代调试循环

在沙箱中执行代码 → 失败则读取报错 → LLM修复 → 重新执行 → 循环到跑通或达到上限。
每轮的历史都会传递给LLM，避免反复踩同一个坑。
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

from code_executor import CodeExecutor, ExecutionResult


@dataclass
class DebugIteration:
    """单次调试迭代记录"""
    iteration: int = 0
    code: str = ""
    result: Optional[ExecutionResult] = None
    fix_description: str = ""

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "code": self.code[:500],
            "success": self.result.success if self.result else False,
            "error_type": self.result.error_type if self.result else "",
            "error_message": self.result.error_message if self.result else "",
            "fix_description": self.fix_description,
        }


@dataclass
class DebugResult:
    """调试循环最终结果"""
    success: bool = False
    final_code: str = ""
    iterations: int = 0
    history: List[DebugIteration] = field(default_factory=list)
    final_output: str = ""
    total_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "final_code": self.final_code[:1000],
            "iterations": self.iterations,
            "history": [h.to_dict() for h in self.history],
            "final_output": self.final_output[:500],
            "total_time": round(self.total_time, 3),
        }


class DebugLoop:
    """迭代调试循环"""

    def __init__(self, executor: CodeExecutor, llm_provider=None,
                 config: dict = None):
        self.executor = executor
        self.llm = llm_provider
        config = config or {}
        self.max_iterations = config.get("max_iterations", 5)
        self.history_file = config.get("history_file",
                                       "memory/debug_history.json")

    # ─── 公开接口 ──────────────────────────────

    def run(self, code: str, max_iterations: int = None,
            timeout: int = None) -> DebugResult:
        """运行调试循环

        Args:
            code: 初始代码
            max_iterations: 最大迭代次数（不含首次执行）
            timeout: 每次执行超时

        Returns:
            DebugResult
        """
        max_iter = max_iterations or self.max_iterations
        result = DebugResult(final_code=code)
        t0 = time.time()

        current_code = code

        for i in range(max_iter + 1):  # +1: 首次执行不算迭代
            iteration = DebugIteration(iteration=i, code=current_code)

            # 执行
            exec_result = self.executor.execute(current_code, timeout=timeout)
            iteration.result = exec_result

            # 成功 → 收工
            if exec_result.success:
                result.success = True
                result.final_code = current_code
                result.final_output = exec_result.stdout
                result.history.append(iteration)
                break

            # 记录失败
            result.history.append(iteration)

            # 已达最大轮次
            if i >= max_iter:
                result.final_code = current_code
                break

            # SecurityBlock 不需要重试
            if exec_result.error_type == "SecurityBlock":
                result.final_code = current_code
                break

            # 用LLM修复
            if not self.llm:
                break

            fixed_code = self._generate_fix(
                current_code, exec_result, result.history
            )

            if fixed_code is None or fixed_code == current_code:
                # LLM无法修复 或 修复后代码没变
                break

            current_code = fixed_code
            iteration.fix_description = f"第{i+1}轮修复已生成"

        result.iterations = len(result.history)
        result.total_time = round(time.time() - t0, 3)

        # 保存历史
        self._save_history(result)

        return result

    def get_stats(self) -> dict:
        """获取调试循环统计"""
        try:
            history_path = Path(self.history_file)
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    histories = json.load(f)
                total = len(histories)
                successes = sum(1 for h in histories if h.get("success"))
                avg_iter = (sum(h.get("iterations", 0) for h in histories)
                            / max(total, 1))
                return {
                    "enabled": True,
                    "total_runs": total,
                    "successes": successes,
                    "success_rate": f"{successes}/{total}",
                    "avg_iterations": round(avg_iter, 1),
                    "max_iterations": self.max_iterations,
                }
        except Exception:
            pass
        return {"enabled": True, "total_runs": 0}

    def get_history(self, limit: int = 10) -> list:
        """获取历史记录"""
        try:
            history_path = Path(self.history_file)
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    histories = json.load(f)
                return histories[-limit:]
        except Exception:
            pass
        return []

    # ─── 内部方法 ──────────────────────────────

    def _generate_fix(self, code: str, error: ExecutionResult,
                      history: list) -> Optional[str]:
        """用LLM生成修复版本"""
        # 构建历史上下文（最近3轮）
        history_text = ""
        if len(history) > 1:
            history_text = "\n\n## 之前的尝试（避免重复踩坑）\n"
            for h in history[-3:]:
                h_result = h.result
                history_text += (
                    f"第{h.iteration}轮: {h_result.error_type}: "
                    f"{h_result.error_message}\n"
                )
                if h.fix_description:
                    history_text += f"  → {h.fix_description}\n"

        stdout_snippet = error.stdout[:500] if error.stdout else "(无输出)"
        stderr_snippet = (error.stderr[:800] if error.stderr
                          else error.error_message)

        prompt = f"""你是Python代码调试专家。下面代码执行失败，请修复。

## 原始代码
```python
{code[:2000]}
```

## 错误信息
- 错误类型: {error.error_type}
- 错误消息: {error.error_message}
- stderr:
```
{stderr_snippet}
```

## stdout（部分）
```
{stdout_snippet}
```
{history_text}
## 要求
1. 只输出修复后的完整代码，用```python```包裹
2. 保持原有功能不变，只修复错误
3. 不要使用os/subprocess/socket等危险模块
4. 不要解释，只给代码"""

        messages = [
            {"role": "system",
             "content": "你是Python调试专家，只输出修复后的代码，不要解释。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = ""
            for chunk in self.llm.chat(messages, stream=True):
                response += chunk
            return self._extract_code(response)
        except Exception:
            return None

    def _extract_code(self, text: str) -> Optional[str]:
        """从LLM回复中提取代码块"""
        if "```python" in text:
            start = text.index("```python") + len("```python")
            remaining = text[start:]
            if "```" in remaining:
                end = remaining.index("```")
                return remaining[:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            remaining = text[start:]
            if "```" in remaining:
                end = remaining.index("```")
                return remaining[:end].strip()
        # 无代码块但看起来像代码
        if any(kw in text for kw in ("def ", "import ", "print", "class ")):
            return text.strip()
        return None

    def _save_history(self, result: DebugResult):
        """保存调试历史"""
        try:
            history_path = Path(self.history_file)
            history_path.parent.mkdir(parents=True, exist_ok=True)

            histories = []
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    histories = json.load(f)

            histories.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                **result.to_dict(),
            })

            # 只保留最近50条
            if len(histories) > 50:
                histories = histories[-50:]

            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(histories, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
