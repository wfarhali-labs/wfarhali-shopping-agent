"""Chat models behind one interface: Meta Model API (Muse Spark) and the offline mock."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    def as_message(self) -> dict:
        message: dict = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [{"id": c.id, "type": "function",
                                      "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)}}
                                     for c in self.tool_calls]
        return message


class ChatModel(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn: ...


class ModelError(RuntimeError):
    pass


@dataclass
class MetaChatModel:
    """Muse Spark through the OpenAI-compatible Chat Completions endpoint of Meta Model API.

    Per Meta's docs: instructions go in a `developer` message, Muse Spark always reasons
    (reasoning_effort minimal..xhigh, never "none"), max_completion_tokens counts reasoning tokens,
    temperature/top_p stay at their defaults, images go in a user message as image_url parts.
    """
    api_key: str
    model: str = "muse-spark-1.3"
    base_url: str = "https://api.meta.ai/v1"
    reasoning_effort: str = "low"
    max_completion_tokens: int = 4000
    timeout: float = 60.0
    client: httpx.Client | None = None
    name: str = "meta"

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        if not self.api_key:
            raise ModelError("MODEL_API_KEY is not set")
        body = {"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto",
                "reasoning_effort": self.reasoning_effort, "max_completion_tokens": self.max_completion_tokens,
                "prompt_cache_key": "wfarhali-shopping-agent"}
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(f"{self.base_url}/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {self.api_key}"})
        finally:
            if self.client is None:
                client.close()
        if response.status_code >= 400:
            raise ModelError(f"Meta Model API {response.status_code}: {response.text[:300]}")
        choice = (response.json().get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {"_invalid_json": function.get("arguments")}
            calls.append(ToolCall(id=raw.get("id") or f"call_{len(calls)}", name=function.get("name", ""), arguments=arguments))
        if not calls and choice.get("finish_reason") == "length":
            raise ModelError("answer cut off (max_completion_tokens too small for the reasoning)")
        return ModelTurn(content=message.get("content") or "", tool_calls=calls)


def from_settings(settings) -> ChatModel:
    if settings.llm == "meta":
        return MetaChatModel(api_key=settings.model_api_key, model=settings.model, base_url=settings.meta_base_url)
    from .mock_llm import MockChatModel
    return MockChatModel()
