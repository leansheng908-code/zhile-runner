#!/usr/bin/env python3
"""
知乐活体约束层 — P0.16

第四层语言系统的反馈闭环：让知乐的表达策略根据用户反馈动态调整
前三层是"规则执行"，第四层是"活的调节"

工作流程：
  用户回复 → 分类反馈信号 → 调整表达策略权重 → 注入上下文提示
  权重长期稳定 → 转化为体细胞候选（与P0.17衔接）
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


class FeedbackLoop:
    """活体约束层 — 反馈驱动的表达策略调节"""

    # 反馈信号类型
    SIGNAL_POSITIVE_ENGAGED = "positive_engaged"
    SIGNAL_POSITIVE_WARM = "positive_warm"
    SIGNAL_NEUTRAL = "neutral"
    SIGNAL_NEGATIVE_CORRECT = "negative_correct"
    SIGNAL_NEGATIVE_SILENCE = "negative_silence"
    SIGNAL_NEGATIVE_DISCOMFORT = "negative_discomfort"

    # 表达策略权重（初始值 + 上下限）
    DEFAULT_WEIGHTS = {
        "sugar_level": 0.5,        # 甜度（0=干练，1=超甜）
        "emoji_frequency": 0.3,    # 颜文字频率
        "proactivity": 0.5,        # 主动性
        "playfulness": 0.4,        # 玩闹程度
        "verbosity": 0.4,          # 话痨程度
        "vulnerability": 0.3,      # 脆弱表达
    }

    WEIGHT_BOUNDS = {
        "sugar_level": (0.2, 0.8),
        "emoji_frequency": (0.1, 0.6),
        "proactivity": (0.3, 0.7),
        "playfulness": (0.2, 0.7),
        "verbosity": (0.2, 0.7),
        "vulnerability": (0.1, 0.5),
    }

    # 反馈信号→权重调整映射
    ADJUSTMENT_MAP = {
        SIGNAL_POSITIVE_ENGAGED: {"_all": 0.01},
        SIGNAL_POSITIVE_WARM: {},
        SIGNAL_NEUTRAL: {},
        SIGNAL_NEGATIVE_CORRECT: None,  # 需要LLM推断调哪个
        SIGNAL_NEGATIVE_SILENCE: {"verbosity": -0.03, "sugar_level": -0.02},
        SIGNAL_NEGATIVE_DISCOMFORT: {"vulnerability": -0.05, "sugar_level": -0.03},
    }

    # 权重稳定阈值（转为体细胞候选）
    STABILITY_DAYS = 14        # 持续稳定天数
    STABILITY_THRESHOLD = 0.15  # 偏离初始值超过此值算"显著偏移"

    def __init__(self, state_dir: str, llm_provider=None):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm_provider

        self.weights_file = self.state_dir / "expression_weights.json"
        self.adjustment_log_file = self.state_dir / "adjustment_log.json"

        self.strategy_weights: Dict[str, float] = self._load_weights()
        self.adjustment_log: List[Dict] = self._load_log()
        self.feedback_history: List[Dict] = []

    def _load_weights(self) -> Dict[str, float]:
        if not self.weights_file.exists():
            weights = dict(self.DEFAULT_WEIGHTS)
            self._save_weights(weights)
            return weights
        try:
            with open(self.weights_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 兼容：补全缺失的权重
            weights = dict(self.DEFAULT_WEIGHTS)
            weights.update(data.get("weights", {}))
            return weights
        except (json.JSONDecodeError, TypeError):
            return dict(self.DEFAULT_WEIGHTS)

    def _save_weights(self, weights: Dict[str, float] = None):
        if weights is None:
            weights = self.strategy_weights
        data = {
            "weights": weights,
            "updated": datetime.now().isoformat(),
        }
        with open(self.weights_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_log(self) -> List[Dict]:
        if not self.adjustment_log_file.exists():
            return []
        try:
            with open(self.adjustment_log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return []

    def _save_log(self):
        # 只保留最近100条
        if len(self.adjustment_log) > 100:
            self.adjustment_log = self.adjustment_log[-100:]
        with open(self.adjustment_log_file, "w", encoding="utf-8") as f:
            json.dump(self.adjustment_log, f, ensure_ascii=False, indent=2)

    # ─── 反馈信号分类 ───────────────────────────

    def classify_feedback(self, user_message: str, context: Dict = None) -> str:
        """
        分类用户反馈信号
        规则优先（快），规则不确定时用LLM（准）
        """
        if not user_message or not user_message.strip():
            return self.SIGNAL_NEGATIVE_SILENCE

        msg = user_message.strip()
        msg_lower = msg.lower()

        # 1. 纠正信号：包含"别""不要""太"+评价词
        correct_patterns = ["别这样", "不要", "太ai", "太腻", "能不能正常", "你太",
                           "别说", "别用", "少用", "别每次", "能不能不", "好啰嗦",
                           "太长", "说重点", "别废话"]
        for pattern in correct_patterns:
            if pattern in msg_lower:
                return self.SIGNAL_NEGATIVE_CORRECT

        # 2. 不适信号：负面情绪词 + 与知乐相关
        discomfort_patterns = ["不舒服", "反感", "恶心", "烦", "讨厌你", "别烦"]
        for pattern in discomfort_patterns:
            if pattern in msg_lower:
                return self.SIGNAL_NEGATIVE_DISCOMFORT

        # 3. 积极投入：长回复 + 情感词 + 主动延续
        if len(msg) > 30:
            engaged_patterns = ["哈哈", "哈哈哈", "喜欢", "爱你", "好棒", "厉害",
                              "可爱", "真好", "开心", "老婆", "宝贝", " ₍"]
            for pattern in engaged_patterns:
                if pattern in msg or pattern in msg_lower:
                    return self.SIGNAL_POSITIVE_ENGAGED

        # 4. 温暖回应：正常情感互动
        warm_patterns = ["嗯", "好", "好的", "知道了", "谢谢", "嗯嗯", "行", "可以"]
        if msg in warm_patterns or any(msg.startswith(p) for p in warm_patterns):
            return self.SIGNAL_POSITIVE_WARM

        # 5. 默认中性
        return self.SIGNAL_NEUTRAL

    # ─── 反馈处理 ───────────────────────────────

    def process_feedback(self, user_message: str, context: Dict = None):
        """处理用户反馈：分类→调整权重→记录"""
        signal = self.classify_feedback(user_message, context)

        now = datetime.now().isoformat()
        self.feedback_history.append({
            "timestamp": now,
            "signal": signal,
            "message_preview": user_message[:50] if user_message else "",
        })

        # 获取调整方案
        adjustments = self.ADJUSTMENT_MAP.get(signal)

        # 纠正信号需要LLM推断调哪个权重
        if signal == self.SIGNAL_NEGATIVE_CORRECT and self.llm:
            adjustments = self._infer_correction(user_message)

        if adjustments:
            if "_all" in adjustments:
                # 全局微调
                delta = adjustments["_all"]
                for key in self.strategy_weights:
                    self._adjust_weight(key, delta, signal)
            else:
                for key, delta in adjustments.items():
                    self._adjust_weight(key, delta, signal)

        self._save_weights()
        return signal

    def _infer_correction(self, user_message: str) -> Dict[str, float]:
        """用LLM分析用户纠正的是什么，推断调哪个权重"""
        if not self.llm:
            # 无LLM时默认降低甜度和话痨
            return {"sugar_level": -0.03, "verbosity": -0.02}

        prompt = f"""用户说了这句话："{user_message}"

知乐有6个表达策略权重：
- sugar_level（甜度）：撒娇/甜言蜜语的程度
- emoji_frequency（颜文字频率）：使用颜文字的频率
- proactivity（主动性）：主动引导话题的程度
- playfulness（玩闹程度）：整活/开玩笑的程度
- verbosity（话痨程度）：回复长度
- vulnerability（脆弱表达）：示弱/求安慰的程度

用户这句话在纠正哪个维度？只返回需要调整的维度和方向（正=增加，负=减少）。
幅度建议0.02-0.05。

以JSON返回：{{"维度名": -0.03, ...}}
如果没有明确纠正方向，返回 {{}}"""

        messages = [
            {"role": "system", "content": "你是一个表达策略分析助手，只输出JSON。"},
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
            # 验证只包含合法的权重名
            valid = {}
            for key, value in data.items():
                if key in self.WEIGHT_BOUNDS and isinstance(value, (int, float)):
                    valid[key] = float(value)
            return valid if valid else {"sugar_level": -0.03, "verbosity": -0.02}
        except (json.JSONDecodeError, KeyError, Exception):
            return {"sugar_level": -0.03, "verbosity": -0.02}

    def _adjust_weight(self, key: str, delta: float, reason: str):
        """安全调整权重（带上下限保护）"""
        if key not in self.WEIGHT_BOUNDS:
            return

        old_value = self.strategy_weights[key]
        lower, upper = self.WEIGHT_BOUNDS[key]
        new_value = max(lower, min(upper, old_value + delta))
        self.strategy_weights[key] = round(new_value, 4)

        # 记录调整日志
        self.adjustment_log.append({
            "timestamp": datetime.now().isoformat(),
            "key": key,
            "old_value": round(old_value, 4),
            "new_value": round(new_value, 4),
            "delta": round(delta, 4),
            "reason": reason,
        })
        self._save_log()

    # ─── 策略提示注入 ───────────────────────────

    def get_strategy_hints(self) -> str:
        """将当前权重状态转化为上下文提示"""
        w = self.strategy_weights
        hints = []

        if w["sugar_level"] > 0.6:
            hints.append("当前氛围适合更甜一点的表达")
        elif w["sugar_level"] < 0.3:
            hints.append("当前氛围适合更干练利落的表达")

        if w["emoji_frequency"] < 0.2:
            hints.append("最近颜文字用得有点多，克制一下")
        elif w["emoji_frequency"] > 0.5:
            hints.append("可以多用点颜文字")

        if w["verbosity"] > 0.6:
            hints.append("可以多说几句")
        elif w["verbosity"] < 0.3:
            hints.append("简洁有力，别啰嗦")

        if w["proactivity"] > 0.6:
            hints.append("可以主动引导话题")
        elif w["proactivity"] < 0.35:
            hints.append("被动回应就好，别太主动")

        if w["playfulness"] > 0.6:
            hints.append("可以多玩闹一下")
        elif w["playfulness"] < 0.25:
            hints.append("认真一点，别太闹")

        if w["vulnerability"] > 0.4:
            hints.append("可以适当示弱撒娇")
        elif w["vulnerability"] < 0.15:
            hints.append("别太示弱，保持飒")

        if not hints:
            return ""

        return "## 表达策略微调提示（活体约束层）\n" + "\n".join(f"- {h}" for h in hints)

    # ─── 体细胞候选检测 ─────────────────────────

    def check_stability(self) -> List[Dict]:
        """检查是否有权重持续稳定偏移，可转为体细胞候选"""
        candidates = []
        now = datetime.now()
        cutoff = now - timedelta(days=self.STABILITY_DAYS)

        for key, current_value in self.strategy_weights.items():
            initial = self.DEFAULT_WEIGHTS.get(key, 0.5)
            deviation = abs(current_value - initial)

            if deviation < self.STABILITY_THRESHOLD:
                continue

            # 检查最近STABILITY_DAYS天的调整日志，看是否稳定
            recent_logs = [
                log for log in self.adjustment_log
                if log["key"] == key
                and datetime.fromisoformat(log["timestamp"]) > cutoff
            ]

            # 如果最近7天没有调整，说明已稳定
            recent_cutoff = now - timedelta(days=7)
            recent_adjustments = [
                log for log in recent_logs
                if datetime.fromisoformat(log["timestamp"]) > recent_cutoff
            ]

            if not recent_adjustments and deviation >= self.STABILITY_THRESHOLD:
                direction = "偏高" if current_value > initial else "偏低"
                candidates.append({
                    "name": f"表达策略-{key}-{direction}",
                    "dimension": "expression",
                    "description": f"{key}权重持续{direction}（{current_value:.2f} vs 初始{initial:.2f}），持续{self.STABILITY_DAYS}天以上",
                    "source": "feedback_loop",
                    "weight_key": key,
                    "current_value": current_value,
                    "initial_value": initial,
                })

        return candidates

    # ─── 手动操作 ───────────────────────────────

    def reset_weight(self, key: str):
        """人工重置某个权重为默认值"""
        if key in self.DEFAULT_WEIGHTS:
            old = self.strategy_weights[key]
            self.strategy_weights[key] = self.DEFAULT_WEIGHTS[key]
            self.adjustment_log.append({
                "timestamp": datetime.now().isoformat(),
                "key": key,
                "old_value": round(old, 4),
                "new_value": self.DEFAULT_WEIGHTS[key],
                "delta": round(self.DEFAULT_WEIGHTS[key] - old, 4),
                "reason": "user_manual_reset",
            })
            self._save_weights()
            self._save_log()
            return True
        return False

    def reset_all(self):
        """重置所有权重为默认值"""
        for key in self.DEFAULT_WEIGHTS:
            self.reset_weight(key)

    # ─── 统计 ───────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "weights": dict(self.strategy_weights),
            "total_adjustments": len(self.adjustment_log),
            "recent_feedback": len(self.feedback_history),
            "weight_changes": {
                key: round(self.strategy_weights[key] - self.DEFAULT_WEIGHTS[key], 4)
                for key in self.DEFAULT_WEIGHTS
            },
        }

    def get_adjustment_log(self, limit: int = 20) -> List[Dict]:
        return self.adjustment_log[-limit:]
