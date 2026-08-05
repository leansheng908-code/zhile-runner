#!/usr/bin/env python3
"""
P0.46⑥ 模型Provider插件化 — 统一模型调用抽象层

将 LLM 调用抽象为 Provider 接口，支持多种模型后端的插件化扩展。
现有 DeepSeek 调用方式（llm_provider.py）完全不受影响，新 Provider
是可选升级路径。

架构设计：
  - ModelProvider(ABC): 抽象基类，定义统一接口
  - DeepSeekProvider: DeepSeek API 实现（OpenAI 兼容格式）
  - ProviderFactory: 工厂模式，根据 config 创建对应 Provider

使用示例：
    # 通过工厂创建
    factory = ProviderFactory()
    factory.register_provider("deepseek", DeepSeekProvider)
    provider = factory.create_provider(config)

    # 直接使用
    provider = DeepSeekProvider(config["llm"])
    response = provider.chat(messages)
    for chunk in provider.chat(messages, stream=True):
        print(chunk, end="")

    # function calling
    content, tool_calls = provider.chat_with_tools(messages, tools)

向后兼容：
    现有的 LLMProvider(llm_provider.py) 可继续使用，不受影响。
    新代码可选择使用 ModelProvider 抽象层以获得更好的扩展性。
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests


# ─── 默认配置 ──────────────────────────────────────────

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TIMEOUT = 90
DEFAULT_STREAM_TIMEOUT = 120


# ─── 抽象基类 ──────────────────────────────────────────

class ModelProvider(ABC):
    """模型 Provider 抽象基类。

    定义了所有模型 Provider 必须实现的统一接口。
    子类需要实现 chat() 方法，可选实现 chat_with_tools() 方法。

    Attributes:
        api_key: API 密钥。
        base_url: API 基础 URL。
        model: 模型名称。
        temperature: 采样温度。
        top_p: nucleus sampling 参数。
        max_tokens: 最大生成 token 数。
        frequency_penalty: 频率惩罚。
        presence_penalty: 存在惩罚。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化 Provider。

        Args:
            config: 配置字典，至少包含 api_key。
        """
        self.api_key: str = config.get("api_key", "")
        self.base_url: str = config.get("base_url", DEFAULT_BASE_URL)
        self.model: str = config.get("model", DEFAULT_MODEL)
        self.temperature: float = config.get("temperature", 0.85)
        self.top_p: float = config.get("top_p", 0.92)
        self.max_tokens: int = config.get("max_tokens", 512)
        self.frequency_penalty: float = config.get("frequency_penalty", 0.3)
        self.presence_penalty: float = config.get("presence_penalty", 0.5)
        self.timeout: int = config.get("timeout", DEFAULT_TIMEOUT)

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Generator[str, None, None] | str:
        """调用模型进行对话。

        Args:
            messages: 消息列表，格式为
                [{"role": "user"/"assistant"/"system", "content": "..."}]。
            stream: 是否使用流式输出。若为 True 则返回生成器，
                逐块 yield 文本片段；若为 False 则返回完整字符串。
            **kwargs: 额外的模型参数（如 temperature 覆盖等）。

        Returns:
            流式模式下返回 Generator[str, None, None]，
            非流式模式下返回 str。

        Raises:
            ConnectionError: 无法连接 API 服务器。
            TimeoutError: API 请求超时。
            Exception: API 返回错误。
        """
        ...

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """调用模型并支持 function calling。

        默认实现抛出 NotImplementedError，子类可按需覆盖。

        Args:
            messages: 消息列表。
            tools: 工具/函数定义列表（OpenAI function calling 格式）。
            **kwargs: 额外参数。

        Returns:
            元组 (content, tool_calls)：
            - content: 模型回复文本。
            - tool_calls: 工具调用列表，若无则返回 None。

        Raises:
            NotImplementedError: 当前 Provider 不支持 function calling。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 不支持 function calling"
        )

    def test_connection(self) -> Tuple[bool, str]:
        """测试 API 连接是否正常。

        默认实现发送一条简单消息测试连通性。
        子类可覆盖以提供更具体的测试逻辑。

        Returns:
            元组 (success, message)：
            - success: 连接是否成功。
            - message: 描述信息。
        """
        try:
            messages = [{"role": "user", "content": "Hi"}]
            result = self.chat(messages, stream=False)
            if isinstance(result, str) and result:
                return True, f"连接正常，模型回复: {result[:50]}"
            return True, "连接正常"
        except Exception as e:
            return False, str(e)


# ─── DeepSeek Provider ─────────────────────────────────

class DeepSeekProvider(ModelProvider):
    """DeepSeek API Provider 实现。

    支持 OpenAI 兼容格式的 API 调用，包括：
      - 流式和非流式输出
      - Function calling（工具调用）
      - 自定义模型参数

    配置从 config.json 的 "llm" 段读取，也可通过环境变量覆盖。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化 DeepSeek Provider。

        Args:
            config: 配置字典，通常为 config.json 中 "llm" 段的内容。
                必须包含 api_key，可选 base_url、model 等参数。

        Raises:
            ValueError: API Key 未配置。
        """
        # 优先从环境变量读取 API Key
        config = dict(config)  # 浅拷贝，避免修改原配置
        config["api_key"] = os.environ.get(
            "DEEPSEEK_API_KEY", config.get("api_key", "")
        )

        super().__init__(config)

        if not self.api_key:
            raise ValueError(
                "API Key 未配置，请设置环境变量 DEEPSEEK_API_KEY "
                "或在 config.json 中配置 llm.api_key"
            )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Generator[str, None, None] | str:
        """调用 DeepSeek API 进行对话。

        Args:
            messages: 消息列表。
            stream: 是否流式输出。
            **kwargs: 额外参数，可覆盖 temperature、max_tokens 等。

        Returns:
            流式模式返回 Generator，非流式模式返回 str。

        Raises:
            ConnectionError: 无法连接 API 服务器。
            TimeoutError: 请求超时。
            Exception: API 错误。
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # 合并参数：实例默认值 < kwargs 覆盖
        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "frequency_penalty": kwargs.get(
                "frequency_penalty", self.frequency_penalty
            ),
            "presence_penalty": kwargs.get(
                "presence_penalty", self.presence_penalty
            ),
            "stream": stream,
        }

        timeout = kwargs.get("timeout", self.timeout if stream else DEFAULT_TIMEOUT)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=stream,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 API 服务器，请检查网络或 VPN")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{timeout}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        if stream:
            return self._parse_stream(response)
        else:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """调用 DeepSeek API 并支持 function calling。

        使用非流式模式发送请求，附带 tools 参数。

        Args:
            messages: 消息列表。
            tools: 工具定义列表（OpenAI function calling 格式）。
            **kwargs: 额外参数。

        Returns:
            元组 (content, tool_calls)：
            - content: 模型回复文本。
            - tool_calls: 工具调用列表，若无则返回 None。

        Raises:
            ConnectionError: 无法连接 API 服务器。
            TimeoutError: 请求超时。
            Exception: API 错误。
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "frequency_penalty": kwargs.get(
                "frequency_penalty", self.frequency_penalty
            ),
            "presence_penalty": kwargs.get(
                "presence_penalty", self.presence_penalty
            ),
            "stream": False,
            "tools": tools,
            "tool_choice": kwargs.get("tool_choice", "auto"),
        }

        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 API 服务器，请检查网络或 VPN")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{timeout}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        data = response.json()
        choice = data["choices"][0]["message"]
        content: str = choice.get("content") or ""
        tool_calls: Optional[List[Dict[str, Any]]] = choice.get("tool_calls")
        return content, tool_calls

    def _parse_stream(
        self, response: requests.Response
    ) -> Generator[str, None, None]:
        """解析 SSE 流式响应。

        Args:
            response: requests Response 对象（stream=True 模式）。

        Yields:
            文本片段字符串。
        """
        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"]
                if "content" in delta and delta["content"]:
                    yield delta["content"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# ─── OpenAI Provider ───────────────────────────────────

class OpenAIProvider(ModelProvider):
    """OpenAI API Provider 实现。

    支持 GPT-4o / GPT-4-turbo / GPT-3.5-turbo 等模型，
    使用 OpenAI 标准 API 格式（与 DeepSeek 兼容）。

    配置示例（config.json 的 llm 段）：
        {
            "provider": "openai",
            "api_key": "sk-xxx",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1"
        }
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        config = dict(config)
        config["api_key"] = os.environ.get(
            "OPENAI_API_KEY", config.get("api_key", "")
        )
        config.setdefault("base_url", "https://api.openai.com/v1")
        config.setdefault("model", "gpt-4o")
        super().__init__(config)

        if not self.api_key:
            raise ValueError(
                "API Key 未配置，请设置环境变量 OPENAI_API_KEY "
                "或在 config.json 中配置 llm.api_key"
            )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Generator[str, None, None] | str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "frequency_penalty": kwargs.get("frequency_penalty", self.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.presence_penalty),
            "stream": stream,
        }
        timeout = kwargs.get("timeout", self.timeout if stream else DEFAULT_TIMEOUT)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=stream,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 OpenAI API，请检查网络或代理设置")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{timeout}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"OpenAI API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        if stream:
            return self._parse_stream(response)
        else:
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": False,
            "tools": tools,
            "tool_choice": kwargs.get("tool_choice", "auto"),
        }
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 OpenAI API")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{timeout}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"OpenAI API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        data = response.json()
        choice = data["choices"][0]["message"]
        content: str = choice.get("content") or ""
        tool_calls: Optional[List[Dict[str, Any]]] = choice.get("tool_calls")
        return content, tool_calls

    def _parse_stream(self, response: requests.Response) -> Generator[str, None, None]:
        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"]
                if "content" in delta and delta["content"]:
                    yield delta["content"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# ─── Claude Provider ───────────────────────────────────

class ClaudeProvider(ModelProvider):
    """Anthropic Claude API Provider 实现。

    支持 Claude-3.5-Sonnet / Claude-3-Opus / Claude-3-Haiku 等模型。
    使用 Anthropic 原生 API 格式（与 OpenAI 格式不同）。

    主要差异：
      - 端点: /v1/messages（非 /v1/chat/completions）
      - 认证: x-api-key 头（非 Authorization Bearer）
      - system 消息: 顶层 system 字段（非 messages 内）
      - 响应: content[0].text（非 choices[0].message.content）
      - 流式: event-based SSE（非 data: JSON）

    配置示例（config.json 的 llm 段）：
        {
            "provider": "claude",
            "api_key": "sk-ant-xxx",
            "model": "claude-sonnet-4-20250514",
            "base_url": "https://api.anthropic.com"
        }
    """

    # Anthropic API 版本
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, config: Dict[str, Any]) -> None:
        config = dict(config)
        config["api_key"] = os.environ.get(
            "ANTHROPIC_API_KEY", config.get("api_key", "")
        )
        config.setdefault("base_url", "https://api.anthropic.com")
        config.setdefault("model", "claude-sonnet-4-20250514")
        # Claude 的 max_tokens 上限更大
        config.setdefault("max_tokens", 1024)
        super().__init__(config)

        if not self.api_key:
            raise ValueError(
                "API Key 未配置，请设置环境变量 ANTHROPIC_API_KEY "
                "或在 config.json 中配置 llm.api_key"
            )

    def _split_system(self, messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        """将 system 消息从 messages 中分离。

        Claude API 要求 system 作为顶层参数，不能放在 messages 里。

        Args:
            messages: 原始消息列表（OpenAI 格式）。

        Returns:
            元组 (system_text, filtered_messages)。
        """
        system_parts = []
        filtered = []
        for msg in messages:
            if msg.get("role") == "system":
                if msg.get("content"):
                    system_parts.append(str(msg["content"]))
            else:
                filtered.append(msg)
        return "\n\n".join(system_parts), filtered

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将 OpenAI 格式消息转换为 Claude 格式。

        Claude 要求 user/assistant 交替，且不支持 system 角色。
        system 已由 _split_system 处理。
        """
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Claude 只接受 user 和 assistant
            if role not in ("user", "assistant"):
                role = "user"
            converted.append({"role": role, "content": str(content)})
        return converted

    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Generator[str, None, None] | str:
        system_text, filtered_msgs = self._split_system(messages)
        claude_msgs = self._convert_messages(filtered_msgs)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
        }
        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": claude_msgs,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "stream": stream,
        }
        if system_text:
            payload["system"] = system_text

        timeout = kwargs.get("timeout", self.timeout if stream else DEFAULT_TIMEOUT)

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
                stream=stream,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 Anthropic API，请检查网络或代理设置")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{timeout}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"Claude API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        if stream:
            return self._parse_stream(response)
        else:
            data = response.json()
            # Claude 响应: {"content": [{"type": "text", "text": "..."}], ...}
            content_blocks = data.get("content", [])
            return "".join(
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            )

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        # Claude 的 function calling 格式与 OpenAI 不同
        # 转换 OpenAI tools -> Claude tools
        claude_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                claude_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object"}),
                })

        system_text, filtered_msgs = self._split_system(messages)
        claude_msgs = self._convert_messages(filtered_msgs)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
        }
        payload: Dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": claude_msgs,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False,
            "tools": claude_tools,
        }
        if system_text:
            payload["system"] = system_text

        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接 Anthropic API")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"API 请求超时（{timeout}s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"Claude API 错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        data = response.json()
        content_parts = []
        tool_calls: List[Dict[str, Any]] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        content = "".join(content_parts)
        return content, (tool_calls if tool_calls else None)

    def _parse_stream(self, response: requests.Response) -> Generator[str, None, None]:
        """解析 Anthropic SSE 流式响应。

        Claude 的流式格式与 OpenAI 不同：
          event: content_block_delta
          data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
        """
        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:]
            try:
                chunk = json.loads(data_str)
                chunk_type = chunk.get("type", "")
                if chunk_type == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield delta["text"]
                elif chunk_type == "message_stop":
                    break
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# ─── Provider 工厂 ──────────────────────────────────────

class ProviderFactory:
    """模型 Provider 工厂。

    使用工厂模式根据配置创建对应的 Provider 实例。
    支持动态注册新的 Provider 类型。

    内置 Provider:
      - deepseek: DeepSeek API (OpenAI 兼容格式)
      - openai: OpenAI API (GPT-4o 等)
      - claude: Anthropic Claude API (Claude-3.5 等)

    Attributes:
        _providers: 已注册的 Provider 类映射。
    """

    # 内置 Provider 注册
    _BUILTIN_PROVIDERS: Dict[str, type] = {
        "deepseek": DeepSeekProvider,
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
    }

    def __init__(self) -> None:
        """初始化工厂，注册内置 Provider。"""
        # 每个实例有独立的注册表副本
        self._providers: Dict[str, type] = dict(self._BUILTIN_PROVIDERS)

    def register_provider(
        self, name: str, provider_class: type
    ) -> None:
        """注册一个新的 Provider 类型。

        Args:
            name: Provider 名称（如 "openai"、"anthropic"）。
            provider_class: Provider 类，必须是 ModelProvider 的子类。

        Raises:
            TypeError: provider_class 不是 ModelProvider 的子类。
        """
        if not issubclass(provider_class, ModelProvider):
            raise TypeError(
                f"{provider_class.__name__} 必须是 ModelProvider 的子类"
            )
        self._providers[name.lower()] = provider_class
        print(f"[ProviderFactory] 已注册 Provider: {name}")

    def unregister_provider(self, name: str) -> bool:
        """取消注册一个 Provider 类型。

        Args:
            name: Provider 名称。

        Returns:
            是否成功取消注册。
        """
        if name.lower() in self._providers:
            del self._providers[name.lower()]
            return True
        return False

    def create_provider(
        self, config: Dict[str, Any]
    ) -> ModelProvider:
        """根据配置创建 Provider 实例。

        从 config 的 "llm" 段读取 provider 名称（默认 "deepseek"），
        创建对应的 Provider 实例。

        Args:
            config: 完整配置字典。需要包含 "llm" 段，
                其中 "provider" 字段指定 Provider 类型。

        Returns:
            Provider 实例。

        Raises:
            ValueError: 未知的 Provider 类型。
            ValueError: 配置缺少必要字段。
        """
        llm_config = config.get("llm", config)
        provider_name = llm_config.get("provider", "deepseek").lower()

        provider_class = self._providers.get(provider_name)
        if provider_class is None:
            available = ", ".join(self._providers.keys())
            raise ValueError(
                f"未知的 Provider 类型: {provider_name}。"
                f"可用类型: {available}"
            )

        return provider_class(llm_config)

    def list_providers(self) -> List[str]:
        """列出所有已注册的 Provider 名称。

        Returns:
            Provider 名称列表。
        """
        return list(self._providers.keys())

    def is_registered(self, name: str) -> bool:
        """检查指定名称的 Provider 是否已注册。

        Args:
            name: Provider 名称。

        Returns:
            是否已注册。
        """
        return name.lower() in self._providers


# ─── 向后兼容适配器 ──────────────────────────────────────

class LLMProviderAdapter:
    """向后兼容适配器。

    将新的 ModelProvider 接口适配为旧的 LLMProvider 接口，
    使现有代码无需修改即可使用新的 Provider 系统。

    旧的 llm_provider.py 中的 LLMProvider.chat() 方法返回 Generator[str, None, None]，
    本适配器保持相同签名。
    """

    def __init__(self, provider: ModelProvider) -> None:
        """初始化适配器。

        Args:
            provider: ModelProvider 实例。
        """
        self._provider = provider

    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """适配旧版 chat 接口（始终返回生成器）。

        Args:
            messages: 消息列表。
            stream: 是否流式（适配器中始终以生成器方式返回）。
            **kwargs: 额外参数（如 max_tokens 覆盖），透传给 Provider。

        Yields:
            文本片段。
        """
        if stream:
            yield from self._provider.chat(messages, stream=True, **kwargs)  # type: ignore
        else:
            result = self._provider.chat(messages, stream=False, **kwargs)
            if isinstance(result, str):
                yield result

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """适配旧版 chat_with_tools 接口。

        Args:
            messages: 消息列表。
            tools: 工具定义列表。

        Returns:
            元组 (content, tool_calls)。
        """
        return self._provider.chat_with_tools(messages, tools)

    def test_connection(self) -> Tuple[bool, str]:
        """适配旧版 test_connection 接口。

        Returns:
            元组 (success, message)。
        """
        return self._provider.test_connection()

    # ─── 兼容属性 ──────────────────────────────────────────

    @property
    def model(self) -> str:
        """模型名称（兼容旧 LLMProvider.model）。"""
        return self._provider.model

    @property
    def base_url(self) -> str:
        """API Base URL（兼容旧 LLMProvider.base_url）。"""
        return self._provider.base_url

    @property
    def api_key(self) -> str:
        """API Key（兼容旧 LLMProvider.api_key）。"""
        return self._provider.api_key

    @property
    def temperature(self) -> float:
        """采样温度（兼容旧 LLMProvider.temperature）。"""
        return self._provider.temperature

    @property
    def max_tokens(self) -> int:
        """最大 token 数（兼容旧 LLMProvider.max_tokens）。"""
        return self._provider.max_tokens

    @property
    def config(self) -> Dict[str, Any]:
        """配置字典（兼容 /provider 命令访问）。

        Returns:
            包含 provider/model/base_url/temperature/max_tokens 等键的字典。
        """
        provider_name = self._provider.__class__.__name__.replace("Provider", "").lower()
        return {
            "provider": provider_name,
            "model": self._provider.model,
            "base_url": self._provider.base_url,
            "temperature": self._provider.temperature,
            "max_tokens": self._provider.max_tokens,
            "top_p": self._provider.top_p,
            "frequency_penalty": self._provider.frequency_penalty,
            "presence_penalty": self._provider.presence_penalty,
        }

    @property
    def provider(self) -> ModelProvider:
        """获取内部 Provider 实例。"""
        return self._provider
