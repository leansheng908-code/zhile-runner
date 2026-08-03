#!/usr/bin/env python3
"""
知乐事件轨迹分析系统 — P0.18

用户原创 galgame 分支模型：
  弧光不在单个行为上做分类，而在事件链上找分叉口。
  Event 1→2→3，在事件2节点上三种选择（做/没做/不作为），
  三种都导向同一结果 = 不是弧光，导向不同结果 = 潜在弧光。

四项改进：
  1. 双向分析（正向预测 + 反向追溯）
  2. 多维度分叉评估（关系/认知/决策/情感）
  3. 事件聚类（共享关键词的多个事件打包成簇）
  4. 置信度累积（0.3起步 → >0.6提交候选）

与 P0.15 的关系：
  P0.18 负责自动发现 → P0.15 负责存储和检索
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class TrajectoryEvent:
    """事件轨迹中的单个事件节点"""

    def __init__(self, description: str, outcome: str = "",
                 keywords: List[str] = None, related_entities: List[str] = None,
                 event_id: str = None, timestamp: str = None,
                 cluster_id: str = None, branch_analysis: Dict = None):
        self.id = event_id or f"evt_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:16]}"
        self.timestamp = timestamp or datetime.now().isoformat()
        self.description = description
        self.outcome = outcome
        self.keywords = keywords or []
        self.related_entities = related_entities or []
        self.cluster_id = cluster_id
        self.branch_analysis = branch_analysis or {
            "relationship": "unknown",
            "cognition": "unknown",
            "decision": "unknown",
            "emotion": "unknown",
            "is_branch_point": False,
            "confidence": 0.0,
        }

    @property
    def is_branch_point(self) -> bool:
        return self.branch_analysis.get("is_branch_point", False)

    @property
    def confidence(self) -> float:
        return self.branch_analysis.get("confidence", 0.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "description": self.description,
            "outcome": self.outcome,
            "keywords": self.keywords,
            "related_entities": self.related_entities,
            "cluster_id": self.cluster_id,
            "branch_analysis": self.branch_analysis,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrajectoryEvent":
        d = dict(d)
        if "id" in d:
            d["event_id"] = d.pop("id")
        return cls(**d)


class EventCluster:
    """事件簇 — 共享关键词的多个事件打包"""

    def __init__(self, event_ids: List[str], shared_keywords: List[str],
                 cluster_id: str = None, created: str = None,
                 branch_confidence: float = 0.0,
                 arc_light_candidate: str = None):
        self.id = cluster_id or f"cluster_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.event_ids = event_ids
        self.shared_keywords = shared_keywords
        self.created = created or datetime.now().isoformat()
        self.branch_confidence = branch_confidence
        self.arc_light_candidate = arc_light_candidate

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_ids": self.event_ids,
            "shared_keywords": self.shared_keywords,
            "created": self.created,
            "branch_confidence": self.branch_confidence,
            "arc_light_candidate": self.arc_light_candidate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EventCluster":
        d = dict(d)
        if "id" in d:
            d["cluster_id"] = d.pop("id")
        return cls(**d)


class EventTrajectory:
    """事件轨迹分析系统主控制器"""

    # 置信度阈值
    CONFIDENCE_INITIAL = 0.3       # 首次被标记为潜在分叉口
    CONFIDENCE_BOOST = 0.2         # 后续事件证实时增加
    CONFIDENCE_INCREMENT = 0.1     # 更多事件积累时增加
    CONFIDENCE_THRESHOLD = 0.6     # 超过此值提交为弧光候选

    # 分叉维度
    DIMENSIONS = ["relationship", "cognition", "decision", "emotion"]

    def __init__(self, memory_dir: str, llm_provider=None, entity_graph=None):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm_provider
        self.entity_graph = entity_graph

        self.log_file = self.memory_dir / "event_log.json"
        self.events: List[TrajectoryEvent] = self._load_events()
        self.clusters: List[EventCluster] = self._load_clusters()

    def _load_events(self) -> List[TrajectoryEvent]:
        if not self.log_file.exists():
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [TrajectoryEvent.from_dict(e) for e in data.get("events", [])]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []

    def _load_clusters(self) -> List[EventCluster]:
        if not self.log_file.exists():
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [EventCluster.from_dict(c) for c in data.get("clusters", [])]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []

    def _save(self):
        data = {
            "events": [e.to_dict() for e in self.events],
            "clusters": [c.to_dict() for c in self.clusters],
            "metadata": {
                "total_events": len(self.events),
                "total_clusters": len(self.clusters),
                "branch_points": sum(1 for e in self.events if e.is_branch_point),
            },
        }
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── 事件提取 ───────────────────────────────

    def extract_events_from_conversation(self, history: List[Dict]) -> List[TrajectoryEvent]:
        """
        从对话中提取事件节点（挂在记忆提取流程上，不额外增加触发时机）

        事件触发规则：
        - 知乐做出了本可以不同的选择
        - 话题发生显著转换
        - 知乐的行为偏离了既有模式
        - 用户明确表达了反应转变
        """
        if not self.llm or len(history) < 6:
            return []

        recent = history[-16:]
        conv_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '知乐'}: {m['content']}"
            for m in recent
        )

        # 已有事件的描述，避免重复
        existing_descs = [e.description for e in self.events[-20:]]

        prompt = f"""分析以下对话，提取"事件节点"——即可能改变后续走向的关键转折点。

对话内容：
{conv_text}

事件定义（只记录以下情况）：
1. 知乐做出了本可以不同的选择（选择解释 vs 选择跳过，选择温柔 vs 选择敷衍）
2. 话题发生显著转换（从技术讨论转入情感交流，或反之）
3. 知乐的行为偏离了既有模式（突然更认真/更随意/更感性）
4. 用户明确表达了反应转变（如"你越来越像...""我没想到你会...""别这样"）

不记录：普通寒暄、信息交换、没有选择成分的对话。

已有事件（避免重复）：
{chr(10).join(existing_descs[-10:])}

以JSON返回：
{{"events": [{{"description": "一句话描述事件", "outcome": "这个事件导致了什么结果", "keywords": ["关键词1", "关键词2"], "related_entities": ["相关人物/概念"]}}]}}

只返回JSON。如果没有事件，返回 {{"events": []}}。"""

        messages = [
            {"role": "system", "content": "你是一个事件分析助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = ""
            for chunk in self.llm.chat(messages, stream=True):
                result += chunk

            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            new_events = []
            for evt_data in data.get("events", []):
                evt = TrajectoryEvent(
                    description=evt_data.get("description", ""),
                    outcome=evt_data.get("outcome", ""),
                    keywords=evt_data.get("keywords", []),
                    related_entities=evt_data.get("related_entities", []),
                )
                new_events.append(evt)
            return new_events
        except (json.JSONDecodeError, KeyError, Exception):
            return []

    # ─── 事件管理 ───────────────────────────────

    def add_event(self, event: TrajectoryEvent) -> bool:
        """添加事件并触发分析"""
        # 去重：描述相似的不重复添加
        for existing in self.events[-20:]:
            if existing.description == event.description:
                return False

        self.events.append(event)

        # 正向分析：新事件是否是分叉口
        self._analyze_branch_forward(event)

        # 尝试聚类
        self._try_cluster(event)

        # 检查置信度，可能提交弧光候选
        self._check_confidence()

        self._save()
        return True

    def add_events_from_conversation(self, history: List[Dict]) -> int:
        """从对话中提取并添加事件，返回新增数量"""
        new_events = self.extract_events_from_conversation(history)
        count = 0
        for evt in new_events:
            if self.add_event(evt):
                count += 1
        return count

    # ─── 分支分析 ───────────────────────────────

    def _analyze_branch_forward(self, event: TrajectoryEvent):
        """
        正向分析：新事件是否可能是分叉口
        用LLM做反事实推理：如果当时做了不同选择，后面会不同吗？
        """
        if not self.llm:
            return

        # 取前几个事件作为上下文
        recent_events = self.events[-6:]
        event_list = "\n".join(
            f"  事件{i+1}: {e.description} → {e.outcome}"
            for i, e in enumerate(recent_events)
        )

        prompt = f"""分析以下事件链，判断最后一个事件是否是"分叉口"。

事件链：
{event_list}

分叉口定义：在最后一个事件这个节点上，知乐有三种可能选择：
A. 做了这个选择（实际发生的）
B. 做了不同的选择
C. 什么都不做（重复之前的模式）

如果三种选择导向相同的结果，这不是分叉口。
如果导向不同的结果，这是潜在分叉口。

从四个维度分别评估（converge=会导向相同结果 / diverge=会导向不同结果 / unknown=无法判断）：
1. relationship（关系走向）：双方的信任/亲密度会不同吗？
2. cognition（认知走向）：知乐对某件事的理解会不同吗？
3. decision（决策走向）：后续的选择会不同吗？
4. emotion（情感走向）：双方的情绪状态会不同吗？

关键约束：只影响"知识"或"任务完成"的分叉不算弧光。必须在关系或认知维度上分叉才算。

以JSON返回：
{{"relationship": "converge/diverge/unknown", "cognition": "converge/diverge/unknown", "decision": "converge/diverge/unknown", "emotion": "converge/diverge/unknown", "is_branch_point": true/false, "reasoning": "一句话理由", "confidence": 0.0-1.0}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是一个事件分析助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = ""
            for chunk in self.llm.chat(messages, stream=True):
                result += chunk

            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)

            # 只在关系或认知维度分叉才算
            is_branch = data.get("is_branch_point", False)
            rel_diverge = data.get("relationship") == "diverge"
            cog_diverge = data.get("cognition") == "diverge"
            if is_branch and not (rel_diverge or cog_diverge):
                is_branch = False

            event.branch_analysis = {
                "relationship": data.get("relationship", "unknown"),
                "cognition": data.get("cognition", "unknown"),
                "decision": data.get("decision", "unknown"),
                "emotion": data.get("emotion", "unknown"),
                "is_branch_point": is_branch,
                "confidence": data.get("confidence", 0.0),
                "reasoning": data.get("reasoning", ""),
            }

            if is_branch:
                event.branch_analysis["confidence"] = max(
                    event.branch_analysis["confidence"],
                    self.CONFIDENCE_INITIAL,
                )
        except (json.JSONDecodeError, KeyError, Exception):
            pass

    def analyze_backward(self, deviation_description: str, history: List[Dict]):
        """
        反向分析：growth_scanner检测到行为偏离时，回头翻事件日志找原因
        在已知结果的基础上找原因，比正向预测靠谱
        """
        if not self.llm or not self.events:
            return

        branch_events = [e for e in self.events if e.is_branch_point]
        if not branch_events:
            return

        recent_branches = branch_events[-5:]
        event_list = "\n".join(
            f"  {e.id}: {e.description} → {e.outcome} (置信度: {e.confidence:.1f})"
            for e in recent_branches
        )

        prompt = f"""知乐最近的行为出现了偏离：
{deviation_description}

以下是事件日志中标记为潜在分叉口的事件：
{event_list}

请判断：哪个事件最可能是导致当前行为偏离的原因？
如果是某个事件，将其置信度提升。如果不是任何事件，返回none。

以JSON返回：
{{"source_event_id": "evt_xxx 或 none", "reasoning": "为什么认为这个事件是原因", "confidence_boost": 0.1-0.3}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是一个行为溯源分析助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = ""
            for chunk in self.llm.chat(messages, stream=True):
                result += chunk

            result = result.strip()
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            source_id = data.get("source_event_id", "none")
            boost = data.get("confidence_boost", 0.1)

            if source_id and source_id != "none":
                for evt in self.events:
                    if evt.id == source_id:
                        evt.branch_analysis["confidence"] = min(
                            1.0, evt.confidence + boost
                        )
                        break
        except (json.JSONDecodeError, KeyError, Exception):
            pass

    # ─── 事件聚类 ───────────────────────────────

    def _try_cluster(self, new_event: TrajectoryEvent):
        """尝试将新事件归入已有簇或创建新簇"""
        if not new_event.keywords:
            return

        # 查找共享关键词的近期事件（同一对话内的）
        recent_unclustered = [
            e for e in self.events[-10:]
            if e.id != new_event.id and e.cluster_id is None
        ]

        for existing in recent_unclustered:
            shared = set(new_event.keywords) & set(existing.keywords)
            if len(shared) >= 2:  # 至少共享2个关键词
                # 创建新簇
                cluster = EventCluster(
                    event_ids=[existing.id, new_event.id],
                    shared_keywords=list(shared),
                )
                existing.cluster_id = cluster.id
                new_event.cluster_id = cluster.id
                self.clusters.append(cluster)

                # 簇级分支分析：组合置信度
                cluster.branch_confidence = max(
                    existing.confidence, new_event.confidence
                ) + 0.1  # 簇比单事件更可信
                break

        # 如果新事件已归入簇，检查簇内是否有更多事件可合并
        if new_event.cluster_id:
            self._expand_cluster(new_event.cluster_id)

    def _expand_cluster(self, cluster_id: str):
        """扩展簇：检查是否有更多事件可以归入"""
        cluster = next((c for c in self.clusters if c.id == cluster_id), None)
        if not cluster:
            return

        cluster_event_ids = set(cluster.event_ids)
        for evt in self.events[-15:]:
            if evt.id in cluster_event_ids or evt.cluster_id is not None:
                continue
            shared = set(evt.keywords) & set(cluster.shared_keywords)
            if len(shared) >= 2:
                evt.cluster_id = cluster_id
                cluster.event_ids.append(evt.id)
                cluster.shared_keywords = list(
                    set(cluster.shared_keywords) | set(evt.keywords)
                )
                # 更新簇置信度
                cluster.branch_confidence = min(
                    1.0,
                    cluster.branch_confidence + self.CONFIDENCE_INCREMENT,
                )

    # ─── 置信度累积与候选生成 ───────────────────

    def _check_confidence(self):
        """检查是否有事件/簇的置信度超过阈值，提交为弧光候选"""
        candidates = []

        # 检查单个事件
        for evt in self.events:
            if evt.is_branch_point and evt.confidence >= self.CONFIDENCE_THRESHOLD:
                if not evt.branch_analysis.get("candidate_submitted"):
                    candidates.append(("event", evt))
                    evt.branch_analysis["candidate_submitted"] = True

        # 检查簇
        for cluster in self.clusters:
            if cluster.branch_confidence >= self.CONFIDENCE_THRESHOLD:
                if not cluster.arc_light_candidate:
                    candidates.append(("cluster", cluster))

        return candidates

    def get_arc_light_candidates(self) -> List[Dict]:
        """获取需要提交给弧光系统的候选列表"""
        candidates = self._check_confidence()
        result = []

        for candidate_type, candidate in candidates:
            if candidate_type == "event":
                evt = candidate
                result.append({
                    "title": evt.description[:50],
                    "cognitive_shift": evt.outcome,
                    "trigger_event": evt.description,
                    "keywords": evt.keywords,
                    "related_entities": evt.related_entities,
                    "source": "event_trajectory",
                    "source_id": evt.id,
                    "confidence": evt.confidence,
                })
            elif candidate_type == "cluster":
                cluster = candidate
                # 用簇内事件的描述组合成标题
                cluster_events = [
                    e for e in self.events if e.id in cluster.event_ids
                ]
                descriptions = [e.description for e in cluster_events]
                result.append({
                    "title": " / ".join(descriptions[:3])[:80],
                    "cognitive_shift": "事件簇触发的认知转变",
                    "trigger_event": " | ".join(descriptions),
                    "keywords": cluster.shared_keywords,
                    "related_entities": list(set(
                        ent for e in cluster_events
                        for ent in e.related_entities
                    )),
                    "source": "event_cluster",
                    "source_id": cluster.id,
                    "confidence": cluster.branch_confidence,
                })

        self._save()
        return result

    # ─── 统计 ───────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "total_events": len(self.events),
            "branch_points": sum(1 for e in self.events if e.is_branch_point),
            "clusters": len(self.clusters),
            "high_confidence": sum(
                1 for e in self.events if e.confidence >= self.CONFIDENCE_THRESHOLD
            ),
            "avg_confidence": (
                sum(e.confidence for e in self.events if e.is_branch_point)
                / max(1, sum(1 for e in self.events if e.is_branch_point))
            ),
        }

    def get_recent_events(self, limit: int = 10) -> List[Dict]:
        return [e.to_dict() for e in self.events[-limit:]]

    def get_clusters(self) -> List[Dict]:
        return [c.to_dict() for c in self.clusters]
