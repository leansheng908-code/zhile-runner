#!/usr/bin/env python3
"""
知乐唤醒词监听器 — P0.69 Phase 2
本地唤醒词检测，纯零API消耗

架构：
  - 优先使用 sherpa-onnx（本地KWS，~50MB RAM，零API）
  - 降级方案：键盘监听（按Enter键模拟唤醒词）
  - 降级方案：定时轮询（无硬件依赖时仅用于测试）

sherpa-onnx 安装：
  pip install sherpa-onnx
  自定义唤醒词模型需训练（参考 sherpa-onnx 官方文档）

唤醒词触发后：
  1. 调用 sleep_manager.wake(reason="wake_word")
  2. 唤醒事件通过回调通知上层
"""

import threading
import time
import sys
from typing import Optional, Callable
from datetime import datetime


class WakeWordListener:
    """唤醒词监听器 — 唯一7×24运行的进程"""

    def __init__(self, sleep_manager, config: dict = None):
        """
        Args:
            sleep_manager: SleepManager实例
            config: wake_word配置字典
        """
        self.sm = sleep_manager
        cfg = config or {}

        self.engine = cfg.get("engine", "auto")  # auto / sherpa / keyboard / none
        self.wake_word = cfg.get("wake_word", "知乐")
        self.model_dir = cfg.get("model_dir", "models/wake_word")

        # sherpa-onnx 相关
        self._sherpa_kws = None
        self._sherpa_available = False

        # 线程
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # 唤醒回调
        self._wake_callbacks: list = []

        # 统计
        self._wake_count = 0
        self._last_wake_time: Optional[str] = None

        # 自动检测可用引擎
        if self.engine == "auto":
            self._detect_engine()

    def _detect_engine(self):
        """自动检测可用的唤醒引擎"""
        # 尝试 sherpa-onnx
        try:
            import sherpa_onnx
            self._sherpa_available = True
            self.engine = "sherpa"
            print(f"🎤 [唤醒词] 使用 sherpa-onnx 引擎", file=sys.stderr)
            return
        except ImportError:
            pass

        # 尝试键盘监听（用于CLI模式）
        try:
            import keyboard
            self.engine = "keyboard"
            print(f"🎤 [唤醒词] 使用键盘监听引擎（按Enter唤醒）", file=sys.stderr)
            return
        except ImportError:
            pass

        # 无可用引擎
        self.engine = "none"
        print(f"🎤 [唤醒词] 无可用引擎（sherpa-onnx/keyboard均未安装），唤醒词功能待激活",
              file=sys.stderr)
        print(f"🎤 [唤醒词] 安装 sherpa-onnx: pip install sherpa-onnx", file=sys.stderr)

    def _init_sherpa(self):
        """初始化 sherpa-onnx 唤醒词检测"""
        try:
            import sherpa_onnx
            from pathlib import Path

            model_path = Path(self.model_dir)
            if not model_path.exists():
                print(f"🎤 [唤醒词] 模型目录不存在: {model_path}", file=sys.stderr)
                print(f"🎤 [唤醒词] 请下载唤醒词模型到该目录", file=sys.stderr)
                return False

            # 查找模型文件
            model_files = list(model_path.glob("*.onnx"))
            if not model_files:
                print(f"🎤 [唤醒词] 模型目录中未找到 .onnx 文件", file=sys.stderr)
                return False

            # 创建KWS实例
            # 注意：具体API取决于sherpa-onnx版本
            # 这里使用通用的keyword spotting接口
            self._sherpa_kws = sherpa_onnx.KeywordSpotter(
                model=str(model_files[0]),
                tokens=str(model_path / "tokens.txt") if (model_path / "tokens.txt").exists() else "",
                keywords_file=str(model_path / "keywords.txt") if (model_path / "keywords.txt").exists() else "",
                num_threads=1,
                max_active_paths=4,
                keywords_score=1.0,
                keywords_threshold=0.5,
                decoding_method="greedy_search",
            )

            # 创建音频流
            self._sherpa_stream = self._sherpa_kws.create_stream()

            # 尝试打开麦克风
            try:
                import sounddevice as sd
                self._audio_available = True
                print(f"🎤 [唤醒词] 麦克风就绪，唤醒词=\"{self.wake_word}\"", file=sys.stderr)
                return True
            except ImportError:
                try:
                    import pyaudio
                    self._audio_available = True
                    print(f"🎤 [唤醒词] 麦克风就绪（pyaudio），唤醒词=\"{self.wake_word}\"", file=sys.stderr)
                    return True
                except ImportError:
                    print(f"🎤 [唤醒词] 无音频输入库（sounddevice/pyaudio），请安装", file=sys.stderr)
                    return False

        except Exception as e:
            print(f"🎤 [唤醒词] sherpa-onnx 初始化失败: {e}", file=sys.stderr)
            return False

    # ─── 生命周期 ─────────────────────────────

    def start(self):
        """启动唤醒词监听"""
        if self._running:
            return

        if self.engine == "none":
            print(f"🎤 [唤醒词] 引擎不可用，跳过启动", file=sys.stderr)
            return

        if self.engine == "sherpa":
            if not self._init_sherpa():
                # sherpa初始化失败，降级到keyboard
                self.engine = "keyboard"
                print(f"🎤 [唤醒词] sherpa初始化失败，降级到键盘模式", file=sys.stderr)

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="wake-word-listener"
        )
        self._thread.start()
        print(f"🎤 [唤醒词] 监听已启动（引擎：{self.engine}）", file=sys.stderr)

    def stop(self):
        """停止唤醒词监听"""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        print(f"🎤 [唤醒词] 监听已停止", file=sys.stderr)

    def _run_loop(self):
        """主循环"""
        if self.engine == "sherpa":
            self._run_sherpa_loop()
        elif self.engine == "keyboard":
            self._run_keyboard_loop()

    def _run_sherpa_loop(self):
        """sherpa-onnx 唤醒词检测循环"""
        try:
            import sounddevice as sd
            import numpy as np

            SAMPLE_RATE = 16000
            CHUNK = 512  # 32ms @ 16kHz

            def audio_callback(indata, frames, time_info, status):
                if status:
                    pass
                try:
                    audio_data = indata[:, 0].astype(np.float32)
                    self._sherpa_stream.accept_waveform(SAMPLE_RATE, audio_data)
                    while True:
                        result = self._sherpa_stream.get_result()
                        if result and result.strip():
                            self._on_wake_word_detected(result.strip())
                        else:
                            break
                except Exception as e:
                    pass

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=CHUNK,
                callback=audio_callback,
            ):
                while not self._stop_event.is_set():
                    self._stop_event.wait(0.1)

        except ImportError:
            # 尝试 pyaudio 作为后备
            try:
                import pyaudio
                self._run_sherpa_with_pyaudio()
            except ImportError:
                print(f"🎤 [唤醒词] 无音频库可用，降级到键盘模式", file=sys.stderr)
                self.engine = "keyboard"
                self._run_keyboard_loop()

    def _run_sherpa_with_pyaudio(self):
        """使用 pyaudio 的 sherpa-onnx 循环"""
        import pyaudio
        import numpy as np

        SAMPLE_RATE = 16000
        CHUNK = 512

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )

            while not self._stop_event.is_set():
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    audio_data = np.frombuffer(data, dtype=np.float32)
                    self._sherpa_stream.accept_waveform(SAMPLE_RATE, audio_data)
                    while True:
                        result = self._sherpa_stream.get_result()
                        if result and result.strip():
                            self._on_wake_word_detected(result.strip())
                        else:
                            break
                except Exception:
                    pass
                self._stop_event.wait(0.01)

            stream.stop_stream()
            stream.close()

        finally:
            pa.terminate()

    def _run_keyboard_loop(self):
        """键盘监听模式（CLI降级方案）"""
        try:
            import keyboard
        except ImportError:
            # 最终降级：stdin监听
            self._run_stdin_loop()
            return

        print(f"🎤 [唤醒词] 键盘模式：按 Enter 键模拟唤醒", file=sys.stderr)

        while not self._stop_event.is_set():
            # keyboard模块的阻塞等待
            try:
                keyboard.record(until="enter")
                self._on_wake_word_detected("keyboard_enter")
            except Exception:
                self._stop_event.wait(1)

    def _run_stdin_loop(self):
        """stdin监听模式（最终降级方案）"""
        print(f"🎤 [唤醒词] stdin模式：输入任意字符+Enter唤醒", file=sys.stderr)

        while not self._stop_event.is_set():
            try:
                import select
                # 非阻塞检查stdin
                if select.select([sys.stdin], [], [], 1)[0]:
                    sys.stdin.readline()
                    self._on_wake_word_detected("stdin_input")
            except Exception:
                self._stop_event.wait(5)

    # ─── 唤醒事件 ─────────────────────────────

    def _on_wake_word_detected(self, keyword: str):
        """唤醒词检测到"""
        self._wake_count += 1
        now = datetime.now()
        self._last_wake_time = now.strftime("%Y-%m-%d %H:%M:%S")

        print(f"🎤 [唤醒词] 检测到唤醒！keyword=\"{keyword}\"（第{self._wake_count}次）",
              file=sys.stderr)

        # 通知睡眠管理器
        self.sm.wake(reason="wake_word")

        # 触发回调
        for cb in self._wake_callbacks:
            try:
                cb(keyword)
            except Exception as e:
                print(f"🎤 [唤醒词] 回调异常: {e}", file=sys.stderr)

    def register_callback(self, callback: Callable):
        """注册唤醒回调"""
        self._wake_callbacks.append(callback)

    # ─── 手动唤醒（测试用） ───────────────────

    def manual_wake(self):
        """手动触发唤醒（用于测试/CLI命令）"""
        self._on_wake_word_detected("manual")

    # ─── 状态查询 ─────────────────────────────

    def get_status(self) -> dict:
        """获取唤醒词监听器状态"""
        return {
            "engine": self.engine,
            "running": self._running,
            "wake_word": self.wake_word,
            "wake_count": self._wake_count,
            "last_wake_time": self._last_wake_time,
            "sherpa_available": self._sherpa_available,
        }
