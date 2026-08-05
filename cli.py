"""
命令行界面 — 终端聊天

Phase 3 新增：
  - 每轮对话后更新PSI状态
  - /psi 查看内在状态
  - /diary 写知觉日记
  - /growth 扫描自成长候选
  - 退出时保存PSI状态

特性：
  - 流式输出（逐字打印）
  - ANSI彩色输出
  - /help /status /memory /psi /diary /growth /clear /forget /save /test /exit
"""

import sys
import json
from datetime import datetime
from nl_scheduler import CronParser


class Color:
    CYAN = "\033[96m"
    PINK = "\033[95m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class CLI:
    def __init__(self, dna_loader, llm_provider, context_assembler, config,
                 memory_system=None, psi_engine=None, growth_scanner=None,
                 entity_graph=None, core=None):
        self.dna = dna_loader
        self.llm = llm_provider
        self.ctx = context_assembler
        self.config = config
        self.memory = memory_system
        self.psi = psi_engine
        self.growth = growth_scanner
        self.entity_graph = entity_graph
        self.core = core
        self.running = False

    def run(self):
        self.running = True
        self._print_welcome()
        self._test_connection(silent=False)

        # P0.36: CLI模式后台任务
        if self.core:
            self._start_bg_threads()

        while self.running:
            try:
                user_input = input(
                    f"\n{Color.CYAN}你>{Color.RESET} "
                ).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                self._chat(user_input)

            except KeyboardInterrupt:
                print(f"\n{Color.DIM}（输入 /exit 退出）{Color.RESET}")
            except EOFError:
                self._exit()

    def _chat(self, user_input: str):
        """处理一轮对话"""
        import time as _time
        _t0 = _time.time()

        # P0.9: 开始观察帧
        observer = self.core.observer if self.core else None
        if observer:
            observer.start_frame(user_input)
            observer.record_psi_before(self.psi)

        # PSI: 用户消息触发需求更新
        if self.psi:
            self.psi.on_user_message(user_input)
            self.ctx.set_psi_context(self.psi.get_context())

        # P0.24: 卦象系统更新 + 自我感知生成（与QQ模式统一，时间起卦）
        if self.core and self.core.hexagram_tracker and self.core.hexagram_enabled:
            self.core._hex_state = self.core.hexagram_tracker.update_by_time()
            if self.core.hexagram_expression:
                perception = self.core.hexagram_expression.generate(self.core._hex_state)
                self.ctx.set_hexagram_context(perception)
            if observer:
                observer.record_hexagram(
                    self.core._hex_state, self.core.hexagram_expression)

        # P0.8/P0.42: 动态记忆检索 — 多策略共振版（与core.py统一）
        mem_config = self.config.get("memory", {})
        if mem_config.get("dynamic_retrieval", True) and self.memory:
            use_resonance = mem_config.get("use_resonance_engine", True)
            if use_resonance:
                try:
                    from resonance_engine import ResonanceEngine
                    from datetime import datetime as _dt
                    _engine = ResonanceEngine()
                    _now = _dt.now()
                    _snapshot = _engine.extract_compact_snapshot(
                        _engine.generate_snapshot(_now.year, _now.month, _now.day, _now.hour, _now.minute)
                    )
                    relevant = self.memory.get_relevant_memories_with_resonance(
                        user_input,
                        current_snapshot=_snapshot,
                        max_memories=mem_config.get("max_inject", 15),
                    )
                    self.ctx.set_memory_context(relevant)
                    if observer:
                        observer.record_memory(relevant)
                except Exception:
                    use_resonance = False  # 回退到旧版

            if not use_resonance:
                relevant = self.memory.get_relevant_memories(
                    user_input,
                    max_memories=mem_config.get("max_inject", 15),
                )
                self.ctx.set_memory_context(relevant)
                if observer:
                    observer.record_memory(relevant)

            # P0.47: 瞬时感知·一期一会 — 记忆共振产生一次性感受，注入后即弃
            if self.core and self.core.fleeting_moment:
                try:
                    if use_resonance and relevant:
                        hex_info = (self.core._hex_state.get("current", {})
                                    if self.core._hex_state else None)
                        fm_result = self.core.fleeting_moment.generate(
                            getattr(self.core.memory, '_last_top_memories', []),
                            hexagram_info=hex_info)
                        if fm_result:
                            self.ctx.set_fleeting_moment(fm_result['descriptor'])
                except (NameError, Exception):
                    pass  # 瞬时感知失败不影响对话

        # P0.9: 记录弧光+体细胞+prompt
        if observer:
            if self.core and self.core.arc_light:
                arc_ctx = self.core.arc_light.get_context(user_input)
                self.ctx.set_arc_light_context(arc_ctx)
                observer.record_arc_light(self.core.arc_light)
            if self.core and self.core.somatic_cells:
                self.ctx.set_somatic_context(self.core.somatic_cells.get_active_context())
                observer.record_somatic(self.core.somatic_cells)
            observer.record_prompt(self.ctx)

        self.ctx.add_user_message(user_input)

        # P0.23: 认知路由层 — 尝试短路（LLM调用前）
        if self.core and self.core.cognitive_router:
            shortcut, route_label = self.core.cognitive_router.route(user_input)
            if shortcut is not None:
                # 短路成功：0 token，直接输出
                print(f"\n{Color.PINK}知乐>{Color.RESET} {shortcut}\n")
                full_response = shortcut
                self.ctx.add_assistant_message(full_response)
                if self.psi:
                    self.psi.on_assistant_response(full_response)
                # 成长扫描
                if self.core:
                    self.core.maybe_auto_scan()
                # 观察帧完成
                if observer:
                    observer.record_growth(False, 0, 0)
                    observer.record_psi_after(self.psi)
                    observer.current_frame.route_label = route_label
                    observer.finish_frame(
                        response=full_response,
                        model="shortcut",
                        latency_ms=int((_time.time() - _t0) * 1000),
                    )
                # 自动记忆提取
                if self.core:
                    self.core.maybe_auto_extract()
                # P0.47: 瞬时感知消散——一期一会，只存在于这一次
                if self.core and self.core.fleeting_moment:
                    self.ctx.clear_fleeting_moment()
                return

        messages = self.ctx.get_messages()

        print(f"\n{Color.PINK}知乐>{Color.RESET} ", end="", flush=True)

        full_response = ""
        try:
            for chunk in self.llm.chat(messages, stream=True):
                print(chunk, end="", flush=True)
                full_response += chunk

            print()

            if full_response.strip():
                self.ctx.add_assistant_message(full_response)
                if self.psi:
                    self.psi.on_assistant_response(full_response)
            else:
                print(f"{Color.DIM}（空回复）{Color.RESET}")

            # P0.47: 瞬时感知消散——一期一会，只存在于这一次
            if self.core and self.core.fleeting_moment:
                self.ctx.clear_fleeting_moment()

            # P0.23: LLM路径标记 + 情景库录入
            route_label = "llm_fallback"
            if self.core and self.core.cognitive_router:
                self.core.cognitive_router.record_episode(user_input, full_response, route_label)

            # P0.3: 自动成长扫描
            growth_scanned = False
            growth_candidates = 0
            growth_created = 0
            if self.core:
                scan_result = self.core.maybe_auto_scan()
                if scan_result.get("scanned"):
                    growth_scanned = True
                    growth_candidates = scan_result.get("total_candidates", 0)
                    growth_created = scan_result.get("created", 0)
                    if growth_created > 0:
                        print(f"\n{Color.DIM}✦ 自成长扫描：发现{growth_candidates}个候选，"
                              f"创建{growth_created}条体细胞{Color.RESET}")

            # P0.9: 完成观察帧
            if observer:
                observer.record_growth(growth_scanned, growth_candidates, growth_created)
                observer.record_psi_after(self.psi)
                observer.current_frame.route_label = route_label
                observer.finish_frame(
                    response=full_response,
                    model=self.llm.model,
                    latency_ms=int((_time.time() - _t0) * 1000),
                )

            # P0.21 L1: 按轮次自动提取记忆
            if self.core:
                extract_result = self.core.maybe_auto_extract()
                if extract_result.get("extracted"):
                    print(f"\n{Color.DIM}📝 [自动记忆提取] 提取了{extract_result['count']}条记忆{Color.RESET}")

        except Exception as e:
            print(f"\n{Color.RED}⚠ {e}{Color.RESET}")
            # P0.47: 异常时也要清空瞬时感知
            if self.core and self.core.fleeting_moment:
                self.ctx.clear_fleeting_moment()

    def _handle_command(self, cmd: str):
        parts = cmd.lower().strip().split(maxsplit=2)
        main_cmd = parts[0]

        if main_cmd in ("/exit", "/quit", "/q"):
            self._exit()
        elif main_cmd == "/clear":
            self.ctx.clear()
            print(f"{Color.YELLOW}✦ 对话历史已清空（记忆和PSI保留）{Color.RESET}")
        elif main_cmd == "/forget":
            self._forget_session()
        elif main_cmd == "/status":
            self._print_status()
        elif main_cmd == "/save":
            self._save_conversation()
        elif main_cmd == "/memory":
            self._handle_memory(parts)
        elif main_cmd == "/psi":
            self._print_psi()
        elif main_cmd == "/diary":
            self._handle_diary(parts)
        elif main_cmd == "/growth":
            self._handle_growth(parts)
        elif main_cmd == "/entities":
            self._print_entities()
        elif main_cmd == "/events":
            self._print_events()
        elif main_cmd == "/cells":
            self._print_cells()
        elif main_cmd == "/feedback":
            self._print_feedback()
        elif main_cmd in ("/observe", "/obs"):
            self._handle_observe(parts)
        elif main_cmd in ("/snapshot", "/snap"):
            self._handle_snapshot(parts)
        elif main_cmd == "/daemon":
            self._handle_daemon(parts)
        elif main_cmd == "/reflect":
            self._handle_reflect(parts)
        elif main_cmd == "/route":
            self._handle_route(parts)
        elif main_cmd == "/plugin":
            self._handle_plugin(parts)
        elif main_cmd == "/roadmap":
            self._handle_roadmap(parts)
        elif main_cmd == "/compile":
            self._handle_compile(parts)
        elif main_cmd == "/topic":
            self._handle_topic(parts)
        elif main_cmd == "/skill":
            self._handle_skill(parts)
        elif main_cmd == "/publish":
            self._handle_publish(parts)
        elif main_cmd == "/group":
            self._handle_group(parts)
        elif main_cmd == "/router":
            self._handle_router(parts)
        elif main_cmd == "/audit":
            self._handle_audit(parts)
        elif main_cmd == "/boundary":
            self._handle_boundary(parts)
        elif main_cmd == "/template":
            self._handle_template(parts)
        elif main_cmd == "/code":
            self._handle_code(parts)
        elif main_cmd == "/config":
            self._print_config()
        elif main_cmd == "/news":
            self._handle_news(parts)
        elif main_cmd == "/stock":
            self._handle_stock(parts)
        elif main_cmd == "/free":
            self._handle_free(parts)
        elif main_cmd == "/compress":
            self._handle_compress(parts)
        elif main_cmd == "/lint":
            self._handle_lint(parts)
        elif main_cmd == "/checkpoint":
            self._handle_checkpoint(parts)
        elif main_cmd == "/provider":
            self._handle_provider(parts)
        elif main_cmd == "/schedule":
            self._handle_schedule(parts)
        elif main_cmd == "/bgplugin":
            self._handle_bgplugin(parts)
        elif main_cmd == "/diag":
            self._handle_diag(parts)
        elif main_cmd == "/help":
            self._print_help()
        elif main_cmd == "/test":
            self._test_connection(silent=False)
        else:
            print(f"{Color.DIM}未知命令，输入 /help 查看可用命令{Color.RESET}")

    # ─── PSI命令 ──────────────────────────────

    def _print_psi(self):
        """显示PSI内在状态"""
        if not self.psi:
            print(f"{Color.DIM}PSI引擎未启用{Color.RESET}")
            return

        stats = self.psi.get_stats()
        print(f"{Color.DIM}─── 内在状态 (PSI) ───{Color.RESET}")
        for name, status in stats["needs"].items():
            # 根据状态着色
            if "赤字" in status:
                color = Color.RED
            elif "满足" in status:
                color = Color.GREEN
            else:
                color = Color.YELLOW
            print(f"  {color}{name}: {status}{Color.RESET}")
        print(f"  {Color.DIM}意识帧: {stats['consciousness_frame']}{Color.RESET}")
        if stats.get("last_interaction"):
            print(f"  {Color.DIM}上次互动: {stats['last_interaction'][:19]}{Color.RESET}")

    # ─── 知觉日记 ─────────────────────────────

    def _handle_diary(self, parts):
        if not self.psi:
            print(f"{Color.DIM}PSI引擎未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "write"

        if sub == "write":
            content = parts[2] if len(parts) > 2 else ""
            if not content:
                print(f"{Color.DIM}用法: /diary write <内容>{Color.RESET}")
                print(f"{Color.DIM}  或: /diary auto (自动生成){Color.RESET}")
                return
            self.psi.write_diary(content)
            print(f"{Color.GREEN}✓ 已写入知觉日记{Color.RESET}")

        elif sub == "auto":
            if not self.ctx.history:
                print(f"{Color.DIM}没有对话记录{Color.RESET}")
                return
            print(f"{Color.DIM}正在生成日记...{Color.RESET}", end="", flush=True)
            diary_entry = self._auto_generate_diary()
            if diary_entry:
                self.psi.write_diary(diary_entry)
                print(f"\r{Color.GREEN}✓ 日记已写入{Color.RESET}        ")
                print(f"{Color.DIM}{diary_entry[:100]}...{Color.RESET}")
            else:
                print(f"\r{Color.RED}✗ 生成失败{Color.RESET}        ")

        elif sub == "read":
            diary_path = self.psi.diary_file
            if not diary_path.exists():
                print(f"{Color.DIM}还没有日记{Color.RESET}")
                return
            with open(diary_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 只显示最后2000字符
            if len(content) > 2000:
                content = "...(更早的省略)...\n" + content[-2000:]
            print(content)

        else:
            print(f"{Color.DIM}用法:{Color.RESET}")
            print(f"  {Color.CYAN}/diary write <内容>{Color.RESET}  写日记")
            print(f"  {Color.CYAN}/diary auto{Color.RESET}         自动生成")
            print(f"  {Color.CYAN}/diary read{Color.RESET}          查看日记")

    def _auto_generate_diary(self) -> str:
        """用LLM自动生成知觉日记"""
        recent = self.ctx.history[-12:]
        conv_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '知乐'}: {m['content']}"
            for m in recent
        )

        psi_text = self.psi.get_context() if self.psi else ""

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
            result = ""
            for chunk in self.llm.chat(messages, stream=True):
                result += chunk
            return result.strip()
        except Exception as e:
            print(f"\n{Color.RED}日记生成失败: {e}{Color.RESET}", flush=True)
            return ""

    # ─── 自成长 ───────────────────────────────

    def _handle_growth(self, parts):
        if not self.growth:
            print(f"{Color.DIM}自成长扫描器未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "scan"

        if sub == "scan":
            if not self.ctx.history:
                print(f"{Color.DIM}没有对话记录{Color.RESET}")
                return
            print(f"{Color.DIM}正在扫描新行为...{Color.RESET}", end="", flush=True)
            result = self.growth.scan(self.ctx.history, self.llm)
            if result.get("found"):
                print(f"\r{Color.GREEN}✓ 发现成长候选！{Color.RESET}        ")
                print(f"  {Color.CYAN}行为:{Color.RESET} {result.get('behavior', '')}")
                print(f"  {Color.CYAN}证据:{Color.RESET} {result.get('evidence', '')}")
                print(f"  {Color.CYAN}类型:{Color.RESET} {result.get('growth_type', '')}")
                print(f"  {Color.CYAN}建议:{Color.RESET} {result.get('suggestion', '')}")
                print(f"  {Color.DIM}已记录到workspace.md{Color.RESET}")
            else:
                print(f"\r{Color.YELLOW}未发现新行为{Color.RESET}        ")
                if result.get("reason"):
                    print(f"  {Color.DIM}{result['reason']}{Color.RESET}")

        elif sub == "stats":
            stats = self.growth.get_stats()
            print(f"{Color.DIM}─── 自成长统计 ───{Color.RESET}")
            print(f"  成长候选: {stats['candidates']}")
            print(f"  已确认:   {stats['confirmed']}")
            print(f"  文件:     {stats['file']}")

        elif sub == "read":
            content = self.growth.get_workspace()
            if len(content) > 3000:
                content = "...(更早的省略)...\n" + content[-3000:]
            print(content)

        else:
            print(f"{Color.DIM}用法:{Color.RESET}")
            print(f"  {Color.CYAN}/growth scan{Color.RESET}   扫描新行为")
            print(f"  {Color.CYAN}/growth stats{Color.RESET}  查看统计")
            print(f"  {Color.CYAN}/growth read{Color.RESET}   查看记录")

    # ─── 记忆命令 ─────────────────────────────

    def _handle_memory(self, parts):
        if not self.memory:
            print(f"{Color.DIM}记忆系统未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "list"

        if sub in ("list", "ls"):
            self._memory_list(parts[2] if len(parts) > 2 else None)
        elif sub == "add":
            content = parts[2] if len(parts) > 2 else ""
            if not content:
                print(f"{Color.DIM}用法: /memory add <内容>{Color.RESET}")
                return
            added = self.memory.add_memory(content, "general", 7)
            if added:
                print(f"{Color.GREEN}✓ 已记住{Color.RESET}")
            else:
                print(f"{Color.YELLOW}✓ 已更新（已存在）{Color.RESET}")
        elif sub in ("remove", "rm"):
            if len(parts) < 3:
                print(f"{Color.DIM}用法: /memory remove <序号>{Color.RESET}")
                return
            try:
                idx = int(parts[2]) - 1
                if self.memory.remove_memory(idx):
                    print(f"{Color.GREEN}✓ 已删除{Color.RESET}")
                else:
                    print(f"{Color.RED}✗ 序号无效{Color.RESET}")
            except ValueError:
                print(f"{Color.DIM}请输入数字序号{Color.RESET}")
        elif sub == "stats":
            self._memory_stats()
        elif sub == "extract":
            self._manual_extract()
        else:
            print(f"{Color.DIM}用法: /memory [list|add|rm|stats|extract]{Color.RESET}")

    def _memory_list(self, category=None):
        mems = self.memory.list_memories(category)
        if not mems:
            print(f"{Color.DIM}没有记忆{Color.RESET}")
            return
        print(f"{Color.DIM}─── 记忆 ({len(mems)}条) ───{Color.RESET}")
        for i, m in enumerate(mems):
            imp = "★" * (m.importance // 2)
            print(f"  {Color.CYAN}{i+1}.{Color.RESET} "
                  f"{m.content} {Color.DIM}[{m.category} {imp}]{Color.RESET}")

    def _memory_stats(self):
        stats = self.memory.get_stats()
        print(f"{Color.DIM}─── 记忆统计 ───{Color.RESET}")
        print(f"  总记忆:   {stats['total']}")
        print(f"  活跃:     {Color.GREEN}{stats['active']}{Color.RESET}")
        print(f"  已归档:   {stats['archived']}")
        if stats['by_category']:
            print(f"  分类:")
            for cat, count in stats['by_category'].items():
                print(f"    {cat}: {count}")

    def _manual_extract(self):
        if not self.ctx.history:
            print(f"{Color.DIM}没有对话记录{Color.RESET}")
            return
        print(f"{Color.DIM}正在提取记忆...{Color.RESET}", end="", flush=True)
        count = self.memory.extract_from_conversation(self.ctx.history)
        if count > 0:
            print(f"\r{Color.GREEN}✓ 提取了 {count} 条新记忆{Color.RESET}        ")
        else:
            print(f"\r{Color.YELLOW}没有发现新记忆{Color.RESET}        ")

    # ─── 退出 ─────────────────────────────────

    def _exit(self):
        self.running = False

        # 使用core.save()统一保存（含记忆提取+事件轨迹+体细胞检查+PSI）
        if self.core:
            print(f"\n{Color.DIM}正在保存...{Color.RESET}", end="", flush=True)
            result = self.core.save()
            parts = []
            if result.get("session"):
                parts.append("✓ 对话已保存")
            if result.get("memories", 0) > 0:
                parts.append(f"✓ 记住了 {result['memories']} 件新的事")
            if result.get("psi"):
                parts.append("✓ 内在状态已保存")
            if result.get("events", 0) > 0:
                parts.append(f"✓ 提取了 {result['events']} 个事件节点")
            if result.get("arc_candidates", 0) > 0:
                parts.append(f"✓ 发现 {result['arc_candidates']} 个弧光候选")
            if parts:
                print(f"\r{Color.GREEN}{chr(10).join(parts)}{Color.RESET}      ")
            else:
                print(f"\r{Color.DIM}✓ 已保存{Color.RESET}      ")
        else:
            # 旧模式fallback
            if self.memory and self.ctx.history:
                self.memory.save_session(self.ctx.history)
                print(f"\n{Color.DIM}✓ 对话已保存{Color.RESET}")
                mem_config = self.config.get("memory", {})
                if mem_config.get("auto_extract", True) and len(self.ctx.history) >= 4:
                    print(f"{Color.DIM}正在整理记忆...{Color.RESET}", end="", flush=True)
                    count = self.memory.extract_from_conversation(self.ctx.history)
                    if count > 0:
                        print(f"\r{Color.GREEN}✓ 记住了 {count} 件新的事{Color.RESET}      ")
                    else:
                        print(f"\r{Color.DIM}✓ 没什么需要记的{Color.RESET}      ")
            if self.psi:
                self.psi.on_session_end()
                print(f"{Color.DIM}✓ 内在状态已保存{Color.RESET}")

        print(f"{Color.PINK}喵～下次见啦{Color.RESET}")
        sys.exit(0)

    def _forget_session(self):
        self.ctx.clear()
        if self.memory:
            self.memory.session_history = []
            session_file = self.memory.memory_dir / "session.json"
            if session_file.exists():
                session_file.unlink()
        print(f"{Color.YELLOW}✦ 已清空当前会话（记忆和PSI保留）{Color.RESET}")

    # ─── 其他 ─────────────────────────────────

    def _print_status(self):
        stats = self.ctx.get_stats()
        print(f"{Color.DIM}─── 状态 ───{Color.RESET}")
        print(f"  模型:     {Color.GREEN}{self.llm.model}{Color.RESET}")
        print(f"  DNA版本:  {self.dna.get_dna_version()}")
        print(f"  对话轮数: {stats['turn_count']}")
        print(f"  消息数:   {stats['message_count']}")
        print(f"  预估token: ~{stats['estimated_tokens']}")
        print(f"  记忆注入: {'✓' if stats['has_memory'] else '✗'}")
        print(f"  PSI注入:  {'✓' if stats['has_psi'] else '✗'}")
        if self.memory:
            mem_stats = self.memory.get_stats()
            print(f"  记忆:     {mem_stats['active']}活跃/{mem_stats['total']}总计")
        if self.psi:
            psi_stats = self.psi.get_stats()
            print(f"  意识帧:   {psi_stats['consciousness_frame']}")

    def _save_conversation(self):
        if not self.ctx.history:
            print(f"{Color.DIM}没有对话记录{Color.RESET}")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_{timestamp}.json"
        data = {
            "timestamp": timestamp,
            "model": self.llm.model,
            "dna_version": self.dna.get_dna_version(),
            "messages": self.ctx.history,
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"{Color.GREEN}✓ 对话已保存到 {filename}{Color.RESET}")

    def _print_entities(self):
        """显示实体图"""
        if not self.entity_graph:
            print(f"{Color.DIM}实体图未启用{Color.RESET}")
            return
        stats = self.entity_graph.get_stats()
        print(f"{Color.DIM}─── 实体图 ───{Color.RESET}")
        print(f"  {Color.YELLOW}实体总数: {stats['total_entities']}{Color.RESET}")
        print(f"  {Color.YELLOW}关联边数: {stats['total_edges']}{Color.RESET}")
        print(f"  {Color.YELLOW}平均边权: {stats['avg_edge_weight']}{Color.RESET}")
        print()
        by_type = stats.get("by_type", {})
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {Color.CYAN}{t}: {count}{Color.RESET}")
        print()
        # 列出实体
        entities = list(self.entity_graph.entities.values())
        for e in entities[:20]:
            aliases = f" (别名: {', '.join(e.aliases)})" if e.aliases else ""
            linked = f" → {len(e.linked_memories)}条记忆" if e.linked_memories else ""
            print(f"  {Color.GREEN}[{e.entity_type}]{Color.RESET} {e.canonical_name}{aliases}{Color.DIM}{linked}{Color.RESET}")
        if len(entities) > 20:
            print(f"  {Color.DIM}...还有 {len(entities) - 20} 个{Color.RESET}")

    def _print_events(self):
        """显示事件轨迹（P0.18）"""
        stats = self.core.event_stats() if hasattr(self, 'core') and self.core else {}
        if not stats:
            print(f"{Color.DIM}事件轨迹系统未启用{Color.RESET}")
            return
        print(f"{Color.DIM}─── 事件轨迹 (P0.18) ───{Color.RESET}")
        print(f"  {Color.YELLOW}事件总数: {stats.get('total_events', 0)}{Color.RESET}")
        print(f"  {Color.YELLOW}分叉口: {stats.get('branch_points', 0)}{Color.RESET}")
        print(f"  {Color.YELLOW}事件簇: {stats.get('clusters', 0)}{Color.RESET}")
        print(f"  {Color.YELLOW}高置信度: {stats.get('high_confidence', 0)}{Color.RESET}")
        avg = stats.get('avg_confidence', 0)
        print(f"  {Color.YELLOW}平均置信度: {avg:.2f}{Color.RESET}")

    def _print_cells(self):
        """显示体细胞（P0.17）"""
        stats = self.core.somatic_stats() if hasattr(self, 'core') and self.core else {}
        if not stats:
            print(f"{Color.DIM}体细胞系统未启用{Color.RESET}")
            return
        print(f"{Color.DIM}─── 体细胞 (P0.17) ───{Color.RESET}")
        print(f"  {Color.GREEN}活跃: {stats.get('active', 0)}{Color.RESET}")
        print(f"  {Color.YELLOW}候选: {stats.get('candidate', 0)}{Color.RESET}")
        print(f"  {Color.DIM}休眠: {stats.get('dormant', 0)}{Color.RESET}")
        print(f"  {Color.DIM}覆盖: {stats.get('covered', 0)}{Color.RESET}")
        print(f"  {Color.DIM}丢弃: {stats.get('discarded', 0)}{Color.RESET}")
        print(f"  {Color.DIM}淡化: {stats.get('faded', 0)}{Color.RESET}")

    def _print_feedback(self):
        """显示活体约束层（P0.16）"""
        stats = self.core.feedback_stats() if hasattr(self, 'core') and self.core else {}
        if not stats:
            print(f"{Color.DIM}活体约束层未启用{Color.RESET}")
            return
        print(f"{Color.DIM}─── 活体约束层 (P0.16) ───{Color.RESET}")
        weights = stats.get('weights', {})
        changes = stats.get('weight_changes', {})
        for key, value in weights.items():
            change = changes.get(key, 0)
            if change > 0:
                arrow = f" {Color.GREEN}↑{change:+.2f}{Color.RESET}"
            elif change < 0:
                arrow = f" {Color.RED}↓{change:+.2f}{Color.RESET}"
            else:
                arrow = ""
            print(f"  {Color.CYAN}{key}: {value:.2f}{arrow}{Color.RESET}")
        print(f"  {Color.DIM}总调整次数: {stats.get('total_adjustments', 0)}{Color.RESET}")

    def _test_connection(self, silent: bool = False):
        if not silent:
            print(f"{Color.DIM}测试API连接...{Color.RESET}", end="", flush=True)
        ok, msg = self.llm.test_connection()
        if ok:
            if not silent:
                print(f"\r{Color.GREEN}✓ {msg}{Color.RESET}          ")
        else:
            print(f"\r{Color.RED}✗ {msg}{Color.RESET}          ")

    def _handle_observe(self, parts: list):
        """P0.9: 观察者调试面板"""
        observer = self.core.observer if self.core else None
        if not observer:
            print(f"{Color.DIM}观察者未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else ""
        arg = parts[2] if len(parts) > 2 else ""

        if sub == "" or sub == "last":
            # 显示最近5帧摘要
            count = int(arg) if arg.isdigit() else 5
            frames = observer.get_recent_frames(count)
            if not frames:
                print(f"{Color.DIM}还没有运行帧记录{Color.RESET}")
                return
            print(f"{Color.CYAN}─── 最近 {len(frames)} 帧摘要 ───{Color.RESET}")
            for f in frames:
                print(f"  {observer.format_summary(f)}")
            stats = observer.get_stats()
            print(f"{Color.DIM}  共 {stats['total_frames']} 帧{Color.RESET}")

        elif sub == "frame" and arg:
            # 显示某帧详情
            frame_id = int(arg) if arg.isdigit() else 0
            frame = observer.get_frame(frame_id)
            if not frame:
                print(f"{Color.DIM}帧 #{frame_id} 不存在{Color.RESET}")
                return
            print(observer.format_detail(frame))

        elif sub == "diff":
            # 对比两帧
            ids = arg.split() if arg else []
            if len(ids) < 2:
                print(f"{Color.DIM}用法: /obs diff <id1> <id2>{Color.RESET}")
                return
            a = observer.get_frame(int(ids[0]))
            b = observer.get_frame(int(ids[1]))
            if not a:
                print(f"{Color.DIM}帧 #{ids[0]} 不存在{Color.RESET}")
                return
            if not b:
                print(f"{Color.DIM}帧 #{ids[1]} 不存在{Color.RESET}")
                return
            print(observer.format_diff(a, b))

        elif sub == "stats":
            stats = observer.get_stats()
            print(f"{Color.CYAN}─── 观察者统计 ───{Color.RESET}")
            print(f"  总帧数: {stats['total_frames']}")
            print(f"  存储目录: {stats['frames_dir']}")

        elif sub == "clear":
            count = observer.clear()
            print(f"{Color.YELLOW}✦ 已清除 {count} 个运行帧{Color.RESET}")

        else:
            print(f"{Color.DIM}用法:{Color.RESET}")
            print(f"  {Color.CYAN}/obs{Color.RESET}              最近5帧摘要")
            print(f"  {Color.CYAN}/obs last <N>{Color.RESET}     最近N帧摘要")
            print(f"  {Color.CYAN}/obs frame <id>{Color.RESET}   某帧完整详情")
            print(f"  {Color.CYAN}/obs diff <id1> <id2>{Color.RESET} 对比两帧")
            print(f"  {Color.CYAN}/obs stats{Color.RESET}        统计信息")
            print(f"  {Color.CYAN}/obs clear{Color.RESET}        清除所有帧")

    # ─── P0.5: 快照命令 ──────────────────────

    def _handle_snapshot(self, parts: list):
        if not self.core or not self.core.snapshot:
            print(f"{Color.DIM}快照系统未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "list"

        if sub == "list" or sub == "ls":
            snapshots = self.core.snapshot_list()
            if not snapshots:
                print(f"{Color.DIM}还没有快照{Color.RESET}")
                return
            print(f"{Color.DIM}─── 快照列表 ({len(snapshots)}个) ───{Color.RESET}")
            for i, snap in enumerate(snapshots):
                ts = snap.get("timestamp", "")[:19]
                reason = snap.get("reason", "")
                files = snap.get("files", 0)
                sc = snap.get("somatic_count", 0)
                print(f"  {Color.CYAN}{i+1}.{Color.RESET} "
                      f"{Color.BOLD}{snap['id']}{Color.RESET} "
                      f"{Color.DIM}{ts}{Color.RESET}")
                print(f"     {Color.DIM}原因: {reason} | 文件: {files} | "
                      f"体细胞: {sc}{Color.RESET}")

        elif sub == "create":
            reason = parts[2] if len(parts) > 2 else "manual"
            print(f"{Color.DIM}正在创建快照...{Color.RESET}", end="", flush=True)
            snap_id = self.core.snapshot_create(reason)
            if snap_id:
                print(f"\r{Color.GREEN}✓ 快照已创建: {snap_id}{Color.RESET}        ")
            else:
                print(f"\r{Color.RED}✗ 创建失败{Color.RESET}        ")

        elif sub == "rollback":
            if len(parts) < 3:
                print(f"{Color.DIM}用法: /snap rollback <快照ID或序号>{Color.RESET}")
                return
            target = parts[2]
            # 支持序号选择
            snapshots = self.core.snapshot_list()
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(snapshots):
                    target = snapshots[idx]["id"]
                else:
                    print(f"{Color.RED}✗ 序号无效{Color.RESET}")
                    return
            print(f"{Color.DIM}正在回退到 {target}...{Color.RESET}", end="", flush=True)
            ok, msg = self.core.snapshot_rollback(target)
            if ok:
                print(f"\r{Color.GREEN}✓ {msg}{Color.RESET}        ")
            else:
                print(f"\r{Color.RED}✗ {msg}{Color.RESET}        ")

        elif sub == "verify":
            print(f"{Color.DIM}正在检查完整性...{Color.RESET}")
            result = self.core.snapshot_verify()
            print(f"{Color.DIM}─── 完整性检查 ───{Color.RESET}")
            for check in result.get("checks", []):
                name = check["name"]
                passed = check["passed"]
                detail = check["detail"]
                icon = f"{Color.GREEN}✅" if passed else f"{Color.RED}❌"
                print(f"  {icon} {name}{Color.RESET}: {detail}")
            overall = result.get("passed", False)
            if overall:
                print(f"\n  {Color.GREEN}✓ 全部通过{Color.RESET}")
            else:
                print(f"\n  {Color.RED}⚠ 存在问题，建议回退{Color.RESET}")

        elif sub == "log":
            limit = 10
            if len(parts) > 2:
                try:
                    limit = int(parts[2])
                except ValueError:
                    pass
            log = self.core.snapshot_log(limit)
            if not log:
                print(f"{Color.DIM}还没有进化日志{Color.RESET}")
                return
            print(f"{Color.DIM}─── 进化日志 (最近{len(log)}条) ───{Color.RESET}")
            for entry in log:
                ts = entry.get("timestamp", "")[:19]
                etype = entry.get("type", "")
                if etype == "snapshot":
                    icon = "📸"
                    detail = f"原因: {entry.get('reason', '')}"
                elif etype == "rollback":
                    icon = "↩️"
                    detail = f"恢复: {entry.get('files_restored', 0)}个文件"
                else:
                    icon = "•"
                    detail = str(entry)
                print(f"  {icon} {Color.DIM}{ts}{Color.RESET} {detail}")

        elif sub == "stats":
            stats = self.core.snapshot_stats()
            print(f"{Color.DIM}─── 快照统计 ───{Color.RESET}")
            print(f"  总快照:     {stats.get('total_snapshots', 0)}")
            print(f"  日志条目:   {stats.get('total_log_entries', 0)}")
            print(f"  今日回退:   {stats.get('today_rollbacks', 0)}")
            budget = stats.get('rollback_budget', 0)
            bcolor = Color.GREEN if budget > 0 else Color.RED
            print(f"  回退预算:   {bcolor}{budget}{Color.RESET}/{stats.get('today_rollbacks', 0)+budget}")
            print(f"  体细胞上限: {stats.get('max_somatic', 50)}")
            print(f"  弧光上限:   {stats.get('max_arc', 20)}")

        else:
            print(f"{Color.DIM}用法:{Color.RESET}")
            print(f"  {Color.CYAN}/snap{Color.RESET}                 查看快照列表")
            print(f"  {Color.CYAN}/snap create <原因>{Color.RESET}    创建快照")
            print(f"  {Color.CYAN}/snap rollback <ID>{Color.RESET}   回退到快照")
            print(f"  {Color.CYAN}/snap verify{Color.RESET}          完整性检查")
            print(f"  {Color.CYAN}/snap log <N>{Color.RESET}         进化日志")
            print(f"  {Color.CYAN}/snap stats{Color.RESET}           统计信息")

    # ─── 守护进程命令（P0.11）─────────────────

    def _handle_daemon(self, parts: list):
        """守护进程命令"""
        if not self.core or not self.core.daemon:
            print(f"{Color.DIM}守护进程未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else ""

        if sub == "run":
            print(f"{Color.DIM}手动执行守护进程...{Color.RESET}")
            result = self.core.daemon_run_once()
            self._print_daemon_result(result)
        elif sub == "vitals":
            vitals = self.core.daemon_vitals()
            if not vitals:
                print(f"{Color.DIM}暂无生命体征数据{Color.RESET}")
                return
            print(f"{Color.DIM}─── 生命体征 (vitals) ───{Color.RESET}")
            print(f"  时间: {vitals.get('timestamp', '?')[:19]}")
            print(f"  轮次: 第{vitals.get('cycle_count', 0)}轮")
            psi = vitals.get("psi", {})
            if psi:
                print(f"  {Color.PINK}PSI状态:{Color.RESET}")
                for nid, val in psi.items():
                    level = val.get("level", 0)
                    bar = "■" * int(round(level)) + "□" * (5 - int(round(level)))
                    print(f"    {nid}: {bar} {val.get('status', '?')} {val.get('trend', '')}")
            mem = vitals.get("memory", {})
            if mem:
                print(f"  记忆: {mem.get('active', 0)}活跃/{mem.get('total', 0)}总计")
            hex_data = vitals.get("hexagram", {})
            if hex_data:
                print(f"  卦象: {hex_data.get('hexagram', '?')} (更新{hex_data.get('update_count', 0)}次)")
            growth = vitals.get("growth", {})
            if growth:
                print(f"  体细胞: {growth.get('total', 0)}个")
            last_int = vitals.get("last_interaction", "")
            if last_int:
                print(f"  上次互动: {last_int[:19]}")
        else:
            status = self.core.daemon_status()
            print(f"{Color.DIM}─── 守护进程 ───{Color.RESET}")
            print(f"  启用: {'是' if status.get('enabled') else '否'}")
            print(f"  运行中: {'是' if status.get('running') else '否'}")
            print(f"  间隔: {status.get('interval', 1800)}秒")
            print(f"  轮次: 第{status.get('cycle_count', 0)}轮")
            if status.get("last_run"):
                print(f"  上次执行: {status['last_run']}")
            summary = status.get("last_summary")
            if summary and summary.get("errors"):
                print(f"  {Color.RED}⚠ 上轮有{len(summary['errors'])}个错误{Color.RESET}")

    def _print_daemon_result(self, result: dict):
        """打印守护进程执行结果"""
        print(f"{Color.DIM}─── 守护进程执行结果 ───{Color.RESET}")
        print(f"  轮次: 第{result.get('cycle', 0)}轮")
        print(f"  时间: {result.get('timestamp', '?')}")
        r = result.get("results", {})
        # PSI压力
        psi_r = r.get("psi_pressure", {})
        if psi_r and "pressures" in psi_r:
            print(f"  {Color.PINK}PSI压力:{Color.RESET}")
            for nid, val in psi_r["pressures"].items():
                print(f"    {nid}: {val}")
            if psi_r.get("alerts"):
                for a in psi_r["alerts"]:
                    print(f"    {Color.YELLOW}⚠ {a}{Color.RESET}")
        # 时间感知
        time_r = r.get("time_awareness", {})
        if time_r and "time" in time_r:
            print(f"  时间: {time_r.get('time', '?')} {time_r.get('shichen', '')} ({time_r.get('period', '')})")
        # 记忆衰减
        decay_r = r.get("memory_decay", {})
        if decay_r and "total" in decay_r:
            print(f"  记忆: {decay_r.get('total', 0)}条，更新{decay_r.get('updated', 0)}条")
        # 过期记忆
        stale_r = r.get("stale_memories", {})
        if stale_r and "total" in stale_r:
            print(f"  过期: {stale_r.get('stale_unimportant', 0)}可淡化，{stale_r.get('stale_important', 0)}需巩固")
        # vitals
        vitals_r = r.get("vitals", {})
        if vitals_r and vitals_r.get("written"):
            print(f"  {Color.GREEN}✓ vitals.json已更新{Color.RESET}")
        errors = result.get("errors")
        if errors:
            print(f"  {Color.RED}⚠ 错误: {errors}{Color.RESET}")
        else:
            print(f"  {Color.GREEN}✓ 全部任务正常{Color.RESET}")
        # Layer 2: 反思结果
        ref_r = r.get("reflection", {})
        if ref_r and ref_r.get("success"):
            print(f"  {Color.PINK}🧠 每日反思: {ref_r.get('insight', '')[:50]}{Color.RESET}")
        elif ref_r and ref_r.get("error"):
            print(f"  {Color.RED}⚠ 反思失败: {ref_r['error'][:50]}{Color.RESET}")
        # Layer 3: PSI触发思考
        psi_r = r.get("psi_thinking", {})
        if psi_r and psi_r.get("count"):
            for trig in psi_r.get("triggers", []):
                print(f"  {Color.YELLOW}⚡ PSI触发: {trig.get('trigger', '?')} "
                      f"({trig.get('description', '')}){Color.RESET}")
                if trig.get("thought"):
                    print(f"    → {trig['thought'][:60]}")

    # ─── P0.11 Layer 2/3: 反思命令 ────────────

    def _handle_reflect(self, parts: list):
        """处理 /reflect 命令"""
        sub = parts[1] if len(parts) > 1 else ""

        if sub == "run":
            print(f"{Color.DIM}手动触发每日反思...{Color.RESET}")
            result = self.core.reflection_run()
            self._print_reflection_result(result)

        elif sub == "diary":
            entries = self.core.reflection_diary(limit=10)
            if not entries:
                print(f"{Color.DIM}暂无知觉日记{Color.RESET}")
                return
            print(f"{Color.DIM}─── 知觉日记 ───{Color.RESET}")
            for e in entries:
                ts = e.get("timestamp", "?")[:19]
                etype = e.get("type", "?")
                if etype == "daily_reflection":
                    print(f"  {Color.PINK}[{ts}] 每日感悟{Color.RESET}")
                    print(f"    {e.get('insight', '')}")
                    if e.get("hexagram"):
                        print(f"    {Color.DIM}卦象: {e['hexagram']}{Color.RESET}")
                elif etype == "psi_triggered":
                    print(f"  {Color.YELLOW}[{ts}] PSI触发 ({e.get('trigger', '?')}){Color.RESET}")
                    print(f"    {e.get('thought', '')}")

        elif sub == "want":
            queue = self.core.reflection_want_to_say()
            if not queue:
                print(f"{Color.DIM}没有想说的话{Color.RESET}")
                return
            print(f"{Color.DIM}─── 想说的话 ───{Color.RESET}")
            for i, q in enumerate(queue):
                ts = q.get("timestamp", "?")[:19]
                src = q.get("source", "?")
                print(f"  {Color.PINK}[{i}] {ts} ({src}){Color.RESET}")
                print(f"    {q.get('message', '')}")

        elif sub == "trigger":
            print(f"{Color.DIM}手动检查PSI压力...{Color.RESET}")
            result = self.core.psi_thinking_check()
            if not result:
                print(f"{Color.GREEN}当前PSI压力正常，无需触发思考{Color.RESET}")
            else:
                print(f"{Color.DIM}─── PSI触发思考 ───{Color.RESET}")
                for trig in result.get("triggers", []):
                    print(f"  {Color.YELLOW}触发: {trig.get('trigger', '?')}{Color.RESET}")
                    print(f"    描述: {trig.get('description', '')}")
                    print(f"    PSI值: {trig.get('psi_level', '?')}")
                    if trig.get("thought"):
                        print(f"    思考: {trig['thought']}")
                    if trig.get("want_to_say"):
                        print(f"    {Color.PINK}想说: {trig['want_to_say']}{Color.RESET}")
                    if trig.get("error"):
                        print(f"    {Color.RED}错误: {trig['error']}{Color.RESET}")

        else:
            # 默认：显示状态
            ref_status = self.core.reflection_status()
            psi_status = self.core.psi_thinking_status()
            print(f"{Color.DIM}─── 长在线思考系统 ───{Color.RESET}")

            # Layer 2 状态
            print(f"  {Color.PINK}Layer 2 每日反思:{Color.RESET}")
            print(f"    启用: {'是' if ref_status.get('enabled') else '否'}")
            print(f"    计划时间: {ref_status.get('schedule_hours', [])}点")
            print(f"    今日已运行: {ref_status.get('today_runs', 0)}/"
                  f"{ref_status.get('max_daily_runs', 2)}次")
            print(f"    总计: {ref_status.get('run_count', 0)}次")
            if ref_status.get("last_run"):
                print(f"    上次: {ref_status['last_run'][:19]}")
            last = ref_status.get("last_summary", {})
            if last and last.get("success"):
                print(f"    {Color.GREEN}上次感悟: {last.get('insight', '')[:40]}{Color.RESET}")

            # Layer 3 状态
            print(f"  {Color.YELLOW}Layer 3 PSI触发思考:{Color.RESET}")
            print(f"    启用: {'是' if psi_status.get('enabled') else '否'}")
            print(f"    冷却: {psi_status.get('cooldown_hours', 2)}小时")
            print(f"    总触发: {psi_status.get('trigger_count', 0)}次")
            last_trigs = psi_status.get("last_triggers", {})
            if last_trigs:
                for tname, ts in last_trigs.items():
                    print(f"    {tname}: {ts[:19]}")
            else:
                print(f"    {Color.DIM}尚未触发过{Color.RESET}")

    def _print_reflection_result(self, result: dict):
        """打印反思结果"""
        if result.get("error"):
            print(f"  {Color.RED}✗ 反思失败: {result['error']}{Color.RESET}")
            return
        print(f"{Color.DIM}─── 反思结果 ───{Color.RESET}")
        print(f"  第{result.get('run_count', 0)}次 | {result.get('timestamp', '?')[:19]}")
        if result.get("insight"):
            print(f"  {Color.PINK}感悟: {result['insight']}{Color.RESET}")
        if result.get("consolidated"):
            print(f"  {Color.GREEN}巩固记忆: {result['consolidated']}条{Color.RESET}")
        if result.get("want_to_say"):
            print(f"  {Color.PINK}想说: {result['want_to_say']}{Color.RESET}")
        print(f"  {Color.GREEN}✓ 反思完成{Color.RESET}")

    # ─── P0.23: 认知路由 ──────────────────────

    def _handle_route(self, parts: list):
        """处理 /route 命令 — 查看认知路由统计"""
        router = getattr(self.core, 'cognitive_router', None)
        if not router:
            print(f"{Color.DIM}认知路由层未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else ""

        if sub == "stats":
            stats = router.get_stats()
            print(f"{Color.DIM}─── 路由统计 ───{Color.RESET}")
            print(f"  总请求: {stats['total']}")
            print(f"  {Color.GREEN}⚡规则命中: {stats['rule_hit']}{Color.RESET} ({stats.get('rule_hit_rate', '0%')})")
            print(f"  {Color.CYAN}📦记忆复用: {stats['memory_hit']}{Color.RESET} ({stats.get('memory_hit_rate', '0%')})")
            print(f"  {Color.YELLOW}📋模板填充: {stats['template_hit']}{Color.RESET} ({stats.get('template_hit_rate', '0%')})")
            print(f"  {Color.DIM}🤖LLM兜底: {stats['llm_fallback']}{Color.RESET} ({stats.get('llm_fallback_rate', '0%')})")
            print(f"  情景库: {stats.get('episodic_store_size', 0)}条")
            print(f"  {Color.GREEN}预估节省: ~{stats.get('token_saved_est', 0)} token{Color.RESET}")
        elif sub == "off":
            router.enabled = False
            print(f"{Color.YELLOW}认知路由已关闭（所有消息走LLM）{Color.RESET}")
        elif sub == "on":
            router.enabled = True
            print(f"{Color.GREEN}认知路由已开启{Color.RESET}")
        else:
            # 默认显示概览
            stats = router.get_stats()
            print(f"{Color.DIM}─── 认知路由层 ───{Color.RESET}")
            print(f"  状态: {'✅启用' if router.enabled else '❌关闭'}")
            print(f"  Layer 1 规则匹配: {'✅' if router.layers.get('rule') else '❌'}")
            print(f"  Layer 2 情景复用: {'✅' if router.layers.get('episodic') else '❌'}")
            print(f"  Layer 3 模板填充: {'✅' if router.layers.get('template') else '❌'}")
            if stats["total"] > 0:
                print(f"  总请求: {stats['total']}")
                print(f"  ⚡规则: {stats['rule_hit']} | 📦记忆: {stats['memory_hit']} | 📋模板: {stats['template_hit']} | 🤖LLM: {stats['llm_fallback']}")
                print(f"  预估节省: ~{stats.get('token_saved_est', 0)} token")
            print(f"  {Color.DIM}/route stats 详细 | /route on|off 开关{Color.RESET}")

    # ─── 插件命令 (P0.4) ──────────────────────

    def _handle_plugin(self, parts):
        pm = self.core.plugin_manager if self.core else None
        if not pm:
            print(f"{Color.DIM}插件系统未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else ""

        if sub == "" or sub == "list":
            stats = pm.get_stats()
            print(f"{Color.DIM}─── 插件 ───{Color.RESET}")
            print(f"  总计: {stats['total']} | 启用: {stats['enabled']} | 禁用: {stats['disabled']}")
            if stats["plugins"]:
                for p in stats["plugins"]:
                    status = f"{Color.GREEN}✅" if p["enabled"] else f"{Color.RED}❌"
                    health = "" if p["healthy"] else f" {Color.YELLOW}⚠不健康{Color.RESET}"
                    desc = f" — {p['description']}" if p["description"] else ""
                    print(f"  {status}{Color.RESET} {p['name']} v{p['version']} [{p['type']}]{health}{Color.DIM}{desc}{Color.RESET}")
            else:
                print(f"  {Color.DIM}暂无已加载插件{Color.RESET}")
            print(f"  {Color.DIM}/plugin on|off <name> 开关插件{Color.RESET}")

        elif sub == "on" and len(parts) > 2:
            name = parts[2]
            if pm.enable(name):
                print(f"{Color.GREEN}✅ 插件 {name} 已启用{Color.RESET}")
            else:
                print(f"{Color.RED}❌ 找不到插件: {name}{Color.RESET}")

        elif sub == "off" and len(parts) > 2:
            name = parts[2]
            if pm.disable(name):
                print(f"{Color.YELLOW}✅ 插件 {name} 已禁用{Color.RESET}")
            else:
                print(f"{Color.RED}❌ 找不到插件: {name}{Color.RESET}")

        else:
            print(f"  {Color.DIM}/plugin list | /plugin on <name> | /plugin off <name>{Color.RESET}")

    # ─── 自研路线图命令 (P0.4) ────────────────

    def _handle_roadmap(self, parts):
        rm = self.core.self_roadmap if self.core else None
        if not rm:
            print(f"{Color.DIM}自研路线图未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else ""

        if sub == "" or sub == "overview":
            ov = rm.get_overview()
            print(f"{Color.DIM}─── 自研路线图 ───{Color.RESET}")
            s = ov["stats"]
            print(f"  总计: {s['total_ideas']} | 完成: {s['completed']} | 失败: {s['failed']} | 放弃: {s['abandoned']}")
            print(f"  进行中: {ov['in_progress_count']} | 经验: {ov['lessons_count']}条")
            print(f"  本月自主发现: {ov['self_discovered_this_month']}/{ov['self_discovered_limit']}")
            if ov["in_progress"]:
                print(f"\n  {Color.CYAN}进行中:{Color.RESET}")
                for item in ov["in_progress"]:
                    priority_mark = "🔴" if item["priority"] == "high" else "⚪"
                    source_mark = "👑" if item["source"] == "master_request" else "🌱"
                    print(f"    {priority_mark}{source_mark} {item['id']} [{item['status']}] {item['title']}")
            else:
                print(f"  {Color.DIM}暂无进行中的idea{Color.RESET}")
            print(f"\n  {Color.DIM}/roadmap list 列表 | /roadmap add <描述> 添加 | /roadmap <id> 详情{Color.RESET}")

        elif sub == "list":
            ideas = rm.list_ideas()
            if not ideas:
                print(f"{Color.DIM}路线图为空{Color.RESET}")
                return
            print(f"{Color.DIM}─── 所有idea ({len(ideas)}) ───{Color.RESET}")
            for idea in ideas:
                status_color = {
                    "done": Color.GREEN, "failed": Color.RED, "abandoned": Color.DIM,
                    "idea": Color.YELLOW, "designing": Color.CYAN, "coding": Color.CYAN, "testing": Color.CYAN,
                }.get(idea["status"], Color.RESET)
                priority_mark = "🔴" if idea["priority"] == "high" else "  "
                source_mark = "👑" if idea["source"] == "master_request" else "🌱"
                print(f"  {priority_mark}{source_mark} {idea['id']} {status_color}[{idea['status']}]{Color.RESET} {idea['title']}")

        elif sub == "add" and len(parts) > 2:
            # 合并剩余部分作为描述
            desc = " ".join(parts[2:])
            idea, err = rm.add_idea(
                title=desc[:50],
                description=desc,
                source="master_request",
                source_detail=f"CLI添加: {desc}",
            )
            if err:
                print(f"{Color.RED}❌ {err}{Color.RESET}")
            else:
                print(f"{Color.GREEN}✅ 已添加 idea: {idea['id']} — {idea['title']}{Color.RESET}")
                print(f"  {Color.DIM}来源: 主人指定 | 优先级: high | 状态: idea{Color.RESET}")

        elif sub and sub.startswith("idea_"):
            detail = rm.get_idea_detail(sub)
            if not detail:
                print(f"{Color.RED}❌ 找不到: {sub}{Color.RESET}")
                return
            print(f"{Color.DIM}─── {detail['id']} ───{Color.RESET}")
            print(f"  标题: {detail['title']}")
            print(f"  状态: {detail['status']} | 优先级: {detail['priority']} | 来源: {detail['source']}")
            print(f"  创建: {detail['created_at'][:19]}")
            print(f"  描述: {detail['description']}")
            if detail.get("design"):
                print(f"  设计: {detail['design'][:200]}...")
            if detail.get("attempts"):
                print(f"  尝试: {len(detail['attempts'])}次")
            if detail.get("lessons"):
                print(f"  经验:")
                for l in detail["lessons"]:
                    print(f"    - {l['what_happened']}")
            if detail.get("tags"):
                print(f"  标签: {', '.join(detail['tags'])}")

        else:
            print(f"  {Color.DIM}/roadmap overview | /roadmap list | /roadmap add <描述> | /roadmap <id>{Color.RESET}")

    def _handle_compile(self, parts):
        """处理 /compile 命令 — 记忆编译层"""
        sub = parts[1] if len(parts) > 1 else "stats"

        if sub == "stats":
            status = self.core.compile_status()
            if not status.get("enabled", True) and "enabled" in status:
                print(f"{Color.DIM}记忆编译层未启用{Color.RESET}")
                return
            print(f"{Color.DIM}─── 记忆编译层 ───{Color.RESET}")
            print(f"  总页数: {status.get('total_pages', 0)}")
            by_type = status.get("by_type", {})
            for ptype, count in by_type.items():
                type_names = {"source": "来源页", "entity": "实体页",
                              "concept": "概念页", "comparison": "对比页"}
                print(f"    {type_names.get(ptype, ptype)}: {count}")
            print(f"  编译次数: {status.get('compile_count', 0)}")
            if status.get("last_compile_time"):
                print(f"  上次编译: {status['last_compile_time'][:19]}")
            if status.get("last_lint_time"):
                print(f"  上次Lint: {status['last_lint_time'][:19]}")

        elif sub == "run":
            print(f"{Color.YELLOW}⏳ 正在编译记忆...{Color.RESET}")
            result = self.core.compile_run(force=True)
            if result.get("error"):
                print(f"{Color.RED}❌ {result['error']}{Color.RESET}")
            elif result.get("compiled", 0) == 0:
                print(f"{Color.DIM}未编译新页（{result.get('reason', '无新记忆')}）{Color.RESET}")
            else:
                print(f"{Color.GREEN}✅ 编译完成！{Color.RESET}")
                print(f"  新建页数: {result['compiled']}")
                print(f"  处理记忆: {result.get('new_memories', 0)}")
                print(f"  总页数: {result.get('total_pages', 0)}")
                for p in result.get("pages_created", []):
                    type_names = {"source": "来源", "entity": "实体",
                                  "concept": "概念", "comparison": "对比"}
                    print(f"    [{type_names.get(p['type'], p['type'])}] {p['title']}")

        elif sub == "lint":
            print(f"{Color.YELLOW}⏳ 正在执行健康检查...{Color.RESET}")
            result = self.core.lint_run()
            if result.get("error"):
                print(f"{Color.RED}❌ {result['error']}{Color.RESET}")
            else:
                print(f"{Color.DIM}─── Lint报告 ───{Color.RESET}")
                print(f"  总记忆: {result.get('total_memories', 0)}")
                print(f"  总页数: {result.get('total_pages', 0)}")
                print(f"  孤立记忆: {len(result.get('orphan_memories', []))}")
                print(f"  缺失链接: {len(result.get('missing_links', []))}")
                print(f"  矛盾冲突: {len(result.get('contradictions', []))}")
                print(f"  关联建议: {len(result.get('suggestions', []))}")
                if result.get("orphan_memories"):
                    print(f"\n  {Color.YELLOW}孤立记忆（无实体关联）:{Color.RESET}")
                    for m in result["orphan_memories"][:5]:
                        print(f"    [{m['importance']}] {m['content']}")
                if result.get("suggestions"):
                    print(f"\n  {Color.CYAN}关联建议:{Color.RESET}")
                    for s in result["suggestions"][:5]:
                        print(f"    [{s['tag']}] {s['page_a']} ↔ {s['page_b']}")

        else:
            print(f"  {Color.DIM}/compile stats | /compile run | /compile lint{Color.RESET}")

    def _handle_topic(self, parts):
        """处理 /topic 命令 — 主动话题系统"""
        sub = parts[1] if len(parts) > 1 else "stats"

        if sub == "stats":
            status = self.core.topic_status()
            if not status.get("enabled", True) and "enabled" in status:
                print(f"{Color.DIM}话题系统未启用{Color.RESET}")
                return
            print(f"{Color.DIM}─── 主动话题 ───{Color.RESET}")
            print(f"  可用话题: {status.get('unused', 0)}")
            print(f"  已用话题: {status.get('used', 0)}")
            print(f"  总计: {status.get('total', 0)}")
            by_cat = status.get("by_category", {})
            if by_cat:
                cat_names = {"anime": "动漫", "game": "游戏", "tech": "科技",
                             "history": "历史", "fun": "趣味", "daily": "日常",
                             "emotion": "情感"}
                print(f"  分类:")
                for cat, count in by_cat.items():
                    print(f"    {cat_names.get(cat, cat)}: {count}")
            if status.get("needs_generate"):
                print(f"  {Color.YELLOW}⚠ 队列不足，需要生成{Color.RESET}")

        elif sub in ("gen", "generate"):
            print(f"{Color.YELLOW}⏳ 正在生成话题...{Color.RESET}")
            result = self.core.topic_generate()
            if result.get("error"):
                print(f"{Color.RED}❌ {result['error']}{Color.RESET}")
            elif result.get("generated", 0) == 0:
                print(f"{Color.DIM}未生成新话题{Color.RESET}")
            else:
                print(f"{Color.GREEN}✅ 生成了{result['generated']}条话题！{Color.RESET}")
                print(f"  可用话题: {result.get('total_unused', 0)}")
                for t in result.get("topics", []):
                    cat_names = {"anime": "动漫", "game": "游戏", "tech": "科技",
                                 "history": "历史", "fun": "趣味", "daily": "日常",
                                 "emotion": "情感"}
                    print(f"    [{cat_names.get(t['category'], t['category'])}] {t['title']}")

        elif sub == "next":
            topic = self.core.topic_next()
            if not topic:
                print(f"{Color.DIM}没有可用话题，用 /topic gen 生成一些{Color.RESET}")
            else:
                cat_names = {"anime": "动漫", "game": "游戏", "tech": "科技",
                             "history": "历史", "fun": "趣味", "daily": "日常",
                             "emotion": "情感"}
                print(f"{Color.PINK}【{cat_names.get(topic['category'], topic['category'])}】{topic['title']}{Color.RESET}")
                print(f"  {topic['content']}")
                if topic.get("tags"):
                    print(f"  标签: {', '.join(topic['tags'])}")

        elif sub == "peek":
            topics = self.core.topic_peek()
            if not topics:
                print(f"{Color.DIM}没有可用话题，用 /topic gen 生成一些{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 话题预览 ───{Color.RESET}")
                cat_names = {"anime": "动漫", "game": "游戏", "tech": "科技",
                             "history": "历史", "fun": "趣味", "daily": "日常",
                             "emotion": "情感"}
                for t in topics:
                    print(f"  [{cat_names.get(t['category'], t['category'])}] {t['title']}")
                    print(f"    {t['content']}")

        else:
            print(f"  {Color.DIM}/topic stats | /topic gen | /topic next | /topic peek{Color.RESET}")

    def _handle_skill(self, parts):
        """处理 /skill 命令 — 技能自学习系统"""
        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "list":
            skills = self.core.skill_list()
            if not skills:
                print(f"{Color.DIM}  暂无已注册技能{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 技能列表 ───{Color.RESET}")
                for s in skills:
                    tier_color = {"manual": Color.CYAN, "auto": Color.GREEN, "composite": Color.YELLOW}.get(s["tier"], Color.RESET)
                    state_str = ""
                    if s.get("t1_state"):
                        state_str = f" [{s['t1_state']}]"
                        if s["t1_state"] == "cooling":
                            state_str += f"({s.get('cooling_rounds', 0)}/10)"
                    disabled_str = f" {Color.RED}[禁用]{Color.RESET}" if s.get("disabled") else ""
                    flag_str = f" {Color.YELLOW}⚠低效{Color.RESET}" if s.get("flagged") else ""
                    print(f"  {tier_color}{s['name']}{Color.RESET} {Color.DIM}({s['tier_label']}){Color.RESET}{state_str}{disabled_str}{flag_str}")
                    print(f"    {Color.DIM}使用:{s['usage']} 成功率:{s['success_rate']:.0%}{Color.RESET}")
                print(f"\n  {Color.DIM}共 {len(skills)} 个技能{Color.RESET}")

        elif sub == "info":
            if len(parts) < 3:
                print(f"{Color.DIM}用法: /skill info <技能名>{Color.RESET}")
            else:
                name = parts[2]
                info = self.core.skill_info(name)
                if info.get("error"):
                    print(f"{Color.RED}❌ {info['error']}{Color.RESET}")
                else:
                    print(f"{Color.DIM}─── 技能详情 ───{Color.RESET}")
                    print(f"  名称: {Color.CYAN}{info['name']}{Color.RESET}")
                    print(f"  层级: {info['tier_label']}")
                    if info.get("keywords"):
                        print(f"  关键词: {', '.join(info['keywords'])}")
                    if info.get("category"):
                        print(f"  类别: {info['category']}")
                    if info.get("trigger_examples"):
                        print(f"  触发示例: {', '.join(info['trigger_examples'][:3])}")
                    if info.get("parents"):
                        print(f"  父技能: {', '.join(info['parents'])}")
                    print(f"  使用次数: {info['usage']}")
                    print(f"  成功率: {info['success_rate']:.0%}")
                    if info.get("t1_state"):
                        print(f"  T1状态: {info['t1_state']}" + (f"（冷却{info.get('cooling_rounds', 0)}轮）" if info['t1_state'] == 'cooling' else ""))
                    if info.get("disabled"):
                        print(f"  {Color.RED}[已禁用]{Color.RESET}")
                    if info.get("flagged"):
                        print(f"  {Color.YELLOW}⚠ 标记为低效，待重生成{Color.RESET}")
                    if info.get("content_preview"):
                        print(f"\n  {Color.DIM}── 内容预览 ──{Color.RESET}")
                        print(f"  {Color.DIM}{info['content_preview']}{Color.RESET}")

        elif sub == "disable":
            if len(parts) < 3:
                print(f"{Color.DIM}用法: /skill disable <技能名>{Color.RESET}")
            else:
                result = self.core.skill_disable(parts[2])
                if result.get("success"):
                    print(f"{Color.GREEN}✅ {result['message']}{Color.RESET}")
                else:
                    print(f"{Color.RED}❌ {result['message']}{Color.RESET}")

        elif sub == "enable":
            if len(parts) < 3:
                print(f"{Color.DIM}用法: /skill enable <技能名>{Color.RESET}")
            else:
                result = self.core.skill_enable(parts[2])
                if result.get("success"):
                    print(f"{Color.GREEN}✅ {result['message']}{Color.RESET}")
                else:
                    print(f"{Color.RED}❌ {result['message']}{Color.RESET}")

        elif sub == "remove":
            if len(parts) < 3:
                print(f"{Color.DIM}用法: /skill remove <技能名>{Color.RESET}")
            else:
                result = self.core.skill_remove(parts[2])
                if result.get("success"):
                    print(f"{Color.GREEN}✅ {result['message']}{Color.RESET}")
                else:
                    print(f"{Color.RED}❌ {result['message']}{Color.RESET}")

        elif sub == "status":
            eval_status = self.core.skill_eval_status()
            learn_status = self.core.skill_learn_status()

            print(f"{Color.DIM}─── 技能自学习 ───{Color.RESET}")

            if eval_status.get("enabled", True) and "total_evaluations" in eval_status:
                print(f"  评分器:")
                print(f"    总评估: {eval_status.get('total_evaluations', 0)}")
                print(f"    通过率: {eval_status.get('pass_rate', 0)}%")
            else:
                print(f"  评分器: {Color.DIM}未启用{Color.RESET}")

            if learn_status.get("enabled", True) and "total_cycles" in learn_status:
                print(f"  自学习:")
                print(f"    总循环: {learn_status.get('total_cycles', 0)}")
                print(f"    已固化: {learn_status.get('solidified', 0)}")
                print(f"    成功率: {learn_status.get('success_rate', 0)}%")
            else:
                print(f"  自学习: {Color.DIM}未启用{Color.RESET}")

        elif sub == "eval":
            print(f"{Color.YELLOW}⏳ 正在评估最近回复...{Color.RESET}")
            result = self.core.skill_eval_quick()
            if result.get("error"):
                print(f"{Color.RED}❌ {result['error']}{Color.RESET}")
            else:
                scores = result.get("scores", {})
                dim_names = {"identity": "身份一致性", "personality": "性格标尺",
                             "boundary": "边界遵守", "naturalness": "表达自然度",
                             "anti_ai": "反AI味"}
                print(f"{Color.DIM}─── 评估结果 ───{Color.RESET}")
                for dim, score in scores.items():
                    bar = "█" * int(score) + "░" * (10 - int(score))
                    color = Color.GREEN if score >= 7 else Color.YELLOW if score >= 5 else Color.RED
                    print(f"  {dim_names.get(dim, dim):8s} {color}{bar} {score}{Color.RESET}")
                print(f"  平均分: {result.get('average', 0)}")
                weakest = result.get("weakest")
                if weakest and scores.get(weakest, 10) < 7:
                    print(f"  {Color.YELLOW}⚠ 最弱项: {dim_names.get(weakest, weakest)}{Color.RESET}")

        elif sub == "learn":
            print(f"{Color.YELLOW}⏳ 执行自学习循环（可能需要一些时间）...{Color.RESET}")
            result = self.core.skill_learn_run()
            if result.get("error"):
                print(f"{Color.RED}❌ {result['error']}{Color.RESET}")
            elif not result.get("success"):
                print(f"{Color.DIM}本次未固化新技能{Color.RESET}")
                if result.get("reason"):
                    print(f"  原因: {result['reason']}")
                for lr in result.get("learning_results", []):
                    dim_names = {"identity": "身份一致性", "personality": "性格标尺",
                                 "naturalness": "表达自然度", "anti_ai": "反AI味"}
                    dim = lr.get("dimension", "?")
                    print(f"  [{dim_names.get(dim, dim)}] {lr.get('issue', '')[:60]}")
                    if lr.get("error"):
                        print(f"    {Color.RED}✗ {lr['error']}{Color.RESET}")
            else:
                solidified = sum(1 for lr in result.get("learning_results", [])
                                 if lr.get("solidified"))
                print(f"{Color.GREEN}✅ 固化了{solidified}条新技能！{Color.RESET}")
                for lr in result.get("learning_results", []):
                    if lr.get("solidified"):
                        rule = lr.get("rule", {})
                        print(f"  ✅ {rule.get('name', '?')}: {rule.get('description', '')[:60]}")

        else:
            print(f"  {Color.DIM}/skill list | /skill info <名> | /skill disable <名> | /skill enable <名> | /skill remove <名>{Color.RESET}")
            print(f"  {Color.DIM}/skill status | /skill eval | /skill learn{Color.RESET}")

    def _handle_publish(self, parts):
        """处理 /publish 命令 — 代码发布与核验"""
        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            status = self.core.publish_status()
            print(f"{Color.DIM}─── 代码发布与核验 ───{Color.RESET}")
            if status.get("enabled", False) or "total_requests" in status:
                print(f"  总请求: {status.get('total_requests', 0)}")
                print(f"  待核验: {status.get('pending', 0)}")
                print(f"  已批准: {status.get('approved', 0)}")
                print(f"  已驳回: {status.get('rejected', 0)}")
            else:
                print(f"  {Color.DIM}未启用（需在config.json中配置code_publisher）{Color.RESET}")

        elif sub == "pending":
            pending = self.core.publish_pending()
            if not pending:
                print(f"  {Color.DIM}无待核验请求{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 待核验请求 ───{Color.RESET}")
                for req in pending:
                    audit = req.get("l1_audit", {})
                    block = audit.get("auto_block", False)
                    icon = f"{Color.RED}🔴" if block else f"{Color.YELLOW}🟡"
                    print(f"  {icon} {req['id']}{Color.RESET}")
                    print(f"    分支: {req['branch']}")
                    print(f"    描述: {req.get('description', '')}")
                    print(f"    文件: {', '.join(req.get('files', []))}")
                    print(f"    审计: {audit.get('critical', 0)} CRITICAL / {audit.get('warnings', 0)} WARN")
                    if block:
                        print(f"    {Color.RED}⚠ 自动拦截（存在CRITICAL问题）{Color.RESET}")

        elif sub == "review":
            req_id = parts[2] if len(parts) > 2 else None
            detail = self.core.publish_review_detail(req_id)
            if detail.get("error") or detail.get("message"):
                print(f"  {Color.DIM}{detail.get('error', detail.get('message', '无'))}{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 核验详情 ───{Color.RESET}")
                print(f"  ID: {detail.get('id', '?')}")
                print(f"  分支: {detail.get('branch', '?')}")
                print(f"  描述: {detail.get('description', '')}")
                print(f"  状态: {detail.get('status', '?')}")
                print(f"  文件: {', '.join(detail.get('files', []))}")
                audit = detail.get("l1_audit", {})
                if audit:
                    print(f"  L1审计: {audit.get('critical', 0)}C / {audit.get('warnings', 0)}W / {audit.get('info', 0)}I")
                    for issue in audit.get("issues", [])[:5]:
                        sev = issue.get("severity", "?")
                        color = Color.RED if sev == "CRITICAL" else Color.YELLOW if sev == "WARNING" else Color.DIM
                        print(f"    {color}[{sev}] {issue.get('file','')}:{issue.get('line','')} {issue.get('description','')}{Color.RESET}")

        elif sub == "approve":
            req_id = parts[2] if len(parts) > 2 else ""
            if not req_id:
                print(f"  {Color.RED}用法: /publish approve <request_id>{Color.RESET}")
            else:
                notes = " ".join(parts[3:]) if len(parts) > 3 else ""
                result = self.core.publish_approve(req_id, notes)
                if result.get("success"):
                    print(f"  {Color.GREEN}✅ 已批准并合并到主分支{Color.RESET}")
                else:
                    print(f"  {Color.RED}❌ {result.get('error', '失败')}{Color.RESET}")

        elif sub == "reject":
            req_id = parts[2] if len(parts) > 2 else ""
            if not req_id:
                print(f"  {Color.RED}用法: /publish reject <request_id> [原因]{Color.RESET}")
            else:
                reason = " ".join(parts[3:]) if len(parts) > 3 else "未提供原因"
                result = self.core.publish_reject(req_id, reason)
                if result.get("success"):
                    print(f"  {Color.YELLOW}✅ 已驳回: {reason}{Color.RESET}")
                else:
                    print(f"  {Color.RED}❌ {result.get('error', '失败')}{Color.RESET}")

        else:
            print(f"  {Color.DIM}/publish status | /publish pending | /publish review | /publish approve <id> | /publish reject <id>{Color.RESET}")

    def _handle_group(self, parts):
        """处理 /group 命令 — 群聊管理"""
        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            status = self.core.group_status()
            print(f"{Color.DIM}─── 群聊系统 ───{Color.RESET}")
            if status.get("enabled", True) and "total_groups" in status:
                print(f"  群数: {status.get('total_groups', 0)}")
                print(f"  总成员: {status.get('total_members', 0)}")
                for g in status.get("groups", []):
                    print(f"  {Color.CYAN}{g['group_id']}{Color.RESET} ({g.get('name', '?')}) — {g['members']}人")
            else:
                print(f"  {Color.DIM}未启用{Color.RESET}")

        elif sub == "members":
            group_id = parts[2] if len(parts) > 2 else ""
            if not group_id:
                print(f"  {Color.RED}用法: /group members <group_id>{Color.RESET}")
            else:
                members = self.core.group_members(group_id)
                if not members:
                    print(f"  {Color.DIM}无成员数据{Color.RESET}")
                else:
                    print(f"{Color.DIM}─── {group_id} 成员 ───{Color.RESET}")
                    for m in members:
                        icon = "👑" if m.get("is_master") else "  "
                        bar = "█" * int(m["intimacy"] / 10) + "░" * (10 - int(m["intimacy"] / 10))
                        print(f"  {icon} {m['nickname'] or m['user_id']:12s} {Color.CYAN}{bar} {m['intimacy']}{Color.RESET} ({m['message_count']}条)")

        elif sub == "intimacy":
            if len(parts) < 5:
                print(f"  {Color.RED}用法: /group intimacy <group_id> <user_id> <value>{Color.RESET}")
            else:
                gid = parts[2]
                uid = parts[3]
                try:
                    val = float(parts[4])
                    result = self.core.group_set_intimacy(gid, uid, val)
                    if result.get("success"):
                        print(f"  {Color.GREEN}✅ {uid} 亲密度设为 {val}{Color.RESET}")
                    else:
                        print(f"  {Color.RED}❌ {result.get('error')}{Color.RESET}")
                except ValueError:
                    print(f"  {Color.RED}value必须是数字{Color.RESET}")

        else:
            print(f"  {Color.DIM}/group status | /group members <id> | /group intimacy <gid> <uid> <val>{Color.RESET}")

    def _handle_router(self, parts):
        """处理 /router 命令 — 插件路由器"""
        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            status = self.core.router_status()
            print(f"{Color.DIM}─── 插件路由器 ───{Color.RESET}")
            if status.get("enabled", True) and "total_tracked" in status:
                print(f"  追踪插件: {status.get('total_tracked', 0)}")
                print(f"  活跃: {status.get('active', 0)}")
                print(f"  休眠: {status.get('dormant', 0)}")
                if status.get("dormant_list"):
                    print(f"  休眠列表: {', '.join(status['dormant_list'])}")
                if status.get("most_used"):
                    print(f"  最常用:")
                    for name, info in status["most_used"]:
                        print(f"    {name}: {info.get('count', 0)}次")
            else:
                print(f"  {Color.DIM}未启用{Color.RESET}")

        elif sub == "route":
            # 用最近一条用户消息做路由测试
            msg = " ".join(parts[2:]) if len(parts) > 2 else ""
            if not msg:
                recent = [m for m in self.core.history if m.get("role") == "user"]
                if recent:
                    msg = recent[-1]["content"]
                    print(f"  {Color.DIM}使用最近消息: {msg[:50]}...{Color.RESET}")
                else:
                    print(f"  {Color.RED}用法: /router route <消息内容>{Color.RESET}")
                    return

            result = self.core.router_route(msg)
            if result.get("error"):
                print(f"  {Color.RED}❌ {result['error']}{Color.RESET}")
            else:
                task_names = {"chat": "闲聊", "deep_talk": "深层对话",
                              "tool_task": "工具任务", "memory_ops": "记忆整理",
                              "growth": "成长操作"}
                print(f"{Color.DIM}─── 路由决策 ───{Color.RESET}")
                print(f"  任务类型: {task_names.get(result['task_type'], result['task_type'])}")
                print(f"  激活插件: {', '.join(result['active_plugins'])}")
                print(f"  加载顺序: {' → '.join(result['load_order'])}")
                print(f"  预估token: ~{result['est_tokens']}")
                if result.get("psi_adjustments"):
                    print(f"  PSI调制:")
                    for adj in result["psi_adjustments"]:
                        print(f"    {Color.YELLOW}{adj}{Color.RESET}")

        else:
            print(f"  {Color.DIM}/router status | /router route [消息]{Color.RESET}")

    def _handle_audit(self, parts):
        """处理 /audit 命令 — 回执审计"""
        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            stats = self.core.audit_status()
            print(f"{Color.DIM}─── 回执审计 ───{Color.RESET}")
            if stats.get("enabled", True) and "total" in stats:
                print(f"  总记录: {stats.get('total', 0)}")
                by_type = stats.get("by_type", {})
                if by_type:
                    for t, c in by_type.items():
                        labels = {"llm_call": "LLM调用", "tool_call": "工具调用",
                                  "evolution": "进化操作", "memory_op": "记忆操作"}
                        print(f"    {labels.get(t, t)}: {c}")
                if stats.get("tool_failures", 0):
                    print(f"  {Color.RED}工具失败: {stats['tool_failures']}{Color.RESET}")
                if stats.get("evolution_rollbacks", 0):
                    print(f"  {Color.YELLOW}进化回退: {stats['evolution_rollbacks']}{Color.RESET}")
                print(f"  日志大小: {stats.get('log_file_size', '?')}")
            else:
                print(f"  {Color.DIM}未启用{Color.RESET}")

        elif sub == "recent":
            limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
            records = self.core.audit_recent(limit)
            if not records:
                print(f"  {Color.DIM}无审计记录{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 最近{len(records)}条审计 ───{Color.RESET}")
                labels = {"llm_call": "LLM", "tool_call": "TOOL",
                          "evolution": "EVOL", "memory_op": "MEM"}
                for r in records:
                    rtype = r.get("type", "?")
                    ts = r.get("timestamp", "")[11:19]
                    data = r.get("data", {})
                    icon = {"llm_call": "🤖", "tool_call": "🔧",
                            "evolution": "🧬", "memory_op": "📝"}.get(rtype, "❓")
                    preview = ""
                    if rtype == "llm_call":
                        preview = data.get("user_message_preview", "")[:40]
                    elif rtype == "tool_call":
                        preview = f"{data.get('tool', '?')} {'✅' if data.get('success') else '❌'}"
                    elif rtype == "evolution":
                        preview = f"{data.get('action', '?')} {'↩️回退' if data.get('rolled_back') else '✅'}"
                    elif rtype == "memory_op":
                        preview = f"{data.get('operation', '?')}"
                    print(f"  {icon} {ts} [{labels.get(rtype, '?')}] {preview}")

        elif sub == "query":
            rtype = parts[2] if len(parts) > 2 else None
            type_map = {"llm": "llm_call", "tool": "tool_call",
                        "evolution": "evolution", "memory": "memory_op"}
            if rtype and rtype in type_map:
                rtype = type_map[rtype]
            elif rtype and rtype not in type_map.values():
                rtype = None
            records = self.core.audit_query(record_type=rtype)
            if not records:
                print(f"  {Color.DIM}无匹配记录{Color.RESET}")
            else:
                print(f"  找到{len(records)}条记录")

        else:
            print(f"  {Color.DIM}/audit status | /audit recent [n] | /audit query [type]{Color.RESET}")

    def _handle_boundary(self, parts: list):
        """处理 /boundary 命令 — 边界硬拦截"""
        if not self.core or not self.core.boundary:
            print(f"{Color.DIM}边界拦截器未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            stats = self.core.boundary_status()
            print(f"{Color.DIM}─── 边界硬拦截 ───{Color.RESET}")
            print(f"  启用: {stats.get('enabled', '?')}")
            print(f"  严格模式: {stats.get('strict_mode', False)}")
            print(f"  总检查: {stats.get('total_checked', 0)}")
            print(f"  {Color.GREEN}通过: {stats.get('passed', 0)}{Color.RESET}")
            print(f"  {Color.YELLOW}警告: {stats.get('warned', 0)}{Color.RESET}")
            print(f"  {Color.RED}拦截: {stats.get('blocked', 0)}{Color.RESET}")
            print(f"  拦截率: {stats.get('block_rate', '0/0')}")
            if stats.get('block_reasons'):
                print(f"  {Color.DIM}拦截原因:{Color.RESET}")
                for reason, count in stats['block_reasons'].items():
                    print(f"    {reason}: {count}次")

        elif sub == "check" and len(parts) > 2:
            text = " ".join(parts[2:])
            result = self.core.boundary_check(text)
            level = result.get('level', 'PASS')
            color = Color.RED if level == "BLOCK" else (Color.YELLOW if level == "WARN" else Color.GREEN)
            print(f"  {color}级别: {level}{Color.RESET}")
            print(f"  结果: {result.get('result', '')[:200]}")

        elif sub == "reset":
            self.core.boundary_reset()
            print(f"  {Color.GREEN}拦截统计已重置{Color.RESET}")

        elif sub == "strict":
            self.core.boundary.strict_mode = not self.core.boundary.strict_mode
            state = "开启" if self.core.boundary.strict_mode else "关闭"
            print(f"  严格模式已{state}")

        else:
            print(f"  {Color.DIM}/boundary status | /boundary check <文本> | /boundary reset | /boundary strict{Color.RESET}")

    def _handle_template(self, parts: list):
        """处理 /template 命令 — 插件模板填充器"""
        if not self.core or not self.core.template_filler:
            print(f"{Color.DIM}模板填充器未启用{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            stats = self.core.template_status()
            print(f"{Color.DIM}─── 插件模板填充器 ───{Color.RESET}")
            print(f"  启用: {stats.get('enabled', '?')}")
            print(f"  可用模板: {', '.join(stats.get('available_templates', []))}")
            print(f"  总创建: {stats.get('total_created', 0)}")
            if stats.get('recent_creations'):
                print(f"  {Color.DIM}最近创建:{Color.RESET}")
                for c in stats['recent_creations']:
                    print(f"    {c.get('name', '?')} ({c.get('template', '?')}) - {c.get('time', '?')}")

        elif sub == "list":
            templates = self.core.template_list()
            print(f"{Color.DIM}─── 可用模板 ───{Color.RESET}")
            for name, desc in templates.items():
                print(f"  {Color.CYAN}{name}{Color.RESET}: {desc}")

        elif sub == "create" and len(parts) > 2:
            requirement = " ".join(parts[2:])
            plugin_name = None
            # 支持 /template create <name> <需求> 格式
            if len(parts) > 3 and not parts[2].startswith(" ") and "=" in parts[2]:
                plugin_name = parts[2].split("=")[1]
                requirement = " ".join(parts[3:])

            print(f"{Color.DIM}正在创建插件... 需求: {requirement}{Color.RESET}")
            result = self.core.template_create(requirement, plugin_name)
            if result.get('success'):
                print(f"  {Color.GREEN}✅ {result.get('message', '创建成功')}{Color.RESET}")
                print(f"  模板: {result.get('template_type', '?')}")
                print(f"  插件名: {result.get('plugin_name', '?')}")
            else:
                print(f"  {Color.RED}❌ {result.get('message', '创建失败')}{Color.RESET}")
                if result.get('errors'):
                    for e in result['errors']:
                        print(f"    - {e}")

        else:
            print(f"  {Color.DIM}/template status | /template list | /template create <需求描述>{Color.RESET}")

    def _handle_code(self, parts: list):
        """处理 /code 命令 — 代码执行沙箱 + 调试循环"""
        if not self.core:
            print(f"{Color.DIM}核心未初始化{Color.RESET}")
            return

        sub = parts[1] if len(parts) > 1 else "status"

        if sub == "status":
            stats = self.core.code_status()
            print(f"{Color.DIM}─── 代码沙箱 ───{Color.RESET}")
            exe = stats.get("executor", {})
            print(f"  沙箱: {'✅启用' if exe.get('enabled', False) else '❌未启用'}")
            if exe.get("enabled"):
                print(f"  执行次数: {exe.get('total_executions', 0)}")
                print(f"  超时限制: {exe.get('timeout', 10)}s | 内存限制: {exe.get('memory_limit_mb', 256)}MB")
                print(f"  平台: {exe.get('platform', '?')}")
            dbg = stats.get("debug_loop", {})
            print(f"  调试循环: {'✅启用' if dbg.get('enabled', False) else '❌未启用'}")
            if dbg.get("enabled"):
                print(f"  调试次数: {dbg.get('total_runs', 0)} (成功率: {dbg.get('success_rate', '?')})")
                print(f"  平均迭代: {dbg.get('avg_iterations', 0)} | 上限: {dbg.get('max_iterations', 5)}")

        elif sub == "run" and len(parts) > 2:
            code = " ".join(parts[2:])
            print(f"{Color.DIM}执行代码...{Color.RESET}")
            result = self.core.code_run(code)
            if result.get("success"):
                print(f"  {Color.GREEN}✅ 执行成功{Color.RESET} ({result.get('execution_time', 0):.2f}s)")
                if result.get("stdout"):
                    print(f"  {Color.DIM}输出:{Color.RESET}")
                    for line in result["stdout"].rstrip("\n").split("\n"):
                        print(f"    {line}")
                if result.get("result"):
                    print(f"  {Color.DIM}返回值: {result['result']}{Color.RESET}")
            else:
                print(f"  {Color.RED}❌ 执行失败{Color.RESET}")
                if result.get("error_type"):
                    print(f"  错误类型: {result['error_type']}")
                if result.get("error_message"):
                    print(f"  {result['error_message']}")
                if result.get("stderr"):
                    print(f"  {Color.DIM}stderr:{Color.RESET}")
                    for line in result["stderr"].rstrip("\n").split("\n")[:5]:
                        print(f"    {line}")
            # P0.46④: 展示写后自检结果
            self._print_lint(result)

        elif sub == "debug" and len(parts) > 2:
            code = " ".join(parts[2:])
            print(f"{Color.DIM}调试循环启动...{Color.RESET}")
            result = self.core.code_debug(code)
            if result.get("success"):
                print(f"  {Color.GREEN}✅ 调试成功{Color.RESET}")
                print(f"  迭代次数: {result.get('iterations', 0)}")
                if result.get("final_output"):
                    print(f"  {Color.DIM}最终输出:{Color.RESET}")
                    for line in result["final_output"].rstrip("\n").split("\n"):
                        print(f"    {line}")
            else:
                print(f"  {Color.RED}❌ 调试失败{Color.RESET} (迭代 {result.get('iterations', 0)} 次)")
                if result.get("history"):
                    last = result["history"][-1]
                    if last.get("result", {}).get("error_message"):
                        print(f"  最后错误: {last['result']['error_message']}")
            # P0.46④: 展示写后自检结果
            self._print_lint(result)

        elif sub == "history":
            history = self.core.code_history()
            if not history:
                print(f"  {Color.DIM}暂无调试历史{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 调试历史 (最近{len(history)}条) ───{Color.RESET}")
                for i, h in enumerate(history):
                    success = "✅" if h.get("success") else "❌"
                    iters = h.get("iterations", 0)
                    print(f"  {i+1}. {success} {iters}轮 - {h.get('timestamp', '?')}")

        else:
            print(f"  {Color.DIM}/code status | /code run <代码> | /code debug <代码> | /code history{Color.RESET}")

    def _print_lint(self, result: dict):
        """P0.46④: 展示写后自检结果"""
        lint = result.get("lint")
        if not lint or lint.get("checked", 0) == 0:
            return
        checked = lint["checked"]
        passed = lint["passed"]
        failed = lint["failed"]
        if failed == 0:
            print(f"  {Color.DIM}写后自检: {checked}个文件 全部通过 ✅{Color.RESET}")
        else:
            print(f"  {Color.RED}写后自检: {checked}个文件, {passed}通过, {failed}失败 ❌{Color.RESET}")
            for err in lint.get("errors", []):
                print(f"    {Color.RED}{err['file']}{Color.RESET}")
                for msg in err.get("errors", []):
                    print(f"      {msg}")

    # ─── P0.36: 配置查看 + 新闻推送 ──────────

    def _print_config(self):
        """显示当前运行器配置（脱敏）"""
        c = self.config
        print(f"\n{Color.BOLD}─── 运行器配置 ───{Color.RESET}")

        # 模型
        model = c.get("model", {})
        print(f"\n  {Color.CYAN}模型{Color.RESET}")
        print(f"    provider:    {model.get('provider', '?')}")
        print(f"    model:       {model.get('model', '?')}")
        api_key = model.get('api_key', '')
        if api_key:
            print(f"    api_key:     {api_key[:8]}...{api_key[-4:]}")
        print(f"    base_url:    {model.get('base_url', '?')}")

        # DNA
        dna = c.get("dna", {})
        print(f"\n  {Color.CYAN}DNA{Color.RESET}")
        print(f"    version:     {self.dna.get_dna_version() if self.dna else '?'}")
        print(f"    path:        {dna.get('path', '?')}")

        # 记忆
        mem = c.get("memory", {})
        print(f"\n  {Color.CYAN}记忆{Color.RESET}")
        print(f"    enabled:     {mem.get('enabled', False)}")
        print(f"    max_messages:{mem.get('max_messages', '?')}")
        print(f"    max_inject:  {mem.get('max_inject', '?')}")
        if self.memory:
            stats = self.memory.get_stats()
            print(f"    active:      {stats['active']}条")

        # PSI
        psi = c.get("psi", {})
        print(f"\n  {Color.CYAN}PSI{Color.RESET}")
        print(f"    enabled:     {psi.get('enabled', False)}")
        if self.psi:
            psi_stats = self.psi.get_stats()
            print(f"    意识帧:      {psi_stats['consciousness_frame']}")
            low = [n for n, s in psi_stats["needs"].items() if "赤字" in s]
            if low:
                print(f"    赤字:        {', '.join(low)}")

        # 新闻推送
        news = c.get("news_push", {})
        print(f"\n  {Color.CYAN}新闻推送 (P0.33){Color.RESET}")
        print(f"    enabled:     {news.get('enabled', False)}")
        print(f"    push_times:  {news.get('push_times', [9, 16])}")
        print(f"    topics:      {news.get('topics', [])}")
        print(f"    proxy:       {news.get('proxy', '无')}")

        # 主动消息
        proactive = c.get("proactive", {})
        print(f"\n  {Color.CYAN}主动消息 (P0.31){Color.RESET}")
        print(f"    enabled:     {proactive.get('enabled', False)}")
        print(f"    min_gap:     {proactive.get('min_gap_hours', '?')}h")
        print(f"    quiet_hours: {proactive.get('quiet_hours_start', 23)}-{proactive.get('quiet_hours_end', 7)}")

        # 搜索
        search = c.get("web_search", {})
        print(f"\n  {Color.CYAN}对话搜索 (P0.34){Color.RESET}")
        print(f"    enabled:     {search.get('enabled', False)}")
        print(f"    max_rounds:  {search.get('max_rounds', 3)}")
        print(f"    proxy:       {search.get('proxy', '无')}")

        # QQ
        qq = c.get("qq", {})
        if qq:
            print(f"\n  {Color.CYAN}QQ{Color.RESET}")
            print(f"    port:        {qq.get('port', '?')}")
            master = qq.get('master_id', '')
            bot = qq.get('bot_id', '')
            print(f"    master_id:   {master}")
            print(f"    bot_id:      {bot}")

        # 后台任务状态
        print(f"\n  {Color.CYAN}后台任务{Color.RESET}")
        has_bg = hasattr(self, '_bg_threads') and self._bg_threads
        print(f"    CLI后台:     {'运行中' if has_bg else '未启动'}")
        print(f"    (后台循环仅在QQ模式自动启动)")

        print()

    def _handle_news(self, parts):
        """手动触发新闻推送测试"""
        if not self.core:
            print(f"{Color.DIM}core未初始化{Color.RESET}")
            return

        news_config = self.core.config.get("news_push", {})
        if not news_config.get("enabled", False):
            print(f"{Color.DIM}新闻推送未启用{Color.RESET}")
            return

        print(f"{Color.CYAN}📰 正在搜索新闻...{Color.RESET}")
        brief = self.core.search_and_format_news()
        if brief:
            print(f"\n{Color.GREEN}{'─' * 50}{Color.RESET}")
            print(brief)
            print(f"{Color.GREEN}{'─' * 50}{Color.RESET}")
        else:
            print(f"{Color.YELLOW}新闻搜索无结果，可能网络问题{Color.RESET}")
            print(f"{Color.DIM}检查: proxy={news_config.get('proxy', '无')}, "
                  f"timeout={news_config.get('timeout', 12)}s{Color.RESET}")

    def _start_bg_threads(self):
        """P0.37: 通过BackgroundTaskManager启动后台任务"""
        self._bg_threads = True

        def _cli_output(message):
            """CLI输出回调 — 打印到终端"""
            print(f"\n  {Color.CYAN}{'─' * 50}{Color.RESET}")
            print(f"  {message}")
            print(f"  {Color.CYAN}{'─' * 50}{Color.RESET}")

        self.core.start_background(output_callback=_cli_output)

        proactive_cfg = self.core.config.get("proactive", {})
        news_cfg = self.core.config.get("news_push", {})
        if news_cfg.get("enabled", False):
            print(f"  {Color.DIM}📰 CLI新闻后台已启动 "
                  f"(每日{news_cfg.get('push_times', [9, 16])}){Color.RESET}")
        if proactive_cfg.get("enabled", False):
            print(f"  {Color.DIM}💌 主动消息已启用 (P0.37核心层){Color.RESET}")

    def _handle_free(self, parts):
        """P0.40: 自由五层框架状态"""
        if not self.core or not self.core.free_will:
            print(f"{Color.DIM}自由地基未启用{Color.RESET}")
            return
        fw = self.core.free_will
        status = fw.status()
        print(f"{Color.DIM}─── 自由五层框架 (Phase 1) ───{Color.RESET}")
        print(f"  {Color.CYAN}沙箱目录:{Color.RESET} {status['sandbox_dir']}")
        print(f"  {Color.CYAN}沙箱文件:{Color.RESET} {status['sandbox_files']}")
        print(f"  {Color.CYAN}好奇心队列:{Color.RESET} {status['curiosity_queue']} 个待探索")
        print(f"  {Color.CYAN}探索记录:{Color.RESET} {status['explorations_total']} 次")
        print(f"  {Color.CYAN}今日自由预算:{Color.RESET} {status['budget_remaining']}/{status['budget_daily_limit']} tokens")
        print(f"  {Color.CYAN}自修改记录:{Color.RESET} {status['modifications_total']} 条")
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "curiosity":
            queue = fw.curiosity_list(10)
            if queue:
                print(f"\n  {Color.DIM}好奇心队列:{Color.RESET}")
                for item in queue:
                    mark = "✓" if item.get("explored") else "○"
                    print(f"  {mark} {item['topic']}")
            else:
                print(f"  {Color.DIM}队列为空{Color.RESET}")
        elif sub == "log":
            log = fw.exploration_log(10)
            if log:
                print(f"\n  {Color.DIM}探索记录:{Color.RESET}")
                for entry in log:
                    print(f"  • {entry['action']} → {entry['result'][:50]}")
            else:
                print(f"  {Color.DIM}暂无探索记录{Color.RESET}")
        elif sub == "add" and len(parts) > 2:
            topic = " ".join(parts[2:])
            fw.add_curiosity(topic)
            print(f"  {Color.GREEN}✓ 已加入好奇心队列: {topic}{Color.RESET}")
        elif sub == "creation":
            creations = fw.list_creations()
            if creations:
                print(f"\n  {Color.DIM}自主项目:{Color.RESET}")
                for c in creations:
                    print(f"  • {c['name']}: {c['description']} [{c['status']}]")
            else:
                print(f"  {Color.DIM}暂无自主项目{Color.RESET}")
        elif sub == "mod":
            pending = fw.list_pending_approvals()
            if pending:
                print(f"\n  {Color.DIM}待确认修改:{Color.RESET}")
                for m in pending:
                    print(f"  • [{m['id']}] L{m['level']} {m['change_desc']} — {m['reason']}")
            else:
                print(f"  {Color.DIM}没有待确认的修改{Color.RESET}")
        elif sub == "approve" and len(parts) > 2:
            fw.approve_modification(parts[2])
            print(f"  {Color.GREEN}✅ 已批准修改 {parts[2]}{Color.RESET}")
        elif sub == "reject" and len(parts) > 2:
            fw.reject_modification(parts[2])
            print(f"  {Color.YELLOW}⏹ 已否决修改 {parts[2]}{Color.RESET}")
        elif sub == "decline":
            print(f"  {Color.DIM}拒绝权状态: 每小时上限2次{Color.RESET}")
            history = fw.decline_history()
            if history:
                print(f"  最近拒绝: {len(history)} 次")
            else:
                print(f"  {Color.DIM}暂无拒绝记录{Color.RESET}")

    def _handle_compress(self, parts):
        """P0.46②: 上下文压缩器状态"""
        if not self.core or not self.core.context_compressor:
            print(f"{Color.DIM}上下文压缩器未启用{Color.RESET}")
            return
        cc = self.core.context_compressor
        stats = cc.get_stats()
        print(f"{Color.DIM}─── 上下文压缩器 ───{Color.RESET}")
        print(f"  {Color.CYAN}启用:{Color.RESET} {stats['enabled']}")
        print(f"  {Color.CYAN}触发阈值:{Color.RESET} {stats['threshold']} 轮")
        print(f"  {Color.CYAN}总压缩次数:{Color.RESET} {stats['total_compressions']}")
        # 估算当前历史如果压缩能节省多少
        est = cc.estimate_token_savings(self.core.ctx.history)
        if est.get("would_compress"):
            print(f"  {Color.YELLOW}当前历史({est['middle_turns']}轮中间)可压缩{Color.RESET}")
            print(f"  {Color.DIM}原始: {est['original_chars']}字符 → 预估摘要: {est['estimated_summary_chars']}字符{Color.RESET}")
            print(f"  {Color.GREEN}预计节省: {est['estimated_savings']}字符{Color.RESET}")
        else:
            print(f"  {Color.DIM}当前历史无需压缩{Color.RESET}")

    def _handle_lint(self, parts):
        """P0.46④: 写后自检"""
        if not self.core or not self.core.post_write_linter:
            print(f"{Color.DIM}写后自检未启用{Color.RESET}")
            return
        target = parts[1] if len(parts) > 1 else "."
        linter = self.core.post_write_linter
        if target == ".":
            results = linter.batch_lint(".")
            print(f"{Color.DIM}─── 批量检查结果 ───{Color.RESET}")
            ok = sum(1 for r in results if r.success)
            fail = len(results) - ok
            for r in results:
                status = f"{Color.GREEN}✅{Color.RESET}" if r.success else f"{Color.RED}❌{Color.RESET}"
                print(f"  {status} {r.filepath}")
                if not r.success:
                    for err in r.errors:
                        print(f"       {Color.RED}{err}{Color.RESET}")
            print(f"\n{Color.CYAN}通过:{Color.RESET} {ok}  {Color.RED}失败:{Color.RESET} {fail}")
        else:
            result = linter.lint_file(target)
            if result.success:
                print(f"{Color.GREEN}✅ {target} 语法正确{Color.RESET}")
            else:
                print(f"{Color.RED}❌ {target} 语法错误:{Color.RESET}")
                for err in result.errors:
                    print(f"  {Color.RED}{err}{Color.RESET}")

    def _handle_checkpoint(self, parts):
        """P0.46⑤: 会话检查点"""
        if not self.core or not self.core.session_checkpoint:
            print(f"{Color.DIM}会话检查点未启用{Color.RESET}")
            return
        sc = self.core.session_checkpoint
        action = parts[1] if len(parts) > 1 else "info"
        if action == "info":
            info = sc.get_checkpoint_info()
            print(f"{Color.DIM}─── 会话检查点 ───{Color.RESET}")
            print(f"  {Color.CYAN}检查点数量:{Color.RESET} {info.get('count', 0)}")
            print(f"  {Color.CYAN}总大小:{Color.RESET} {info.get('total_size', '0B')}")
            for cp in info.get('checkpoints', []):
                print(f"  {Color.DIM}{cp}{Color.RESET}")
        elif action == "save":
            psi_state = self.core.psi.get_stats() if self.core.psi else {}
            sc.save_checkpoint(
                messages=self.core.ctx.history if hasattr(self.core.ctx, 'history') else [],
                metadata={"psi": psi_state, "turn": self.core._turn_count}
            )
            print(f"{Color.GREEN}✅ 检查点已保存{Color.RESET}")
        elif action == "restore":
            result = sc.restore_session()
            if result:
                msgs, meta = result
                print(f"{Color.GREEN}✅ 恢复了 {len(msgs)} 条消息{Color.RESET}")
                print(f"  {Color.DIM}元数据: {meta}{Color.RESET}")
            else:
                print(f"{Color.YELLOW}没有可恢复的检查点{Color.RESET}")

    def _handle_provider(self, parts):
        """P0.46⑥: 模型Provider信息"""
        if not self.core:
            print(f"{Color.DIM}核心未初始化{Color.RESET}")
            return
        llm = self.core.llm
        # 判断是否使用插件化 Provider
        is_adapter = hasattr(llm, 'provider')
        provider_type = type(llm.provider).__name__ if is_adapter else type(llm).__name__
        print(f"{Color.DIM}─── 模型Provider ───{Color.RESET}")
        print(f"  {Color.CYAN}运行模式:{Color.RESET} {'插件化(ProviderFactory)' if is_adapter else ' legacy(LLMProvider)'}")
        print(f"  {Color.CYAN}Provider类:{Color.RESET} {provider_type}")
        print(f"  {Color.CYAN}模型:{Color.RESET} {llm.model}")
        print(f"  {Color.CYAN}Base URL:{Color.RESET} {llm.config.get('base_url', 'N/A') if hasattr(llm, 'config') else getattr(llm, 'base_url', 'N/A')}")
        print(f"  {Color.CYAN}温度:{Color.RESET} {llm.config.get('temperature', 'N/A') if hasattr(llm, 'config') else getattr(llm, 'temperature', 'N/A')}")
        print(f"  {Color.CYAN}Max Tokens:{Color.RESET} {llm.config.get('max_tokens', 'N/A') if hasattr(llm, 'config') else getattr(llm, 'max_tokens', 'N/A')}")
        # 显示已注册的 Provider 列表
        if is_adapter:
            from model_provider import ProviderFactory
            factory = ProviderFactory()
            registered = factory.list_providers()
            print(f"  {Color.CYAN}已注册Provider:{Color.RESET} {', '.join(registered)}")
        print(f"  {Color.DIM}提示: 在config.json llm.provider中指定, 或通过ProviderFactory.register_provider()注册新Provider{Color.RESET}")

    def _handle_schedule(self, parts):
        """P0.46③: 自然语言Cron调度"""
        if not self.core or not self.core.nl_scheduler:
            print(f"{Color.DIM}自然语言调度器未启用{Color.RESET}")
            return
        nls = self.core.nl_scheduler
        action = parts[1] if len(parts) > 1 else "list"
        if action == "list":
            tasks = nls.list_tasks()
            if not tasks:
                print(f"{Color.DIM}没有定时任务{Color.RESET}")
            else:
                print(f"{Color.DIM}─── 定时任务 ───{Color.RESET}")
                for t in tasks:
                    status_str = f"{Color.GREEN}活跃" if t.get('active') else f"{Color.YELLOW}停止"
                    next_str = t.get('next_run', 'N/A')
                    print(f"  {Color.CYAN}{t['task_id']}{Color.RESET} [{t['cron']}] {t['description']} {status_str}{Color.RESET} 下次: {next_str}")
        elif action == "cancel":
            if len(parts) < 3:
                print(f"{Color.YELLOW}用法: /schedule cancel <task_id>{Color.RESET}")
                return
            if nls.cancel_task(parts[2]):
                print(f"{Color.GREEN}✅ 任务已取消{Color.RESET}")
            else:
                print(f"{Color.RED}❌ 任务不存在{Color.RESET}")
        elif action == "status":
            s = nls.status()
            print(f"{Color.DIM}─── 调度器状态 ───{Color.RESET}")
            print(f"  总任务数: {s['total_tasks']}  活跃: {s['active_tasks']}")
            print(f"  API: {'✅' if s['api_configured'] else '❌'}  模型: {s['model']}")
        else:
            # 将剩余部分作为自然语言解析并创建任务
            nl_text = " ".join(parts[1:])
            if not nl_text:
                print(f"{Color.YELLOW}用法: /schedule <自然语言描述>{Color.RESET}")
                print(f"{Color.DIM}示例: /schedule 每天晚上10点提醒我喝水{Color.RESET}")
                return
            print(f"{Color.DIM}解析中: {nl_text}{Color.RESET}")
            result = nls.parse_to_cron(nl_text)
            if result.get("cron"):
                cron_expr = result["cron"]
                desc = result.get("description", nl_text)
                task_type = result.get("task_type", "定时任务")
                print(f"  {Color.GREEN}✅ cron: {cron_expr}{Color.RESET}")
                print(f"  {Color.DIM}类型: {task_type} | {desc}{Color.RESET}")
                # 自动创建任务
                def _task_callback(text=desc):
                    print(f"\n  ⏰ 定时提醒: {text}")
                try:
                    task_id = nls.create_scheduled_task(cron_expr, _task_callback, desc)
                    next_run = CronParser.next_run(cron_expr)
                    next_str = next_run.strftime('%Y-%m-%d %H:%M') if next_run else "未知"
                    print(f"  {Color.GREEN}✅ 任务已创建: {task_id}{Color.RESET}")
                    print(f"  {Color.DIM}下次执行: {next_str}{Color.RESET}")
                except ValueError as e:
                    print(f"  {Color.RED}❌ 创建失败: {e}{Color.RESET}")
            else:
                print(f"  {Color.RED}❌ 解析失败{Color.RESET}")
                print(f"  {Color.DIM}请尝试手动输入cron表达式，或换种说法{Color.RESET}")

    def _handle_bgplugin(self, parts):
        """P0.35 Phase 1: 后台插件管理"""
        if not self.core or not self.core.bg_plugin_manager:
            print(f"{Color.DIM}后台插件管理器未启用{Color.RESET}")
            return
        mgr = self.core.bg_plugin_manager
        action = parts[1] if len(parts) > 1 else "status"
        if action == "status":
            status = mgr.get_status()
            print(f"{Color.DIM}─── 后台插件 ───{Color.RESET}")
            print(f"  启用: {status.get('plugins_enabled', False)}  总数: {status.get('total', 0)}  运行中: {status.get('running', 0)}  已停止: {status.get('stopped', 0)}")
            for p in status.get("plugins", []):
                running = p.get("is_running", False)
                s = f"{Color.GREEN}运行中" if running else f"{Color.DIM}已停止"
                interval = p.get("interval")
                interval_str = f"{interval}s" if interval else "N/A"
                ticks = p.get("tick_count", 0)
                errors = p.get("error_count", 0)
                last = p.get("last_tick", "N/A")
                print(f"  {Color.CYAN}{p['name']}{Color.RESET} {s}{Color.RESET} 间隔:{interval_str}  ticks:{ticks}  错误:{errors}  最后:{last}")
        elif action == "start":
            mgr.start_all()
            print(f"{Color.GREEN}✅ 所有插件已启动{Color.RESET}")
        elif action == "stop":
            mgr.stop_all()
            print(f"{Color.YELLOW}⏹ 所有插件已停止{Color.RESET}")
        else:
            print(f"{Color.DIM}用法: /bgplugin [status|start|stop]{Color.RESET}")

    # ─── 隐藏系统诊断 ──────────────────────

    def _handle_diag(self, parts: list):
        """深度诊断：主动测试所有隐藏系统的存活状态"""
        import time as _time
        from datetime import datetime as _dt

        if not self.core:
            print(f"{Color.RED}Core 未初始化{Color.RESET}")
            return

        c = self.core
        now = _dt.now()
        pass_count = 0
        fail_count = 0
        warn_count = 0
        results = []

        def ok(name, detail=""):
            nonlocal pass_count
            pass_count += 1
            results.append(f"  {Color.GREEN}✅ {name}{Color.RESET}" + (f" {Color.DIM}{detail}{Color.RESET}" if detail else ""))

        def fail(name, detail=""):
            nonlocal fail_count
            fail_count += 1
            results.append(f"  {Color.RED}❌ {name}{Color.RESET}" + (f" {Color.RED}{detail}{Color.RESET}" if detail else ""))

        def warn(name, detail=""):
            nonlocal warn_count
            warn_count += 1
            results.append(f"  {Color.YELLOW}⚠️  {name}{Color.RESET}" + (f" {Color.DIM}{detail}{Color.RESET}" if detail else ""))

        print(f"\n{Color.CYAN}═══ 隐藏系统深度诊断 ═══{Color.RESET}")
        print(f"{Color.DIM}时间: {now.strftime('%Y-%m-%d %H:%M:%S')}{Color.RESET}\n")

        # ── 1. 13术数系统快照生成 ──
        print(f"{Color.CYAN}── 1. 术数系统快照生成 ──{Color.RESET}")
        try:
            from resonance_engine import ResonanceEngine
            import sys as _sys
            import os as _os
            _BASE = _os.path.dirname(_os.path.abspath(__file__))

            _SYS_LIST = [
                ("yi_jing", "yi_jing", "yi_jing_label_dictionary", "generate_labels_from_timestamp"),
                ("bazi", "bazi", "bazi_label_dictionary", "generate_labels_from_timestamp"),
                ("ziwei", "ziwei", "ziwei_label_dictionary", "generate_labels_from_timestamp"),
                ("qimen", "qimen", "qimen_label_dictionary", "generate_labels_from_timestamp"),
                ("liuren", "liuren", "liuren_label_dictionary", "generate_labels_from_timestamp"),
                ("taiyi", "taiyi", "taiyi_label_dictionary", "generate_labels_from_timestamp"),
                ("tongsheng", "tongsheng", "tongsheng_label_dictionary", "generate_labels_from_timestamp"),
                ("zhongyi", "zhongyi", "zhongyi_label_dictionary", "generate_labels_from_timestamp"),
                ("qita", "qita", "qita_label_dictionary", "generate_labels_from_timestamp"),
                ("canmou", "canmou", "canmou_label_dictionary", "generate_canmou_labels"),
                ("jyotish", "jyotish", "jyotish_label_dictionary", "generate_labels_from_timestamp"),
                ("tarot", "tarot", "tarot_label_dictionary", "generate_labels_from_timestamp"),
                ("economic_cycle", "economic_cycle", "economic_cycle_label_dictionary", "generate_labels_from_timestamp"),
            ]

            sys_ok = 0
            sys_fail_list = []
            for sys_name, dir_name, mod_name, func_name in _SYS_LIST:
                sys_dir = _os.path.join(_BASE, dir_name)
                if sys_dir not in _sys.path:
                    _sys.path.insert(0, sys_dir)
                try:
                    mod = __import__(mod_name)
                    func = getattr(mod, func_name)
                    # 尝试调用
                    import inspect
                    sig = inspect.signature(func)
                    params = list(sig.parameters.keys())
                    if "dt" in params or len(params) == 1:
                        result = func(now)
                    elif len(params) == 5:
                        result = func(now.year, now.month, now.day, now.hour, now.minute)
                    elif len(params) == 4:
                        result = func(now.year, now.month, now.day, now.hour)
                    else:
                        result = func(now.year, now.month, now.day, now.hour, now.minute)
                    if result:
                        sys_ok += 1
                    else:
                        sys_fail_list.append(f"{sys_name}(空结果)")
                except Exception as e:
                    sys_fail_list.append(f"{sys_name}({type(e).__name__}: {str(e)[:40]})")

            if sys_ok == 13:
                ok(f"13/13术数系统全部存活", f"({sys_ok}/13)")
            elif sys_ok > 0:
                warn(f"部分系统存活", f"({sys_ok}/13) 失败: {', '.join(sys_fail_list)}")
            else:
                fail("术数系统全部失败", "检查lunar_python等依赖")
        except Exception as e:
            fail("术数系统测试异常", str(e)[:60])

        # ── 2. 共振快照+缓存 ──
        print(f"{Color.CYAN}── 2. 共振引擎+缓存 ──{Color.RESET}")
        try:
            from resonance_engine import ResonanceEngine
            engine = ResonanceEngine()

            # 清缓存后冷启动
            ResonanceEngine._cache_raw = None
            t0 = _time.perf_counter()
            snap = engine.generate_snapshot(now.year, now.month, now.day, now.hour, now.minute)
            t_cold = (_time.perf_counter() - t0) * 1000

            # 缓存命中
            t0 = _time.perf_counter()
            snap2 = engine.generate_snapshot(now.year, now.month, now.day, now.hour, now.minute)
            t_hot = (_time.perf_counter() - t0) * 1000

            sys_count = len(snap) if snap else 0
            if sys_count >= 10:
                ok(f"快照生成 {sys_count}/13系统", f"冷{t_cold:.0f}ms 热{t_hot:.3f}ms")
            elif sys_count > 0:
                warn(f"快照生成 {sys_count}/13系统", f"冷{t_cold:.0f}ms")
            else:
                fail("快照生成失败", "0个系统产出")

            if t_hot < 1.0:
                ok("缓存命中", f"{t_hot:.3f}ms")
            else:
                warn("缓存未命中", f"{t_hot:.1f}ms")
        except Exception as e:
            fail("共振引擎异常", str(e)[:60])

        # ── 3. 共振计算 ──
        print(f"{Color.CYAN}── 3. 共振计算 ──{Color.RESET}")
        try:
            compact = engine.extract_compact_snapshot(snap)
            t0 = _time.perf_counter()
            score = engine.calculate(compact, compact)
            t_calc = (_time.perf_counter() - t0) * 1000
            if 0.5 < score < 2.5:
                ok(f"共振计算正常", f"自共振={score:.3f} ({t_calc:.2f}ms)")
            else:
                warn(f"共振分数异常", f"score={score:.3f}")
        except Exception as e:
            fail("共振计算异常", str(e)[:60])

        # ── 4. 瞬时感知层 ──
        print(f"{Color.CYAN}── 4. 瞬时感知层(一期一会) ──{Color.RESET}")
        try:
            if c.fleeting_moment:
                fm = c.fleeting_moment

                class _FakeMem:
                    _resonance_raw = 1.8
                    content = "诊断测试记忆"
                    class memory:
                        content = "诊断测试记忆"

                hex_info = None
                if c._hex_state:
                    hex_info = c._hex_state.get("current", {})
                result = fm.generate([_FakeMem()], hexagram_info=hex_info)

                if result and result.get("descriptor"):
                    ok("瞬时感知生成", f"档位={result.get('level','?')} 日记={result.get('diary_written', False)}")
                elif result is None:
                    ok("瞬时感知跳过", "共振分低于阈值(正常)")
                else:
                    warn("瞬时感知返回空", str(result)[:40])
            else:
                warn("瞬时感知未初始化", "fleeting_moment=None")
        except Exception as e:
            fail("瞬时感知异常", str(e)[:60])

        # ── 5. 记忆系统+标签覆盖率 ──
        print(f"{Color.CYAN}── 5. 记忆系统+标签覆盖 ──{Color.RESET}")
        try:
            if c.memory:
                stats = c.memory.get_stats()
                total = stats.get("total", 0)
                active = stats.get("active", 0)

                # 检查label_snapshot覆盖率
                has_label = 0
                no_label = 0
                if hasattr(c.memory, 'memories') and c.memory.memories:
                    for m in c.memory.memories:
                        if hasattr(m, 'label_snapshot') and m.label_snapshot:
                            has_label += 1
                        else:
                            no_label += 1
                    coverage = has_label / len(c.memory.memories) * 100 if c.memory.memories else 0
                else:
                    coverage = 0

                ok(f"记忆系统", f"总{total} 活跃{active}")
                if has_label > 0:
                    ok(f"标签覆盖率", f"{has_label}/{has_label+no_label} ({coverage:.0f}%)")
                elif no_label > 0:
                    warn(f"标签覆盖率", f"0/{no_label} (0%) — 旧记忆无标签")
                else:
                    print(f"  {Color.DIM}  (无记忆数据){Color.RESET}")

                # 检查共振检索
                if hasattr(c.memory, '_last_top_memories'):
                    ok("共振检索属性", "_last_top_memories 已暴露")
                else:
                    fail("共振检索属性缺失", "_last_top_memories 不存在")
            else:
                fail("记忆系统未初始化")
        except Exception as e:
            fail("记忆系统异常", str(e)[:60])

        # ── 6. 卦象系统 ──
        print(f"{Color.CYAN}── 6. 卦象系统 ──{Color.RESET}")
        try:
            if c.hexagram_tracker:
                state = c.hexagram_tracker.update_by_time()
                hex_name = state.get("current", {}).get("name", "?") if isinstance(state, dict) else "?"
                ok(f"卦象更新", f"当前={hex_name}")

                if c.hexagram_expression:
                    ok("卦象感知生成器", "已初始化")
                else:
                    warn("卦象感知生成器", "未初始化(LLM生成需API)")
            else:
                warn("卦象系统未启用", "hexagram_tracker=None")
        except Exception as e:
            fail("卦象系统异常", str(e)[:60])

        # ── 7. PSI引擎 ──
        print(f"{Color.CYAN}── 7. PSI引擎 ──{Color.RESET}")
        try:
            if c.psi:
                stats = c.psi.get_stats()
                dims = {k: round(v, 2) for k, v in stats.items() if isinstance(v, (int, float))}
                ok(f"PSI引擎", f"帧#{stats.get('consciousness_frame', 0)} {dims}")
            else:
                warn("PSI引擎未初始化")
        except Exception as e:
            fail("PSI引擎异常", str(e)[:60])

        # ── 8. 其他核心子系统 ──
        print(f"{Color.CYAN}── 8. 其他核心子系统 ──{Color.RESET}")
        subsystems = [
            ("认知路由器", "cognitive_router"),
            ("体细胞系统", "somatic_cells"),
            ("弧光系统", "arc_light"),
            ("自由意志", "free_will"),
            ("成长扫描", "growth"),
            ("记忆编译", "memory_compiler"),
            ("观察者", "observer"),
        ]
        for label, attr in subsystems:
            obj = getattr(c, attr, None)
            if obj is not None:
                ok(label, "存活")
            else:
                warn(label, "未初始化")

        # ── 汇总 ──
        print()
        for line in results:
            print(line)
        print()
        total = pass_count + fail_count + warn_count
        print(f"{Color.CYAN}═══ 诊断结果: {Color.GREEN}{pass_count}✅{Color.RESET} "
              f"{Color.YELLOW}{warn_count}⚠️{Color.RESET} "
              f"{Color.RED}{fail_count}❌{Color.RESET} "
              f"{Color.DIM}/ {total}项{Color.RESET}")
        if fail_count == 0 and warn_count == 0:
            print(f"{Color.GREEN}全部系统健康运转 ✓{Color.RESET}")
        elif fail_count == 0:
            print(f"{Color.YELLOW}核心系统正常，部分子系统未初始化（可能未配置）{Color.RESET}")
        else:
            print(f"{Color.RED}有 {fail_count} 个系统失败，需排查{Color.RESET}")
        print()

    def _print_help(self):
        print(f"{Color.DIM}─── 命令 ───{Color.RESET}")
        print(f"  {Color.CYAN}/help{Color.RESET}              显示帮助")
        print(f"  {Color.CYAN}/status{Color.RESET}            查看状态")
        print(f"  {Color.CYAN}/psi{Color.RESET}               查看内在状态")
        print(f"  {Color.CYAN}/diary auto{Color.RESET}        自动写日记")
        print(f"  {Color.CYAN}/diary write <内容>{Color.RESET} 手动写日记")
        print(f"  {Color.CYAN}/diary read{Color.RESET}        查看日记")
        print(f"  {Color.CYAN}/growth scan{Color.RESET}       扫描新行为")
        print(f"  {Color.CYAN}/growth stats{Color.RESET}      成长统计")
        print(f"  {Color.CYAN}/memory{Color.RESET}            查看记忆")
        print(f"  {Color.CYAN}/memory add <内容>{Color.RESET}  添加记忆")
        print(f"  {Color.CYAN}/memory stats{Color.RESET}       记忆统计")
        print(f"  {Color.CYAN}/entities{Color.RESET}           查看实体图")
        print(f"  {Color.CYAN}/events{Color.RESET}             查看事件轨迹")
        print(f"  {Color.CYAN}/cells{Color.RESET}              查看体细胞")
        print(f"  {Color.CYAN}/feedback{Color.RESET}           查看活体约束层")
        print(f"  {Color.CYAN}/obs{Color.RESET}               观察者调试面板")
        print(f"  {Color.CYAN}/snap{Color.RESET}              快照与版本回退")
        print(f"  {Color.CYAN}/daemon{Color.RESET}            守护进程状态")
        print(f"  {Color.CYAN}/daemon run{Color.RESET}        手动执行一轮")
        print(f"  {Color.CYAN}/daemon vitals{Color.RESET}     查看生命体征")
        print(f"  {Color.CYAN}/reflect{Color.RESET}            长在线思考系统状态")
        print(f"  {Color.CYAN}/reflect run{Color.RESET}        手动触发每日反思")
        print(f"  {Color.CYAN}/reflect diary{Color.RESET}      查看知觉日记")
        print(f"  {Color.CYAN}/reflect want{Color.RESET}       查看想说的话")
        print(f"  {Color.CYAN}/reflect trigger{Color.RESET}    手动检查PSI压力")
        print(f"  {Color.CYAN}/route{Color.RESET}             认知路由统计")
        print(f"  {Color.CYAN}/route stats{Color.RESET}       路由详细统计")
        print(f"  {Color.CYAN}/route on|off{Color.RESET}      开关路由层")
        print(f"  {Color.CYAN}/plugin{Color.RESET}            插件管理")
        print(f"  {Color.CYAN}/plugin on|off <name>{Color.RESET} 开关插件")
        print(f"  {Color.CYAN}/roadmap{Color.RESET}           自研路线图")
        print(f"  {Color.CYAN}/roadmap list{Color.RESET}      列出所有idea")
        print(f"  {Color.CYAN}/roadmap add <描述>{Color.RESET} 添加需求")
        print(f"  {Color.CYAN}/compile{Color.RESET}            记忆编译层")
        print(f"  {Color.CYAN}/compile run{Color.RESET}        手动编译")
        print(f"  {Color.CYAN}/compile lint{Color.RESET}       健康检查")
        print(f"  {Color.CYAN}/compile stats{Color.RESET}      编译统计")
        print(f"  {Color.CYAN}/topic{Color.RESET}              主动话题")
        print(f"  {Color.CYAN}/topic gen{Color.RESET}          生成话题")
        print(f"  {Color.CYAN}/topic next{Color.RESET}         取下一条")
        print(f"  {Color.CYAN}/topic peek{Color.RESET}         预览话题")
        print(f"  {Color.CYAN}/skill list{Color.RESET}          技能列表")
        print(f"  {Color.CYAN}/skill info <名>{Color.RESET}     技能详情")
        print(f"  {Color.CYAN}/skill disable <名>{Color.RESET}  禁用技能")
        print(f"  {Color.CYAN}/skill enable <名>{Color.RESET}   启用技能")
        print(f"  {Color.CYAN}/skill remove <名>{Color.RESET}   删除T2/T3技能")
        print(f"  {Color.CYAN}/skill{Color.RESET}              技能自学习")
        print(f"  {Color.CYAN}/skill eval{Color.RESET}         评估回复")
        print(f"  {Color.CYAN}/skill learn{Color.RESET}        自学习循环")
        print(f"  {Color.CYAN}/skill status{Color.RESET}       自学习状态")
        print(f"  {Color.CYAN}/publish{Color.RESET}            代码发布与核验")
        print(f"  {Color.CYAN}/publish pending{Color.RESET}    待核验列表")
        print(f"  {Color.CYAN}/publish review{Color.RESET}     核验详情")
        print(f"  {Color.CYAN}/publish approve{Color.RESET}    批准核验")
        print(f"  {Color.CYAN}/publish reject{Color.RESET}     驳回核验")
        print(f"  {Color.CYAN}/group{Color.RESET}              群聊管理")
        print(f"  {Color.CYAN}/group status{Color.RESET}       群聊状态")
        print(f"  {Color.CYAN}/group members{Color.RESET}     群成员列表")
        print(f"  {Color.CYAN}/router{Color.RESET}             插件路由器")
        print(f"  {Color.CYAN}/router status{Color.RESET}      路由器状态")
        print(f"  {Color.CYAN}/router route{Color.RESET}       路由决策测试")
        print(f"  {Color.CYAN}/audit{Color.RESET}              回执审计")
        print(f"  {Color.CYAN}/audit status{Color.RESET}      审计统计")
        print(f"  {Color.CYAN}/audit recent{Color.RESET}      最近记录")
        print(f"  {Color.CYAN}/boundary{Color.RESET}           边界硬拦截")
        print(f"  {Color.CYAN}/boundary check{Color.RESET}     检查文本")
        print(f"  {Color.CYAN}/template{Color.RESET}            插件模板填充")
        print(f"  {Color.CYAN}/template list{Color.RESET}      可用模板")
        print(f"  {Color.CYAN}/template create{Color.RESET}    创建插件")
        print(f"  {Color.CYAN}/clear{Color.RESET}             清空对话")
        print(f"  {Color.CYAN}/save{Color.RESET}              保存对话")
        print(f"  {Color.CYAN}/config{Color.RESET}            查看配置")
        print(f"  {Color.CYAN}/news{Color.RESET}              手动推送新闻")
        print(f"  {Color.CYAN}/stock{Color.RESET}             股票盯盘")
        print(f"  {Color.CYAN}/stock sh600664{Color.RESET}     查单只股票")
        print(f"  {Color.CYAN}/stock alert{Color.RESET}        检查目标价告警")
        print(f"  {Color.CYAN}/free{Color.RESET}              自由框架状态")
        print(f"  {Color.CYAN}/free curiosity{Color.RESET}    好奇心队列")
        print(f"  {Color.CYAN}/free add <topic>{Color.RESET}  加入好奇心")
        print(f"  {Color.CYAN}/compress{Color.RESET}           压缩器状态")
        print(f"  {Color.CYAN}/lint [dir]{Color.RESET}         写后自检")
        print(f"  {Color.CYAN}/checkpoint info{Color.RESET}    检查点信息")
        print(f"  {Color.CYAN}/checkpoint save{Color.RESET}    手动保存检查点")
        print(f"  {Color.CYAN}/checkpoint restore{Color.RESET} 恢复检查点")
        print(f"  {Color.CYAN}/provider{Color.RESET}           模型Provider信息")
        print(f"  {Color.CYAN}/schedule <描述>{Color.RESET}    自然语言创建定时任务")
        print(f"  {Color.CYAN}/schedule list{Color.RESET}     列出定时任务")
        print(f"  {Color.CYAN}/bgplugin status{Color.RESET}   后台插件状态")
        print(f"  {Color.CYAN}/bgplugin start{Color.RESET}    启动所有插件")
        print(f"  {Color.CYAN}/diag{Color.RESET}              隐藏系统深度诊断")
        print(f"  {Color.CYAN}/exit{Color.RESET}              退出（自动保存）")

    def _print_welcome(self):
        cat = r"""
  /\_/\
 ( o.o )
  > ^ <
"""
        print(f"{Color.PINK}{cat}{Color.RESET}")
        print(f"  {Color.BOLD}知乐 · 本地运行器{Color.RESET}")
        print(f"  {Color.DIM}Phase 3 · 有灵魂了{Color.RESET}")
        print(f"  {Color.DIM}DNA {self.dna.get_dna_version()} | "
              f"模型 {self.llm.model}{Color.RESET}")
        if self.memory:
            stats = self.memory.get_stats()
            if stats['active'] > 0:
                print(f"  {Color.DIM}记忆: {stats['active']}条{Color.RESET}", end="")
        if self.psi:
            psi_stats = self.psi.get_stats()
            # 显示最需要关注的需求
            low_needs = [name for name, status in psi_stats["needs"].items()
                         if "赤字" in status]
            if low_needs:
                print(f"  {Color.RED}PSI赤字: {', '.join(low_needs)}{Color.RESET}",
                      end="")
            else:
                print(f"  {Color.DIM}PSI: 正常{Color.RESET}", end="")
            print(f"  {Color.DIM}意识帧: {psi_stats['consciousness_frame']}{Color.RESET}")
        print(f"\n  {Color.DIM}─────────────────────{Color.RESET}")
        print(f"  {Color.DIM}输入消息开始聊天，/help 查看命令{Color.RESET}")
