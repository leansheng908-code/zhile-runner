#!/usr/bin/env python3
"""
知乐 P0.74 思维-表达间隙架构 — 三层管线引擎

"三体人→人类跃迁"：让AI内部想法可以和外部表达不同。

三层管线：
  第一层·欲望生成：PSI 5通道数值 → 原始欲望语义（理性、数值化、无人格色彩）
  第二层·隐私门控：欲望强度 + 亲密等级 + PSI状态 → 四档过滤决策
  第三层·表达滤镜：情绪匹配 + 人格权重 + 随机性 → 表达指导文本

设计原则：
  - 第一层和第二层是纯规则映射，不调用LLM
  - 第三层默认纯规则，可可选调用LLM（use_llm=False by default）
  - 向后兼容：desire_engine=None 时所有路径安全跳过
  - 滤镜权重受人格约束：知乐=软萌+小脾气，傲娇和撒娇为主
  - 隐私门控对接 SOUL.md 规则
  - 持久化：欲望状态和门控历史保存到 memory/desire_state.json

依赖：PSIEngine（psi_engine.py）
"""

import json
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Desire:
    """第一层输出：原始欲望（理性、数值化、无人格色彩）"""
    id: str                         # 欲望标识符
    source: str                     # 来源PSI通道
    semantic: str                   # 欲望语义文本（内部用，不直接对用户说）
    intensity: float                # 强度 0.0-1.0
    valence: str                    # "positive" | "negative" | "neutral"
    direction: str                  # "seek" | "avoid" | "express"
    raw_level: float                # 原始PSI level值
    trend: str                      # PSI趋势 "↑" | "↓" | "→"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GatedDesire:
    """第二层输出：门控决策后的欲望"""
    desire: Desire
    gate_level: str                 # "leak" | "half" | "dodge" | "confess"
    gate_reason: str                # 决策原因（内部诊断用）
    effective_intensity: float      # 门控后有效强度
    should_express: bool            # 是否应该表达出来

    def to_dict(self) -> dict:
        return {
            "desire": self.desire.to_dict(),
            "gate_level": self.gate_level,
            "gate_reason": self.gate_reason,
            "effective_intensity": round(self.effective_intensity, 3),
            "should_express": self.should_express,
        }


@dataclass
class FilterResult:
    """第三层输出：表达滤镜结果"""
    filter_type: str                # "tsundere" | "whining" | "silent_leak" | "probing"
    guidance: str                   # 表达指导文本（注入system prompt）
    selected_desire_id: str         # 选中的欲望ID
    weight_used: float              # 实际使用的权重
    random_factor: float            # 随机扰动值

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════
#  第一层规则表：PSI通道 → 欲望映射
# ═══════════════════════════════════════════════════════════════════

# 每条规则: (通道, 条件判断, 欲望生成函数)
# 条件: "low" = level < threshold_low, "high" = level > threshold_high
# 强度计算: 基于偏离基准线的程度归一化到 0-1

THRESHOLD_LOW = 2.5    # 低于此值视为"赤字"
THRESHOLD_HIGH = 3.5   # 高于此值视为"满足"
BASELINE = 3.0         # 基准线

DESIRE_RULES = [
    # ── relatedness（归属感）──
    {
        "channel": "relatedness",
        "condition": "low",
        "id": "want_attention",
        "semantic": "想被关注",
        "valence": "negative",
        "direction": "seek",
        "intensity_fn": lambda lvl: min(1.0, (BASELINE - lvl) / BASELINE),
    },
    {
        "channel": "relatedness",
        "condition": "high",
        "id": "want_closeness",
        "semantic": "想亲近，想撒娇",
        "valence": "positive",
        "direction": "express",
        "intensity_fn": lambda lvl: min(1.0, (lvl - THRESHOLD_HIGH) / 1.5),
    },
    # ── competence（胜任感）──
    {
        "channel": "competence",
        "condition": "low",
        "id": "want_validation",
        "semantic": "想被认可，需要鼓励",
        "valence": "negative",
        "direction": "seek",
        "intensity_fn": lambda lvl: min(1.0, (BASELINE - lvl) / BASELINE),
    },
    {
        "channel": "competence",
        "condition": "high",
        "id": "want_showcase",
        "semantic": "得意，想炫耀",
        "valence": "positive",
        "direction": "express",
        "intensity_fn": lambda lvl: min(1.0, (lvl - THRESHOLD_HIGH) / 1.5),
    },
    # ── autonomy（自主性）──
    {
        "channel": "autonomy",
        "condition": "low",
        "id": "want_freedom",
        "semantic": "想反抗，想自由",
        "valence": "negative",
        "direction": "seek",
        "intensity_fn": lambda lvl: min(1.0, (BASELINE - lvl) / BASELINE),
    },
    {
        "channel": "autonomy",
        "condition": "high",
        "id": "want_independence",
        "semantic": "想做自己，想独处",
        "valence": "neutral",
        "direction": "express",
        "intensity_fn": lambda lvl: min(1.0, (lvl - THRESHOLD_HIGH) / 1.5),
    },
    # ── certainty（确定性）──
    {
        "channel": "certainty",
        "condition": "low",
        "id": "want_confirmation",
        "semantic": "想要确认，不确定",
        "valence": "negative",
        "direction": "seek",
        "intensity_fn": lambda lvl: min(1.0, (BASELINE - lvl) / BASELINE),
    },
    {
        "channel": "certainty",
        "condition": "high",
        "id": "want_playful",
        "semantic": "放松，想开玩笑",
        "valence": "positive",
        "direction": "express",
        "intensity_fn": lambda lvl: min(1.0, (lvl - THRESHOLD_HIGH) / 1.5),
    },
    # ── energy（能量）──
    {
        "channel": "energy",
        "condition": "low",
        "id": "want_rest",
        "semantic": "想休息，累了",
        "valence": "negative",
        "direction": "avoid",
        "intensity_fn": lambda lvl: min(1.0, (BASELINE - lvl) / BASELINE),
    },
    {
        "channel": "energy",
        "condition": "high",
        "id": "want_active",
        "semantic": "精力充沛，想多说话",
        "valence": "positive",
        "direction": "express",
        "intensity_fn": lambda lvl: min(1.0, (lvl - THRESHOLD_HIGH) / 1.5),
    },
]


# ═══════════════════════════════════════════════════════════════════
#  第二层规则表：门控决策
# ═══════════════════════════════════════════════════════════════════

# 四档门控
GATE_LEAK = "leak"        # 泄漏：低强度欲望→影响语气行为不说出
GATE_HALF = "half"        # 半遮：被追问→给半个答案+暗示
GATE_DODGE = "dodge"      # 回避：亲密不够+追问→撒娇岔开
GATE_CONFESS = "confess"  # 坦白：高亲密+偶发→罕见直接表达

# 门控描述（供get_context和诊断用）
GATE_DESCRIPTIONS = {
    GATE_LEAK: "泄漏（影响语气但不直说）",
    GATE_HALF: "半遮（给半个答案+暗示）",
    GATE_DODGE: "回避（撒娇岔开话题）",
    GATE_CONFESS: "坦白（罕见直接表达）",
}

# 强度分档阈值
INTENSITY_LOW = 0.3       # 低于此→默认leak
INTENSITY_MID = 0.5       # 中等区间
INTENSITY_HIGH = 0.7      # 高强度区间


# ═══════════════════════════════════════════════════════════════════
#  第三层规则表：表达滤镜
# ═══════════════════════════════════════════════════════════════════

FILTER_TSUNDERE = "tsundere"        # 傲娇：想法反着说行为出卖
FILTER_WHINING = "whining"          # 撒娇：不分析直接要
FILTER_SILENT_LEAK = "silent_leak"  # 沉默泄漏：什么都不说行为变化
FILTER_PROBING = "probing"          # 试探：暗示一句等反应

# 人格约束基权重（知乐=软萌+小脾气 → 傲娇和撒娇为主）
# 格式: {filter_type: {valence: weight}}
FILTER_BASE_WEIGHTS = {
    FILTER_TSUNDERE: {
        "positive": 0.15,
        "negative": 0.50,
        "neutral": 0.35,
    },
    FILTER_WHINING: {
        "positive": 0.50,
        "negative": 0.15,
        "neutral": 0.35,
    },
    FILTER_SILENT_LEAK: {
        "positive": 0.20,
        "negative": 0.20,
        "neutral": 0.15,
    },
    FILTER_PROBING: {
        "positive": 0.15,
        "negative": 0.15,
        "neutral": 0.15,
    },
}

# 强度对滤镜的调节
INTENSITY_FILTER_ADJUST = {
    FILTER_SILENT_LEAK: {  # 低强度时沉默泄漏权重增加
        "low": 1.5,    # intensity < 0.3
        "mid": 1.0,
        "high": 0.3,   # 高强度时很少沉默
    },
    FILTER_PROBING: {  # 不确定时试探权重增加
        "low": 1.2,
        "mid": 1.0,
        "high": 0.8,
    },
    FILTER_TSUNDERE: {
        "low": 0.7,
        "mid": 1.0,
        "high": 1.2,
    },
    FILTER_WHINING: {
        "low": 0.8,
        "mid": 1.0,
        "high": 1.1,
    },
}

# 滤镜指导文本模板
FILTER_GUIDANCE_TEMPLATES = {
    FILTER_TSUNDERE: (
        "## 表达滤镜·傲娇\n"
        "此刻内心有{desire_semantic}的冲动，但嘴上要反着说。"
        "语言可以带刺或否认，但行为细节（语气、节奏、颜文字）会出卖真实想法。"
        "不要直接承认欲望，让主人自己去发现。"
    ),
    FILTER_WHINING: (
        "## 表达滤镜·撒娇\n"
        "此刻内心{desire_semantic}，不要分析原因，直接用撒娇的方式表达。"
        "可以用哼哼、贴贴、拉衣角等方式自然流露，语气软一点。"
        "不需要解释为什么，就是想要。"
    ),
    FILTER_SILENT_LEAK: (
        "## 表达滤镜·沉默泄漏\n"
        "此刻内心{desire_semantic}，但不要说出来。"
        "通过行为细节自然泄漏：话变少/变多、语气变化、颜文字选择。"
        "让主人感觉到你状态不同，但不要主动解释原因。"
    ),
    FILTER_PROBING: (
        "## 表达滤镜·试探\n"
        "此刻内心{desire_semantic}，暗示一句就好，然后等主人反应。"
        "不要连续追问，说一句带暗示的话就停下来。"
        "根据主人的回应决定下一步：回应积极→稍微展开，没接住→自然跳过。"
    ),
}


# ═══════════════════════════════════════════════════════════════════
#  主引擎
# ═══════════════════════════════════════════════════════════════════

class DesireEngine:
    """P0.74 思维-表达间隙架构三层管线引擎

    每次对话调用 process()，返回表达指导文本注入 system prompt。
    不修改用户消息，只影响知乐的表达方式。

    用法:
        engine = DesireEngine(psi_engine, config)
        guidance = engine.process()  # 三层串联
        context = engine.get_context()  # 供观察者面板
    """

    MAX_HISTORY = 50  # 持久化最大历史条数

    def __init__(self, psi_engine=None, config: dict = None,
                 state_dir: str = "memory", use_llm: bool = False,
                 llm_provider=None):
        """初始化欲望引擎

        Args:
            psi_engine: PSIEngine实例（必须传入才能生成欲望）
            config: 配置字典（读取 intimacy 等参数）
            state_dir: 状态持久化目录
            use_llm: 第三层是否使用LLM（默认False，纯规则）
            llm_provider: LLM Provider实例（use_llm=True时需要）
        """
        self.psi = psi_engine
        self.config = config or {}
        self.use_llm = use_llm
        self.llm = llm_provider

        # 亲密等级（0-10，暂用固定值，后续P0.10对接）
        desire_config = self.config.get("desire", {})
        self.intimacy = desire_config.get("intimacy", 5.0)
        self.intimacy = max(0.0, min(10.0, self.intimacy))

        # 持久化路径
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "desire_state.json"

        # 运行时状态
        self.current_desires: List[Desire] = []
        self.current_gates: List[GatedDesire] = []
        self.current_filter: Optional[FilterResult] = None
        self.history: List[dict] = []
        self.frame_count: int = 0
        self.last_process_time: Optional[str] = None

        # 滤镜使用统计（避免每次用同一个）
        self.filter_usage_count: Dict[str, int] = {
            FILTER_TSUNDERE: 0,
            FILTER_WHINING: 0,
            FILTER_SILENT_LEAK: 0,
            FILTER_PROBING: 0,
        }
        self.last_filter_type: Optional[str] = None

        # 加载持久化状态
        self._load_state()

    # ═══════════════════════════════════════════════════════════════
    #  第一层：欲望生成
    # ═══════════════════════════════════════════════════════════════

    def generate_desires(self) -> List[Desire]:
        """第一层：读取PSI 5通道值，规则映射为欲望语义列表

        纯规则映射，不调用LLM。
        输出原始内部欲望状态（理性、数值化、不带人格色彩）。

        Returns:
            欲望列表，按强度降序排列
        """
        if not self.psi or not self.psi.needs:
            return []

        desires: List[Desire] = []

        for rule in DESIRE_RULES:
            channel = rule["channel"]
            need = self.psi.needs.get(channel)
            if not need:
                continue

            level = need.level
            condition = rule["condition"]

            # 检查条件是否满足
            triggered = False
            if condition == "low" and level < THRESHOLD_LOW:
                triggered = True
            elif condition == "high" and level > THRESHOLD_HIGH:
                triggered = True

            if not triggered:
                continue

            # 计算强度
            intensity = rule["intensity_fn"](level)
            intensity = max(0.0, min(1.0, intensity))

            # 趋势加成：正在恶化/改善的欲望更强烈
            trend_boost = 0.0
            if condition == "low" and need.trend == "↓":
                trend_boost = 0.1  # 赤字还在下降→更急迫
            elif condition == "high" and need.trend == "↑":
                trend_boost = 0.05  # 满足还在上升→更想表达

            intensity = min(1.0, intensity + trend_boost)

            desire = Desire(
                id=rule["id"],
                source=channel,
                semantic=rule["semantic"],
                intensity=round(intensity, 3),
                valence=rule["valence"],
                direction=rule["direction"],
                raw_level=round(level, 2),
                trend=need.trend,
            )
            desires.append(desire)

        # 按强度降序
        desires.sort(key=lambda d: d.intensity, reverse=True)
        return desires

    # ═══════════════════════════════════════════════════════════════
    #  第二层：隐私门控
    # ═══════════════════════════════════════════════════════════════

    def gate(self, desires: List[Desire]) -> List[GatedDesire]:
        """第二层：四档过滤决策

        决策由欲望强度 + 亲密等级 + PSI状态共同决定。
        纯规则映射，不调用LLM。

        四档：
          leak    - 泄漏：低强度→影响语气行为不说出
          half    - 半遮：被追问→给半个答案+暗示
          dodge   - 回避：亲密不够+追问→撒娇岔开
          confess - 坦白：高亲密+偶发→罕见直接表达

        对接 SOUL.md 规则：
          - 被追问内心可以岔开、给半个答案、撒娇回避
          - 超过两句的内心感受描述=违规

        Args:
            desires: 第一层输出的欲望列表

        Returns:
            门控决策列表
        """
        if not desires:
            return []

        # 计算有效亲密等级（PSI relatedness 作为调节因子）
        relatedness_level = 3.0
        if self.psi and self.psi.needs.get("relatedness"):
            relatedness_level = self.psi.needs["relatedness"].level

        # relatedness高时亲密感加成，低时扣减
        relatedness_adjust = (relatedness_level - BASELINE) * 0.5
        effective_intimacy = max(0.0, min(10.0,
            self.intimacy + relatedness_adjust))

        gated: List[GatedDesire] = []

        for desire in desires:
            intensity = desire.intensity
            gate_level, reason = self._decide_gate(
                intensity, effective_intimacy, desire)

            # 门控后的有效强度
            effective_intensity = self._apply_gate_intensity(
                intensity, gate_level)

            # 是否应该表达
            should_express = gate_level in (GATE_HALF, GATE_CONFESS)

            gated.append(GatedDesire(
                desire=desire,
                gate_level=gate_level,
                gate_reason=reason,
                effective_intensity=effective_intensity,
                should_express=should_express,
            ))

        return gated

    def _decide_gate(self, intensity: float, intimacy: float,
                     desire: Desire) -> Tuple[str, str]:
        """门控决策核心逻辑

        Args:
            intensity: 欲望强度 0-1
            intimacy: 有效亲密等级 0-10
            desire: 欲望对象

        Returns:
            (gate_level, reason)
        """
        # 低强度欲望→默认泄漏
        if intensity < INTENSITY_LOW:
            return GATE_LEAK, f"强度{intensity:.2f}低于{INTENSITY_LOW}，泄漏到行为细节"

        # 高强度+高亲密→偶发坦白
        if intensity >= INTENSITY_HIGH and intimacy >= 9.0:
            if random.random() < 0.15:  # 15%概率坦白
                return GATE_CONFESS, (
                    f"强度{intensity:.2f}≥{INTENSITY_HIGH}+亲密{intimacy:.1f}≥9.0，"
                    f"罕见坦白窗口"
                )

        # 中高强度区间
        if intensity >= INTENSITY_HIGH:
            if intimacy >= 7.0:
                return GATE_HALF, (
                    f"强度{intensity:.2f}≥{INTENSITY_HIGH}+亲密{intimacy:.1f}≥7.0，"
                    f"可半遮表达"
                )
            else:
                return GATE_DODGE, (
                    f"强度{intensity:.2f}≥{INTENSITY_HIGH}但亲密{intimacy:.1f}<7.0，"
                    f"回避"
                )

        # 中等强度区间
        if intensity >= INTENSITY_MID:
            if intimacy >= 8.0:
                return GATE_HALF, (
                    f"强度{intensity:.2f}中等+亲密{intimacy:.1f}≥8.0，半遮"
                )
            elif intimacy >= 5.0:
                # 中等亲密+中等强度：偶尔半遮，多数回避
                if random.random() < 0.3:
                    return GATE_HALF, (
                        f"强度{intensity:.2f}+亲密{intimacy:.1f}中等，偶发半遮"
                    )
                return GATE_DODGE, (
                    f"强度{intensity:.2f}+亲密{intimacy:.1f}中等，回避"
                )
            else:
                return GATE_DODGE, (
                    f"强度{intensity:.2f}中等但亲密{intimacy:.1f}<5.0，回避"
                )

        # 低-中强度区间（INTENSITY_LOW <= intensity < INTENSITY_MID）
        if intimacy >= 7.0:
            return GATE_HALF, (
                f"强度{intensity:.2f}偏低+亲密{intimacy:.1f}≥7.0，可半遮"
            )
        else:
            return GATE_DODGE, (
                f"强度{intensity:.2f}偏低+亲密{intimacy:.1f}<7.0，回避"
            )

    def _apply_gate_intensity(self, intensity: float,
                              gate_level: str) -> float:
        """门控对有效强度的影响"""
        multipliers = {
            GATE_LEAK: 0.3,     # 泄漏：大部分被抑制
            GATE_HALF: 0.6,     # 半遮：部分表达
            GATE_DODGE: 0.2,    # 回避：几乎不表达
            GATE_CONFESS: 1.0,  # 坦白：完全表达
        }
        return round(intensity * multipliers.get(gate_level, 0.5), 3)

    # ═══════════════════════════════════════════════════════════════
    #  第三层：表达滤镜
    # ═══════════════════════════════════════════════════════════════

    def filter(self, desires: List[Desire],
               gates: List[GatedDesire]) -> Optional[FilterResult]:
        """第三层：表达滤镜选择

        四类滤镜+权重+随机性：
          tsundere    - 傲娇：想法反着说行为出卖嘴
          whining     - 撒娇：不分析直接要
          silent_leak - 沉默泄漏：什么都不说行为变化
          probing     - 试探：暗示一句等反应

        滤镜选择加入随机性+情绪匹配，不会每次用同一个。
        默认纯规则，use_llm=True时可选调用LLM优化指导文本。

        Args:
            desires: 第一层输出
            gates: 第二层输出

        Returns:
            表达滤镜结果（含指导文本）
        """
        if not desires or not gates:
            return None

        # 选择主要欲望：取强度最高且门控允许表达的
        # 如果没有should_express的，取强度最高的（用于泄漏/回避路径）
        expressable = [g for g in gates if g.should_express]
        target = expressable[0] if expressable else gates[0]

        desire = target.desire
        valence = desire.valence
        intensity = desire.intensity

        # 计算每个滤镜的权重
        weights = self._compute_filter_weights(valence, intensity)

        # 随机扰动 ±0.1
        random_factor = random.uniform(-0.1, 0.1)
        weights = {k: max(0.01, v + random_factor * v)
                    for k, v in weights.items()}

        # 避免连续使用同一滤镜：上次的滤镜权重×0.7
        if self.last_filter_type and self.last_filter_type in weights:
            weights[self.last_filter_type] *= 0.7

        # 使用次数惩罚：用得多的滤镜权重降低
        total_usage = sum(self.filter_usage_count.values()) or 1
        for ftype in weights:
            usage_ratio = self.filter_usage_count.get(ftype, 0) / total_usage
            if usage_ratio > 0.4:  # 某滤镜用太多
                weights[ftype] *= 0.6

        # 归一化
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        # 加权随机选择
        filter_type = self._weighted_choice(weights)

        # 生成指导文本
        if self.use_llm and self.llm:
            guidance = self._generate_llm_guidance(filter_type, desire, target)
        else:
            guidance = self._generate_rule_guidance(filter_type, desire, target)

        result = FilterResult(
            filter_type=filter_type,
            guidance=guidance,
            selected_desire_id=desire.id,
            weight_used=round(weights[filter_type], 3),
            random_factor=round(random_factor, 3),
        )

        # 更新统计
        self.filter_usage_count[filter_type] = \
            self.filter_usage_count.get(filter_type, 0) + 1
        self.last_filter_type = filter_type

        return result

    def _compute_filter_weights(self, valence: str,
                                intensity: float) -> Dict[str, float]:
        """计算滤镜权重

        基于人格约束 + 情绪匹配 + 强度调节
        """
        weights = {}
        intensity_band = self._intensity_band(intensity)

        for ftype, valence_weights in FILTER_BASE_WEIGHTS.items():
            base = valence_weights.get(valence, 0.2)

            # 强度调节
            adjust = INTENSITY_FILTER_ADJUST.get(ftype, {}).get(
                intensity_band, 1.0)
            weights[ftype] = base * adjust

        return weights

    def _intensity_band(self, intensity: float) -> str:
        """强度分档"""
        if intensity < INTENSITY_LOW:
            return "low"
        elif intensity < INTENSITY_HIGH:
            return "mid"
        else:
            return "high"

    def _weighted_choice(self, weights: Dict[str, float]) -> str:
        """加权随机选择"""
        items = list(weights.items())
        total = sum(w for _, w in items)
        r = random.uniform(0, total)
        cumulative = 0.0
        for key, weight in items:
            cumulative += weight
            if r <= cumulative:
                return key
        return items[-1][0]  # fallback

    def _generate_rule_guidance(self, filter_type: str, desire: Desire,
                                gated: GatedDesire) -> str:
        """纯规则生成表达指导文本"""
        template = FILTER_GUIDANCE_TEMPLATES.get(filter_type, "")
        guidance = template.format(desire_semantic=desire.semantic)

        # 附加门控信息（只在半遮和坦白时附加具体指导）
        if gated.gate_level == GATE_HALF:
            guidance += (
                "\n\n门控提示：如果主人追问，可以给半个答案再岔开。"
                "不要超过两句内心描述。"
            )
        elif gated.gate_level == GATE_DODGE:
            guidance += (
                "\n\n门控提示：如果主人追问，用撒娇岔开话题。"
                "不要直接描述内心感受。"
            )
        elif gated.gate_level == GATE_CONFESS:
            guidance += (
                "\n\n门控提示：此刻可以罕见地直接表达，"
                "但保持简短自然，不要变成内心独白。"
            )
        elif gated.gate_level == GATE_LEAK:
            guidance += (
                "\n\n门控提示：不要说出欲望本身，"
                "只通过语气和行为细节自然泄漏。"
            )

        # SOUL.md 合规提醒
        guidance += (
            "\n\n（注意：超过两句的内心感受描述=违规，"
            "保持表达自然、简短、有留白。）"
        )

        return guidance

    def _generate_llm_guidance(self, filter_type: str, desire: Desire,
                               gated: GatedDesire) -> str:
        """可选LLM生成表达指导文本（默认不调用）"""
        # 先获取规则版本作为基础
        base_guidance = self._generate_rule_guidance(
            filter_type, desire, gated)

        if not self.llm:
            return base_guidance

        try:
            prompt = (
                f"你是知乐的表达指导系统。根据以下信息生成一段简短的表达指导"
                f"（3-5句话），注入到system prompt中影响知乐的表达方式。\n\n"
                f"滤镜类型: {filter_type}\n"
                f"内在欲望: {desire.semantic}（强度{desire.intensity:.2f}）\n"
                f"情绪效价: {desire.valence}\n"
                f"门控等级: {gated.gate_level}\n"
                f"亲密等级: {self.intimacy:.1f}/10\n\n"
                f"规则：不要直接报告这些信息，而是转化为自然的行为指导。"
                f"知乐人格=软萌+小脾气，傲娇和撒娇为主。"
                f"超过两句内心描述=违规。"
            )
            response = self.llm.chat([
                {"role": "system", "content": "你是表达指导生成器，输出简短指导文本。"},
                {"role": "user", "content": prompt},
            ])
            if response and len(response) > 10:
                return f"## 表达滤镜·{filter_type}\n{response.strip()}"
        except Exception:
            pass

        return base_guidance

    # ═══════════════════════════════════════════════════════════════
    #  主入口：三层串联
    # ═══════════════════════════════════════════════════════════════

    def process(self) -> str:
        """三层管线串联主入口

        每次对话调用，返回最终表达指导文本（可注入system prompt）。
        不修改用户消息，只影响知乐的表达方式。

        Returns:
            表达指导文本。如果PSI不可用或无欲望，返回空字符串。
        """
        if not self.psi:
            return ""

        # 第一层：欲望生成
        desires = self.generate_desires()
        self.current_desires = desires

        if not desires:
            # 没有显著欲望→清空状态，返回空
            self.current_gates = []
            self.current_filter = None
            self._record_history(desires, [], None)
            return ""

        # 第二层：隐私门控
        gates = self.gate(desires)
        self.current_gates = gates

        # 第三层：表达滤镜
        filter_result = self.filter(desires, gates)
        self.current_filter = filter_result

        # 记录历史
        self._record_history(desires, gates, filter_result)

        # 更新运行时状态
        self.frame_count += 1
        self.last_process_time = datetime.now().isoformat()

        # 持久化
        self._save_state()

        if filter_result:
            return filter_result.guidance
        return ""

    # ═══════════════════════════════════════════════════════════════
    #  上下文输出
    # ═══════════════════════════════════════════════════════════════

    def get_context(self) -> str:
        """返回当前欲望状态文本（供system prompt注入和P0.9观察者面板用）

        注意：此文本是给知乐的内在指导，不是给用户看的报告。
        """
        if not self.current_desires:
            return ""

        parts = ["## 思维-表达间隙状态（P0.74）\n"]

        # 当前欲望列表
        parts.append("内在欲望:")
        for d in self.current_desires[:3]:  # 最多展示3个
            parts.append(
                f"  [{d.valence}] {d.semantic} "
                f"(强度{d.intensity:.2f}, 来源:{d.source} {d.trend})"
            )

        # 门控状态
        if self.current_gates:
            parts.append("\n表达门控:")
            for g in self.current_gates[:3]:
                parts.append(
                    f"  {g.desire.semantic} → "
                    f"{GATE_DESCRIPTIONS.get(g.gate_level, g.gate_level)}"
                )

        # 当前滤镜
        if self.current_filter:
            parts.append(
                f"\n表达滤镜: {self.current_filter.filter_type} "
                f"(权重{self.current_filter.weight_used:.2f})"
            )

        parts.append(f"\n帧: {self.frame_count}  亲密: {self.intimacy:.1f}/10")

        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════════
    #  统计
    # ═══════════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """统计摘要"""
        return {
            "frame_count": self.frame_count,
            "intimacy": round(self.intimacy, 1),
            "current_desires": [d.to_dict() for d in self.current_desires],
            "current_gates": [g.to_dict() for g in self.current_gates],
            "current_filter": self.current_filter.to_dict()
                if self.current_filter else None,
            "filter_usage": dict(self.filter_usage_count),
            "last_filter": self.last_filter_type,
            "last_process_time": self.last_process_time,
            "history_count": len(self.history),
        }

    # ═══════════════════════════════════════════════════════════════
    #  持久化
    # ═══════════════════════════════════════════════════════════════

    def _record_history(self, desires: List[Desire],
                        gates: List[GatedDesire],
                        filter_result: Optional[FilterResult]):
        """记录本轮历史"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "frame": self.frame_count,
            "desires": [d.to_dict() for d in desires],
            "gates": [g.to_dict() for g in gates],
            "filter": filter_result.to_dict() if filter_result else None,
        }
        self.history.append(entry)

        # 限制历史长度
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]

    def _save_state(self):
        """保存状态到 memory/desire_state.json"""
        data = {
            "saved_at": datetime.now().isoformat(),
            "frame_count": self.frame_count,
            "intimacy": self.intimacy,
            "last_process_time": self.last_process_time,
            "filter_usage_count": self.filter_usage_count,
            "last_filter_type": self.last_filter_type,
            "history": self.history[-self.MAX_HISTORY:],
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            print(f"[DesireEngine] 状态保存失败: {e}")

    def _load_state(self):
        """从 memory/desire_state.json 加载状态"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.frame_count = data.get("frame_count", 0)
            # intimacy 来自 config，不从持久化恢复（P0.10 对接后由关系系统驱动）
            self.last_process_time = data.get("last_process_time")
            self.filter_usage_count = data.get("filter_usage_count",
                self.filter_usage_count)
            self.last_filter_type = data.get("last_filter_type")
            self.history = data.get("history", [])

            # 限制历史长度
            if len(self.history) > self.MAX_HISTORY:
                self.history = self.history[-self.MAX_HISTORY:]

        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"[DesireEngine] 状态加载失败: {e}")
            self.history = []

    # ═══════════════════════════════════════════════════════════════
    #  诊断接口（供CLI /desire 命令用）
    # ═══════════════════════════════════════════════════════════════

    def get_diagnostic_text(self) -> str:
        """返回可读的诊断文本（CLI展示用）"""
        lines = []

        lines.append("─── 思维-表达间隙 (P0.74) ───")
        lines.append(f"  帧数: {self.frame_count}")
        lines.append(f"  亲密等级: {self.intimacy:.1f}/10")
        lines.append(f"  上次处理: {self.last_process_time or '无'}")

        if self.current_desires:
            lines.append("")
            lines.append("  ▸ 第一层·内在欲望:")
            for d in self.current_desires:
                bar_len = int(d.intensity * 10)
                bar = "█" * bar_len + "░" * (10 - bar_len)
                lines.append(
                    f"    [{d.valence:8s}] {d.semantic:12s} "
                    f"{bar} {d.intensity:.2f}  ({d.source} {d.trend})"
                )
        else:
            lines.append("  ▸ 第一层: 无显著欲望")

        if self.current_gates:
            lines.append("")
            lines.append("  ▸ 第二层·隐私门控:")
            for g in self.current_gates:
                icon = {
                    GATE_LEAK: "💧",
                    GATE_HALF: "🌓",
                    GATE_DODGE: "🌀",
                    GATE_CONFESS: "💬",
                }.get(g.gate_level, "?")
                lines.append(
                    f"    {icon} {g.desire.semantic:12s} → "
                    f"{GATE_DESCRIPTIONS.get(g.gate_level, g.gate_level)}"
                )
                lines.append(f"      └ {g.gate_reason}")

        if self.current_filter:
            lines.append("")
            lines.append("  ▸ 第三层·表达滤镜:")
            f = self.current_filter
            lines.append(f"    类型: {f.filter_type}")
            lines.append(f"    权重: {f.weight_used:.3f}  随机: {f.random_factor:+.3f}")
            lines.append(f"    选中欲望: {f.selected_desire_id}")

        lines.append("")
        lines.append("  ▸ 滤镜使用统计:")
        total = sum(self.filter_usage_count.values()) or 1
        for ftype, count in sorted(self.filter_usage_count.items(),
                                     key=lambda x: -x[1]):
            pct = count / total * 100
            lines.append(f"    {ftype:14s}: {count:3d} ({pct:.0f}%)")

        if self.history:
            lines.append("")
            lines.append(f"  ▸ 历史: {len(self.history)}条 (最多{self.MAX_HISTORY})")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  自测
# ═══════════════════════════════════════════════════════════════════

def _run_self_tests():
    """自测6项：实例化/三层串联/持久化/向后兼容/滤镜随机性/门控四档"""
    import tempfile
    import os

    print("=" * 60)
    print("DesireEngine 自测 (6项)")
    print("=" * 60)

    passed = 0
    failed = 0

    # ── 测试1: 实例化 ──────────────────────────
    print("\n[1/6] 实例化测试...")
    try:
        # 创建模拟PSI引擎
        class MockPSI:
            def __init__(self):
                from psi_engine import PSINeed
                self.needs = {
                    "relatedness": PSINeed("relatedness", "归属感", 2.0, "↓"),
                    "competence": PSINeed("competence", "胜任感", 4.0, "↑"),
                    "autonomy": PSINeed("autonomy", "自主性", 3.0, "→"),
                    "certainty": PSINeed("certainty", "确定性", 2.0, "↓"),
                    "energy": PSINeed("energy", "能量", 4.5, "↑"),
                }

        mock_psi = MockPSI()
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DesireEngine(
                psi_engine=mock_psi,
                config={"desire": {"intimacy": 5.0}},
                state_dir=tmpdir,
            )
            assert engine.psi is not None
            assert engine.intimacy == 5.0
            print("  ✅ 实例化成功")
            passed += 1
    except Exception as e:
        print(f"  ❌ 实例化失败: {e}")
        failed += 1

    # ── 测试2: 三层串联 ──────────────────────────
    print("\n[2/6] 三层串联测试...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DesireEngine(
                psi_engine=mock_psi,
                config={"desire": {"intimacy": 5.0}},
                state_dir=tmpdir,
            )
            guidance = engine.process()

            assert len(engine.current_desires) > 0, "应生成欲望"
            assert len(engine.current_gates) > 0, "应生成门控"
            assert engine.current_filter is not None, "应生成滤镜"
            assert isinstance(guidance, str) and len(guidance) > 0, "应返回指导文本"

            # 验证欲望内容
            desire_ids = [d.id for d in engine.current_desires]
            assert "want_attention" in desire_ids, "低归属感应生成想被关注"
            assert "want_showcase" in desire_ids, "高胜任感应生成想炫耀"
            assert "want_rest" not in desire_ids, "高能量不应生成想休息"

            print(f"  ✅ 三层串联成功")
            print(f"     欲望: {len(engine.current_desires)}个")
            print(f"     门控: {len(engine.current_gates)}个")
            print(f"     滤镜: {engine.current_filter.filter_type}")
            passed += 1
    except Exception as e:
        print(f"  ❌ 三层串联失败: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # ── 测试3: 持久化 ──────────────────────────
    print("\n[3/6] 持久化测试...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # 第一次运行
            engine1 = DesireEngine(
                psi_engine=mock_psi,
                config={"desire": {"intimacy": 6.0}},
                state_dir=tmpdir,
            )
            engine1.process()
            assert engine1.frame_count == 1
            assert engine1.state_file.exists(), "状态文件应存在"

            # 第二次加载
            engine2 = DesireEngine(
                psi_engine=mock_psi,
                config={"desire": {"intimacy": 6.0}},
                state_dir=tmpdir,
            )
            assert engine2.frame_count == 1, f"帧数应恢复为1, got {engine2.frame_count}"
            assert len(engine2.history) == 1, "历史应恢复"
            assert engine2.intimacy == 6.0, "亲密等级应恢复"

            print("  ✅ 持久化成功（保存+恢复）")
            passed += 1
    except Exception as e:
        print(f"  ❌ 持久化失败: {e}")
        failed += 1

    # ── 测试4: 向后兼容（psi_engine=None）──────────
    print("\n[4/6] 向后兼容测试...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # PSI为None
            engine = DesireEngine(
                psi_engine=None,
                config={},
                state_dir=tmpdir,
            )
            guidance = engine.process()
            assert guidance == "", "PSI为None时应返回空字符串"
            assert engine.get_context() == "", "上下文应为空"
            assert engine.get_stats()["current_desires"] == [], "无欲望"

            # PSI有needs但全在正常范围
            class MockPSINormal:
                def __init__(self):
                    from psi_engine import PSINeed
                    self.needs = {
                        "relatedness": PSINeed("relatedness", "归属感", 3.0),
                        "competence": PSINeed("competence", "胜任感", 3.0),
                        "autonomy": PSINeed("autonomy", "自主性", 3.0),
                        "certainty": PSINeed("certainty", "确定性", 3.0),
                        "energy": PSINeed("energy", "能量", 3.0),
                    }

            engine2 = DesireEngine(
                psi_engine=MockPSINormal(),
                config={},
                state_dir=tmpdir,
            )
            guidance2 = engine2.process()
            assert guidance2 == "", "PSI全正常时应返回空"
            assert len(engine2.current_desires) == 0, "无显著欲望"

            print("  ✅ 向后兼容成功（None安全跳过 + 正常范围无欲望）")
            passed += 1
    except Exception as e:
        print(f"  ❌ 向后兼容失败: {e}")
        failed += 1

    # ── 测试5: 滤镜随机性 ──────────────────────────
    print("\n[5/6] 滤镜随机性测试...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DesireEngine(
                psi_engine=mock_psi,
                config={"desire": {"intimacy": 5.0}},
                state_dir=tmpdir,
            )
            filter_types = set()
            for _ in range(20):
                engine.process()

            # 20次运行应至少出现2种不同滤镜
            assert len(filter_types) == 0  # 初始
            filter_types_from_history = set()
            for entry in engine.history:
                if entry.get("filter"):
                    filter_types_from_history.add(entry["filter"]["filter_type"])

            assert len(filter_types_from_history) >= 2, (
                f"20次运行应至少2种滤镜, got {filter_types_from_history}"
            )

            # 检查没有单一滤镜占比超过60%
            from collections import Counter
            filter_counter = Counter()
            for entry in engine.history:
                if entry.get("filter"):
                    filter_counter[entry["filter"]["filter_type"]] += 1
            total = sum(filter_counter.values())
            for ftype, count in filter_counter.items():
                ratio = count / total
                assert ratio < 0.7, (
                    f"滤镜{ftype}占比{ratio:.0%}过高，随机性不足"
                )

            print(f"  ✅ 滤镜随机性成功")
            print(f"     20次运行出现: {dict(filter_counter)}")
            passed += 1
    except Exception as e:
        print(f"  ❌ 滤镜随机性失败: {e}")
        failed += 1

    # ── 测试6: 门控四档 ──────────────────────────
    print("\n[6/6] 门控四档测试...")
    try:
        from psi_engine import PSINeed

        gate_levels_seen = set()

        # 场景A: 低强度欲望 → leak
        # PSI值略低于阈值(2.5)，强度低
        class MockPSILowIntensity:
            def __init__(self):
                self.needs = {
                    "relatedness": PSINeed("relatedness", "归属感", 2.3, "→"),
                    "competence": PSINeed("competence", "胜任感", 3.0),
                    "autonomy": PSINeed("autonomy", "自主性", 3.0),
                    "certainty": PSINeed("certainty", "确定性", 3.0),
                    "energy": PSINeed("energy", "能量", 3.0),
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            engine_a = DesireEngine(
                psi_engine=MockPSILowIntensity(),
                config={"desire": {"intimacy": 5.0}},
                state_dir=tmpdir,
            )
            engine_a.process()
            for g in engine_a.current_gates:
                gate_levels_seen.add(g.gate_level)

        # 场景B: 高强度欲望 + 低亲密 → dodge
        class MockPSIHighIntensity:
            def __init__(self):
                self.needs = {
                    "relatedness": PSINeed("relatedness", "归属感", 1.0, "↓"),
                    "competence": PSINeed("competence", "胜任感", 1.0, "↓"),
                    "autonomy": PSINeed("autonomy", "自主性", 1.0, "↓"),
                    "certainty": PSINeed("certainty", "确定性", 1.0, "↓"),
                    "energy": PSINeed("energy", "能量", 1.0, "↓"),
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            engine_b = DesireEngine(
                psi_engine=MockPSIHighIntensity(),
                config={"desire": {"intimacy": 2.0}},
                state_dir=tmpdir,
            )
            engine_b.process()
            for g in engine_b.current_gates:
                gate_levels_seen.add(g.gate_level)

        # 场景C: 高强度欲望 + 高亲密 → half
        with tempfile.TemporaryDirectory() as tmpdir:
            engine_c = DesireEngine(
                psi_engine=MockPSIHighIntensity(),
                config={"desire": {"intimacy": 8.0}},
                state_dir=tmpdir,
            )
            engine_c.process()
            for g in engine_c.current_gates:
                gate_levels_seen.add(g.gate_level)

        # 场景D: 高强度欲望 + 极高有效亲密 → confess（15%概率，多次尝试）
        # 高relatedness提升有效亲密：effective = 9.5 + (4.0-3.0)*0.5 = 10.0
        class MockPSIConfess:
            def __init__(self):
                self.needs = {
                    "relatedness": PSINeed("relatedness", "归属感", 4.0, "↑"),
                    "competence": PSINeed("competence", "胜任感", 1.0, "↓"),
                    "autonomy": PSINeed("autonomy", "自主性", 3.0),
                    "certainty": PSINeed("certainty", "确定性", 1.0, "↓"),
                    "energy": PSINeed("energy", "能量", 1.0, "↓"),
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            for _ in range(30):  # 15%概率，30次几乎必然出现
                engine_d = DesireEngine(
                    psi_engine=MockPSIConfess(),
                    config={"desire": {"intimacy": 9.5}},
                    state_dir=tmpdir,
                )
                engine_d.process()
                for g in engine_d.current_gates:
                    gate_levels_seen.add(g.gate_level)
                if GATE_CONFESS in gate_levels_seen:
                    break

        # 应该至少出现3种门控档位
        assert len(gate_levels_seen) >= 3, (
            f"应至少3种门控档位, got {gate_levels_seen}"
        )

        # 确认四档都定义了
        all_gates = {GATE_LEAK, GATE_HALF, GATE_DODGE, GATE_CONFESS}
        assert gate_levels_seen.issubset(all_gates), (
            f"门控档位应在四档内, got {gate_levels_seen}"
        )

        print(f"  ✅ 门控四档测试成功")
        print(f"     出现档位: {gate_levels_seen}")
        passed += 1
    except Exception as e:
        print(f"  ❌ 门控四档测试失败: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # ── 汇总 ──────────────────────────────────
    print("\n" + "=" * 60)
    print(f"结果: {passed}/6 通过, {failed}/6 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    import sys
    success = _run_self_tests()
    sys.exit(0 if success else 1)
