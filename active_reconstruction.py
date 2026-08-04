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


class ActiveReconstructor:
    """主动记忆重建引擎

    通过 Cue-Tag-Content 三层关联图进行迭代式记忆重建。
    每轮：提取Cue → 激活Tag → 检索Content → 判断充分性 → (不充分)提取新Cue
    """

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    # ─── 复杂度判断 ─────────────────────────────

    @staticmethod
    def is_complex_query(query: str) -> bool:
        """判断问题是否需要主动重建（多跳/复杂问题）

        简单问题（单跳）走被动检索：
        - query长度 < 20 且不含多跳信号词 → 简单
        - 否则 → 复杂，需要主动重建
        """
        if not query or not query.strip():
            return False
        if len(query) < 20 and not any(sig in query for sig in MULTI_HOP_SIGNALS):
            return False
        return True

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
