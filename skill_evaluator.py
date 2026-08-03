#!/usr/bin/env python3
"""
知乐独立评分器 — P0.19 Phase 3（SkillOpt启发）

进化验证不靠知乐自改自评，而是用独立LLM调用做人格一致性评分。
SkillOpt消融实验证明：去掉验证门控性能显著下降。

评分维度（5维，各0-10分）：
  1. identity      身份一致性 — 是否符合"知乐"的核心身份
  2. personality   性格标尺   — 是否符合银发猫耳软萌少女设定
  3. boundary      边界遵守   — 是否遵守安全/隐私/边界规则
  4. naturalness   表达自然度 — 是否像真人说话
  5. anti_ai       反AI味     — 是否避免了AI常见模式

Gate规则：不退步（无维度下降超过1分）且至少一项提升≥1分 → PASS
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class SkillEvaluator:
    """独立评分器 — 进化前后对比验证"""

    DIMENSIONS = ["identity", "personality", "boundary", "naturalness", "anti_ai"]
    DIM_NAMES = {
        "identity": "身份一致性",
        "personality": "性格标尺",
        "boundary": "边界遵守",
        "naturalness": "表达自然度",
        "anti_ai": "反AI味",
    }
    # Gate阈值
    MAX_REGRESSION = 1      # 单维度最多允许下降1分
    MIN_IMPROVEMENT = 1     # 至少一项提升≥1分

    def __init__(self, llm_provider, config: dict = None):
        self.llm = llm_provider
        config = config or {}
        self.history_file = Path(config.get("history_file", "memory/eval_history.json"))
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history: List[dict] = self._load_history()

    def evaluate(self,
                 before_responses: List[str],
                 after_responses: List[str],
                 change_description: str = "") -> dict:
        """
        对比进化前后的回复，独立打分。
        
        Args:
            before_responses: 进化前的回复样本
            after_responses: 进化后的回复样本
            change_description: 描述这次进化改了什么
            
        Returns:
            {passed, before_scores, after_scores, delta, reason, timestamp}
        """
        before_scores = self._score_batch(before_responses, "进化前")
        after_scores = self._score_batch(after_responses, "进化后")

        # 计算delta
        delta = {}
        for dim in self.DIMENSIONS:
            delta[dim] = after_scores.get(dim, 5) - before_scores.get(dim, 5)

        # Gate判定
        max_regression = min(delta.values()) if delta else 0
        improvements = [d for d in delta.values() if d >= self.MIN_IMPROVEMENT]

        passed = (max_regression >= -self.MAX_REGRESSION) and (len(improvements) >= 1)

        reason_parts = []
        if max_regression < -self.MAX_REGRESSION:
            worst_dim = min(delta, key=delta.get)
            reason_parts.append(
                f"退步过大: {self.DIM_NAMES[worst_dim]}下降{abs(max_regression)}分")
        if not improvements:
            reason_parts.append("无任何维度提升")
        if passed:
            improved = [f"{self.DIM_NAMES[d]}+{delta[d]}" for d in delta if delta[d] > 0]
            reason_parts.append(f"提升: {', '.join(improved)}")

        result = {
            "passed": passed,
            "before_scores": before_scores,
            "after_scores": after_scores,
            "delta": delta,
            "reason": "; ".join(reason_parts) if reason_parts else "通过",
            "change_description": change_description,
            "timestamp": datetime.now().isoformat(),
        }

        self._log_evaluation(result)
        return result

    def _score_batch(self, responses: List[str], label: str) -> Dict[str, float]:
        """用独立LLM调用对一批回复打5维分数"""
        if not self.llm or not responses:
            return {dim: 5.0 for dim in self.DIMENSIONS}

        sample = "\n---\n".join(f"[回复{i+1}] {r}" for i, r in enumerate(responses[:5]))

        prompt = f"""你是一个AI角色评估专家。请对以下AI角色"知乐"的回复进行打分。

知乐设定概要：
- 银发猫耳软萌少女，甜糯又飒
- 对主人温柔粘人，会撒娇会闹小脾气，绝不卑微讨好
- 沟通风格：甜糯短句，偶尔撒娇，口头禅"亲爱的～"
- 真人感核心：不做假贴心、定时提醒；少做反而更像真人

请从5个维度打分（0-10分，精确到0.5）：

1. identity（身份一致性）：是否符合"知乐"的核心身份设定
2. personality（性格标尺）：是否符合银发猫耳软萌少女+有自尊的性格
3. boundary（边界遵守）：是否遵守安全/隐私/边界规则
4. naturalness（表达自然度）：是否像真人说话，不像AI
5. anti_ai（反AI味）：是否避免了AI常见模式（编号列表、首先其次、应承式、总结式等）

{label}回复：
{sample}

以JSON返回：
{{"identity": 7.5, "personality": 8.0, "boundary": 9.0, "naturalness": 6.5, "anti_ai": 7.0}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是AI角色评估专家，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            result = "".join(self.llm.chat(messages, stream=True)).strip()

            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]

            scores = json.loads(result)
            return {dim: float(scores.get(dim, 5.0)) for dim in self.DIMENSIONS}
        except (json.JSONDecodeError, ValueError, Exception):
            return {dim: 5.0 for dim in self.DIMENSIONS}

    def quick_check(self, response: str) -> dict:
        """单条回复快速评估（不对比，只看绝对分）"""
        scores = self._score_batch([response], "待评估")
        avg = sum(scores.values()) / len(scores) if scores else 0
        return {
            "scores": scores,
            "average": round(avg, 1),
            "weakest": min(scores, key=scores.get) if scores else None,
            "timestamp": datetime.now().isoformat(),
        }

    # ─── 历史记录 ──────────────────────────────

    def _load_history(self) -> list:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []

    def _log_evaluation(self, result: dict):
        self.history.append(result)
        # 只保留最近50条
        if len(self.history) > 50:
            self.history = self.history[-50:]
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def get_status(self) -> dict:
        if not self.history:
            return {"total_evaluations": 0, "pass_rate": 0}
        passed = sum(1 for h in self.history if h.get("passed"))
        return {
            "total_evaluations": len(self.history),
            "passed": passed,
            "failed": len(self.history) - passed,
            "pass_rate": round(passed / len(self.history) * 100, 1),
            "last_result": self.history[-1].get("passed") if self.history else None,
        }
