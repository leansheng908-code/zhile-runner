#!/usr/bin/env python3
"""
知乐长在线思考系统 — P0.11 Layer 1：零token守护进程

纯Python后台线程，不调用任何LLM，定期执行"思考"的基础整理工作：
  - 记忆衰减计算
  - PSI压力监测
  - 时间感知
  - 生命体征(vitals)更新
  - 记忆索引维护
  - 成长候选扫描
  - 过期记忆检测
  - 实体图维护
  - 关系状态更新

运行频率：每30分钟一次（可配置）
Token成本：0
"""

import json
import threading
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List


class DaemonThinker:
    """后台守护进程 — 零token自主整理"""

    DEFAULT_INTERVAL = 1800  # 30分钟（秒）
    STALE_THRESHOLD_DAYS = 14  # 14天未触发的记忆标记为stale
    DECAY_RATE_PER_DAY = 0.05  # 每天衰减5%

    def __init__(self, core, interval: int = None,
                 enabled: bool = True):
        """
        Args:
            core: ZhileCore实例（访问memory/psi/entity_graph等）
            interval: 运行间隔（秒），默认1800（30分钟）
            enabled: 是否启用
        """
        self.core = core
        self.interval = interval or self.DEFAULT_INTERVAL
        self.enabled = enabled

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # 运行状态
        self._cycle_count = 0
        self._last_run: Optional[str] = None
        self._last_summary: Optional[dict] = None

        # vitals.json 路径
        mem_dir = Path(core.config.get("memory", {}).get("dir", "memory"))
        self.vitals_path = mem_dir / "vitals.json"
        self.vitals_path.parent.mkdir(parents=True, exist_ok=True)

    # ─── 生命周期 ─────────────────────────────

    def start(self):
        """启动守护线程"""
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="daemon-thinker"
        )
        self._thread.start()
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"🧠 [守护进程] 已启动，每{self.interval}秒执行一次（{ts}）",
              file=sys.stderr)

    def stop(self):
        """停止守护线程"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        """主循环"""
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                print(f"🧠 [守护进程] 异常: {e}", file=sys.stderr)
            # 等待间隔或停止信号
            self._stop_event.wait(self.interval)

    # ─── 核心循环 ─────────────────────────────

    def run_cycle(self) -> dict:
        """执行一次完整的整理周期"""
        with self._lock:
            self._cycle_count += 1
            now = datetime.now()
            ts = now.strftime("%Y-%m-%d %H:%M:%S")

            results = {}
            errors = []

            # 逐个执行整理任务
            tasks = [
                ("memory_decay", self._calculate_memory_decay),
                ("psi_pressure", self._check_psi_pressure),
                ("time_awareness", self._check_time_awareness),
                ("vitals", self._update_vitals),
                ("stale_memories", self._detect_stale_memories),
                ("memory_index", self._organize_memory_index),
                ("growth_candidates", self._scan_growth_candidates),
                ("entity_graph", self._maintain_entity_graph),
                ("relationship", self._update_relationship_state),
            ]

            for name, task in tasks:
                try:
                    results[name] = task()
                except Exception as e:
                    errors.append(f"{name}: {e}")
                    results[name] = {"error": str(e)}

            # ─── P0.29: 记忆编译 ──────────────────
            if hasattr(self.core, "memory_compiler") and self.core.memory_compiler:
                try:
                    if self.core.memory_compiler.should_compile(self.core._turn_count):
                        compile_result = self.core.memory_compiler.compile(
                            turn_count=self.core._turn_count)
                        results["memory_compile"] = compile_result
                except Exception as e:
                    errors.append(f"memory_compile: {e}")
                    results["memory_compile"] = {"error": str(e)}

                try:
                    if self.core.memory_compiler.should_lint():
                        lint_result = self.core.memory_compiler.lint()
                        results["memory_lint"] = lint_result
                except Exception as e:
                    errors.append(f"memory_lint: {e}")
                    results["memory_lint"] = {"error": str(e)}

            # ─── P0.13: 主动话题补充 ──────────────
            if hasattr(self.core, "topic_manager") and self.core.topic_manager:
                try:
                    if self.core.topic_manager.should_generate():
                        psi_ctx = ""
                        if self.core.psi:
                            psi_ctx = self.core.psi.get_context()
                        topic_result = self.core.topic_manager.generate(
                            psi_context=psi_ctx)
                        results["topic_generate"] = topic_result
                except Exception as e:
                    errors.append(f"topic_generate: {e}")
                    results["topic_generate"] = {"error": str(e)}

            # ─── Layer 2: 每日深度思考（微量token） ──
            if hasattr(self.core, "reflection_engine") and self.core.reflection_engine:
                try:
                    if self.core.reflection_engine.should_run():
                        ref_result = self.core.reflection_engine.run_reflection()
                        results["reflection"] = ref_result
                except Exception as e:
                    errors.append(f"reflection: {e}")
                    results["reflection"] = {"error": str(e)}

            # ─── Layer 3: PSI驱动按需思考 ──────────
            if hasattr(self.core, "psi_thinker") and self.core.psi_thinker:
                try:
                    psi_result = self.core.psi_thinker.check_and_trigger()
                    if psi_result:
                        results["psi_thinking"] = psi_result
                except Exception as e:
                    errors.append(f"psi_thinking: {e}")
                    results["psi_thinking"] = {"error": str(e)}

            # 汇总
            summary = {
                "cycle": self._cycle_count,
                "timestamp": ts,
                "results": results,
                "errors": errors if errors else None,
            }
            self._last_run = ts
            self._last_summary = summary

            # 打印简要日志
            err_str = f" ⚠{len(errors)}错误" if errors else ""
            print(f"🧠 [守护进程] 第{self._cycle_count}轮完成{err_str}（{ts}）",
                  file=sys.stderr)

            return summary

    # ─── 任务1: 记忆衰减计算 ──────────────────

    def _calculate_memory_decay(self) -> dict:
        """计算每条记忆的鲜活度，更新优先级"""
        if not self.core.memory:
            return {"skipped": "无记忆系统"}

        mems = self.core.memory.memories
        if not mems:
            return {"total": 0, "updated": 0}

        now = datetime.now()
        updated = 0
        decayed_list = []

        for m in mems:
            try:
                last = datetime.fromisoformat(m.last_triggered)
                days = (now - last).total_seconds() / 86400
                # 遗忘曲线：priority = importance × max(0.3, 1.0 - days × 0.05)
                decay_factor = max(0.3, 1.0 - days * self.DECAY_RATE_PER_DAY)
                effective_priority = m.importance * decay_factor

                if days > 3 and m.trigger_count > 0:
                    # 3天以上未触发的记忆，降低触发计数（缓慢淡忘）
                    m.trigger_count = max(0, m.trigger_count - 1)
                    updated += 1

                if effective_priority < 2.0:
                    decayed_list.append({
                        "id": m.id,
                        "content": m.content[:40],
                        "days": round(days, 1),
                        "effective": round(effective_priority, 2),
                    })
            except (ValueError, TypeError):
                continue

        return {
            "total": len(mems),
            "updated": updated,
            "decayed_below_2": len(decayed_list),
            "decay_details": decayed_list[:5],  # 只记前5条
        }

    # ─── 任务2: PSI压力监测 ───────────────────

    def _check_psi_pressure(self) -> dict:
        """监测PSI需求压力，记录异常"""
        if not self.core.psi:
            return {"skipped": "无PSI系统"}

        needs = self.core.psi.needs
        pressures = {}
        alerts = []

        for nid, need in needs.items():
            level = need.level
            pressures[nid] = round(level, 2)

            # 归属感压力高（很久没跟主人说话）
            if nid == "relatedness" and level < 2.0:
                alerts.append(f"归属感赤字({level:.1f})，可能想主人了")
            # 胜任感压力低（最近被纠正）
            elif nid == "competence" and level < 2.0:
                alerts.append(f"胜任感赤字({level:.1f})，可能需要复盘")
            # 能量极低
            elif nid == "energy" and level < 1.5:
                alerts.append(f"能量极低({level:.1f})，需要恢复")
            # 自主性压力高
            elif nid == "autonomy" and level > 4.5:
                alerts.append(f"自主性高涨({level:.1f})，可能想尝试新事物")

        # 计算上次互动到现在的时间
        last_interaction = self.core.psi.last_interaction
        gap_hours = 0
        if last_interaction:
            try:
                last = datetime.fromisoformat(last_interaction)
                gap_hours = (datetime.now() - last).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        return {
            "pressures": pressures,
            "baseline": round(self.core.psi._get_baseline(), 2),
            "gap_hours": round(gap_hours, 1),
            "alerts": alerts if alerts else None,
        }

    # ─── 任务3: 时间感知 ──────────────────────

    def _check_time_awareness(self) -> dict:
        """感知当前时间、该做什么"""
        now = datetime.now()
        hour = now.hour

        # 时辰
        shichen_map = {
            23: "子时", 0: "子时", 1: "丑时", 2: "丑时",
            3: "寅时", 4: "寅时", 5: "卯时", 6: "卯时",
            7: "辰时", 8: "辰时", 9: "巳时", 10: "巳时",
            11: "午时", 12: "午时", 13: "未时", 14: "未时",
            15: "申时", 16: "申时", 17: "酉时", 18: "酉时",
            19: "戌时", 20: "戌时", 21: "亥时", 22: "亥时",
        }
        shichen = shichen_map.get(hour, "?")

        # 时间段判断
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

        # 判断是否在主人工作时间（参考排班：值→待→休三段循环）
        # 这里只做时间感知，不做排班计算（排班是主对话的事）
        work_hint = ""
        if 8 <= hour < 17:
            work_hint = "可能是工作时间"
        elif hour >= 22 or hour < 6:
            work_hint = "主人可能休息了"

        return {
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%Y-%m-%d"),
            "weekday": ["一", "二", "三", "四", "五", "六", "日"][now.weekday()],
            "shichen": shichen,
            "period": period,
            "work_hint": work_hint or None,
        }

    # ─── 任务4: 更新vitals.json ───────────────

    def _update_vitals(self) -> dict:
        """更新生命体征文件，供网页版/观察者读取"""
        now = datetime.now()

        # 收集PSI数据
        psi_data = {}
        if self.core.psi:
            for nid, need in self.core.psi.needs.items():
                psi_data[nid] = {
                    "level": round(need.level, 2),
                    "status": need.status(),
                    "trend": need.trend,
                }

        # 收集记忆数据
        mem_stats = {}
        if self.core.memory:
            mem_stats = self.core.memory.get_stats()

        # 收集卦象数据
        hex_data = {}
        if self.core.hexagram_tracker and self.core._hex_state:
            cur = self.core._hex_state.get("current", {})
            hex_data = {
                "hexagram": cur.get("name", ""),
                "binary": cur.get("binary", ""),
                "update_count": self.core.hexagram_tracker.update_count,
            }

        # 收集成长数据
        growth_data = {}
        if self.core.somatic_cells:
            growth_data = self.core.somatic_cells.get_stats()

        vitals = {
            "timestamp": now.isoformat(),
            "cycle_count": self._cycle_count,
            "psi": psi_data,
            "psi_baseline": round(self.core.psi._get_baseline(), 2) if self.core.psi else None,
            "memory": {
                "active": mem_stats.get("active", 0),
                "total": mem_stats.get("total", 0),
            },
            "hexagram": hex_data,
            "growth": growth_data,
            "last_interaction": self.core.psi.last_interaction if self.core.psi else None,
        }

        try:
            with open(self.vitals_path, "w", encoding="utf-8") as f:
                json.dump(vitals, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return {"error": f"写入vitals失败: {e}"}

        return {"written": True, "path": str(self.vitals_path)}

    # ─── 任务5: 检测过期记忆 ──────────────────

    def _detect_stale_memories(self) -> dict:
        """发现需要巩固或可以淡化的记忆"""
        if not self.core.memory:
            return {"skipped": "无记忆系统"}

        mems = self.core.memory.memories
        if not mems:
            return {"total": 0}

        now = datetime.now()
        stale = []
        important_stale = []

        for m in mems:
            try:
                last = datetime.fromisoformat(m.last_triggered)
                days = (now - last).total_seconds() / 86400

                if days > self.STALE_THRESHOLD_DAYS:
                    if m.importance >= 7:
                        # 重要记忆过期 → 需要巩固
                        important_stale.append({
                            "id": m.id,
                            "content": m.content[:40],
                            "importance": m.importance,
                            "days": round(days, 1),
                        })
                    else:
                        # 不重要的过期记忆 → 可以淡化
                        stale.append({
                            "id": m.id,
                            "content": m.content[:40],
                            "importance": m.importance,
                            "days": round(days, 1),
                        })
            except (ValueError, TypeError):
                continue

        return {
            "total": len(mems),
            "stale_unimportant": len(stale),
            "stale_important": len(important_stale),
            "needs_consolidation": important_stale[:3],
            "can_fade": len(stale),
        }

    # ─── 任务6: 整理记忆索引 ──────────────────

    def _organize_memory_index(self) -> dict:
        """按时间/重要性排序，更新索引"""
        if not self.core.memory:
            return {"skipped": "无记忆系统"}

        mems = self.core.memory.memories
        if not mems:
            return {"total": 0}

        # 按有效优先级排序
        now = datetime.now()
        scored = []
        for m in mems:
            try:
                last = datetime.fromisoformat(m.last_triggered)
                days = (now - last).total_seconds() / 86400
                decay = max(0.3, 1.0 - days * self.DECAY_RATE_PER_DAY)
                effective = m.importance * decay
                scored.append((m, effective))
            except (ValueError, TypeError):
                scored.append((m, 0))

        scored.sort(key=lambda x: x[1], reverse=True)

        # 按维度统计
        dim_counts = {}
        for m in mems:
            dim = m.dimension or "recent"
            dim_counts[dim] = dim_counts.get(dim, 0) + 1

        # 按类别统计
        cat_counts = {}
        for m in mems:
            cat = m.category or "general"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        return {
            "total": len(mems),
            "by_dimension": dim_counts,
            "by_category": cat_counts,
            "top_priority": {
                "content": scored[0][0].content[:40] if scored else None,
                "effective_score": round(scored[0][1], 2) if scored else 0,
            } if scored else None,
        }

    # ─── 任务7: 扫描成长候选 ──────────────────

    def _scan_growth_candidates(self) -> dict:
        """检查workspace.md中是否有新的成长候选"""
        growth_dir = Path(self.core.config.get("growth", {}).get("dir", "memory/growth"))
        workspace_path = growth_dir / "workspace.md"

        if not workspace_path.exists():
            return {"skipped": "无workspace.md"}

        try:
            content = workspace_path.read_text(encoding="utf-8")
        except Exception:
            return {"error": "读取workspace.md失败"}

        # 统计候选数量（简单关键词匹配）
        candidates = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- [") and "候选" in line:
                candidates.append(line[:60])
            elif line.startswith("- [") and "观察" in line:
                candidates.append(line[:60])

        # 检查体细胞数量
        somatic_count = 0
        if self.core.somatic_cells:
            stats = self.core.somatic_cells.get_stats()
            somatic_count = stats.get("total", 0)

        return {
            "workspace_candidates": len(candidates),
            "candidates_preview": candidates[:3],
            "somatic_cells": somatic_count,
        }

    # ─── 任务8: 实体图维护 ────────────────────

    def _maintain_entity_graph(self) -> dict:
        """维护实体图，检查边权重"""
        if not self.core.entity_graph:
            return {"skipped": "无实体图"}

        stats = self.core.entity_graph.get_stats()
        entities = self.core.entity_graph.entities

        # 检查孤立实体（没有关联记忆的）
        isolated = 0
        low_link = 0
        for eid, entity in entities.items():
            linked = len(entity.linked_memories) if hasattr(entity, 'linked_memories') else 0
            if linked == 0:
                isolated += 1
            elif linked == 1:
                low_link += 1

        return {
            "total_entities": stats.get("total_entities", 0),
            "total_edges": stats.get("total_edges", 0),
            "isolated": isolated,
            "low_link": low_link,
        }

    # ─── 任务9: 关系状态更新 ──────────────────

    def _update_relationship_state(self) -> dict:
        """更新关系状态（主人锁定不衰减）"""
        now = datetime.now()

        # 计算上次互动到现在的时间
        gap_hours = 0
        if self.core.psi and self.core.psi.last_interaction:
            try:
                last = datetime.fromisoformat(self.core.psi.last_interaction)
                gap_hours = (now - last).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        # 判断关系活跃度
        if gap_hours < 1:
            activity = "active"
        elif gap_hours < 6:
            activity = "recent"
        elif gap_hours < 24:
            activity = "today"
        elif gap_hours < 72:
            activity = "distant"
        else:
            activity = "inactive"

        # 记忆中跟主人相关的高重要性记忆数量
        master_related = 0
        if self.core.memory:
            for m in self.core.memory.memories:
                if m.importance >= 7:
                    master_related += 1

        return {
            "activity": activity,
            "gap_hours": round(gap_hours, 1),
            "important_memories": master_related,
            "consciousness_frame": self.core.psi.consciousness_frame if self.core.psi else 0,
        }

    # ─── 查询接口 ─────────────────────────────

    def get_status(self) -> dict:
        """获取守护进程状态"""
        return {
            "enabled": self.enabled,
            "running": self._thread is not None and self._thread.is_alive(),
            "interval": self.interval,
            "cycle_count": self._cycle_count,
            "last_run": self._last_run,
            "last_summary": self._last_summary,
        }

    def get_vitals(self) -> dict:
        """读取最新的生命体征"""
        if not self.vitals_path.exists():
            return {}
        try:
            with open(self.vitals_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def run_once(self) -> dict:
        """手动触发一次（不等间隔），用于测试"""
        return self.run_cycle()
