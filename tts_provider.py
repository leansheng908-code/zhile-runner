"""
P0.58 能说（TTS）— 语音合成Provider抽象层
设计方向: 基类 + 工厂模式，类似ModelProvider
预置Provider: EdgeTTSProvider（免费）/ ChatTTSProvider（本地）/ AzureTTSProvider（付费）
PSI情绪状态 → 语速/音调/停顿 自动调整
"""
import os
import sys
import asyncio
import tempfile
import hashlib
from typing import Optional, Dict, Any


class TTSResult:
    """TTS合成结果"""
    def __init__(self, audio_path: str, text: str, voice: str, duration_ms: int = 0):
        self.audio_path = audio_path
        self.text = text
        self.voice = voice
        self.duration_ms = duration_ms

    def __repr__(self):
        return f"TTSResult(voice={self.voice}, path={self.audio_path}, dur={self.duration_ms}ms)"


class TTSProvider:
    """TTS Provider 基类"""

    name = "base"
    requires_api_key = False
    requires_local_model = False

    def __init__(self, config: dict):
        self.config = config
        self.cache_dir = config.get("cache_dir", os.path.join(tempfile.gettempdir(), "tts_cache"))
        os.makedirs(self.cache_dir, exist_ok=True)

    def synthesize(self, text: str, voice: str = None, **kwargs) -> Optional[TTSResult]:
        """合成语音，返回TTSResult或None"""
        raise NotImplementedError

    def list_voices(self) -> list:
        """返回可用音色列表"""
        return []

    def is_available(self) -> bool:
        """检查Provider是否可用"""
        return True

    def _get_cache_path(self, text: str, voice: str) -> str:
        """生成缓存路径"""
        key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{key}.mp3")

    def _check_cache(self, text: str, voice: str) -> Optional[str]:
        """检查缓存是否存在"""
        path = self._get_cache_path(text, voice)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        return None


class EdgeTTSProvider(TTSProvider):
    """Edge TTS — 微软免费TTS，音质好，支持中文多音色"""

    name = "edge_tts"
    requires_api_key = False

    # 推荐中文音色
    VOICES = {
        # 女声
        "xiaoyi": "zh-CN-XiaoyiNeural",        # 晓伊 — 温暖亲切，适合猫娘
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",     # 晓晓 — 标准女声，清晰
        "xiaoyou": "zh-CN-XiaoyouNeural",       # 晓悠 — 温柔年轻女声
        "xiaohan": "zh-CN-XiaohanNeural",       # 晓涵 — 温暖成熟女声
        "xiaomeng": "zh-CN-XiaomengNeural",     # 晓梦 — 甜美可爱
        "xiaoqiu": "zh-CN-XiaoqiuNeural",       # 晓秋 — 温暖知性
        "xiaorui": "zh-CN-XiaoruiNeural",       # 晓瑞 — 沉稳干练
        "xiaoshuang": "zh-CN-XiaoshuangNeural", # 晓双 — 儿童声，适合萌系
        # 男声
        "yunyang": "zh-CN-YunyangNeural",       # 云扬 — 标准男声
        "yunjian": "zh-CN-YunjianNeural",       # 云健 — 体育解说风
        "yunfeng": "zh-CN-YunfengNeural",       # 云枫 — 叙事深沉
    }

    # PSI情绪 → 语音参数映射
    PSI_VOICE_MAP = {
        # (rate, pitch, volume) — rate: 相对速度, pitch: 相对音调, volume: 音量
        "happy": {"rate": "+10%", "pitch": "+15Hz", "volume": "+0%"},       # 开心：快一点高一点
        "sad": {"rate": "-15%", "pitch": "-10Hz", "volume": "-10%"},        # 难过：慢一点低一点
        "excited": {"rate": "+20%", "pitch": "+20Hz", "volume": "+10%"},    # 兴奋：更快更高
        "calm": {"rate": "-5%", "pitch": "+0Hz", "volume": "+0%"},          # 平静：稍慢
        "sleepy": {"rate": "-20%", "pitch": "-5Hz", "volume": "-15%"},      # 困倦：很慢很轻
        "caring": {"rate": "-10%", "pitch": "+5Hz", "volume": "-5%"},       # 关心：温柔稍慢
        "playful": {"rate": "+15%", "pitch": "+10Hz", "volume": "+5%"},     # 调皮：快一点高一点
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.default_voice = config.get("voice", "xiaoyi")
        self.base_volume = config.get("volume", 0)  # 音量调节 -100~+100
        self.base_rate = config.get("rate", 0)      # 语速调节 -100~+100
        self._edge_tts = None
        self._init_lib()

    def _init_lib(self):
        """尝试导入edge-tts库"""
        try:
            import edge_tts
            self._edge_tts = edge_tts
        except ImportError:
            print("⚠ [TTS] edge-tts未安装，请运行: pip install edge-tts", file=sys.stderr)
            self._edge_tts = None

    def is_available(self) -> bool:
        return self._edge_tts is not None

    def _get_voice_id(self, voice: str = None) -> str:
        """获取Edge TTS音色ID"""
        voice = voice or self.default_voice
        return self.VOICES.get(voice, self.VOICES["xiaoyi"])

    def _get_emotion_params(self, emotion: str = None) -> dict:
        """根据情绪获取语音参数（叠加用户配置的基础音量/语速）"""
        if not emotion:
            base = {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"}
        else:
            base = self.PSI_VOICE_MAP.get(emotion, {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})

        # 解析情绪参数中的数值，叠加用户基础配置
        import re
        def _parse_pct(s):
            m = re.match(r'([+-]\d+)%', s)
            return int(m.group(1)) if m else 0

        final_volume = max(-100, min(100, _parse_pct(base["volume"]) + self.base_volume))
        final_rate = max(-100, min(100, _parse_pct(base["rate"]) + self.base_rate))

        return {
            "rate": f"{final_rate:+d}%",
            "pitch": base["pitch"],  # pitch不叠加，保持情绪原始值
            "volume": f"{final_volume:+d}%",
        }

    def synthesize(self, text: str, voice: str = None, emotion: str = None, **kwargs) -> Optional[TTSResult]:
        """使用Edge TTS合成语音

        Args:
            text: 要合成的文本
            voice: 音色名称（如"xiaoyi"），None用默认
            emotion: 情绪标签（happy/sad/excited/calm/sleepy/caring/playful）
        """
        if not self._edge_tts or not text.strip():
            return None

        voice_id = self._get_voice_id(voice)
        params = self._get_emotion_params(emotion)

        # 检查缓存
        cache_key = f"{voice_id}:{emotion or 'none'}:{text[:100]}"
        cached = self._check_cache(text, f"{voice_id}_{emotion or 'none'}")
        if cached:
            return TTSResult(cached, text, voice_id)

        # 合成
        output_path = self._get_cache_path(text, f"{voice_id}_{emotion or 'none'}")
        try:
            asyncio.run(self._synthesize_async(text, voice_id, params, output_path))
            return TTSResult(output_path, text, voice_id)
        except Exception as e:
            print(f"⚠ [TTS] Edge TTS合成失败: {e}", file=sys.stderr)
            return None

    async def _synthesize_async(self, text: str, voice_id: str, params: dict, output_path: str):
        """异步合成"""
        communicate = self._edge_tts.Communicate(
            text, voice_id,
            rate=params["rate"],
            pitch=params["pitch"],
            volume=params["volume"],
        )
        await communicate.save(output_path)

    def list_voices(self) -> list:
        """返回可用音色列表"""
        return [(key, desc) for key, desc in [
            ("xiaoyi", "晓伊 — 温暖亲切（推荐·猫娘感）"),
            ("xiaoxiao", "晓晓 — 标准清晰女声"),
            ("xiaoyou", "晓悠 — 温柔年轻女声"),
            ("xiaomeng", "晓梦 — 甜美可爱"),
            ("xiaoshuang", "晓双 — 儿童声（超萌）"),
            ("xiaohan", "晓涵 — 温暖成熟女声"),
            ("xiaorui", "晓瑞 — 沉稳干练"),
            ("yunyang", "云扬 — 标准男声"),
            ("yunjian", "云健 — 热血男声"),
            ("yunfeng", "云枫 — 深沉叙事"),
        ]]


class GPTSoVITSProvider(TTSProvider):
    """GPT-SoVITS — 本地语音克隆TTS，用参考音频克隆音色

    需要先启动GPT-SoVITS API服务:
        python api_v2.py -a 127.0.0.1 -p 9880

    config.json 配置示例:
        "tts": {
            "provider": "gpt_sovits",
            "api_url": "http://127.0.0.1:9880",
            "ref_audio_path": "F:/voices/my_voice.wav",
            "prompt_text": "这是我的声音样本",
            "prompt_lang": "zh",
            "cache_dir": "memory/tts_cache"
        }
    """

    name = "gpt_sovits"
    requires_local_model = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_url = config.get("api_url", "http://127.0.0.1:9880").rstrip("/")
        self.ref_audio_path = config.get("ref_audio_path", "")
        self.prompt_text = config.get("prompt_text", "")
        self.prompt_lang = config.get("prompt_lang", "zh")
        self.text_lang = config.get("text_lang", "zh")
        self.speed = config.get("speed", 1.0)
        self.base_volume = config.get("volume", 0)
        self.base_rate = config.get("rate", 0)
        self._requests = None
        self._init_lib()

    def _init_lib(self):
        try:
            import requests
            self._requests = requests
        except ImportError:
            try:
                import urllib.request as _ur
                self._requests = "urllib"
            except Exception:
                self._requests = None

    def is_available(self) -> bool:
        if not self._requests:
            return False
        if not self.ref_audio_path or not os.path.exists(self.ref_audio_path):
            return False
        # 检查API是否在线 — 任何HTTP响应(含404)都说明服务在运行
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(self.api_url, method="GET")
            urllib.request.urlopen(req, timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # 404等也说明服务在运行
        except Exception:
            return False

    def synthesize(self, text: str, voice: str = None, emotion: str = None, **kwargs) -> Optional[TTSResult]:
        """调用GPT-SoVITS API合成语音"""
        if not text.strip():
            return None
        if not self.ref_audio_path:
            print("⚠ [TTS] GPT-SoVITS未配置ref_audio_path", file=sys.stderr)
            return None

        # 速度调节：基础speed + rate偏移
        speed = self.speed
        if self.base_rate != 0:
            speed = max(0.5, min(2.0, speed + self.base_rate / 100.0))

        # 检查缓存（包含speed，否则改rate不生效）
        cache_key = f"gsovits:{emotion or 'none'}:sp{speed:.2f}:{text[:100]}"
        cached = self._check_cache(text, cache_key)
        if cached:
            return TTSResult(cached, text, "gpt_sovits")

        output_path = self._get_cache_path(text, cache_key)
        # 改扩展名为wav（GPT-SoVITS默认输出wav）
        output_path = output_path.replace(".mp3", ".wav")

        payload = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "text_split_method": "cut5",
            "batch_size": 1,
            "media_type": "wav",
            "streaming_mode": True,
            "speed_factor": speed,
        }

        try:
            if self._requests and self._requests != "urllib":
                # 流式读取：服务器边生成边发送，减少等待
                resp = self._requests.post(f"{self.api_url}/tts", json=payload, timeout=60, stream=True)
                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    return TTSResult(output_path, text, "gpt_sovits")
                else:
                    print(f"⚠ [TTS] GPT-SoVITS API返回 {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
                    return None
            else:
                # urllib fallback — 也支持流式读取
                import urllib.request as _ur
                import json as _json
                data = _json.dumps(payload).encode("utf-8")
                req = _ur.Request(f"{self.api_url}/tts", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
                resp = _ur.urlopen(req, timeout=60)
                if resp.status == 200:
                    with open(output_path, "wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                    return TTSResult(output_path, text, "gpt_sovits")
                else:
                    print(f"⚠ [TTS] GPT-SoVITS API返回 {resp.status}", file=sys.stderr)
                    return None
        except Exception as e:
            print(f"⚠ [TTS] GPT-SoVITS合成失败: {e}", file=sys.stderr)
            return None

    def list_voices(self) -> list:
        return [("ref_audio", f"参考音频: {os.path.basename(self.ref_audio_path) or '未配置'}")]


class TTSProviderFactory:
    """TTS Provider 工厂"""

    _providers = {
        "edge_tts": EdgeTTSProvider,
        "gpt_sovits": GPTSoVITSProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class):
        """注册自定义Provider"""
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, config: dict) -> Optional[TTSProvider]:
        """根据配置创建Provider"""
        provider_name = config.get("provider", "edge_tts")
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            print(f"⚠ [TTS] 未知Provider: {provider_name}", file=sys.stderr)
            return None

        provider = provider_class(config)
        if not provider.is_available():
            print(f"⚠ [TTS] Provider '{provider_name}' 不可用", file=sys.stderr)
            return None

        return provider

    @classmethod
    def list_providers(cls) -> list:
        """列出所有已注册Provider"""
        return list(cls._providers.keys())


class TTSEngine:
    """TTS 引擎 — 管理Provider + 情绪映射 + 缓存"""

    # PSI五维状态 → 情绪标签映射
    PSI_EMOTION_MAP = {
        # 当多个PSI维度同时命中时，优先级从高到低
        ("energy_low",): "sleepy",
        ("belonging_low",): "caring",
        ("competence_low",): "caring",
        ("autonomy_high",): "playful",
    }

    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.provider = None
        if self.enabled:
            self.provider = TTSProviderFactory.create(config)
            if self.provider:
                print(f"[TTS] Provider: {self.provider.name}, 音色: {config.get('voice', 'xiaoyi')}")
            else:
                self.enabled = False

    def synthesize(self, text: str, emotion: str = None, voice: str = None) -> Optional[TTSResult]:
        """合成语音

        Args:
            text: 要合成的文本
            emotion: 情绪标签（happy/sad/excited/calm/sleepy/caring/playful）
            voice: 指定音色，None用默认
        """
        if not self.enabled or not self.provider:
            return None
        return self.provider.synthesize(text, voice=voice, emotion=emotion)

    def emotion_from_psi(self, psi_state: dict) -> str:
        """从PSI状态推断情绪标签"""
        belonging = psi_state.get("belonging", 3.0)
        energy = psi_state.get("energy", 3.0)
        competence = psi_state.get("competence", 3.0)
        autonomy = psi_state.get("autonomy", 3.0)

        if energy < 1.5:
            return "sleepy"
        if belonging < 2.0:
            return "caring"
        if competence < 2.0:
            return "caring"
        if autonomy > 3.5:
            return "playful"
        if energy > 3.5 and belonging > 3.0:
            return "happy"

        return "calm"

    def get_status(self) -> dict:
        """获取TTS状态"""
        return {
            "enabled": self.enabled,
            "provider": self.provider.name if self.provider else None,
            "available": self.provider.is_available() if self.provider else False,
            "voices": self.provider.list_voices() if self.provider else [],
        }
