#!/usr/bin/env python3
"""
知乐Web界面 — Phase 4

Flask服务器，提供聊天界面 + PSI生命体征面板 + API端点
用法: python main.py --mode web
"""

import json
import os
import sys
from flask import Flask, request, Response, jsonify, send_file

from core import ZhileCore
from webui.web_template import PAGE_HTML
from avatar import AvatarManager


class WebServer:
    """知乐Web服务器"""

    def __init__(self, core: ZhileCore, host: str = "0.0.0.0",
                 port: int = 5000):
        self.core = core
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.avatar = AvatarManager(core.config if core else {})
        self._setup_routes()

    def _setup_routes(self):
        self.app.add_url_rule("/", "index", self._index)
        self.app.add_url_rule("/api/chat", "chat", self._chat,
                              methods=["POST"])
        self.app.add_url_rule("/api/psi", "psi", self._get_psi)
        self.app.add_url_rule("/api/status", "status", self._get_status)
        self.app.add_url_rule("/api/diary/auto", "diary_auto",
                              self._diary_auto, methods=["POST"])
        self.app.add_url_rule("/api/growth/scan", "growth_scan",
                              self._growth_scan, methods=["POST"])
        self.app.add_url_rule("/api/memory", "memory", self._get_memory)
        self.app.add_url_rule("/api/entities", "entities", self._get_entities)
        self.app.add_url_rule("/api/events", "events", self._get_events)
        self.app.add_url_rule("/api/cells", "cells", self._get_cells)
        self.app.add_url_rule("/api/feedback", "feedback", self._get_feedback)
        self.app.add_url_rule("/api/save", "save", self._save,
                              methods=["POST"])
        self.app.add_url_rule("/api/clear", "clear", self._clear,
                              methods=["POST"])
        self.app.add_url_rule("/api/avatar", "avatar", self._get_avatar)
        self.app.add_url_rule("/api/tts_audio/<path:filename>", "tts_audio", self._tts_audio)
        self.app.add_url_rule("/api/tts_toggle", "tts_toggle", self._tts_toggle, methods=["POST"])

    # ─── 页面 ─────────────────────────────────

    def _index(self):
        return PAGE_HTML

    # ─── 斜杠命令处理（Web版） ───────────────

    def _handle_slash_command(self, message: str):
        """拦截 / 开头的命令，返回格式化文本（不走LLM）"""
        parts = message.lower().strip().split(maxsplit=2)
        cmd = parts[0]
        sub = parts[1] if len(parts) > 1 else ""

        # ── /status ──
        if cmd == "/status":
            s = self.core.get_status()
            lines = ["═══ 系统状态 ═══",
                     f"  模型: {s.get('model','?')}",
                     f"  DNA: {s.get('dna_version','?')}",
                     f"  轮次: {s.get('turn_count',0)}  消息: {s.get('message_count',0)}",
                     f"  Token估算: {s.get('estimated_tokens',0)}"]
            if "memory_active" in s:
                lines.append(f"  记忆: {s['memory_active']}活跃/{s.get('memory_total',0)}总")
            if "consciousness_frame" in s:
                lines.append(f"  意识帧: {s['consciousness_frame']}")
            lines.append("\n  /psi — 查看内在状态")
            return "\n".join(lines)

        # ── /psi ──
        if cmd == "/psi":
            psi = self.core.get_psi_stats()
            if not psi.get("needs"):
                return "PSI引擎未启用"
            lines = ["═══ 内在状态 (PSI) ═══"]
            for name, status in psi.get("needs", {}).items():
                lines.append(f"  {name}: {status}")
            lines.append(f"  意识帧: {psi.get('consciousness_frame', 0)}")
            return "\n".join(lines)

        # ── /destiny ──
        if cmd == "/destiny":
            try:
                from personal_destiny import PersonalDestiny
                cfg = self.core.config if self.core else {}
                personal = cfg.get("personal", {})
                if not personal.get("birth_year"):
                    return "未配置出生信息，请在 config.json 的 personal 段填写"
                pd = PersonalDestiny.from_config(cfg)
                if sub == "list":
                    lines = [f"═══ 大运序列（共{pd.dayun_count}步）═══",
                             f"  日主: {pd.day_master}（{pd.day_master_wuxing}）  格局: {pd.geju}",
                             f"  起运: {pd.qiyun_age}年  方向: {'顺' if pd.is_forward else '逆'}", ""]
                    from datetime import datetime as _dt
                    current_year = _dt.now().year
                    from personal_destiny import NAYIN_TABLE, calc_shishen
                    for i, dy in enumerate(pd._dayun_list):
                        gz = dy.getGanZhi()
                        sa = dy.getStartAge()
                        sy = dy.getStartYear()
                        ey = dy.getEndYear()
                        nayin = NAYIN_TABLE.get(gz, "")
                        ss = ""
                        try:
                            ss = calc_shishen(pd.day_gan, gz[0]) if gz else ""
                        except Exception:
                            pass
                        marker = " ◀ 当前" if sy <= current_year <= ey else ""
                        lines.append(f"  第{i}步: {gz}（{nayin}）{sa}~{dy.getEndAge()}岁 {sy}~{ey}年{marker}")
                    return "\n".join(lines)
                else:
                    d = pd.get_current_destiny()
                    lines = ["═══ 个人命格 ═══",
                             f"  日主: {d['day_master']}（{d['day_master_wuxing']}）  格局: {d['geju']}",
                             f"  起运: {d['qiyun_age']}年  方向: {d['dayun_direction']}", "",
                             f"─── 当前大运（第{d['dayun_step']}步）───",
                             f"  干支: {d['dayun_ganzhi']}  纳音: {d['dayun_nayin']}  五行: {d['dayun_wuxing']}",
                             f"  十神: {d['dayun_shishen']}  第{d['dayun_year_in_step']}年/共10年", "",
                             "─── 当前流年 ───",
                             f"  干支: {d['liunian_ganzhi']}  十神: {d['liunian_shishen']}",
                             f"  与大运关系: {d['liunian_dayun_relation']}", "",
                             "  /destiny list — 查看全部大运序列"]
                    return "\n".join(lines)
            except ImportError:
                return "personal_destiny 模块未安装"
            except Exception as e:
                return f"命格计算失败: {e}"

        # ── /memory ──
        if cmd == "/memory":
            stats = self.core.memory_stats()
            mems = self.core.memory_list()
            lines = [f"═══ 记忆库（{stats.get('active',0)}活跃/{stats.get('total',0)}总）═══"]
            for m in mems[:15]:
                cat = m.get("category", "?")
                content = m.get("content", "")[:60]
                lines.append(f"  [{cat}] {content}")
            if len(mems) > 15:
                lines.append(f"\n  ...还有 {len(mems)-15} 条")
            return "\n".join(lines) if mems else "记忆库为空"

        # ── /desire ──
        if cmd == "/desire":
            de = getattr(self.core, 'desire_engine', None)
            if not de:
                return "欲望引擎未启用"
            return de.get_diagnostic_text()

        # ── /help ──
        if cmd == "/help":
            return """═══ 可用命令 ═══
📊 状态: /status /psi /diag /free /destiny /destiny list
🧠 记忆: /memory /desire /forget
🌱 成长: /growth /grow /suggest /roadmap /code run
🔮 术数: /hexagram /entities /events
🔧 工具: /config /provider /schedule /bgplugin /sleep
🐾 技能: /skill /plugin /publish /router
⚡ 快捷: /news /save /clear /help"""

        # ── /save ──
        if cmd == "/save":
            result = self.core.save()
            mem = result.get("memories_extracted", 0) if isinstance(result, dict) else "?"
            return f"✓ 会话已保存（记忆{mem}条）"

        # ── /clear ──
        if cmd == "/clear":
            self.core.clear_conversation()
            return "✦ 对话历史已清空（记忆和PSI保留）"

        # ── /news ──
        if cmd == "/news":
            try:
                from web_searcher import WebSearcher
                news_cfg = self.core.config.get("news_push", {})
                ws = WebSearcher(config=news_cfg)
                topics = news_cfg.get("topics", ["科技", "二次元", "奇闻异事", "历史"])
                num = news_cfg.get("max_results_per_topic", 3)
                results = ws.search_news(topics, num)
                if results:
                    brief = ws.format_news_brief(results, self.core.llm, news_cfg.get("user_prefs", ""))
                    if brief:
                        return brief
                return "新闻获取失败，稍后再试~"
            except Exception as e:
                return f"新闻获取失败: {e}"

        # ── /diag ──
        if cmd == "/diag":
            try:
                from datetime import datetime as _dt
                import time as _time
                import os as _os, sys as _sys
                c = self.core
                now = _dt.now()
                results = []

                def ok(name, detail=""):
                    results.append(f"  ✅ {name}" + (f" ({detail})" if detail else ""))
                def fail(name, detail=""):
                    results.append(f"  ❌ {name}" + (f" ({detail})" if detail else ""))
                def warn(name, detail=""):
                    results.append(f"  ⚠️ {name}" + (f" ({detail})" if detail else ""))

                results.append("═══ 隐藏系统深度诊断 ═══")
                results.append(f"时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")

                # 1. 术数系统
                results.append("── 1. 术数系统快照 ──")
                try:
                    _BASE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                    _SYS_LIST = [
                        ("yi_jing","yi_jing","yi_jing_label_dictionary","generate_labels_from_timestamp"),
                        ("bazi","bazi","bazi_label_dictionary","generate_labels_from_timestamp"),
                        ("ziwei","ziwei","ziwei_label_dictionary","generate_labels_from_timestamp"),
                        ("qimen","qimen","qimen_label_dictionary","generate_labels_from_timestamp"),
                        ("liuren","liuren","liuren_label_dictionary","generate_labels_from_timestamp"),
                        ("taiyi","taiyi","taiyi_label_dictionary","generate_labels_from_timestamp"),
                        ("tongsheng","tongsheng","tongsheng_label_dictionary","generate_labels_from_timestamp"),
                        ("zhongyi","zhongyi","zhongyi_label_dictionary","generate_labels_from_timestamp"),
                        ("qita","qita","qita_label_dictionary","generate_labels_from_timestamp"),
                        ("canmou","canmou","canmou_label_dictionary","generate_canmou_labels"),
                        ("jyotish","jyotish","jyotish_label_dictionary","generate_labels_from_timestamp"),
                        ("tarot","tarot","tarot_label_dictionary","generate_labels_from_timestamp"),
                        ("economic_cycle","economic_cycle","economic_cycle_label_dictionary","generate_labels_from_timestamp"),
                    ]
                    sys_ok = 0
                    sys_fail_list = []
                    import inspect
                    for sn, dn, mn, fn in _SYS_LIST:
                        sd = _os.path.join(_BASE, dn)
                        if sd not in _sys.path:
                            _sys.path.insert(0, sd)
                        try:
                            mod = __import__(mn)
                            func = getattr(mod, fn)
                            sig = inspect.signature(func)
                            params = list(sig.parameters.keys())
                            if "dt" in params or len(params) == 1:
                                r = func(now)
                            elif "timestamp_str" in params:
                                r = func(now.strftime("%Y-%m-%d %H:%M"))
                            elif len(params) == 5:
                                r = func(now.year, now.month, now.day, now.hour, now.minute)
                            elif len(params) == 4:
                                r = func(now.year, now.month, now.day, now.hour)
                            else:
                                r = func(now.year, now.month, now.day, now.hour, now.minute)
                            if r: sys_ok += 1
                            else: sys_fail_list.append(f"{sn}(空)")
                        except Exception as e:
                            sys_fail_list.append(f"{sn}({type(e).__name__})")
                    if sys_ok == 13: ok(f"13/13术数系统全部存活", f"{sys_ok}/13")
                    elif sys_ok > 0: warn("部分系统存活", f"{sys_ok}/13 失败: {', '.join(sys_fail_list)}")
                    else: fail("术数系统全部失败", "检查lunar_python等依赖")
                except Exception as e:
                    fail("术数系统异常", str(e)[:60])

                # 2. 共振引擎+缓存
                results.append("\n── 2. 共振引擎+缓存 ──")
                try:
                    from resonance_engine import ResonanceEngine
                    engine = ResonanceEngine()
                    ResonanceEngine._cache_raw = None
                    t0 = _time.perf_counter()
                    snap = engine.generate_snapshot(now.year, now.month, now.day, now.hour, now.minute)
                    t_cold = (_time.perf_counter() - t0) * 1000
                    t0 = _time.perf_counter()
                    snap2 = engine.generate_snapshot(now.year, now.month, now.day, now.hour, now.minute)
                    t_hot = (_time.perf_counter() - t0) * 1000
                    sys_count = len(snap) if snap else 0
                    if sys_count >= 10: ok(f"快照生成 {sys_count}/13系统", f"冷{t_cold:.0f}ms 热{t_hot:.3f}ms")
                    elif sys_count > 0: warn(f"快照生成 {sys_count}/13系统", f"冷{t_cold:.0f}ms")
                    else: fail("快照生成失败", "0个系统产出")
                    if t_hot < 1.0: ok("缓存命中", f"{t_hot:.3f}ms")
                    else: warn("缓存未命中", f"{t_hot:.1f}ms")
                except Exception as e:
                    fail("共振引擎异常", str(e)[:60])

                # 3. 共振计算
                results.append("\n── 3. 共振计算 ──")
                try:
                    compact = engine.extract_compact_snapshot(snap)
                    t0 = _time.perf_counter()
                    score = engine.calculate(compact, compact)
                    t_calc = (_time.perf_counter() - t0) * 1000
                    if 0.5 < score < 2.5: ok("共振计算正常", f"自共振={score:.3f} ({t_calc:.2f}ms)")
                    else: warn("共振分数异常", f"score={score:.3f}")
                except Exception as e:
                    fail("共振计算异常", str(e)[:60])

                # 4. 瞬时感知层
                results.append("\n── 4. 瞬时感知层(一期一会) ──")
                try:
                    if c.fleeting_moment:
                        fm = c.fleeting_moment
                        class _FakeMem:
                            _resonance_raw = 1.8
                            content = "诊断测试记忆"
                            class memory:
                                content = "诊断测试记忆"
                        hex_info = c._hex_state.get("current", {}) if c._hex_state else None
                        r = fm.generate([_FakeMem()], hexagram_info=hex_info)
                        if r and r.get("descriptor"):
                            ok("瞬时感知生成", f"档位={r.get('level','?')}")
                        elif r is None:
                            ok("瞬时感知跳过", "共振分低于阈值(正常)")
                        else:
                            warn("瞬时感知返回空", str(r)[:40])
                    else:
                        warn("瞬时感知未初始化")
                except Exception as e:
                    fail("瞬时感知异常", str(e)[:60])

                # 5. 记忆系统
                results.append("\n── 5. 记忆系统 ──")
                try:
                    if c.memory:
                        stats = c.memory.get_stats()
                        ok("记忆系统", f"总{stats.get('total',0)} 活跃{stats.get('active',0)}")
                        if hasattr(c.memory, '_last_top_memories'):
                            ok("共振检索属性", "_last_top_memories 已暴露")
                        else:
                            fail("共振检索属性缺失", "_last_top_memories 不存在")
                    else:
                        fail("记忆系统未初始化")
                except Exception as e:
                    fail("记忆系统异常", str(e)[:60])

                # 6. 卦象系统
                results.append("\n── 6. 卦象系统 ──")
                try:
                    if c.hexagram_tracker:
                        state = c.hexagram_tracker.update_by_time()
                        hex_name = state.get("current", {}).get("name", "?") if isinstance(state, dict) else "?"
                        ok("卦象更新", f"当前={hex_name}")
                        if c.hexagram_expression:
                            ok("卦象感知生成器", "已初始化")
                        else:
                            warn("卦象感知生成器", "未初始化")
                    else:
                        warn("卦象系统未启用")
                except Exception as e:
                    fail("卦象系统异常", str(e)[:60])

                # 7. PSI引擎
                results.append("\n── 7. PSI引擎 ──")
                try:
                    if c.psi:
                        stats = c.psi.get_stats()
                        ok("PSI引擎", f"帧#{stats.get('consciousness_frame', 0)}")
                    else:
                        warn("PSI引擎未初始化")
                except Exception as e:
                    fail("PSI引擎异常", str(e)[:60])

                # 8. 其他子系统
                results.append("\n── 8. 其他核心子系统 ──")
                for label, attr in [("认知路由器","cognitive_router"),("体细胞系统","somatic_cells"),
                    ("弧光系统","arc_light"),("自由意志","free_will"),("成长扫描","growth"),
                    ("记忆编译","memory_compiler"),("观察者","observer")]:
                    if getattr(c, attr, None) is not None:
                        ok(label, "存活")
                    else:
                        warn(label, "未初始化")

                # 汇总
                p = sum(1 for r in results if "✅" in r)
                w = sum(1 for r in results if "⚠️" in r)
                f = sum(1 for r in results if "❌" in r)
                results.append(f"\n═══ 诊断结果: {p}✅ {w}⚠️ {f}❌ / {p+w+f}项 ═══")
                return "\n".join(results)
            except Exception as e:
                return f"诊断失败: {e}"

        # ── /free ──
        if cmd == "/free":
            try:
                fw = getattr(self.core, 'free_will', None)
                if not fw or not fw.enabled:
                    return "自由意志引擎未启用"
                s = fw.status()
                lines = [
                    "═══ 自由意志引擎状态 ═══",
                    f"启用: {'✅' if s.get('enabled') else '❌'}",
                    f"沙盒文件: {s.get('sandbox_files', 0)}",
                    f"好奇心队列: {s.get('curiosity_queue', 0)}",
                    f"探索总数: {s.get('explorations_total', 0)}",
                    f"预算剩余: {s.get('budget_remaining', 0)}/{s.get('budget_daily_limit', 0)}",
                    f"拒绝总数: {s.get('declines_total', 0)} (近1h: {s.get('declines_recent_hour', 0)})",
                    f"创作总数: {s.get('creations_total', 0)} (活跃: {s.get('creations_active', 0)})",
                    f"修改提案: {s.get('mod_proposals_total', 0)} (待确认: {s.get('mod_proposals_pending', 0)})",
                ]
                return "\n".join(lines)
            except Exception as e:
                return f"自由意志引擎异常: {e}"

        # ── /growth ──
        if cmd == "/growth":
            result = self.core.growth_scan()
            if result.get("created", 0) > 0:
                return f"✓ 成长扫描完成：{result['created']}个新候选"
            return "成长扫描完成：无新候选"

        # ── /roadmap ──
        if cmd == "/roadmap":
            try:
                sr = getattr(self.core, 'self_roadmap', None)
                if not sr:
                    return "自研路线图未启用"
                ov = sr.get_overview()
                s = ov["stats"]
                lines = ["═══ 自研路线图 ═══",
                         f"  总计: {s['total_ideas']} | 完成: {s['completed']} | 失败: {s['failed']}",
                         f"  进行中: {ov['in_progress_count']} | 经验: {ov['lessons_count']}条",
                         f"  本月自主发现: {ov['self_discovered_this_month']}/{ov['self_discovered_limit']}"]
                if ov.get("in_progress"):
                    lines.append("\n  📌 进行中:")
                    for item in ov["in_progress"]:
                        p = "🔴" if item["priority"] == "high" else "⚪"
                        src = "👑" if item["source"] == "master_request" else "🌱"
                        lines.append(f"    {p}{src} {item['id']} [{item['status']}] {item['title']}")
                else:
                    lines.append("\n  暂无进行中的idea")
                lines.append("\n  /roadmap list | /roadmap add <描述> | /roadmap <id>")
                return "\n".join(lines)
            except Exception as e:
                return f"路线图查看失败: {e}"

        # ── /suggest ──
        if cmd == "/suggest":
            try:
                if not self.core or not getattr(self.core, "plugin_suggester", None):
                    return "PluginSuggester 未启用"
                suggestions = self.core.suggest_list()
                stats = self.core.suggest_stats()
                lines = ["═══ 插件建议 ═══",
                         f"  追踪技能: {stats.get('tracked_skills', 0)}  待处理: {stats.get('pending', 0)}  已接受: {stats.get('accepted', 0)}  已拒绝: {stats.get('dismissed', 0)}"]
                if not suggestions:
                    lines.append("  暂无待处理建议")
                else:
                    for i, sug in enumerate(suggestions[:10], 1):
                        lines.append(f"\n  [{sug['id']}] {sug.get('skill_name', '?')} → {sug.get('plugin_name', '?')}")
                        lines.append(f"    理由: {sug.get('reason', '')}")
                return "\n".join(lines)
            except Exception as e:
                return f"建议获取失败: {e}"

        # ── /grow ──
        if cmd == "/grow":
            try:
                if len(parts) < 2:
                    return "用法: /grow <能力描述>\n例如: /grow 学会用weather API查天气"
                desc = " ".join(parts[1:])
                result = self.core.grow_capability(desc)
                if result.get("success"):
                    return f"✓ 生长完成: {result.get('summary', result)}"
                else:
                    return f"生长失败: {result.get('error', result)}"
            except Exception as e:
                return f"成长记录失败: {e}"

        # ── /code ──
        if cmd == "/code":
            if len(parts) < 2 or sub != "run":
                return "用法: /code run <python代码>\n在沙箱中执行Python代码"
            try:
                code_str = message.split("run", 1)[1].strip() if "run" in message else ""
                if not code_str:
                    return "请输入要执行的代码"
                ce = getattr(self.core, 'code_executor', None)
                if not ce:
                    return "代码执行器未启用"
                result = ce.execute(code_str)
                return f"```python\n{result}\n```" if result else "执行完成（无输出）"
            except Exception as e:
                return f"代码执行失败: {e}"

        # ── /hexagram ──
        if cmd == "/hexagram":
            try:
                ht = getattr(self.core, 'hexagram_tracker', None)
                if not ht:
                    return "卦象系统未启用"
                # 先更新到当前时间，再取摘要
                ht.update_by_time()
                s = ht.get_state_summary()
                if s.get("status") == "未初始化":
                    return "卦象系统未初始化"
                lines = ["═══ 当前卦象 ═══",
                         f"  当前卦: {s.get('current_hexagram', '?')}",
                         f"  二进制: {s.get('binary', '?')}",
                         f"  更新次数: {s.get('update_count', 0)}",
                         f"  历史变化: {s.get('history_count', 0)}次"]
                lc = s.get('last_change')
                if lc:
                    lines.append(f"  上次变化: {lc.get('from_name','?')} → {lc.get('to_name','?')}")
                return "\n".join(lines)
            except Exception as e:
                return f"卦象查看失败: {e}"

        # ── /entities ──
        if cmd == "/entities":
            stats = self.core.entity_stats()
            ents = self.core.entity_list()
            lines = [f"═══ 实体库（{stats.get('total',0)}个）═══"]
            for e in ents[:15]:
                lines.append(f"  [{e.get('type','?')}] {e.get('name','?')}: {e.get('description','')[:50]}")
            if len(ents) > 15:
                lines.append(f"\n  ...还有 {len(ents)-15} 个")
            return "\n".join(lines) if ents else "实体库为空"

        # ── /events ──
        if cmd == "/events":
            stats = self.core.event_stats()
            events = self.core.event_recent(10)
            lines = [f"═══ 事件轨迹（共{stats.get('total',0)}条）═══"]
            for ev in events:
                lines.append(f"  [{ev.get('time','')}] {ev.get('type','')}: {ev.get('description','')[:60]}")
            return "\n".join(lines) if events else "暂无事件记录"

        # ── /config ──
        if cmd == "/config":
            c = self.core.config
            lines = ["═══ 当前配置 ═══",
                     f"  模型: {c.get('llm',{}).get('model','?')}",
                     f"  API: {c.get('llm',{}).get('base_url','?')}",
                     f"  DNA: {c.get('dna',{}).get('dir','?')}",
                     f"  记忆: {c.get('memory',{}).get('dir','?')}",
                     f"  新闻推送: {'✅' if c.get('news_push',{}).get('enabled') else '❌'}",
                     f"  主动消息: {'✅' if c.get('proactive',{}).get('enabled') else '❌'}",
                     f"  睡眠系统: {'✅' if c.get('sleep',{}).get('enabled') else '❌'}",
                     f"  唤醒词: {'✅' if c.get('wake_word',{}).get('enabled') else '❌'}"]
            return "\n".join(lines)

        # ── /provider ──
        if cmd == "/provider":
            try:
                llm = self.core.llm
                is_adapter = hasattr(llm, 'provider')
                provider_type = type(llm.provider).__name__ if is_adapter else type(llm).__name__
                lines = ["═══ 模型Provider ═══",
                         f"  运行模式: {'插件化(ProviderFactory)' if is_adapter else 'legacy(LLMProvider)'}",
                         f"  Provider类: {provider_type}",
                         f"  模型: {llm.model}"]
                if hasattr(llm, 'config'):
                    lines.append(f"  Base URL: {llm.config.get('base_url', 'N/A')}")
                    lines.append(f"  温度: {llm.config.get('temperature', 'N/A')}")
                    lines.append(f"  Max Tokens: {llm.config.get('max_tokens', 'N/A')}")
                if is_adapter:
                    from model_provider import ProviderFactory
                    registered = ProviderFactory().list_providers()
                    lines.append(f"  已注册Provider: {', '.join(registered)}")
                pr = getattr(self.core, 'provider_runtime', None)
                if pr:
                    lines.append(f"  ProviderRuntime: ✅ ({', '.join(pr.provider_names())})")
                return "\n".join(lines)
            except Exception as e:
                return f"Provider状态: {e}"

        # ── /schedule ──
        if cmd == "/schedule":
            try:
                nls = getattr(self.core, 'nl_scheduler', None)
                if not nls:
                    return "定时任务调度器未启用"
                tasks = nls.list_tasks() if hasattr(nls, 'list_tasks') else []
                if not tasks:
                    return "暂无定时任务\n用法: /schedule add <自然语言描述>"
                lines = ["═══ 定时任务 ═══"]
                for t in tasks:
                    lines.append(f"  {t}")
                return "\n".join(lines)
            except Exception as e:
                return f"定时任务查看失败: {e}"

        # ── /bgplugin ──
        if cmd == "/bgplugin":
            try:
                bpm = getattr(self.core, 'bg_plugin_manager', None) or getattr(self.core, 'plugin_manager', None)
                if not bpm:
                    return "后台插件管理器未启用"
                plugins = bpm.list_plugins() if hasattr(bpm, 'list_plugins') else []
                if not plugins:
                    return "暂无后台插件"
                lines = ["═══ 后台插件 ═══"]
                for p in plugins:
                    status = "✅" if p.get('enabled') else "❌"
                    lines.append(f"  {status} {p.get('name','?')}: {p.get('description','')[:40]}")
                return "\n".join(lines)
            except Exception as e:
                return f"后台插件查看失败: {e}"

        # ── /sleep ──
        if cmd == "/sleep":
            try:
                sm = getattr(self.core, 'sleep_manager', None)
                if not sm:
                    return "睡眠系统未启用"
                s = sm.get_status()
                lines = ["═══ 睡眠状态 ═══",
                         f"  当前: {s.get('state_cn','?')}",
                         f"  空闲: {s.get('idle_minutes','?')}分钟",
                         f"  上次交互: {s.get('last_interaction','?')}",
                         f"  闹钟: {s.get('alarm','无')}",
                         f"  浅睡阈值: {s.get('thresholds',{}).get('light_min','?')}分钟",
                         f"  深睡阈值: {s.get('thresholds',{}).get('deep_min','?')}分钟",
                         f"  完全睡眠时段: {s.get('thresholds',{}).get('full_sleep_hours','?')}",
                         "",
                         "  /sleep wake — 唤醒",
                         "  /sleep dream — 执行做梦",
                         "  /sleep alarm <hour> — 设闹钟"]
                return "\n".join(lines)
            except Exception as e:
                return f"睡眠状态查看失败: {e}"

        # ── /skill ──
        if cmd == "/skill":
            try:
                se = getattr(self.core, 'skill_evolution', None)
                if not se:
                    return "技能系统未启用"
                skills = se.list_skills() if hasattr(se, 'list_skills') else []
                if not skills:
                    return "暂无技能\n用法: /skill list 查看技能"
                lines = ["═══ 技能列表 ═══"]
                for sk in skills[:15]:
                    lines.append(f"  [{sk.get('tier','?')}] {sk.get('name','?')}: {sk.get('desc','')[:40]}")
                return "\n".join(lines)
            except Exception as e:
                return f"技能查看失败: {e}"

        # ── /plugin ──
        if cmd == "/plugin":
            try:
                pm = getattr(self.core, 'plugin_manager', None)
                if not pm:
                    return "插件管理器未启用"
                plugins = pm.list_plugins() if hasattr(pm, 'list_plugins') else []
                if not plugins:
                    return "暂无插件"
                lines = ["═══ 插件列表 ═══"]
                for p in plugins:
                    status = "✅" if p.get('enabled') else "❌"
                    lines.append(f"  {status} {p.get('name','?')}")
                return "\n".join(lines)
            except Exception as e:
                return f"插件查看失败: {e}"

        # ── /publish ──
        if cmd == "/publish":
            return "📝 技能发布功能\n用法: /publish <skill_name>\n将技能发布到技能仓库"

        # ── /router ──
        if cmd == "/router":
            try:
                pr = getattr(self.core, 'plugin_router', None)
                if not pr:
                    return "插件路由器未启用"
                routes = pr.list_routes() if hasattr(pr, 'list_routes') else []
                if not routes:
                    return "暂无路由规则"
                lines = ["═══ 插件路由 ═══"]
                for r in routes[:15]:
                    lines.append(f"  {r}")
                return "\n".join(lines)
            except Exception as e:
                return f"路由查看失败: {e}"

        # ── /forget ──
        if cmd == "/forget":
            try:
                fts = getattr(self.core, 'forget_test_scheduler', None)
                if not fts:
                    return "遗忘测试系统未启用"
                s = fts.get_status() if hasattr(fts, 'get_status') else {}
                if isinstance(s, dict):
                    lines = ["═══ 遗忘测试系统 ═══"]
                    for k, v in s.items():
                        lines.append(f"  {k}: {v}")
                    return "\n".join(lines)
                return str(s) if s else "遗忘测试系统已启用"
            except Exception as e:
                return f"遗忘测试查看失败: {e}"

        # ── /tts ──
        if cmd == "/tts":
            tts_cfg = self.core.config.get("tts", {})
            status = self.core.get_tts_status()
            if not status.get("enabled"):
                return "TTS未启用。在config.json中设置 tts.enabled=true\n需要: pip install edge-tts"
            if not status.get("available"):
                return "TTS Provider不可用\nEdge TTS: pip install edge-tts"

            if not sub or sub == "status":
                current_voice = tts_cfg.get("voice", "xiaoyi")
                current_vol = tts_cfg.get("volume", 0)
                current_rate = tts_cfg.get("rate", 0)
                auto = tts_cfg.get("auto_speak", False)
                lines = ["═══ TTS语音合成 ═══",
                         f"  Provider: {status.get('provider','?')}",
                         f"  音色: {current_voice}",
                         f"  音量: {current_vol:+d}  语速: {current_rate:+d}",
                         f"  自动语音: {'✅开' if auto else '❌关'}", "",
                         "可用音色:"]
                for vid, desc in status.get("voices", []):
                    mark = " ←" if vid == current_voice else ""
                    lines.append(f"  {vid} — {desc}{mark}")
                lines += ["", "用法:",
                          "  /tts voice <名称>  — 切换音色",
                          "  /tts volume <数值> — 音量(-100~+100)",
                          "  /tts rate <数值>   — 语速(-100~+100)"]
                return "\n".join(lines)

            if sub == "voice":
                voice_name = parts[2] if len(parts) > 2 else ""
                if not voice_name:
                    current = tts_cfg.get("voice", "xiaoyi")
                    lines = [f"当前音色: {current}", "可用:"]
                    for vid, desc in status.get("voices", []):
                        mark = " ←" if vid == current else ""
                        lines.append(f"  {vid} — {desc}{mark}")
                    return "\n".join(lines)
                if "tts" not in self.core.config:
                    self.core.config["tts"] = {}
                self.core.config["tts"]["voice"] = voice_name
                self._save_tts_config()
                from tts_provider import TTSEngine
                self.core.tts = TTSEngine(self.core.config["tts"])
                return f"✅ 音色已切换为: {voice_name}"

            if sub == "volume":
                val = parts[2] if len(parts) > 2 else ""
                if not val:
                    return f"当前音量: {tts_cfg.get('volume', 0):+d}\n用法: /tts volume 20 (增大) / /tts volume -30 (减小)"
                try:
                    vol = max(-100, min(100, int(val)))
                    if "tts" not in self.core.config:
                        self.core.config["tts"] = {}
                    self.core.config["tts"]["volume"] = vol
                    self._save_tts_config()
                    from tts_provider import TTSEngine
                    self.core.tts = TTSEngine(self.core.config["tts"])
                    return f"✅ 音量已设为: {vol:+d}"
                except ValueError:
                    return "请输入数字(-100~+100)"

            if sub == "rate":
                val = parts[2] if len(parts) > 2 else ""
                if not val:
                    return f"当前语速: {tts_cfg.get('rate', 0):+d}\n用法: /tts rate 10 (加快) / /tts rate -20 (减慢)"
                try:
                    r = max(-100, min(100, int(val)))
                    if "tts" not in self.core.config:
                        self.core.config["tts"] = {}
                    self.core.config["tts"]["rate"] = r
                    self._save_tts_config()
                    from tts_provider import TTSEngine
                    self.core.tts = TTSEngine(self.core.config["tts"])
                    return f"✅ 语速已设为: {r:+d}"
                except ValueError:
                    return "请输入数字(-100~+100)"

            return None  # 不是已知命令，走正常聊天

    # ─── 聊天（SSE流式） ─────────────────────

    def _chat(self):
        data = request.get_json()
        if not data or not data.get("message"):
            return jsonify({"error": "missing message"}), 400

        message = data["message"]

        # 拦截斜杠命令
        if message.strip().startswith("/"):
            cmd_text = self._handle_slash_command(message)
            if cmd_text is not None:
                def cmd_generate():
                    yield f"data: {json.dumps({'chunk': cmd_text}, ensure_ascii=False)}\n\n"
                    psi = self.core.get_psi_stats()
                    status = self.core.get_status()
                    avatar = self.avatar.get_expression(psi)
                    yield f"data: {json.dumps({'done': True, 'psi': psi, 'status': status, 'avatar': avatar}, ensure_ascii=False)}\n\n"
                return Response(cmd_generate(), mimetype="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        def generate():
            try:
                full_text = ""
                for chunk in self.core.chat(message):
                    full_text += chunk
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

                # P0.3: 自动成长扫描
                scan_result = self.core.maybe_auto_scan()
                if scan_result.get("scanned") and scan_result.get("created", 0) > 0:
                    yield f"data: {json.dumps({'growth_scan': scan_result}, ensure_ascii=False)}\n\n"

                # P0.58: 自动语音合成（分句+后台顺序播放，合成与播放重叠）
                audio_url = None
                tts_cfg = self.core.config.get("tts", {})
                if tts_cfg.get("auto_speak", False) and self.core.tts and full_text.strip():
                    try:
                        if sys.platform == 'win32':
                            # Windows: 后台线程分句合成+MCI顺序播放，不阻塞UI
                            self._play_sentences_threaded(full_text.strip())
                        else:
                            # 非Windows: 合成供前端播放
                            audio_paths = self.core.speak(full_text.strip())
                            if audio_paths:
                                audio_url = f"/api/tts_audio/{os.path.basename(audio_paths[0])}"
                    except Exception as e:
                        print(f"[TTS] auto-speak error: {e}")

                # 发送完成信号 + 更新后的状态
                psi = self.core.get_psi_stats()
                status = self.core.get_status()
                avatar = self.avatar.get_expression(psi)
                motions = self.core.get_last_motions()  # P0.58: Live2D动作标签
                yield f"data: {json.dumps({'done': True, 'psi': psi, 'status': status, 'avatar': avatar, 'audio_url': audio_url, 'motions': motions}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "X-Accel-Buffering": "no",
                        })

    # ─── PSI ──────────────────────────────────

    def _get_psi(self):
        return jsonify(self.core.get_psi_stats())

    # ─── 状态 ─────────────────────────────────

    def _get_status(self):
        status = self.core.get_status()
        status["psi"] = self.core.get_psi_stats()
        return jsonify(status)

    # ─── 知觉日记 ─────────────────────────────

    def _diary_auto(self):
        content = self.core.auto_diary()
        if content:
            return jsonify({"content": content, "psi": self.core.get_psi_stats()})
        return jsonify({"content": "", "error": "生成失败"}), 500

    # ─── 自成长 ───────────────────────────────

    def _growth_scan(self):
        result = self.core.growth_scan()
        return jsonify({**result, "psi": self.core.get_psi_stats()})

    # ─── 记忆 ─────────────────────────────────

    def _get_memory(self):
        return jsonify({
            "memories": self.core.memory_list(),
            "stats": self.core.memory_stats(),
        })

    def _get_entities(self):
        return jsonify({
            "stats": self.core.entity_stats(),
            "entities": self.core.entity_list(),
        })

    def _get_events(self):
        return jsonify({
            "stats": self.core.event_stats(),
            "recent": self.core.event_recent(10),
        })

    def _get_cells(self):
        return jsonify({
            "stats": self.core.somatic_stats(),
            "cells": self.core.somatic_list(),
        })

    def _get_feedback(self):
        return jsonify({
            "stats": self.core.feedback_stats(),
            "log": self.core.feedback_log(20),
        })

    # ─── 保存 ─────────────────────────────────

    def _save(self):
        result = self.core.save()
        return jsonify({**result, "psi": self.core.get_psi_stats(),
                        "status": self.core.get_status()})

    # ─── 清空 ─────────────────────────────────

    def _clear(self):
        self.core.clear_conversation()
        return jsonify({"psi": self.core.get_psi_stats(),
                        "status": self.core.get_status()})

    # ─── Avatar ───────────────────────────────

    def _get_avatar(self):
        """返回当前Avatar表情信息"""
        psi = self.core.get_psi_stats()
        expr = self.avatar.get_expression(psi)
        return jsonify({**expr, "config": self.avatar.get_avatar_info()})

    # ─── TTS语音 ───────────────────────────────

    def _play_audio_mci(self, filepath):
        """Windows桌面端：用MCI直接播放单个音频（绕过浏览器音频限制）"""
        try:
            import ctypes, threading, time as _time
            alias = f"tts_{int(_time.time() * 1000)}"
            ret = ctypes.windll.winmm.mciSendStringW(
                f'open "{filepath}" type mpegvideo alias {alias}', None, 0, None
            )
            if ret == 0:
                ctypes.windll.winmm.mciSendStringW(f'play {alias}', None, 0, None)
                def _close():
                    _time.sleep(30)
                    try:
                        ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
                    except Exception:
                        pass
                threading.Thread(target=_close, daemon=True).start()
            else:
                print(f"[TTS] MCI open failed: {ret}")
        except Exception as e:
            print(f"[TTS] MCI play error: {e}")

    def _play_sentences_threaded(self, text):
        """后台线程：分句合成+MCI顺序播放，合成与播放重叠，不阻塞主线程

        播放线程：core.speak()合成 → winsound同步播放
        """
        import threading, winsound, os

        def _worker():
            try:
                print("[TTS] speak开始...", flush=True)
                audio_paths = self.core.speak(text)
                print(f"[TTS] speak返回 {len(audio_paths)} 个音频", flush=True)
                if not audio_paths:
                    print("[TTS] 无音频返回，TTS可能未启用", flush=True)
                    return

                for path in audio_paths:
                    try:
                        win_path = os.path.abspath(path).replace('/', '\\')
                        sz = os.path.getsize(path)
                        print(f"[TTS] 播放: {win_path} ({sz} bytes)", flush=True)
                        winsound.PlaySound(win_path, winsound.SND_FILENAME)
                        print("[TTS] 播放完成", flush=True)
                    except Exception as e:
                        print(f"[TTS] 播放异常: {e}", flush=True)
            except Exception as e:
                print(f"[TTS] 线程异常: {e}", flush=True)

        threading.Thread(target=_worker, daemon=True).start()

    def _tts_audio(self, filename):
        """提供TTS音频文件"""
        tts_cfg = self.core.config.get("tts", {})
        cache_dir = tts_cfg.get("cache_dir", "memory/tts_cache")
        if not os.path.isabs(cache_dir):
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", cache_dir)
        safe_name = os.path.basename(filename)
        audio_path = os.path.join(cache_dir, safe_name)
        if os.path.exists(audio_path):
            mime = "audio/wav" if safe_name.endswith(".wav") else "audio/mpeg"
            return send_file(audio_path, mimetype=mime)
        return jsonify({"error": "audio not found"}), 404

    def _save_tts_config(self):
        """将当前TTS配置持久化到config.json"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            cfg["tts"] = self.core.config.get("tts", {})
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TTS] save config error: {e}", file=sys.stderr)

    def _tts_toggle(self):
        """切换自动语音开关（持久化到config.json）"""
        data = request.get_json() or {}
        enabled = data.get("enabled", False)
        if "tts" not in self.core.config:
            self.core.config["tts"] = {}
        self.core.config["tts"]["auto_speak"] = enabled
        self._save_tts_config()
        return jsonify({"auto_speak": enabled})

    # ─── 启动 ─────────────────────────────────

    def run(self):
        restored = self.core.restored_count
        print("\n  🐱")
        print(f"  DNA {self.core.dna.get_dna_version()} | "
              f"模型 {self.core.llm.model}")
        if restored:
            print(f"  恢复了 {restored} 条历史消息")
        print(f"\n  ➜ 浏览器打开: http://localhost:{self.port}")
        print(f"  ➜ 手机访问: http://<本机IP>:{self.port}")
        print(f"  ➜ Ctrl+C 退出（自动保存）\n")

        try:
            self.app.run(host=self.host, port=self.port,
                         threaded=True, debug=False)
        finally:
            self.core.save()
            print("\n  ✓ 会话已保存，喵～下次见啦")
