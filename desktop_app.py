#!/usr/bin/env python3
"""
知乐桌面应用 — P0.38 Phase 1
用 pywebview 将运行器 Web 界面包装为原生桌面窗口
零额外工具链（仅需 pip install flask pywebview）

架构：
  desktop_app.py 启动
    → 后台线程启动 Flask Web 服务器 (localhost:17891)
    → 主线程打开 pywebview 窗口加载 localhost:17891
    → 关闭窗口 = 退出应用
"""
import sys
import os
import time
import threading
import subprocess
import importlib

# ─── 依赖检查与自动安装 ─────────────────────
def ensure_deps():
    """检查并安装必要依赖"""
    missing = []
    try:
        importlib.import_module("flask")
    except ImportError:
        missing.append("flask")
    try:
        importlib.import_module("webview")
    except ImportError:
        missing.append("pywebview")
    
    if missing:
        print(f"正在安装依赖: {', '.join(missing)}")
        pip_args = [sys.executable, "-m", "pip", "install",
                     "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"] + missing
        result = subprocess.run(pip_args, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"安装失败: {result.stderr}")
            print(f"请手动运行: {sys.executable} -m pip install {' '.join(missing)}")
            sys.exit(1)
        print("依赖安装完成!")

ensure_deps()

import webview  # noqa: E402
from webui.web import WebServer  # noqa: E402
from core import ZhileCore  # noqa: E402

# ─── 配置 ────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
WEB_HOST = "127.0.0.1"
WEB_PORT = 17891  # 固定端口，避免冲突
WINDOW_TITLE = "知乐 · 本地运行器"
WINDOW_SIZE = (960, 700)  # 桌面横屏，侧边栏+聊天区
MIN_SIZE = (400, 600)  # 最小可缩到手机模式

# ─── 启动 Web 服务器（后台线程）─────────────
def start_web_server(core, server):
    """在后台线程中启动 Flask 服务器"""
    try:
        print(f"Web服务器启动: http://{WEB_HOST}:{WEB_PORT}")
        server.run()
    except Exception as e:
        print(f"Web服务器启动失败: {e}")

# ─── 等待服务器就绪 ──────────────────────────
def wait_for_server(url, timeout=15):
    """等待 Web 服务器响应"""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False

# ─── 主入口 ──────────────────────────────────
def main():
    print("=" * 50)
    print("  知乐桌面应用 · P0.38 Phase 1")
    print("=" * 50)

    # 初始化核心（提前到main中，便于退出时保存）
    try:
        core = ZhileCore(CONFIG_FILE, no_restore=False)
        server = WebServer(core, host=WEB_HOST, port=WEB_PORT)
    except Exception as e:
        print(f"初始化失败: {e}")
        input("按回车键退出...")
        sys.exit(1)

    # 启动 Web 服务器线程
    server_thread = threading.Thread(target=start_web_server, args=(core, server), daemon=True)
    server_thread.start()

    # 等待服务器就绪
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    print(f"等待服务器就绪...", end=" ", flush=True)
    if not wait_for_server(url):
        print("失败!")
        print("服务器未能在超时内启动，请检查 config.json 配置")
        input("按回车键退出...")
        sys.exit(1)
    print("就绪!")

    # 打开桌面窗口
    print(f"打开窗口: {WINDOW_TITLE}")
    webview.create_window(
        title=WINDOW_TITLE,
        url=url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_SIZE,
    )
    
    # 启动 pywebview（阻塞，关闭窗口后继续）
    webview.start(debug=False)  # debug=True 可打开开发者工具

    # 窗口已关闭 — 保存会话后退出
    print("窗口已关闭，正在保存会话...")
    try:
        result = core.save()
        memories = result.get("memories_extracted", 0) if isinstance(result, dict) else "?"
        print(f"✓ 会话已保存（记忆{memories}条），喵～下次见啦")
    except Exception as e:
        print(f"保存失败: {e}")
    sys.exit(0)

if __name__ == "__main__":
    main()
