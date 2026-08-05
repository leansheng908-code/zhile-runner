#!/usr/bin/env python3
"""
知乐Web界面 — Phase 4

Flask服务器，提供聊天界面 + PSI生命体征面板 + API端点
用法: python main.py --mode web
"""

import json
from flask import Flask, request, Response, jsonify

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
  /status    — 系统状态
  /psi       — 内在状态
  /destiny   — 个人命格（/destiny list 看全部大运）
  /memory    — 记忆库
  /desire    — 思维-表达间隙
  /news      — 有趣新闻
  /diag      — 系统诊断
  /free      — 自由五层
  /save      — 保存会话
  /clear     — 清空对话
  /growth    — 成长扫描"""

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
                ws = WebSearcher()
                result = ws.fetch_interesting_news()
                if result:
                    return result
                return "新闻获取失败，稍后再试~"
            except Exception as e:
                return f"新闻获取失败: {e}"

        # ── /diag ──
        if cmd == "/diag":
            try:
                from observer import Observer
                obs = Observer(self.core)
                report = obs.generate_diagnostic_report()
                return report if report else "诊断报告生成失败"
            except Exception as e:
                return f"诊断失败: {e}"

        # ── /free ──
        if cmd == "/free":
            try:
                from freedom_engine import FreedomEngine
                fe = getattr(self.core, 'freedom_engine', None)
                if not fe:
                    return "自由引擎未启用"
                return fe.get_status_text()
            except Exception as e:
                return f"自由引擎未启用: {e}"

        # ── /growth ──
        if cmd == "/growth":
            result = self.core.growth_scan()
            if result.get("created", 0) > 0:
                return f"✓ 成长扫描完成：{result['created']}个新候选"
            return "成长扫描完成：无新候选"

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
                for chunk in self.core.chat(message):
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

                # P0.3: 自动成长扫描
                scan_result = self.core.maybe_auto_scan()
                if scan_result.get("scanned") and scan_result.get("created", 0) > 0:
                    yield f"data: {json.dumps({'growth_scan': scan_result}, ensure_ascii=False)}\n\n"

                # 发送完成信号 + 更新后的状态
                psi = self.core.get_psi_stats()
                status = self.core.get_status()
                avatar = self.avatar.get_expression(psi)
                yield f"data: {json.dumps({'done': True, 'psi': psi, 'status': status, 'avatar': avatar}, ensure_ascii=False)}\n\n"
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
