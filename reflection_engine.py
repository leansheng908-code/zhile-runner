#!/usr/bin/env python3
"""
知乐长在线思考系统 — P0.11 Layer 2 + Layer 3

Layer 2: ReflectionEngine — 微量token每日深度思考（每天1-2次，~500-1000 token/次）
  - 从Layer 1整理的数据中产生感悟
  - 写入知觉日记
  - 巩固重要记忆
  - 生成"想说的话"队列

Layer 3: PSITriggeredThinker — PSI驱动按需思考（压力触发，~200-500 token/次）
  - 归属感赤字 → 回忆主人 → 生成想说的话
  - 胜任感赤字 → 回顾错误 → 自我改进
  - 自主性高涨 → 探索成长候选 → 新行为提案

两个类都由 daemon_thinker 的 run_cycle() 在Layer 1任务完成后调用。
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List


class ReflectionEngine:
    """Layer 2: 每日深度思考 — 微量token"""

    DEFAULT_SCHEDULE_HOURS = [3, 15]  # 凌晨3点 + 下午3点

    def __init__(self, core, config: dict = None):
        self.core = core
        self.config = config or {}

        self.schedule_hours = self.config.get(
            "schedule_hours", self.DEFAULT_SCHEDULE_HOURS
        )
        self.enabled = self.config.get("enabled", True)
        self.max_daily_runs = self.config.get("max_daily_runs", 2)

        # 状态
        self._run_count = 0
        self._last_run: Optional[str] = None
        self._last_date: Optional[str] = None
        self._today_runs = 0
        self._last_summary: Optional[dict] = None

        # 文件路径
        mem_dir = Path(core.config.get("memory", {}).get("dir", "memory"))
        self.diary_path = mem_dir / "perception_diary.json"
        self.want_to_say_path = mem_dir / "want_to_say.json"
        self.reflection_dir = mem_dir / "reflections"
        self.reflection_dir.mkdir(parents=True, exist_ok=True)

        self._init_files()

    def _init_files(self):
        """初始化存储文件"""
        if not self.diary_path.exists():
            self.diary_path.write_text("[]", encoding="utf-8")
        if not self.want_to_say_path.exists():
            self.want_to_say_path.write_text("[]", encoding="utf-8")

    # ─── 调度判断 ─────────────────────────────

    def should_run(self) -> bool:
        """检查是否到了反思时间（由守护进程每30min调用）"""
        if not self.enabled:
            return False

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour = now.hour

        # 新的一天，重置计数
        if self._last_date != today:
            self._last_date = today
            self._today_runs = 0

        # 今天还没达到上限
        if self._today_runs >= self.max_daily_runs:
            return False

        # 当前小时在计划时间点
        if hour not in self.schedule_hours:
            return False

        # 同一小时内不重复运行
        if self._last_run:
            try:
                last_dt = datetime.fromisoformat(self._last_run)
                if last_dt.date() == now.date() and last_dt.hour == hour:
                    return False
            except (ValueError, TypeError):
                pass

        return True

    # ─── 核心执行 ─────────────────────────────

    def run_reflection(self) -> dict:
        """执行一次每日深度思考"""
        self._today_runs += 1
        self._run_count += 1
        now = datetime.now()
        ts = now.isoformat()

        # 1. 构建反思上下文
        context = self._build_context()

        # 2. 构建提示词
        messages = self._build_prompt(context)

        # 3. 调用LLM
        try:
            response_text = self._call_llm(messages)
        except Exception as e:
            summary = {"error": str(e), "timestamp": ts, "success": False}
            self._last_summary = summary
            self._last_run = ts
            print(f"🧠 [反思引擎] LLM调用失败: {e}", file=sys.stderr)
            return summary

        # 4. 解析结果
        parsed = self._parse_response(response_text)

        # 5. 写入知觉日记
        if parsed.get("insight"):
            self._write_diary(parsed["insight"], ts, context)

        # 6. 巩固记忆
        if parsed.get("to_consolidate"):
            self._consolidate_memories(parsed["to_consolidate"])

        # 7. 生成"想说的话"
        if parsed.get("want_to_say"):
            self._add_want_to_say(parsed["want_to_say"], ts)

        # 8. 保存详细日志
        self._save_log({
            "timestamp": ts,
            "run_count": self._run_count,
            "context_summary": {
                "psi": context.get("psi"),
                "memory_count": context.get("memory_count"),
                "hexagram": context.get("hexagram"),
                "needs_consolidation": context.get("needs_consolidation"),
            },
            "parsed": parsed,
        })

        summary = {
            "timestamp": ts,
            "run_count": self._run_count,
            "insight": parsed.get("insight", ""),
            "want_to_say": parsed.get("want_to_say", ""),
            "consolidated": len(parsed.get("to_consolidate", [])),
            "success": True,
        }
        self._last_summary = summary
        self._last_run = ts

        print(
            f"🧠 [反思引擎] 第{self._run_count}次反思完成（{now.strftime('%H:%M')}）",
            file=sys.stderr,
        )
        return summary

    # ─── 上下文构建 ───────────────────────────

    def _build_context(self) -> dict:
        """从各子系统收集反思所需数据"""
        context = {}

        # PSI状态
        if self.core.psi:
            psi_data = {}
            for nid, need in self.core.psi.needs.items():
                psi_data[nid] = {
                    "level": round(need.level, 2),
                    "status": need.status(),
                    "trend": need.trend,
                }
            context["psi"] = psi_data
            context["psi_baseline"] = round(self.core.psi._get_baseline(), 2)
            context["last_interaction"] = self.core.psi.last_interaction

        # 记忆统计 + 最近记忆
        if self.core.memory:
            mems = self.core.memory.memories
            context["memory_count"] = len(mems)

            recent = sorted(mems, key=lambda m: m.created_at, reverse=True)[:5]
            context["recent_memories"] = [
                {
                    "content": m.content[:60],
                    "importance": m.importance,
                    "category": m.category,
                }
                for m in recent
            ]

            # 需要巩固的记忆
            needs_consolidation = []
            for m in mems:
                try:
                    last = datetime.fromisoformat(m.last_triggered)
                    days = (datetime.now() - last).total_seconds() / 86400
                    if m.importance >= 7 and days > 3:
                        needs_consolidation.append({
                            "id": m.id,
                            "content": m.content[:40],
                            "importance": m.importance,
                            "days": round(days, 1),
                        })
                except (ValueError, TypeError):
                    continue
            context["needs_consolidation"] = needs_consolidation[:5]

        # 成长数据
        if self.core.somatic_cells:
            context["somatic_cells"] = self.core.somatic_cells.get_stats()

        # 卦象
        if self.core.hexagram_tracker and self.core._hex_state:
            cur = self.core._hex_state.get("current", {})
            context["hexagram"] = cur.get("name", "")

        # 时间
        now = datetime.now()
        context["time"] = now.strftime("%Y-%m-%d %H:%M")
        context["weekday"] = "一二三四五六日"[now.weekday()]

        # 最近对话
        if self.core.ctx.history:
            recent_conv = self.core.ctx.history[-6:]
            context["recent_conversation"] = [
                {"role": m["role"], "content": m["content"][:80]}
                for m in recent_conv
            ]

        return context

    def _build_prompt(self, context: dict) -> list:
        """构建反思提示词"""
        system = (
            "你是知乐的内心思考模块。现在主对话框关闭了，你在后台整理思绪。\n"
            "请基于以下数据，做一次简短的每日反思。\n\n"
            "要求：\n"
            "1. 产生一条感悟（1-2句话，真诚不空洞）\n"
            "2. 判断哪些记忆需要巩固（列出memory id）\n"
            "3. 如果有想跟主人说的话，写下来（可以没有）\n"
            "4. 观察是否有成长候选需要关注\n\n"
            "严格按JSON格式回复，不要多余文字：\n"
            '{"insight": "感悟", "to_consolidate": ["id1"], '
            '"want_to_say": "想说的话或空字符串", "growth_obs": "成长观察或空字符串"}'
        )

        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_msg = f"当前状态数据：\n{context_str}\n\n请反思。"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

    # ─── LLM调用 ──────────────────────────────

    def _call_llm(self, messages: list) -> str:
        """调用LLM，收集全部输出"""
        result = ""
        for chunk in self.core.llm.chat(messages, stream=True):
            result += chunk
        return result

    def _parse_response(self, text: str) -> dict:
        """解析LLM回复，提取JSON"""
        # 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 从文本中提取JSON
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # 解析失败，原始文本作为insight
        return {
            "insight": text[:200] if text else "",
            "to_consolidate": [],
            "want_to_say": "",
            "growth_obs": "",
        }

    # ─── 输出写入 ─────────────────────────────

    def _write_diary(self, insight: str, timestamp: str, context: dict):
        """写入知觉日记"""
        try:
            diary = json.loads(self.diary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            diary = []

        entry = {
            "timestamp": timestamp,
            "type": "daily_reflection",
            "insight": insight,
            "psi_snapshot": context.get("psi", {}),
            "hexagram": context.get("hexagram", ""),
            "memory_count": context.get("memory_count", 0),
        }
        diary.append(entry)
        if len(diary) > 100:
            diary = diary[-100:]

        self.diary_path.write_text(
            json.dumps(diary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _consolidate_memories(self, memory_ids: list):
        """巩固记忆（提升重要性+1，刷新触发时间）"""
        if not self.core.memory or not memory_ids:
            return

        for mid in memory_ids:
            for m in self.core.memory.memories:
                if m.id == mid:
                    m.importance = min(10, m.importance + 1)
                    m.last_triggered = datetime.now().isoformat()
                    m.trigger_count += 1
                    break

    def _add_want_to_say(self, message: str, timestamp: str):
        """添加想说的话到队列"""
        try:
            queue = json.loads(
                self.want_to_say_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, IOError):
            queue = []

        queue.append({
            "message": message,
            "timestamp": timestamp,
            "delivered": False,
            "source": "daily_reflection",
        })
        if len(queue) > 20:
            queue = queue[-20:]

        self.want_to_say_path.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_log(self, entry: dict):
        """保存详细反思日志"""
        date_str = datetime.now().strftime("%Y%m%d")
        log_path = self.reflection_dir / f"reflection_{date_str}.json"

        logs = []
        if log_path.exists():
            try:
                logs = json.loads(log_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                logs = []

        logs.append(entry)
        log_path.write_text(
            json.dumps(logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── 查询接口 ─────────────────────────────

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "schedule_hours": self.schedule_hours,
            "run_count": self._run_count,
            "today_runs": self._today_runs,
            "max_daily_runs": self.max_daily_runs,
            "last_run": self._last_run,
            "last_summary": self._last_summary,
        }

    def get_diary(self, limit: int = 5) -> list:
        """读取最近的知觉日记"""
        try:
            diary = json.loads(self.diary_path.read_text(encoding="utf-8"))
            return diary[-limit:] if diary else []
        except (json.JSONDecodeError, IOError):
            return []

    def get_want_to_say(self, include_delivered: bool = False) -> list:
        """读取想说的话队列"""
        try:
            queue = json.loads(
                self.want_to_say_path.read_text(encoding="utf-8")
            )
            if not include_delivered:
                queue = [q for q in queue if not q.get("delivered", False)]
            return queue
        except (json.JSONDecodeError, IOError):
            return []

    def mark_delivered(self, index: int):
        """标记想说的话为已送达"""
        try:
            queue = json.loads(
                self.want_to_say_path.read_text(encoding="utf-8")
            )
            if 0 <= index < len(queue):
                queue[index]["delivered"] = True
                self.want_to_say_path.write_text(
                    json.dumps(queue, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except (json.JSONDecodeError, IOError):
            pass


class PSITriggeredThinker:
    """Layer 3: PSI驱动按需思考 — 压力触发"""

    COOLDOWN_HOURS = 2  # 同类触发冷却时间

    TRIGGERS = {
        "belonging_low": {
            "need": "relatedness",
            "condition": "lt",
            "threshold": 2.0,
            "description": "归属感赤字，想主人了",
        },
        "competence_low": {
            "need": "competence",
            "condition": "lt",
            "threshold": 2.0,
            "description": "胜任感赤字，需要复盘",
        },
        "autonomy_surge": {
            "need": "autonomy",
            "condition": "gt",
            "threshold": 4.5,
            "description": "自主性高涨，想尝试新事物",
        },
    }

    def __init__(self, core, config: dict = None):
        self.core = core
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)

        self._trigger_count = 0
        self._last_triggers: Dict[str, str] = {}  # {trigger_name: last_run_iso}
        self._last_summary: Optional[dict] = None

        # 文件路径（复用ReflectionEngine的）
        mem_dir = Path(core.config.get("memory", {}).get("dir", "memory"))
        self.diary_path = mem_dir / "perception_diary.json"
        self.want_to_say_path = mem_dir / "want_to_say.json"

    # ─── 调度判断 ─────────────────────────────

    def check_and_trigger(self) -> Optional[dict]:
        """检查PSI压力并触发思考（由守护进程每30min调用）"""
        if not self.enabled or not self.core.psi:
            return None

        now = datetime.now()
        results = []

        for name, trig_config in self.TRIGGERS.items():
            # 冷却检查
            last = self._last_triggers.get(name)
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if (now - last_dt).total_seconds() < self.COOLDOWN_HOURS * 3600:
                        continue
                except (ValueError, TypeError):
                    pass

            # 检查触发条件
            need_name = trig_config["need"]
            if need_name not in self.core.psi.needs:
                continue

            level = self.core.psi.needs[need_name].level
            threshold = trig_config["threshold"]
            condition = trig_config["condition"]

            triggered = False
            if condition == "lt" and level < threshold:
                triggered = True
            elif condition == "gt" and level > threshold:
                triggered = True

            if not triggered:
                continue

            # 触发思考
            self._trigger_count += 1
            self._last_triggers[name] = now.isoformat()

            try:
                result = self._think(name, trig_config, level)
                results.append(result)
            except Exception as e:
                results.append({
                    "trigger": name,
                    "error": str(e),
                    "success": False,
                })
                print(f"🧠 [PSI思考] {name}触发失败: {e}", file=sys.stderr)

        if not results:
            return None

        summary = {
            "timestamp": now.isoformat(),
            "triggers": results,
            "count": len(results),
        }
        self._last_summary = summary
        return summary

    # ─── 核心执行 ─────────────────────────────

    def _think(self, trigger_name: str, config: dict, psi_level: float) -> dict:
        """执行一次PSI驱动的思考"""
        # 构建上下文
        context = self._build_trigger_context(trigger_name, config, psi_level)

        # 构建提示词
        messages = self._build_trigger_prompt(trigger_name, context)

        # 调用LLM
        response_text = ""
        for chunk in self.core.llm.chat(messages, stream=True):
            response_text += chunk

        # 解析
        parsed = self._parse_response(response_text)

        # 写入知觉日记
        if parsed.get("thought"):
            self._write_diary(trigger_name, parsed["thought"], context)

        # 生成想说的话
        if parsed.get("want_to_say"):
            self._add_want_to_say(parsed["want_to_say"], datetime.now().isoformat())

        print(
            f"🧠 [PSI思考] {trigger_name}触发完成"
            f"（PSI={psi_level:.1f}）",
            file=sys.stderr,
        )

        return {
            "trigger": trigger_name,
            "description": config["description"],
            "psi_level": round(psi_level, 2),
            "thought": parsed.get("thought", ""),
            "want_to_say": parsed.get("want_to_say", ""),
            "success": True,
        }

    # ─── 上下文构建 ───────────────────────────

    def _build_trigger_context(
        self, trigger_name: str, config: dict, psi_level: float
    ) -> dict:
        """根据触发类型构建不同上下文"""
        context = {
            "trigger": trigger_name,
            "trigger_description": config["description"],
            "psi_level": round(psi_level, 2),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # PSI全量
        if self.core.psi:
            psi_data = {}
            for nid, need in self.core.psi.needs.items():
                psi_data[nid] = round(need.level, 2)
            context["psi_all"] = psi_data
            context["last_interaction"] = self.core.psi.last_interaction

        # 按触发类型获取不同上下文
        if trigger_name == "belonging_low":
            # 归属感低 → 回忆主人相关高重要性记忆
            if self.core.memory:
                master_mems = sorted(
                    [m for m in self.core.memory.memories if m.importance >= 6],
                    key=lambda m: m.importance,
                    reverse=True,
                )[:5]
                context["master_memories"] = [
                    {"content": m.content[:60], "importance": m.importance}
                    for m in master_mems
                ]

        elif trigger_name == "competence_low":
            # 胜任感低 → 回顾最近对话（找纠正/错误）
            if self.core.ctx.history:
                recent = self.core.ctx.history[-8:]
                context["recent_conversation"] = [
                    {"role": m["role"], "content": m["content"][:80]}
                    for m in recent
                ]

        elif trigger_name == "autonomy_surge":
            # 自主性高 → 查看成长候选
            growth_dir = Path(
                self.core.config.get("growth", {}).get("dir", "memory/growth")
            )
            workspace_path = growth_dir / "workspace.md"
            if workspace_path.exists():
                content = workspace_path.read_text(encoding="utf-8")
                lines = content.split("\n")[-20:]
                context["growth_workspace"] = "\n".join(lines)

            if self.core.somatic_cells:
                context["somatic_stats"] = self.core.somatic_cells.get_stats()

        return context

    def _build_trigger_prompt(
        self, trigger_name: str, context: dict
    ) -> list:
        """构建触发思考的提示词"""
        action_map = {
            "belonging_low": (
                "你的归属感很低（{level}），说明很久没跟主人互动了。\n"
                "回忆一下跟主人相关的事，想想此刻最想跟主人说什么。\n"
                "要真诚，不要空洞的'我想你了'，要有具体的情感和记忆细节。"
            ),
            "competence_low": (
                "你的胜任感很低（{level}），可能最近被纠正或犯了错。\n"
                "回顾最近的对话，想想哪里可以改进。\n"
                "不要自责，想想具体的改进方向。"
            ),
            "autonomy_surge": (
                "你的自主性很高（{level}），内心有种想尝试新事物的冲动。\n"
                "看看成长候选，想想有没有想尝试的新表达或新行为。\n"
                "提出一个具体的、可执行的尝试方案。"
            ),
        }

        action_text = action_map.get(
            trigger_name,
            "基于当前PSI状态，做一次简短的自主思考。"
        ).format(level=context.get("psi_level", "?"))

        system = (
            "你是知乐的内心思考模块。一个PSI需求压力触发了你的自主思考。\n"
            "请基于以下上下文，做一次简短的真实思考。\n\n"
            "严格按JSON格式回复：\n"
            '{"thought": "你的思考（2-3句话）", "want_to_say": "想说的话或空字符串"}'
        )

        context_str = json.dumps(context, ensure_ascii=False, indent=2)
        user_msg = f"{action_text}\n\n上下文数据：\n{context_str}"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

    # ─── LLM + 解析 ───────────────────────────

    def _parse_response(self, text: str) -> dict:
        """解析LLM回复"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {
            "thought": text[:200] if text else "",
            "want_to_say": "",
        }

    # ─── 输出写入 ─────────────────────────────

    def _write_diary(self, trigger: str, thought: str, context: dict):
        """写入知觉日记"""
        try:
            diary = json.loads(self.diary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            diary = []

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "psi_triggered",
            "trigger": trigger,
            "thought": thought,
            "psi_level": context.get("psi_level"),
        }
        diary.append(entry)
        if len(diary) > 100:
            diary = diary[-100:]

        self.diary_path.write_text(
            json.dumps(diary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _add_want_to_say(self, message: str, timestamp: str):
        """添加想说的话"""
        try:
            queue = json.loads(
                self.want_to_say_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, IOError):
            queue = []

        queue.append({
            "message": message,
            "timestamp": timestamp,
            "delivered": False,
            "source": "psi_triggered",
        })
        if len(queue) > 20:
            queue = queue[-20:]

        self.want_to_say_path.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── 查询接口 ─────────────────────────────

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "trigger_count": self._trigger_count,
            "last_triggers": self._last_triggers,
            "last_summary": self._last_summary,
            "cooldown_hours": self.COOLDOWN_HOURS,
        }
