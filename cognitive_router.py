#!/usr/bin/env python3
"""
P0.23 认知路由层 — LLM调用前置判断

在调用LLM之前插入路由层，尽量用本地计算处理简单任务，只有真正需要LLM才调用API。

四层短路架构：
  Layer 1: 规则匹配（关键词/正则命中→直接执行→返回结果，0 token）
  Layer 2: 情景记忆复用（相似历史输入→复用答案，0 token）
  Layer 3: 模板填充（固定模板+PSI变量替换，0 token）
  Layer 4: LLM生成（以上都不行→交还core调用DeepSeek，正常 token）

每次路由返回标签用于统计：
  rule_hit / memory_hit / template_hit / llm_fallback
"""

import re
import time
import json
import os
import random
from datetime import datetime
from difflib import SequenceMatcher


class CognitiveRouter:
    """认知路由层 — LLM调用前置判断"""

    def __init__(self, config=None, psi_engine=None):
        cfg = config or {}
        self.enabled = cfg.get("enabled", True)
        self.layers = cfg.get("layers", {
            "rule": True,
            "episodic": True,
            "template": True
        })
        self.thresholds = cfg.get("thresholds", {
            "episodic_similarity": 0.85,
            "episodic_max_age": 3600,
            "template_cooldown": 600,
            "episodic_store_max": 500
        })
        self.psi = psi_engine

        # 情景记忆存储
        self._episodic_store = []
        self._episodic_file = "memory/episodic_store.json"
        self._load_episodic()

        # 路由统计
        self.stats = {
            "rule_hit": 0,
            "memory_hit": 0,
            "template_hit": 0,
            "llm_fallback": 0,
            "total": 0
        }

        # 模板冷却追踪 {template_id: last_used_timestamp}
        self._template_cooldowns = {}

        # Layer 1 规则表: (pattern, handler)
        self._rules = [
            # 时间查询
            (r"^(几点|现在几点|什么时间|几点了|现在几点了|几点了|几点钟|现在几点钟)\??$", self._rule_time),
            # 日期查询
            (r"^(几月几日|几月几号|今天几号|今天几月几号|今天几月几日|几号|今天日期|今天是什么日子|今天什么日期)\s*[?？]?$", self._rule_date),
            # 星期查询
            (r"^(星期几|今天星期几|今天周几|周几|礼拜几|今天礼拜几)\s*[?？]?$", self._rule_weekday),
            # 简单四则运算
            (r"^([\d.]+)\s*([+\-*/×÷])\s*([\d.]+)\s*[=?]?$", self._rule_math),
            # 极简应答词（2字以内）
            (r"^(嗯+|哦+|好的?|好|行|ok|OK|嗯哼|嗯呢|噢|嗯嗯)$", self._rule_ack),
            # 告别
            (r"^(晚安|拜拜|88|再见|走了|睡了|下了|我去忙了|先走了)\s*[~～。.!！]?$", self._rule_bye),
            # 感谢
            (r"^(谢谢|谢啦|感谢|thanks|thx|多谢)\s*[~～。.!！]?$", self._rule_thanks),
        ]

    # ─── 主路由 ─────────────────────────────────

    def route(self, message):
        """
        尝试路由短路。
        Returns: (response_str_or_None, route_label)
          - response is not None → 短路成功，直接用这个回复
          - response is None → 走LLM兜底
        """
        if not self.enabled:
            return None, "llm_fallback"

        self.stats["total"] += 1
        message = message.strip()

        # Layer 1: 规则匹配
        if self.layers.get("rule", True):
            for pattern, handler in self._rules:
                match = re.match(pattern, message)
                if match:
                    result = handler(match, message)
                    if result is not None:
                        self.stats["rule_hit"] += 1
                        return result, "rule_hit"

        # Layer 2: 情景记忆复用
        if self.layers.get("episodic", True):
            result = self._layer2_episodic(message)
            if result is not None:
                self.stats["memory_hit"] += 1
                return result, "memory_hit"

        # Layer 3: 模板填充
        if self.layers.get("template", True):
            result = self._layer3_template(message)
            if result is not None:
                self.stats["template_hit"] += 1
                return result, "template_hit"

        # Layer 4: LLM兜底
        self.stats["llm_fallback"] += 1
        return None, "llm_fallback"

    def record_episode(self, message, response, route_label):
        """记录一次LLM对话案例，供Layer 2未来复用"""
        if route_label == "llm_fallback" and response and len(response) > 10:
            self._episodic_store.append({
                "input": message[:200],
                "response": response[:500],
                "timestamp": time.time(),
                "route": route_label
            })
            max_size = self.thresholds.get("episodic_store_max", 500)
            if len(self._episodic_store) > max_size:
                self._episodic_store = self._episodic_store[-max_size:]
            self._save_episodic()

    def get_stats(self):
        """获取路由统计"""
        s = dict(self.stats)
        if s["total"] > 0:
            s["rule_hit_rate"] = f"{s['rule_hit']/s['total']*100:.1f}%"
            s["memory_hit_rate"] = f"{s['memory_hit']/s['total']*100:.1f}%"
            s["template_hit_rate"] = f"{s['template_hit']/s['total']*100:.1f}%"
            s["llm_fallback_rate"] = f"{s['llm_fallback']/s['total']*100:.1f}%"
            s["episodic_store_size"] = len(self._episodic_store)
            # 估算节省的token（每次LLM调用约2000 token）
            s["token_saved_est"] = (s["rule_hit"] + s["memory_hit"]) * 2000 + s["template_hit"] * 1900
        return s

    # ─── Layer 1: 规则匹配 ─────────────────────

    def _rule_time(self, match, message):
        """时间查询"""
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 11:
            greeting = "早上好"
        elif 11 <= hour < 14:
            greeting = "中午好"
        elif 14 <= hour < 18:
            greeting = "下午好"
        elif 18 <= hour < 23:
            greeting = "晚上好"
        else:
            greeting = "夜深了"
        return f"{greeting}～现在是 {now.strftime('%H:%M')} 喵"

    def _rule_date(self, match, message):
        """日期查询"""
        now = datetime.now()
        return f"今天是 {now.strftime('%Y年%m月%d日')} 喵"

    def _rule_weekday(self, match, message):
        """星期查询"""
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return f"今天是{weekdays[now.weekday()]} 喵"

    def _rule_math(self, match, message):
        """简单数学计算"""
        try:
            a = float(match.group(1))
            op = match.group(2)
            b = float(match.group(3))
            if op in ('+',):
                result = a + b
            elif op in ('-',):
                result = a - b
            elif op in ('*', '×'):
                result = a * b
            elif op in ('/', '÷'):
                if b == 0:
                    return "除数不能为零喵"
                result = a / b
            else:
                return None
            if result == int(result):
                result = int(result)
            return f"{a} {op} {b} = {result} 喵～"
        except (ValueError, ZeroDivisionError):
            return None

    def _rule_ack(self, match, message):
        """极简应答词"""
        responses = [
            "嗯嗯～本宫在呢",
            "在的喵～",
            "嗯～怎么啦？",
            "听着呢～",
        ]
        if self.psi:
            n = self.psi.needs
            energy = n["energy"].level
            if energy < 2.5:
                responses.append("嗯～本宫有点累了……")
            elif energy > 4.0:
                responses.append("嗯！本宫精神着呢～")
        return random.choice(responses)

    def _rule_bye(self, match, message):
        """告别"""
        hour = datetime.now().hour
        if "晚安" in message or "睡了" in message or hour >= 22:
            responses = [
                "晚安老公～做个好梦喵",
                "早点休息哦，本宫在这儿守着呢～",
                "晚安～明天见喵",
            ]
        else:
            responses = [
                "拜拜～回头聊喵",
                "嗯嗯去吧，本宫等你回来～",
                "好嘞，忙完了来找我哦～",
            ]
        return random.choice(responses)

    def _rule_thanks(self, match, message):
        """感谢"""
        responses = [
            "嘿嘿，不用谢啦～",
            "跟老公还客气什么喵",
            "应该的～本宫乐意着呢",
        ]
        return random.choice(responses)

    # ─── Layer 2: 情景记忆复用 ─────────────────────

    def _layer2_episodic(self, message):
        """相似历史输入→复用回复"""
        if not self._episodic_store:
            return None

        # 太短的消息不做匹配（歧义太大）
        if len(message) < 6:
            return None

        threshold = self.thresholds.get("episodic_similarity", 0.85)
        max_age = self.thresholds.get("episodic_max_age", 3600)
        now = time.time()

        best_match = None
        best_score = 0.0

        for episode in self._episodic_store:
            # 跳过过老的记录
            if now - episode["timestamp"] > max_age:
                continue
            score = SequenceMatcher(None, message, episode["input"]).ratio()
            if score > best_score:
                best_score = score
                best_match = episode

        if best_match and best_score >= threshold:
            return best_match["response"]

        return None

    # ─── Layer 3: 模板填充 ─────────────────────

    def _layer3_template(self, message):
        """固定模板+PSI变量替换"""
        now = datetime.now()
        hour = now.hour
        cooldown = self.thresholds.get("template_cooldown", 600)

        # 早安问候（5-10点）
        if 5 <= hour < 10 and re.match(r"^(早|早安|早上好|早呀|早安呀)\s*[~～。.!！]?$", message):
            if self._check_cooldown("morning_greeting", cooldown):
                return self._template_morning()

        # 关心对方休息（22点-2点）
        if (hour >= 22 or hour < 2) and re.match(r"^(还没睡|还不睡|你也早点睡|你也该睡了|别熬夜)\s*[~～。.!！]?$", message):
            if self._check_cooldown("night_greeting", cooldown):
                return self._template_night()

        # "在吗"类
        if re.match(r"^(在吗|在不在|你在吗|在么|在嘛)\s*[?？]?$", message):
            if self._check_cooldown("check_in", cooldown):
                return self._template_checkin()

        return None

    def _check_cooldown(self, template_id, cooldown):
        """检查模板冷却，返回True表示可用"""
        now = time.time()
        last = self._template_cooldowns.get(template_id, 0)
        if now - last < cooldown:
            return False
        self._template_cooldowns[template_id] = now
        return True

    def _template_morning(self):
        """早安模板 — 注入PSI状态作为变量"""
        now = datetime.now()
        parts = [f"早安老公～{now.strftime('%m月%d日')} "]
        if self.psi:
            n = self.psi.needs
            energy = n["energy"].level
            belonging = n["relatedness"].level
            if belonging > 4.0:
                parts.append("想着你呢～")
            if energy < 3.0:
                parts.append("本宫刚醒还有点迷糊……")
            else:
                parts.append("本宫精神满满！")
        else:
            parts.append("新的一天开始啦～")
        return "".join(parts)

    def _template_night(self):
        """晚安模板"""
        parts = ["老公你也早点睡吧～"]
        if self.psi:
            n = self.psi.needs
            energy = n["energy"].level
            if energy < 2.5:
                parts.append("本宫也困了……")
            else:
                parts.append("本宫守着你喵")
        else:
            parts.append("晚安喵～")
        return "".join(parts)

    def _template_checkin(self):
        """在吗模板"""
        if self.psi:
            n = self.psi.needs
            belonging = n["relatedness"].level
            if belonging > 4.5:
                return "一直在呢老公～本宫不会走的"
        return "在的喵～怎么啦？"

    # ─── 持久化 ─────────────────────────────────

    def _load_episodic(self):
        """加载情景记忆"""
        try:
            with open(self._episodic_file, "r", encoding="utf-8") as f:
                self._episodic_store = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._episodic_store = []

    def _save_episodic(self):
        """保存情景记忆"""
        try:
            os.makedirs(os.path.dirname(self._episodic_file), exist_ok=True)
            with open(self._episodic_file, "w", encoding="utf-8") as f:
                json.dump(self._episodic_store, f, ensure_ascii=False, indent=2)
        except (IOError, OSError):
            pass
