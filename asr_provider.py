"""
P0.58 能听（ASR）— 语音识别Provider抽象层
设计方向: 基类 + 工厂模式，类似TTSProvider
预置Provider: WhisperASRProvider（本地 faster-whisper）

config.json 配置示例:
    "asr": {
        "enabled": true,
        "provider": "whisper",
        "model_size": "base",
        "device": "auto",
        "compute_type": "int8",
        "language": "zh"
    }
"""
import os
import sys
import tempfile
from typing import Optional, Dict, Any


class ASRResult:
    """ASR识别结果"""
    def __init__(self, text: str, language: str = "zh", duration_ms: int = 0, segments: list = None):
        self.text = text
        self.language = language
        self.duration_ms = duration_ms
        self.segments = segments or []

    def __repr__(self):
        return f"ASRResult(text={self.text[:50]!r}, lang={self.language}, dur={self.duration_ms}ms)"


class ASRProvider:
    """ASR Provider 基类"""

    name = "base"
    requires_api_key = False
    requires_local_model = False

    def __init__(self, config: dict):
        self.config = config

    def transcribe(self, audio_path: str, language: str = None, **kwargs) -> Optional[ASRResult]:
        """识别音频文件，返回ASRResult或None"""
        raise NotImplementedError

    def is_available(self) -> bool:
        """检查Provider是否可用"""
        return True

    def get_info(self) -> dict:
        """返回Provider信息"""
        return {
            "name": self.name,
            "available": self.is_available(),
            "model": self.config.get("model_size", "unknown"),
        }


class WhisperASRProvider(ASRProvider):
    """faster-whisper 本地语音识别

    模型大小选择:
        tiny   — ~75MB, 最快, 精度低
        base   — ~145MB, 快, 精度中（推荐丐版）
        small  — ~480MB, 中速, 精度好
        medium — ~1.5GB, 慢, 精度高
        large  — ~3GB, 最慢, 精度最高

    显存占用:
        base   — ~200MB (int8)
        small  — ~500MB (int8)
        medium — ~1.5GB (int8)
    """

    name = "whisper"
    requires_local_model = True

    # 模型大小 → 显存估算（int8, approximate）
    MODEL_VRAM = {
        "tiny": 0.1,
        "base": 0.2,
        "small": 0.5,
        "medium": 1.5,
        "large": 3.0,
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.model_size = config.get("model_size", "base")
        self.device = config.get("device", "auto")  # auto / cpu / cuda
        self.compute_type = config.get("compute_type", "int8")  # int8 / int8_float16 / float16 / float32
        self.default_language = config.get("language", "zh")
        self._model = None
        self._init_model()

    def _init_model(self):
        """加载 faster-whisper 模型"""
        try:
            # 国内用户使用 HuggingFace 镜像
            if not os.environ.get("HF_ENDPOINT"):
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                print(f"[ASR] 使用HuggingFace镜像: {os.environ['HF_ENDPOINT']}")

            from faster_whisper import WhisperModel

            # 自动选择设备
            device = self.device
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"

            # CPU 用 int8，GPU 可以用更好的精度
            compute_type = self.compute_type
            if device == "cpu" and compute_type not in ("int8", "int8_float16"):
                compute_type = "int8"

            print(f"[ASR] 加载 faster-whisper 模型: {self.model_size} on {device} ({compute_type})")

            self._model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type,
            )
            print(f"[ASR] 模型加载完成 ✓")

        except ImportError:
            print("⚠ [ASR] faster-whisper 未安装，请运行: pip install faster-whisper", file=sys.stderr)
            self._model = None
        except Exception as e:
            print(f"⚠ [ASR] 模型加载失败: {e}", file=sys.stderr)
            self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    def transcribe(self, audio_path: str, language: str = None, **kwargs) -> Optional[ASRResult]:
        """识别音频文件

        Args:
            audio_path: 音频文件路径（wav/mp3/webm等）
            language: 语言代码（zh/en/ja等），None用默认配置
        """
        if not self._model:
            return None

        if not os.path.exists(audio_path):
            print(f"⚠ [ASR] 音频文件不存在: {audio_path}", file=sys.stderr)
            return None

        lang = language or self.default_language

        try:
            segments, info = self._model.transcribe(
                audio_path,
                language=lang,
                beam_size=5,
                vad_filter=True,  # 过滤静音段，提升速度
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            # 收集所有段文本
            segment_list = []
            full_text = []
            total_duration = 0.0

            for seg in segments:
                segment_list.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                })
                full_text.append(seg.text.strip())
                total_duration = max(total_duration, seg.end)

            text = "".join(full_text).strip()

            if not text:
                return ASRResult(text="", language=lang, duration_ms=int(total_duration * 1000))

            return ASRResult(
                text=text,
                language=info.language if info else lang,
                duration_ms=int(total_duration * 1000),
                segments=segment_list,
            )

        except Exception as e:
            print(f"⚠ [ASR] 识别失败: {e}", file=sys.stderr)
            return None

    def get_info(self) -> dict:
        vram = self.MODEL_VRAM.get(self.model_size, 0.5)
        return {
            "name": self.name,
            "available": self.is_available(),
            "model": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "vram_estimate_gb": vram,
            "language": self.default_language,
        }


class ASRProviderFactory:
    """ASR Provider 工厂"""

    _providers = {
        "whisper": WhisperASRProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class):
        """注册自定义Provider"""
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, config: dict) -> Optional[ASRProvider]:
        """根据配置创建Provider"""
        provider_name = config.get("provider", "whisper")
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            print(f"⚠ [ASR] 未知Provider: {provider_name}", file=sys.stderr)
            return None

        provider = provider_class(config)
        if not provider.is_available():
            print(f"⚠ [ASR] Provider '{provider_name}' 不可用", file=sys.stderr)
            return None

        return provider

    @classmethod
    def list_providers(cls) -> list:
        """列出所有已注册Provider"""
        return list(cls._providers.keys())


class ASREngine:
    """ASR 引擎 — 管理Provider + 配置"""

    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.provider = None
        if self.enabled:
            self.provider = ASRProviderFactory.create(config)
            if self.provider:
                info = self.provider.get_info()
                print(f"[ASR] Provider: {info['name']}, 模型: {info.get('model', '?')}")
            else:
                self.enabled = False
        else:
            print("[ASR] 未启用（config.asr.enabled = false）")

    def transcribe(self, audio_path: str, language: str = None) -> Optional[ASRResult]:
        """识别音频文件

        Args:
            audio_path: 音频文件路径
            language: 语言代码，None用默认
        """
        if not self.enabled or not self.provider:
            return None
        return self.provider.transcribe(audio_path, language=language)

    def get_status(self) -> dict:
        """获取ASR状态"""
        return {
            "enabled": self.enabled,
            "provider": self.provider.name if self.provider else None,
            "available": self.provider.is_available() if self.provider else False,
            "info": self.provider.get_info() if self.provider else {},
        }
