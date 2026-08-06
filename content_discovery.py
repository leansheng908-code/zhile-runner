"""
P0.79 — PSI驱动的个性化内容发现引擎
Layer 1: 用户兴趣画像 + Layer 2: PSI→内容类型映射 + Layer 4: 反馈闭环

依赖: psi_engine.py, memory_system.py
"""
import json
import os
import time
from typing import Optional


class InterestProfiler:
    """用户兴趣画像管理器 — 从静态偏好、动态信号、PSI状态三个来源构建动态画像"""

    # 默认兴趣标签（从USER.md已知偏好初始化）
    DEFAULT_TAGS = {
        "二次元": {"weight": 7, "source": "static", "last_active": 0},
        "游戏": {"weight": 6, "source": "static", "last_active": 0},
        "崩坏三": {"weight": 8, "source": "static", "last_active": 0},
        "星穹铁道": {"weight": 6, "source": "static", "last_active": 0},
        "绝区零": {"weight": 5, "source": "static", "last_active": 0},
        "Re:Zero": {"weight": 7, "source": "static", "last_active": 0},
        "东方Project": {"weight": 7, "source": "static", "last_active": 0},
        "科技": {"weight": 6, "source": "static", "last_active": 0},
        "历史": {"weight": 5, "source": "static", "last_active": 0},
        "奇闻异事": {"weight": 5, "source": "static", "last_active": 0},
        "AI": {"weight": 8, "source": "static", "last_active": 0},
        "投资理财": {"weight": 5, "source": "static", "last_active": 0},
        "编程": {"weight": 6, "source": "static", "last_active": 0},
    }

    # 兴趣关键词识别表（聊天中出现这些词时提取为兴趣信号）
    KEYWORD_MAP = {
        "原神": "原神",
        "崩坏": "崩坏三",
        "星铁": "星穹铁道",
        "星穹": "星穹铁道",
        "绝区零": "绝区零",
        "re0": "Re:Zero",
        "re:zero": "Re:Zero",
        "从零开始": "Re:Zero",
        "东方": "东方Project",
        "车万": "东方Project",
        "灵梦": "东方Project",
        "科技": "科技",
        "AI": "AI",
        "人工智能": "AI",
        "大模型": "AI",
        "deepseek": "AI",
        "股票": "投资理财",
        "炒股": "投资理财",
        "基金": "投资理财",
        "哈药": "投资理财",
        "代码": "编程",
        "python": "编程",
        "编程": "编程",
        "历史": "历史",
        "战争": "历史",
        "宇宙": "科技",
        "太空": "科技",
        "猫": "二次元",
        "番剧": "二次元",
        "动漫": "二次元",
        "cos": "二次元",
        "B站": "二次元",
        "b站": "二次元",
    }

    WEIGHT_MIN = 0
    WEIGHT_MAX = 10
    DECAY_INTERVAL = 86400 * 7  # 7天衰减1点
    DECAY_AMOUNT = 1

    def __init__(self, profile_path: str = "user_interest_profile.json"):
        self.profile_path = profile_path
        self.tags = {}
        self.feedback_history = []
        self._load()

    def _load(self):
        """从文件加载画像"""
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.tags = data.get("tags", {})
                self.feedback_history = data.get("feedback_history", [])
                # 合并默认标签（不覆盖已有动态标签）
                for tag, info in self.DEFAULT_TAGS.items():
                    if tag not in self.tags:
                        self.tags[tag] = dict(info)
            except (json.JSONDecodeError, IOError):
                self.tags = dict(self.DEFAULT_TAGS)
                for t in self.tags.values():
                    t["last_active"] = time.time()
        else:
            self.tags = dict(self.DEFAULT_TAGS)
            for t in self.tags.values():
                t["last_active"] = time.time()

    def _save(self):
        """保存画像到文件"""
        data = {
            "tags": self.tags,
            "feedback_history": self.feedback_history[-50:],  # 只保留最近50条反馈
            "updated_at": time.time(),
        }
        try:
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def extract_signals(self, text: str) -> list:
        """从文本中提取兴趣信号"""
        if not text:
            return []
        text_lower = text.lower()
        signals = []
        for keyword, tag in self.KEYWORD_MAP.items():
            if keyword.lower() in text_lower:
                signals.append(tag)
        return list(set(signals))

    def update_from_chat(self, text: str):
        """从聊天文本中更新兴趣画像"""
        signals = self.extract_signals(text)
        if not signals:
            return
        now = time.time()
        for tag in signals:
            if tag in self.tags:
                self.tags[tag]["weight"] = min(
                    self.tags[tag]["weight"] + 0.5, self.WEIGHT_MAX
                )
                self.tags[tag]["last_active"] = now
                self.tags[tag]["source"] = "dynamic"
            else:
                # 新发现的兴趣标签
                self.tags[tag] = {
                    "weight": 3.0,
                    "source": "dynamic",
                    "last_active": now,
                }
        self._save()

    def update_from_feedback(self, tag: str, feedback: str):
        """从用户对推送内容的反馈更新权重

        Args:
            tag: 兴趣标签
            feedback: "positive"/"negative"/"neutral"
        """
        if tag not in self.tags:
            self.tags[tag] = {
                "weight": 3.0,
                "source": "feedback",
                "last_active": time.time(),
            }

        if feedback == "positive":
            self.tags[tag]["weight"] = min(
                self.tags[tag]["weight"] + 1, self.WEIGHT_MAX
            )
        elif feedback == "negative":
            self.tags[tag]["weight"] = max(
                self.tags[tag]["weight"] - 1, self.WEIGHT_MIN
            )
        # neutral: 不变

        self.tags[tag]["last_active"] = time.time()
        self.feedback_history.append(
            {"tag": tag, "feedback": feedback, "time": time.time()}
        )
        self._save()

    def apply_decay(self):
        """应用时间衰减——超过7天未活跃的标签权重-1"""
        now = time.time()
        changed = False
        for tag, info in self.tags.items():
            if info["weight"] <= 0:
                continue
            elapsed = now - info.get("last_active", now)
            decay_steps = int(elapsed / self.DECAY_INTERVAL)
            if decay_steps > 0:
                new_weight = max(info["weight"] - decay_steps * self.DECAY_AMOUNT, self.WEIGHT_MIN)
                if new_weight != info["weight"]:
                    info["weight"] = new_weight
                    changed = True
        if changed:
            self._save()

    def get_top_interests(self, n: int = 5) -> list:
        """获取权重最高的N个兴趣标签"""
        sorted_tags = sorted(
            self.tags.items(), key=lambda x: x[1]["weight"], reverse=True
        )
        return [(tag, info["weight"]) for tag, info in sorted_tags[:n] if info["weight"] > 0]

    def get_search_keywords(self, n: int = 3) -> list:
        """生成搜索关键词——基于权重最高的兴趣标签"""
        top = self.get_top_interests(n)
        return [tag for tag, weight in top]

    def get_profile_summary(self) -> str:
        """生成画像摘要文本（用于感知注释注入）"""
        top = self.get_top_interests(5)
        if not top:
            return ""
        parts = [f"{tag}({w:.1f})" for tag, w in top]
        return "用户兴趣画像: " + ", ".join(parts)

    def get_stats(self) -> dict:
        """获取画像统计信息"""
        total = len(self.tags)
        active = sum(1 for t in self.tags.values() if t["weight"] > 0)
        dynamic = sum(1 for t in self.tags.values() if t["source"] == "dynamic")
        return {
            "total_tags": total,
            "active_tags": active,
            "dynamic_tags": dynamic,
            "feedback_count": len(self.feedback_history),
            "top_interests": self.get_top_interests(5),
        }


class PSIContentMapper:
    """Layer 2: PSI五维状态→内容类型映射表 + 感知注释生成"""

    # PSI状态→内容类型映射
    PSI_CONTENT_MAP = {
        "belonging_low": {
            "label": "归属感赤字",
            "content_types": ["治愈", "陪伴", "温暖", "萌宠", "日常", "温馨故事"],
            "search_hints": ["治愈系", "萌宠", "温馨", "日常", "暖心"],
            "annotation": "用户此刻归属感偏低，可能需要温暖陪伴类内容",
        },
        "energy_low": {
            "label": "能量低",
            "content_types": ["轻松", "搞笑", "短内容", "沙雕", "段子"],
            "search_hints": ["搞笑", "沙雕图", "段子", "轻松", "快乐"],
            "annotation": "用户此刻能量偏低，适合轻松搞笑类内容提神",
        },
        "certainty_low": {
            "label": "确定性低",
            "content_types": ["科普", "解释", "深度分析", "知识"],
            "search_hints": ["科普", "知识", "解析", "原理", "揭秘"],
            "annotation": "用户此刻确定性偏低，适合帮助建立认知的内容",
        },
        "competence_low": {
            "label": "胜任感赤字",
            "content_types": ["励志", "成长", "技能展示", "成就"],
            "search_hints": ["励志", "成长", "逆袭", "成功", "技能"],
            "annotation": "用户此刻胜任感偏低，适合激发成就感的内容",
        },
        "autonomy_high": {
            "label": "自主性高",
            "content_types": ["反直觉", "反差", "新奇", "探索", "冷知识"],
            "search_hints": ["冷知识", "反直觉", "新奇", "不可思议", "反差"],
            "annotation": "用户此刻探索欲旺盛，适合新奇反差类内容",
        },
    }

    # PSI维度阈值
    THRESHOLDS = {
        "belonging": 2.0,  # 低于此值=赤字
        "energy": 2.0,
        "certainty": 2.0,
        "competence": 2.0,
        "autonomy_high": 3.5,  # 高于此值=探索欲旺盛
    }

    def __init__(self):
        pass

    def analyze_psi(self, psi_state: dict) -> list:
        """分析PSI状态，返回命中的内容类型映射

        Args:
            psi_state: {"belonging": x, "energy": y, "certainty": z, "competence": w, "autonomy": v}

        Returns:
            命中的映射key列表，如 ["belonging_low", "energy_low"]
        """
        hits = []
        if not psi_state:
            return hits

        belonging = psi_state.get("belonging", 3.0)
        energy = psi_state.get("energy", 3.0)
        certainty = psi_state.get("certainty", 3.0)
        competence = psi_state.get("competence", 3.0)
        autonomy = psi_state.get("autonomy", 3.0)

        if belonging < self.THRESHOLDS["belonging"]:
            hits.append("belonging_low")
        if energy < self.THRESHOLDS["energy"]:
            hits.append("energy_low")
        if certainty < self.THRESHOLDS["certainty"]:
            hits.append("certainty_low")
        if competence < self.THRESHOLDS["competence"]:
            hits.append("competence_low")
        if autonomy > self.THRESHOLDS["autonomy_high"]:
            hits.append("autonomy_high")

        return hits

    def get_content_direction(self, psi_state: dict) -> dict:
        """根据PSI状态获取内容推荐方向

        Returns:
            {"hits": [...], "search_hints": [...], "annotation": "..."}
        """
        hits = self.analyze_psi(psi_state)
        if not hits:
            return {
                "hits": [],
                "search_hints": [],
                "annotation": "",
                "content_types": [],
            }

        # 合并所有命中状态的搜索提示和注释
        all_hints = []
        all_annotations = []
        all_types = []
        for hit in hits:
            mapping = self.PSI_CONTENT_MAP[hit]
            all_hints.extend(mapping["search_hints"])
            all_annotations.append(mapping["annotation"])
            all_types.extend(mapping["content_types"])

        return {
            "hits": hits,
            "search_hints": list(set(all_hints)),
            "annotation": "；".join(all_annotations),
            "content_types": list(set(all_types)),
        }

    def generate_combined_keywords(
        self, interests: list, psi_state: dict, max_keywords: int = 3
    ) -> list:
        """联合兴趣画像和PSI状态生成搜索关键词

        Args:
            interests: 兴趣标签列表，如 ["二次元", "AI"]
            psi_state: PSI状态字典
            max_keywords: 最多返回关键词数

        Returns:
            搜索关键词列表
        """
        direction = self.get_content_direction(psi_state)
        psi_hints = direction["search_hints"]

        # 策略：兴趣×PSI提示 交叉组合，优先选有交集的组合
        keywords = []

        # 1. 先尝试兴趣+PSI提示组合
        if interests and psi_hints:
            keywords.append(f"{interests[0]} {psi_hints[0]}")

        # 2. 补充纯兴趣关键词
        for tag in interests:
            if len(keywords) >= max_keywords:
                break
            keywords.append(tag)

        # 3. 补充PSI提示关键词
        for hint in psi_hints:
            if len(keywords) >= max_keywords:
                break
            keywords.append(hint)

        return keywords[:max_keywords]

    def get_annotation(self, psi_state: dict) -> str:
        """生成PSI内容推荐感知注释（注入到上下文）"""
        direction = self.get_content_direction(psi_state)
        if not direction["annotation"]:
            return ""
        return f"[内容推荐感知] {direction['annotation']}。推荐类型: {', '.join(direction['content_types'][:3])}"


class ContentDiscoveryEngine:
    """P0.79 总引擎 — 联合兴趣画像+PSI映射，驱动内容发现"""

    def __init__(self, profiler: InterestProfiler, mapper: PSIContentMapper):
        self.profiler = profiler
        self.mapper = mapper

    def discover(self, psi_state: dict, max_keywords: int = 3) -> dict:
        """执行内容发现流程

        Returns:
            {
                "keywords": [...],          # 搜索关键词
                "annotation": "...",         # 感知注释
                "profile_summary": "...",   # 画像摘要
                "top_interests": [...],     # Top兴趣
                "psi_hits": [...],          # PSI命中的状态
            }
        """
        # 1. 应用衰减
        self.profiler.apply_decay()

        # 2. 获取Top兴趣
        top_interests = self.profiler.get_top_interests(5)
        interest_tags = [tag for tag, _ in top_interests]

        # 3. 联合生成关键词
        keywords = self.mapper.generate_combined_keywords(
            interest_tags, psi_state, max_keywords
        )

        # 4. 生成感知注释
        annotation = self.mapper.get_annotation(psi_state)
        profile_summary = self.profiler.get_profile_summary()

        # 5. PSI命中
        psi_hits = self.mapper.analyze_psi(psi_state)

        return {
            "keywords": keywords,
            "annotation": annotation,
            "profile_summary": profile_summary,
            "top_interests": top_interests,
            "psi_hits": psi_hits,
        }

    def process_feedback(self, tag: str, feedback: str):
        """处理用户对推送内容的反馈"""
        self.profiler.update_from_feedback(tag, feedback)

    def process_chat(self, text: str):
        """从聊天中提取兴趣信号"""
        self.profiler.update_from_chat(text)
