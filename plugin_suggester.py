#!/usr/bin/env python3
"""
P0.62: Skills×Plugin 联动 Layer 2 — plugin_suggester.py

桥接 T2 技能模式检测与 growth_engine 自主生长闭环。

工作流:
  1. track_skill_usage() 在 core.chat() 中被调用，记录每次 T2 技能触发
  2. _classify_pattern() 基于规则判断使用模式是否适合转为后台插件
  3. 阈值达到(>=5次 + 跨度>=2天 + 查询型) → _generate_suggestion() 生成建议
  4. 用户通过 CLI /suggest accept → 调用 core.growth_engine.grow() 启动自主生长
  5. 持久化到 memory/plugin_suggestions.json，保留最近 20 条

约束:
  - LLM 调用通过 core.llm，不直接 new provider
  - growth_engine.grow() 通过 core.growth_engine，不直接 import
  - 建议生成不消耗 token（基于规则分类，不调用 LLM）
  - 向后兼容：core/plugin_suggester=None 时所有方法安全返回空
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── 常量 ──────────────────────────────────────────────

SUGGESTION_FILE = Path(__file__).parent / "memory" / "plugin_suggestions.json"

# 阈值
MIN_TRIGGER_COUNT = 5          # 同一技能最少触发次数
MIN_SPAN_DAYS = 2              # 首次到末次使用的最小跨度（天）
MAX_SUGGESTIONS = 20           # 保留最近建议条数

# 模式分类关键词（规则驱动，不调用 LLM）
QUERY_KEYWORDS = [
    "查", "搜索", "查询", "看看", "多少", "什么", "怎么",
    "价格", "天气", "新闻", "股票", "汇率", "行情",
    "状态", "排名", "更新", "最新", "数据", "信息",
]

CHAT_KEYWORDS = [
    "哈哈", "好玩", "有趣", "笑话", "聊天", "闲聊",
    "无聊", "陪我", "讲个", "猜", "游戏",
]

# 技能元数据中 category 值的查询型标识
QUERY_CATEGORIES = {"query", "info", "data", "search", "monitor", "plugin"}


class PluginSuggester:
    """Skills×Plugin 联动建议器 — 检测 T2 技能重复使用模式，建议转为后台插件。"""

    def __init__(self, core=None):
        """初始化建议器。

        Args:
            core: ZhileCore 实例。用于访问 skill_evolution、growth_engine。
                  为 None 时所有方法安全降级返回空。
        """
        self.core = core
        self._file = SUGGESTION_FILE
        self._usage_log: Dict[str, Dict[str, Any]] = {}
        self._suggestions: List[Dict[str, Any]] = []
        self._load()

    # ─── 持久化 ──────────────────────────────────────

    def _load(self) -> None:
        """从磁盘加载历史数据。"""
        try:
            if self._file.exists():
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                self._usage_log = raw.get("usage_log", {})
                self._suggestions = raw.get("suggestions", [])
        except Exception as e:
            print(f"[PluginSuggester] 加载失败，使用空状态: {e}")
            self._usage_log = {}
            self._suggestions = []

    def _save(self) -> None:
        """持久化到磁盘，保留最近 MAX_SUGGESTIONS 条建议。"""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            # 只保留最近 MAX_SUGGESTIONS 条建议
            self._suggestions = self._suggestions[-MAX_SUGGESTIONS:]
            data = {
                "usage_log": self._usage_log,
                "suggestions": self._suggestions,
            }
            self._file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[PluginSuggester] 保存失败: {e}")

    # ─── 核心：记录技能使用 ──────────────────────────

    def track_skill_usage(self, skill_name: str, user_message: str = "") -> None:
        """记录 T2 技能每次被触发，统计频率与时间模式。

        在 core.chat() 流程中调用（通过 core.suggest_check()）。

        Args:
            skill_name: 技能名称
            user_message: 触发该技能的用户消息
        """
        if not skill_name:
            return

        now = datetime.now()
        entry = self._usage_log.get(skill_name, {
            "timestamps": [],
            "messages": [],
            "total_count": 0,
            "first_use": None,
            "last_use": None,
        })

        entry["timestamps"].append(now.isoformat())
        # 保留消息摘要（截断防止膨胀）
        msg_snippet = (user_message or "")[:200]
        entry["messages"].append(msg_snippet)
        entry["total_count"] = entry["total_count"] + 1

        if entry["first_use"] is None:
            entry["first_use"] = now.isoformat()
        entry["last_use"] = now.isoformat()

        # 保留最近 50 条记录防止无限增长
        if len(entry["timestamps"]) > 50:
            entry["timestamps"] = entry["timestamps"][-50:]
            entry["messages"] = entry["messages"][-50:]

        self._usage_log[skill_name] = entry
        self._save()

        # 检查是否应生成新建议
        self._maybe_create_suggestion(skill_name)

    # ─── 模式分类（规则驱动，不调用 LLM）─────────────

    def _classify_pattern(self, skill_name: str) -> str:
        """判断使用模式是否适合转为后台插件。

        分类逻辑（纯规则，不消耗 token）：
          - "query_type": 定时重复+信息查询型 → 适合转插件
          - "chat_type": 偶尔闲聊型 → 不适合

        判定维度：
          1. 技能名/元数据 category 是否属于查询类
          2. 用户消息中查询关键词占比
          3. 使用频率（高频→查询型倾向）

        Returns:
            "query_type" | "chat_type"
        """
        entry = self._usage_log.get(skill_name, {})
        messages = entry.get("messages", [])
        total = entry.get("total_count", 0)

        # 维度1: 技能元数据 category
        skill_category = ""
        if self.core and hasattr(self.core, "skill_evolution") and self.core.skill_evolution:
            reg = self.core.skill_evolution.skills_registry
            meta = reg.get(skill_name, {}).get("metadata", {})
            skill_category = meta.get("category", "").lower()

        category_is_query = skill_category in QUERY_CATEGORIES

        # 维度2: 用户消息中查询关键词命中
        query_hits = 0
        chat_hits = 0
        for msg in messages:
            msg_lower = msg.lower()
            for kw in QUERY_KEYWORDS:
                if kw in msg_lower:
                    query_hits += 1
                    break
            for kw in CHAT_KEYWORDS:
                if kw in msg_lower:
                    chat_hits += 1
                    break

        query_ratio = query_hits / max(len(messages), 1)
        chat_ratio = chat_hits / max(len(messages), 1)

        # 维度3: 使用频率（平均间隔）
        timestamps = entry.get("timestamps", [])
        avg_interval_hours = 0
        if len(timestamps) >= 2:
            try:
                times = [datetime.fromisoformat(ts) for ts in timestamps]
                total_span = (times[-1] - times[0]).total_seconds()
                avg_interval_hours = total_span / max(len(times) - 1, 1) / 3600
            except Exception:
                pass

        # 规则决策：
        # 1) category 明确为查询类 → query_type
        # 2) 查询关键词占比 > 50% 且 闲聊占比 < 20% → query_type
        # 3) 高频使用(平均间隔 < 24h) 且 查询占比 > 闲聊占比 → query_type
        # 4) 闲聊占比 > 50% → chat_type
        # 5) 默认 → chat_type（保守策略）

        if category_is_query:
            return "query_type"

        if query_ratio > 0.5 and chat_ratio < 0.2:
            return "query_type"

        if avg_interval_hours > 0 and avg_interval_hours < 24 and query_ratio > chat_ratio:
            return "query_type"

        if chat_ratio > 0.5:
            return "chat_type"

        return "chat_type"

    # ─── 建议生成 ────────────────────────────────────

    def _maybe_create_suggestion(self, skill_name: str) -> None:
        """检查阈值，满足条件则生成建议。"""
        entry = self._usage_log.get(skill_name, {})
        total = entry.get("total_count", 0)

        # 阈值1: 触发次数
        if total < MIN_TRIGGER_COUNT:
            return

        # 阈值2: 跨度 >= 2 天
        first = entry.get("first_use")
        last = entry.get("last_use")
        span_days = 0
        if first and last:
            try:
                d1 = datetime.fromisoformat(first)
                d2 = datetime.fromisoformat(last)
                span_days = (d2 - d1).days
            except Exception:
                pass
        if span_days < MIN_SPAN_DAYS:
            return

        # 阈值3: 模式分类为查询型
        pattern = self._classify_pattern(skill_name)
        if pattern != "query_type":
            return

        # 去重：已有 pending 建议则跳过
        existing = [
            s for s in self._suggestions
            if s.get("skill_name") == skill_name and s.get("status") == "pending"
        ]
        if existing:
            return

        suggestion = self._generate_suggestion(skill_name, span_days)
        self._suggestions.append(suggestion)
        self._save()
        print(f"[PluginSuggester] 生成新建议: {suggestion['id']} "
              f"(技能={skill_name}, 次数={total}, 跨度={span_days}天)")

    def _generate_suggestion(
        self, skill_name: str, span_days: int = 0
    ) -> Dict[str, Any]:
        """生成插件建议（不调用 LLM，基于规则拼接）。

        Args:
            skill_name: 技能名称
            span_days: 使用跨度天数

        Returns:
            建议 dict
        """
        entry = self._usage_log.get(skill_name, {})
        total = entry.get("total_count", 0)
        messages = entry.get("messages", [])

        # 获取技能描述
        skill_desc = ""
        if self.core and hasattr(self.core, "skill_evolution") and self.core.skill_evolution:
            reg = self.core.skill_evolution.skills_registry
            meta = reg.get(skill_name, {}).get("metadata", {})
            skill_desc = meta.get("description", "")

        # 频率建议
        if span_days > 0 and total > 0:
            per_day = total / span_days
            if per_day >= 2:
                freq_advice = "建议定时执行（每4小时）"
            elif per_day >= 1:
                freq_advice = "建议定时执行（每日）"
            else:
                freq_advice = "建议定时执行（每2-3天）"
        else:
            freq_advice = "建议定时执行（每日）"

        # 提取代表性用户消息
        sample_msgs = [m for m in messages if m.strip()][:3]

        description = (
            f"技能「{skill_name}」在 {span_days} 天内被触发 {total} 次，"
            f"模式为查询型，适合转为后台插件自动执行。"
        )
        if skill_desc:
            description += f" 技能描述: {skill_desc}"

        capability_desc = (
            f"将技能 {skill_name} 的查询能力转为后台插件，"
            f"自动定时执行。用户典型请求: {'; '.join(sample_msgs[:2])}"
        )

        return {
            "id": str(uuid.uuid4())[:8],
            "skill_name": skill_name,
            "created": datetime.now().isoformat(),
            "status": "pending",
            "usage_count": total,
            "span_days": span_days,
            "pattern": "query_type",
            "description": description,
            "capability_desc": capability_desc,
            "frequency_advice": freq_advice,
            "sample_messages": sample_msgs,
        }

    # ─── 外部 API ────────────────────────────────────

    def get_suggestions(self, status: str = "pending") -> List[Dict[str, Any]]:
        """返回待处理建议列表。

        Args:
            status: "pending" | "accepted" | "dismissed" | "all"

        Returns:
            建议列表
        """
        if status == "all":
            return list(self._suggestions)
        return [s for s in self._suggestions if s.get("status") == status]

    def accept_suggestion(self, suggestion_id: str) -> Dict[str, Any]:
        """用户接受建议 → 调用 core.growth_engine.grow() 启动自主生长闭环。

        Args:
            suggestion_id: 建议 ID

        Returns:
            {"success": bool, "message": str, "grow_result": dict}
        """
        suggestion = None
        for s in self._suggestions:
            if s["id"] == suggestion_id:
                suggestion = s
                break

        if not suggestion:
            return {"success": False, "message": f"未找到建议: {suggestion_id}"}

        if suggestion["status"] != "pending":
            return {"success": False,
                    "message": f"建议已处理（当前状态: {suggestion['status']}）"}

        # 通过 core.growth_engine 调用，不直接 import
        if not self.core or not getattr(self.core, "growth_engine", None):
            return {"success": False, "message": "GrowthEngine 未启用，无法启动生长"}

        capability_desc = suggestion.get("capability_desc", suggestion["description"])
        print(f"[PluginSuggester] 接受建议 {suggestion_id}，启动生长: {capability_desc[:80]}")

        try:
            grow_result = self.core.growth_engine.grow(capability_desc)
        except Exception as e:
            return {"success": False, "message": f"生长引擎异常: {e}"}

        suggestion["status"] = "accepted"
        suggestion["accepted_at"] = datetime.now().isoformat()
        suggestion["grow_result"] = {
            "success": grow_result.get("success", False),
            "installed": grow_result.get("installed", False),
        }
        self._save()

        return {
            "success": True,
            "message": "建议已接受，生长闭环已启动",
            "grow_result": grow_result,
        }

    def reject_suggestion(self, suggestion_id: str) -> Dict[str, Any]:
        """用户拒绝建议 → 标记 dismissed。

        Args:
            suggestion_id: 建议 ID

        Returns:
            {"success": bool, "message": str}
        """
        suggestion = None
        for s in self._suggestions:
            if s["id"] == suggestion_id:
                suggestion = s
                break

        if not suggestion:
            return {"success": False, "message": f"未找到建议: {suggestion_id}"}

        if suggestion["status"] != "pending":
            return {"success": False,
                    "message": f"建议已处理（当前状态: {suggestion['status']}）"}

        suggestion["status"] = "dismissed"
        suggestion["dismissed_at"] = datetime.now().isoformat()
        self._save()

        return {"success": True, "message": "建议已拒绝"}

    def get_stats(self) -> Dict[str, Any]:
        """返回统计摘要。"""
        pending = len([s for s in self._suggestions if s["status"] == "pending"])
        accepted = len([s for s in self._suggestions if s["status"] == "accepted"])
        dismissed = len([s for s in self._suggestions if s["status"] == "dismissed"])
        tracked_skills = len(self._usage_log)
        return {
            "tracked_skills": tracked_skills,
            "total_suggestions": len(self._suggestions),
            "pending": pending,
            "accepted": accepted,
            "dismissed": dismissed,
        }


# ─── 自测 ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("PluginSuggester 自测 — 5项")
    print("=" * 60)

    # 使用临时文件避免污染正式数据
    tmpdir = tempfile.mkdtemp()
    test_file = Path(tmpdir) / "plugin_suggestions.json"

    all_passed = True

    # ── 测试1: 实例化 ──
    print("\n[1/5] 实例化...")
    try:
        # 临时替换文件路径
        original_file = SUGGESTION_FILE
        # 直接操作类属性
        PluginSuggester._test_file_override = test_file
        suggester = PluginSuggester(core=None)
        # 手动设置文件路径
        suggester._file = test_file
        print(f"  ✅ 实例化成功 (core=None, 安全降级)")
        print(f"  统计: {suggester.get_stats()}")
    except Exception as e:
        print(f"  ❌ 实例化失败: {e}")
        all_passed = False
        suggester = None

    if suggester is None:
        print("\n无法继续后续测试")
        sys_exit_code = 1
    else:
        # ── 测试2: track_skill_usage ──
        print("\n[2/5] track_skill_usage...")
        try:
            suggester.track_skill_usage("test_skill", "查一下今天的天气")
            suggester.track_skill_usage("test_skill", "查一下股票价格")
            stats = suggester.get_stats()
            assert stats["tracked_skills"] == 1, f"期望1个追踪技能, 得到{stats['tracked_skills']}"
            entry = suggester._usage_log["test_skill"]
            assert entry["total_count"] == 2, f"期望2次, 得到{entry['total_count']}"
            print(f"  ✅ track_skill_usage 正常 (count={entry['total_count']})")
        except Exception as e:
            print(f"  ❌ track_skill_usage 失败: {e}")
            all_passed = False

        # ── 测试3: get_suggestions ──
        print("\n[3/5] get_suggestions...")
        try:
            pending = suggester.get_suggestions("pending")
            all_s = suggester.get_suggestions("all")
            assert isinstance(pending, list), "应返回列表"
            assert isinstance(all_s, list), "应返回列表"
            print(f"  ✅ get_suggestions 正常 (pending={len(pending)}, all={len(all_s)})")
        except Exception as e:
            print(f"  ❌ get_suggestions 失败: {e}")
            all_passed = False

        # ── 测试4: 持久化 ──
        print("\n[4/5] 持久化...")
        try:
            suggester._save()
            assert test_file.exists(), "持久化文件应存在"
            raw = json.loads(test_file.read_text(encoding="utf-8"))
            assert "usage_log" in raw, "应包含 usage_log"
            assert "suggestions" in raw, "应包含 suggestions"
            assert "test_skill" in raw["usage_log"], "应包含 test_skill"
            print(f"  ✅ 持久化正常 (文件存在, 数据完整)")
        except Exception as e:
            print(f"  ❌ 持久化失败: {e}")
            all_passed = False

        # ── 测试5: 阈值判断 ──
        print("\n[5/5] 阈值判断...")
        try:
            # 模拟跨2天5次查询型使用
            suggester2 = PluginSuggester(core=None)
            suggester2._file = test_file
            suggester2._usage_log = {}
            suggester2._suggestions = []

            skill_name = "threshold_test"
            base_time = datetime.now() - timedelta(days=3)
            for i in range(5):
                ts = base_time + timedelta(days=i * 0.75)
                entry = suggester2._usage_log.get(skill_name, {
                    "timestamps": [], "messages": [],
                    "total_count": 0, "first_use": None, "last_use": None,
                })
                entry["timestamps"].append(ts.isoformat())
                entry["messages"].append(f"查询第{i+1}次数据")
                entry["total_count"] = entry["total_count"] + 1
                if entry["first_use"] is None:
                    entry["first_use"] = ts.isoformat()
                entry["last_use"] = ts.isoformat()
                suggester2._usage_log[skill_name] = entry

            # 检查阈值条件
            entry = suggester2._usage_log[skill_name]
            first_dt = datetime.fromisoformat(entry["first_use"])
            last_dt = datetime.fromisoformat(entry["last_use"])
            span = (last_dt - first_dt).days
            assert entry["total_count"] >= MIN_TRIGGER_COUNT, "次数应达标"
            assert span >= MIN_SPAN_DAYS, f"跨度应>=2天, 实际{span}天"

            # 分类应为 query_type（消息含查询关键词）
            pattern = suggester2._classify_pattern(skill_name)
            assert pattern == "query_type", f"应分类为query_type, 实际{pattern}"

            # 手动触发建议生成检查
            suggester2._maybe_create_suggestion(skill_name)
            pending = suggester2.get_suggestions("pending")
            assert len(pending) == 1, f"应生成1条建议, 实际{len(pending)}"
            assert pending[0]["skill_name"] == skill_name
            print(f"  ✅ 阈值判断正确 (5次/{span}天 → query_type → 生成建议)")
            print(f"     建议ID: {pending[0]['id']}")
            print(f"     描述: {pending[0]['description'][:60]}...")

            # 测试 accept（core=None 应安全返回失败）
            result = suggester2.accept_suggestion(pending[0]["id"])
            assert not result["success"], "core=None 时 accept 应返回失败"
            print(f"  ✅ 向后兼容: core=None 时 accept 安全降级")

            # 测试 reject
            result = suggester2.reject_suggestion(pending[0]["id"])
            assert result["success"], "reject 应成功"
            assert suggester2.get_suggestions("pending") == []
            print(f"  ✅ reject 正常 (建议已标记 dismissed)")

        except Exception as e:
            print(f"  ❌ 阈值判断失败: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    print(f"\n{'=' * 60}")
    if all_passed:
        print("🎉 全部 5 项测试通过！")
    else:
        print("⚠ 部分测试未通过")
    print(f"{'=' * 60}")
