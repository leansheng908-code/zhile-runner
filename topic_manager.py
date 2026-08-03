#!/usr/bin/env python3
"""
知乐主动话题系统 — P0.13（N.E.K.O.启发）

主动生成有趣的话题、冷知识、讨论点，让知乐不只是被动回复，
而是能主动找主人聊天。话题基于用户画像+时间感知+PSI状态筛选。

运行方式：
  - generate() 由 daemon_thinker 定期调用（队列不足时自动补充）
  - get_next_topic() 由链式关心/QQ主动消息调用
  - 零token检索：get_status() 查看队列状态
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class Topic:
    """单条话题"""

    def __init__(self, topic_id: str, category: str, title: str,
                 content: str, tags: List[str] = None,
                 created_at: str = None, used: bool = False,
                 used_at: str = None, source: str = "llm"):
        self.id = topic_id
        self.category = category  # anime/game/tech/history/fun/daily/emotion
        self.title = title
        self.content = content
        self.tags = tags or []
        self.created_at = created_at or datetime.now().isoformat()
        self.used = used
        self.used_at = used_at
        self.source = source

    def to_dict(self) -> dict:
        return {
            "id": self.id, "category": self.category,
            "title": self.title, "content": self.content,
            "tags": self.tags, "created_at": self.created_at,
            "used": self.used, "used_at": self.used_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Topic":
        return cls(
            topic_id=d["id"], category=d["category"],
            title=d["title"], content=d["content"],
            tags=d.get("tags", []),
            created_at=d.get("created_at"),
            used=d.get("used", False),
            used_at=d.get("used_at"),
            source=d.get("source", "llm"),
        )


class TopicManager:
    """主动话题管理器"""

    GENERATE_THRESHOLD = 5  # 队列剩余可用话题<5时触发生成
    MAX_QUEUE = 30          # 队列上限
    GENERATE_BATCH = 5      # 每次生成5条

    # 默认用户兴趣（从USER.md提取，可被config覆盖）
    DEFAULT_INTERESTS = {
        "anime": ["Re:Zero", "东方Project", "崩坏三", "星穹铁道", "绝区零"],
        "tech": ["AI", "编程", "科技新闻"],
        "history": ["历史故事", "冷知识"],
        "fun": ["沙雕新闻", "反差感", "二次元梗"],
    }

    # 时间段→话题类型偏好
    TIME_PREFERENCE = {
        "清晨": ["daily", "emotion"],
        "上午": ["tech", "history"],
        "中午": ["fun", "anime"],
        "下午": ["anime", "game"],
        "傍晚": ["daily", "emotion"],
        "晚上": ["anime", "game", "fun"],
        "深夜": ["emotion", "history"],
    }

    def __init__(self, llm_provider, config: dict, user_profile: dict = None):
        self.llm = llm_provider
        self.interests = config.get("interests", self.DEFAULT_INTERESTS)
        self.max_queue = config.get("max_queue", self.MAX_QUEUE)

        mem_dir = Path(config.get("memory_dir", "memory"))
        self.topics_file = mem_dir / "topics.json"
        self.topics_file.parent.mkdir(parents=True, exist_ok=True)

        self.topics: List[Topic] = self._load_topics()

    # ─── 持久化 ───────────────────────────────

    def _load_topics(self) -> List[Topic]:
        if not self.topics_file.exists():
            return []
        try:
            with open(self.topics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Topic.from_dict(t) for t in data]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def _save_topics(self):
        data = [t.to_dict() for t in self.topics]
        with open(self.topics_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── 生成 ─────────────────────────────────

    def should_generate(self) -> bool:
        """检查队列是否需要补充"""
        unused = [t for t in self.topics if not t.used]
        return len(unused) < self.GENERATE_THRESHOLD

    def generate(self, count: int = None, psi_context: str = "") -> dict:
        """用LLM生成新话题"""
        if not self.llm:
            return {"generated": 0, "reason": "无LLM"}

        count = count or self.GENERATE_BATCH

        # 构建兴趣描述
        interest_desc = "\n".join(
            f"- {cat}: {', '.join(items)}"
            for cat, items in self.interests.items()
        )

        # 时间感知
        hour = datetime.now().hour
        if 5 <= hour < 8:
            period = "清晨"
        elif 8 <= hour < 11:
            period = "上午"
        elif 11 <= hour < 14:
            period = "中午"
        elif 14 <= hour < 17:
            period = "下午"
        elif 17 <= hour < 19:
            period = "傍晚"
        elif 19 <= hour < 23:
            period = "晚上"
        else:
            period = "深夜"

        # 已有话题标题（避免重复）
        existing_titles = [t.title for t in self.topics[-20:]]

        prompt = f"""你是一个话题策划师。为一个AI伴侣"知乐"生成{count}个有趣的话题，
让她可以主动找主人聊天。

主人的兴趣爱好：
{interest_desc}

当前时间段：{period}
{'当前内在状态：' + psi_context if psi_context else ''}

话题类型说明：
- anime: 动漫/二次元相关（Re:Zero、东方、崩坏3、星铁、绝区零等）
- game: 游戏相关（剧情、世界观、角色讨论）
- tech: 科技/AI/编程话题
- history: 历史故事、冷知识
- fun: 沙雕新闻、反差感、有趣事实
- daily: 日常生活话题（美食、天气、季节感）
- emotion: 情感话题、关系互动、表达关心

要求：
1. 话题要自然，像朋友之间聊天，不像推送通知
2. 结合主人兴趣但不局限于已知领域
3. 有互动性——能引发讨论而非单向信息
4. 避免与这些已有话题重复：{existing_titles[:10]}

以JSON格式返回：
{{"topics": [{{"category": "...", "title": "...", "content": "一句话描述话题内容，知乐可以怎么开口", "tags": ["..."]}}]}}

只返回JSON。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你是一个话题策划师，只输出JSON。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()

            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            generated = []

            for t in data.get("topics", []):
                # 去重
                if t["title"] in existing_titles:
                    continue

                topic_id = hashlib_id(t["title"], t["category"])
                topic = Topic(
                    topic_id=topic_id,
                    category=t["category"],
                    title=t["title"],
                    content=t["content"],
                    tags=t.get("tags", []),
                )
                self.topics.append(topic)
                generated.append(topic)

            # 修剪：移除已使用超过7天的话题
            self._prune_old()
            self._save_topics()

            return {
                "generated": len(generated),
                "total_unused": len([t for t in self.topics if not t.used]),
                "topics": [{"category": t.category, "title": t.title}
                           for t in generated],
            }
        except (json.JSONDecodeError, KeyError, Exception) as e:
            return {"generated": 0, "error": str(e)}

    def _prune_old(self):
        """修剪已使用的旧话题"""
        now = datetime.now()
        keep = []
        for t in self.topics:
            if not t.used:
                keep.append(t)
            elif t.used_at:
                try:
                    used_dt = datetime.fromisoformat(t.used_at)
                    if (now - used_dt).days < 7:
                        keep.append(t)
                except (ValueError, TypeError):
                    keep.append(t)
            else:
                keep.append(t)

        # 保持队列上限
        if len(keep) > self.max_queue:
            keep.sort(key=lambda t: t.created_at, reverse=True)
            keep = keep[:self.max_queue]

        self.topics = keep

    # ─── 检索 ─────────────────────────────────

    def get_next_topic(self, time_aware: bool = True) -> Optional[Topic]:
        """获取下一条话题（零token，按时间偏好排序）"""
        unused = [t for t in self.topics if not t.used]
        if not unused:
            return None

        if time_aware:
            # 按时间段偏好排序
            hour = datetime.now().hour
            if 5 <= hour < 8:
                period = "清晨"
            elif 8 <= hour < 11:
                period = "上午"
            elif 11 <= hour < 14:
                period = "中午"
            elif 14 <= hour < 17:
                period = "下午"
            elif 17 <= hour < 19:
                period = "傍晚"
            elif 19 <= hour < 23:
                period = "晚上"
            else:
                period = "深夜"

            preferred = self.TIME_PREFERENCE.get(period, [])
            # 优先匹配时间段偏好的类型
            preferred_topics = [t for t in unused if t.category in preferred]
            other_topics = [t for t in unused if t.category not in preferred]

            # 各类型内随机选一条
            random.shuffle(preferred_topics)
            random.shuffle(other_topics)
            sorted_topics = preferred_topics + other_topics
        else:
            sorted_topics = list(unused)
            random.shuffle(sorted_topics)

        topic = sorted_topics[0]
        topic.used = True
        topic.used_at = datetime.now().isoformat()
        self._save_topics()

        return topic

    def peek_topics(self, count: int = 5) -> List[dict]:
        """预览可用话题（不标记为已使用）"""
        unused = [t for t in self.topics if not t.used]
        random.shuffle(unused)
        return [{"category": t.category, "title": t.title,
                 "content": t.content, "tags": t.tags}
                for t in unused[:count]]

    # ─── 状态 ─────────────────────────────────

    def get_status(self) -> dict:
        unused = [t for t in self.topics if not t.used]
        by_category = {}
        for t in unused:
            by_category[t.category] = by_category.get(t.category, 0) + 1

        return {
            "total": len(self.topics),
            "unused": len(unused),
            "used": len(self.topics) - len(unused),
            "by_category": by_category,
            "needs_generate": self.should_generate(),
        }


def hashlib_id(title: str, category: str) -> str:
    import hashlib
    return hashlib.md5(f"{category}:{title}".encode()).hexdigest()[:12]
