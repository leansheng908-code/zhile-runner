#!/usr/bin/env python3
"""
P0.46① 自进化Skills系统 — 对话轨迹自动沉淀为可复用技能

在对话过程中自动追踪工具调用序列，当单次对话中工具调用超过阈值时，
调用LLM分析执行轨迹，生成结构化的Markdown技能文件。生成的技能可被
注入system prompt供后续对话复用，同时支持基于使用效果的评估与更新。

技能文件存储在 skills/ 目录下，格式为 .md，包含：
  - 目标 (Goal)
  - 步骤 (Steps)
  - 工具序列 (Tool Sequence)
  - 关键决策点 (Key Decision Points)
  - 评估记录 (Evaluation Log)

依赖：requests（与 llm_provider.py 一致的 HTTP 调用风格）
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# ─── 常量 ──────────────────────────────────────────────

SKILLS_DIR = Path(__file__).parent / "skills"
"""技能文件存储目录"""

TOOL_CALL_THRESHOLD = 5
"""单次对话工具调用次数阈值，超过则触发技能生成"""

LLM_BASE_URL = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-v4-flash"
LLM_TIMEOUT = 60
"""LLM 请求超时（秒）"""

MAX_CHECKPOINT_AGE_DAYS = 30
"""技能文件最大保留天数，超过则可在清理时移除"""

SKILL_FILE_PREFIX = "skill_"
"""技能文件名前缀"""


class SkillEvolution:
    """自进化技能系统。

    在对话过程中自动追踪工具调用，当调用次数达到阈值时，
    通过LLM分析执行轨迹并生成可复用的Markdown技能文件。

    Attributes:
        llm_config: LLM 配置字典（api_key, base_url, model）。
        skills_dir: 技能文件存储目录。
        tool_calls: 当前对话的工具调用记录列表。
        skills_registry: 已加载技能的注册表。
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: str = "config.json",
    ) -> None:
        """初始化技能进化系统。

        Args:
            config: 可选的配置字典。若提供则直接使用，否则从 config_path 读取。
            config_path: 配置文件路径，默认为当前目录下的 config.json。
        """
        # 加载配置
        if config is None:
            config = self._load_config(config_path)

        # LLM 配置：优先环境变量，其次 config.json
        llm_cfg = config.get("llm", {})
        self.api_key: str = os.environ.get(
            "DEEPSEEK_API_KEY", llm_cfg.get("api_key", "")
        )
        self.base_url: str = llm_cfg.get("base_url", LLM_BASE_URL)
        self.model: str = llm_cfg.get("model", LLM_MODEL)

        # 技能目录
        self.skills_dir: Path = Path(
            config.get("skill_evolution", {}).get("dir", SKILLS_DIR)
        )
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 运行时状态
        self.tool_calls: List[Dict[str, Any]] = []
        self.skills_registry: Dict[str, Dict[str, Any]] = {}
        self._last_loaded_skills: List[str] = []  # 上次加载的技能名列表

        # 加载已有技能
        self._load_skills_internal()

    # ─── 配置加载 ──────────────────────────────────────────

    @staticmethod
    def _load_config(config_path: str) -> Dict[str, Any]:
        """从 JSON 文件加载配置。

        Args:
            config_path: 配置文件路径。

        Returns:
            配置字典。若文件不存在或解析失败，返回空字典。
        """
        try:
            path = Path(config_path)
            if not path.is_absolute():
                path = Path(__file__).parent / path
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    # ─── 工具调用追踪 ──────────────────────────────────────

    def track_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
    ) -> None:
        """记录一次工具调用。

        在对话过程中每次调用工具时调用此方法，系统会自动累积调用记录，
        当记录数量超过阈值时可触发技能生成。

        Args:
            tool_name: 工具名称，如 "web_search"、"code_executor"。
            args: 传递给工具的参数字典。
            result: 工具返回的结果（任意类型）。
        """
        self.tool_calls.append(
            {
                "tool": tool_name,
                "args": args,
                "result_summary": self._summarize_result(result),
                "timestamp": datetime.now().isoformat(),
            }
        )

    @staticmethod
    def _summarize_result(result: Any, max_len: int = 200) -> str:
        """将工具结果摘要为字符串。

        Args:
            result: 工具返回结果。
            max_len: 摘要最大长度。

        Returns:
            结果的字符串摘要。
        """
        try:
            text = str(result)
        except Exception:
            text = "<unrepresentable result>"
        if len(text) > max_len:
            text = text[:max_len] + "..."
        return text

    def should_generate_skill(self) -> bool:
        """判断是否应该生成新技能。

        当单次对话中工具调用次数超过阈值（默认5次）时返回 True。

        Returns:
            是否应触发技能生成。
        """
        return len(self.tool_calls) > TOOL_CALL_THRESHOLD

    # ─── 技能生成 ──────────────────────────────────────────

    def generate_skill(
        self, conversation_context: List[Dict[str, Any]]
    ) -> Optional[str]:
        """调用 LLM 分析执行轨迹，生成 Markdown 技能文件。

        将工具调用序列和对话上下文发送给 LLM，让模型分析执行模式，
        提炼出可复用的技能，并生成结构化的 Markdown 文件。

        Args:
            conversation_context: 对话上下文消息列表，
                格式为 [{"role": "user"/"assistant", "content": "..."}]。

        Returns:
            生成的技能文件路径，若生成失败则返回 None。
        """
        if not self.tool_calls:
            return None

        # 构造 LLM 提示
        prompt = self._build_generation_prompt(conversation_context)

        # 调用 LLM
        try:
            skill_content = self._call_llm(prompt)
        except Exception as e:
            print(f"[SkillEvolution] LLM 调用失败: {e}")
            return None

        if not skill_content or not skill_content.strip():
            return None

        # 生成技能名称
        skill_name = self._derive_skill_name(skill_content)

        # 写入文件
        skill_path = self.skills_dir / f"{SKILL_FILE_PREFIX}{skill_name}.md"
        try:
            with open(skill_path, "w", encoding="utf-8") as f:
                f.write(skill_content)
        except OSError as e:
            print(f"[SkillEvolution] 写入技能文件失败: {e}")
            return None

        # 注册到内存
        self.skills_registry[skill_name] = {
            "file": str(skill_path),
            "created": datetime.now().isoformat(),
            "usage_count": 0,
            "success_count": 0,
            "fail_count": 0,
        }

        # 清空当前对话的工具调用记录
        self.tool_calls.clear()

        print(f"[SkillEvolution] 新技能已生成: {skill_path}")
        return str(skill_path)

    def _build_generation_prompt(
        self, conversation_context: List[Dict[str, Any]]
    ) -> str:
        """构造发送给 LLM 的技能生成提示。

        Args:
            conversation_context: 对话上下文消息列表。

        Returns:
            完整的 prompt 字符串。
        """
        # 格式化工具调用轨迹
        tool_trace_lines: List[str] = []
        for i, tc in enumerate(self.tool_calls, 1):
            tool_trace_lines.append(
                f"  {i}. 工具: {tc['tool']}\n"
                f"     参数: {json.dumps(tc['args'], ensure_ascii=False, default=str)}\n"
                f"     结果摘要: {tc['result_summary']}\n"
                f"     时间: {tc['timestamp']}"
            )
        tool_trace = "\n".join(tool_trace_lines) or "  (无工具调用记录)"

        # 格式化对话上下文（截取最后 10 轮）
        recent_msgs = conversation_context[-10:] if conversation_context else []
        conv_lines: List[str] = []
        for msg in recent_msgs:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False, default=str)
            conv_lines.append(f"  [{role}] {content[:300]}")
        conv_summary = "\n".join(conv_lines) or "  (无对话上下文)"

        return f"""你是一个技能分析专家。请分析以下工具调用轨迹和对话上下文，
提炼出一个可复用的技能，并以 Markdown 格式输出。

## 工具调用轨迹
{tool_trace}

## 对话上下文（最近10轮）
{conv_summary}

请按以下格式输出技能文件内容（纯 Markdown，不要代码块包裹）：

# 技能名称：简短描述

## 目标
这个技能要解决什么问题，适用什么场景。

## 步骤
1. 第一步...
2. 第二步...
3. ...

## 工具序列
1. 工具A — 用途说明
2. 工具B — 用途说明
3. ...

## 关键决策点
- 决策点1：在什么情况下选择什么路径
- 决策点2：...

## 注意事项
- 常见陷阱和规避方法

请直接输出 Markdown 内容，不要有任何额外说明。"""

    def _call_llm(self, prompt: str) -> str:
        """调用 DeepSeek API 生成技能内容。

        Args:
            prompt: 发送给 LLM 的完整提示。

        Returns:
            LLM 生成的技能内容字符串。

        Raises:
            ConnectionError: 无法连接 API 服务器。
            TimeoutError: API 请求超时。
            Exception: API 返回错误。
        """
        if not self.api_key:
            raise ValueError("API Key 未配置，请设置环境变量 DEEPSEEK_API_KEY 或在 config.json 中配置 llm.api_key")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 2048,
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 API 服务器，请检查网络")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{LLM_TIMEOUT}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        data = response.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _derive_skill_name(content: str) -> str:
        """从技能内容中提取技能名称。

        尝试从 Markdown 标题中提取名称，提取失败则使用时间戳。

        Args:
            content: 技能 Markdown 内容。

        Returns:
            技能名称字符串（仅含小写字母、数字、下划线）。
        """
        # 尝试从标题提取
        match = re.search(r"^#\s+技能名称[：:]\s*(.+)$", content, re.MULTILINE)
        if match:
            name = match.group(1).strip()
            # 转为安全文件名
            name = re.sub(r"[^\w\u4e00-\u9fff]", "_", name)
            name = re.sub(r"_+", "_", name).strip("_").lower()
            if name:
                return name

        # 回退到时间戳
        return f"auto_{int(time.time())}"

    # ─── 技能加载 ──────────────────────────────────────────

    def load_skills(self) -> str:
        """加载已有技能文件，返回可注入 system prompt 的文本。

        扫描技能目录下所有 .md 文件，将内容拼接为一段文本，
        可直接追加到 system prompt 中供后续对话使用。

        Returns:
            拼接后的技能文本。若无技能文件则返回空字符串。
        """
        self._load_skills_internal()

        if not self.skills_registry:
            self._last_loaded_skills = []
            return ""

        parts: List[str] = ["", "## 已积累的技能经验", ""]
        loaded: List[str] = []
        for name, info in self.skills_registry.items():
            skill_path = Path(info["file"])
            if not skill_path.exists():
                continue
            try:
                content = skill_path.read_text(encoding="utf-8")
                parts.append(f"### 技能：{name}\n\n{content}\n")
                loaded.append(name)
            except OSError:
                continue

        self._last_loaded_skills = loaded

        return "\n".join(parts) if len(parts) > 3 else ""

    def _load_skills_internal(self) -> None:
        """内部方法：扫描技能目录并更新注册表。"""
        self.skills_registry.clear()
        for md_file in sorted(self.skills_dir.glob("*.md")):
            name = md_file.stem
            if name.startswith(SKILL_FILE_PREFIX):
                name = name[len(SKILL_FILE_PREFIX):]
            self.skills_registry[name] = {
                "file": str(md_file),
                "created": datetime.fromtimestamp(
                    md_file.stat().st_mtime
                ).isoformat(),
                "usage_count": 0,
                "success_count": 0,
                "fail_count": 0,
            }

    # ─── 技能评估 ──────────────────────────────────────────

    def evaluate_skill(self, skill_name: str, success: bool) -> None:
        """评估技能使用效果。

        记录技能的使用成功/失败次数，写入技能文件的评估日志段落。

        Args:
            skill_name: 技能名称。
            success: 本次使用是否成功。
        """
        if skill_name not in self.skills_registry:
            # 尝试带前缀匹配
            full_name = f"{SKILL_FILE_PREFIX}{skill_name}"
            skill_path = self.skills_dir / f"{full_name}.md"
        else:
            skill_path = Path(self.skills_registry[skill_name]["file"])

        if not skill_path.exists():
            print(f"[SkillEvolution] 技能文件不存在: {skill_name}")
            return

        # 更新注册表计数
        if skill_name in self.skills_registry:
            info = self.skills_registry[skill_name]
            info["usage_count"] += 1
            if success:
                info["success_count"] += 1
            else:
                info["fail_count"] += 1

        # 追加评估日志到技能文件
        try:
            content = skill_path.read_text(encoding="utf-8")
            log_entry = (
                f"\n---\n**评估记录** — {datetime.now().isoformat()}: "
                f"{'✅ 成功' if success else '❌ 失败'}\n"
            )

            # 检查是否已有评估记录段落
            if "## 评估记录" not in content:
                content += "\n\n## 评估记录\n" + log_entry
            else:
                content += log_entry

            skill_path.write_text(content, encoding="utf-8")
        except OSError as e:
            print(f"[SkillEvolution] 更新评估记录失败: {e}")

    # ─── 技能更新 ──────────────────────────────────────────

    def update_skill(self, skill_name: str, new_content: str) -> bool:
        """发现更优解时更新技能内容。

        用新内容覆盖技能文件，同时保留评估记录。

        Args:
            skill_name: 技能名称。
            new_content: 新的技能内容（Markdown 格式）。

        Returns:
            是否更新成功。
        """
        # 定位技能文件
        skill_path = self._find_skill_file(skill_name)
        if skill_path is None:
            print(f"[SkillEvolution] 技能不存在，无法更新: {skill_name}")
            return False

        try:
            old_content = skill_path.read_text(encoding="utf-8")

            # 提取旧的评估记录
            eval_section = ""
            if "## 评估记录" in old_content:
                idx = old_content.index("## 评估记录")
                eval_section = old_content[idx:]

            # 合并新内容和评估记录
            final_content = new_content.rstrip()
            if eval_section:
                final_content += "\n\n" + eval_section

            skill_path.write_text(final_content, encoding="utf-8")
            print(f"[SkillEvolution] 技能已更新: {skill_name}")
            return True
        except OSError as e:
            print(f"[SkillEvolution] 更新技能文件失败: {e}")
            return False

    def _find_skill_file(self, skill_name: str) -> Optional[Path]:
        """查找技能文件路径。

        Args:
            skill_name: 技能名称（可带或不带前缀）。

        Returns:
            技能文件路径，若不存在则返回 None。
        """
        # 尝试多种文件名
        candidates = [
            self.skills_dir / f"{SKILL_FILE_PREFIX}{skill_name}.md",
            self.skills_dir / f"{skill_name}.md",
        ]
        # 从注册表查找
        if skill_name in self.skills_registry:
            candidates.insert(0, Path(self.skills_registry[skill_name]["file"]))

        for path in candidates:
            if path.exists():
                return path
        return None

    # ─── 重置 ──────────────────────────────────────────────

    def reset_tool_calls(self) -> None:
        """重置当前对话的工具调用记录。

        在新对话开始时调用，清空上一轮的调用记录。
        """
        self.tool_calls.clear()

    # ─── 工具方法 ──────────────────────────────────────────

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有已注册的技能。

        Returns:
            技能信息列表，每项包含名称、文件路径、创建时间、使用统计。
        """
        self._load_skills_internal()
        result: List[Dict[str, Any]] = []
        for name, info in self.skills_registry.items():
            result.append({"name": name, **info})
        return result

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """获取指定技能的完整内容。

        Args:
            skill_name: 技能名称。

        Returns:
            技能文件内容字符串，若不存在则返回 None。
        """
        skill_path = self._find_skill_file(skill_name)
        if skill_path is None or not skill_path.exists():
            return None
        try:
            return skill_path.read_text(encoding="utf-8")
        except OSError:
            return None

    # ─── 清理与迭代 ──────────────────────────────────────────

    def cleanup_old_skills(self) -> int:
        """清理过期且低效的技能文件。

        删除同时满足以下条件的技能：
          1. 文件修改时间超过 MAX_CHECKPOINT_AGE_DAYS 天
          2. 使用次数 >= 3 且成功率 < 30%

        Returns:
            被删除的技能数量。
        """
        self._load_skills_internal()
        now = time.time()
        max_age_sec = MAX_CHECKPOINT_AGE_DAYS * 86400
        removed = 0

        for name in list(self.skills_registry.keys()):
            info = self.skills_registry[name]
            skill_path = Path(info["file"])
            if not skill_path.exists():
                continue

            # 检查文件年龄
            try:
                file_age = now - skill_path.stat().st_mtime
            except OSError:
                continue
            if file_age < max_age_sec:
                continue  # 还没过期

            # 检查使用效果
            usage = info.get("usage_count", 0)
            success = info.get("success_count", 0)
            if usage < 3:
                continue  # 使用次数不够，不判断效果

            success_rate = success / usage if usage > 0 else 0
            if success_rate >= 0.3:
                continue  # 成功率还行，保留

            # 删除
            try:
                skill_path.unlink()
                del self.skills_registry[name]
                removed += 1
                print(f"[SkillEvolution] 清理低效技能: {name} "
                      f"(成功率 {success_rate:.0%})")
            except OSError:
                pass

        return removed

    def get_low_performing_skills(self, min_usage: int = 3,
                                  max_success_rate: float = 0.5
                                  ) -> List[Dict[str, Any]]:
        """获取表现不佳的技能列表。

        Args:
            min_usage: 最少使用次数（低于此值不判断）。
            max_success_rate: 成功率上限（低于此值视为不佳）。

        Returns:
            低效技能信息列表，每项含 name, usage_count, success_rate。
        """
        self._load_skills_internal()
        result: List[Dict[str, Any]] = []
        for name, info in self.skills_registry.items():
            usage = info.get("usage_count", 0)
            if usage < min_usage:
                continue
            success = info.get("success_count", 0)
            rate = success / usage if usage > 0 else 0
            if rate < max_success_rate:
                result.append({
                    "name": name,
                    "usage_count": usage,
                    "success_rate": rate,
                })
        return result

    def evaluate_last_loaded(self, success: bool) -> None:
        """评估上次加载的所有技能的使用效果。

        在对话结束后调用，根据对话是否成功来更新技能评估记录。

        Args:
            success: 本次对话是否成功完成。
        """
        for name in self._last_loaded_skills:
            try:
                self.evaluate_skill(name, success)
            except Exception:
                pass
        # 评估完清空，避免重复计分
        self._last_loaded_skills = []