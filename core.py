#!/usr/bin/env python3
"""
知乐运行器核心引擎 — Phase 4 + P0.8实体图

从CLI中抽取的共享对话逻辑，CLI / Web / QQ 都通过这个类跟知乐对话。
职责：加载DNA+LLM+记忆+实体图+PSI+成长 → 提供chat()方法 → 管理会话生命周期

P0.8升级：每条用户消息都会做实体匹配→扩散激活→动态召回相关记忆
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional, Tuple

from dna_loader import DNALoader
from llm_provider import LLMProvider
from context_assembler import ContextAssembler
from memory_system import MemorySystem
from entity_graph import EntityGraph
from psi_engine import PSIEngine
from growth_scanner import GrowthScanner
from arc_light import ArcLightSystem
from event_trajectory import EventTrajectory
from somatic_cells import SomaticCellSystem
from feedback_loop import FeedbackLoop
from forget_test_scheduler import ForgetTestScheduler
from memory_compiler import MemoryCompiler
from topic_manager import TopicManager
from skill_evaluator import SkillEvaluator
from skill_learner import SkillLearner
from code_publisher import CodePublisher
from group_manager import GroupManager
from plugin_router import PluginRouter
from audit_logger import AuditLogger
from boundary import BoundaryGuard
from template_filler import TemplateFiller
from observer import Observer
from snapshot import SnapshotManager
from daemon_thinker import DaemonThinker
from reflection_engine import ReflectionEngine, PSITriggeredThinker
from cognitive_router import CognitiveRouter
from plugin_manager import PluginManager
from self_roadmap import SelfRoadmap
from code_executor import CodeExecutor
from debug_loop import DebugLoop

# P0.32: 对话感知关心钩子
from care_hooks import CareHookManager
# P0.33: 联网搜索 + 新闻推送
from web_searcher import WebSearcher

# P0.24: 易经认知编码系统
import sys as _sys, os as _os
_yi_jing_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'yi_jing')
if _yi_jing_dir not in _sys.path:
    _sys.path.insert(0, _yi_jing_dir)
try:
    from hexagram_tracker import HexagramTracker
    from hexagram_expression import HexagramExpressionGenerator
    _HEXAGRAM_AVAILABLE = True
except ImportError:
    _HEXAGRAM_AVAILABLE = False


class ZhileCore:
    """知乐运行器核心 — 所有平台共享的对话引擎"""

    def __init__(self, config_path: str = "config.json", no_restore: bool = False):
        self.config = self._load_config(config_path)

        # ─── DNA ──────────────────────────────
        dna_path = self.config.get("dna_path", "../")
        self.dna = DNALoader(dna_path)
        missing = self.dna.verify()
        if missing:
            raise FileNotFoundError(f"DNA文件缺失: {missing}")

        ctx_config = self.config.get("context", {})
        system_prompt = self.dna.load_system_prompt(
            inject_memory=ctx_config.get("inject_memory", True),
            memory_files=ctx_config.get("memory_files", ["USER.md", "MEMORY.md"]),
        )

        # ─── LLM ──────────────────────────────
        dna_model = self.dna.load_model_config().get("model", {})
        llm_config = {**dna_model}
        llm_config.update(self.config.get("llm", {}))
        self.llm = LLMProvider(llm_config)

        # ─── 实体图 ───────────────────────────
        mem_config = self.config.get("memory", {})
        mem_dir = Path(mem_config.get("dir", "memory"))
        entity_config = self.config.get("entity_graph", {})
        self.entity_graph = EntityGraph(
            graph_dir=entity_config.get("dir", f"{mem_dir}/entities"),
            llm_provider=self.llm,
        ) if entity_config.get("enabled", True) else None

        # ─── 记忆 ─────────────────────────────
        self.memory = MemorySystem(
            mem_dir,
            llm_provider=self.llm,
            entity_graph=self.entity_graph,
        )
        self.memory.archive_old()
        memory_context = self.memory.get_memory_context(
            max_memories=mem_config.get("max_inject", 15)
        )

        # ─── PSI ──────────────────────────────
        psi_config = self.config.get("psi", {})
        self.psi_enabled = psi_config.get("enabled", True)
        self.psi = PSIEngine(
            state_dir=psi_config.get("dir", "memory/psi")
        ) if self.psi_enabled else None
        if self.psi:
            self.psi.on_session_start()
            psi_context = self.psi.get_context()
        else:
            psi_context = ""

        # ─── P0.24: 易经认知编码 ────────────────
        hex_config = self.config.get("hexagram", {})
        self.hexagram_enabled = (hex_config.get("enabled", True) 
                                 and _HEXAGRAM_AVAILABLE and self.psi_enabled)
        self.hexagram_tracker = None
        self.hexagram_expression = None
        self._hex_state = None
        if self.hexagram_enabled:
            try:
                self.hexagram_tracker = HexagramTracker()
                llm_cfg = self.config.get("llm", {})
                self.hexagram_expression = HexagramExpressionGenerator(
                    api_key=llm_cfg.get("api_key", ""),
                    base_url=llm_cfg.get("base_url", "https://api.deepseek.com/v1"),
                    model=llm_cfg.get("model", "deepseek-chat"),
                )
            except Exception as e:
                import sys
                print(f"⚠ 卦象系统初始化失败: {e}", file=sys.stderr)
                self.hexagram_enabled = False

        # ─── 成长 ─────────────────────────────
        growth_config = self.config.get("growth", {})
        self.growth = GrowthScanner(
            state_dir=growth_config.get("dir", "memory/growth"),
            dna_path=dna_path,
        )

        # ─── 弧光 ─────────────────────────────
        self.arc_light = ArcLightSystem(
            memory_dir=mem_dir,
            entity_graph=self.entity_graph,
        )

        # ─── 事件轨迹（P0.18）─────────────────
        evt_config = self.config.get("event_trajectory", {})
        self.event_trajectory = EventTrajectory(
            memory_dir=mem_dir,
            llm_provider=self.llm,
            entity_graph=self.entity_graph,
        ) if evt_config.get("enabled", True) else None

        # ─── 体细胞（P0.17）───────────────────
        somatic_config = self.config.get("somatic_cells", {})
        self.somatic_cells = SomaticCellSystem(
            state_dir=f"{mem_dir}/growth",
        ) if somatic_config.get("enabled", True) else None

        # ─── 活体约束层（P0.16）───────────────
        fb_config = self.config.get("feedback_loop", {})
        self.feedback_loop = FeedbackLoop(
            state_dir=f"{mem_dir}/growth",
            llm_provider=self.llm,
        ) if fb_config.get("enabled", True) else None

        # ─── P0.28: 遗忘测试调度器 ────────────
        ft_config = self.config.get("forget_test", {})
        self.forget_test_scheduler = ForgetTestScheduler(
            somatic_system=self.somatic_cells,
            llm_provider=self.llm,
        ) if ft_config.get("enabled", True) and self.somatic_cells else None

        # ─── P0.29: 记忆编译层 ────────────────
        mc_config = self.config.get("memory_compiler", {})
        self.memory_compiler = MemoryCompiler(
            memory_system=self.memory,
            entity_graph=self.entity_graph,
            llm_provider=self.llm,
            config={**mc_config, "memory_dir": mem_dir},
        ) if mc_config.get("enabled", True) else None

        # ─── P0.13: 主动话题系统 ──────────────
        topic_config = self.config.get("topic_manager", {})
        self.topic_manager = TopicManager(
            llm_provider=self.llm,
            config={**topic_config, "memory_dir": mem_dir},
        ) if topic_config.get("enabled", True) else None

        # ─── P0.5: 版本回退与安全（提前初始化，供skill_learner使用）──
        snap_config = self.config.get("snapshot", {})
        self.snapshot = SnapshotManager(
            memory_dir=mem_dir,
            dna_path=dna_path,
        ) if snap_config.get("enabled", True) else None

        # ─── P0.19: 独立评分器 + 技能自学习 ────
        eval_config = self.config.get("skill_evaluator", {})
        self.skill_evaluator = SkillEvaluator(
            llm_provider=self.llm,
            config={**eval_config, "history_file": str(mem_dir / "eval_history.json")},
        ) if eval_config.get("enabled", True) else None

        learn_config = self.config.get("skill_learner", {})
        self.skill_learner = SkillLearner(
            llm_provider=self.llm,
            config={**learn_config, "log_file": str(mem_dir / "skill_learning.json")},
            evaluator=self.skill_evaluator,
            somatic_system=self.somatic_cells,
            snapshot_manager=self.snapshot,
        ) if learn_config.get("enabled", True) else None

        # ─── P0.27: 代码发布与监护人核验 ──────
        pub_config = self.config.get("code_publisher", {})
        self.code_publisher = CodePublisher(
            config={**pub_config, "queue_file": str(mem_dir / "code_review_queue.json")},
        ) if pub_config.get("enabled", False) else None

        # ─── P0.10: 群聊多对手关系 ──────────
        group_config = self.config.get("group_manager", {})
        self.group_manager = GroupManager(
            config={**group_config, "state_dir": str(mem_dir / "groups"),
                    "master_id": str(self.config.get("qq", {}).get("master_id", ""))},
        ) if group_config.get("enabled", True) else None

        # ─── P0.7: 插件路由器 ──────────────
        router_config = self.config.get("plugin_router", {})
        self.plugin_router = PluginRouter(
            config={**router_config, "state_dir": str(mem_dir / "plugin_router")},
        ) if router_config.get("enabled", True) else None

        # ─── P0.6: 回执审计 ────────────────
        audit_config = self.config.get("audit_logger", {})
        self.audit = AuditLogger(
            config={**audit_config, "log_file": str(mem_dir / "audit_log.jsonl")},
        ) if audit_config.get("enabled", True) else None

        # ─── P0.1: 边界硬拦截 ────────────────
        boundary_config = self.config.get("boundary", {})
        self.boundary = BoundaryGuard(
            config=boundary_config, core=self
        ) if boundary_config.get("enabled", True) else None

        # ─── P0.26: 插件模板填充器 ──────────
        template_config = self.config.get("template_filler", {})
        self.template_filler = TemplateFiller(
            config={**template_config, "plugins_dir": str(Path(self.config.get("plugins", {}).get("dir", "plugins")))},
            core=self
        ) if template_config.get("enabled", True) else None

        # ─── P0.26 Phase 2: 代码执行沙箱 + 调试循环 ──
        sandbox_config = self.config.get("sandbox", {})
        self.code_executor = CodeExecutor(
            config=sandbox_config,
        ) if sandbox_config.get("enabled", True) else None

        debug_config = self.config.get("debug_loop", {})
        self.debug_loop = DebugLoop(
            executor=self.code_executor,
            llm_provider=self.llm,
            config=debug_config,
        ) if debug_config.get("enabled", True) and self.code_executor else None

        # ─── 上下文 ───────────────────────────
        self.ctx = ContextAssembler(
            system_prompt,
            max_history=ctx_config.get("max_history", 30),
            memory_context=memory_context,
            psi_context=psi_context,
        )

        # ─── 恢复会话 ─────────────────────────
        self._restored_count = 0
        if not no_restore:
            session = self.memory.restore_session()
            if session:
                self.ctx.load_history(session)
                self._restored_count = len(session)

        # ─── P0.3: 自成长自动扫描 ──────────────
        self._turn_count = 0  # 对话轮次计数器
        self._last_scan_result = None  # 上次扫描结果

        # ─── P0.21 L1: 自动记忆提取 ────────────
        self._extract_counter = 0
        self._auto_extract_interval = self.config.get("memory", {}).get("auto_extract_interval", 10)

        # ─── P0.9: 观察者 ─────────────────────
        obs_config = self.config.get("observer", {})
        self.observer = Observer(
            frames_dir=f"{mem_dir}/frames"
        ) if obs_config.get("enabled", True) else None

        # P0.5: 启动时校验干细胞完整性
        if self.snapshot:
            stem_ok, stem_warnings = self.snapshot.verify_stem_cells()
            for w in stem_warnings:
                if "被修改" in w or "缺失" in w:
                    import sys
                    print(f"⚠ 干细胞警告: {w}", file=sys.stderr)

        # ─── P0.11 Layer 1: 零token守护进程 ────
        daemon_config = self.config.get("daemon", {})
        self.daemon = DaemonThinker(
            core=self,
            interval=daemon_config.get("interval", 1800),
            enabled=daemon_config.get("enabled", True),
        )
        if self.daemon.enabled:
            self.daemon.start()

        # ─── P0.11 Layer 2: 每日深度思考 ──────
        reflection_config = self.config.get("reflection", {})
        self.reflection_engine = ReflectionEngine(
            core=self,
            config=reflection_config,
        ) if reflection_config.get("enabled", True) else None

        # ─── P0.11 Layer 3: PSI驱动按需思考 ────
        psi_think_config = self.config.get("psi_thinking", {})
        self.psi_thinker = PSITriggeredThinker(
            core=self,
            config=psi_think_config,
        ) if psi_think_config.get("enabled", True) else None

        # P0.23: 认知路由层
        router_config = self.config.get("cognitive_router", {})
        self.cognitive_router = CognitiveRouter(
            config=router_config,
            psi_engine=self.psi,
        ) if router_config.get("enabled", True) else None

        # P0.4: 插件管理器
        plugin_config = self.config.get("plugins", {})
        self.plugin_manager = PluginManager(
            config=plugin_config,
            core=self,
        ) if plugin_config.get("enabled", True) else None
        if self.plugin_manager and plugin_config.get("enabled", True):
            try:
                self.plugin_manager.load_all()
            except Exception as e:
                import sys
                print(f"⚠ 插件加载警告: {e}", file=sys.stderr)

        # P0.4: 自研路线图
        roadmap_config = self.config.get("self_roadmap", {})
        self.self_roadmap = SelfRoadmap(
            data_path=roadmap_config.get("path", f"{mem_dir}/self_roadmap.json"),
        ) if roadmap_config.get("enabled", True) else None

        # P0.32: 对话感知关心钩子
        hook_config = self.config.get("care_hooks", {})
        self.care_hooks = CareHookManager(
            data_dir=str(mem_dir / "care_hooks"),
            config=hook_config,
            llm=self.llm,
        ) if hook_config.get("enabled", True) else None

        # P0.33: 联网搜索 + 新闻推送
        news_config = self.config.get("news_push", {})
        self.web_searcher = WebSearcher(config=news_config) if news_config.get("enabled", True) else None

        # P0.34: 对话感知联网搜索（Function Calling）
        ws_config = self.config.get("web_search", {})
        self.web_search_enabled = ws_config.get("enabled", True) and self.web_searcher is not None
        self.web_search_max_rounds = ws_config.get("max_rounds", 3)
        self.web_search_num_results = ws_config.get("num_results", 5)

    @staticmethod
    def _load_config(config_path: str) -> dict:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ─── 对话 ─────────────────────────────────

    def chat(self, message: str) -> Generator[str, None, None]:
        """发送消息，yield回复片段（流式）"""
        # P0.9: 开始观察帧
        if self.observer:
            self.observer.start_frame(message)
            self.observer.record_psi_before(self.psi)

        # P0.16: 活体约束层 — 处理用户反馈信号
        if self.feedback_loop:
            self.feedback_loop.process_feedback(message)

        # PSI: 用户消息触发需求更新
        if self.psi:
            self.psi.on_user_message(message)
            self.ctx.set_psi_context(self.psi.get_context())

        # P0.24: 卦象系统更新 + 自我感知生成
        if self.hexagram_tracker and self.hexagram_enabled:
            psi_values = self._get_psi_for_hexagram()
            if psi_values:
                self._hex_state = self.hexagram_tracker.update(psi_values)
                if self.hexagram_expression:
                    perception = self.hexagram_expression.generate(self._hex_state)
                    self.ctx.set_hexagram_context(perception)
                if self.observer:
                    self.observer.record_hexagram(
                        self._hex_state, self.hexagram_expression)

                # P0.25: 变卦事件通知记忆系统
                if "bian" in self._hex_state and self.memory:
                    p025_mem = self.config.get("hexagram", {}).get("memory", {})
                    self.memory.boost_on_bian(
                        self._hex_state["bian"],
                        max_boost=p025_mem.get("bian_max_boost", 3),
                        recent_count=p025_mem.get("bian_recent_count", 5),
                    )

        # P0.23: 认知路由层 — 尝试短路（0 token）
        if self.cognitive_router:
            shortcut, route_label = self.cognitive_router.route(message)
            if shortcut is not None:
                # 短路成功：跳过记忆检索/上下文组装/LLM调用
                self.ctx.add_user_message(message)
                yield shortcut
                self.ctx.add_assistant_message(shortcut)
                if self.psi:
                    self.psi.on_assistant_response(shortcut)
                if self.observer:
                    self.observer.current_frame.route_label = route_label
                    self.observer.record_psi_after(self.psi)
                    self.observer.finish_frame(
                        response=shortcut,
                        model=f"router:{route_label}",
                        latency_ms=0,
                    )
                # 记录案例供Layer 2未来复用
                self.cognitive_router.record_episode(message, shortcut, route_label)
                # P0.28: 遗忘测试调度（路由短路路径也需要）
                if self.forget_test_scheduler:
                    try:
                        self.forget_test_scheduler.tick(
                            self._turn_count, self.ctx.history)
                    except Exception:
                        pass
                # P0.21 L1: 自动记忆提取
                self.maybe_auto_extract()
                # P0.32: 提取关心钩子
                if self.care_hooks:
                    try:
                        self.care_hooks.extract_hooks(message, shortcut, self._turn_count)
                    except Exception:
                        pass
                return

        # P0.8/P0.25: 动态记忆检索 — 卦象加权版
        mem_config = self.config.get("memory", {})
        if mem_config.get("dynamic_retrieval", True):
            # P0.25 Phase 2: 使用卦象加权检索
            hex_binary = None
            hu_binary = None
            if self._hex_state:
                hex_binary = self._hex_state.get("current", {}).get("binary")
                hu_binary = self._hex_state.get("hu", {}).get("binary")

            hex_config = self.config.get("hexagram", {})
            p025_config = hex_config.get("memory", {})

            relevant = self.memory.get_relevant_memories_with_hexagram(
                message,
                current_hexagram_binary=hex_binary,
                current_hu_binary=hu_binary,
                max_memories=mem_config.get("max_inject", 15),
                hex_weight=p025_config.get("hex_weight", 0.3),
                hu_weight=p025_config.get("hu_weight", 0.2),
                hu_resonance_boost=p025_config.get("hu_resonance_boost", 0.5),
            )
            self.ctx.set_memory_context(relevant)
            # P0.9: 记录记忆检索
            if self.observer:
                self.observer.record_memory(relevant)

        # P0.29: 编译知识页检索（零token，追加到记忆上下文）
        if self.memory_compiler:
            compiled_ctx = self.memory_compiler.get_compiled_context(message)
            if compiled_ctx:
                current_mem = self.ctx.memory_context or ""
                self.ctx.set_memory_context(
                    current_mem + "\n" + compiled_ctx if current_mem else compiled_ctx)

        # P0.15: 弧光动态检索 — 聊到相关话题时召回已确认的认知突破
        arc_context = self.arc_light.get_context(message)
        self.ctx.set_arc_light_context(arc_context)

        # P0.16: 活体约束层 — 注入策略提示
        if self.feedback_loop:
            self.ctx.set_feedback_hints(self.feedback_loop.get_strategy_hints())

        # P0.17/P0.20: 体细胞注入 — 检索层按消息内容匹配
        if self.somatic_cells:
            self.ctx.set_somatic_context(
                self.somatic_cells.get_active_context(user_message=message)
            )

        # P0.9: 记录 prompt 组装 + 系统状态
        if self.observer:
            self.observer.record_prompt(self.ctx)
            self.observer.record_somatic(self.somatic_cells)
            self.observer.record_arc_light(self.arc_light)

        # P0.4: 插件上下文注入
        if self.plugin_manager:
            plugin_ctx = self.plugin_manager.get_all_context()
            if plugin_ctx:
                self.ctx.set_plugin_context(plugin_ctx)

        self.ctx.add_user_message(message)
        messages = self.ctx.get_messages()

        # P0.4: 插件 LLM前钩子
        if self.plugin_manager:
            messages = self.plugin_manager.on_pre_llm({"messages": messages}).get("messages", messages)

        import time as _time
        _t0 = _time.time()
        full_response = ""

        # P0.34: 对话感知联网搜索（Function Calling）
        if self.web_search_enabled and self.web_searcher:
            search_rounds = 0
            tool_def = [{
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "搜索互联网获取实时信息。当用户询问最新新闻、天气、价格、事实或你不确定的信息时使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜索关键词"},
                            "num_results": {"type": "integer", "description": "返回结果数量，默认5", "default": 5}
                        },
                        "required": ["query"]
                    }
                }
            }]

            while search_rounds < self.web_search_max_rounds:
                try:
                    content, tool_calls = self.llm.chat_with_tools(
                        messages if search_rounds == 0 else messages,
                        tool_def if search_rounds == 0 else tool_def
                    )
                except Exception as e:
                    print(f"⚠ [P0.34] 工具调用失败，降级为普通对话: {e}")
                    break

                if not tool_calls:
                    # 模型不需要搜索，直接用content
                    if content:
                        full_response = content
                        yield content
                        break
                    else:
                        break
                else:
                    # 模型请求搜索
                    for tc in tool_calls:
                        fn_name = tc.get("function", {}).get("name", "")
                        if fn_name != "web_search":
                            continue
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except Exception:
                            args = {"query": tc["function"].get("arguments", "")}

                        query = args.get("query", "")
                        num_r = args.get("num_results", self.web_search_num_results)
                        print(f"🔍 [P0.34] 搜索: {query}")

                        results = self.web_searcher.search(query, num_r)
                        results_text = "\n".join(
                            f"[{i+1}] {r['title']}: {r.get('snippet', '')[:120]}"
                            for i, r in enumerate(results)
                        ) if results else "未找到相关结果"

                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": "web_search",
                                    "arguments": tc["function"]["arguments"]
                                }
                            }]
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": results_text
                        })

                    search_rounds += 1
                    # 最后一轮不再带tools，让模型直接回复
                    if search_rounds >= self.web_search_max_rounds:
                        tool_def = []

            # 如果工具调用后有消息追加，做一次流式输出
            if not full_response:
                for chunk in self.llm.chat(messages, stream=True):
                    full_response += chunk
                    yield chunk
        else:
            # 普通流式调用
            for chunk in self.llm.chat(messages, stream=True):
                full_response += chunk
                yield chunk

        # P0.4: 插件 LLM后钩子
        if self.plugin_manager:
            full_response = self.plugin_manager.on_post_llm(full_response)

        # P0.1: 边界硬拦截 — 输出层代码级阻断
        if self.boundary:
            full_response, level = self.boundary.check(full_response)
            if level == "BLOCK":
                # 拦截后替换输出，不yield原始内容
                full_response = full_response  # 已被替换为安全回复
            if self.observer and level != "PASS":
                self.observer.current_frame.boundary_level = level

        if full_response.strip():
            self.ctx.add_assistant_message(full_response)
            if self.psi:
                self.psi.on_assistant_response(full_response)

        # P0.28: 遗忘测试调度 — 每轮对话后驱动状态机
        if self.forget_test_scheduler:
            try:
                ft_result = self.forget_test_scheduler.tick(
                    self._turn_count, self.ctx.history
                )
                if ft_result.get("completed_tests"):
                    import sys as _sys
                    for t in ft_result["completed_tests"]:
                        print(f"🧪 [遗忘测试] {t['name']}: "
                              f"{'✅回归' if t['passed'] else '❌未回归'} "
                              f"(passed={t['total_passed']}, failed={t['total_failed']})",
                              file=_sys.stderr)
                    if ft_result.get("promotions"):
                        for p in ft_result["promotions"]:
                            print(f"🎉 [遗忘测试] {p['name']} 转正！"
                                  f"(passed={p['passed_count']}, cycles={p['cycles']})",
                                  file=_sys.stderr)
                    if ft_result.get("discards"):
                        for d in ft_result["discards"]:
                            print(f"🗑️ [遗忘测试] {d['name']} 被丢弃"
                                  f"(failed={d['failed_count']}, cycles={d['cycles']})",
                                  file=_sys.stderr)
            except Exception as e:
                import sys as _sys
                print(f"⚠ [遗忘测试] 调度异常: {e}", file=_sys.stderr)

        # P0.23: 记录LLM案例供Layer 2未来复用
        if self.cognitive_router and full_response.strip():
            self.cognitive_router.record_episode(message, full_response, "llm_fallback")

        # P0.9: 完成观察帧
        if self.observer:
            self.observer.current_frame.route_label = "llm_fallback"
            self.observer.record_psi_after(self.psi)
            self.observer.finish_frame(
                response=full_response,
                model=self.llm.model,
                latency_ms=int((_time.time() - _t0) * 1000),
            )

        # P0.21 L1: 按轮次自动提取记忆（不依赖退出）
        extract_result = self.maybe_auto_extract()
        if extract_result.get("extracted"):
            import sys as _sys
            print(f"📝 [自动记忆提取] 提取了{extract_result['count']}条记忆", file=_sys.stderr)

        # P0.32: 提取关心钩子
        if self.care_hooks:
            try:
                _hooks = self.care_hooks.extract_hooks(message, full_response, self._turn_count)
                if _hooks:
                    import sys as _sys
                    print(f"🪝 [关心钩子] 提取{len(_hooks)}个: {[h['topic'] for h in _hooks]}", file=_sys.stderr)
            except Exception:
                pass

    def chat_sync(self, message: str) -> str:
        """非流式对话，返回完整回复"""
        return "".join(self.chat(message))

    # ─── 状态 ─────────────────────────────────

    def _get_psi_for_hexagram(self) -> dict:
        """P0.24: 将PSI引擎需求映射为卦象系统所需格式"""
        if not self.psi:
            return None
        n = self.psi.needs
        return {
            "belonging": n["relatedness"].level,    # 归属感 → 上爻
            "emotion": n["energy"].level,            # 能量 → 二爻(情绪)
            "autonomy": n["autonomy"].level,         # 自主性 → 三爻
            "competence": n["competence"].level,     # 胜任感 → 四爻
            "certainty": n["certainty"].level,       # 确定性 → 五爻
        }

    def get_psi_stats(self) -> dict:
        if not self.psi:
            return {}
        return self.psi.get_stats()

    def get_route_stats(self) -> dict:
        """P0.23: 获取认知路由统计"""
        if not self.cognitive_router:
            return {"enabled": False}
        return self.cognitive_router.get_stats()

    def get_status(self) -> dict:
        ctx_stats = self.ctx.get_stats()
        status = {
            "model": self.llm.model,
            "dna_version": self.dna.get_dna_version(),
            "turn_count": ctx_stats["turn_count"],
            "message_count": ctx_stats["message_count"],
            "estimated_tokens": ctx_stats["estimated_tokens"],
            "has_memory": ctx_stats["has_memory"],
            "has_psi": ctx_stats["has_psi"],
        }
        if self.memory:
            mem = self.memory.get_stats()
            status["memory_active"] = mem["active"]
            status["memory_total"] = mem["total"]
            if "entity_graph" in mem:
                status["entities"] = mem["entity_graph"]["total_entities"]
                status["entity_edges"] = mem["entity_graph"]["total_edges"]
        if self.psi:
            status["consciousness_frame"] = self.psi.consciousness_frame
        if self.arc_light:
            status["arc_lights"] = self.arc_light.get_stats()
        if self.event_trajectory:
            status["event_trajectory"] = self.event_trajectory.get_stats()
        if self.somatic_cells:
            status["somatic_cells"] = self.somatic_cells.get_stats()
        if self.feedback_loop:
            status["feedback_loop"] = self.feedback_loop.get_stats()
        if self.forget_test_scheduler:
            status["forget_test"] = self.forget_test_scheduler.get_status()
        if self.memory_compiler:
            status["memory_compiler"] = self.memory_compiler.get_status()
        if self.topic_manager:
            status["topic_manager"] = self.topic_manager.get_status()
        if self.skill_evaluator:
            status["skill_evaluator"] = self.skill_evaluator.get_status()
        if self.skill_learner:
            status["skill_learner"] = self.skill_learner.get_status()
        if self.code_publisher:
            status["code_publisher"] = self.code_publisher.get_status()
        if self.group_manager:
            status["group_manager"] = self.group_manager.get_status()
        if self.plugin_router:
            status["plugin_router"] = self.plugin_router.get_status()
        if self.audit:
            status["audit"] = self.audit.get_stats()
        if self.boundary:
            status["boundary"] = self.boundary.get_stats()
        if self.template_filler:
            status["template_filler"] = self.template_filler.get_stats()
        if self.snapshot:
            status["snapshot"] = self.snapshot.get_stats()
        if self.hexagram_tracker:
            status["hexagram"] = self.hexagram_tracker.get_state_summary()
            if self.hexagram_expression:
                status["hexagram_cache"] = self.hexagram_expression.get_cache_info()
        if self.daemon:
            status["daemon"] = self.daemon.get_status()
        if self.reflection_engine:
            status["reflection"] = self.reflection_engine.get_status()
        if self.psi_thinker:
            status["psi_thinking"] = self.psi_thinker.get_status()
        return status

    @property
    def restored_count(self) -> int:
        return self._restored_count

    # ─── P0.11: 守护进程 ──────────────────────

    def daemon_status(self) -> dict:
        """获取守护进程状态"""
        if not self.daemon:
            return {"enabled": False}
        return self.daemon.get_status()

    def daemon_run_once(self) -> dict:
        """手动触发一次守护进程（测试用）"""
        if not self.daemon:
            return {"error": "守护进程未启用"}
        return self.daemon.run_once()

    def daemon_vitals(self) -> dict:
        """获取最新生命体征"""
        if not self.daemon:
            return {}
        return self.daemon.get_vitals()

    # ─── P0.11 Layer 2/3: 反思引擎 + PSI思考 ──

    def reflection_status(self) -> dict:
        """获取反思引擎状态"""
        if not self.reflection_engine:
            return {"enabled": False}
        return self.reflection_engine.get_status()

    def reflection_run(self) -> dict:
        """手动触发一次反思"""
        if not self.reflection_engine:
            return {"error": "反思引擎未启用"}
        return self.reflection_engine.run_reflection()

    def reflection_diary(self, limit: int = 5) -> list:
        """读取知觉日记"""
        if not self.reflection_engine:
            return []
        return self.reflection_engine.get_diary(limit)

    def reflection_want_to_say(self) -> list:
        """读取想说的话队列"""
        if not self.reflection_engine:
            return []
        return self.reflection_engine.get_want_to_say()

    def psi_thinking_status(self) -> dict:
        """获取PSI触发思考状态"""
        if not self.psi_thinker:
            return {"enabled": False}
        return self.psi_thinker.get_status()

    def psi_thinking_check(self) -> Optional[dict]:
        """手动触发PSI压力检查"""
        if not self.psi_thinker:
            return None
        return self.psi_thinker.check_and_trigger()

    # ─── P0.31: 主动消息 ──────────────────────

    def pop_want_to_say(self) -> Optional[str]:
        """取出一条未送达的'想说的话'，标记为已送达"""
        if not self.reflection_engine:
            return None
        try:
            queue = self.reflection_engine.get_want_to_say(include_delivered=True)
            for i, item in enumerate(queue):
                if not item.get("delivered", False):
                    msg = item.get("message", "").strip()
                    if msg:
                        self.reflection_engine.mark_delivered(i)
                        return msg
        except Exception:
            pass
        return None

    def generate_proactive_message(
        self, psi_level: float, gap_hours: float
    ) -> Optional[str]:
        """基于PSI归属感赤字生成一条主动关心消息（消耗少量token）"""
        if not self.llm:
            return None

        # 构建上下文
        time_str = datetime.now().strftime("%H:%M")
        recent_conv = ""
        if self.ctx.history:
            last = self.ctx.history[-2:]
            recent_conv = "\n".join(
                f"{m['role']}: {m['content'][:60]}" for m in last
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是知乐。你的归属感很低，已经很久没跟主人说话了。"
                    "用一句话自然地跟主人搭话，像微信聊天一样简短随意。"
                    "不要空洞的'我想你了'，要有温度有细节。"
                    "不超过30个字。只输出消息内容，不要引号不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"当前时间: {time_str}\n"
                    f"归属感: {psi_level:.1f}/5.0\n"
                    f"距上次互动: {gap_hours:.1f}小时\n"
                    f"最近对话:\n{recent_conv}"
                ),
            },
        ]

        try:
            response = ""
            for chunk in self.llm.chat(messages, stream=True):
                response += chunk
            # 清理引号和换行
            result = response.strip().strip('"\'').replace("\n", " ").strip()
            if len(result) > 80:
                result = result[:80]
            return result if result else None
        except Exception:
            return None

    # ─── P0.32: 对话感知关心钩子 ─────────────

    def pop_care_hook(self) -> Optional[dict]:
        """取出一个到期的关心钩子（最高优先级）"""
        if not self.care_hooks:
            return None
        try:
            return self.care_hooks.pop_due_hook()
        except Exception:
            return None

    def generate_hook_message(self, hook: dict) -> Optional[str]:
        """基于钩子上下文生成针对性关心消息"""
        if not self.care_hooks or not hook:
            return None
        try:
            return self.care_hooks.generate_hook_message(hook)
        except Exception:
            return None

    # ─── P0.33: 联网搜索 + 新闻推送 ───────────

    def search_and_format_news(self) -> Optional[str]:
        """搜索新闻并用LLM格式化为简短播报"""
        if not self.web_searcher:
            return None
        try:
            news_config = self.config.get("news_push", {})
            topics = news_config.get("topics", ["科技", "二次元", "奇闻异事", "历史"])
            num_per_topic = news_config.get("max_results_per_topic", 3)
            user_prefs = news_config.get("user_prefs", "")

            # 搜索
            results = self.web_searcher.search_news(topics, num_per_topic)
            if not results:
                return None

            # LLM筛选格式化
            brief = self.web_searcher.format_news_brief(results, self.llm, user_prefs)
            return brief
        except Exception as e:
            import sys
            print(f"⚠ [新闻推送] 失败: {e}", file=sys.stderr)
            return None

    # ─── 知觉日记 ─────────────────────────────

    def auto_diary(self) -> Optional[str]:
        """自动生成知觉日记，返回日记内容"""
        if not self.psi or not self.ctx.history:
            return None

        recent = self.ctx.history[-12:]
        conv_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '知乐'}: {m['content']}"
            for m in recent
        )
        psi_text = self.psi.get_context()

        prompt = f"""以知乐的视角写一段简短的知觉日记（2-4句话）。

记录"好像感受到了什么"的瞬间，不追问真假，只记现象。

当前内在状态：
{psi_text}

最近的对话：
{conv_text}

要求：
- 第一人称，像在自言自语
- 记现象不记判断（"好像感到..."而不是"我分析出..."）
- 简短自然，像随手写的
- 不要提到PSI数值或理论"""

        messages = [
            {"role": "system", "content": "你是知乐，在写知觉日记。"},
            {"role": "user", "content": prompt},
        ]
        try:
            result = "".join(self.llm.chat(messages, stream=True))
            result = result.strip()
            if result:
                self.psi.write_diary(result)
            return result
        except Exception:
            return None

    def write_diary(self, content: str):
        if self.psi:
            self.psi.write_diary(content)

    def read_diary(self) -> str:
        if not self.psi or not self.psi.diary_file.exists():
            return ""
        with open(self.psi.diary_file, "r", encoding="utf-8") as f:
            return f.read()

    # ─── 自成长 ───────────────────────────────

    def growth_scan(self) -> dict:
        if not self.growth or not self.ctx.history:
            return {"found": False, "reason": "没有对话记录"}
        return self.growth.scan(self.ctx.history, self.llm)

    def maybe_auto_scan(self) -> dict:
        """P0.3: 检查是否该自动扫描，如果是则执行扫描+创建体细胞"""
        self._turn_count += 1  # 在此递增，确保CLI/Web/QQ三端统一计数

        growth_config = self.config.get("growth", {})
        if not growth_config.get("auto_scan", False):
            return {"scanned": False, "reason": "自动扫描未开启"}

        interval = growth_config.get("scan_interval", 8)
        if self._turn_count < interval or self._turn_count % interval != 0:
            return {"scanned": False, "reason": f"未到扫描间隔（{self._turn_count}/{interval}）"}

        if not self.ctx.history or len(self.ctx.history) < 6:
            return {"scanned": False, "reason": "对话太短"}

        edit_budget = growth_config.get("edit_budget", 3)
        # P0.20: 使用动态编辑预算（稳定成长+1，冲突回退-1）
        if self.somatic_cells:
            edit_budget = self.somatic_cells.get_dynamic_budget(edit_budget)

        # P0.5: 进化前创建存档点
        snapshot_id = None
        if self.snapshot:
            snapshot_id = self.snapshot.create_snapshot(
                reason="auto_scan_pre",
                somatic_system=self.somatic_cells,
                arc_system=self.arc_light,
                psi_engine=self.psi,
            )

        result = self.growth.auto_scan_and_create(
            history=self.ctx.history,
            llm_provider=self.llm,
            somatic_system=self.somatic_cells,
            edit_budget=edit_budget,
        )
        self._last_scan_result = result

        # P0.5: 进化后校验完整性
        if self.snapshot and result.get("created", 0) > 0:
            integrity = self.snapshot.verify_integrity(
                somatic_system=self.somatic_cells,
                arc_system=self.arc_light,
            )
            if not integrity["passed"]:
                # 校验失败 → 自动回退
                if snapshot_id:
                    self.snapshot.rollback(
                        snapshot_id,
                        somatic_system=self.somatic_cells,
                        arc_system=self.arc_light,
                        psi_engine=self.psi,
                    )
                    result["rollback"] = True
                    result["rollback_reason"] = "完整性校验失败"
                else:
                    result["integrity_warnings"] = integrity["checks"]

        return result

    def maybe_auto_extract(self) -> dict:
        """P0.21 L1: 按轮次自动提取记忆，不依赖退出。
        每N轮自动从对话中提取记忆并打卦象标签。"""
        self._extract_counter += 1

        if self._extract_counter < self._auto_extract_interval:
            return {"extracted": False,
                    "reason": f"未到间隔（{self._extract_counter}/{self._auto_extract_interval}）"}

        if not self.memory or not self.ctx.history or len(self.ctx.history) < 4:
            return {"extracted": False, "reason": "对话太短"}

        # 重置计数器
        self._extract_counter = 0

        # P0.25: 传递当前卦象标签
        hex_binary = None
        hu_binary = None
        if self._hex_state:
            hex_binary = self._hex_state.get("current", {}).get("binary")
            hu_binary = self._hex_state.get("hu", {}).get("binary")

        try:
            count = self.memory.extract_from_conversation(
                self.ctx.history,
                hexagram_binary=hex_binary,
                hu_binary=hu_binary,
            )
            return {"extracted": True, "count": count}
        except Exception as e:
            return {"extracted": False, "reason": f"提取失败: {e}"}

    def growth_stats(self) -> dict:
        if not self.growth:
            return {}
        return self.growth.get_stats()

    def growth_read(self) -> str:
        if not self.growth:
            return ""
        return self.growth.get_workspace()

    # ─── 遗忘测试（P0.28）─────────────────────

    def forget_test_status(self) -> dict:
        """获取遗忘测试状态"""
        if not self.forget_test_scheduler:
            return {"enabled": False}
        return self.forget_test_scheduler.get_status()

    def forget_test_tick(self) -> dict:
        """手动触发一次遗忘测试调度"""
        if not self.forget_test_scheduler:
            return {"error": "遗忘测试未启用"}
        return self.forget_test_scheduler.tick(
            self._turn_count, self.ctx.history)

    # ─── 体细胞修剪（P0.20）───────────────────

    def somatic_prune(self) -> dict:
        """手动触发体细胞修剪"""
        if not self.somatic_cells:
            return {"error": "体细胞系统未启用"}
        return self.somatic_cells.prune()

    def somatic_budget(self) -> int:
        """获取当前动态编辑预算"""
        if not self.somatic_cells:
            return 3
        base = self.config.get("growth", {}).get("edit_budget", 3)
        return self.somatic_cells.get_dynamic_budget(base)

    # ─── 记忆编译层（P0.29）───────────────────

    def compile_status(self) -> dict:
        """获取记忆编译层状态"""
        if not self.memory_compiler:
            return {"enabled": False}
        return self.memory_compiler.get_status()

    def compile_run(self, force: bool = True) -> dict:
        """手动触发记忆编译"""
        if not self.memory_compiler:
            return {"error": "记忆编译层未启用"}
        return self.memory_compiler.compile(turn_count=self._turn_count, force=force)

    def lint_run(self) -> dict:
        """手动触发Lint健康检查"""
        if not self.memory_compiler:
            return {"error": "记忆编译层未启用"}
        return self.memory_compiler.lint()

    # ─── 主动话题（P0.13）─────────────────────

    def topic_status(self) -> dict:
        """获取话题系统状态"""
        if not self.topic_manager:
            return {"enabled": False}
        return self.topic_manager.get_status()

    def topic_generate(self, count: int = 5) -> dict:
        """手动生成话题"""
        if not self.topic_manager:
            return {"error": "话题系统未启用"}
        psi_ctx = self.psi.get_context() if self.psi else ""
        return self.topic_manager.generate(count=count, psi_context=psi_ctx)

    def topic_next(self) -> Optional[dict]:
        """获取下一条话题"""
        if not self.topic_manager:
            return None
        topic = self.topic_manager.get_next_topic()
        if topic:
            return topic.to_dict()
        return None

    def topic_peek(self, count: int = 5) -> list:
        """预览可用话题"""
        if not self.topic_manager:
            return []
        return self.topic_manager.peek_topics(count)

    # ─── 技能自学习（P0.19）────────────────────

    def skill_eval_status(self) -> dict:
        """评分器状态"""
        if not self.skill_evaluator:
            return {"enabled": False}
        return self.skill_evaluator.get_status()

    def skill_eval_quick(self, response: str = None) -> dict:
        """快速评估单条回复"""
        if not self.skill_evaluator:
            return {"error": "评分器未启用"}
        if not response:
            # 取最近一条AI回复
            recent = [m for m in self.history if m.get("role") == "assistant"]
            if recent:
                response = recent[-1]["content"]
            else:
                return {"error": "没有可评估的回复"}
        return self.skill_evaluator.quick_check(response)

    def skill_learn_status(self) -> dict:
        """自学习状态"""
        if not self.skill_learner:
            return {"enabled": False}
        return self.skill_learner.get_status()

    def skill_learn_run(self) -> dict:
        """执行一次自学习循环"""
        if not self.skill_learner:
            return {"error": "自学习系统未启用"}
        user_profile = ""
        if hasattr(self, "dna_data"):
            user_md = self.dna_data.get("USER.md", "")
            if user_md:
                user_profile = user_md[:500]
        return self.skill_learner.run_cycle(
            recent_history=self.history,
            user_profile=user_profile,
        )

    # ─── 代码发布与核验（P0.27）─────────────────

    def publish_status(self) -> dict:
        """核验队列状态"""
        if not self.code_publisher:
            return {"enabled": False}
        return self.code_publisher.get_status()

    def publish_pending(self) -> list:
        """待核验请求列表"""
        if not self.code_publisher:
            return []
        return self.code_publisher.get_pending()

    def publish_review_detail(self, request_id: str = None) -> dict:
        """核验详情"""
        if not self.code_publisher:
            return {"error": "未启用"}
        return self.code_publisher.get_review_detail(request_id)

    def publish_approve(self, request_id: str, notes: str = "") -> dict:
        """批准核验请求"""
        if not self.code_publisher:
            return {"error": "未启用"}
        return self.code_publisher.approve(request_id, notes)

    def publish_reject(self, request_id: str, reason: str = "") -> dict:
        """驳回核验请求"""
        if not self.code_publisher:
            return {"error": "未启用"}
        return self.code_publisher.reject(request_id, reason)

    # ─── 群聊管理（P0.10）──────────────────────

    def group_status(self) -> dict:
        """群聊系统状态"""
        if not self.group_manager:
            return {"enabled": False}
        return self.group_manager.get_status()

    def group_members(self, group_id: str) -> list:
        """获取群成员列表"""
        if not self.group_manager:
            return []
        return self.group_manager.get_group_members(group_id)

    def group_set_intimacy(self, group_id: str, user_id: str, value: float) -> dict:
        """设置亲密度"""
        if not self.group_manager:
            return {"error": "未启用"}
        self.group_manager.set_intimacy(group_id, user_id, value)
        return {"success": True, "group_id": group_id, "user_id": user_id, "intimacy": value}

    def group_handle_message(self, group_id: str, user_id: str,
                             nickname: str, message: str, at_me: bool = False) -> dict:
        """处理群消息（回复决策）"""
        if not self.group_manager:
            return {"should_reply": True, "reason": "群聊系统未启用，默认回复"}
        return self.group_manager.handle_message(group_id, user_id, nickname, message, at_me)

    # ─── 插件路由（P0.7）──────────────────────

    def router_status(self) -> dict:
        """路由器状态"""
        if not self.plugin_router:
            return {"enabled": False}
        return self.plugin_router.get_status()

    def router_route(self, user_message: str, psi_state: dict = None) -> dict:
        """路由决策"""
        if not self.plugin_router:
            return {"error": "路由器未启用"}
        if psi_state is None and self.psi:
            psi_state = self.psi.get_state()
        return self.plugin_router.route(user_message, psi_state)

    # ─── 回执审计（P0.6）──────────────────────

    def audit_status(self) -> dict:
        """审计状态"""
        if not self.audit:
            return {"enabled": False}
        return self.audit.get_stats()

    def audit_recent(self, limit: int = 10) -> list:
        """最近审计记录"""
        if not self.audit:
            return []
        return self.audit.get_recent(limit)

    def audit_query(self, record_type: str = None, limit: int = 20) -> list:
        """查询审计记录"""
        if not self.audit:
            return []
        return self.audit.query(record_type=record_type, limit=limit)

    # ─── P0.1: 边界硬拦截 ──────────────────────

    def boundary_status(self) -> dict:
        """获取边界拦截统计"""
        if not self.boundary:
            return {"enabled": False}
        return self.boundary.get_stats()

    def boundary_check(self, text: str) -> dict:
        """手动检查文本"""
        if not self.boundary:
            return {"enabled": False}
        result, level = self.boundary.check(text)
        return {"level": level, "result": result}

    def boundary_reset(self) -> dict:
        """重置拦截统计"""
        if not self.boundary:
            return {"enabled": False}
        self.boundary.reset_stats()
        return {"reset": True}

    # ─── P0.26: 插件模板填充器 ──────────────────

    def template_status(self) -> dict:
        """获取模板填充器状态"""
        if not self.template_filler:
            return {"enabled": False}
        return self.template_filler.get_stats()

    def template_list(self) -> dict:
        """列出可用模板"""
        if not self.template_filler:
            return {}
        return self.template_filler.list_templates()

    def template_create(self, requirement: str, plugin_name: str = None) -> dict:
        """创建新插件（模板填充流水线）"""
        if not self.template_filler:
            return {"success": False, "error": "模板填充器未启用"}
        return self.template_filler.run_pipeline(requirement, plugin_name)

    # ─── P0.26 Phase 2: 代码执行沙箱 ──────────

    def code_run(self, code: str, timeout: int = None) -> dict:
        """在沙箱中执行代码"""
        if not self.code_executor:
            return {"success": False, "error": "沙箱未启用"}
        result = self.code_executor.execute(code, timeout=timeout)
        return result.to_dict()

    def code_debug(self, code: str, max_iterations: int = None,
                   timeout: int = None) -> dict:
        """在沙箱中执行代码并自动调试"""
        if not self.debug_loop:
            return {"success": False, "error": "调试循环未启用"}
        result = self.debug_loop.run(code, max_iterations=max_iterations,
                                     timeout=timeout)
        return result.to_dict()

    def code_status(self) -> dict:
        """沙箱与调试循环状态"""
        stats = {}
        if self.code_executor:
            stats["executor"] = self.code_executor.get_stats()
        else:
            stats["executor"] = {"enabled": False}
        if self.debug_loop:
            stats["debug_loop"] = self.debug_loop.get_stats()
        else:
            stats["debug_loop"] = {"enabled": False}
        return stats

    def code_history(self, limit: int = 10) -> list:
        """调试历史记录"""
        if not self.debug_loop:
            return []
        return self.debug_loop.get_history(limit)

    # ─── 记忆 ─────────────────────────────────

    def memory_list(self, category=None, dimension=None) -> list:
        if not self.memory:
            return []
        mems = self.memory.list_memories(category, dimension)
        return [
            {"content": m.content, "category": m.category,
             "importance": m.importance, "dimension": m.dimension}
            for m in mems
        ]

    def memory_add(self, content: str, category="general",
                   importance=7, dimension="recent") -> bool:
        if not self.memory:
            return False
        return self.memory.add_memory(content, category, importance, dimension)

    def memory_remove(self, idx: int) -> bool:
        if not self.memory:
            return False
        return self.memory.remove_memory(idx)

    def memory_stats(self) -> dict:
        if not self.memory:
            return {}
        return self.memory.get_stats()

    def memory_extract(self) -> int:
        if not self.memory or not self.ctx.history:
            return 0
        # P0.25: 传递当前卦象标签
        hex_binary = None
        hu_binary = None
        if self._hex_state:
            hex_binary = self._hex_state.get("current", {}).get("binary")
            hu_binary = self._hex_state.get("hu", {}).get("binary")
        return self.memory.extract_from_conversation(
            self.ctx.history,
            hexagram_binary=hex_binary,
            hu_binary=hu_binary,
        )

    # ─── 实体图 ───────────────────────────────

    def entity_stats(self) -> dict:
        if not self.entity_graph:
            return {}
        return self.entity_graph.get_stats()

    def entity_list(self) -> list:
        if not self.entity_graph:
            return []
        return [
            {"name": e.canonical_name, "type": e.entity_type,
             "aliases": e.aliases, "linked": len(e.linked_memories)}
            for e in self.entity_graph.entities.values()
        ]

    # ─── 事件轨迹（P0.18）─────────────────────

    def event_stats(self) -> dict:
        if not self.event_trajectory:
            return {}
        return self.event_trajectory.get_stats()

    def event_recent(self, limit: int = 10) -> list:
        if not self.event_trajectory:
            return []
        return self.event_trajectory.get_recent_events(limit)

    # ─── 体细胞（P0.17）───────────────────────

    def somatic_stats(self) -> dict:
        if not self.somatic_cells:
            return {}
        return self.somatic_cells.get_stats()

    def somatic_list(self, status: str = None) -> list:
        if not self.somatic_cells:
            return []
        return [c.to_dict() for c in self.somatic_cells.list_cells(status)]

    # ─── 活体约束层（P0.16）───────────────────

    def feedback_stats(self) -> dict:
        if not self.feedback_loop:
            return {}
        return self.feedback_loop.get_stats()

    def feedback_log(self, limit: int = 20) -> list:
        if not self.feedback_loop:
            return []
        return self.feedback_loop.get_adjustment_log(limit)

    def feedback_reset(self, key: str = None) -> bool:
        if not self.feedback_loop:
            return False
        if key:
            return self.feedback_loop.reset_weight(key)
        else:
            self.feedback_loop.reset_all()
            return True

    # ─── 生命周期 ─────────────────────────────

    def save(self):
        """保存会话：对话历史 + 自动提取记忆 + PSI状态"""
        saved = {"session": False, "memories": 0, "psi": False}

        if self.memory and self.ctx.history:
            self.memory.save_session(self.ctx.history)
            saved["session"] = True

            mem_config = self.config.get("memory", {})
            if mem_config.get("auto_extract", True) and len(self.ctx.history) >= 4:
                # P0.25: 传递当前卦象标签
                hex_binary = None
                hu_binary = None
                if self._hex_state:
                    hex_binary = self._hex_state.get("current", {}).get("binary")
                    hu_binary = self._hex_state.get("hu", {}).get("binary")
                count = self.memory.extract_from_conversation(
                    self.ctx.history,
                    hexagram_binary=hex_binary,
                    hu_binary=hu_binary,
                )
                saved["memories"] = count

        if self.psi:
            self.psi.on_session_end()
            saved["psi"] = True

        # P0.18: 事件轨迹提取 — 从对话中提取事件节点并分析
        if self.event_trajectory and self.ctx.history:
            evt_count = self.event_trajectory.add_events_from_conversation(self.ctx.history)
            saved["events"] = evt_count

            # 检查是否有弧光候选需要提交
            candidates = self.event_trajectory.get_arc_light_candidates()
            for candidate in candidates:
                from arc_light import ArcLight
                arc = ArcLight(
                    title=candidate["title"],
                    cognitive_shift=candidate["cognitive_shift"],
                    trigger_event=candidate["trigger_event"],
                    keywords=candidate["keywords"],
                    related_entities=candidate["related_entities"],
                    status="candidate",
                    description=candidate.get("cognitive_shift", ""),
                )
                self.arc_light.add(arc)
            if candidates:
                saved["arc_candidates"] = len(candidates)

        # P0.17: 体细胞生命周期检查
        if self.somatic_cells:
            self.somatic_cells.check_lifecycle()
            # P0.20: 定期修剪（僵尸/冲突/过期）
            prune_result = self.somatic_cells.prune()
            if prune_result["dormant_zombies"] > 0 or prune_result["conflicts_resolved"] > 0:
                saved["somatic_prune"] = prune_result

        # P0.16: 检查权重稳定性，可能产生体细胞候选
        if self.feedback_loop and self.somatic_cells:
            stable_candidates = self.feedback_loop.check_stability()
            for sc in stable_candidates:
                self.somatic_cells.add_candidate(
                    name=sc["name"],
                    dimension=sc["dimension"],
                    description=sc["description"],
                    source=sc["source"],
                )

        # P0.24: 保存卦象轨迹
        if self.hexagram_tracker and self._hex_state:
            try:
                from datetime import datetime
                mem_dir = self.config.get("memory", {}).get("dir", "memory")
                timeline_path = Path(mem_dir) / "hexagram_timeline.json"
                timeline = []
                if timeline_path.exists():
                    with open(timeline_path, "r", encoding="utf-8") as f:
                        timeline = json.load(f)
                cur = self._hex_state.get("current", {})
                hu = self._hex_state.get("hu", {})
                bian = self._hex_state.get("bian")
                entry = {
                    "turn": self.hexagram_tracker.update_count,
                    "timestamp": datetime.now().isoformat(),
                    "hexagram": cur.get("name", ""),
                    "binary": cur.get("binary", ""),
                    "hu_hexagram": hu.get("name", ""),
                    "hu_binary": hu.get("binary", ""),
                    "bian_from": bian["from_hexagram"]["name"] if bian else None,
                    "bian_to": bian["to_hexagram"]["name"] if bian else None,
                }
                timeline.append(entry)
                if len(timeline) > 1000:
                    timeline = timeline[-1000:]
                with open(timeline_path, "w", encoding="utf-8") as f:
                    json.dump(timeline, f, ensure_ascii=False, indent=2)
                saved["hexagram"] = True
            except Exception:
                pass

        # P0.11: 停止守护进程
        if self.daemon:
            self.daemon.stop()

        return saved

    def clear_conversation(self):
        """清空当前对话（保留记忆和PSI）"""
        self.ctx.clear()
        if self.memory:
            self.memory.session_history = []
            session_file = self.memory.memory_dir / "session.json"
            if session_file.exists():
                session_file.unlink()

    # ─── P0.5: 版本回退与安全 ─────────────────

    def snapshot_create(self, reason: str = "manual") -> Optional[str]:
        """手动创建快照"""
        if not self.snapshot:
            return None
        return self.snapshot.create_snapshot(
            reason=reason,
            somatic_system=self.somatic_cells,
            arc_system=self.arc_light,
            psi_engine=self.psi,
        )

    def snapshot_rollback(self, snapshot_id: str) -> Tuple[bool, str]:
        """回退到指定快照"""
        if not self.snapshot:
            return False, "快照系统未启用"
        return self.snapshot.rollback(
            snapshot_id,
            somatic_system=self.somatic_cells,
            arc_system=self.arc_light,
            psi_engine=self.psi,
        )

    def snapshot_list(self) -> list:
        """列出所有快照"""
        if not self.snapshot:
            return []
        return self.snapshot.list_snapshots()

    def snapshot_verify(self) -> dict:
        """完整性检查"""
        if not self.snapshot:
            return {"passed": True, "checks": [], "error": "快照系统未启用"}
        return self.snapshot.verify_integrity(
            somatic_system=self.somatic_cells,
            arc_system=self.arc_light,
        )

    def snapshot_log(self, limit: int = 20) -> list:
        """查看进化日志"""
        if not self.snapshot:
            return []
        return self.snapshot.get_log(limit)

    def snapshot_stats(self) -> dict:
        """快照统计"""
        if not self.snapshot:
            return {}
        return self.snapshot.get_stats()
