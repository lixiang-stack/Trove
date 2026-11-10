from __future__ import annotations

import json
from typing import Any

import httpx

from trove.config import Config, ConfigError, resolve_llm_api_key
from trove.domain.organization import (
    MAX_EXISTING_TAGS,
    chunk_text,
    estimate_cost,
    estimate_tokens,
    normalize_tags,
)
from trove.errors import ProcessingError
from trove.ports import OrganizationResult, StageContext

PROMPT_VERSION = "organize-1"
PROMPT_OVERHEAD_TOKENS = 200
JSON_ATTEMPTS = 2

SYSTEM_PROMPT = (
    "You organize a personal library. Return only a JSON object with "
    '"summary" (1-2 sentences) and "tags" (3-5 short, reusable tags). '
    "Prefer reusing the provided existing tags when they fit. "
    "Do not include markdown or commentary."
)

MAP_INSTRUCTIONS = (
    "Summarize this chunk of a longer work in one sentence and propose up to "
    "three reusable tags. Return only JSON with keys summary and tags."
)

SINGLE_INSTRUCTIONS = (
    "Summarize the full content in 1-2 sentences and propose 3-5 reusable tags. "
    "Return only JSON with keys summary and tags."
)

REDUCE_INSTRUCTIONS = (
    "Combine the chunk summaries into one 1-2 sentence summary that covers the "
    "whole work. Propose 3-5 reusable tags, preferring the existing tag "
    "vocabulary. Return only JSON with keys summary and tags."
)


class DeepSeekOrganizer:
    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client

    def organize(
        self,
        *,
        text: str,
        title: str,
        existing_tags: list[str],
        context: StageContext,
    ) -> OrganizationResult:
        if not self.config.llm_enabled:
            return OrganizationResult(
                summary="", tags=[], model="disabled", prompt_version="disabled"
            )
        try:
            api_key = resolve_llm_api_key(self.config)
        except ConfigError as exc:
            raise ProcessingError("llm.not_configured", str(exc)) from exc
        if not api_key:
            raise ProcessingError(
                "llm.not_configured",
                f"DeepSeek API key is not configured; write it to "
                f"{self.config.llm_api_key_path}",
            )
        body = (text or "").strip()
        if not body:
            raise ProcessingError("llm.invalid_output", "No text to organize")
        chunks = chunk_text(body, self.config.llm_chunk_chars)
        calls = len(chunks) if len(chunks) == 1 else len(chunks) + 1
        if calls > self.config.llm_max_calls_per_item:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization needs {calls} calls; limit is "
                f"{self.config.llm_max_calls_per_item}",
            )
        estimated_input = (
            sum(estimate_tokens(chunk) for chunk in chunks)
            + PROMPT_OVERHEAD_TOKENS * calls
        )
        if estimated_input > self.config.llm_max_input_tokens_per_item:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization needs about {estimated_input} input tokens; limit is "
                f"{self.config.llm_max_input_tokens_per_item}",
            )
        vocabulary = normalize_tags(existing_tags, limit=MAX_EXISTING_TAGS)

        client = self.client or httpx.Client(timeout=self.config.llm_timeout_seconds)
        calls_used = 0
        try:
            if len(chunks) == 1:
                context.check_cancelled()
                payload, input_tokens, output_tokens, calls_used = self._call_json(
                    client,
                    api_key,
                    title=title,
                    instructions=SINGLE_INSTRUCTIONS,
                    content=chunks[0],
                    existing_tags=vocabulary,
                    tag_limit="3-5 tags",
                    remaining_calls=self.config.llm_max_calls_per_item,
                )
                summary = _summary(payload)
                tags = _tags(payload)
            else:
                map_summaries: list[str] = []
                map_tags: list[str] = []
                input_tokens = 0
                output_tokens = 0
                for index, chunk in enumerate(chunks, start=1):
                    context.check_cancelled()
                    payload, used_input, used_output, used_calls = self._call_json(
                        client,
                        api_key,
                        title=title,
                        instructions=MAP_INSTRUCTIONS,
                        content=chunk,
                        existing_tags=vocabulary,
                        tag_limit="up to 3 tags",
                        prefix=f"Chunk {index}/{len(chunks)}.",
                        remaining_calls=self.config.llm_max_calls_per_item - calls_used,
                    )
                    input_tokens += used_input
                    output_tokens += used_output
                    calls_used += used_calls
                    map_summaries.append(_summary(payload))
                    map_tags.extend(_tags(payload))
                reduce_content = "\n".join(
                    f"{index}. {summary}"
                    for index, summary in enumerate(map_summaries, start=1)
                )
                payload, used_input, used_output, used_calls = self._call_json(
                    client,
                    api_key,
                    title=title,
                    instructions=REDUCE_INSTRUCTIONS,
                    content=reduce_content,
                    existing_tags=normalize_tags(vocabulary + map_tags, limit=MAX_EXISTING_TAGS),
                    tag_limit="3-5 tags",
                    remaining_calls=self.config.llm_max_calls_per_item - calls_used,
                )
                input_tokens += used_input
                output_tokens += used_output
                calls_used += used_calls
                summary = _summary(payload)
                tags = normalize_tags(_tags(payload) + map_tags)
        finally:
            if self.client is None:
                client.close()

        if input_tokens > self.config.llm_max_input_tokens_per_item:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization used {input_tokens} input tokens; limit is "
                f"{self.config.llm_max_input_tokens_per_item}",
            )

        return OrganizationResult(
            summary=summary,
            tags=tags,
            model=self.config.llm_model,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(
                input_tokens,
                output_tokens,
                self.config.llm_input_cost_per_million,
                self.config.llm_output_cost_per_million,
            ),
        )

    def _call_json(
        self,
        client: httpx.Client,
        api_key: str,
        *,
        title: str,
        instructions: str,
        content: str,
        existing_tags: list[str],
        tag_limit: str,
        prefix: str = "",
        remaining_calls: int,
    ) -> tuple[dict[str, Any], int, int, int]:
        if remaining_calls <= 0:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization exceeded {self.config.llm_max_calls_per_item} calls",
            )
        prompt = _prompt(
            title=title,
            instructions=instructions,
            content=content,
            existing_tags=existing_tags,
            tag_limit=tag_limit,
            prefix=prefix,
        )
        request_body = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.config.llm_max_output_tokens_per_call,
            "temperature": 0.2,
        }
        input_tokens = 0
        output_tokens = 0
        last_error: Exception | None = None
        max_attempts = min(JSON_ATTEMPTS, remaining_calls)
        for attempt in range(max_attempts):
            response = self._post(client, api_key, request_body)
            payload = response.get("choices") or []
            content_value = ""
            if payload:
                message = payload[0].get("message") or {}
                content_value = str(message.get("content") or "")
            usage = response.get("usage") or {}
            attempt_input = int(usage.get("prompt_tokens") or 0)
            attempt_output = int(usage.get("completion_tokens") or 0)
            input_tokens += attempt_input
            output_tokens += attempt_output
            if attempt_output > self.config.llm_max_output_tokens_per_call:
                raise ProcessingError(
                    "llm.limit_exceeded",
                    f"Model returned {attempt_output} output tokens in one call; limit is "
                    f"{self.config.llm_max_output_tokens_per_call}",
                )
            if not content_value.strip():
                last_error = ValueError("empty response")
                continue
            try:
                parsed = json.loads(content_value)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if not isinstance(parsed, dict):
                last_error = ValueError("JSON response is not an object")
                continue
            if not isinstance(parsed.get("summary"), str) or not isinstance(
                parsed.get("tags"), list
            ):
                last_error = ValueError("JSON response is missing summary or tags")
                continue
            return parsed, input_tokens, output_tokens, attempt + 1
        if max_attempts < JSON_ATTEMPTS:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization exceeded {self.config.llm_max_calls_per_item} calls",
            )
        raise ProcessingError(
            "llm.invalid_output",
            f"Organization output is invalid: {last_error}",
        ) from last_error

    def _post(
        self, client: httpx.Client, api_key: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = client.post(
                f"{self.config.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProcessingError("llm.failed", f"Organization request failed: {exc}") from exc
        if response.status_code in {401, 403}:
            raise ProcessingError(
                "llm.not_configured", "DeepSeek rejected the configured API key"
            )
        if response.status_code >= 400:
            raise ProcessingError(
                "llm.failed", f"Organization request failed with HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProcessingError(
                "llm.invalid_output", "Organization response was not JSON"
            ) from exc
        if not isinstance(data, dict):
            raise ProcessingError("llm.invalid_output", "Organization response was not JSON")
        return data


def _prompt(
    *,
    title: str,
    instructions: str,
    content: str,
    existing_tags: list[str],
    tag_limit: str,
    prefix: str,
) -> str:
    vocabulary = ", ".join(existing_tags) if existing_tags else "(none yet)"
    lead = f"{prefix} " if prefix else ""
    return (
        f"{lead}{instructions}\n\n"
        f"Title: {title}\n"
        f"Existing tags: {vocabulary}\n"
        f"Requested tags: {tag_limit}\n\n"
        f"Content:\n{content}"
    )


def _summary(payload: dict[str, Any]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ProcessingError("llm.invalid_output", "Organization output has no summary")
    return summary.strip()


def _tags(payload: dict[str, Any]) -> list[str]:
    tags = payload.get("tags")
    if not isinstance(tags, list):
        return []
    return normalize_tags([str(tag) for tag in tags])
