from __future__ import annotations

import json
from typing import Any

from trove.config import CONFIG_FILENAME, DEFAULT_HOME, LLMConfig
from trove.domain.cache import AiCacheIdentity
from trove.domain.organization import (
    MAX_EXISTING_TAGS,
    MAX_TAGS_PER_ITEM,
    chunk_text,
    estimate_cost,
    estimate_tokens,
    fill_tags,
    normalize_tags,
    select_tags,
)
from trove.domain.organization_prompts import (
    MAP_INSTRUCTIONS,
    MAP_TAG_LIMIT,
    MAP_TAG_LIMIT_REUSE,
    PROMPT_VERSION,
    REDUCE_INSTRUCTIONS,
    SINGLE_INSTRUCTIONS,
    SINGLE_TAG_LIMIT,
    SINGLE_TAG_LIMIT_REUSE,
    build_messages,
)
from trove.errors import ProcessingError
from trove.ports import ChatClient, OrganizationResult, StageContext

JSON_ATTEMPTS = 2
PROMPT_OVERHEAD_TOKENS = 200


class OrganizationWorkflow:
    def __init__(self, llm: LLMConfig, chat_client: ChatClient) -> None:
        self.llm = llm
        self.chat_client = chat_client

    @property
    def cache_identity(self) -> AiCacheIdentity | None:
        if not self.llm.enabled:
            return None
        if not (self.llm.model and self.llm.base_url and self.llm.api_key):
            return None
        return AiCacheIdentity(model=self.llm.model, prompt_version=PROMPT_VERSION)

    def organize(
        self,
        *,
        text: str,
        title: str,
        existing_tags: list[str],
        context: StageContext,
        collection_title: str | None = None,
        collection_index: int | None = None,
        reuse_existing_tags: bool = False,
    ) -> OrganizationResult:
        llm = self.llm
        if not llm.enabled:
            return OrganizationResult(
                summary="", tags=[], model="disabled", prompt_version="disabled"
            )
        if not (llm.model and llm.base_url and llm.api_key):
            raise ProcessingError(
                "llm.not_configured",
                "LLM is not configured; set [llm] model, base_url, and api_key in "
                f"{DEFAULT_HOME / CONFIG_FILENAME}",
            )
        body = (text or "").strip()
        if not body:
            raise ProcessingError("llm.invalid_output", "No text to organize")
        chunks = chunk_text(body, llm.chunk_chars)
        calls = len(chunks) if len(chunks) == 1 else len(chunks) + 1
        if calls > llm.max_calls_per_item:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization needs {calls} calls; limit is "
                f"{llm.max_calls_per_item}",
            )
        estimated_input = (
            sum(estimate_tokens(chunk) for chunk in chunks)
            + PROMPT_OVERHEAD_TOKENS * calls
        )
        if estimated_input > llm.max_input_tokens_per_item:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization needs about {estimated_input} input tokens; limit is "
                f"{llm.max_input_tokens_per_item}",
            )
        vocabulary = normalize_tags(existing_tags, limit=MAX_EXISTING_TAGS)
        single_tag_limit = (
            SINGLE_TAG_LIMIT_REUSE if reuse_existing_tags else SINGLE_TAG_LIMIT
        )
        map_tag_limit = MAP_TAG_LIMIT_REUSE if reuse_existing_tags else MAP_TAG_LIMIT

        calls_used = 0
        if len(chunks) == 1:
            context.check_cancelled()
            payload, input_tokens, output_tokens, calls_used = self._call_json(
                title=title,
                instructions=SINGLE_INSTRUCTIONS,
                content=chunks[0],
                existing_tags=vocabulary,
                tag_limit=single_tag_limit,
                collection_title=collection_title,
                collection_index=collection_index,
                reuse_existing_tags=reuse_existing_tags,
                remaining_calls=llm.max_calls_per_item,
            )
            summary = _summary(payload)
            tags = select_tags(
                _tags(payload),
                existing_tags=vocabulary,
                allow_new=not reuse_existing_tags,
            )
        else:
            map_summaries: list[str] = []
            map_tags: list[str] = []
            input_tokens = 0
            output_tokens = 0
            for index, chunk in enumerate(chunks, start=1):
                context.check_cancelled()
                payload, used_input, used_output, used_calls = self._call_json(
                    title=title,
                    instructions=MAP_INSTRUCTIONS,
                    content=chunk,
                    existing_tags=vocabulary,
                    tag_limit=map_tag_limit,
                    collection_title=collection_title,
                    collection_index=collection_index,
                    reuse_existing_tags=reuse_existing_tags,
                    prefix=f"Chunk {index}/{len(chunks)}.",
                    remaining_calls=llm.max_calls_per_item - calls_used,
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
                title=title,
                instructions=REDUCE_INSTRUCTIONS,
                content=reduce_content,
                existing_tags=normalize_tags(vocabulary + map_tags, limit=MAX_EXISTING_TAGS),
                tag_limit=single_tag_limit,
                collection_title=collection_title,
                collection_index=collection_index,
                reuse_existing_tags=reuse_existing_tags,
                remaining_calls=llm.max_calls_per_item - calls_used,
            )
            input_tokens += used_input
            output_tokens += used_output
            calls_used += used_calls
            summary = _summary(payload)
            tags = select_tags(
                _tags(payload) + map_tags,
                existing_tags=vocabulary,
                allow_new=not reuse_existing_tags,
            )
        if reuse_existing_tags:
            tags = fill_tags(
                tags,
                vocabulary=vocabulary,
                limit=MAX_TAGS_PER_ITEM,
            )

        if input_tokens > llm.max_input_tokens_per_item:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization used {input_tokens} input tokens; limit is "
                f"{llm.max_input_tokens_per_item}",
            )

        return OrganizationResult(
            summary=summary,
            tags=tags,
            model=llm.model,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(
                input_tokens,
                output_tokens,
                llm.input_cost_per_million,
                llm.output_cost_per_million,
            ),
        )

    def _call_json(
        self,
        *,
        title: str,
        instructions: str,
        content: str,
        existing_tags: list[str],
        tag_limit: str,
        collection_title: str | None = None,
        collection_index: int | None = None,
        reuse_existing_tags: bool = False,
        prefix: str = "",
        remaining_calls: int,
    ) -> tuple[dict[str, Any], int, int, int]:
        if remaining_calls <= 0:
            raise ProcessingError(
                "llm.limit_exceeded",
                f"Organization exceeded {self.llm.max_calls_per_item} calls",
            )
        messages = build_messages(
            title=title,
            instructions=instructions,
            content=content,
            existing_tags=existing_tags,
            tag_limit=tag_limit,
            collection_title=collection_title,
            collection_index=collection_index,
            reuse_existing_tags=reuse_existing_tags,
            prefix=prefix,
        )
        input_tokens = 0
        output_tokens = 0
        last_error: Exception | None = None
        max_attempts = min(JSON_ATTEMPTS, remaining_calls)
        for attempt in range(max_attempts):
            response = self.chat_client.complete(
                messages, max_tokens=self.llm.max_output_tokens_per_call
            )
            if response.finish_reason == "length":
                raise ProcessingError(
                    "llm.limit_exceeded",
                    f"Model reached max_tokens={self.llm.max_output_tokens_per_call} "
                    "before returning a complete answer",
                )
            input_tokens += response.input_tokens
            output_tokens += response.output_tokens
            if response.output_tokens > self.llm.max_output_tokens_per_call:
                raise ProcessingError(
                    "llm.limit_exceeded",
                    f"Model returned {response.output_tokens} output tokens in one call; "
                    f"limit is {self.llm.max_output_tokens_per_call}",
                )
            if not response.content.strip():
                last_error = ValueError("empty response")
                continue
            try:
                parsed = json.loads(response.content)
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
                f"Organization exceeded {self.llm.max_calls_per_item} calls",
            )
        raise ProcessingError(
            "llm.invalid_output",
            f"Organization output is invalid: {last_error}",
        ) from last_error


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
