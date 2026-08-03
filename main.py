#!/usr/bin/env python3
"""
知乐·本地运行器 — 主入口
Phase 4: 核心 + CLI + 记忆 + PSI + 成长 + Web界面

用法:
    python main.py                 # CLI模式（默认）
    python main.py --mode web      # Web界面模式
    python main.py --mode web --port 8080
    python main.py --config xxx    # 指定配置文件
    python main.py --no-restore    # 不恢复上次对话
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="知乐·本地运行器")
    parser.add_argument("--mode", default="cli", choices=["cli", "web", "qq"],
                        help="运行模式: cli(终端) web(浏览器) qq(QQ)")
    parser.add_argument("--config", default="config.json",
                        help="配置文件路径 (默认: config.json)")
    parser.add_argument("--no-restore", action="store_true",
                        help="不恢复上次对话历史")
    parser.add_argument("--port", type=int, default=None,
                        help="Web模式端口号 (默认: config中的web.port或5000)")
    args = parser.parse_args()

    # ─── Web模式 ─────────────────────────────
    if args.mode == "web":
        from core import ZhileCore
        from webui.web import WebServer

        try:
            core = ZhileCore(args.config, no_restore=args.no_restore)
        except Exception as e:
            print(f"启动失败: {e}")
            sys.exit(1)

        web_config = core.config.get("web", {})
        host = web_config.get("host", "0.0.0.0")
        port = args.port or web_config.get("port", 5000)

        server = WebServer(core, host=host, port=port)
        server.run()
        return

    # ─── QQ模式 ──────────────────────────────
    if args.mode == "qq":
        from core import ZhileCore
        from webui.qq import QQAdapter

        try:
            core = ZhileCore(args.config, no_restore=args.no_restore)
        except Exception as e:
            print(f"启动失败: {e}")
            sys.exit(1)

        qq_config = core.config.get("qq", {})
        host = qq_config.get("host", "0.0.0.0")
        port = args.port or qq_config.get("port", 6199)

        adapter = QQAdapter(core, host=host, port=port)
        adapter.run()
        return

    # ─── CLI模式 ──────────────────────────────
    from core import ZhileCore
    from cli import CLI

    try:
        core = ZhileCore(args.config, no_restore=args.no_restore)
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)

    if core.restored_count:
        print(f"  恢复了 {core.restored_count} 条历史消息")

    cli = CLI(
        dna_loader=core.dna,
        llm_provider=core.llm,
        context_assembler=core.ctx,
        config=core.config,
        memory_system=core.memory,
        psi_engine=core.psi,
        growth_scanner=core.growth,
        entity_graph=core.entity_graph,
        core=core,
    )
    cli.run()


if __name__ == "__main__":
    main()
