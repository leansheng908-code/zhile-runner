#!/usr/bin/env python3
"""
P0.46① 自进化Skills系统 v4 — 对话轨迹自动沉淀 + 三层分层 + 智能匹配 + 懒加载组合 + T1会话粘性 + 状态持久化 + 用户管理

v4 新增:
  - T1状态持久化：重启后恢复激活/冷却状态
  - 用户技能管理接口：list/info/disable/enable/remove
  - 禁用技能持久化：重启后保持禁用状态

v3 新增:
  - T1 无硬性注入上限，靠打分激活
  - T1 会话粘性: 激活态→场景结束→冷却态→下线 三阶段生命周期
  - T1 不参与自动组合，仅T2可组合
  - T2+T3 合计上限独立于T1

v2:
  - 三层技能架构: manual(手动T1) / auto(自进化T2) / composite(组合T3)
  - 多信号打分筛选: 关键词×3 + 触发示例×2 + 类别×1 + 频率×0.5
  - 懒加载组合: 同组技能共现3次自动触发组合
  - 自纠偏: 低效/零使用技能标记重生成
  - 技能元数据: .json sidecar (keywords/category/trigger_examples/tier/parents)

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
"""技能文件存储根目录"""

# 三层目录
TIER_DIRS = {
    "manual": "manual",      # T1: 手动安装
    "auto": "auto",          # T2: 自动生成
    "composite": "composite", # T3: 组合产物
}

TOOL_CALL_THRESHOLD = 5
"""单次对话工具调用次数阈值，超过则触发技能生成"""

LLM_BASE_URL = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-v4-flash"
LLM_TIMEOUT = 60

MAX_CHECKPOINT_AGE_DAYS = 30
"""T2技能文件最大保留天数"""

SKILL_FILE_PREFIX = "skill_"
"""技能文件名前缀"""

# ── 多信号打分权重 ──
WEIGHT_KEYWORD = 3.0       # 关键词精确命中
WEIGHT_TRIGGER = 2.0       # 触发示例重叠
WEIGHT_CATEGORY = 1.0      # 类别推断命中
WEIGHT_FREQUENCY = 0.5     # 使用频率加成
WEIGHT_NOVELTY = 2.0       # 新手加成

SCORE_THRESHOLD = 3.0      # 注入阈值
# T1 无硬性注入上限，靠打分+会话粘性管理
MAX_INJECT_T2 = 3          # T2每轮最多注入
MAX_INJECT_T3 = 1          # T3每轮最多注入
MAX_INJECT_T2T3 = 4        # T2+T3 合计上限
SMALL_POOL_THRESHOLD = 3   # 技能总数≤此值时全灌

# ── T1 会话粘性 ──
COOLING_ROUNDS = 10        # T1 冷却期轮数
SCENE_END_SIGNALS = [
    "不玩了", "结束", "好了", "换个话题", "算了", "就这样吧",
    "不聊了", "换一个", "退出", "完事了", "到此为止", "不打了",
    "下线了", "去忙了", "先这样", "结束吧", "不搞了",
]

# ── 懒加载组合 ──
COMPOSE_THRESHOLD = 3      # 共现次数达到此值触发组合
NOVELTY_BOOST_ROUNDS = 5   # 新技能前N轮获得新手加成

# ── 自纠偏 ──
REGEN_ZERO_USE_ROUNDS = 20 # 连续N轮未被选中→标记重生成
REGEN_LOW_SUCCESS_RATE = 0.3  # 成功率低于此值+使用≥3次→标记重生成

# ── 类别推断规则 ──
CATEGORY_RULES = [
    # (类别名, 匹配关键词列表)
    ("search", ["查", "搜索", "找", "看看", "查询", "最新", "新闻"]),
    ("finance", ["股", "基金", "行情", "涨", "跌", "大盘", "投资", "收益"]),
    ("writing", ["写", "总结", "报告", "文章", "文案", "草稿"]),
    ("analysis", ["分析", "对比", "评估", "优缺点", "比较"]),
    ("coding", ["代码", "脚本", "程序", "bug", "运行", "部署"]),
    ("chat", ["聊天", "推荐", "建议", "怎么办", "怎么样"]),
]

# ── 停用词（不计入触发示例重叠） ──
STOP_WORDS = set("的了是在我你有他她它们这那和与或但ifthea用于对给到从被把让说")


class SkillEvolution:
    """自进化技能系统 v2。

    三层分层 + 智能匹配 + 懒加载组合 + 自纠偏。

    Attributes:
        llm_config: LLM 配置字典。
        skills_dir: 技能文件存储根目录。
        tool_calls: 当前对话的工具调用记录列表。
        skills_registry: 已加载技能的注册表（含 tier/metadata）。
        cooccurrence: 技能共现计数字典。
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: str = "config.json",
    ) -> None:
        if config is None:
            config = self._load_config(config_path)

        llm_cfg = config.get("llm", {})
        self.api_key: str = os.environ.get(
            "DEEPSEEK_API_KEY", llm_cfg.get("api_key", "")
        )
        self.base_url: str = llm_cfg.get("base_url", LLM_BASE_URL)
        self.model: str = llm_cfg.get("model", LLM_MODEL)

        # 技能根目录
        self.skills_dir: Path = Path(
            config.get("skill_evolution", {}).get("dir", SKILLS_DIR)
        )
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 创建三层子目录
        for tier_name, subdir in TIER_DIRS.items():
            (self.skills_dir / subdir).mkdir(parents=True, exist_ok=True)

        # 运行时状态
        self.tool_calls: List[Dict[str, Any]] = []
        self.skills_registry: Dict[str, Dict[str, Any]] = {}
        self._last_loaded_skills: List[str] = []
        self.cooccurrence: Dict[str, int] = {}
        self._round_count: int = 0  # 总轮次计数（用于零使用检测）

        # T1 会话粘性状态
        self._t1_states: Dict[str, str] = {}         # skill_name -> "active" | "cooling"
        self._t1_cooling_rounds: Dict[str, int] = {}  # skill_name -> 已冷却轮数

        # 已禁用技能集合（用户手动禁用）
        self._disabled_skills: set = set()

        # 加载共现记录
        self._load_cooccurrence()

        # 加载T1状态和禁用列表（持久化恢复）
        self._load_t1_states()
        self._load_disabled_skills()

        # 加载已有技能
        self._load_skills_internal()

    # ─── 配置加载 ──────────────────────────────────────────

    @staticmethod
    def _load_config(config_path: str) -> Dict[str, Any]:
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
        try:
            text = str(result)
        except Exception:
            text = "<unrepresentable result>"
        if len(text) > max_len:
            text = text[:max_len] + "..."
        return text

    def should_generate_skill(self) -> bool:
        return len(self.tool_calls) > TOOL_CALL_THRESHOLD

    # ─── 技能生成 ──────────────────────────────────────────

    def generate_skill(
        self, conversation_context: List[Dict[str, Any]]
    ) -> Optional[str]:
        """调用 LLM 分析执行轨迹，生成 Markdown 技能文件 + 元数据 JSON。"""
        if not self.tool_calls:
            return None

        prompt = self._build_generation_prompt(conversation_context)

        try:
            raw_response = self._call_llm(prompt)
        except Exception as e:
            print(f"[SkillEvolution] LLM 调用失败: {e}")
            return None

        if not raw_response or not raw_response.strip():
            return None

        # 解析响应：分离 Markdown 内容和元数据
        skill_content, metadata = self._parse_skill_response(raw_response)

        # 生成技能名称
        skill_name = self._derive_skill_name(skill_content)

        # 写入 .md 文件到 auto/ 目录
        auto_dir = self.skills_dir / TIER_DIRS["auto"]
        skill_path = auto_dir / f"{SKILL_FILE_PREFIX}{skill_name}.md"
        try:
            with open(skill_path, "w", encoding="utf-8") as f:
                f.write(skill_content)
        except OSError as e:
            print(f"[SkillEvolution] 写入技能文件失败: {e}")
            return None

        # 写入 .json 元数据
        metadata["tier"] = "auto"
        metadata["parents"] = []
        metadata["novelty_boost_remaining"] = NOVELTY_BOOST_ROUNDS
        metadata["flagged_for_regen"] = False
        metadata["zero_use_rounds"] = 0
        self._save_metadata(skill_name, metadata, "auto")

        # 注册到内存
        self.skills_registry[skill_name] = {
            "file": str(skill_path),
            "tier": "auto",
            "created": datetime.now().isoformat(),
            "usage_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "metadata": metadata,
        }

        # 清空当前对话的工具调用记录
        self.tool_calls.clear()

        print(f"[SkillEvolution] 新技能已生成: {skill_path}")
        return str(skill_path)

    def _build_generation_prompt(
        self, conversation_context: List[Dict[str, Any]]
    ) -> str:
        tool_trace_lines: List[str] = []
        for i, tc in enumerate(self.tool_calls, 1):
            tool_trace_lines.append(
                f"  {i}. 工具: {tc['tool']}\n"
                f"     参数: {json.dumps(tc['args'], ensure_ascii=False, default=str)}\n"
                f"     结果摘要: {tc['result_summary']}\n"
                f"     时间: {tc['timestamp']}"
            )
        tool_trace = "\n".join(tool_trace_lines) or "  (无工具调用记录)"

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

请按以下格式输出（纯文本，不要代码块包裹）：

# 技能名称：简短描述

## 目标
这个技能要解决什么问题，适用什么场景。

## 步骤
1. 第一步...
2. 第二步...

## 工具序列
1. 工具A — 用途说明
2. 工具B — 用途说明

## 关键决策点
- 决策点1：在什么情况下选择什么路径

## 注意事项
- 常见陷阱和规避方法

---METADATA---
{{
  "keywords": ["5到8个关键词，每个至少2个字，覆盖用户可能的说法"],
  "category": "从以下选一个: search/finance/writing/analysis/coding/chat",
  "description": "一句话描述这个技能做什么",
  "trigger_examples": [
    "用户可能说的3种不同表达方式的示例消息",
    "示例2",
    "示例3"
  ]
}}

请直接输出，不要有任何额外说明。"""

    def _parse_skill_response(
        self, raw: str
    ) -> Tuple[str, Dict[str, Any]]:
        """将 LLM 响应分离为 Markdown 内容和元数据字典。"""
        # 查找分隔符
        delimiter = "---METADATA---"
        if delimiter in raw:
            parts = raw.split(delimiter, 1)
            md_content = parts[0].strip()
            json_str = parts[1].strip()
            # 去除可能的代码块包裹
            json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
            json_str = re.sub(r"\s*```$", "", json_str)
            try:
                metadata = json.loads(json_str)
            except json.JSONDecodeError:
                metadata = self._default_metadata(md_content)
        else:
            md_content = raw.strip()
            metadata = self._default_metadata(md_content)

        return md_content, metadata

    def _default_metadata(self, content: str) -> Dict[str, Any]:
        """从技能内容推断默认元数据（LLM 未输出时的回退）。"""
        # 尝试从标题提取关键词
        keywords: List[str] = []
        match = re.search(r"^#\s+技能名称[：:]\s*(.+)$", content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            keywords = [w for w in re.split(r"[\s,，、]+", title) if len(w) >= 2][:5]

        return {
            "keywords": keywords or ["auto"],
            "category": "chat",
            "description": "自动生成的技能",
            "trigger_examples": [],
        }

    @staticmethod
    def _derive_skill_name(content: str) -> str:
        match = re.search(r"^#\s+技能名称[：:]\s*(.+)$", content, re.MULTILINE)
        if match:
            name = match.group(1).strip()
            name = re.sub(r"[^\w\u4e00-\u9fff]", "_", name)
            name = re.sub(r"_+", "_", name).strip("_").lower()
            if name:
                return name
        return f"auto_{int(time.time())}"

    # ─── 元数据读写 ────────────────────────────────────────

    def _metadata_path(self, skill_name: str, tier: str) -> Path:
        """获取技能元数据文件路径。"""
        tier_dir = self.skills_dir / TIER_DIRS.get(tier, TIER_DIRS["auto"])
        # 也检查根目录（旧技能兼容）
        return tier_dir / f"{SKILL_FILE_PREFIX}{skill_name}.json"

    def _save_metadata(
        self, skill_name: str, metadata: Dict[str, Any], tier: str
    ) -> None:
        """保存技能元数据到 .json 文件。"""
        path = self._metadata_path(skill_name, tier)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[SkillEvolution] 保存元数据失败: {e}")

    def _load_metadata(self, skill_name: str, md_path: Path, tier: str) -> Dict[str, Any]:
        """加载技能元数据，不存在则生成默认值。"""
        # 尝试同名 .json 文件
        json_path = md_path.with_suffix(".json")
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        # 回退：从 .md 文件名和内容推断
        content = ""
        try:
            content = md_path.read_text(encoding="utf-8")
        except OSError:
            pass
        meta = self._default_metadata(content)
        meta["tier"] = tier
        meta["parents"] = []
        meta["novelty_boost_remaining"] = 0
        meta["flagged_for_regen"] = False
        meta["zero_use_rounds"] = 0
        return meta

    # ─── 技能加载（多信号打分） ─────────────────────────────

    def _detect_scene_end(self, user_message: str) -> bool:
        """检测用户消息是否表示当前场景结束。"""
        if not user_message:
            return False
        for signal in SCENE_END_SIGNALS:
            if signal in user_message:
                return True
        return False

    def _has_keyword_match(self, name: str, info: Dict[str, Any],
                           user_message: str) -> bool:
        """检查技能是否有关键词或触发示例命中（强信号）。

        用于场景结束时判断技能是否「绝对用不上」。
        仅看强信号（关键词+触发示例），不看类别等弱信号。
        """
        if not user_message:
            return False
        metadata = info.get("metadata", {})
        msg_lower = user_message.lower()

        # 关键词命中
        for kw in metadata.get("keywords", []):
            if len(kw) >= 2 and kw.lower() in msg_lower:
                return True

        # 触发示例重叠
        for example in metadata.get("trigger_examples", []):
            if self._count_word_overlap(user_message, example) >= 2:
                return True

        return False

    def load_skills(self, user_message: str = "") -> str:
        """根据用户消息智能加载技能，返回可注入 system prompt 的文本。

        v3: T1 无上限+会话粘性(激活/冷却/下线)，T2/T3 打分筛选+懒加载组合。

        Args:
            user_message: 当前用户消息文本，用于匹配筛选。

        Returns:
            拼接后的技能文本。若无匹配技能则返回空字符串。
        """
        self._load_skills_internal()

        # 过滤掉用户手动禁用的技能
        active_registry = {
            n: i for n, i in self.skills_registry.items()
            if n not in self._disabled_skills
        }

        if not active_registry:
            self._last_loaded_skills = []
            return ""

        # 小池子直接全灌
        total_skills = len(active_registry)
        if total_skills <= SMALL_POOL_THRESHOLD:
            return self._inject_all_skills(active_registry)

        # 检测场景结束信号
        scene_ended = self._detect_scene_end(user_message)

        # ── T1 处理：会话粘性机制 ──
        t1_injected: List[str] = []

        for name, info in active_registry.items():
            if info.get("tier", "auto") != "manual":
                continue

            state = self._t1_states.get(name)

            if state == "active":
                if scene_ended:
                    # 场景结束：用强信号判断是否绝对用不上
                    if not self._has_keyword_match(name, info, user_message):
                        # 无关键词/触发命中 → 绝对用不上 → 立即下线
                        self._t1_states.pop(name, None)
                        self._t1_cooling_rounds.pop(name, None)
                        continue
                    score = self._score_skill(name, info, user_message)
                    if score >= SCORE_THRESHOLD:
                        # 仍然高度相关 → 保持激活
                        t1_injected.append(name)
                        continue
                    else:
                        # 有弱关联但不够强 → 进入冷却
                        self._t1_states[name] = "cooling"
                        self._t1_cooling_rounds[name] = 0
                        t1_injected.append(name)
                        continue
                else:
                    # 场景继续 → 始终注入
                    t1_injected.append(name)
                    continue

            elif state == "cooling":
                cooling_rounds = self._t1_cooling_rounds.get(name, 0)
                if cooling_rounds >= COOLING_ROUNDS:
                    # 冷却期结束 → 下线
                    self._t1_states.pop(name, None)
                    self._t1_cooling_rounds.pop(name, None)
                    continue

                # 冷却期内：始终注入（粘性保活）
                t1_injected.append(name)

                # 检查是否有关键词命中 → 重新激活
                score = self._score_skill(name, info, user_message)
                if score >= SCORE_THRESHOLD:
                    self._t1_states[name] = "active"
                    self._t1_cooling_rounds.pop(name, None)
                else:
                    self._t1_cooling_rounds[name] = cooling_rounds + 1
                continue

            else:
                # 未激活：正常打分
                score = self._score_skill(name, info, user_message)
                if score >= SCORE_THRESHOLD:
                    self._t1_states[name] = "active"
                    t1_injected.append(name)

        # ── T2/T3 处理：打分筛选 ──
        scored: List[Tuple[str, float, str, Dict]] = []

        for name, info in active_registry.items():
            tier = info.get("tier", "auto")
            if tier == "manual":
                continue  # T1 已处理
            score = self._score_skill(name, info, user_message)
            if score >= SCORE_THRESHOLD:
                scored.append((name, score, tier, info))

        scored.sort(key=lambda x: x[1], reverse=True)

        excluded_by_composite: set = set()
        tier_counts = {"auto": 0, "composite": 0}
        max_per_tier = {"auto": MAX_INJECT_T2, "composite": MAX_INJECT_T3}

        t2t3_injected: List[str] = []
        for name, score, tier, info in scored:
            if len(t2t3_injected) >= MAX_INJECT_T2T3:
                break
            if tier_counts.get(tier, 0) >= max_per_tier.get(tier, MAX_INJECT_T2):
                continue
            if name in excluded_by_composite:
                continue
            if tier == "composite":
                parents = info.get("metadata", {}).get("parents", [])
                excluded_by_composite.update(parents)
                t2t3_injected = [n for n in t2t3_injected if n not in parents]
            t2t3_injected.append(name)
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        # 合并 T1 + T2/T3
        injected = t1_injected + t2t3_injected

        # 兜底：一条都没命中，加载使用频率最高的 T2 技能
        if not injected:
            t2_skills = [(n, i) for n, i in self.skills_registry.items()
                         if i.get("tier", "auto") == "auto"]
            t2_skills.sort(key=lambda x: x[1].get("usage_count", 0), reverse=True)
            for name, info in t2_skills[:2]:
                injected.append(name)

        if not injected:
            self._last_loaded_skills = []
            return ""

        # 读取并拼接技能内容
        parts: List[str] = ["", "## 已积累的技能经验", ""]
        loaded: List[str] = []
        for name in injected:
            info = self.skills_registry.get(name)
            if not info:
                continue
            skill_path = Path(info["file"])
            if not skill_path.exists():
                continue
            try:
                content = skill_path.read_text(encoding="utf-8")
                tier_tag = info.get("tier", "auto")
                parts.append(f"### 技能：{name}（{tier_tag}）\n\n{content}\n")
                loaded.append(name)
            except OSError:
                continue

        self._last_loaded_skills = loaded

        # 持久化T1状态（重启后可恢复）
        self._save_t1_states()

        return "\n".join(parts) if len(parts) > 3 else ""

    def _inject_all_skills(self, registry: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
        """小池子模式：注入所有技能。T1技能设为激活态。"""
        if registry is None:
            registry = self.skills_registry
        parts: List[str] = ["", "## 已积累的技能经验", ""]
        loaded: List[str] = []
        for name, info in registry.items():
            skill_path = Path(info["file"])
            if not skill_path.exists():
                continue
            try:
                content = skill_path.read_text(encoding="utf-8")
                tier = info.get("tier", "auto")
                parts.append(f"### 技能：{name}（{tier}）\n\n{content}\n")
                loaded.append(name)
                # T1 技能在小池子模式下也设为激活态
                if tier == "manual" and name not in self._t1_states:
                    self._t1_states[name] = "active"
            except OSError:
                continue
        self._last_loaded_skills = loaded
        # 持久化T1状态
        self._save_t1_states()
        return "\n".join(parts) if len(parts) > 3 else ""

    def _score_skill(
        self,
        name: str,
        info: Dict[str, Any],
        user_message: str,
    ) -> float:
        """多信号打分：关键词 + 触发示例 + 类别 + 频率 + 新手加成。"""
        if not user_message:
            return 0.0

        metadata = info.get("metadata", {})
        score = 0.0
        msg_lower = user_message.lower()

        # 信号1: 关键词精确命中 (×3)
        keywords = metadata.get("keywords", [])
        for kw in keywords:
            if len(kw) >= 2 and kw.lower() in msg_lower:
                score += WEIGHT_KEYWORD

        # 信号2: 触发示例重叠 (×2)
        trigger_examples = metadata.get("trigger_examples", [])
        for example in trigger_examples:
            overlap = self._count_word_overlap(user_message, example)
            if overlap >= 2:
                score += WEIGHT_TRIGGER
                break  # 命中一个即可

        # 信号3: 类别推断命中 (×1)
        category = metadata.get("category", "chat")
        if self._infer_category(user_message) == category:
            score += WEIGHT_CATEGORY

        # 信号4: 使用频率加成 (×0.5)
        usage = info.get("usage_count", 0)
        if usage > 0:
            freq_boost = min(WEIGHT_FREQUENCY, usage * 0.05)
            score += freq_boost

        # 信号5: 新手加成 (×2)
        novelty = metadata.get("novelty_boost_remaining", 0)
        if novelty > 0:
            score += WEIGHT_NOVELTY

        # 长消息降低阈值（多话题更可能需要技能）
        if len(user_message) > 100 and score >= SCORE_THRESHOLD - 1:
            score += 1.0

        return score

    @staticmethod
    def _count_word_overlap(text1: str, text2: str) -> int:
        """计算两段文本的实词重叠数（2字以上片段）。"""
        # 提取2-4字的中文/英文片段
        def extract_words(text: str) -> set:
            words = set()
            # 中文2字词
            for i in range(len(text) - 1):
                w = text[i:i+2]
                if all('\u4e00' <= c <= '\u9fff' for c in w):
                    words.add(w)
            # 英文单词
            for w in re.findall(r'[a-zA-Z]{2,}', text):
                words.add(w.lower())
            return words

        w1 = extract_words(text1)
        w2 = extract_words(text2)
        return len(w1 & w2)

    @staticmethod
    def _infer_category(message: str) -> str:
        """根据消息内容推断类别。"""
        msg_lower = message.lower()
        best_cat = "chat"
        best_score = 0
        for cat, keywords in CATEGORY_RULES:
            hits = sum(1 for kw in keywords if kw in msg_lower)
            if hits > best_score:
                best_score = hits
                best_cat = cat
        return best_cat

    def _load_skills_internal(self) -> None:
        """扫描三层目录 + 根目录（兼容旧技能），更新注册表。"""
        self.skills_registry.clear()

        # 扫描三层子目录
        for tier, subdir in TIER_DIRS.items():
            tier_dir = self.skills_dir / subdir
            if not tier_dir.exists():
                continue
            for md_file in sorted(tier_dir.glob("*.md")):
                name = md_file.stem
                if name.startswith(SKILL_FILE_PREFIX):
                    name = name[len(SKILL_FILE_PREFIX):]
                metadata = self._load_metadata(name, md_file, tier)
                self.skills_registry[name] = {
                    "file": str(md_file),
                    "tier": tier,
                    "created": datetime.fromtimestamp(
                        md_file.stat().st_mtime
                    ).isoformat(),
                    "usage_count": 0,
                    "success_count": 0,
                    "fail_count": 0,
                    "metadata": metadata,
                }

        # 兼容：扫描根目录下的旧 .md 文件（视为 T2 auto）
        for md_file in sorted(self.skills_dir.glob("*.md")):
            name = md_file.stem
            if name.startswith(SKILL_FILE_PREFIX):
                name = name[len(SKILL_FILE_PREFIX):]
            if name not in self.skills_registry:
                metadata = self._load_metadata(name, md_file, "auto")
                self.skills_registry[name] = {
                    "file": str(md_file),
                    "tier": "auto",
                    "created": datetime.fromtimestamp(
                        md_file.stat().st_mtime
                    ).isoformat(),
                    "usage_count": 0,
                    "success_count": 0,
                    "fail_count": 0,
                    "metadata": metadata,
                }

    # ─── 技能评估 ──────────────────────────────────────────

    def evaluate_skill(self, skill_name: str, success: bool) -> None:
        """评估技能使用效果，更新计数和评估日志。"""
        if skill_name not in self.skills_registry:
            return

        info = self.skills_registry[skill_name]
        info["usage_count"] += 1
        if success:
            info["success_count"] += 1
        else:
            info["fail_count"] += 1

        # 更新元数据中的新手加成计数
        metadata = info.get("metadata", {})
        novelty = metadata.get("novelty_boost_remaining", 0)
        if novelty > 0:
            metadata["novelty_boost_remaining"] = novelty - 1

        # 检查是否需要标记重生成
        self._check_regen_flag(skill_name, info)

        # 持久化元数据
        tier = info.get("tier", "auto")
        self._save_metadata(skill_name, metadata, tier)

        # 追加评估日志到技能文件
        skill_path = Path(info["file"])
        if skill_path.exists():
            try:
                content = skill_path.read_text(encoding="utf-8")
                log_entry = (
                    f"\n---\n**评估记录** — {datetime.now().isoformat()}: "
                    f"{'✅ 成功' if success else '❌ 失败'}\n"
                )
                if "## 评估记录" not in content:
                    content += "\n\n## 评估记录\n" + log_entry
                else:
                    content += log_entry
                skill_path.write_text(content, encoding="utf-8")
            except OSError:
                pass

    def _check_regen_flag(self, skill_name: str, info: Dict[str, Any]) -> None:
        """检查技能是否应标记为待重生成。"""
        tier = info.get("tier", "auto")
        if tier == "manual":
            return  # T1 不自动标记

        metadata = info.get("metadata", {})
        usage = info.get("usage_count", 0)
        success = info.get("success_count", 0)
        zero_rounds = metadata.get("zero_use_rounds", 0)

        # 条件1: 使用≥3次且成功率<30%
        if usage >= 3:
            rate = success / usage if usage > 0 else 0
            if rate < REGEN_LOW_SUCCESS_RATE:
                metadata["flagged_for_regen"] = True
                print(f"[SkillEvolution] 技能 {skill_name} 标记重生成（成功率{rate:.0%}）")

    # ─── 技能更新 ──────────────────────────────────────────

    def update_skill(self, skill_name: str, new_content: str) -> bool:
        skill_path = self._find_skill_file(skill_name)
        if skill_path is None:
            print(f"[SkillEvolution] 技能不存在，无法更新: {skill_name}")
            return False

        try:
            old_content = skill_path.read_text(encoding="utf-8")
            eval_section = ""
            if "## 评估记录" in old_content:
                idx = old_content.index("## 评估记录")
                eval_section = old_content[idx:]
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
        candidates = [
            self.skills_dir / TIER_DIRS["auto"] / f"{SKILL_FILE_PREFIX}{skill_name}.md",
            self.skills_dir / TIER_DIRS["manual"] / f"{SKILL_FILE_PREFIX}{skill_name}.md",
            self.skills_dir / TIER_DIRS["composite"] / f"{SKILL_FILE_PREFIX}{skill_name}.md",
            self.skills_dir / f"{SKILL_FILE_PREFIX}{skill_name}.md",
            self.skills_dir / TIER_DIRS["auto"] / f"{skill_name}.md",
            self.skills_dir / TIER_DIRS["manual"] / f"{skill_name}.md",
        ]
        if skill_name in self.skills_registry:
            candidates.insert(0, Path(self.skills_registry[skill_name]["file"]))
        for path in candidates:
            if path.exists():
                return path
        return None

    # ─── 重置 ──────────────────────────────────────────────

    def reset_tool_calls(self) -> None:
        self.tool_calls.clear()

    # ─── 工具方法 ──────────────────────────────────────────

    def list_skills(self) -> List[Dict[str, Any]]:
        self._load_skills_internal()
        result: List[Dict[str, Any]] = []
        for name, info in self.skills_registry.items():
            result.append({
                "name": name,
                "tier": info.get("tier", "auto"),
                "keywords": info.get("metadata", {}).get("keywords", []),
                "usage": info.get("usage_count", 0),
                "success_rate": (
                    info["success_count"] / info["usage_count"]
                    if info.get("usage_count", 0) > 0
                    else 0
                ),
                "flagged": info.get("metadata", {}).get("flagged_for_regen", False),
            })
        return result

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        skill_path = self._find_skill_file(skill_name)
        if skill_path is None or not skill_path.exists():
            return None
        try:
            return skill_path.read_text(encoding="utf-8")
        except OSError:
            return None

    # ─── 清理与迭代 ──────────────────────────────────────────

    def cleanup_old_skills(self) -> int:
        """清理过期且低效的 T2 技能。T1(manual) 永不清理。"""
        self._load_skills_internal()
        now = time.time()
        max_age_sec = MAX_CHECKPOINT_AGE_DAYS * 86400
        removed = 0

        for name in list(self.skills_registry.keys()):
            info = self.skills_registry[name]
            tier = info.get("tier", "auto")

            # T1 永不清理
            if tier == "manual":
                continue

            skill_path = Path(info["file"])
            if not skill_path.exists():
                continue

            try:
                file_age = now - skill_path.stat().st_mtime
            except OSError:
                continue
            if file_age < max_age_sec:
                continue

            usage = info.get("usage_count", 0)
            success = info.get("success_count", 0)
            if usage < 3:
                continue

            success_rate = success / usage if usage > 0 else 0
            if success_rate >= 0.3:
                continue

            # 删除 .md 和 .json
            try:
                skill_path.unlink()
                json_path = skill_path.with_suffix(".json")
                if json_path.exists():
                    json_path.unlink()
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
        """获取表现不佳的技能列表（排除 T1）。"""
        self._load_skills_internal()
        result: List[Dict[str, Any]] = []
        for name, info in self.skills_registry.items():
            if info.get("tier", "auto") == "manual":
                continue  # T1 不报告
            usage = info.get("usage_count", 0)
            if usage < min_usage:
                continue
            success = info.get("success_count", 0)
            rate = success / usage if usage > 0 else 0
            if rate < max_success_rate:
                result.append({
                    "name": name,
                    "tier": info.get("tier", "auto"),
                    "usage_count": usage,
                    "success_rate": rate,
                })
        return result

    def evaluate_last_loaded(self, success: bool) -> None:
        """评估上次加载的所有技能，并更新共现记录。"""
        loaded = list(self._last_loaded_skills)

        for name in loaded:
            try:
                self.evaluate_skill(name, success)
            except Exception:
                pass

        # 跟踪共现（仅T2技能参与组合）
        t2_loaded = [
            n for n in loaded
            if self.skills_registry.get(n, {}).get("tier", "auto") == "auto"
        ]
        if len(t2_loaded) >= 2:
            self._track_cooccurrence(t2_loaded)
            self._check_compose_trigger(t2_loaded)

        # 更新零使用计数
        self._update_zero_use_rounds(loaded)

        # 评估完清空
        self._last_loaded_skills = []

    def _update_zero_use_rounds(self, loaded: List[str]) -> None:
        """更新未被选中的技能的零使用轮次计数。"""
        for name, info in self.skills_registry.items():
            if info.get("tier", "auto") == "manual":
                continue
            metadata = info.get("metadata", {})
            if name in loaded:
                metadata["zero_use_rounds"] = 0
            else:
                rounds = metadata.get("zero_use_rounds", 0) + 1
                metadata["zero_use_rounds"] = rounds
                if rounds >= REGEN_ZERO_USE_ROUNDS:
                    metadata["flagged_for_regen"] = True
                    print(f"[SkillEvolution] 技能 {name} 标记重生成（{rounds}轮未使用）")

    # ─── 懒加载组合 ────────────────────────────────────────

    def _track_cooccurrence(self, loaded: List[str]) -> None:
        """记录技能共现。"""
        loaded_sorted = sorted(loaded)
        for i in range(len(loaded_sorted)):
            for j in range(i + 1, len(loaded_sorted)):
                pair_key = f"{loaded_sorted[i]}+{loaded_sorted[j]}"
                self.cooccurrence[pair_key] = self.cooccurrence.get(pair_key, 0) + 1

        # 持久化
        self._save_cooccurrence()

    def _check_compose_trigger(self, loaded: List[str]) -> None:
        """检查是否有技能组合达到阈值，触发组合生成。"""
        loaded_sorted = sorted(loaded)
        for i in range(len(loaded_sorted)):
            for j in range(i + 1, len(loaded_sorted)):
                pair_key = f"{loaded_sorted[i]}+{loaded_sorted[j]}"
                count = self.cooccurrence.get(pair_key, 0)
                if count >= COMPOSE_THRESHOLD:
                    # 检查是否已有组合技能
                    comp_name = f"composite_{loaded_sorted[i]}_{loaded_sorted[j]}"
                    if comp_name not in self.skills_registry:
                        print(f"[SkillEvolution] 触发技能组合: {pair_key} (共现{count}次)")
                        try:
                            self.compose_skills(
                                [loaded_sorted[i], loaded_sorted[j]],
                                comp_name,
                            )
                        except Exception as e:
                            print(f"[SkillEvolution] 技能组合失败: {e}")

    def compose_skills(
        self,
        skill_names: List[str],
        composite_name: str,
    ) -> Optional[str]:
        """将多个技能组合为一个新的组合技能。

        Args:
            skill_names: 要组合的技能名列表。
            composite_name: 组合技能名称。

        Returns:
            生成的组合技能文件路径，失败返回 None。
        """
        # 读取所有技能内容
        skill_contents: List[str] = []
        for name in skill_names:
            content = self.get_skill_content(name)
            if content is None:
                print(f"[SkillEvolution] 技能不存在，无法组合: {name}")
                return None
            skill_contents.append(f"--- 技能: {name} ---\n{content}")

        # 构造组合 prompt
        combined_text = "\n\n".join(skill_contents)
        prompt = f"""你是一个技能整合专家。请将以下多个技能合并为一个连贯的单一技能。

## 待合并的技能
{combined_text}

请合并为一个技能文件，要求：
1. 消解冲突的指令（如一个要求简洁，一个要求详细，根据组合场景决定）
2. 合并重复的步骤
3. 保持工作流连贯（先做什么，后做什么）
4. 生成新的关键词和触发示例，覆盖原来所有技能的触发场景

输出格式（纯文本，不要代码块包裹）：

# 技能名称：{composite_name}

## 目标
（合并后的目标描述）

## 步骤
（合并后的完整步骤）

## 工具序列
（合并后的工具序列）

## 关键决策点
（合并后的决策点）

## 注意事项
（合并后的注意事项）

---METADATA---
{{
  "keywords": ["合并后的关键词，覆盖所有原技能"],
  "category": "合并后的类别",
  "description": "合并后的描述",
  "trigger_examples": ["合并后的触发示例"]
}}
"""

        try:
            raw_response = self._call_llm(prompt)
        except Exception as e:
            print(f"[SkillEvolution] 组合 LLM 调用失败: {e}")
            return None

        if not raw_response or not raw_response.strip():
            return None

        skill_content, metadata = self._parse_skill_response(raw_response)

        # 写入 composite/ 目录
        comp_dir = self.skills_dir / TIER_DIRS["composite"]
        comp_path = comp_dir / f"{SKILL_FILE_PREFIX}{composite_name}.md"
        try:
            with open(comp_path, "w", encoding="utf-8") as f:
                f.write(skill_content)
        except OSError as e:
            print(f"[SkillEvolution] 写入组合技能失败: {e}")
            return None

        # 保存元数据
        metadata["tier"] = "composite"
        metadata["parents"] = skill_names
        metadata["novelty_boost_remaining"] = NOVELTY_BOOST_ROUNDS
        metadata["flagged_for_regen"] = False
        metadata["zero_use_rounds"] = 0
        self._save_metadata(composite_name, metadata, "composite")

        # 注册到内存
        self.skills_registry[composite_name] = {
            "file": str(comp_path),
            "tier": "composite",
            "created": datetime.now().isoformat(),
            "usage_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "metadata": metadata,
        }

        print(f"[SkillEvolution] 组合技能已生成: {comp_path}")
        return str(comp_path)

    # ─── 共现记录持久化 ────────────────────────────────────

    def _cooccurrence_path(self) -> Path:
        return self.skills_dir / ".cooccurrence.json"

    def _save_cooccurrence(self) -> None:
        try:
            with open(self._cooccurrence_path(), "w", encoding="utf-8") as f:
                json.dump(self.cooccurrence, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_cooccurrence(self) -> None:
        path = self._cooccurrence_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.cooccurrence = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.cooccurrence = {}
        else:
            self.cooccurrence = {}

    # ─── LLM 调用 ──────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError(
                "API Key 未配置，请设置环境变量 DEEPSEEK_API_KEY "
                "或在 config.json 中配置 llm.api_key"
            )

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

    # ─── T1状态持久化 ──────────────────────────────────────

    def _t1_states_path(self) -> Path:
        return self.skills_dir / ".t1_states.json"

    def _save_t1_states(self) -> None:
        """持久化T1会话粘性状态，重启后可恢复。"""
        try:
            data = {
                "t1_states": self._t1_states,
                "t1_cooling_rounds": self._t1_cooling_rounds,
            }
            with open(self._t1_states_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_t1_states(self) -> None:
        """从磁盘恢复T1会话粘性状态。"""
        path = self._t1_states_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._t1_states = data.get("t1_states", {})
            self._t1_cooling_rounds = data.get("t1_cooling_rounds", {})
        except (json.JSONDecodeError, OSError):
            pass

    # ─── 禁用技能持久化 ────────────────────────────────────

    def _disabled_path(self) -> Path:
        return self.skills_dir / ".disabled_skills.json"

    def _save_disabled_skills(self) -> None:
        try:
            with open(self._disabled_path(), "w", encoding="utf-8") as f:
                json.dump(list(self._disabled_skills), f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_disabled_skills(self) -> None:
        path = self._disabled_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._disabled_skills = set(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass

    # ─── 用户技能管理接口 ──────────────────────────────────

    def list_skills_detailed(self) -> List[Dict[str, Any]]:
        """列出所有技能的详细信息，含T1状态和禁用状态。"""
        self._load_skills_internal()
        result: List[Dict[str, Any]] = []
        for name, info in self.skills_registry.items():
            tier = info.get("tier", "auto")
            result.append({
                "name": name,
                "tier": tier,
                "tier_label": {"manual": "T1手动", "auto": "T2自进化", "composite": "T3组合"}.get(tier, tier),
                "keywords": info.get("metadata", {}).get("keywords", []),
                "category": info.get("metadata", {}).get("category", ""),
                "usage": info.get("usage_count", 0),
                "success_rate": (
                    info["success_count"] / info["usage_count"]
                    if info.get("usage_count", 0) > 0 else 0
                ),
                "flagged": info.get("metadata", {}).get("flagged_for_regen", False),
                "t1_state": self._t1_states.get(name, "inactive") if tier == "manual" else None,
                "cooling_rounds": self._t1_cooling_rounds.get(name, 0) if tier == "manual" else None,
                "disabled": name in self._disabled_skills,
                "file": info.get("file", ""),
            })
        return result

    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取单个技能的详细信息。"""
        self._load_skills_internal()
        info = self.skills_registry.get(skill_name)
        if not info:
            return None
        tier = info.get("tier", "auto")
        content = self.get_skill_content(skill_name) or ""
        return {
            "name": skill_name,
            "tier": tier,
            "tier_label": {"manual": "T1手动", "auto": "T2自进化", "composite": "T3组合"}.get(tier, tier),
            "keywords": info.get("metadata", {}).get("keywords", []),
            "category": info.get("metadata", {}).get("category", ""),
            "trigger_examples": info.get("metadata", {}).get("trigger_examples", []),
            "parents": info.get("metadata", {}).get("parents", []),
            "usage": info.get("usage_count", 0),
            "success": info.get("success_count", 0),
            "success_rate": (
                info["success_count"] / info["usage_count"]
                if info.get("usage_count", 0) > 0 else 0
            ),
            "flagged": info.get("metadata", {}).get("flagged_for_regen", False),
            "t1_state": self._t1_states.get(skill_name, "inactive") if tier == "manual" else None,
            "cooling_rounds": self._t1_cooling_rounds.get(skill_name, 0) if tier == "manual" else None,
            "disabled": skill_name in self._disabled_skills,
            "file": info.get("file", ""),
            "content_preview": content[:500] + "..." if len(content) > 500 else content,
        }

    def disable_skill(self, skill_name: str) -> bool:
        """禁用一个技能。禁用后不会被注入。"""
        self._load_skills_internal()
        if skill_name not in self.skills_registry:
            return False
        self._disabled_skills.add(skill_name)
        # 如果是T1，同时清除激活/冷却状态
        self._t1_states.pop(skill_name, None)
        self._t1_cooling_rounds.pop(skill_name, None)
        self._save_disabled_skills()
        self._save_t1_states()
        return True

    def enable_skill(self, skill_name: str) -> bool:
        """重新启用一个被禁用的技能。"""
        if skill_name not in self._disabled_skills:
            return False
        self._disabled_skills.discard(skill_name)
        self._save_disabled_skills()
        return True

    def remove_skill(self, skill_name: str) -> Tuple[bool, str]:
        """删除一个技能文件。T1手动技能不允许通过此方法删除。"""
        self._load_skills_internal()
        info = self.skills_registry.get(skill_name)
        if not info:
            return False, f"技能 '{skill_name}' 不存在"
        tier = info.get("tier", "auto")
        if tier == "manual":
            return False, f"T1手动技能 '{skill_name}' 不支持命令删除，请直接删除文件或使用 /skill disable 禁用"
        skill_path = Path(info["file"])
        # 删除 .md 和 .json
        deleted_files = []
        if skill_path.exists():
            skill_path.unlink()
            deleted_files.append(str(skill_path))
        json_path = skill_path.with_suffix(".json")
        if json_path.exists():
            json_path.unlink()
            deleted_files.append(str(json_path))
        # 清理运行时状态
        self._disabled_skills.discard(skill_name)
        self._t1_states.pop(skill_name, None)
        self._t1_cooling_rounds.pop(skill_name, None)
        self._save_disabled_skills()
        self._save_t1_states()
        # 重新加载注册表
        self._load_skills_internal()
        return True, f"已删除技能 '{skill_name}'（{len(deleted_files)}个文件）"
