from __future__ import annotations

import json

import httpx
import pytest

from trove.adapters.deepseek import DeepSeekOrganizer
from trove.config import Config, resolve_llm_api_key
from trove.domain.organization import (
    chunk_text,
    estimate_cost,
    estimate_tokens,
    normalize_tags,
)
from trove.errors import ProcessingError
from trove.ports import StageContext

from .conftest import seed_item


def _context(tmp_path) -> StageContext:
    return StageContext(
        item_id="item-1",
        run_id="run-1",
        work_dir=tmp_path,
        should_cancel=lambda: False,
        log=lambda message: None,
    )


def test_chunk_text_preserves_every_character_and_respects_the_limit():
    text = "第一段" * 12 + "\n" + "second paragraph " * 9 + "\n" + "尾" * 25
    chunks = chunk_text(text, 20)
    assert chunks
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert "".join(chunks) == text


def test_tag_normalization_deduplicates_case_and_plural_forms():
    assert normalize_tags(["#LLM", "llm", "Agents", "agent", "记忆"]) == [
        "LLM",
        "Agents",
        "记忆",
    ]


def test_cost_is_derived_from_token_usage():
    assert estimate_cost(1_000_000, 1_000_000, 0.28, 0.42) == pytest.approx(0.70)
    assert estimate_tokens("记忆" * 10) > estimate_tokens("hello world")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _json_response(summary: str, tags: list[str], *, input_tokens=50, output_tokens=20):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps({"summary": summary, "tags": tags})}}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
        },
    )


def _config(tmp_path) -> Config:
    key_path = tmp_path / "llm_api_key"
    if not key_path.exists():
        key_path.write_text("test-key", encoding="utf-8")
    config = Config(home=tmp_path)
    config.llm_api_key_path = key_path
    return config


def test_environment_key_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-key")
    config = Config(home=tmp_path)
    config.llm_api_key_path = tmp_path / "missing-llm-api-key"
    organizer = DeepSeekOrganizer(
        config, client=_client(lambda request: _json_response("unexpected", ["tag"]))
    )
    with pytest.raises(ProcessingError) as excinfo:
        organizer.organize(
            text="短文本",
            title="env ignored",
            existing_tags=[],
            context=_context(tmp_path),
        )
    assert excinfo.value.code == "llm.not_configured"


def test_short_text_uses_one_json_mode_call_and_records_usage(tmp_path):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert body["response_format"] == {"type": "json_object"}
        assert body["model"] == "deepseek-flash"
        assert request.headers["authorization"] == "Bearer test-key"
        return _json_response("关于记忆的讨论。", ["#记忆", "Memory"])

    config = _config(tmp_path)
    organizer = DeepSeekOrganizer(config, client=_client(handler))
    result = organizer.organize(
        text="短文本内容",
        title="短内容",
        existing_tags=["智能体"],
        context=_context(tmp_path),
    )
    assert result.summary == "关于记忆的讨论。"
    assert result.tags == ["记忆", "Memory"]
    assert result.model == "deepseek-flash"
    assert result.prompt_version
    assert result.input_tokens == 50
    assert result.output_tokens == 20
    assert result.cost_usd > 0
    assert len(requests) == 1
    assert "智能体" in requests[0]["messages"][1]["content"]


def test_long_text_is_mapped_and_reduced_without_dropping_chunks(tmp_path):
    requests: list[dict] = []
    text = "\n".join(f"chunk-{index} " + "内容" * 30 for index in range(6))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        prompt = body["messages"][1]["content"]
        if "Combine the chunk summaries" in prompt:
            return _json_response("覆盖全文的最终摘要。", ["Alpha", "Beta"])
        return _json_response(f"map summary {len(requests)}", ["Beta"])

    config = _config(tmp_path)
    config.llm_chunk_chars = 120
    organizer = DeepSeekOrganizer(config, client=_client(handler))
    result = organizer.organize(
        text=text,
        title="长内容",
        existing_tags=[],
        context=_context(tmp_path),
    )
    assert result.summary == "覆盖全文的最终摘要。"
    assert result.tags == ["Alpha", "Beta"]
    assert len(requests) > 2
    combined = "\n".join(body["messages"][1]["content"] for body in requests)
    for index in range(6):
        assert f"chunk-{index}" in combined


def test_call_limit_fails_before_sending_requests(tmp_path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response("ok", ["tag"])

    config = _config(tmp_path)
    config.llm_chunk_chars = 10
    config.llm_max_calls_per_item = 2
    organizer = DeepSeekOrganizer(config, client=_client(handler))
    with pytest.raises(ProcessingError) as excinfo:
        organizer.organize(
            text="长文本" * 20,
            title="limit",
            existing_tags=[],
            context=_context(tmp_path),
        )
    assert excinfo.value.code == "llm.limit_exceeded"
    assert calls == 0


def test_input_token_limit_fails_explicitly(tmp_path):
    config = _config(tmp_path)
    config.llm_max_input_tokens_per_item = 5
    organizer = DeepSeekOrganizer(
        config, client=_client(lambda request: _json_response("ok", ["tag"]))
    )
    with pytest.raises(ProcessingError) as excinfo:
        organizer.organize(
            text="记忆" * 100,
            title="tokens",
            existing_tags=[],
            context=_context(tmp_path),
        )
    assert excinfo.value.code == "llm.limit_exceeded"


def test_output_token_limit_fails_explicitly(tmp_path):
    config = _config(tmp_path)
    config.llm_max_output_tokens_per_call = 10
    organizer = DeepSeekOrganizer(
        config,
        client=_client(lambda request: _json_response("ok", ["tag"], output_tokens=11)),
    )
    with pytest.raises(ProcessingError) as excinfo:
        organizer.organize(
            text="短文本",
            title="tokens",
            existing_tags=[],
            context=_context(tmp_path),
        )
    assert excinfo.value.code == "llm.limit_exceeded"


def test_blank_json_is_retried_once(tmp_path):
    responses = [
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}], "usage": {}}),
        _json_response("retry worked", ["tag"]),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    config = _config(tmp_path)
    organizer = DeepSeekOrganizer(config, client=_client(handler))
    result = organizer.organize(
        text="短文本",
        title="retry",
        existing_tags=[],
        context=_context(tmp_path),
    )
    assert result.summary == "retry worked"
    assert not responses


def test_blank_json_retry_counts_toward_the_call_limit(tmp_path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}], "usage": {}})

    config = _config(tmp_path)
    config.llm_max_calls_per_item = 1
    organizer = DeepSeekOrganizer(config, client=_client(handler))
    with pytest.raises(ProcessingError) as excinfo:
        organizer.organize(
            text="短文本",
            title="retry limit",
            existing_tags=[],
            context=_context(tmp_path),
        )
    assert excinfo.value.code == "llm.limit_exceeded"
    assert calls == 1


def test_persistent_invalid_json_fails(tmp_path):

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}], "usage": {}}
        )

    config = _config(tmp_path)
    organizer = DeepSeekOrganizer(config, client=_client(handler))
    with pytest.raises(ProcessingError) as excinfo:
        organizer.organize(
            text="短文本",
            title="invalid",
            existing_tags=[],
            context=_context(tmp_path),
        )
    assert excinfo.value.code == "llm.invalid_output"


def test_disabled_llm_returns_an_empty_result(tmp_path):
    config = Config(home=tmp_path, llm_enabled=False)
    organizer = DeepSeekOrganizer(config)
    result = organizer.organize(
        text="短文本",
        title="disabled",
        existing_tags=[],
        context=_context(tmp_path),
    )
    assert result.summary == ""
    assert result.tags == []
    assert result.model == "disabled"


@pytest.mark.ffmpeg
def test_reprocess_only_reruns_organizing_and_indexing(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    assert host.stack.organizer.calls
    calls_before = len(host.stack.organizer.calls)
    downloads_before = len(host.stack.downloader.calls)
    transcriptions_before = len(host.stack.transcriber.calls)

    host.stack.organizer.summary = "新的摘要。"
    host.stack.organizer.tags = ["新标签"]
    reprocess = host.client.post(
        f"/api/items/{item_id}/reprocess", json={"from_stage": "organizing"}
    )
    assert reprocess.status_code == 202, reprocess.text
    payload = host.wait_for_item(item_id)
    assert payload["summary"] == "新的摘要。"
    assert payload["tags"] == ["新标签"]
    assert len(host.stack.organizer.calls) == calls_before + 1
    assert len(host.stack.downloader.calls) == downloads_before
    assert len(host.stack.transcriber.calls) == transcriptions_before
    stages = [step["stage"] for step in payload["run"]["steps"] if step["state"] == "completed"]
    assert "organizing" in stages and "indexing" in stages


@pytest.mark.ffmpeg
def test_reprocess_organizing_reads_package_transcript(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=packageorganize"}
    )
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    calls_before = len(host.stack.organizer.calls)

    reprocess = host.client.post(
        f"/api/items/{item_id}/reprocess", json={"from_stage": "organizing"}
    )
    assert reprocess.status_code == 202, reprocess.text
    host.wait_for_item(item_id)

    assert len(host.stack.organizer.calls) == calls_before + 1
    assert "为什么智能体的瓶颈不是模型" in host.stack.organizer.calls[-1]


@pytest.mark.ffmpeg
def test_ai_result_metadata_is_exposed(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    payload = host.item(item_id)
    assert payload["ai"]["model"] == "fake-model"
    assert payload["ai"]["prompt_version"] == "test-1"
    assert payload["ai"]["input_tokens"] == 120
    assert payload["ai"]["output_tokens"] == 30
    assert payload["ai"]["cost_usd"] == pytest.approx(0.0001)
    assert payload["ai"]["generated_at"] > 0
    ai_json = json.loads(
        (host.config.library_dir / item_id / "ai.json").read_text(encoding="utf-8")
    )
    assert ai_json["generated_at"] == payload["ai"]["generated_at"]
    detail = host.client.get(f"/items/{item_id}")
    assert "fake-model" in detail.text
    assert "test-1" in detail.text


@pytest.mark.ffmpeg
def test_llm_limit_failure_keeps_audio_and_transcript_usable(host):
    host.stack.organizer.fail_code = "llm.limit_exceeded"
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "failed"
    assert payload["run"]["error_code"] == "llm.limit_exceeded"
    assert host.client.get(f"/api/items/{item_id}/audio").status_code == 200
    transcript = host.client.get(f"/api/items/{item_id}/transcript").json()
    assert transcript["segments"]
    assert host.client.get("/api/search", params={"q": "记忆"}).json()["count"] == 1
    detail = host.client.get(f"/items/{item_id}")
    assert "llm.limit_exceeded" in detail.text


def test_reprocess_rejects_unknown_items_and_stages(host):
    host.login()
    missing = host.client.post("/api/items/missing/reprocess", json={"from_stage": "organizing"})
    assert missing.status_code == 404
    bundle = seed_item(host, title="Invalid reprocess")
    invalid = host.client.post(
        f"/api/items/{bundle.item.id}/reprocess", json={"from_stage": "downloading"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["details"]["code"] == "reprocess.invalid_stage"


def test_seeded_item_without_organizing_has_no_ai_payload(host):
    bundle = seed_item(host, title="No AI")
    host.login()
    assert host.item(bundle.item.id)["ai"] is None


@pytest.mark.network
def test_real_deepseek_smoke(tmp_path):
    config = Config(home=tmp_path)
    if not resolve_llm_api_key(config):
        pytest.skip(f"DeepSeek key file is missing: {config.llm_api_key_path}")
    organizer = DeepSeekOrganizer(config)
    result = organizer.organize(
        text="记忆是智能体的瓶颈。上下文窗口是临时的，记忆需要被选择、压缩和遗忘。",
        title="记忆与智能体",
        existing_tags=["智能体"],
        context=_context(tmp_path),
    )
    assert result.summary
    assert 1 <= len(result.tags) <= 5
    assert result.input_tokens > 0
    assert result.output_tokens > 0
