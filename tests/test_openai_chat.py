from __future__ import annotations

import json

import httpx
import pytest

from trove.adapters.openai_chat import OpenAICompatibleChatClient
from trove.config import LLMConfig
from trove.errors import ProcessingError
from trove.ports import ChatResult


def _llm(**overrides) -> LLMConfig:
    values = {
        "model": "deepseek-flash",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-key",
    }
    values.update(overrides)
    return LLMConfig(**values)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_response(content: str = "{}", *, input_tokens: int = 50, output_tokens: int = 20):
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
        },
    )


def test_complete_builds_the_openai_request_and_reads_usage():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        assert str(request.url) == "https://api.example.com/v1/chat/completions"
        return _ok_response('{"summary": "ok", "tags": ["tag"]}')

    client = OpenAICompatibleChatClient(_llm(), client=_client(handler))
    result = client.complete(
        [{"role": "user", "content": "hello"}], max_tokens=256
    )

    assert result == ChatResult(
        content='{"summary": "ok", "tags": ["tag"]}',
        input_tokens=50,
        output_tokens=20,
        finish_reason="stop",
    )
    body = requests[0]
    assert body["model"] == "deepseek-flash"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == 256
    assert body["temperature"] == 0.2


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_map_to_not_configured(status):
    client = OpenAICompatibleChatClient(
        _llm(), client=_client(lambda request: httpx.Response(status))
    )

    with pytest.raises(ProcessingError) as excinfo:
        client.complete([{"role": "user", "content": "hello"}], max_tokens=10)

    assert excinfo.value.code == "llm.not_configured"


def test_rate_limit_is_reported_with_retry_after():
    client = OpenAICompatibleChatClient(
        _llm(),
        client=_client(
            lambda request: httpx.Response(
                429, headers={"retry-after": "7"}, json={"error": "slow down"}
            )
        ),
    )

    with pytest.raises(ProcessingError) as excinfo:
        client.complete([{"role": "user", "content": "hello"}], max_tokens=10)

    assert excinfo.value.code == "llm.failed"
    assert excinfo.value.details == {"status": 429, "retry_after": 7}


@pytest.mark.parametrize("status", [500, 503])
def test_server_errors_map_to_llm_failed(status):
    client = OpenAICompatibleChatClient(
        _llm(), client=_client(lambda request: httpx.Response(status))
    )

    with pytest.raises(ProcessingError) as excinfo:
        client.complete([{"role": "user", "content": "hello"}], max_tokens=10)

    assert excinfo.value.code == "llm.failed"
    assert excinfo.value.details == {"status": status}


def test_timeouts_map_to_llm_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OpenAICompatibleChatClient(_llm(), client=_client(handler))

    with pytest.raises(ProcessingError) as excinfo:
        client.complete([{"role": "user", "content": "hello"}], max_tokens=10)

    assert excinfo.value.code == "llm.failed"


def test_non_json_response_maps_to_invalid_output():
    client = OpenAICompatibleChatClient(
        _llm(),
        client=_client(
            lambda request: httpx.Response(
                200, text="<html>not json</html>", headers={"content-type": "text/html"}
            )
        ),
    )

    with pytest.raises(ProcessingError) as excinfo:
        client.complete([{"role": "user", "content": "hello"}], max_tokens=10)

    assert excinfo.value.code == "llm.invalid_output"


def test_missing_usage_and_choices_use_empty_defaults():
    client = OpenAICompatibleChatClient(
        _llm(), client=_client(lambda request: httpx.Response(200, json={}))
    )

    result = client.complete([{"role": "user", "content": "hello"}], max_tokens=10)

    assert result == ChatResult(content="", input_tokens=0, output_tokens=0)
