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


class WebServer:
    """知乐Web服务器"""

    def __init__(self, core: ZhileCore, host: str = "0.0.0.0",
                 port: int = 5000):
        self.core = core
        self.host = host
        self.port = port
        self.app = Flask(__name__)
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

    # ─── 页面 ─────────────────────────────────

    def _index(self):
        return PAGE_HTML

    # ─── 聊天（SSE流式） ─────────────────────

    def _chat(self):
        data = request.get_json()
        if not data or not data.get("message"):
            return jsonify({"error": "missing message"}), 400

        message = data["message"]

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
                yield f"data: {json.dumps({'done': True, 'psi': psi, 'status': status}, ensure_ascii=False)}\n\n"
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
