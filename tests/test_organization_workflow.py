from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from trove.config import LLMConfig
from trove.domain.organization import chunk_text, estimate_cost
from trove.domain.organization_prompts import PROMPT_VERSION
from trove.errors import ProcessingError
from trove.ports import ChatResult, StageContext
from trove.services.organization import OrganizationWorkflow


@dataclass(slots=True)
class FakeCall:
    messages: list[dict[str, str]]
    max_tokens: int


class FakeChatClient:
    def __init__(self, responses: list[ChatResult | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[FakeCall] = []

    def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int
    ) -> ChatResult:
        self.calls.append(FakeCall(messages=messages, max_tokens=max_tokens))
        assert self.responses, "fake ChatClient ran out of responses"
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _context(tmp_path) -> StageContext:
    return StageContext(
        item_id="item-1",
        run_id="run-1",
        work_dir=tmp_path,
        should_cancel=lambda: False,
        log=lambda message: None,
    )


def _llm(**overrides) -> LLMConfig:
    values = {
        "model": "deepseek-flash",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-key",
    }
    values.update(overrides)
    return LLMConfig(**values)


def _result(
    summary: str = "摘要",
    tags: list[str] | None = None,
    *,
    input_tokens: int = 10,
    output_tokens: int = 5,
    finish_reason: str | None = "stop",
) -> ChatResult:
    return ChatResult(
        content=json.dumps({"summary": summary, "tags": tags or ["tag"]}),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason=finish_reason,
    )


def test_single_chunk_uses_one_call_and_records_cost(tmp_path):
    chat = FakeChatClient([_result("摘要", ["Alpha"], input_tokens=100, output_tokens=20)])
    workflow = OrganizationWorkflow(_llm(chunk_chars=1_000), chat)

    result = workflow.organize(
        text="短文本",
        title="标题",
        existing_tags=["智能体"],
        context=_context(tmp_path),
    )

    assert len(chat.calls) == 1
    assert chat.calls[0].max_tokens == 1024
    assert "短文本" in chat.calls[0].messages[1]["content"]
    assert result.summary == "摘要"
    assert result.tags == ["Alpha"]
    assert result.model == "deepseek-flash"
    assert result.prompt_version == PROMPT_VERSION
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.cost_usd == estimate_cost(100, 20, 0.28, 0.42)


def test_tags_prefer_the_existing_vocabulary_and_cap_new_tags(tmp_path):
    chat = FakeChatClient([_result("摘要", ["单集主题", "道家哲学", "另一个新主题"])])
    workflow = OrganizationWorkflow(_llm(), chat)

    result = workflow.organize(
        text="短文本",
        title="tags",
        existing_tags=["道德经", "道家哲学"],
        context=_context(tmp_path),
    )

    assert result.tags == ["单集主题", "道家哲学"]


def test_long_text_maps_every_chunk_then_reduces(tmp_path):
    text = "\n".join(f"chunk-{index} " + "内容" * 30 for index in range(6))
    llm = _llm(chunk_chars=120)
    chunks = chunk_text(text.strip(), llm.chunk_chars)
    responses = [_result(f"map {index}", ["Beta"]) for index in range(len(chunks))]
    responses.append(_result("覆盖全文的最终摘要。", ["Alpha", "Beta"]))
    chat = FakeChatClient(responses)
    workflow = OrganizationWorkflow(llm, chat)

    result = workflow.organize(
        text=text,
        title="长内容",
        existing_tags=[],
        context=_context(tmp_path),
    )

    assert len(chat.calls) == len(chunks) + 1
    prompts = [call.messages[1]["content"] for call in chat.calls]
    for index in range(len(chunks)):
        assert f"Chunk {index + 1}/{len(chunks)}." in prompts[index]
        assert f"chunk-{index}" in prompts[index]
    assert "Combine the chunk summaries" in prompts[-1]
    assert "1. map 0" in prompts[-1]
    assert result.summary == "覆盖全文的最终摘要。"
    assert result.tags == ["Alpha", "Beta"]
    assert result.input_tokens == (len(chunks) + 1) * 10
    assert result.output_tokens == (len(chunks) + 1) * 5


def test_empty_text_fails_without_calling_the_client(tmp_path):
    chat = FakeChatClient([])
    workflow = OrganizationWorkflow(_llm(), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="   ",
            title="empty",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.invalid_output"
    assert not chat.calls


def test_transport_failures_propagate_without_a_json_retry(tmp_path):
    chat = FakeChatClient([ProcessingError("llm.failed", "HTTP 429")])
    workflow = OrganizationWorkflow(_llm(), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="短文本",
            title="transport",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.failed"
    assert len(chat.calls) == 1


def test_invalid_json_is_retried_once_then_fails(tmp_path):
    chat = FakeChatClient(
        [
            ChatResult(content="not json"),
            ChatResult(content="still not json"),
        ]
    )
    workflow = OrganizationWorkflow(_llm(), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="短文本",
            title="invalid",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.invalid_output"
    assert len(chat.calls) == 2


@pytest.mark.parametrize(
    "content",
    [
        '{"tags": ["tag"]}',
        '{"summary": "摘要"}',
        "[]",
    ],
)
def test_malformed_payloads_are_retried_then_fail(tmp_path, content):
    chat = FakeChatClient([ChatResult(content=content), ChatResult(content=content)])
    workflow = OrganizationWorkflow(_llm(), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="短文本",
            title="malformed",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.invalid_output"
    assert len(chat.calls) == 2


def test_call_limit_fails_before_sending_requests(tmp_path):
    chat = FakeChatClient([])
    workflow = OrganizationWorkflow(
        _llm(chunk_chars=10, max_calls_per_item=2), chat
    )

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="长文本" * 20,
            title="limit",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.limit_exceeded"
    assert not chat.calls


def test_input_token_limit_fails_before_sending_requests(tmp_path):
    chat = FakeChatClient([])
    workflow = OrganizationWorkflow(_llm(max_input_tokens_per_item=5), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="记忆" * 100,
            title="tokens",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.limit_exceeded"
    assert not chat.calls


def test_output_token_limit_fails_after_the_call(tmp_path):
    chat = FakeChatClient([_result(output_tokens=11)])
    workflow = OrganizationWorkflow(_llm(max_output_tokens_per_call=10), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="短文本",
            title="tokens",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.limit_exceeded"
    assert len(chat.calls) == 1


def test_length_finish_reason_fails_as_limit_exceeded(tmp_path):
    chat = FakeChatClient([_result(finish_reason="length")])
    workflow = OrganizationWorkflow(_llm(max_output_tokens_per_call=10), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="短文本",
            title="length",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.limit_exceeded"
    assert len(chat.calls) == 1


def test_invalid_json_retry_counts_toward_the_call_limit(tmp_path):
    chat = FakeChatClient([ChatResult(content="not json")])
    workflow = OrganizationWorkflow(_llm(max_calls_per_item=1), chat)

    with pytest.raises(ProcessingError) as excinfo:
        workflow.organize(
            text="短文本",
            title="retry limit",
            existing_tags=[],
            context=_context(tmp_path),
        )

    assert excinfo.value.code == "llm.limit_exceeded"
    assert len(chat.calls) == 1
