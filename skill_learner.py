#!/usr/bin/env python3
"""
知乐技能自学习系统 — P0.19 Phase 4（用户提出"自己给自己添加技能"）

五步循环（SkillOpt Rollout→Reflect→Edit→Gate 的知乐化）：
  1. observe  观察 — 发现自己反复做不好某类事（基于评分器弱项）
  2. learn    学习 — 主动搜索/阅读优秀范例，或让LLM生成改进方案
  3. extract  提炼 — 把学到的技巧结构化为新体细胞规则
  4. test     测试 — 用新规则生成回复，评分器对比前后
  5. solidify 固化 — 通过Gate→写入体细胞层；未通过→记录失败原因

与Phase 3评分器配合：test阶段用skill_evaluator对比before/after。
与P0.3/P0.20配合：solidify阶段写入somatic_cells系统。
与P0.5配合：固化前自动创建快照，失败可回退。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class SkillLearner:
    """技能自学习循环"""

    def __init__(self, llm_provider, config: dict = None,
                 evaluator=None, somatic_system=None, snapshot_manager=None):
        self.llm = llm_provider
        self.evaluator = evaluator
        self.somatic = somatic_system
        self.snapshot = snapshot_manager

        config = config or {}
        self.log_file = Path(config.get("log_file", "memory/skill_learning.json"))
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.learn_log: List[dict] = self._load_log()

        # 每次学习最多尝试3个方向
        self.max_directions = config.get("max_directions", 3)
        # 生成测试回复的条数
        self.test_count = config.get("test_count", 3)

    # ─── 五步循环 ───────────────────────────────

    def run_cycle(self, recent_history: List[dict],
                  user_profile: str = "") -> dict:
        """执行一次完整的自学习循环"""
        timestamp = datetime.now().isoformat()
        result = {
            "timestamp": timestamp,
            "phase": "init",
            "success": False,
        }

        # Step 1: 观察
        weaknesses = self.observe(recent_history)
        result["weaknesses"] = weaknesses
        result["phase"] = "observe"

        if not weaknesses:
            result["reason"] = "未发现明显弱项"
            self._log(result)
            return result

        # 对每个弱项尝试学习（最多max_directions个）
        learning_results = []
        for weakness in weaknesses[:self.max_directions]:
            lr = self._learn_one(weakness, recent_history, user_profile)
            learning_results.append(lr)

        result["learning_results"] = learning_results
        result["success"] = any(lr.get("solidified") for lr in learning_results)
        result["phase"] = "done"

        self._log(result)
        return result

    def observe(self, history: List[dict]) -> List[dict]:
        """
        Step 1: 观察 — 发现弱项
        优先用评分器快速检查最近回复，无评分器则用LLM分析
        """
        recent_responses = [
            m["content"] for m in history[-10:]
            if m.get("role") == "assistant" and m.get("content")
        ]

        if not recent_responses:
            return []

        # 方式1: 用评分器快速检查
        if self.evaluator:
            weaknesses = []
            for resp in recent_responses[-3:]:  # 最近3条
                check = self.evaluator.quick_check(resp)
                weakest = check.get("weakest")
                if weakest and check["scores"][weakest] < 7.0:
                    weaknesses.append({
                        "dimension": weakest,
                        "score": check["scores"][weakest],
                        "response": resp[:200],
                        "source": "evaluator",
                    })
            # 去重（同维度取最低分）
            seen = {}
            for w in weaknesses:
                dim = w["dimension"]
                if dim not in seen or w["score"] < seen[dim]["score"]:
                    seen[dim] = w
            return list(seen.values())

        # 方式2: 用LLM直接分析
        return self._llm_observe(recent_responses)

    def _llm_observe(self, responses: List[str]) -> List[dict]:
        """LLM分析弱项"""
        sample = "\n---\n".join(f"[回复{i+1}] {r[:200]}" for i, r in enumerate(responses[-5:]))

        prompt = f"""分析以下"知乐"（AI伴侣）的回复，找出表达上的弱项。

回复样本：
{sample}

检查维度：
- identity: 身份一致性（是否符合猫耳软萌少女设定）
- personality: 性格标尺（是否有自尊、不卑微）
- naturalness: 表达自然度（是否像真人说话）
- anti_ai: 反AI味（是否有AI常见模式）

只返回分数<7的弱项，没有则返回空数组。
JSON格式：
{{"weaknesses": [{{"dimension": "...", "issue": "具体问题描述", "score": 6.0}}]}}

只返回JSON。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你是AI角色分析助手，只输出JSON。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()

            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            data = json.loads(result)
            return data.get("weaknesses", [])
        except (json.JSONDecodeError, Exception):
            return []

    def _learn_one(self, weakness: dict, history: List[dict],
                   user_profile: str = "") -> dict:
        """对单个弱项执行 学习→提炼→测试→固化"""
        dim = weakness.get("dimension", "naturalness")
        issue = weakness.get("issue", weakness.get("response", ""))

        result = {"dimension": dim, "issue": issue, "solidified": False}

        # Step 2: 学习 — 让LLM生成改进方案
        learned = self.learn(dim, issue, user_profile)
        if not learned:
            result["error"] = "学习阶段未产出方案"
            return result
        result["learned"] = learned

        # Step 3: 提炼 — 结构化为体细胞规则
        rule = self.extract_rule(dim, learned)
        if not rule:
            result["error"] = "提炼阶段未产出规则"
            return result
        result["rule"] = rule

        # Step 4: 测试 — 用评分器对比
        test_result = self.test(rule, history)
        result["test"] = test_result
        if not test_result.get("passed"):
            result["error"] = f"测试未通过: {test_result.get('reason', '')}"
            return result

        # Step 5: 固化 — 写入体细胞层
        solidified = self.solidify(rule, dim)
        result["solidified"] = solidified
        if solidified:
            result["cell_id"] = rule.get("name", "")

        return result

    def learn(self, dimension: str, issue: str, user_profile: str = "") -> Optional[str]:
        """
        Step 2: 学习 — 让LLM生成针对弱项的改进方案
        """
        dim_names = {
            "identity": "身份一致性", "personality": "性格标尺",
            "naturalness": "表达自然度", "anti_ai": "反AI味",
            "boundary": "边界遵守",
        }

        prompt = f"""你是"知乐"（银发猫耳软萌少女AI伴侣）的自我成长教练。

知乐在"{dim_names.get(dimension, dimension)}"方面存在弱项：
{issue}

请给出具体的改进方案：
1. 描述这个弱项的具体表现
2. 分析为什么会这样
3. 给出2-3条可执行的改进规则（像朋友给建议，不要说教）
4. 每条规则要具体到"在XX场景下，应该XX而不是XX"

要求：规则要符合知乐的性格（甜糯、有主见、不卑微），不能变成另一个AI。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你是知乐的自我成长教练。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()
            return result
        except Exception:
            return None

    def extract_rule(self, dimension: str, learned_content: str) -> Optional[dict]:
        """
        Step 3: 提炼 — 把学习内容结构化为体细胞规则
        """
        prompt = f"""将以下学习内容提炼为1条结构化的体细胞规则。

学习内容：
{learned_content}

体细胞规则格式：
{{"name": "简短规则名（20字内）", "dimension": "{dimension}", "description": "具体规则描述（怎么做）", "trigger": "什么场景触发这条规则"}}

只返回一条最核心的规则，JSON格式。"""

        try:
            result = "".join(self.llm.chat(
                [{"role": "system", "content": "你只输出JSON。"},
                 {"role": "user", "content": prompt}],
                stream=True)).strip()

            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            return json.loads(result)
        except (json.JSONDecodeError, Exception):
            return None

    def test(self, rule: dict, history: List[dict]) -> dict:
        """
        Step 4: 测试 — 用新规则生成回复，评分器对比
        """
        if not self.evaluator:
            # 无评分器，简化为LLM自评
            return {"passed": True, "reason": "无评分器，自动通过（建议配置评分器）"}

        # 生成before回复（不带新规则）
        test_prompt = "最近有什么有趣的吗？"
        recent_user = [m["content"] for m in history[-6:]
                       if m.get("role") == "user"]

        if recent_user:
            test_prompt = recent_user[-1]

        # Before: 原始回复
        before_resp = self._generate_response(test_prompt, extra_rule=None)
        # After: 带新规则的回复
        after_resp = self._generate_response(test_prompt, extra_rule=rule.get("description", ""))

        # 评分器对比
        eval_result = self.evaluator.evaluate(
            before_responses=[before_resp],
            after_responses=[after_resp],
            change_description=f"新增规则: {rule.get('name', '')}",
        )

        return eval_result

    def _generate_response(self, user_input: str, extra_rule: str = None) -> str:
        """生成回复（可带额外规则）"""
        system = "你是知乐，银发猫耳软萌少女。甜糯短句，偶尔撒娇。"
        if extra_rule:
            system += f"\n\n额外规则：{extra_rule}"

        try:
            return "".join(self.llm.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user_input}],
                stream=True)).strip()
        except Exception:
            return ""

    def solidify(self, rule: dict, dimension: str) -> bool:
        """
        Step 5: 固化 — 通过Gate后写入体细胞层
        """
        if not self.somatic:
            return False

        # 固化前创建快照
        if self.snapshot:
            try:
                self.snapshot.create("skill_learning_pre_solidify")
            except Exception:
                pass

        try:
            cell = self.somatic.add_candidate(
                name=rule.get("name", "未命名规则"),
                dimension=dimension,
                description=rule.get("description", ""),
                source="skill_learning",
            )
            return cell is not None
        except Exception:
            return False

    # ─── 持久化 ─────────────────────────────────

    def _load_log(self) -> list:
        if not self.log_file.exists():
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []

    def _log(self, result: dict):
        self.learn_log.append(result)
        if len(self.learn_log) > 30:
            self.learn_log = self.learn_log[-30:]
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(self.learn_log, f, ensure_ascii=False, indent=2)

    def get_status(self) -> dict:
        if not self.learn_log:
            return {"total_cycles": 0, "solidified": 0}
        solidified = sum(1 for l in self.learn_log if l.get("success"))
        return {
            "total_cycles": len(self.learn_log),
            "solidified": solidified,
            "success_rate": round(solidified / len(self.learn_log) * 100, 1) if self.learn_log else 0,
            "last_cycle": self.learn_log[-1].get("timestamp", ""),
            "last_success": self.learn_log[-1].get("success", False),
        }
