from __future__ import annotations


def locate_url(item_id: str, source_type: str, doc_kind: str, ref: str) -> str:
    if doc_kind == "transcript":
        seq = ref.split(":", 1)[0]
        if seq.isdigit():
            return f"/items/{item_id}/listen#segment-{seq}"
    if doc_kind == "book":
        parts = ref.split(":")
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            return f"/items/{item_id}/read?chapter={parts[0]}#paragraph-{parts[0]}-{parts[1]}"
    if source_type == "epub":
        return f"/items/{item_id}/read"
    return f"/items/{item_id}/listen"
