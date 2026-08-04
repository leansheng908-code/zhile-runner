#!/usr/bin/env python3
"""
主动记忆重建引擎 — P0.39 Phase 1

基于 MRAgent 论文 (arxiv.org/abs/2606.06036)
"Memory is Reconstructed, Not Retrieved"

核心思想：记忆不是被动检索的，而是通过 Cue-Tag-Content 三层
关联图主动重建的。复杂多跳问题通过迭代式 Cue→Tag→Content
激活链逐步重建出完整的相关记忆集合。

三层结构：
  Cue(细粒度关键词) → Tag(语义标签桥梁, ≤2词) → Content(记忆内容)

重建流程：
  1. LLM分析问题，提取初始Cue（关键词）
  2. 激活候选Tag → 选择最相关Tag
  3. 通过Tag检索Content → 获取证据
  4. LLM判断证据是否充分
  5. 不充分 → 从证据中提取新Cue → 回到步骤2
  6. 最多N轮，充分或到上限 → 返回收集到的记忆

简单问题（单跳）仍走现有被动检索，不做重建。
"""

import json
import re
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime


# 多跳信号词 — 出现这些词时认为问题需要主动重建
MULTI_HOP_SIGNALS = [
    "之前", "上次", "记得", "上回", "刚才说", "之前提到",
    "还说过", "又", "另外", "结合", "关联", "联系起来",
    "那个", "那次", "那件事", "我们聊过", "讨论过",
    "继续", "接着", "然后呢", "后来", "上次说",
    "之前问", "提到过", "说过", "聊到",
]

# P0.39 Phase 2: 时序信号词 — 时间相关的问题需要时序重建
TEMPORAL_SIGNALS = [
    "之前", "上次", "那天", "还记得", "什么时候",
    "前几天", "昨天", "上周", "上个月", "当时",
]

# P0.39 Phase 2: 跨主题信号词 — 需要对比不同主题的记忆
CROSS_TOPIC_SIGNALS = [
    "相比", "不同", "区别", "变化", "之前vs现在",
    "对比", "差异", "转变", "另一个", "另外",
]

# P0.39 Phase 2: 推理信号词 — 需要链式推理检索
REASONING_SIGNALS = [
    "为什么", "怎么会", "如果", "假设",
    "推理", "因为", "所以", "导致", "原因",
]


class ComplexityResult(dict):
    """复杂度分析结果

    兼容 bool 上下文：可直接用于 ``if`` 判断，也可通过属性/键访问详细信息。

    属性:
        is_complex: 是否需要主动重建
        complexity_score: 复杂度评分 (0-10)
        signal_type: 信号类型
            ``"multi_hop" | "temporal" | "cross_topic" | "reasoning" | "none"``
    """

    def __bool__(self) -> bool:
        return self.get("is_complex", False)

    @property
    def is_complex(self) -> bool:
        return self.get("is_complex", False)

    @property
    def complexity_score(self) -> int:
        return self.get("complexity_score", 0)

    @property
    def signal_type(self) -> str:
        return self.get("signal_type", "none")


class ActiveReconstructor:
    """主动记忆重建引擎

    通过 Cue-Tag-Content 三层关联图进行迭代式记忆重建。
    每轮：提取Cue → 激活Tag → 检索Content → 判断充分性 → (不充分)提取新Cue
    """

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    # ─── 复杂度判断 ─────────────────────────────

    @staticmethod
    def is_complex_query(query: str) -> ComplexityResult:
        """判断问题是否需要主动重建（多跳/复杂问题）

        P0.39 Phase 2 增强：在原有 24 个多跳信号词基础上，新增
        - 时序信号词 (之前/上次/那天/还记得/什么时候)
        - 跨主题信号词 (相比/不同/区别/变化/之前vs现在)
        - 推理信号词 (为什么/怎么会/如果/假设)

        返回 :class:`ComplexityResult`，兼容旧版 ``bool`` 用法::

            if ActiveReconstructor.is_complex_query(query):  # 仍然可用
                ...
            result = ActiveReconstructor.is_complex_query(query)
            print(result.complexity_score, result.signal_type)

        返回:
            ComplexityResult: {is_complex, complexity_score, signal_type}
        """
        if not query or not query.strip():
            return ComplexityResult(
                is_complex=False, complexity_score=0, signal_type="none")

        score = 0
        signal_type = "none"

        # 1. 多跳信号词（原有 24 个）
        multi_hop_hits = sum(1 for sig in MULTI_HOP_SIGNALS if sig in query)
        if multi_hop_hits > 0:
            score += min(multi_hop_hits * 2, 4)
            signal_type = "multi_hop"

        # 2. 时序信号词（新增）
        temporal_hits = sum(1 for sig in TEMPORAL_SIGNALS if sig in query)
        if temporal_hits > 0:
            score += min(temporal_hits * 2, 4)
            if signal_type == "none":
                signal_type = "temporal"

        # 3. 跨主题信号词（新增）
        cross_topic_hits = sum(1 for sig in CROSS_TOPIC_SIGNALS if sig in query)
        if cross_topic_hits > 0:
            score += min(cross_topic_hits * 2, 4)
            if signal_type == "none":
                signal_type = "cross_topic"

        # 4. 推理信号词（新增）
        reasoning_hits = sum(1 for sig in REASONING_SIGNALS if sig in query)
        if reasoning_hits > 0:
            score += min(reasoning_hits * 2, 4)
            if signal_type == "none":
                signal_type = "reasoning"

        # 5. 长度加分
        if len(query) >= 20:
            score += 1
        if len(query) >= 50:
            score += 1

        # 阈值 = 1：保持向后兼容
        #   旧逻辑: len>=20 → True (score=1 ✓) | 有信号词 → True (score>=2 ✓)
        #   旧逻辑: len<20 且无信号 → False (score=0 ✓)
        is_complex = score >= 1

        return ComplexityResult(
            is_complex=is_complex,
            complexity_score=score,
            signal_type=signal_type,
        )

    # ─── LLM调用封装 ─────────────────────────────

    def _llm_call(self, messages: List[Dict]) -> str:
        """调用LLM，返回完整文本"""
        if not self.llm:
            return ""
        result = ""
        for chunk in self.llm.chat(messages, stream=True):
            result += chunk
        return result

    @staticmethod
    def _parse_json_response(result: str) -> Optional[dict]:
        """解析LLM返回的JSON（容错处理）"""
        result = result.strip()
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            result = result.split("```")[1].split("```")[0]
        return json.loads(result.strip())

    # ─── 步骤1: 提取Cue ──────────────────────────

    def _extract_cues(self, query: str) -> List[str]:
        """LLM分析问题，提取初始Cue（关键词）"""
        prompt = f"""分析以下问题，提取用于记忆检索的关键词（Cue）。

问题：{query}

提取规则：
1. 提取3-7个细粒度关键词，用于在记忆库中定位相关信息
2. 关键词应该具体、可匹配（如人名、地名、事件名、技术术语等）
3. 避免泛化词（如"事情"、"东西"等）

以JSON格式返回：
{{"cues": ["关键词1", "关键词2", ...]}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是记忆检索分析助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = self._llm_call(messages)
            data = self._parse_json_response(result)
            return data.get("cues", [])
        except (json.JSONDecodeError, KeyError, TypeError, Exception):
            return self._fallback_cue_extraction(query)

    @staticmethod
    def _fallback_cue_extraction(query: str) -> List[str]:
        """无LLM时的退化Cue提取：简单分词"""
        stop_words = {"的", "了", "是", "在", "我", "你", "他", "她", "它",
                      "和", "与", "或", "但", "也", "都", "就", "把", "被",
                      "吗", "呢", "吧", "啊", "呀", "哦", "嗯", "什么",
                      "怎么", "为什么", "哪里", "哪个", "谁", "多少",
                      "这个", "那个", "这些", "那些"}
        tokens = re.split(r'[，。！？\s,\.!?;:、]+', query)
        cues = [t.strip() for t in tokens
                if t.strip() and len(t.strip()) >= 2
                and t.strip() not in stop_words]
        return cues[:7]

    # ─── 步骤2: 激活Tag + 选择Tag ────────────────

    def _activate_tags(self, cues: List[str], memory_system) -> List[str]:
        """激活候选Tag — 通过Cue匹配记忆，收集其Tag"""
        candidate_tags: Set[str] = set()
        query_cue_set = set(c.lower() for c in cues)

        for mem in memory_system.memories:
            if mem.should_archive():
                continue
            matched = False

            # 1. 如果记忆有cues，检查cue交集
            if mem.cues:
                mem_cue_set = set(c.lower() for c in mem.cues)
                if mem_cue_set & query_cue_set:
                    matched = True

            # 2. cue匹配失败或没有cues，用内容子串匹配
            if not matched:
                content_lower = mem.content.lower()
                for cue in cues:
                    if cue.lower() in content_lower:
                        matched = True
                        break

            # 3. 匹配成功 → 激活该记忆的tags
            if matched and mem.tags:
                for tag in mem.tags:
                    candidate_tags.add(tag)

        return list(candidate_tags)

    def _select_tags(self, cues: List[str],
                     candidate_tags: List[str]) -> List[str]:
        """从候选Tag中选择最相关的Tag（LLM辅助）"""
        if not candidate_tags:
            return []
        if len(candidate_tags) <= 5:
            return candidate_tags

        prompt = f"""从以下候选语义标签中，选择与检索关键词最相关的标签。

检索关键词：{', '.join(cues)}

候选标签：{', '.join(candidate_tags)}

选择规则：
1. 选择最多5个最相关的标签
2. 优先选择与关键词语义直接相关的标签

以JSON格式返回：
{{"selected_tags": ["标签1", "标签2", ...]}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是语义匹配助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = self._llm_call(messages)
            data = self._parse_json_response(result)
            return data.get("selected_tags", [])
        except (json.JSONDecodeError, KeyError, TypeError, Exception):
            return candidate_tags[:5]

    # ─── 步骤3: 检索Content ──────────────────────

    def _retrieve_content(self, tags: List[str], memory_system,
                          exclude_ids: Set[str] = None) -> List:
        """通过Tag检索Content — 获取记忆证据"""
        exclude_ids = exclude_ids or set()
        results = []
        sel_tag_set = set(t.lower() for t in tags)

        for mem in memory_system.memories:
            if mem.id in exclude_ids:
                continue
            if mem.should_archive():
                continue

            matched = False
            # 1. 记忆有tags → 检查tag交集
            if mem.tags:
                mem_tag_set = set(t.lower() for t in mem.tags)
                if mem_tag_set & sel_tag_set:
                    matched = True

            # 2. 没有tags的旧记忆 → 用tag子串匹配内容
            if not matched and not mem.tags:
                content_lower = mem.content.lower()
                for tag in tags:
                    if tag.lower() in content_lower:
                        matched = True
                        break

            if matched:
                results.append(mem)

        return results

    # ─── 步骤4: 判断充分性 ──────────────────────

    def _judge_sufficiency(self, query: str,
                           evidence: List) -> Tuple[bool, List[str]]:
        """LLM判断证据是否充分，返回(是否充分, 新Cue列表)"""
        if not evidence:
            return False, []

        evidence_text = "\n".join(
            f"[{i+1}] {m.content}" for i, m in enumerate(evidence[:20])
        )

        prompt = f"""问题：{query}

已收集的记忆证据：
{evidence_text}

请判断：
1. 现有证据是否足以回答该问题？
2. 如果不足以回答，请从证据中提取新的检索关键词（Cue），用于下一轮检索。
   新关键词应该指向尚未检索到的相关记忆方向。

以JSON格式返回：
{{"sufficient": true/false, "new_cues": ["新关键词1", "新关键词2", ...]}}

注意：如果sufficient为true，new_cues可以为空列表。
只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是记忆充分性判断助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = self._llm_call(messages)
            data = self._parse_json_response(result)
            sufficient = data.get("sufficient", False)
            new_cues = data.get("new_cues", [])
            return sufficient, new_cues
        except (json.JSONDecodeError, KeyError, TypeError, Exception):
            # 退化：有证据就认为充分
            return True, []

    # ─── 主流程: 主动重建 ────────────────────────

    def reconstruct(self, query: str, memory_system, llm_provider=None,
                    max_rounds: int = 5) -> str:
        """主动记忆重建主流程

        参数：
        - query: 用户问题
        - memory_system: 记忆系统实例
        - llm_provider: LLM提供者（可选，默认用初始化时的）
        - max_rounds: 最大重建轮次

        返回：格式化的记忆上下文字符串
        """
        if llm_provider:
            self.llm = llm_provider

        # 无LLM或记忆太少 → 退化到被动检索
        if not self.llm or len(memory_system.memories) < 3:
            return memory_system._format_memories(15)

        collected_memories = []
        collected_ids: Set[str] = set()
        all_cues: List[str] = []

        # 步骤1: 提取初始Cue
        initial_cues = self._extract_cues(query)
        if not initial_cues:
            return memory_system._format_memories(15)

        all_cues = list(initial_cues)
        current_cues = initial_cues

        for round_num in range(max_rounds):
            # 步骤2: 激活候选Tag → 选择最相关Tag
            candidate_tags = self._activate_tags(current_cues, memory_system)

            if not candidate_tags:
                # 没有候选Tag，尝试用Cue直接匹配内容
                for mem in memory_system.memories:
                    if mem.id in collected_ids or mem.should_archive():
                        continue
                    content_lower = mem.content.lower()
                    for cue in current_cues:
                        if cue.lower() in content_lower:
                            collected_memories.append(mem)
                            collected_ids.add(mem.id)
                            break
                break

            selected_tags = self._select_tags(current_cues, candidate_tags)
            if not selected_tags:
                break

            # 步骤3: 通过Tag检索Content
            new_evidence = self._retrieve_content(
                selected_tags, memory_system, exclude_ids=collected_ids)

            if not new_evidence:
                break

            for mem in new_evidence:
                if mem.id not in collected_ids:
                    collected_memories.append(mem)
                    collected_ids.add(mem.id)

            # 步骤4: LLM判断证据是否充分
            sufficient, new_cues = self._judge_sufficiency(
                query, collected_memories)

            # 步骤5: 充分 → 返回；不充分 → 提取新Cue → 继续
            if sufficient:
                break

            if new_cues:
                # 过滤已用过的cue
                new_unique = [c for c in new_cues if c not in all_cues]
                if not new_unique:
                    break  # 没有新cue了，退出
                all_cues.extend(new_unique)
                current_cues = new_unique
            else:
                break  # 没有新cue了，退出

        # 步骤6: 返回收集到的记忆
        if not collected_memories:
            return memory_system._format_memories(15)

        # 按优先级排序
        collected_memories.sort(key=lambda m: m.priority(), reverse=True)

        # 收集的记忆不够时补充
        max_memories = 15
        if len(collected_memories) < max_memories:
            remaining = [
                m for m in memory_system.memories
                if m.id not in collected_ids and not m.should_archive()
            ]
            remaining.sort(key=lambda m: m.priority(), reverse=True)
            collected_memories.extend(
                remaining[:max_memories - len(collected_memories)])

        top = collected_memories[:max_memories]

        # 触发记录
        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        memory_system._save_memories()

        return memory_system._format_memory_list(top)

    # ─── P0.39 Phase 2: 多步重建策略 ──────────────

    def reconstruct_with_strategy(
        self, query: str, memory_system, strategy: str = "auto",
        llm_provider=None, max_rounds: int = 5
    ) -> str:
        """根据复杂度类型选择策略进行记忆重建

        P0.39 Phase 2: 在标准重建流程之上，根据问题类型选择
        不同的重建策略，使检索结果更贴合问题意图。

        参数:
            query: 用户问题
            memory_system: 记忆系统实例
            strategy: 策略类型

                - ``"auto"`` — 自动判断复杂度类型（默认）
                - ``"temporal"`` — 时序策略，按时间线组织
                - ``"cross_topic"`` — 跨主题策略，对比不同主题
                - ``"reasoning"`` — 推理策略，链式检索
                - ``"default"`` — 标准重建流程

            llm_provider: LLM 提供者（可选）
            max_rounds: 最大重建轮次

        返回:
            格式化的记忆上下文字符串
        """
        if llm_provider:
            self.llm = llm_provider

        # auto 模式：自动判断复杂度类型
        if strategy == "auto":
            result = self.is_complex_query(query)
            if not result["is_complex"]:
                return memory_system._format_memories(15)
            strategy = result["signal_type"]
            if strategy in ("none", "multi_hop"):
                strategy = "default"

        if strategy == "temporal":
            return self._reconstruct_temporal(
                query, memory_system, llm_provider, max_rounds)
        elif strategy == "cross_topic":
            return self._reconstruct_cross_topic(
                query, memory_system, llm_provider, max_rounds)
        elif strategy == "reasoning":
            return self._reconstruct_reasoning(
                query, memory_system, llm_provider, max_rounds)
        else:
            return self.reconstruct(
                query, memory_system, llm_provider, max_rounds)

    def _reconstruct_temporal(
        self, query: str, memory_system, llm_provider=None,
        max_rounds: int = 5
    ) -> str:
        """时序策略：按时间线组织检索结果

        适用于含时序信号词的问题（之前/上次/那天/还记得/什么时候）。
        先执行标准 Cue-Tag-Content 检索，再按记忆创建时间排序，
        构建从旧到新的时间线视图。

        参数:
            query: 用户问题
            memory_system: 记忆系统实例
            llm_provider: LLM 提供者
            max_rounds: 最大重建轮次

        返回:
            时间线格式的记忆上下文字符串
        """
        if llm_provider:
            self.llm = llm_provider

        # 提取初始 Cue
        cues = self._extract_cues(query) if self.llm else \
            self._fallback_cue_extraction(query)
        if not cues:
            cues = self._fallback_cue_extraction(query)

        # 激活 Tag → 选择 → 检索 Content
        candidate_tags = self._activate_tags(cues, memory_system)
        selected_tags = self._select_tags(cues, candidate_tags)
        evidence = self._retrieve_content(
            selected_tags, memory_system) if selected_tags else []

        # 补充：直接用 Cue 匹配内容
        cue_set = set(c.lower() for c in cues)
        for mem in memory_system.memories:
            if mem.should_archive() or mem in evidence:
                continue
            content_lower = mem.content.lower()
            if any(cue in content_lower for cue in cue_set):
                evidence.append(mem)

        if not evidence:
            return memory_system._format_memories(15)

        # 按时间线排序（旧 → 新）
        evidence.sort(key=lambda m: m.created_at)
        top = evidence[:15]

        # 触发记录
        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        memory_system._save_memories()

        return self._format_timeline(top)

    def _reconstruct_cross_topic(
        self, query: str, memory_system, llm_provider=None,
        max_rounds: int = 5
    ) -> str:
        """跨主题策略：对比检索不同主题的记忆

        适用于含跨主题信号词的问题（相比/不同/区别/变化/之前vs现在）。
        先执行标准检索，再按主题（tags 或 dimension）分组，
        组织为多主题对比视图。

        参数:
            query: 用户问题
            memory_system: 记忆系统实例
            llm_provider: LLM 提供者
            max_rounds: 最大重建轮次

        返回:
            跨主题对比格式的记忆上下文字符串
        """
        if llm_provider:
            self.llm = llm_provider

        # 提取 Cue
        cues = self._extract_cues(query) if self.llm else \
            self._fallback_cue_extraction(query)
        if not cues:
            cues = self._fallback_cue_extraction(query)

        # 激活 Tag → 选择 → 检索
        candidate_tags = self._activate_tags(cues, memory_system)
        selected_tags = self._select_tags(cues, candidate_tags)
        evidence = self._retrieve_content(
            selected_tags, memory_system) if selected_tags else []

        # 补充：直接用 Cue 匹配
        cue_set = set(c.lower() for c in cues)
        for mem in memory_system.memories:
            if mem.should_archive() or mem in evidence:
                continue
            content_lower = mem.content.lower()
            if any(cue in content_lower for cue in cue_set):
                evidence.append(mem)

        if not evidence:
            return memory_system._format_memories(15)

        # 按主题分组：优先使用 tags，回退到 dimension
        by_topic: Dict[str, list] = {}
        for mem in evidence:
            topics = mem.tags if mem.tags else [mem.dimension]
            for topic in topics:
                by_topic.setdefault(topic, []).append(mem)

        # 主题太少时用 dimension 补充分组
        if len(by_topic) < 2:
            by_topic = {}
            for mem in evidence:
                by_topic.setdefault(mem.dimension, []).append(mem)

        top = evidence[:15]

        # 触发记录
        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        memory_system._save_memories()

        return self._format_cross_topic(by_topic, top)

    def _reconstruct_reasoning(
        self, query: str, memory_system, llm_provider=None,
        max_rounds: int = 5
    ) -> str:
        """推理策略：链式检索，每步基于上一步结果

        适用于含推理信号词的问题（为什么/怎么会/如果/假设）。
        迭代式检索，每轮从上一步的证据中提取新 Cue，构建推理链。
        与标准重建的区别：更强调推理深度，记录每步的检索路径。

        参数:
            query: 用户问题
            memory_system: 记忆系统实例
            llm_provider: LLM 提供者
            max_rounds: 最大重建轮次

        返回:
            推理链格式的记忆上下文字符串
        """
        if llm_provider:
            self.llm = llm_provider

        # 无 LLM 或记忆太少 → 退化到标准重建
        if not self.llm or len(memory_system.memories) < 3:
            return self.reconstruct(
                query, memory_system, llm_provider, max_rounds)

        collected: list = []
        collected_ids: Set[str] = set()
        reasoning_chain: List[Dict] = []

        # 初始 Cue
        cues = self._extract_cues(query)
        if not cues:
            cues = self._fallback_cue_extraction(query)

        reasoning_chain.append(
            {"step": 1, "cues": list(cues), "found": 0})

        for round_num in range(max_rounds):
            # 激活 Tag
            candidate_tags = self._activate_tags(cues, memory_system)
            if not candidate_tags:
                # 直接用 Cue 匹配内容
                for mem in memory_system.memories:
                    if mem.id in collected_ids or mem.should_archive():
                        continue
                    content_lower = mem.content.lower()
                    if any(cue.lower() in content_lower for cue in cues):
                        collected.append(mem)
                        collected_ids.add(mem.id)
                reasoning_chain[-1]["found"] = len(collected)
                break

            selected_tags = self._select_tags(cues, candidate_tags)
            if not selected_tags:
                break

            new_evidence = self._retrieve_content(
                selected_tags, memory_system, exclude_ids=collected_ids)
            if not new_evidence:
                break

            for mem in new_evidence:
                collected.append(mem)
                collected_ids.add(mem.id)

            reasoning_chain[-1]["found"] = len(new_evidence)

            # 推理策略：判断是否需要继续链式检索
            sufficient, new_cues = self._judge_sufficiency(
                query, collected)

            if sufficient:
                break

            if new_cues:
                new_unique = [c for c in new_cues if c not in cues]
                if not new_unique:
                    break
                cues = new_unique
                reasoning_chain.append(
                    {"step": round_num + 2, "cues": list(cues), "found": 0})
            else:
                break

        if not collected:
            return self.reconstruct(
                query, memory_system, llm_provider, max_rounds)

        # 按优先级排序
        collected.sort(key=lambda m: m.priority(), reverse=True)
        top = collected[:15]

        # 触发记录
        now = datetime.now().isoformat()
        for m in top:
            m.trigger_count += 1
            m.last_triggered = now
        memory_system._save_memories()

        return self._format_reasoning(top, reasoning_chain)

    # ─── P0.39 Phase 2: 格式化辅助 ──────────────

    @staticmethod
    def _format_timeline(memories: list) -> str:
        """将记忆按时间线格式化（旧 → 新）"""
        if not memories:
            return ""
        parts = ["【时间线记忆重建】"]
        for m in memories:
            try:
                dt = datetime.fromisoformat(m.created_at)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_str = m.created_at[:16] if m.created_at else "未知时间"
            parts.append(f"  [{date_str}] {m.content}")
        return "\n".join(parts)

    @staticmethod
    def _format_cross_topic(by_topic: Dict[str, list],
                            all_memories: list) -> str:
        """将记忆按主题对比格式化"""
        if not all_memories:
            return ""
        parts = ["【跨主题记忆对比】"]
        grouped_ids: Set[str] = set()
        for topic, memories in by_topic.items():
            parts.append(f"  ◆ 主题: {topic}")
            for m in memories[:5]:
                parts.append(f"    - {m.content}")
                grouped_ids.add(m.id)
        # 补充未分组记忆
        ungrouped = [m for m in all_memories if m.id not in grouped_ids]
        if ungrouped:
            parts.append("  ◆ 其他")
            for m in ungrouped[:5]:
                parts.append(f"    - {m.content}")
        return "\n".join(parts)

    @staticmethod
    def _format_reasoning(memories: list,
                          chain: List[Dict]) -> str:
        """将记忆按推理链格式化"""
        if not memories:
            return ""
        parts = ["【推理链记忆重建】"]
        if len(chain) > 1:
            parts.append(f"  推理深度: {len(chain)} 步")
            for step in chain:
                cues_str = ", ".join(step["cues"][:3])
                parts.append(
                    f"    步骤{step['step']}: 检索词=[{cues_str}] → "
                    f"找到 {step['found']} 条")
        parts.append("  相关记忆:")
        for m in memories:
            parts.append(f"    - {m.content}")
        return "\n".join(parts)

    # ─── P0.39 Phase 2: 重建质量评估 ──────────────

    def evaluate_reconstruction(self, query: str, result: str) -> dict:
        """评估重建结果质量

        对重建结果进行无 LLM 的启发式评估，计算覆盖度、置信度，
        并识别可能缺失的方面。

        参数:
            query: 用户问题
            result: 重建结果文本（reconstruct 等方法的返回值）

        返回:
            ``{coverage: float, confidence: float, missing_aspects: list}``

            - **coverage** (0.0~1.0): query 关键词在结果中出现的比例
            - **confidence** (0.0~1.0): 基于结果长度和记忆条数的置信度
            - **missing_aspects**: 缺失方面列表（空列表表示无缺失）
        """
        if not result or not result.strip():
            return {
                "coverage": 0.0,
                "confidence": 0.0,
                "missing_aspects": ["无结果"],
            }

        # 提取 query 关键词
        query_cues = self._fallback_cue_extraction(query)
        if not query_cues:
            query_cues = [query.strip()[:5]] if query.strip() else []

        # 覆盖度：query 关键词在结果中出现的比例
        result_lower = result.lower()
        matched = sum(1 for cue in query_cues
                      if cue.lower() in result_lower)
        coverage = matched / len(query_cues) if query_cues else 0.0

        # 置信度：基于结果长度和记忆条数
        memory_count = result.count("- [") + result.count("    - ") + \
            result.count("  - [")
        length_factor = min(len(result) / 500.0, 1.0)  # 500 字符为满分
        count_factor = min(memory_count / 5.0, 1.0)    # 5 条记忆为满分
        confidence = length_factor * 0.4 + count_factor * 0.6

        # 识别缺失方面
        missing_aspects: List[str] = []
        if coverage < 0.3:
            missing_aspects.append("关键词覆盖不足")
        if memory_count < 2:
            missing_aspects.append("相关记忆数量不足")
        if len(result) < 100:
            missing_aspects.append("结果内容过短")
        if coverage < 0.5 and confidence < 0.5:
            missing_aspects.append("可能需要补充检索")

        return {
            "coverage": round(coverage, 3),
            "confidence": round(confidence, 3),
            "missing_aspects": missing_aspects,
        }
