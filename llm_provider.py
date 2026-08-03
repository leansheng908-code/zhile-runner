"""
LLM提供者 — 调用DeepSeek/OpenAI兼容API

特性：
  - 支持流式输出（SSE解析）
  - 错误处理（网络/超时/限流/鉴权）
  - 模型参数从DNA的model_config.json读取
  - test_connection() 供启动时验证
"""

import json
import requests
from typing import Generator


class LLMProvider:
    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "https://api.deepseek.com/v1")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "deepseek-chat")
        self.temperature = config.get("temperature", 0.85)
        self.top_p = config.get("top_p", 0.92)
        self.max_tokens = config.get("max_tokens", 512)
        self.frequency_penalty = config.get("frequency_penalty", 0.3)
        self.presence_penalty = config.get("presence_penalty", 0.5)

        if not self.api_key:
            raise ValueError(
                "API Key未配置，请在 config.json 中填写 llm.api_key"
            )

    def chat(self, messages: list, stream: bool = True) -> Generator[str, None, None]:
        """调用LLM，yield输出文本片段"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": stream,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=stream,
                timeout=90,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接API服务器，请检查网络或VPN")
        except requests.exceptions.Timeout:
            raise TimeoutError("API请求超时（90s），请重试")
        except requests.exceptions.HTTPError as e:
            error_msg = f"API错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        if stream:
            yield from self._parse_stream(response)
        else:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            yield content

    def chat_with_tools(self, messages: list, tools: list) -> tuple:
        """非流式调用，支持function calling。返回 (content, tool_calls)"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": False,
            "tools": tools,
            "tool_choice": "auto",
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接API服务器，请检查网络或VPN")
        except requests.exceptions.Timeout:
            raise TimeoutError("API请求超时（60s）")
        except requests.exceptions.HTTPError as e:
            error_msg = f"API错误 ({response.status_code})"
            try:
                detail = response.json().get("error", {})
                error_msg += f": {detail.get('message', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            raise Exception(error_msg)

        data = response.json()
        choice = data["choices"][0]["message"]
        content = choice.get("content") or ""
        tool_calls = choice.get("tool_calls")
        return content, tool_calls

    def _parse_stream(self, response) -> Generator[str, None, None]:
        """解析SSE流式响应"""
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"]
                if "content" in delta and delta["content"]:
                    yield delta["content"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    def test_connection(self) -> tuple:
        """测试API连接，返回 (成功?, 消息)"""
        try:
            messages = [{"role": "user", "content": "说一个字：喵"}]
            result = ""
            for chunk in self.chat(messages, stream=True):
                result += chunk
            if result:
                return True, f"连接正常，模型回复: {result[:20]}"
            return True, "连接正常"
        except Exception as e:
            return False, str(e)
