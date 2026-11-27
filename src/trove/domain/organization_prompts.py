from __future__ import annotations

PROMPT_VERSION = "organize-3"

SINGLE_TAG_LIMIT = "2-3 个标签"
SINGLE_TAG_LIMIT_REUSE = "2-3 个现有标签"
MAP_TAG_LIMIT = "最多 2 个标签"
MAP_TAG_LIMIT_REUSE = "最多 2 个现有标签"

SYSTEM_PROMPT = (
    "你负责整理个人内容库。只返回一个 JSON 对象，包含 "
    '"summary"（1-2 句话）和 "tags"（2-3 个简短、可复用的标签）。'
    "摘要和标签必须使用简体中文，即使原文是英文。"
    "优先复用提供的现有标签；只有在现有标签都不合适时才提出新标签，"
    "每条内容最多提出一个新标签；不要用单集标题、章节名或一次性短语作为标签。"
    "不要输出 Markdown 或额外说明。"
)

MAP_INSTRUCTIONS = (
    "用一句话概括这段较长内容的一部分，并提出最多两个可复用标签。"
    "只返回 JSON，键为 summary 和 tags。"
)

SINGLE_INSTRUCTIONS = (
    "用 1-2 句话概括完整内容，并提出 2-3 个可复用标签。"
    "只返回 JSON，键为 summary 和 tags。"
)

REDUCE_INSTRUCTIONS = (
    "把各段摘要合并成一段 1-2 句话的完整摘要。"
    "提出 2-3 个可复用标签，优先复用现有标签。"
    "只返回 JSON，键为 summary 和 tags。"
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
    vocabulary = "、".join(existing_tags) if existing_tags else "（暂无）"
    lead = f"{prefix} " if prefix else ""
    collection = ""
    if collection_title:
        position = f"（第 {collection_index} 集）" if collection_index is not None else ""
        collection = (
            f"合集：{collection_title}{position}\n"
            "标签描述合集或系列，而不是单集。\n"
        )
    reuse = "只使用现有标签。\n" if reuse_existing_tags else ""
    return (
        f"{lead}{instructions}\n\n"
        f"标题：{title}\n"
        f"{collection}{reuse}"
        f"现有标签：{vocabulary}\n"
        f"要求的标签数：{tag_limit}\n\n"
        f"内容：\n{content}"
    )
