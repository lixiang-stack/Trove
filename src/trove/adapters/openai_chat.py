from __future__ import annotations

from typing import Any

import httpx

from trove.config import LLMConfig
from trove.errors import ProcessingError
from trove.ports import ChatResult

TEMPERATURE = 0.2


class OpenAICompatibleChatClient:
    def __init__(self, llm: LLMConfig, client: httpx.Client) -> None:
        self.llm = llm
        self.client = client

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
    ) -> ChatResult:
        body = {
            "model": self.llm.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
            "max_tokens": max_tokens,
            "temperature": TEMPERATURE,
        }
        data = self._post(body)
        choices = data.get("choices") or []
        content = ""
        finish_reason = None
        if choices:
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "")
            finish_reason = choices[0].get("finish_reason")
        usage = data.get("usage") or {}
        return ChatResult(
            content=content,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            finish_reason=finish_reason,
        )

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.llm.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.llm.api_key}"}
        try:
            response = self.client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ProcessingError("llm.failed", f"LLM request failed: {exc}") from exc
        if response.status_code in {401, 403}:
            raise ProcessingError(
                "llm.not_configured", "LLM rejected the configured API key"
            )
        if response.status_code >= 400:
            retry_after = _retry_after_seconds(response)
            details = {"status": response.status_code}
            if retry_after is not None:
                details["retry_after"] = retry_after
            raise ProcessingError(
                "llm.failed",
                f"LLM request failed with HTTP {response.status_code}",
                details=details,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProcessingError("llm.invalid_output", "LLM response was not JSON") from exc
        if not isinstance(data, dict):
            raise ProcessingError("llm.invalid_output", "LLM response was not JSON")
        return data


def _retry_after_seconds(response: httpx.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
