from __future__ import annotations

PROMPT_VERSION = "organize-2"

SINGLE_TAG_LIMIT = "2-3 tags"
SINGLE_TAG_LIMIT_REUSE = "2-3 existing tags"
MAP_TAG_LIMIT = "up to 2 tags"
MAP_TAG_LIMIT_REUSE = "up to 2 existing tags"

SYSTEM_PROMPT = (
    "You organize a personal library. Return only a JSON object with "
    '"summary" (1-2 sentences) and "tags" (2-3 short, reusable tags). '
    "Prefer tags from the provided existing tags. Only propose a new tag when "
    "no existing tag fits, at most one per item, and never use episode titles, "
    "chapter names, or one-off phrases as tags. "
    "Do not include markdown or commentary."
)

MAP_INSTRUCTIONS = (
    "Summarize this chunk of a longer work in one sentence and propose up to "
    "two reusable tags. Return only JSON with keys summary and tags."
)

SINGLE_INSTRUCTIONS = (
    "Summarize the full content in 1-2 sentences and propose 2-3 reusable tags. "
    "Return only JSON with keys summary and tags."
)

REDUCE_INSTRUCTIONS = (
    "Combine the chunk summaries into one 1-2 sentence summary that covers the "
    "whole work. Propose 2-3 reusable tags, preferring the existing tags. "
    "Return only JSON with keys summary and tags."
)


def build_messages(
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
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _prompt(
                title=title,
                instructions=instructions,
                content=content,
                existing_tags=existing_tags,
                tag_limit=tag_limit,
                collection_title=collection_title,
                collection_index=collection_index,
                reuse_existing_tags=reuse_existing_tags,
                prefix=prefix,
            ),
        },
    ]


def _prompt(
    *,
    title: str,
    instructions: str,
    content: str,
    existing_tags: list[str],
    tag_limit: str,
    collection_title: str | None = None,
    collection_index: int | None = None,
    reuse_existing_tags: bool = False,
    prefix: str,
) -> str:
    vocabulary = ", ".join(existing_tags) if existing_tags else "(none yet)"
    lead = f"{prefix} " if prefix else ""
    collection = ""
    if collection_title:
        position = f" (episode {collection_index})" if collection_index is not None else ""
        collection = (
            f"Collection: {collection_title}{position}\n"
            "Tags describe the collection or series, not the episode.\n"
        )
    reuse = "Use existing tags only.\n" if reuse_existing_tags else ""
    return (
        f"{lead}{instructions}\n\n"
        f"Title: {title}\n"
        f"{collection}{reuse}"
        f"Existing tags: {vocabulary}\n"
        f"Requested tags: {tag_limit}\n\n"
        f"Content:\n{content}"
    )
