#!/usr/bin/env python3
"""
P0.28 · 遗忘测试自动化闭环

管理"移出→观察→评分→恢复/转正"完整周期。

流程：
  1. 候选体细胞创建后立即注入上下文（P0.3设计）
  2. 注入WITHDRAW_DELAY轮后，临时从上下文移出
  3. 观察OBSERVE_TURNS轮对话，检测行为是否自发回归
  4. LLM分析判定：回归=passed+1，消失=failed+1
  5. passed≥3 → 转活跃（永久注入）；failed≥2 → 丢弃
  6. 未达阈值 → 恢复注入，等待下个测试周期
  7. 超过MAX_TEST_CYCLES仍未决定 → 强制转正（稳定存在）

Token成本：每个测试周期结束时1次LLM调用（约500-1000 token）
依赖：somatic_cells.py（SomaticCellSystem）+ llm_provider.py（LLMProvider）
"""

import json
import sys
from datetime import datetime
from typing import Optional, List


class ForgetTestScheduler:
    """遗忘测试编排器 — 协调移出/观察/评分/恢复"""

    WITHDRAW_DELAY = 5      # 注入N轮后开始移出测试
    OBSERVE_TURNS = 5       # 移出后观察N轮
    MAX_TEST_CYCLES = 5     # 最大测试周期数（防止无限循环）

    def __init__(self, somatic_system, llm_provider=None):
        """
        Args:
            somatic_system: SomaticCellSystem实例
            llm_provider: LLMProvider实例（用于回归检测）
        """
        self.somatic = somatic_system
        self.llm = llm_provider

    def tick(self, current_turn: int, history: List[dict]) -> dict:
        """
        每轮对话后调用，驱动遗忘测试状态机。
        
        Args:
            current_turn: 当前对话轮次（从1开始）
            history: 对话历史列表
            
        Returns:
            {
                "started_tests": [...],    # 本轮开始测试的cell
                "completed_tests": [...],  # 本轮完成测试的cell
                "promotions": [...],       # 本轮转正的cell
                "discards": [...],         # 本轮丢弃的cell
            }
        """
        result = {
            "started_tests": [],
            "completed_tests": [],
            "promotions": [],
            "discards": [],
        }

        if not self.somatic:
            return result

        for cell in self.somatic.cells:
            # 只处理候选状态的体细胞
            if cell.status != "candidate":
                continue

            ft = cell.forget_test
            phase = ft.get("test_phase", "idle")

            if phase == "idle":
                # 首次：设置移出时间
                if ft.get("withdraw_at_turn") is None:
                    ft["withdraw_at_turn"] = current_turn + self.WITHDRAW_DELAY
                    ft["test_phase"] = "injecting"
                    ft["test_cycles"] = ft.get("test_cycles", 0)

            elif phase == "injecting":
                # 检查是否该开始移出测试
                withdraw_at = ft.get("withdraw_at_turn", 0)
                if (current_turn >= withdraw_at 
                        and ft.get("test_cycles", 0) < self.MAX_TEST_CYCLES):
                    # 开始移出测试
                    ft["test_phase"] = "observing"
                    ft["observe_until_turn"] = current_turn + self.OBSERVE_TURNS
                    result["started_tests"].append({
                        "cell_id": cell.id,
                        "name": cell.name,
                        "cycle": ft.get("test_cycles", 0) + 1,
                    })

            elif phase == "observing":
                # 检查观察期是否结束
                observe_until = ft.get("observe_until_turn", 0)
                if current_turn >= observe_until:
                    # 观察期结束，进行回归检测
                    passed = self._detect_regression(cell, history)

                    # 记录测试结果（调用已有的record_forget_test）
                    self.somatic.record_forget_test(cell.id, passed)

                    ft["test_cycles"] = ft.get("test_cycles", 0) + 1
                    ft["last_test"] = datetime.now().isoformat()

                    # 重新获取cell（record_forget_test可能改变了状态）
                    cell_now = self.somatic._find(cell.id)
                    new_status = cell_now.status if cell_now else "unknown"

                    if new_status == "active":
                        ft["test_phase"] = "graduated"
                        result["promotions"].append({
                            "cell_id": cell.id,
                            "name": cell.name,
                            "passed_count": ft.get("passed", 0),
                            "cycles": ft.get("test_cycles", 0),
                        })
                    elif new_status == "discarded":
                        ft["test_phase"] = "discarded"
                        result["discards"].append({
                            "cell_id": cell.id,
                            "name": cell.name,
                            "failed_count": ft.get("failed", 0),
                            "cycles": ft.get("test_cycles", 0),
                        })
                    else:
                        # 未达阈值，恢复注入，等待下个周期
                        ft["test_phase"] = "injecting"
                        ft["withdraw_at_turn"] = current_turn + self.WITHDRAW_DELAY

                    result["completed_tests"].append({
                        "cell_id": cell.id,
                        "name": cell.name,
                        "passed": passed,
                        "total_passed": ft.get("passed", 0),
                        "total_failed": ft.get("failed", 0),
                        "new_status": new_status,
                    })

            # 超过最大测试周期仍 undecided → 强制转正
            if (ft.get("test_cycles", 0) >= self.MAX_TEST_CYCLES
                    and cell.status == "candidate"
                    and ft.get("test_phase") not in ("graduated", "discarded")):
                cell.status = "active"
                cell.last_activated = datetime.now().isoformat()
                ft["test_phase"] = "graduated"
                ft["forced"] = True
                self.somatic._save()
                result["promotions"].append({
                    "cell_id": cell.id,
                    "name": cell.name,
                    "passed_count": ft.get("passed", 0),
                    "cycles": ft.get("test_cycles", 0),
                    "forced": True,
                })

        return result

    def _detect_regression(self, cell, history: List[dict]) -> bool:
        """
        用LLM检测移出期间行为是否自发回归。
        
        如果没有LLM或分析失败，默认返回True（通过测试），避免误删。
        """
        if not self.llm or not history or len(history) < 2:
            return True

        # 取观察期间的对话（最近OBSERVE_TURNS*2条消息）
        recent = history[-(self.OBSERVE_TURNS * 2):]
        conv_text = "\n".join(
            f"{'用户' if m.get('role') == 'user' else '知乐'}: {m.get('content', '')}"
            for m in recent
        )

        prompt = f"""分析以下对话，判断知乐（AI角色）是否自发地表现出了特定行为。

要检测的行为：{cell.name}
行为描述：{cell.description}

最近对话：
{conv_text}

判定标准：
- "自发"意味着知乐在没有被明确指示的情况下自然表现出了这个行为
- 如果知乐的回复中体现了这个行为模式（语气/风格/措辞/习惯），即使只是轻微的，也算回归
- 如果对话中没有体现这个行为，或者行为完全消失，算未回归
- 排除用户主动引导导致的行为（如果是用户要求的，不算自发回归）

以JSON返回：
{{"regressed": true/false, "evidence": "对话中的具体证据（引用原话）", "confidence": 0.0-1.0}}

只返回JSON。"""

        messages = [
            {"role": "system", "content": "你是一个行为分析助手，只输出JSON。"},
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
            regressed = data.get("regressed", True)
            confidence = data.get("confidence", 0.5)

            # 低置信度时默认通过（宁可不误杀）
            if confidence < 0.3:
                return True

            return bool(regressed)
        except (json.JSONDecodeError, KeyError, Exception) as e:
            print(f"⚠ [遗忘测试] 回归检测失败: {e}", file=sys.stderr)
            return True  # 分析失败时默认通过

    def get_status(self) -> dict:
        """获取遗忘测试整体状态"""
        if not self.somatic:
            return {"enabled": False}

        testing = []
        for cell in self.somatic.cells:
            if cell.status != "candidate":
                continue
            ft = cell.forget_test
            phase = ft.get("test_phase", "idle")
            if phase in ("injecting", "observing"):
                testing.append({
                    "cell_id": cell.id,
                    "name": cell.name,
                    "phase": phase,
                    "passed": ft.get("passed", 0),
                    "failed": ft.get("failed", 0),
                    "cycles": ft.get("test_cycles", 0),
                    "max_cycles": self.MAX_TEST_CYCLES,
                })

        return {
            "enabled": True,
            "testing_count": len(testing),
            "testing_cells": testing,
            "withdraw_delay": self.WITHDRAW_DELAY,
            "observe_turns": self.OBSERVE_TURNS,
            "max_cycles": self.MAX_TEST_CYCLES,
        }
