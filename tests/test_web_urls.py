from __future__ import annotations

from trove.web.urls import locate_url


def test_locate_urls_use_stable_evidence_refs():
    assert (
        locate_url("item-1", "video_url", "transcript", "3:65000")
        == "/items/item-1/listen#segment-3"
    )
    assert (
        locate_url("item-1", "epub", "book", "2:4")
        == "/items/item-1/read?chapter=2#paragraph-2-4"
    )
    assert locate_url("item-1", "video_url", "title", "title") == "/items/item-1/listen"
    assert locate_url("item-1", "epub", "title", "title") == "/items/item-1/read"
