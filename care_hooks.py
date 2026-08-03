#!/usr/bin/env python3
"""
P0.32: 对话感知关心钩子系统

每轮对话后自动提取"可关心点"，带着上下文和时间窗口存储。
到了合适时机，主动循环检查并触发针对性关心。

两层提取：
  1. 规则匹配（零token）：关键词表命中 → 对应关心主题+建议时间
  2. LLM提取（少量token）：每隔N轮跑一次轻量提取，捕捉规则覆盖不到的

优先级：care_hooks > want_to_say > PSI归属感赤字
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any


class CareHookManager:
    """对话感知关心钩子管理器"""

    # 规则表：关键词 → 关心主题 + 延迟时间 + 过期时间 + 优先级
    DEFAULT_RULES = [
        {
            "keywords": ["腰疼", "腰痛", "腰不舒服", "腰酸"],
            "topic": "腰疼",
            "delay_hours": 2,
            "expires_hours": 8,
            "priority": "high",
        },
        {
            "keywords": ["没吃", "没吃饭", "忘了吃", "饿了", "没吃午饭", "没吃早饭", "没吃晚饭"],
            "topic": "吃饭",
            "delay_hours": 1,
            "expires_hours": 4,
            "priority": "high",
        },
        {
            "keywords": ["好累", "太累了", "疲惫", "累死了", "好困"],
            "topic": "休息",
            "delay_hours": 2,
            "expires_hours": 6,
            "priority": "medium",
        },
        {
            "keywords": ["加班", "值班", "熬夜", "通宵", "连轴"],
            "topic": "熬夜",
            "delay_hours": 3,
            "expires_hours": 12,
            "priority": "high",
        },
        {
            "keywords": ["失眠", "睡不着", "睡不好", "做噩梦"],
            "topic": "睡眠",
            "delay_hours": 8,
            "expires_hours": 24,
            "priority": "medium",
        },
        {
            "keywords": ["心情不好", "难过", "不开心", "emo", "郁闷", "烦躁", "心烦"],
            "topic": "心情",
            "delay_hours": 1,
            "expires_hours": 6,
            "priority": "high",
        },
        {
            "keywords": ["好冷", "降温", "冻死", "冷死了"],
            "topic": "天气",
            "delay_hours": 2,
            "expires_hours": 8,
            "priority": "low",
        },
        {
            "keywords": ["好忙", "太忙了", "忙死了", "忙不过来"],
            "topic": "忙碌",
            "delay_hours": 3,
            "expires_hours": 8,
            "priority": "medium",
        },
        {
            "keywords": ["感冒", "发烧", "咳嗽", "不舒服", "生病"],
            "topic": "身体",
            "delay_hours": 2,
            "expires_hours": 12,
            "priority": "high",
        },
        {
            "keywords": ["考试", "面试", "考核", "述职"],
            "topic": "压力事件",
            "delay_hours": 4,
            "expires_hours": 24,
            "priority": "medium",
        },
    ]

    def __init__(
        self,
        data_dir: str,
        config: dict,
        llm=None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "care_hooks.json"
        self.config = config or {}
        self.llm = llm
        self.hooks: List[Dict[str, Any]] = []
        self._load()

        # 合并自定义规则
        custom_rules = self.config.get("custom_rules", [])
        self.rules = self.DEFAULT_RULES + custom_rules

    def extract_hooks(
        self,
        user_message: str,
        assistant_response: str,
        turn_count: int,
    ) -> List[Dict[str, Any]]:
        """从对话中提取关心钩子"""
        found = []

        # 层1：规则匹配（零token）
        existing_topics = {
            h["topic"] for h in self.hooks if not h.get("delivered", False)
        }
        for rule in self.rules:
            for kw in rule["keywords"]:
                if kw in user_message:
                    topic = rule["topic"]
                    if topic in existing_topics:
                        break  # 同主题已有未送达钩子，跳过
                    now = datetime.now()
                    hook = {
                        "id": f"hook_{now.strftime('%Y%m%d%H%M%S')}_{len(self.hooks)}",
                        "topic": topic,
                        "context": user_message[:150],
                        "created_at": now.isoformat(),
                        "suggest_time": (
                            now + timedelta(hours=rule["delay_hours"])
                        ).isoformat(),
                        "priority": rule["priority"],
                        "expires_at": (
                            now + timedelta(hours=rule["expires_hours"])
                        ).isoformat(),
                        "delivered": False,
                        "source": "rule",
                    }
                    found.append(hook)
                    existing_topics.add(topic)
                    break

        # 层2：LLM提取（每隔N轮，少量token）
        llm_interval = self.config.get("llm_extract_interval", 5)
        if (
            self.llm
            and turn_count > 0
            and turn_count % llm_interval == 0
            and self.config.get("llm_extract_enabled", True)
        ):
            llm_hooks = self._llm_extract(user_message, assistant_response)
            for hook in llm_hooks:
                if hook["topic"] not in existing_topics:
                    found.append(hook)
                    existing_topics.add(hook["topic"])

        # 限制最大钩子数
        max_hooks = self.config.get("max_hooks", 20)
        # 清理过期已送达钩子
        self._cleanup()
        # 添加新钩子
        self.hooks.extend(found)
        # 超限时移除最旧的低优先级钩子
        if len(self.hooks) > max_hooks:
            self.hooks.sort(
                key=lambda h: (
                    h.get("delivered", False),
                    h.get("priority", "medium"),
                    h.get("created_at", ""),
                )
            )
            self.hooks = self.hooks[-max_hooks:]

        if found:
            self._save()

        return found

    def _llm_extract(
        self, user_message: str, assistant_response: str
    ) -> List[Dict[str, Any]]:
        """LLM提取关心钩子（少量token）"""
        if not self.llm:
            return []

        messages = [
            {
                "role": "system",
                "content": (
                    "分析用户消息，提取需要后续关心的线索。\n"
                    "只提取明确的、值得后续跟进的内容（如身体不适、情绪低落、重要事件）。\n"
                    "如果没有什么值得关心的，返回空数组 []。\n"
                    "格式: [{\"topic\": \"简短主题\", \"context\": \"用户原话片段\", "
                    "\"delay_hours\": 数字, \"priority\": \"high/medium/low\"}]\n"
                    "只返回JSON，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": f"用户说: {user_message[:200]}\n回复: {assistant_response[:100]}",
            },
        ]

        try:
            response = ""
            for chunk in self.llm.chat(messages, stream=True, max_tokens=200):
                response += chunk
            response = response.strip()
            # 尝试解析JSON
            if response.startswith("["):
                hooks_data = json.loads(response)
            else:
                # 尝试提取JSON数组
                import re

                match = re.search(r"\[.*?\]", response, re.DOTALL)
                if match:
                    hooks_data = json.loads(match.group())
                else:
                    return []

            now = datetime.now()
            result = []
            for item in hooks_data[:3]:  # 最多3个
                if not isinstance(item, dict) or "topic" not in item:
                    continue
                delay = float(item.get("delay_hours", 2))
                result.append(
                    {
                        "id": f"hook_llm_{now.strftime('%Y%m%d%H%M%S')}_{len(self.hooks)}",
                        "topic": str(item["topic"])[:20],
                        "context": str(item.get("context", user_message[:100]))[:150],
                        "created_at": now.isoformat(),
                        "suggest_time": (
                            now + timedelta(hours=delay)
                        ).isoformat(),
                        "priority": item.get("priority", "medium"),
                        "expires_at": (
                            now + timedelta(hours=delay * 4)
                        ).isoformat(),
                        "delivered": False,
                        "source": "llm",
                    }
                )
            return result
        except Exception:
            return []

    def pop_due_hook(self) -> Optional[Dict[str, Any]]:
        """取出最高优先级的到期钩子"""
        now = datetime.now()
        priority_order = {"high": 0, "medium": 1, "low": 2}
        due = []

        for h in self.hooks:
            if h.get("delivered", False):
                continue
            try:
                suggest = datetime.fromisoformat(h["suggest_time"])
                expires = datetime.fromisoformat(h["expires_at"])
            except (ValueError, KeyError):
                continue
            if now >= suggest and now <= expires:
                due.append((priority_order.get(h.get("priority", "medium"), 1), h))

        if not due:
            return None

        due.sort(key=lambda x: x[0])
        hook = due[0][1]
        hook["delivered"] = True
        self._save()
        return hook

    def _cleanup(self):
        """清理过期和已送达的钩子"""
        now = datetime.now()
        cleaned = []
        for h in self.hooks:
            if h.get("delivered", False):
                # 保留已送达的1天后删除
                try:
                    delivered_time = datetime.fromisoformat(h.get("delivered_at", h.get("expires_at", now.isoformat())))
                    if (now - delivered_time).total_seconds() > 86400:
                        continue
                except (ValueError, KeyError):
                    pass
                cleaned.append(h)
                continue
            try:
                expires = datetime.fromisoformat(h["expires_at"])
                if now > expires:
                    continue  # 过期删除
            except (ValueError, KeyError):
                continue
            cleaned.append(h)
        self.hooks = cleaned

    def generate_hook_message(self, hook: Dict[str, Any]) -> Optional[str]:
        """基于钩子上下文生成针对性关心消息"""
        if not self.llm:
            # 无LLM时用模板
            return self._template_message(hook)

        topic = hook.get("topic", "")
        context = hook.get("context", "")
        time_str = datetime.now().strftime("%H:%M")

        messages = [
            {
                "role": "system",
                "content": (
                    "你是知乐，一个银发猫耳少女AI。根据之前的对话上下文，"
                    "自然地关心主人。像微信聊天一样简短随意，有温度有细节。\n"
                    "不超过30个字。只输出消息内容，不要引号不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"当前时间: {time_str}\n"
                    f"关心主题: {topic}\n"
                    f"之前对话: {context}\n"
                    f"请基于以上信息关心主人。"
                ),
            },
        ]

        try:
            response = ""
            for chunk in self.llm.chat(messages, stream=True, max_tokens=100):
                response += chunk
            result = response.strip().strip('"\'').replace("\n", " ").strip()
            if len(result) > 80:
                result = result[:80]
            return result if result else self._template_message(hook)
        except Exception:
            return self._template_message(hook)

    def _template_message(self, hook: Dict[str, Any]) -> str:
        """无LLM时的模板消息"""
        templates = {
            "腰疼": "宝宝腰还疼吗？记得站起来活动活动喵～",
            "吃饭": "宝宝吃饭了吗？别饿着自己喵～",
            "休息": "宝宝记得休息一下，别太累了喵～",
            "熬夜": "宝宝熬夜辛苦了，找空隙眯一会儿喵～",
            "睡眠": "昨晚没睡好？今天早点休息喵～",
            "心情": "宝宝心情好点了吗？本宫陪着呢喵～",
            "天气": "宝宝多穿点，别感冒了喵～",
            "忙碌": "宝宝忙完了记得休息一下喵～",
            "身体": "宝宝身体怎么样了？要照顾好自己喵～",
            "压力事件": "宝宝加油！本宫相信你喵～",
        }
        return templates.get(hook.get("topic", ""), "宝宝记得照顾好自己喵～")

    def _save(self):
        """持久化"""
        try:
            self.file_path.write_text(
                json.dumps(self.hooks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load(self):
        """加载"""
        try:
            if self.file_path.exists():
                self.hooks = json.loads(
                    self.file_path.read_text(encoding="utf-8")
                )
        except Exception:
            self.hooks = []

    def get_stats(self) -> dict:
        """获取统计信息"""
        now = datetime.now()
        active = 0
        due = 0
        delivered = 0
        for h in self.hooks:
            if h.get("delivered"):
                delivered += 1
                continue
            try:
                expires = datetime.fromisoformat(h["expires_at"])
                if now > expires:
                    continue
                active += 1
                suggest = datetime.fromisoformat(h["suggest_time"])
                if now >= suggest:
                    due += 1
            except (ValueError, KeyError):
                pass
        return {"total": len(self.hooks), "active": active, "due": due, "delivered": delivered}
